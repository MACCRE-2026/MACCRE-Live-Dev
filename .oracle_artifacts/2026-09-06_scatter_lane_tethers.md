# 2026-09-06: The Scatter Auto-Wrap Assigns Per-Lane Tethers (task 4c-3)

## Summary

**This is the commit where the tether hierarchy becomes real at runtime.** 4b built the
seam, 4c-1 taught the gather gate to read through it, 4c-2 stopped routing from re-parenting
nodes — and none of those changed a single value a live flow writes. This one does.

The scatter auto-wrap now produces, for an 8-agent scatter:

```
CTRL_SCATTER   scatter_ef3031e2       the group, and its own gather scope
AGENT_A        scatter_ef3031e2.1     \
...                                    |  eight individually addressable lanes
AGENT_H        scatter_ef3031e2.8     /
CTRL_MERGE     scatter_ef3031e2       the gather scope those lanes belong to
```

Verified by running the real auto-wrap: 10 rows, 8 distinct lane tethers, scatter and merge
on the group, every lane in the merge's gather scope, every `lane_group(lane) == group`.

## Files Modified

- `maccre_core/orchestration/flow_engine.py` — the `CTRL_SCATTER` auto-wrap in
  `_get_macronode`. `tether_id` renamed to `group_tether`; `lane_tethers` derived via
  `child_tether_ids`; agent rows take `lane_tethers[i]`, scatter and merge keep
  `group_tether`. Imports `TetherIdError, child_tether_ids`. Log line now names the group
  and the lane range.
- `tests/test_topology_graph.py` — **three pre-existing tests updated**, each with a dated
  note. Imports `lane_group`.
- `tests/test_scatter_lane_tethers.py` — **new. 32 tests, five groups, one red marker.**

## State Contracts

| Object | Owner | Observers | Mutation Rights |
|--------|-------|-----------|-----------------|
| `group_tether`, `lane_tethers` | `_get_macronode` local | the row dicts it builds | owner only, die with the call |
| `topo_rows` | `_get_macronode` | the caller that hydrates them | returned by value; not shared |

No new shared state, no locks. `child_tether_ids` is pure.

## Architecture Decisions

### The merge sits on the group tether, and that is the load-bearing line

A merge on a *lane* tether is the deadlock 4c-2 exists to prevent: the gate would look for
lanes whose group matched `X.1` and find none. The scatter is on the group tether for the
same reason — it is the scope, not a member of it.

**Revert-to-red proved this is the assertion that matters.** Putting `lane_tethers[0]` on
the merge row reddened 6 tests, including `test_every_lane_is_in_the_merges_gather_scope` —
the deadlock itself — while the lane-shape tests stayed green. So a mistake here fails
loudly rather than producing a plausible-looking topology.

### An operator-typed tether is validated, substituted, and reported — not propagated, not fatal

The Tether ID box accepts any text. A value containing `,` `|` `@` or `>` would be re-split
by another parser — `Wait_For` would read one lane as two. **That was already true before
this change and merely silent**; `child_tether_ids` refuses it via `validate_tether_id`.

Three options, and the middle one was taken:

- **Propagate it** — the pre-existing behaviour. Rejected: an approximately-correct
  identifier that downstream logic acts on, which is exactly Principle 2.
- **Fail the flow build** — loudest, and defensible. Rejected: it takes an operator's flow
  away over a field they can fix, and the value was already broken before today.
- **Substitute the generated tether, log at ERROR naming the offending value and the
  reason.** The flow still runs, the result is well-formed, and the operator is told what
  was ignored and why. `test_the_substituted_group_still_gathers_its_lanes` checks the
  fallback did not itself break the gather — a fallback that broke it would be worse than
  the bad tether.

### A hierarchical operator tether nests one level deeper

An operator naming `X.1` gets lanes `X.1.1`..`X.1.8` — Requirement 18.3's shape, and the
first nested tethers this system can produce. `child_tether_ids` needed no special case for
it; that falls out of deriving children from the parent.

### Lane numbers are one-based and follow declared order

They appear in refusals, in `NODE@TETHER` references and eventually in the TUI. A "lane 0"
reads as an off-by-one every time it is seen. Order follows `scatter_agents`, which is the
same order `Wait_For` declares, so a lane's number and its position agree.

### Alternatives rejected

- **Giving the merge its own child tether** (`X.9` or similar). It is not a lane; it is the
  scope, and a scope with a parent would need a second rule for where gathering stops.
- **Keeping one tether and adding a separate lane-index column.** A second representation
  of lane identity, which is the divergence this whole sequence exists to remove.
- **Rewriting saved topologies to per-lane tethers.** Unnecessary: a saved flat topology
  re-wraps through this same code path on load, so it gains lanes without a migration, and
  `lane_group` keeps the flat form working if it does not.

## Testing

`tests/test_scatter_lane_tethers.py` — 32 tests driving the **real auto-wrap** through
`_get_macronode` with stub MacroNode stores:

| Group | Covers |
|---|---|
| `TestTheAutoWrapAssignsPerLaneTethers` | 8 distinct lanes; children in declared order; **one-based**; each one level deeper; every lane well-formed; parameterised over 1/2/3/8/12 agents; a single-agent scatter still gets a lane |
| `TestTheMergeStillGathersEveryLane` | merge on the group; **merge not on any lane**; **every lane in the merge's scope**; `lane_group` maps all back; `Wait_For` unchanged; two scatters do not share a scope |
| `TestTheWrapIsReproducible` | two calls identical; group asserted against `_default_tether_id` not a literal digest; different agent order is a different scope |
| `TestAnOperatorSuppliedTether` | operator name becomes the group; blank falls back; **five bad values parameterised**, each substituted and well-formed; the substitute still gathers; a hierarchical tether nests |
| `TestTheReadoutConsequences` | peak concurrency now 8; lanes individually named; **one red marker for 4e** |

### Three pre-existing tests updated, with dated notes

`test_topology_graph.py` asserted `len(tethers) == 1` — *"scatter, lanes and merge must
agree"*. That was correct while one flat tether covered a scatter, and 4c-3 deliberately
changes the mechanism. **The intent survives and is now stated in terms of the thing that
actually matters**: every row belongs to one *gather scope*, asserted through `lane_group`.
That is strictly stronger than the string equality it replaced — it would still fail if a
lane were tethered under a different group, which string equality could not distinguish
from a rename.

The hydration test additionally now asserts `len(tethers) == 3` (group + 2 lanes), because
the half of it that still matters is that hydration **carries lane identity through to the
CSV column rather than flattening it** — `Tether_ID` was once dropped entirely by the
flatten step.

### Gate observed 2026-09-06

| Step | Result |
|---|---|
| `omni clean` | 12:01 — 302 bytecode files |
| `omni qa` | **PASS, whole project** 12:08:51 |
| `pytest tests` | **1404 collected / 1401 passed / 3 xfailed / 0 failed** — 176.10 s |
| `omni smoke` | **ALL CHECKS PASSED** — inference 31.1 s, $0.00 |

Reconciles exactly against 1372 / 1370 / 2: `1372 + 32 = 1404`; `1370 + 31 = 1401`;
xfailed `2 + 1 = 3` (Req 34.1, Req 31.6, and the new 4e lane-count marker).

The first full-suite run of this task **failed 3 tests** — the flat-model assertions above.
They were fixed by correcting the assertions to the surviving intent, not by loosening
them.

## What this changed about the readout — one number fixed, one not

`total_sum_readout`, measured against the real auto-wrap's rows:

| Field | Before 4c-3 | After 4c-3 | Verdict |
|---|---|---|---|
| `expected_peak_concurrency` | **1** | **8** | **Correct now.** `min(lane_count, resolve_scatter_cap(8))` was `min(1, 8)`; the pre-launch readout promised the operator one thread for an 8-way run |
| `lane_count` | **1** | **9** | **Still wrong, differently.** It counts the group tether as a lane |

`expected_peak_concurrency` being right is a **side effect**, not a fix I designed, and it
is pinned by a test so it cannot regress silently.

`lane_count == 9` is *not* progress dressed up as a fix. Requirement 33.5 asks for the
number of Flow Lanes; the group tether is a *gather scope*. Rather than assert 9 and call
it done, the gap is a **red `xfail(strict=True)` marker** —
`test_lane_count_reports_eight_lanes_for_an_eight_lane_scatter` — so it breaks the gate the
moment 4e makes it true, and reads as outstanding until then.

## Limits of this work

- **No live 8-lane run has happened.** `omni smoke` runs a single-node flow with no
  scatter, so it proves this did not break the ordinary path — **it does not exercise a
  single per-lane tether.** Every hierarchical tether observed so far comes from the
  auto-wrap in isolation or from a test-seeded queue row. **The 8-lane live run is the real
  proof and it is an operator action.**
- **The whole 4c chain is now live but jointly unproven in production.** 4c-1's scope rule,
  4c-2's per-target stamping and 4c-3's lane tethers only interact on a real scatter. The
  unit and integration evidence is strong and each was revert-to-red verified, but their
  *composition* has been exercised only by tests.
- **`lane_count` is still wrong** (see above). 4e.
- **The TUI still mints its own tether IDs.** `macronode_workshop` writes
  `tether_a`/`tether_b` from a widget counter, and that value can land in `cfg["tether_id"]`
  and become the group tether. It will be *accepted* — `tether_a` is well-formed — so lanes
  become `tether_a.1`.., which works. But there are still two generators. 4d.
- **Nested scatter is reachable but untested end to end.** An operator tether of `X.1`
  produces `X.1.1`..`X.1.8`, and nothing yet limits depth or total lanes. That is 4g.
- **`_default_tether_id` remains the group-tether generator** and was not moved into
  `tether.py`. It is a digest over the agent set — a *naming* decision specific to the
  auto-wrap — whereas `tether.py` owns hierarchy mechanics. Recorded as a deliberate
  split rather than an oversight.
