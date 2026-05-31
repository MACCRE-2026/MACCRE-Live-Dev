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
maccre_core/tests/burn_in_test.py
===================================
Bounded Burn-In Test — Phase 10 Sovereign Dual-Pipeline.

Executes four sequential phases:
  Phase 1: Scorched Earth (purge all DBs + logs + IPC temp)
  Phase 2: Payload Injection (seed swarm_queue.db with first raw-source file)
  Phase 3: Bounded Swarm Execution (max 20 cycles, break on empty queue)
  Phase 4: Forensic Autopsy Generation (markdown report in __DATACENTER)

Strictly typed, pyright-compliant, zero external runtime dependencies beyond
the MACCREv2 stdlib modules.

Usage:
    python maccre_core/tests/burn_in_test.py
"""
from __future__ import annotations

import os
import glob
import shutil
import sqlite3
import sys
import textwrap
import traceback
from datetime import datetime, timezone
from typing import Optional

# ── Path constants ─────────────────────────────────────────────────────────────
_REPO_ROOT   = "B:/MACCREv2"
_DC          = f"{_REPO_ROOT}/__DATACENTER"
_QUEUE_DB    = f"{_DC}/swarm_queue.db"
_TELEM_DIR   = f"{_DC}/telemetry"
_IPC_TEMP    = f"{_DC}/IPC_Temp"
_SYSTEM_LOG  = f"{_REPO_ROOT}/maccre_system.log"
_AUTOPSY_OUT = f"{_DC}/burn_in_autopsy.md"
_RAW_SOURCE  = f"{_DC}/01_Raw_Source"
_LEDGERS_DIR = f"{_DC}/03_Agent_Ledgers"
_TELEM_DBS   = {
    "system_logs.db":       "system_logs",
    "user_interactions.db": "user_interactions",
    "terminal_logs.db":     "terminal_logs",
    "thoughts.db":          "thoughts",
}
_JOB_ID         = "BURN_IN_001"
_MAX_CYCLES     = 20
_STARTING_NODE  = "LOREWEAVER_PERSONA_CREATION"   # First node in topology.csv
_FALLBACK_NODE  = "ARCHIVIST_FACT_GATHERING"       # Second node if first unavailable


# ══════════════════════════════════════════════════════════════════════════════
# PHASE 1: Scorched Earth
# ══════════════════════════════════════════════════════════════════════════════

def phase1_scorched_earth() -> None:
    print("\n" + "=" * 60)
    print("PHASE 1: SCORCHED EARTH -- Purging all state vectors")
    print("=" * 60)

    # 1a. Zombie hunt (DISABLED)
    # The wildcard taskkill was causing IDE fratricide and locking .pak files.
    # We rely on `omni clean` for process management instead.
    print("[P1] Zombie hunt bypassed to prevent IDE file locks.")

    # 1b. Purge swarm_queue.db via DROP TABLE (preserves file, wipes data)
    print(f"[P1] Purging swarm_queue.db -> {_QUEUE_DB}")
    if os.path.exists(_QUEUE_DB):
        with sqlite3.connect(_QUEUE_DB) as conn:
            conn.execute("DROP TABLE IF EXISTS task_queue")
            conn.commit()

    # 1c. Purge all four telemetry silos
    for db_file, table_name in _TELEM_DBS.items():
        db_path = os.path.join(_TELEM_DIR, db_file)
        print(f"[P1] Purging {db_file} -> table: {table_name}")
        if os.path.exists(db_path):
            with sqlite3.connect(db_path) as conn:
                conn.execute(f"DROP TABLE IF EXISTS {table_name}")
                conn.commit()

    # 1d. Purge maccre_system.log (truncate in-place -- safe for open FileHandlers)
    if os.path.exists(_SYSTEM_LOG):
        print(f"[P1] Truncating {_SYSTEM_LOG}...")
        with open(_SYSTEM_LOG, "w", encoding="utf-8") as fh:
            fh.truncate(0)

    # 1e. Clear IPC_Temp directory
    if os.path.isdir(_IPC_TEMP):
        print(f"[P1] Clearing IPC_Temp: {_IPC_TEMP}")
        for item in os.listdir(_IPC_TEMP):
            item_path = os.path.join(_IPC_TEMP, item)
            try:
                if os.path.isfile(item_path):
                    os.remove(item_path)
                elif os.path.isdir(item_path):
                    shutil.rmtree(item_path)
            except OSError:
                pass

    # 1f. Re-initialise all schemas via telemetry_db + LocalMessageBroker
    print("[P1] Re-initialising telemetry matrix schemas...")
    from maccre_core.orchestration.telemetry_db import init_all_silos
    init_all_silos()

    print("[P1] Re-initialising swarm queue schema...")
    from maccre_core.orchestration.local_broker import LocalMessageBroker
    LocalMessageBroker()  # constructor calls _init_db()

    print("[P1] Scorched Earth complete. All state vectors zeroed.\n")


# ══════════════════════════════════════════════════════════════════════════════
# PHASE 2: Payload Injection
# ══════════════════════════════════════════════════════════════════════════════

def phase2_payload_injection() -> str:
    """Injects the first available raw-source file. Returns the payload path."""
    print("=" * 60)
    print("PHASE 2: PAYLOAD INJECTION -- Seeding swarm_queue.db")
    print("=" * 60)

    # Scan 01_Raw_Source for the first available file
    sample_file: Optional[str] = None
    if os.path.isdir(_RAW_SOURCE):
        candidates = sorted(glob.glob(os.path.join(_RAW_SOURCE, "*")))
        candidates = [c for c in candidates if os.path.isfile(c)]
        if candidates:
            sample_file = candidates[0]

    if sample_file is None:
        # Fallback: create a synthetic payload so the test can still proceed
        os.makedirs(_RAW_SOURCE, exist_ok=True)
        sample_file = os.path.join(_RAW_SOURCE, "burn_in_synthetic_payload.txt")
        with open(sample_file, "w", encoding="utf-8") as fh:
            fh.write(
                "BURN IN SYNTHETIC PAYLOAD\n"
                "This is a synthetic test document injected by burn_in_test.py.\n"
                "Topic: the architectural principles of MACCREv2 Phase 10.\n"
            )
        print(f"[P2] No files in 01_Raw_Source. Synthetic payload created: {sample_file}")
    else:
        print(f"[P2] Selected raw-source file: {sample_file}")

    # Verify the starting node is in the topology; fall back if not
    from maccre_core.orchestration.topology_engine import TopologyEngine
    from maccre_core.orchestration.local_broker import LocalMessageBroker

    topo = TopologyEngine()
    starting_node = _STARTING_NODE
    try:
        topo.get_node_config(starting_node)
        print(f"[P2] Starting node confirmed in topology: {starting_node}")
    except ValueError:
        try:
            topo.get_node_config(_FALLBACK_NODE)
            starting_node = _FALLBACK_NODE
            print(f"[P2] Primary node not found. Falling back to: {starting_node}")
        except ValueError:
            # Use the first node available in topology
            available = list(topo.get_topology().keys())
            starting_node = available[0] if available else starting_node
            print(f"[P2] Both primary and fallback nodes missing. Using: {starting_node}")

    broker = LocalMessageBroker()
    broker.inject_task(
        job_id=_JOB_ID,
        payload_path=sample_file,
        starting_node=starting_node,
    )
    print(f"[P2] Injected job_id='{_JOB_ID}' at node '{starting_node}' | payload: {sample_file}")
    print("[P2] Payload injection complete.\n")
    return sample_file


# ══════════════════════════════════════════════════════════════════════════════
# PHASE 3: Bounded Swarm Execution
# ══════════════════════════════════════════════════════════════════════════════

def _open_task_count() -> int:
    """Non-locking read of open/locked task rows -- safe to call between cycles."""
    if not os.path.exists(_QUEUE_DB):
        return 0
    try:
        with sqlite3.connect(_QUEUE_DB) as conn:
            row = conn.execute(
                "SELECT COUNT(*) FROM task_queue WHERE lock_status IN ('open', 'locked')"
            ).fetchone()
            return int(row[0]) if row else 0
    except sqlite3.OperationalError:
        return 0


def phase3_bounded_swarm() -> tuple[str, int]:
    """
    Runs the swarm for at most _MAX_CYCLES cycles.

    Uses a read-only COUNT query to check queue depth rather than acquiring
    EXCLUSIVE locks (those are owned solely by execute_cycle via
    fetch_and_lock_task), eliminating the TOCTOU double-lock race.

    Returns:
        Tuple of (execution_status, cycles_run) where execution_status is
        'SUCCESS' or 'FAILED:<traceback>'.
    """
    print("=" * 60)
    print(f"PHASE 3: BOUNDED SWARM EXECUTION (MAX {_MAX_CYCLES} CYCLES)")
    print("=" * 60)

    from maccre_core.orchestration.swarm_worker import UniversalSwarmWorker

    status = "SUCCESS"
    cycles = 0

    try:
        worker = UniversalSwarmWorker()

        for cycle_num in range(1, _MAX_CYCLES + 1):
            # Non-locking pre-flight check -- avoids TOCTOU with execute_cycle
            pending = _open_task_count()
            if pending == 0:
                print(f"[P3] Queue empty at cycle {cycle_num} pre-check. Stopping.")
                break

            cycles = cycle_num
            print(f"\n[P3] -- Cycle {cycle_num}/{_MAX_CYCLES} -- {pending} task(s) pending --")
            worker.execute_cycle()

            # Post-cycle depth check (still non-locking)
            if _open_task_count() == 0:
                print(f"[P3] Queue drained after cycle {cycle_num}. Swarm complete.")
                break
        else:
            print(f"[P3] Max cycle cap ({_MAX_CYCLES}) reached. Forcing stop.")

    except Exception:
        tb = traceback.format_exc()
        status = f"FAILED\n\n```\n{tb}\n```"
        print(f"[P3] CRITICAL EXCEPTION:\n{tb}")

    print(f"\n[P3] Swarm execution complete. Status: {status[:20]}... | Cycles: {cycles}\n")
    return status, cycles


# ══════════════════════════════════════════════════════════════════════════════
# PHASE 4: Forensic Autopsy Generation
# ══════════════════════════════════════════════════════════════════════════════

def _dump_table(db_path: str, table_name: str, limit: int = 50) -> str:
    """Return a markdown table dump of up to `limit` rows from an SQLite table."""
    if not os.path.exists(db_path):
        return f"*Database not found: `{db_path}`*\n"
    try:
        with sqlite3.connect(db_path) as conn:
            conn.execute("PRAGMA journal_mode=WAL;")
            cursor = conn.execute(f"SELECT * FROM {table_name} ORDER BY id DESC LIMIT {limit}")
            rows   = cursor.fetchall()
            cols   = [d[0] for d in cursor.description] if cursor.description else []
    except sqlite3.OperationalError as exc:
        return f"*Table query error: {exc}*\n"

    if not rows:
        return f"*No rows in `{table_name}`.*\n"

    # Markdown table
    header = "| " + " | ".join(cols) + " |"
    sep    = "| " + " | ".join(["---"] * len(cols)) + " |"
    lines  = [header, sep]
    for row in rows:
        cells = [str(v)[:80].replace("|", "!").replace("\n", " ") for v in row]
        lines.append("| " + " | ".join(cells) + " |")
    return "\n".join(lines) + "\n"


def phase4_autopsy(
    execution_status: str,
    cycles_run: int,
    payload_path: str,
) -> None:
    print("=" * 60)
    print("PHASE 4: FORENSIC AUTOPSY GENERATION")
    print("=" * 60)

    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    status_emoji = "[OK]" if execution_status == "SUCCESS" else "[FAIL]"

    # -- Section 1: Header
    sections: list[str] = [
        "# MACCREv2 Burn-In Autopsy Report\n",
        f"**Generated:** {now}  ",
        f"**Job ID:** `{_JOB_ID}`  ",
        f"**Cycles Executed:** {cycles_run} / {_MAX_CYCLES}  ",
        f"**Payload Injected:** `{payload_path}`\n",
        "---\n",
    ]

    # -- Section 2: Execution Status
    sections.append("## Execution Status\n")
    sections.append(f"{status_emoji} **{execution_status[:7].upper()}**\n")
    if execution_status.startswith("FAILED"):
        sections.append("<details><summary>Traceback</summary>\n\n")
        sections.append(execution_status)
        sections.append("\n</details>\n")
    sections.append("\n---\n")

    # -- Section 3: Queue State
    sections.append("## Queue State (swarm_queue.db -- full routing path)\n")
    sections.append(_dump_table(_QUEUE_DB, "task_queue", limit=100))
    sections.append("\n---\n")

    # -- Section 4: Cognitive Telemetry (Thoughts)
    sections.append("## Cognitive Telemetry -- Gemini Scratchpad Extracts (thoughts.db)\n")
    thoughts_db = os.path.join(_TELEM_DIR, "thoughts.db")
    sections.append(_dump_table(thoughts_db, "thoughts", limit=50))
    sections.append("\n---\n")

    # -- Section 5: System Events
    sections.append("## System Events (system_logs.db)\n")
    system_db = os.path.join(_TELEM_DIR, "system_logs.db")
    sections.append(_dump_table(system_db, "system_logs", limit=50))
    sections.append("\n---\n")

    # -- Section 6: Final Payload (latest 03_Agent_Ledgers file)
    sections.append("## Final Payload -- Latest Agent Ledger\n")
    os.makedirs(_LEDGERS_DIR, exist_ok=True)
    ledger_files = sorted(
        glob.glob(os.path.join(_LEDGERS_DIR, f"*{_JOB_ID}*")),
        key=os.path.getmtime,
        reverse=True,
    )
    if ledger_files:
        latest = ledger_files[0]
        sections.append(f"**Source:** `{latest}`\n\n")
        try:
            with open(latest, "r", encoding="utf-8", errors="replace") as fh:
                content = fh.read()
            if len(content) > 20_000:
                content = content[:20_000] + "\n\n*[TRUNCATED -- full output in ledger file]*"
            sections.append(f"```markdown\n{content}\n```\n")
        except OSError as exc:
            sections.append(f"*Could not read ledger: {exc}*\n")
    else:
        sections.append(f"*No ledger files found for job `{_JOB_ID}` in `{_LEDGERS_DIR}`.*\n")

    # -- Write autopsy file
    autopsy_content = "\n".join(sections)
    os.makedirs(os.path.dirname(_AUTOPSY_OUT), exist_ok=True)
    with open(_AUTOPSY_OUT, "w", encoding="utf-8") as fh:
        fh.write(autopsy_content)

    print(f"[P4] Autopsy written -> {_AUTOPSY_OUT}")
    print(f"[P4] Report size: {len(autopsy_content):,} bytes\n")


# ══════════════════════════════════════════════════════════════════════════════
# Entry Point
# ══════════════════════════════════════════════════════════════════════════════

def main() -> None:
    # Force UTF-8 on Windows cp1252 terminals so box-drawing glyphs don't crash
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]

    wall_start = datetime.now(timezone.utc)
    print(textwrap.dedent(f"""
        MACCREv2 BURN-IN TEST -- Phase 10
        Started: {wall_start.strftime("%Y-%m-%d %H:%M:%S UTC")}
    """))

    phase1_scorched_earth()
    payload_path = phase2_payload_injection()
    execution_status, cycles_run = phase3_bounded_swarm()
    phase4_autopsy(execution_status, cycles_run, payload_path)

    wall_end = datetime.now(timezone.utc)
    elapsed  = (wall_end - wall_start).total_seconds()

    print(f"\nBURN-IN COMPLETE | Status: {execution_status[:7].upper()} | "
          f"Elapsed: {elapsed:.1f}s | Autopsy: {_AUTOPSY_OUT}")

    sys.exit(0 if execution_status == "SUCCESS" else 1)


if __name__ == "__main__":
    main()
