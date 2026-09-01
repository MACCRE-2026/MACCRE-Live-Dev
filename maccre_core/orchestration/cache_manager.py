import hashlib
import json
import time
from typing import Any

from maccre_core.logger import logger
from maccre_core.orchestration.concurrency import atomic_write_text, file_lock, named_lock
from maccre_core.utils.path_resolver import get_datacenter_path

# To avoid circular imports, type hint generic Any for GeminiClient
# from maccre_core._net.gemini_client import GeminiClient


class CacheManager:
    """Manages the cross-process registry for Google GenAI Context Caching.

    Thread safety
    -------------
    :meth:`get_or_create_cache` is a read-modify-write over a shared JSON file
    with a **network upload in the middle**. Three separate hazards had to be
    closed for Phase 6.12:

    1. *Lost registry updates.* Two threads could both load the registry, both
       upload, and both save — the second save overwriting the first thread's new
       entry, leaking a paid cache that nothing would ever reference again.
    2. *Duplicate uploads.* An 8-wide scatter in ``full_copy`` mode gives every
       lane the **same** payload, so all eight compute the same hash and would
       each upload the same >120 kB context. Serialising per payload hash turns
       that into one upload and seven cache hits.
    3. *Silent registry loss.* ``_load_registry`` swallowed every exception and
       returned ``{}``. A torn read therefore looked like "no caches exist", and
       the next save persisted that empty dict — wiping every live entry with no
       error anywhere.
    """

    def __init__(self) -> None:
        self._registry_path = get_datacenter_path("02_Dynamic_Context", "active_caches.json")

    def _load_registry(self) -> dict[str, Any]:
        """Read the registry. Never silently discards a populated registry.

        A parse failure used to return ``{}``, which the next ``_save_registry``
        would then persist over the real data. Now the corrupt file is preserved
        for diagnosis and the loss is logged loudly. Writes are atomic, so a
        partially written registry should no longer be reachable — if this branch
        ever fires, something outside this class produced it.
        """
        if not self._registry_path.exists():
            return {}
        try:
            raw = self._registry_path.read_text(encoding="utf-8")
        except OSError as exc:
            logger.error(f"[CacheManager] Could not read cache registry: {exc}")
            return {}
        if not raw.strip():
            return {}
        try:
            data = json.loads(raw)
        except (json.JSONDecodeError, ValueError) as exc:
            corrupt_path = self._registry_path.with_suffix(".corrupt.json")
            try:
                corrupt_path.write_text(raw, encoding="utf-8")
            except OSError:
                corrupt_path = self._registry_path  # best effort only
            logger.error(
                "[CacheManager] Cache registry is unparseable (%s). "
                "Preserved a copy at %s and continuing with an empty registry — "
                "previously cached content will be re-uploaded.",
                exc, corrupt_path,
            )
            return {}
        if not isinstance(data, dict):
            logger.error(
                "[CacheManager] Cache registry is a %s, expected an object. Ignoring.",
                type(data).__name__,
            )
            return {}
        return data

    def _save_registry(self, data: dict[str, Any]) -> None:
        """Persist the registry atomically.

        A plain truncate-and-write left a window in which a concurrent reader saw
        a partial file — which ``_load_registry`` used to translate into "the
        registry is empty".
        """
        atomic_write_text(self._registry_path, json.dumps(data, indent=2))

    @staticmethod
    def _payload_hash(model: str, contents: list[dict[str, Any]]) -> str:
        """Stable key for a (model, context) pair."""
        hasher = hashlib.sha256()
        hasher.update(model.encode("utf-8"))
        for turn in contents:
            hasher.update(str(turn.get("role", "")).encode("utf-8"))
            for part in turn.get("parts", []):
                hasher.update(str(part.get("text", "")).encode("utf-8"))
        return hasher.hexdigest()

    def _lookup(self, payload_hash: str, current_time: float) -> str | None:
        """Return a live cache URI for *payload_hash*, purging it if expired.

        Holds the registry lock for the whole read-modify-write, so an expiry
        purge cannot race another thread's insert.
        """
        with file_lock(self._registry_path):
            registry = self._load_registry()
            entry = registry.get(payload_hash)
            if entry is None:
                return None
            expires_at = entry.get("expires_at", 0)
            # 5-minute safety buffer before expiration.
            if current_time < (expires_at - 300):
                logger.info(f"[CacheManager] Cache hit for payload. URI: {entry['cache_uri']}")
                return str(entry["cache_uri"])
            logger.info(
                f"[CacheManager] Cache {entry['cache_uri']} expired. Purging from registry."
            )
            del registry[payload_hash]
            self._save_registry(registry)
            return None

    def _record(self, payload_hash: str, cache_uri: str, model: str, expires_at: float) -> None:
        """Insert a new entry, re-reading first so concurrent inserts survive.

        Re-loading inside the lock is the fix for the lost-update hazard: the
        registry may have gained other threads' entries while this thread was
        uploading.
        """
        with file_lock(self._registry_path):
            registry = self._load_registry()
            registry[payload_hash] = {
                "cache_uri": cache_uri,
                "expires_at": expires_at,
                "model": model,
            }
            self._save_registry(registry)

    def get_or_create_cache(
        self,
        client: Any,
        model: str,
        contents: list[dict[str, Any]],
        system_instruction: str | None = None,
        ttl_seconds: int = 3600,
    ) -> str | None:
        """Retrieve an active Cache URI or create a new one.

        Args:
            client: An authenticated GeminiClient instance.
            model: The base model (e.g. 'gemini-1.5-pro-001').
            contents: The context payload.
            system_instruction: Ignored for caching purposes, to allow cross-agent hits.
            ttl_seconds: Time to live in seconds.

        Returns:
            The resource URI string ('cachedContents/abc123xyz') or None on failure.
        """
        payload_hash = self._payload_hash(model, contents)

        # Serialised per payload, not globally: identical payloads dedupe into a
        # single upload, while different payloads still upload concurrently.
        with named_lock(f"context_cache:{payload_hash}"):
            current_time = time.time()
            existing = self._lookup(payload_hash, current_time)
            if existing is not None:
                return existing

            # Cache miss — create new
            try:
                logger.info(
                    f"[CacheManager] Cache miss. Uploading {len(str(contents))} bytes "
                    "to Context Caching API..."
                )
                cache_uri = client.create_cached_content(
                    model=model,
                    contents=contents,
                    # Do not cache the system prompt so multiple agents can reuse the payload
                    system_instruction=None,
                    ttl_seconds=ttl_seconds,
                )
                self._record(payload_hash, cache_uri, model, current_time + ttl_seconds)
                logger.info(f"[CacheManager] Successfully created cache URI: {cache_uri}")
                return cache_uri

            except Exception as e:
                logger.error(f"[CacheManager] Failed to create cache: {e}")
                return None
