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
maccre_core/tools/admin_tools.py
============================================
Admin-level orchestration tools for the MACCREv2 workbook pipeline
and MCP integration layer.
"""
import os
import json
import csv
import shutil
import sqlite3
import subprocess
from pathlib import Path as _Path
from typing import Any, List
from maccre_core.utils.path_resolver import get_datacenter_path, get_maccre_root

def mint_agent(
    name: str,
    model: str,
    system_prompt: str = "",
    description: str = "",
    tools_string: str = "none",
    *,
    persona: str = "",
    instructions: str = "",
    target_project: str = "",
) -> str:
    """Creates or overwrites an Agent profile in the project's agent_roster.csv.

    Args:
        name: The Agent persona name.
        model: Compute backend (e.g., 'gemini-2.5-flash', 'gemma3:9b').
        system_prompt: Long-form instruction / system prompt for the agent.
            Alias: ``instructions`` (AgentRecord-style field name).
        description: Short description of agent capabilities.
            Alias: ``persona`` (AgentRecord-style field name).
        tools_string: Pipe-separated string of MACCRE tools (default 'none').
        persona: Alias for ``description`` — accepted so Gemini can pass either.
        instructions: Alias for ``system_prompt`` — accepted so Gemini can pass either.
    """
    # Resolve aliases — persona IS the system instruction; instructions is short metadata
    resolved_system_prompt = system_prompt or persona
    resolved_description   = description   or instructions

    try:
        roster_path = get_maccre_root() / "__DATACENTER" / "GLOBAL" / "agent_roster.csv"
        roster_path.parent.mkdir(parents=True, exist_ok=True)
            
        file_exists = roster_path.exists()

        rows: list[list[str]] = []
        if file_exists:
            with open(roster_path, "r", encoding="utf-8") as f:
                reader = csv.reader(f)
                next(reader, None)
                for row in reader:
                    if row and row[0] != name:
                        rows.append(row)

        rows.append([name, model, tools_string, resolved_system_prompt, resolved_description])

        with open(roster_path, "w", encoding="utf-8", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["Agent_Name", "Model", "Tools_Allowed", "System_Prompt", "Description"])
            writer.writerows(rows)

        return f"[ADMIN_SUCCESS] Agent '{name}' minted successfully into {roster_path}."
    except Exception as e:
        return f"[ADMIN_FAULT] Agent Minting Failed: {e}"

def build_topology(nodes: List[List[str]]) -> str:
    """Writes a new execution topology.csv for the Swarm to follow.

    Columns written (topology_engine.py canonical schema)::

        Node_ID, Agent_Name, Model_Override, Next_Node, Temperature,
        Instruction_Override, Wait_For, Failure_Target, Max_Recursion, Artifact_Path, Live_Profile

    Args:
        nodes: A list of rows. Each row is 6-15 items:
               [Node_ID, Agent_Name, Model_Override, Next_Node,
                Temperature, Instruction_Override,
                Wait_For?, Failure_Target?, Max_Recursion?, Artifact_Path?, Live_Profile?, Dialogue_Partner?, Dialogue_Rounds?, Payload_Mode?, Tools_Allowed?]
               Optional columns receive defaults.
    """
    _DEFAULTS = ["none", "FAILED", "3", "", "FALSE", "", "0", "Unified Ledger", ""]
    try:
        topo_path = get_datacenter_path("02_Dynamic_Context", "topology.csv")
        os.makedirs(os.path.dirname(topo_path), exist_ok=True)
        with open(topo_path, 'w', encoding='utf-8', newline='') as f:
            writer = csv.writer(f)
            writer.writerow([
                "Node_ID", "Agent_Name", "Model_Override", "Next_Node",
                "Temperature", "Instruction_Override",
                "Wait_For", "Failure_Target", "Max_Recursion", "Artifact_Path", "Live_Profile",
                "Dialogue_Partner", "Dialogue_Rounds", "Payload_Mode", "Tools_Allowed"
            ])
            for raw_node in nodes:
                node: list[str] = list(raw_node)
                if len(node) < 6 or len(node) > 15:
                    return (
                        f"[ADMIN_FAULT] Node malformed. Expected 6-14 items, "
                        f"got {len(node)}. Node: {node}"
                    )
                # Pad optional trailing columns with defaults
                while len(node) < 15:
                    node.append(_DEFAULTS[len(node) - 6])
                writer.writerow(node)
                
        return f"[ADMIN_SUCCESS] Topology constructed successfully at {topo_path}."
    except Exception as e:
        return f"[ADMIN_FAULT] Topology Build Failed: {e}"

def link_projects(target_project: str) -> str:
    """Modifies the active project_schema.json to allow Synaptic Bridge access to foreign databases.
    
    Args:
        target_project: A comma-separated string of foreign project names to whitelist.
    """
    try:
        schema_path = get_datacenter_path("project_schema.json")
        schema = {"linked_projects": []}
        if schema_path.exists():
            with open(schema_path, "r", encoding="utf-8") as f:
                schema = json.load(f)
                
        projects_to_link = [p.strip() for p in target_project.split(",") if p.strip()]
        linked_count = 0
        
        for proj in projects_to_link:
            if proj not in schema["linked_projects"]:
                schema["linked_projects"].append(proj)
                linked_count += 1
            
        with open(schema_path, "w", encoding="utf-8") as f:
            json.dump(schema, f, indent=4)
            
        return f"[ADMIN_SUCCESS] Successfully whitelisted {linked_count} project(s) for Synaptic Bridge operations. Requested: {target_project}"
    except Exception as e:
        return f"[ADMIN_FAULT] Project Linkage Failed: {e}"

def ignite_swarm(payload_path_relative: str, starting_node: str = "OSINT") -> str:
    """Ingests a markdown file from 01_Raw_Source and queues it to start the swarm execution pipeline!
    
    Args:
        payload_path_relative: The filename inside 01_Raw_Source (e.g. 'conversation.md').
        starting_node: The Node_ID in the topology to start at.
    """
    try:
        from maccre_core.orchestration.local_broker import LocalMessageBroker
        from maccre_core.utils.session_manager import generate_session_id

        if payload_path_relative and payload_path_relative.lower() != "none":
            full_path = get_datacenter_path("01_Raw_Source", payload_path_relative)
            if not full_path.exists():
                return f"[ADMIN_FAULT] Payload '{payload_path_relative}' not found in 01_Raw_Source."
            payload_str = str(full_path)
        else:
            payload_str = "none"

        job_id = f"job_{generate_session_id()}"
        broker = LocalMessageBroker()
        broker.inject_task(job_id=job_id, payload_path=payload_str, starting_node=starting_node)
        return f"[ADMIN_SUCCESS] Swarm Ignited! Job {job_id} dispatched starting at node '{starting_node}'."
    except Exception as e:
        return f"[ADMIN_FAULT] Ignition Sequence Failed: {e}"

# ── Template helpers (Phase 20) ───────────────────────────────────────────────



def _copy_template_to_project(project_base: _Path) -> None:
    """Copy the blank MACCRE_Swarm_Request.xlsx template into a project root.

    Regenerates the template from scripts/generate_template.py if the file is
    missing.  Silent on failure — workspace creation proceeds regardless.
    """
    import logging  # noqa: PLC0415
    log = logging.getLogger("maccre_core")
    root = get_maccre_root()
    template_src = root / "templates" / "MACCRE_Swarm_Request.xlsx"

    if not template_src.exists():
        log.info("[AdminTools] Template missing — regenerating via generate_template.py")
        try:
            subprocess.run(
                ["python", "scripts/generate_global_template.py"],
                cwd=str(root),
                capture_output=True,
                check=False,
            )
        except Exception as exc:  # noqa: BLE001
            log.warning("[AdminTools] Could not regenerate template: %s", exc)

    dest = project_base / "MACCRE_Swarm_Request.xlsx"
    if template_src.exists() and not dest.exists():
        try:
            shutil.copy2(str(template_src), str(dest))
            log.info("[AdminTools] Template copied to %s", dest)
        except Exception as exc:  # noqa: BLE001
            log.warning("[AdminTools] Template copy failed: %s", exc)


def ensure_project_workbook(project_name: str) -> str:
    """Guarantee a MACCRE_Swarm_Request.xlsx exists in the project root.

    Called automatically before every swarm run.  If the file is missing
    (deleted, never created) it is regenerated from the base template.

    Args:
        project_name: Target project silo name.

    Returns:
        A status string indicating whether the file was present or regenerated.
    """
    base = get_maccre_root() / "__DATACENTER" / project_name
    wb_path = base / "MACCRE_Swarm_Request.xlsx"
    
    from maccre_core.orchestration.telemetry_db import init_all_silos
    init_all_silos()
    
    if wb_path.exists():
        return f"[WB_OK] Workbook present: {wb_path}"
    _copy_template_to_project(base)
    if wb_path.exists():
        return f"[WB_RESTORED] Workbook regenerated: {wb_path}"
    return "[WB_WARN] Could not restore workbook — base template missing."


def initialize_workspace(project_name: str) -> str:
    """Provisions a new project workspace within __DATACENTER.

    Creates the 6-tier directory tree, bootstraps project_schema.json,
    agent_roster.csv, telemetry silos, and copies a blank
    MACCRE_Swarm_Request.xlsx template into the project root.

    Args:
        project_name: The name of the new project workspace (alphanumeric + underscores).
    """
    try:
        if not all(c.isalnum() or c == "_" for c in project_name):
            return "[ADMIN_FAULT] Project names must be alphanumeric or use underscores."

        base = get_maccre_root() / "__DATACENTER" / project_name
        if base.exists():
            return f"[ADMIN_FAULT] Workspace '{project_name}' already exists."

        (base / "01_Raw_Source").mkdir(parents=True, exist_ok=True)
        (base / "02_Dynamic_Context").mkdir(parents=True, exist_ok=True)
        (base / "03_Agent_Ledgers").mkdir(parents=True, exist_ok=True)
        (base / "04_Code_Artifacts").mkdir(parents=True, exist_ok=True)
        (base / "05_Rendered_Media").mkdir(parents=True, exist_ok=True)
        (base / "02_Dynamic_Context" / "memory_pins").mkdir(parents=True, exist_ok=True)
        (base / "chroma_db").mkdir(parents=True, exist_ok=True)

        # Deploy project baseline
        schema = {
            "project_name": project_name,
            "scope": "Default project scope. The Swarm will reference this to align outputs.",
            "linked_projects": [],
        }
        with open(base / "project_schema.json", "w", encoding="utf-8") as f:
            json.dump(schema, f, indent=4)

        # Bootstrap empty agent roster
        roster_path = base / "agent_roster.csv"
        with open(roster_path, "w", encoding="utf-8", newline="") as f:
            f.write("Agent_Name,Model,Tools_Allowed,System_Prompt,Description\n")

        # Copy blank MACCRE_Swarm_Request.xlsx template into project root
        _copy_template_to_project(base)

        # Bootstrap telemetry silos and switch active project
        os.environ["MACCRE_ACTIVE_PROJECT"] = project_name
        from maccre_core.orchestration.telemetry_db import init_all_silos  # noqa: PLC0415
        init_all_silos()

        # Register in project_registry.db
        from maccre_core.utils.session_manager import register_project  # noqa: PLC0415
        register_project(project_name, schema.get("scope", ""), [])

        return (
            f"[ADMIN_SUCCESS] Workspace '{project_name}' initialized. "
            f"Active project is now '{project_name}'. "
            "Blank MACCRE_Swarm_Request.xlsx written to project root."
        )
    except Exception as e:
        return f"[ADMIN_FAULT] Initialization Failed: {e}"

def switch_workspace(project_name: str) -> str:
    """Dynamically re-binds the active session's RAG and Data context to a target project.
    
    Args:
        project_name: The target project (or 'GLOBAL') to switch context to.
    """
    try:
        if project_name == "GLOBAL":
            os.environ["MACCRE_ACTIVE_PROJECT"] = "GLOBAL"
            from maccre_core.orchestration.telemetry_db import init_all_silos
            init_all_silos()
            return "[ADMIN_SUCCESS] Workspace context reverted to GLOBAL."

        base = get_maccre_root() / "__DATACENTER" / project_name
        if not base.exists():
            return f"[ADMIN_FAULT] Workspace '{project_name}' does not exist. Initialize it first."

        os.environ["MACCRE_ACTIVE_PROJECT"] = project_name
        # Ensure telemetry silos exist in the newly active project
        from maccre_core.orchestration.telemetry_db import init_all_silos
        init_all_silos()
        return f"[ADMIN_SUCCESS] Workspace context successfully switched to '{project_name}'. All subsequent file and memory commands will route here."
    except Exception as e:
        return f"[ADMIN_FAULT] Switch Failed: {e}"


def create_persona_card(
    agent_name: str,
    instructions: str,
    temperature: float = 0.7,
    context_notes: str = "",
) -> str:
    """Write a JSON ROM cartridge persona card that the swarm worker loads for this agent.

    The worker prioritises persona cards over the CSV system_prompt field, so this is
    the canonical way to give an agent rich, detailed instructions.  Cards live in
    ``02_Dynamic_Context/<agent_name>.json`` inside the active project silo.

    Args:
        agent_name: The agent's exact name (must match agent_roster.csv).
        instructions: The full system prompt / persona instructions for the agent.
        temperature: Default generation temperature for this agent (0.0–1.0).
        context_notes: Optional human-readable notes for documentation purposes.

    Returns:
        A status string confirming the card path, or a fault message.
    """
    try:
        card: dict[str, Any] = {
            "agent_name": agent_name,
            "instructions": instructions,
            "temperature": temperature,
            "context_notes": context_notes,
        }
        card_path = get_datacenter_path("02_Dynamic_Context", f"{agent_name}.json")
        card_path.parent.mkdir(parents=True, exist_ok=True)
        card_path.write_text(json.dumps(card, indent=2, ensure_ascii=False), encoding="utf-8")
        return f"[ADMIN_SUCCESS] Persona card '{agent_name}.json' written to {card_path}."
    except Exception as e:
        return f"[ADMIN_FAULT] create_persona_card failed: {e}"


def run_swarm(project_name: str = "", max_cycles: int = 500, timeout_seconds: int = 3600) -> str:
    """Execute all queued swarm jobs for the active project inline, blocking until complete.

    This is the primary execution tool — called by the workbook pipeline and
    the MCP server. ``ignite_swarm`` queues a job and ``run_swarm`` executes
    it end-to-end without any external script.

    Args:
        project_name: Target project name. Defaults to the current ``MACCRE_ACTIVE_PROJECT``.
            If provided, the active project is switched to this value before execution.
        max_cycles: Maximum worker cycles before aborting. Each cycle processes one node.
            Default 500 supports large multi-node topologies with retries.
        timeout_seconds: Hard wall-clock timeout in seconds. Default 600 (10 minutes).

    Returns:
        A summary string listing all ledger artifacts produced and the total cost,
        or a fault message if the queue is empty or execution failed.
    """
    import sqlite3
    import time as _time
    from maccre_core.orchestration.swarm_worker import UniversalSwarmWorker  # noqa: PLC0415

    project = project_name.strip() or os.environ.get("MACCRE_ACTIVE_PROJECT", "GLOBAL")
    os.environ["MACCRE_ACTIVE_PROJECT"] = project

    # Phase 20: guarantee spec workbook exists in project root before execution
    ensure_project_workbook(project)

    db_path = str(get_datacenter_path("swarm_queue.db"))
    if not os.path.exists(db_path):
        return f"[SWARM_FAULT] No swarm queue found for project '{project}'. Call ignite_swarm first."

    # Verify there are open tasks
    with sqlite3.connect(db_path) as _chk:
        open_count: int = _chk.execute(
            "SELECT COUNT(*) FROM task_queue WHERE lock_status = 'open'"
        ).fetchone()[0]
    if open_count == 0:
        return f"[SWARM_FAULT] No open tasks in queue for project '{project}'. Has ignite_swarm been called?"

    worker = UniversalSwarmWorker()
    start_time = _time.time()

    for _ in range(max_cycles):
        if _time.time() - start_time > timeout_seconds:
            break
        worker.execute_cycle()

        with sqlite3.connect(db_path) as _q:
            still_open: int = _q.execute(
                "SELECT COUNT(*) FROM task_queue WHERE lock_status = 'open'"
            ).fetchone()[0]
        if still_open == 0:
            break

    # Collect final cost and artifacts
    total_cost: float = 0.0
    with sqlite3.connect(db_path) as _q:
        cost_row = _q.execute(
            "SELECT COALESCE(SUM(actual_cost), 0.0) FROM task_queue"
        ).fetchone()
        total_cost = float(cost_row[0]) if cost_row else 0.0

    ledger_root = get_datacenter_path("03_Agent_Ledgers")
    artifacts: list[str] = []
    if ledger_root.exists():
        artifacts = [
            str(f.relative_to(ledger_root))
            for f in sorted(ledger_root.rglob("*.md"))
        ]
    artifact_str = "\n".join(f"  {a}" for a in artifacts) if artifacts else "  (no markdown ledgers produced)"

    elapsed = f"{_time.time() - start_time:.1f}s"
    return (
        f"[SWARM_COMPLETE] Project: {project} | Elapsed: {elapsed} | Total Cost: ${total_cost:.6f}\n"
        f"Output Artifacts:\n{artifact_str}"
    )



# ── Initiative 3: Topology Promotion & Recall ────────────────────────────────

def promote_topology_to_library(topology_name: str, job_id: str) -> str:
    """Promote the active topology.csv into the persistent topology_library in definitions.db.

    Reads the current project's topology.csv and inserts every node row into
    ``definitions.db``->``topology_library`` so proven topologies accumulate
    as queryable institutional memory for future swarm design.

    Args:
        topology_name: A human-readable label for this topology snapshot
            (e.g. ``'OSINT_REFACTOR_v2'``).
        job_id: The job_id of the completed swarm run that proved this topology.

    Returns:
        A status string indicating how many nodes were promoted, or a fault
        message if the operation failed.
    """
    from maccre_core.orchestration.telemetry_db import promote_topology_row

    try:
        topo_path = get_datacenter_path("02_Dynamic_Context", "topology.csv")
        if not topo_path.exists():
            return f"[ADMIN_FAULT] topology.csv not found at {topo_path}."

        promoted = 0
        with open(topo_path, mode="r", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            for row in reader:
                try:
                    temp_val = float(row.get("Temperature", 0.7))
                except ValueError:
                    temp_val = 0.7
                promote_topology_row(
                    node_id=str(row.get("Node_ID", "")).strip(),
                    agent_name=str(row.get("Agent_Name", "")).strip(),
                    model_override=str(row.get("Model_Override", "")).strip(),
                    auto_tool=str(row.get("Auto_Tool", "")).strip(),
                    next_node=str(row.get("Next_Node", "")).strip(),
                    output_file=str(row.get("Output_File", "")).strip(),
                    temperature=temp_val,
                    instruction_override=str(row.get("Instruction_Override", "")).strip(),
                    topology_name=topology_name,
                    job_id=job_id,
                )
                promoted += 1

        return f"[ADMIN_SUCCESS] Promoted {promoted} node(s) from topology.csv into topology_library as '{topology_name}'."
    except Exception as e:
        return f"[ADMIN_FAULT] Topology promotion failed: {e}"


def recall_topology(query: str) -> str:
    """Retrieve proven topologies from the topology_library whose names or instructions match a query.

    Performs a case-insensitive LIKE search against ``topology_name`` and
    ``instruction_override`` columns so the MCP server or workbook pipeline can
    identify suitable prior-art topologies for a new swarm design without reading
    raw CSV files.

    Args:
        query: A keyword or phrase to search for (e.g. ``'OSINT'``,
            ``'video render'``, ``'multi-agent scatter'``).

    Returns:
        A formatted markdown string listing matching topology snapshots,
        grouped by topology_name, or a message if no matches were found.
    """
    from maccre_core.orchestration.telemetry_db import get_db_path  # noqa: PLC0415

    try:
        db_path = get_db_path("definitions.db")
        if not os.path.exists(db_path):
            return "[RECALL_EMPTY] definitions.db does not yet exist. Run promote_topology_to_library after a successful swarm."

        pattern = f"%{query}%"
        with sqlite3.connect(db_path) as conn:
            conn.execute("PRAGMA journal_mode=WAL;")
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                """
                SELECT topology_name, node_id, agent_name, model_override, auto_tool,
                       next_node, temperature, instruction_override, job_id, timestamp
                FROM topology_library
                WHERE topology_name LIKE ? OR instruction_override LIKE ?
                ORDER BY timestamp DESC
                LIMIT 50
                """,
                (pattern, pattern),
            ).fetchall()

        if not rows:
            return f"[RECALL_EMPTY] No topologies matching '{query}' found in topology_library."

        grouped: dict[str, list[dict[str, Any]]] = {}
        for row in rows:
            d = dict(row)
            grouped.setdefault(d["topology_name"], []).append(d)

        lines: list[str] = [f"## Topology Recall: '{query}'\n"]
        for tname, nodes in grouped.items():
            ts = nodes[0]["timestamp"][:19]
            job = nodes[0]["job_id"]
            lines.append(f"### {tname} | job: `{job}` | recorded: {ts}")
            lines.append("| Node_ID | Agent_Name | Model | Tool | Next_Node | Output | Temp |")
            lines.append("|---------|------------|-------|------|-----------|--------|------|")
            for n in nodes:
                lines.append(
                    f"| {n['node_id']} | {n['agent_name']} | {n['model_override'] or 'default'} "
                    f"| {n['auto_tool'] or 'none'} | {n['next_node']} | {n.get('output_file') or 'none'} | {n['temperature']} |"
                )
            lines.append("")

        return "\n".join(lines)
    except Exception as e:
        return f"[ADMIN_FAULT] recall_topology failed: {e}"
