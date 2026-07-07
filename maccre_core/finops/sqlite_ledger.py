import sqlite3
import logging
from typing import Optional, Dict, Any, List
from pathlib import Path
from datetime import datetime, timezone
import contextlib

from maccre_core.finops.ledger_interface import AbstractFinOpsLedger
from maccre_core.utils.path_resolver import get_maccre_root, get_datacenter_path

logger = logging.getLogger("maccre_core.finops")

class SQLiteFinOpsLedger(AbstractFinOpsLedger):
    """
    Concrete SQLite WAL implementation of the FinOps ledger.
    Stores telemetry in __DATACENTER/GLOBAL/maccre_books.db.
    """
    
    def __init__(self, db_path: Optional[str] = None):
        if not db_path:
            db_path = str(get_datacenter_path("GLOBAL", "maccre_books.db"))
            
        self.db_path = db_path
        self._ensure_schema()
        
    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=10.0)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        conn.row_factory = sqlite3.Row
        return conn

    def _ensure_schema(self) -> None:
        with contextlib.closing(self._get_connection()) as conn:
            with conn:
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS ledger_entries (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        timestamp TEXT NOT NULL,
                        project_name TEXT NOT NULL,
                        session_id TEXT NOT NULL,
                        node_type TEXT NOT NULL,
                        agent_name TEXT,
                        tool_name TEXT,
                        model_name TEXT,
                        media_type TEXT NOT NULL,
                        cost_usd REAL NOT NULL,
                        canonization_status TEXT DEFAULT 'uncanonized'
                    )
                """)
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS health_metrics (
                        project_name TEXT PRIMARY KEY,
                        last_updated TEXT NOT NULL,
                        fail_rate REAL,
                        canonization_ratio REAL,
                        size_ratio_04_05 REAL
                    )
                """)
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS budget_projections (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        timestamp TEXT NOT NULL,
                        project_name TEXT NOT NULL,
                        session_id TEXT NOT NULL,
                        projected_cost_usd REAL NOT NULL
                    )
                """)
                
                # Indexes for fast querying in OnionBook
                conn.execute("CREATE INDEX IF NOT EXISTS idx_ledger_project ON ledger_entries (project_name)")
                conn.execute("CREATE INDEX IF NOT EXISTS idx_ledger_session ON ledger_entries (session_id)")

    def record_cost(
        self,
        project_name: str,
        session_id: str,
        node_type: str,
        agent_name: str,
        tool_name: str,
        model_name: str,
        media_type: str,
        cost_usd: float,
        canonization_status: str = "uncanonized"
    ) -> None:
        timestamp = datetime.now(timezone.utc).isoformat()
        with contextlib.closing(self._get_connection()) as conn:
            with conn:
                conn.execute("""
                    INSERT INTO ledger_entries (
                        timestamp, project_name, session_id, node_type,
                        agent_name, tool_name, model_name, media_type, cost_usd, canonization_status
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    timestamp, project_name, session_id, node_type,
                    agent_name, tool_name, model_name, media_type, cost_usd, canonization_status
                ))

    def get_aggregated_costs(
        self,
        project_name: Optional[str] = None,
        session_id: Optional[str] = None
    ) -> float:
        query = "SELECT SUM(cost_usd) as total FROM ledger_entries WHERE 1=1"
        params = []
        if project_name:
            query += " AND project_name = ?"
            params.append(project_name)
        if session_id:
            query += " AND session_id = ?"
            params.append(session_id)
            
        with contextlib.closing(self._get_connection()) as conn:
            row = conn.execute(query, params).fetchone()
            return float(row["total"] or 0.0)

    def get_ledger_entries(self, filters: Dict[str, Any]) -> List[Dict[str, Any]]:
        query = "SELECT * FROM ledger_entries WHERE 1=1"
        params = []
        
        for k, v in filters.items():
            query += f" AND {k} = ?"
            params.append(v)
            
        query += " ORDER BY timestamp DESC"
        
        with contextlib.closing(self._get_connection()) as conn:
            rows = conn.execute(query, params).fetchall()
            return [dict(r) for r in rows]

    def record_budget_projection(
        self,
        project_name: str,
        session_id: str,
        projected_cost_usd: float,
        timestamp_iso: str
    ) -> None:
        with contextlib.closing(self._get_connection()) as conn:
            with conn:
                conn.execute("""
                    INSERT INTO budget_projections (timestamp, project_name, session_id, projected_cost_usd)
                    VALUES (?, ?, ?, ?)
                """, (timestamp_iso, project_name, session_id, projected_cost_usd))

    def update_health_metrics(
        self,
        project_name: str,
        fail_rate: float,
        canonization_ratio: float,
        size_ratio_04_05: float
    ) -> None:
        timestamp = datetime.now(timezone.utc).isoformat()
        with contextlib.closing(self._get_connection()) as conn:
            with conn:
                conn.execute("""
                    INSERT INTO health_metrics (project_name, last_updated, fail_rate, canonization_ratio, size_ratio_04_05)
                    VALUES (?, ?, ?, ?, ?)
                    ON CONFLICT(project_name) DO UPDATE SET
                        last_updated = excluded.last_updated,
                        fail_rate = excluded.fail_rate,
                        canonization_ratio = excluded.canonization_ratio,
                        size_ratio_04_05 = excluded.size_ratio_04_05
                """, (project_name, timestamp, fail_rate, canonization_ratio, size_ratio_04_05))

    def get_health_metrics(self, project_name: str) -> Optional[Dict[str, Any]]:
        with contextlib.closing(self._get_connection()) as conn:
            row = conn.execute("SELECT * FROM health_metrics WHERE project_name = ?", (project_name,)).fetchone()
            if row:
                return dict(row)
            return None

    def close(self) -> None:
        pass
