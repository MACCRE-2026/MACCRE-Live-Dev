# 2026-09-05: CTRL_WAIT and Lanes That Never Merge (Requirements 29.3/29.4, 32)

## Summary

Two requirements, one idea from two ends. Requirement 29 says a scatter lane may end
without being collected; Requirement 32 says something may collect from a named lane
later, at a point the author picks. Neither is expressible while a merge is mandatory per
branch, which is what Requirement 19.4 demanded and this amendment superseded.

**The most valuable thing in this pass is not any of the six markers. It is that
`CTRL_WAIT` stopped silently succeeding.** `CTRL_WAIT` was declared in
`controlnode_registry` on 2026-09-04 but was absent from `DeterministicNodeType`, so
`_resolve_node_type` returned `None` and `execute_deterministic_node` fell through to
`_handle_anchor`: **the node passed its payload straight through and the task reported
`completed`.** That is Principle 3, and the `NODE_ALIASES` docstring in the same file names
this exact hazard for `CTRL_REVIEW` — nobody noticed `CTRL_WAIT` had inherited it the
moment it was declared.

## Files Modified

- `maccre_core/orchestration/topology_graph.py` — new Requirement 29 section:
  `GatherReachabilityReport`, `TerminalOutputSet`, `_normalise_strategy`,
  `validate_gather_reachability`, `terminal_outputs_for_step`. `ParadoxReport` gains
  `unresolvable_waiters`; `detect_temporal_paradox` now validates the **waiter keys**, not
  only the targets. `__all__` extended.
- `maccre_core/orchestration/deterministic_nodes.py` — `DeterministicNodeType.WAIT`;
  `TERMINAL_LANE_STATES`; `WaitOutcome`; `evaluate_wait`; `_handle_wait` registered in
  `_NODE_HANDLERS`. `_resolve_node_type` now actually sorts by prefix length. Imports
  `dataclass, field`, `Mapping, Sequence`, and `topology_graph`'s ref parser.
- `tests/test_topological_semantic_spec.py` — six markers removed after XPASS; the 29.4
  marker's **signature corrected** (see below); one new test added for the wait handler's
  refusal.
- `tests/test_ctrl_wait_and_ungathered_lanes.py` — **new. 60 tests, seven groups.**

## Function Signatures Added

```python
# topology_graph.py
@dataclass(frozen=True)
class GatherReachabilityReport:
    refused: bool
    unreachable_lanes: list[str]
    strategy: str
    def message(self) -> str: ...

@dataclass(frozen=True)
class TerminalOutputSet:
    pairs: list[tuple[str, str]]
    lanes_without_output: list[str]
    duplicated_paths: list[str]
    @property
    def complete(self) -> bool: ...
    @property
    def distinct(self) -> bool: ...
    def message(self) -> str: ...

def validate_gather_reachability(
    lanes: Mapping[str, Sequence[str]],
    gather_strategy: str,
    gather_nodes: Sequence[str],
    edges: Mapping[str, Sequence[str]] | None = None,
) -> GatherReachabilityReport: ...

def terminal_outputs_for_step(
    lanes: Mapping[str, Sequence[str]],
    recorded_outputs: Mapping[str, str],
    gather_strategy: str,
) -> TerminalOutputSet: ...

# deterministic_nodes.py
TERMINAL_LANE_STATES: frozenset[str]   # abandoned cancelled completed failed stalled timeout

@dataclass(frozen=True)
class WaitOutcome:
    status: str                 # "released" | "waiting" | "unsatisfiable" — never "timeout"
    decided_immediately: bool
    satisfied_by: list[str]
    outstanding: list[str]
    unsatisfiable_because: list[tuple[str, str]]
    def message(self) -> str: ...

def evaluate_wait(
    targets: Sequence[str],
    lane_states: Mapping[str, str],
    recorded_outputs: Mapping[str, str],
) -> WaitOutcome: ...

def _handle_wait(...) -> DeterministicNodeResult: ...   # always raises NotImplementedError
```

## State Contracts

| Object | Owner | Observers | Mutation Rights |
|--------|-------|-----------|-----------------|
| `lanes`, `recorded_outputs`, `lane_states`, `gather_nodes`, `edges` | caller | the functions above | **none** — read only |
| `known` / `wanted` / `reached` (locals) | the function | none | owner only, die with the call |
| all four dataclasses | the returning function | everyone | **frozen** |

Nothing added here takes a `threading.Event`, a `queue.Queue`, a connection or a broker.
`evaluate_wait` deliberately holds **no clock** — that is Requirement 32.5, not a style
choice.

## Architecture Decisions

### `evaluate_wait` decides from state, and holds no clock

Requirement 32.5 forbids discovering an unsatisfiable wait by wall clock. That is a lesson
already paid for: defect F3 was a hold nobody could release, which burned a 3600-second
budget and then reported `completed`. A wait whose target lane has already finished
without producing is knowable **now** — the queue already contains the fact.
`pause_owner_alive` established the pattern: ask, rather than wait and guess.

Three outcomes rather than two, because **"not yet" and "never" need different
responses**, and folding them together is precisely how F3 reported success over work that
never happened. `"unsatisfiable"` wins over `"waiting"`: once one target can never arrive,
waiting for the rest is waiting for a release that cannot come.

`TERMINAL_LANE_STATES` is an explicit allow-list rather than "anything that is not
running". A state this function has never heard of is treated as **live**, because reading
an unknown as *finished* would turn ignorance into a refusal — the same guessing 32.5
forbids, pointed the other way.

### `_handle_wait` raises, and that is the deliverable

The handler contract is `(node_id, payload_path, job_id, config, predecessor_payloads)`
and carries **no broker and no queue access**, so lane states and recorded outputs are not
reachable from inside a handler. `evaluate_wait` is complete and tested; supplying it with
live state needs a state provider on the dispatch contract, which changes how **every**
deterministic node is dispatched and is not done here.

So the handler refuses. An unevaluable wait must not pass its payload on, because the
node's entire purpose is that the payload should *not* move yet. The registry stays
`ComingSoon`, which remains the truth: **it has a guard, not a capability.**

Registering it also fixed the dispatch hole. Before: `CTRL_WAIT` → no type →
`_handle_anchor` → payload through, task `completed`. After: a loud
`NotImplementedError`, caught by `swarm_worker`'s cycle handler, which marks the task
failed. The register already carries two instances of this same hole, one of which claimed
a node named `FAILED`, **ran real inference on it**, and fed the output downstream.

### `validate_gather_reachability` refuses to answer without edges

"Does this lane reach a gather" is a question about paths, not names. With **no** gather
nodes the answer needs no edges — nothing can reach a node that does not exist, which is
the marker's case. With gather nodes present it is not derivable from names, so the
function **raises** rather than returning a plausible answer. This check gates launch, and
a wrong `reachable` would pass exactly the flow 19.4 existed to catch. A validator that
says it cannot tell is better than one that guesses.

### Requirement 29.4's marker signature was corrected, and the reason is the criterion

As authored the marker called:

```python
terminal_outputs_for_step(step_index=0, gather_strategy="Ungathered")
```

and asserted `len(outputs) > 1` with **distinct paths**. No lanes, no topology, no outputs
were passed in, and `topology_graph` is a pure module with no I/O and no global state — so
there was nowhere for two outputs to come from. **The only way to satisfy that call was to
fabricate them.** A test that can only pass against invented data is Principle 3 in test
form, and the invented paths would be Principle 2 besides.

The call now supplies the lanes and what the queue recorded. **The criterion is unchanged**
— each ungathered lane's terminal output recorded separately — and the signature is one
that can be satisfied by reading real state. This is the second marker correction this
phase; the first (31.3's `report.message`) was a calling convention, this one is a
signature that could not be honestly implemented. Both are recorded rather than quietly
edited, because editing a red marker to make it pass is a suspicious shape by default.

`TerminalOutputSet` reports rather than hides two conditions the naive list would lose:
a lane that recorded **nothing** (a silently shorter list reads as a smaller scatter), and
a path claimed by **more than one lane** — defect E1's exact signature, eight lanes all
naming `unified_session_ledger.md`. De-duplicating there would produce a set that looks
smaller but complete, which is how `Merged 8 sources` came to be literally true over one
file.

### The waits-key hole, recorded by Requirement 31 and closed here

`detect_temporal_paradox` validated wait *targets* and never the *keys*, so a malformed
waiter was `setdefault`-ed straight into the precedence graph. It could then appear in a
reported cycle **under a name no lane contained** — a refusal naming a node the author
cannot go and look at. Waiter keys now go through the same `_lane_fault` resolver, land in
a new `unresolvable_waiters` field (separate, because there is no target to blame), and are
**excluded from the graph** rather than added.

### `_resolve_node_type`'s longest-prefix comment made true

The comment claimed longest-prefix matching since Phase 4 while the loop iterated **enum
declaration order** and returned the first match. The two agreed only because no member's
value is a prefix of another's — luck, not design. Now sorted by length, and
`test_no_node_type_value_is_a_prefix_of_another` asserts the property mechanically, so a
future `CTRL_MERGE_ALL` cannot be quietly swallowed by `CTRL_MERGE`. Doctrine 5: a claim
about behaviour needs a test that fails when it goes false.

### Alternatives rejected

- **Fabricating two outputs to satisfy 29.4's marker as written.** The shortest path, and
  it would have made a Principle 3 violation into a passing test.
- **Widening the deterministic-node dispatch contract** to carry lane state, so
  `_handle_wait` could actually wait. That touches all 17 handlers and the worker's call
  site; it is the right eventual move and is not a side effect of Requirement 32's
  decision function.
- **Flipping the registry row to `active`.** The handler refuses; calling that active
  would be the third place in this codebase asserting a capability that does not exist.
- **Making `_handle_wait` a passthrough** so a flow containing one keeps running. That is
  the defect being fixed, restated as a feature.
- **Reading "not running" as terminal** in `evaluate_wait`. Fewer lines, and it converts
  every unrecognised state into a refusal.
- **De-duplicating `TerminalOutputSet.pairs`.** Produces a plausible smaller set and hides
  E1's signature.

## Testing

`tests/test_ctrl_wait_and_ungathered_lanes.py` — 60 tests:

| Group | Covers |
|---|---|
| `TestGatherReachability` | Ungathered never refused **first**, reachable-gather negative case, 29.3, chain reachability, cycle safety, refusal-without-edges, case-insensitive strategy, strategy names asserted against `GatherStrategy` |
| `TestTerminalOutputsForStep` | per-lane outputs, terminal is the **tail** of a chain, declared lane order, missing lane reported, empty path ≠ artifact, E1 duplicate surfaced, exact ref matching, Merge/Concat refusal |
| `TestEvaluateWaitReleases` | release, declared-order record (32.6), output beats lane state |
| `TestEvaluateWaitWaits` | waiting, the only non-immediate outcome, partial release, unknown state treated as live |
| `TestEvaluateWaitIsUnsatisfiable` | 32.4, never `timeout`/`completed`, 32.5 immediacy, **parameterised over every** `TERMINAL_LANE_STATES` member, absent lane, malformed target, no targets, precedence over waiting |
| `TestCtrlWaitNoLongerSilentlyNoOps` | type resolution incl. `_S0` suffix and `DET_` prefix, **the anchor passthrough is gone**, refusal names node + requirement, no-enum-value-is-a-prefix property |
| `TestParadoxDetectionValidatesTheWaiterToo` | bad waiter reported, named, in participants, **not a graph vertex**, and the negative case |

### Gate observed 2026-09-05

| Step | Result |
|---|---|
| `omni clean` | 15:46 — 297 bytecode files |
| `omni qa` | **PASS, whole project** 15:47:23 |
| `pytest tests` | **1213 collected / 1211 passed / 2 xfailed / 0 failed** — 175.76 s |
| `omni smoke` | **ALL CHECKS PASSED** — inference 0.9 s, $0.00 |

Reconciles exactly against 1152 / 1144 / 8: `1152 + 60 + 1 = 1213`;
`1144 + 60 + 1 + 6 = 1211`; xfailed `8 - 6 = 2`.

The 2 remaining red markers are Req 34.1 (payload wiring, blocked on an operator baseline
run) and Req 31.6 (`record_crossing` unwired).

## Limits of this work

- **Requirement 32 is partial and the unbuilt part is the part that waits.** 32.2 (release
  and expose the outputs) and 32.7 (a distinct TUI state) are not built. 32.1 is delivered
  as *dispatch that refuses*, not as a working node. `evaluate_wait` has no caller.
- **`validate_gather_reachability` and `terminal_outputs_for_step` have no caller either.**
  29.3's home is pre-flight validation; 29.4's is the step-boundary output capture.
- **29.5 is untouched** — "SHALL still reach a terminal session status, and SHALL NOT
  report `completed` while any lane holds an unresolved task". That is a flow-engine
  statement and belongs with the wiring.
- **No `CTRL_WAIT` node has ever been authored or executed.** The refusal path is proven by
  unit test, not by a live flow hitting it.

## OPEN FINDING — an intermittent full-suite hang, NOT root-caused

`tests/test_demand_overprovisioning.py::TestTheFixDoesNotCostConcurrency::
test_a_real_burst_still_reaches_full_width` **hung 2 of 5 full-suite runs today** while
passing 8/8 in 3.6 s in isolation and passing in the 3 runs that completed.

Observed on the two hangs: the module printed 4 of 8 dots and stopped; the worker process
held **8 threads** and ~650 MB; CPU climbed steadily (58.9 s → 117 s over 121 s of wall,
roughly half a core) with **zero test progress for over four minutes**. Not memory
pressure — 7 GB of 15.9 GB free at the time.

**What makes it a real finding rather than a slow test:** the code path has an explicit
ceiling. `run_until_drained` is called with `timeout_seconds=60` and its `finally` calls
`_join_all`, which is bounded at 30 s. That is a 90-second maximum, and it was exceeded
four times over. The stub worker's `execute_cycle` sleeps at most 0.02 s, so the usual
suspect — a long cycle that never checks `_shutdown` — does not explain it either.

**I did not find the cause.** A `faulthandler.dump_traceback_later` probe was set up
specifically to capture every thread's stack mid-hang; both instrumented runs completed
normally, so no stack was captured. The instrument is the right one and should be reused
the next time it hangs.

This module's own docstring already records that the defect it guards is **load-sensitive
by construction** and surfaced only under full-suite load, so an intermittent failure in
exactly this test is consistent with the pool's behaviour under load rather than with a
flaky assertion. **A concurrency test that hangs unboundedly instead of failing is the F3
shape again** — it would hold a CI run open indefinitely — and it should be given a hard
per-test bound so it fails loudly.

Recorded rather than fixed: it is not in Requirement 29/32's scope, the changes in this
pass are pure functions plus a handler that raises, and nothing here touches the pool.
