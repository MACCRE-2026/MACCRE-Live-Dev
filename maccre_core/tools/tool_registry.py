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
maccre_core/tools/tool_registry.py
=====================================
MACCRE Tool Registry — unified manifest of all atomic, GUI-agnostic tools.

This module is the single import point for the Cognitive Router
(``maccre_core/maccre_router.py``).  It exposes:

  TOOL_REGISTRY : list[Callable]
      Every registered atomic function, suitable for direct injection into
      ``client.models.generate_content(tools=[...])`` via the Gemini
      Function Calling API.

  get_tools_for_tier(tier: str) -> list[Callable]
      Tier-aware subset selector used by the Cognitive Router to match tools
      to the appropriate model:
        - "heavy"  → tools for Gemini 1.5 Pro / 2.5 Pro (text-heavy ops)
        - "fast"   → tools for Gemini Flash / Flash-Lite (JSON/validation ops)
        - anything else → full registry

Design contract (enforced by tests/test_tool_registry.py):
  Every function in TOOL_REGISTRY MUST have:
    1. A complete Google-style docstring (Args / Returns / Raises).
    2. Explicit Python type annotations on ALL parameters AND the return type.
  These are required for the ``google-generativeai`` SDK to compile a correct
  OpenAPI schema for Function Calling.

Google-style docstring contract — DO NOT use Sphinx or reST here.
"""

from typing import Any, Callable, Dict, List

# ── Import all atomic tool functions ─────────────────────────────────────────
from maccre_core.tools.text_tools import (
    parse_json_response,
    build_system_instruction,
    truncate_history,
    format_cost_str,
)
from maccre_core.tools.finops_tools import estimate_manifest_cost, render_cost_report
from maccre_core.tools.audio_tools import (
    pack_wav_bytes,
    make_tts_filename,
)
from maccre_core.tools.media_tools import (
    build_concat_manifest,
    build_ffmpeg_cmd,
    save_manifest,
)
from maccre_core.tools.agent_tools import (
    load_agent_from_dict,
    load_agent_from_file,
    save_agent_to_file,
    request_scope_expansion,
)
from maccre_core.tools.storage_tools import (
    read_file,
    write_file,
    write_dynamic_context,
    file_exists,
    trash_file,
)
from maccre_core.tools.rag_tools import (
    query_local_memory,
    fts_search_memory,
    ingest_document,
    query_foreign_memory,
    import_foreign_vectors,
    prune_semantic_memory,
    iterative_scoped_search,
)
from maccre_core.tools.telemetry_tools import (
    read_local_codebase,
    query_telemetry_matrix,
    query_thoughts,
    export_and_purge_thoughts,
    generate_telemetry_report,
)

from maccre_core.tools.admin_tools import (
    mint_agent,
    build_topology,
    link_projects,
    ignite_swarm,
    initialize_workspace,
    switch_workspace,
    promote_topology_to_library,
    recall_topology,
    run_swarm,
    create_persona_card,
    ensure_project_workbook,
)
from maccre_core.tools.design_tools import design_swarm, fill_swarm_sheet
from maccre_core.tools.render_executor import (
    execute_render_pipeline, render_podcast_audio,
    render_video, render_image, render_image_batch,
)
from maccre_core.orchestration.access_control import (
    request_elevation,
)
from maccre_core.logger import rotate_logs
from maccre_core.tools.sync_tools import (
    export_project_nugget,
    import_project_nuggets,
    list_project_nuggets,
)
from maccre_core.tools.web_tools import search_web, read_url_content, cascade_search
from maccre_core.tools.hybrid_search import execute_hybrid_synthesis
from maccre_core.tools.collection_ingest import scout_archive_themes, execute_archive_ingestion

# ── Master Dispatcher ────────────────────────────────────────────────────────

TOOL_DISPATCHER: Dict[str, Callable[..., Any]] = {
    "parse_json_response": parse_json_response,
    "build_system_instruction": build_system_instruction,
    "truncate_history": truncate_history,
    "format_cost_str": format_cost_str,
    "pack_wav_bytes": pack_wav_bytes,
    "make_tts_filename": make_tts_filename,
    "build_concat_manifest": build_concat_manifest,
    "build_ffmpeg_cmd": build_ffmpeg_cmd,
    "save_manifest": save_manifest,
    "load_agent_from_dict": load_agent_from_dict,
    "load_agent_from_file":       load_agent_from_file,
    "save_agent_to_file":         save_agent_to_file,
    "request_scope_expansion":    request_scope_expansion,
    # ── Storage & Memory ──────────────────────────────────────────────────
    "read_file":                  read_file,
    "write_file":                 write_file,
    "write_dynamic_context":      write_dynamic_context,
    "file_exists":                file_exists,
    "trash_file":                 trash_file,          # Project-aware: resolves via ProjectAwareAdapter
    "query_local_memory":         query_local_memory,
    "fts_search_memory":          fts_search_memory,   # BM25 full-text — reaches deep content unavailable via vector
    "ingest_document":            ingest_document,
    "query_foreign_memory":       query_foreign_memory,
    "import_foreign_vectors":     import_foreign_vectors,
    "prune_semantic_memory":      prune_semantic_memory,
    "iterative_scoped_search":    iterative_scoped_search,
    # ── Telemetry & RBAC ──────────────────────────────────────────────────
    "read_local_codebase":        read_local_codebase,
    "query_telemetry_matrix":     query_telemetry_matrix,
    "query_thoughts":             query_thoughts,
    "export_and_purge_thoughts":  export_and_purge_thoughts,
    # ── Global Orchestration (Nexus Agents) ───────────────────────────────
    "mint_agent":                 mint_agent,
    "build_topology":             build_topology,
    "link_projects":              link_projects,
    "ignite_swarm":               ignite_swarm,
    "initialize_workspace":       initialize_workspace,
    "switch_workspace":           switch_workspace,
    "request_elevation":          request_elevation,
    # ── FinOps ───────────────────────────────────────────────────────
    "execute_render_pipeline":    execute_render_pipeline,
    "render_podcast_audio":       render_podcast_audio,       # audio-only: WAV output
    "render_video":               render_video,               # video: TTS + images → MP4
    "render_image":               render_image,               # single image from prompt
    "render_image_batch":         render_image_batch,         # concurrent multi-image batch
    # ── FinOps Estimator ────────────────────────────────────────────
    "estimate_manifest_cost":     estimate_manifest_cost,
    "render_cost_report":          render_cost_report,         # Post-render actual cost breakdown
    # ── Initiative 3: Topology Library ──────────────────────────────────
    "promote_topology_to_library": promote_topology_to_library,
    "recall_topology":            recall_topology,
    # ── Initiative 4: Telemetry Reporting & Log Rotation ────────────────
    "generate_telemetry_report":  generate_telemetry_report,
    "rotate_logs":                rotate_logs,
    # ── Swarm Design & Execution Engine ──────────────────────────────────
    "design_swarm":               design_swarm,
    "run_swarm":                  run_swarm,
    "create_persona_card":        create_persona_card,
    "fill_swarm_sheet":           fill_swarm_sheet,
    # ── Cross-Device Sync (Phase 19) ──────────────────────────────────────
    "export_project_nugget":      export_project_nugget,
    "import_project_nuggets":     import_project_nuggets,
    "list_project_nuggets":       list_project_nuggets,
    # ── Project Workbook Utility (Phase 20) ───────────────────────────────
    "ensure_project_workbook":    ensure_project_workbook,
    # ── Web Access (OSINT / NewsNexus) ────────────────────────────────────
    "search_web":                 search_web,
    "read_url_content":           read_url_content,
    "cascade_search":             cascade_search,
    "execute_hybrid_synthesis":   execute_hybrid_synthesis,
    # ── CollectionLM Ingestion ──────────────────────────────────────────────
    "scout_archive_themes":       scout_archive_themes,
    "execute_archive_ingestion":  execute_archive_ingestion,
}

# ── TOOL_REGISTRY: auto-generated from TOOL_DISPATCHER (single source of truth) ─
#: Prevents dual-declaration maintenance — never manually edit this list.
TOOL_REGISTRY: list[Callable[..., Any]] = list(TOOL_DISPATCHER.values())

def get_tools_from_sheet(tools_str: str) -> List[Callable[..., Any]]:
    """Resolves a pipe-separated (|) string of tool names to their callable functions.

    Also accepts legacy comma-separated strings and normalises them to pipes
    so existing topology rows continue to work during migration.

    Args:
        tools_str: Pipe- or comma-separated tool name string from topology.csv
            (e.g. ``"write_file|ingest_document"`` or ``"read_file,write_file"``).

    Returns:
        List of callables for all recognised tool names.
    """
    if not tools_str or tools_str.lower() == "none":
        return []
    normalized_str = tools_str.replace(",", "|")
    return [TOOL_DISPATCHER[t.strip()] for t in normalized_str.split("|") if t.strip() in TOOL_DISPATCHER]

# ── Tier tagging (used by get_tools_for_tier) ─────────────────────────────────

_HEAVY_TOOLS: set[str] = {
    # Tools that involve high-context reasoning or complex I/O composition
    "parse_json_response",
    "build_system_instruction",
    "build_concat_manifest",
    "build_ffmpeg_cmd",
    "save_manifest",
    "pack_wav_bytes",
    "load_agent_from_file",
    "save_agent_to_file",
    "execute_render_pipeline",
    "render_podcast_audio",
    "render_video",
    "render_image",
    "render_image_batch",
    "iterative_scoped_search",
}

_FAST_TOOLS: set[str] = {
    # Lightweight validation and formatting tools
    "truncate_history",
    "format_cost_str",
    "make_tts_filename",
    "load_agent_from_dict",
    "read_file",
    "write_file",
    "write_dynamic_context",
    "file_exists",
    "estimate_manifest_cost",
}


def get_tools_for_tier(tier: str) -> list[Callable[..., Any]]:
    """Return a filtered subset of ``TOOL_REGISTRY`` appropriate for the given model tier.

    The Cognitive Router calls this function to compose the ``tools`` argument
    when calling ``client.models.generate_content``.  Heavy tools are routed
    to high-capacity models; fast tools go to Flash-class models for lower
    latency and cost.

    Args:
        tier: Routing tier identifier.  Accepted values:
            - ``"heavy"`` – tools suited for Gemini 1.5 Pro / 2.5 Pro.
            - ``"fast"``  – tools suited for Gemini Flash / Flash-Lite.
            - Any other string returns the complete ``TOOL_REGISTRY``.

    Returns:
        A list of callable tool functions for the requested tier.
    """
    if tier == "heavy":
        return [t for t in TOOL_REGISTRY if t.__name__ in _HEAVY_TOOLS]
    if tier == "fast":
        return [t for t in TOOL_REGISTRY if t.__name__ in _FAST_TOOLS]
    return TOOL_REGISTRY


# ── Universal JSON Schema Generator ───────────────────────────────────────────

import inspect  # noqa: E402 (kept local to avoid polluting top-level namespace)


def generate_universal_json_schema(func: Callable[..., Any]) -> Dict[str, Any]:
    """Dynamically reads a Python function and returns an Anthropic/OpenAI-compatible JSON Schema.

    Inspects the function's signature and type annotations to build the
    ``input_schema`` block required by the Anthropic Messages API and the
    Ollama OpenAI-compatible tool-calling API.

    Args:
        func: Any callable registered in ``TOOL_DISPATCHER``.

    Returns:
        A dict with ``name``, ``description``, and ``input_schema`` keys
        suitable for direct injection into an Anthropic or Ollama tool list.
    """
    sig = inspect.signature(func)
    doc = inspect.getdoc(func) or "No description provided."

    properties: Dict[str, Any] = {}
    required: List[str] = []

    for name, param in sig.parameters.items():
        ann = param.annotation
        param_type = "string"
        if ann is int:
            param_type = "integer"
        elif ann is float:
            param_type = "number"
        elif ann is bool:
            param_type = "boolean"
        elif ann in (dict, Dict[str, Any]):
            param_type = "object"
        elif ann is list or getattr(ann, "__origin__", None) is list:
            param_type = "array"

        properties[name] = {"type": param_type, "description": f"Parameter: {name}"}
        if param.default == inspect.Parameter.empty:
            required.append(name)

    return {
        "name": func.__name__,
        "description": doc,
        "input_schema": {
            "type": "object",
            "properties": properties,
            "required": required,
        },
    }
