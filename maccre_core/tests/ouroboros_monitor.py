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
maccre_core/tests/ouroboros_monitor.py
========================================
Ouroboros Live-Fix Monitor — Phase 12 Sovereign Watchdog.

Continuously watches two anomaly surfaces:
  1. SQLite WAL: tasks stuck in 'locked' state for > 45 seconds signal a dead
     worker that crashed without releasing its lock.
  2. Filesystem log tail: new 'Traceback' or 'CRITICAL FAILURE' strings in
     maccre_system.log signal a runtime crash.

On anomaly detection:
  - gemini-2.5-pro (Structured Output) evaluates the crash dump and outputs a
    strict ``OuroborosDecision`` JSON object.
  - LIVE_FIX  → writes a surgical patch directive for Antigravity to
    ``antigravity_live_fix.md`` and reverts stalled SQLite locks to 'open'.
  - RESET     → runs ``execute_factory_reset()`` and terminates the monitor.

Architecture:
  Dual-Pipeline: Cloud Accelerator (Gemini 2.5 Pro structured) +
                 Local Successor (SQLite Julian-day deadlock scan).
"""

import os
import sys
import time
import sqlite3
from typing import Literal

from dataclasses import dataclass, field
from maccre_core._net.omnidaemon import OmniDaemon

from maccre_core.tools.factory_reset import execute_factory_reset

_QUEUE_DB       = "B:/MACCREv2/__DATACENTER/swarm_queue.db"
_LOG_PATH       = "B:/MACCREv2/maccre_system.log"
_DIRECTIVE_PATH = "B:/MACCREv2/__DATACENTER/antigravity_live_fix.md"

# Deadlock threshold — seconds a task may stay 'locked' before it's flagged
_DEADLOCK_THRESHOLD_SEC: float = 45.0

# Maximum chars of new log content fed into the triage prompt
_MAX_LOG_TAIL: int = 2000


# ── Strict Decision Schema (Diamond Loop: Critic) ─────────────────────────────

@dataclass
class OuroborosDecision:
    diagnosis: str = field(
        metadata={"description": "Technical explanation of why the system stalled or crashed."}
    )
    action: Literal["LIVE_FIX", "RESET"] = field(
        metadata={"description": (
            "Choose LIVE_FIX for code bugs (TypeError, missing import, logic error). "
            "Choose RESET only for unrecoverable state corruption."
        )}
    )
    antigravity_directive: str = field(
        metadata={"description": (
            "If LIVE_FIX: exact markdown instructions for the Antigravity coding agent "
            "to patch the affected Python files. If RESET: leave blank."
        )}
    )
    justification: str = field(
        metadata={"description": "Why this action was chosen over the alternative."}
    )


# ── Monitor ───────────────────────────────────────────────────────────────────

class OuroborosMonitor:
    def __init__(self) -> None:
        self.daemon = OmniDaemon()
        # Track log file offset so we only scan new bytes each cycle
        self.last_log_size: int = 0

    # ── Anomaly Detection ─────────────────────────────────────────────────────

    def _detect_anomalies(self) -> str | None:
        """
        Dual-surface scan: SQLite deadlocks + log file crash signatures.

        Returns:
            A human-readable anomaly report string, or None if clean.
        """
        anomaly_report = ""

        # Surface 1: SQLite WAL — Julian-day deadlock scan
        if os.path.exists(_QUEUE_DB):
            try:
                with sqlite3.connect(_QUEUE_DB, timeout=5) as conn:
                    conn.row_factory = sqlite3.Row
                    conn.execute("PRAGMA journal_mode=WAL;")
                    cur = conn.execute("""
                        SELECT id, job_id, current_node, locked_by,
                               (julianday('now') - julianday(created_at)) * 86400 AS lock_sec
                        FROM task_queue
                        WHERE lock_status = 'locked'
                    """)
                    for row in cur.fetchall():
                        lock_sec = float(row["lock_sec"] or 0.0)
                        if lock_sec > _DEADLOCK_THRESHOLD_SEC:
                            anomaly_report += (
                                f"[DEADLOCK] Row {row['id']} stuck at node "
                                f"'{row['current_node']}' for {lock_sec:.1f}s "
                                f"(locked_by={row['locked_by']}).\n"
                            )
            except Exception as exc:
                anomaly_report += f"[QUEUE_ERROR] Could not scan task_queue: {exc}\n"

        # Surface 2: Log tail — crash signature scan
        if os.path.exists(_LOG_PATH):
            current_size = os.path.getsize(_LOG_PATH)
            if current_size > self.last_log_size:
                try:
                    with open(_LOG_PATH, "r", encoding="utf-8", errors="replace") as f:
                        f.seek(self.last_log_size)
                        new_logs = f.read()
                    self.last_log_size = current_size
                    if "Traceback" in new_logs or "CRITICAL FAILURE" in new_logs:
                        anomaly_report += (
                            f"[CRASH DUMP]\n{new_logs[-_MAX_LOG_TAIL:]}\n"
                        )
                except Exception as exc:
                    anomaly_report += f"[LOG_ERROR] Could not read log tail: {exc}\n"

        return anomaly_report.strip() if anomaly_report.strip() else None

    # ── Lock Releaser ─────────────────────────────────────────────────────────

    def _release_stalled_locks(self) -> None:
        """
        Reverts tasks stalled for > 45 seconds back to 'open'.

        This is the key to the live-fix loop: when a swarm worker dies mid-task
        its ``finally`` block never fires, leaving the row permanently 'locked'.
        After Antigravity patches the code, the next spawned worker will
        immediately pick up that exact row and retry from where the crash
        occurred.
        """
        if not os.path.exists(_QUEUE_DB):
            return
        try:
            with sqlite3.connect(_QUEUE_DB, timeout=5) as conn:
                conn.execute("PRAGMA journal_mode=WAL;")
                conn.execute("""
                    UPDATE task_queue
                    SET lock_status = 'open', locked_by = NULL
                    WHERE lock_status = 'locked'
                      AND (julianday('now') - julianday(created_at)) * 86400 > ?
                """, (_DEADLOCK_THRESHOLD_SEC,))
                conn.commit()
            print("[OUROBOROS] Stalled database locks released → tasks reverted to 'open'.")
        except Exception as exc:
            print(f"[OUROBOROS] WARNING: Could not release locks: {exc}")

    # ── LLM Triage ───────────────────────────────────────────────────────────

    def analyze_and_react(self, anomaly_data: str) -> None:
        """
        Dispatches the anomaly dump to Gemini 2.5 Pro (Structured Output).

        The response is parsed into an ``OuroborosDecision`` via Pydantic
        ``model_validate`` — fully Pyright-safe, no regex, no raw JSON groping.
        """
        print(
            "\n[OUROBOROS] Anomaly detected. Dispatching to Nexus Agent for triage..."
        )

        prompt = (
            "You are the Ouroboros Monitor, a Principal Reliability Engineer for "
            "the MACCREv2 Sovereign Edge pipeline. The Swarm has encountered an anomaly. "
            "Analyze the trace below carefully.\n\n"
            "If this is a code bug (TypeError, missing import, AttributeError, logic "
            "error, or any Python exception), choose LIVE_FIX and write a precise, "
            "surgical directive for the Antigravity coding agent that specifies exactly "
            "which file, which function, and which lines to modify.\n\n"
            "If the SQLite database schema is corrupted, a WAL file is torn, or the "
            "state is fundamentally unrecoverable by a code change alone, choose RESET.\n\n"
            f"ANOMALY TRACE:\n{anomaly_data}"
        )

        try:
            decision = self.daemon.generate(
                prompt=prompt,
                model_id="gemini-3.1-pro-preview", # Fallback to latest
                schema=OuroborosDecision,
                temperature=0.1,
                compute_tier="cloud", # Watchdog must be rock solid
            )
            
            if not decision:
                print("[OUROBOROS] Gemini returned an empty response. Skipping triage.")
                return

            print(f"\n{'=' * 60}")
            print(f"[OUROBOROS VERDICT] {decision.action}")
            print(f"{'=' * 60}")
            print(f"Diagnosis    : {decision.diagnosis}")
            print(f"Justification: {decision.justification}")

            if decision.action == "LIVE_FIX":
                os.makedirs(os.path.dirname(_DIRECTIVE_PATH), exist_ok=True)
                with open(_DIRECTIVE_PATH, "w", encoding="utf-8") as fh:
                    fh.write(decision.antigravity_directive)

                self._release_stalled_locks()

                print(f"\n[ACTION REQUIRED] Live-Fix Directive → {_DIRECTIVE_PATH}")
                print("  1. Have Antigravity apply the patch from the directive.")
                print("  2. Run `omni qa .` to verify Ruff + Pyright pass.")
                print("  3. Click 'Kill Workers' then 'Spawn Worker' in the GUI.")
                print("     The new daemon will import the patched AST and retry.")

                # Pause the watchdog until the human confirms the fix is applied.
                # This prevents a second triage cycle before the patch is live.
                input("\n[OUROBOROS] Press ENTER once Antigravity has applied the fix...")

                # Reset log offset so the next cycle only reads post-fix logs
                self.last_log_size = (
                    os.path.getsize(_LOG_PATH) if os.path.exists(_LOG_PATH) else 0
                )

            elif decision.action == "RESET":
                print(
                    "\n[OUROBOROS] Unrecoverable state detected. "
                    "Initiating Factory Reset..."
                )
                execute_factory_reset()
                print("[OUROBOROS] Reset complete. Restart Mission Control GUI.")
                sys.exit(0)

        except Exception as exc:
            print(f"[OUROBOROS] LLM Triage Failed: {exc}")

    # ── Main Watch Loop ───────────────────────────────────────────────────────

    def watch(self, poll_interval_sec: float = 5.0) -> None:
        """
        Blocking event loop. Polls for anomalies every ``poll_interval_sec``
        seconds.

        Args:
            poll_interval_sec: How frequently to scan the two anomaly surfaces.
                Default 5 seconds. Lower values improve responsiveness but
                increase SQLite read pressure.
        """
        print("[OUROBOROS] Live-Fix Monitor active. Watching for anomalies...")

        # Anchor the log offset so we don't re-trigger on pre-existing crashes
        if os.path.exists(_LOG_PATH):
            self.last_log_size = os.path.getsize(_LOG_PATH)

        while True:
            time.sleep(poll_interval_sec)
            anomaly = self._detect_anomalies()
            if anomaly:
                self.analyze_and_react(anomaly)


# ── Entry Point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]
    monitor = OuroborosMonitor()
    monitor.watch()
