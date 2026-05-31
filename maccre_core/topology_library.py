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
maccre_core/topology_library.py
================================
Named topology store — save, load, list, and delete swarm topologies.

Architecture:
  Every project silo has its own topology_library.db.
  The GLOBAL silo acts as a universal aggregate — every successful launch
  upserts its topology here so it is always available regardless of project.

Storage path (relative to MACCRE root):
  __DATACENTER/<project_id>/topology_library.db
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

_DATACENTER = "topology_library.db"
_GLOBAL_PROJECT = "GLOBAL"


def _db_path(project_id: str = "") -> Path:
    """Return the topology_library.db path for a given project (or GLOBAL)."""
    pid = project_id.strip() or _GLOBAL_PROJECT
    return get_maccre_root() / "__DATACENTER" / pid / _DATACENTER


# ── Abstract Interface ────────────────────────────────────────────────────────

class TopologyStore(abc.ABC):
    """ABC for named topology persistence. Swap implementations without callers knowing."""

    @abc.abstractmethod
    def save(
        self,
        name: str,
        topology_rows: list[dict[str, Any]],
        roster_rows: list[dict[str, Any]] | None = None,
        description: str = "",
    ) -> None:
        """Upsert a named topology (and optional agent roster) into the store."""

    @abc.abstractmethod
    def load(self, name: str) -> dict[str, Any]:
        """Return topology dict with keys: name, description, topology_rows, roster_rows.

        Raises KeyError if name not found.
        """

    @abc.abstractmethod
    def list_all(self) -> list[dict[str, Any]]:
        """Return summary list: [{name, description, node_count, created_at, last_used}]."""

    @abc.abstractmethod
    def delete(self, name: str) -> None:
        """Remove a named topology. Raises KeyError if not found."""


# ── SQLite Implementation ─────────────────────────────────────────────────────

_CREATE_SQL = """
CREATE TABLE IF NOT EXISTS topology_library (
    name            TEXT PRIMARY KEY,
    description     TEXT DEFAULT '',
    node_count      INTEGER DEFAULT 0,
    topology_json   TEXT NOT NULL,
    roster_json     TEXT,
    created_at      TEXT NOT NULL,
    last_used       TEXT NOT NULL
);
"""


class SQLiteTopologyStore(TopologyStore):
    """SQLite-backed topology store. Thread-safe via check_same_thread=False."""

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

    def save(
        self,
        name: str,
        topology_rows: list[dict[str, Any]],
        roster_rows: list[dict[str, Any]] | None = None,
        description: str = "",
    ) -> None:
        now = datetime.now(timezone.utc).isoformat()
        conn = self._conn()
        try:
            conn.execute(
                """INSERT INTO topology_library
                   (name, description, node_count, topology_json, roster_json, created_at, last_used)
                   VALUES (?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(name) DO UPDATE SET
                     description   = excluded.description,
                     node_count    = excluded.node_count,
                     topology_json = excluded.topology_json,
                     roster_json   = excluded.roster_json,
                     last_used     = excluded.last_used
                """,
                (
                    name.strip(),
                    description,
                    len(topology_rows),
                    json.dumps(topology_rows),
                    json.dumps(roster_rows) if roster_rows else None,
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
                "SELECT name, description, topology_json, roster_json, created_at, last_used "
                "FROM topology_library WHERE name = ?",
                (name.strip(),),
            ).fetchone()
        finally:
            conn.close()
        if not row:
            raise KeyError(f"Topology '{name}' not found in {self._path}")
        # Touch last_used
        self._touch(name.strip())
        return {
            "name": row[0],
            "description": row[1],
            "topology_rows": json.loads(row[2]),
            "roster_rows": json.loads(row[3]) if row[3] else [],
            "created_at": row[4],
            "last_used": row[5],
        }

    def list_all(self) -> list[dict[str, Any]]:
        conn = self._conn()
        try:
            rows = conn.execute(
                "SELECT name, description, node_count, created_at, last_used "
                "FROM topology_library ORDER BY last_used DESC"
            ).fetchall()
        finally:
            conn.close()
        return [
            {
                "name": r[0], "description": r[1], "node_count": r[2],
                "created_at": r[3], "last_used": r[4],
            }
            for r in rows
        ]

    def delete(self, name: str) -> None:
        conn = self._conn()
        try:
            cur = conn.execute("DELETE FROM topology_library WHERE name = ?", (name.strip(),))
            conn.commit()
        finally:
            conn.close()
        if cur.rowcount == 0:
            raise KeyError(f"Topology '{name}' not found — nothing deleted.")

    def _touch(self, name: str) -> None:
        conn = self._conn()
        try:
            conn.execute(
                "UPDATE topology_library SET last_used = ? WHERE name = ?",
                (datetime.now(timezone.utc).isoformat(), name),
            )
            conn.commit()
        finally:
            conn.close()


# ── Public Factory ────────────────────────────────────────────────────────────

def get_topology_store(project_id: str = "") -> SQLiteTopologyStore:
    """Return a SQLiteTopologyStore for the given project (defaults to GLOBAL)."""
    return SQLiteTopologyStore(_db_path(project_id))


def save_topology_globally(
    name: str,
    topology_rows: list[dict[str, Any]],
    roster_rows: list[dict[str, Any]] | None = None,
    description: str = "",
    source_project: str = "",
) -> None:
    """Upsert topology into both the source project store AND the GLOBAL store.

    Called automatically on every successful workbook fire when SAVE_TO_LIBRARY=TRUE.
    """
    if source_project and source_project.upper() != _GLOBAL_PROJECT:
        get_topology_store(source_project).save(name, topology_rows, roster_rows, description)
    get_topology_store(_GLOBAL_PROJECT).save(name, topology_rows, roster_rows, description)
