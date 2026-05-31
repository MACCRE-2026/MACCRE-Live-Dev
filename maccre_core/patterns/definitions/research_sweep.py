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
maccre_core/patterns/definitions/research_sweep.py
===================================================
Pattern: research_sweep

Deep domain investigation before acting on unfamiliar territory.

Three parallel research agents attack the topic from different angles
(overview, deep technical dive, and counterargument/risk), then a
synthesizer reconciles findings. One fork uses Deep Research (grounding)
for live web search.

DAG:
    INGEST → FORK_OVERVIEW, FORK_DEEP_DIVE, FORK_COUNTERARGUMENT
             ↓ (wait_for all three)
         JOIN_COMPILE → BRIEF_FORMATTER → HUMAN_GATE → STOP

Cost: ~$0.15–0.80 (Deep Research grounding varies by query depth)
"""
from maccre_core.patterns import PatternDefinition, PatternNode, register_pattern

_OVERVIEW_INSTR = """\
You are the Overview Researcher. Provide a comprehensive but accessible overview of the topic.
Cover:
1. What is it? Core concepts in plain language.
2. How does it work? Key mechanisms.
3. What are the primary use cases?
4. What is the current state of practice (2025-2026)?

Be factual. Cite specific examples. Aim for 400-600 words. No filler.
"""

_DEEP_DIVE_INSTR = """\
You are the Deep Research Agent. Perform a thorough technical investigation of the topic.
You have access to live web search — use it to find current, authoritative information.

Cover:
1. Technical implementation details (specific algorithms, APIs, data structures)
2. Relevant open source projects or libraries (with links)
3. Known limitations, failure modes, and edge cases
4. Performance characteristics and benchmarks where available
5. Recent developments (last 6 months)

Be specific and technical. This is for an experienced engineer. Cite your sources.
"""

_COUNTERARGUMENT_INSTR = """\
You are the Devil's Advocate Researcher. Your job is to challenge the topic.
Find:
1. What are the strongest arguments AGAINST this approach?
2. What are the common failure modes in production?
3. What do skeptical practitioners say?
4. Are there better alternatives? What does each trade off?
5. What are the hidden costs (technical debt, operational overhead, learning curve)?

Be ruthlessly honest. Steel-man the counterarguments.
"""

_SYNTHESIZER_INSTR = """\
You are the Research Synthesizer. Three researchers have investigated a topic:
- FORK_OVERVIEW: broad landscape knowledge
- FORK_DEEP_DIVE: technical depth + current sources
- FORK_COUNTERARGUMENT: risks and alternatives

Produce a BriefPacket JSON research report for Antigravity.

Output ONLY valid JSON:
{
  "pattern": "research_sweep",
  "job_id": "__JOB_ID_PLACEHOLDER__",
  "fired_at": "__NOW__",
  "completed_at": "__NOW__",
  "cost_usd": 0.0,
  "decision_surface": {
    "question": "What do I need to know before acting on this topic?",
    "options": [
      {
        "label": "Main Approach",
        "agent": "FORK_OVERVIEW",
        "summary": "[Distilled overview — 3-4 sentences]",
        "risks": [],
        "confidence": 0.9,
        "artifacts": []
      },
      {
        "label": "Technical Depth",
        "agent": "FORK_DEEP_DIVE",
        "summary": "[Most important technical finding — 3-4 sentences]",
        "risks": ["[key technical risk]"],
        "confidence": 0.8,
        "artifacts": []
      },
      {
        "label": "Counterarguments",
        "agent": "FORK_COUNTERARGUMENT",
        "summary": "[Strongest counterargument or alternative — 2-3 sentences]",
        "risks": ["[primary risk raised]"],
        "confidence": 0.7,
        "artifacts": []
      }
    ],
    "synthesizer_recommendation": "[Balanced recommendation: proceed / reconsider / alternatives. 3-5 sentences.]",
    "next_action_options": ["proceed_with_approach", "investigate_alternative", "run_simulation_swarm", "cancel"]
  },
  "session_context": null,
  "raw_synthesis": "",
  "pattern_artifacts": [],
  "error": ""
}
"""

register_pattern(PatternDefinition(
    name="research_sweep",
    description=(
        "Deep domain investigation via 3 parallel research agents (overview, deep technical, "
        "counterargument). FORK_DEEP_DIVE uses grounding. Cost: ~$0.15–0.80."
    ),
    estimated_cost_usd=0.30,
    required_surfaces=["TEXT", "DEEP_RESEARCH"],
    has_human_gate=True,
    payload_template=(
        "## Research Sweep Input\n\n"
        "**Research Question:**\n{question}\n\n"
        "**Scope / Context:**\n{context}\n\n"
        "**Key constraints or non-negotiables:**\n{constraints}"
    ),
    nodes=[
        PatternNode(
            node_id="INGEST",
            agent_name="Pattern_Fork_Agent",
            instruction_override="Fan out the research question to three parallel research agents. Pass input unchanged.",
            next_node="FORK_OVERVIEW,FORK_DEEP_DIVE,FORK_COUNTERARGUMENT",
            temperature=0.1,
            model_override="gemini-2.5-flash-lite",
        ),
        PatternNode(
            node_id="FORK_OVERVIEW",
            agent_name="Pattern_Fork_Agent",
            instruction_override=_OVERVIEW_INSTR,
            next_node="JOIN_COMPILE",
            temperature=0.7,
            model_override="gemini-2.5-flash",
        ),
        PatternNode(
            node_id="FORK_DEEP_DIVE",
            agent_name="Pattern_Deep_Research_Agent",
            instruction_override=_DEEP_DIVE_INSTR,
            next_node="JOIN_COMPILE",
            temperature=0.7,
            model_override="gemini-2.5-pro",    # Pro for grounding quality
        ),
        PatternNode(
            node_id="FORK_COUNTERARGUMENT",
            agent_name="Pattern_Fork_Agent",
            instruction_override=_COUNTERARGUMENT_INSTR,
            next_node="JOIN_COMPILE",
            temperature=1.0,                    # Higher temp for devil's advocate creativity
            model_override="gemini-2.5-flash",
        ),
        PatternNode(
            node_id="JOIN_COMPILE",
            agent_name="Pattern_Synthesizer",
            instruction_override=_SYNTHESIZER_INSTR,
            next_node="HUMAN_GATE",
            temperature=0.1,
            model_override="gemini-2.5-pro",
            wait_for="FORK_OVERVIEW,FORK_DEEP_DIVE,FORK_COUNTERARGUMENT",
        ),
        PatternNode(
            node_id="HUMAN_GATE",
            agent_name="Pattern_Fork_Agent",
            instruction_override="Pass the input through unchanged.",
            next_node="MANUAL",
            temperature=0.1,
            model_override="gemini-2.5-flash-lite",
        ),
    ],
    agent_roster_entries=[
        {
            "Agent_Name": "Pattern_Deep_Research_Agent",
            "Model": "gemini-2.5-pro",
            "Tools_Allowed": "grounding_search",
            "System_Prompt": (
                "You are a Deep Research agent with live web search capability. "
                "Always use grounding to verify facts. Cite sources. Be technically precise."
            ),
        },
    ],
))
