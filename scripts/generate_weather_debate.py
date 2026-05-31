"""
scripts/generate_weather_debate.py
=====================================
MACCREv2 Weather Debate Swarm — Topology Generator

6 city agents, each with search grounding, argue over who has the best weather.
3 recursive rounds of debate. Then a vote. Consensus → champion report.
No consensus → losers move to the exile city (fewest votes) → report on that.

Commit: Phase 2C Stress Test — validating SovereignPinStore under live swarm load.

Run: python scripts/generate_weather_debate.py
Then: python maccre.py launch B:\\MACCREv2\\MACCRE_WeatherDebate.xlsx
"""
from __future__ import annotations

import random
import sys
import os
from pathlib import Path

# ── Sovereign path injection ───────────────────────────────────────────────────
vendor_dir = str(Path(__file__).parent.parent / "maccre_core" / "_vendor")
if vendor_dir not in sys.path:
    sys.path.insert(0, vendor_dir)

sys.path.insert(0, str(Path(__file__).parent.parent))
os.environ["MACCRE_MEMORY_BACKEND"] = "sovereign"
os.environ["MACCRE_ACTIVE_PROJECT"] = "WeatherDebate"

from maccre_core._net.ooxml import (  # noqa: E402
    Alignment, Border, Font, PatternFill, Side, Workbook, get_column_letter
)

# ── City Pool ──────────────────────────────────────────────────────────────────
CITY_POOL = [
    "Phoenix, AZ", "San Diego, CA", "Honolulu, HI", "Miami, FL",
    "Denver, CO", "Seattle, WA", "Minneapolis, MN", "Chicago, IL",
    "Austin, TX", "Asheville, NC", "Santa Fe, NM", "Portland, OR",
    "New Orleans, LA", "Salt Lake City, UT", "Nashville, TN",
    "Tucson, AZ", "Burlington, VT", "Boise, ID",
]

random.seed(42)  # reproducible for test validation
CITIES = random.sample(CITY_POOL, 6)

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
    """Write a styled header + data sheet with title banner."""
    n = len(cols)

    # Title banner row 1
    ws.merge_cells(f"A1:{get_column_letter(n)}1")
    cell = ws.cell(row=1, column=1, value=title)
    cell.font = _title_font()
    cell.fill = PatternFill("solid", PAL["bg_dark"])
    cell.alignment = Alignment(horizontal="center", vertical="center")
    ws.row_dimensions[1].height = 26

    # Header row 2
    for ci, (col_name, _) in enumerate(cols, 1):
        hc = ws.cell(row=2, column=ci, value=col_name)
        hc.font = _header_font()
        hc.fill = PatternFill("solid", PAL["bg_header"])
        hc.border = _border()
        hc.alignment = Alignment(horizontal="center", vertical="center", wrap_text=False)

    # Column widths
    for ci, (_, width) in enumerate(cols, 1):
        ws.column_dimensions[get_column_letter(ci)].width = width

    # Data rows starting row 3
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
        ("PROJECT_NAME", "WeatherDebate"),
        ("DESCRIPTION",  "6-city recursive weather debate swarm. 3 rounds of argument, "
                         "then democratic vote. Consensus→winner report; no consensus→exile report."),
        ("SESSION_LABEL", "weather_debate_phase2c_stress"),
    ]
    _write_sheet(ws_proj, "PROJECT DEFINITION", proj_cols, proj_rows)

    # ── 2. SWARM_REQUEST ────────────────────────────────────────────────────
    ws_req = wb.create_sheet("SWARM_REQUEST")
    req_cols = [
        ("PROJECT_NAME", 20), ("DESCRIPTION", 60), ("START_NODE", 25),
        ("PAYLOAD_TEXT", 100), ("COMPUTE_TIER", 15),
    ]
    cities_list = "\n".join(f"  - {c}" for c in CITIES)
    payload = (
        f"WEATHER DEBATE SWARM\n"
        f"Participants and their assigned cities:\n{cities_list}\n\n"
        f"MISSION: Each agent champions their assigned city's weather in 3 rounds of debate. "
        f"After the debate, a vote is taken. If consensus is reached, produce an expert meteorological "
        f"report on the winning city. If no consensus, all agents are exiled to the city that received "
        f"the fewest votes — produce the expert report on that city instead."
    )
    req_rows = [
        ("WeatherDebate", "6-city weather debate → vote → expert report", "DEBATE_ANCHOR", payload, "cloud"),
    ]
    _write_sheet(ws_req, "SWARM INITIATION", req_cols, req_rows)

    # ── 3. AGENTS ───────────────────────────────────────────────────────────
    ws_ag = wb.create_sheet("AGENTS")
    ag_cols = [
        ("AGENT_NAME", 22), ("MODEL", 26), ("ROLE", 28), ("SEARCH_GROUNDING", 18),
        ("TEMPERATURE", 14), ("TOOLS", 35), ("PERSONA", 120),
    ]
    ag_rows: list[tuple[str | float, ...]] = []

    # City advocate agents (6)
    for i, city in enumerate(CITIES, 1):
        ag_rows.append((
            f"Advocate_{i}",
            "gemini-2.5-flash",
            f"City Weather Champion — {city}",
            "TRUE",
            0.9,
            "execute_hybrid_synthesis",
            f"You are Agent Advocate_{i}, the passionate champion of {city}. "
            f"Using your search grounding tool, find REAL current and historical weather data for {city}. "
            f"Make the most compelling, fact-based argument for why {city} has the BEST weather in America. "
            f"Reference actual climate statistics: average temps, sunshine hours, precipitation, extreme weather "
            f"frequency, outdoor activity scores, air quality, and quality of life weather metrics. "
            f"Be persuasive, specific, and back every claim with real data. "
            f"Address and counter any weaknesses in your city's climate profile honestly but optimistically. "
            f"You MUST mention your city name '{city}' at least 3 times in your argument.",
        ))

    # Debate Coordinator — fans out to all advocates, collects 3 rounds
    ag_rows.append((
        "DebateCoordinator",
        "gemini-2.5-flash",
        "Swarm Debate Orchestrator",
        "FALSE",
        0.3,
        "none",
        "You are the DebateCoordinator. You receive the full PAYLOAD context listing all 6 cities. "
        "Your role is to formally open the weather debate by introducing all 6 city representatives "
        "and the 3-round debate format. State the cities clearly, explain the voting rules, and "
        "declare the debate OPEN. Format your output as a formal debate introduction.",
    ))

    # Round Synthesizer — aggregates each round and seeds the next
    ag_rows.append((
        "RoundSynthesizer",
        "gemini-2.5-flash",
        "Inter-Round Debate Synthesizer",
        "FALSE",
        0.2,
        "none",
        "You are the RoundSynthesizer. You receive the arguments from all 6 city advocates in the current round. "
        "Produce a structured Round Summary that: (1) lists each city and their strongest claim from this round, "
        "(2) identifies which arguments were most compelling and why, (3) flags any factual disputes or weak claims, "
        "(4) scores each city 1-10 on argument quality this round. "
        "End with: 'DEBATE CONTINUES — Round [N] complete, [3-N] rounds remain.' or 'DEBATE CONCLUDED — proceeding to vote.'",
    ))

    # Vote Synthesizer — the jury
    ag_rows.append((
        "VoteSynthesizer",
        "gemini-2.5-pro",
        "Democratic Vote Tallier and Ruling Body",
        "FALSE",
        0.1,
        "none",
        "You are the VoteSynthesizer, the ultimate arbiter of the weather debate. "
        "You receive the full 3-round debate transcript from all 6 city advocates. "
        "Conduct a rigorous democratic vote:\n"
        "1. Score each city on: temperature comfort (20pts), sunshine hours (20pts), "
        "precipitation/humidity (15pts), extreme weather risk (15pts), air quality (15pts), "
        "outdoor recreation score (15pts). Max 100 points.\n"
        "2. Rank all 6 cities 1-6.\n"
        "3. Declare CONSENSUS if the top city scores 10+ points more than 2nd place.\n"
        "4. Declare NO_CONSENSUS if scores are tight.\n"
        "5. In NO_CONSENSUS case, identify the city with the FEWEST total points (exile destination).\n\n"
        "OUTPUT FORMAT (strict):\n"
        "VOTE_RESULT: [CONSENSUS/NO_CONSENSUS]\n"
        "WINNER_CITY: [city name] (or EXILE_CITY if no consensus)\n"
        "EXILE_CITY: [city with fewest points] (always include)\n"
        "SCORES:\n"
        "  1. [City]: [score]pts\n"
        "  2. [City]: [score]pts\n"
        "  ... (all 6)\n"
        "RULING_RATIONALE: [3-4 sentence explanation of the decision]",
    ))

    # Director — produces the final expert report
    ag_rows.append((
        "WeatherDirector",
        "gemini-2.5-pro",
        "Expert Meteorological Report Author",
        "TRUE",
        0.2,
        "execute_hybrid_synthesis,write_file",
        "You are the WeatherDirector, the senior meteorologist and final authority. "
        "You receive the vote ruling from VoteSynthesizer. Identify the REPORT_CITY: "
        "if VOTE_RESULT is CONSENSUS, use WINNER_CITY. If NO_CONSENSUS, use EXILE_CITY. "
        "Using your search grounding, research REPORT_CITY thoroughly and produce a "
        "definitive Expert Meteorological Report with these sections:\n"
        "1. EXECUTIVE SUMMARY — why this city's weather was selected\n"
        "2. CLIMATE PROFILE — detailed seasonal breakdown with real statistics\n"
        "3. SUNSHINE AND TEMPERATURE — monthly averages, comfort index\n"
        "4. PRECIPITATION AND HUMIDITY — rain patterns, drought cycles\n"
        "5. EXTREME WEATHER RISK ASSESSMENT — historical data on storms, fires, floods\n"
        "6. OUTDOOR RECREATION INDEX — how weather enables lifestyle\n"
        "7. AIR QUALITY ANALYSIS — AQI averages, pollution cycles\n"
        "8. EXPERT VERDICT — definitive statement on why this is objectively excellent weather\n\n"
        "Save the report using write_file to: "
        "B:\\MACCREv2\\__DATACENTER\\WeatherDebate\\05_Rendered_Media\\weather_expert_report.md",
    ))

    _write_sheet(ws_ag, "AGENT ROSTER — WEATHER DEBATE", ag_cols, ag_rows)

    # ── 4. TOPOLOGY ─────────────────────────────────────────────────────────
    ws_top = wb.create_sheet("TOPOLOGY")
    top_cols = [
        ("NODE_ID", 28), ("AGENT_NAME", 22), ("NEXT_NODE", 90),
        ("AUTO_TOOL", 35), ("TEMPERATURE", 14), ("MAX_RECURSION", 15),
        ("INSTRUCTION_OVERRIDE", 110),
    ]

    # Fan-out: DEBATE_ANCHOR triggers all 6 advocates simultaneously
    advocate_fan = ",".join(f"Advocate_{i}_Round1" for i in range(1, 7))
    # Fan-in target: all round1 advocates feed into RoundSynth_1
    round2_fan = ",".join(f"Advocate_{i}_Round2" for i in range(1, 7))
    round3_fan = ",".join(f"Advocate_{i}_Round3" for i in range(1, 7))

    top_rows: list[tuple[str | float, ...]] = []

    # Anchor node — opens the debate
    top_rows.append((
        "DEBATE_ANCHOR",
        "DebateCoordinator",
        advocate_fan,
        "none",
        0.3,
        1,
        "",
    ))

    # Round 1 — all 6 advocates argue
    for i, city in enumerate(CITIES, 1):
        top_rows.append((
            f"Advocate_{i}_Round1",
            f"Advocate_{i}",
            "RoundSynth_1",
            "execute_hybrid_synthesis",
            0.9,
            3,
            f"ROUND 1 — Initial Arguments. You are the champion of {city}. "
            f"Search for real weather data for {city} and make your opening argument "
            f"for why {city} has the best weather in America. Be specific with facts and statistics. "
            f"Target 200-300 words.",
        ))

    # Round Synthesizer 1 — waits for all 6, produces summary, fans to round 2
    top_rows.append((
        "RoundSynth_1",
        "RoundSynthesizer",
        round2_fan,
        "none",
        0.2,
        7,   # must be >= number of fan-in advocates (6) to survive multi-source routing
        "Synthesize Round 1. Review all 6 city arguments above. "
        "Score each city 1-10 on argument strength. State 'Round 1 complete, 2 rounds remain.'",
    ))

    # Round 2 — rebuttals
    for i, city in enumerate(CITIES, 1):
        top_rows.append((
            f"Advocate_{i}_Round2",
            f"Advocate_{i}",
            "RoundSynth_2",
            "execute_hybrid_synthesis",
            0.9,
            3,
            f"ROUND 2 — Rebuttals. You are the champion of {city}. "
            f"Read the Round 1 summary. Rebuttal the strongest competitor's claims directly. "
            f"Reinforce your own city's advantages with additional searched data. "
            f"Target 150-200 words per argument.",
        ))

    # Round Synthesizer 2
    top_rows.append((
        "RoundSynth_2",
        "RoundSynthesizer",
        round3_fan,
        "none",
        0.2,
        7,   # must be >= number of fan-in advocates (6)
        "Synthesize Round 2. Score each city 1-10. State 'Round 2 complete, 1 round remains.'",
    ))

    # Round 3 — closing statements
    for i, city in enumerate(CITIES, 1):
        top_rows.append((
            f"Advocate_{i}_Round3",
            f"Advocate_{i}",
            "VoteNode",
            "execute_hybrid_synthesis",
            0.9,
            3,
            f"ROUND 3 — Closing Statement. You are the champion of {city}. "
            f"Deliver your final, most compelling closing argument. "
            f"Summarize your strongest data points. End with a direct call to vote for {city}. "
            f"Target 100-150 words.",
        ))

    # Vote node — receives all 6 closing statements
    top_rows.append((
        "VoteNode",
        "VoteSynthesizer",
        "FinalDirector",
        "none",
        0.1,
        7,   # must be >= number of fan-in advocates (6)
        "The 3-round debate is complete. Review ALL arguments from ALL rounds for all 6 cities. "
        "Conduct your scored democratic vote now. Declare CONSENSUS or NO_CONSENSUS as instructed. "
        "Identify the WINNER_CITY and EXILE_CITY as required.",
    ))

    # Final Director node
    top_rows.append((
        "FinalDirector",
        "WeatherDirector",
        "STOP",
        "execute_hybrid_synthesis,write_file",
        0.2,
        1,
        "The vote ruling is above. Identify whether VOTE_RESULT is CONSENSUS or NO_CONSENSUS. "
        "If CONSENSUS → research and report on WINNER_CITY. "
        "If NO_CONSENSUS → research and report on EXILE_CITY (the city with fewest votes — ALL agents move there). "
        "Produce the full 8-section expert meteorological report using your search grounding. "
        "Save to: B:\\MACCREv2\\__DATACENTER\\WeatherDebate\\05_Rendered_Media\\weather_expert_report.md",
    ))

    _write_sheet(ws_top, "SWARM ROUTING DAG — WEATHER DEBATE", top_cols, top_rows)

    # ── 5. PIPELINE_CONFIG ───────────────────────────────────────────────────
    ws_cfg = wb.create_sheet("PIPELINE_CONFIG")
    cfg_cols = [("KEY", 35), ("VALUE", 80)]
    cfg_rows = [
        ("INGEST_BEFORE_RUN", "FALSE"),
        ("CANONIZE_AFTER_RUN", "TRUE"),
        ("LOG_PATH", "B:\\MACCREv2\\__DATACENTER\\WeatherDebate\\03_Agent_Ledgers"),
        ("OUTPUT_PATH", "B:\\MACCREv2\\__DATACENTER\\WeatherDebate\\05_Rendered_Media"),
        ("MEMORY_BACKEND", "sovereign"),
        ("TELEMETRY_MODE", "json"),
    ]
    _write_sheet(ws_cfg, "PIPELINE CONFIGURATION", cfg_cols, cfg_rows)

    # Save directly to the datacenter session slot (correct location for maccre.py launch)
    out_dir = Path("B:/MACCREv2/__DATACENTER/WeatherDebate")
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / "MACCRE_Session.xlsx"
    wb.save(str(out))
    print(f"\n[OK] Weather Debate Swarm Workbook generated: {out}")
    print(f"     Cities selected: {', '.join(CITIES)}")
    print(f"\n     Topology: {1 + 6 + 1 + 6 + 1 + 6 + 1 + 1} nodes")
    print("     Fan-Out:  DEBATE_ANCHOR -> 6 parallel Round 1 advocates")
    print("     Fan-In:   All 6 Round 3 closings -> VoteNode -> FinalDirector -> STOP")
    print("\n     To run:  python maccre.py launch B:\\MACCREv2\\MACCRE_WeatherDebate.xlsx")


if __name__ == "__main__":
    build_workbook()
