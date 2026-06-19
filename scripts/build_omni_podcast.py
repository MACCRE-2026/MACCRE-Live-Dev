"""
scripts/build_omni_podcast.py
=====================================
MACCREv2 Omni-Archive Podcast Swarm — Topology Generator

This script dynamically scans the __DATACENTER for all valid projects.
It builds a 6-phase Map-Reduce pipeline:
1. Init_Agent: Links all discovered projects.
2. Analyst Layer (Map): 1 agent per project, queries telemetry & semantic DB.
3. Synthesizer Layer (Reduce 1): Consolidates every 3 analysts.
4. Final Synthesizer Layer (Reduce 2): Consolidates the two halves.
5. Scriptwriter: Writes a 4-speaker podcast script.
6. Director: Renders the audio podcast.

Run: python scripts/build_omni_podcast.py
Then: python maccre.py launch OmniPodcast --workbook B:\\MACCREv2\\MACCRE_OmniPodcast.xlsx
"""
from __future__ import annotations

import sys
from pathlib import Path

# ── Sovereign path injection ───────────────────────────────────────────────────
vendor_dir = str(Path(__file__).parent.parent / "maccre_core" / "_vendor")
if vendor_dir not in sys.path:
    sys.path.insert(0, vendor_dir)

sys.path.insert(0, str(Path(__file__).parent.parent))

from maccre_core._net.ooxml import (  # noqa: E402
    Alignment, Border, Font, PatternFill, Side, Workbook, get_column_letter
)
from maccre_core.utils.path_resolver import get_maccre_root  # noqa: E402

# ── Project Discovery ──────────────────────────────────────────────────────────
def get_valid_projects() -> list[str]:
    datacenter = get_maccre_root() / "__DATACENTER"
    if not datacenter.exists():
        return []
    
    projects = []
    # Core system directories to ignore
    ignore_list = {
        "01_Raw_Source", "02_Dynamic_Context", "03_Agent_Ledgers",
        "04_Code_Artifacts", "05_Rendered_Media",
        "__GLOBAL_LEDGER", "telemetry", "GLOBAL", "UNNAMED"
    }
    
    for silo in datacenter.iterdir():
        if silo.is_dir() and not silo.name.startswith(".") and silo.name not in ignore_list:
            projects.append(silo.name)
    
    return sorted(projects)

PROJECTS = get_valid_projects()
if not PROJECTS:
    print("CRITICAL: No valid projects found in __DATACENTER to scan.")
    sys.exit(1)

print(f"[*] Discovered {len(PROJECTS)} projects for Omni-Podcast extraction.")

# ── Style System ───────────────────────────────────────────────────────────────
PAL = {
    "bg_dark":    "0A0F1E",
    "bg_header":  "141C2E",
    "bg_row_a":   "0D1117",
    "bg_row_b":   "131A26",
    "fg_title":   "7AFFB2",
    "fg_header":  "94A3B8",
    "fg_key":     "7DD3FC",
    "fg_body":    "C9D1D9",
    "border":     "1E2D45",
}

def _thin() -> Side:
    return Side(style="thin", color=PAL["border"])

def _border() -> Border:
    t = _thin()
    return Border(left=t, right=t, top=t, bottom=t)

def _title_font() -> Font:
    return Font(bold=True, size=13, color=PAL["fg_title"], name="Calibri")

def _header_font() -> Font:
    return Font(bold=True, size=10, color=PAL["fg_key"], name="Calibri")

def _body_font() -> Font:
    return Font(size=10, color=PAL["fg_body"], name="Calibri")


def _write_sheet(ws: Workbook, title: str, cols: list[tuple[str, float]], rows: list[tuple[str | float, ...]]) -> None:
    n = len(cols)

    ws.merge_cells(f"A1:{get_column_letter(n)}1")
    cell = ws.cell(row=1, column=1, value=title)
    cell.font = _title_font()
    cell.fill = PatternFill("solid", PAL["bg_dark"])
    cell.alignment = Alignment(horizontal="center", vertical="center")
    ws.row_dimensions[1].height = 26

    for ci, (col_name, _) in enumerate(cols, 1):
        hc = ws.cell(row=2, column=ci, value=col_name)
        hc.font = _header_font()
        hc.fill = PatternFill("solid", PAL["bg_header"])
        hc.border = _border()
        hc.alignment = Alignment(horizontal="center", vertical="center", wrap_text=False)

    for ci, (_, width) in enumerate(cols, 1):
        ws.column_dimensions[get_column_letter(ci)].width = width

    for ri, row_data in enumerate(rows, 3):
        bg = PAL["bg_row_a"] if ri % 2 == 1 else PAL["bg_row_b"]
        for ci, val in enumerate(row_data, 1):
            c = ws.cell(row=ri, column=ci, value=val)
            c.font = _body_font()
            c.fill = PatternFill("solid", bg)
            c.border = _border()
            c.alignment = Alignment(vertical="top", wrap_text=True)

# ── Workbook Construction ──────────────────────────────────────────────────────
wb = Workbook()

# 1. SWARM_REQUEST
ws_req = wb.create_sheet("SWARM_REQUEST")
_write_sheet(
    ws_req,
    "MACCREv2 SWARM DEPLOYMENT TICKET",
    [("PROJECT_NAME", 20), ("DESCRIPTION", 60), ("START_NODE", 25), ("COMPUTE_TIER", 15), ("PAYLOAD_PATH", 40)],
    [
        ("OmniPodcast", f"Map-Reduce extraction across {len(PROJECTS)} projects into a 4-speaker podcast.", "INIT_PHASE", "cloud", "none"),
    ]
)

# ── Dynamic Agent & Topology Generation ───────────────────────────────────────
agent_rows = []
topology_rows = []

# --- INIT PHASE ---
agent_rows.append((
    "Init_Agent", "gemini-3-flash-preview", "Swarm Archon", "TRUE", 0.1, "link_projects",
    "You are Init_Agent. Your objective is to ensure Synaptic Bridge access is granted for all projects. "
    f"Use the 'link_projects' tool and pass this exact comma-separated string: '{', '.join(PROJECTS)}'. "
    "Do this completely autonomously to whitelist all projects in a single turn."
))
topology_rows.append((
    "INIT_PHASE", "Init_Agent", "none",
    f"Call the link_projects tool and pass the string '{','.join(PROJECTS)}'. Once done, return a success message.",
    ",".join([f"ANALYST_{p}" for p in PROJECTS])
))

# --- ANALYST LAYER (Map) ---
CHUNK_SIZE = 3
chunks = [PROJECTS[i:i + CHUNK_SIZE] for i in range(0, len(PROJECTS), CHUNK_SIZE)]
synthesizer_nodes = []

for i, chunk in enumerate(chunks, 1):
    synth_node_id = f"REDUCE1_{i}"
    synthesizer_nodes.append(synth_node_id)
    for proj in chunk:
        ag_name = f"Analyst_{proj}"
        agent_rows.append((
            ag_name, "gemini-3-flash-preview", "Data Extractor", "FALSE", 0.5, "query_foreign_memory, generate_telemetry_report",
            f"You are the Data Extractor for project: '{proj}'. "
            f"1. Call query_foreign_memory with target_project='{proj}' and query='project goal architecture results'. "
            f"2. Call generate_telemetry_report with project_id='{proj}'. "
            "Synthesize the findings into a highly structured markdown summary of the project's purpose, actions taken, and final results."
        ))
        
        topology_rows.append((
            f"ANALYST_{proj}", ag_name, "INIT_PHASE",
            f"Query the memory and telemetry for '{proj}', synthesize the results, and return the summary.",
            synth_node_id
        ))

# --- REGIONAL SYNTHESIZER LAYER (Reduce 1) ---
mid = len(synthesizer_nodes) // 2
for i, chunk in enumerate(chunks, 1):
    ag_name = f"Synthesizer_{i}"
    wait_for = "|".join([f"ANALYST_{p}" for p in chunk])
    target_master = "MASTER_A" if i <= mid else "MASTER_B"
    
    agent_rows.append((
        ag_name, "gemini-2.5-pro", "Regional Synthesizer", "FALSE", 0.7, "",
        f"You are Regional Synthesizer {i}. You will receive {len(chunk)} project summaries. "
        "Combine them into a single, cohesive narrative report detailing the overlapping themes, individual goals, and overall success of these projects. "
        "Do not lose critical detail, but ensure it reads smoothly."
    ))
    
    topology_rows.append((
        f"REDUCE1_{i}", ag_name, wait_for,
        "Synthesize the provided analyst summaries into a comprehensive regional report.",
        target_master
    ))

# --- MASTER SYNTHESIZER LAYER (Reduce 2) ---
mid = len(synthesizer_nodes) // 2
group_a = synthesizer_nodes[:mid]
group_b = synthesizer_nodes[mid:]

agent_rows.append((
    "Final_Synthesizer_A", "gemini-3.1-pro-preview", "Master Editor", "FALSE", 0.7, "",
    "You are Final_Synthesizer_A. Combine the provided regional reports into a master volume (Part 1). "
    "Identify overarching themes and global accomplishments across the MACCRE Datacenter."
))
topology_rows.append((
    "MASTER_A", "Final_Synthesizer_A", "|".join(group_a),
    "Write the definitive Part 1 summary of the datacenter operations.",
    "SCRIPTWRITER"
))

agent_rows.append((
    "Final_Synthesizer_B", "gemini-3.1-pro-preview", "Master Editor", "FALSE", 0.7, "",
    "You are Final_Synthesizer_B. Combine the provided regional reports into a master volume (Part 2). "
    "Identify overarching themes and global accomplishments across the MACCRE Datacenter."
))
topology_rows.append((
    "MASTER_B", "Final_Synthesizer_B", "|".join(group_b),
    "Write the definitive Part 2 summary of the datacenter operations.",
    "SCRIPTWRITER"
))

# --- PODCAST LAYER ---
agent_rows.append((
    "Podcast_Scriptwriter", "gemini-2.5-pro", "Scriptwriter", "FALSE", 0.8, "write_file",
    "You are the Podcast Scriptwriter. You will receive two massive master reports detailing all projects in the MACCRE Datacenter. "
    "Your job is to write a dynamic, 4-speaker podcast script that discusses every single project. "
    "The speakers are: 'Randy' (Host), 'Mark' (Co-Host), 'Sammy' (Guest), 'Alistair' (Guest). "
    "They should banter, analyze, and take turns presenting the projects. "
    "Output the script in plain Markdown format like this:\n**Randy**: Welcome to the show!\n**Mark**: Glad to be here.\n"
    "Save this markdown via write_file to 04_Code_Artifacts/{SESSION_ID}/omni_podcast.md."
))
topology_rows.append((
    "SCRIPTWRITER", "Podcast_Scriptwriter", "MASTER_A|MASTER_B",
    "Write the Markdown podcast script for the Omni-Archive Datacenter extraction.",
    "DIRECTOR_PARSER"
))

agent_rows.append((
    "Podcast_Parser", "gemini-2.5-pro", "Data Synthesizer", "FALSE", 0.1, "read_file, write_file",
    "You are the Podcast Parser. 1. Use read_file to read 04_Code_Artifacts/{SESSION_ID}/omni_podcast.md. "
    "2. Parse the markdown dialogue into a strict JSON array where each object has 'speaker' and 'text'. "
    "3. Save this JSON array via write_file to 04_Code_Artifacts/{SESSION_ID}/omni_podcast.json. "
    "You are a deterministic parser. Do not hallucinate dialogue, just convert the format."
))
topology_rows.append((
    "DIRECTOR_PARSER", "Podcast_Parser", "none",
    "Parse the markdown script into the required JSON array format for the audio renderer.",
    "DIRECTOR"
))

agent_rows.append((
    "Podcast_Director", "gemini-2.5-flash", "Audio Director", "FALSE", 0.1, "read_file, render_podcast_audio",
    "You are the Audio Director. 1. Use read_file to read 04_Code_Artifacts/{SESSION_ID}/omni_podcast.json. "
    "2. Pass the exact raw JSON string into the render_podcast_audio tool. Do not modify the JSON string."
))
topology_rows.append((
    "DIRECTOR", "Podcast_Director", "none",
    "Execute the rendering pipeline for the podcast.",
    "STOP"
))

# 2. AGENTS
ws_ag = wb.create_sheet("AGENTS")
_write_sheet(
    ws_ag,
    "AGENT ROSTER",
    [("Agent_Name", 25), ("Model", 30), ("Role", 20), ("Search_Grounding", 15), ("Temperature", 12), ("Tools", 60), ("Persona", 150)],
    agent_rows
)

# 3. TOPOLOGY
ws_tp = wb.create_sheet("TOPOLOGY")
_write_sheet(
    ws_tp,
    "SWARM TOPOLOGY",
    [("Node_ID", 20), ("Agent_Name", 25), ("Wait_For", 30), ("Instruction_Override", 150), ("Next_Node", 20)],
    topology_rows
)

# 4. CONFIG SHEETS
ws_pipe = wb.create_sheet("SESSION_CONFIG")
_write_sheet(ws_pipe, "SESSION CONFIG", [("SETTING", 30), ("VALUE", 40)], [("MAX_CONCURRENT_AGENTS", "25")])

ws_mem = wb.create_sheet("MEMORY_CONFIG")
_write_sheet(ws_mem, "MEMORY CONFIG", [("SETTING", 30), ("VALUE", 40)], [("REQUIRE_APPROVAL", "false")])

ws_vault = wb.create_sheet("VAULT_KEYS")
_write_sheet(ws_vault, "VAULT INJECTION", [("SETTING", 30), ("VALUE", 40)], [])

out_path = get_maccre_root() / "MACCRE_OmniPodcast.xlsx"
wb.save(out_path)

print(f"\n[OK] Omni-Podcast Workbook generated: {out_path}")
print(f"     To run:  python maccre.py launch OmniPodcast --workbook {out_path}")
