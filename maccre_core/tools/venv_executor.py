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
maccre_core/tools/venv_executor.py
====================================
Stateful, persistent venv shell for real-time command execution.

Provides two interfaces:

1. ``execute_in_venv(command)`` — stateless one-shot generator (preserved
   from the previous implementation for backwards-compatibility with
   existing callers).

2. ``PersistentVenvShell`` — a stateful class that spawns a single
   ``cmd.exe`` process, activates the .venv once, and reuses the live
   shell session for all subsequent commands.  Dramatically faster than
   spawning a new process per command (no repeated venv activation cost).

Architecture (non-blocking I/O):
  Two daemon threads drive stdout and stderr into a shared ``queue.Queue``
  keyed by channel tag.  ``execute_command`` dequeues from the live queue
  and yields tagged lines in real-time, then flushes all queued output to
  the Telemetry Matrix (terminal_logs.db) atomically when the sentinel
  marker is detected.

Shell protocol:
  After each user command, a unique sentinel ``echo __MACCRE_DONE__``
  is injected.  The reader loop terminates on ``__MACCRE_DONE__``, giving
  us a clean end-of-output signal without needing to wait for process exit.

Zombie prevention (omni clean compliance):
  ``close()`` writes ``exit\\n`` to stdin and ``join()``s both reader
  threads before ``terminate()`` /  ``wait()``.
"""

import os
import queue
import subprocess
import threading
from collections.abc import Generator
from typing import Optional, Self

from maccre_core.orchestration.telemetry_db import (
    log_terminal_command,
    log_user_interaction,
)
from maccre_core.utils.path_resolver import get_maccre_root

import logging

logger = logging.getLogger(__name__)

_REPO_ROOT    = get_maccre_root()
_VENV_PYTHON  = _REPO_ROOT / ".venv" / "Scripts" / "python.exe"
_VENV_ACTIVATE = _REPO_ROOT / ".venv" / "Scripts" / "activate.bat"
_SENTINEL     = "__MACCRE_DONE__"


# ── Stateless one-shot helper (backwards-compatible) ─────────────────────────

def execute_in_venv(command: str) -> Generator[str, None, None]:
    """Execute a single command inside the .venv and yield output lines.

    Args:
        command: Shell command string, e.g. ``"python test_scatter.py"``.

    Yields:
        Tagged output lines: ``[STDOUT] ...``, ``[STDERR] ...``, ``[EXIT] ...``.
    """
    if not _VENV_PYTHON.exists():
        yield f"[STDERR] VENV_PYTHON_MISSING: '{_VENV_PYTHON}' not found."
        return

    env = os.environ.copy()
    env["PATH"] = str(_VENV_PYTHON.parent) + os.pathsep + env.get("PATH", "")
    env["VIRTUAL_ENV"] = str(_REPO_ROOT / ".venv")
    env.pop("PYTHONHOME", None)

    if command.strip().startswith("python "):
        full_command = str(_VENV_PYTHON) + " " + command.strip()[len("python "):]
    else:
        full_command = command

    process: Optional[subprocess.Popen[str]] = None
    try:
        process = subprocess.Popen(
            full_command, shell=True,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, encoding="utf-8", errors="replace",
            env=env, cwd=str(_REPO_ROOT),
        )

        line_q: queue.Queue[str | None] = queue.Queue()

        def _reader(stream: object, tag: str) -> None:
            for line in stream:  # type: ignore[union-attr]
                line_q.put(f"[{tag}] {line.rstrip()}")
            line_q.put(None)

        threading.Thread(target=_reader, args=(process.stdout, "STDOUT"), daemon=True).start()
        threading.Thread(target=_reader, args=(process.stderr, "STDERR"), daemon=True).start()

        sentinels = 0
        while sentinels < 2:
            item = line_q.get()
            if item is None:
                sentinels += 1
            else:
                yield item

        process.wait()
        yield f"[EXIT] Return code: {process.returncode}"
    except Exception as exc:
        yield f"[STDERR] EXECUTOR_ERROR: {exc}"
    finally:
        if process is not None:
            try:
                if process.stdout:
                    process.stdout.close()
                if process.stderr:
                    process.stderr.close()
            except Exception:
                pass


# ── Stateful Persistent Shell ─────────────────────────────────────────────────

class PersistentVenvShell:
    """
    A long-lived ``cmd.exe`` process with the .venv pre-activated.

    Spawn once, reuse the shell session for the duration of the Flet GUI
    session.  Eliminates the per-command activation overhead (~0.5–2 s).

    Usage::

        shell = PersistentVenvShell(session_id="gui-001", project_id="PRISM")
        for line in shell.execute_command("python test_scatter.py"):
            logger.info(line)
        shell.close()

    Or use as a context manager::

        with PersistentVenvShell("gui-001", "PRISM") as shell:
            for line in shell.execute_command("omni qa maccre_core"):
                logger.info(line)
    """

    def __init__(self, session_id: str = "", project_id: str = "") -> None:
        self.session_id  = session_id
        self.project_id  = project_id
        self._closed     = False
        self._output_q: queue.Queue[str | None] = queue.Queue()

        env = os.environ.copy()
        env["VIRTUAL_ENV"] = str(_REPO_ROOT / ".venv")
        env.pop("PYTHONHOME", None)

        self._process = subprocess.Popen(
            "cmd.exe",
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=env,
            cwd=str(_REPO_ROOT),
        )

        # Start non-blocking reader threads immediately
        self._stdout_thread = threading.Thread(
            target=self._reader, args=(self._process.stdout, "STDOUT"), daemon=True
        )
        self._stderr_thread = threading.Thread(
            target=self._reader, args=(self._process.stderr, "STDERR"), daemon=True
        )
        self._stdout_thread.start()
        self._stderr_thread.start()

        # Activate .venv — consume all activation banner output silently
        self._send_raw(f'"{_VENV_ACTIVATE}"')
        self._drain_until_sentinel()

    # ── Internal helpers ──────────────────────────────────────────────────────

    def _reader(self, stream: object, tag: str) -> None:
        """Daemon thread: writes tagged lines into the shared queue."""
        try:
            for line in stream:  # type: ignore[union-attr]
                self._output_q.put(f"[{tag}] {line.rstrip()}")
        except ValueError:
            pass  # Stream closed on shutdown
        finally:
            self._output_q.put(None)  # sentinel

    def _send_raw(self, command: str) -> None:
        """Write a raw command line to the shell stdin."""
        if self._process.stdin and not self._closed:
            self._process.stdin.write(command + "\n")
            self._process.stdin.flush()

    def _drain_until_sentinel(self) -> list[str]:
        """
        Consume the output queue until the __MACCRE_DONE__ sentinel line
        appears.  Returns all collected lines (without the sentinel).
        """
        collected: list[str] = []
        active_channels = 2  # stdout + stderr threads

        while True:
            try:
                item = self._output_q.get(timeout=30.0)
            except queue.Empty:
                break

            if item is None:
                active_channels -= 1
                if active_channels <= 0:
                    break
                continue

            if _SENTINEL in item:
                break  # Clean end-of-command signal

            collected.append(item)

        return collected

    # ── Public interface ──────────────────────────────────────────────────────

    def execute_command(
        self,
        command: str,
        agent_id: str = "",
        source_node: str = "",
    ) -> Generator[str, None, None]:
        """
        Execute a command in the persistent shell and yield output lines.

        Silently logs the command to ``user_interactions.db`` before sending
        it, and logs the aggregated output block to ``terminal_logs.db``
        after the sentinel is detected.

        Args:
            command:     Shell command to execute.
            agent_id:    Optional agent identifier for telemetry tagging.
            source_node: Optional topology node name for telemetry tagging.

        Yields:
            Tagged line strings: ``[STDOUT] ...``, ``[STDERR] ...``.
        """
        if self._closed:
            yield "[STDERR] SHELL_CLOSED: This PersistentVenvShell instance has been closed."
            return

        # Log intent to telemetry (non-blocking — fire and forget)
        log_user_interaction(
            input_text=command,
            context_tags="venv_shell",
            session_id=self.session_id,
            project_id=self.project_id,
            agent_id=agent_id,
            source_node=source_node,
        )

        # Inject command then immediately inject sentinel marker
        self._send_raw(command)
        self._send_raw(f"echo {_SENTINEL}")

        # Stream output to caller, accumulate for telemetry
        aggregated: list[str] = []
        active_channels = 2
        has_error = False

        while True:
            try:
                item = self._output_q.get(timeout=30.0)
            except queue.Empty:
                yield "[STDERR] TIMEOUT: Command produced no output within 30s."
                break

            if item is None:
                active_channels -= 1
                if active_channels <= 0:
                    break
                continue

            if _SENTINEL in item:
                break  # End of this command's output

            if "[STDERR]" in item:
                has_error = True
            aggregated.append(item)
            yield item

        # Flush aggregated output to telemetry matrix
        log_terminal_command(
            command_run=command,
            std_output="\n".join(aggregated),
            is_error=has_error,
            session_id=self.session_id,
            project_id=self.project_id,
            agent_id=agent_id,
            source_node=source_node,
        )

    def close(self) -> None:
        """Gracefully terminate the persistent shell and join reader threads."""
        if self._closed:
            return
        self._closed = True
        try:
            self._send_raw("exit")
        except Exception:
            pass
        finally:
            self._stdout_thread.join(timeout=3.0)
            self._stderr_thread.join(timeout=3.0)
            try:
                self._process.terminate()
                self._process.wait(timeout=3.0)
            except Exception:
                pass

    # ── Context manager support ───────────────────────────────────────────────

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()
