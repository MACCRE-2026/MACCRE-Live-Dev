import sqlite3
import logging
from typing import Any
from datetime import datetime, timezone
from pathlib import Path
from maccre_core.utils.path_resolver import get_datacenter_path

logger = logging.getLogger("maccre_core")

class FlowRegistryStore:
    """SQLite-backed registry for saving and loading ephemeral Flow Lines globally."""

    def __init__(self, db_path: Path | None = None) -> None:
        self.db_path = db_path or get_datacenter_path("GLOBAL", "flow_registry.db")
        self._init_db()

    def _init_db(self) -> None:
        """Initialize the SQLite database with the flows table."""
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS flows (
                    name TEXT PRIMARY KEY,
                    description TEXT,
                    steps_json TEXT,
                    created_at TEXT
                )
            ''')
            conn.commit()

    def save_flow(self, name: str, description: str, steps_json: str) -> None:
        """Save a flow to the registry."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            now_str = datetime.now(timezone.utc).isoformat()
            cursor.execute('''
                INSERT INTO flows (name, description, steps_json, created_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(name) DO UPDATE SET
                    description=excluded.description,
                    steps_json=excluded.steps_json,
                    created_at=excluded.created_at
            ''', (name.strip(), description.strip(), steps_json, now_str))
            conn.commit()

    def load_flow(self, name: str) -> dict[str, Any]:
        """Load a single flow by name."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT name, description, steps_json, created_at FROM flows WHERE name = ?", (name,))
            row = cursor.fetchone()
            if row:
                return {
                    "name": row[0],
                    "description": row[1],
                    "steps_json": row[2],
                    "created_at": row[3]
                }
            raise KeyError(f"Flow '{name}' not found in registry.")

    def load_all_flows(self) -> list[dict[str, Any]]:
        """Return a list of all saved flows."""
        flows = []
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT name, description, steps_json, created_at FROM flows ORDER BY created_at DESC")
            for row in cursor.fetchall():
                flows.append({
                    "name": row[0],
                    "description": row[1],
                    "steps_json": row[2],
                    "created_at": row[3]
                })
        return flows

    def delete_flow(self, name: str) -> None:
        """Delete a flow from the registry."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM flows WHERE name = ?", (name,))
            conn.commit()
