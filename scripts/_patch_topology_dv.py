"""Patch TOPOLOGY agent DV to warning-mode, then populate workbook for USER_TEST1."""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# ── 1. Patch generate_global_template.py ──────────────────────────────────────
gen_path = ROOT / "scripts" / "generate_global_template.py"
src = gen_path.read_text(encoding="utf-8")

# Find the _add_dv line for agent_names_inline in the topology section
old_pattern = re.compile(
    r"    _add_dv\(ws_topo, f\"B3:B\{topo_end\}\", f'\"(\{agent_names_inline\[:250\])\"'\)"
)
new_block = (
    "    _add_dv_warn(\n"
    "        ws_topo, f\"B3:B{topo_end}\", f'\"{agent_names_inline[:250]}\"',\n"
    '        error_title="Agent Not in Roster",\n'
    "        error_msg=(\n"
    '            "This agent is not in the current project roster. "\n'
    '            "Click YES to use this name - the agent must be defined "\n'
    '            "in the AGENTS sheet and will be minted on first execution."\n'
    "        ),\n"
    "    )"
)

# simpler: direct substring replace using the exact bytes we know are there
TARGET = "    _add_dv(ws_topo, f\"B3:B{topo_end}\", f'\"{agent_names_inline[:250]}\"')"
if TARGET in src:
    src = src.replace(TARGET, new_block)
    gen_path.write_text(src, encoding="utf-8")
    print("PATCHED: TOPOLOGY agent DV -> warning-mode")
else:
    print("WARNING: Could not find TOPOLOGY DV target - patch skipped")
    # show context
    for i, line in enumerate(src.splitlines(), 1):
        if "agent_names_inline" in line:
            print(f"  L{i}: {repr(line)}")

# ── 2. Populate the workbook ──────────────────────────────────────────────────
import sys
sys.path.insert(0, str(ROOT))

from maccre_core._vendor.openpyxl import load_workbook

WB_PATH = ROOT / "MACCRE_Global.xlsx"
wb = load_workbook(str(WB_PATH))

# ── Helpers ───────────────────────────────────────────────────────────────────
def _hmap(ws):  # type: ignore[no-untyped-def]
    """Build col-index map from header row 2."""
    result: dict[str, int] = {}
    for ci, cell in enumerate(ws[2], start=1):
        if cell.value:
            key = str(cell.value).strip().upper().replace(" ", "_").lstrip("★* ")
            result[key] = ci
    return result

def _set(ws, row: int, hmap: dict[str, int], col_name: str, value: object) -> None:  # type: ignore[no-untyped-def]
    """Write value to named column in given row."""
    ci = hmap.get(col_name.upper())
    if ci:
        ws.cell(row=row, column=ci, value=value)

# ── SWARM_REQUEST ─────────────────────────────────────────────────────────────
ws_req = wb["SWARM_REQUEST"]
hmap_req = _hmap(ws_req)
print("SWARM_REQUEST headers:", hmap_req)

DATA_ROW = 3
_set(ws_req, DATA_ROW, hmap_req, "PROJECT_NAME",  "USER_TEST1")
_set(ws_req, DATA_ROW, hmap_req, "DESCRIPTION",   "5-agent parallel research + synthesis validation run")
_set(ws_req, DATA_ROW, hmap_req, "COMPUTE_TIER",  "cloud")
_set(ws_req, DATA_ROW, hmap_req, "PAYLOAD_TEXT",
    "[TOPIC - REPLACE BEFORE FIRING]: "
    "Research the current state of AI-assisted scientific discovery. "
    "Each agent should investigate a different facet: Randy=recent breakthroughs, "
    "Mark=key tools and platforms, Sammy=major institutions and funding, "
    "Tommy=challenges and limitations. PoosMcfloos synthesizes all four into a final report.")
_set(ws_req, DATA_ROW, hmap_req, "START_NODE",    "RANDY_RESEARCH")
_set(ws_req, DATA_ROW, hmap_req, "OUTPUT_FOLDER", "04_Code_Artifacts")

# ── TOPOLOGY ──────────────────────────────────────────────────────────────────
ws_topo = wb["TOPOLOGY"]
hmap_topo = _hmap(ws_topo)
print("TOPOLOGY headers:", hmap_topo)

# Linear chain: Randy → Mark → Sammy → Tommy → PoosMcfloos → STOP
# Each researcher writes to their own file; synthesizer reads via fts/query_local
NODES = [
    {
        "NODE_ID":            "RANDY_RESEARCH",
        "AGENT_NAME":         "Randy",
        "NEXT_NODE":          "MARK_RESEARCH",
        "MODEL_OVERRIDE":     "",
        "TEMPERATURE":        "1.0",
        "INSTRUCTION_OVERRIDE": (
            "Your research facet: RECENT BREAKTHROUGHS in AI-assisted scientific discovery. "
            "Use search_web to find the 3-5 most significant recent developments (2023-2025). "
            "Write a structured markdown report to write_file with path "
            "'04_Code_Artifacts/randy_research.md'. "
            "Include: headline, key findings, source URLs."
        ),
        "WAIT_FOR":           "",
        "FAILURE_TARGET":     "STOP",
        "MAX_RECURSION":      "0",
        "ARTIFACT_PATH":      "04_Code_Artifacts/randy_research.md",
    },
    {
        "NODE_ID":            "MARK_RESEARCH",
        "AGENT_NAME":         "Mark",
        "NEXT_NODE":          "SAMMY_RESEARCH",
        "MODEL_OVERRIDE":     "",
        "TEMPERATURE":        "1.0",
        "INSTRUCTION_OVERRIDE": (
            "Your research facet: KEY TOOLS AND PLATFORMS for AI-assisted scientific discovery. "
            "Use search_web to identify the leading software, models, and platforms being used. "
            "Write a structured markdown report to write_file with path "
            "'04_Code_Artifacts/mark_research.md'. "
            "Include: tool name, use case, adoption status."
        ),
        "WAIT_FOR":           "",
        "FAILURE_TARGET":     "STOP",
        "MAX_RECURSION":      "0",
        "ARTIFACT_PATH":      "04_Code_Artifacts/mark_research.md",
    },
    {
        "NODE_ID":            "SAMMY_RESEARCH",
        "AGENT_NAME":         "Sammy",
        "NEXT_NODE":          "TOMMY_RESEARCH",
        "MODEL_OVERRIDE":     "",
        "TEMPERATURE":        "1.0",
        "INSTRUCTION_OVERRIDE": (
            "Your research facet: MAJOR INSTITUTIONS AND FUNDING in AI-assisted scientific discovery. "
            "Use search_web to identify who is driving and funding this space. "
            "Write a structured markdown report to write_file with path "
            "'04_Code_Artifacts/sammy_research.md'. "
            "Include: institution, funding amounts if known, focus areas."
        ),
        "WAIT_FOR":           "",
        "FAILURE_TARGET":     "STOP",
        "MAX_RECURSION":      "0",
        "ARTIFACT_PATH":      "04_Code_Artifacts/sammy_research.md",
    },
    {
        "NODE_ID":            "TOMMY_RESEARCH",
        "AGENT_NAME":         "Tommy",
        "NEXT_NODE":          "SYNTHESIS",
        "MODEL_OVERRIDE":     "",
        "TEMPERATURE":        "1.0",
        "INSTRUCTION_OVERRIDE": (
            "Your research facet: CHALLENGES AND LIMITATIONS of AI-assisted scientific discovery. "
            "Use search_web to find critiques, limitations, failure modes, and unsolved problems. "
            "Write a structured markdown report to write_file with path "
            "'04_Code_Artifacts/tommy_research.md'. "
            "Include: challenge, current severity, any proposed solutions."
        ),
        "WAIT_FOR":           "",
        "FAILURE_TARGET":     "STOP",
        "MAX_RECURSION":      "0",
        "ARTIFACT_PATH":      "04_Code_Artifacts/tommy_research.md",
    },
    {
        "NODE_ID":            "SYNTHESIS",
        "AGENT_NAME":         "PoosMcfloos",
        "NEXT_NODE":          "STOP",
        "MODEL_OVERRIDE":     "",
        "TEMPERATURE":        "0.1",
        "INSTRUCTION_OVERRIDE": (
            "You are PoosMcfloos, a synthesis agent. "
            "The four research agents have completed their work. "
            "Use fts_search_memory to retrieve their findings, or query_local_memory for semantic recall. "
            "Synthesize all findings into a single comprehensive executive report covering: "
            "1) Recent Breakthroughs, 2) Key Tools & Platforms, 3) Major Institutions & Funding, "
            "4) Challenges & Limitations, 5) Your own synthesis conclusion. "
            "Write the final report to write_file with path "
            "'04_Code_Artifacts/final_synthesis_report.md'."
        ),
        "WAIT_FOR":           "",
        "FAILURE_TARGET":     "STOP",
        "MAX_RECURSION":      "0",
        "ARTIFACT_PATH":      "04_Code_Artifacts/final_synthesis_report.md",
    },
]

for i, node in enumerate(NODES, start=3):
    for col_name, val in node.items():
        _set(ws_topo, i, hmap_topo, col_name, val if val != "" else None)

# ── SESSION_CONFIG ────────────────────────────────────────────────────────────
if "SESSION_CONFIG" in wb.sheetnames:
    ws_sess = wb["SESSION_CONFIG"]
    hmap_sess = _hmap(ws_sess)
    _set(ws_sess, 3, hmap_sess, "SETTING", "INGEST_BEFORE_RUN")
    _set(ws_sess, 3, hmap_sess, "VALUE",   "TRUE")
    _set(ws_sess, 4, hmap_sess, "SETTING", "CANONIZE_AFTER_RUN")
    _set(ws_sess, 4, hmap_sess, "VALUE",   "FALSE")
    _set(ws_sess, 5, hmap_sess, "SETTING", "OUTPUT_FORMATS")
    _set(ws_sess, 5, hmap_sess, "VALUE",   "md")

wb.save(str(WB_PATH))
print("\nWorkbook saved.")
print("Topology nodes written:", len(NODES))
print("\n⚠️  NOTES FOR REVIEW:")
print("  1. SWARM_REQUEST!PAYLOAD_TEXT contains a placeholder topic - edit before firing.")
print("  2. PoosMcfloos temperature in AGENTS sheet is blank - set to 0.1 (Synthesiser).")
print("  3. PoosMcfloos tools do not include read_file - using fts_search_memory instead.")
print("     If fts fails to find prior outputs, add read_file to PoosMcfloos tools.")
print("  4. Topology is LINEAR (Randy→Mark→Sammy→Tommy→SYNTHESIS) not parallel fan-out.")
print("     Parallel fan-in requires broker-level concurrency - linear is safer for first test.")
