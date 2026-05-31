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
maccre_core/patterns/__init__.py
=================================
Sovereign Pattern Library — reusable topology templates that serve Antigravity
as an active orchestration layer rather than a passive tool.

A Pattern is a parameterizable topology template that:
  1. Materializes as a signed topology.csv in an isolated project silo
  2. Injects itself into the swarm queue via inject_task()
  3. Terminates at a HUMAN_GATE (awaiting_orders) that delivers a BriefPacket

The pattern library solves the statelessness problem: each Antigravity
instantiation starts from zero, but the swarm maintains state and delivers
a structured context packet (BriefPacket) that re-contextualizes the session.

Core Patterns:
  simulation_swarm    — Pre-commit deliberation via N parallel implementation paths
  research_sweep      — Deep domain investigation before acting
  session_brief       — Wake-up context packet for new sessions
  checkpoint_sweep    — End-of-work validation + KI update
  fault_investigation — Root cause analysis on failures
  monitor_watch       — Background daemon monitoring with threshold alerting
  code_review         — Multi-angle independent code analysis
"""
from __future__ import annotations

import importlib
import logging
from dataclasses import dataclass, field
from typing import Any

_log = logging.getLogger("maccre_core.patterns")


@dataclass
class PatternNode:
    """A single node in a pattern topology definition."""

    node_id: str
    agent_name: str
    instruction_override: str
    next_node: str                          # comma-separated for FORK fan-out
    temperature: float = 0.7
    model_override: str = ""               # empty = inherit from agent roster
    wait_for: str = "none"                 # comma-separated for JOIN Gather Gate
    max_recursion: int = 3
    failure_target: str = "PATTERN_FAILED"


@dataclass
class PatternDefinition:
    """A complete, parameterizable topology pattern.

    Encapsulates everything needed to materialize and run a sovereign swarm
    pattern — topology nodes, agent roster entries, payload template, and cost
    metadata.  Patterns are defined as Python dataclasses (not YAML/JSON) so
    pyright validates them at build time and they version-control cleanly.
    """

    name: str
    description: str
    nodes: list[PatternNode]
    payload_template: str                   # Template for human-readable input payload
    estimated_cost_usd: float
    required_surfaces: list[str]            # e.g. ["TEXT", "DEEP_RESEARCH", "IMAGE"]
    has_human_gate: bool = True
    agent_roster_entries: list[dict[str, Any]] = field(default_factory=list)

    # ── CSV Rendering ──────────────────────────────────────────────────────────

    def render_topology_csv(self) -> str:
        """Render nodes as a complete topology.csv string the TopologyEngine can load."""
        header = (
            "Node_ID,Agent_Name,Model_Override,Next_Node,"
            "Temperature,Instruction_Override,Wait_For,Failure_Target,Max_Recursion"
        )
        rows: list[str] = [header]
        for node in self.nodes:
            safe_instr = node.instruction_override.replace('"', '""')
            rows.append(
                f"{node.node_id},"
                f"{node.agent_name},"
                f"{node.model_override},"
                f"{node.next_node},"
                f"{node.temperature},"
                f'"{safe_instr}",'
                f"{node.wait_for},"
                f"{node.failure_target},"
                f"{node.max_recursion}"
            )
        return "\n".join(rows)

    def render_roster_csv_rows(self) -> str:
        """Render agent roster entries as CSV rows (no header, for appending)."""
        rows: list[str] = []
        for entry in self.agent_roster_entries:
            safe_prompt = entry.get("System_Prompt", "").replace('"', '""')
            rows.append(
                f"{entry.get('Agent_Name', '')},"
                f"{entry.get('Model', '')},"
                f"{entry.get('Tools_Allowed', 'none')},"
                f'"{safe_prompt}"'
            )
        return "\n".join(rows)


# ── Pattern Registry ──────────────────────────────────────────────────────────

_PATTERN_REGISTRY: dict[str, PatternDefinition] = {}


def register_pattern(pattern: PatternDefinition) -> PatternDefinition:
    """Register a pattern definition into the global registry.

    Designed to be used as a call at module level in each definition file:
        register_pattern(PatternDefinition(name="simulation_swarm", ...))
    """
    _PATTERN_REGISTRY[pattern.name] = pattern
    _log.debug("[PatternLibrary] Registered pattern: %s", pattern.name)
    return pattern


def get_pattern(name: str) -> PatternDefinition:
    """Retrieve a pattern definition by name.

    Raises:
        KeyError: If the pattern name is not registered.
    """
    if name not in _PATTERN_REGISTRY:
        available = list(_PATTERN_REGISTRY.keys())
        raise KeyError(
            f"Pattern '{name}' not found in registry. "
            f"Available: {available}"
        )
    return _PATTERN_REGISTRY[name]


def list_patterns() -> list[dict[str, Any]]:
    """Return metadata for all registered patterns (for MCP tool surface)."""
    return [
        {
            "name": p.name,
            "description": p.description,
            "estimated_cost_usd": p.estimated_cost_usd,
            "required_surfaces": p.required_surfaces,
            "has_human_gate": p.has_human_gate,
            "node_count": len(p.nodes),
        }
        for p in _PATTERN_REGISTRY.values()
    ]


# ── Auto-Loader ───────────────────────────────────────────────────────────────

_PATTERN_MODULES: list[str] = [
    "maccre_core.patterns.definitions.simulation_swarm",
    "maccre_core.patterns.definitions.research_sweep",
    "maccre_core.patterns.definitions.session_brief",
    "maccre_core.patterns.definitions.checkpoint_sweep",
    "maccre_core.patterns.definitions.fault_investigation",
    "maccre_core.patterns.definitions.monitor_watch",
    "maccre_core.patterns.definitions.code_review",
    "maccre_core.patterns.definitions.shift_register",
]


def _load_all_patterns() -> None:
    """Import all definition modules to populate the registry on first import."""
    for mod_name in _PATTERN_MODULES:
        try:
            importlib.import_module(mod_name)
        except ModuleNotFoundError:
            pass  # Definition file not yet written — skip silently
        except Exception as exc:
            _log.warning("[PatternLibrary] Failed to load '%s': %s", mod_name, exc)


_load_all_patterns()

__all__ = [
    "PatternNode",
    "PatternDefinition",
    "register_pattern",
    "get_pattern",
    "list_patterns",
]
