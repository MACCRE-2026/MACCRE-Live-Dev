# ┌─────────────────────────────────────────────────────────────────────────────┐
# │  MACCREv2 ENGINEERING DOCTRINE                             Law Rev: 19.0   │
# ├─────────────────────────────────────────────────────────────────────────────┤
# │  I.   TYPING      All signatures: explicit Python 3.11+ type hints.        │
# │  II.  LINTING     Zero unused imports. No wildcards. 120-char line max.    │
# │  III. PATHS       Never hardcode absolute paths. Use get_maccre_root().     │
# │  IV.  DATACENTER  5-Tier Data Sovereignty.                                 │
# │  VI.  ABSTRACTION All I/O behind abc.ABC before any concrete driver.       │
# │  VII. TEARDOWN    try/finally on all handles (omni clean compliance).      │
# └─────────────────────────────────────────────────────────────────────────────┘
"""
maccre_core/orchestration/flow_engine.py
=========================================
Linear Flow Engine.

Acts as a Supervisor over the UniversalSwarmWorker.
Takes a linear sequence of MacroNodes, instantiates their templates (if any),
writes them to topology.csv dynamically, and executes them sequentially.
"""
from __future__ import annotations

import os
import sqlite3
import time
from typing import Any

from maccre_core.macronode_registry import get_macronode_store
from maccre_core.orchestration.local_broker import LocalMessageBroker
from maccre_core.orchestration.swarm_worker import UniversalSwarmWorker
from maccre_core.tools.admin_tools import build_topology, ensure_project_workbook
from maccre_core.utils.path_resolver import get_datacenter_path
from maccre_core.utils.session_manager import generate_session_id


class FlowStep:
    """A single step in a Linear Flow, pointing to a MacroNode."""
    def __init__(self, macronode_name: str, agent_mapping: dict[str, str] | None = None) -> None:
        self.macronode_name = macronode_name
        self.agent_mapping = agent_mapping or {}


class FlowRunner:
    """Supervises the execution of a Linear Flow."""

    def __init__(self, project_name: str = "") -> None:
        self.project_name = project_name.strip() or os.environ.get("MACCRE_ACTIVE_PROJECT", "GLOBAL")
        self.macronode_store = get_macronode_store(self.project_name)
        # Verify fallback to GLOBAL registry if needed.
        self.global_store = get_macronode_store("GLOBAL")

    def _get_macronode(self, name: str) -> dict[str, Any]:
        """Fetch MacroNode definition from Project, fallback to GLOBAL."""
        try:
            return self.macronode_store.load(name)
        except KeyError:
            return self.global_store.load(name)

    def _hydrate_topology(self, topology_rows: list[dict[str, Any]], agent_mapping: dict[str, str]) -> list[list[str]]:
        """Apply agent mapping and convert JSON dict rows back into a List[List[str]] format suitable for topology.csv."""
        # topology_rows from registry are expected to be list of dicts.
        hydrated: list[list[str]] = []
        for row_dict in topology_rows:
            agent_name = str(row_dict.get("Agent_Name", ""))
            
            # If the assigned agent name is a slot like {Writer}, map it!
            # Or if it's explicitly matched in agent_mapping.
            for slot_key, slot_val in agent_mapping.items():
                if agent_name == f"{{{slot_key}}}" or agent_name == slot_key:
                    agent_name = slot_val

            # Standard order: Node_ID, Agent_Name, Model_Override, Next_Node, Temp, Instr, Wait, Fail, MaxRec, Artifact, Live, Partner, Rounds
            row_list = [
                str(row_dict.get("Node_ID", "")),
                agent_name,
                str(row_dict.get("Model_Override", "none")),
                str(row_dict.get("Next_Node", "")),
                str(row_dict.get("Temperature", "0.7")),
                str(row_dict.get("Instruction_Override", "")),
                str(row_dict.get("Wait_For", "none")),
                str(row_dict.get("Failure_Target", "FAILED")),
                str(row_dict.get("Max_Recursion", "3")),
                str(row_dict.get("Artifact_Path", "")),
                str(row_dict.get("Live_Profile", "FALSE")),
                str(row_dict.get("Dialogue_Partner", "")),
                str(row_dict.get("Dialogue_Rounds", "0")),
            ]
            hydrated.append(row_list)
        return hydrated

    def _find_starting_node(self, topology_rows: list[dict[str, Any]]) -> str:
        """Heuristically find the starting Node_ID of a MacroNode DAG."""
        if not topology_rows:
            return "OSINT"
        # First node in the list is almost always the entrypoint in MACCREv2.
        return str(topology_rows[0].get("Node_ID", "OSINT"))

    def _find_final_ledger_path(self, job_id: str, topology_rows: list[dict[str, Any]]) -> str | None:
        """Find the final expected artifact path for the DAG to pass it sequentially to the next step."""
        # For simplicity, if we don't have a deterministic way to find the final output, 
        # we can just return the most recently written ledger in the job_id directory.
        ledger_dir = get_datacenter_path("03_Agent_Ledgers", job_id)
        if not ledger_dir.exists():
            return None
        md_files = sorted(ledger_dir.glob("*.md"), key=lambda p: p.stat().st_mtime, reverse=True)
        if md_files:
            return str(md_files[0])
        return None

    def execute_flow(self, steps: list[FlowStep], initial_payload_path: str = "none") -> str:
        """
        Execute a sequential linear flow of MacroNodes.
        
        Args:
            steps: List of FlowStep objects.
            initial_payload_path: Starting context.

        Returns:
            The path to the final output file from the last step in the flow.
        """
        os.environ["MACCRE_ACTIVE_PROJECT"] = self.project_name
        ensure_project_workbook(self.project_name)

        job_id = f"job_{generate_session_id()}"
        print(f"[FLOW_ENGINE] Booting Linear Flow (Job: {job_id}) across {len(steps)} MacroNode(s).")

        current_payload = initial_payload_path
        broker = LocalMessageBroker()
        
        for idx, step in enumerate(steps):
            print(f"\n[FLOW_ENGINE] === STEP {idx+1}/{len(steps)}: Loading MacroNode '{step.macronode_name}' ===")
            
            # 1. Load the MacroNode
            try:
                macro_def = self._get_macronode(step.macronode_name)
            except KeyError:
                print(f"[FLOW_ENGINE] ERROR: MacroNode '{step.macronode_name}' not found. Aborting flow.")
                return current_payload
                
            # 2. Hydrate Agent Slots
            topo_rows = macro_def.get("topology_rows", [])
            hydrated_lists = self._hydrate_topology(topo_rows, step.agent_mapping)
            
            # 3. Write to topology.csv
            build_res = build_topology(hydrated_lists)
            print(f"[FLOW_ENGINE] {build_res}")
            
            # 4. Inject Initial Task
            start_node = self._find_starting_node(topo_rows)
            broker.inject_task(job_id=job_id, payload_path=current_payload, starting_node=start_node)
            print(f"[FLOW_ENGINE] Queued entrypoint: {start_node} with payload '{current_payload}'")

            # 5. Ignite the Swarm Worker for this DAG
            db_path = str(get_datacenter_path("swarm_queue.db"))
            worker = UniversalSwarmWorker()
            
            # Invalidate any cached topologies in the worker so it reads the new topology.csv
            if worker.topology:
                worker.topology.flush_cache()
                
            start_time = time.time()
            timeout_seconds = 3600
            
            for _ in range(500):
                if time.time() - start_time > timeout_seconds:
                    print("[FLOW_ENGINE] Swarm Worker Timeout reached.")
                    break
                    
                worker.execute_cycle()
                
                with sqlite3.connect(db_path) as _q:
                    still_open: int = _q.execute(
                        "SELECT COUNT(*) FROM task_queue WHERE lock_status = 'open' AND job_id = ?",
                        (job_id,)
                    ).fetchone()[0]
                    
                if still_open == 0:
                    break

            print(f"[FLOW_ENGINE] MacroNode '{step.macronode_name}' completed execution.")
            
            # 6. Capture output to pass to next step
            latest_ledger = self._find_final_ledger_path(job_id, topo_rows)
            if latest_ledger:
                current_payload = latest_ledger
                print(f"[FLOW_ENGINE] Output captured: {current_payload}")
            else:
                print(f"[FLOW_ENGINE] Warning: No output ledger found for {step.macronode_name}.")

        print(f"\n[FLOW_ENGINE] Linear Flow Complete. Final artifact: {current_payload}")
        return current_payload
