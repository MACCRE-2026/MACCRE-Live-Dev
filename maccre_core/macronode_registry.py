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
maccre_core/macronode_registry.py
==================================
MacroNode Registry — SQLite backend for saved MacroNodes.

A MacroNode is essentially a saved topology configuration (from the old workbook logic),
with added properties indicating whether it's a 'template' (requiring agent hydration)
or a 'fixed' flow.

Storage path (relative to MACCRE root):
  __DATACENTER/<project_id>/macronode_registry.db
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

_DATACENTER = "macronode_registry.db"
_GLOBAL_PROJECT = "GLOBAL"


def _db_path(project_id: str = "") -> Path:
    """Return the macronode_registry.db path (now strictly GLOBAL)."""
    return get_maccre_root() / "__DATACENTER" / _GLOBAL_PROJECT / _DATACENTER


# ── Abstract Interface ────────────────────────────────────────────────────────

class MacroNodeStore(abc.ABC):
    """ABC for MacroNode persistence."""

    @abc.abstractmethod
    def save(
        self,
        name: str,
        topology_rows: list[dict[str, Any]],
        roster_rows: list[dict[str, Any]] | None = None,
        description: str = "",
        is_template: bool = False,
        agent_slots: list[str] | None = None,
        template_type: str = "",
        template_config: dict[str, Any] | None = None,
    ) -> None:
        """Upsert a named MacroNode into the store."""

    @abc.abstractmethod
    def load(self, name: str) -> dict[str, Any]:
        """Return MacroNode dict with all fields. Raises KeyError if not found."""

    @abc.abstractmethod
    def list_all(self) -> list[dict[str, Any]]:
        """Return summary list."""

    @abc.abstractmethod
    def delete(self, name: str) -> None:
        """Remove a named MacroNode. Raises KeyError if not found."""


# ── SQLite Implementation ─────────────────────────────────────────────────────

_CREATE_SQL = """
CREATE TABLE IF NOT EXISTS macronode_registry (
    name            TEXT PRIMARY KEY,
    description     TEXT DEFAULT '',
    is_template     INTEGER DEFAULT 0,
    agent_slots     TEXT DEFAULT '[]',
    topology_json   TEXT NOT NULL,
    roster_json     TEXT,
    template_type   TEXT DEFAULT NULL,
    template_config TEXT DEFAULT NULL,
    created_at      TEXT NOT NULL,
    last_used       TEXT NOT NULL
);
"""

_MIGRATE_TEMPLATE_COLS: list[str] = [
    "ALTER TABLE macronode_registry ADD COLUMN template_type TEXT DEFAULT NULL",
    "ALTER TABLE macronode_registry ADD COLUMN template_config TEXT DEFAULT NULL",
]


class SQLiteMacroNodeStore(MacroNodeStore):
    """SQLite-backed MacroNode registry. Thread-safe via check_same_thread=False."""

    def __init__(self, db_path: Path) -> None:
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self._path = db_path
        self._bootstrap()

    def _bootstrap(self) -> None:
        conn = sqlite3.connect(str(self._path), check_same_thread=False)
        try:
            conn.execute(_CREATE_SQL)
            for stmt in _MIGRATE_TEMPLATE_COLS:
                try:
                    conn.execute(stmt)
                except sqlite3.OperationalError:
                    pass  # column already exists — safe to ignore
            conn.commit()
        finally:
            conn.close()

    def _conn(self) -> sqlite3.Connection:
        return sqlite3.connect(str(self._path), check_same_thread=False)

    def save(
        self,
        name: str,
        topology_rows: list[dict[str, Any]],
        roster_rows: list[dict[str, Any]] | None = None,
        description: str = "",
        is_template: bool = False,
        agent_slots: list[str] | None = None,
        template_type: str = "",
        template_config: dict[str, Any] | None = None,
    ) -> None:
        now = datetime.now(timezone.utc).isoformat()
        slots_json = json.dumps(agent_slots) if agent_slots else "[]"
        tpl_type = template_type or None
        tpl_config = json.dumps(template_config) if template_config else None
        conn = self._conn()
        try:
            conn.execute(
                """INSERT INTO macronode_registry
                   (name, description, is_template, agent_slots, topology_json,
                    roster_json, template_type, template_config, created_at, last_used)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(name) DO UPDATE SET
                     description     = excluded.description,
                     is_template     = excluded.is_template,
                     agent_slots     = excluded.agent_slots,
                     topology_json   = excluded.topology_json,
                     roster_json     = excluded.roster_json,
                     template_type   = excluded.template_type,
                     template_config = excluded.template_config,
                     last_used       = excluded.last_used
                """,
                (
                    name.strip(),
                    description,
                    1 if is_template else 0,
                    slots_json,
                    json.dumps(topology_rows),
                    json.dumps(roster_rows) if roster_rows else None,
                    tpl_type,
                    tpl_config,
                    now,
                    now,
                ),
            )
            conn.commit()
        finally:
            conn.close()

    def load(self, name: str) -> dict[str, Any]:
        conn = self._conn()
        try:
            row = conn.execute(
                "SELECT name, description, is_template, agent_slots, topology_json, "
                "roster_json, template_type, template_config, created_at, last_used "
                "FROM macronode_registry WHERE name = ?",
                (name.strip(),),
            ).fetchone()
        finally:
            conn.close()
        if not row:
            raise KeyError(f"MacroNode '{name}' not found in {self._path}")
        # Touch last_used
        self._touch(name.strip())
        return {
            "name": row[0],
            "description": row[1],
            "is_template": bool(row[2]),
            "agent_slots": json.loads(row[3]),
            "topology_rows": json.loads(row[4]),
            "roster_rows": json.loads(row[5]) if row[5] else [],
            "template_type": row[6] or "",
            "template_config": json.loads(row[7]) if row[7] else None,
            "created_at": row[8],
            "last_used": row[9],
        }

    def list_all(self) -> list[dict[str, Any]]:
        conn = self._conn()
        try:
            rows = conn.execute(
                "SELECT name, description, is_template, template_type, created_at, last_used "
                "FROM macronode_registry ORDER BY last_used DESC"
            ).fetchall()
        finally:
            conn.close()
        return [
            {
                "name": r[0],
                "description": r[1],
                "is_template": bool(r[2]),
                "template_type": r[3] or "",
                "created_at": r[4],
                "last_used": r[5],
            }
            for r in rows
        ]

    def delete(self, name: str) -> None:
        conn = self._conn()
        try:
            cur = conn.execute("DELETE FROM macronode_registry WHERE name = ?", (name.strip(),))
            conn.commit()
        finally:
            conn.close()
        if cur.rowcount == 0:
            raise KeyError(f"MacroNode '{name}' not found — nothing deleted.")

    def _touch(self, name: str) -> None:
        conn = self._conn()
        try:
            conn.execute(
                "UPDATE macronode_registry SET last_used = ? WHERE name = ?",
                (datetime.now(timezone.utc).isoformat(), name),
            )
            conn.commit()
        finally:
            conn.close()


# ── Public Factory ────────────────────────────────────────────────────────────

def get_macronode_store(project_id: str = "") -> SQLiteMacroNodeStore:
    """Return a SQLiteMacroNodeStore for the given project (defaults to GLOBAL)."""
    return SQLiteMacroNodeStore(_db_path(project_id))
