# 2026-09-04: Pre-Launch Validation — Temporal Paradox Detection and Total-Sum Readout

**Plan task:** Era 3 tracker #7
**Requirement:** Spec Requirement 33 (added by the 2026-09-04 spec amendment, commit `96b50fd`)
**Oracle domain:** OrchestrationAndEngine

## Summary

Requirement 33 asked for two things the operator wanted before pressing launch: a refusal
when the configured waits describe an ordering no execution can satisfy, and a *total-sum*
readout of the whole Active Flow rather than a node-by-node view.

Both are now implemented and covered. The five `xfail(strict=True)` markers that stood in
for Requirement 33 in `tests/test_topological_semantic_spec.py` were removed — all five
XPASSed, which is the mechanism working as intended: a strict xfail that starts passing
becomes a failure, so the markers could not be left behind by accident.

## Files Modified

- `maccre_core/orchestration/topology_graph.py` — added `ParadoxReport`, `_qualify`,
  `_find_cycles`, `detect_temporal_paradox`. Import of `dataclass, field` added.
- `maccre_core/orchestration/flow_engine.py` — added `total_sum_readout`, inserted
  immediately before `class FlowStep`.
- `tests/test_topological_semantic_spec.py` — 5 `xfail(strict=True)` markers removed.
- `tests/test_prelaunch_validation.py` — new, 26 tests.

## Function Signatures Added

```python
@dataclass
class ParadoxReport:
    paradox: bool
    cycles: list[list[str]]
    unresolvable: list[tuple[str, str, str]]   # (waiter, target, reason)
    participants: list[str]

def detect_temporal_paradox(
    lanes: Mapping[str, Sequence[str]],
    waits: Mapping[str, Sequence[str]],
) -> ParadoxReport:
    """Refuse a configuration whose waits no execution order can satisfy."""

def total_sum_readout(
    topology_rows: list[dict[str, Any]],
    step_index: int,
    max_workers: int | None = None,
) -> dict[str, Any]:
    """Describe the whole Active Flow before launch. Requirement 33.4-33.7."""
```

## State Contracts

Neither function touches shared mutable state. Both are pure: they read the arguments
handed to them and return a new object.

| Object | Owner | Observers | Mutation Rights |
|--------|-------|-----------|-----------------|
| `lanes`, `waits` (mappings) | caller | `detect_temporal_paradox` | **none** — read only, never mutated |
| `topology_rows` | caller (`FlowRunner._hydrate_topology`) | `total_sum_readout` | **none** — copied via `list(...)` on entry |
| `precedence` graph | `detect_temporal_paradox` local | none | owner only, dies with the call |

No `threading.Event`, `queue.Queue` or broker handle is taken by either function, so the
observer rule in the Oracle principles has nothing to bind to here. That is deliberate:
pre-launch validation runs before any of the concurrency machinery is constructed.

## Architecture Decisions

### One precedence-graph cycle check, not four detectors

Requirement 33.2 enumerates four conditions. Two of them are the same thing once both
kinds of ordering constraint are written as edges:

```
sequence edge   node[i] --> node[i+1]      execution within a lane is ordered
wait edge       target  --> waiter         a waiter cannot precede its target
```

A lane `[W, B]` where `W` waits on `B` yields `W -> B` and `B -> W`: a two-node cycle.
Two lanes waiting on each other yield the same shape with no sequence edges. One cycle
detection covers both, **and covers three-lane and longer cycles nobody enumerated** —
which is the argument for deriving the check from the model rather than from the list of
examples in the requirement.

*Rejected:* four special-case detectors matching the four enumerated conditions. It would
have passed every test written from the requirement text and missed the shapes the
requirement did not think of.

The remaining two conditions are reference-validity errors, not ordering contradictions,
and are reported in a separate `unresolvable` field so a refusal can say which kind of
wrong the topology is.

### `_find_cycles` is iterative with an explicit stack

*Rejected:* recursive DFS, which is shorter. This validator runs on operator input
immediately before launch. A validator that raises `RecursionError` on a pathological
topology is worse than the defect it exists to catch — it converts "your config is
unsatisfiable" into "the tool crashed", and the operator learns nothing.

### An unresolvable target is excluded from the graph, not graphed against nothing

A wait naming a node that does not exist cannot be ordered. Adding the edge anyway would
invent a graph node for a nonexistent target and could manufacture a phantom cycle —
Principle 2, an approximately-correct identifier acted upon. The pair is recorded in
`unresolvable` with a reason string and skipped when edges are built.

### `participants` is an order-preserving de-dup, not a set

A set makes the refusal message order non-deterministic, which makes both the operator's
reading experience and the tests unstable. Cheap to do properly.

### The readout's `source` is **checked**, not asserted

Requirement 33.6 says the readout derives from the hydrated topology, never the authoring
surface. Hardcoding `source = "hydrated_topology"` would have made 33.6 decorative. The
function tests whether every `Node_ID` carries the `_S{step_index}` suffix that
`FlowRunner._hydrate_topology` applies, and reports `"unhydrated_topology_rows"` plus a
`logger.warning` when it does not.

This is Principle 4 in the one place whose whole job is to tell the operator the truth
before they commit. The TUI once built node ids as `NAME_{i}` while the engine built
`NAME_S{i}`; a readout generated from what was *drawn* would be a second representation
of the topology, free to drift from the one that executes.

### Unbuilt fields are empty, not fabricated

`gather_strategies={}`, `waits={}`, `cross_lane_routes=[]`. Gather Strategy (Req 29),
cross-lane routes (Req 31) and `CTRL_WAIT` targets (Req 32) are specified and unbuilt.
The keys exist so consumers have a stable shape; a plausible-looking default would be
Principle 3 in a readout — describing work that has not happened.

### `expected_peak_concurrency` follows the pool's request, not the lane count

This one was found by a failing test rather than by design, and is worth recording as
such.

The first implementation computed `resolve_scatter_cap(lane_count)`. The test asserted a
64-lane topology could not expect more than 8-way concurrency, and it failed: the call
returned **12**. Both sides were wrong in different ways, and reading the engine settled
it. `FlowRunner.execute_step` passes `max_workers=len(scatter_agents)` when agents are
slotted and `None` otherwise, and `DynamicSwarmPool` then clamps *that* through
`resolve_scatter_cap`. So:

- an unconfigured step peaks at `MAX_SCATTER_AGENTS` (8), **not** `SCATTER_HARD_CAP` (12);
- the lane count was never the pool's input, so resolving it as one was a second
  derivation of the sizing rule — Principle 4 again, in a readout.

A 64-lane topology would therefore have read as "12-way" while the run opened 8 threads:
a readout over-promising concurrency the engine was never going to deliver, in the one
artifact the operator consults *instead of* watching the run.

Fixed by giving the readout the same input the pool gets:

```python
min(lane_count, resolve_scatter_cap(max_workers)) if lane_count else 1
```

Bounded twice over — you cannot run more lanes at once than exist, and the pool will not
open more threads than `resolve_scatter_cap` allows. The test now asserts against the
imported constants rather than literals, so a change to either ceiling cannot leave it
passing for the wrong reason.

*Rejected:* keeping `resolve_scatter_cap(lane_count)` and relaxing the test to
`<= SCATTER_HARD_CAP`. It would have gone green while leaving the over-promise in place.

### A linear flow reports `lane_count == 0` and a peak of 1

An absent `Tether_ID` is not an error — a linear flow has one implicit lane. Reporting
`lane_count == 0` rather than 1 distinguishes "this flow has no lanes" from "this flow
has one lane", which matters because the second is a scatter of width one and the first
is not a scatter at all.

## Testing

`tests/test_prelaunch_validation.py` — 26 tests, in four groups:

- **Paradox detection catches real shapes** — the satisfiable negative case first (a
  detector that fires on everything is useless), same-lane backwards wait, two-lane
  mutual wait, three-lane cycle, self-wait.
- **Reference validity** — target in a lane the topology never spawns, target absent
  from an existing lane, target that is not tether-qualified, and the reason strings.
- **Refusal quality** — deterministic participant ordering, both failure kinds reported
  together, participants non-empty whenever `paradox` is True.
- **Total-sum readout** — every documented key always present; `source` checked against
  the suffix (including partial hydration and wrong step index); lanes and nodes-per-lane
  from `Tether_ID`; the four `expected_peak_concurrency` bounds; unbuilt fields empty.

`tests/test_topological_semantic_spec.py` — 5 `xfail(strict=True)` markers removed after
all five XPASSed.

### Gate run 2026-09-04

| Gate | Result |
|------|--------|
| `omni clean` | Zombie hunt: nothing to terminate. Purged 55 bytecode files, 2 caches. |
| `omni qa` | **PASS** — Ruff + Pyright, whole project, 20:17. |
| `pytest tests -q` | **853 passed, 16 xfailed, 0 failed** — 869 collected (was 843). |
| `omni smoke` | **ALL CHECKS PASSED** — inference 0.9s, $0.00. |

Collected count moved 843 -> 869: +26 new tests, and 5 previously-xfailed spec tests
moved into the passing count (21 xfailed -> 16). `853 = 822 + 5 + 26`.

`omni smoke` was run because both modified files sit on execution paths.

## Limits of this work

- **Nothing calls either function yet.** `detect_temporal_paradox` and
  `total_sum_readout` are implemented, covered and unwired: no launch path invokes them,
  so no operator currently sees a refusal or a readout. The wiring is tracker #13 (TUI)
  and the `CTRL_WAIT` work in tracker #11. Stating this plainly because "Requirement 33
  is implemented" and "MACCRE refuses paradoxical configs at launch" are different
  claims and only the first is true today.
- **`waits` has no producer.** The `waits` argument is shaped for `CTRL_WAIT` config,
  and `CTRL_WAIT` is a `ComingSoon` registry row. Every wait in the tests is
  hand-constructed.
- **`paradox=False` is a statement about the two inputs**, not a guarantee the flow will
  succeed. It says no ordering contradiction was found among the lanes and waits given.
