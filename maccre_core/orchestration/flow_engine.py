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

import logging
import os
import sqlite3
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from maccre_core.macronode_registry import get_macronode_store
from maccre_core.orchestration.local_broker import LocalMessageBroker
from maccre_core.orchestration.swarm_worker import UniversalSwarmWorker
from maccre_core.tools.admin_tools import build_topology, ensure_project_workbook
from maccre_core.utils.path_resolver import get_datacenter_path
from maccre_core.utils.session_manager import generate_session_id

logger = logging.getLogger(__name__)


class FlowStep:
    """A single step in a Linear Flow, pointing to a MacroNode."""
    def __init__(self, macronode_name: str, agent_mapping: dict[str, str] | None = None, payload_mode: str = "Unified Ledger", custom_instructions: str = "", agent_tools_overrides: dict[str, str] | None = None, config: dict[str, Any] | None = None) -> None:
        self.macronode_name = macronode_name
        self.agent_mapping = agent_mapping or {}
        self.payload_mode = payload_mode
        self.custom_instructions = custom_instructions
        self.agent_tools_overrides = agent_tools_overrides or {}
        self.config: dict[str, Any] = config or {}

    def to_dict(self) -> dict[str, Any]:
        """Serialize for JSON persistence in flow_history."""
        return {"macronode_name": self.macronode_name, "agent_mapping": self.agent_mapping, "payload_mode": self.payload_mode, "custom_instructions": self.custom_instructions, "agent_tools_overrides": self.agent_tools_overrides, "config": self.config}

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "FlowStep":
        """Reconstruct from a dict (flow_history deserialization)."""
        return cls(
            macronode_name=d.get("macronode_name", ""),
            agent_mapping=d.get("agent_mapping", {}),
            payload_mode=d.get("payload_mode", "Unified Ledger"),
            custom_instructions=d.get("custom_instructions", ""),
            agent_tools_overrides=d.get("agent_tools_overrides", {}),
            config=d.get("config", {})
        )


@dataclass
class PreflightReport:
    """Aggregated result of all pre-flight validation checks."""

    issues: list[dict[str, str]] = field(default_factory=list)
    estimated_cost: float = 0.0

    @property
    def is_ok(self) -> bool:
        """True when no ERROR-severity issues were recorded."""
        return not any(i['severity'] == 'ERROR' for i in self.issues)

    def render(self) -> str:
        """Return Rich markup string for the Flow Monitor."""
        lines: list[str] = ['[bold cyan]━━━ Pre-Flight Report ━━━[/bold cyan]']
        for issue in self.issues:
            sev = issue['severity']
            if sev == 'ERROR':
                icon = '[red]✗[/red]'
            elif sev == 'WARN':
                icon = '[yellow]⚠[/yellow]'
            else:
                icon = '[green]✓[/green]'
            lines.append(f"  {icon} {issue['detail']}")

        lines.append(f"\n  Estimated Cost: [bold]${self.estimated_cost:.4f}[/bold]")

        error_count = sum(1 for i in self.issues if i['severity'] == 'ERROR')
        if error_count:
            lines.append(f"\n  [bold red]{error_count} ERROR(s) found. Flow blocked.[/bold red]")
        else:
            lines.append("\n  [bold green]All checks passed.[/bold green]")
        return '\n'.join(lines)



class FlowRunner:
    """Supervises the execution of a Linear Flow."""

    def __init__(self, project_name: str = "") -> None:
        self.project_name = project_name.strip() or os.environ.get("MACCRE_ACTIVE_PROJECT", "GLOBAL")
        self.macronode_store = get_macronode_store(self.project_name)
        # Verify fallback to GLOBAL registry if needed.
        self.global_store = get_macronode_store("GLOBAL")

    def _get_macronode(self, name: str, step_config: dict[str, Any] | None = None) -> dict[str, Any]:
        """Fetch MacroNode definition from Project, fallback to GLOBAL, fallback to agent/CTRL auto-wrap."""
        try:
            return self.macronode_store.load(name)
        except KeyError:
            try:
                return self.global_store.load(name)
            except KeyError:
                pass

        # ── Single-Agent Auto-Wrap ────────────────────────────────────────────
        # If the name isn't a registered MacroNode, check if it's an agent name
        # in the roster. If so, generate a synthetic single-node topology on the fly.
        try:
            from maccre_core.orchestration.roster_loader import (  # noqa: PLC0415
                list_roster_agents,
                load_agent_from_roster,
            )
            roster_names = list_roster_agents()
            if name in roster_names:
                agent_profile = load_agent_from_roster(name)
                model = agent_profile.get("Model_Override", "gemini-2.5-flash")
                system_prompt = agent_profile.get("System_Prompt", "")
                tools = agent_profile.get("Tools_Allowed", "")
                node_id = f"AGENT_{name[:20]}_{id(name) % 9999:04d}"
                logger.info(
                    "[FLOW_ENGINE] Auto-wrapping agent '%s' as single-node MacroNode (node=%s).",
                    name, node_id,
                )
                return {
                    "name": name,
                    "description": f"Auto-wrapped single agent: {name}",
                    "is_template": False,
                    "agent_slots": [name],
                    "topology_rows": [{
                        "Node_ID": node_id,
                        "Agent_Name": name,
                        "System_Instruction": system_prompt,
                        "Next_Node": "END",
                        "Temperature": "1.0",
                        "Model_Override": model,
                        "Tools_Allowed": tools,
                        "Fallback_Node": "FAILED",
                        "Max_Retries": 3,
                        "Is_End_Node": "TRUE",
                        "Dialogue_Partner": "",
                        "Dialogue_Rounds": 0,
                    }],
                    "roster_rows": [],
                    "template_type": "",
                    "template_config": None,
                }
        except Exception:  # noqa: BLE001
            pass

        # ── CTRL_ Node Auto-Wrap ──────────────────────────────────────────────
        # CTRL_ nodes are deterministic control-flow primitives. They don't
        # exist in the MacroNode registry — synthesize a topology on the fly.
        if name.upper().startswith("CTRL_"):
            cfg = step_config or {}
            scatter_agents: list[str] = cfg.get("scatter_agents", [])

            # CTRL_SCATTER with slotted agents → full scatter→agents→merge DAG
            if name.upper().startswith("CTRL_SCATTER") and scatter_agents:
                agent_overrides: dict[str, dict[str, Any]] = cfg.get("scatter_agent_overrides", {})
                scatter_mode: str = cfg.get("scatter_mode", "full_copy")
                topo_rows: list[dict[str, Any]] = []

                # 1. CTRL_SCATTER entry node → fans out to all agents
                topo_rows.append({
                    "Node_ID": "CTRL_SCATTER",
                    "Agent_Name": "SYSTEM",
                    "Model_Override": "none",
                    "Next_Node": ",".join(scatter_agents),
                    "Temperature": "0",
                    "Instruction_Override": f"scatter_mode={scatter_mode}",
                    "Wait_For": "none",
                    "Failure_Target": "FAILED",
                })

                # 2. One row per slotted agent with profile overrides
                for agent_name in scatter_agents:
                    ovr = agent_overrides.get(agent_name, {})
                    topo_rows.append({
                        "Node_ID": agent_name,
                        "Agent_Name": agent_name,
                        "Model_Override": str(ovr.get("model", "")),
                        "Next_Node": "CTRL_MERGE",
                        "Temperature": str(ovr.get("temperature", "1.0")),
                        "Instruction_Override": str(ovr.get("system_prompt_override", "")),
                        "Wait_For": "none",
                        "Failure_Target": "FAILED",
                        "Tools_Allowed": str(ovr.get("tools_allowed", "")),
                    })

                # 3. CTRL_MERGE fan-in — waits for all agents
                topo_rows.append({
                    "Node_ID": "CTRL_MERGE",
                    "Agent_Name": "SYSTEM",
                    "Model_Override": "none",
                    "Next_Node": "END",
                    "Temperature": "0",
                    "Instruction_Override": "",
                    "Wait_For": "|".join(scatter_agents),
                    "Failure_Target": "FAILED",
                })

                logger.info(
                    "[FLOW_ENGINE] Auto-wrapped CTRL_SCATTER with %d agents: %s",
                    len(scatter_agents), scatter_agents,
                )
                return {
                    "name": name,
                    "description": f"Dynamic scatter: {len(scatter_agents)} agents",
                    "is_template": False,
                    "agent_slots": list(scatter_agents),
                    "topology_rows": topo_rows,
                    "roster_rows": [],
                    "template_type": "",
                    "template_config": None,
                }

            # Generic CTRL_ node (PAUSE, GATE, CHECKPOINT, etc.) → single-node passthrough
            logger.info("[FLOW_ENGINE] Auto-wrapping CTRL node '%s' as single-node topology.", name)
            return {
                "name": name,
                "description": f"Auto-wrapped control node: {name}",
                "is_template": False,
                "agent_slots": [],
                "topology_rows": [{
                    "Node_ID": name,
                    "Agent_Name": "SYSTEM",
                    "Model_Override": "none",
                    "Next_Node": "END",
                    "Temperature": "0",
                    "Instruction_Override": "",
                    "Wait_For": "none",
                    "Failure_Target": "FAILED",
                }],
                "roster_rows": [],
                "template_type": "",
                "template_config": None,
            }

        raise KeyError(f"MacroNode '{name}' not found in project, GLOBAL, or agent roster.")

    # ── Phase B: Pre-Flight Validation Gate ────────────────────────────────────

    def preflight_check(self, steps: list[FlowStep]) -> PreflightReport:
        """Run all pre-flight validations against the proposed flow.

        Checks performed (in order):
          a) MacroNode existence in project/GLOBAL registries.
          b) Agent mapping — every mapped agent must exist in the roster.
          c) Topology schema — hydrate, write, and validate each step's DAG.
          d) Model health — non-blocking WARN via ModelSentinel (if available).
          e) Cost estimation — sum estimated API costs across all topology rows.

        Returns:
            PreflightReport with collected issues and estimated cost.
        """
        # Deferred imports to break circular dependency chains.
        from maccre_core.orchestration.roster_loader import validate_agents_exist
        from maccre_core.orchestration.topology_engine import TopologyEngine
        from maccre_core.tools.workbook_engine import _estimate_node_cost, get_pricing_table

        report = PreflightReport()
        pricing: dict[str, dict[str, float]] = get_pricing_table()
        all_models: list[str] = []

        for step in steps:
            macro_name = step.macronode_name

            # ── (a) MacroNode existence ───────────────────────────────────────
            if macro_name.strip().upper() in ("CTRL_REVIEW", "DET_REVIEW"):
                continue  # CTRL_REVIEW is a hardcoded intercept node, bypass validation
            if macro_name.strip().upper().startswith("CTRL_"):
                continue  # CTRL_ nodes are auto-wrapped at runtime, skip registry check

            try:
                macro_def = self._get_macronode(macro_name)
            except KeyError:
                report.issues.append({
                    'severity': 'ERROR',
                    'detail': f"MacroNode '{macro_name}' not found in project or GLOBAL registry.",
                })
                logger.error("[PREFLIGHT] MacroNode '%s' not found.", macro_name)
                continue  # Can't validate further without the definition

            # ── (b) Agent mapping validation ──────────────────────────────────
            if step.agent_mapping:
                mapped_agents: list[str] = list(step.agent_mapping.values())
                missing = validate_agents_exist(mapped_agents)
                for agent_name in missing:
                    report.issues.append({
                        'severity': 'ERROR',
                        'detail': (
                            f"Agent '{agent_name}' (mapped in step '{macro_name}') "
                            "not found in roster."
                        ),
                    })
                    logger.error("[PREFLIGHT] Agent '%s' missing from roster.", agent_name)

            # ── (c) Topology schema validation ────────────────────────────────
            topo_rows: list[dict[str, Any]] = macro_def.get('topology_rows', [])
            if topo_rows:
                hydrated_lists = self._hydrate_topology(topo_rows, step.agent_mapping, agent_tools_overrides=getattr(step, "agent_tools_overrides", {}))
                try:
                    build_topology(hydrated_lists)
                    topo_engine = TopologyEngine()
                    topo_engine.flush_cache()
                    val_report = topo_engine.validate()
                    for issue in val_report.issues:
                        report.issues.append({
                            'severity': issue['severity'],
                            'detail': (
                                f"[{macro_name}/{issue.get('node', '?')}] "
                                f"{issue['detail']}"
                            ),
                        })
                except Exception as exc:  # noqa: BLE001
                    report.issues.append({
                        'severity': 'ERROR',
                        'detail': f"Topology build/validate failed for '{macro_name}': {exc}",
                    })
                    logger.error("[PREFLIGHT] Topology error for '%s': %s", macro_name, exc)

                # Collect model names for health & cost checks
                for row in topo_rows:
                    model = str(row.get('Model_Override', 'none')).strip()
                    if model and model.lower() != 'none':
                        all_models.append(model)

        # ── (d) Model health — non-blocking WARN ─────────────────────────────
        try:
            from maccre_core._net.model_sentinel import get_sentinel
            api_key = os.environ.get('GOOGLE_API_KEY', '')
            if api_key:
                from maccre_core.orchestration.universal_vault import get_provider_credential
                sentinel = get_sentinel(lambda: get_provider_credential("MACCRE_Sovereign"))
                for model in set(all_models):
                    if not sentinel.is_healthy(model):
                        report.issues.append({
                            'severity': 'WARN',
                            'detail': f"Model '{model}' reported unhealthy by ModelSentinel.",
                        })
                        logger.warning("[PREFLIGHT] Model '%s' unhealthy.", model)
        except Exception:  # noqa: BLE001
            # Sentinel not available or no API key — skip silently
            pass

        # ── (e) Cost estimation ───────────────────────────────────────────────
        total_cost: float = 0.0
        for model in all_models:
            total_cost += _estimate_node_cost(model, pricing)
        report.estimated_cost = round(total_cost, 6)
        logger.info("[PREFLIGHT] Estimated flow cost: $%.4f across %d node(s).", total_cost, len(all_models))

        # Summary log
        error_count = sum(1 for i in report.issues if i['severity'] == 'ERROR')
        warn_count = sum(1 for i in report.issues if i['severity'] == 'WARN')
        logger.info(
            "[PREFLIGHT] Complete — %d ERROR(s), %d WARN(s), cost=$%.4f.",
            error_count, warn_count, report.estimated_cost,
        )
        return report

    def _hydrate_topology(self, topology_rows: list[dict[str, Any]], agent_mapping: dict[str, str], payload_mode: str = "Unified Ledger", custom_instructions: str = "", step_index: int = 0, agent_tools_overrides: dict[str, str] | None = None) -> list[list[str]]:
        """Convert a list of topology dictionaries into lists of strings (for CSV) and inject agent overrides."""
        hydrated: list[list[str]] = []
        agent_tools_overrides = agent_tools_overrides or {}
        
        for row_dict in topology_rows:
            agent_name = str(row_dict.get("Agent_Name", ""))
            
            # If the assigned agent name is a slot like {Writer}, map it!
            # Or if it's explicitly matched in agent_mapping.
            for slot_key, slot_val in agent_mapping.items():
                if agent_name == f"{{{slot_key}}}" or agent_name == slot_key:
                    agent_name = slot_val

            node_id = str(row_dict.get("Node_ID", ""))
            next_node = str(row_dict.get("Next_Node", ""))
            wait_for = str(row_dict.get("Wait_For", "none"))

            if node_id:
                node_id = f"{node_id}_S{step_index}"
            if next_node and next_node.upper() not in ("END", "FAILED"):
                next_node = f"{next_node}_S{step_index}"
            if wait_for and wait_for.lower() not in ("none", ""):
                parts = []
                for p in wait_for.replace("|", ",").split(","):
                    p = p.strip()
                    if p:
                        parts.append(f"{p}_S{step_index}")
                wait_for = "|".join(parts)

            instr = str(row_dict.get("Instruction_Override", ""))
            if custom_instructions:
                wrapped_instructions = f"\n\n[NODE DIRECTIVES]\n{custom_instructions}\n[MAINTAIN CORE PERSONA WHILE EXECUTING DIRECTIVES]\n"
                instr = f"{instr}{wrapped_instructions}".strip()
                
            tools_allowed = agent_tools_overrides.get(agent_name, "")

            # Standard order: Node_ID, Agent_Name, Model_Override, Next_Node, Temp, Instr, Wait, Fail, MaxRec, Artifact, Live, Partner, Rounds, Payload_Mode, Tools_Allowed
            row_list = [
                node_id,
                agent_name,
                str(row_dict.get("Model_Override", "none")),
                next_node,
                str(row_dict.get("Temperature", "0.7")),
                instr,
                wait_for,
                str(row_dict.get("Failure_Target", "FAILED")),
                str(row_dict.get("Max_Recursion", "3")),
                str(row_dict.get("Artifact_Path", "")),
                str(row_dict.get("Live_Profile", "FALSE")),
                str(row_dict.get("Dialogue_Partner", "")),
                str(row_dict.get("Dialogue_Rounds", "0")),
                payload_mode,
                tools_allowed,
            ]
            hydrated.append(row_list)
        return hydrated

    def _find_starting_nodes(self, topology_rows: list[dict[str, Any]], step_index: int = 0) -> list[str]:
        """Heuristically find all starting Node_IDs of a MacroNode DAG."""
        if not topology_rows:
            return [f"OSINT_S{step_index}"]
        
        start_nodes = []
        for row in topology_rows:
            wait_for = str(row.get("Wait_For", "none")).strip().lower()
            if wait_for in ("none", "", "null"):
                node_id = str(row.get("Node_ID", "OSINT"))
                start_nodes.append(f"{node_id}_S{step_index}")
        
        if not start_nodes:
            # Fallback if somehow there's a circular Wait_For loop with no entry
            node_id = str(topology_rows[0].get("Node_ID", "OSINT"))
            start_nodes.append(f"{node_id}_S{step_index}")
            
        return start_nodes

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


    def resume_flow(
        self,
        job_id: str,
        cancel_event: threading.Event | None = None,
        pause_event: threading.Event | None = None,
        step_callback: Callable[[int, str], None] | None = None,
        hitl_callback: Callable[[int, str, str], None] | None = None,
        job_started_callback: Callable[[str], None] | None = None,
        node_started_callback: Callable[[int, str], None] | None = None,
    ) -> str:
        """Resume a failed or paused flow from its last known step."""
        os.environ["MACCRE_ACTIVE_PROJECT"] = self.project_name
        ensure_project_workbook(self.project_name)

        if job_started_callback:
            try:
                job_started_callback(job_id)
            except Exception:
                pass
        
        broker = LocalMessageBroker()
        conn = broker._get_conn()
        conn.row_factory = sqlite3.Row
        session = conn.execute("SELECT * FROM job_sessions WHERE job_id = ?", (job_id,)).fetchone()
        if not session:
            logger.error(f"[FLOW_ENGINE] Cannot resume: job_id {job_id} not found in job_sessions.")
            return ""
            
        broker.update_session_status(job_id, "active")
        
        import json
        topology_csv_str = session["topology_csv"]
        current_ledger_path = session["current_ledger_path"]
        start_idx = session["current_step_index"]
        
        steps_data = json.loads(topology_csv_str)
        steps = [FlowStep(s.get("macronode", s.get("macro_name")), s.get("mapping", s.get("agent_mapping", {})), s.get("payload_mode", "Unified Ledger")) for s in steps_data]
        
        logger.info(f"[FLOW_ENGINE] Resuming Flow (Job: {job_id}) from step {start_idx + 1}/{len(steps)}.")
        
        current_payload = current_ledger_path
        is_cancelled = False
        
        # When resuming, the tasks for start_idx might already be in task_queue, or the step might have failed before injection.
        # We'll just run the worker. It will pick up 'open' tasks. If there are none, it will exit immediately.
        # But wait! If the step crashed before tasks were injected, 'open' tasks will be 0.
        # For safety, let's just re-inject the start node if there are NO tasks for this step.
        
        try:
            for idx in range(start_idx, len(steps)):
                step = steps[idx]
                broker.update_session_step_index(job_id, idx)
                
                if cancel_event and cancel_event.is_set():
                    logger.info("[FLOW_ENGINE] Cancellation requested — halting flow.")
                    is_cancelled = True
                    break

                if pause_event is not None:
                    pause_event.wait()

                logger.info(f"\n[FLOW_ENGINE] === RESUMING STEP {idx+1}/{len(steps)}: MacroNode '{step.macronode_name}' ===")

                # Notify TUI that this step is starting (for live topology highlighting)
                if node_started_callback is not None:
                    try:
                        node_started_callback(idx, step.macronode_name)
                    except Exception:  # noqa: BLE001
                        pass
                
                # 1. Load MacroNode
                if step.macronode_name.strip().upper() in ("CTRL_REVIEW", "DET_REVIEW"):
                    macro_def = {"topology_rows": [{"Node_ID": "CTRL_PAUSE_MANUAL", "Model_Override": "none", "Wait_For": "none", "Next_Node": "END"}]}
                else:
                    try:
                        macro_def = self._get_macronode(step.macronode_name)
                    except KeyError:
                        logger.error(f"[FLOW_ENGINE] ERROR: MacroNode '{step.macronode_name}' not found. Aborting flow.")
                        return current_payload
                        
                topo_rows = macro_def.get("topology_rows", [])
                hydrated_lists = self._hydrate_topology(topo_rows, step.agent_mapping, step.payload_mode, step_index=idx, agent_tools_overrides=getattr(step, "agent_tools_overrides", {}))
                build_topology(hydrated_lists)
                
                # Check task status for this step's topology nodes.
                # Tasks are stored with _S{idx} suffixes (e.g., CTRL_PAUSE_MANUAL_S1).
                nodes_in_topo = [r[0] for r in hydrated_lists]
                placeholders = ",".join(["?"] * len(nodes_in_topo))
                
                # Count tasks by status category
                task_rows = conn.execute(
                    f"SELECT lock_status FROM task_queue WHERE job_id = ? AND current_node IN ({placeholders})",
                    [job_id] + nodes_in_topo,
                ).fetchall()
                total_tasks = len(task_rows)
                completed_tasks = sum(1 for r in task_rows if r[0] in ("completed", "cancelled"))
                open_tasks = sum(1 for r in task_rows if r[0] == "open")
                paused_tasks = sum(1 for r in task_rows if r[0] == "paused")
                
                if total_tasks > 0 and completed_tasks == total_tasks:
                    # All tasks for this step already finished — skip it
                    logger.info(f"[FLOW_ENGINE] Step {idx+1} ('{step.macronode_name}') already completed ({completed_tasks} task(s)). Skipping.")
                    latest_ledger = self._find_final_ledger_path(job_id, topo_rows)
                    if latest_ledger:
                        current_payload = latest_ledger
                    if step_callback is not None:
                        try:
                            step_callback(idx, current_payload)
                        except Exception:  # noqa: BLE001
                            pass
                    continue
                
                if total_tasks == 0:
                    start_nodes = self._find_starting_nodes(topo_rows, step_index=idx)
                    for start_node in start_nodes:
                        broker.inject_task(job_id=job_id, payload_path=current_payload, starting_node=start_node)
                        logger.info(f"[FLOW_ENGINE] Queued entrypoint for resume: {start_node}")
                else:
                    logger.info(f"[FLOW_ENGINE] Step {idx+1}: {open_tasks} open, {paused_tasks} paused, {completed_tasks} completed task(s). Resuming worker.")
                
                db_path = str(get_datacenter_path("swarm_queue.db"))
                worker = UniversalSwarmWorker()
                if worker.topology:
                    worker.topology.flush_cache()
                    
                start_time = time.time()
                timeout_seconds = 3600
                
                for _ in range(500):
                    if cancel_event and cancel_event.is_set():
                        is_cancelled = True
                        break
                    if pause_event is not None:
                        pause_event.wait()
                    if time.time() - start_time > timeout_seconds:
                        break
                        
                    worker.execute_cycle(pause_event=pause_event, stop_event=cancel_event)
                    
                    with sqlite3.connect(db_path) as _q:
                        still_open = _q.execute("SELECT COUNT(*) FROM task_queue WHERE lock_status = 'open' AND job_id = ?", (job_id,)).fetchone()[0]
                        still_paused = _q.execute("SELECT COUNT(*) FROM task_queue WHERE lock_status = 'paused' AND job_id = ?", (job_id,)).fetchone()[0]

                    if still_open == 0 and still_paused > 0:
                        if hitl_callback is not None:
                            try:
                                hitl_callback(idx, job_id, current_payload)
                            except Exception:
                                pass
                        if pause_event is not None:
                            pause_event.clear()
                            pause_event.wait()
                        continue
                        
                    if still_open == 0:
                        break

                latest_ledger = self._find_final_ledger_path(job_id, topo_rows)
                if latest_ledger:
                    current_payload = latest_ledger
                    
                if step_callback is not None:
                    try:
                        step_callback(idx, current_payload)
                    except Exception:
                        pass

        except Exception as e:
            logger.error(f"[FLOW_ENGINE] Swarm Orchestration Failed on Resume: {e}")
            broker.update_session_status(job_id, "failed")
            raise
        finally:
            if is_cancelled:
                broker.update_session_status(job_id, "cancelled")
            else:
                broker.update_session_status(job_id, "completed")

        try:
            with sqlite3.connect(str(get_datacenter_path("swarm_queue.db"))) as conn:
                conn.execute("UPDATE task_queue SET lock_status = 'cancelled' WHERE job_id = ? AND lock_status IN ('open', 'paused')", (job_id,))
        except Exception:
            pass

        try:
            generate_unified_ledger(job_id, steps)
        except Exception:
            pass

        try:
            from maccre_core.utils.session_manager import save_flow_history
            import json
            save_flow_history(
                project_name=self.project_name,
                job_id=job_id,
                flow_steps_json=json.dumps([{"macronode": s.macronode_name, "agent_mapping": s.agent_mapping} for s in steps]),
                final_artifact=current_payload,
            )
        except Exception:
            pass

        return current_payload

    def execute_flow(
        self,
        steps: list[FlowStep],
        initial_payload_path: str,
        cancel_event: threading.Event | None = None,
        pause_event: threading.Event | None = None,
        step_callback: Callable[[int, str], None] | None = None,
        hitl_callback: Callable[[int, str, str], None] | None = None,
        job_started_callback: Callable[[str], None] | None = None,
        node_started_callback: Callable[[int, str], None] | None = None,
    ) -> str:
        """
        Execute a sequential linear flow of MacroNodes.
        
        Args:
            steps: List of FlowStep objects.
            initial_payload_path: Starting context.
            cancel_event: Optional threading.Event — checked between nodes for graceful cancellation.
            pause_event: Optional threading.Event — when cleared, blocks worker loop (VCR pause).
                         Must be set (unblocked) to allow execution.
            step_callback: Optional callable(step_index: int, output_path: str) — called after each step.
            hitl_callback: Optional callable(step_index: int, job_id: str, payload: str) — called on HITL pause.

        Returns:
            The path to the final output file from the last step in the flow.
        """
        os.environ["MACCRE_ACTIVE_PROJECT"] = self.project_name
        ensure_project_workbook(self.project_name)

        job_id = f"job_{generate_session_id()}"
        if job_started_callback:
            try:
                job_started_callback(job_id)
            except Exception:
                pass
        logger.info(f"[FLOW_ENGINE] Booting Linear Flow (Job: {job_id}) across {len(steps)} MacroNode(s).")

        current_payload = initial_payload_path
        broker = LocalMessageBroker()
        
        # Build combined topology for the session tracking
        import json
        topology_csv_str = json.dumps([{"macronode": step.macronode_name, "agent_mapping": step.agent_mapping} for step in steps])
        broker.create_session(job_id, topology_csv_str)
        
        is_cancelled = False
        try:
            for idx, step in enumerate(steps):
                broker.update_session_step_index(job_id, idx)
                
                # Check for cancellation between steps
                if cancel_event and cancel_event.is_set():
                    logger.info("[FLOW_ENGINE] Cancellation requested — halting flow.")
                    break

                # VCR pause gate — blocks here when pause_event is cleared
                if pause_event is not None:
                    pause_event.wait()

                logger.info(f"\n[FLOW_ENGINE] === STEP {idx+1}/{len(steps)}: Loading MacroNode '{step.macronode_name}' ===")

                # Notify TUI that this step is starting (for live topology highlighting)
                if node_started_callback is not None:
                    try:
                        node_started_callback(idx, step.macronode_name)
                    except Exception:  # noqa: BLE001
                        pass
            
                # 1. Load the MacroNode
                if step.macronode_name.strip().upper() in ("CTRL_REVIEW", "DET_REVIEW"):
                    macro_def = {
                        "topology_rows": [{
                            "Node_ID": "CTRL_PAUSE_MANUAL",
                            "Model_Override": "none",
                            "Wait_For": "none",
                            "Next_Node": "END"
                        }]
                    }
                else:
                    try:
                        macro_def = self._get_macronode(step.macronode_name, step_config=getattr(step, "config", {}))
                    except KeyError:
                        logger.error(f"[FLOW_ENGINE] ERROR: MacroNode '{step.macronode_name}' not found. Aborting flow.")
                        return current_payload
                
                # 2. Hydrate Agent Slots
                topo_rows = macro_def.get("topology_rows", [])
                hydrated_lists = self._hydrate_topology(topo_rows, step.agent_mapping, getattr(step, "payload_mode", "Unified Ledger"), getattr(step, "custom_instructions", ""), step_index=idx, agent_tools_overrides=getattr(step, "agent_tools_overrides", {}))
            
                # 3. Write to topology.csv
                build_res = build_topology(hydrated_lists)
                logger.info(f"[FLOW_ENGINE] {build_res}")
            
                # 4. Inject Initial Tasks
                start_nodes = self._find_starting_nodes(topo_rows, step_index=idx)
                for start_node in start_nodes:
                    broker.inject_task(job_id=job_id, payload_path=current_payload, starting_node=start_node)
                    logger.info(f"[FLOW_ENGINE] Queued entrypoint: {start_node} with payload '{current_payload}'")

                # 5. Ignite the Swarm Worker for this DAG
                db_path = str(get_datacenter_path("swarm_queue.db"))
                worker = UniversalSwarmWorker()
            
                # Invalidate any cached topologies in the worker so it reads the new topology.csv
                if worker.topology:
                    worker.topology.flush_cache()

                # 5b. Inject FlowStep.config as topology overlay for CTRL_ nodes
                step_config = getattr(step, "config", {})
                if step_config and worker.topology:
                    for row_dict in topo_rows:
                        raw_node_id = str(row_dict.get("Node_ID", ""))
                        if raw_node_id.startswith("CTRL_"):
                            suffixed_id = f"{raw_node_id}_S{idx}"
                            worker.topology.merge_config_overlay(suffixed_id, step_config)
                            logger.info(f"[FLOW_ENGINE] Injected step config overlay for {suffixed_id}")
                
                start_time = time.time()
                timeout_seconds = 3600
            
                for _ in range(500):
                    if cancel_event and cancel_event.is_set():
                        logger.info("[FLOW_ENGINE] Cancellation requested — aborting current MacroNode.")
                        break

                    # VCR pause gate — blocks inside the worker loop too
                    if pause_event is not None:
                        pause_event.wait()

                    if time.time() - start_time > timeout_seconds:
                        logger.info("[FLOW_ENGINE] Swarm Worker Timeout reached.")
                        break
                    
                    worker.execute_cycle(pause_event=pause_event, stop_event=cancel_event)
                
                    with sqlite3.connect(db_path) as _q:
                        still_open: int = _q.execute(
                            "SELECT COUNT(*) FROM task_queue WHERE lock_status = 'open' AND job_id = ?",
                            (job_id,)
                        ).fetchone()[0]
                        still_paused: int = _q.execute(
                            "SELECT COUNT(*) FROM task_queue WHERE lock_status = 'paused' AND job_id = ?",
                            (job_id,)
                        ).fetchone()[0]

                    if still_open == 0 and still_paused > 0:
                        # ── HITL Pause Gate ────────────────────────────────────────
                        # All tasks done except paused ones — surface to TUI for user input
                        logger.info("[FLOW_ENGINE] HITL pause detected — awaiting user input.")
                        if hitl_callback is not None:
                            try:
                                hitl_callback(idx, job_id, current_payload)
                            except Exception:  # noqa: BLE001
                                pass
                        # Block until the TUI resumes (sets pause_event after injecting context)
                        if pause_event is not None:
                            pause_event.clear()
                            pause_event.wait()
                        # After resume, the paused task should now be 'open' again
                        continue

                    if still_open == 0:
                        break

                logger.info(f"[FLOW_ENGINE] MacroNode '{step.macronode_name}' completed execution.")
            
                # 6. Capture output to pass to next step
                latest_ledger = self._find_final_ledger_path(job_id, topo_rows)
                if latest_ledger:
                    current_payload = latest_ledger
                    logger.info(f"[FLOW_ENGINE] Output captured: {current_payload}")
                else:
                    logger.warning(f"[FLOW_ENGINE] Warning: No output ledger found for {step.macronode_name}.")

                # 7. Notify step callback (for TUI payload tracking)
                if step_callback is not None:
                    try:
                        step_callback(idx, current_payload)
                    except Exception:  # noqa: BLE001
                        pass

        except Exception as e:
            logger.error(f"[FLOW_ENGINE] Swarm Orchestration Failed: {e}")
            broker.update_session_status(job_id, "failed")
            raise
        finally:
            if is_cancelled:
                broker.update_session_status(job_id, "cancelled")
            else:
                # If we got here and it is not cancelled and did not exception, it completed successfully
                broker.update_session_status(job_id, "completed")

        # ── 9. Generate Unified Session Ledger ────────────────────────────────
        try:
            self.active_flow_steps = steps
            _ul_path = generate_unified_ledger(job_id, steps)
            logger.info(f"[FLOW_ENGINE] Wrote final unified ledger to {_ul_path}")
            current_payload = str(_ul_path)
        except Exception as e:  # noqa: BLE001
            logger.warning(f"[FLOW_ENGINE] Could not assemble unified ledger: {e}")

        logger.info(f"\n[FLOW_ENGINE] Linear Flow Complete. Final artifact: {current_payload}")

        # ── 8. Cleanup Orphaned Tasks ────────────────────────────────────────────
        try:
            db_path = str(get_datacenter_path("swarm_queue.db"))
            with sqlite3.connect(db_path) as conn:
                conn.execute(
                    "UPDATE task_queue SET lock_status = 'cancelled' WHERE job_id = ? AND lock_status IN ('open', 'paused')",
                    (job_id,)
                )
        except Exception as e:  # noqa: BLE001
            logger.warning(f"[FLOW_ENGINE] Could not clean up orphaned tasks: {e}")

        # (Unified Ledger generation moved above so it can be returned as the Final Artifact)

        # ── 9b. Final Topology Snapshot ───────────────────────────────────────
        try:
            import shutil
            topo_src = get_datacenter_path("02_Dynamic_Context", "topology.csv")
            if topo_src.exists():
                session_dir = get_datacenter_path("02_Dynamic_Context", job_id)
                session_dir.mkdir(parents=True, exist_ok=True)
                topo_dst = session_dir / "topology_snapshot.csv"
                shutil.copy2(topo_src, topo_dst)
                logger.info(f"[FLOW_ENGINE] Saved final topology snapshot to {topo_dst}")
                
                # --- AS-WRAPPED ARTIFACTS ---
                from maccre_core.macronode_registry import get_macronode_store
                from maccre_core.agent_library import get_agent_store
                import json
                import csv
                
                macronode_store = get_macronode_store()
                agent_store = get_agent_store("GLOBAL")
                
                as_wrapped = {
                    "job_id": job_id,
                    "macronodes": {},
                    "agents": {}
                }
                
                used_agents = set()
                with open(topo_src, newline="", encoding="utf-8") as f:
                    for row in csv.reader(f):
                        if len(row) > 1 and row[1].strip():
                            used_agents.add(row[1].strip())
                            
                for step in steps:
                    m_name = step.macronode_name
                    if m_name not in as_wrapped["macronodes"]:
                        try:
                            as_wrapped["macronodes"][m_name] = macronode_store.load(m_name)
                        except Exception:
                            as_wrapped["macronodes"][m_name] = None
                            
                special_nodes = {"CTRL_REVIEW", "CTRL_PAUSE", "CTRL_ANCHOR", "CTRL_RECURSION", "CTRL_GATE", "CTRL_CHECKPOINT", "CTRL_DELAY", "CTRL_TRANSFORM", "DET_REVIEW", "DET_PAUSE", "DET_ANCHOR", "DET_RECURSION", "DET_GATE", "DET_CHECKPOINT", "DET_DELAY", "DET_TRANSFORM"}
                for a_name in used_agents:
                    if a_name.upper() in special_nodes:
                        continue
                    try:
                        as_wrapped["agents"][a_name] = agent_store.get(a_name)
                    except Exception:
                        as_wrapped["agents"][a_name] = None
                        
                wrapped_dst = session_dir / "as_wrapped_topology.json"
                with open(wrapped_dst, "w", encoding="utf-8") as f:
                    json.dump(as_wrapped, f, indent=4)
                logger.info(f"[FLOW_ENGINE] Saved as-wrapped topology to {wrapped_dst}")
                
        except Exception as e:
            logger.warning(f"[FLOW_ENGINE] Could not save topology snapshots: {e}")

        # ── 10. Persist Flow History ───────────────────────────────────────────
        try:
            import json as _json  # noqa: PLC0415
            from maccre_core.utils.session_manager import save_flow_history  # noqa: PLC0415

            steps_json = _json.dumps([s.to_dict() for s in steps])
            # Calculate total cost from task_queue
            total_cost = 0.0
            try:
                db_path = str(get_datacenter_path("swarm_queue.db"))
                with sqlite3.connect(db_path) as _q:
                    total_cost = _q.execute(
                        "SELECT COALESCE(SUM(actual_cost), 0) FROM task_queue WHERE job_id = ?",
                        (job_id,),
                    ).fetchone()[0]
            except Exception:  # noqa: BLE001
                pass

            save_flow_history(
                job_id=job_id,
                project_name=self.project_name,
                flow_steps_json=steps_json,
                initial_payload=initial_payload_path,
                final_artifact=current_payload,
                total_cost=total_cost,
                status="completed",
            )
            logger.info(f"[FLOW_ENGINE] Flow History persisted: {job_id} (${total_cost:.6f})")
        except Exception as e:  # noqa: BLE001
            logger.warning(f"[FLOW_ENGINE] Could not persist flow history: {e}")

        return current_payload


def generate_targeted_ledger(job_id: str, target_node: str, aggregator_node: str = "C_JUDGE") -> str | None:
    """Assemble a Targeted Filter ledger for an agent during recursion.
    It returns only the agent's own previous outputs and the aggregator's outputs.
    - Includes the setup phase (anything before the target's first turn).
    - Includes the target's own previous drafts.
    - Includes the aggregator's reviews (ONLY if routed to this target, or unrouted).
    """
    from datetime import datetime, timezone  # noqa: PLC0415
    import sqlite3  # noqa: PLC0415
    import re  # noqa: PLC0415
    
    ledger_dir = get_datacenter_path("03_Agent_Ledgers", job_id)
    artifact_dir = get_datacenter_path("04_Code_Artifacts", job_id)
    artifact_dir.mkdir(parents=True, exist_ok=True)
    output_path = artifact_dir / f"targeted_ledger_{target_node}.md"
    
    node_meta: list[dict[str, Any]] = []
    try:
        db_path = str(get_datacenter_path("swarm_queue.db"))
        with sqlite3.connect(db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT id, current_node, completed_at FROM task_queue WHERE job_id = ? AND lock_status='completed' ORDER BY id",
                (job_id,)
            ).fetchall()
            for r in rows:
                node_meta.append(dict(r))
    except Exception:  # noqa: BLE001
        pass
        
    ledger_entries: list[tuple[Path, float]] = []
    if ledger_dir.exists():
        for f in ledger_dir.iterdir():
            if f.suffix == ".md" and "thoughts_and_tools" not in f.name and "tool_audit" not in f.name:
                ledger_entries.append((f, f.stat().st_mtime))
                
    def get_sort_key(item: tuple[Path, float]) -> str:
        fpath, mtime = item
        for m in node_meta:
            if m.get("current_node", "") in fpath.stem:
                return m.get("completed_at", "") or ""
        return datetime.fromtimestamp(mtime, tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        
    ledger_entries.sort(key=get_sort_key)
    
    parts = [f"# Targeted Filter Ledger for {target_node}", ""]
    
    # Identify the timestamp/ID of the target's first turn
    target_first_idx = len(ledger_entries)
    for i, (fpath, _) in enumerate(ledger_entries):
        if target_node in fpath.stem:
            target_first_idx = i
            break
            
    for i, (fpath, _) in enumerate(ledger_entries):
        c_node = fpath.stem.rsplit("_", 1)[0]  # strip the _id
        
        # Rule 1: Setup phase (before target's first turn)
        if i < target_first_idx:
            content = fpath.read_text(encoding="utf-8")
            parts.append(f"## [SETUP PHASE: {c_node}]\n{content}\n")
            continue
            
        # Rule 2: The Target's Voice
        if target_node in c_node:
            content = fpath.read_text(encoding="utf-8")
            parts.append(f"## [YOUR PREVIOUS DRAFT]\n{content}\n")
            continue
            
        # Rule 3: The Aggregator's Critique
        if aggregator_node in c_node:
            content = fpath.read_text(encoding="utf-8")
            # Check if this critique was routed to this target (or no explicit route)
            if not re.search(r"ROUTE_TO:.*", content, re.IGNORECASE) or re.search(r"ROUTE_TO:.*" + target_node, content, re.IGNORECASE):
                parts.append(f"## [AGGREGATOR REVIEW]\n{content}\n")
                
        # Rule 4: Discard everything else
        
    unified_text = "\n".join(parts)
    output_path.write_text(unified_text, encoding="utf-8")
    return str(output_path)

def generate_unified_ledger(job_id: str, steps: list[FlowStep] | None = None) -> str:
    """Assemble a unified session ledger from all agent turns in the flow.

    Output: ``04_Code_Artifacts/<job_id>/unified_session_ledger.md``

    Contents:
    - Session metadata (job_id, flow steps, total cost, timestamps)
    - Chronological agent turns with content, node_id, cost, timing
    - Tool call audits (if any)
    - Memory pin summaries
    """
    from datetime import datetime, timezone  # noqa: PLC0415
    import sqlite3

    if job_id.startswith("studio_session_"):
        clean_id = job_id.replace("studio_session_", "", 1)
        ledger_dir = get_datacenter_path("03_Agent_Ledgers", f"ChatStudioSessions/{clean_id}-Chat")
        artifact_dir = get_datacenter_path("04_Code_Artifacts", f"ChatStudioSessions/{clean_id}-Chat")
        artifact_dir.mkdir(parents=True, exist_ok=True)
        output_path = artifact_dir / "unified_chat_ledger.md"
    else:
        ledger_dir = get_datacenter_path("03_Agent_Ledgers", job_id)
        artifact_dir = get_datacenter_path("04_Code_Artifacts", job_id)
        artifact_dir.mkdir(parents=True, exist_ok=True)
        output_path = artifact_dir / "unified_session_ledger.md"

    # ── Collect per-node metadata from task_queue ─────────────────────────
    node_meta: list[dict[str, Any]] = []
    try:
        db_path = str(get_datacenter_path("swarm_queue.db"))
        with sqlite3.connect(db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT id, current_node, lock_status, actual_cost, created_at, "
                "completed_at, locked_by, payload_path "
                "FROM task_queue WHERE job_id = ? ORDER BY id",
                (job_id,),
            ).fetchall()
            for r in rows:
                node_meta.append(dict(r))
    except Exception:  # noqa: BLE001
        pass

    # ── Collect ledger files ──────────────────
    ledger_entries: list[tuple[Path, float]] = []
    if ledger_dir.exists():
        for f in ledger_dir.iterdir():
            if f.suffix == ".md" and "thoughts_and_tools" not in f.name and "tool_audit" not in f.name:
                ledger_entries.append((f, f.stat().st_mtime))
                
    def get_ledger_sort_key(item: tuple[Path, float]) -> str:
        fpath, mtime = item
        if job_id.startswith("studio_session_"):
            return datetime.fromtimestamp(mtime, tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
            
        fname = fpath.stem
        for m in node_meta:
            if m.get("current_node", "") in fname:
                return m.get("completed_at", "") or ""
        # Fallback to mtime if not in db. Use SQLite datetime format so string-sort matches.
        return datetime.fromtimestamp(mtime, tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        
    ledger_entries.sort(key=get_ledger_sort_key)

    # ── Collect memory pins ───────────────────────────────────────────────
    memory_pins: list[dict[str, Any]] = []
    pins_dir = get_datacenter_path("02_Dynamic_Context", "memory_pins")
    if pins_dir.exists():
        import json  # noqa: PLC0415
        for pin_file in sorted(pins_dir.glob(f"pin_*_{job_id}*.json")):
            try:
                pin_data = json.loads(pin_file.read_text(encoding="utf-8"))
                memory_pins.extend(pin_data if isinstance(pin_data, list) else [pin_data])
            except Exception:  # noqa: BLE001
                pass

    # ── Calculate totals ──────────────────────────────────────────────────
    total_cost = sum(m.get("actual_cost", 0.0) for m in node_meta)
    
    if steps is None:
        try:
            import sqlite3
            db_path = str(get_datacenter_path("swarm_queue.db"))
            with sqlite3.connect(db_path) as conn:
                conn.row_factory = sqlite3.Row
                session = conn.execute("SELECT topology_csv FROM job_sessions WHERE job_id = ?", (job_id,)).fetchone()
                if session and session["topology_csv"]:
                    import json
                    steps_data = json.loads(session["topology_csv"])
                    flow_names = " → ".join(s.get("macronode", s.get("macro_name", "Unknown")) for s in steps_data)
                else:
                    flow_names = "Dynamic Swarm"
        except Exception:
            flow_names = "Dynamic Swarm"
    else:
        flow_names = " → ".join(s.macronode_name for s in steps)
        
    gen_ts = datetime.now(tz=timezone.utc).isoformat()

    # ── Assemble document ─────────────────────────────────────────────────
    parts: list[str] = []
    parts.append("# Unified Session Ledger\n")
    parts.append(f"**Job ID:** `{job_id}`  ")
    parts.append(f"**Generated:** {gen_ts}  ")
    parts.append(f"**Flow:** {flow_names}  ")
    parts.append(f"**Total Cost:** ${total_cost:.6f}  ")
    parts.append(f"**Nodes Executed:** {len(node_meta)}  \n")

    # ── Session Timeline ──────────────────────────────────────────────────
    parts.append("## Session Timeline\n")
    parts.append("| # | Node | Status | Cost | Started | Completed |")
    parts.append("|---|------|--------|------|---------|-----------|")
    for i, m in enumerate(node_meta):
        parts.append(
            f"| {i + 1} | `{m.get('current_node', '?')}` | {m.get('lock_status', '?')} "
            f"| ${m.get('actual_cost', 0.0):.6f} "
            f"| {m.get('created_at', '-')} | {m.get('completed_at', '-')} |"
        )
    parts.append("")

    # ── Agent Turns ───────────────────────────────────────────────────────
    parts.append("## Agent Turns (Chronological)\n")
    for ledger_path, _mtime in ledger_entries:
        node_name = ledger_path.stem
        ts_str = datetime.fromtimestamp(_mtime, tz=timezone.utc).isoformat()
        content = ledger_path.read_text(encoding="utf-8")

        # Find matching metadata
        cost = 0.0
        for m in node_meta:
            if m.get("current_node", "") in node_name:
                cost = m.get("actual_cost", 0.0)
                break

        # Strip out embedded tool calls and system responses from pure output
        import re
        content = re.sub(r'\[TOOL CALL REQUESTED:.*?\]', '', content, flags=re.DOTALL | re.IGNORECASE)
        content = re.sub(r'\[SYSTEM_TOOL_CALLBACK.*?\]', '', content, flags=re.DOTALL | re.IGNORECASE)
        content = re.sub(r'\[SYSTEM\]:.*', '', content, flags=re.IGNORECASE)
        
        parts.append(f"### {node_name}")
        parts.append(f"*Written: {ts_str} | Cost: ${cost:.6f}*\n")
        parts.append(content.strip())
        parts.append("\n---\n")

    # Tool Call Audits are intentionally excluded from the unified session ledger
    # to ensure the final payload is clean and primarily prose-based.

    # ── Memory Pins (Knowledge Triplets) ──────────────────────────────────
    if memory_pins:
        parts.append("## Extracted Knowledge Triplets\n")
        parts.append("| Subject | Predicate | Object | Significance |")
        parts.append("|---------|-----------|--------|-------------|")
        for pin in memory_pins[:50]:  # Cap at 50 for readability
            parts.append(
                f"| {pin.get('subject', '?')} | {pin.get('predicate', '?')} "
                f"| {pin.get('object', '?')} | {pin.get('significance', '-')} |"
            )
        if len(memory_pins) > 50:
            parts.append(f"\n*... and {len(memory_pins) - 50} more triplets*\n")
        parts.append("")

    # ── Canonization Status ───────────────────────────────────────────────
    parts.append("## Canonization Status\n")
    parts.append("**Status:** `CANDIDATE` — awaiting selection for project-level canonization.  ")
    parts.append(
        "**To canonize:** `python maccre.py canonize --project <project> --session "
        f"{job_id}`  "
    )
    parts.append(
        "Canonization will elevate memory pins → `memory_pins.db` vectors, "
        "ledger vectors → project canon, and topology → `topology_library`.\n"
    )

    # ── Write ─────────────────────────────────────────────────────────────
    unified_text = "\n".join(parts)
    output_path.write_text(unified_text, encoding="utf-8")
    logger.info(
        "[FLOW_ENGINE] Unified Session Ledger: %d chars, %d turns, %d pins, $%.6f total.",
        len(unified_text), len(ledger_entries), len(memory_pins), total_cost,
    )
    
    # Also generate the thoughts ledger
    try:
        generate_unified_thoughts_ledger(job_id)
    except Exception as e:
        logger.warning(f"[FLOW_ENGINE] Failed to generate unified thoughts ledger: {e}")
        
    return str(output_path)

def generate_unified_thoughts_ledger(job_id: str) -> str:
    """Assemble a unified thoughts ledger from all agent logs in the flow.

    Output: ``04_Code_Artifacts/<job_id>/unified_thoughts_ledger.md``

    Contents:
    - Session metadata (job_id, timestamps)
    - Chronological agent turns with their raw thoughts and tool calls extracted from their .log files.
    """
    from datetime import datetime, timezone
    import sqlite3
    import re

    ledger_dir = get_datacenter_path("03_Agent_Ledgers", job_id)
    artifact_dir = get_datacenter_path("04_Code_Artifacts", job_id)
    artifact_dir.mkdir(parents=True, exist_ok=True)
    output_path = artifact_dir / "unified_thoughts_ledger.md"

    # ── Collect per-node metadata from task_queue ─────────────────────────
    node_meta: list[dict[str, Any]] = []
    try:
        db_path = str(get_datacenter_path("swarm_queue.db"))
        with sqlite3.connect(db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT id, current_node, lock_status, actual_cost, created_at, "
                "completed_at, locked_by, payload_path "
                "FROM task_queue WHERE job_id = ? ORDER BY id",
                (job_id,),
            ).fetchall()
            for r in rows:
                node_meta.append(dict(r))
    except Exception:  # noqa: BLE001
        pass

    # ── Collect log files ──────────────────
    log_entries: list[tuple[Path, float]] = []
    if ledger_dir.exists():
        for f in ledger_dir.iterdir():
            if f.suffix == ".log" and "_agent.log" in f.name:
                log_entries.append((f, f.stat().st_mtime))
                
    def get_ledger_sort_key(item: tuple[Path, float]) -> str:
        fpath, mtime = item
        fname = fpath.stem.replace("_agent", "")
        for m in node_meta:
            if m.get("current_node", "") in fname:
                return m.get("completed_at", "") or ""
        # Fallback to mtime if not in db. Use SQLite datetime format so string-sort matches.
        return datetime.fromtimestamp(mtime, tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        
    log_entries.sort(key=get_ledger_sort_key)

    gen_ts = datetime.now(tz=timezone.utc).isoformat()

    # ── Assemble document ─────────────────────────────────────────────────
    parts: list[str] = []
    parts.append("# Unified Thoughts Ledger\n")
    parts.append(f"**Job ID:** `{job_id}`  ")
    parts.append(f"**Generated:** {gen_ts}  \n")

    # ── Agent Turns ───────────────────────────────────────────────────────
    parts.append("## Agent Thoughts & Tool Executions (Chronological)\n")
    for log_path, _mtime in log_entries:
        node_name = log_path.stem.replace("_agent", "")
        ts_str = datetime.fromtimestamp(_mtime, tz=timezone.utc).isoformat()
        
        try:
            raw_content = log_path.read_text(encoding="utf-8")
        except Exception:
            continue

        import json as _json_mod
        # ── Parse JSON-formatted log lines ─────────────────────────
        # Each line is a JSON object with a "message" field. Extract all
        # message fields and reassemble them into a single content string.
        # This handles multi-line tagged messages (e.g. <api_thought>\n...\n</api_thought>)
        # that span a single JSON "message" value.
        parsed_messages: list[str] = []
        for line in raw_content.splitlines():
            stripped = line.strip()
            if stripped.startswith("{"):
                try:
                    obj = _json_mod.loads(stripped)
                    if "message" in obj:
                        parsed_messages.append(str(obj["message"]))
                    else:
                        parsed_messages.append(stripped)
                except Exception:
                    parsed_messages.append(line)
            else:
                parsed_messages.append(line)
        content = "\n".join(parsed_messages)

        # Extract thoughts, generation logs, and tools
        thought_matches = list(re.finditer(r"<(?:api_)?thought>(.*?)</(?:api_)?thought>", content, re.DOTALL | re.IGNORECASE))
        gen_log_matches = list(re.finditer(r"<generation_log>(.*?)</generation_log>", content, re.DOTALL | re.IGNORECASE))
        # Support both legacy [TOOL CALL...] format and the newer <tool_call> format
        tool_matches = list(re.finditer(r"<tool_call>(.*?)</tool_call>|(\[TOOL CALL REQUESTED:.*?\])(?=\n\[TOOL|\n<|\n\Z|\Z)", content, re.DOTALL | re.IGNORECASE))
        
        all_matches: list[tuple[int, str, str]] = []
        for tm in thought_matches:
            all_matches.append((tm.start(), "thought", tm.group(1).strip()))
        for tm in gen_log_matches:
            all_matches.append((tm.start(), "generation", tm.group(1).strip()))
        for tm in tool_matches:
            text = tm.group(1) if tm.group(1) is not None else tm.group(2)
            all_matches.append((tm.start(), "tool", text.strip()))
            
        all_matches.sort(key=lambda x: x[0])
        
        has_content = False
        turn_parts = [f"### {node_name}", f"*Written: {ts_str}*\n"]
        
        for _pos, mtype, text in all_matches:
            has_content = True
            if mtype == "thought":
                turn_parts.append("#### 🤔 Thought")
            elif mtype == "generation":
                turn_parts.append("#### 📡 Generation")
            else:
                turn_parts.append("#### 🛠️ Tool Call")
            turn_parts.append(f"```\n{text}\n```\n")

        if has_content:
            parts.extend(turn_parts)
            parts.append("\n---\n")

    # ── Write ─────────────────────────────────────────────────────────────
    unified_text = "\n".join(parts)
    output_path.write_text(unified_text, encoding="utf-8")
    return str(output_path)
