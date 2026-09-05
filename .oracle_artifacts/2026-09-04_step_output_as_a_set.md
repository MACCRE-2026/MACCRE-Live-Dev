# 2026-09-04: A Step's Output Is a Set — Requirement 30, with Requirement 29's Enum

**Plan task:** Era 3 tracker #8
**Requirements:** 30 (all six criteria), plus 29.2 and 29.6 pulled forward
**Oracle domain:** OrchestrationAndEngine

## Summary

A step used to produce *an artifact*. That was true only while every step had one
endpoint, and it stopped being true the moment Requirement 29 allowed a scatter to leave
its lanes ungathered. Requirement 30 makes the multi-output case **normal** and moves the
error from "there are several" to **"something chose between them without being told to"**.

## Files Modified

- `maccre_core/orchestration/deterministic_nodes.py` — added `GatherStrategy` enum
  (Req 29.2), beside `DeterministicNodeType`.
- `maccre_core/orchestration/flow_engine.py` — added `DECLARED_TOPOLOGY_POSITION`,
  `StepOutputSet`, `resolve_gather_strategy` (Req 29.6),
  `step_declares_a_gather_strategy`, and `FlowRunner._collect_step_output_set`.
  Rewired `_capture_step_output`; added `self._step_output_sets` to `FlowRunner.__init__`;
  all three call sites now pass `step.config`.
- `tests/test_step_output_set.py` — new, 44 tests.
- `tests/test_topological_semantic_spec.py` — 6 `xfail(strict=True)` markers removed.

## Function Signatures Added/Changed

```python
class GatherStrategy(Enum):          # deterministic_nodes.py
    MERGE = "Merge"
    CONCAT = "Concat"
    UNGATHERED = "Ungathered"

@dataclass
class StepOutputSet:                 # flow_engine.py
    pairs: list[tuple[str, str]]     # (node_id, output_path), declared order
    @property
    def ordered_by(self) -> str      # always DECLARED_TOPOLOGY_POSITION
    def is_empty(self) -> bool
    def __len__(self) -> int
    def nodes(self) -> list[str]
    def paths(self) -> list[str]
    def single(self) -> str          # raises on 0 and on >1, with distinct messages
    def substitute_guess(self) -> None
    def as_record(self) -> dict[str, Any]

def resolve_gather_strategy(step_config: dict[str, Any] | None) -> str
def step_declares_a_gather_strategy(topology_rows: list[dict[str, Any]]) -> bool

# CHANGED — gained an optional trailing parameter, so no existing caller breaks
def _capture_step_output(
    self, job_id, topology_rows, step_index, broker,
    step_config: dict[str, Any] | None = None,
) -> str | None

# NEW
def _collect_step_output_set(self, job_id, topology_rows, step_index, broker) -> StepOutputSet
```

## State Contracts

| Object | Owner | Observers | Mutation Rights |
|--------|-------|-----------|-----------------|
| `FlowRunner._step_output_sets` | `FlowRunner.__init__` | anything holding the runner | **owner only**, written solely in `_capture_step_output` |
| `StepOutputSet.pairs` | the `StepOutputSet` | callers via `nodes()`/`paths()`/`as_record()` | copied on construction, never written after |
| `topology_rows` | caller | `_collect_step_output_set`, `step_declares_a_gather_strategy` | **none** — read only |

`StepOutputSet.__post_init__` copies the incoming list rather than aliasing it. The Oracle
principles name mutating a caller's list as a bug pattern, and this object exists to be a
stable record of what a step produced — a later reorder of the caller's list must not
rewrite history. `test_the_set_does_not_alias_the_callers_list` pins it.

No `threading.Event`, `queue.Queue` or broker handle is taken by any of the new
functions. `_collect_step_output_set` reads the broker through
`get_completed_payload_paths` only.

## Architecture Decisions

### Requirement 29's enum arrived with Requirement 30, and only two pieces of it

30.3 and 30.4 are both phrased *"AND the step's Gather Strategy is ..."*. There is no
honest way to implement 30.4 — the clause the whole amendment turns on — without the
thing it branches on. So `GatherStrategy` (29.2) and `resolve_gather_strategy`'s `Merge`
default (29.6) came forward with it.

Deliberately **not** built: 29.3's launch-time `validate_gather_reachability` and 29.4's
`terminal_outputs_for_step`. Both remain `xfail(strict=True)` for tracker #11. Pulling
forward the two pieces 30 depends on and stopping there keeps the boundary legible; half
building the validator would have left a mechanism nobody could tell was incomplete.

### `ordered_by` is a property, not a field

As a field with a default it could be constructed as
`StepOutputSet(pairs=..., ordered_by="completion_time")` — a caller able to *state* an
ordering it did not perform. That is the shape of every label defect in the register
(`is_stalled = True` for a timeout; `payload_path` naming the shared ledger). The ordering
is a property of how the object is built, so it is not the constructor's to declare.
`test_the_ordering_cannot_be_declared_by_the_caller` asserts the `TypeError`.

### The empty case and the crowded case fail differently

`single()` raises on both, with messages that do not overlap: `"no output"` for empty,
`"more than one"` for several. "Several outputs and no instruction" is an authoring
question; "no output at all" is a run failure. They call for different responses, and a
caller matching on the message has to be able to tell them apart — folding them into one
error would be the ambiguous-terminal-state problem in miniature.

### `substitute_guess()` is a canary, and is documented as one

It always returns `None`. That looks like a method that does nothing, and it is closer to
a tripwire. Defect E2's whole failure mode was a helper that, asked for a step's output,
produced a *plausible* one rather than nothing. A no-fallback rule is otherwise an
absence, and an absence cannot be asserted. Naming it means a future change that adds a
fallback has to come through here and redden `test_there_is_no_substitute`, rather than
arriving as an innocuous-looking default.

### An unrecognised Gather Strategy is refused, never defaulted

`resolve_gather_strategy` returns `Merge` for **absent or blank** and raises `ValueError`
for a declared-but-unrecognised value. Quietly treating `"ungatherd"` as `Merge` would
gather lanes the author explicitly asked to be left alone — the approximately-correct
value in its most expensive form, because the wrong behaviour is indistinguishable from
the right one until someone reads the merged document.

Resolution is case-insensitive. The authoring surface is a text field, and casing is not
a declaration.

`_capture_step_output` catches that `ValueError` and refuses the step output rather than
letting it escape. A resolver that raises is right; a running flow dying on an
authoring typo at step 4 is not. The launch-time refusal this really deserves is Req
29.3's job.

### A step with no scatter has no Gather Strategy — the boundary, and why it is one

This was the decision that took the longest and is the one most likely to be revisited.

`resolve_gather_strategy` defaults to `Merge` (Req 29.6, so saved MacroNodes keep their
behaviour). Applied unconditionally, that default reaches a **plain divergent DAG** —
`ROOT → L1,L2`, both terminating — which has two endpoints and no lanes. It would then
resolve to `Merge`, find no merge node, and be refused.

That would change the behaviour of topologies Requirement 30 says nothing about, *in the
name of implementing Requirement 30*. So `step_declares_a_gather_strategy` gates the
whole strategy branch on the presence of a `CTRL_SCATTER`: a Gather Strategy is a
scatter's declaration about its own lanes, and where there are no lanes there is nothing
to declare.

For the plain divergent DAG the pre-amendment behaviour therefore stands unchanged —
first in declared order, with the warning that has always said it is *a choice, not a
fact*. The two existing tests in `tests/test_payload_lineage.py` that pin this
(`test_divergent_terminals_resolve_by_declared_order`,
`test_divergent_terminals_are_reported`) still pass **untouched**, which is the evidence
that this change did not reach behaviour it was not meant to reach.

`TestAPlainDivergentDagIsUntouched` guards the boundary from the other side. If extending
30.4's refusal to plain divergent DAGs becomes the right call, it should arrive as a spec
change that reddens that class deliberately, not as a side effect. **Raised as a register
entry rather than decided here.**

Detection is by prefix, matching how `_resolve_node_type` classifies control nodes, so
`CTRL_SCATTER_WIDE` counts.

### `Ungathered` with one lane is still the degenerate case

`Ungathered` does not mean "refuse always". One lane has one output, so there is nothing
to choose between and nothing to refuse. Refusing there would break a legitimate one-lane
scatter, which is a real authoring shape (a scatter of width one is how a flow gets a
tether scope without fanning out).

### `Merge`/`Concat` with no gather output refuses; with two, also refuses

Declared `Merge`, nothing merged, several lane outputs sitting there — that is the
unreachable gather 29.3 exists to refuse *before* launch. Reached at runtime, refusing is
still the answer, because the alternative is handing the next step one lane of several.
Two gather nodes with output is likewise an authoring error and not a choice for the
engine to make.

### `_capture_step_output` still returns `str | None`, and `None` now means more things

The set is built and recorded; what the method returns is the narrower answer the current
payload contract can carry — *which single path does the next step read?* — and
increasingly a refusal to answer it. `None` now covers five conditions, each logged with
which one it was:

1. the topology declares no terminal node (WARNING),
2. no terminal recorded an output (ERROR),
3. `Ungathered` with several outputs (ERROR — Req 30.4),
4. a declared gather that produced nothing, or two that did (ERROR),
5. an unresolvable strategy declaration (ERROR).

Recorded as an accepted cost rather than glossed: the callers treat `None` uniformly as
"carry the previous payload forward", which is the same conservative behaviour as before,
and the distinction lives only in the log. Handing the *set* to the next step is the
payload contract's job — tracker #9 — and is not built. Widening the return type here
before that design exists would have produced the second representation the payload work
is supposed to eliminate.

## Testing

`tests/test_step_output_set.py` — **44 tests**, in eight groups:

- **The ordered set** (Req 30.1) — ordering constant, ordering not caller-declarable,
  order preserved, caller's list not aliased, length.
- **The degenerate case** (30.2) — one output returned; E2's 426 KB merge reached through
  the same call as everything else.
- **Refusal to choose** (30.4) — two, eight, candidates named, and the empty-versus-
  crowded message split.
- **The empty set** (30.5) — `is_empty`, and the `substitute_guess` canary.
- **The audit record** (30.6) — ordering stated, every pair in order, empty records as
  empty rather than absent.
- **`GatherStrategy`** (29.2) — the three values exist.
- **`resolve_gather_strategy`** (29.6) — pre-amendment default, `None`/`{}`/blank,
  round-trip per strategy, case-insensitivity, refusal to default an unrecognised value,
  refusal names the options.
- **When a strategy applies** — scatter yes, linear no, divergent-without-scatter no,
  prefix match, empty rows no.
- **Through the engine** — the set recorded for a single terminal and for a refusal, in
  declared order against reversed completion; `Ungathered` hands nothing forward and logs
  at ERROR; one-lane `Ungathered` still resolves; `Merge` and `Concat` pass the gather's
  output; unreachable gather and unresolvable strategy both refuse; and the plain
  divergent DAG untouched, including when handed a `Merge` config.

### Revert-to-red proof

The `Ungathered` branch was temporarily changed to `return output_set.paths()[0]` and the
file re-run. Two tests went red with the production signature —
`AssertionError: assert '/dc/Agent1_S0.md' is None` — one lane of eight wearing the whole
step's name. Probe removed and confirmed absent by grep before re-running green.

**A finding from that probe worth keeping.**
`test_the_refusal_is_logged_at_error_with_the_count` **still passed** under the probe,
because the ERROR line was still emitted while the value was returned anyway. That is the
log-says-one-thing-code-does-another shape, and it means the log assertion alone is not
evidence of the refusal. The two value assertions are what carry the claim; the log test
covers a different property (that the refusal is *visible*), and it is worth knowing it
cannot substitute.

### Gate run 2026-09-04

| Gate | Result |
|------|--------|
| `omni clean` | 21:24 — zombie hunt: nothing to terminate; 284 bytecode files purged. |
| `omni qa` | **PASS** — Ruff + Pyright, whole project, 21:25. |
| `pytest tests -q` | **903 passed, 10 xfailed, 0 failed** in 205.34s — 913 collected. |
| `omni smoke` | **ALL CHECKS PASSED** — inference 0.9s, $0.00. |

Collected 869 → 913 reconciles exactly: +44 new tests. Six xfail markers removed
(16 → 10), so `903 = 853 + 6 + 44`.

`omni smoke` was run because `flow_engine` and `deterministic_nodes` are both on
execution paths.

## Limits of this work

- **No live run.** Static analysis, 913 collected tests and a single-node smoke are not a
  live multi-lane run — the exact combination that was green while six real defects sat in
  this path. `Ungathered` has never executed against a real scatter.
- **Nothing authors a Gather Strategy.** `step_config["gather_strategy"]` has **no
  producer**: the TUI does not offer the field, so every declaration in the tests is
  hand-constructed and every real flow today resolves to the `Merge` default. The
  authoring surface was deliberately left unspecified by the amendment (it belongs with
  the open Era 2 authoring-ownership decision).
- **Therefore the runtime behaviour of every existing topology is unchanged.** That is
  intended, and it also means this change is unproven where it matters most.
- **Req 30.6's audit trail is in-process plus the log.** `_step_output_sets` survives to
  the next step boundary and for the whole run; `as_record()` is logged at INFO so it
  reaches `maccre_system.log`. It is **not** persisted to the queue or telemetry, so
  "auditable after the run" holds only as far as the log does.
- **The plain-divergent-DAG boundary is a decision, not a discovery.** It is defensible
  and it is guarded by a test, but it is the thing most likely to want revisiting, and it
  is raised as a register entry for that reason.
