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
maccre_core/notebook_registry.py
=================================
Notebook Registry — SQLite backend for RAG Notebooks.

Storage path (relative to MACCRE root):
  __DATACENTER/<project_id>/notebook_registry.db
"""
from __future__ import annotations

import abc
import json
import sqlite3
import shutil
from datetime import datetime, timezone
from pathlib import Path

from maccre_core.utils.path_resolver import get_maccre_root

# ── Path helpers ──────────────────────────────────────────────────────────────

_DATACENTER = "notebook_registry.db"
_GLOBAL_PROJECT = "GLOBAL"


def _db_path(project_id: str = "") -> Path:
    """Return the notebook_registry.db path for a given project (or GLOBAL)."""
    pid = project_id.strip() or _GLOBAL_PROJECT
    return get_maccre_root() / "__DATACENTER" / pid / _DATACENTER


# ── Abstract Interface ────────────────────────────────────────────────────────

class NotebookStore(abc.ABC):
    """ABC for Notebook persistence."""

    @abc.abstractmethod
    def save(
        self,
        name: str,
        files: list[str],
    ) -> None:
        """Upsert a named Notebook into the store."""

    @abc.abstractmethod
    def load(self, name: str) -> dict[str, list[str]]:
        """Return Notebook dict. Raises KeyError if not found."""

    @abc.abstractmethod
    def list_all(self) -> list[str]:
        """Return summary list."""

    @abc.abstractmethod
    def delete(self, name: str) -> None:
        """Remove a named Notebook. Raises KeyError if not found."""


# ── SQLite Implementation ─────────────────────────────────────────────────────

_CREATE_SQL = """
CREATE TABLE IF NOT EXISTS notebook_registry (
    name            TEXT PRIMARY KEY,
    files_json      TEXT NOT NULL,
    created_at      TEXT NOT NULL,
    last_used       TEXT NOT NULL
);
"""


class SQLiteNotebookStore(NotebookStore):
    """SQLite-backed Notebook registry. Thread-safe via check_same_thread=False."""

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

    def save(self, name: str, files: list[str]) -> None:
        now = datetime.now(timezone.utc).isoformat()
        conn = self._conn()
        try:
            conn.execute(
                """INSERT INTO notebook_registry
                   (name, files_json, created_at, last_used)
                   VALUES (?, ?, ?, ?)
                   ON CONFLICT(name) DO UPDATE SET
                     files_json    = excluded.files_json,
                     last_used     = excluded.last_used
                """,
                (
                    name.strip(),
                    json.dumps(files),
                    now,
                    now,
                ),
            )
            conn.commit()
        finally:
            conn.close()

    def load(self, name: str) -> dict[str, list[str]]:
        conn = self._conn()
        try:
            row = conn.execute(
                "SELECT name, files_json, created_at, last_used "
                "FROM notebook_registry WHERE name = ?",
                (name.strip(),),
            ).fetchone()
        finally:
            conn.close()
        if not row:
            raise KeyError(f"Notebook '{name}' not found in {self._path}")
        self._touch(name.strip())
        return {
            "name": row[0],
            "files": json.loads(row[1]),
            "created_at": row[2],
            "last_used": row[3],
        }

    def list_all(self) -> list[str]:
        conn = self._conn()
        try:
            rows = conn.execute(
                "SELECT name FROM notebook_registry ORDER BY last_used DESC"
            ).fetchall()
        finally:
            conn.close()
        return [r[0] for r in rows]

    def delete(self, name: str) -> None:
        conn = self._conn()
        try:
            cur = conn.execute("DELETE FROM notebook_registry WHERE name = ?", (name.strip(),))
            conn.commit()
        finally:
            conn.close()
        if cur.rowcount == 0:
            raise KeyError(f"Notebook '{name}' not found — nothing deleted.")

    def _touch(self, name: str) -> None:
        conn = self._conn()
        try:
            conn.execute(
                "UPDATE notebook_registry SET last_used = ? WHERE name = ?",
                (datetime.now(timezone.utc).isoformat(), name),
            )
            conn.commit()
        finally:
            conn.close()


# ── Public Factory ────────────────────────────────────────────────────────────

def get_notebook_store(project_id: str = "") -> SQLiteNotebookStore:
    """Return a SQLiteNotebookStore for the given project (defaults to GLOBAL)."""
    return SQLiteNotebookStore(_db_path(project_id))


def ingest_to_notebook(notebook_name: str, project_id: str, files: list[str]) -> None:
    """
    Ingest a list of files into a RAG Notebook.
    1. Copies files to __DATACENTER/<project_id>/01_Raw_Source/<notebook_name>
    2. Registers them in the notebook_registry.db
    """
    root = get_maccre_root()
    pid = project_id.strip() or _GLOBAL_PROJECT
    dest_dir = root / "__DATACENTER" / pid / "01_Raw_Source" / notebook_name
    dest_dir.mkdir(parents=True, exist_ok=True)
    
    ingested_paths = []
    for fpath in files:
        fpath = fpath.strip()
        if not fpath:
            continue
            
        src = Path(fpath)
        if not src.exists():
            continue
            
        dest = dest_dir / src.name
        try:
            shutil.copy2(src, dest)
            ingested_paths.append(str(dest))
        except Exception:
            pass # Skip unreadable files
            
    store = get_notebook_store(pid)
    # If notebook exists, append. Else create new.
    try:
        existing = store.load(notebook_name)
        new_files = existing["files"] + ingested_paths
        # Dedup keeping order
        new_files = list(dict.fromkeys(new_files))
        store.save(notebook_name, new_files)
    except KeyError:
        store.save(notebook_name, ingested_paths)

