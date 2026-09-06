# 2026-09-05: The Gather Gate Reads Through `lane_group` (task 4c-1)

## Summary

`local_broker` held **three** copies of `AND tether_id = ?` — the gather gate, the merge's
input collector, and the tether-scoped completed-task query. All three now go through one
function, `tether.in_gather_scope`, and the gate's two SQL branches collapse into one.

**This is deliberately a no-op for every topology on disk**, and that is what licenses it
as a separate commit ahead of 4c-2 and 4c-3. For a flat tether `lane_group(t) == t`, so
"in scope" reduces to exactly the equality that was there before. What it *adds* is the
ability for a merge scoped to `X` to gather lanes `X.1`..`X.8` — which SQL could not
express, because that is a parent test rather than an equality.

**The 8-lane hierarchical gather is now observed closing against a real
`LocalMessageBroker`, not argued.** In 4b that property was reasoning; it is now a test
result.

## Files Modified

- `maccre_core/orchestration/tether.py` — added `in_gather_scope`; `__all__` extended.
- `maccre_core/orchestration/local_broker.py` — imports `in_gather_scope`; three call
  sites converted:
  - `_gather_gate_state` — two SQL branches → one, `tether_id` selected as a column and
    filtered in Python.
  - `get_completed_payload_paths` — `AND tether_id = ?` removed from the WHERE clause.
  - `get_completed_by_tether` — same, plus a docstring recording one unreachable
    behavioural difference.
- `tests/test_tether.py` — `TestInGatherScope`, **16 tests**.
- `tests/test_gather_scope_migration.py` — **new. 19 tests against a real broker.**

## Function Signature Added

```python
def in_gather_scope(row_tether: str, scope_tether: str) -> bool: ...
```

`row_tether == scope_tether or lane_group(row_tether) == scope_tether`, with an empty
scope admitting everything and an unusable tether admitted to nothing.

## State Contracts

| Object | Owner | Observers | Mutation Rights |
|--------|-------|-----------|-----------------|
| `row_tether`, `scope_tether` | caller | `in_gather_scope` | **none** |
| `cursor` | `fetch_and_lock_task` / `count_ready_tasks` | `_gather_gate_state` | read only — it issues SELECTs and returns a verdict |

No new shared state. `_gather_gate_state` remains a pure read, which is what lets the
claiming path and the sizing hint share one rule instead of two copies.

## Architecture Decisions

### The rule moved out of SQL because SQL cannot express it

A merge scoped to `X` must accept `X.1` through `X.8`. That is a *parent* test. A plain
`WHERE` clause can only do equality here, short of registering a custom SQLite function on
every connection — a per-connection moving part in the one module where connection
handling has already been a defect source. Selecting `tether_id` as a column and filtering
in Python puts the rule where it is testable and where the other two call sites can reach
it.

A side benefit that is really the main one: **the gate stopped needing a branch.** The
`if task_tether_id: ... else: ...` pair existed only because the filter had to be absent
for tetherless flows. `in_gather_scope` handles the empty scope, so there is one query.

### Skipping out-of-scope rows is equivalent to never selecting them

The gate keeps the latest status per node by letting later rows (ordered `id ASC`)
overwrite earlier ones. Filtering in Python means an out-of-scope row is skipped rather
than allowed to overwrite an in-scope one — which is precisely what the old `WHERE` clause
achieved by not returning it. Same outcome, and the comment says so at the line.

### One behavioural difference, recorded rather than special-cased

`get_completed_by_tether`'s old SQL applied `tether_id = ?` unconditionally, so an
**empty** tether matched only rows whose tether was also empty. `in_gather_scope` treats
an empty scope as unscoped, so it now returns every completed row.

That path is **unreachable from the only caller**: `swarm_worker`'s tether-scoped fan-in
guards it with `if _tether_id and _wait_for_nodes and ...`, and intersects the result with
its `Wait_For` list regardless. Recorded in the docstring rather than special-cased,
because a second empty-scope convention in this module is exactly what 4c-1 exists to
remove. The other two sites already treated empty as unscoped, so this makes all three
agree.

### Alternatives rejected

- **A custom SQLite function.** Would have kept the filter in SQL at the cost of
  registering a Python callback on every connection in the module whose connection
  handling has already produced defects.
- **Computing the acceptable tether set in Python and passing an `IN` clause.** Requires
  knowing the lane count before querying, which the gate does not have.
- **Leaving `get_completed_by_tether` on equality** so its empty-scope behaviour was
  untouched. Rejected: three call sites and two conventions is the thing being fixed.
- **Doing 4c-1 together with 4c-2 and 4c-3.** Rejected on the operator's agreement: it
  would put the riskiest edit in the repository and a change to what a tether *means* in
  one reviewable unit, so a subsequent gather-gate misbehaviour would have two candidate
  causes.

## Testing

`tests/test_gather_scope_migration.py` — 19 tests, **against a real `LocalMessageBroker`
on a throwaway database**, seeding `task_queue` rows directly so the test controls the
tethers exactly.

| Group | Covers |
|---|---|
| `TestTheFlatTetherStillGathers` | 8 flat lanes open the gate; **7 of 8 keeps it shut**; a failed lane reports `upstream_failed`; another scatter's lanes do not open it |
| `TestHierarchicalLanesGather` | **8 lanes at `X.1`..`X.8` open a merge at `X`**; 7 keeps it shut; another root's lanes do not; a nested merge at `X.1` gathers `X.1.*` while `X.2.*` is present; `X.10` does not satisfy `X.1` |
| `TestCompletedPayloadPathsRespectScope` | flat collected; hierarchical collected with **8 distinct paths** (E1's shape); other roots excluded; empty scope unchanged |
| `TestCompletedByTetherRespectsScope` | flat, hierarchical, **`open` rows still excluded**, other roots excluded |
| `TestCountReadyTasksStillMirrorsTheGate` | the sizing hint and the claim path still share one rule |

Why integration rather than unit: if the scope rule is wrong the gate never opens, the
task stays `open`, the pool spawns workers that cannot claim it and each retires idle, and
the run burns its wall-clock budget with nothing in the log. That is the named Principle 2
incident and it is invisible to a stubbed test.

### Revert-to-red, performed

Removing the `lane_group` clause from `in_gather_scope` (leaving bare equality) failed
**8 tests — and only the hierarchical ones**:

- 5 integration tests: the root gather, the nested gather, both other call sites, and the
  sizing hint
- 3 unit tests

**All 128 remaining tests passed, including every flat/legacy assertion.** That is the
right pair: it demonstrates the new clause is purely additive and that the migration
property does not depend on it.

### Gate observed 2026-09-05

| Step | Result |
|---|---|
| `omni clean` | 17:38 — 299 bytecode files |
| `omni qa` | **FAILED first**, then PASS 17:40:30 — see below |
| `pytest tests` | **1349 collected / 1347 passed / 2 xfailed / 0 failed** — 228.89 s |
| `omni smoke` | **ALL CHECKS PASSED** — inference 0.9 s, $0.00 |

Reconciles exactly against 1314 / 1312 / 2: `1314 + 16 + 19 = 1349`;
`1312 + 16 + 19 = 1347`; xfailed unchanged at 2.

**`omni qa` earned its keep.** It failed with a real defect —
`get_completed_payload_paths`'s `tether_id` is `str | None`, and passing it straight to
`in_gather_scope(scope_tether: str)` is a type error the old `if tether_id:` guard had
made invisible. Fixed with `tether_id or ""`, which also states that `None` means
unscoped. **A scoped check on `tether.py` would have passed**; this is the
success-siloing the mandate describes, caught by the whole-project gate.

**Process note against myself:** I put `omni clean` and `omni qa` in one message and they
interleaved — clean purged caches at 17:38:18 while qa had started at 17:38:15. Harmless
for lint and types, and the error it found was real and reproduced on the clean re-run, but
it is the hazard I had already recorded and said I would stop creating.

The suite also ran **228.89 s against a usual 172 s**, with no stall: the
over-provisioning test completed all 8. Slower, not hung.

## Limits of this work

- **No hierarchical tether exists at runtime.** Every `X.1` in these tests is seeded by
  the test. The engine still writes one flat tether per scatter group until 4c-3, so the
  capability is proven **against a real broker and a real database, but on synthetic
  rows.**
- **No live flow has run.** `omni smoke` is a single-node flow with no scatter, so it
  proves the change did not break the ordinary path — not that an 8-lane gather closes in
  production. That evidence arrives with 4c-3 and a live run.
- **The gate is the only consumer proven end-to-end.** `get_completed_payload_paths` and
  `get_completed_by_tether` are covered by these tests but their production callers
  (`_handle_merge`, the worker's fan-in) were not exercised with hierarchical tethers.
- **4c-2 is still the blocker for anything further.** Until a node's tether comes from the
  topology rather than from whoever routed to it, assigning per-lane tethers would have
  `route_task` stamp `CTRL_MERGE` with a lane's tether and the gate would never match —
  the deadlock this whole change exists to make impossible.
