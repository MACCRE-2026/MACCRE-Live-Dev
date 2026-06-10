import hashlib
import json
import time
from typing import Any

from maccre_core.logger import logger
from maccre_core.utils.path_resolver import get_datacenter_path

# To avoid circular imports, type hint generic Any for GeminiClient
# from maccre_core._net.gemini_client import GeminiClient


class CacheManager:
    """Manages the cross-process registry for Google GenAI Context Caching."""

    def __init__(self) -> None:
        self._registry_path = get_datacenter_path("02_Dynamic_Context", "active_caches.json")

    def _load_registry(self) -> dict[str, Any]:
        if not self._registry_path.exists():
            return {}
        try:
            return json.loads(self._registry_path.read_text(encoding="utf-8"))
        except Exception:
            return {}

    def _save_registry(self, data: dict[str, Any]) -> None:
        self._registry_path.parent.mkdir(parents=True, exist_ok=True)
        self._registry_path.write_text(json.dumps(data, indent=2), encoding="utf-8")

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
        # Hash the contents + model to form a unique key
        hasher = hashlib.sha256()
        hasher.update(model.encode("utf-8"))
        
        # Hash the actual text inside the contents
        for turn in contents:
            hasher.update(str(turn.get("role", "")).encode("utf-8"))
            for part in turn.get("parts", []):
                hasher.update(str(part.get("text", "")).encode("utf-8"))
                
        payload_hash = hasher.hexdigest()
        
        registry = self._load_registry()
        current_time = time.time()
        
        # Check for existing valid cache
        if payload_hash in registry:
            entry = registry[payload_hash]
            expires_at = entry.get("expires_at", 0)
            # Give a 5-minute safety buffer before expiration
            if current_time < (expires_at - 300):
                logger.info(f"[CacheManager] Cache hit for payload. URI: {entry['cache_uri']}")
                return str(entry["cache_uri"])
            else:
                logger.info(f"[CacheManager] Cache {entry['cache_uri']} expired. Purging from registry.")
                del registry[payload_hash]
                self._save_registry(registry)

        # Cache miss — create new
        try:
            logger.info(f"[CacheManager] Cache miss. Uploading {len(str(contents))} bytes to Context Caching API...")
            cache_uri = client.create_cached_content(
                model=model,
                contents=contents,
                system_instruction=None,  # Do not cache the system prompt so multiple agents can reuse the payload
                ttl_seconds=ttl_seconds
            )
            
            registry[payload_hash] = {
                "cache_uri": cache_uri,
                "expires_at": current_time + ttl_seconds,
                "model": model
            }
            self._save_registry(registry)
            logger.info(f"[CacheManager] Successfully created cache URI: {cache_uri}")
            return cache_uri
            
        except Exception as e:
            logger.error(f"[CacheManager] Failed to create cache: {e}")
            return None
