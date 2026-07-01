# ┌─────────────────────────────────────────────────────────────────────────────┐
# │  MACCREv2 ENGINEERING DOCTRINE                             Law Rev: 19.0   │
# ├─────────────────────────────────────────────────────────────────────────────┤
# │  I.   TYPING      All signatures: explicit Python 3.11+ type hints.        │
# │  II.  LINTING     Zero unused imports. No wildcards. 120-char line max.    │
# │  III. PATHS       Never hardcode absolute paths. Use get_maccre_root().     │
# │  VI.  ABSTRACTION All I/O behind abc.ABC before any concrete driver.       │
# │  VII. TEARDOWN    try/finally on all handles (omni clean compliance).      │
# └─────────────────────────────────────────────────────────────────────────────┘
"""
maccre_core/orchestration/macro_factory.py
============================================
MacroNode Template Catalog — parameterised topology patterns.

Each template defines a reusable multi-agent topology pattern with:
  - **Slots** — named agent positions (filled from the Global roster)
  - **Config** — loop count, end-agent, topology variation, etc.
  - **Builder** — function that takes filled slots + config → topology rows

Templates are listed by Nexus via ``list_templates()`` and filled via
``fill_template()`` which saves the resulting MacroNode to the registry.

Legacy ``expand_macro()`` is retained for backward-compatible MACRO: prefix
interception in topology.csv.
"""
from __future__ import annotations

import logging

import uuid
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════════════
# Template Data Model
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class SlotSpec:
    """Definition of an agent slot within a template."""

    name: str                    # e.g. "agents", "synthesizer", "judge"
    description: str             # Human-readable description for Nexus
    min_agents: int = 1          # Minimum agents that must fill this slot
    max_agents: int = 1          # Maximum agents allowed in this slot


@dataclass
class ConfigSpec:
    """Definition of a configurable parameter within a template."""

    name: str                    # e.g. "loop_count", "end_agent", "variation"
    param_type: str              # "int", "str", "choice"
    description: str             # Human-readable description for Nexus
    default: Any = None          # Default value if not specified
    choices: list[str] = field(default_factory=list)  # Valid choices for "choice" type
    min_val: int | None = None   # Minimum value for "int" type
    max_val: int | None = None   # Maximum value for "int" type


@dataclass
class TemplateDefinition:
    """A MacroNode template — topology pattern with parameterised slots and config."""

    name: str                               # e.g. "cascade", "hologram", "chord", "crucible"
    description: str                        # Human-readable description
    slots: list[SlotSpec] = field(default_factory=list)
    config: list[ConfigSpec] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Serialise for Nexus display (no builder function)."""
        return {
            "name": self.name,
            "description": self.description,
            "slots": [
                {
                    "name": s.name,
                    "description": s.description,
                    "min_agents": s.min_agents,
                    "max_agents": s.max_agents,
                }
                for s in self.slots
            ],
            "config": [
                {
                    "name": c.name,
                    "type": c.param_type,
                    "description": c.description,
                    "default": c.default,
                    "choices": c.choices if c.choices else None,
                    "min": c.min_val,
                    "max": c.max_val,
                }
                for c in self.config
            ],
        }


# ═══════════════════════════════════════════════════════════════════════════════
# Silent Instruction Augments
# ═══════════════════════════════════════════════════════════════════════════════

_CASCADE_SEARCH_AUGMENT = """
[CASCADE DUAL-INDEX SEARCH PROTOCOL]
You have access to a specialized web search tool. For EVERY research turn you MUST:
1. Call `cascade_search` with your research query and explicitly set `num_passes={exclusionary_search}`.
   This tells the tool to perform a primary web search followed by exclusionary searches 
   that omit all domains found in previous passes, giving you completely unique, non-overlapping source sets.
2. Combine ALL result sets into your report. Cite and tag every source.
Do NOT skip the cascade search. The dual-index protocol is your primary research method.
"""

_HOLOGRAM_SYNTHESIS_AUGMENT = """
[HOLOGRAM SYNTHESIS PROTOCOL]
You are the central synthesizer {host}. You will receive independent analysis from 
the following facet agents: {agents}.
Synthesize their disparate views into a cohesive, singular output.
"""

_CHORD_RECURSION_AUGMENT = """
[CHORD RECURSION PROTOCOL]
You are the central host {host}. The following participant agents have responded: {agents}.
Synthesize their inputs and send a refined prompt back to them for the next round.
Maximum rounds remaining: {max_recursion}.
"""

_CRUCIBLE_JUDGE_AUGMENT = """
[CRUCIBLE ROUTING PROTOCOL]
After reviewing all Advocate submissions, you MUST evaluate each one against your
professional standards and criteria as defined in your role.

ROUTING COMMANDS (you MUST output exactly one per evaluation):
- If an Advocate's submission does NOT meet your standards, output on its own line:
ROUTE_TO:Agent_Name — followed by your detailed critique and revision directives.
- If ALL submissions meet your standards, output on its own line:
  ROUTE_TO:ACCEPTED — followed by your synthesis or approval statement.

Valid Agent Names to route back to are:
{node_ids}

You may route to ONE Advocate at a time, or MULTIPLE Advocates concurrently by separating their names with commas (e.g. ROUTE_TO:Agent_A,Agent_B).
Address the weakest submissions first.
Maximum revision rounds remaining: {max_recursion}.

***CRITICAL FINAL INSTRUCTION***
Because you are an automated judge inside a CI/CD pipeline, you MUST end your evaluation by explicitly outputting the ROUTE_TO: command on its own line at the very bottom of your response. If you just write a memo and forget the ROUTE_TO tag, the pipeline will break!
"""


# ═══════════════════════════════════════════════════════════════════════════════
# Template Definitions
# ═══════════════════════════════════════════════════════════════════════════════

TEMPLATE_CASCADE = TemplateDefinition(
    name="cascade",
    description=(
        "Exclusionary dual-index research conversation. Agents take turns in a "
        "GroupDialogRunner loop. The first agent in the sequence uses cascade_search "
        "for dual-index web research (two non-overlapping result sets per turn). "
        "Configurable loop count, agent ordering, and end-agent."
    ),
    slots=[
        SlotSpec(
            name="agents",
            description="Research and conversation agents (order matters — first agent gets search augment)",
            min_agents=2,
            max_agents=3,
        ),
    ],
    config=[
        ConfigSpec(
            name="loop_count", param_type="int",
            description="Number of full conversation cycles",
            default=3, min_val=1, max_val=20,
        ),
        ConfigSpec(
            name="end_agent", param_type="str",
            description="Agent name that provides the final output (must be one of the agents)",
        ),
        ConfigSpec(
            name="agent_order", param_type="str",
            description="Pipe-separated agent ordering (e.g. 'OSINT_Analyst|Regular_Joe')",
        ),
        ConfigSpec(
            name="exclusionary_search", param_type="int",
            description="Number of total search passes (1 primary + N exclusionary)",
            default=2, min_val=1, max_val=5,
        ),
        ConfigSpec(
            name="structural_augment", param_type="str",
            description="Agent directive injected into the first agent's system prompt",
            default=_CASCADE_SEARCH_AUGMENT.strip(),
        ),
    ],
)

TEMPLATE_HOLOGRAM = TemplateDefinition(
    name="hologram",
    description=(
        "Fan-out + synthesize (one-shot). Payload is sent to N facet agents in parallel. "
        "All responses are gathered and passed to a single low-temperature synthesizer. "
        "Each facet agent represents one discipline of a compound intellect."
    ),
    slots=[
        SlotSpec(
            name="facets",
            description="Discipline facet agents (each sees the payload independently)",
            min_agents=2,
            max_agents=10,
        ),
        SlotSpec(
            name="synthesizer",
            description="Low-temperature synthesizer agent that combines all facet responses",
            min_agents=1,
            max_agents=1,
        ),
    ],
    config=[
        ConfigSpec(
            name="structural_augment", param_type="str",
            description="Synthesizer directive injected into the host's system prompt",
            default=_HOLOGRAM_SYNTHESIS_AUGMENT.strip(),
        ),
    ],
)

TEMPLATE_CHORD = TemplateDefinition(
    name="chord",
    description=(
        "Fan-out + synthesize with recursion. N participant agents respond to a central "
        "host. The host synthesizes and sends a report back to all participants. "
        "Participants cannot see each other's responses — only the host's synthesis. "
        "This loops for a configurable number of rounds."
    ),
    slots=[
        SlotSpec(
            name="participants",
            description="Fan-out participant agents (cannot see each other, only the host)",
            min_agents=2,
            max_agents=10,
        ),
        SlotSpec(
            name="host",
            description="Central host/synthesizer agent that sees all participant responses",
            min_agents=1,
            max_agents=1,
        ),
    ],
    config=[
        ConfigSpec(
            name="loop_count", param_type="int",
            description="Number of host→participants→host cycles",
            default=3, min_val=1, max_val=20,
        ),
        ConfigSpec(
            name="structural_augment", param_type="str",
            description="Recursion directive injected into the host's system prompt",
            default=_CHORD_RECURSION_AUGMENT.strip(),
        ),
    ],
)

TEMPLATE_CRUCIBLE = TemplateDefinition(
    name="crucible",
    description=(
        "Adversarial/refinement GAN with conditional routing. Multiple advocate agents "
        "build arguments or drafts independently. A judge agent evaluates submissions "
        "and conditionally routes failures back for revision (the GAN loop). After "
        "acceptance, a configurable post-acceptance phase runs: 'synthesis' (judge "
        "synthesizes), 'debate' (GroupDialogRunner between advocates), or 'panel' "
        "(full round-table discussion). True conditional logic — the judge's own "
        "instructions define the quality criteria."
    ),
    slots=[
        SlotSpec(
            name="advocates",
            description="Agents that build arguments/drafts (each works independently)",
            min_agents=2,
            max_agents=10,
        ),
        SlotSpec(
            name="judge",
            description="Evaluative agent with quality criteria in its instructions (routes failures back)",
            min_agents=1,
            max_agents=1,
        ),
    ],
    config=[
        ConfigSpec(
            name="max_recursion", param_type="int",
            description="Maximum times the judge can send advocates back for revision",
            default=3, min_val=1, max_val=10,
        ),
        ConfigSpec(
            name="variation", param_type="choice",
            description="Post-acceptance topology mode",
            default="synthesis",
            choices=["synthesis", "synthesis-blind", "debate", "panel"],
        ),
        ConfigSpec(
            name="structural_augment", param_type="str",
            description="Judge evaluation protocol/augment injected into system prompt",
            default=_CRUCIBLE_JUDGE_AUGMENT.strip(),
        ),
    ],
)

# Master catalog — keyed by template name
TEMPLATE_CATALOG: dict[str, TemplateDefinition] = {
    "cascade": TEMPLATE_CASCADE,
    "hologram": TEMPLATE_HOLOGRAM,
    "chord": TEMPLATE_CHORD,
    "crucible": TEMPLATE_CRUCIBLE,
}


# ═══════════════════════════════════════════════════════════════════════════════
# Topology Builders — generate topology rows from filled template config
# ═══════════════════════════════════════════════════════════════════════════════


def _build_cascade_topology(
    agent_mapping: dict[str, list[str]],
    config: dict[str, Any],
    roster: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    """Build Cascade topology rows.

    Generates a single GroupDialogRunner node where the host is the first agent
    in the sequence and the remaining agents are dialogue partners.
    """
    agents = agent_mapping["agents"]
    order_str: str = config.get("agent_order", "")
    if order_str:
        ordered = [a.strip() for a in order_str.split("|") if a.strip()]
    else:
        ordered = list(agents)

    loop_count: int = int(config.get("loop_count", 3))
    end_agent: str = config.get("end_agent", ordered[-1])

    host_name = ordered[0]
    partners = ordered[1:]
    host_profile = roster[host_name]

    macro_id = str(uuid.uuid4())[:8]
    node_id = f"CASCADE_{macro_id}"

    # The host gets the search augment injected into its system prompt
    host_system = str(host_profile.get("system_prompt", ""))
    
    augment_template = config.get("structural_augment")
    if not augment_template:
        augment_template = _CASCADE_SEARCH_AUGMENT
        
    augmented_system = host_system + "\n" + augment_template.replace(
        "{macro_id}", macro_id
    ).replace(
        "{agents}", ", ".join(ordered)
    ).replace(
        "{host}", host_name
    ).replace(
        "{exclusionary_search}", str(config.get("exclusionary_search", 2))
    )

    # Build the tools string: host gets cascade_search + whatever it already has
    host_tools = str(host_profile.get("tools_allowed", "none"))
    if host_tools.lower() == "none":
        host_tools = "cascade_search"
    elif "cascade_search" not in host_tools:
        host_tools = f"{host_tools}|cascade_search"

    # Determine dialogue_rounds based on end_agent:
    # If end_agent is the host, we need loop_count rounds (host speaks last).
    # If end_agent is a partner, we need loop_count rounds but the final output
    # is extracted from the last participant turn (handled by FlowRunner).
    dialogue_rounds = loop_count

    return [{
        "Node_ID": node_id,
        "Agent_Name": host_name,
        "System_Instruction": augmented_system,
        "Next_Node": "END",
        "Temperature": str(host_profile.get("temperature", "1.0")),
        "Output_Format": None,
        "Wait_For": None,
        "Fallback_Node": "FAILED",
        "Max_Retries": 3,
        "Payload_Path": None,
        "Is_End_Node": "TRUE",
        "Timeout_Sec": 0,
        "Dialogue_Partner": "|".join(partners),
        "Dialogue_Rounds": dialogue_rounds,
        "Model_Override": str(host_profile.get("model", "gemini-2.5-flash")),
        "Tools_Allowed": host_tools,
        "_end_agent": end_agent,
        "_template_meta": {"type": "cascade", "ordered_agents": ordered},
    }]


def _build_hologram_topology(
    agent_mapping: dict[str, list[str]],
    config: dict[str, Any],
    roster: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    """Build Hologram topology rows.

    Generates N parallel facet nodes that all point to a single synthesizer node.
    """
    facets = agent_mapping["facets"]
    synthesizer_name = agent_mapping["synthesizer"][0]
    synth_profile = roster[synthesizer_name]

    macro_id = str(uuid.uuid4())[:8]
    synth_id = f"HOLO_SYNTH_{macro_id}"

    rows: list[dict[str, Any]] = []
    facet_ids: list[str] = []

    for facet_name in facets:
        f_profile = roster[facet_name]
        f_id = f"HOLO_{facet_name.upper()[:12]}_{macro_id}"
        facet_ids.append(f_id)

        rows.append({
            "Node_ID": f_id,
            "Agent_Name": facet_name,
            "System_Instruction": str(f_profile.get("system_prompt", "")),
            "Next_Node": synth_id,
            "Temperature": str(f_profile.get("temperature", "0.7")),
            "Output_Format": None,
            "Wait_For": None,
            "Fallback_Node": "FAILED",
            "Max_Retries": 3,
            "Payload_Path": None,
            "Is_End_Node": "FALSE",
            "Timeout_Sec": 0,
            "Dialogue_Partner": None,
            "Dialogue_Rounds": 0,
            "Model_Override": str(f_profile.get("model", "gemini-2.5-flash")),
            "Tools_Allowed": str(f_profile.get("tools_allowed", "none")),
        })

    # Synthesizer waits for all facets
    augment_template = config.get("structural_augment")
    if not augment_template:
        augment_template = _HOLOGRAM_SYNTHESIS_AUGMENT
        
    synth_system = str(synth_profile.get("system_prompt", ""))
    synth_system += "\n\n" + augment_template.replace(
        "{macro_id}", macro_id
    ).replace(
        "{agents}", ", ".join(facets)
    ).replace(
        "{host}", synthesizer_name
    )
    
    rows.append({
        "Node_ID": synth_id,
        "Agent_Name": synthesizer_name,
        "System_Instruction": synth_system,
        "Next_Node": "END",
        "Temperature": "0.3",  # Low temp for synthesis
        "Output_Format": None,
        "Wait_For": ",".join(facet_ids),
        "Fallback_Node": "FAILED",
        "Max_Retries": 3,
        "Payload_Path": None,
        "Is_End_Node": "TRUE",
        "Timeout_Sec": 0,
        "Dialogue_Partner": None,
        "Dialogue_Rounds": 0,
        "Model_Override": str(synth_profile.get("model", "gemini-2.5-pro")),
        "Tools_Allowed": str(synth_profile.get("tools_allowed", "none")),
    })

    return rows


def _build_chord_topology(
    agent_mapping: dict[str, list[str]],
    config: dict[str, Any],
    roster: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    """Build Chord topology rows.

    Generates a single GroupDialogRunner node where the host is the central
    synthesiser and participants are the fan-out agents. Participants cannot
    see each other — only the host's synthesis.
    """
    participants = agent_mapping["participants"]
    host_name = agent_mapping["host"][0]
    host_profile = roster[host_name]
    loop_count: int = int(config.get("loop_count", 3))

    macro_id = str(uuid.uuid4())[:8]
    node_id = f"CHORD_{macro_id}"
    
    augment_template = config.get("structural_augment")
    if not augment_template:
        augment_template = _CHORD_RECURSION_AUGMENT
        
    host_system = str(host_profile.get("system_prompt", ""))
    host_system += "\n\n" + augment_template.replace(
        "{macro_id}", macro_id
    ).replace(
        "{agents}", ", ".join(participants)
    ).replace(
        "{host}", host_name
    ).replace(
        "{max_recursion}", str(loop_count)
    )

    return [{
        "Node_ID": node_id,
        "Agent_Name": host_name,
        "System_Instruction": host_system,
        "Next_Node": "END",
        "Temperature": str(host_profile.get("temperature", "0.7")),
        "Output_Format": None,
        "Wait_For": None,
        "Fallback_Node": "FAILED",
        "Max_Retries": 3,
        "Payload_Path": None,
        "Is_End_Node": "TRUE",
        "Timeout_Sec": 0,
        "Dialogue_Partner": "|".join(participants),
        "Dialogue_Rounds": loop_count,
        "Model_Override": str(host_profile.get("model", "gemini-2.5-flash")),
        "Tools_Allowed": str(host_profile.get("tools_allowed", "none")),
        "_template_meta": {"type": "chord", "participants": participants},
    }]


def _build_crucible_topology(
    agent_mapping: dict[str, list[str]],
    config: dict[str, Any],
    roster: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    """Build Crucible topology rows.

    Pre-acceptance: N parallel advocate nodes → 1 judge node with conditional routing.
    Post-acceptance: varies by ``config["variation"]``.
    """
    advocates = agent_mapping["advocates"]
    judge_name = agent_mapping["judge"][0]
    judge_profile = roster[judge_name]

    max_recursion: int = int(config.get("max_recursion", 3))
    variation: str = str(config.get("variation", "synthesis"))

    macro_id = str(uuid.uuid4())[:8]
    judge_id = f"C_JUDGE_{macro_id}"

    rows: list[dict[str, Any]] = []
    advocate_ids: list[str] = []

    # ── Advocate nodes (parallel fan-out) ─────────────────────────────────────
    for adv_name in advocates:
        a_profile = roster[adv_name]
        a_id = f"C_ADV_{adv_name.upper()[:12]}_{macro_id}"
        advocate_ids.append(a_id)

        rows.append({
            "Node_ID": a_id,
            "Agent_Name": adv_name,
            "System_Instruction": str(a_profile.get("system_prompt", "")),
            "Next_Node": judge_id,
            "Temperature": str(a_profile.get("temperature", "1.0")),
            "Output_Format": None,
            "Wait_For": None,
            "Fallback_Node": "FAILED",
            "Max_Retries": max_recursion,
            "Payload_Path": None,
            "Payload_Mode": "Targeted Filter" if variation == "synthesis-blind" else "Unified Ledger",
            "Is_End_Node": "FALSE",
            "Timeout_Sec": 0,
            "Dialogue_Partner": None,
            "Dialogue_Rounds": 0,
            "Model_Override": str(a_profile.get("model", "gemini-2.5-flash")),
            "Tools_Allowed": str(a_profile.get("tools_allowed", "none")),
        })

    # ── Build node-id map for the routing augment ─────────────────────────────
    adv_id_map = "\n".join(f"- {advocates[i]}" for i in range(len(advocate_ids)))
    
    augment_template = config.get("structural_augment")
    if not augment_template:
        augment_template = _CRUCIBLE_JUDGE_AUGMENT
        
    judge_augment = augment_template.format(
        node_ids=adv_id_map,
        max_recursion=max_recursion,
    )
    judge_system = str(judge_profile.get("system_prompt", "")) + "\n" + judge_augment

    # ── Post-acceptance target ────────────────────────────────────────────────
    if variation == "debate":
        post_id = f"C_DEBATE_{macro_id}"
    elif variation == "panel":
        post_id = f"C_PANEL_{macro_id}"
    else:
        # synthesis — judge IS the final node
        post_id = "END"

    # ── Judge node (conditional gate) ─────────────────────────────────────────
    rows.append({
        "Node_ID": judge_id,
        "Agent_Name": judge_name,
        "System_Instruction": judge_system,
        "Next_Node": post_id,
        "Temperature": "0.2",  # Low temp for evaluation
        "Output_Format": None,
        "Wait_For": ",".join(advocate_ids),
        "Fallback_Node": "FAILED",
        "Max_Retries": max_recursion,
        "Payload_Path": None,
        "Is_End_Node": "TRUE" if post_id == "END" else "FALSE",
        "Timeout_Sec": 0,
        "Dialogue_Partner": None,
        "Dialogue_Rounds": 0,
        "Model_Override": str(judge_profile.get("model", "gemini-2.5-pro")),
        "Tools_Allowed": str(judge_profile.get("tools_allowed", "none")),
        "_conditional_routing": True,
        "_advocate_ids": advocate_ids,
    })

    # ── Post-acceptance variations ────────────────────────────────────────────
    if variation == "debate":
        # Host (judge) facilitates a GroupDialogRunner between advocates
        rows.append({
            "Node_ID": post_id,
            "Agent_Name": judge_name,
            "System_Instruction": (
                str(judge_profile.get("system_prompt", ""))
                + "\n\n[POST-ACCEPTANCE DEBATE] All submissions have been accepted. "
                "Now facilitate a structured debate. Pose challenging questions and "
                "drive the discussion toward a final synthesis."
            ),
            "Next_Node": "END",
            "Temperature": "0.5",
            "Output_Format": None,
            "Wait_For": judge_id,
            "Fallback_Node": "FAILED",
            "Max_Retries": 3,
            "Payload_Path": None,
            "Is_End_Node": "TRUE",
            "Timeout_Sec": 0,
            "Dialogue_Partner": "|".join(advocates),
            "Dialogue_Rounds": 2,
            "Model_Override": str(judge_profile.get("model", "gemini-2.5-pro")),
            "Tools_Allowed": str(judge_profile.get("tools_allowed", "none")),
        })
    elif variation == "panel":
        # All advocates + judge do a GroupDialogRunner round-table
        all_panel = list(advocates)
        rows.append({
            "Node_ID": post_id,
            "Agent_Name": judge_name,
            "System_Instruction": (
                str(judge_profile.get("system_prompt", ""))
                + "\n\n[PANEL ROUND-TABLE] All submissions have been accepted. "
                "Facilitate a collaborative round-table discussion with all "
                "advocates. Drive toward a unified final synthesis."
            ),
            "Next_Node": "END",
            "Temperature": "0.5",
            "Output_Format": None,
            "Wait_For": judge_id,
            "Fallback_Node": "FAILED",
            "Max_Retries": 3,
            "Payload_Path": None,
            "Is_End_Node": "TRUE",
            "Timeout_Sec": 0,
            "Dialogue_Partner": "|".join(all_panel),
            "Dialogue_Rounds": 2,
            "Model_Override": str(judge_profile.get("model", "gemini-2.5-pro")),
            "Tools_Allowed": str(judge_profile.get("tools_allowed", "none")),
        })

    return rows


# ── Builder dispatch ──────────────────────────────────────────────────────────

_BUILDERS: dict[str, Any] = {
    "cascade": _build_cascade_topology,
    "hologram": _build_hologram_topology,
    "chord": _build_chord_topology,
    "crucible": _build_crucible_topology,
}


def build_from_template(
    template_type: str,
    agent_mapping: dict[str, list[str]],
    config: dict[str, Any],
    roster: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    """Build topology rows from a template.

    Args:
        template_type: One of 'cascade', 'hologram', 'chord', 'crucible'.
        agent_mapping: Dict mapping slot names to lists of roster agent names.
        config: Template-specific configuration parameters.
        roster: Dict of agent_name → agent profile dicts (from roster_loader).

    Returns:
        List of topology row dicts ready to save to the registry.

    Raises:
        KeyError: If template_type is unknown.
        ValueError: If validation fails (missing agents, bad config, etc.).
    """
    builder = _BUILDERS.get(template_type)
    if not builder:
        raise KeyError(f"Unknown template type: '{template_type}'. Available: {list(_BUILDERS)}")

    template = TEMPLATE_CATALOG[template_type]

    # ── Validate slots ────────────────────────────────────────────────────────
    for slot in template.slots:
        agents_in_slot = agent_mapping.get(slot.name, [])
        if len(agents_in_slot) < slot.min_agents:
            raise ValueError(
                f"Slot '{slot.name}' requires at least {slot.min_agents} agent(s), "
                f"got {len(agents_in_slot)}"
            )
        if len(agents_in_slot) > slot.max_agents:
            raise ValueError(
                f"Slot '{slot.name}' allows at most {slot.max_agents} agent(s), "
                f"got {len(agents_in_slot)}"
            )
        # Verify all agents exist in the roster
        for agent_name in agents_in_slot:
            if agent_name not in roster:
                raise ValueError(f"Agent '{agent_name}' not found in the Global roster.")

    # ── Validate config ───────────────────────────────────────────────────────
    for cfg in template.config:
        val = config.get(cfg.name, cfg.default)
        if val is None and cfg.default is None:
            raise ValueError(f"Config '{cfg.name}' is required for template '{template_type}'.")
        if cfg.param_type == "int" and val is not None:
            val = int(val)
            if cfg.min_val is not None and val < cfg.min_val:
                raise ValueError(f"Config '{cfg.name}' minimum is {cfg.min_val}, got {val}.")
            if cfg.max_val is not None and val > cfg.max_val:
                raise ValueError(f"Config '{cfg.name}' maximum is {cfg.max_val}, got {val}.")
        if cfg.param_type == "choice" and cfg.choices and val not in cfg.choices:
            raise ValueError(f"Config '{cfg.name}' must be one of {cfg.choices}, got '{val}'.")

    rows = builder(agent_mapping, config, roster)
    
    # ── Apply slot_tools overrides ────────────────────────────────────────────
    slot_tools = config.get("slot_tools", {})
    if slot_tools:
        agent_to_slot = {}
        for slot_name, agents in agent_mapping.items():
            for a in agents:
                agent_to_slot[a] = slot_name
                
        for row in rows:
            a_name = row.get("Agent_Name")
            if a_name:
                slot = agent_to_slot.get(a_name)
                specific_key = f"{slot}_{a_name}"
                if specific_key in slot_tools:
                    row["Tools_Allowed"] = slot_tools[specific_key]
                elif slot and slot in slot_tools:
                    row["Tools_Allowed"] = slot_tools[slot]
                    
    return rows


# ═══════════════════════════════════════════════════════════════════════════════
# Legacy expand_macro() — backward-compatible MACRO: prefix interception
# ═══════════════════════════════════════════════════════════════════════════════


def _register_ephemeral_nodes(nodes: dict[str, dict[str, Any]]) -> None:
    """Writes generated macro nodes to macronode_registry.db (ephemeral_nodes table)."""
    from maccre_core.macronode_registry import get_macronode_store  # noqa: PLC0415
    store = get_macronode_store()
    store.save_ephemeral_nodes(nodes)


def expand_macro(
    agent_name: str,
    current_node: str,
    next_node: str,
    job_id: str,
    payload_path: str,
    source_payload_path: str,
    broker: Any,
    row_id: int,
) -> None:
    """Expand a MACRO: agent into ephemeral tasks.

    First attempts to load the macro from the macronode_registry.db.
    Falls back to a clear error if the type is unknown.
    """
    from maccre_core.macronode_registry import get_macronode_store  # noqa: PLC0415

    macro_type = agent_name.split(":", 1)[1].strip()
    logger.info(f"[MACRO_FACTORY] Intercepted MACRO request: '{macro_type}'. Expanding...")

    # ── Try loading from registry ─────────────────────────────────────────────
    try:
        store = get_macronode_store("GLOBAL")
        macro = store.load(macro_type)
        topology_rows = macro.get("topology_rows", [])

        if not topology_rows:
            logger.info(f"[MACRO_FACTORY] Registry entry '{macro_type}' has no topology rows.")
            broker.route_task(row_id, job_id, "FAILED", payload_path, source_payload_path=source_payload_path)
            return

        macro_id = str(uuid.uuid4())[:8]
        ephemeral_nodes: dict[str, dict[str, Any]] = {}
        first_nodes: list[str] = []

        for row in topology_rows:
            # Rewrite Node_IDs with unique macro_id to prevent collisions
            orig_id = str(row.get("Node_ID", ""))
            new_id = f"{orig_id}_{macro_id}"
            node_next = str(row.get("Next_Node", "END"))

            # If Next_Node references another node in this macro, rewrite it too
            # If it's "END", wire to the downstream next_node
            if node_next.upper() == "END":
                resolved_next = next_node
            else:
                resolved_next = f"{node_next}_{macro_id}"

            ephemeral_nodes[new_id] = {
                "prompt": str(row.get("System_Instruction", "")),
                "artifact_path": "",
                "next_node_success": resolved_next,
                "next_node_failure": "FAILED",
                "wait_for": _rewrite_wait_for(str(row.get("Wait_For", "") or ""), macro_id),
                "temperature": float(row.get("Temperature", "0.7")),
                "tools_allowed": str(row.get("Tools_Allowed", "none")),
                "model": str(row.get("Model_Override", "gemini-2.5-flash")),
                "agent_name": str(row.get("Agent_Name", orig_id)),
                "agent": str(row.get("Agent_Name", orig_id)),
                "max_recursion": int(row.get("Max_Retries", 3)),
            }

            # Dialogue fields
            dp = row.get("Dialogue_Partner")
            if dp:
                ephemeral_nodes[new_id]["dialogue_partner"] = str(dp)
                ephemeral_nodes[new_id]["dialogue_rounds"] = int(row.get("Dialogue_Rounds", 0))

            # Track first nodes (no Wait_For dependency)
            wait = str(row.get("Wait_For", "") or "").strip()
            if not wait or wait.lower() == "none":
                first_nodes.append(new_id)

        _register_ephemeral_nodes(ephemeral_nodes)

        next_node_str = ",".join(first_nodes) if first_nodes else list(ephemeral_nodes.keys())[0]
        logger.info(f"[MACRO_FACTORY] Spawned {len(ephemeral_nodes)} ephemeral nodes from registry. Queueing: {next_node_str}")
        broker.route_task(
            row_id, job_id, next_node_str, payload_path,
            actual_cost=0.0, source_payload_path=source_payload_path,
        )
        return

    except KeyError:
        # Not in registry — fall through to error
        pass
    except Exception as exc:  # noqa: BLE001
        logger.info(f"[MACRO_FACTORY] Registry lookup failed: {exc}")

    # ── Unknown type ──────────────────────────────────────────────────────────
    logger.info(f"[MACRO_FACTORY] Unknown macro type: {macro_type}")
    broker.route_task(row_id, job_id, "FAILED", payload_path, source_payload_path=source_payload_path)


def _rewrite_wait_for(wait_for: str, macro_id: str) -> str:
    """Rewrite comma-separated Wait_For node IDs with the macro_id suffix."""
    if not wait_for or wait_for.lower() == "none":
        return "none"
    parts = [f"{p.strip()}_{macro_id}" for p in wait_for.split(",") if p.strip()]
    return ",".join(parts)
