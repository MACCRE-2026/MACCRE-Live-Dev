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
maccre_core/maccre_router.py
==============================
Phase 10 — Sovereign Dual-Pipeline UniversalRouter.

Exposes two surfaces:

  UniversalRouter.generate(model, payload, system_prompt, tools_str, temperature)
      Low-level swarm-worker interface (unchanged from Phase 7).
      Returns (output_text, cost_usd) — no schema enforcement.

  AgentRouter.chat(agent_name, message, session_id, preloaded_context) -> str
      High-level Flet GUI interface.
      Enforces the AgentResponse Pydantic schema in BOTH pipelines:
        {"scratchpad": "...", "final_response": "..."}
      Extracts scratchpad and discards it since we no longer log thoughts.
      Returns only final_response to the caller.

Pipeline routing:
  gemini-*          → Cloud (google-genai SDK, response_schema enforced)
  gemma* / llama*  → Local (Ollama JSON mode, schema injected via system prompt)
  claude-*          → Anthropic (no structured schema in this path; falls through
                       to generate() for swarm use only)
"""
from __future__ import annotations

import json
import re
import urllib.request
import urllib.error
from pathlib import Path
from typing import Any

from maccre_core.logger import logger
from maccre_core._net.gemini_client import (
    GeminiClient,
    GeminiResponse,
    history_to_contents,
    user_turn,
    is_transient_error,
    is_fatal_error,
)
from maccre_core._net.model_registry import get_registry, ModelRegistry

from maccre_core.orchestration.universal_vault import get_provider_credential
from maccre_core.tools.tool_registry import get_tools_from_sheet, generate_universal_json_schema
from maccre_core.orchestration.cache_manager import CacheManager


from dataclasses import dataclass, field

# ── Sovereign Schema enforced across both pipelines ─────────────────────────────

@dataclass
class AgentResponse:
    scratchpad: str = field(metadata={'description': 'Your internal reasoning.'})
    final_response: str = field(metadata={'description': 'Your verbal answer to the user.'})


_SCHEMA_INSTRUCTION = (
    "You MUST reply with a single JSON object matching this exact schema:\n"
    '{"scratchpad": "<your internal reasoning>", "final_response": "<your answer to the user>"}\n'
    "Do not include any text outside the JSON object."
)

# Per-step delay in seconds when moving through the failover chain.
# position 0 = first attempt (no delay), position N = Nth failover (increasing backoff).
# Chains are now built dynamically by ModelRegistry + ModelSentinel — no static dict needed.
_CHAIN_DELAYS: list[int] = [0, 3, 8, 20, 40]

# ── Multi-modal payload resolution ───────────────────────────────────────────
_MEDIA_EXTS: frozenset[str] = frozenset({
    ".mp3", ".wav", ".m4a", ".aac", ".flac", ".ogg", ".opus", ".weba",
    ".mp4", ".webm", ".mov", ".avi", ".mkv", ".m4v", ".3gp",
    ".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp",
    ".pdf",
})
_MEDIA_TOKEN_RE  = re.compile(r"\[\[MEDIA:\s*(.+?)\]\]", re.IGNORECASE)
_YOUTUBE_RE      = re.compile(r"https?://(?:www\.)?(?:youtube\.com/watch|youtu\.be/)")
_FILE_API_LIMIT: int = 20 * 1024 * 1024  # 20 MB — above this, use Files API


def _build_multimodal_parts(
    payload: str,
    gemini_client: "GeminiClient",
) -> list[dict[str, Any]]:
    """Resolve [[MEDIA: /path]] tokens and YouTube URLs into Gemini content parts.

    Patterns supported:
      1. ``[[MEDIA: /abs/path/file.mp3]]`` tokens — can appear multiple times.
         Text around them becomes a companion text part.
      2. Bare YouTube URL as the *entire* payload — injected as a fileData URI.
      3. Plain text — fast path, zero overhead, returns [text_part(payload)].

    Files <=20 MB are base64-inlined; larger files upload via the Files API.
    """
    from maccre_core._net.gemini_client import inline_part, file_uri_part, text_part  # noqa: PLC0415

    stripped = payload.strip()

    # Fast path: no tokens and not a YouTube URL
    if not _MEDIA_TOKEN_RE.search(stripped) and not _YOUTUBE_RE.match(stripped):
        return [text_part(payload)]

    # Entire payload is a YouTube URL
    if _YOUTUBE_RE.match(stripped) and not _MEDIA_TOKEN_RE.search(stripped):
        logger.info("[ROUTER:MM] YouTube URL -> fileData part.")
        return [file_uri_part(stripped, "video/mp4")]

    # Mixed payload: extract tokens, keep remaining text
    media_refs: list[str] = _MEDIA_TOKEN_RE.findall(stripped)
    clean_text: str = _MEDIA_TOKEN_RE.sub("", stripped).strip()

    parts: list[dict[str, Any]] = []
    for raw_ref in media_refs:
        ref = raw_ref.strip()
        if _YOUTUBE_RE.match(ref):
            logger.info("[ROUTER:MM] YouTube token -> fileData part.")
            parts.append(file_uri_part(ref, "video/mp4"))
            continue
        p = Path(ref)
        if not p.exists():
            logger.warning("[ROUTER:MM] Media file not found: '%s' -- skipping.", ref)
            continue
        if p.suffix.lower() not in _MEDIA_EXTS:
            logger.warning("[ROUTER:MM] Unknown media extension '%s' -- skipping.", p.suffix)
            continue
        if p.stat().st_size <= _FILE_API_LIMIT:
            logger.info("[ROUTER:MM] Inline embedding '%s' (%d bytes).", p.name, p.stat().st_size)
            parts.append(inline_part(p))
        else:
            logger.info("[ROUTER:MM] Files API upload '%s' (%d bytes).", p.name, p.stat().st_size)
            _meta = gemini_client.upload_file(p)
            parts.append(file_uri_part(_meta.uri, _meta.mime_type))

    if clean_text:
        parts.append(text_part(clean_text))

    if not parts:
        logger.warning("[ROUTER:MM] All media refs failed -- falling back to text.")
        return [text_part(payload)]

    return parts


class UniversalRouter:
    """Universal Inference Dispatcher — routes model calls to the correct vendor.

    Maintained for backwards-compatibility with swarm_worker.py. The high-level
    GUI interface is AgentRouter.chat().
    """

    def __init__(self) -> None:
        def gemini_provider() -> str | None:
            k = get_provider_credential("MACCRE_Sovereign")
            return str(k).strip() if k and str(k).strip().startswith("AIza") else None

        # Sovereign Gemini HTTP Client — zero SDK dependency
        if gemini_provider():
            self.gemini_client: GeminiClient | None = GeminiClient(key_provider=gemini_provider)
            # Phase 6: Live model registry + ModelSentinel for health-aware routing
            self._model_registry: ModelRegistry = get_registry(gemini_provider)
            from maccre_core._net.model_sentinel import get_sentinel  # noqa: PLC0415
            self._sentinel = get_sentinel(gemini_provider)
            self._sentinel.start()                          # No-op if already running
            self._model_registry.set_sentinel(self._sentinel)
        else:
            self.gemini_client = None
            self._model_registry = get_registry(lambda: None)
            self._sentinel = None
            
        self._cache_manager = CacheManager()

        # Third-party clients (lazy import — only loaded when requested)
        self.anthropic_client: object | None = None
        self.openai_client: object | None = None
        self.groq_client: object | None = None

    def generate(
        self,
        model_name: str,
        payload: str,
        system_prompt: str,
        tools_str: str,
        temperature: float,
        conversation_history: list[dict[str, str]] | None = None,
        response_schema: Any | None = None,
        expect_multiple_reads: bool = False,
        thinking_level: str = "none",
        safety_level: str = "BLOCK_NONE",
    ) -> tuple[str, float, str]:
        """Universal Dispatcher. Routes to the correct vendor based on ``model_name``.

        Args:
            model_name: The model identifier from topology.csv.
            payload: The user-facing content / task description.
            system_prompt: System instruction string.
            tools_str: Pipe/comma-separated tool names from the topology CSV.
            temperature: Sampling temperature from the topology node.
            conversation_history: Optional prior turns as list of
                ``{"role": "user"|"nexus", "text": str}`` dicts.  When supplied
                and the model is Gemini, the history is passed as proper
                ``types.Content`` objects rather than a flattened text blob,
                giving the model genuine multi-turn context.

        Returns:
            Tuple of (output_text, cost_usd).

        Raises:
            ValueError: If the model name is unrecognised or the vault key is missing.
            RuntimeError: On 404/epoch-drift errors from the Gemini API.
        """
        model_lower = model_name.lower()
        
        # ── Anchor Temporal Awareness ──
        import datetime
        _now_str = datetime.datetime.now().strftime("%B %d, %Y")
        if system_prompt:
            system_prompt = f"Today is {_now_str}.\n\n{system_prompt}"
        else:
            system_prompt = f"Today is {_now_str}."
        
        # Detect and strip the google_search sentinel — it is a native Gemini capability,
        # not a registered Python callable.  Must be removed before tool schema generation.
        _tool_names = [t.strip() for t in tools_str.replace("|", ",").split(",")]
        _use_grounding: bool = "google_search" in _tool_names
        _filtered_tools = ",".join(t for t in _tool_names if t != "google_search")
        active_tools = get_tools_from_sheet(_filtered_tools)
        # Initialise at function scope so all routing branches (Gemini, edge, Groq…)
        # can safely reference it — avoids Pyright reportUnboundVariable on the edge path.
        _resolved_schema: dict[str, Any] | None = None

        if "gemini" in model_lower:
            if not self.gemini_client:
                raise ValueError("Missing Gemini OS Vault Key ('MACCRE_Sovereign').")

            # Build tool declarations in OpenAPI format for the sovereign client
            tool_declarations: list[dict[str, Any]] | None = None
            if active_tools:
                tool_declarations = [
                    {
                        "name": s["name"],
                        "description": s["description"],
                        "parameters": s["input_schema"],
                    }
                    for s in (generate_universal_json_schema(t) for t in active_tools)
                ]
                
            if response_schema:
                if isinstance(response_schema, dict):
                    _resolved_schema = response_schema
                elif hasattr(response_schema, "model_json_schema"):
                    _resolved_schema = response_schema.model_json_schema()
                elif hasattr(response_schema, "schema"):
                    _resolved_schema = response_schema.schema()

            # ── Cloud Gemini with tiered failover (Phase 5: live registry) ────
            _chain = self._model_registry.get_failover_chain(model_name)
            last_exc: Exception = RuntimeError("No attempts made")

            for _chain_idx, _attempt_model in enumerate(_chain):
                _delay = _CHAIN_DELAYS[_chain_idx] if _chain_idx < len(_CHAIN_DELAYS) else _CHAIN_DELAYS[-1]
                if _delay:
                    logger.warning(
                        "[ROUTER] Failover to '%s' (position %d/%d in chain for '%s') -- waiting %ds...",
                        _attempt_model, _chain_idx + 1, len(_chain), model_name, _delay,
                    )
                    import time as _time  # noqa: PLC0415
                    _time.sleep(_delay)
                elif _attempt_model != model_name:
                    logger.info("[ROUTER] Failover: using '%s' (requested '%s')", _attempt_model, model_name)

                try:
                    # Build contents — resolve any [[MEDIA:]] tokens or YouTube URLs
                    _mm_parts = _build_multimodal_parts(payload, self.gemini_client)
                    if conversation_history:
                        contents = []
                        for _ht in conversation_history:
                            _hr = "user" if _ht.get("role") == "user" else "model"
                            contents.append({"role": _hr, "parts": [{"text": _ht.get("text", "")}]})
                        contents.append(user_turn(*_mm_parts))
                    else:
                        contents = [user_turn(*_mm_parts)]

                    # ── Evaluate Context Caching ───────────────────────────────────────
                    _cached_uri = None
                    _req_contents = contents
                    if expect_multiple_reads and self.gemini_client and len(contents) > 1:
                        _cache_contents = contents[:-1]
                        # Compute total characters across all turns in the context window
                        _total_chars = sum(len(str(part.get("text", ""))) for turn in _cache_contents for part in turn.get("parts", []))
                        
                        # Heuristic: 120,000 chars roughly equals ~30k tokens. Threshold is 32k.
                        if _total_chars >= 120_000:
                            logger.info("[ROUTER] Context window exceeds 120k chars (%d) and expects multiple reads. Evaluating Cache...", _total_chars)
                            _cached_uri = self._cache_manager.get_or_create_cache(
                                client=self.gemini_client,
                                model=_attempt_model,
                                contents=_cache_contents,
                                system_instruction=system_prompt if system_prompt else None,
                                ttl_seconds=3600
                            )
                            if _cached_uri:
                                _req_contents = [contents[-1]]

                    import time as _t0  # noqa: PLC0415
                    _t0_start = _t0.monotonic()
                    # Sovereign pipeline: BLOCK_NONE on all harm categories.
                    # OSINT and journalism agents require maximally permissive thresholds.
                    # This mirrors the AI Studio "Safety Off" toggle at the API level.
                    _safety_off: list[dict[str, str]] = [
                        {"category": "HARM_CATEGORY_HARASSMENT",        "threshold": safety_level},
                        {"category": "HARM_CATEGORY_HATE_SPEECH",       "threshold": safety_level},
                        {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": safety_level},
                        {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": safety_level},
                    ]
                    

                    _thinking_config = None
                    if thinking_level.lower() == "low":
                        _thinking_config = {"thinkingBudget": 1024}
                    elif thinking_level.lower() == "high":
                        _thinking_config = {"thinkingBudget": 4096}
                    
                    response: GeminiResponse = self.gemini_client.generate_content(
                        model=_attempt_model,
                        contents=_req_contents,
                        system_instruction=system_prompt if system_prompt else None,
                        temperature=temperature,
                        tool_declarations=tool_declarations,
                        search_grounding=_use_grounding,
                        disable_auto_function_calling=bool(tool_declarations) and not _use_grounding,
                        response_schema=_resolved_schema,
                        safety_settings=_safety_off,
                        max_output_tokens=8192,
                        cached_content_uri=_cached_uri,
                        thinking_config=_thinking_config,
                    )
                    _latency_ms = (_t0.monotonic() - _t0_start) * 1000.0

                    cost: float = 0.0
                    if response.prompt_tokens or response.candidate_tokens:
                        from maccre_core.tools.finops_tools import calculate_actual_cost  # noqa: PLC0415
                        cost = calculate_actual_cost(
                            _attempt_model,
                            response.prompt_tokens,
                            response.candidate_tokens,
                        )
                        # ── Direct FinOps attribution to DB ───────────────────────────
                        # Log cost + token counts with model attribution here so
                        # every call is tracked regardless of which swarm node
                        # fired it. This closes the $19 billing gap.
                        try:
                            from maccre_core.orchestration.telemetry_db import log_system_event  # noqa: PLC0415
                            log_system_event(
                                action_type="INFERENCE_COST",
                                payload=f"model={_attempt_model} requested={model_name}",
                                cost=cost,
                                model_id=_attempt_model,
                                input_tokens=response.prompt_tokens,
                                output_tokens=response.candidate_tokens,
                            )
                        except Exception:
                            pass  # Never let telemetry crash the inference path

                    # ── Sentinel health reporting ───────────────────────────────────
                    if self._sentinel is not None:
                        self._sentinel.record_success(_attempt_model, latency_ms=_latency_ms)

                    api_thought = response.scratchpad_thought

                    # Check if the model returned a function call
                    fc = response.function_call
                    
                    if fc is not None:
                        fc_name, fc_args = fc
                        try:
                            args_json = json.dumps(fc_args)
                        except Exception:
                            args_json = str(fc_args)
                        return (f"[TOOL CALL REQUESTED: {fc_name} - {args_json}]", cost, api_thought)

                    final_text = response.text
                    if _attempt_model != model_name:
                        logger.info(
                            "[ROUTER] '%s' served by failover model '%s'.",
                            model_name, _attempt_model,
                        )
                    return (final_text, cost, api_thought)

                except Exception as exc:
                    if self._sentinel is not None:
                        self._sentinel.record_error(_attempt_model, error=str(exc))
                    if is_fatal_error(exc):
                        raise RuntimeError(
                            f"[ROUTER_FATAL] Model '{_attempt_model}' not found or bad request. "
                            f"Failover chain for '{model_name}': {_chain}."
                        ) from exc
                    if is_transient_error(exc):
                        last_exc = exc
                        logger.warning(
                            "[ROUTER] Transient error on '%s' (chain pos %d/%d): %s",
                            _attempt_model, _chain_idx + 1, len(_chain), str(exc)[:120],
                        )
                        break  # advance to next chain model
                    raise RuntimeError(f"Gemini API Error ({_attempt_model}): {exc}") from exc

            raise RuntimeError(
                f"[ROUTER_EXHAUSTED] All failover models for '{model_name}' returned transient errors. "
                f"Chain tried: {_chain}. Last error: {last_exc}"
            )


        # ── Claude ────────────────────────────────────────────────────────────
        elif "claude" in model_lower:
            anthropic_key = get_provider_credential("MACCRE_Sovereign_Anthropic")
            if not anthropic_key:
                raise ValueError("Missing Anthropic OS Vault Key.")
            try:
                from anthropic import Anthropic  # type: ignore[import-untyped]
            except ImportError:
                raise ValueError("'anthropic' package not installed. Run: pip install anthropic")
            if self.anthropic_client is None:
                self.anthropic_client = Anthropic(api_key=str(anthropic_key))
            anthropic_tools = [generate_universal_json_schema(t) for t in active_tools]
            kwargs: dict[str, Any] = {
                "model": model_name,
                "max_tokens": 4096,
                "temperature": temperature,
                "messages": [{"role": "user", "content": payload}],
            }
            if system_prompt:
                kwargs["system"] = system_prompt
            if anthropic_tools:
                kwargs["tools"] = anthropic_tools
            response_ant = self.anthropic_client.messages.create(**kwargs)  # type: ignore[union-attr]
            output = ""
            for block in response_ant.content:
                if block.type == "text":
                    output += block.text
                elif block.type == "tool_use":
                    output += f"\n[TOOL CALL REQUESTED: {block.name} with args {block.input}]"
            return (output, 0.0, "")

        # ── OpenAI Schema Tools (Used natively by OpenAI, Groq, and Ollama) ───
        oai_tools = []
        if active_tools:
            oai_tools = [
                {
                    "type": "function",
                    "function": {
                        "name": s["name"],
                        "description": s["description"],
                        "parameters": s["input_schema"],
                    },
                }
                for s in (generate_universal_json_schema(t) for t in active_tools)
            ]

        # ── OpenAI ────────────────────────────────────────────────────────────
        if "gpt" in model_lower or "o1" in model_lower or "o3" in model_lower:
            openai_key = get_provider_credential("MACCRE_Sovereign_OpenAI")
            if not openai_key:
                raise ValueError("Missing OpenAI OS Vault Key.")
            try:
                import openai as _openai
            except ImportError:
                raise ValueError("'openai' package not installed. Run: pip install openai")
            if self.openai_client is None:
                self.openai_client = _openai.Client(api_key=str(openai_key))
            kwargs = {
                "model": model_name,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": payload}
                ]
            }
            if oai_tools:
                kwargs["tools"] = oai_tools  # type: ignore
            res = self.openai_client.chat.completions.create(**kwargs)  # type: ignore[union-attr]
            msg = res.choices[0].message
            if msg.tool_calls:
                return (f"[TOOL CALL REQUESTED: {msg.tool_calls[0].function.name} - {msg.tool_calls[0].function.arguments}]", 0.0, "")
            return (msg.content or "", 0.0, "")
            
        # ── Groq ──────────────────────────────────────────────────────────────
        elif "groq" in model_lower:
            groq_key = get_provider_credential("MACCRE_Sovereign_Groq")
            if not groq_key:
                raise ValueError("Missing Groq OS Vault Key.")
            try:
                import groq as _groq  # type: ignore[import-untyped]
            except ImportError:
                raise ValueError("'groq' package not installed. Run: pip install groq")
            if self.groq_client is None:
                self.groq_client = _groq.Client(api_key=str(groq_key))
            kwargs = {
                "model": model_name,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": payload}
                ],
                "temperature": temperature,
            }
            if oai_tools:
                kwargs["tools"] = oai_tools  # type: ignore
            res = self.groq_client.chat.completions.create(**kwargs)  # type: ignore[union-attr]
            msg = res.choices[0].message
            if msg.tool_calls:
                return (f"[TOOL CALL REQUESTED: {msg.tool_calls[0].function.name} - {msg.tool_calls[0].function.arguments}]", 0.0, "")
            return (msg.content or "", 0.0, "")

        # ── Edge Compute (Personal Cloud) ──────────────────────────────────────
        elif model_lower.startswith("edge-"):
            import os
            edge_url = os.environ.get("MACCRE_EDGE_URL", "http://127.0.0.1:8080/v1/chat/completions")
            req_body: dict[str, Any] = {
                "model": model_name,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": payload},
                ],
                "stream": False,
                "temperature": temperature,
            }
            if oai_tools:
                req_body["tools"] = oai_tools
            if _resolved_schema:
                req_body["response_format"] = {"type": "json_object"}
            
            _edge_bytes = json.dumps(req_body, ensure_ascii=False).encode("utf-8")
            _edge_req = urllib.request.Request(
                edge_url,
                data=_edge_bytes,
                method="POST",
                headers={"Content-Type": "application/json", "Authorization": "Bearer edge-token"},
            )
            try:
                with urllib.request.urlopen(_edge_req, timeout=300) as _r:
                    _edge_data: dict[str, Any] = json.loads(_r.read().decode("utf-8"))
            except urllib.error.HTTPError as _e:
                raise ValueError(f"Edge Error ({_e.code}): {_e.read().decode('utf-8', errors='replace')[:200]}") from _e
            except Exception as _e:
                raise ValueError(f"Edge Connection Error: {_e}. Is S25 running at {edge_url}?") from _e
                
            msg_dict = _edge_data.get("choices", [{}])[0].get("message", {})
            if "tool_calls" in msg_dict and msg_dict["tool_calls"]:
                return (f"[LOCAL TOOL CALL REQUESTED: {json.dumps(msg_dict['tool_calls'])}]", 0.0, "")
            return (str(msg_dict.get("content", "", "")), 0.0)

        # ── Ollama (local air-gap) ─────────────────────────────────────────────
        # Ollama tag format always has a colon: gemma3:4b, llama3.1:8b
        # Google AI API Gemma IDs use dashes: gemma-4-31b-it, gemma-3-27b-it
        _is_ollama = ":" in model_name or model_lower.startswith("llama")
        if _is_ollama or (model_lower.startswith("gemma") and "-" not in model_lower):
            req_body: dict[str, Any] = {
                "model": model_name,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": payload},
                ],
                "stream": False,
                "options": {"temperature": temperature},
            }
            if oai_tools:
                req_body["tools"] = oai_tools
            _ollama_bytes = json.dumps(req_body, ensure_ascii=False).encode("utf-8")
            _ollama_req = urllib.request.Request(
                "http://localhost:11434/api/chat",
                data=_ollama_bytes,
                method="POST",
                headers={"Content-Type": "application/json"},
            )
            try:
                with urllib.request.urlopen(_ollama_req, timeout=300) as _r:
                    _ollama_data: dict[str, Any] = json.loads(_r.read().decode("utf-8"))
            except urllib.error.HTTPError as _e:
                raise ValueError(f"Ollama Error ({_e.code}): {_e.read().decode('utf-8', errors='replace')[:200]}") from _e
            msg_dict = _ollama_data.get("message", {})
            if "tool_calls" in msg_dict:
                return (f"[LOCAL TOOL CALL REQUESTED: {json.dumps(msg_dict['tool_calls'])}]", 0.0, "")
            return (str(msg_dict.get("content", "", "")), 0.0)

        # ── Google AI API-hosted Gemma (gemma-4-31b-it, gemma-3-27b-it …) ──────
        # Dash-format Gemma IDs are served by generativelanguage.googleapis.com
        # via the same GeminiClient as gemini-* models.
        elif "gemma" in model_lower:
            if not self.gemini_client:
                raise ValueError(
                    "Missing Gemini OS Vault Key ('MACCRE_Sovereign'). "
                    "API-hosted Gemma requires the same credential as Gemini."
                )
            _chain_g = self._model_registry.get_failover_chain(model_name)
            _last_exc_g: Exception = RuntimeError("No attempts made")
            for _cidx, _amodel in enumerate(_chain_g):
                _dg = _CHAIN_DELAYS[_cidx] if _cidx < len(_CHAIN_DELAYS) else _CHAIN_DELAYS[-1]
                if _dg:
                    import time as _tg  # noqa: PLC0415
                    _tg.sleep(_dg)
                try:
                    _gc = [user_turn(payload)]
                    if conversation_history:
                        _gc = history_to_contents(conversation_history, payload)
                    _gr: GeminiResponse = self.gemini_client.generate_content(
                        model=_amodel,
                        contents=_gc,
                        system_instruction=system_prompt or None,
                        temperature=temperature,
                    )
                    _gc_cost: float = 0.0
                    if _gr.prompt_tokens or _gr.candidate_tokens:
                        from maccre_core.tools.finops_tools import calculate_actual_cost  # noqa: PLC0415
                        _gc_cost = calculate_actual_cost(_amodel, _gr.prompt_tokens, _gr.candidate_tokens)
                        try:
                            from maccre_core.orchestration.telemetry_db import log_system_event  # noqa: PLC0415
                            log_system_event(
                                action_type="INFERENCE_COST",
                                payload=f"model={_amodel} requested={model_name}",
                                cost=_gc_cost, model_id=_amodel,
                                input_tokens=_gr.prompt_tokens, output_tokens=_gr.candidate_tokens,
                            )
                        except Exception:
                            pass
                    if self._sentinel is not None:
                        self._sentinel.record_success(_amodel)
                    return (_gr.text, _gc_cost, "")
                except Exception as _gex:
                    if self._sentinel is not None:
                        self._sentinel.record_error(_amodel, error=str(_gex))
                    if is_fatal_error(_gex):
                        raise RuntimeError(
                            f"[ROUTER_FATAL] API-Gemma '{_amodel}' not found or bad request."
                        ) from _gex
                    _last_exc_g = _gex
            raise RuntimeError(
                f"[ROUTER_EXHAUSTED] All models for API-Gemma '{model_name}' failed. "
                f"Last: {_last_exc_g}"
            )

        else:
            raise ValueError(
                f"CRITICAL: Unknown model routing for '{model_name}'. "
                "Add 'gemini', 'claude', 'gemma', 'llama', or 'groq' to the model name."
            )




# ── High-level GUI interface (Phase 10) ───────────────────────────────────────

class AgentRouter:
    """
    MCP-facing router that enforces the AgentResponse structured schema
    in both cloud and local inference pipelines.

    Automatically extracts the <scratchpad> and writes it to thoughts.db.
    Returns only final_response to the caller.
    """

    _DEFAULT_CLOUD_MODEL = "gemini-3-flash-preview"
    _DEFAULT_LOCAL_MODEL  = "gemma3:9b"

    def __init__(self) -> None:
        self._router = UniversalRouter()

    # ── Public API ────────────────────────────────────────────────────────────

    def chat(
        self,
        agent_name: str,
        message: str,
        session_id: str = "",
        preloaded_context: str = "",
        model: str | None = None,
    ) -> str:
        """
        Send a message to a named agent and return only the clean final_response.
        """
        effective_model = model or self._DEFAULT_CLOUD_MODEL
        full_message = (
            f"[PRELOADED CONTEXT]\n{preloaded_context}\n\n[USER MESSAGE]\n{message}"
            if preloaded_context else message
        )


        try:
            # Replaces OmniDaemon logic natively with the Sovereign UniversalRouter
            raw_output, _cost = self._router.generate(
                model_name=effective_model,
                payload=full_message,
                system_prompt=_SCHEMA_INSTRUCTION,
                tools_str="",
                temperature=0.7,
                response_schema=AgentResponse,
            )

            return self._extract_and_log(raw_output, agent_name, session_id)
        except Exception as exc:
            return f"FATAL ERROR: UniversalRouter Generation Failed - {exc}"

    # ── Shared extraction + telemetry write ───────────────────────────────────

    def _extract_and_log(
        self, raw_json: str, agent_name: str, session_id: str
    ) -> str:
        """
        Parse the JSON mapping, write scratchpad to thoughts.db,
        and return only final_response.
        """
        from maccre_core.schemas.sovereign_schema import dict_to_dataclass

        try:
            data_dict = json.loads(raw_json)
            parsed = dict_to_dataclass(AgentResponse, data_dict)
        except Exception:
            # JSON failed entirely — log raw as a thought fragment and return it
            import logging
            logging.getLogger(__name__).warning(f"[PARSE_FAILURE] raw={raw_json[:500]}")
            return raw_json

        import os
        project_name = os.environ.get("MACCRE_ACTIVE_PROJECT", "GLOBAL")
        
        # Route the JSON scratchpad into the standard stdout stream so _FileTee 
        # captures it as a standard <thought> block for the unified ledger.
        if parsed.scratchpad:
            print(f"<thought>\n{parsed.scratchpad}\n</thought>\n")
        if parsed.final_response:
            try:
                from maccre_core.tools.rag_tools import vectorize_ledger
                vectorize_ledger(parsed.final_response, project_name, session_id, agent_name)
            except Exception as e:
                import logging
                logging.getLogger(__name__).warning(f"Failed to vectorize ledger: {e}")

        return parsed.final_response