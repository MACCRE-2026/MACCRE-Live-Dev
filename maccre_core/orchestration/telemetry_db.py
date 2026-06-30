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
maccre_core/orchestration/telemetry_db.py
==========================================
The Telemetry Matrix — four WAL-mode SQLite silos with a universal
composite tagging structure across all tables.

Silo layout (all under B:/MACCREv2/__DATACENTER/telemetry/):
  system_logs.db      — agent actions, topology hops, FinOps cost events
  user_interactions.db — Architect / API inputs and their context tags
  terminal_logs.db    — live venv subprocess commands and their output

Definitions silo (B:/MACCREv2/__DATACENTER/telemetry/):
  definitions.db      — topology_library: proven topologies promoted from CSV

All tables share the universal header:
  id, session_id, project_id, agent_id, source_node, timestamp

WAL is enforced on every connection open (PRAGMA journal_mode=WAL) so
concurrent swarm workers can read/write without SQLITE_BUSY.
"""
from __future__ import annotations

import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Generator

from maccre_core.utils.path_resolver import get_datacenter_path

def _get_telemetry_dir() -> str:
    return str(get_datacenter_path("telemetry"))

def get_db_path(db_name: str) -> str:
    return os.path.join(_get_telemetry_dir(), db_name)

_UNIVERSAL_HEADER = """
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id  TEXT    NOT NULL DEFAULT '',
    project_id  TEXT    NOT NULL DEFAULT '',
    agent_id    TEXT    NOT NULL DEFAULT '',
    source_node TEXT    NOT NULL DEFAULT '',
    timestamp   DATETIME DEFAULT CURRENT_TIMESTAMP
"""


@contextmanager
def _wal_conn(db_path: str) -> Generator[sqlite3.Connection, None, None]:
    """Open a WAL-mode connection and guarantee close on exit."""
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    conn = sqlite3.connect(db_path)
    try:
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA synchronous=NORMAL;")
        yield conn
        conn.commit()
    finally:
        conn.close()


def _add_column_if_missing(conn: sqlite3.Connection, table: str, column: str, col_def: str) -> None:
    """Add a column to an existing table only if it does not already exist."""
    existing = {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}
    if column not in existing:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {col_def}")



def init_all_silos() -> None:
    """
    Idempotently creates all four telemetry databases and their tables.
    Safe to call on every application start.
    """
    # 1. system_logs
    with _wal_conn(get_db_path("system_logs.db")) as conn:
        conn.execute(f"""
            CREATE TABLE IF NOT EXISTS system_logs (
                {_UNIVERSAL_HEADER},
                action_type   TEXT NOT NULL DEFAULT '',
                payload       TEXT NOT NULL DEFAULT '',
                cost          REAL NOT NULL DEFAULT 0.0,
                model_id      TEXT NOT NULL DEFAULT '',
                input_tokens  INTEGER NOT NULL DEFAULT 0,
                output_tokens INTEGER NOT NULL DEFAULT 0
            )
        """)
        # Idempotent migration: add columns to existing DBs that predate this schema
        _add_column_if_missing(conn, "system_logs", "model_id",      "TEXT NOT NULL DEFAULT ''")
        _add_column_if_missing(conn, "system_logs", "input_tokens",  "INTEGER NOT NULL DEFAULT 0")
        _add_column_if_missing(conn, "system_logs", "output_tokens", "INTEGER NOT NULL DEFAULT 0")

    # 2. user_interactions
    with _wal_conn(get_db_path("user_interactions.db")) as conn:
        conn.execute(f"""
            CREATE TABLE IF NOT EXISTS user_interactions (
                {_UNIVERSAL_HEADER},
                input_text   TEXT NOT NULL DEFAULT '',
                context_tags TEXT NOT NULL DEFAULT ''
            )
        """)

    # 3. terminal_logs
    with _wal_conn(get_db_path("terminal_logs.db")) as conn:
        conn.execute(f"""
            CREATE TABLE IF NOT EXISTS terminal_logs (
                {_UNIVERSAL_HEADER},
                command_run TEXT    NOT NULL DEFAULT '',
                std_output  TEXT    NOT NULL DEFAULT '',
                is_error    BOOLEAN NOT NULL DEFAULT 0
            )
        """)

    # 5. definitions — topology_library (8-column parity with topology.csv)
    with _wal_conn(get_db_path("definitions.db")) as conn:
        conn.execute(f"""
            CREATE TABLE IF NOT EXISTS topology_library (
                {_UNIVERSAL_HEADER},
                node_id             TEXT NOT NULL DEFAULT '',
                agent_name          TEXT NOT NULL DEFAULT '',
                model_override      TEXT NOT NULL DEFAULT '',
                auto_tool           TEXT NOT NULL DEFAULT '',
                next_node           TEXT NOT NULL DEFAULT '',
                output_file         TEXT NOT NULL DEFAULT '',
                temperature         REAL NOT NULL DEFAULT 0.7,
                instruction_override TEXT NOT NULL DEFAULT '',
                topology_name       TEXT NOT NULL DEFAULT '',
                job_id              TEXT NOT NULL DEFAULT ''
            )
        """)


# ── Fast Isolated Insert Methods ──────────────────────────────────────────────

def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def log_system_event(
    action_type: str,
    payload: str,
    cost: float = 0.0,
    session_id: str = "",
    project_id: str = "",
    agent_id: str = "",
    source_node: str = "",
    model_id: str = "",
    input_tokens: int = 0,
    output_tokens: int = 0,
) -> None:
    """Log an agent action, routing hop, or FinOps cost event to system_logs.db."""
    with _wal_conn(get_db_path("system_logs.db")) as conn:
        conn.execute(
            "INSERT INTO system_logs "
            "(session_id, project_id, agent_id, source_node, timestamp, "
            " action_type, payload, cost, model_id, input_tokens, output_tokens) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (session_id, project_id, agent_id, source_node, _now(),
             action_type, payload, cost, model_id, input_tokens, output_tokens),
        )


def log_user_interaction(
    input_text: str,
    context_tags: str = "",
    session_id: str = "",
    project_id: str = "",
    agent_id: str = "",
    source_node: str = "",
) -> None:
    """Log an Architect input or API invocation to user_interactions.db."""
    with _wal_conn(get_db_path("user_interactions.db")) as conn:
        conn.execute(
            "INSERT INTO user_interactions "
            "(session_id, project_id, agent_id, source_node, timestamp, input_text, context_tags) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (session_id, project_id, agent_id, source_node, _now(), input_text, context_tags),
        )


def log_terminal_command(
    command_run: str,
    std_output: str,
    is_error: bool = False,
    session_id: str = "",
    project_id: str = "",
    agent_id: str = "",
    source_node: str = "",
) -> None:
    """Log a completed venv subprocess command and its aggregated output to terminal_logs.db."""
    with _wal_conn(get_db_path("terminal_logs.db")) as conn:
        conn.execute(
            "INSERT INTO terminal_logs "
            "(session_id, project_id, agent_id, source_node, timestamp, command_run, std_output, is_error) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (session_id, project_id, agent_id, source_node, _now(),
             command_run, std_output, 1 if is_error else 0),
        )


def promote_topology_row(
    node_id: str,
    agent_name: str,
    model_override: str,
    auto_tool: str,
    next_node: str,
    output_file: str,
    temperature: float,
    instruction_override: str,
    topology_name: str,
    job_id: str,
    session_id: str = "",
    project_id: str = "",
    agent_id: str = "",
    source_node: str = "",
) -> None:
    """Promote a single topology row into the definitions.db topology_library.

    Called once per node after a successful [STOP] terminal so proven
    topologies accumulate as queryable institutional memory.
    """
    with _wal_conn(get_db_path("definitions.db")) as conn:
        conn.execute(
            "INSERT INTO topology_library "
            "(session_id, project_id, agent_id, source_node, timestamp, "
            " node_id, agent_name, model_override, auto_tool, next_node, "
            " output_file, temperature, instruction_override, topology_name, job_id) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                session_id, project_id, agent_id, source_node, _now(),
                node_id, agent_name, model_override, auto_tool, next_node,
                output_file, temperature, instruction_override, topology_name, job_id,
            ),
        )


# ── Auto-init on import ───────────────────────────────────────────────────────
init_all_silos()
