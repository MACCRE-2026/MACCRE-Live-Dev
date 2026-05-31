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
maccre_core/orchestration/session_registry.py
=============================================
Global Ledger for Session Validation.
Ensures bespoke UUIDs are uniquely registered and only used once
to prevent multi-tenant index corruption.
"""

import os
import sqlite3
from datetime import datetime, timezone

from maccre_core.utils.path_resolver import get_maccre_root
from maccre_core.utils.session_utils import generate_short_uuid

_GLOBAL_REGISTRY_DIR = str(get_maccre_root() / "__DATACENTER" / "__GLOBAL_LEDGER")
_REGISTRY_DB = os.path.join(_GLOBAL_REGISTRY_DIR, "session_registry.db")

def _init_registry() -> None:
    os.makedirs(_GLOBAL_REGISTRY_DIR, exist_ok=True)
    with sqlite3.connect(_REGISTRY_DB) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS global_sessions (
                session_id TEXT PRIMARY KEY,
                project_name TEXT NOT NULL,
                status TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                used_at TIMESTAMP
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_status ON global_sessions(status)")
        conn.commit()

# Ensure schema exists on module import
_init_registry()

def register_session(project_name: str) -> str:
    """Generates and registers a new unique session ID for a project."""
    max_retries = 5
    for _ in range(max_retries):
        session_id = generate_short_uuid()
        try:
            with sqlite3.connect(_REGISTRY_DB) as conn:
                conn.execute(
                    "INSERT INTO global_sessions (session_id, project_name, status) VALUES (?, ?, ?)",
                    (session_id, project_name, "REGISTERED")
                )
                conn.commit()
            return session_id
        except sqlite3.IntegrityError:
            # Collision occurred (extremely rare with Base62 but handled), retry loop.
            continue
            
    raise RuntimeError("CRITICAL: Failed to generate unique session ID after maximum retries.")

def validate_and_consume_session(session_id: str, project_name: str) -> bool:
    """
    Validates that a session exists, belongs to the project, and hasn't been used yet.
    If valid, marks it as USED. Returns True if authorized, False if rejected.
    """
    with sqlite3.connect(_REGISTRY_DB) as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT status, project_name FROM global_sessions WHERE session_id = ?",
            (session_id,)
        )
        row = cursor.fetchone()
        
        if not row:
            return False
            
        status, reserved_project = row
        if status != "REGISTERED" or reserved_project != project_name:
            return False
            
        # Consume the UUID
        cursor.execute(
            "UPDATE global_sessions SET status = 'USED', used_at = ? WHERE session_id = ?",
            (datetime.now(timezone.utc).isoformat(), session_id)
        )
        conn.commit()
        return True
