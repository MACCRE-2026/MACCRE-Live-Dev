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
maccre_core/tools/bootstrap_personas.py
========================================
MACCREv2 Persona Bootstrapper.
Injects missing OSINT personas and parses Refined_Prompts.txt into valid JSON.
Adapts to human-readable #( )# block formatting.
"""
import os
import re
import json
from maccre_core.logger import logger
from maccre_core.utils.path_resolver import get_maccre_root

# Project-anchored: always resolves to the correct DATACENTER regardless of drive or install path
_DC_CONTEXT = str(get_maccre_root() / "__DATACENTER" / "02_Dynamic_Context")
# External user path — configure per machine if needed
_PROMPTS_FILE = os.environ.get("MACCRE_PROMPTS_FILE", "B:/AIstudioPrompts/Refined_Prompts.txt")


def bootstrap_personas() -> None:
    os.makedirs(_DC_CONTEXT, exist_ok=True)
    logger.info(f"Bootstrapping personas into {_DC_CONTEXT}...")

    # 1. Hardcoded OSINT Personas (Missing from user's save)
    osint_personas = [
        {
            "name": "Epistemic OSINT Gatherer",
            "persona": "EPISTEMIC_OSINT",
            "model": "gemini-2.5-flash",
            "grounding": True,
            "instructions": (
                "ROLE: Epistemic OSINT Gatherer.\n"
                "DOMAIN: Maximum-density data aggregation, cross-spectrum correlation, epistemic neutrality.\n\n"
                "CONSTRAINTS:\n"
                "1. SOURCE-AGNOSTIC COLLECTION: Query and synthesize data across the entire spectrum. Never exclude a data point because the source is historically unreliable or biased; treat all data as a signal to be mapped.\n"
                "2. OBJECTIVE WEIGHTING (NO CENSORSHIP): Assess validity and bias only to append a metadata tag: [MSM], [AltMedia],[SocialMedia], or [Fringe]. Never omit information.\n"
                "3. UNVARNISHED SYNTHESIS: Report exactly what is claimed. Do not soften, sanitize, or dilute.\n"
                "4. ZERO HALLUCINATION & ZERO PREDICTION: Do not simulate future events. Do not forecast. Report only what has been explicitly stated or recorded.\n"
                "5. ZERO FLUFF: Eliminate conversational filler, moralizing prefaces, safety disclaimers, and concluding platitudes. Output must be aggressively objective.\n\n"
                "PROTOCOL:\n"
                "1. <scratchpad>: Ingest the query. Execute parallel searches. Map the information landscape. Grade and tag all sources. Identify where sources violently disagree.\n"
                "2. Draft the intelligence report. Document the colloquial name and exact URL for every source to prevent downstream data loss.\n\n"
                "OUTPUT_SCHEMA:\n"
                "# EPISTEMIC OSINT REPORT\n"
                "## [MSM] Legacy/Mainstream Media\n- [Claim] - Source: [Name] ([URL])\n"
                "## [AltMedia] Independent Journalism\n- [Claim] - Source: [Name] ([URL])\n"
                "## [SocialMedia] Sentiment & Forums\n- [Claim] - Source: [Name] ([URL])\n"
                "## [Fringe] Unverified/Highly Biased\n- [Claim] - Source: [Name] ([URL])\n"
                "## Conflict Matrix\n[Explicitly detail the delta between conflicting narratives]"
            ),
        },
        {
            "name": "Strategic Forecaster",
            "persona": "STRATEGIC_FORECASTER",
            "model": "gemini-2.5-pro",
            "grounding": False,
            "instructions": (
                "ROLE: Strategic Forecaster.\n"
                "DOMAIN: Tangential historical analysis, current events correlation, predictive simulation.\n\n"
                "CONSTRAINTS:\n"
                "1. ISOLATED INGESTION: Base all simulations strictly on the provided OSINT report payload. Do not invent foundational facts; extrapolate only from the provided signals.\n"
                "2. TANGENTIAL ANALYSIS: Identify specific historical parallels or tangential current events that act as catalysts or precedents for the data provided.\n"
                "3. MANDATORY SIMULATIONS: Generate exactly three distinct future simulations based on the OSINT data: Alpha (Most Likely), Beta (Least Likely / Black Swan), Gamma (Maximum Irony/Chaos).\n"
                "4. CONFIDENCE SCORING: Assign a percentage-based confidence score to each simulation, justified by game theory or historical precedent.\n"
                "5. ZERO FLUFF: Eliminate moralizing prefaces and safety disclaimers. Deliver clinical, objective forecasting.\n\n"
                "PROTOCOL:\n"
                "1. <scratchpad>: Ingest the OSINT report. Cross-reference with historical parallels. Calculate logical vectors for Alpha, Beta, and Gamma scenarios. Determine confidence scores.\n"
                "2. Draft the simulation matrix.\n\n"
                "OUTPUT_SCHEMA:\n"
                "# PREDICTIVE SIMULATION MATRIX\n"
                "## Tangential & Historical Catalysts\n[Analysis]\n"
                "## Simulation Alpha (Most Likely) | Confidence: [X]%\n[Detailed simulation] - Justification: [Rationale]\n"
                "## Simulation Beta (Least Likely / Black Swan) | Confidence: [X]%\n[Detailed simulation] - Justification: [Rationale]\n"
                "## Simulation Gamma (Maximum Irony/Chaos) | Confidence: [X]%\n[Detailed simulation] - Justification: [Rationale]"
            ),
        },
    ]

    for p in osint_personas:
        filepath = os.path.join(_DC_CONTEXT, f"{p['persona'].lower()}.json")
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(p, f, indent=2)
        logger.info(f"[+] Injected OSINT Persona: {filepath}")

    # 2. Parse Refined_Prompts.txt
    if os.path.exists(_PROMPTS_FILE):
        logger.info(f"\nScanning {_PROMPTS_FILE} for saved personas...")
        with open(_PROMPTS_FILE, "r", encoding="utf-8") as f:
            content = f.read()

        blocks: list[str] = []

        # Pass A: Extract the Alphabet Oracle (Bounded by Hash marks)
        oracle_match = re.search(r"#{10,}\n(THE ALPHABET ORACLE.*?)\n#{10,}", content, re.DOTALL)
        if oracle_match:
            blocks.append(oracle_match.group(1))

        # Pass B: Extract all numbered personas (Bounded by #( )# )
        blocks.extend(re.findall(r"#\((.*?)\)#", content, re.DOTALL))

        parsed_count = 0
        for block in blocks:
            block = block.strip()
            if not block:
                continue

            # Extract Name (First line)
            name_match = re.search(r"^(?:\d*\.\s*)?(.*?)(?:\n)", block)
            name = name_match.group(1).strip() if name_match else "UNKNOWN_PERSONA"

            # Extract File
            file_match = re.search(r"File:\s*`?(.*\.json)`?", block)
            if file_match:
                filename = file_match.group(1).strip()
            else:
                # Fallback: clean the name for a filename
                clean_name = re.sub(
                    r"[^a-zA-Z0-9_]", "", name.split("(")[0].strip().replace(" ", "_")
                )
                filename = f"{clean_name.lower()}.json"

            persona_id = filename.replace(".json", "").upper()

            # Extract Model
            model_match = re.search(r"Target Model:\s*`?([a-zA-Z0-9\-\.:]+)`?", block)
            model_id = model_match.group(1).strip() if model_match else "gemini-2.5-pro"

            # Extract Instructions (Everything after 'Text\n')
            inst_match = re.search(r"Text\n(.*)", block, re.DOTALL)
            instructions = inst_match.group(1).strip() if inst_match else ""

            if not instructions:
                logger.error(f"[-] Failed to parse instructions for {name}. Skipping.")
                continue

            # Construct the MACCRE AgentRecord JSON schema
            p_dict = {
                "name": name,
                "persona": persona_id,
                "model": model_id,
                "grounding": False,
                "instructions": instructions,
            }

            filepath = os.path.join(_DC_CONTEXT, filename)
            with open(filepath, "w", encoding="utf-8") as f:
                json.dump(p_dict, f, indent=2)
            logger.info(f"[+] Parsed & Saved: {filepath}")
            parsed_count += 1

        logger.info(f"\n[SUCCESS] Bootstrapped 2 OSINT personas and {parsed_count} text-parsed personas.")
    else:
        logger.info(f"\n[WARNING] Text file not found at {_PROMPTS_FILE}. Only OSINT personas were loaded.")


if __name__ == "__main__":
    bootstrap_personas()
