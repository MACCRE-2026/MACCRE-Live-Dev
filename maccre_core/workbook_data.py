"""
maccre_core/workbook_data.py
==============================
Live data loaders for the MACCRE Global Workbook generator.

Reads models, projects, agents, topology rows, and session logs
from live system state so dropdowns are always current at refresh time.
"""
from __future__ import annotations

import csv
import json
import sqlite3
from typing import Any

from maccre_core.utils.path_resolver import get_maccre_root
from maccre_core.utils.session_manager import list_projects, get_project_sessions

_GLOBAL = "GLOBAL"


# ── Models ────────────────────────────────────────────────────────────────────

def load_model_ids() -> list[str]:
    """Return all text-generation model IDs from the capability map."""
    cap_path = get_maccre_root() / "scripts" / "model_capability_map.json"
    if not cap_path.exists():
        return ["gemini-2.5-flash", "gemini-2.5-pro", "gemini-3.1-pro-preview"]
    with cap_path.open(encoding="utf-8") as fh:
        data: dict[str, Any] = json.load(fh)
    models: list[str] = []
    for entry in data.values() if isinstance(data, dict) else data:
        if isinstance(entry, dict):
            mid = str(entry.get("model_id") or entry.get("name") or "")
            if mid and mid not in models:
                models.append(mid)
        elif isinstance(entry, str) and entry not in models:
            models.append(entry)
    return sorted(models) if models else ["gemini-2.5-flash"]


# ── Projects ──────────────────────────────────────────────────────────────────

def load_project_names() -> list[str]:
    """Return all registered project names + GLOBAL + any folder in __DATACENTER."""
    rows = list_projects()
    names = [r["project_name"] for r in rows if r.get("project_name")]
    
    dc_path = get_maccre_root() / "__DATACENTER"
    if dc_path.exists():
        for d in dc_path.iterdir():
            if d.is_dir() and not d.name.startswith("."):
                if d.name not in names:
                    names.append(d.name)
                    
    if _GLOBAL not in names:
        names.insert(0, _GLOBAL)
    else:
        names.remove(_GLOBAL)
        names.insert(0, _GLOBAL)
        
    return names


# ── Topology ──────────────────────────────────────────────────────────────────

def load_topology_csv(project_id: str = "") -> list[dict[str, str]]:
    """Read topology.csv from a project silo. Returns list of row dicts."""
    pid = project_id.strip() or _GLOBAL
    path = (
        get_maccre_root()
        / "__DATACENTER" / pid / "02_Dynamic_Context" / "topology.csv"
    )
    if not path.exists():
        return []
    rows: list[dict[str, str]] = []
    with path.open(newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            rows.append(dict(row))
    return rows


def load_node_ids(project_id: str = "") -> list[str]:
    """Return Node_ID list from topology.csv for a project."""
    rows = load_topology_csv(project_id)
    ids = [r.get("Node_ID", "").strip() for r in rows if r.get("Node_ID", "").strip()]
    return ids or ["NODE_01"]


# ── Agents ────────────────────────────────────────────────────────────────────

def load_agent_roster_csv(project_id: str = "") -> list[dict[str, Any]]:
    """Read agents from the agent_library.db (formerly agent_roster.csv). Returns list of row dicts."""
    from maccre_core.agent_library import get_agent_store
    
    # In the modern architecture, all agents are retrieved from the GLOBAL store
    # regardless of project_id, but we'll respect project_id if it's passed just in case.
    store = get_agent_store(project_id if project_id else "GLOBAL")
    
    # load_all() returns exactly the list of agent dictionaries we need
    return store.load_all()


def load_agent_names_from_library(project_id: str = "") -> list[str]:
    """Return agent names from the GLOBAL SQLite agent_library.db."""
    from maccre_core.agent_library import get_agent_store
    return get_agent_store("GLOBAL").get_names()


def load_topology_names_from_library(project_id: str = "") -> list[str]:
    """Return topology names from the project's topology_library.db."""
    from maccre_core.topology_library import get_topology_store
    rows = get_topology_store(project_id).list_all()
    return [r["name"] for r in rows]


# ── Sessions ──────────────────────────────────────────────────────────────────

def load_recent_sessions(project_id: str = "", limit: int = 20) -> list[dict[str, str]]:
    """Return recent session records for the given project."""
    if not project_id or project_id.upper() == _GLOBAL:
        # Pull across all projects from registry
        reg = get_maccre_root() / "project_registry.db"
        if not reg.exists():
            return []
        with sqlite3.connect(str(reg)) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT * FROM sessions ORDER BY created_at DESC LIMIT ?", (limit,)
            ).fetchall()
        return [dict(r) for r in rows]
    return get_project_sessions(project_id, limit)


# ── Registered tools ──────────────────────────────────────────────────────────

def load_tool_names() -> list[str]:
    """Return operator-facing tool names available for the AGENTS TOOLS column.

    Internal engine tools (TTS helpers, manifest builders, SDK wrappers) are
    excluded — only tools meaningful for an agent to call are listed here.
    This list is sourced from TOOL_DISPATCHER in tool_registry.py and must
    stay in sync whenever a new tool is registered.
    """
    return [
        # ── Web & OSINT ───────────────────────────────────────────────────
        "search_web", "read_url_content", "execute_hybrid_synthesis",
        # ── Memory & RAG ──────────────────────────────────────────────────
        "query_local_memory", "fts_search_memory", "ingest_document",
        "query_foreign_memory", "import_foreign_vectors", "prune_semantic_memory",
        # ── File I/O ──────────────────────────────────────────────────────
        "read_file", "write_file", "file_exists", "trash_file",
        # ── Telemetry ─────────────────────────────────────────────────────
        "query_thoughts", "query_telemetry_matrix", "read_local_codebase",
        "generate_telemetry_report", "rotate_logs",
        # ── FinOps ────────────────────────────────────────────────────────
        "estimate_manifest_cost",
        "render_cost_report",      # Post-render actual cost breakdown
        # ── Render Pipeline ───────────────────────────────────────────────
        "execute_render_pipeline",
        "render_podcast_audio",    # audio-only broadcast WAV
        "render_video",            # TTS + images → MP4 slideshow
        "render_image",            # single image from prompt
        "render_image_batch",      # concurrent multi-image batch
        # ── Orchestration ─────────────────────────────────────────────────
        "mint_agent", "build_topology", "link_projects", "ignite_swarm",
        "initialize_workspace", "switch_workspace", "request_elevation",
        "promote_topology_to_library", "recall_topology",
        "design_swarm", "run_swarm", "create_persona_card",
        # ── Sync ──────────────────────────────────────────────────────────
        "export_project_nugget", "import_project_nuggets", "list_project_nuggets",
        # ── Project Utilities ─────────────────────────────────────────────
        "ensure_project_workbook",
    ]





def load_all_agents_across_projects() -> list[str]:
    """Return every known agent name from the GLOBAL roster."""
    root = get_maccre_root() / "__DATACENTER" / "GLOBAL" / "agent_roster.csv"
    if not root.exists():
        return []
    entries: list[str] = []
    try:
        with root.open(newline="", encoding="utf-8") as fh:
            for row in csv.DictReader(fh):
                name = str(row.get("Agent_Name", row.get("agent_name", ""))).strip()
                if name:
                    entries.append(name)
    except Exception:
        pass
    return sorted(list(set(entries)))

def load_full_agent_rosters() -> dict[str, list[dict]]:
    """Return the full agent roster dictionaries grouped by project.
    Now that agents are global, this just returns them under the 'GLOBAL' key.
    """
    root = get_maccre_root() / "__DATACENTER" / "GLOBAL" / "agent_roster.csv"
    if not root.exists():
        return {}
    rosters: dict[str, list[dict]] = {}
    try:
        with root.open(newline="", encoding="utf-8") as fh:
            agents = list(csv.DictReader(fh))
            if agents:
                rosters["GLOBAL"] = agents
    except Exception:
        pass
    return rosters
