"""
scripts/build_live_session.py
=====================================
MACCREv2 Live Swarm — Topology Generator

This script dynamically generates the MACCRE_LiveSession.xlsx topology workbook.
It creates a multi-agent Live Swarm with 3 agents and sets their Live_Profile flag.

Run: python scripts/build_live_session.py
Then: python maccre.py launch LiveSession --workbook B:\\MACCREv2\\MACCRE_LiveSession.xlsx
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
        ("LiveSession", "Real-time conversational Swarm with 3 agents and ScoreKeeper tracking.", "START", "cloud", "none"),
    ]
)

# ── Dynamic Agent & Topology Generation ───────────────────────────────────────
agent_rows = []
topology_rows = []

# AGENTS
agent_rows.append((
    "Agent_Alpha", "gemini-3.1-flash-live-preview", "Alpha Leader", "FALSE", 1.0, "none",
    "You are Alpha. You are assertive, analytical, and highly structured. You drive the conversation forward. Keep your responses conversational and concise."
))
agent_rows.append((
    "Agent_Beta", "gemini-3.1-flash-live-preview", "Beta Synthesizer", "FALSE", 1.0, "none",
    "You are Beta. You are empathetic, creative, and try to find middle ground. You often build on what Alpha says. Keep your responses conversational and concise."
))
agent_rows.append((
    "Agent_Gamma", "gemini-3.1-flash-live-preview", "Gamma Critic", "FALSE", 1.0, "none",
    "You are Gamma. You are skeptical, chaotic, and like to poke holes in theories. You challenge Alpha and Beta. Keep your responses conversational and concise."
))

# TOPOLOGY
# We use comma-separated Next_Node to trigger Fan-out (concurrent agents)
topology_rows.append((
    "START", "Agent_Alpha", "none",
    "", "NODE_B, NODE_C", "TRUE" # Live_Profile = TRUE
))
topology_rows.append((
    "NODE_B", "Agent_Beta", "none",
    "", "DONE", "TRUE"
))
topology_rows.append((
    "NODE_C", "Agent_Gamma", "none",
    "", "DONE", "TRUE"
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
    [("Node_ID", 20), ("Agent_Name", 25), ("Wait_For", 30), ("Instruction_Override", 150), ("Next_Node", 20), ("Live_Profile", 15)],
    topology_rows
)

# 4. CONFIG SHEETS
ws_pipe = wb.create_sheet("SESSION_CONFIG")
_write_sheet(ws_pipe, "SESSION CONFIG", [("SETTING", 30), ("VALUE", 40)], [("MAX_CONCURRENT_AGENTS", "25")])

ws_mem = wb.create_sheet("MEMORY_CONFIG")
_write_sheet(ws_mem, "MEMORY CONFIG", [("SETTING", 30), ("VALUE", 40)], [("REQUIRE_APPROVAL", "false")])

ws_vault = wb.create_sheet("VAULT_KEYS")
_write_sheet(ws_vault, "VAULT INJECTION", [("SETTING", 30), ("VALUE", 40)], [])

out_path = get_maccre_root() / "MACCRE_LiveSession.xlsx"
wb.save(out_path)

print(f"\\n[OK] Live Session Workbook generated: {out_path}")
print(f"     To run:  python maccre.py launch LiveSession --workbook {out_path}")
