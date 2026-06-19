"""
maccre_core/tools/macro_nodes.py
=================================
Manages reusable topology graph fragments (Macro Nodes).

Two creation paths:
  1. **Template-based** — ``fill_template()`` fills a template from the catalog
     and saves the resulting MacroNode to the registry.
  2. **Freeform** — ``save_macro_node()`` saves an ad-hoc topology directly.

Both paths write to the Sovereign SQLite Triad (macronode_registry.db).
"""
from __future__ import annotations

import json
import os
from typing import Any


def list_templates() -> str:
    """Return all available MacroNode templates with their slot descriptions and config parameters."""
    from maccre_core.orchestration.macro_factory import TEMPLATE_CATALOG  # noqa: PLC0415

    if not TEMPLATE_CATALOG:
        return "No templates available."

    sections: list[str] = ["=== MACRONODE TEMPLATE CATALOG ===\n"]
    for tpl in TEMPLATE_CATALOG.values():
        info = tpl.to_dict()
        sections.append(f"## {info['name'].upper()}")
        sections.append(f"   {info['description']}\n")

        sections.append("   SLOTS:")
        for slot in info["slots"]:
            range_str = f"{slot['min_agents']}" if slot["min_agents"] == slot["max_agents"] else f"{slot['min_agents']}–{slot['max_agents']}"
            sections.append(f"     • {slot['name']} ({range_str} agents): {slot['description']}")

        if info["config"]:
            sections.append("   CONFIG:")
            for cfg in info["config"]:
                default_str = f" [default: {cfg['default']}]" if cfg["default"] is not None else ""
                choices_str = f" choices: {cfg['choices']}" if cfg.get("choices") else ""
                sections.append(f"     • {cfg['name']} ({cfg['type']}): {cfg['description']}{default_str}{choices_str}")

        sections.append("")

    return "\n".join(sections)


def fill_template(
    template_type: str,
    name: str,
    description: str,
    agent_mapping: dict[str, list[str]],
    config: dict[str, Any] | None = None,
) -> str:
    """Fill a template with agents from the roster and save as a named MacroNode.

    Args:
        template_type: One of 'cascade', 'hologram', 'chord', 'crucible'.
        name: Name for the saved MacroNode (e.g., 'Cascade-OSINTx3').
        description: Human-readable description.
        agent_mapping: Dict mapping slot names to lists of roster agent names.
            Example: {"agents": ["OSINT_Analyst", "Regular_Joe"]}
        config: Template-specific config. Example: {"loop_count": 3, "end_agent": "Regular_Joe"}

    Returns:
        Success or failure message string.
    """
    from maccre_core.orchestration.macro_factory import TEMPLATE_CATALOG, build_from_template  # noqa: PLC0415
    from maccre_core.orchestration.roster_loader import load_agent_from_roster  # noqa: PLC0415
    from maccre_core.macronode_registry import get_macronode_store  # noqa: PLC0415

    if config is None:
        config = {}

    # Validate template exists
    if template_type not in TEMPLATE_CATALOG:
        return f"[TEMPLATE_FAULT] Unknown template: '{template_type}'. Available: {list(TEMPLATE_CATALOG)}"

    # Load all referenced agents from the roster
    all_agent_names: list[str] = []
    for agents_in_slot in agent_mapping.values():
        all_agent_names.extend(agents_in_slot)

    roster: dict[str, dict[str, Any]] = {}
    missing: list[str] = []
    for agent_name in all_agent_names:
        try:
            roster[agent_name] = load_agent_from_roster(agent_name)
        except KeyError:
            missing.append(agent_name)

    if missing:
        return f"[TEMPLATE_FAULT] Agent(s) not found in Global roster: {missing}"

    # Build topology rows from template
    try:
        topology_rows = build_from_template(template_type, agent_mapping, config, roster)
    except (KeyError, ValueError) as exc:
        return f"[TEMPLATE_FAULT] Validation failed: {exc}"

    # Save to registry
    try:
        project = os.environ.get("MACCRE_ACTIVE_PROJECT", "GLOBAL")
        store = get_macronode_store(project)

        # Collect slot agent names for the agent_slots field
        agent_slots: list[str] = []
        for agents_in_slot in agent_mapping.values():
            agent_slots.extend(agents_in_slot)

        store.save(
            name=name,
            topology_rows=topology_rows,
            description=description,
            is_template=False,  # It's a FILLED template — no longer a template itself
            agent_slots=agent_slots,
            template_type=template_type,
            template_config=config,
        )
        return (
            f"[TEMPLATE_SUCCESS] Saved MacroNode '{name}' from template '{template_type}' "
            f"with {len(topology_rows)} nodes ({len(agent_slots)} agents) to {project} registry."
        )
    except Exception as exc:  # noqa: BLE001
        return f"[TEMPLATE_FAULT] Failed to save: {exc}"


def save_macro_node(name: str, description: str, nodes: list[list[str]]) -> str:
    """Saves a freeform (non-template) topology graph fragment into the macro node registry."""
    try:
        topology_rows: list[dict[str, Any]] = []
        agent_slots: list[str] = []
        is_template = False

        for row in nodes:
            while len(row) < 8:
                row.append("none")

            node_id = row[0]
            agent_name = row[1]
            sys_inst = row[2]
            next_node = row[3]
            temp = row[4]
            out_fmt = row[5]
            dialogue_partner = row[6]
            dialogue_rounds = row[7]

            # Basic heuristic for template slotting
            if agent_name.upper().startswith("SLOT_"):
                is_template = True
                agent_slots.append(agent_name)

            topology_rows.append({
                "Node_ID": node_id,
                "Agent_Name": agent_name,
                "System_Instruction": sys_inst if sys_inst != "none" else None,
                "Next_Node": next_node,
                "Temperature": temp,
                "Output_Format": out_fmt if out_fmt != "none" else None,
                "Wait_For": None,
                "Fallback_Node": "FAILED",
                "Max_Retries": 3,
                "Payload_Path": None,
                "Is_End_Node": "TRUE" if next_node.upper() == "END" else "FALSE",
                "Timeout_Sec": 0,
                "Dialogue_Partner": dialogue_partner if dialogue_partner != "none" else None,
                "Dialogue_Rounds": int(dialogue_rounds) if dialogue_rounds != "none" else 0,
            })

        # Nexus usually targets the active project
        from maccre_core.macronode_registry import get_macronode_store  # noqa: PLC0415
        project = os.environ.get("MACCRE_ACTIVE_PROJECT", "GLOBAL")
        store = get_macronode_store(project)
        store.save(
            name=name,
            topology_rows=topology_rows,
            description=description,
            is_template=is_template,
            agent_slots=agent_slots,
        )
        return f"[ADMIN_SUCCESS] Saved Macro Node '{name}' with {len(nodes)} nodes to {project} registry."
    except Exception as e:  # noqa: BLE001
        return f"[ADMIN_FAULT] Failed to save Macro Node: {e}"


def list_macro_nodes() -> str:
    """Returns a list of all saved Macro Nodes in the active project registry."""
    try:
        from maccre_core.macronode_registry import get_macronode_store  # noqa: PLC0415
        project = os.environ.get("MACCRE_ACTIVE_PROJECT", "GLOBAL")
        store = get_macronode_store(project)
        items = store.list_all()

        if not items:
            return f"No Macro Nodes currently saved in {project}."

        output = f"Available Macro Nodes in {project}:\n"
        for item in items:
            tpl_tag = f" [from: {item['template_type']}]" if item.get("template_type") else ""
            output += f"- {item['name']}: {item['description']}{tpl_tag}\n"
        return output
    except Exception as e:  # noqa: BLE001
        return f"[ADMIN_FAULT] Failed to list Macro Nodes: {e}"


def fetch_macro_node(name: str) -> str:
    """Returns the JSON string representation of a specific Macro Node's wiring."""
    try:
        from maccre_core.macronode_registry import get_macronode_store  # noqa: PLC0415
        project = os.environ.get("MACCRE_ACTIVE_PROJECT", "GLOBAL")
        store = get_macronode_store(project)
        node = store.load(name)

        simplified: list[list[str]] = []
        for row in node["topology_rows"]:
            simplified.append([
                row.get("Node_ID", ""),
                row.get("Agent_Name", ""),
                row.get("System_Instruction", "none") or "none",
                row.get("Next_Node", ""),
                str(row.get("Temperature", "0.7")),
                row.get("Output_Format", "none") or "none",
            ])
        return json.dumps(simplified)
    except KeyError:
        return f"[ADMIN_FAULT] Macro Node '{name}' not found."
    except Exception as e:  # noqa: BLE001
        return f"[ADMIN_FAULT] Failed to fetch Macro Node: {e}"
