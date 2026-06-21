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
    def __init__(self, macronode_name: str, agent_mapping: dict[str, str] | None = None) -> None:
        self.macronode_name = macronode_name
        self.agent_mapping = agent_mapping or {}

    def to_dict(self) -> dict[str, Any]:
        """Serialize for JSON persistence in flow_history."""
        return {"macronode_name": self.macronode_name, "agent_mapping": self.agent_mapping}

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "FlowStep":
        """Reconstruct from a dict (flow_history deserialization)."""
        return cls(
            macronode_name=d.get("macronode_name", ""),
            agent_mapping=d.get("agent_mapping", {}),
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

    def _get_macronode(self, name: str) -> dict[str, Any]:
        """Fetch MacroNode definition from Project, fallback to GLOBAL, fallback to agent auto-wrap."""
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

    def _find_starting_nodes(self, topology_rows: list[dict[str, Any]]) -> list[str]:
        """Heuristically find all starting Node_IDs of a MacroNode DAG."""
        if not topology_rows:
            return ["OSINT"]
        
        start_nodes = []
        for row in topology_rows:
            wait_for = str(row.get("Wait_For", "none")).strip().lower()
            if wait_for in ("none", "", "null"):
                start_nodes.append(str(row.get("Node_ID", "OSINT")))
        
        if not start_nodes:
            # Fallback if somehow there's a circular Wait_For loop with no entry
            start_nodes.append(str(topology_rows[0].get("Node_ID", "OSINT")))
            
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

    def execute_flow(
        self,
        steps: list[FlowStep],
        initial_payload_path: str,
        cancel_event: threading.Event | None = None,
        pause_event: threading.Event | None = None,
        step_callback: Callable[[int, str], None] | None = None,
        hitl_callback: Callable[[int, str, str], None] | None = None,
        job_started_callback: Callable[[str], None] | None = None,
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
            
            # 4. Inject Initial Tasks
            start_nodes = self._find_starting_nodes(topo_rows)
            for start_node in start_nodes:
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

        logger.info(f"\n[FLOW_ENGINE] Linear Flow Complete. Final artifact: {current_payload}")

        # ── 8. Generate Unified Session Ledger ────────────────────────────────
        try:
            unified_path = self._generate_unified_ledger(job_id, steps)
            logger.info(f"[FLOW_ENGINE] Unified Session Ledger → {unified_path}")
        except Exception as e:  # noqa: BLE001
            logger.warning(f"[FLOW_ENGINE] Could not generate unified ledger: {e}")

        # ── 9. Persist Flow History ───────────────────────────────────────────
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

    def _generate_unified_ledger(self, job_id: str, steps: list[FlowStep]) -> str:
        """Assemble a unified session ledger from all agent turns in the flow.

        Output: ``04_Code_Artifacts/<job_id>/unified_session_ledger.md``

        Contents:
        - Session metadata (job_id, flow steps, total cost, timestamps)
        - Chronological agent turns with content, node_id, cost, timing
        - Tool call audits (if any)
        - Memory pin summaries
        """
        from datetime import datetime, timezone  # noqa: PLC0415

        ledger_dir = get_datacenter_path("03_Agent_Ledgers", job_id)
        artifact_dir = get_datacenter_path("04_Code_Artifacts", job_id)
        artifact_dir.mkdir(parents=True, exist_ok=True)
        output_path = artifact_dir / "unified_session_ledger.md"

        # ── Collect per-node metadata from task_queue ─────────────────────────
        node_meta: list[dict[str, Any]] = []
        try:
            import sqlite3  # noqa: PLC0415
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

        # ── Collect ledger files sorted by modification time ──────────────────
        ledger_entries: list[tuple[Path, float]] = []
        tool_audits: list[tuple[Path, float]] = []
        if ledger_dir.exists():
            for f in ledger_dir.iterdir():
                if f.suffix == ".md" and "tool_audit" not in f.name:
                    ledger_entries.append((f, f.stat().st_mtime))
                elif f.suffix == ".md" and "tool_audit" in f.name:
                    tool_audits.append((f, f.stat().st_mtime))
        ledger_entries.sort(key=lambda x: x[1])
        tool_audits.sort(key=lambda x: x[1])

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

            parts.append(f"### {node_name}")
            parts.append(f"*Written: {ts_str} | Cost: ${cost:.6f}*\n")
            parts.append(content)
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
            "Canonization will elevate memory pins → `thought_pins.db` vectors, "
            "ledger vectors → project canon, and topology → `topology_library`.\n"
        )

        # ── Write ─────────────────────────────────────────────────────────────
        unified_text = "\n".join(parts)
        output_path.write_text(unified_text, encoding="utf-8")
        logger.info(
            "[FLOW_ENGINE] Unified Session Ledger: %d chars, %d turns, %d pins, $%.6f total.",
            len(unified_text), len(ledger_entries), len(memory_pins), total_cost,
        )
        return str(output_path)
