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
import os
from typing import Any

from maccre_core.logger import logger
from maccre_core.utils.path_resolver import get_maccre_root


def _roster_path() -> str:
    """Return the resolved path to the Global agent roster CSV."""
    return str(get_maccre_root() / "__DATACENTER" / "GLOBAL" / "agent_roster.csv")


_roster_cache: list[dict[str, str]] = []
_roster_mtime: float = 0.0


def _read_roster() -> list[dict[str, str]]:
    """Read all rows from the agent_roster.csv via DictReader.

    Uses mtime-based caching to avoid redundant disk I/O during
    swarm cycles and flow execution. Cache auto-invalidates when
    admin_tools.py writes to the roster file.

    Returns:
        List of row dicts keyed by CSV column headers.
    """
    global _roster_cache, _roster_mtime  # noqa: PLW0603
    path = _roster_path()
    try:
        current_mtime = os.path.getmtime(path)
    except FileNotFoundError:
        return []
    if current_mtime != _roster_mtime:
        with open(path, newline="", encoding="utf-8") as fh:
            _roster_cache = list(csv.DictReader(fh))
        _roster_mtime = current_mtime
    return _roster_cache


def load_agent_from_roster(agent_name: str) -> dict[str, Any]:
    """Load an agent's full config from the Global agent store (redirected from roster).

    Args:
        agent_name: Exact agent name.

    Returns:
        Dict with keys: name, model, system_prompt, tools_allowed, description.

    Raises:
        KeyError: If the agent_name is not found.
    """
    from maccre_core.agent_library import get_agent_store
    agent = get_agent_store("GLOBAL").get(agent_name)
    logger.info("[roster_loader] Loaded agent '%s' from SQLiteAgentStore", agent_name)
    
    # Translate from library format to roster format if needed
    return {
        "name": agent.get("agent_name", ""),
        "model": agent.get("model", ""),
        "system_prompt": agent.get("system_prompt", ""),
        "tools_allowed": agent.get("tools_allowed", ""),
        "description": agent.get("description", ""),
    }


def list_roster_agents() -> list[str]:
    """Return sorted list of all agent names in the Global store."""
    from maccre_core.agent_library import get_agent_store
    return get_agent_store("GLOBAL").get_names()


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
