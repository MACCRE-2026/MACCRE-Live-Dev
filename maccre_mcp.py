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
maccre_mcp.py
=============
MACCREv2 Model Context Protocol Server — The Sole Agentic Interface.

All agentic consumers (Antigravity, Nexus-Gemma, external frameworks)
interact with MACCRE exclusively through this server.

Transport: stdio (Antigravity's native MCP channel)
Usage:     python maccre_mcp.py    (invoked automatically by Antigravity)

Tool Groups:
    SYSTEM      — status, session brief, project context
    SWARM       — submit/poll/resolve patterns, queue control, hot-mic
    KNOWLEDGE   — RAG ingest, query, federated search
    STORAGE     — read/write/trash files in DATACENTER
    RENDER      — pipeline execution, manifest cost estimation
    TELEMETRY   — codebase read, thought audit, log rotation
    FINOPS      — cost reconciliation, manifest cost estimation
    ADMIN       — agent mint, topology build, workspace control
"""
from __future__ import annotations

import json
import os
import sqlite3
import subprocess
import sys
from pathlib import Path

# ── Bulletproof startup — runs before ANY non-stdlib import ───────────────────
# __file__ is always the real script path regardless of CWD, so _ROOT is
# always correct even when Antigravity spawns us from its own working directory.
_ROOT = Path(__file__).resolve().parent

# Belt: explicit sys.path injection so maccre_core is always importable
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

# Suspenders: honour PYTHONPATH additions without clobbering our entry
for _extra in os.environ.get("PYTHONPATH", "").split(os.pathsep):
    if _extra and _extra not in sys.path:
        sys.path.insert(0, _extra)

# UTF-8 stdout/stderr — critical for Windows stdio MCP transport.
# PYTHONUNBUFFERED=1 (set in mcp_config env) ensures line-by-line flushing;
# these reconfigure calls handle the encoding layer.
import io as _io  # noqa: E402
if hasattr(sys.stdout, "buffer"):
    sys.stdout = _io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace", line_buffering=True)
if hasattr(sys.stderr, "buffer"):
    sys.stderr = _io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace", line_buffering=True)

# ── MCP STDIO ISOLATION ───────────────────────────────────────────────────────
# CRITICAL: stdout is the JSON-RPC pipe.  ANY non-JSON byte written to stdout
# corrupts the framing and kills the MCP connection with "invalid character".
# Redirect the root Python logger to stderr + file ONLY — never stdout.
# This must run BEFORE any maccre_core import that instantiates setup_maccre_logger.
import logging as _logging  # noqa: E402
_root_log = _logging.getLogger()
# Remove any pre-existing stdout StreamHandlers (from basicConfig or imports)
for _h in list(_root_log.handlers):
    if isinstance(_h, _logging.StreamHandler) and getattr(_h, "stream", None) is sys.stdout:
        _root_log.removeHandler(_h)
# Add a single stderr handler so log output is still visible in debug
_stderr_handler = _logging.StreamHandler(sys.stderr)
_stderr_handler.setFormatter(_logging.Formatter("[MCP-LOG] %(name)s %(levelname)s: %(message)s"))
_root_log.addHandler(_stderr_handler)
_root_log.setLevel(_logging.WARNING)  # Suppress DEBUG/INFO noise from sub-modules in MCP context
# ─────────────────────────────────────────────────────────────────────────────

from mcp.server.fastmcp import FastMCP  # noqa: E402

mcp = FastMCP("MACCREv2")

# ─────────────────────────────────────────────────────────────────────────────
# GROUP 1: SYSTEM
# ─────────────────────────────────────────────────────────────────────────────

@mcp.tool()
def maccre_status() -> str:
    """Returns MACCREv2 system status, active project, and Sentinel health summary.

    Returns:
        JSON string with status, active_project, mcp_version, and sentinel_health.
    """
    active = os.environ.get("MACCRE_ACTIVE_PROJECT", "GLOBAL")
    sentinel_health: dict = {}
    try:
        from maccre_core.orchestration.windows_vault import get_native_credential
        from maccre_core._net.model_sentinel import get_sentinel
        key = get_native_credential("MACCRE_Sovereign")
        if key:
            s = get_sentinel(str(key))
            report = s.report()
            sentinel_health = {
                "healthy": int(report.get("healthy", 0)),
                "degraded": int(report.get("degraded", 0)),
                "dead": int(report.get("dead", 0)),
            }
    except Exception:
        pass

    return json.dumps({
        "status": "operational",
        "active_project": active,
        "mcp_version": "2.0-Orchestrator",
        "sentinel_health": sentinel_health,
        "pattern_library": "online",
        "note": "Antigravity controls the DAG from this endpoint.",
    }, indent=2)


@mcp.tool()
def get_session_brief(project_id: str = "") -> str:
    """Build a zero-cost synchronous session brief at conversation startup.

    Reads git log, 7-day cost data, and Sentinel health directly from
    local state without queuing any swarm. Use this at the start of every
    session to re-contextualize.

    Args:
        project_id: Active project silo name. Defaults to MACCRE_ACTIVE_PROJECT env var.

    Returns:
        Formatted markdown BriefPacket + raw JSON block.
    """
    from maccre_core.tools.pattern_tools import get_session_brief as _brief
    return _brief(project_id)


@mcp.tool()
def set_active_project(project_id: str) -> str:
    """Set the active project context for subsequent tool calls.

    Args:
        project_id: Project silo directory name (e.g. 'SilmLOTR', 'GLOBAL').

    Returns:
        Confirmation string with the new active project.
    """
    os.environ["MACCRE_ACTIVE_PROJECT"] = project_id
    return json.dumps({"status": "ok", "active_project": project_id})


@mcp.tool()
def list_projects() -> str:
    """Lists all available project silos in the DATACENTER.

    Returns:
        JSON array of project names and their last-modified timestamps.
    """
    try:
        datacenter = _ROOT / "__DATACENTER"
        projects = []
        for d in sorted(datacenter.iterdir()):
            if d.is_dir() and not d.name.startswith("PATTERN_"):
                import time
                mtime = d.stat().st_mtime
                projects.append({
                    "name": d.name,
                    "last_modified": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(mtime)),
                })
        return json.dumps({"projects": projects}, indent=2)
    except Exception as exc:
        return json.dumps({"error": str(exc)})


# ─────────────────────────────────────────────────────────────────────────────
# GROUP 2: SWARM / PATTERN ORCHESTRATION
# ─────────────────────────────────────────────────────────────────────────────

@mcp.tool()
def list_patterns() -> str:
    """List all registered swarm topology patterns with metadata and cost estimates.

    Returns:
        JSON array of pattern metadata: name, description, estimated_cost_usd,
        required_surfaces, has_human_gate, node_count.
    """
    from maccre_core.tools.pattern_tools import list_patterns as _list
    return _list()


@mcp.tool()
def submit_pattern(pattern_name: str, payload: str, cost_limit_usd: float = 5.0) -> str:
    """Materialize a named swarm topology pattern and fire it into an isolated silo.

    Available patterns:
      - simulation_swarm: Pre-commit deliberation via 3 parallel paths. ~$0.08
      - research_sweep: Deep domain investigation with grounding. ~$0.30
      - session_brief: Async version of session context brief. ~$0.005
      - checkpoint_sweep: End-of-work code audit + cost reconciliation. ~$0.04
      - fault_investigation: Root cause analysis on failures. ~$0.05
      - monitor_watch: Background daemon monitoring with threshold alerts. ~$0.02
      - code_review: Multi-angle correctness/security/performance review. ~$0.05

    The pattern runs asynchronously. Use poll_human_gate(job_id) to retrieve
    the BriefPacket when the HUMAN_GATE fires.

    Args:
        pattern_name: One of the registered pattern names above.
        payload: Input payload as markdown text (problem statement, context, etc.).
        cost_limit_usd: Abort if estimated cost exceeds this limit. Default 5.0.

    Returns:
        JSON with job_id, silo_project, estimated_cost_usd, and topology_path.
    """
    from maccre_core.tools.pattern_tools import submit_pattern as _submit
    project_id = os.environ.get("MACCRE_ACTIVE_PROJECT", "GLOBAL")
    return _submit(pattern_name, payload, project_id, cost_limit_usd)


@mcp.tool()
def poll_human_gate(job_id: str, silo_project: str = "") -> str:
    """Check whether a HUMAN_GATE has fired for a running pattern job.

    Args:
        job_id: The job_id returned by submit_pattern().
        silo_project: Silo project name from submit_pattern result (optional —
            executor will scan DATACENTER silos if not provided).

    Returns:
        One of:
          'still_running' — job is active, gate not reached
          'not_found' — job_id not in any silo
          Formatted BriefPacket markdown + JSON — gate fired, ready for review
    """
    from maccre_core.tools.pattern_tools import poll_human_gate as _poll
    return _poll(job_id, silo_project)


@mcp.tool()
def resolve_gate(job_id: str, decision: str, silo_project: str = "") -> str:
    """Inject a decision into a paused HUMAN_GATE to continue the swarm.

    Args:
        job_id: The paused job ID.
        decision: Decision string — should match one of the next_action_options
            from the BriefPacket (e.g. 'approve_path_A', 'commit_and_continue').
        silo_project: Silo project name (optional).

    Returns:
        'acknowledged' on success, or an error string.
    """
    from maccre_core.tools.pattern_tools import resolve_gate as _resolve
    return _resolve(job_id, decision, silo_project)


@mcp.tool()
def check_swarm_queue(project_id: str = "") -> str:
    """Read the SQLite queue DB for active background swarm jobs in a project.

    Args:
        project_id: Project silo to check. Defaults to MACCRE_ACTIVE_PROJECT.

    Returns:
        JSON with active_jobs list (job_id, current_node, lock_status).
    """
    pid = project_id or os.environ.get("MACCRE_ACTIVE_PROJECT", "GLOBAL")
    try:
        from maccre_core.utils.path_resolver import get_maccre_root
        db_path = get_maccre_root() / "__DATACENTER" / pid / "swarm_queue.db"
        if not db_path.exists():
            # Try global queue
            db_path = get_maccre_root() / "swarm_queue.db"
        if not db_path.exists():
            return json.dumps({"status": "no database for project", "project": pid})
        with sqlite3.connect(str(db_path)) as conn:
            conn.row_factory = sqlite3.Row
            cur = conn.execute(
                "SELECT id, job_id, current_node, lock_status, created_at "
                "FROM task_queue WHERE lock_status != 'completed' ORDER BY id DESC LIMIT 50"
            )
            rows = [dict(r) for r in cur.fetchall()]
        return json.dumps({"project": pid, "active_jobs": rows}, indent=2)
    except Exception as exc:
        return json.dumps({"error": str(exc)})


@mcp.tool()
def inject_hot_mic(job_id: str, message: str) -> str:
    """Force a live priority override into a running swarm session.

    Injects a high-priority interrupt that the swarm worker will pick up
    on its next polling cycle and incorporate into its current context.

    Args:
        job_id: The UUID of the active swarm session.
        message: The instruction the swarm must pivot to obey immediately.

    Returns:
        Confirmation string.
    """
    from maccre_core.orchestration.local_broker import LocalMessageBroker
    broker = LocalMessageBroker()
    broker.inject_interrupt(job_id, message)
    return f"SUCCESS: Hot-Mic Priority override injected into session [{job_id}]: '{message}'"


@mcp.tool()
def ignite_background_swarm(payload: str, start_node: str = "INGEST") -> str:
    """Ignite a MACCRE Swarm on the active project asynchronously in the background.

    Fires the main project swarm (not a pattern silo) using the workbook
    topology. The swarm runs entirely headless.

    Args:
        payload: The prompt or data to feed into the swarm entry node.
        start_node: The topology node to begin execution. Default: INGEST.

    Returns:
        JSON confirming ignition with the PID of the headless process.
    """
    cmd = [
        sys.executable, str(_ROOT / "maccre.py"),
        "ignite", payload, "--node", start_node,
    ]
    CREATE_NO_WINDOW = 0x08000000
    proc = subprocess.Popen(
        cmd,
        cwd=str(_ROOT),
        creationflags=CREATE_NO_WINDOW,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    return json.dumps({
        "status": "ignited",
        "pid": proc.pid,
        "start_node": start_node,
        "message": f"Swarm launched headlessly at node '{start_node}'.",
    }, indent=2)


# ─────────────────────────────────────────────────────────────────────────────
# GROUP 3: KNOWLEDGE / RAG
# ─────────────────────────────────────────────────────────────────────────────

@mcp.tool()
def query_knowledge(query: str, project_id: str = "", n_results: int = 5) -> str:
    """Semantic search across the active project's ChromaDB vector memory.

    Args:
        query: Natural language query string.
        project_id: Project silo to search. Defaults to MACCRE_ACTIVE_PROJECT.
        n_results: Number of results to return. Default 5.

    Returns:
        JSON array of matched documents with metadata and relevance scores.
    """
    from maccre_core.tools.rag_tools import query_local_memory
    pid = project_id or os.environ.get("MACCRE_ACTIVE_PROJECT", "GLOBAL")
    return query_local_memory(query, pid, n_results=n_results)


@mcp.tool()
def ingest_to_knowledge(document_path: str, project_id: str = "") -> str:
    """Ingest a document from the DATACENTER into the project's vector memory.

    Args:
        document_path: Absolute path to the document (must be in 01_Raw_Source
            or 02_Dynamic_Context per DATACENTER doctrine).
        project_id: Target project silo. Defaults to MACCRE_ACTIVE_PROJECT.

    Returns:
        JSON confirmation with chunk count and ingestion status.
    """
    from maccre_core.tools.rag_tools import ingest_document
    pid = project_id or os.environ.get("MACCRE_ACTIVE_PROJECT", "GLOBAL")
    os.environ["MACCRE_ACTIVE_PROJECT"] = pid
    return ingest_document(file_path=document_path)


@mcp.tool()
def read_agent_ledger(job_id: str, node: str, node_id: int) -> str:
    """Retrieve the raw text output from a specific swarm agent node run.

    Args:
        job_id: The session/job string (e.g. 'session-abc123').
        node: The node name (e.g. 'OSINT', 'SYNTHESIZER', 'FORK_PATH_A').
        node_id: The DB task integer id matching that node.

    Returns:
        Raw ledger text, or JSON error if not found.
    """
    try:
        from maccre_core.utils.path_resolver import get_datacenter_path
        path = get_datacenter_path("03_Agent_Ledgers", job_id) / f"{node}_{node_id}.md"
        if not path.exists():
            return json.dumps({"error": f"Ledger not found: {path}"})
        return path.read_text(encoding="utf-8")
    except Exception as exc:
        return json.dumps({"error": str(exc)})


# ─────────────────────────────────────────────────────────────────────────────
# GROUP 4: STORAGE
# ─────────────────────────────────────────────────────────────────────────────

@mcp.tool()
def read_datacenter_file(path: str) -> str:
    """Read a file from within the MACCRE DATACENTER.

    Enforces DATACENTER-only reads — paths outside __DATACENTER are rejected.

    Args:
        path: Absolute path to a file within __DATACENTER.

    Returns:
        File contents as a string, or JSON error.
    """
    from maccre_core.tools.storage_tools import read_file
    return read_file(path)


@mcp.tool()
def write_datacenter_file(path: str, content: str) -> str:
    """Write content to a file within the MACCRE DATACENTER.

    Per DATACENTER doctrine:
      - Output artifacts → 04_Code_Artifacts or 05_Rendered_Media ONLY
      - Thought audits → 03_Agent_Ledgers ONLY

    Args:
        path: Absolute path for the output file (must be in 04_ or 03_ tier).
        content: String content to write.

    Returns:
        JSON confirmation with bytes written, or error.
    """
    resolved = Path(path).resolve()
    datacenter = (_ROOT / "__DATACENTER").resolve()
    # Enforce DATACENTER boundary
    try:
        resolved.relative_to(datacenter)
    except ValueError:
        return json.dumps({
            "error": f"PATH_VIOLATION: '{path}' is outside __DATACENTER. "
                     "Only paths inside __DATACENTER are writable via this tool."
        })
    # Enforce tier restriction: only 03, 04, 05 are writable output tiers
    _WRITABLE_TIERS = ("03_Agent_Ledgers", "04_Code_Artifacts", "05_Rendered_Media")
    parts = resolved.parts
    tier_ok = any(tier in parts for tier in _WRITABLE_TIERS)
    if not tier_ok:
        return json.dumps({
            "error": f"TIER_VIOLATION: '{path}' must be inside one of "
                     f"{_WRITABLE_TIERS}. Tiers 01 and 02 are read-only."
        })
    from maccre_core.tools.storage_tools import write_file
    return write_file(path, content)


@mcp.tool()
def list_datacenter_directory(directory: str) -> str:
    """List files and subdirectories within a DATACENTER path.

    Args:
        directory: Absolute path to a directory within __DATACENTER.

    Returns:
        JSON array of entries with name, type (file/dir), and size.
    """
    try:
        p = Path(directory)
        if not p.exists():
            return json.dumps({"error": f"Path does not exist: {directory}"})
        entries = []
        for child in sorted(p.iterdir()):
            entry: dict = {"name": child.name, "type": "dir" if child.is_dir() else "file"}
            if child.is_file():
                entry["size_bytes"] = child.stat().st_size
            entries.append(entry)
        return json.dumps({"path": str(p), "entries": entries}, indent=2)
    except Exception as exc:
        return json.dumps({"error": str(exc)})


# ─────────────────────────────────────────────────────────────────────────────
# GROUP 5: RENDER
# ─────────────────────────────────────────────────────────────────────────────

@mcp.tool()
def execute_render(manifest_json: str, session_dir: str = "") -> str:
    """Execute the full dual-pipeline media render: TTS + image generation + FFmpeg stitch.

    Consumes a Director manifest JSON array (speaker, text, video_prompt per scene),
    generates audio via TTS and images via Imagen, then assembles via local FFmpeg.

    Args:
        manifest_json: JSON array of scene dicts with keys: speaker, text, video_prompt.
        session_dir: Absolute path to output directory. Leave empty for default silo.

    Returns:
        SUCCESS string with output MP4 path, or TOOL_CRASH description.
    """
    from maccre_core.tools.render_executor import execute_render_pipeline
    return execute_render_pipeline(manifest_json, session_dir)


@mcp.tool()
def estimate_render_cost(manifest_json: str) -> str:
    """Estimate the cost of rendering a manifest before executing.

    Args:
        manifest_json: JSON array of scene dicts (same format as execute_render).

    Returns:
        JSON with estimated_usd, scene_count, tts_chars, image_count.
    """
    from maccre_core.tools.finops_tools import estimate_manifest_cost
    return estimate_manifest_cost(manifest_json)


# ─────────────────────────────────────────────────────────────────────────────
# GROUP 6: TELEMETRY
# ─────────────────────────────────────────────────────────────────────────────

@mcp.tool()
def read_codebase(
    directory: str = "",
    file_pattern: str = "*.py",
    max_files: int = 20,
) -> str:
    """Read and summarize Python source files in the MACCRE codebase.

    Args:
        directory: Subdirectory within the MACCRE root to scan. Empty = root.
        file_pattern: Glob pattern for files to include. Default '*.py'.
        max_files: Maximum number of files to return. Default 20.

    Returns:
        JSON with file list and content summaries.
    """
    from maccre_core.tools.telemetry_tools import read_local_codebase
    from pathlib import Path as _Path
    import glob as _glob

    base = _Path(_ROOT) / directory if directory else _Path(_ROOT)
    pattern = str(base / "**" / file_pattern)
    files = _glob.glob(pattern, recursive=True)[:max_files]
    if not files:
        return json.dumps({"error": f"No files found matching {pattern}"})
    results = {}
    for f in files:
        try:
            results[f] = read_local_codebase(f)
        except Exception as exc:
            results[f] = f"ERROR: {exc}"
    return json.dumps({"scanned": len(files), "files": results}, indent=2)


@mcp.tool()
def query_telemetry(event_type: str = "", limit: int = 50) -> str:
    """Query the system_logs telemetry database for recent events.

    Args:
        event_type: Filter by event type (e.g. 'INFERENCE_COST', 'MEDIA_RENDER_COMPLETE').
            Leave empty for all events.
        limit: Maximum rows to return. Default 50.

    Returns:
        JSON array of telemetry events with timestamp, event_type, payload, cost.
    """
    from maccre_core.tools.telemetry_tools import query_telemetry_matrix
    # Always query the global system_logs silo — project context is a filter, not the silo name
    where_parts: list[str] = []
    if event_type:
        safe_et = event_type.replace("'", "''")
        where_parts.append(f"action_type = '{safe_et}'")
    where_clause = " AND ".join(where_parts) if where_parts else "1=1"
    safe_limit = max(1, min(limit, 500))
    try:
        rows = query_telemetry_matrix("system_logs", where_clause)[:safe_limit]
        return json.dumps(rows, indent=2, default=str)
    except Exception as exc:
        return json.dumps({"error": str(exc)})


@mcp.tool()
def query_agent_thoughts(job_id: str = "", limit: int = 20) -> str:
    """Query the agent thought audit logs from 03_Agent_Ledgers.

    Args:
        job_id: Filter by specific job ID. Leave empty for recent thoughts across all jobs.
        limit: Maximum results to return. Default 20.

    Returns:
        JSON array of thought audit entries.
    """
    from maccre_core.tools.telemetry_tools import query_thoughts
    # Build a WHERE clause from optional job_id filter
    where = f"WHERE job_id = '{job_id}'" if job_id else ""
    if limit:
        where = (where + " " if where else "") + f"LIMIT {limit}"
    try:
        rows = query_thoughts(where)
        return json.dumps(rows, indent=2, default=str)
    except Exception as exc:
        return json.dumps({"error": str(exc)})


@mcp.tool()
def rotate_system_logs() -> str:
    """Rotate and archive MACCRE system logs to prevent unbounded growth.

    Returns:
        JSON confirmation with bytes archived and new log path.
    """
    from maccre_core.logger import rotate_logs
    return rotate_logs()


# ─────────────────────────────────────────────────────────────────────────────
# GROUP 7: FINOPS
# ─────────────────────────────────────────────────────────────────────────────

@mcp.tool()
def get_finops_report(job_id: str = "mcp_query") -> str:
    """Get a FinOps reconciliation report for recent inference spend.

    Compares projected costs (from pricing matrix) against actual costs
    (from system_logs INFERENCE_COST events) over the last 7 days.

    Args:
        job_id: Job identifier for the report context. Default 'mcp_query'.

    Returns:
        JSON with projected_usd, actual_usd, delta_usd, status, and per-model breakdown.
    """
    from maccre_core.tools.finops_tools import reconcile_session_finops
    return reconcile_session_finops(job_id)


@mcp.tool()
def list_model_registry() -> str:
    """List all 55 registered models with health status from the ModelSentinel.

    Returns:
        JSON array of models with name, surface, health_status, and pricing tier.
    """
    try:
        from maccre_core.orchestration.windows_vault import get_native_credential
        from maccre_core._net.model_registry import get_registry
        key = get_native_credential("MACCRE_Sovereign")
        if not key:
            return json.dumps({"error": "No sovereign key found in vault."})
        registry = get_registry(str(key))
        # all_models() returns the full model list from the capability map
        models = registry.all_models()
        return json.dumps({"model_count": len(models), "models": models}, indent=2)
    except Exception as exc:
        return json.dumps({"error": str(exc)})


# ─────────────────────────────────────────────────────────────────────────────
# GROUP 8: ADMIN / ORCHESTRATION
# ─────────────────────────────────────────────────────────────────────────────

@mcp.tool()
def mint_new_agent(
    agent_name: str,
    model: str,
    system_prompt: str,
    tools_allowed: str = "none",
) -> str:
    """Create a new agent roster entry for use in swarm topologies.

    Args:
        agent_name: Unique name for the agent (used in topology.csv Agent_Name column).
        model: Model ID for this agent (e.g. 'gemini-2.5-flash').
        system_prompt: System instruction defining the agent's role and behavior.
        tools_allowed: Pipe-separated tool names this agent can call. Default 'none'.

    Returns:
        JSON confirmation with the new roster entry.
    """
    from maccre_core.tools.admin_tools import mint_agent
    return mint_agent(agent_name, model, system_prompt, tools_allowed)


@mcp.tool()
def build_topology_from_spec(topology_spec: str, project_id: str = "") -> str:
    """Build and write a topology.csv from a JSON spec.

    Args:
        topology_spec: JSON array of node spec dicts with keys:
            Node_ID, Agent_Name, Next_Node, Instruction_Override,
            Temperature, Model_Override, Wait_For, Failure_Target.
        project_id: Target project silo. Defaults to MACCRE_ACTIVE_PROJECT.

    Returns:
        JSON with topology_path and node_count, or error.
    """
    from maccre_core.tools.admin_tools import build_topology
    # New 9-col schema (topology_engine.py canonical):
    #   Node_ID, Agent_Name, Model_Override, Next_Node,
    #   Temperature, Instruction_Override,
    #   Wait_For, Failure_Target, Max_Recursion
    # build_topology writes its own header — do NOT prepend a header row.
    try:
        raw = json.loads(topology_spec)
        if not raw:
            return json.dumps({"error": "topology_spec is empty"})
        if isinstance(raw[0], dict):
            rows: list[list[str]] = [
                [
                    str(node.get("Node_ID", "")),               # [0] Node_ID
                    str(node.get("Agent_Name", "")),            # [1] Agent_Name
                    str(node.get("Model_Override", "")),        # [2] Model_Override
                    str(node.get("Next_Node", "")),             # [3] Next_Node
                    str(node.get("Temperature", "1.0")),        # [4] Temperature
                    str(node.get("Instruction_Override", "")),  # [5] Instruction_Override
                    str(node.get("Wait_For", "none")),          # [6] Wait_For
                    str(node.get("Failure_Target", "FAILED")),  # [7] Failure_Target
                    str(node.get("Max_Recursion", "3")),        # [8] Max_Recursion
                ]
                for node in raw
            ]
        else:
            rows = raw
        return build_topology(rows)
    except (json.JSONDecodeError, TypeError) as exc:
        return json.dumps({"error": f"topology_spec parse error: {exc}"})


@mcp.tool()
def run_maccre_command(command: str) -> str:
    """Run a maccre.py CLI command as a subprocess and return its output.

    Safe commands only: brief, pattern list, pattern poll, status.
    Blocked: commands that could mutate live state (ignite, build, delete).

    Args:
        command: The maccre.py subcommand and args (e.g. 'brief --project SilmLOTR').

    Returns:
        Combined stdout output as a string.
    """
    ALLOWED_PREFIXES = ("brief", "pattern list", "pattern poll", "status")
    cmd_stripped = command.strip()
    if not any(cmd_stripped.startswith(p) for p in ALLOWED_PREFIXES):
        return json.dumps({
            "error": f"Command '{cmd_stripped}' not in safe list. "
                     f"Allowed: {ALLOWED_PREFIXES}"
        })
    full_cmd = [sys.executable, "-X", "utf8", str(_ROOT / "maccre.py")] + cmd_stripped.split()
    try:
        result = subprocess.run(
            full_cmd,
            cwd=str(_ROOT),
            capture_output=True,
            timeout=30,
            env={**os.environ, "PYTHONIOENCODING": "utf-8"},
        )
        output = result.stdout.decode("utf-8", errors="replace")
        if result.returncode != 0:
            output += "\nSTDERR:\n" + result.stderr.decode("utf-8", errors="replace")
        return output
    except Exception as exc:
        return json.dumps({"error": str(exc)})


# ─────────────────────────────────────────────────────────────────────────────
# ENTRY POINT
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    mcp.run()
