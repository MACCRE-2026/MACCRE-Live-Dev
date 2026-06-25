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
maccre_core/_net/model_registry.py
====================================
Phase 6 — Multi-Surface Model Registry.

Replaces the single-tier `generateContent` model catalogue with a
capability-keyed surface map. Each surface has its own ordered failover
chain and endpoint routing hint, because TTS, image, embedding, live,
video, and text models all use different API shapes.

Ground truth from 2026-04-24 live probe (55 models):
  - generateContent + cache  : 22 models  → TEXT_GENERATION
  - generateContent only     : 16 models  → TEXT_GENERATION / DEEP_RESEARCH / EDGE /
                                             TTS / IMAGE_GENERATION / AUDIO_GEN /
                                             ROBOTICS / COMPUTER_USE (by name pattern)
  - bidiGenerateContent      : 4 models   → LIVE
  - embedContent             : 3 models   → EMBEDDING
  - predict                  : 3 models   → IMAGEN (Vertex AI endpoint)
  - predictLongRunning       : 6 models   → VIDEO (Veo)
  - generateAnswer           : 1 model    → AQA (legacy)
"""
from __future__ import annotations

import json
import logging
import ssl
import threading
import time
import urllib.error
import urllib.request
from enum import Enum
from typing import Any, Callable

from maccre_core.orchestration.universal_vault import wipe_string

logger = logging.getLogger("maccre_core")


# ── Model Surface Taxonomy ────────────────────────────────────────────────────

class ModelSurface(str, Enum):
    """Capability surface — determines endpoint shape and routing rules."""
    TEXT_GENERATION  = "text_generation"    # generateContent — text/multimodal
    DEEP_RESEARCH    = "deep_research"      # generateContent + grounding synthesis
    TTS              = "tts"                # generateContent → AUDIO modality
    IMAGE_GENERATION = "image_generation"   # generateContent → IMAGE modality
    LIVE             = "live"               # bidiGenerateContent — WebSocket streaming
    EMBEDDING        = "embedding"          # embedContent
    IMAGEN           = "imagen"             # predict — Vertex AI Imagen 4
    VIDEO            = "video"              # predictLongRunning — Veo
    AUDIO_GEN        = "audio_gen"          # generateContent — Lyria music synthesis
    EDGE             = "edge"               # generateContent — Gemma local-capable
    ROBOTICS         = "robotics"           # generateContent — gemini-robotics-*
    COMPUTER_USE     = "computer_use"       # generateContent — gemini-computer-use-*
    AQA              = "aqa"                # generateAnswer — legacy
    UNKNOWN          = "unknown"


# ── Surface classification patterns ──────────────────────────────────────────
# Applied in priority order (first match wins).

_SURFACE_PATTERNS: list[tuple[str, ModelSurface]] = [
    # Exact / prefix matches first (most specific)
    ("deep-research",                    ModelSurface.DEEP_RESEARCH),
    ("imagen-",                          ModelSurface.IMAGEN),
    ("veo-",                             ModelSurface.VIDEO),
    ("lyria-",                           ModelSurface.AUDIO_GEN),
    ("gemma-",                           ModelSurface.EDGE),
    ("gemini-embedding",                 ModelSurface.EMBEDDING),
    ("gemini-robotics",                  ModelSurface.ROBOTICS),
    ("gemini-2.5-computer-use",          ModelSurface.COMPUTER_USE),
    ("aqa",                              ModelSurface.AQA),
    # TTS — must check before generic flash/pro names
    ("-tts",                             ModelSurface.TTS),
    ("native-audio",                     ModelSurface.TTS),
    # Image generation via generateContent
    ("-image",                           ModelSurface.IMAGE_GENERATION),
    # Live / streaming
    # (bidiGenerateContent — identified by supportedMethods during probe, not name)
]


def classify_surface(name: str, supported_methods: list[str] | None = None) -> ModelSurface:
    """Classify a model into its capability surface.

    Args:
        name: Short model name (without 'models/' prefix).
        supported_methods: List of supported generation methods from the API.
                           Used to handle bidi / embed / predict routing.

    Returns:
        The most specific ``ModelSurface`` that matches.
    """
    n = name.lower()
    methods = set(supported_methods or [])

    # Method-first classification (most authoritative signal)
    if "bidiGenerateContent" in methods and "generateContent" not in methods:
        return ModelSurface.LIVE
    if "embedContent" in methods or "asyncBatchEmbedContent" in methods:
        return ModelSurface.EMBEDDING
    if "predictLongRunning" in methods:
        return ModelSurface.VIDEO
    if "predict" in methods and "generateContent" not in methods:
        return ModelSurface.IMAGEN
    if "generateAnswer" in methods:
        return ModelSurface.AQA

    # Name-pattern classification for all generateContent variants
    for pattern, surface in _SURFACE_PATTERNS:
        if pattern in n:
            return surface

    return ModelSurface.TEXT_GENERATION


# ── Tier classification (within TEXT_GENERATION surface) ─────────────────────

_TIER_ORDER: list[str] = ["pro", "flash", "lite", "experimental", "unknown"]


def _classify_tier(name: str) -> str:
    """Assign a tier label for intra-surface ordering (TEXT_GENERATION only)."""
    n = name.lower()
    if "lite" in n:
        return "lite"
    if "pro" in n:
        return "pro"
    if "flash" in n:
        return "flash"
    if "exp" in n or "preview" in n:
        return "experimental"
    return "unknown"


def _model_priority(name: str) -> tuple[int, str]:
    """Sort key: (tier_index, name). Lower = preferred."""
    tier = _classify_tier(name)
    tier_idx = _TIER_ORDER.index(tier) if tier in _TIER_ORDER else 99
    return (tier_idx, name)


def _strip_prefix(name: str) -> str:
    """'models/gemini-2.5-flash' → 'gemini-2.5-flash'."""
    return name.removeprefix("models/")


# ── Hardcoded fallback chains (TEXT_GENERATION surface) ──────────────────────
# Used when the live probe fails.

_FALLBACK_CHAINS: dict[str, list[str]] = {
    "gemini-2.5-pro": [
        "gemini-2.5-pro", "gemini-3.1-pro-preview",
        "gemini-3-pro-preview", "gemini-2.5-flash", "gemini-3-flash-preview",
    ],
    "gemini-3.1-pro-preview": [
        "gemini-3.1-pro-preview", "gemini-2.5-pro",
        "gemini-3-pro-preview", "gemini-2.5-flash", "gemini-3-flash-preview",
    ],
    "gemini-3-pro-preview": [
        "gemini-3-pro-preview", "gemini-3.1-pro-preview",
        "gemini-2.5-pro", "gemini-2.5-flash", "gemini-3-flash-preview",
    ],
    "gemini-2.5-flash": [
        "gemini-2.5-flash", "gemini-3-flash-preview", "gemini-2.5-flash-lite",
    ],
    "gemini-3-flash-preview": [
        "gemini-3-flash-preview", "gemini-2.5-flash", "gemini-2.5-flash-lite",
    ],
    "gemini-2.5-flash-lite": [
        "gemini-2.5-flash-lite", "gemini-3.1-flash-lite-preview",
    ],
    "gemini-3.1-flash-lite-preview": [
        "gemini-3.1-flash-lite-preview", "gemini-2.5-flash-lite",
    ],
}

# Fallback surface → preferred model (used when live data unavailable)
_FALLBACK_SURFACE_DEFAULTS: dict[ModelSurface, list[str]] = {
    ModelSurface.TTS:              ["gemini-2.5-flash-preview-tts", "gemini-3.1-flash-tts-preview", "gemini-2.5-pro-preview-tts"],
    ModelSurface.IMAGE_GENERATION: ["gemini-2.5-flash-image", "gemini-3.1-flash-image-preview", "gemini-3-pro-image-preview"],
    ModelSurface.DEEP_RESEARCH:    ["deep-research-max-preview-04-2026", "deep-research-preview-04-2026", "deep-research-pro-preview-12-2025"],
    ModelSurface.EDGE:             ["gemma-3-27b-it", "gemma-4-31b-it", "gemma-3-12b-it", "gemma-3-4b-it", "gemma-3-1b-it"],
    ModelSurface.LIVE:             ["gemini-3.1-flash-live-preview", "gemini-2.5-flash-native-audio-latest"],
    ModelSurface.EMBEDDING:        ["gemini-embedding-2", "gemini-embedding-2-preview", "gemini-embedding-001"],
    ModelSurface.VIDEO:            ["veo-3.1-generate-preview", "veo-3.1-fast-generate-preview", "veo-3.0-generate-001", "veo-3.0-fast-generate-001", "veo-2.0-generate-001"],
    ModelSurface.IMAGEN:           ["imagen-4.0-generate-001", "imagen-4.0-fast-generate-001", "imagen-4.0-ultra-generate-001"],
    ModelSurface.AUDIO_GEN:        ["lyria-3-pro-preview", "lyria-3-clip-preview"],
    ModelSurface.ROBOTICS:         ["gemini-robotics-er-1.6-preview", "gemini-robotics-er-1.5-preview"],
}


# ── Registry ──────────────────────────────────────────────────────────────────

class ModelRegistry:
    """Live-probed Gemini model catalogue with multi-surface failover routing.

    Each model is classified into a ``ModelSurface`` based on its
    ``supportedGenerationMethods`` and name pattern. Failover chains
    are built per-surface — text models never bleed into TTS chains
    and vice versa.

    Thread-safe: a single module-level instance is shared across the swarm
    worker pool. The probe lock prevents thundering-herd on the first call.

    Usage::

        registry = ModelRegistry(api_key="AIza...")
        # Text generation failover
        chain = registry.get_failover_chain("gemini-2.5-flash")

        # TTS model list (ordered best → acceptable)
        tts_models = registry.get_models_for_surface(ModelSurface.TTS)

        # Check what surface a model belongs to
        surface = registry.surface_of("gemini-2.5-flash-image")
        # → ModelSurface.IMAGE_GENERATION
    """

    def __init__(self, key_provider: Callable[[], str | None], ttl_seconds: int = 3600) -> None:
        self._key_provider = key_provider
        self._ttl = ttl_seconds
        self._ssl = ssl.create_default_context()
        self._lock = threading.Lock()

        # Cache state
        self._last_probe: float = 0.0
        self._all_models:   list[dict[str, Any]] = []          # full raw API response
        self._by_surface:   dict[str, list[str]] = {}           # surface.value → model names
        self._surface_of:   dict[str, ModelSurface] = {}        # model_name → surface
        self._gc_models:    list[dict[str, Any]] = []           # generateContent subset
        self._probe_ok:    bool = False
        self._sentinel: Any = None             # optional health filter

    # ── Sentinel integration ──────────────────────────────────────────────────

    def set_sentinel(self, sentinel: Any) -> None:
        """Wire a ModelSentinel for health-aware chain filtering.

        Call this once from ``maccre_router`` after both registry and sentinel
        are initialised. Once wired, ``get_failover_chain()`` will transparently
        filter dead/degraded models from every chain it returns.
        """
        self._sentinel = sentinel
        logger.info("[ModelRegistry] ModelSentinel wired — health-aware routing ACTIVE.")

    # ── Public API ────────────────────────────────────────────────────────────

    def get_failover_chain(self, model_name: str) -> list[str]:
        """Return an ordered, health-aware failover chain.

        Chain stays within the same surface tier. If a ``ModelSentinel`` is
        wired, degraded/dead models are sorted to the back of the chain so
        the routing layer always starts with the healthiest candidate.

        Args:
            model_name: Short or fully-qualified model name.

        Returns:
            Ordered list of model names to try, requested model always first
            (unless it is outright dead, in which case a healthy peer leads).
        """
        self._maybe_refresh()
        normalized = _strip_prefix(model_name)

        if self._probe_ok:
            surface = self._surface_of.get(normalized, ModelSurface.TEXT_GENERATION)
            if surface == ModelSurface.TEXT_GENERATION:
                return self._build_text_chain(normalized)
            # For non-text surfaces: return the full surface list with requested model first
            surface_list = self._by_surface.get(surface.value, [normalized])
            ordered = [normalized] + [m for m in surface_list if m != normalized]
            return ordered if ordered else [normalized]

        return _FALLBACK_CHAINS.get(normalized, [normalized])

    def get_models_for_surface(self, surface: ModelSurface) -> list[str]:
        """Return all model names for a given capability surface.

        Args:
            surface: The ``ModelSurface`` to query.

        Returns:
            Ordered list of model names (best/fastest first within the surface).
            Returns hardcoded fallback if the live probe has not succeeded.
        """
        self._maybe_refresh()
        if self._probe_ok:
            return list(self._by_surface.get(surface.value, []))
        return list(_FALLBACK_SURFACE_DEFAULTS.get(surface, []))

    def surface_of(self, model_name: str) -> ModelSurface:
        """Return the capability surface for a given model name.

        Args:
            model_name: Short or fully-qualified model name.

        Returns:
            The ``ModelSurface`` enum variant, or ``ModelSurface.UNKNOWN``
            if the model is not in the live catalogue.
        """
        self._maybe_refresh()
        normalized = _strip_prefix(model_name)
        return self._surface_of.get(normalized, classify_surface(normalized))

    def available_models(self) -> list[str]:
        """Return all model short-names that support generateContent.

        Compatible with the Phase 5 API — callers using this method continue
        to see only text-generation models, preserving backward compatibility.
        """
        self._maybe_refresh()
        return [_strip_prefix(m["name"]) for m in self._gc_models]

    def all_models(self) -> list[str]:
        """Return ALL model short-names across every surface."""
        self._maybe_refresh()
        return [_strip_prefix(m["name"]) for m in self._all_models]

    def supports_method(self, model_name: str, method: str = "generateContent") -> bool:
        """Return True if the model supports a given generation method."""
        self._maybe_refresh()
        clean = _strip_prefix(model_name)
        for m in self._all_models:
            if _strip_prefix(m.get("name", "")) == clean:
                return method in m.get("supportedGenerationMethods", [])
        return False

    def probe_now(self) -> bool:
        """Force an immediate re-probe, bypassing the TTL cache."""
        with self._lock:
            self._last_probe = 0.0
        self._maybe_refresh()
        return self._probe_ok

    # ── Internal ──────────────────────────────────────────────────────────────

    def _maybe_refresh(self) -> None:
        now = time.monotonic()
        if now - self._last_probe < self._ttl:
            return
        with self._lock:
            if now - self._last_probe < self._ttl:
                return
            self._probe()
            self._last_probe = time.monotonic()

    def _probe(self) -> None:
        """Fetch all models, classify into surfaces, build per-surface lists."""
        try:
            models = self._fetch_all_models()
            self._all_models = models

            by_surface: dict[str, list[str]] = {s.value: [] for s in ModelSurface}
            surface_of: dict[str, ModelSurface] = {}
            gc_models: list[dict[str, Any]] = []

            # Filter exclusions — noisy/junk models that pollute failover chains
            _EXCLUSION_SUBSTRINGS = {"nano-banana"}  # remove placeholder models

            for m in models:
                short = _strip_prefix(m.get("name", ""))
                methods = m.get("supportedGenerationMethods", [])

                # Skip exclusions
                if any(ex in short for ex in _EXCLUSION_SUBSTRINGS):
                    logger.debug("[ModelRegistry] Excluding junk model: %s", short)
                    continue

                surface = classify_surface(short, methods)
                by_surface.setdefault(surface.value, []).append(short)
                surface_of[short] = surface

                if "generateContent" in methods:
                    gc_models.append(m)

            # Sort within TEXT_GENERATION by tier priority
            by_surface[ModelSurface.TEXT_GENERATION.value].sort(key=_model_priority)

            # Sort other surfaces by quality (prefer non-"fast", non-"lite" first)
            for surface_val, names in by_surface.items():
                if surface_val != ModelSurface.TEXT_GENERATION.value:
                    # Heuristic: put "fast"/"lite" variants after full-quality models
                    names.sort(key=lambda n: (
                        1 if "fast" in n or "lite" in n else 0,
                        n
                    ))

            self._by_surface = by_surface
            self._surface_of = surface_of
            self._gc_models = gc_models
            self._probe_ok = True

            # Build surface summary for log
            surface_counts = {
                k: len(v) for k, v in by_surface.items() if v
            }
            logger.info(
                "[ModelRegistry] Probe OK — %d total models across %d surfaces: %s",
                len(models),
                len(surface_counts),
                surface_counts,
            )

        except Exception as exc:
            self._probe_ok = False
            logger.warning(
                "[ModelRegistry] Live probe failed (%s). Using hardcoded fallback chains.",
                str(exc)[:120],
            )

    def _fetch_all_models(self) -> list[dict[str, Any]]:
        """Paginate through GET /v1beta/models and return all model dicts."""
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

                headers = {"User-Agent": "MACCREv2-ModelRegistry/6.0 (Python urllib)"}
                if raw_key:
                    headers["x-goog-api-key"] = raw_key

                req = urllib.request.Request(
                    url, method="GET",
                    headers=headers,
                )
                try:
                    with urllib.request.urlopen(req, context=self._ssl, timeout=30) as resp:
                        result: dict[str, Any] = json.loads(resp.read().decode("utf-8"))
                except urllib.error.HTTPError as exc:
                    err_body = exc.read().decode("utf-8", errors="replace")
                    raise RuntimeError(f"HTTP {exc.code}: {err_body[:200]}") from exc

                models.extend(result.get("models", []))
                page_token = result.get("nextPageToken")
                if not page_token:
                    break

            return models
        finally:
            if raw_key:
                wipe_string(raw_key)

    def _build_text_chain(self, model_name: str) -> list[str]:
        """Build a dynamic failover chain within TEXT_GENERATION surface.

        Strategy:
          1. Requested model is always first.
          2. Same-tier peers (ordered by priority), excluding requested.
          3. Next lower tier (at most 2) as depth-drop fallback.
          4. Never cross into TTS / image / other surfaces.
        """
        requested_tier = _classify_tier(model_name)
        tier_idx = _TIER_ORDER.index(requested_tier) if requested_tier in _TIER_ORDER else 99

        # Only pull from TEXT_GENERATION surface
        text_models = self._by_surface.get(ModelSurface.TEXT_GENERATION.value, [])

        # Group text models by tier
        by_tier: dict[str, list[str]] = {}
        for m in text_models:
            t = _classify_tier(m)
            by_tier.setdefault(t, []).append(m)

        chain: list[str] = [model_name]
        same_tier = [m for m in by_tier.get(requested_tier, []) if m != model_name]
        chain.extend(same_tier)

        for next_tier in _TIER_ORDER[tier_idx + 1:]:
            peers = by_tier.get(next_tier, [])
            if peers:
                chain.extend(peers[:2])
                break

        # Deduplicate preserving order
        seen: set[str] = set()
        deduped: list[str] = []
        for m in chain:
            if m not in seen:
                seen.add(m)
                deduped.append(m)

        return deduped or [model_name]


# ── Module-level singleton ────────────────────────────────────────────────────

_registry: ModelRegistry | None = None
_registry_lock = threading.Lock()


def get_registry(key_provider: Callable[[], str | None]) -> ModelRegistry:
    """Get or create the module-level ModelRegistry singleton."""
    global _registry  # noqa: PLW0603
    if _registry is None:
        with _registry_lock:
            if _registry is None:
                _registry = ModelRegistry(key_provider=key_provider)
    return _registry


# Re-export for convenience
__all__ = ["ModelRegistry", "ModelSurface", "classify_surface", "get_registry"]
