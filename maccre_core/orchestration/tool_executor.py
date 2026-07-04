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
maccre_core/orchestration/tool_executor.py
==========================================
Phase 20 — Tool Executor Microservice.

Provides a single, hardened `ToolExecutor` class that both the TUI
interactive shell (`maccre.py`) and the background Swarm Worker
(`swarm_worker.py`) use for parsing and dispatching Gemini tool calls.

Before Phase 20, each module had its own copy of the parsing loop —
a DRY violation that required dual maintenance. This microservice
eliminates that.

Architecture:
  - Parses both JSON-array ("LOCAL TOOL CALL REQUESTED: [...]") and
    plain-text ("TOOL CALL REQUESTED: tool_name - {...}") formats.
  - Dispatches through TOOL_DISPATCHER — never raw evals.
  - Appends tool result to a rolling prompt ledger (caller owns the ledger).
  - Returns a (did_fire: bool, updated_prompt: str) tuple so callers can
    decide whether to continue the generation loop.
"""
from __future__ import annotations

import json
import logging
from typing import Any

from maccre_core.logger import ops_log
from maccre_core.tools.tool_registry import TOOL_DISPATCHER
from maccre_core.orchestration.tool_executor_interface import ToolDispatcher as ToolDispatcherABC

logger = logging.getLogger("maccre_core")

_TOOL_CALL_MARKERS = ("TOOL CALL REQUESTED:", "LOCAL TOOL CALL REQUESTED:")


def _contains_tool_call(text: str) -> bool:
    return any(marker in text for marker in _TOOL_CALL_MARKERS)


class ToolExecutor(ToolDispatcherABC):
    """Stateless tool call parser and dispatcher.

    Usage (TUI loop):
        executor = ToolExecutor()
        did_fire, updated_prompt = executor.run(response_text, current_prompt)

    Usage (Swarm Worker):
        executor = ToolExecutor()
        did_fire, output_text = executor.run(final_output_text, final_output_text)
    """

    def run(
        self,
        response_text: str,
        current_prompt: str,
        session_id: str = "",
        project_id: str = "",
        agent_id: str = "",
        is_final_turn: bool = True,
    ) -> tuple[bool, str]:
        """Parse a model response for a tool call and dispatch it if found.

        Args:
            response_text: Raw text returned by the model.
            current_prompt: The current rolling prompt ledger to append results to.
            session_id: Active session identifier (forwarded to ops_log).
            project_id: Active project identifier (forwarded to ops_log).
            agent_id: Calling agent identifier (forwarded to ops_log).

        Returns:
            (did_fire, updated_prompt):
                did_fire      — True if a tool was found and executed.
                updated_prompt — The prompt ledger with the tool result appended,
                                 or the original prompt if no tool was found.
        """
        if not _contains_tool_call(response_text):
            return False, current_prompt

        t_name, t_args = self._parse(response_text)
        if t_name is None:
            logger.warning("[ToolExecutor] Tool call detected but could not be parsed.")
            return False, current_prompt + "\n\n[SYSTEM_TOOL_CALLBACK]: PARSE_FAULT — could not extract tool name/args."

        logger.info(f"[ToolExecutor] ⚡ TOOL_FIRE: {t_name}")

        result: str
        if t_name not in TOOL_DISPATCHER:
            result = f"FAULT — '{t_name}' not found in TOOL_DISPATCHER."
        else:
            try:
                import os as _os  # noqa: PLC0415

                # ── Project-Aware Environment Injection ──────────────────────
                # ProjectAwareAdapter reads MACCRE_ACTIVE_PROJECT from os.environ
                # at call time. In async/threaded contexts the env var may be
                # 'GLOBAL' even when the swarm is running against a real project.
                # Inject it here — before every dispatch — so all storage tools
                # (read_file, write_file, file_exists, etc.) resolve correctly.
                _prev_project = _os.environ.get("MACCRE_ACTIVE_PROJECT", "GLOBAL")
                if project_id:
                    _os.environ["MACCRE_ACTIVE_PROJECT"] = project_id

                # ── Dynamic Native Injection ──────────────────────────────────
                # Render tools: strip any model-supplied session_dir unconditionally,
                # then inject the correct project-scoped path. The model must never
                # control where media lands — the runtime owns this routing.
                if t_name in (
                    "execute_render_pipeline", "render_podcast_audio",
                    "render_video", "render_image", "render_image_batch",
                ):
                    t_args.pop("session_dir", None)  # discard model-supplied value
                    if project_id:
                        from maccre_core.utils.path_resolver import get_datacenter_path  # noqa: PLC0415
                        t_args["session_dir"] = str(
                            get_datacenter_path(f"05_Rendered_Media/{session_id}")
                        )

                # ── Auto-scope write_file to session artifact directory ────────
                # Any write_file call targeting 04_Code_Artifacts/ is silently
                # routed to 04_Code_Artifacts/{session_id}/ so every swarm run
                # has its own isolated output folder. No workbook changes needed.
                # Guard: skip if session_id is already in the path (i.e. the
                # agent already received the resolved {SESSION_ID} token in its
                # instruction and wrote the full session-scoped path itself).
                if t_name == "write_file" and session_id:
                    _write_path = str(t_args.get("path", ""))
                    _PREFIX = "04_Code_Artifacts/"
                    if _write_path.startswith(_PREFIX) and session_id not in _write_path:
                        _rel_part = _write_path[len(_PREFIX):]
                        t_args["path"] = f"{_PREFIX}{session_id}/{_rel_part}"
                        logger.debug(
                            "[ToolExecutor] write_file auto-scoped: %s → %s",
                            _write_path, t_args['path'],
                        )
                        pass
                
                # Sandbox write_file to the active session directory
                if t_name == "write_file" and session_id:
                    path = t_args.get("path", "")
                    if not path.startswith(f"04_Code_Artifacts/{session_id}"):
                        import pathlib
                        if path.startswith("04_Code_Artifacts/"):
                            # Agent forgot session_id
                            fixed_path = f"04_Code_Artifacts/{session_id}/{path.split('04_Code_Artifacts/')[-1].lstrip('/')}"
                        else:
                            # Agent tried to write somewhere else, force into session folder
                            basename = pathlib.Path(path).name
                            fixed_path = f"04_Code_Artifacts/{session_id}/{basename}"
                        t_args["path"] = fixed_path
                        logger.info(f"[ToolExecutor] Sandboxed write_file path from '{path}' to '{fixed_path}'")

                result = str(TOOL_DISPATCHER[t_name](**t_args))

            except Exception as e:
                result = f"EXECUTION_FAULT — {t_name} raised: {e}"
                logger.error(f"[ToolExecutor] {result}")
            finally:
                # Restore env so any other thread/context is unaffected
                if project_id:
                    _os.environ["MACCRE_ACTIVE_PROJECT"] = _prev_project

        # ── Initiative 4: Emit structured tool-fire event via OperationsLogger ──
        ops_log.tool_fired(
            tool_name=t_name,
            result_summary=result[:200],
            session_id=session_id,
            project_id=project_id,
            agent_id=agent_id,
        )

        if is_final_turn:
            sys_suffix = (
                "\n\n[SYSTEM]: Tool execution complete. Produce your final output now. "
                f"Do NOT call '{t_name}' or any other tool again."
            )
        else:
            sys_suffix = (
                "\n\n[SYSTEM]: Tool result received. Review the result and continue your task. "
                "Call your next required tool, or if research is complete, produce your final output."
            )
        updated_prompt = (
            current_prompt
            + f"\n\n[MODEL_ACTION]:\n{response_text}"
            + f"\n\n[SYSTEM_TOOL_CALLBACK - '{t_name}' Executed]: {result}"
            + sys_suffix
        )
        return True, updated_prompt

    def _parse(self, text: str) -> tuple[str | None, dict[str, Any]]:
        """Extract tool name and args from the model response text.

        Handles three emission formats from the model:
          A) JSON array  → "TOOL CALL REQUESTED: [{"function": {"name":...,"arguments":...}}]"
          B) JSON dict   → "TOOL CALL REQUESTED: write_file - {"path": "...", "data": "..."}"
          C) Python dict → "TOOL CALL REQUESTED: write_file - {'path': '...', 'data': '...'}"

        Format C is the most common failure mode — Gemini occasionally emits single-quoted
        Python dicts instead of JSON. ast.literal_eval safely handles this.
        """
        import ast  # noqa: PLC0415

        try:
            # ── Format A: JSON array  ─────────────────────────────────────────
            if "LOCAL TOOL CALL" in text or "TOOL CALL REQUESTED: [" in text:
                start = text.find("[{")
                end = text.rfind("}]") + 2
                if start != -1 and end > 1:
                    tool_array: list[dict[str, Any]] = json.loads(
                        text[start:end], strict=False
                    )
                    t_name: str = tool_array[0]["function"]["name"]
                    raw_args = tool_array[0]["function"]["arguments"]
                    t_args: dict[str, Any] = (
                        json.loads(raw_args, strict=False)
                        if isinstance(raw_args, str)
                        else raw_args
                    )
                    return t_name, t_args

            # ── Formats B & C: "TOOL CALL REQUESTED: <name> - <args>" ─────────
            _header, _, payload = text.partition("TOOL CALL REQUESTED:")
            if not payload:
                return None, {}

            payload = payload.strip()
            # Strip wrapping "[...]"  if model wrapped the whole thing
            if payload.startswith("[") and payload.endswith("]"):
                payload = payload[1:-1].strip()

            name_part, sep, args_part = payload.partition(" - ")
            t_name = name_part.strip()
            if not sep or not t_name:
                return None, {}

            args_str = args_part.strip().rstrip("]").strip()

            # Stage B: try strict JSON first
            parsed_args: dict[str, Any] = {}
            _parse_succeeded = False
            try:
                parsed_args = json.loads(args_str, strict=False)
                _parse_succeeded = True
            except (json.JSONDecodeError, ValueError):
                pass

            # Stage C: fall back to ast.literal_eval for single-quoted Python dicts
            if not _parse_succeeded:
                try:
                    result = ast.literal_eval(args_str)
                    if isinstance(result, dict):
                        parsed_args = result
                        _parse_succeeded = True
                except (ValueError, SyntaxError):
                    pass

            if not _parse_succeeded:
                logger.warning("[ToolExecutor] Could not parse args via JSON or ast: %s", args_str[:120])
                return None, {}

            # ── Arg key normalisation for write_file ─────────────────────────
            # Models sometimes emit 'path'/'file_path'/'filename' instead of 'path'
            # and 'data'/'content'/'text' instead of 'data'.
            if t_name == "write_file":
                for alias in ("file_path", "filename", "filepath"):
                    if alias in parsed_args and "path" not in parsed_args:
                        parsed_args["path"] = parsed_args.pop(alias)
                for alias in ("content", "text", "body"):
                    if alias in parsed_args and "data" not in parsed_args:
                        parsed_args["data"] = parsed_args.pop(alias)

            return t_name, parsed_args

        except Exception as exc:
            logger.warning("[ToolExecutor] Parse failure: %s", exc)
            return None, {}

