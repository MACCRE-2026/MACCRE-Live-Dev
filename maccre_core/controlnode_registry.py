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
maccre_core/controlnode_registry.py
====================================
ControlNode Registry — SQLite backend for deterministic control-flow nodes.

A ControlNode is a non-AI pipeline primitive (gates, checkpoints, delays,
transforms, routing, etc.) that participates in topology execution but does
NOT invoke an LLM.  Each entry maps a canonical name to its handler module/func
plus metadata (category, schema, deprecation status).

Storage path (relative to MACCRE root):
  __DATACENTER/GLOBAL/controlnode_registry.db
"""
from __future__ import annotations

import abc
import json
import logging
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from maccre_core.utils.path_resolver import get_maccre_root

# ── Module-level logger ───────────────────────────────────────────────────────
logger = logging.getLogger(__name__)

# ── Path helpers ──────────────────────────────────────────────────────────────

_DB_FILENAME = "controlnode_registry.db"


def _db_path() -> Path:
    """Return the controlnode_registry.db path (strictly GLOBAL)."""
    return get_maccre_root() / "__DATACENTER" / "GLOBAL" / _DB_FILENAME


# ── Abstract Interface ────────────────────────────────────────────────────────

class ControlNodeStore(abc.ABC):
    """ABC for ControlNode persistence."""

    @abc.abstractmethod
    def get(self, name: str) -> dict[str, Any]:
        """Return ControlNode dict with all fields. Raises KeyError if not found."""

    @abc.abstractmethod
    def list_all(self) -> list[dict[str, Any]]:
        """Return summary list of all control nodes."""

    @abc.abstractmethod
    def list_by_category(self, category: str) -> list[dict[str, Any]]:
        """Return summary list filtered by category."""

    @abc.abstractmethod
    def save(
        self,
        name: str,
        category: str,
        description: str = "",
        config_schema: dict[str, Any] | None = None,
        handler_module: str = "",
        handler_func: str = "",
        is_builtin: bool = True,
        status: str = "active",
    ) -> None:
        """Upsert a named ControlNode into the store."""

    @abc.abstractmethod
    def delete(self, name: str) -> None:
        """Remove a named ControlNode. Raises KeyError if not found."""


# ── SQLite Implementation ─────────────────────────────────────────────────────

_CREATE_SQL = """
CREATE TABLE IF NOT EXISTS controlnode_registry (
    name            TEXT PRIMARY KEY,
    category        TEXT NOT NULL,
    description     TEXT DEFAULT '',
    config_schema   TEXT DEFAULT '{}',
    handler_module  TEXT NOT NULL,
    handler_func    TEXT NOT NULL,
    is_builtin      INTEGER DEFAULT 1,
    deprecated      INTEGER DEFAULT 0,
    status          TEXT DEFAULT 'active',
    created_at      TEXT NOT NULL,
    updated_at      TEXT NOT NULL
);
"""

# ── Builtin seed data ────────────────────────────────────────────────────────

_DEFAULT_HANDLER_MODULE = "maccre_core.orchestration.deterministic_nodes"

_BUILTIN_NODES: list[dict[str, Any]] = [
    # ── Active (16) ───────────────────────────────────────────────────────────
    {
        "name": "CTRL_ANCHOR",
        "category": "Flow Control",
        "description": "Entry marker — passes payload through unchanged.",
        "handler_module": _DEFAULT_HANDLER_MODULE,
        "handler_func": "_handle_anchor",
        "status": "active",
    },
    {
        "name": "CTRL_PAUSE",
        "category": "Flow Control",
        "description": "Halts execution, sets task to paused for manual resume.",
        "handler_module": _DEFAULT_HANDLER_MODULE,
        "handler_func": "_handle_pause",
        "status": "active",
    },
    {
        "name": "CTRL_REVIEW",
        "category": "HITL",
        "description": "Live swarm intercept — pauses the task via broker route_task interception for manual resume.",
        "handler_module": "maccre_core.orchestration.local_broker",
        "handler_func": "intercept_review_via_route_task",
        "status": "active",
    },
    {
        "name": "CTRL_GATE",
        "category": "Flow Control",
        "description": "Conditional gate — blocks unless prerequisite nodes complete.",
        "handler_module": _DEFAULT_HANDLER_MODULE,
        "handler_func": "_handle_gate",
        "status": "active",
    },
    {
        "name": "CTRL_CHECKPOINT",
        "category": "State Management",
        "description": "Snapshots current payload to a checkpoint file.",
        "handler_module": _DEFAULT_HANDLER_MODULE,
        "handler_func": "_handle_checkpoint",
        "status": "active",
    },
    {
        "name": "CTRL_DELAY",
        "category": "Flow Control",
        "description": "Sleeps for a configurable number of seconds.",
        "handler_module": _DEFAULT_HANDLER_MODULE,
        "handler_func": "_handle_delay",
        "status": "active",
    },
    {
        "name": "CTRL_TRANSFORM",
        "category": "Data Flow",
        "description": "Applies a static text wrapper/template to the payload.",
        "handler_module": _DEFAULT_HANDLER_MODULE,
        "handler_func": "_handle_transform",
        "status": "active",
    },
    {
        "name": "CTRL_RECURSION",
        "category": "Loop Control",
        "description": "Loop-back control with counter tracking.",
        "handler_module": _DEFAULT_HANDLER_MODULE,
        "handler_func": "_handle_recursion",
        "status": "active",
    },
    # ── Active — Wave 3 data-flow / routing nodes ─────────────────────────────
    {
        "name": "CTRL_MERGE",
        "category": "Data Flow",
        "description": "Merges multiple upstream payloads into a single output.",
        "handler_module": _DEFAULT_HANDLER_MODULE,
        "handler_func": "_handle_merge",
        "status": "active",
        "config_schema": {
            "merge_mode": {"type": "string", "enum": ["structured", "concat"], "default": "structured"},
            "merge_delimiter": {"type": "string", "default": "\n---\n"},
        },
    },
    {
        "name": "CTRL_CONCAT",
        "category": "Data Flow",
        "description": "Concatenates payloads in topological order.",
        "handler_module": _DEFAULT_HANDLER_MODULE,
        "handler_func": "_handle_concat",
        "status": "active",
        "config_schema": {
            "concat_delimiter": {"type": "string", "default": "\n"},
        },
    },
    {
        "name": "CTRL_SCATTER",
        "category": "Data Flow",
        "description": "Fans out a single payload to multiple downstream nodes.",
        "handler_module": _DEFAULT_HANDLER_MODULE,
        "handler_func": "_handle_scatter",
        "status": "active",
        "config_schema": {
            "scatter_targets": {"type": "array", "items": {"type": "string"}, "default": []},
            "scatter_mode": {"type": "string", "enum": ["full_copy", "chunk_split"], "default": "full_copy"},
        },
    },
    {
        "name": "CTRL_BRANCH",
        "category": "Routing",
        "description": "Routes payload to one of several downstream nodes based on keyword conditions.",
        "handler_module": _DEFAULT_HANDLER_MODULE,
        "handler_func": "_handle_branch",
        "status": "active",
        "config_schema": {
            "keyword_map": {"type": "object", "additionalProperties": {"type": "string"}, "default": {}},
            "default_target": {"type": "string", "default": "END"},
        },
    },
    {
        "name": "CTRL_FILTER",
        "category": "Data Flow",
        "description": "Filters payload content — strip sections, regex removal, truncation.",
        "handler_module": _DEFAULT_HANDLER_MODULE,
        "handler_func": "_handle_filter",
        "status": "active",
        "config_schema": {
            "filter_rules": {
                "type": "object",
                "properties": {
                    "strip_sections": {"type": "array", "items": {"type": "string"}, "default": []},
                    "max_chars": {"type": "integer", "default": 0},
                    "regex_remove": {"type": "string", "default": ""},
                },
                "default": {},
            },
        },
    },
    {
        "name": "CTRL_CLEANUP",
        "category": "State Management",
        "description": "Deletes temporary files matching glob patterns in the job ledger.",
        "handler_module": _DEFAULT_HANDLER_MODULE,
        "handler_func": "_handle_cleanup",
        "status": "active",
        "config_schema": {
            "glob_patterns": {"type": "array", "items": {"type": "string"}, "default": ["*.tmp"]},
            "cleanup_dir": {"type": "string", "default": ""},
        },
    },
    {
        "name": "CTRL_END",
        "category": "Flow Control",
        "description": "Terminal node — marks flow completion. Semantic endpoint.",
        "handler_module": _DEFAULT_HANDLER_MODULE,
        "handler_func": "_handle_end",
        "status": "active",
    },
    {
        "name": "CTRL_PAYLOAD_INJECT",
        "category": "Data Flow",
        "description": "Injects a static payload string into the flow. Content configured via modal.",
        "handler_module": _DEFAULT_HANDLER_MODULE,
        "handler_func": "_handle_payload_inject",
        "status": "active",
    },
    # ── Coming Soon (8) ───────────────────────────────────────────────────────
    {
        "name": "CTRL_CONDITIONAL_ROUTE",
        "category": "Routing",
        "description": "Replaces implicit ROUTE_TO regex — explicit conditional routing.",
        "handler_module": _DEFAULT_HANDLER_MODULE,
        "handler_func": "_handle_conditional_route",
        "status": "active",
    },
    {
        "name": "CTRL_DIALOG",
        "category": "Orchestration",
        "description": "Typed group dialog dispatch between multiple agents.",
        "handler_module": "",
        "handler_func": "",
        "status": "ComingSoon",
    },
    {
        "name": "CTRL_MEDIA_PROBE",
        "category": "Media",
        "description": "Extracts metadata from media files for pipeline routing.",
        "handler_module": "",
        "handler_func": "",
        "status": "ComingSoon",
    },
    {
        "name": "CTRL_RENDER_STITCH",
        "category": "Media",
        "description": "Orchestrates ffmpeg-based media stitching pipeline.",
        "handler_module": "",
        "handler_func": "",
        "status": "ComingSoon",
    },
    {
        "name": "CTRL_MANIFEST",
        "category": "Media",
        "description": "Generates a structured manifest from produced media artifacts.",
        "handler_module": "",
        "handler_func": "",
        "status": "ComingSoon",
    },
    {
        "name": "CTRL_USER_REVIEW",
        "category": "HITL",
        "description": "Extended human review with FinOps gating and cost awareness.",
        "handler_module": "",
        "handler_func": "",
        "status": "ComingSoon",
    },
    {
        "name": "CTRL_EXTRACT",
        "category": "Data Flow",
        "description": "Extracts structured data from unstructured payload content.",
        "handler_module": "",
        "handler_func": "",
        "status": "ComingSoon",
    },
    {
        "name": "CTRL_WEBHOOK",
        "category": "External",
        "description": "Sends payload to an external webhook endpoint.",
        "handler_module": "",
        "handler_func": "",
        "status": "ComingSoon",
    },
    {
        "name": "CTRL_CHAT",
        "category": "Orchestration",
        "description": "Enables interactive chat session within a flow node.",
        "handler_module": "",
        "handler_func": "",
        "status": "ComingSoon",
    },
]


class SQLiteControlNodeStore(ControlNodeStore):
    """SQLite-backed ControlNode registry. Thread-safe via check_same_thread=False."""

    def __init__(self, db_path: Path) -> None:
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self._path = db_path
        self._bootstrap()

    def _bootstrap(self) -> None:
        conn = sqlite3.connect(str(self._path), check_same_thread=False)
        try:
            conn.execute(_CREATE_SQL)
            conn.commit()
            self._seed_builtins(conn)
        finally:
            conn.close()

    def _seed_builtins(self, conn: sqlite3.Connection) -> None:
        """Populate the registry with all 23 builtin control nodes if table is empty."""
        row = conn.execute("SELECT COUNT(*) FROM controlnode_registry").fetchone()
        if row and row[0] > 0:
            return
        now = datetime.now(timezone.utc).isoformat()
        for node in _BUILTIN_NODES:
            conn.execute(
                """INSERT INTO controlnode_registry
                   (name, category, description, config_schema,
                    handler_module, handler_func, is_builtin, deprecated,
                    status, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    node["name"],
                    node["category"],
                    node["description"],
                    json.dumps(node.get("config_schema", {})),
                    node["handler_module"],
                    node["handler_func"],
                    1,
                    0,
                    node["status"],
                    now,
                    now,
                ),
            )
        conn.commit()
        logger.info("[ControlNodeStore] Seeded %d builtin control nodes", len(_BUILTIN_NODES))

    def _conn(self) -> sqlite3.Connection:
        return sqlite3.connect(str(self._path), check_same_thread=False)

    def get(self, name: str) -> dict[str, Any]:
        conn = self._conn()
        try:
            row = conn.execute(
                "SELECT name, category, description, config_schema, "
                "handler_module, handler_func, is_builtin, deprecated, "
                "status, created_at, updated_at "
                "FROM controlnode_registry WHERE name = ?",
                (name.strip(),),
            ).fetchone()
        finally:
            conn.close()
        if not row:
            raise KeyError(f"ControlNode '{name}' not found in {self._path}")
        return {
            "name": row[0],
            "category": row[1],
            "description": row[2],
            "config_schema": json.loads(row[3]),
            "handler_module": row[4],
            "handler_func": row[5],
            "is_builtin": bool(row[6]),
            "deprecated": bool(row[7]),
            "status": row[8],
            "created_at": row[9],
            "updated_at": row[10],
        }

    def list_all(self) -> list[dict[str, Any]]:
        conn = self._conn()
        try:
            rows = conn.execute(
                "SELECT name, category, description, status, is_builtin, deprecated "
                "FROM controlnode_registry ORDER BY category, name"
            ).fetchall()
        finally:
            conn.close()
        return [
            {
                "name": r[0],
                "category": r[1],
                "description": r[2],
                "status": r[3],
                "is_builtin": bool(r[4]),
                "deprecated": bool(r[5]),
            }
            for r in rows
        ]

    def list_by_category(self, category: str) -> list[dict[str, Any]]:
        conn = self._conn()
        try:
            rows = conn.execute(
                "SELECT name, category, description, status, is_builtin, deprecated "
                "FROM controlnode_registry WHERE category = ? ORDER BY name",
                (category.strip(),),
            ).fetchall()
        finally:
            conn.close()
        return [
            {
                "name": r[0],
                "category": r[1],
                "description": r[2],
                "status": r[3],
                "is_builtin": bool(r[4]),
                "deprecated": bool(r[5]),
            }
            for r in rows
        ]

    def save(
        self,
        name: str,
        category: str,
        description: str = "",
        config_schema: dict[str, Any] | None = None,
        handler_module: str = "",
        handler_func: str = "",
        is_builtin: bool = True,
        status: str = "active",
    ) -> None:
        now = datetime.now(timezone.utc).isoformat()
        schema_json = json.dumps(config_schema) if config_schema else "{}"
        conn = self._conn()
        try:
            conn.execute(
                """INSERT INTO controlnode_registry
                   (name, category, description, config_schema,
                    handler_module, handler_func, is_builtin, deprecated,
                    status, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(name) DO UPDATE SET
                     category       = excluded.category,
                     description    = excluded.description,
                     config_schema  = excluded.config_schema,
                     handler_module = excluded.handler_module,
                     handler_func   = excluded.handler_func,
                     is_builtin     = excluded.is_builtin,
                     status         = excluded.status,
                     updated_at     = excluded.updated_at
                """,
                (
                    name.strip(),
                    category,
                    description,
                    schema_json,
                    handler_module,
                    handler_func,
                    1 if is_builtin else 0,
                    0,
                    status,
                    now,
                    now,
                ),
            )
            conn.commit()
        finally:
            conn.close()

    def delete(self, name: str) -> None:
        conn = self._conn()
        try:
            cur = conn.execute("DELETE FROM controlnode_registry WHERE name = ?", (name.strip(),))
            conn.commit()
        finally:
            conn.close()
        if cur.rowcount == 0:
            raise KeyError(f"ControlNode '{name}' not found — nothing deleted.")


# ── Public Factory ────────────────────────────────────────────────────────────

def get_controlnode_store() -> SQLiteControlNodeStore:
    """Return a SQLiteControlNodeStore backed by the GLOBAL DATACENTER path."""
    return SQLiteControlNodeStore(_db_path())
