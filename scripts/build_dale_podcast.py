"""
scripts/build_dale_podcast.py
=====================================
MACCREv2 Dale Earnhardt Podcast Swarm — Topology Generator

4-node sequential swarm that researches, scripts, voice-configures, and renders
a 3-speaker NASCAR podcast video about Dale Earnhardt Sr.

Run: python scripts/build_dale_podcast.py
Then: python maccre.py launch B:\MACCREv2\MACCRE_Dale_Podcast.xlsx
"""
from __future__ import annotations

import sys
from pathlib import Path

# ── Sovereign path injection ───────────────────────────────────────────────────
vendor_dir = str(Path(__file__).parent.parent / "maccre_core" / "_vendor")
if vendor_dir not in sys.path:
    sys.path.insert(0, vendor_dir)

sys.path.insert(0, str(Path(__file__).parent.parent))

from maccre_core._net.ooxml import (
    Alignment, Border, Font, PatternFill, Side, Workbook, get_column_letter
)

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
        fill_key = "bg_row_a" if ri % 2 != 0 else "bg_row_b"
        for ci, val in enumerate(row_data, 1):
            dc = ws.cell(row=ri, column=ci, value=val)
            dc.font = _body_font()
            dc.fill = PatternFill("solid", PAL[fill_key])
            dc.border = _border()
            dc.alignment = Alignment(wrap_text=True, vertical="top")


def build_workbook() -> None:
    wb = Workbook()

    # ── 1. PROJECT_DEFINITION ────────────────────────────────────────────────
    ws_proj = wb.create_sheet("PROJECT_DEFINITION")
    proj_cols = [("KEY", 30), ("VALUE", 80)]
    proj_rows = [
        ("PROJECT_NAME", "DalePodcast"),
        ("DESCRIPTION",  "4-node swarm testing multi-modal render pipeline via a NASCAR documentary podcast."),
        ("SESSION_LABEL", "dale_podcast_burn_in"),
    ]
    _write_sheet(ws_proj, "PROJECT DEFINITION", proj_cols, proj_rows)

    # ── 2. SWARM_REQUEST ────────────────────────────────────────────────────
    ws_req = wb.create_sheet("SWARM_REQUEST")
    req_cols = [
        ("PROJECT_NAME", 20), ("DESCRIPTION", 60), ("START_NODE", 25),
        ("PAYLOAD_TEXT", 100), ("COMPUTE_TIER", 15),
    ]
    payload = (
        "MISSION: Produce a 3-speaker podcast video about Dale Earnhardt Sr. "
        "covering his career stats, the Intimidator persona, the 1998 Daytona win, "
        "the 2001 crash, and his safety legacy. Generate a JSON manifest, voice roster, "
        "and execute the render_video tool to produce the final MP4."
    )
    req_rows = [
        ("DalePodcast", "Dale Earnhardt Podcast Render Test", "RESEARCH", payload, "cloud"),
    ]
    _write_sheet(ws_req, "SWARM INITIATION", req_cols, req_rows)

    # ── 3. AGENTS ───────────────────────────────────────────────────────────
    ws_ag = wb.create_sheet("AGENTS")
    ag_cols = [
        ("AGENT_NAME", 22), ("MODEL", 26), ("ROLE", 28), ("SEARCH_GROUNDING", 18),
        ("TEMPERATURE", 14), ("TOOLS", 35), ("PERSONA", 120),
    ]
    ag_rows = [
        (
            "Researcher",
            "gemini-2.5-flash",
            "NASCAR Historian",
            "TRUE",
            0.7,
            "search_web,write_file",
            "You are the Researcher. Use search_web to gather accurate facts on Dale Earnhardt Sr: "
            "career stats, 1998 Daytona win, 2001 crash, HANS device legacy. "
            "Organize findings into a markdown report and save via write_file to 04_Code_Artifacts/{SESSION_ID}/research_notes.md."
        ),
        (
            "Scriptwriter",
            "gemini-3-flash-preview",
            "Podcast Producer",
            "FALSE",
            1.0,
            "read_file,write_file",
            "You are the Scriptwriter. Read 04_Code_Artifacts/{SESSION_ID}/research_notes.md. "
            "Write an 18-24 scene podcast script between Randy (emotional fan), Mark (analytical), "
            "and Sammy (enthusiast). Format as a strict JSON array of objects with keys: "
            "'speaker', 'text' (include [micro-direction] tags), and 'video_prompt' (documentary still photo prompts). "
            "Save the JSON array via write_file to 04_Code_Artifacts/{SESSION_ID}/dale_manifest.json."
        ),
        (
            "VoiceSetup",
            "gemini-2.5-flash",
            "Audio Engineer",
            "FALSE",
            0.1,
            "write_dynamic_context",
            "You are VoiceSetup. Create the voice profile roster for the TTS engine. "
            "Write a strict JSON dictionary mapping speaker names to voice profiles. "
            "Randy: voice='Fenrir'. Mark: voice='Orus'. Sammy: voice='Charon'. "
            "Include 'character' description for each. "
            "Save the JSON via write_dynamic_context to 02_Dynamic_Context/voice_roster.json."
        ),
        (
            "Director",
            "gemini-2.5-flash",
            "Render Orchestrator",
            "FALSE",
            0.3,
            "read_file,render_video",
            "You are the Director. First, read the manifest from 04_Code_Artifacts/{SESSION_ID}/dale_manifest.json. "
            "Then, call the render_video tool, passing the raw string contents of the manifest "
            "as the manifest_json argument. Ensure the voice_roster.json was already placed in 02_Dynamic_Context."
        )
    ]
    _write_sheet(ws_ag, "AGENT ROSTER", ag_cols, ag_rows)

    # ── 4. TOPOLOGY ─────────────────────────────────────────────────────────
    ws_top = wb.create_sheet("TOPOLOGY")
    top_cols = [
        ("NODE_ID", 28), ("AGENT_NAME", 22), ("NEXT_NODE", 90),
        ("AUTO_TOOL", 35), ("TEMPERATURE", 14), ("MAX_RECURSION", 15),
        ("INSTRUCTION_OVERRIDE", 110),
    ]
    
    top_rows = [
        (
            "RESEARCH",
            "Researcher",
            "SCRIPTWRITER",
            "search_web",
            0.7,
            5,
            "Begin the pipeline. Perform 4-6 searches to gather facts on Dale Earnhardt, compile them, and write to research_notes.md."
        ),
        (
            "SCRIPTWRITER",
            "Scriptwriter",
            "VOICE_SETUP",
            "none",
            1.0,
            2,
            "Read the research notes, craft the podcast dialogue manifest JSON, and write it to dale_manifest.json."
        ),
        (
            "VOICE_SETUP",
            "VoiceSetup",
            "DIRECTOR",
            "write_file",
            0.1,
            2,
            "Write the voice_roster.json to 02_Dynamic_Context mapping Randy, Mark, and Sammy."
        ),
        (
            "DIRECTOR",
            "Director",
            "STOP",
            "render_video",
            0.3,
            2,
            "Read the dale_manifest.json and execute render_video to produce the final MP4 artifact."
        ),
    ]
    _write_sheet(ws_top, "SWARM ROUTING DAG", top_cols, top_rows)

    # ── 5. PIPELINE_CONFIG ───────────────────────────────────────────────────
    ws_cfg = wb.create_sheet("PIPELINE_CONFIG")
    cfg_cols = [("KEY", 35), ("VALUE", 80)]
    cfg_rows = [
        ("INGEST_BEFORE_RUN", "FALSE"),
        ("CANONIZE_AFTER_RUN", "FALSE"),
        ("LOG_PATH", "B:\\MACCREv2\\__DATACENTER\\DalePodcast\\03_Agent_Ledgers"),
        ("OUTPUT_PATH", "B:\\MACCREv2\\__DATACENTER\\DalePodcast\\05_Rendered_Media"),
        ("MEMORY_BACKEND", "sovereign"),
        ("TELEMETRY_MODE", "json"),
    ]
    _write_sheet(ws_cfg, "PIPELINE CONFIGURATION", cfg_cols, cfg_rows)

    out = Path("B:/MACCREv2/MACCRE_Dale_Podcast.xlsx")
    wb.save(str(out))
    print(f"\\n[OK] Dale Podcast Workbook generated: {out}")
    print("\\n     To run:  python maccre.py launch B:\\MACCREv2\\MACCRE_Dale_Podcast.xlsx")

if __name__ == "__main__":
    build_workbook()
