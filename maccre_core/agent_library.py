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
maccre_core/agent_library.py
==============================
Named agent store — save, load, list, and search agents across projects.

Architecture:
  Every project silo has its own agent_library.db.
  The GLOBAL silo aggregates all agents ever used, with project provenance.
  When a workbook is fired against an existing project, its agent dropdown
  is populated from both the project-local DB and the GLOBAL DB.

Storage path (relative to MACCRE root):
  __DATACENTER/<project_id>/agent_library.db
"""
from __future__ import annotations

import abc
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from maccre_core.utils.path_resolver import get_maccre_root

# ── Path helpers ──────────────────────────────────────────────────────────────

_DB_NAME = "agent_library.db"
_GLOBAL_PROJECT = "GLOBAL"


def _db_path(project_id: str = "") -> Path:
    """Return the agent_library.db path (now strictly GLOBAL)."""
    return get_maccre_root() / "__DATACENTER" / _GLOBAL_PROJECT / _DB_NAME


# ── Abstract Interface ────────────────────────────────────────────────────────

class AgentStore(abc.ABC):
    """ABC for agent roster persistence."""

    @abc.abstractmethod
    def save(self, agent: dict[str, Any], source_project: str = "") -> None:
        """Upsert a single agent dict into the store."""

    @abc.abstractmethod
    def save_roster(self, agents: list[dict[str, Any]], source_project: str = "") -> None:
        """Upsert a full roster (list of agent dicts) into the store."""

    @abc.abstractmethod
    def load_all(self) -> list[dict[str, Any]]:
        """Return all agents, most recently used first."""

    @abc.abstractmethod
    def get_names(self) -> list[str]:
        """Return a flat list of all agent names (for dropdown population)."""

    @abc.abstractmethod
    def delete(self, agent_name: str) -> None:
        """Remove an agent by name. Raises KeyError if not found."""


# ── SQLite Implementation ─────────────────────────────────────────────────────

_CREATE_SQL = """
CREATE TABLE IF NOT EXISTS agent_library (
    agent_name      TEXT PRIMARY KEY,
    model           TEXT DEFAULT '',
    tools_allowed   TEXT DEFAULT '',
    system_prompt   TEXT DEFAULT '',
    temperature     REAL DEFAULT 1.0,
    agent_json      TEXT NOT NULL,
    source_project  TEXT DEFAULT '',
    created_at      TEXT NOT NULL,
    last_used       TEXT NOT NULL
);
"""


class SQLiteAgentStore(AgentStore):
    """SQLite-backed agent store. Thread-safe via check_same_thread=False."""

    def __init__(self, db_path: Path) -> None:
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self._path = db_path
        self._bootstrap()

    def _bootstrap(self) -> None:
        conn = sqlite3.connect(str(self._path), check_same_thread=False)
        try:
            conn.execute(_CREATE_SQL)
            conn.commit()
        finally:
            conn.close()

    def _conn(self) -> sqlite3.Connection:
        return sqlite3.connect(str(self._path), check_same_thread=False)

    def save(self, agent: dict[str, Any], source_project: str = "") -> None:
        now = datetime.now(timezone.utc).isoformat()
        name = str(agent.get("agent_name") or agent.get("AGENT_NAME", "")).strip()
        if not name:
            return
        conn = self._conn()
        try:
            conn.execute(
                """INSERT INTO agent_library
                   (agent_name, model, tools_allowed, system_prompt, temperature,
                    agent_json, source_project, created_at, last_used)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(agent_name) DO UPDATE SET
                     model          = excluded.model,
                     tools_allowed  = excluded.tools_allowed,
                     system_prompt  = excluded.system_prompt,
                     temperature    = excluded.temperature,
                     agent_json     = excluded.agent_json,
                     source_project = excluded.source_project,
                     last_used      = excluded.last_used
                """,
                (
                    name,
                    str(agent.get("model") or agent.get("MODEL", "")),
                    str(agent.get("tools_allowed") or agent.get("TOOLS", "")),
                    str(agent.get("system_prompt") or agent.get("PERSONA", "")),
                    float(agent.get("temperature") or agent.get("TEMPERATURE", 1.0)),
                    json.dumps(agent),
                    source_project,
                    now,
                    now,
                ),
            )
            conn.commit()
        finally:
            conn.close()

    def save_roster(self, agents: list[dict[str, Any]], source_project: str = "") -> None:
        for agent in agents:
            self.save(agent, source_project)

    def load_all(self) -> list[dict[str, Any]]:
        conn = self._conn()
        try:
            rows = conn.execute(
                "SELECT agent_json FROM agent_library ORDER BY last_used DESC"
            ).fetchall()
        finally:
            conn.close()
        return [json.loads(r[0]) for r in rows]

    def get(self, agent_name: str) -> dict[str, Any]:
        """Retrieve a specific agent by name."""
        conn = self._conn()
        try:
            row = conn.execute(
                "SELECT agent_json FROM agent_library WHERE agent_name = ?", (agent_name.strip(),)
            ).fetchone()
        finally:
            conn.close()
        
        if not row:
            raise KeyError(f"Agent '{agent_name}' not found in AgentStore.")
        return json.loads(row[0])

    def get_names(self) -> list[str]:
        conn = self._conn()
        try:
            rows = conn.execute(
                "SELECT agent_name FROM agent_library ORDER BY last_used DESC"
            ).fetchall()
        finally:
            conn.close()
        return [r[0] for r in rows]

    def delete(self, agent_name: str) -> None:
        conn = self._conn()
        try:
            cur = conn.execute(
                "DELETE FROM agent_library WHERE agent_name = ?", (agent_name.strip(),)
            )
            conn.commit()
        finally:
            conn.close()
        if cur.rowcount == 0:
            raise KeyError(f"Agent '{agent_name}' not found — nothing deleted.")


# ── Public Factory ────────────────────────────────────────────────────────────

def get_agent_store(project_id: str = "") -> SQLiteAgentStore:
    """Return a SQLiteAgentStore for the given project (defaults to GLOBAL)."""
    return SQLiteAgentStore(_db_path(project_id))


def save_roster_globally(
    agents: list[dict[str, Any]],
    source_project: str = "",
) -> None:
    """Upsert roster into both the source project store AND the GLOBAL store.

    Called automatically on every successful workbook fire when SAVE_TO_LIBRARY=TRUE.
    """
    if source_project and source_project.upper() != _GLOBAL_PROJECT:
        get_agent_store(source_project).save_roster(agents, source_project)
    get_agent_store(_GLOBAL_PROJECT).save_roster(agents, source_project)
