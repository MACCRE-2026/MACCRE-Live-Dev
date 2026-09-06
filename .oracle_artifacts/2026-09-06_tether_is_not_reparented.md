# 2026-09-06: A Node's Tether Is Not Re-Parented By Its Router (task 4c-2)

## Summary

`route_task` stamped every successor with the **router's** tether. It now stamps each
successor with **its own**, as the topology declares it, via a new `target_tethers`
parameter on the `MessageBroker` ABC.

This is the prerequisite that makes 4c-3 possible. Only the entry task is seeded; every
other `task_queue` row is created by whoever routes to it. While one flat tether covered a
whole scatter that was correct *by accident* — the scatter, all eight lanes and the merge
shared one value, so it did not matter who wrote it. The moment lanes carry their own
tethers it is fatal: `CTRL_MERGE` is created by whichever lane finishes first and would be
stamped with **that lane's** tether, the gather gate would look for lanes whose group
matched `X.1` and find none, and the run would deadlock.

That is the register's named incident — a scatter and its merge in different scopes, an
8-lane run that never gathered. `swarm_worker`'s own fan-out branch already carries the
live symptom in a comment: *"a wrong non-empty tether makes it check a scope the
predecessors are not in — so the gate matches zero rows and can never open. Observed live
as an 8-lane merge waiting forever on eight completed lanes."*

Requirement 31.7 states this rule for cross-lane routes, where
`topology_graph.apply_cross_lane_route` refuses to re-parent. **This is that rule applied
to ordinary routing**, which had been violating it on every hop.

## Files Modified

- `maccre_core/orchestration/broker_interface.py` — `route_task` gains
  `target_tethers: Mapping[str, str] | None = None`, documented with why the fallback *is*
  the re-parenting. `Mapping` imported. **Operator approved widening this ABC.**
- `maccre_core/orchestration/local_broker.py` — new module-level
  `_resolve_target_tether`; `route_task` takes the parameter and resolves a per-node
  `node_tether` used at **both** SQL sites (the non-completed `UPDATE` and the
  `INSERT ... ON CONFLICT`). `Mapping` imported.
- `maccre_core/orchestration/swarm_worker.py` — new `_target_tethers` method resolving
  each target's tether from the topology; passed at **all five** `route_task` call sites.
- `tests/mocks/mock_broker.py` — signature widened to match, and it **applies the same
  resolution** rather than accepting the argument and ignoring it.
- `tests/test_tether_is_not_reparented.py` — **new. 23 tests.**

## Function Signatures Added / Changed

```python
# broker_interface.py + local_broker.py + tests/mocks/mock_broker.py — all three together
def route_task(
    self, row_id, job_id, next_node_str, new_payload_path,
    actual_cost=0.0, source_payload_path="", max_recursion=3, status="completed",
    flow_line_id="", flow_vector="", tether_id="", output_path="", payload_bytes=0,
    target_tethers: Mapping[str, str] | None = None,   # NEW
) -> None: ...

# local_broker.py, module level
def _resolve_target_tether(
    node_id: str,
    target_tethers: Mapping[str, str] | None,
    router_tether: str,
) -> str: ...

# swarm_worker.py, UniversalSwarmWorker
def _target_tethers(self, next_node_str: str) -> dict[str, str]: ...
```

## State Contracts

| Object | Owner | Observers | Mutation Rights |
|--------|-------|-----------|-----------------|
| `target_tethers` mapping | the worker that builds it | `route_task`, `_resolve_target_tether` | **none** — read only; the mock copies it before recording |
| `node_tether` | `route_task` local | the two SQL statements | owner only, dies with the loop iteration |
| `self.topology` | `UniversalSwarmWorker.__init__` | `_target_tethers` | **read only** — `get_node_config` is a lookup |

No `threading.Event`, `queue.Queue` or lock is introduced. `_target_tethers` performs
topology reads only, and swallows per-node lookup failures so it cannot add a new way for
a routing call to raise.

## Architecture Decisions

### `target_tethers` is additive, and the fallback is the old behaviour stated as such

Any successor not named in the mapping falls back to `tether_id` — exactly what happened
before. That makes the change unable to regress a caller with no topology to consult
(`macro_factory`'s spawn routes, the `CTRL_PAUSE` resolver), and it keeps every saved
topology behaving identically.

**The fallback is documented as being the defect, not as a sensible default.** A doc
comment that called it "the default" would leave the next reader believing re-parenting is
intended. `test_without_the_mapping_the_merge_inherits_the_lane_and_that_is_the_bug` pins
the fallback behaviour *as a bug*, so nobody removes the mapping thinking it is optional.

### An empty mapped value falls back rather than blanking

"The topology does not say" and "the topology says empty" want the same answer, and only
one of them deserves a dict entry. `_target_tethers` omits empty tethers rather than
recording them, and `_resolve_target_tether` treats an empty mapped value as absent. A
blank stamped over a real tether would be the Principle 2 incident directly — the register
records a blanked tether id putting a scatter and its merge in different scopes.

### Both SQL sites, not just the INSERT

`route_task` writes the tether in two places: the `INSERT ... ON CONFLICT` for a first
arrival or re-queue, and the `UPDATE` on the branch where the row exists and has **not**
completed — which is the *fan-in* path, the one every lane after the first takes. Changing
only the INSERT would have left the second, third and eighth lanes re-parenting the merge
they were converging on. `test_eight_lanes_all_agree_on_the_merges_tether` covers exactly
that: it routes all eight and asserts the last writer did not change it.

### The mock applies the resolution instead of accepting and discarding

`tests/mocks/mock_broker.py` could have taken the parameter to satisfy the signature-parity
test and ignored it. Then a test could pass against the re-parenting this change removes —
"the only thing a mock can get seriously wrong", as its own comment about `payload_bytes`
already says. It imports `_resolve_target_tether` and uses it, so the double and the driver
agree by construction rather than by inspection.

### Write-once tether was considered and deliberately not done

The strongest guarantee would be to refuse any change to an existing non-empty tether. That
is a *behavioural* change to a path where an existing `UPDATE` deliberately sets the tether,
and per-target resolution already makes every writer agree on the same value — so
write-once would be belt-and-braces on top of a correct answer. Rejected for this commit to
keep the change minimal on the highest-risk surface in the repository; recorded here so it
is a considered omission rather than an oversight.

### Alternatives rejected

- **Having `route_task` look the tether up itself.** The broker has no topology and should
  not acquire one; it is a queue.
- **Passing a single resolved tether per call** and looping in the worker. `next_node_str`
  is one field that may name several targets, and the fan-out branch already loops — but
  the default-routing branch does not, so a single-tether parameter would have needed a
  loop added on a path that currently routes a multi-target string in one call.
- **A mock that accepts and ignores the argument.** See above.
- **Doing this together with 4c-3.** The operator agreed to the split. This commit
  contains no per-lane tether *production*, so nothing in it can change what a live flow
  writes; 4c-3 is where behaviour visibly moves.

## Testing

`tests/test_tether_is_not_reparented.py` — 23 tests:

| Group | Covers |
|---|---|
| `TestResolveTargetTether` | own tether wins; falls back on unknown target, on no mapping, and on an **empty mapped value**; an empty router tether is still returned |
| `TestTheDeadlockThisPrevents` | **the merge is created with its own tether, not the first lane's**; the fallback pinned *as the bug*; all eight lanes agree; **the gather gate then opens on all eight**; the merge collects 8 distinct outputs |
| `TestTheFlatModelIsUnchanged` | a flat scatter still stamps one tether everywhere; its gate still opens; a tetherless linear flow still routes with no tether; a sentinel still creates no row |
| `TestFanOutStampsEachLane` | a scatter stamps each lane with its own tether; every stamped lane gathers back at the scatter |
| `TestWorkerTargetTetherResolution` | resolves each target; both `,` and `|`; unknown target absent rather than guessed; empty tether omitted; no topology → no mapping; **a raising topology does not break routing**; empty target string |

### Revert-to-red, performed

Making `_resolve_target_tether` ignore the mapping (returning the router's tether always —
the pre-4c-2 behaviour) failed **5 tests**, including
`test_the_gather_gate_then_opens_on_all_eight_lanes`, which is the deadlock itself.

**Every flat-model test stayed green, and all 19 tests in
`test_gather_scope_migration.py` stayed green.** That is the right pair: the change is
purely additive, and 4c-1's migration property does not depend on it.

Notably `test_the_merge_collects_eight_distinct_lane_outputs` also stayed green under the
probe — correctly, because `get_completed_payload_paths` filters lanes by *their own*
tethers, and the merge's tether is not an input to that query. The probe reddened exactly
the assertions that depend on the merge's own tether being right.

### Gate observed 2026-09-06

| Step | Result |
|---|---|
| `omni clean` | 11:44 — 301 bytecode files |
| `omni qa` | **PASS, whole project** 11:45:23 |
| `pytest tests` | **1372 collected / 1370 passed / 2 xfailed / 0 failed** — 230.34 s |
| `omni smoke` | **ALL CHECKS PASSED** — inference 0.9 s, $0.00 |

Reconciles exactly against 1349 / 1347 / 2: `1349 + 23 = 1372`; `1347 + 23 = 1370`;
xfailed unchanged at 2 (Req 34.1, Req 31.6).

**This is the first commit in the 4c sequence where `omni smoke` exercises the changed
code.** Smoke's single-node flow routes through `route_task` with the new parameter
supplied by `_target_tethers`, so the resolver ran against a real topology and a real
queue — not just against test fixtures.

The signature-parity tests in `test_broker_contract.py` and `test_abc_contracts.py` pass,
confirming the ABC, `LocalMessageBroker` and the mock agree on the widened signature.

## Limits of this work

- **No per-lane tether is produced yet.** The engine still writes one flat tether per
  scatter group; 4c-3 is what starts emitting `X.1`..`X.8`. Every hierarchical tether in
  these tests is supplied by the test.
- **No 8-lane live run.** The gather gate opening on eight hierarchical lanes is proven
  against a real `LocalMessageBroker` and a real SQLite database, but on rows the test
  seeded. `omni smoke` has no scatter.
- **Write-once is not enforced** (see above). Correctness currently rests on every router
  resolving the same value from the same topology, which is true but is a weaker invariant
  than the schema refusing the change.
- **The fallback path is still live and still re-parents.** Callers without a topology —
  `macro_factory`'s spawn routes and the `CTRL_PAUSE` resolver — continue to stamp the
  router's tether. That is deliberate for backward compatibility, and it means the
  guarantee is "every route the worker makes", not "every route".
- **`_target_tethers` swallows lookup failures.** A topology that raises yields an empty
  mapping, which falls back to the router's tether rather than failing the route. That
  trade is deliberate — a routing call must not fail because a lookup did — but it means a
  broken topology degrades to the old behaviour silently rather than loudly.
