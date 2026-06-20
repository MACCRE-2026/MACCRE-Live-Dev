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
maccre_core/utils/session_manager.py
======================================
Session ID generation and registration for the MACCREv2 Workbook Sovereign model.

Every swarm run, ingest pass, or workbook execution is stamped with a unique
session_id in the format: YYYYMMDD-HHMMSS-{4rand}[-label]

Sessions are registered into project_registry.db for full audit traceability.
Output filenames are produced as: {project}-{session_id}.{ext}
"""
from __future__ import annotations

import random
import sqlite3
import string
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from maccre_core.utils.path_resolver import get_maccre_root


# ── ID Generation ─────────────────────────────────────────────────────────────


def generate_session_id(label: str = "") -> str:
    """Generate a unique, timestamped session ID.

    Args:
        label: Optional human-readable tag appended to the base ID.
                e.g. 'chapter_2_draft' → '20260416-154500-a3k9-chapter_2_draft'

    Returns:
        Session ID string suitable for use in filenames and DB keys.
    """
    rand = "".join(random.choices(string.ascii_lowercase + string.digits, k=4))
    ts = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    base = f"{ts}-{rand}"
    return f"{base}-{label}" if label.strip() else base


def get_output_name(project: str, session_id: str, ext: str) -> str:
    """Produce a standardised output filename: {project}-{session_id}.{ext}.

    Args:
        project:    Active project name.
        session_id: Session ID from generate_session_id().
        ext:        File extension without leading dot.

    Returns:
        Filename string e.g. 'QUANTUM_001-20260416-154500-a3k9.md'
    """
    return f"{project}-{session_id}.{ext.lstrip('.')}"


# ── Registry ──────────────────────────────────────────────────────────────────


def _registry_path() -> Path:
    """Return the absolute path to project_registry.db at the MACCRE root."""
    return get_maccre_root() / "project_registry.db"


def _ensure_registry() -> None:
    """Idempotently create project_registry.db schema if not present."""
    db = str(_registry_path())
    with sqlite3.connect(db) as conn:
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("""
            CREATE TABLE IF NOT EXISTS projects (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                project_name    TEXT NOT NULL UNIQUE,
                description     TEXT NOT NULL DEFAULT '',
                linked_projects TEXT NOT NULL DEFAULT '',
                created_at      DATETIME DEFAULT CURRENT_TIMESTAMP,
                last_active_at  DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS sessions (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id      TEXT NOT NULL UNIQUE,
                project_name    TEXT NOT NULL,
                label           TEXT NOT NULL DEFAULT '',
                workbook_type   TEXT NOT NULL DEFAULT 'session',
                sections_run    TEXT NOT NULL DEFAULT '',
                est_cost_usd    REAL NOT NULL DEFAULT 0.0,
                actual_cost_usd REAL NOT NULL DEFAULT 0.0,
                status          TEXT NOT NULL DEFAULT 'started',
                created_at      DATETIME DEFAULT CURRENT_TIMESTAMP,
                completed_at    DATETIME
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS flow_history (
                id               INTEGER PRIMARY KEY AUTOINCREMENT,
                job_id           TEXT NOT NULL UNIQUE,
                project_name     TEXT NOT NULL,
                flow_steps_json  TEXT NOT NULL,
                initial_payload  TEXT NOT NULL DEFAULT '',
                final_artifact   TEXT NOT NULL DEFAULT '',
                total_cost       REAL NOT NULL DEFAULT 0.0,
                status           TEXT NOT NULL DEFAULT 'running',
                created_at       DATETIME DEFAULT CURRENT_TIMESTAMP,
                completed_at     DATETIME
            )
        """)
        conn.commit()


def register_project(
    project_name: str,
    description: str = "",
    linked_projects: list[str] | None = None,
) -> None:
    """Upsert a project record into project_registry.db.

    Args:
        project_name:    Unique project silo name.
        description:     Human-readable project brief.
        linked_projects: List of sibling project names for Synaptic Bridge.
    """
    _ensure_registry()
    linked = ",".join(linked_projects or [])
    db = str(_registry_path())
    with sqlite3.connect(db) as conn:
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("""
            INSERT INTO projects (project_name, description, linked_projects)
            VALUES (?, ?, ?)
            ON CONFLICT(project_name) DO UPDATE SET
                description     = excluded.description,
                linked_projects = excluded.linked_projects,
                last_active_at  = CURRENT_TIMESTAMP
        """, (project_name, description, linked))
        conn.commit()


def register_session(
    project_name: str,
    session_id: str,
    label: str = "",
    workbook_type: str = "session",
    sections_run: list[str] | None = None,
    est_cost_usd: float = 0.0,
) -> None:
    """Insert a new session record into project_registry.db.

    Args:
        project_name:  Owning project silo name.
        session_id:    Generated ID from generate_session_id().
        label:         Optional human readable tag.
        workbook_type: 'global' or 'session'.
        sections_run:  List of workbook sections that were executed.
        est_cost_usd:  Pre-run FinOps estimate.
    """
    _ensure_registry()
    sections = ",".join(sections_run or [])
    db = str(_registry_path())
    with sqlite3.connect(db) as conn:
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("""
            INSERT OR IGNORE INTO sessions
                (session_id, project_name, label, workbook_type, sections_run, est_cost_usd)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (session_id, project_name, label, workbook_type, sections, est_cost_usd))
        conn.commit()


def complete_session(session_id: str, actual_cost_usd: float = 0.0) -> None:
    """Mark a session as completed with actual cost in project_registry.db.

    Args:
        session_id:      The session to close.
        actual_cost_usd: Actual cost scraped from swarm_queue.db after run.
    """
    _ensure_registry()
    db = str(_registry_path())
    with sqlite3.connect(db) as conn:
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("""
            UPDATE sessions SET
                status          = 'completed',
                actual_cost_usd = ?,
                completed_at    = CURRENT_TIMESTAMP
            WHERE session_id = ?
        """, (actual_cost_usd, session_id))
        conn.commit()


def list_projects() -> list[dict[str, str]]:
    """Return all registered projects ordered by last activity.

    Returns:
        List of dicts with keys: project_name, description, linked_projects,
        created_at, last_active_at.
    """
    _ensure_registry()
    db = str(_registry_path())
    with sqlite3.connect(db) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT * FROM projects ORDER BY last_active_at DESC"
        ).fetchall()
    return [dict(r) for r in rows]


def get_project_sessions(project_name: str, limit: int = 20) -> list[dict[str, str]]:
    """Return recent sessions for a project.

    Args:
        project_name: Target project.
        limit:        Maximum rows to return.

    Returns:
        List of session dicts ordered by created_at DESC.
    """
    _ensure_registry()
    db = str(_registry_path())
    with sqlite3.connect(db) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT * FROM sessions WHERE project_name = ? ORDER BY created_at DESC LIMIT ?",
            (project_name, limit),
        ).fetchall()
    return [dict(r) for r in rows]


# ── Flow History ──────────────────────────────────────────────────────────────


def save_flow_history(
    job_id: str,
    project_name: str,
    flow_steps_json: str,
    initial_payload: str = "",
    final_artifact: str = "",
    total_cost: float = 0.0,
    status: str = "completed",
) -> None:
    """Persist a completed (or failed) flow execution for the history browser.

    Args:
        job_id:          Unique job identifier from the flow run.
        project_name:    Owning project silo name.
        flow_steps_json: JSON-serialized list of FlowStep dicts.
        initial_payload: Path to the original payload used at launch.
        final_artifact:  Path to the final output artifact.
        total_cost:      Total API cost incurred.
        status:          'completed' or 'failed'.
    """
    _ensure_registry()
    db = str(_registry_path())
    with sqlite3.connect(db) as conn:
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("""
            INSERT INTO flow_history
                (job_id, project_name, flow_steps_json, initial_payload,
                 final_artifact, total_cost, status, completed_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(job_id) DO UPDATE SET
                final_artifact = excluded.final_artifact,
                total_cost     = excluded.total_cost,
                status         = excluded.status,
                completed_at   = CURRENT_TIMESTAMP
        """, (job_id, project_name, flow_steps_json, initial_payload,
              final_artifact, total_cost, status))
        conn.commit()


def list_completed_flows(
    project_name: str = "",
    limit: int = 50,
) -> list[dict[str, Any]]:
    """Return completed flows with artifacts, optionally filtered by project.

    Args:
        project_name: If non-empty, filter to this project only.
        limit:        Maximum rows to return.

    Returns:
        List of flow history dicts ordered by completed_at DESC.
    """
    _ensure_registry()
    db = str(_registry_path())
    with sqlite3.connect(db) as conn:
        conn.row_factory = sqlite3.Row
        if project_name:
            rows = conn.execute(
                "SELECT * FROM flow_history "
                "WHERE project_name = ? AND status = 'completed' "
                "ORDER BY completed_at DESC LIMIT ?",
                (project_name, limit),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM flow_history "
                "WHERE status = 'completed' "
                "ORDER BY completed_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
    return [dict(r) for r in rows]


def load_flow_history(job_id: str) -> dict[str, Any] | None:
    """Load a single flow history record by job_id.

    Returns:
        Dict with all columns, or None if not found.
    """
    _ensure_registry()
    db = str(_registry_path())
    with sqlite3.connect(db) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT * FROM flow_history WHERE job_id = ?",
            (job_id,),
        ).fetchone()
    return dict(row) if row else None
