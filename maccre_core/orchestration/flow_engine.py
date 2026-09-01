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

import hashlib
import logging
import os
import sqlite3
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Sequence

from maccre_core.macronode_registry import get_macronode_store
from maccre_core.orchestration.concurrency import atomic_write_text, file_lock
from maccre_core.orchestration.deterministic_nodes import (
    is_deterministic_node,
    resolve_primitive_node_id,
)
from maccre_core.orchestration.local_broker import LocalMessageBroker
from maccre_core.orchestration.swarm_pool import DynamicSwarmPool
from maccre_core.orchestration.topology_engine import TopologyEngine
from maccre_core.orchestration.topology_graph import (
    entry_nodes,
    is_terminal_target,
    parse_targets,
    terminal_nodes,
)
from maccre_core.tools.admin_tools import build_topology, ensure_project_workbook
from maccre_core.utils.path_resolver import get_datacenter_path
from maccre_core.utils.session_manager import generate_session_id

logger = logging.getLogger(__name__)


def _default_tether_id(scatter_agents: Sequence[str]) -> str:
    """Generate a scatter's tether scope when the operator did not name one.

    Derived from the agent set, so it is **stable**: the same scatter produces the
    same tether on every call and in every process.

    That stability matters more than it looks. The previous default was
    ``f"scatter_{id(scatter_agents) % 9999:04d}"`` — keyed on a CPython object
    address, which is neither reproducible across runs nor guaranteed identical
    between two calls in one run. The auto-wrap *is* called twice per step, once
    for pre-flight validation and once for execution, so the tether validated was
    not necessarily the tether executed. All rows within a single call agreed,
    which is why it never broke outright, but nothing about it was load-bearing by
    design.

    Deriving from the agent set also keeps two different scatters in one job from
    colliding into a single gather scope, which an address-derived value could do
    by coincidence.
    """
    digest = hashlib.sha1("|".join(scatter_agents).encode("utf-8")).hexdigest()[:8]
    return f"scatter_{digest}"


#: ``FlowStep.config`` keys whose values name routing targets, and so must carry
#: the ``_S{step}`` suffix that :meth:`FlowRunner._hydrate_topology` applies to the
#: topology itself.
#:
#: Kept as an explicit allow-list rather than "hydrate anything that looks like a
#: node name". Most config values are not node references — ``scatter_mode``,
#: ``merge_delimiter``, ``auto_resume_after`` — and suffixing one of those would
#: corrupt it silently. Adding a routing key to config means adding it here.
_ROUTING_CONFIG_KEYS: tuple[str, ...] = (
    "scatter_targets",
    "next_node",
    "wait_for",
)


def _hydrate_config_targets(config: dict[str, Any], step_index: int) -> dict[str, Any]:
    """Copy *config* with routing-target values suffixed for *step_index*.

    Handles both list-valued keys (``scatter_targets``) and delimited strings
    (``next_node``, ``wait_for``), and leaves terminal sentinels alone so ``END``
    does not become ``END_S0``.
    """
    hydrated = dict(config)
    for key in _ROUTING_CONFIG_KEYS:
        if key not in hydrated:
            continue
        value = hydrated[key]
        if isinstance(value, list):
            hydrated[key] = [
                name if is_terminal_target(str(name)) else f"{str(name).strip()}_S{step_index}"
                for name in value
                if str(name).strip()
            ]
        elif isinstance(value, str) and value.strip():
            if is_terminal_target(value):
                continue
            hydrated[key] = ",".join(
                f"{name}_S{step_index}" for name in parse_targets(value)
            )
    return hydrated


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
        #
        # Gate on is_deterministic_node() rather than a literal startswith("CTRL_"):
        # it also admits the legacy DET_ prefix, which the hardcoded review
        # intercept used to handle separately (DET_REVIEW would otherwise fall
        # through to the KeyError below).
        if is_deterministic_node(name):
            cfg = step_config or {}
            scatter_agents: list[str] = cfg.get("scatter_agents", [])

            # CTRL_SCATTER with slotted agents → full scatter→agents→merge DAG
            if name.upper().startswith("CTRL_SCATTER") and scatter_agents:
                agent_overrides: dict[str, dict[str, Any]] = cfg.get("scatter_agent_overrides", {})
                scatter_mode: str = cfg.get("scatter_mode", "full_copy")
                # `or` rather than a .get default, because the authoring UI writes
                # the key even when the field is blank. `_collect_ctrl_config` does
                # cfg["tether_id"] = <input>.value.strip(), so saving a CTRL_SCATTER
                # with the Tether ID box empty stores "" — a *present* key. A
                # .get("tether_id", <generated>) then returns "" and the generated
                # value never applies. Measured live: every task_queue row carried
                # an empty tether, which left the tether-scoped fan-in unreachable
                # and an 8-lane CTRL_MERGE gathering 1 source instead of 8.
                tether_id: str = (
                    str(cfg.get("tether_id") or "").strip()
                    or _default_tether_id(scatter_agents)
                )
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
                    "Tether_ID": tether_id,
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
                        "Tether_ID": tether_id,
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
                    "Tether_ID": tether_id,
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

            # Generic CTRL_ node (PAUSE, REVIEW, GATE, CHECKPOINT, ...) →
            # single-node passthrough.
            #
            # Node_ID goes through resolve_primitive_node_id so authoring-level
            # aliases land on the primitive that actually implements them. This is
            # what replaced the hardcoded
            #     if step.macronode_name.upper() in ("CTRL_REVIEW", "DET_REVIEW"):
            #         macro_def = {... "Node_ID": "CTRL_PAUSE_MANUAL", "Next_Node": "END"}
            # blocks that used to sit inline in execute_flow and resume_flow. Those
            # violated Law III (registry-driven, no string special-casing), skipped
            # preflight validation entirely, and discarded step.config — so an
            # operator-set auto_resume_after was silently ignored.
            node_id = resolve_primitive_node_id(name)

            # Next_Node and Wait_For are config-driven with the previous literals
            # as defaults. "END" terminates this macronode's *internal* DAG only;
            # the outer step loop in execute_flow still advances to the next
            # FlowStep, which is why the 3-step baseline reaches S2. Allowing an
            # override is what lets a control node sit mid-lane inside a scatter
            # and continue to that lane's successor instead of closing the lane.
            next_node = str(cfg.get("next_node", "END")).strip() or "END"
            wait_for = str(cfg.get("wait_for", "none")).strip() or "none"

            logger.info(
                "[FLOW_ENGINE] Auto-wrapping control node '%s' as single-node topology "
                "(node_id=%s, next=%s).",
                name, node_id, next_node,
            )
            return {
                "name": name,
                "description": f"Auto-wrapped control node: {name}",
                "is_template": False,
                "agent_slots": [],
                "topology_rows": [{
                    "Node_ID": node_id,
                    "Agent_Name": "SYSTEM",
                    "Model_Override": "none",
                    "Next_Node": next_node,
                    "Temperature": "0",
                    "Instruction_Override": str(cfg.get("instruction_override", "")),
                    "Wait_For": wait_for,
                    "Failure_Target": str(cfg.get("failure_target", "FAILED")),
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
            # Review nodes used to be skipped here ("CTRL_REVIEW is a hardcoded
            # intercept node, bypass validation"). They now resolve through the
            # ordinary control-node auto-wrap, so they are validated like anything
            # else — a review step with a bad next_node or wait_for is caught
            # before the flow spends money.
            try:
                macro_def = self._get_macronode(macro_name, step_config=getattr(step, "config", {}))
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
            # Both fields go through the shared parser, so a hand-authored
            # topology means the same thing here as it does to the broker that
            # enqueues successors. This used to split Next_Node on "," alone while
            # route_task accepted "," and "|", so a pipe-delimited Next_Node
            # hydrated into one phantom token ("B|C_S0") and neither successor ran.
            if next_node and not is_terminal_target(next_node):
                targets = parse_targets(next_node)
                next_node = ",".join(f"{p}_S{step_index}" for p in targets)
            if wait_for and wait_for.lower() not in ("none", ""):
                wait_for = "|".join(
                    f"{p}_S{step_index}" for p in parse_targets(wait_for)
                )

            instr = str(row_dict.get("Instruction_Override", ""))
            if custom_instructions:
                wrapped_instructions = f"\n\n[NODE DIRECTIVES]\n{custom_instructions}\n[MAINTAIN CORE PERSONA WHILE EXECUTING DIRECTIVES]\n"
                instr = f"{instr}{wrapped_instructions}".strip()
                
            tools_allowed = agent_tools_overrides.get(agent_name, "")

            # Standard order: Node_ID, Agent_Name, Model_Override, Next_Node, Temp,
            # Instr, Wait, Fail, MaxRec, Artifact, Live, Partner, Rounds,
            # Payload_Mode, Tools_Allowed, Tether_ID
            #
            # Tether_ID is last and was previously absent. The scatter auto-wrap
            # computed a tether and wrote it into every row dict, but this flatten
            # step had no slot for it, so it was dropped before reaching the CSV —
            # and with it the whole tether-scoped fan-in path.
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
                str(row_dict.get("Tether_ID", "")),
            ]
            hydrated.append(row_list)
        return hydrated

    def _find_starting_nodes(self, topology_rows: list[dict[str, Any]], step_index: int = 0) -> list[str]:
        """Find the entry Node_IDs of a MacroNode DAG, hydrated with the step suffix.

        An entry point is a node **nothing else routes to**. That is a property of
        the graph's edges, so it is read from the edges — see
        :mod:`maccre_core.orchestration.topology_graph`.

        This previously inferred entry points from ``Wait_For == "none"``, which
        conflated two different things. ``Wait_For`` is the *gather gate*: how many
        upstreams must finish before a node may run. It is not a predecessor list.
        For most topologies the two happen to agree, which is why it survived; for
        a scatter they diverge completely, because the auto-wrap gives every lane
        ``Wait_For: "none"`` (a lane gathers from nothing) while every lane is
        clearly downstream of the scatter.

        Read as entry points, all eight lanes of an 8-wide scatter were seeded
        directly against the raw job payload in parallel with the scatter that was
        supposed to feed them — so every agent executed twice. Measured live in
        UT-0: 16 inference calls for an 8-lane scatter, and the flow still reported
        success.
        """
        if not topology_rows:
            return [f"OSINT_S{step_index}"]

        start_nodes = [
            f"{node_id}_S{step_index}" for node_id in entry_nodes(topology_rows)
        ]
        if start_nodes:
            return start_nodes

        # No Node_IDs at all in these rows. entry_nodes already handles the cyclic
        # case by nominating a node, so reaching here means the rows are malformed.
        node_id = str(topology_rows[0].get("Node_ID", "OSINT"))
        logger.warning(
            "[FLOW_ENGINE] Step %d topology has no usable Node_ID; seeding %r.",
            step_index + 1, node_id,
        )
        return [f"{node_id}_S{step_index}"]

    def _find_terminal_nodes(
        self, topology_rows: list[dict[str, Any]], step_index: int = 0
    ) -> list[str]:
        """Sink Node_IDs of a MacroNode DAG, hydrated with the step suffix.

        The mirror of :meth:`_find_starting_nodes`, and deliberately built the same
        way: the structural question goes to
        :mod:`maccre_core.orchestration.topology_graph`, and hydration happens here
        through the one ``f"{node_id}_S{step_index}"`` expression the engine uses
        everywhere. A second derivation of either half is how the TUI and the
        engine came to disagree about node ids.
        """
        if not topology_rows:
            return []
        return [
            f"{node_id}_S{step_index}" for node_id in terminal_nodes(topology_rows)
        ]

    def _capture_step_output(
        self,
        job_id: str,
        topology_rows: list[dict[str, Any]],
        step_index: int,
        broker: LocalMessageBroker,
    ) -> str | None:
        """The artifact this step's terminal node recorded, for the next step to read.

        Returns ``None`` when no terminal node has a recorded output. The caller
        must **not** substitute a guess: leaving the previous payload in place is
        wrong but visible, whereas any fabricated path is wrong and acted upon.

        .. note::
           **What this replaces, and why (defect E2).**

           This used to be ``_find_final_ledger_path``, which globbed
           ``03_Agent_Ledgers/<job_id>/*.md`` and returned the newest by mtime. It
           took ``topology_rows`` and never read them, so the "final node of the
           DAG" in its docstring was never consulted.

           On the D-GATE run the merge wrote ``CTRL_MERGE_S0_merged.md`` (426 KB)
           and the worker then wrote the node's 59-byte ledger stub
           ``CTRL_MERGE_S0_93.md`` *after* the handler returned. The stub is
           therefore always the newer file — this was not a race the glob
           occasionally lost, it was one it always lost. The next step received 59
           bytes describing the merge instead of the merged document, and the flow
           reported success.

           Three further hazards the glob carried, all removed by asking the queue
           instead: the directory is scoped to the *job*, not the step, so step 2
           could inherit a step 1 file; ``*.md`` also matches
           ``thoughts_and_tools_*``, ``*_agent.log`` siblings' companions and
           scatter chunk files; and mtime resolution on Windows is coarse enough
           that two files written in the same handler are not reliably ordered.

           The queue row is the authoritative record because ``route_task`` writes
           the completing node's ``output_path``, and
           :meth:`~LocalMessageBroker.get_completed_payload_paths` filters on
           ``lock_status = 'completed'`` — so a node that failed, stalled or was
           cancelled contributes nothing rather than a stale path.
        """
        terminals = self._find_terminal_nodes(topology_rows, step_index)
        if not terminals:
            logger.warning(
                "[FLOW_ENGINE] Step %d topology declares no terminal node; cannot "
                "identify this step's output.",
                step_index + 1,
            )
            return None

        found = broker.get_completed_payload_paths(job_id, terminals)
        if not found:
            logger.error(
                "[FLOW_ENGINE] Step %d produced no recorded output: none of its "
                "terminal node(s) %s has a completed row with an output. The next "
                "step will NOT be handed a substitute — a guessed payload is worse "
                "than a visibly missing one.",
                step_index + 1, terminals,
            )
            return None

        # Order by the topology's own declaration, never by completion time or
        # mtime, so a divergent-lane DAG resolves to the same artifact on every run.
        ordered = [node for node in terminals if node in found]
        if len(ordered) > 1:
            logger.warning(
                "[FLOW_ENGINE] Step %d has %d terminal nodes with output (%s). "
                "Handing the next step the first in declared order (%s). A DAG with "
                "divergent endpoints has no single output, so this is a choice, not "
                "a fact — author a CTRL_MERGE if the next step needs all of them.",
                step_index + 1, len(ordered), ordered, ordered[0],
            )
        return found[ordered[0]]


    # ── Phase 6.12B: shared worker-pool driver ─────────────────────────────────

    @staticmethod
    def _build_topology_overlays(
        topo_rows: list[dict[str, Any]],
        step_config: dict[str, Any],
        step_index: int,
    ) -> dict[str, dict[str, Any]]:
        """Map ``FlowStep.config`` onto the step's hydrated control-node ids.

        Only control nodes get an overlay: agent rows take their configuration
        from the roster and the topology row itself.

        Previously this lived inline in ``execute_flow`` only, so a resumed flow
        silently ran its control nodes **without** their config — an operator's
        ``auto_resume_after`` or gate predicate applied on the first run and
        vanished on resume.

        Node-name-bearing config keys are hydrated with the step suffix
        ------------------------------------------------------------------
        ``step_config`` comes straight from the authoring UI, where node names are
        written bare. The topology those names refer to is hydrated to
        ``NAME_S{step}``. Any config value that is a *routing target* therefore has
        to be hydrated too, or the control node routes somewhere the topology does
        not describe.

        ``CTRL_SCATTER`` is where this bit: its ``scatter_targets`` were passed
        through untouched, so the deterministic node routed to bare ``Testy``,
        ``Regular_Joe``, ... while the topology described ``Testy_S0``,
        ``Regular_Joe_S0``, ... The broker happily created rows for both sets, so
        every lane of an 8-wide scatter existed twice and every agent ran twice.
        """
        overlays: dict[str, dict[str, Any]] = {}
        if not step_config:
            return overlays
        for row in topo_rows:
            raw_node_id = str(row.get("Node_ID", ""))
            if raw_node_id and is_deterministic_node(raw_node_id):
                overlays[f"{raw_node_id}_S{step_index}"] = _hydrate_config_targets(
                    step_config, step_index
                )
        return overlays

    def _run_worker_pool(
        self,
        job_id: str,
        step_index: int,
        broker: LocalMessageBroker,
        topo_rows: list[dict[str, Any]],
        step_config: dict[str, Any],
        current_payload: str,
        pause_event: threading.Event | None = None,
        cancel_event: threading.Event | None = None,
        hitl_callback: Callable[[int, str, str], None] | None = None,
        node_active_callback: Callable[[int | None, str, int | None], None] | None = None,
        node_finished_callback: Callable[[int | None, str, int | None], None] | None = None,
        max_workers: int | None = None,
        timeout_seconds: float = 3600.0,
    ) -> str:
        """Execute one flow step's DAG on a :class:`DynamicSwarmPool`.

        Replaces the two near-identical ``for _ in range(500): worker.execute_cycle()``
        loops that used to live in :meth:`execute_flow` and :meth:`resume_flow`.
        Having one copy is the point: the duplicates had already drifted — only
        ``execute_flow`` applied the step's config overlay, and only it logged the
        HITL gate.

        Concurrency comes from the pool; this method stays single-threaded and
        keeps the HITL pause gate exactly where it was.

        Returns:
            ``"completed"``, ``"cancelled"``, ``"timeout"`` or ``"stalled"``.

            ``"stalled"`` means tasks were left ``locked`` with no worker alive to
            finish them — a claimed node that never ran. It is reported separately
            from ``"timeout"`` because the two need different responses: a timeout
            may just need a longer budget, while a stall is a worker that died.
        """
        overlays = self._build_topology_overlays(topo_rows, step_config, step_index)
        if overlays:
            logger.info(
                "[FLOW_ENGINE] Step %d: applying step config to %d control node(s): %s",
                step_index + 1, len(overlays), sorted(overlays),
            )

        # Resolve the concurrency ceiling from the step's own configuration. A
        # scatter with 4 slotted agents should not open 8 threads.
        scatter_agents = step_config.get("scatter_agents") or []
        if max_workers is None and scatter_agents:
            max_workers = len(scatter_agents)

        topology_for_gate = TopologyEngine()
        topology_for_gate.flush_cache()
        for node_id, overlay in overlays.items():
            topology_for_gate.merge_config_overlay(node_id, overlay)

        pool = DynamicSwarmPool(
            job_id=job_id,
            max_workers=max_workers,
            # Advisory sizing only. The atomic claim in the broker remains the
            # sole authority on who owns a task.
            demand_estimator=lambda cap: broker.count_ready_tasks(
                job_id, topology_for_gate, cap
            ),
            on_node_start=node_active_callback,
            on_node_finish=node_finished_callback,
            topology_overlays=overlays,
        )

        # One connection for the whole step, not one per poll tick. The old loops
        # opened a fresh sqlite3.connect() on every iteration — up to 500 per step,
        # each with its own WAL handshake.
        db_path = str(get_datacenter_path("swarm_queue.db"))
        deadline = time.time() + timeout_seconds

        with sqlite3.connect(db_path, timeout=30.0) as poll_conn:

            def count_by_status(status: str) -> int:
                return int(
                    poll_conn.execute(
                        "SELECT COUNT(*) FROM task_queue "
                        "WHERE lock_status = ? AND job_id = ?",
                        (status, job_id),
                    ).fetchone()[0]
                )

            # Each iteration is one drain-then-check-for-HITL cycle. A flow with
            # two review nodes in one step goes round twice.
            while True:
                if cancel_event is not None and cancel_event.is_set():
                    logger.info("[FLOW_ENGINE] Cancellation requested — aborting current MacroNode.")
                    return "cancelled"

                remaining = deadline - time.time()
                if remaining <= 0:
                    logger.info("[FLOW_ENGINE] Swarm Worker Timeout reached.")
                    return "timeout"

                result = pool.run_until_drained(
                    is_drained=lambda: count_by_status("open") == 0,
                    pause_event=pause_event,
                    stop_event=cancel_event,
                    timeout_seconds=remaining,
                    # Without this the pool cannot tell "everything finished" from
                    # "a worker died still holding its task". Both look like an
                    # empty queue, because a locked row is not an open one.
                    locked_probe=lambda: count_by_status("locked"),
                )
                logger.info(
                    "[FLOW_ENGINE] Step %d pool: drained=%s peak_concurrency=%d "
                    "nodes=%d spawned=%d",
                    step_index + 1, result.drained, result.peak_concurrency,
                    result.cycles_worked, result.workers_spawned,
                )
                for err in result.errors:
                    logger.error("[FLOW_ENGINE] Worker error: %s", err)

                if result.stopped:
                    return "cancelled"
                if result.timed_out:
                    return "timeout"
                if result.stalled:
                    # Checked before the HITL gate: a stall means a claimed node
                    # never ran, so there is no artifact for the next step to
                    # consume. Continuing would propagate a hole.
                    logger.critical(
                        "[FLOW_ENGINE] Step %d STALLED: %d task(s) left locked with "
                        "no worker alive. Those nodes did not execute; refusing to "
                        "report the step complete.",
                        step_index + 1, result.orphaned_locks,
                    )
                    return "stalled"

                still_paused = count_by_status("paused")
                if still_paused > 0:
                    # ── HITL Pause Gate ────────────────────────────────────────
                    # Everything is finished except paused task(s) — surface to the
                    # TUI for operator input, then block until it resumes us.
                    logger.info("[FLOW_ENGINE] HITL pause detected — awaiting user input.")
                    if hitl_callback is not None:
                        try:
                            hitl_callback(step_index, job_id, current_payload)
                        except Exception:  # noqa: BLE001
                            pass
                    if not self._wait_for_hitl_resume(pause_event, cancel_event, deadline):
                        if cancel_event is not None and cancel_event.is_set():
                            return "cancelled"
                        return "timeout"
                    # The paused task should now be 'open' again — go round.
                    continue

                if result.aborted:
                    logger.error(
                        "[FLOW_ENGINE] Step %d abandoned: worker error budget exhausted.",
                        step_index + 1,
                    )
                    return "timeout"

                return "completed"

    @staticmethod
    def _wait_for_hitl_resume(
        pause_event: threading.Event | None,
        cancel_event: threading.Event | None,
        deadline: float,
    ) -> bool:
        """Block until the TUI signals that HITL input has been injected.

        .. note::
           **Known ownership inversion, preserved deliberately.**

           ``pause_event`` is created and owned by the TUI (``nexus_plex``); the
           flow engine only receives it. Under
           ``orchestration_oracle_principles.md`` that makes the engine an
           observer, which may not call ``.clear()``. It does so here.

           This is pre-existing baseline behaviour and it is load-bearing: the
           TUI's contract is "pause_event set == running", and the engine clears
           it to park itself until the TUI re-sets it after writing
           ``HITL_injection.md``. Removing the ``clear()`` without moving it into
           the TUI's ``hitl_callback`` would make the engine spin straight past
           the gate and resume the flow with no operator input — exactly the class
           of silent skip that caused the Phase 6.12 rollback.

           The correct fix is for the owner to clear its own event inside
           ``hitl_callback``. That is a TUI change, tracked for Phase 6.12C, and
           deliberately not bundled into this refactor.

        Returns:
            True when resumed, False if cancelled or the deadline passed.
        """
        if pause_event is None:
            # No pause channel: nothing can resume us, so do not spin.
            return False
        pause_event.clear()
        while True:
            if cancel_event is not None and cancel_event.is_set():
                return False
            if time.time() > deadline:
                return False
            # Bounded wait so cancellation and the deadline stay observable.
            if pause_event.wait(timeout=0.25):
                return True

    def resume_flow(
        self,
        job_id: str,
        cancel_event: threading.Event | None = None,
        pause_event: threading.Event | None = None,
        step_callback: Callable[[int, str], None] | None = None,
        hitl_callback: Callable[[int, str, str], None] | None = None,
        job_started_callback: Callable[[str], None] | None = None,
        node_started_callback: Callable[[int, str], None] | None = None,
        node_active_callback: Callable[[int | None, str, int | None], None] | None = None,
        node_finished_callback: Callable[[int | None, str, int | None], None] | None = None,
    ) -> str:
        """Resume a failed or paused flow from its last known step.

        ``node_active_callback`` / ``node_finished_callback`` fire per **node**
        with ``(step_index, node_id, slot)``, unlike ``node_started_callback``
        which fires per **step**. Under concurrency several nodes are live at once,
        so a per-step signal can no longer describe what is running.
        """
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
        is_stalled = False
        
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
                
                # 1. Load MacroNode — review nodes included, via the registry-driven
                # control-node auto-wrap (no name special-casing here).
                try:
                    macro_def = self._get_macronode(step.macronode_name, step_config=getattr(step, "config", {}))
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
                    step_output = self._capture_step_output(job_id, topo_rows, idx, broker)
                    if step_output:
                        current_payload = step_output
                    else:
                        # This path is the glob's worst case and the reason it had
                        # to go: nothing was written during this invocation, so
                        # "newest .md in the job directory" could easily belong to
                        # another step entirely. The queue still knows.
                        logger.warning(
                            "[FLOW_ENGINE] Step %d was already complete but records "
                            "no terminal output; carrying the previous payload "
                            "forward unchanged: %s",
                            idx + 1, current_payload,
                        )
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
                
                # Execute this step's DAG on the worker pool. Same helper as
                # execute_flow, so the resume path can no longer drift from it.
                pool_status = self._run_worker_pool(
                    job_id=job_id,
                    step_index=idx,
                    broker=broker,
                    topo_rows=topo_rows,
                    step_config=getattr(step, "config", {}) or {},
                    current_payload=current_payload,
                    pause_event=pause_event,
                    cancel_event=cancel_event,
                    hitl_callback=hitl_callback,
                    node_active_callback=node_active_callback,
                    node_finished_callback=node_finished_callback,
                )
                if pool_status == "cancelled":
                    is_cancelled = True
                    break
                if pool_status == "stalled":
                    is_stalled = True
                    break

                step_output = self._capture_step_output(job_id, topo_rows, idx, broker)
                if step_output:
                    current_payload = step_output
                else:
                    # _capture_step_output has already logged why. Say what the
                    # consequence is, because a resumed flow silently reusing the
                    # previous step's payload is exactly the kind of quiet wrongness
                    # that took three live runs to find last time.
                    logger.warning(
                        "[FLOW_ENGINE] Step %d output not captured on resume; the "
                        "next step will read the unchanged payload %s",
                        idx + 1, current_payload,
                    )

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
            elif is_stalled:
                broker.update_session_status(job_id, "failed")
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
        node_active_callback: Callable[[int | None, str, int | None], None] | None = None,
        node_finished_callback: Callable[[int | None, str, int | None], None] | None = None,
    ) -> str:
        """
        Execute a sequential linear flow of MacroNodes.

        Steps run in order, but the nodes **within** a step run concurrently on a
        :class:`DynamicSwarmPool` sized to the work available — one thread for a
        linear step, up to the slotted agent count for a scatter.

        Args:
            steps: List of FlowStep objects.
            initial_payload_path: Starting context.
            cancel_event: Optional threading.Event — checked between nodes for graceful cancellation.
            pause_event: Optional threading.Event — when cleared, blocks worker loop (VCR pause).
                         Must be set (unblocked) to allow execution.
            step_callback: Optional callable(step_index: int, output_path: str) — called after each step.
            hitl_callback: Optional callable(step_index: int, job_id: str, payload: str) — called on HITL pause.
            node_started_callback: Optional callable(step_index: int, macronode_name: str) —
                fires once per **step**. Retained for compatibility.
            node_active_callback: Optional callable(step_index, node_id, slot) — fires
                once per **node** as it starts. Several nodes are live at once during
                a scatter, which a per-step signal cannot express.
            node_finished_callback: Optional callable(step_index, node_id, slot) — fires
                as each node ends, on every path including failure.

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
        is_stalled = False
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
            
                # 1. Load the MacroNode — review nodes included, via the
                # registry-driven control-node auto-wrap (no name special-casing here).
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

                # 5. Execute this step's DAG on the worker pool.
                # Concurrency lives entirely inside _run_worker_pool: a linear step
                # runs on one thread, a scatter step scales to its slotted agent
                # count and back down. The step config overlay and the HITL pause
                # gate are handled there too, shared with resume_flow.
                pool_status = self._run_worker_pool(
                    job_id=job_id,
                    step_index=idx,
                    broker=broker,
                    topo_rows=topo_rows,
                    step_config=getattr(step, "config", {}) or {},
                    current_payload=current_payload,
                    pause_event=pause_event,
                    cancel_event=cancel_event,
                    hitl_callback=hitl_callback,
                    node_active_callback=node_active_callback,
                    node_finished_callback=node_finished_callback,
                )
                if pool_status == "cancelled":
                    is_cancelled = True
                    break
                if pool_status == "stalled":
                    # A node was claimed and never ran, so this step produced no
                    # artifact for the next one. Stop rather than feed the rest of
                    # the flow a hole — and record the session as failed, which is
                    # what the old code could not do because it never found out.
                    is_stalled = True
                    break

                logger.info(f"[FLOW_ENGINE] MacroNode '{step.macronode_name}' completed execution.")
            
                # 6. Capture output to pass to next step.
                # Read from the step's terminal node in the queue, not from whichever
                # file in the job directory happens to have the newest mtime. See
                # _capture_step_output for what that cost (defect E2).
                step_output = self._capture_step_output(job_id, topo_rows, idx, broker)
                if step_output:
                    current_payload = step_output
                    logger.info(f"[FLOW_ENGINE] Output captured: {current_payload}")
                else:
                    logger.warning(
                        "[FLOW_ENGINE] Step %d ('%s') recorded no terminal output; "
                        "the next step will read the unchanged payload %s",
                        idx + 1, step.macronode_name, current_payload,
                    )

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
            elif is_stalled:
                broker.update_session_status(job_id, "failed")
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
                    _reader = csv.reader(f)
                    # Skip the header row. Without this, the literal column name
                    # "Agent_Name" was collected as an agent and snapshotted as
                    # {"Agent_Name": null} — visible in the verified Aug 29
                    # baseline's as_wrapped_topology.json.
                    next(_reader, None)
                    for row in _reader:
                        if len(row) > 1 and row[1].strip():
                            used_agents.add(row[1].strip())
                            
                for step in steps:
                    m_name = step.macronode_name
                    if m_name not in as_wrapped["macronodes"]:
                        try:
                            as_wrapped["macronodes"][m_name] = macronode_store.load(m_name)
                        except Exception:
                            as_wrapped["macronodes"][m_name] = None
                            
                # Control nodes and the SYSTEM pseudo-agent are not roster agents.
                # This replaced a hand-maintained set of 16 node names that had
                # already fallen behind the registry — it was missing CTRL_SCATTER,
                # CTRL_MERGE, CTRL_CONCAT, CTRL_BRANCH, CTRL_FILTER, CTRL_CLEANUP,
                # CTRL_CONDITIONAL_ROUTE, CTRL_END and CTRL_PAYLOAD_INJECT, so any
                # of those appearing in the Agent_Name column would be looked up as
                # an agent and snapshotted as null.
                for a_name in used_agents:
                    if a_name.upper() == "SYSTEM" or is_deterministic_node(a_name):
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
    # Atomic: this file is read back as an agent payload during recursion.
    with file_lock(output_path):
        atomic_write_text(output_path, unified_text)
    return str(output_path)

def unified_ledger_path(job_id: str) -> Path:
    """Resolve the unified session ledger path for *job_id*.

    Split out so the concurrency wrapper can derive the lock key without running
    the (expensive) assembly first.
    """
    if job_id.startswith("studio_session_"):
        clean_id = job_id.replace("studio_session_", "", 1)
        artifact_dir = get_datacenter_path("04_Code_Artifacts", f"ChatStudioSessions/{clean_id}-Chat")
        return artifact_dir / "unified_chat_ledger.md"
    return get_datacenter_path("04_Code_Artifacts", job_id) / "unified_session_ledger.md"


def generate_unified_ledger(job_id: str, steps: list[FlowStep] | None = None) -> str:
    """Assemble a unified session ledger from all agent turns in the flow.

    Output: ``04_Code_Artifacts/<job_id>/unified_session_ledger.md``

    **Serialised per job.** This is the single most concurrency-sensitive artifact
    in the system: ``swarm_worker`` regenerates it on every node completion and
    then hands the result straight to ``route_task`` as the *next* node's input
    payload. Two nodes finishing at once would otherwise interleave a
    read-collect-write over the same file, and a torn read there does not raise —
    it silently feeds a truncated document to the next agent.

    Serialising rather than debouncing is deliberate. A debounce would skip
    regeneration while still returning the path, so the caller would route the
    *previous* snapshot — missing the output of the node that just finished. That
    trades correctness for CPU on exactly the artifact that can least afford it.
    Under an 8-wide scatter this costs N sequential assemblies per gather; the
    write itself is atomic, so readers are never blocked by it.
    """
    with file_lock(unified_ledger_path(job_id)):
        return _generate_unified_ledger_unlocked(job_id, steps)


def _generate_unified_ledger_unlocked(job_id: str, steps: list[FlowStep] | None = None) -> str:
    """Assembly body for :func:`generate_unified_ledger`. Hold its lock first."""
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
    # Atomic swap, not truncate-and-write. The next node reads this exact path as
    # its input payload, so a reader must never observe a partial document.
    unified_text = "\n".join(parts)
    atomic_write_text(output_path, unified_text)
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

def thoughts_ledger_path(job_id: str) -> Path:
    """Resolve the unified thoughts ledger path for *job_id*."""
    return get_datacenter_path("04_Code_Artifacts", job_id) / "unified_thoughts_ledger.md"


def generate_unified_thoughts_ledger(job_id: str) -> str:
    """Assemble a unified thoughts ledger from all agent logs in the flow.

    Output: ``04_Code_Artifacts/<job_id>/unified_thoughts_ledger.md``

    Serialised per job, like :func:`generate_unified_ledger`. It reads every
    ``*_agent.log`` in the job directory, and under concurrency those files are
    being appended to by live nodes.

    Uses a **different** lock key (its own output path), so the call made from
    inside ``generate_unified_ledger`` cannot self-deadlock on a non-reentrant
    lock.
    """
    with file_lock(thoughts_ledger_path(job_id)):
        return _generate_unified_thoughts_ledger_unlocked(job_id)


def _generate_unified_thoughts_ledger_unlocked(job_id: str) -> str:
    """Assembly body for :func:`generate_unified_thoughts_ledger`."""
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
    atomic_write_text(output_path, unified_text)
    return str(output_path)
