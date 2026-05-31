"""
patch_pipeline.py
One-shot patcher for the NewsNexus agent roster and topology.
Fixes:
  1. OSINT  — force payload-as-target + mandatory hybrid search call
  2. NewsVet — "The Midnight Editor" identity anchor + no-headers enforced
  3. SCRIPT  — enforce speaker="NewsVet", remove session_dir instruction
  4. Topology — OSINT instruction override forces search tool first
"""
import csv

from maccre_core.utils.path_resolver import get_maccre_root

DATACENTER = get_maccre_root() / "__DATACENTER" / "NewsNexus"
ROSTER_PATH = DATACENTER / "agent_roster.csv"
TOPOLOGY_PATH = DATACENTER / "02_Dynamic_Context/topology.csv"

# ── 1. Patch Topology ─────────────────────────────────────────────────────────
topology_rows: list[dict[str, str]] = []
with open(TOPOLOGY_PATH, newline="", encoding="utf-8") as f:
    reader = csv.DictReader(f)
    fieldnames = reader.fieldnames or []
    for row in reader:
        nid = row.get("Node_ID", "").strip()

        if nid == "OSINT":
            row["Instruction_Override"] = (
                "The text content of your input IS the Research Target for this OSINT sweep — "
                "treat it verbatim as your subject matter. "
                "Your FIRST action MUST be to call execute_hybrid_synthesis passing the research target as the query parameter. "
                "You will receive up to 15 web results. "
                "Then call read_url_content on AT LEAST 10 of the returned source URLs, deliberately selecting across "
                "the full ideological and geographic spectrum: include mainstream Western outlets (Reuters, AP, BBC), "
                "US conservative media, US progressive media, regional Middle Eastern sources, European press, "
                "and independent/alternative outlets. "
                "Do NOT cherry-pick only the top results — read sources that represent opposing viewpoints and conflicting narratives. "
                "Only after completing all read_url_content calls, write the structured intelligence brief with populated "
                "source tiers to 04_Code_Artifacts/NewsNexus_OSINT_Brief.md via write_file."
            )
            row["Max_Recursion"] = "14"  # 1 search + 10 reads + 1 write + headroom

        if nid == "SOURCE_CHECK":
            row["Instruction_Override"] = (
                "Load 04_Code_Artifacts/NewsNexus_OSINT_Brief.md via read_file. "
                "Verify every URL in the KEY CLAIMS INVENTORY by calling read_url_content "
                "on each one. Rate each source: VERIFIED | UNVERIFIABLE | CONTEXTUAL_MISMATCH. "
                "Write the structured audit to 04_Code_Artifacts/NewsNexus_SourceAudit.md via write_file."
            )

        if nid == "NEWSVET":
            row["Instruction_Override"] = (
                "Call read_file twice: once for 04_Code_Artifacts/NewsNexus_OSINT_Brief.md "
                "and once for 04_Code_Artifacts/NewsNexus_SourceAudit.md. "
                "Then write your 800-1200 word gonzo broadcast editorial to "
                "04_Code_Artifacts/NewsNexus_Editorial.md via write_file. "
                "Follow your full V4.2 role instructions exactly. "
                "NO markdown headers, NO bylines, NO author credits. "
                "Start mid-thought. Your on-air call sign is 'The Midnight Editor' — use it freely in the prose."
            )

        if nid == "SCRIPT":
            row["Instruction_Override"] = (
                "Call read_file to load 04_Code_Artifacts/NewsNexus_Editorial.md. "
                "Convert the editorial into a JSON array manifest following your full role instructions. "
                "CRITICAL: Every scene object MUST have speaker set to the exact string 'NewsVet' — "
                "no other value. Even though the prose says 'The Midnight Editor', the technical "
                "speaker field routing MUST be 'NewsVet'. "
                "Do NOT include a session_dir argument when calling execute_render_pipeline. "
                "Call execute_render_pipeline with only the manifest_json argument."
            )

        topology_rows.append(row)

with open(TOPOLOGY_PATH, "w", newline="", encoding="utf-8") as f:
    writer = csv.DictWriter(f, fieldnames=fieldnames)
    writer.writeheader()
    writer.writerows(topology_rows)
print(f"[PATCH] Topology updated: {TOPOLOGY_PATH}")

# ── 2. Patch Roster ───────────────────────────────────────────────────────────
roster_rows: list[dict[str, str]] = []
with open(ROSTER_PATH, newline="", encoding="utf-8") as f:
    reader = csv.DictReader(f)
    roster_fields = reader.fieldnames or []
    for row in reader:
        name = row.get("Agent_Name", "").strip()

        if name == "OSINT_AGENT":
            # Make the payload-as-target rule explicit in the system prompt too
            prompt: str = row.get("System_Prompt", "")
            if "The input you receive IS the research target" not in prompt:
                row["System_Prompt"] = (
                    "CRITICAL INPUT RULE: The text you receive as your input payload IS your research target. "
                    "Extract it directly and immediately. Do not wait for a structured request. "
                    "Any text you receive is a valid research subject.\n\n" + prompt
                )

        if name == "NewsVet":
            prompt = row.get("System_Prompt", "")
            # Inject identity anchor if not already there
            if "The Midnight Editor" not in prompt:
                anchor = (
                    "\n\n**ON-AIR IDENTITY**\n"
                    "Your call sign is 'The Midnight Editor'. Use this name to refer to yourself "
                    "within the broadcast prose — it is your editorial persona. "
                    "Never use the name 'NewsVet' in the editorial prose itself; that is a routing label. "
                    "Never refer to yourself as an AI, a system, an algorithm, or a language model.\n"
                    "OUTPUT FORMAT HARD CONSTRAINTS:\n"
                    "- NO markdown headers (no #, ##, ###)\n"
                    "- NO bylines, no author credits, no datelines\n"
                    "- NO signature lines\n"
                    "- Start the editorial MID-THOUGHT. No title. No preamble.\n"
                    "- The downstream SCRIPT_MANAGER will use speaker: 'NewsVet' for voice routing — "
                    "this does not affect your prose identity as 'The Midnight Editor'."
                )
                row["System_Prompt"] = prompt + anchor

        if name == "SCRIPT_MANAGER":
            prompt = row.get("System_Prompt", "")
            # Enforce speaker name and session_dir prohibition
            if "session_dir" not in prompt or "The Midnight Editor" not in prompt:
                addendum = (
                    "\n\nCRITICAL MANIFEST RULES:\n"
                    "1. Every scene object MUST have speaker set to exactly 'NewsVet' — "
                    "not 'Midnight Editor', not 'The Midnight Editor', not any other string. "
                    "The voice routing system will FAIL silently if this field is wrong.\n"
                    "2. When calling execute_render_pipeline, pass ONLY the manifest_json argument. "
                    "Do NOT pass a session_dir argument under any circumstances.\n"
                    "3. Each scene's text field MUST include the acoustic stage directions "
                    "as [bracketed instructions] embedded directly in the dialogue text.\n"
                )
                row["System_Prompt"] = prompt + addendum

        roster_rows.append(row)

with open(ROSTER_PATH, "w", newline="", encoding="utf-8") as f:
    writer = csv.DictWriter(f, fieldnames=roster_fields, extrasaction="ignore")
    writer.writeheader()
    writer.writerows(roster_rows)
print(f"[PATCH] Roster updated: {ROSTER_PATH}")

# ── 3. Verify ─────────────────────────────────────────────────────────────────
print("\n=== TOPOLOGY OVERRIDES ===")
with open(TOPOLOGY_PATH, newline="", encoding="utf-8") as f:
    for row in csv.DictReader(f):
        nid = row.get("Node_ID", "").strip()
        override = row.get("Instruction_Override", "")[:80]
        if nid:
            print(f"  {nid}: {override}...")

print("\n=== ROSTER PROMPT PREFIXES ===")
with open(ROSTER_PATH, newline="", encoding="utf-8") as f:
    for row in csv.DictReader(f):
        name = row.get("Agent_Name", "").strip()
        prompt = row.get("System_Prompt", "")[:80]
        if name:
            print(f"  {name}: {prompt}...")
