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
maccre_core/patterns/definitions/checkpoint_sweep.py
=====================================================
Pattern: checkpoint_sweep

End-of-work-block consolidation. Run after completing a significant work block.

Validates what was done (code correctness, QA), reconciles costs, and writes
a Knowledge Item (KI) update. Produces a forward brief with the recommended
next action before the session ends.

DAG:
    INGEST → CODE_AUDITOR, COST_RECONCILER (parallel)
             ↓ (wait_for both)
         KI_WRITER → BRIEF_FORMATTER → HUMAN_GATE → STOP
"""
from maccre_core.patterns import PatternDefinition, PatternNode, register_pattern

_CODE_AUDITOR_INSTR = """\
You are the Code Auditor. Review the work block context provided.
Analyze:
1. CORRECTNESS: Does the implementation match the stated intent? Any logical errors?
2. COMPLETENESS: Are there obvious gaps, missing edge cases, or TODO items left open?
3. QUALITY: Ruff/pyright compliance, type safety, resource teardown (try/finally).
4. RISK: What is the highest-risk change made? Why?
5. RECOMMENDATION: Should this be committed as-is, or does it need fixes first?

Output format:
STATUS: [CLEAN / NEEDS_FIXES / BLOCKED]
RISK_LEVEL: [LOW / MEDIUM / HIGH]
ISSUES: [numbered list of specific issues, or "none"]
RECOMMENDATION: [1-2 sentences]
"""

_COST_RECONCILER_INSTR = """\
You are the Cost Reconciler. Review the FinOps and telemetry context provided.
Analyze:
1. Total cost for this work block (USD)
2. Cost per major task / model used
3. Any cost anomalies (unexpected spikes, wrong model for task)
4. Projected cost if this pattern of work continues for 7 days
5. Optimization opportunities (could a cheaper model have done the same job?)

Output format:
BLOCK_COST_USD: [amount]
TOP_SPENDS: [model:cost pairs]
ANOMALIES: [list or "none"]
PROJECTION_7D_USD: [estimated]
OPTIMIZATION: [specific suggestions or "none"]
"""

_KI_WRITER_INSTR = """\
You are the Knowledge Item Writer. You have received:
- Code audit results
- Cost reconciliation results

Produce a BriefPacket JSON that serves as both a KI update and a forward brief.

Output ONLY valid JSON:
{
  "pattern": "checkpoint_sweep",
  "job_id": "__JOB_ID_PLACEHOLDER__",
  "fired_at": "__NOW__",
  "completed_at": "__NOW__",
  "cost_usd": 0.0,
  "decision_surface": {
    "question": "Is the work block complete and ready to commit? What is the recommended next action?",
    "options": [
      {
        "label": "Code Audit Result",
        "agent": "CODE_AUDITOR",
        "summary": "[Summary of audit findings — 2-3 sentences]",
        "risks": ["[top risk identified]"],
        "confidence": 0.9,
        "artifacts": []
      },
      {
        "label": "Cost Reconciliation",
        "agent": "COST_RECONCILER",
        "summary": "[Summary of cost findings — 2-3 sentences]",
        "risks": ["[cost anomaly if any]"],
        "confidence": 0.9,
        "artifacts": []
      }
    ],
    "synthesizer_recommendation": "[Combined recommendation: commit/fix/next-steps. Include KI update summary. 3-5 sentences.]",
    "next_action_options": ["commit_and_continue", "fix_issues_first", "run_simulation_swarm", "end_session"]
  },
  "session_context": null,
  "raw_synthesis": "",
  "pattern_artifacts": [],
  "error": ""
}
"""

register_pattern(PatternDefinition(
    name="checkpoint_sweep",
    description=(
        "End-of-work validation + KI update. Runs code audit and cost reconciliation "
        "in parallel. Produces a forward brief. Fire after completing a significant work block."
    ),
    estimated_cost_usd=0.04,
    required_surfaces=["TEXT"],
    has_human_gate=True,
    payload_template=(
        "## Checkpoint Sweep Input\n\n"
        "**Work Block Summary:**\n{summary}\n\n"
        "**Files Changed:**\n{files_changed}\n\n"
        "**Git Diff (or description):**\n{diff}\n\n"
        "**Cost Data:**\n{cost_data}"
    ),
    nodes=[
        PatternNode(
            node_id="INGEST",
            agent_name="Pattern_Fork_Agent",
            instruction_override="Fan out to parallel audit agents. Pass input unchanged.",
            next_node="CODE_AUDITOR,COST_RECONCILER",
            temperature=0.1,
            model_override="gemini-2.5-flash-lite",
        ),
        PatternNode(
            node_id="CODE_AUDITOR",
            agent_name="Pattern_Code_Auditor",
            instruction_override=_CODE_AUDITOR_INSTR,
            next_node="KI_WRITER",
            temperature=0.1,
            model_override="gemini-2.5-pro",    # Needs judgment — use Pro
        ),
        PatternNode(
            node_id="COST_RECONCILER",
            agent_name="Pattern_Fork_Agent",
            instruction_override=_COST_RECONCILER_INSTR,
            next_node="KI_WRITER",
            temperature=0.1,
            model_override="gemini-2.5-flash",
        ),
        PatternNode(
            node_id="KI_WRITER",
            agent_name="Pattern_Synthesizer",
            instruction_override=_KI_WRITER_INSTR,
            next_node="HUMAN_GATE",
            temperature=0.1,
            model_override="gemini-2.5-flash",
            wait_for="CODE_AUDITOR,COST_RECONCILER",
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
            "Agent_Name": "Pattern_Code_Auditor",
            "Model": "gemini-2.5-pro",
            "Tools_Allowed": "none",
            "System_Prompt": (
                "You are a senior code reviewer. Be specific, concrete, and unsparing. "
                "Identify real issues, not theoretical ones. Follow the output format exactly."
            ),
        },
    ],
))
