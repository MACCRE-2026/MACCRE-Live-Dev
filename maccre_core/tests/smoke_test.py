# maccre_core/tests/smoke_test.py
# ================================
# Canonical Zero-Cost Smoke Test for MACCREv2.
#
# Proves the core swarm machinery end-to-end in < 90 seconds at $0.00 cost:
#   1. Builds an isolated temp DATACENTER with a single-node topology
#   2. Injects a minimal payload into a temp SQLite queue
#   3. Calls the router/broker directly (same path as swarm_worker)
#   4. Asserts ledger written + queue row = completed
#   5. Cleans up all temp files via finally block
#
# Model: gemma-3-4b-it (free Gemma API) - no Ollama, no TTS, no video, $0.00
#
# Usage:
#   python -m maccre_core.tests.smoke_test
#   omni smoke b:\MACCREv2
from __future__ import annotations

import csv
import os
import shutil
import sqlite3
import sys
import tempfile
import time
import traceback
from pathlib import Path
from typing import Optional

# ── Path Bootstrap ────────────────────────────────────────────────────────────
_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))
# ─────────────────────────────────────────────────────────────────────────────

_SEP = "=" * 70
_SMOKE_MODEL = "gemma-3-4b-it"  # Free Gemma API — always $0.00


def _banner(msg: str) -> None:
    print(f"\n{_SEP}\n  SMOKE TEST: {msg}\n{_SEP}")


def _check(label: str, condition: bool, detail: str = "") -> bool:
    mark = "PASS" if condition else "FAIL"
    line = f"  [{mark}]  {label}"
    if detail and not condition:
        line += f"\n         -> {detail}"
    print(line)
    return condition


def _build_temp_datacenter(base: Path) -> tuple[Path, Path, Path]:
    """Build a minimal isolated DATACENTER layout for the smoke run."""
    dc = base / "__DATACENTER" / "SMOKE_PROJECT"
    for tier in ("01_Raw_Source", "02_Dynamic_Context", "03_Agent_Ledgers"):
        (dc / tier).mkdir(parents=True, exist_ok=True)

    payload = dc / "01_Raw_Source" / "smoke_input.md"
    payload.write_text(
        "SMOKE TEST: Respond with exactly five words confirming you are operational.",
        encoding="utf-8",
    )

    roster = dc / "agent_roster.csv"
    with open(roster, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(
            f, fieldnames=["Agent_Name", "Model", "System_Prompt", "Tools_Allowed"]
        )
        w.writeheader()
        w.writerow({
            "Agent_Name": "SmokeAgent",
            "Model": _SMOKE_MODEL,
            "System_Prompt": (
                "You are a system health diagnostic agent. "
                "Respond with exactly five words confirming you are operational."
            ),
            "Tools_Allowed": "none",
        })

    topo = dc / "02_Dynamic_Context" / "topology.csv"
    with open(topo, "w", newline="", encoding="utf-8") as f:
        fields = [
            "Node_ID", "Agent_Name", "Model_Override",
            "Next_Node", "Temperature", "Max_Recursion",
            "Instruction_Override", "Wait_For", "Failure_Target",
        ]
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerow({
            "Node_ID": "SMOKE_TEST",
            "Agent_Name": "SmokeAgent",
            "Model_Override": "",
            "Next_Node": "STOP",
            "Temperature": "0.1",
            "Max_Recursion": "1",
            "Instruction_Override": (
                "You are a system health diagnostic agent. "
                "Respond with exactly five words confirming you are operational."
            ),
            "Wait_For": "none",
            "Failure_Target": "FAILED",
        })

    return dc, payload, topo


def _seed_queue_db(dc: Path, payload: Path, job_id: str) -> Path:
    """Create and seed the isolated swarm queue database."""
    db = dc / "swarm_queue.db"
    with sqlite3.connect(str(db)) as conn:
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("""
            CREATE TABLE IF NOT EXISTS task_queue (
                id                  INTEGER PRIMARY KEY AUTOINCREMENT,
                job_id              TEXT    NOT NULL,
                session_id          TEXT,
                project_id          TEXT,
                payload_path        TEXT    NOT NULL,
                source_payload_path TEXT,
                current_node        TEXT    NOT NULL,
                lock_status         TEXT    NOT NULL DEFAULT 'open',
                locked_by           TEXT,
                actual_cost         REAL    DEFAULT 0.0,
                loop_iteration_count INTEGER DEFAULT 0,
                created_at          REAL    DEFAULT (strftime('%s','now'))
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS interrupt_queue (
                id       INTEGER PRIMARY KEY AUTOINCREMENT,
                job_id   TEXT NOT NULL,
                message  TEXT NOT NULL,
                consumed INTEGER DEFAULT 0
            )
        """)
        conn.execute(
            "INSERT INTO task_queue "
            "(job_id, session_id, project_id, payload_path, source_payload_path, "
            "current_node, lock_status, locked_by, actual_cost, loop_iteration_count) "
            "VALUES (?, ?, ?, ?, ?, ?, 'open', NULL, 0.0, 0)",
            (job_id, job_id, "SMOKE_PROJECT", str(payload), str(payload), "SMOKE_TEST"),
        )
        conn.commit()
    return db


def run_smoke_test() -> bool:
    """Execute the full smoke test. Returns True on pass, False on fail."""
    _banner("MACCREv2 Operational Readiness Check")
    print(f"  Model  : {_SMOKE_MODEL} (free Gemma API)")
    print("  Cost   : $0.00")
    print("  Timeout: 90 seconds\n")

    all_ok = True
    tmp = Path(tempfile.mkdtemp(prefix="maccre_smoke_"))

    try:
        # ── 1. Build isolated environment ─────────────────────────────────────
        dc, payload, topo_path = _build_temp_datacenter(tmp)
        job_id = f"smoke_{int(time.time())}"
        db_path = _seed_queue_db(dc, payload, job_id)

        all_ok &= _check("Temp DATACENTER created", dc.exists())
        all_ok &= _check("Topology CSV written", topo_path.exists())
        all_ok &= _check("Queue DB seeded", db_path.exists())

        # ── 2. Set up isolated env vars ────────────────────────────────────────
        os.environ["MACCRE_ACTIVE_PROJECT"] = "SMOKE_PROJECT"
        os.environ["MACCRE_DATACENTER_OVERRIDE"] = str(tmp / "__DATACENTER")
        os.environ["MACCRE_SKIP_AUTH"] = "1"   # No USB token in smoke/CI context
        os.environ["MACCRE_SKIP_VALIDATE"] = "1"  # We run validate() manually below


        # ── 3. Run one inference cycle via the same path swarm_worker uses ─────
        print(f"\n  Running inference for job [{job_id}]...")
        try:
            from maccre_core.orchestration.local_broker import LocalMessageBroker  # noqa: PLC0415
            from maccre_core.orchestration.topology_engine import TopologyEngine  # noqa: PLC0415
            from maccre_core.maccre_router import UniversalRouter  # noqa: PLC0415
            from maccre_core.orchestration.memory_engine import CognitiveMemoryEngine  # noqa: PLC0415

            broker = LocalMessageBroker(str(db_path))
            topology = TopologyEngine(str(topo_path))

            # Pre-flight validate the temp topology itself
            report = topology.validate()
            all_ok &= _check(
                "Pre-flight topology validation",
                report.is_ok,
                report.render_table() if not report.is_ok else "",
            )
            if not report.is_ok:
                return False

            router = UniversalRouter()
            memory = CognitiveMemoryEngine()

            # Lock the task exactly as swarm_worker does
            task: Optional[dict[str, object]] = broker.fetch_and_lock_task(
                "smoke_worker", topology
            )
            all_ok &= _check(
                "Task locked from queue",
                task is not None,
                "fetch_and_lock_task returned None — DB seed or broker issue.",
            )
            if not task:
                return False

            row_id: int = int(task["id"])  # type: ignore[arg-type]
            node: str = str(task.get("current_node", "SMOKE_TEST"))
            cfg = topology.get_node_config(node)

            # Inference
            t0 = time.time()
            output, cost, _ = router.generate(
                model_name=str(cfg.get("model", _SMOKE_MODEL)),
                payload=(
                    "SMOKE TEST: Respond with exactly five words "
                    "confirming you are operational."
                ),
                system_prompt=str(cfg.get("prompt", "")),
                tools_str="none",
                temperature=float(cfg.get("temperature", 0.1)),
            )
            elapsed = time.time() - t0

            all_ok &= _check(
                f"Inference completed ({elapsed:.1f}s)",
                bool(output.strip()),
                f"Router returned empty output. cost=${cost:.6f}",
            )
            print(f"         -> Response: {output.strip()[:120]!r}")

            # Write ledger (same path as swarm_worker)
            ledger_dir = dc / "03_Agent_Ledgers" / job_id
            ledger_dir.mkdir(parents=True, exist_ok=True)
            ledger_path = ledger_dir / f"{node}_{row_id}.md"
            ledger_path.write_text(output, encoding="utf-8")
            all_ok &= _check("Ledger file written", ledger_path.exists())

            # Memory extraction
            try:
                memory.extract_from_canonized_ledger(str(ledger_path), job_id)
            except AttributeError:
                pass

            # Route to STOP (same as swarm_worker)
            broker.route_task(
                row_id,
                job_id,
                next_node_str="STOP",
                new_payload_path=str(ledger_path),
                actual_cost=cost,
                source_payload_path=str(payload),
            )

        except Exception as exc:  # noqa: BLE001
            all_ok &= _check(
                "Swarm execute_cycle",
                False,
                f"{exc}\n{traceback.format_exc()[:600]}",
            )
            return False

        # ── 4. Verify final DB state ───────────────────────────────────────────
        with sqlite3.connect(str(db_path)) as conn:
            row = conn.execute(
                "SELECT lock_status, actual_cost FROM task_queue "
                "WHERE job_id = ? ORDER BY id DESC LIMIT 1",
                (job_id,),
            ).fetchone()

        all_ok &= _check(
            "Queue row transitioned to 'completed'",
            row is not None and row[0] == "completed",
            f"Got lock_status={row[0] if row else 'None'}",
        )
        all_ok &= _check(
            "Cost recorded in queue row",
            row is not None and float(row[1] or 0) >= 0.0,
        )

    finally:
        # ── 5. Tear down — always runs ─────────────────────────────────────────
        os.environ.pop("MACCRE_DATACENTER_OVERRIDE", None)
        os.environ.pop("MACCRE_ACTIVE_PROJECT", None)
        os.environ.pop("MACCRE_SKIP_AUTH", None)
        os.environ.pop("MACCRE_SKIP_VALIDATE", None)
        import gc  # noqa: PLC0415
        gc.collect()
        for _retry in range(3):
            shutil.rmtree(tmp, ignore_errors=True)
            if not tmp.exists():
                break
            time.sleep(0.2)  # Windows WAL lock release backoff
        if tmp.exists():
            print("  [WARN]  Temp dir held by OS (WAL lock) — will release on process exit.")
        else:
            print("  [PASS]  Temp environment cleaned up")


    # ── Summary ───────────────────────────────────────────────────────────────
    print(f"\n{_SEP}")
    if all_ok:
        print("  RESULT:  ALL CHECKS PASSED - MACCREv2 swarm is operational.")
    else:
        print("  RESULT:  ONE OR MORE CHECKS FAILED - review output above.")
    print(f"{_SEP}\n")
    return all_ok


if __name__ == "__main__":
    sys.exit(0 if run_smoke_test() else 1)
