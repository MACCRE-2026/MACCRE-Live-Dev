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
maccre_core/patterns/definitions/simulation_swarm.py
=====================================================
Pattern: simulation_swarm

Pre-commit deliberation via 3 parallel implementation paths.

Fire this before writing complex code to explore multiple paths first.
Three fork agents each take a different approach, a synthesizer reconciles
their findings into a decision surface, and execution pauses at HUMAN_GATE
for review before any code is committed.

DAG:
    INGEST → FORK_PATH_A, FORK_PATH_B, FORK_PATH_C
             ↓ (all three → wait_for)
         JOIN_SYNTHESIZE → BRIEF_FORMATTER → HUMAN_GATE → STOP
"""
from maccre_core.patterns import PatternDefinition, PatternNode, register_pattern

_FORK_INSTR = """\
You are an implementation path explorer in a pre-commit simulation swarm.
Your assigned path: {path_label}

You will receive a problem statement. Explore your specific path and produce:

1. APPROACH: Describe your implementation strategy in concrete detail.
2. KEY DECISIONS: What architectural choices does this path require?
3. RISKS: List specific technical risks (not generic platitudes).
4. EFFORT: Rough complexity estimate (Low / Medium / High).
5. CONFIDENCE: Your confidence this path solves the problem correctly (0.0–1.0).

Be specific. Cite concrete code patterns, data structures, or algorithms.
No fluff. A senior engineer should be able to implement from your analysis.

End with exactly:
CONFIDENCE: [float 0.0-1.0]
RISKS: [comma-separated]
"""

_SYNTHESIZER_INSTR = """\
You are the Pattern Synthesizer. You have received analysis from 3 independent
implementation path agents. Produce a BriefPacket JSON for Antigravity.

Output ONLY a valid JSON object matching this exact schema (no markdown wrapping):
{
  "pattern": "simulation_swarm",
  "job_id": "__JOB_ID_PLACEHOLDER__",
  "fired_at": "__NOW__",
  "completed_at": "__NOW__",
  "cost_usd": 0.0,
  "decision_surface": {
    "question": "Which implementation path should I take?",
    "options": [
      {
        "label": "Path A — [one line description]",
        "agent": "FORK_PATH_A",
        "summary": "[2-3 sentences of concrete analysis]",
        "risks": ["risk1", "risk2"],
        "confidence": 0.85,
        "artifacts": []
      },
      {
        "label": "Path B — [one line description]",
        "agent": "FORK_PATH_B",
        "summary": "[2-3 sentences]",
        "risks": ["risk1"],
        "confidence": 0.70,
        "artifacts": []
      },
      {
        "label": "Path C — [one line description]",
        "agent": "FORK_PATH_C",
        "summary": "[2-3 sentences]",
        "risks": ["risk1"],
        "confidence": 0.60,
        "artifacts": []
      }
    ],
    "synthesizer_recommendation": "[Your recommendation and concise reasoning — 2-4 sentences]",
    "next_action_options": ["approve_path_A", "approve_path_B", "approve_path_C", "request_deeper_research", "cancel"]
  },
  "session_context": null,
  "raw_synthesis": "",
  "pattern_artifacts": [],
  "error": ""
}
"""

_PASSTHROUGH_INSTR = "Pass the input through unchanged. Do not modify or summarize. Output exactly what you received."

register_pattern(PatternDefinition(
    name="simulation_swarm",
    description=(
        "Pre-commit deliberation via 3 parallel implementation paths. "
        "Fire before writing complex code. Returns a structured decision surface."
    ),
    estimated_cost_usd=0.08,
    required_surfaces=["TEXT"],
    has_human_gate=True,
    payload_template=(
        "## Simulation Swarm Input\n\n"
        "**Problem Statement:**\n{problem}\n\n"
        "**Relevant Context:**\n{context}\n\n"
        "**Constraints / Non-negotiables:**\n{constraints}"
    ),
    nodes=[
        PatternNode(
            node_id="INGEST",
            agent_name="Pattern_Fork_Agent",
            instruction_override=_FORK_INSTR.format(
                path_label="Path A — Primary / most straightforward approach"
            ),
            next_node="FORK_PATH_A,FORK_PATH_B,FORK_PATH_C",
            temperature=0.7,
            model_override="gemini-2.5-flash",
        ),
        PatternNode(
            node_id="FORK_PATH_A",
            agent_name="Pattern_Fork_Agent",
            instruction_override=_FORK_INSTR.format(
                path_label="Path A — Primary / most straightforward approach"
            ),
            next_node="JOIN_SYNTHESIZE",
            temperature=1.0,
            model_override="gemini-2.5-flash",
        ),
        PatternNode(
            node_id="FORK_PATH_B",
            agent_name="Pattern_Fork_Agent",
            instruction_override=_FORK_INSTR.format(
                path_label="Path B — Alternative architecture / different design philosophy"
            ),
            next_node="JOIN_SYNTHESIZE",
            temperature=1.0,
            model_override="gemini-2.5-flash",
        ),
        PatternNode(
            node_id="FORK_PATH_C",
            agent_name="Pattern_Fork_Agent",
            instruction_override=_FORK_INSTR.format(
                path_label="Path C — Contrarian / challenge the assumptions of both Path A and B"
            ),
            next_node="JOIN_SYNTHESIZE",
            temperature=1.0,
            model_override="gemini-2.5-flash",
        ),
        PatternNode(
            node_id="JOIN_SYNTHESIZE",
            agent_name="Pattern_Synthesizer",
            instruction_override=_SYNTHESIZER_INSTR,
            next_node="HUMAN_GATE",
            temperature=0.1,
            model_override="gemini-2.5-pro",
            wait_for="FORK_PATH_A,FORK_PATH_B,FORK_PATH_C",
        ),
        PatternNode(
            node_id="HUMAN_GATE",
            agent_name="Pattern_Fork_Agent",
            instruction_override=_PASSTHROUGH_INSTR,
            next_node="MANUAL",
            temperature=0.1,
            model_override="gemini-2.5-flash-lite",
        ),
    ],
    agent_roster_entries=[
        {
            "Agent_Name": "Pattern_Fork_Agent",
            "Model": "gemini-2.5-flash",
            "Tools_Allowed": "none",
            "System_Prompt": (
                "You are a focused analytical agent in a simulation swarm. "
                "Follow your specific instructions exactly. Be concrete and specific."
            ),
        },
        {
            "Agent_Name": "Pattern_Synthesizer",
            "Model": "gemini-2.5-pro",
            "Tools_Allowed": "none",
            "System_Prompt": (
                "You are the final synthesizer in a MACCRE pattern. "
                "Produce structured JSON output exactly as specified. "
                "Temperature=0.1 — deterministic, precise, no creative divergence."
            ),
        },
    ],
))
