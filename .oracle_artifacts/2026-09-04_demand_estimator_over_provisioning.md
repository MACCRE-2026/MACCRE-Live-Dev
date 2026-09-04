# 2026-09-04: The Demand Estimator Ramped To The Ceiling For One Task

## Summary

The intermittent `test_linear_flow_stays_single_threaded` failure is **reproduced, root-caused,
fixed and guarded.** It was neither a flake nor slot-id reuse.

`_scale_to_demand` computed `target = active + ready`, which double-counts every live worker
that has not claimed yet: the worker is in `_active`, and the task it is about to take is still
`open`, so it is still counted in `ready`. Because `active` grows while `ready` does not, the
target grew by one on **every recheck interval** — a ramp toward `max_workers` for a single
task, bounded only by the ceiling.

Measured on a single-task queue with construction slower than the recheck interval:

| Metric | Before | After |
|---|---|---|
| `workers_spawned` | **5** | 1 |
| `workers_that_never_worked` | **4** | 0 |
| claim attempts for 1 task | **11** | 3 |
| slots that executed | `[0]` | `[0]` |

Decision record before the fix, as `(active_before, ready, is_fresh, target)`:

```
(0, 1, True, 1)
(1, 1, True, 2)   <-- double count
(2, 1, True, 3)   <-- double count
(3, 1, True, 4)   <-- double count
(4, 1, True, 5)   <-- double count
```

**This is defect F2's construction storm reached by a different route.** F2 was *paused, so
demand stays high, so respawn*; this is *unclaimed, so demand stays high, so spawn more*. F2's
fix — the scaler returning early while paused — could not have caught this and did not.

## Files Modified

- `maccre_core/orchestration/swarm_pool.py`
- `tests/test_demand_overprovisioning.py` — new, 8 tests

## Function Signatures Added/Changed

```python
# module scope
_MAX_SPAWN_DECISIONS = 64          # bound on the diagnostic record

# PoolResult — new fields
workers_that_never_worked: int = 0
spawn_decisions: list[tuple[int, int | None, bool, int]] = field(default_factory=list)

# DynamicSwarmPool — new
def _unclaimed_worker_count(self) -> int: ...   # live workers that have not executed a node
```

`_scale_to_demand`'s target calculation changed from
`min(max_workers, max(1, active + ready))` to
`min(max_workers, max(1, active + max(0, ready - unclaimed)))`.

No public signature changed. `PoolResult.peak_concurrency` keeps its value and its name; only
its docstring was corrected — see *Architecture Decisions*.

## State Contracts

| Object | Owner | Observers | Mutation Rights |
|---|---|---|---|
| `_active` | `DynamicSwarmPool` | — | Pool, under `_lock` |
| `_worked_slots` | `DynamicSwarmPool` | — | Pool, under `_lock`. **New.** Added on `WORKED`, discarded on retire so a recycled slot starts unclaimed |
| `_workers_that_never_worked` | `DynamicSwarmPool` | — | Pool, under `_lock`. Incremented in `_worker_loop`'s `finally` |
| `_spawn_decisions` | `DynamicSwarmPool` | — | Pool, under `_lock`. Bounded at `_MAX_SPAWN_DECISIONS` |
| `pause_event` / `stop_event` | TUI / `execute_flow` | pool, workers | **Unchanged — observer only.** Nothing in this change reads or writes either differently |

`_worked_slots` is discarded per slot on retirement. Without that, a recycled slot would credit
its new worker with the previous one's claim, and the subtraction would under-provision instead
of over-provisioning — the same defect with the sign flipped.

## Architecture Decisions

**Instrument before fixing.** The register entry had this as *observed, not reproduced*, and
explicitly *not distinguished from slot-id reuse*. Principle 7 says the first task is
reproduction and the size is unknown until it completes — so the first change was
`workers_that_never_worked` and `spawn_decisions`, not a fix. That ordering is what turned "one
spare thread, sometimes" into "five workers for one task, deterministically".

**`workers_that_never_worked` counts worker *instances*, not slots.** This is what separates the
defect from slot-id reuse: a recycled slot handed to a worker that claims never registers, while
a fresh worker that claims nothing always does. Counting distinct slot ids — which is what the
failing test did — cannot make that distinction.

**Subtract the unclaimed rather than abandon `active + ready`.** The original formula exists for
a measured reason recorded in its docstring: using `ready` alone left an 8-lane scatter settled
at 7, because the estimator counts *open* tasks and a worker busy on lane 1 is not spare
capacity. The subtraction preserves that and removes only the double-count.
*Alternatives rejected:* `max(active, ready)` re-introduces the off-by-one on scatter width;
capping the pool at 1 for linear flows requires the pool to know the flow's shape, which it
deliberately does not; and lengthening `demand_recheck_seconds` would only widen the window the
defect needs, not close it.

**`PoolResult.peak_concurrency` was left measuring what it measures, and its docstring
corrected.** It documented itself as workers *executing nodes* and has always been
`max(len(_active))`, counted from `_spawn` — before the thread starts, before the worker exists,
before any claim. *Alternative rejected:* silently redefining it. The number is quoted in four
artifacts and a live run log, and a published metric that changes meaning without notice is
worse than one that is correctly labelled. A true measurement needs interval overlap and is
recorded as its own register entry.

**The 8-lane width claim is unaffected**, and this was verified rather than assumed:
`tests/test_scatter_concurrency.py` uses `threading.Barrier(8)`, which **deadlocks** rather than
degrading if the pool cannot get eight lanes in flight simultaneously. It passes.

**Over-provisioning was never double execution.** Asserted separately, because "the pool opened
five threads for one task" sounds like a correctness defect and is not one — the atomic claim
was always the authority and the losers retired. Conflating the two would have misprioritised
the fix and probably produced a much larger one.

## Testing

`tests/test_demand_overprovisioning.py`, 8 tests in five classes.

The reproduction is **forced, not waited for**: `SlowToStartWorker` delays in `__init__`, not in
`execute_cycle`, because the defect is about the gap between a slot being reserved and its worker
claiming — in production that gap is a `TopologyEngine` plus a `LocalMessageBroker` being built.
A delay in `execute_cycle` models a slow *node* and does not reproduce this at all.

**The most important class is `TestTheFixDoesNotCostConcurrency`.** Capping the pool at one
worker would satisfy every guard on the defect and destroy the entire Phase 6.12 deliverable, so
two tests assert that a genuine 8-task burst still reaches width and that work arriving *after* a
claim still scales the pool up.

`test_no_decision_double_counts_an_unclaimed_worker` asserts the *cause* is gone rather than the
symptom, by checking the decision record. A future change that masks the arithmetic while
reintroducing it still fails there.

**Gate, all observed 2026-09-04:**

```
omni clean   bytecode + cache purge                        05:59
omni qa      PASS, whole project                           06:14
pytest       792 collected / 792 passed, 186.65s           06:18
pytest       792 collected / 792 passed, 187.98s  (repeat) 11:05
omni smoke   ALL CHECKS PASSED                             06:20
targeted     167 passed — test_scatter_concurrency +
             test_swarm_pool + test_flow_pool_integration   06:10
```

`omni smoke` was run because `swarm_pool` is on an execution path.

**Not verified.** No live 8-lane scatter has been run since this change. The width proof is
deterministic and the smoke test is single-node, but neither is a live multi-lane run — which is
precisely the combination that was green while six real defects sat in this path. **UT-1 test 3
and UT-0 remain the proof.**

Also unproven: that this was the *only* cause of the observed failure. It is a sufficient
explanation, it is reproduced, and the fix holds across two full-suite runs — but the original
failure occurred once in six runs, so absence of recurrence is weak evidence on its own. The
decision record now makes a recurrence diagnosable rather than mysterious, which is the more
durable outcome.

**Consequence for 4.99: UT-0 is unblocked.** It was blocked because the demand estimator is the
component UT-0 exists to measure and it held an unexplained non-determinism. A baseline taken
after this is measuring a pool that behaves the same way twice.
