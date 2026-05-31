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
maccre_core/patterns/definitions/session_brief.py
==================================================
Pattern: session_brief

"The reminder pattern." Fires at the start of each session to re-contextualize
Antigravity as a stateless process with a fully informed starting state.

Reads: git log, telemetry, cost data → produces a compact BriefPacket JSON
describing the current project state, recent activity, and recommended
next action.

DAG:
    INGEST → GIT_HISTORIAN, TELEMETRY_READER, COST_AUDITOR (parallel)
             ↓ (wait_for all three)
         JOIN_BRIEF → BRIEF_FORMATTER → HUMAN_GATE → STOP

Cost: ~$0.005 (all flash-lite)
This should be free to fire at every session start.
"""
from maccre_core.patterns import PatternDefinition, PatternNode, register_pattern

_GIT_INSTR = """\
You are the Git Historian. Read the git log context provided to you.
Summarize the last 7 commits in plain language:
- What changed?
- Any breaking changes, new features, or bug fixes?
- What is the current HEAD commit hash?

Output format (3 sections):
HEAD: [7-char hash]
RECENT_ACTIVITY: [2-4 sentence summary]
NOTABLE_CHANGES: [bullet list of significant changes]
"""

_TELEMETRY_INSTR = """\
You are the Telemetry Reader. Read the swarm execution context provided.
Summarize:
- Any pending tasks, failed nodes, or stuck jobs
- Recent agent activity (what nodes ran, what completed)
- Any anomalies or warnings worth flagging

Output format:
STATUS: [HEALTHY / WARNING / DEGRADED]
PENDING_JOBS: [list or "none"]
ANOMALIES: [list or "none"]
SUMMARY: [2-3 sentence summary]
"""

_COST_INSTR = """\
You are the Cost Auditor. Review the cost and FinOps context provided.
Summarize:
- Total spend in the last 7 days (USD)
- Most expensive models used
- Any cost anomalies or unexpected charges
- Cost-per-session trend (increasing / stable / decreasing)

Output format:
TOTAL_7D_USD: [amount]
TOP_MODELS: [list of model:cost pairs]
TREND: [INCREASING / STABLE / DECREASING]
ANOMALIES: [list or "none"]
"""

_BRIEF_INSTR = """\
You are the Session Brief Formatter. You have received reports from:
- Git Historian (recent code activity)
- Telemetry Reader (system health)
- Cost Auditor (spending summary)

Produce a BriefPacket JSON for Antigravity's session startup.

Output ONLY valid JSON (no markdown fences):
{
  "pattern": "session_brief",
  "job_id": "__JOB_ID_PLACEHOLDER__",
  "fired_at": "__NOW__",
  "completed_at": "__NOW__",
  "cost_usd": 0.0,
  "decision_surface": {
    "question": "What is the current project state and recommended next action?",
    "options": [],
    "synthesizer_recommendation": "[Concise synthesis: what happened, what's next, any blockers. 3-5 sentences.]",
    "next_action_options": ["continue_current_task", "run_simulation_swarm", "run_checkpoint_sweep", "start_new_task"]
  },
  "session_context": {
    "project": "__PROJECT__",
    "git_head": "[7-char hash from git historian]",
    "git_recent_commits": ["[commit line 1]", "[commit line 2]", "[commit line 3]"],
    "open_tasks": [],
    "cost_7d_usd": 0.0,
    "cost_session_usd": 0.0,
    "sentinel_health": {},
    "active_jobs": []
  },
  "raw_synthesis": "",
  "pattern_artifacts": [],
  "error": ""
}
"""

_PASSTHROUGH_INSTR = "Pass the input through unchanged."

register_pattern(PatternDefinition(
    name="session_brief",
    description=(
        "The wake-up pattern. Fires at session start to re-contextualize Antigravity. "
        "Reads git log, telemetry, and cost data. Returns a compact BriefPacket. ~$0.005."
    ),
    estimated_cost_usd=0.005,
    required_surfaces=["TEXT"],
    has_human_gate=True,
    payload_template=(
        "## Session Brief Input\n\n"
        "**Active Project:** {project}\n\n"
        "**Git Log (last 10 commits):**\n```\n{git_log}\n```\n\n"
        "**Recent Telemetry:**\n{telemetry}\n\n"
        "**Cost Summary:**\n{cost_summary}"
    ),
    nodes=[
        PatternNode(
            node_id="INGEST",
            agent_name="Pattern_Session_Reader",
            instruction_override="Read the session context and fan out to parallel readers. Pass input unchanged.",
            next_node="GIT_HISTORIAN,TELEMETRY_READER,COST_AUDITOR",
            temperature=0.1,
            model_override="gemini-2.5-flash-lite",
        ),
        PatternNode(
            node_id="GIT_HISTORIAN",
            agent_name="Pattern_Session_Reader",
            instruction_override=_GIT_INSTR,
            next_node="JOIN_BRIEF",
            temperature=0.1,
            model_override="gemini-2.5-flash-lite",
        ),
        PatternNode(
            node_id="TELEMETRY_READER",
            agent_name="Pattern_Session_Reader",
            instruction_override=_TELEMETRY_INSTR,
            next_node="JOIN_BRIEF",
            temperature=0.1,
            model_override="gemini-2.5-flash-lite",
        ),
        PatternNode(
            node_id="COST_AUDITOR",
            agent_name="Pattern_Session_Reader",
            instruction_override=_COST_INSTR,
            next_node="JOIN_BRIEF",
            temperature=0.1,
            model_override="gemini-2.5-flash-lite",
        ),
        PatternNode(
            node_id="JOIN_BRIEF",
            agent_name="Pattern_Synthesizer",
            instruction_override=_BRIEF_INSTR,
            next_node="HUMAN_GATE",
            temperature=0.1,
            model_override="gemini-2.5-flash",
            wait_for="GIT_HISTORIAN,TELEMETRY_READER,COST_AUDITOR",
        ),
        PatternNode(
            node_id="HUMAN_GATE",
            agent_name="Pattern_Session_Reader",
            instruction_override=_PASSTHROUGH_INSTR,
            next_node="MANUAL",
            temperature=0.1,
            model_override="gemini-2.5-flash-lite",
        ),
    ],
    agent_roster_entries=[
        {
            "Agent_Name": "Pattern_Session_Reader",
            "Model": "gemini-2.5-flash-lite",
            "Tools_Allowed": "none",
            "System_Prompt": (
                "You are a session analysis agent. Follow your specific instructions exactly. "
                "Be concise and factual. No elaboration beyond what is asked."
            ),
        },
    ],
))
