# 2026-09-06: A Lane and a Gather Scope Are Different Facts (task 4e)

## Summary

`total_sum_readout`'s `lane_count` was `len(distinct Tether_ID)`. That had been wrong twice
for the same 8-agent scatter, **in opposite directions**:

| | `lane_count` | `expected_peak_concurrency` |
|---|---|---|
| before per-lane tethers | **1** — one tether covered the whole scatter | **1** — promised the operator one thread for an 8-way run |
| after 4c-3 | **9** — the group tether counted as a tenth lane | 8 (correct, as a side effect) |
| **after 4e** | **8** | **8** |

Requirement 33.5 asks for *the number of Flow Lanes* **and** for their tether IDs. The
group tether is neither: it is the **gather scope** the lanes report into, carried by the
scatter and its merge. A lane is a tether that has a parent — `lane_group(t) != t`.

**It also fixed the legacy case, which I had not planned for.** A hand-authored CSV with
one flat tether identifies no lane individually, so the tether column cannot answer the
question at all. The scatter's fan-out width can, and gives the same answer. That topology
went from `lane_count == 1` and a peak of 1 to **8 and 8**.

## Files Modified

- `maccre_core/orchestration/flow_engine.py` — `total_sum_readout`: `lane_tethers`,
  `gather_scopes`, the fan-out fallback, `lane_count_source`; `nodes_per_lane` now keyed by
  lane tethers only. Docstring updated. Imports `lane_group`.
- `tests/test_prelaunch_validation.py` — new `TestLanesAreNotGatherScopes`, **10 tests**.
  `from typing import Any` added.
- `tests/test_scatter_lane_tethers.py` — the 4e red marker **removed** after it XPASSed;
  two tests updated to the corrected contract; one added.

## Signature / Contract Changes

`total_sum_readout`'s returned dict gains two keys and changes the meaning of two:

```python
"lane_count":        int    # lanes, not tethers
"lane_count_source": str    # "lane_tethers" | "scatter_fan_out" | "none"   NEW
"lane_tether_ids":   list   # lanes ONLY (was: every distinct tether)
"gather_scopes":     list   # distinct lane_group values                    NEW
"nodes_per_lane":    dict   # keyed by lane tether ONLY (was: every tether)
```

## State Contracts

| Object | Owner | Observers | Mutation Rights |
|--------|-------|-----------|-----------------|
| `topology_rows` | caller | `total_sum_readout` | **none** — copied via `list(...)` on entry |
| `tethers`, `lane_tethers`, `gather_scopes`, `fan_out_lanes` | function locals | none | owner only, die with the call |

Still a pure read. No locks, no I/O.

## Architecture Decisions

### A lane is a tether with a parent

One line — `lane_group(t) != t` — and it is the whole definition. It works out correctly for
every case the engine produces:

- `X.1`..`X.8` → 8 lanes, `X` → a scope. Correct.
- A flat `scatter_abc12345` is its own group → a scope, not a lane. **Also correct**: under
  the flat scheme no lane was ever individually identified, and saying "0 lane tethers" is
  the true statement about that topology.

Because it reads through `lane_group`, it inherits the level-by-level comparison rather
than a prefix test, so `X.10` is not mistaken for something under `X.1`.

### Two sources of evidence for one question, with the source reported

The flat case still has a knowable lane count — the scatter's fan-out width — so refusing
to answer would have been needlessly weak. But taking the number from a *different place*
without saying so is how an unattributable count gets trusted.

So `lane_count_source` names the evidence: `"lane_tethers"` (direct), `"scatter_fan_out"`
(inferred from edges), or `"none"`. **This is not a second definition of a lane; it is one
question answered from the best available evidence, labelled.** The precedent is in the same
function: `source` already reports whether the rows are hydrated rather than asserting it.

Lane tethers win when both are present, because they are the direct evidence.

### `nodes_per_lane` excludes the control nodes, and the gap is asserted

The scatter and the merge sit on the scope, not in a lane, so they appear in no bucket. A
caller summing `nodes_per_lane` gets 8 against a `node_count` of 10.

That difference is informative rather than a miscount, and
`test_nodes_per_lane_covers_lanes_only` asserts the relationship (`sum == node_count - 2`)
so the gap is a documented property rather than something a future reader has to work out.

### The scatter is detected through the enum, not a literal

`DeterministicNodeType.SCATTER.value` rather than `"CTRL_SCATTER"`. The prefix check
tolerates the hydration suffix (`CTRL_SCATTER_S0`).

**Known limit, stated rather than hidden:** the legacy `DET_` alias is not matched, so a
topology using `DET_SCATTER` with flat tethers would fall through to `lane_count == 0`.
`_resolve_node_type` handles that normalisation but is private to `deterministic_nodes`, and
reaching into another module's private helper to cover an alias the auto-wrap never emits
was the worse trade.

### Alternatives rejected

- **Deriving `lane_count` from the fan-out in all cases.** It requires a `CTRL_SCATTER` row
  to be present, and four existing readout tests describe lanes with tether-only rows — a
  legitimate shape, since a readout may be asked about rows that carry tethers without the
  scatter that made them. Per-lane tethers are the direct evidence where they exist.
- **Keeping `lane_tether_ids` as every distinct tether** and adding a separate lane list.
  Two lists, one of which is a superset, and 33.5 asks for the lanes' tether IDs.
- **Reporting `lane_count == 0` for a flat topology** and stopping there. Honest but
  needlessly weak: the count is knowable from the edges.
- **Counting the group as a lane when it is the only tether** (so a flat scatter reads as
  1 lane). That is the original defect, restated as a special case.

## Testing

`tests/test_prelaunch_validation.py::TestLanesAreNotGatherScopes` — 10 tests, built on two
row fixtures: the hierarchical shape 4c-3 emits, and the same topology flattened to one
tether.

| Test | Covers |
|---|---|
| `test_eight_lanes_are_counted_as_eight` | the number, and its source |
| `test_the_group_tether_is_a_gather_scope_not_a_lane` | `X` in `gather_scopes`, **absent** from `lane_tether_ids` |
| `test_the_peak_is_no_longer_one_for_an_eight_way_run` | the defect as the operator sees it |
| `test_nodes_per_lane_covers_lanes_only` | 8 buckets, and `sum == node_count - 2` |
| `test_a_flat_topology_is_counted_from_the_scatter_fan_out` | **the legacy fix** — 8 lanes, peak 8 |
| `test_a_flat_topology_reports_no_lane_tethers_rather_than_pretending` | "8 lanes, none individually tethered" as an honest pair |
| `test_a_linear_flow_still_reports_no_lanes_and_says_why` | 0 lanes, source `"none"`, peak 1 |
| `test_the_lane_count_source_is_always_one_of_the_three` | the label is never absent or invented |
| `test_lane_tethers_win_over_the_fan_out_when_both_are_present` | precedence |
| `test_two_scatters_report_two_gather_scopes` | two scopes, nine lanes |

**Four pre-existing readout tests were left untouched and still pass** —
`test_lanes_are_counted_from_tether_ids`, the 64-lane clamp, the pool-request test and the
hard-cap test. They describe lanes with hierarchical tethers (`X.0`..`X.63`), so the new
definition agrees with them. That is the check that this is a correction rather than a
redefinition: the tests that were *right* did not move.

### Revert-to-red, performed

Restoring `len(tethers)` failed **5 tests** — the 8-lane count, both flat-topology tests,
the two-scopes test, and the former marker in `test_scatter_lane_tethers.py`.

`test_the_peak_is_no_longer_one_for_an_eight_way_run` **stayed green under the probe**,
correctly: `min(9, 8)` is still 8, so the peak was already fixed by 4c-3 and does not depend
on this change. The probe reddened exactly the assertions about the lane *count*.

### Gate observed 2026-09-06

| Step | Result |
|---|---|
| `omni clean` | 12:43 — 303 bytecode files |
| `omni qa` | **FAILED first**, then PASS 12:44:47 — see below |
| `pytest tests` | **1431 collected / 1429 passed / 2 xfailed / 0 failed** — 206.44 s |
| `omni smoke` | **ALL CHECKS PASSED** — inference 0.8 s, $0.00 |

Reconciles exactly against 1420 / 1417 / 3: `1420 + 10 + 1 = 1431`;
`1417 + 11 + 1 converted marker = 1429`; xfailed `3 - 1 = 2`.

**Only two red markers remain in the whole suite** — Req 34.1 (payload wiring, blocked on an
operator baseline run) and Req 31.6 (`record_crossing` unwired).

**`omni qa` earned its keep again, and the failure mode is worth recording.** Ruff caught
three `F821 Undefined name 'Any'` in `test_prelaunch_validation.py`: I used
`list[dict[str, Any]]` without importing `Any`, and because the file has
`from __future__ import annotations` the annotations are never evaluated — **all 36 tests in
that file passed while the name was undefined.** A green suite could not have found it. This
is the second time in the 4c–4e sequence that the whole-project gate caught something the
tests structurally could not.

## Limits of this work

- **The readout still has no caller.** `total_sum_readout` is not invoked by any launch
  path, so no operator sees these numbers yet. Wiring it is the TUI task. Fixing the
  arithmetic before it has a consumer is deliberate — it was already wrong, and a wrong
  number is worse once someone is reading it.
- **`gather_strategies`, `waits` and `cross_lane_routes` are still empty**, as their comment
  says. Reqs 29/31/32 built the mechanisms; nothing populates these keys from a hydrated
  topology.
- **No live run has produced a readout.** Every number here comes from hand-built rows or
  from the auto-wrap called directly. The 8-lane live run remains the outstanding evidence
  for the whole 4c–4e sequence.
- **The `DET_SCATTER` alias is not matched** by the fan-out fallback (above). It affects
  only a flat-tethered topology using the legacy prefix.
- **`lane_count` for a nested scatter is a flat total, not a tree.** `X.1`, `X.2`, `X.1.1`,
  `X.1.2` counts 4 lanes across 2 gather scopes, which is true but says nothing about depth.
  Requirement 19's depth reporting is 4g.
