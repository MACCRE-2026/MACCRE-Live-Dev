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
# │  VI.  ABSTRACTION All I/O behind abc.ABC before any concrete driver.       │
# │  VII. TEARDOWN    try/finally on all handles (omni clean compliance).      │
# │  VIII.TELEMETRY   No bare print(). logger only. JSON → 03_Agent_Ledgers.  │
# └─────────────────────────────────────────────────────────────────────────────┘
"""
maccre_core/orchestration/roster_loader.py
=============================================
Utility for loading agent configurations from the Global agent roster CSV.

The roster CSV lives at:
  __DATACENTER/GLOBAL/agent_roster.csv

Columns: Agent_Name, Model, Tools_Allowed, System_Prompt, Description
"""
from __future__ import annotations

import csv
from typing import Any

from maccre_core.logger import logger
from maccre_core.utils.path_resolver import get_maccre_root


def _roster_path() -> str:
    """Return the resolved path to the Global agent roster CSV."""
    return str(get_maccre_root() / "__DATACENTER" / "GLOBAL" / "agent_roster.csv")


def _read_roster() -> list[dict[str, str]]:
    """Read all rows from the agent_roster.csv via DictReader.

    Returns:
        List of row dicts keyed by CSV column headers.
    """
    path = _roster_path()
    fh = open(path, newline="", encoding="utf-8")  # noqa: SIM115
    try:
        reader = csv.DictReader(fh)
        return list(reader)
    finally:
        fh.close()


def load_agent_from_roster(agent_name: str) -> dict[str, Any]:
    """Load an agent's full config from the Global agent roster.

    Returns dict with keys: name, model, system_prompt, tools_allowed, description.
    Raises KeyError if agent not found.

    Args:
        agent_name: Exact agent name as it appears in the Agent_Name column.

    Returns:
        Dict with keys: name, model, system_prompt, tools_allowed, description.

    Raises:
        KeyError: If the agent_name is not found in the roster.
    """
    rows = _read_roster()
    for row in rows:
        if row.get("Agent_Name", "").strip() == agent_name.strip():
            logger.info("[roster_loader] Loaded agent '%s' from roster", agent_name)
            return {
                "name": row.get("Agent_Name", "").strip(),
                "model": row.get("Model", "").strip(),
                "system_prompt": row.get("System_Prompt", "").strip(),
                "tools_allowed": row.get("Tools_Allowed", "").strip(),
                "description": row.get("Description", "").strip(),
            }
    raise KeyError(f"Agent '{agent_name}' not found in roster at {_roster_path()}")


def list_roster_agents() -> list[str]:
    """Return sorted list of all agent names in the Global roster.

    Returns:
        Alphabetically sorted list of agent name strings.
    """
    rows = _read_roster()
    names = [row.get("Agent_Name", "").strip() for row in rows if row.get("Agent_Name", "").strip()]
    return sorted(set(names))


def validate_agents_exist(agent_names: list[str]) -> list[str]:
    """Return list of agent names that do NOT exist in the roster.

    Args:
        agent_names: List of agent names to validate.

    Returns:
        List of agent names from the input that were not found in the roster.
        Empty list means all agents exist.
    """
    existing = set(list_roster_agents())
    missing = [n for n in agent_names if n.strip() not in existing]
    if missing:
        logger.warning("[roster_loader] Missing agents: %s", missing)
    return missing
