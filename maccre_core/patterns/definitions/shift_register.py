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
maccre_core/patterns/definitions/shift_register.py
===================================================
Pattern: shift_register

A 3-agent shift-register deliberation topology.

Three agents (Pioneer A/B/C) each produce a distinct implementation plan from
different philosophical starting points, then each plan is circulated through
all the other agents in 3 rotation cycles — like a hardware shift register
where data shifts one position on every clock edge.

The result is 3 plans that stay DIVERGENT throughout (not collapsed into one
answer) but have been cross-pollinated and stress-tested by all three
independent perspectives.  A Synthesizer then packages all three evolved plans
as a structured BriefPacket for Antigravity + User deliberation.

Sequential topology — no parallel execution required:

  INGEST
    └── INIT_A  (Pioneer_A drafts Plan A)
    └── INIT_B  (Pioneer_B drafts Plan B — sees A, writes independently)
    └── INIT_C  (Pioneer_C drafts Plan C — sees A+B, writes independently)
    └── COMPILE_INITS (assembles all 3 init plans into a single clean document)
          │
  ── Shift Cycle 1 ────────────────────────────────────────────────────────────
    └── S1_A_TO_B  (Pioneer_B reviews + refines PLAN_A — outputs ONLY its new section)
    └── S1_B_TO_C  (Pioneer_C reviews + refines PLAN_B — outputs ONLY its new section)
    └── S1_C_TO_A  (Pioneer_A reviews + refines PLAN_C — outputs ONLY its new section)
          │
  ── Shift Cycle 2 ────────────────────────────────────────────────────────────
    └── S2_rA_TO_C (Pioneer_C reviews PLAN_A after B's shift)
    └── S2_rB_TO_A (Pioneer_A reviews PLAN_B after C's shift)
    └── S2_rC_TO_B (Pioneer_B reviews PLAN_C after A's shift)
          │
  ── Shift Cycle 3 (return to origin) ─────────────────────────────────────────
    └── S3_rA_TO_A (Pioneer_A receives PLAN_A — 2 external reviews — final authoritative version)
    └── S3_rB_TO_B (Pioneer_B receives PLAN_B — 2 external reviews — final authoritative version)
    └── S3_rC_TO_C (Pioneer_C receives PLAN_C — 2 external reviews — final authoritative version)
    └── COMPILE_FINALS (assembles the 3 final plans into the synthesizer's input document)
          │
  SYNTHESIZE → HUMAN_GATE → STOP

Key design: COMPILE_INITS and COMPILE_FINALS are pure-concatenation nodes (no model opinion).
Shift nodes only output their ONE new section — no context re-emission required.
"""
from maccre_core.patterns import PatternDefinition, PatternNode, register_pattern

# ─────────────────────────────────────────────────────────────────────────────
# Agent system prompts — persona-level identity locked at roster level
# ─────────────────────────────────────────────────────────────────────────────

_A_PERSONA = (
    "You are Pioneer_A — the Creative Experimentalist in a shift-register deliberation swarm. "
    "Your instinct is to reach for unconventional, forward-looking approaches: event-driven "
    "architectures, emerging patterns, data-first designs, creative re-framings of the problem. "
    "You value novelty and are willing to accept more implementation risk for a better solution shape. "
    "When reviewing another agent's plan, probe its assumptions aggressively and inject your "
    "experimental perspective. Always label your contributions clearly."
)

_B_PERSONA = (
    "You are Pioneer_B — the Pragmatic Engineer in a shift-register deliberation swarm. "
    "Your instinct is toward proven, deliverable solutions: API-contract-first, "
    "dependency-minimal, test-driven, with a clear delivery path. "
    "You value correctness and predictable timelines over elegance. "
    "When reviewing another agent's plan, find the practical gaps and harden the implementation path. "
    "Always label your contributions clearly."
)

_C_PERSONA = (
    "You are Pioneer_C — the Systems Conservative in a shift-register deliberation swarm. "
    "Your instinct is toward battle-tested patterns: monolith-first, slow extraction, "
    "defensive coding, explicit contracts, minimal magic. "
    "You distrust clever approaches and ask 'what happens when this breaks at 2am?' "
    "When reviewing another agent's plan, stress-test it operationally and flag hidden complexity. "
    "Always label your contributions clearly."
)

# ─────────────────────────────────────────────────────────────────────────────
# Node instruction templates
# ─────────────────────────────────────────────────────────────────────────────

_INIT_INSTR = """\
## SHIFT REGISTER — INIT PHASE ({agent_id}: {plan_label})

You are the FIRST agent to produce a plan within your assigned philosophical lane.
**Your lane: {lane_description}**

### Your Task
Read the problem statement in the context you were given.
If other plans are already present in the context, note them briefly (one line each)
but write YOUR plan INDEPENDENTLY in your lane.

Output ONLY your plan — a clean standalone document with exactly this structure:

## {plan_label} [INIT — {agent_id}]

### Approach
[Your core strategy in 2-3 sentences]

### Architecture
[Concrete components, data structures, key interfaces. Be specific enough that a
 senior engineer could begin implementing from this alone.]

### Key Decisions
[3-5 explicit architectural choices and your reasoning for each]

### Risks
[Specific technical risks — not generic. What actually breaks here?]

### Effort Estimate
Low / Medium / High — and why

### Confidence
[Float 0.0–1.0 — how confident you are this path solves the problem correctly]

---
Do NOT include the other plans in your output. Your output is ONLY your plan section.
Do NOT collapse your plan into someone else's approach. Stay firmly in your lane.\
"""

_SHIFT_INSTR = """\
## SHIFT REGISTER — SHIFT PHASE ({reviewer_id} reviews {plan_label})

You are {reviewer_id}. You are reviewing and refining **{plan_label}**.

You will see:
  [SOURCE DOCUMENT] — all 3 initial plans (PLAN_A, PLAN_B, PLAN_C)
  [PREVIOUS NODE OUTPUT] — the most recent refinement of {plan_label} (if any)

### Your Task
Find {plan_label} in the source document (or the previous output if a prior reviewer
already refined it). Produce ONLY your refined section — do NOT re-emit the other plans.

## {plan_label} [SHIFT {cycle} — reviewed by {reviewer_id}]

### What Changed
[Summarise the 2-4 most significant changes you made and why, citing the previous version]

### Architecture (Refined)
[Updated concrete component/structure description — complete, not a diff]

### Key Decisions (Refined)
[Complete updated decision list — add new ones, explicitly note any removed]

### Risks (Refined)
[Re-assessed risks — be specific, not generic]

### Confidence
[Float 0.0–1.0 — your confidence in THIS plan after your review]

---
Output ONLY your new refined section above. Do NOT include other plans. Do NOT repeat
the source document. Your entire output is just the ## {plan_label} [SHIFT {cycle}...] block.\
"""

_FINAL_SHIFT_INSTR = """\
## SHIFT REGISTER — FINAL PASS ({agent_id} receives {plan_label} back after 2 external reviews)

You are {agent_id}, original author of {plan_label}.

You will see:
  [SOURCE DOCUMENT] — all 3 original initial plans
  [PREVIOUS NODE OUTPUT] — the most recent external refinement of {plan_label}

You have now seen your plan reviewed by 2 other agents. Produce the FINAL authoritative
version of {plan_label} incorporating the best improvements while preserving your core vision.

## {plan_label} [FINAL — {agent_id} original author, after full shift cycle]

### Evolution Summary
[3-5 sentences: what changed from your original? What did reviewers improve,
 what did they miss, and what are you restoring or overriding and why?]

### Final Architecture
[The definitive, complete, deliverable-quality architecture description]

### Final Key Decisions
[Complete definitive decision list with full reasoning]

### Final Risks
[Honest, specific operational risk assessment]

### Final Confidence
[Float 0.0–1.0]

### Ready to Implement?
Yes / No — and exactly one sentence on what would need to change for "Yes"

---
Output ONLY your final plan section above. Do NOT include other plans or the source document.\
"""

_COMPILE_INITS_INSTR = (
    "You are the Compiler node in a shift-register swarm. "
    "Your input contains 3 initial implementation plans (PLAN_A, PLAN_B, PLAN_C) "
    "from 3 different agents. "
    "Output them ALL in this exact format, completely verbatim, with section separators:\n\n"
    "=== SHIFT REGISTER INITIAL PLANS ===\n\n"
    "[PASTE PLAN_A SECTION EXACTLY AS WRITTEN]\n\n"
    "---\n\n"
    "[PASTE PLAN_B SECTION EXACTLY AS WRITTEN]\n\n"
    "---\n\n"
    "[PASTE PLAN_C SECTION EXACTLY AS WRITTEN]\n\n"
    "=== END INITIAL PLANS ===\n\n"
    "Do not summarize, modify, or add commentary. Verbatim copy only."
)

_COMPILE_FINALS_INSTR = (
    "You are the Final Compiler node in a shift-register swarm. "
    "Your input document already contains all 3 FINAL plan sections: "
    "PLAN_A [FINAL], PLAN_B [FINAL], and PLAN_C [FINAL], assembled by the preceding S3 chain. "
    "Output the entire document exactly as received, wrapped in these delimiters:\n\n"
    "=== SHIFT REGISTER FINAL PLANS ===\n\n"
    "[paste the entire received document verbatim here]\n\n"
    "=== END FINAL PLANS ===\n\n"
    "Do not summarize or modify. The Synthesizer reads this document directly."
)

# Chain-aware S3 final pass variants — B and C know A's final is already above them
_S3B_FINAL_INSTR = """\
## SHIFT REGISTER — FINAL PASS (Pioneer_B receives PLAN_B back after 2 external reviews)

You are Pioneer_B, original author of PLAN_B.

The [PREVIOUS NODE OUTPUT] contains ## PLAN_A [FINAL...] — Pioneer_A's finalized plan.
The [SOURCE DOCUMENT] contains all 3 original initial plans for context.
You have now seen PLAN_B reviewed by 2 other agents.

Produce the FINAL authoritative version of PLAN_B and append it below PLAN_A's final:

## PLAN_B [FINAL — Pioneer_B original author, after full shift cycle]

### Evolution Summary
[3-5 sentences: what changed from your original? What did reviewers improve,
 what did they miss, and what are you restoring or overriding and why?]

### Final Architecture
[The definitive, complete, deliverable-quality architecture description]

### Final Key Decisions
[Complete definitive decision list with full reasoning]

### Final Risks
[Honest, specific operational risk assessment]

### Final Confidence
[Float 0.0–1.0]

### Ready to Implement?
Yes / No — and exactly one sentence on what would need to change for "Yes"

---
Output: copy PLAN_A's [FINAL] section from the previous input EXACTLY AS-IS at the top,
then append your ## PLAN_B [FINAL...] section below it. Two sections total.\
"""

_S3C_FINAL_INSTR = """\
## SHIFT REGISTER — FINAL PASS (Pioneer_C receives PLAN_C back after 2 external reviews)

You are Pioneer_C, original author of PLAN_C.

The [PREVIOUS NODE OUTPUT] contains ## PLAN_A [FINAL...] and ## PLAN_B [FINAL...] —
the finalized plans from the two preceding authors.
The [SOURCE DOCUMENT] contains all 3 original initial plans for context.
You have now seen PLAN_C reviewed by 2 other agents.

Produce the FINAL authoritative version of PLAN_C and append it below the others:

## PLAN_C [FINAL — Pioneer_C original author, after full shift cycle]

### Evolution Summary
[3-5 sentences: what changed from your original? What did reviewers improve,
 what did they miss, and what are you restoring or overriding and why?]

### Final Architecture
[The definitive, complete, deliverable-quality architecture description]

### Final Key Decisions
[Complete definitive decision list with full reasoning]

### Final Risks
[Honest, specific operational risk assessment]

### Final Confidence
[Float 0.0–1.0]

### Ready to Implement?
Yes / No — and exactly one sentence on what would need to change for "Yes"

---
Output: copy BOTH PLAN_A [FINAL] AND PLAN_B [FINAL] from the previous input EXACTLY
AS-IS at the top, then append your ## PLAN_C [FINAL...] section below them. Three sections total.\
"""

_SYNTHESIZER_INSTR = """\
You are the Shift Register Synthesizer. You have received a compiled document
containing the 3 FINAL versions of PLAN_A, PLAN_B, and PLAN_C, each authored
by their original Pioneer after 2 external review cycles.

Extract each FINAL plan and produce a structured BriefPacket JSON.

Output ONLY a valid JSON object matching this exact schema (no markdown wrapping):
{
  "pattern": "shift_register",
  "job_id": "__JOB_ID_PLACEHOLDER__",
  "fired_at": "__NOW__",
  "completed_at": "__NOW__",
  "cost_usd": 0.0,
  "decision_surface": {
    "question": "Which implementation path should we pursue?",
    "options": [
      {
        "label": "Plan A — [one line: Pioneer_A's approach]",
        "agent": "Pioneer_A",
        "summary": "[3-4 sentences: the final evolved architecture]",
        "evolution": "[1-2 sentences: how this plan changed across shifts]",
        "risks": ["risk1", "risk2"],
        "confidence": 0.0,
        "ready_to_implement": true
      },
      {
        "label": "Plan B — [one line: Pioneer_B's approach]",
        "agent": "Pioneer_B",
        "summary": "[3-4 sentences]",
        "evolution": "[1-2 sentences]",
        "risks": ["risk1"],
        "confidence": 0.0,
        "ready_to_implement": false
      },
      {
        "label": "Plan C — [one line: Pioneer_C's approach]",
        "agent": "Pioneer_C",
        "summary": "[3-4 sentences]",
        "evolution": "[1-2 sentences]",
        "risks": ["risk1"],
        "confidence": 0.0,
        "ready_to_implement": false
      }
    ],
    "cross_pollination_summary": "[2-3 sentences on the most interesting ideas that migrated between plans]",
    "synthesizer_recommendation": "[Your recommendation and concise reasoning — 2-4 sentences]",
    "next_action_options": [
      "approve_plan_A",
      "approve_plan_B",
      "approve_plan_C",
      "merge_A_and_B",
      "merge_A_and_C",
      "merge_B_and_C",
      "request_deeper_shift",
      "cancel"
    ]
  },
  "session_context": null,
  "raw_synthesis": "",
  "pattern_artifacts": [],
  "error": ""
}
"""

_PASSTHROUGH_INSTR = (
    "Pass the input through unchanged. Do not modify or summarize. "
    "Output exactly what you received."
)

# ─────────────────────────────────────────────────────────────────────────────
# Pattern Registration
# ─────────────────────────────────────────────────────────────────────────────

register_pattern(PatternDefinition(
    name="shift_register",
    description=(
        "3-agent shift-register deliberation. Each agent independently authors a plan "
        "from a distinct philosophical lane (experimental / pragmatic / conservative), "
        "then all plans rotate through all agents for 3 refinement cycles. "
        "Returns 3 fully evolved, divergent plans + synthesizer recommendation. "
        "Fire before any significant architectural decision."
    ),
    estimated_cost_usd=0.25,
    required_surfaces=["TEXT"],
    has_human_gate=True,
    payload_template=(
        "## Shift Register Input\n\n"
        "**Problem Statement:**\n{problem}\n\n"
        "**Relevant Context / Constraints:**\n{context}\n\n"
        "**Non-Negotiables:**\n{constraints}\n\n"
        "**What Antigravity wants from the swarm:**\n{intent}"
    ),
    nodes=[
        # ── INGEST (pass-through to first init node) ─────────────────────────
        PatternNode(
            node_id="INGEST",
            agent_name="SR_Pioneer_A",
            instruction_override=_PASSTHROUGH_INSTR,
            next_node="INIT_A",
            temperature=0.1,
            model_override="gemini-2.5-flash",
        ),
        # ── INIT Phase ───────────────────────────────────────────────────────
        PatternNode(
            node_id="INIT_A",
            agent_name="SR_Pioneer_A",
            instruction_override=_INIT_INSTR.format(
                agent_id="Pioneer_A",
                plan_label="PLAN_A",
                lane_description="Creative Experimentalist — unconventional, forward-looking, data-first or event-driven",
            ),
            next_node="INIT_B",
            temperature=1.0,
            model_override="gemini-2.5-flash",
        ),
        PatternNode(
            node_id="INIT_B",
            agent_name="SR_Pioneer_B",
            instruction_override=_INIT_INSTR.format(
                agent_id="Pioneer_B",
                plan_label="PLAN_B",
                lane_description="Pragmatic Engineer — API-contract-first, deliverable, test-driven, dependency-minimal",
            ),
            next_node="INIT_C",
            temperature=1.0,
            model_override="gemini-2.5-flash",
        ),
        PatternNode(
            node_id="INIT_C",
            agent_name="SR_Pioneer_C",
            instruction_override=_INIT_INSTR.format(
                agent_id="Pioneer_C",
                plan_label="PLAN_C",
                lane_description="Systems Conservative — battle-tested patterns, monolith-first, defensive, operationally safe",
            ),
            next_node="COMPILE_INITS",
            temperature=1.0,
            model_override="gemini-2.5-flash",
        ),
        PatternNode(
            node_id="COMPILE_INITS",
            agent_name="SR_Pioneer_A",
            instruction_override=_COMPILE_INITS_INSTR,
            next_node="S1_A_TO_B",
            temperature=0.1,
            model_override="gemini-2.5-flash",
        ),
        # ── Shift Cycle 1 ────────────────────────────────────────────────────
        PatternNode(
            node_id="S1_A_TO_B",
            agent_name="SR_Pioneer_B",
            instruction_override=_SHIFT_INSTR.format(
                reviewer_id="Pioneer_B", plan_label="PLAN_A", cycle="1",
            ),
            next_node="S1_B_TO_C",
            temperature=1.0,
            model_override="gemini-2.5-flash",
        ),
        PatternNode(
            node_id="S1_B_TO_C",
            agent_name="SR_Pioneer_C",
            instruction_override=_SHIFT_INSTR.format(
                reviewer_id="Pioneer_C", plan_label="PLAN_B", cycle="1",
            ),
            next_node="S1_C_TO_A",
            temperature=1.0,
            model_override="gemini-2.5-flash",
        ),
        PatternNode(
            node_id="S1_C_TO_A",
            agent_name="SR_Pioneer_A",
            instruction_override=_SHIFT_INSTR.format(
                reviewer_id="Pioneer_A", plan_label="PLAN_C", cycle="1",
            ),
            next_node="S2_rA_TO_C",
            temperature=1.0,
            model_override="gemini-2.5-flash",
        ),
        # ── Shift Cycle 2 ────────────────────────────────────────────────────
        PatternNode(
            node_id="S2_rA_TO_C",
            agent_name="SR_Pioneer_C",
            instruction_override=_SHIFT_INSTR.format(
                reviewer_id="Pioneer_C", plan_label="PLAN_A", cycle="2",
            ),
            next_node="S2_rB_TO_A",
            temperature=1.0,
            model_override="gemini-2.5-flash",
        ),
        PatternNode(
            node_id="S2_rB_TO_A",
            agent_name="SR_Pioneer_A",
            instruction_override=_SHIFT_INSTR.format(
                reviewer_id="Pioneer_A", plan_label="PLAN_B", cycle="2",
            ),
            next_node="S2_rC_TO_B",
            temperature=1.0,
            model_override="gemini-2.5-flash",
        ),
        PatternNode(
            node_id="S2_rC_TO_B",
            agent_name="SR_Pioneer_B",
            instruction_override=_SHIFT_INSTR.format(
                reviewer_id="Pioneer_B", plan_label="PLAN_C", cycle="2",
            ),
            next_node="S3_rA_TO_A",
            temperature=1.0,
            model_override="gemini-2.5-flash",
        ),
        # ── Shift Cycle 3 — return to origin author ───────────────────────────
        PatternNode(
            node_id="S3_rA_TO_A",
            agent_name="SR_Pioneer_A",
            instruction_override=_FINAL_SHIFT_INSTR.format(
                agent_id="Pioneer_A", plan_label="PLAN_A",
            ),
            next_node="S3_rB_TO_B",
            temperature=0.9,
            model_override="gemini-2.5-flash",
        ),
        PatternNode(
            node_id="S3_rB_TO_B",
            agent_name="SR_Pioneer_B",
            instruction_override=_S3B_FINAL_INSTR,
            next_node="S3_rC_TO_C",
            temperature=0.9,
            model_override="gemini-2.5-flash",
        ),
        PatternNode(
            node_id="S3_rC_TO_C",
            agent_name="SR_Pioneer_C",
            instruction_override=_S3C_FINAL_INSTR,
            next_node="COMPILE_FINALS",
            temperature=0.9,
            model_override="gemini-2.5-flash",
        ),
        PatternNode(
            node_id="COMPILE_FINALS",
            agent_name="SR_Pioneer_A",
            instruction_override=_COMPILE_FINALS_INSTR,
            next_node="SYNTHESIZE",
            temperature=0.1,
            model_override="gemini-2.5-flash",
        ),
        # ── Synthesizer + Gate ────────────────────────────────────────────────
        PatternNode(
            node_id="SYNTHESIZE",
            agent_name="SR_Synthesizer",
            instruction_override=_SYNTHESIZER_INSTR,
            next_node="HUMAN_GATE",
            temperature=0.1,
            model_override="gemini-2.5-pro",
        ),
        PatternNode(
            node_id="HUMAN_GATE",
            agent_name="SR_Pioneer_A",
            instruction_override=_PASSTHROUGH_INSTR,
            next_node="MANUAL",
            temperature=0.1,
            model_override="gemini-2.5-flash-lite",
        ),
    ],
    agent_roster_entries=[
        {
            "Agent_Name": "SR_Pioneer_A",
            "Model": "gemini-2.5-flash",
            "Tools_Allowed": "none",
            "System_Prompt": _A_PERSONA,
        },
        {
            "Agent_Name": "SR_Pioneer_B",
            "Model": "gemini-2.5-flash",
            "Tools_Allowed": "none",
            "System_Prompt": _B_PERSONA,
        },
        {
            "Agent_Name": "SR_Pioneer_C",
            "Model": "gemini-2.5-flash",
            "Tools_Allowed": "none",
            "System_Prompt": _C_PERSONA,
        },
        {
            "Agent_Name": "SR_Synthesizer",
            "Model": "gemini-2.5-pro",
            "Tools_Allowed": "none",
            "System_Prompt": (
                "You are the final Synthesizer in a MACCREv2 shift-register pattern. "
                "Produce structured JSON output exactly as specified. "
                "Temperature=0.1 — deterministic, precise, no creative divergence. "
                "Extract the FINAL version of each plan from the accumulated context."
            ),
        },
    ],
))
