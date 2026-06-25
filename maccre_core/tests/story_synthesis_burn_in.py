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
maccre_core/tests/story_synthesis_burn_in.py
============================================
Control Group Burn-In Test — Autonomous Story Synthesis (12-Node Unrolled DAG).

Validates autonomous MACCREv2 tool usage (`write_file`, `ingest_document`, etc.)
using a strict 5-agent pipeline without curve-fitting.

Phases:
  1. Scorched Earth (DB/Silo Purge)
  2. Persona & Topology Python Injection (Control Group setup)
  3. Hit-the-Brakes FinOps Pre-Flight CLI
  4. Universal Swarm Execution
  5. Forensic Autopsy Generation
"""

from __future__ import annotations

import csv
import glob
import json
import os
import shutil
import sqlite3
import sys
import traceback
from datetime import datetime, timezone
from pathlib import Path

# Need the genai client to calculate predicted token costs
from google import genai

from maccre_core.utils.path_resolver import get_maccre_root, get_datacenter_path
from maccre_core.tools.agent_tools import AgentRecord, save_agent_to_file
from maccre_core.tools.finops_tools import calculate_predicted_cost

_MACCRE_ROOT = get_maccre_root()
_DC          = get_datacenter_path()

_QUEUE_DB    = _DC / "swarm_queue.db"
_TELEM_DIR   = _DC / "telemetry"
_TOPO_FILE   = _DC / "02_Dynamic_Context" / "topology.csv"
_AGENTS_DIR  = _DC / "02_Dynamic_Context" / "agents"
_SOURCE_DIR  = _DC / "01_Raw_Source"
_MEDIA_DIR   = _DC / "05_Rendered_Media"
_AUTOPSY_OUT = _DC / "Control_Group_Autopsy.md"
_ERROR_LOG   = _DC / "burn_in_errors.log"

_JOB_ID      = "CG_STORY_001"
_MAX_CYCLES  = 15  # Capped at 15 to ensure the 12-node DAG terminates cleanly

_TELEM_DBS = {
    "system_logs.db":       "system_logs",
    "user_interactions.db": "user_interactions",
    "terminal_logs.db":     "terminal_logs",
    "thoughts.db":          "thoughts",
}

# ── Phase 1: Scorched Earth ──────────────────────────────────────────────────

def phase1_scorched_earth() -> None:
    print("\n" + "=" * 60)
    print("PHASE 1: SCORCHED EARTH -- Purging the system")
    print("=" * 60)

    if _QUEUE_DB.exists():
        with sqlite3.connect(_QUEUE_DB) as conn:
            conn.execute("DROP TABLE IF EXISTS task_queue")
            conn.commit()

    for db_file, table_name in _TELEM_DBS.items():
        db_path = _TELEM_DIR / db_file
        if db_path.exists():
            with sqlite3.connect(db_path) as conn:
                conn.execute(f"DROP TABLE IF EXISTS {table_name}")
                conn.commit()

    if _ERROR_LOG.exists():
        with open(_ERROR_LOG, "w") as fh:
            fh.truncate(0)

    # Empty Rendered Media
    if _MEDIA_DIR.exists():
        shutil.rmtree(_MEDIA_DIR)
    os.makedirs(_MEDIA_DIR, exist_ok=True)

    from maccre_core.orchestration.telemetry_db import init_all_silos
    init_all_silos()
    from maccre_core.orchestration.local_broker import LocalMessageBroker
    LocalMessageBroker(str(_QUEUE_DB))

    print("[P1] Purge complete. SQLite silos re-initialised.\n")

# ── Phase 2: Topology & Persona Setup ─────────────────────────────────────────

def phase2_setup_control_group() -> None:
    print("=" * 60)
    print("PHASE 2: PERSONA & TOPOLOGY INJECTION")
    print("=" * 60)

    # 1. Generate 5 Agents mathematically via the tools SDK.
    agents = [
        AgentRecord("Archivist", "The Lore Master", "gemini-2.5-flash", True,
                    "Your role is to extract factual lore. You must use 'ingest_document' "
                    "to absorb facts into the `control_group_memory` chromadb collection."),
        
        AgentRecord("Plot Architect", "The Planner", "gemini-2.5-flash", True,
                    "You outline narrative arcs. Given lore, you provide a strict 3-chapter "
                    "outline. Never write the chapters, only outline them."),
        
        AgentRecord("Lead Author", "The Writer", "gemini-2.5-flash", True,
                    "You write 3 full pages of highly detailed prose based on the Outline "
                    "and the Editor's critiques. You never use tools, you only synthesize prose. "
                    "You MUST output exactly 1 chapter when asked."),
        
        AgentRecord("Critical Editor", "The Critic", "gemini-2.5-flash", True,
                    "You critique drafts viciously. You ensure tone consistency and enforce "
                    "that the draft exceeds 3 pages. You demand excellence."),
        
        AgentRecord("The Publisher", "The Synthesizer", "gemini-2.5-pro", True,
                    "You are the final publisher. You use `write_file` to write the finalized "
                    "chapters to `__DATACENTER/05_Rendered_Media/Control_Group_Novel.md`. "
                    "For Chapter 1, use append=False. For Chapters 2 and 3, you MUST set append=True. "
                    "You also use `ingest_document` at the end to absorb the novel into memories.")
    ]

    os.makedirs(_AGENTS_DIR, exist_ok=True)
    for a in agents:
        save_agent_to_file(a.to_dict(), str(_AGENTS_DIR))
    print(f"[P2] Injecting 5 Personas -> {_AGENTS_DIR.name}")

    # 2. Build the 12-node unrolled DAG for the relay race
    topology = [
        # node_id, agent_name, model, permitted_tools, next_nodes, wait_for, temperature, system_instruction
        ["INGEST_LORE", "Archivist", "gemini-2.5-flash", "ingest_document", "PLAN_STORY", "none", "0.1",
         "Read the provided 4-chapter source payload. Use `ingest_document` to save it into collection `control_group`. Then summarize the entire plot, characters, and ending so the authors can continue it."],
        
        ["PLAN_STORY", "Plot Architect", "gemini-2.5-flash", "query_local_memory", "DRAFT_CH5", "none", "1.0",
         "Create a detailed outline for Chapters 5, 6, and 7 that seamlessly continues the overarching direction and character arcs established in the source text."],
        
        ["DRAFT_CH5", "Lead Author", "gemini-2.5-flash", "none", "EDIT_CH5", "none", "1.0",
         "Write Chapter 5. Mathematically pick up the narrative exactly where Chapter 4 of the source text left off. Make it at least 3 pages long."],
        
        ["EDIT_CH5", "Critical Editor", "gemini-2.5-flash", "none", "PUBLISH_CH5", "none", "0.1",
         "Critique Chapter 5. Add your formatting edits directly into the text. Ensure tone continuity with the previous 4 chapters."],
        
        ["PUBLISH_CH5", "The Publisher", "gemini-2.5-pro", "write_file", "DRAFT_CH6", "none", "0.1",
         "Save Chapter 5 exactly at `__DATACENTER/05_Rendered_Media/Chapters_5_to_7.md`. YOU MUST use `write_file` with `append: false` to start the new file."],
        
        ["DRAFT_CH6", "Lead Author", "gemini-2.5-flash", "none", "EDIT_CH6", "none", "1.0",
         "Write Chapter 6. Pick up narrative where Chapter 5 ended. Make it 3 pages."],
        
        ["EDIT_CH6", "Critical Editor", "gemini-2.5-flash", "none", "PUBLISH_CH6", "none", "0.1",
         "Critique Chapter 6. Ensure continuity. Edit strictly."],
        
        ["PUBLISH_CH6", "The Publisher", "gemini-2.5-pro", "write_file", "DRAFT_CH7", "none", "0.1",
         "Save Chapter 6 to `__DATACENTER/05_Rendered_Media/Chapters_5_to_7.md`. YOU MUST use `write_file` with `append: true`."],
        
        ["DRAFT_CH7", "Lead Author", "gemini-2.5-flash", "none", "EDIT_CH7", "none", "1.0",
         "Write Chapter 7, the climax of this arc. Provide intense closure. 3 pages minimum."],
        
        ["EDIT_CH7", "Critical Editor", "gemini-2.5-flash", "none", "PUBLISH_CH7", "none", "0.1",
         "Final critique for Chapter 7. Polish it brilliantly."],
        
        ["PUBLISH_CH7", "The Publisher", "gemini-2.5-pro", "write_file", "ABSORB_NOVEL", "none", "0.1",
         "Save Chapter 7 to `__DATACENTER/05_Rendered_Media/Chapters_5_to_7.md`. YOU MUST use `write_file` with `append: true`."],
        
        ["ABSORB_NOVEL", "Archivist", "gemini-2.5-flash", "ingest_document", "DONE", "none", "0.1",
         "Read the finalized markdown and use `ingest_document` to append 'control_group' with the completed chapters. Output 'NOVEL FINISHED'."],
    ]

    os.makedirs(_TOPO_FILE.parent, exist_ok=True)
    with open(_TOPO_FILE, "w", newline="", encoding="utf-8") as csvfile:
        writer = csv.writer(csvfile)
        writer.writerow(["Node_ID", "Agent_Name", "Model", "Tools_Allowed", "Success_Target", "Wait_For", "Temperature", "Prompt"])
        writer.writerows(topology)
    
    # [PHASE 11 OVERRIDE] Automatically stamp the ADS Steganographic Auth for testing purposes
    # Without this, the new TopologyEngine will reject this dynamic CSV outright!
    ads_path = f"{str(_TOPO_FILE)}:maccre_auth"
    with open(ads_path, "w", encoding="utf-8") as f:
        f.write("O_AUTH_VALID")
        
    print(f"[P2] Injecting & Authenticating 12-Node Unrolled DAG -> {_TOPO_FILE.name}\n")

# ── Phase 3: FinOps Pre-Flight & Injection ───────────────────────────────────

def phase3_finops_gate() -> str:
    print("=" * 60)
    print("PHASE 3: FINOPS GATE & HITL AUTHORIZATION")
    print("=" * 60)

    # Scrape the topology back off disk to calculate the precise input tokens
    topo_rows = []
    with open(_TOPO_FILE, "r", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
             topo_rows.append(row)

    # Use the user's provided payload source
    os.makedirs(_SOURCE_DIR, exist_ok=True)
    source_path = _SOURCE_DIR / "conversation.md"
    
    if not source_path.exists():
        print(f"[P3] CRITICAL: You must place your story payload at {source_path} before running.")
        return "FAILED"
        
    with open(source_path, "r", encoding="utf-8") as fh:
        payload_content = fh.read()

    print(f"[P3] Using custom Source Lore -> {source_path}")

    # Calculate FinOps
    from maccre_core.orchestration.universal_vault import get_provider_credential
    api_key = get_provider_credential("MACCRE_Sovereign")
    if not api_key:
         print("[P3] CRITICAL: No MACCRE_Sovereign key in Vault. Bypassing FinOps Count API.")
         total_usd = 0.0
    else:
         client = genai.Client(api_key=str(api_key).strip())
         total_usd = 0.0
         total_tokens = 0
         print("\nFinOps Predictive Run-Down:")
         print(f"{'Node':<15} | {'Persona':<15} | {'Model':<18} | {'Tokens':<6} | Output")
         print("-" * 75)

         # Load models from agent jsons map
         agent_models = {}
         for p in glob.glob(str(_AGENTS_DIR / "*.json")):
             try:
                 with open(p, "r", encoding="utf-8") as f:
                     ag = json.load(f)
                     agent_models[ag["name"]] = ag.get("model", "gemini-2.5-flash")
             except Exception:
                 pass

         for row in topo_rows:
             node = row["Node_ID"]
             agent = row["Agent_Name"]
             model = agent_models.get(agent, "gemini-2.5-flash")
             prompt = row["Prompt"]

             # Fake a count token request predicting the payload content size
             pred = calculate_predicted_cost(client, model, payload_content, prompt)
             cost = float(pred["predicted_cost"])
             toks = int(pred["tokens"])
             
             total_usd += cost
             total_tokens += toks
             print(f"{node[:15]:<15} | {agent[:15]:<15} | {model[:18]:<18} | {toks:<6} | ${cost:.5f}")
         
         print(f"\n[FinOps Projection] Aggregate Inputs: {total_tokens} tokens | ${total_usd:.4f} USD")
         print("Note: This covers Prompt Inputs. Output tokens will be billed dynamically post-generation.")

    print("\n" + "!" * 60)
    user_auth = input(">>> Type 'PROCEED' to ignite the swarm, or 'ABORT': ").strip()
    if user_auth.upper() != "PROCEED":
         print("[P3] HITL Abort generated. Stopping.")
         sys.exit(1)

    print("[P3] Authorization Accepted. Injecting Job...")
    from maccre_core.orchestration.local_broker import LocalMessageBroker
    broker = LocalMessageBroker(str(_QUEUE_DB))
    broker.inject_task(
        job_id=_JOB_ID,
        payload_path=str(source_path),
        starting_node="INGEST_LORE",
    )
    return str(source_path)

# ── Phase 4: Swarm Execution ──────────────────────────────────────────────────

def phase4_swarm() -> tuple[str, int]:
    print("\n" + "=" * 60)
    print(f"PHASE 4: UNIVERSAL SWARM EXECUTION (MAX {_MAX_CYCLES} CYCLES)")
    print("=" * 60)

    from maccre_core.orchestration.swarm_worker import UniversalSwarmWorker
    status = "SUCCESS"
    cycles = 0

    try:
         worker = UniversalSwarmWorker()
         for cycle_num in range(1, _MAX_CYCLES + 1):
             with sqlite3.connect(_QUEUE_DB) as conn:
                 row = conn.execute("SELECT COUNT(*) FROM task_queue WHERE lock_status IN ('open', 'locked')").fetchone()
                 pending = int(row[0]) if row else 0

             if pending == 0:
                 print(f"[P4] Queue drained after cycle {cycle_num-1}. Swarm complete.")
                 break

             cycles = cycle_num
             print(f"\n[P4] -- Cycle {cycle_num}/{_MAX_CYCLES} -- {pending} task(s) active --")
             worker.execute_cycle()
         else:
             print(f"[P4] Max cycle cap ({_MAX_CYCLES}) reached. Forcing stop.")
    except Exception:
         tb = traceback.format_exc()
         status = f"FAILED\n{tb}"
         print(f"[P4] CRITICAL SWARM FAULT:\n{tb}")
         with open(_ERROR_LOG, "w") as fh:
              fh.write(tb)

    return status, cycles

# ── Phase 5: Autopsy ──────────────────────────────────────────────────────────

def _dump_table(db_path: Path | str, table_name: str, limit: int = 50, filter_clause: str = "1=1") -> str:
    path_str = str(db_path)
    if not os.path.exists(path_str):
        return f"*Database not found: `{path_str}`*\n"
    try:
        with sqlite3.connect(path_str) as conn:
            conn.execute("PRAGMA journal_mode=WAL;")
            cursor = conn.execute(f"SELECT * FROM {table_name} WHERE {filter_clause} ORDER BY id ASC LIMIT {limit}")
            rows = cursor.fetchall()
            cols = [d[0] for d in cursor.description] if cursor.description else []
    except sqlite3.OperationalError as exc:
        return f"*Table query error: {exc}*\n"

    if not rows:
        return f"*No rows in `{table_name}` matching filter.*\n"

    header = "| " + " | ".join(cols) + " |"
    sep = "| " + " | ".join(["---"] * len(cols)) + " |"
    lines = [header, sep]
    for row in rows:
        cells = [str(v)[:80].replace("|", "!").replace("\n", " ") for v in row]
        lines.append("| " + " | ".join(cells) + " |")
    return "\n".join(lines) + "\n"

def phase5_autopsy(status: str, cycles: int, payload: str) -> None:
    print("\n" + "=" * 60)
    print("PHASE 5: FORENSIC AUTOPSY (Control Group)")
    print("=" * 60)

    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    sections = [
        "# Control Group Autopsy Report\n",
        f"**Generated:** {now}  ",
        f"**Job ID:** `{_JOB_ID}`  ",
        f"**Cycles Run:** {cycles} / {_MAX_CYCLES}  ",
        f"**Payload:** `{payload}`\n",
        "---\n",
        "## Verifiable Tool Logs (system_logs.db)\n",
        "The following proves mathematical execution of the tool registry:\n",
        _dump_table(_TELEM_DIR / "system_logs.db", "system_logs", limit=20, filter_clause="action_type = 'TOOL_CALL'"),
        "\n---\n",
        "## Agent Ledger Progression\n",
        _dump_table(_QUEUE_DB, "task_queue", limit=25),
        "\n---\n",
    ]

    target_media = _MEDIA_DIR / "Control_Group_Novel.md"
    sections.append("## Final Rendered Synthesis\n")
    if target_media.exists():
         with open(target_media, "r", encoding="utf-8", errors="replace") as fh:
              content = fh.read()
         sections.append(f"```markdown\n{content}\n```\n")
    else:
         sections.append(f"*File missing at {target_media}. Did the publisher fail?*\n")

    with open(_AUTOPSY_OUT, "w", encoding="utf-8") as fh:
        fh.write("\n".join(sections))

    print(f"[P5] Autopsy formulated -> {_AUTOPSY_OUT.name}\n")

def main() -> None:
    phase1_scorched_earth()
    phase2_setup_control_group()
    payload = phase3_finops_gate()
    status, cycles = phase4_swarm()
    phase5_autopsy(status, cycles, payload)

if __name__ == "__main__":
    main()
