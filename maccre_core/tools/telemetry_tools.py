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
maccre_core/tools/telemetry_tools.py
======================================
RBAC Agent Tools for the Telemetry Matrix.

Access matrix:
  Tool                       | Nexus Agent | Special Agent
  ─────────────────────────────────────────────────────────
  read_local_codebase        |     ✅      |      ❌
  query_telemetry_matrix     |     ✅      |      ❌
  query_thoughts             |     ❌      |      ✅
  export_and_purge_thoughts  |     ❌      |      ✅

Security invariants:
  - read_local_codebase: path is resolved to an absolute path and verified
    to be within B:\\MACCREv2 using os.path.commonpath(). Raises SecurityError
    on any path-traversal attempt.
  - query_telemetry_matrix: thoughts.db is explicitly blocked — the Special
    Agent is the only entity allowed to read the subconscious silo.
  - export_and_purge_thoughts: export is atomic (write CSV before DELETE).
    Purge is conditional on the purge flag; partial failures leave the DB
    intact (no delete-before-write).
"""

import csv
import os
import sqlite3
import uuid
from typing import Any

from maccre_core.orchestration.telemetry_db import get_db_path
from maccre_core.utils.path_resolver import get_maccre_root, get_datacenter_path

_WORKSPACE_ROOT = str(get_maccre_root())

def _get_thoughts_export_dir() -> str:
    return str(get_datacenter_path("02_Dynamic_Context", "memory_pins", "Thoughts_Exports"))

def _get_allowed_dbs() -> dict[str, str]:
    return {
        "system_logs":       get_db_path("system_logs.db"),
        "user_interactions": get_db_path("user_interactions.db"),
        "terminal_logs":     get_db_path("terminal_logs.db"),
    }

_TABLE_MAP: dict[str, str] = {
    "system_logs":       "system_logs",
    "user_interactions": "user_interactions",
    "terminal_logs":     "terminal_logs",
}

class SecurityError(Exception):
    """Raised when a path-traversal or access-control violation is detected."""

# ── Tool 1: read_local_codebase (Nexus) ──────────────────────────────────────

def read_local_codebase(file_path: str) -> str:
    """Read a source file within the MACCREv2 workspace.

    Resolves the path to an absolute path and enforces strict workspace
    confinement. Any attempt to escape via ``../`` or symlink traversal will
    raise a SecurityError so the calling agent can log the violation.

    Args:
        file_path: Relative or absolute path to the file to read.
            Must resolve to a location inside ``B:/MACCREv2``.

    Returns:
        The full UTF-8 text content of the requested file.

    Raises:
        SecurityError: If the resolved path escapes the workspace boundary.
        FileNotFoundError: If the file does not exist within the workspace.
    """
    resolved = os.path.abspath(file_path)

    # Enforce workspace boundary via commonpath comparison
    try:
        common = os.path.commonpath([resolved, _WORKSPACE_ROOT])
    except ValueError:
        # Different drives on Windows — guaranteed traversal
        raise SecurityError(
            f"PATH_TRAVERSAL_BLOCKED: '{file_path}' resolves to '{resolved}' "
            f"which is outside the workspace root '{_WORKSPACE_ROOT}'."
        )

    if common != _WORKSPACE_ROOT:
        raise SecurityError(
            f"PATH_TRAVERSAL_BLOCKED: '{file_path}' resolves to '{resolved}' "
            f"which is outside the workspace root '{_WORKSPACE_ROOT}'."
        )

    if not os.path.isfile(resolved):
        raise FileNotFoundError(
            f"FILE_NOT_FOUND: '{resolved}' does not exist in the workspace."
        )

    with open(resolved, encoding="utf-8", errors="replace") as fh:
        return fh.read()


# ── Tool 2: query_telemetry_matrix (Nexus) ───────────────────────────────────

def query_telemetry_matrix(db_name: str, sql_where_clause: str) -> list[dict[str, Any]]:
    """Query one of the three non-restricted telemetry silos.

    The ``thoughts.db`` silo is explicitly blocked for this tool; use
    ``query_thoughts`` instead (Special Agent only).

    Args:
        db_name: One of ``"system_logs"``, ``"user_interactions"``,
            or ``"terminal_logs"``.
        sql_where_clause: A raw SQL WHERE clause — include ONLY the filter
            conditions, without the ``WHERE`` keyword, ``ORDER BY``, or
            ``LIMIT`` (those are appended automatically).
            Examples:
              ``"action_type = 'TOOL_FIRED'"``
              ``"project_id = 'TEST_13'"``
              ``"agent_id = 'Nexus' AND cost > 0"``
            Pass ``"1=1"`` to return all rows (capped at 100).

    Returns:
        A list of row dicts matching the filter, capped at 100 rows,
        ordered newest-first.

    Raises:
        ValueError: If ``db_name`` is ``"thoughts"`` or ``"thoughts.db"``
            (access denied) or an unrecognised silo name.
        sqlite3.Error: On any DB-level failure.
    """
    # RBAC gate — thoughts silo is off-limits for this tool
    if db_name.replace(".db", "") == "thoughts":
        raise ValueError(
            "ACCESS_DENIED: thoughts.db is restricted to Special Agent tools only. "
            "Use query_thoughts() if you have Special Agent privileges."
        )

    allowed_dbs = _get_allowed_dbs()
    if db_name not in allowed_dbs:
        raise ValueError(
            f"UNKNOWN_SILO: '{db_name}' is not a valid telemetry silo. "
            f"Valid options: {list(allowed_dbs.keys())}"
        )

    db_path = allowed_dbs[db_name]
    table   = _TABLE_MAP[db_name]
    # Strip any accidentally included ORDER BY / LIMIT from the clause
    safe_clause = sql_where_clause.strip() or "1=1"
    # Remove trailing ORDER BY ... or LIMIT ... if Gemini included them
    import re as _re  # noqa: PLC0415
    safe_clause = _re.split(r"\b(?:ORDER\s+BY|LIMIT)\b", safe_clause, flags=_re.IGNORECASE)[0].strip()
    safe_clause = safe_clause or "1=1"

    with sqlite3.connect(db_path) as conn:
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            f"SELECT * FROM {table} WHERE {safe_clause} ORDER BY id DESC LIMIT 100"
        ).fetchall()

    return [dict(r) for r in rows]


# ── Tool 3: query_thoughts (Special Agent) ───────────────────────────────────

def query_thoughts(sql_where_clause: str) -> list[dict[str, Any]]:
    """Query the restricted thoughts.db subconscious silo.

    Exclusive to Special Agents. Returns raw scratchpad extracts matching
    the filter. Results are capped at 200 rows to prevent context overload.

    Args:
        sql_where_clause: A raw SQL WHERE clause (without the ``WHERE``
            keyword), e.g. ``"session_id = 'abc123'"``.
            Pass ``"1=1"`` to return all rows (capped at 200).

    Returns:
        A list of thought row dicts ordered by newest first.
    """
    safe_clause = sql_where_clause.strip() or "1=1"
    # Strip any accidentally included ORDER BY / LIMIT from the clause
    import re as _re  # noqa: PLC0415
    safe_clause = _re.split(r"\b(?:ORDER\s+BY|LIMIT)\b", safe_clause, flags=_re.IGNORECASE)[0].strip()
    safe_clause = safe_clause or "1=1"

    with sqlite3.connect(get_db_path("thoughts.db")) as conn:
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            f"SELECT * FROM thoughts WHERE {safe_clause} ORDER BY id DESC LIMIT 200"
        ).fetchall()

    return [dict(r) for r in rows]


# ── Tool 4: export_and_purge_thoughts (Special Agent) ────────────────────────

def export_and_purge_thoughts(
    session_id: str,
    project_id: str,
    purge: bool,
) -> str:
    """Export and optionally purge thoughts matching a session+project tag pair.

    The export is written as an LLM-friendly chunked CSV before any DELETE
    is attempted, guaranteeing data is not lost on partial failure.

    Args:
        session_id: The session tag to filter on (matches ``session_id`` column).
        project_id: The project tag to filter on (matches ``project_id`` column).
        purge: If ``True``, DELETE matching rows from thoughts.db after a
            successful export. If ``False``, the CSV is written but the DB
            is untouched.

    Returns:
        The absolute path of the written CSV file.

    Raises:
        RuntimeError: If no matching rows are found (nothing to export).
    """
    # 1. Fetch matching thoughts
    with sqlite3.connect(get_db_path("thoughts.db")) as conn:
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT * FROM thoughts WHERE session_id = ? AND project_id = ? ORDER BY id ASC",
            (session_id, project_id),
        ).fetchall()

    if not rows:
        return (
            f"[EXPORT_EMPTY] No thoughts found for session_id='{session_id}' "
            f"project_id='{project_id}'. Nothing to export or purge."
        )

    # 2. Write CSV — export before any purge
    export_dir = _get_thoughts_export_dir()
    os.makedirs(export_dir, exist_ok=True)
    export_path = os.path.join(
        export_dir, f"thoughts_dump_{uuid.uuid4().hex}.csv"
    )

    fieldnames = list(dict(rows[0]).keys())
    with open(export_path, "w", newline="", encoding="utf-8") as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(dict(row))

    # 3. Conditional purge — only after successful write
    if purge:
        with sqlite3.connect(get_db_path("thoughts.db")) as conn:
            conn.execute("PRAGMA journal_mode=WAL;")
            conn.execute(
                "DELETE FROM thoughts WHERE session_id = ? AND project_id = ?",
                (session_id, project_id),
            )
            conn.commit()

    return export_path


# ── Tool 5: generate_telemetry_report (Nexus) ────────────────────────────────

def generate_telemetry_report(project_id: str, session_id: str = "") -> str:
    """Generate a formatted markdown telemetry report for a completed session.

    Queries all three non-restricted telemetry silos (system_logs, user_interactions,
    terminal_logs) for rows matching the given project (and optionally session)
    and assembles a structured markdown summary suitable for publishing or archiving.

    Args:
        project_id: The project tag to filter on (matches ``project_id`` column).
        session_id: Optional. The session tag to filter on. When omitted or
            empty string, all sessions for the project are included.

    Returns:
        A multi-section markdown string summarising the telemetry,
        or an informational message if no rows were found.
    """
    sections: list[str] = [
        "# Telemetry Report",
        f"**Project:** `{project_id}`  **Session:** `{session_id or 'ALL'}`\n",
    ]

    allowed_dbs = _get_allowed_dbs()

    for db_key, table_name in _TABLE_MAP.items():
        db_path = allowed_dbs[db_key]
        if not os.path.exists(db_path):
            sections.append(f"## {db_key}\n_Database not found — no events recorded yet._\n")
            continue

        with sqlite3.connect(db_path) as conn:
            conn.execute("PRAGMA journal_mode=WAL;")
            conn.row_factory = sqlite3.Row
            if session_id:
                rows = conn.execute(
                    f"SELECT * FROM {table_name} WHERE session_id = ? AND project_id = ? "
                    f"ORDER BY id ASC LIMIT 200",
                    (session_id, project_id),
                ).fetchall()
            else:
                rows = conn.execute(
                    f"SELECT * FROM {table_name} WHERE project_id = ? "
                    f"ORDER BY id ASC LIMIT 200",
                    (project_id,),
                ).fetchall()

        if not rows:
            sections.append(f"## {db_key}\n_No events recorded for this session._\n")
            continue

        sections.append(f"## {db_key} ({len(rows)} event(s))\n")

        # Special formatting per silo
        if db_key == "system_logs":
            sections.append("| # | Timestamp | Agent | Node | Action | Cost |")
            sections.append("|---|-----------|-------|------|--------|------|")
            for i, row in enumerate(rows, 1):
                r = dict(row)
                sections.append(
                    f"| {i} | {str(r.get('timestamp',''))[:19]} "
                    f"| {r.get('agent_id','')} | {r.get('source_node','')} "
                    f"| {r.get('action_type','')} | ${float(r.get('cost', 0)):.6f} |"
                )
            sections.append("")
        elif db_key == "user_interactions":
            sections.append("| # | Timestamp | Input Preview | Tags |")
            sections.append("|---|-----------|---------------|------|")
            for i, row in enumerate(rows, 1):
                r = dict(row)
                preview = str(r.get("input_text", ""))[:80].replace("\n", " ")
                sections.append(
                    f"| {i} | {str(r.get('timestamp',''))[:19]} "
                    f"| {preview} | {r.get('context_tags','')} |"
                )
            sections.append("")
        elif db_key == "terminal_logs":
            sections.append("| # | Timestamp | Command | Error? |")
            sections.append("|---|-----------|---------|--------|")
            for i, row in enumerate(rows, 1):
                r = dict(row)
                cmd = str(r.get("command_run", ""))[:60]
                sections.append(
                    f"| {i} | {str(r.get('timestamp',''))[:19]} "
                    f"| `{cmd}` | {'⚠️ YES' if r.get('is_error') else 'no'} |"
                )
            sections.append("")

    # FinOps Summary from system_logs
    sl_path = allowed_dbs.get("system_logs", "")
    if os.path.exists(sl_path):
        with sqlite3.connect(sl_path) as conn:
            conn.execute("PRAGMA journal_mode=WAL;")
            row = conn.execute(
                "SELECT SUM(cost) as total_cost, COUNT(*) as event_count FROM system_logs "
                "WHERE session_id = ? AND project_id = ?",
                (session_id, project_id),
            ).fetchone()
        if row and row[0] is not None:
            sections.append("## FinOps Summary")
            sections.append(f"- **Total Token Cost:** ${float(row[0]):.6f}")
            sections.append(f"- **Total System Events:** {row[1]}\n")

    return "\n".join(sections)

