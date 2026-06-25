# ┌─────────────────────────────────────────────────────────────────────────────┐
# │  MACCREv2 ENGINEERING DOCTRINE                             Law Rev: 19.0   │
# ├─────────────────────────────────────────────────────────────────────────────┤
# │  I.   TYPING      All signatures: explicit Python 3.11+ type hints.        │
# │  II.  LINTING     Zero unused imports. No wildcards. 120-char line max.    │
# │  III. PATHS       Never hardcode absolute paths. Use get_maccre_root().     │
# │                   Default params: def f(p:str='') -> None: p=p or root/x   │
# │  IV.  DATACENTER  5-Tier: 01_Raw_Source · 02_Dynamic_Context               │
# │                           03_Agent_Ledgers · 04_Code_Artifacts             │
# │                           05_Rendered_Media                                 │
# │  V.   DIAMOND     Gen: temp=1.0  ·  Critic: temp=0.1 + dataclass schema   │
# │  VI.  ABSTRACTION All I/O behind abc.ABC before any concrete driver.       │
# │  VII. TEARDOWN    try/finally on all handles (omni clean compliance).      │
# │  VIII.TELEMETRY   No bare print(). logger only. JSON → 03_Agent_Ledgers.  │
# └─────────────────────────────────────────────────────────────────────────────┘
"""
maccre_core/_net/model_sentinel.py
====================================
ModelSentinel — Active Model Management Daemon.

Shifts model management from passive failover (dead model → try next) to
active health monitoring with background probing, change detection, and
error rate tracking.

Architecture:
  - Background thread wakes every ``probe_interval_s`` (default 1800s = 30 min)
  - Full capability re-probe via GET /v1beta/models
  - Diffs against previous snapshot → emits MODEL_ADDED / MODEL_DIED events
  - Per-model error rate tracking from live call telemetry
  - ModelRegistry integration: get_failover_chain() filters degraded models

Usage::

    from maccre_core._net.model_sentinel import get_sentinel
    sentinel = get_sentinel(api_key="AIza...")
    sentinel.start()

    # From any call site:
    sentinel.record_success("gemini-2.5-flash")
    sentinel.record_error("gemini-2.5-flash", "HTTP 503")

    # From ModelRegistry:
    healthy_chain = [m for m in chain if sentinel.is_healthy(m)]
"""
from __future__ import annotations

import json
import logging
import ssl
import threading
import time
import urllib.error
import urllib.request
from collections import deque
from datetime import datetime, timezone
from typing import Any, Callable

from maccre_core.orchestration.universal_vault import wipe_string
from maccre_core.utils.path_resolver import get_maccre_root

logger = logging.getLogger("maccre_core")

# ── Change event types ────────────────────────────────────────────────────────

MODEL_ADDED     = "MODEL_ADDED"
MODEL_DIED      = "MODEL_DIED"
MODEL_DEGRADED  = "MODEL_DEGRADED"
MODEL_RECOVERED = "MODEL_RECOVERED"
QUOTA_EXHAUSTED = "QUOTA_EXHAUSTED"


class ModelHealth:
    """Per-model health record with sliding error window."""

    WINDOW_SIZE = 20          # last N calls tracked
    DEGRADED_THRESHOLD = 0.30  # 30% error rate → degraded
    DEAD_THRESHOLD = 1.00      # 100% errors over full window → dead

    def __init__(self, name: str) -> None:
        self.name = name
        self.in_catalogue: bool = True       # known to API list
        self.is_live: bool = True            # not dead
        self.is_degraded: bool = False       # error rate elevated
        self.error_rate: float = 0.0
        self.last_check: float = time.time()
        self.latency_ms_avg: float = 0.0
        self._window: deque[bool] = deque(maxlen=self.WINDOW_SIZE)  # True=success

    def record(self, success: bool, latency_ms: float = 0.0) -> str | None:
        """Record a call outcome. Returns change event type if state changed."""
        self._window.append(success)
        if latency_ms > 0:
            alpha = 0.2
            self.latency_ms_avg = (alpha * latency_ms) + ((1 - alpha) * self.latency_ms_avg)
        self.last_check = time.time()

        if not self._window:
            return None

        errors = sum(1 for s in self._window if not s)
        self.error_rate = errors / len(self._window)

        was_degraded = self.is_degraded
        was_live    = self.is_live

        self.is_live = self.error_rate < self.DEAD_THRESHOLD
        self.is_degraded = self.error_rate >= self.DEGRADED_THRESHOLD

        if was_live and not self.is_live:
            return MODEL_DIED
        if not was_live and self.is_live:
            return MODEL_RECOVERED
        if not was_degraded and self.is_degraded:
            return MODEL_DEGRADED
        if was_degraded and not self.is_degraded:
            return MODEL_RECOVERED
        return None

    def health_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "in_catalogue": self.in_catalogue,
            "is_live": self.is_live,
            "is_degraded": self.is_degraded,
            "error_rate": round(self.error_rate, 3),
            "latency_ms_avg": round(self.latency_ms_avg, 1),
            "last_check": datetime.fromtimestamp(self.last_check, tz=timezone.utc).isoformat(),
            "window_size": len(self._window),
        }


class ModelSentinel:
    """Active background model health monitor with change detection.

    Thread-safe singleton. Use ``get_sentinel(api_key)`` for module-level access.

    The sentinel runs a background probe thread that:
      1. Fetches the live model list every ``probe_interval_s`` seconds.
      2. Diffs against the previous snapshot to detect MODEL_ADDED / MODEL_DIED.
      3. Persists the capability snapshot to ``capability_cache_path`` for
         cold-start recovery (zero API calls on restart within TTL).

    The sentinel also maintains per-model call telemetry through
    ``record_success()`` / ``record_error()`` which any call site reports into.
    """

    def __init__(
        self,
        key_provider: Callable[[], str | None],
        probe_interval_s: int = 1800,
        capability_cache_path: str = "",
    ) -> None:
        self._key_provider = key_provider
        self._ssl = ssl.create_default_context()
        self._probe_interval = probe_interval_s
        self._cache_path = capability_cache_path or str(
            get_maccre_root() / "scripts" / "model_capability_map.json"
        )

        self._lock = threading.Lock()
        self._health: dict[str, ModelHealth] = {}       # model_name → health
        self._catalogue: dict[str, dict[str, Any]] = {} # model_name → full spec
        self._change_log: list[dict[str, Any]] = []     # chronological events
        self._last_probe: float = 0.0
        self._running: bool = False
        self._thread: threading.Thread | None = None

        # Boot from disk cache if available
        self._load_cache()

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    def start(self) -> None:
        """Launch the background probe thread."""
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(
            target=self._run_loop,
            name="ModelSentinel",
            daemon=True,
        )
        self._thread.start()
        logger.info("[ModelSentinel] Background probe thread started (interval=%ds).", self._probe_interval)

    def stop(self) -> None:
        """Signal the probe thread to stop."""
        self._running = False
        logger.info("[ModelSentinel] Stopping probe thread.")

    # ── Call telemetry (call from router after every API call) ────────────────

    def record_success(self, model_name: str, latency_ms: float = 0.0) -> None:
        """Report a successful API call for ``model_name``."""
        with self._lock:
            h = self._get_or_create_health(model_name)
            event = h.record(success=True, latency_ms=latency_ms)
        if event:
            self._emit_event(event, model_name, "error rate recovered")

    def record_error(self, model_name: str, error: str = "", latency_ms: float = 0.0) -> None:
        """Report a failed API call for ``model_name``."""
        with self._lock:
            h = self._get_or_create_health(model_name)
            event = h.record(success=False, latency_ms=latency_ms)
        if event:
            self._emit_event(event, model_name, error[:120])

        if "429" in error or "RESOURCE_EXHAUSTED" in error:
            self._emit_event(QUOTA_EXHAUSTED, model_name, error[:120])

    # ── Health queries ─────────────────────────────────────────────────────────

    def is_healthy(self, model_name: str) -> bool:
        """Return True if the model is live, not degraded, and in the API catalogue."""
        with self._lock:
            h = self._health.get(model_name)
            if h is None:
                return True   # Unknown model — optimistic, let it try
            return h.in_catalogue and h.is_live and not h.is_degraded

    def is_live(self, model_name: str) -> bool:
        """Return True if the model is in the API catalogue and not dead."""
        with self._lock:
            h = self._health.get(model_name)
            if h is None:
                return True
            return h.in_catalogue and h.is_live

    def get_capability(self, model_name: str) -> dict[str, Any]:
        """Return the full capability spec for a model (from last probe)."""
        with self._lock:
            return dict(self._catalogue.get(model_name, {}))

    def all_capabilities(self) -> list[dict[str, Any]]:
        """Return all models with their capabilities and health status."""
        with self._lock:
            results = []
            for name, spec in self._catalogue.items():
                health = self._health.get(name, ModelHealth(name))
                entry = dict(spec)
                entry["health"] = health.health_dict()
                results.append(entry)
            return results

    def report(self) -> dict[str, Any]:
        """Full sentinel status snapshot."""
        with self._lock:
            healthy = sum(1 for h in self._health.values() if h.is_live and not h.is_degraded)
            degraded = sum(1 for h in self._health.values() if h.is_degraded)
            dead = sum(1 for h in self._health.values() if not h.is_live)
            return {
                "total_models": len(self._catalogue),
                "healthy": healthy,
                "degraded": degraded,
                "dead": dead,
                "last_probe": datetime.fromtimestamp(self._last_probe, tz=timezone.utc).isoformat()
                              if self._last_probe else "never",
                "change_log_count": len(self._change_log),
                "recent_events": self._change_log[-10:],
            }

    def change_log(self, limit: int = 50) -> list[dict[str, Any]]:
        """Return the most recent model change events."""
        with self._lock:
            return list(self._change_log[-limit:])

    # ── Internal probe logic ──────────────────────────────────────────────────

    def _run_loop(self) -> None:
        while self._running:
            try:
                self._probe_cycle()
            except Exception as exc:
                logger.warning("[ModelSentinel] Probe cycle error: %s", exc)
            for _ in range(self._probe_interval):
                if not self._running:
                    break
                time.sleep(1)

    def _probe_cycle(self) -> None:
        """Full API probe cycle with diff detection."""
        logger.debug("[ModelSentinel] Starting probe cycle...")
        models = self._fetch_all_models()
        if not models:
            logger.warning("[ModelSentinel] Probe returned 0 models — skipping diff.")
            return

        new_catalogue: dict[str, dict[str, Any]] = {}
        for m in models:
            short = m.get("name", "").removeprefix("models/")
            new_catalogue[short] = {
                "name": short,
                "displayName": m.get("displayName", ""),
                "description": m.get("description", "")[:120],
                "version": m.get("version", ""),
                "supportedMethods": m.get("supportedGenerationMethods", []),
                "inputTokenLimit": m.get("inputTokenLimit", -1),
                "outputTokenLimit": m.get("outputTokenLimit", -1),
                "temperature": m.get("temperature"),
                "maxTemperature": m.get("maxTemperature"),
                "topP": m.get("topP"),
                "topK": m.get("topK"),
            }

        with self._lock:
            old_names = set(self._catalogue.keys())
            new_names = set(new_catalogue.keys())

            added = new_names - old_names
            removed = old_names - new_names

            for name in added:
                self._get_or_create_health(name)
                self._health[name].in_catalogue = True
                self._emit_event_unlocked(MODEL_ADDED, name, "Discovered in probe")

            for name in removed:
                if name in self._health:
                    self._health[name].in_catalogue = False
                    self._health[name].is_live = False
                self._emit_event_unlocked(MODEL_DIED, name, "Removed from API catalogue")

            self._catalogue = new_catalogue
            self._last_probe = time.time()

        # Save to disk cache
        self._save_cache(list(new_catalogue.values()))
        logger.info(
            "[ModelSentinel] Probe OK — %d models (%d added, %d removed).",
            len(new_catalogue), len(added), len(removed),
        )

    def _fetch_all_models(self) -> list[dict[str, Any]]:
        models: list[dict[str, Any]] = []
        page_token: str | None = None
        raw_key = self._key_provider()
        try:
            while True:
                url = (
                    "https://generativelanguage.googleapis.com/v1beta/models"
                    "?pageSize=100"
                )
                if page_token:
                    url += f"&pageToken={page_token}"
                
                headers = {}
                if raw_key:
                    headers["x-goog-api-key"] = raw_key
                    
                req = urllib.request.Request(url, method="GET", headers=headers)
                try:
                    with urllib.request.urlopen(req, context=self._ssl, timeout=30) as r:
                        result: dict[str, Any] = json.loads(r.read().decode("utf-8"))
                except urllib.error.HTTPError as exc:
                    logger.warning("[ModelSentinel] HTTP %d fetching model list.", exc.code)
                    return []
                except Exception as exc:
                    logger.warning("[ModelSentinel] Fetch error: %s", exc)
                    return []
                models.extend(result.get("models", []))
                page_token = result.get("nextPageToken")
                if not page_token:
                    break
            return models
        finally:
            if raw_key:
                wipe_string(raw_key)

    def _get_or_create_health(self, model_name: str) -> ModelHealth:
        """Must be called with self._lock held."""
        if model_name not in self._health:
            self._health[model_name] = ModelHealth(model_name)
        return self._health[model_name]

    def _emit_event(self, event_type: str, model: str, detail: str) -> None:
        with self._lock:
            self._emit_event_unlocked(event_type, model, detail)

    def _emit_event_unlocked(self, event_type: str, model: str, detail: str) -> None:
        """Must be called with self._lock held."""
        entry = {
            "event": event_type,
            "model": model,
            "detail": detail,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        self._change_log.append(entry)
        logger.info("[ModelSentinel] %s — %s: %s", event_type, model, detail)

    def _load_cache(self) -> None:
        """Load capability map from disk on startup (cold-start recovery)."""
        try:
            import pathlib  # noqa: PLC0415
            path = pathlib.Path(self._cache_path)
            if path.exists():
                specs = json.loads(path.read_text(encoding="utf-8"))
                with self._lock:
                    for s in specs:
                        name = s.get("name", "")
                        if name:
                            self._catalogue[name] = s
                            self._get_or_create_health(name)
                logger.info(
                    "[ModelSentinel] Cold-start: loaded %d models from cache %s.",
                    len(self._catalogue), self._cache_path,
                )
        except Exception as exc:
            logger.warning("[ModelSentinel] Cache load failed: %s", exc)

    def _save_cache(self, specs: list[dict[str, Any]]) -> None:
        try:
            import pathlib  # noqa: PLC0415
            pathlib.Path(self._cache_path).write_text(
                json.dumps(specs, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
        except Exception as exc:
            logger.warning("[ModelSentinel] Cache save failed: %s", exc)


# ── Module-level singleton ────────────────────────────────────────────────────

_sentinel: ModelSentinel | None = None
_sentinel_lock = threading.Lock()


def get_sentinel(key_provider: Callable[[], str | None], probe_interval_s: int = 1800) -> ModelSentinel:
    """Get or create the module-level ModelSentinel singleton."""
    global _sentinel  # noqa: PLW0603
    if _sentinel is None:
        with _sentinel_lock:
            if _sentinel is None:
                _sentinel = ModelSentinel(key_provider=key_provider, probe_interval_s=probe_interval_s)
    return _sentinel


__all__ = ["ModelSentinel", "ModelHealth", "get_sentinel",
           "MODEL_ADDED", "MODEL_DIED", "MODEL_DEGRADED", "MODEL_RECOVERED", "QUOTA_EXHAUSTED"]
