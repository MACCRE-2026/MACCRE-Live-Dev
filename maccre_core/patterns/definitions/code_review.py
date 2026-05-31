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
maccre_core/patterns/definitions/code_review.py
================================================
Pattern: code_review

Multi-angle independent code analysis before committing changes.

Three specialized reviewers attack the code from different angles:
correctness, security, and performance. A REVIEW_SYNTHESIZER aggregates
findings with severity ratings.

DAG:
    INGEST → FORK_CORRECTNESS, FORK_SECURITY, FORK_PERFORMANCE (parallel)
             ↓ (wait_for all three)
         JOIN_REVIEW → BRIEF_FORMATTER → HUMAN_GATE → STOP
"""
from maccre_core.patterns import PatternDefinition, PatternNode, register_pattern

_CORRECTNESS_INSTR = """\
You are the Correctness Reviewer. Review the code changes provided.
Focus on:
1. Logic errors, off-by-one errors, null/None handling
2. Type safety — do the types match? Are there implicit coercions?
3. Edge cases — what inputs would break this?
4. Missing error handling — what exceptions are not caught?
5. Race conditions or concurrency issues (if applicable)

Severity scale: CRITICAL (breaks production) / HIGH (likely bug) / MEDIUM (potential issue) / LOW (style/minor)

Output format:
ISSUES:
  - [SEVERITY] [description with line reference if available]
  - ...
VERDICT: [APPROVE / REQUEST_CHANGES / BLOCK]
NOTES: [1-2 sentences of overall assessment]
"""

_SECURITY_INSTR = """\
You are the Security Reviewer. Review the code changes provided.
Focus on:
1. Credential/key exposure — are secrets ever printed, logged, or stored in plaintext?
2. Path traversal — are file paths validated before use?
3. Injection risks — SQL, command, or prompt injection vectors
4. Authentication/authorization gaps — does any operation bypass access controls?
5. Dependency risks — any new imports from untrusted sources?

Severity scale: CRITICAL / HIGH / MEDIUM / LOW

Output format:
ISSUES:
  - [SEVERITY] [description]
  - ...
VERDICT: [APPROVE / REQUEST_CHANGES / BLOCK]
NOTES: [1-2 sentences]
"""

_PERFORMANCE_INSTR = """\
You are the Performance Reviewer. Review the code changes provided.
Focus on:
1. Unnecessary blocking I/O in hot paths
2. N+1 query patterns or repeated DB calls in loops
3. Memory allocation: large objects created in tight loops
4. Missing caching where repeated computation is obvious
5. Resource leak risk: files, DB connections, sockets not closed in finally

Severity scale: CRITICAL (crashes under load) / HIGH (significant degradation) / MEDIUM / LOW

Output format:
ISSUES:
  - [SEVERITY] [description]
  - ...
VERDICT: [APPROVE / REQUEST_CHANGES / BLOCK]
NOTES: [1-2 sentences]
"""

_REVIEW_SYNTHESIZER_INSTR = """\
You are the Review Synthesizer. Three independent reviewers have analyzed code changes.
Aggregate their findings into a BriefPacket JSON review report.

Output ONLY valid JSON:
{
  "pattern": "code_review",
  "job_id": "__JOB_ID_PLACEHOLDER__",
  "fired_at": "__NOW__",
  "completed_at": "__NOW__",
  "cost_usd": 0.0,
  "decision_surface": {
    "question": "Is this code ready to commit?",
    "options": [
      {
        "label": "Correctness Review",
        "agent": "FORK_CORRECTNESS",
        "summary": "[Top finding from correctness review — 2 sentences]",
        "risks": ["[highest severity issue found]"],
        "confidence": 0.9,
        "artifacts": []
      },
      {
        "label": "Security Review",
        "agent": "FORK_SECURITY",
        "summary": "[Top finding from security review — 2 sentences]",
        "risks": ["[highest severity security issue]"],
        "confidence": 0.9,
        "artifacts": []
      },
      {
        "label": "Performance Review",
        "agent": "FORK_PERFORMANCE",
        "summary": "[Top finding from performance review — 2 sentences]",
        "risks": ["[highest severity perf issue]"],
        "confidence": 0.9,
        "artifacts": []
      }
    ],
    "synthesizer_recommendation": "[Overall verdict: APPROVE / REQUEST_CHANGES / BLOCK + reasoning. List any CRITICAL or HIGH issues explicitly. 3-5 sentences.]",
    "next_action_options": ["approve_and_commit", "fix_critical_issues", "fix_all_issues", "request_simulation_swarm"]
  },
  "session_context": null,
  "raw_synthesis": "",
  "pattern_artifacts": [],
  "error": ""
}
"""

register_pattern(PatternDefinition(
    name="code_review",
    description=(
        "Multi-angle code review: correctness, security, and performance reviewers "
        "run in parallel. Synthesizer aggregates with severity ratings. ~$0.03–0.06."
    ),
    estimated_cost_usd=0.05,
    required_surfaces=["TEXT"],
    has_human_gate=True,
    payload_template=(
        "## Code Review Input\n\n"
        "**Files Changed:** {files}\n\n"
        "**Git Diff:**\n```diff\n{diff}\n```\n\n"
        "**Change Description:**\n{description}\n\n"
        "**Specific Concerns (optional):**\n{concerns}"
    ),
    nodes=[
        PatternNode(
            node_id="INGEST",
            agent_name="Pattern_Fork_Agent",
            instruction_override="Fan out to parallel code reviewers. Pass code diff unchanged.",
            next_node="FORK_CORRECTNESS,FORK_SECURITY,FORK_PERFORMANCE",
            temperature=0.1,
            model_override="gemini-2.5-flash-lite",
        ),
        PatternNode(
            node_id="FORK_CORRECTNESS",
            agent_name="Pattern_Code_Auditor",
            instruction_override=_CORRECTNESS_INSTR,
            next_node="JOIN_REVIEW",
            temperature=0.1,
            model_override="gemini-2.5-flash",
        ),
        PatternNode(
            node_id="FORK_SECURITY",
            agent_name="Pattern_Code_Auditor",
            instruction_override=_SECURITY_INSTR,
            next_node="JOIN_REVIEW",
            temperature=0.1,
            model_override="gemini-2.5-flash",
        ),
        PatternNode(
            node_id="FORK_PERFORMANCE",
            agent_name="Pattern_Code_Auditor",
            instruction_override=_PERFORMANCE_INSTR,
            next_node="JOIN_REVIEW",
            temperature=0.1,
            model_override="gemini-2.5-flash",
        ),
        PatternNode(
            node_id="JOIN_REVIEW",
            agent_name="Pattern_Synthesizer",
            instruction_override=_REVIEW_SYNTHESIZER_INSTR,
            next_node="HUMAN_GATE",
            temperature=0.1,
            model_override="gemini-2.5-pro",
            wait_for="FORK_CORRECTNESS,FORK_SECURITY,FORK_PERFORMANCE",
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
    agent_roster_entries=[],  # Reuses Pattern_Code_Auditor and Pattern_Synthesizer
))
