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
maccre_core/schemas/topology_schemas.py
========================================
Canonical dataclass schemas for Structured-Output topology and agent generation.
Replaces the deprecated Pydantic payload models.
"""
from __future__ import annotations
from dataclasses import dataclass, field

@dataclass
class AgentRecordSchema:
    """Structured schema for minting a new agent into the agent_roster.csv."""
    name: str = field(metadata={"description": "Human readable agent name (e.g. 'Auteur')."})
    persona: str = field(metadata={"description": "UPPERCASE_ID used as internal reference."})
    model: str = field(metadata={"description": "Target compute backend (e.g. 'gemini-3.1-pro-preview', 'gemma3:9b')."})
    grounding: bool = field(metadata={"description": "True if the agent requires live web search grounding."})
    instructions: str = field(metadata={"description": "Strict Temp=0.1 State-Machine instructions."})

@dataclass
class TopologyNode:
    """Structured schema for a single node in a Swarm DAG topology."""
    Node_ID: str = field(metadata={"description": "Unique node identifier within the topology."})
    Agent_Name: str = field(metadata={"description": "Must match an existing Agent_Name in agent_roster.csv."})
    Model_Override: str = field(metadata={"description": "Override model for this node. Leave empty to inherit from agent roster."})
    Next_Node: str = field(metadata={"description": "Next Node_ID on success, comma-separated for Scatter fan-out, or 'STOP'."})
    Temperature: float = field(metadata={"description": "LLM temperature for this node (0.0-2.0). Typical: 0.7 for creative, 0.1 for critic."})
    Instruction_Override: str = field(metadata={"description": "Override system instruction for this node."})
    Max_Recursion: int = field(default=3, metadata={"description": "Maximum tool-call cycles before this node is force-terminated."})
    Wait_For: str = field(default="none", metadata={"description": "Comma-separated Node_IDs that must be 'completed' before this node can run (Gather Gate). Use 'none' to disable."})
    Failure_Target: str = field(default="FAILED", metadata={"description": "Node to route to on failure. Defaults to 'FAILED' terminal sentinel."})

@dataclass
class ForgeProposal:
    """Complete structured proposal from the Nexus Forge, ready for deployment."""
    rationale: str = field(metadata={"description": "Explanation of the proposed architecture and agent roles to the Architect."})
    new_agents: list[AgentRecordSchema] = field(metadata={"description": "New agent personas required for this topology."})
    topology_nodes: list[TopologyNode] = field(metadata={"description": "The complete DAG routing logic as ordered nodes."})
