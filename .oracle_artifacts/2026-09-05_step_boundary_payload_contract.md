# 2026-09-05: The Step-Boundary Payload Contract — Requirement 34, Built and Unwired

**Plan task:** Era 3 tracker #1 (the remainder of the original #9)
**Oracle domain:** OrchestrationAndEngine

## Summary

The operator chose a **3b/3c hybrid** for what a step hands the next step: the unified
session ledger *is* the payload, with the immediate upstream output identified **inside**
it rather than passed as a second copy, bounded by a ceiling, with truncation beyond it.

Requirement 34 was written into the spec, its seven criteria written red as
`xfail(strict=True)`, and **six of the seven implemented**. The seventh is the wiring, and
it is deliberately still red.

## Files Modified

- `.kiro/specs/phase-6-13-multi-flow-lane/requirements.md` — Requirement 34 added (7
  criteria, 3 design notes, a stated limitation), traceability row added.
- `maccre_core/orchestration/payload_contract.py` — **new.** `compose_step_payload`,
  `describe_step_payload`, `distil_truncated_context`, `_bound_context`,
  `ACCOMPANYING_CONTEXT_CHAR_CEILING`, and the section/notice constants.
- `tests/test_topological_semantic_spec.py` — 7 Req 34 markers added; 6 removed after
  XPASS; **34.1 retained red on purpose**.
- `tests/test_payload_contract.py` — new, 31 tests.

## Function Signatures Added

```python
ACCOMPANYING_CONTEXT_CHAR_CEILING: int = 120_000

def compose_step_payload(
    session_context: str, upstream_node: str, source_document: str = "",
) -> str

def describe_step_payload(
    session_context: str, upstream_node: str, source_document: str = "",
) -> dict[str, Any]

def distil_truncated_context(removed: str) -> str | None   # always None — Era 4 seam
```

## State Contracts

Every function is pure. No shared mutable state, no broker handle, no `threading.Event`.
The module imports only `logging` and `typing`, so it cannot participate in an import
cycle and has nothing to lock.

| Object | Owner | Observers | Mutation Rights |
|--------|-------|-----------|-----------------|
| `session_context`, `source_document` (strings) | caller | the composer | **none** — immutable inputs |
| `ACCOMPANYING_CONTEXT_CHAR_CEILING` | this module | anything importing it | read-only constant |

## Architecture Decisions

### Why 3b rather than 3a, and it is a measured reason

3a — the session ledger accompanying the terminal output as its own section — was rejected
because **the ledger already contains the upstream output**. It is assembled from every
agent ledger in the job, so "terminal output **plus** the session ledger" sends the same
prose twice at every hop, and across a multi-step flow that is not linear growth.

3b identifies the upstream section *inside* the ledger. Lineage survives as an
**assertion** — a named node and a sentence pointing at its section — at a fraction of the
tokens. `test_the_upstream_prose_appears_exactly_once` is the assertion that keeps it
honest.

### The ceiling is in characters, and saying so is the point

There is no tokenizer in this repository. The only exact token count available is a
`countTokens` network call that is not on the execution path. A ceiling expressed in
*tokens* would therefore be a character count divided by a heuristic and **called** a token
count — a worse claim than the plain measurement.

**120,000 characters reuses a threshold the codebase already has.** `maccre_router`'s
context-cache heuristic already treats 120,000 characters as its large-context trigger.
Reusing it means there is **one** notion of "this context is big" in the system rather than
two free to drift — Principle 4 applied to a number instead of a data structure. At ~4
chars/token it lands near 30k tokens, an order of magnitude below the 200,000-token
long-context billing tier, so this contract cannot silently move a flow onto a higher input
*rate*. `test_it_stays_below_the_long_context_billing_tier` asserts that against
`_LONG_CTX_THRESHOLD` rather than a literal.

### Truncation says it truncated *and* that it did not distil

`TRUNCATION_NOTICE` is a module constant containing the phrase **"NOT distilled or
summarised"**, and it states how much was removed, out of what total, and against which
ceiling.

A payload merely cut while implying it had been summarised would be **Principle 3 inside
the one document the next agent reasons from** — the worst available place for a success
claim over work that did not happen. Making it a constant means the honesty cannot be
softened at one call site.

**Revert-to-red:** changing the notice to *"was distilled into a summary"* reddened two
tests — the real coverage and the spec marker — which is the right pair, because the spec
criterion and the implementation detail should both refuse it.

### The distillation seam returns `None`, and that is the implementation

`distil_truncated_context` is not a stub awaiting one line; `None` is the answer for Era 3.
Distillation is **an inference call per step boundary**, whose cost cannot be measured
today and whose value cannot be quantified until the payload manager daemon exists to say
what a smaller payload bought.

**It deliberately does not fall back to returning its input.** A seam that quietly handed
back the removed text would make "distilled" true by redefinition, and every message
describing the payload would go false at the same moment.
`test_it_does_not_fall_back_to_returning_its_input` pins that.

The call site is real rather than decorative: `compose_step_payload` *offers* the removed
text to the seam and branches on `None`. When Era 4 implements it, that is the line that
starts returning content, and the notice is what has to change with it.

### The newest end is kept, and the payload says which end went

The session ledger is assembled oldest-first, so the most recent turns are what a successor
most needs. Truncation that does not state which end it dropped leaves a reader unable to
tell an early-flow gap from a late-flow one, so the notice says *"the most recent turns
were kept and the oldest were dropped"*.

The cut prefers a **line boundary** within the retained window so the section does not open
mid-sentence, and falls back to a hard character cut when a single line exceeds the whole
ceiling — an unsplittable blob is not a reason to emit nothing, nor to exceed the ceiling.
Both are tested.

### The source-document section is omitted rather than emitted empty

A labelled heading over nothing is the defect shape found in the ledger's memory-pins
section the same day. `test_it_is_omitted_when_absent` guards it.

## Testing

`tests/test_payload_contract.py` — **31 tests** across eight groups: upstream identified
not duplicated; the source-document section; the ceiling (including the reuse claim and the
billing-tier bound, and that context at *exactly* the ceiling is not truncated); truncation
honesty; retention ordering (including the line-boundary preference and the unsplittable
blob); the distillation seam; the measurement report (including that kept + removed
accounts for the whole context); and the not-wired-yet guard.

Six `xfail(strict=True)` markers removed from `test_topological_semantic_spec.py` after all
six XPASSed. **One retained.**

### Gate run 2026-09-05

| Gate | Result |
|------|--------|
| `omni clean` | 13:12 — 295 bytecode files purged. |
| `omni qa` | **PASS** — whole project, 13:50. |
| `pytest tests -q` | **1085 passed, 11 xfailed, 0 failed** in 168.84s — 1096 collected. |
| `omni smoke` | **Not run.** Nothing on an execution path changed: this module has no importer. The last smoke passed after the most recent execution-path change (the ledger pins fix). |

Collected 1058 → 1096 reconciles exactly: +31 new tests, +7 markers of which 6 became
passes. `1085 = 1048 + 31 + 6`; xfailed `10 → 11`.

**One process note, because it cost half an hour.** A `pytest tests` run was launched in the
same message as `omni clean`, and the tool calls interleaved: clean purged `__pycache__` and
`.pytest_cache` **three seconds after** the suite started. The run stalled at 17% with a
process burning 720 s of CPU, and had to be terminated. The cache-clearing protocol names
this hazard; chaining the two commands is what created it. The re-run alone completed in
169 s. **Terminating the process was corroborated on three signals before acting** — PID,
creation time matching the launch, and the exact `-m pytest tests -q --tb=line -rE`
command line — per Principle 2, not on PID alone.

## Limits

- **Requirement 34.1 is not implemented, and its red marker is the record.** 34.1 requires
  `swarm_worker` to *delegate* to this module, which changes what a live flow sends.
  `test_the_worker_composes_through_the_one_seam` asserts `swarm_worker` references
  `compose_step_payload` and is still `xfail(strict=True)`, so it will break the gate the
  moment wiring lands and force deliberate removal.
- **The reason for stopping is a measurement one, not caution.** `payload_bytes` and
  per-node `INFERENCE_COST` attribution landed on 2026-09-05 (tracker #18) and **no live
  flow has run since**, so the *before* number for this contract **does not exist and
  cannot be obtained retroactively.** Once the contract changes, "what did it cost" is
  answerable only against a baseline taken first. A baseline run is an operator action.
- **Nothing calls this module.** "Requirement 34 is implemented" and "MACCRE composes
  payloads this way" are different claims and only the first holds.
  `TestItIsNotWiredYet` asserts the absence positively, so it fails when the claim stops
  being true.
- **The ceiling has not been validated against a real ledger.** 120,000 characters is
  justified by reuse and by the billing tier, not by evidence about what a receiving agent
  does better or worse with. The 68 KB ledger observed on a live run sits comfortably under
  it, meaning **truncation would not have fired on that run at all** — so the truncation
  path is entirely unexercised outside tests.
