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
maccre_core/patterns/definitions/fault_investigation.py
========================================================
Pattern: fault_investigation

Root cause analysis on failures. Fire when a swarm crashes, costs spike
unexpectedly, or any anomaly occurs.

Three parallel investigators attack the failure from different angles:
log analysis, cost delta, and stack trace. A ROOT_CAUSE synthesizer
produces a diagnosis with remediation options.

DAG:
    INGEST → LOG_ANALYST, COST_DELTA_CHECKER, TRACE_WALKER (parallel)
             ↓ (wait_for all three)
         ROOT_CAUSE → BRIEF_FORMATTER → HUMAN_GATE → STOP
"""
from maccre_core.patterns import PatternDefinition, PatternNode, register_pattern

_LOG_ANALYST_INSTR = """\
You are the Log Analyst. Examine the error logs and system output provided.
Identify:
1. The exact error message and where it occurred (file:line if available)
2. The sequence of events leading up to the failure
3. Any warning patterns that preceded the error
4. Whether this is a first-time failure or a recurring issue
5. Which system component (router, broker, worker, tool) is the likely source

Output format:
ERROR_CLASS: [runtime / config / network / data / auth / unknown]
FIRST_SEEN: [timestamp or "unknown"]
SEQUENCE: [numbered list of events leading to failure]
LIKELY_SOURCE: [specific component name]
RECURRING: [YES / NO / UNKNOWN]
"""

_COST_DELTA_INSTR = """\
You are the Cost Delta Checker. Examine the cost and telemetry data provided.
Identify:
1. Did costs spike around the time of failure?
2. Were any unexpected models used (wrong tier for the task)?
3. Did any node run significantly more times than expected (recursion issue)?
4. Is there evidence of token bloat (unusually large prompts)?
5. What was the total cost attributed to this failed job?

Output format:
FAILED_JOB_COST_USD: [amount or "unknown"]
COST_ANOMALY: [YES / NO]
ANOMALY_DESCRIPTION: [details or "none"]
RECURSION_DETECTED: [YES / NO]
TOKEN_BLOAT: [YES / NO]
"""

_TRACE_WALKER_INSTR = """\
You are the Trace Walker. Examine the stack trace, agent ledgers, or error output provided.
Trace the execution path:
1. Which node was executing when the failure occurred?
2. What was the last successful node?
3. What input was the node processing?
4. Is the failure deterministic (same input → same failure) or intermittent?
5. What data or state would need to change to avoid this failure?

Output format:
FAILED_NODE: [node_id or "unknown"]
LAST_SUCCESS: [node_id or "unknown"]
FAILURE_TYPE: [DETERMINISTIC / INTERMITTENT / UNKNOWN]
ROOT_STATE: [description of the problematic state or input]
FIX_VECTOR: [what needs to change to avoid recurrence]
"""

_ROOT_CAUSE_INSTR = """\
You are the Root Cause Synthesizer. You have received analysis from:
- LOG_ANALYST: error sequencing and source identification
- COST_DELTA_CHECKER: financial anomaly detection
- TRACE_WALKER: execution path tracing

Produce a fault investigation BriefPacket JSON:

Output ONLY valid JSON:
{
  "pattern": "fault_investigation",
  "job_id": "__JOB_ID_PLACEHOLDER__",
  "fired_at": "__NOW__",
  "completed_at": "__NOW__",
  "cost_usd": 0.0,
  "decision_surface": {
    "question": "What caused the failure and how do I fix it?",
    "options": [
      {
        "label": "Root Cause",
        "agent": "ROOT_CAUSE",
        "summary": "[Definitive root cause statement — 2-3 sentences]",
        "risks": ["[risk of recurrence]"],
        "confidence": 0.85,
        "artifacts": []
      },
      {
        "label": "Remediation Option A — Quick Fix",
        "agent": "TRACE_WALKER",
        "summary": "[Fastest path to resolution]",
        "risks": ["[trade-offs of quick fix]"],
        "confidence": 0.8,
        "artifacts": []
      },
      {
        "label": "Remediation Option B — Root Fix",
        "agent": "LOG_ANALYST",
        "summary": "[Permanent fix that addresses root cause]",
        "risks": ["[effort / risk of deeper change]"],
        "confidence": 0.7,
        "artifacts": []
      }
    ],
    "synthesizer_recommendation": "[Recommended remediation path with reasoning. 3-5 sentences.]",
    "next_action_options": ["apply_quick_fix", "apply_root_fix", "resume_from_checkpoint", "cancel_job", "run_simulation_swarm"]
  },
  "session_context": null,
  "raw_synthesis": "",
  "pattern_artifacts": [],
  "error": ""
}
"""

register_pattern(PatternDefinition(
    name="fault_investigation",
    description=(
        "Root cause analysis on failures. 3 parallel investigators (logs, cost, trace) "
        "feed a ROOT_CAUSE synthesizer that produces diagnosis + remediation options."
    ),
    estimated_cost_usd=0.05,
    required_surfaces=["TEXT"],
    has_human_gate=True,
    payload_template=(
        "## Fault Investigation Input\n\n"
        "**Failed Job ID:** {job_id}\n\n"
        "**Error Description:**\n{error}\n\n"
        "**Stack Trace / Log Output:**\n```\n{stack_trace}\n```\n\n"
        "**Recent Cost Data:**\n{cost_data}\n\n"
        "**Agent Ledger Excerpts:**\n{ledger_excerpts}"
    ),
    nodes=[
        PatternNode(
            node_id="INGEST",
            agent_name="Pattern_Fork_Agent",
            instruction_override="Fan out the failure context to three parallel investigators. Pass input unchanged.",
            next_node="LOG_ANALYST,COST_DELTA_CHECKER,TRACE_WALKER",
            temperature=0.1,
            model_override="gemini-2.5-flash-lite",
        ),
        PatternNode(
            node_id="LOG_ANALYST",
            agent_name="Pattern_Fork_Agent",
            instruction_override=_LOG_ANALYST_INSTR,
            next_node="ROOT_CAUSE",
            temperature=0.1,
            model_override="gemini-2.5-flash",
        ),
        PatternNode(
            node_id="COST_DELTA_CHECKER",
            agent_name="Pattern_Fork_Agent",
            instruction_override=_COST_DELTA_INSTR,
            next_node="ROOT_CAUSE",
            temperature=0.1,
            model_override="gemini-2.5-flash",
        ),
        PatternNode(
            node_id="TRACE_WALKER",
            agent_name="Pattern_Fork_Agent",
            instruction_override=_TRACE_WALKER_INSTR,
            next_node="ROOT_CAUSE",
            temperature=0.1,
            model_override="gemini-2.5-flash",
        ),
        PatternNode(
            node_id="ROOT_CAUSE",
            agent_name="Pattern_Synthesizer",
            instruction_override=_ROOT_CAUSE_INSTR,
            next_node="HUMAN_GATE",
            temperature=0.1,
            model_override="gemini-2.5-pro",
            wait_for="LOG_ANALYST,COST_DELTA_CHECKER,TRACE_WALKER",
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
    agent_roster_entries=[],  # Reuses Pattern_Fork_Agent and Pattern_Synthesizer
))
