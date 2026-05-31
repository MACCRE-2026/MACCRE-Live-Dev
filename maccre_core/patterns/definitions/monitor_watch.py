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
maccre_core/patterns/definitions/monitor_watch.py
==================================================
Pattern: monitor_watch

Background daemon monitoring. Watches a running job or system metric for
threshold conditions — cost drift, error spikes, or completion.

Simulates cyclic behavior via ACYCLIC recursion: MONITOR_LOOP re-routes to
itself until a condition triggers, at which point it exits to ALERT_BRIEF.
Max_Recursion bounds the loop depth.

DAG (acyclic simulation of a cycle):
    INGEST → MONITOR_LOOP → CONDITION_CHECK → MONITOR_LOOP (recurse, bounded)
                                             ↘ ALERT_BRIEF → HUMAN_GATE → STOP

Cost: ~$0.001/cycle (flash-lite) × Max_Recursion cycles
Default: 20 cycles × $0.001 = ~$0.02 total
"""
from maccre_core.patterns import PatternDefinition, PatternNode, register_pattern

_MONITOR_INSTR = """\
You are the Monitor Agent. You are watching a long-running swarm job.
Check the provided status snapshot for:
1. Has the job completed? (lock_status = 'completed' on all nodes)
2. Has a cost threshold been exceeded?
3. Are there FAILED nodes?
4. Are there nodes stuck in 'locked' state for >10 minutes?

Respond with EXACTLY one of:
  STATUS: CONTINUE
  STATUS: ALERT [reason]
  STATUS: COMPLETE

If STATUS is ALERT or COMPLETE, add:
REASON: [one sentence explaining why]

Nothing else. No elaboration.
"""

_CONDITION_INSTR = """\
You are the Condition Router. You received a monitor status report.
Read the STATUS line:
  - If STATUS: CONTINUE → output only: ROUTE_TO: MONITOR_LOOP
  - If STATUS: ALERT or STATUS: COMPLETE → output only: ROUTE_TO: ALERT_BRIEF

Then output the full status report below the routing decision.
Nothing else.
"""

_ALERT_INSTR = """\
You are the Alert Formatter. A monitoring condition has been triggered.
Produce a BriefPacket JSON alert:

Output ONLY valid JSON:
{
  "pattern": "monitor_watch",
  "job_id": "__JOB_ID_PLACEHOLDER__",
  "fired_at": "__NOW__",
  "completed_at": "__NOW__",
  "cost_usd": 0.0,
  "decision_surface": {
    "question": "A monitored condition has been triggered. What action is required?",
    "options": [
      {
        "label": "Alert Condition",
        "agent": "MONITOR_LOOP",
        "summary": "[What condition triggered the alert — 2 sentences]",
        "risks": ["[consequence if not addressed]"],
        "confidence": 0.95,
        "artifacts": []
      }
    ],
    "synthesizer_recommendation": "[Recommended immediate action. 2-3 sentences.]",
    "next_action_options": ["acknowledge_and_continue", "investigate_fault", "cancel_watched_job", "run_fault_investigation"]
  },
  "session_context": null,
  "raw_synthesis": "",
  "pattern_artifacts": [],
  "error": ""
}
"""

register_pattern(PatternDefinition(
    name="monitor_watch",
    description=(
        "Background daemon that watches a job for cost drift, errors, or completion. "
        "Simulates cycles via bounded recursion. Fires HUMAN_GATE only on threshold breach. "
        "~$0.001/cycle × Max_Recursion cycles."
    ),
    estimated_cost_usd=0.02,
    required_surfaces=["TEXT"],
    has_human_gate=True,           # Conditional — only fires on alert/complete
    payload_template=(
        "## Monitor Watch Input\n\n"
        "**Watching Job ID:** {watched_job_id}\n\n"
        "**Alert Conditions:**\n{conditions}\n\n"
        "  - Cost threshold: ${cost_threshold_usd}\n"
        "  - Max runtime: {max_runtime_minutes} minutes\n"
        "  - Error threshold: {error_node_count} failed nodes\n\n"
        "**Poll interval:** {poll_interval_minutes} minutes\n"
        "**Max cycles:** {max_cycles}"
    ),
    nodes=[
        PatternNode(
            node_id="INGEST",
            agent_name="Pattern_Monitor_Agent",
            instruction_override=_MONITOR_INSTR,
            next_node="CONDITION_CHECK",
            temperature=0.1,
            model_override="gemini-2.5-flash-lite",
            max_recursion=20,
        ),
        PatternNode(
            node_id="MONITOR_LOOP",
            agent_name="Pattern_Monitor_Agent",
            instruction_override=_MONITOR_INSTR,
            next_node="CONDITION_CHECK",
            temperature=0.1,
            model_override="gemini-2.5-flash-lite",
            max_recursion=20,
        ),
        PatternNode(
            node_id="CONDITION_CHECK",
            agent_name="Pattern_Monitor_Agent",
            instruction_override=_CONDITION_INSTR,
            next_node="MONITOR_LOOP,ALERT_BRIEF",  # Worker reads ROUTE_TO: from output
            temperature=0.1,
            model_override="gemini-2.5-flash-lite",
            max_recursion=20,
        ),
        PatternNode(
            node_id="ALERT_BRIEF",
            agent_name="Pattern_Synthesizer",
            instruction_override=_ALERT_INSTR,
            next_node="HUMAN_GATE",
            temperature=0.1,
            model_override="gemini-2.5-flash",
        ),
        PatternNode(
            node_id="HUMAN_GATE",
            agent_name="Pattern_Monitor_Agent",
            instruction_override="Pass the input through unchanged.",
            next_node="MANUAL",
            temperature=0.1,
            model_override="gemini-2.5-flash-lite",
        ),
    ],
    agent_roster_entries=[
        {
            "Agent_Name": "Pattern_Monitor_Agent",
            "Model": "gemini-2.5-flash-lite",
            "Tools_Allowed": "none",
            "System_Prompt": (
                "You are a monitoring agent. Follow instructions precisely. "
                "Output only what is requested. Be binary in your decisions."
            ),
        },
    ],
))
