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
maccre_core/tools/agent_tools.py
==================================
Atomic, GUI-agnostic agent-definition helpers for the MACCRE Tool Registry.

Harvested from NewsCast/agent_manager.py and NewsCast/topology_manager.py.
Business logic (file-system paths, project constants) stripped.

Strangler Fig note:
  AgentRecord is a pure dataclass. TopologySelector carries no LLM calls —
  all routing logic is deterministic, making it trivially testable.

Gemini Function Calling schema contract:
  - Explicit Python type hints throughout.
  - Google-style docstrings (Args / Returns / Raises).
"""

import json
import pathlib
import random
from dataclasses import dataclass
from typing import Optional, Dict, Any


# ── AgentRecord dataclass ────────────────────────────────────────────────────

@dataclass
class AgentRecord:
    """Immutable description of a MACCRE agent persona.

    This is the canonical data object for agent definitions across all
    MACCRE sub-projects.  It replaces the NewsCast-specific ``AgentTemplate``
    class and is completely decoupled from file I/O.

    Attributes:
        name: Unique display name used as the agent's identifier (e.g.
            ``"AI Opinionist"``).
        persona: Short human-readable label for the role the agent plays
            (e.g. ``"The Host"``).
        model: Verified Gemini model string the agent should use for
            generation.  Must match a value in ``VerifiedModel``.
        grounding: Whether to enable Google Search grounding for this agent.
        instructions: Detailed behavioral directive injected as the system
            instruction when the agent generates a response.
    """

    name: str
    persona: str
    model: str = "gemini-2.5-flash"
    grounding: bool = True
    instructions: str = ""

    def to_dict(self) -> dict:
        """Serialise to a plain dict suitable for JSON output.

        Returns:
            A dictionary with keys: name, persona, model, grounding,
            instructions.
        """
        return {
            "name": self.name,
            "persona": self.persona,
            "model": self.model,
            "grounding": self.grounding,
            "instructions": self.instructions,
        }


# ── Factory functions ────────────────────────────────────────────────────────

def load_agent_from_dict(data: Dict[str, Any]) -> Dict[str, Any]:
    """Construct an AgentRecord dict from a plain Python dictionary.

    Missing optional keys fall back to defaults.

    Args:
        data: Dict containing at minimum ``"name"`` and ``"persona"`` keys.
            Optional keys: ``"model"``, ``"grounding"``, ``"instructions"``.

    Returns:
        A fully initialised dictionary representing the agent.

    Raises:
        KeyError: If the required ``"name"`` or ``"persona"`` keys are absent.
    """
    record = AgentRecord(
        name=data["name"],
        persona=data.get("persona", ""),
        model=data.get("model", "gemini-2.5-flash"),
        grounding=data.get("grounding", True),
        instructions=data.get("instructions", ""),
    )
    return record.to_dict()


def load_agent_from_file(path: str) -> Dict[str, Any]:
    """Deserialise an AgentRecord dict from a JSON file on disk.

    Args:
        path: Filesystem path (as string) to a ``.json`` file containing a single agent
            definition dict (as produced by save_agent_to_file).

    Returns:
        A fully initialised dictionary representing the agent.

    Raises:
        FileNotFoundError: If ``path`` does not exist.
        json.JSONDecodeError: If the file content is not valid JSON.
    """
    p = pathlib.Path(path)
    data = json.loads(p.read_text(encoding="utf-8"))
    return load_agent_from_dict(data)


def save_agent_to_file(
    agent_data: Dict[str, Any],
    directory: str,
) -> str:
    """Write an agent configuration to a JSON file inside ``directory``.

    The filename is derived from the agent's name with spaces replaced by
    underscores (e.g. ``"AI Opinionist"`` → ``"AI_Opinionist.json"``).

    Args:
        agent_data: A dictionary containing the agent's configuration. Must include keys like 'name' and 'persona'. Optional: 'model', 'grounding', 'instructions'.
        directory: Target directory (as string). Created if it does not exist.

    Returns:
        The absolute string path of the written file.

    Raises:
        OSError: If the file cannot be written.
    """
    record = AgentRecord(
        name=agent_data["name"],
        persona=agent_data.get("persona", ""),
        model=agent_data.get("model", "gemini-2.5-flash"),
        grounding=agent_data.get("grounding", True),
        instructions=agent_data.get("instructions", ""),
    )
    # Route relative paths through the datacenter jail so files land inside
    # the active project's __DATACENTER directory, not the process cwd.
    d = pathlib.Path(directory)
    if not d.is_absolute():
        from maccre_core.utils.path_resolver import get_datacenter_path  # noqa: PLC0415
        d = get_datacenter_path(*d.parts)
    d.mkdir(parents=True, exist_ok=True)
    filename = f"{record.name.replace(' ', '_')}.json"
    dest = d / filename
    dest.write_text(json.dumps(record.to_dict(), indent=4), encoding="utf-8")
    return str(dest.absolute())


# ── TopologySelector ─────────────────────────────────────────────────────────

class TopologySelector:
    """Stateless-by-design agent routing selector.

    Extracted and generalised from NewsCast/topology_manager.py.  The only
    mutable state is ``last_speaker`` which can be explicitly reset, making
    it safe to serialise into a queue-backed workflow.

    Attributes:
        mode: Routing strategy. One of ``"linear"`` or ``"chaos"``.
        last_speaker: Name of the agent that spoke most recently, or
            ``None`` if the session has not started.
    """

    def __init__(self, mode: str = "linear") -> None:
        self.mode = mode
        self.last_speaker: Optional[str] = None

    def reset(self) -> None:
        """Clear the last-speaker state so the selector starts fresh.

        Returns:
            None
        """
        self.last_speaker = None

    def next_speaker(
        self,
        agents: list[AgentRecord],
        goal: str,
    ) -> AgentRecord:
        """Select the next agent to speak based on the current routing mode.

        Args:
            agents: All ``AgentRecord`` objects currently active in the swarm.
                Must contain at least one entry.
            goal: The goal or theme of the current show phase (informational;
                may be used by future ML-based routing modes).

        Returns:
            The ``AgentRecord`` that should speak next.

        Raises:
            ValueError: If ``agents`` is empty.
        """
        if not agents:
            raise ValueError("next_speaker requires at least one agent.")

        if self.mode == "linear":
            if self.last_speaker is None or "Opinionist" not in self.last_speaker:
                opinionist = next(
                    (a for a in agents if "Opinionist" in a.name), agents[0]
                )
                self.last_speaker = opinionist.name
                return opinionist
            else:
                panelists = [a for a in agents if "Opinionist" not in a.name]
                chosen = random.choice(panelists) if panelists else agents[0]
                self.last_speaker = chosen.name
                return chosen

        elif self.mode == "chaos":
            candidates = [a for a in agents if a.name != self.last_speaker]
            chosen = random.choice(candidates if candidates else agents)
            self.last_speaker = chosen.name
            return chosen

        # Fallback
        return agents[0]


# ── Scope Expansion Tool ─────────────────────────────────────────────────────

def request_scope_expansion(target_project: str, justification: str) -> str:
    """Allows a myopic agent to request access to a foreign project database.

    Writes the request to the human intervention queue and instructs the agent
    to continue with its current scope rather than hallucinating missing data.

    Args:
        target_project: The collection or project name the agent needs access to.
        justification: One-sentence explanation of why the scope expansion is needed.

    Returns:
        A system acknowledgement string for the agent's observation window.
    """
    import os
    from maccre_core.utils.path_resolver import get_datacenter_path
    request_log = str(get_datacenter_path("human_intervention_queue.txt"))
    os.makedirs(os.path.dirname(request_log), exist_ok=True)
    with open(request_log, "a", encoding="utf-8") as f:
        f.write(f"REQUESTED_SCOPE: {target_project}\nREASON: {justification}\n---\n")

    return (
        f"SYSTEM ACKNOWLEDGEMENT: Scope expansion request for '{target_project}' "
        "has been sent to the Architect. Proceed with your current task using only "
        "your active scope. Do not hallucinate missing data."
    )

# ── Nexus Copilot DeadFlow & Topology Tools ──────────────────────────────────

def inspect_deadflow(job_id: str) -> str:
    """[NEXUS TOOL] Inspect a failed session to identify the failing node.
    
    Args:
        job_id: The job ID of the failed session.
    """
    try:
        from maccre_core.orchestration.local_broker import LocalMessageBroker
        import json
        broker = LocalMessageBroker()
        errors = broker.get_task_errors(job_id)
        return json.dumps(errors, indent=2)
    except Exception as e:
        return f"[ERROR] Failed to inspect DeadFlow: {e}"

def patch_live_topology(node_id: str, field: str, value: str) -> str:
    """[NEXUS TOOL] Patch a live running topology node's config.
    
    Args:
        node_id: The ID of the node to patch.
        field: The column name to patch (e.g. 'MODEL_OVERRIDE', 'INSTRUCTION_OVERRIDE').
        value: The new value to set.
    """
    from maccre_core.orchestration.topology_engine import TopologyEngine
    try:
        TopologyEngine().patch_node(node_id, field, value)
        return f"[TOPOLOGY PATCHED] Successfully updated {node_id}.{field} = {value}"
    except Exception as e:
        return f"[ERROR] Failed to patch topology: {e}"
