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
maccre_core/tools/finops_tools.py
===================================
FinOps Engine — 2026 Pricing Matrix & Cost Calculator.

Two entry points:
  ``calculate_actual_cost``  — post-call receipt from usage_metadata tokens.
  ``calculate_predicted_cost`` — pre-flight cost estimate via Count Tokens API.

Context-window tiers (Gemini Pro/Flash pricing has a ≤200K / >200K break):
  Short context: ≤ 200,000 tokens
  Long context:  > 200,000 tokens

Batch discount: 50% off standard rates for batchGenerateContent calls.
Grounding:      $14.00 per 1,000 search queries (after free monthly quota).
Sovereign local models (Gemma / Ollama) always return 0.0.

Pricing confirmed against ai.google.dev/pricing — 2026-04-24.
"""

import json
import sqlite3
import ssl
import urllib.error
import urllib.request

from maccre_core._net.gemini_client import GeminiClient

# ── 2026 Pricing Matrix (USD per 1,000,000 tokens) ───────────────────────────
# Format per model:
#   "input_short"   — input price in $/M for prompts ≤ 200K tokens
#   "input_long"    — input price in $/M for prompts > 200K tokens
#   "output_short"  — output price in $/M for ≤200K context
#   "output_long"   — output price in $/M for >200K context
#   "cache_read"    — cached input read price in $/M (0 = not supported)
#   "cache_write"   — cache storage write price in $/M/hour
# All prices are for real-time (non-batch). Batch = 0.5× these rates.

PRICING_MATRIX: dict[str, dict[str, float]] = {

    # ── Gemini 3.1 Pro (highest tier) ─────────────────────────────────────────
    "gemini-3.1-pro-preview": {
        "input_short": 2.00, "input_long": 4.00,
        "output_short": 12.00, "output_long": 18.00,
        "cache_read": 0.50, "cache_write": 4.50,
    },
    "gemini-3.1-pro-preview-customtools": {
        "input_short": 2.00, "input_long": 4.00,
        "output_short": 12.00, "output_long": 18.00,
        "cache_read": 0.50, "cache_write": 4.50,
    },

    # ── Gemini 3.0 Pro ────────────────────────────────────────────────────────
    "gemini-3-pro-preview": {
        "input_short": 1.25, "input_long": 2.50,
        "output_short": 10.00, "output_long": 15.00,
        "cache_read": 0.3125, "cache_write": 4.50,
    },
    "gemini-3-pro-image-preview": {
        "input_short": 1.25, "input_long": 2.50,
        "output_short": 10.00, "output_long": 15.00,
        "cache_read": 0.0, "cache_write": 0.0,
    },

    # ── Gemini 2.5 Pro ────────────────────────────────────────────────────────
    "gemini-2.5-pro": {
        "input_short": 1.25, "input_long": 2.50,
        "output_short": 10.00, "output_long": 15.00,
        "cache_read": 0.3125, "cache_write": 4.50,
    },
    "gemini-pro-latest": {  # alias → current Pro
        "input_short": 1.25, "input_long": 2.50,
        "output_short": 10.00, "output_long": 15.00,
        "cache_read": 0.3125, "cache_write": 4.50,
    },

    # ── Deep Research (Pro rates + grounding surcharge tracked separately) ────
    "deep-research-max-preview-04-2026": {
        "input_short": 1.25, "input_long": 2.50,
        "output_short": 10.00, "output_long": 15.00,
        "cache_read": 0.0, "cache_write": 0.0,
        # search_per_1k: 14.00  — tracked in grounding cost events separately
    },
    "deep-research-preview-04-2026": {
        "input_short": 1.25, "input_long": 2.50,
        "output_short": 10.00, "output_long": 15.00,
        "cache_read": 0.0, "cache_write": 0.0,
    },
    "deep-research-pro-preview-12-2025": {
        "input_short": 1.25, "input_long": 2.50,
        "output_short": 10.00, "output_long": 15.00,
        "cache_read": 0.0, "cache_write": 0.0,
    },

    # ── Gemini 3.x Flash ──────────────────────────────────────────────────────
    "gemini-3-flash-preview": {
        "input_short": 0.075, "input_long": 0.15,
        "output_short": 0.30, "output_long": 0.60,
        "cache_read": 0.01875, "cache_write": 1.00,
    },

    # ── Gemini 2.5 Flash ──────────────────────────────────────────────────────
    "gemini-2.5-flash": {
        "input_short": 0.075, "input_long": 0.15,
        "output_short": 0.30, "output_long": 0.60,
        "cache_read": 0.01875, "cache_write": 1.00,
    },
    "gemini-flash-latest": {  # alias
        "input_short": 0.075, "input_long": 0.15,
        "output_short": 0.30, "output_long": 0.60,
        "cache_read": 0.01875, "cache_write": 1.00,
    },
    "gemini-2.0-flash": {
        "input_short": 0.075, "input_long": 0.15,
        "output_short": 0.30, "output_long": 0.60,
        "cache_read": 0.01875, "cache_write": 1.00,
    },
    "gemini-2.0-flash-001": {
        "input_short": 0.075, "input_long": 0.15,
        "output_short": 0.30, "output_long": 0.60,
        "cache_read": 0.01875, "cache_write": 1.00,
    },

    # ── Image Generation (Flash-family, per-token for input prompt) ───────────
    "gemini-2.5-flash-image": {
        "input_short": 0.075, "input_long": 0.15,
        "output_short": 0.30, "output_long": 0.60,  # text out
        "cache_read": 0.0, "cache_write": 0.0,
        # image output: ~$0.04/image billed separately
    },
    "gemini-3.1-flash-image-preview": {
        "input_short": 0.075, "input_long": 0.15,
        "output_short": 0.30, "output_long": 0.60,
        "cache_read": 0.0, "cache_write": 0.0,
    },

    # ── Gemini 2.5 Flash Lite ─────────────────────────────────────────────────
    "gemini-2.5-flash-lite": {
        "input_short": 0.0375, "input_long": 0.075,
        "output_short": 0.15, "output_long": 0.30,
        "cache_read": 0.009375, "cache_write": 1.00,
    },
    "gemini-3.1-flash-lite-preview": {
        "input_short": 0.0375, "input_long": 0.075,
        "output_short": 0.15, "output_long": 0.30,
        "cache_read": 0.009375, "cache_write": 1.00,
    },
    "gemini-flash-lite-latest": {
        "input_short": 0.0375, "input_long": 0.075,
        "output_short": 0.15, "output_long": 0.30,
        "cache_read": 0.009375, "cache_write": 1.00,
    },
    "gemini-2.0-flash-lite": {
        "input_short": 0.0375, "input_long": 0.075,
        "output_short": 0.15, "output_long": 0.30,
        "cache_read": 0.009375, "cache_write": 1.00,
    },
    "gemini-2.0-flash-lite-001": {
        "input_short": 0.0375, "input_long": 0.075,
        "output_short": 0.15, "output_long": 0.30,
        "cache_read": 0.009375, "cache_write": 1.00,
    },

    # ── TTS Models (input token pricing; audio output at per-character rates) ──
    # TTS output is NOT billed per output token — it's per audio second/character.
    # We track input tokens at Flash rates and audio output separately.
    "gemini-2.5-flash-preview-tts": {
        "input_short": 0.075, "input_long": 0.15,
        "output_short": 0.30, "output_long": 0.60,
        "cache_read": 0.0, "cache_write": 0.0,
    },
    "gemini-3.1-flash-tts-preview": {
        "input_short": 0.075, "input_long": 0.15,
        "output_short": 0.30, "output_long": 0.60,
        "cache_read": 0.0, "cache_write": 0.0,
    },
    "gemini-2.5-pro-preview-tts": {
        "input_short": 1.25, "input_long": 2.50,
        "output_short": 10.00, "output_long": 15.00,
        "cache_read": 0.0, "cache_write": 0.0,
    },

    # ── Live / Native Audio (Flash rates, bidi streaming) ────────────────────
    "gemini-2.5-flash-native-audio-latest": {
        "input_short": 0.075, "input_long": 0.15,
        "output_short": 0.30, "output_long": 0.60,
        "cache_read": 0.0, "cache_write": 0.0,
    },
    "gemini-2.5-flash-native-audio-preview-12-2025": {
        "input_short": 0.075, "input_long": 0.15,
        "output_short": 0.30, "output_long": 0.60,
        "cache_read": 0.0, "cache_write": 0.0,
    },
    "gemini-2.5-flash-native-audio-preview-09-2025": {
        "input_short": 0.075, "input_long": 0.15,
        "output_short": 0.30, "output_long": 0.60,
        "cache_read": 0.0, "cache_write": 0.0,
    },
    "gemini-3.1-flash-live-preview": {
        "input_short": 0.075, "input_long": 0.15,
        "output_short": 0.30, "output_long": 0.60,
        "cache_read": 0.0, "cache_write": 0.0,
    },

    # ── Speciality (Pro rates) ────────────────────────────────────────────────
    "gemini-robotics-er-1.6-preview": {
        "input_short": 1.25, "input_long": 2.50,
        "output_short": 10.00, "output_long": 15.00,
        "cache_read": 0.3125, "cache_write": 4.50,
    },
    "gemini-robotics-er-1.5-preview": {
        "input_short": 1.25, "input_long": 2.50,
        "output_short": 10.00, "output_long": 15.00,
        "cache_read": 0.0, "cache_write": 0.0,
    },
    "gemini-2.5-computer-use-preview-10-2025": {
        "input_short": 1.25, "input_long": 2.50,
        "output_short": 10.00, "output_long": 15.00,
        "cache_read": 0.0, "cache_write": 0.0,
    },

    # ── Anthropic (external) ──────────────────────────────────────────────────
    "claude-3-5-sonnet-20241022": {"input_short": 3.00, "input_long": 3.00,
                                    "output_short": 15.00, "output_long": 15.00,
                                    "cache_read": 0.0, "cache_write": 0.0},
}

# ── Context length threshold for the long-context pricing tier ───────────────
_LONG_CTX_THRESHOLD: int = 200_000  # tokens

# ── Free models (always return $0.00) ────────────────────────────────────────
_FREE_MODEL_KEYWORDS: tuple[str, ...] = (
    "gemma",          # all Gemma models are free via Gemini API
    "llama",          # local Ollama
    "gemini-embedding",  # embedding models are free
    "aqa",            # legacy QA model
)

# ── Grounding pricing ─────────────────────────────────────────────────────────
GROUNDING_PRICE_PER_1K_QUERIES: float = 14.00  # USD per 1000 search queries

# ── Batch discount multiplier ─────────────────────────────────────────────────
BATCH_DISCOUNT: float = 0.5  # 50% off for batchGenerateContent


def _get_rates(model_id: str, input_tokens: int) -> dict[str, float]:
    """Return the correct price tier based on model and context length."""
    key = model_id.lower().removeprefix("models/")

    # Exact match first
    if key in PRICING_MATRIX:
        rates = PRICING_MATRIX[key]
    else:
        # Substring/prefix fallback — find the most specific match
        match: dict[str, float] | None = None
        best_len = 0
        for k in PRICING_MATRIX:
            if k in key and len(k) > best_len:
                match = PRICING_MATRIX[k]
                best_len = len(k)
        # Final fallback: charge at Flash rates (safe underestimate alarm)
        rates = match or PRICING_MATRIX["gemini-2.5-flash"]

    tier = "long" if input_tokens > _LONG_CTX_THRESHOLD else "short"
    return {
        "input": rates.get(f"input_{tier}", rates.get("input_short", 0.075)),
        "output": rates.get(f"output_{tier}", rates.get("output_short", 0.30)),
        "cache_read": rates.get("cache_read", 0.0),
        "cache_write": rates.get("cache_write", 0.0),
    }


def calculate_actual_cost(
    model_id: str,
    input_tokens: int,
    output_tokens: int,
    cached_tokens: int = 0,
    is_batch: bool = False,
    grounding_queries: int = 0,
) -> float:
    """Calculate the exact USD cost from post-call usage metadata.

    Args:
        model_id:          The exact model string used in the API call.
        input_tokens:      ``prompt_token_count`` from ``usage_metadata``.
        output_tokens:     ``candidates_token_count`` from ``usage_metadata``.
        cached_tokens:     Tokens served from cache (charged at cache_read rate).
        is_batch:          True if the call used batchGenerateContent (50% discount).
        grounding_queries: Number of Google Search grounding queries fired.

    Returns:
        Cost in USD as a float. Returns 0.0 for sovereign free-tier models.
    """
    lower = model_id.lower()
    if any(kw in lower for kw in _FREE_MODEL_KEYWORDS):
        return 0.0

    rates = _get_rates(model_id, input_tokens)
    billable_input = max(0, input_tokens - cached_tokens)
    in_cost = (billable_input / 1_000_000.0) * rates["input"]
    cache_cost = (cached_tokens / 1_000_000.0) * rates["cache_read"]
    out_cost = (output_tokens / 1_000_000.0) * rates["output"]
    base_cost = in_cost + cache_cost + out_cost

    if is_batch:
        base_cost *= BATCH_DISCOUNT

    grounding_cost = (grounding_queries / 1_000.0) * GROUNDING_PRICE_PER_1K_QUERIES
    return base_cost + grounding_cost


def calculate_predicted_cost(
    client: GeminiClient,
    model_id: str,
    payload: str,
    system_prompt: str,
) -> dict[str, float | int]:
    """Pre-flight cost estimate via the Count Tokens API.

    Returns:
        Dict with ``tokens`` (int) and ``predicted_cost`` (float in USD).
    """
    model_lower = model_id.lower()
    if any(kw in model_lower for kw in _FREE_MODEL_KEYWORDS):
        return {"tokens": 0, "predicted_cost": 0.0}

    combined = f"[{system_prompt}]\n\n{payload}" if system_prompt else payload
    body = {"contents": [{"role": "user", "parts": [{"text": combined}]}]}
    url = (
        f"https://generativelanguage.googleapis.com/v1beta/models/"
        f"{model_id.removeprefix('models/')}:countTokens"
    )
    
    raw_key = client._key_provider()
    headers = {"Content-Type": "application/json"}
    if raw_key:
        headers["x-goog-api-key"] = raw_key

    req = urllib.request.Request(
        url,
        data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
        method="POST",
        headers=headers,
    )
    ctx = ssl.create_default_context()
    try:
        with urllib.request.urlopen(req, context=ctx, timeout=30) as resp:
            result: dict[str, object] = json.loads(resp.read().decode("utf-8"))
        input_tokens: int = int(str(result.get("totalTokens", 0)))
    except Exception:
        input_tokens = 0
    finally:
        if raw_key:
            from maccre_core.orchestration.universal_vault import wipe_string  # noqa: PLC0415
            wipe_string(raw_key)

    rates = _get_rates(model_id, input_tokens)
    predicted = (input_tokens / 1_000_000.0) * rates["input"]
    return {"tokens": input_tokens, "predicted_cost": predicted}


# ── Media Pricing (image / TTS character rates) ───────────────────────────────

MEDIA_PRICING: dict[str, float] = {
    # Image generation — per image (approximate; varies by resolution/quality)
    "gemini-2.5-flash-image":       0.04,   # $/image via generateContent
    "gemini-3.1-flash-image-preview": 0.04,
    "gemini-3-pro-image-preview":   0.06,
    "imagen-4.0-generate-001":      0.04,   # Vertex AI
    "imagen-4.0-fast-generate-001": 0.02,
    "imagen-4.0-ultra-generate-001": 0.08,
    # TTS — per 1,000 characters of input text
    "tts_per_1k_chars":             0.002,  # applies to all -tts and -native-audio models
    # Video — per second of generated video
    "veo-3.1-generate-preview":     0.35,
    "veo-3.1-fast-generate-preview": 0.17,
    "veo-3.1-lite-generate-preview": 0.10,
    "veo-3.0-generate-001":         0.30,
    "veo-3.0-fast-generate-001":    0.15,
    "veo-2.0-generate-001":         0.25,
}


def calculate_media_cost(
    num_images: int,
    tts_text_length: int,
    image_model_used: str = "gemini-2.5-flash-image",
) -> float:
    """Calculate USD cost for a media render batch (images + TTS).

    Args:
        num_images:      Number of generated images.
        tts_text_length: Total character count of all TTS text segments.
        image_model_used: Active image model name (used for per-image pricing lookup).

    Returns:
        Total estimated cost in USD.
    """
    # Image cost — match most specific key
    img_rate = 0.04  # default
    for k, v in MEDIA_PRICING.items():
        if k in image_model_used.lower():
            img_rate = v
            break

    image_cost = num_images * img_rate
    tts_cost = (tts_text_length / 1_000.0) * MEDIA_PRICING["tts_per_1k_chars"]
    return image_cost + tts_cost


def estimate_manifest_cost(manifest_json: str) -> str:
    """Pre-flight cost estimate for a Director's JSON manifest.

    Returns a JSON string with ``estimated_cost_usd``, ``scene_count``,
    ``images``, ``tts_chars``, ``audio_only_cost_usd``.
    Use alongside ``render_cost_report(session_id)`` to compare pre/post costs.
    """
    try:
        manifest = json.loads(manifest_json)
        scene_count = len(manifest)
        num_images = sum(1 for scene in manifest if scene.get("video_prompt"))
        total_chars = sum(len(scene.get("text", "")) for scene in manifest)
        cost_with_images = calculate_media_cost(num_images, total_chars)
        cost_audio_only = calculate_media_cost(0, total_chars)
        return json.dumps({
            "estimated_cost_usd": cost_with_images,
            "audio_only_cost_usd": cost_audio_only,
            "scene_count": scene_count,
            "images": num_images,
            "tts_chars": total_chars,
        })
    except Exception as e:
        return json.dumps({"error": str(e)})



def reconcile_session_finops(session_id: str) -> str:
    """Double-entry reconciliation of projected vs actual costs for a session."""
    from maccre_core.utils.path_resolver import get_datacenter_path  # noqa: PLC0415
    db_path = str(get_datacenter_path("telemetry", "system_logs.db"))
    try:
        with sqlite3.connect(db_path) as conn:
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA journal_mode=WAL;")
            cur_proj = conn.execute(
                "SELECT SUM(cost) AS projected FROM system_logs "
                "WHERE session_id = ? AND action_type = 'FINOPS_PROJECTION'",
                (session_id,),
            )
            proj_row = cur_proj.fetchone()
            projected = float(proj_row["projected"] or 0.0) if proj_row else 0.0
            cur_act = conn.execute(
                "SELECT SUM(cost) AS actual FROM system_logs "
                "WHERE session_id = ? AND action_type != 'FINOPS_PROJECTION'",
                (session_id,),
            )
            act_row = cur_act.fetchone()
            actual = float(act_row["actual"] or 0.0) if act_row else 0.0
            delta = actual - projected
            variance_pct = (delta / projected * 100.0) if projected > 0 else 0.0
            report: dict[str, object] = {
                "session_id": session_id,
                "projected_usd": round(projected, 6),
                "actual_usd": round(actual, 6),
                "delta_usd": round(delta, 6),
                "variance_pct": round(variance_pct, 2),
                "status": "NOMINAL" if abs(variance_pct) <= 10.0 else "DISCREPANCY_DETECTED",
            }
            return json.dumps(report, indent=2)
    except Exception as exc:
        return json.dumps({"error": str(exc)})


def render_cost_report(session_id: str) -> str:
    """Retrieve a detailed cost breakdown for a completed render session.

    Queries system_logs.db for MEDIA_RENDER_COMPLETE events emitted by the
    render pipeline during the given session and returns a formatted markdown
    report with actual costs broken down by TTS and image generation.

    Pair with estimate_manifest_cost() for pre/post comparison:
        1. Before firing: estimate_manifest_cost(manifest_json) → projected
        2. After render:  render_cost_report(session_id)        → actual

    Args:
        session_id: The job_id of the completed render session.
            Visible in the SUCCESS string from render_podcast_audio or
            execute_render_pipeline. Example: "job_20260505-201036-xxyz-Run1"

    Returns:
        Formatted markdown cost report, or JSON error if no events found.
    """
    from maccre_core.orchestration.telemetry_db import get_db_path  # noqa: PLC0415
    try:
        db_path = get_db_path("system_logs.db")
        with sqlite3.connect(db_path) as conn:
            conn.execute("PRAGMA journal_mode=WAL;")
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT * FROM system_logs "
                "WHERE session_id = ? AND action_type = 'MEDIA_RENDER_COMPLETE' "
                "ORDER BY id ASC",
                (session_id,),
            ).fetchall()

        if not rows:
            return json.dumps({
                "status": "NO_RENDER_EVENTS",
                "session_id": session_id,
                "message": (
                    "No MEDIA_RENDER_COMPLETE events found. Verify the session_id "
                    "matches the job_id in the SUCCESS output from render_podcast_audio "
                    "or execute_render_pipeline."
                ),
            })

        total_cost = 0.0
        total_tts_chars = 0
        total_images = 0
        total_scenes = 0
        output_paths: list[str] = []
        render_modes: list[str] = []

        for row in rows:
            r = dict(row)
            total_cost += float(r.get("cost", 0.0))
            try:
                _p: dict[str, object] = json.loads(r.get("payload", "{}"))
                total_tts_chars += int(str(_p.get("tts_chars", 0)))
                total_images    += int(str(_p.get("image_count", 0)))
                total_scenes    += int(str(_p.get("scene_count", 0)))
                if _p.get("output_path"):
                    output_paths.append(str(_p["output_path"]))
                if _p.get("render_mode"):
                    render_modes.append(str(_p["render_mode"]))
            except Exception:  # noqa: BLE001
                pass

        tts_cost = (total_tts_chars / 1_000.0) * MEDIA_PRICING["tts_per_1k_chars"]
        img_cost = max(0.0, total_cost - tts_cost)

        lines: list[str] = [
            "# Render Cost Report",
            f"**Session:** `{session_id}`  **Events:** {len(rows)}\n",
            "## Summary",
            "| Metric | Value |",
            "|---|---|",
            f"| Total Cost | **${total_cost:.6f}** |",
            f"| TTS Characters | {total_tts_chars:,} |",
            f"| Images Generated | {total_images} |",
            f"| Total Scenes | {total_scenes} |",
            f"| Render Mode(s) | {', '.join(set(render_modes)) or 'unknown'} |",
            "",
            "## Cost Breakdown",
            "| Component | Detail | Cost |",
            "|---|---|---|",
            f"| TTS Audio | {total_tts_chars:,} chars @ $0.002/1k | ${tts_cost:.6f} |",
            f"| Image Generation | {total_images} images | ${img_cost:.6f} |",
            f"| **Total** | | **${total_cost:.6f}** |",
        ]
        if output_paths:
            lines += ["", "## Output Files"]
            for path in output_paths:
                lines.append(f"- `{path}`")

        return "\n".join(lines)

    except Exception as exc:  # noqa: BLE001
        return json.dumps({"error": str(exc)})
