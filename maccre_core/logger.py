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
maccre_core/logger.py
======================
Dual-Channel Operations Logger for the MACCREv2 swarm.

Channel A — Rich/JSON console output (human-scannable in the terminal).
Channel B — Silent structured writes into the correct telemetry_db.py silo.

Usage (any MACCRE module):
    from maccre_core.logger import ops_log
    ops_log.tool_fired("execute_render_pipeline", session_id, project_id, cost=0.021)
    ops_log.node_routed("Auteur", "STOP", job_id, duration_ms=1243)
    ops_log.agent_thought(scratchpad_text, session_id, project_id, agent_id)
"""
from __future__ import annotations

import gzip
import json
import logging
import os
import shutil
import sys
from datetime import datetime, timezone
from typing import Any

from maccre_core.utils.path_resolver import get_maccre_root


# ── JSON Formatter ────────────────────────────────────────────────────────────

class JSONFormatter(logging.Formatter):
    """
    Forces all logs into deterministic JSON.
    Critical for allowing the Graph Ingestion Pipeline to parse logs without regex.
    """
    def format(self, record: logging.LogRecord) -> str:
        log_record: dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "funcName": record.funcName,
            "lineNo": record.lineno,
        }

        extra_data = record.__dict__.get("extra_data")
        if extra_data is not None:
            log_record["metadata"] = extra_data

        exc_info = record.exc_info
        if exc_info is not None:
            log_record["exception"] = self.formatException(exc_info)

        return json.dumps(log_record)


# ── Formatters ─────────────────────────────────────────────────────────────────

class HumanFormatter(logging.Formatter):
    """Clean, line-by-line operational readouts for terminal and Op-logs."""
    def format(self, record: logging.LogRecord) -> str:
        ts = datetime.now(timezone.utc).strftime("%H:%M:%S")
        msg = f"[{ts}] {record.getMessage()}"
        extra = record.__dict__.get("extra_data")
        if extra and isinstance(extra, dict):
            # Suppress default internal trackers for human-readability
            filtered = {k: v for k, v in extra.items() if k not in ["session_id", "project_id"] and v}
            if filtered:
                msg += f" | {filtered}"
        
        # We manually attach the string exception for human readability if it hit
        if record.exc_info:
            msg += f"\n[FAULT] {self.formatException(record.exc_info)}"
            
        return msg

# Global Override Flag
ENABLE_DEBUG_LOGGING: bool = True

# ── Logger Factories ──────────────────────────────────────────────────────────

class DynamicStreamHandler(logging.StreamHandler):
    def emit(self, record: logging.LogRecord) -> None:
        self.stream = sys.stdout
        super().emit(record)

def setup_maccre_logger(name: str) -> logging.Logger:
    """
    Singleton-style pre-startup logger instantiation.
    Used exclusively before a workbook parses.
    Usage: logger = setup_maccre_logger(__name__)
    """
    _logger = logging.getLogger(name)

    if _logger.hasHandlers():
        return _logger

    _logger.setLevel(logging.DEBUG)

    stdout_handler = DynamicStreamHandler()
    stdout_handler.setFormatter(JSONFormatter())
    _logger.addHandler(stdout_handler)

    log_path = get_maccre_root() / "maccre_system.log"
    file_handler = logging.FileHandler(str(log_path), encoding="utf-8")
    file_handler.setFormatter(JSONFormatter())
    _logger.addHandler(file_handler)

    return _logger


# ── Module-level base singleton ───────────────────────────────────────────────
logger: logging.Logger = setup_maccre_logger("maccre_core")


# ── Session Management ────────────────────────────────────────────────────────

def setup_session_loggers(project_id: str, session_id: str) -> None:
    """
    Called by SwarmWorker immediately upon parsing the requested Workbook.
    Isolates telemetry natively into Datacenter Op-logs and Bug-logs.
    """
    from maccre_core.logger import ops_log
    
    # 1. Purge the default global fallback file handler
    for handler in ops_log._log.handlers[:]:
        if isinstance(handler, logging.FileHandler):
            ops_log._log.removeHandler(handler)
            handler.close()

    # Ensure paths exist
    from maccre_core.utils.path_resolver import get_maccre_root
    dc_root = get_maccre_root() / "__DATACENTER" / project_id
    op_dir = dc_root / "Op-logs"
    bug_dir = dc_root / "Bug-logs"
    
    os.makedirs(op_dir, exist_ok=True)
    os.makedirs(bug_dir, exist_ok=True)
    
    # 2. Wire Human Operational Logger
    op_handler = logging.FileHandler(str(op_dir / f"{session_id}.log"), encoding="utf-8")
    op_handler.setLevel(logging.INFO)
    op_handler.setFormatter(HumanFormatter())
    ops_log._log.addHandler(op_handler)
    
    # 3. Wire JSON Debug Logger natively
    if ENABLE_DEBUG_LOGGING:
        bug_handler = logging.FileHandler(str(bug_dir / f"{session_id}.log"), encoding="utf-8")
        bug_handler.setLevel(logging.DEBUG)
        bug_handler.setFormatter(JSONFormatter())
        ops_log._log.addHandler(bug_handler)
    
    ops_log.tool_fired("setup_session_loggers", session_id, project_id, result_summary="Session Telemetry Active")


def clear_session_logs(project_id: str, session_id: str, target: str = "all") -> str:
    """Targeted destruction of past session logs."""
    from maccre_core.utils.path_resolver import get_datacenter_path
    
    dc_root = get_datacenter_path() / project_id
    deleted = 0
    
    if target in ("all", "op"):
        p = dc_root / "Op-logs" / f"{session_id}.log"
        if p.exists():
            os.remove(str(p))
            deleted += 1
            
    if target in ("all", "bug"):
        p = dc_root / "Bug-logs" / f"{session_id}.log"
        if p.exists():
            os.remove(str(p))
            deleted += 1
            
    return f"Purged {deleted} session log files."


# ── Global Pre-Session Utilities ──────────────────────────────────────────────

_DEFAULT_LOG_PATH: str = str(get_maccre_root() / "maccre_system.log")


def get_log_size_mb(log_path: str = _DEFAULT_LOG_PATH) -> float:
    """Returns the current size of the active log file in megabytes."""
    try:
        return os.path.getsize(log_path) / (1024 * 1024)
    except OSError:
        return 0.0


def clear_log_file(log_path: str = _DEFAULT_LOG_PATH) -> None:
    """Truncates the log file to zero bytes WITHOUT closing or re-opening it.

    Uses file.truncate(0) rather than os.remove() so that any FileHandler
    instances held by running swarm-worker daemons keep their file descriptors
    open and valid — they will simply start writing from byte 0 again.
    """
    try:
        with open(log_path, "r+", encoding="utf-8") as log_file:
            log_file.seek(0)
            log_file.truncate(0)
    except FileNotFoundError:
        pass


def rotate_logs(archive_dir: str | None = None) -> str:
    """Gzip-compress the active maccre_system.log and move it to the archive.

    Creates the archive directory if it does not exist. After compression the
    live log file is truncated to zero bytes so running FileHandler instances
    remain valid.

    Args:
        archive_dir: Absolute path of the destination directory.
            Defaults to ``B:\\MACCREv2\\_archive\\logs``.

    Returns:
        Absolute path of the newly created ``.log.gz`` file, or an error
        message string prefixed with ``[ROTATE_FAULT]``.
    """
    try:
        dest_dir = archive_dir or str(get_maccre_root() / "_archive" / "logs")
        os.makedirs(dest_dir, exist_ok=True)

        ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H-%M-%S")
        gz_path = os.path.join(dest_dir, f"{ts}_session.log.gz")

        src = _DEFAULT_LOG_PATH
        if not os.path.exists(src):
            return f"[ROTATE_FAULT] Log file not found: {src}"

        with open(src, "rb") as f_in, gzip.open(gz_path, "wb") as f_out:
            shutil.copyfileobj(f_in, f_out)

        # Truncate in-place — do NOT delete so running handlers stay valid
        clear_log_file(src)
        logger.info("Log rotated", extra={"extra_data": {"archive": gz_path}})
        return gz_path

    except Exception as e:
        return f"[ROTATE_FAULT] {e}"


# ── OperationsLogger — Dual-Channel Dispatcher ───────────────────────────────

class OperationsLogger:
    """Semantic dual-channel dispatcher for MACCREv2 operational telemetry.

    Every method writes to two simultaneous channels:
      A) The root ``maccre_core`` JSON logger (console + file).
      B) The appropriate ``telemetry_db`` silo (structured SQLite insert).

    Import the module-level singleton::

        from maccre_core.logger import ops_log
        ops_log.tool_fired("my_tool", session_id, project_id, cost=0.012)
    """

    def __init__(self) -> None:
        self._log: logging.Logger = setup_maccre_logger("maccre_core.ops")

    # ── Channel A helpers ─────────────────────────────────────────────────────

    def _emit(self, level: int, msg: str, meta: dict[str, Any]) -> None:
        """Write to Channel A (JSON logger)."""
        self._log.log(level, msg, extra={"extra_data": meta})

    # ── Semantic Methods ──────────────────────────────────────────────────────

    def tool_fired(
        self,
        tool_name: str,
        session_id: str = "",
        project_id: str = "",
        agent_id: str = "",
        source_node: str = "",
        cost: float = 0.0,
        result_summary: str = "",
    ) -> None:
        """Log a tool invocation event to console and system_logs.db.

        Args:
            tool_name: The registered name of the MACCRE tool called.
            session_id: Active session identifier.
            project_id: Active project identifier.
            agent_id: Calling agent identifier.
            source_node: Topology node initiating the call.
            cost: Estimated or actual token cost in USD.
            result_summary: A short string summary of the tool result.
        """
        meta: dict[str, Any] = {
            "tool": tool_name,
            "session_id": session_id,
            "project_id": project_id,
            "agent_id": agent_id,
            "source_node": source_node,
            "cost": cost,
        }
        self._emit(logging.INFO, f"[TOOL_FIRED] {tool_name}", meta)

        # Channel B
        try:
            from maccre_core.orchestration.telemetry_db import log_system_event
            log_system_event(
                action_type="TOOL_FIRED",
                payload=json.dumps({"tool": tool_name, "result": result_summary}),
                cost=cost,
                session_id=session_id,
                project_id=project_id,
                agent_id=agent_id,
                source_node=source_node,
            )
        except Exception as tdb_err:
            self._emit(logging.WARNING, f"[OPS_LOG] telemetry_db write failed: {tdb_err}", {})

    def node_routed(
        self,
        agent_name: str,
        next_node: str,
        job_id: str,
        session_id: str = "",
        project_id: str = "",
        agent_id: str = "",
        source_node: str = "",
        duration_ms: int = 0,
    ) -> None:
        """Log a topology routing event to console and system_logs.db.

        Args:
            agent_name: Human-readable name of the agent completing the node.
            next_node: The node_id the task was routed to.
            job_id: The swarm job identifier.
            session_id: Active session identifier.
            project_id: Active project identifier.
            agent_id: OS-level agent process identifier.
            source_node: Topology node that completed execution.
            duration_ms: Wall-clock execution time in milliseconds.
        """
        meta: dict[str, Any] = {
            "agent": agent_name,
            "next_node": next_node,
            "job_id": job_id,
            "duration_ms": duration_ms,
            "session_id": session_id,
            "project_id": project_id,
        }
        self._emit(logging.INFO, f"[NODE_ROUTED] {agent_name} -> {next_node}", meta)

        try:
            from maccre_core.orchestration.telemetry_db import log_system_event
            log_system_event(
                action_type="NODE_ROUTED",
                payload=json.dumps({
                    "agent": agent_name,
                    "next_node": next_node,
                    "job_id": job_id,
                    "duration_ms": duration_ms,
                }),
                cost=0.0,
                session_id=session_id,
                project_id=project_id,
                agent_id=agent_id,
                source_node=source_node,
            )
        except Exception as tdb_err:
            self._emit(logging.WARNING, f"[OPS_LOG] telemetry_db write failed: {tdb_err}", {})

    def user_input(
        self,
        input_text: str,
        context_tags: str = "",
        session_id: str = "",
        project_id: str = "",
        agent_id: str = "",
        source_node: str = "",
    ) -> None:
        """Log an Architect / API input to console and user_interactions.db.

        Args:
            input_text: The raw user or API message text.
            context_tags: Free-form comma-separated context labels.
            session_id: Active session identifier.
            project_id: Active project identifier.
            agent_id: Receiving agent identifier.
            source_node: The entry point (e.g. ``'maccre.py'``, ``'MCP'``).
        """
        preview = input_text[:120].replace("\n", " ")
        self._emit(
            logging.INFO,
            f"[USER_INPUT] {preview}{'...' if len(input_text) > 120 else ''}",
            {"session_id": session_id, "project_id": project_id, "tags": context_tags},
        )

        try:
            from maccre_core.orchestration.telemetry_db import log_user_interaction
            log_user_interaction(
                input_text=input_text,
                context_tags=context_tags,
                session_id=session_id,
                project_id=project_id,
                agent_id=agent_id,
                source_node=source_node,
            )
        except Exception as tdb_err:
            self._emit(logging.WARNING, f"[OPS_LOG] user_interactions.db write failed: {tdb_err}", {})

    def terminal_command(
        self,
        command_run: str,
        std_output: str,
        is_error: bool = False,
        session_id: str = "",
        project_id: str = "",
        agent_id: str = "",
        source_node: str = "",
    ) -> None:
        """Log a completed venv subprocess command to console and terminal_logs.db.

        Args:
            command_run: The shell command that was executed.
            std_output: Combined stdout/stderr output.
            is_error: True if the process exited with a non-zero return code.
            session_id: Active session identifier.
            project_id: Active project identifier.
            agent_id: Calling agent identifier.
            source_node: Topology node that issued the command.
        """
        level = logging.ERROR if is_error else logging.INFO
        label = "TERMINAL_ERROR" if is_error else "TERMINAL_OK"
        self._emit(level, f"[{label}] {command_run[:80]}", {"session_id": session_id})

        try:
            from maccre_core.orchestration.telemetry_db import log_terminal_command
            log_terminal_command(
                command_run=command_run,
                std_output=std_output,
                is_error=is_error,
                session_id=session_id,
                project_id=project_id,
                agent_id=agent_id,
                source_node=source_node,
            )
        except Exception as tdb_err:
            self._emit(logging.WARNING, f"[OPS_LOG] terminal_logs.db write failed: {tdb_err}", {})

    # ── Flow Ledgers (Bifurcated) ─────────────────────────────────────────────

    def flow_chat(
        self,
        job_id: str,
        role: str,
        agent_name: str,
        content: str,
        session_id: str = "",
        project_id: str = "",
    ) -> None:
        """Write conversational output to the FlowChat ledger JSONL."""
        from maccre_core.schemas.ledger_models import FlowChatEntry
        from maccre_core.utils.path_resolver import get_datacenter_path
        
        entry = FlowChatEntry(
            job_id=job_id,
            role=role,
            agent_name=agent_name,
            content=content
        )
        
        # We append as JSON Lines (JSONL)
        dc_root = get_datacenter_path() / project_id if project_id else get_datacenter_path("GLOBAL")
        ledger_dir = dc_root / "03_Agent_Ledgers" / "FlowChat"
        os.makedirs(ledger_dir, exist_ok=True)
        
        file_path = ledger_dir / f"{session_id}.jsonl"
        try:
            with open(file_path, "a", encoding="utf-8") as f:
                f.write(entry.to_json() + "\n")
        except Exception as err:
            self._emit(logging.WARNING, f"[OPS_LOG] FlowChat write failed: {err}", {})

        # Emit minimal console signal
        self._emit(logging.INFO, f"[FLOW_CHAT] {role.upper()}: {agent_name} -> {content[:50]}...", {"job_id": job_id})


    def flow_system(
        self,
        job_id: str,
        agent_name: str,
        model_id: str,
        system_prompt: str,
        scratchpad_thought: str,
        tool_calls: list[dict[str, Any]],
        tool_results: list[dict[str, Any]],
        input_tokens: int,
        output_tokens: int,
        duration_ms: int,
        cost: float,
        session_id: str = "",
        project_id: str = "",
    ) -> None:
        """Write compute exhaust to the FlowSystem ledger JSONL."""
        from maccre_core.schemas.ledger_models import FlowSystemEntry
        from maccre_core.utils.path_resolver import get_datacenter_path
        
        entry = FlowSystemEntry(
            job_id=job_id,
            agent_name=agent_name,
            model_id=model_id,
            system_prompt=system_prompt,
            scratchpad_thought=scratchpad_thought,
            tool_calls=tool_calls,
            tool_results=tool_results,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            duration_ms=duration_ms,
            cost=cost
        )
        
        dc_root = get_datacenter_path() / project_id if project_id else get_datacenter_path("GLOBAL")
        ledger_dir = dc_root / "03_Agent_Ledgers" / "FlowSystem"
        os.makedirs(ledger_dir, exist_ok=True)
        
        file_path = ledger_dir / f"{session_id}.jsonl"
        try:
            with open(file_path, "a", encoding="utf-8") as f:
                f.write(entry.to_json() + "\n")
        except Exception as err:
            self._emit(logging.WARNING, f"[OPS_LOG] FlowSystem write failed: {err}", {})

        self._emit(logging.DEBUG, f"[FLOW_SYSTEM] Exhaust saved for {agent_name}", {"job_id": job_id})



# ── Module-level OperationsLogger singleton ───────────────────────────────────
#: Import this in any module that needs structured telemetry:
#:   from maccre_core.logger import ops_log
ops_log: OperationsLogger = OperationsLogger()