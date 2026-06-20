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
from typing import Any

from maccre_core.macronode_registry import get_macronode_store
from maccre_core.orchestration.local_broker import LocalMessageBroker
from maccre_core.orchestration.swarm_worker import UniversalSwarmWorker
from maccre_core.tools.admin_tools import build_topology, ensure_project_workbook
from maccre_core.utils.path_resolver import get_datacenter_path
from maccre_core.utils.session_manager import generate_session_id

logger = logging.getLogger(__name__)


class FlowStep:
    """A single step in a Linear Flow, pointing to a MacroNode."""
    def __init__(self, macronode_name: str, agent_mapping: dict[str, str] | None = None) -> None:
        self.macronode_name = macronode_name
        self.agent_mapping = agent_mapping or {}


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

    def _get_macronode(self, name: str) -> dict[str, Any]:
        """Fetch MacroNode definition from Project, fallback to GLOBAL."""
        try:
            return self.macronode_store.load(name)
        except KeyError:
            return self.global_store.load(name)

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
                hydrated_lists = self._hydrate_topology(topo_rows, step.agent_mapping)
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
                sentinel = get_sentinel(api_key)
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

    def execute_flow(
        self,
        steps: list[FlowStep],
        initial_payload_path: str = "none",
        cancel_event: threading.Event | None = None,
        pause_event: threading.Event | None = None,
        step_callback: Any = None,
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

        Returns:
            The path to the final output file from the last step in the flow.
        """
        os.environ["MACCRE_ACTIVE_PROJECT"] = self.project_name
        ensure_project_workbook(self.project_name)

        job_id = f"job_{generate_session_id()}"
        logger.info(f"[FLOW_ENGINE] Booting Linear Flow (Job: {job_id}) across {len(steps)} MacroNode(s).")

        current_payload = initial_payload_path
        broker = LocalMessageBroker()
        
        for idx, step in enumerate(steps):
            # Check for cancellation between steps
            if cancel_event and cancel_event.is_set():
                logger.info("[FLOW_ENGINE] Cancellation requested — halting flow.")
                break

            # VCR pause gate — blocks here when pause_event is cleared
            if pause_event is not None:
                pause_event.wait()

            logger.info(f"\n[FLOW_ENGINE] === STEP {idx+1}/{len(steps)}: Loading MacroNode '{step.macronode_name}' ===")
            
            # 1. Load the MacroNode
            try:
                macro_def = self._get_macronode(step.macronode_name)
            except KeyError:
                logger.error(f"[FLOW_ENGINE] ERROR: MacroNode '{step.macronode_name}' not found. Aborting flow.")
                return current_payload
                
            # 2. Hydrate Agent Slots
            topo_rows = macro_def.get("topology_rows", [])
            hydrated_lists = self._hydrate_topology(topo_rows, step.agent_mapping)
            
            # 3. Write to topology.csv
            build_res = build_topology(hydrated_lists)
            logger.info(f"[FLOW_ENGINE] {build_res}")
            
            # 4. Inject Initial Task
            start_node = self._find_starting_node(topo_rows)
            broker.inject_task(job_id=job_id, payload_path=current_payload, starting_node=start_node)
            logger.info(f"[FLOW_ENGINE] Queued entrypoint: {start_node} with payload '{current_payload}'")

            # 5. Ignite the Swarm Worker for this DAG
            db_path = str(get_datacenter_path("swarm_queue.db"))
            worker = UniversalSwarmWorker()
            
            # Invalidate any cached topologies in the worker so it reads the new topology.csv
            if worker.topology:
                worker.topology.flush_cache()
                
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
                    
                worker.execute_cycle()
                
                with sqlite3.connect(db_path) as _q:
                    still_open: int = _q.execute(
                        "SELECT COUNT(*) FROM task_queue WHERE lock_status = 'open' AND job_id = ?",
                        (job_id,)
                    ).fetchone()[0]
                    
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

        logger.info(f"\n[FLOW_ENGINE] Linear Flow Complete. Final artifact: {current_payload}")
        return current_payload
