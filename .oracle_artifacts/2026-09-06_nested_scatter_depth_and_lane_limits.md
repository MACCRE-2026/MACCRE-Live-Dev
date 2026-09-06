# 2026-09-06: Requirement 19 — nested scatter depth and the concurrent-lane ceiling

**Task:** 4g of the Era 3 tracker.
**Domain:** `maccre_core/orchestration/` (`tether.py`, `flow_engine.py`).
**Branch:** `phase/6.13-track-a-d-and-payload-lineage`.

---

## Summary

Two constants had sat in `tether.py` since task 4b with **no consumer at all**:
`MAX_CONCURRENT_LANES = 64` and `NESTING_DEPTH_WARN_AT = 2`. Requirement 19 is what they
were declared for. This task gives them one, at the pre-flight seam that actually reaches
the operator, and publishes the nesting depth on the readout so the TUI work has a number
to read rather than one to re-derive.

**The gap was reachable, and both halves were measured before anything was written.**
That ordering matters here more than usual, because the previous attempt at this task was
planned against a documented class that did not exist.

| Probe | Result |
|---|---|
| 70 slotted agents through the real auto-wrap | **70 lanes, 72 topology rows, accepted in silence** |
| readout for that topology | `lane_count=70`, `expected_peak_concurrency=12`, **no depth reported at all** |
| operator types `X.1` in the Tether ID box | lanes `X.1.1`, `X.1.2` — **depth 2, reachable today, nothing warned** |

`_get_macronode` takes `len(scatter_agents)` straight from step config and has no ceiling
of its own. `MAX_SCATTER_AGENTS` (8) bounds the *slots the UI offers* and
`SCATTER_HARD_CAP` (12) bounds *threads*; neither bounds the number of lanes a topology may
declare, and a saved or hand-edited config carries whatever it carries.

---

## Files Modified

- **`maccre_core/orchestration/tether.py`** — new `lane_tethers`, `max_nesting_depth`,
  `deepest_tethers`. **`count_lanes` corrected.** `MAX_CONCURRENT_LANES` and
  `NESTING_DEPTH_WARN_AT` doc-comments now name their consumer and record the measured gap.
- **`maccre_core/orchestration/flow_engine.py`** — new module-level `row_tethers`;
  `total_sum_readout` reads lanes through `tether.lane_tethers` instead of deriving them,
  and gains four keys; `preflight_check` gains check **(f)**; the auto-wrap logs at ERROR
  when an overridden run exceeds the ceiling; local `lane_tethers` renamed `lane_ids`.
- **`tests/test_nested_scatter_limits.py`** — new, **54 tests**, 8 groups.

---

## Function Signatures Added / Changed

```python
# tether.py — new
def lane_tethers(tether_ids: Iterable[str]) -> list[str]:
    """The subset that names LANES. The one definition of a lane: lane_group(t) != t."""

def max_nesting_depth(tether_ids: Iterable[str]) -> int:
    """Deepest nesting present, in separators. X.1.1 -> 2, which is 19.2's '3 levels'."""

def deepest_tethers(tether_ids: Iterable[str]) -> list[str]:
    """The tethers at max_nesting_depth, so a warning can NAME them."""

# tether.py — CORRECTED, was len(set of distinct ids)
def count_lanes(tether_ids: Iterable[str]) -> int:
    """Now len(lane_tethers(...))."""

# flow_engine.py — new
def row_tethers(topology_rows: list[dict[str, Any]]) -> list[str]:
    """Every distinct Tether_ID in first-seen order. The one reader of that column."""
```

`total_sum_readout` gains `max_nesting_depth`, `deepest_lane_tethers`, `lane_limit`,
`exceeds_lane_limit`. **No key changed meaning and none was removed**, so 4e's contract
still holds; this is additive.

---

## State Contracts

| Object | Owner | Observers | Mutation Rights |
|---|---|---|---|
| `PreflightReport.issues` | `FlowRunner.preflight_check` | `nexus_plex.action_launch_flow` (renders, gates on `is_ok`) | Owner only, append-only within one call |

No `threading.Event`, `queue.Queue` or other shared mutable state is introduced or touched.
Every function added is pure, and `tether.py` remains free of I/O and of imports from
elsewhere in the orchestration package.

---

## Architecture Decisions

### 1. `count_lanes` was corrected, not worked around. It would have re-introduced 4e's defect.

`count_lanes` counted **distinct tether ids**. Its docstring named Requirement 19.3's
ceiling, so it was the obvious function to build the limit on — and for the ten rows of an
8-lane scatter the distinct ids are `X` plus `X.1`..`X.8`, which is **nine**. Nine is
exactly what `total_sum_readout` reported before task 4e corrected it.

**Measured by revert-to-red rather than argued:** restoring the old definition failed 10
tests, and the one that matters is `test_exactly_the_limit_is_allowed`. A legal 64-lane
topology was **refused**, because 64 lanes plus their gather scope counts as 65. The
ceiling would have fired one lane early while telling the operator it had counted 64 — an
approximately-correct number acted on, which is Principle 2 in the place a flow gets
blocked.

Nothing consumed `count_lanes`, so no behaviour regressed. Its existing tests passed only
because every one of them fed it lane tethers already stripped of the group
(`child_tether_ids("X", 8)`), so the flaw was invisible to them. **One test changed
meaning and carries a dated note**: `count_lanes(["scatter_84fe89ba"] * 10)` was `1` and is
now `0`, because a flat tether names no lane individually. That is the same fact the
readout already reports by answering the flat case from the scatter's fan-out width
instead.

Rejected: leaving `count_lanes` alone and adding a correctly-defined sibling. That leaves a
function whose docstring points at Requirement 19.3 and whose definition is wrong for it —
a landmine with a label inviting the next reader to step on it.

### 2. The lane rule moved into `tether.py` rather than being written a second time.

4e settled "a lane is a tether with a parent" as a comprehension inside
`total_sum_readout`. 4g needs the same rule at pre-flight. Writing it twice would be
Doctrine 4's named incident, and the cost is specific rather than stylistic: **the ceiling
would refuse one number while the readout displayed another, for one topology, in the same
modal.** `lane_tethers` is now the single definition and both read through it, pinned by
`test_the_readout_reports_through_the_shared_rule`.

`row_tethers` exists for the same reason one level down — both callers need the tether
column off a row dict, and extracting it separately would let them disagree about whether
a whitespace-only cell counts.

### 3. Depth warns. Only the lane ceiling refuses. The asymmetry is the requirement's own.

Requirement 19's user story asks to nest *"until complexity becomes unmanageable"* and for
the system to *"not artificially limit my authoring capability but naturally surface when I
have exceeded manageable complexity."* Surfacing is a warning; a depth refusal would be the
artificial limit the story rules out. The lane ceiling is the one refusal because it alone
bounds a resource.

Verified by revert-to-red: promoting the depth notice to ERROR failed 6 tests, including
`test_no_error_anywhere_mentions_depth_or_nesting` — which is deliberately written against
*any* error mentioning nesting rather than against my own message text, so it holds even if
the wording is reworded later.

### 4. Requirement 19.3 is enforced as a launch block the operator can still override.

`preflight_check` is genuinely wired: `nexus_plex.action_launch_flow` calls it, renders the
report, and gates launch on `is_ok`. That is what distinguishes this seam from
`total_sum_readout`, which is **still consumed by nothing**.

On failure the TUI reveals a *Proceed Anyway* button. That escape hatch predates this check
and is deliberate for the others, so 19.3 lands as *"refuses to launch unless the operator
explicitly overrides"* rather than as an absolute bar. **Recorded rather than glossed,
because the requirement says reject.**

The auto-wrap therefore logs at **ERROR** on an over-limit run without refusing. Refusing
there would take the operator's flow away *after* they had explicitly chosen to proceed,
and it is the same call as 4c-3's substitute-and-log decision for an unusable tether. But
an overridden 70-lane run must not read like a 4-lane one in the log, and before this the
only trace was an INFO line that reads identically at any width.

Rejected: refusing inside `_get_macronode`. It would override an existing, deliberate
operator decision, and it fails the build at execution time rather than at the gate.

### 5. Lanes are counted per step, not summed across the flow.

Steps execute in sequence, so lanes in step 0 and step 2 are never in flight together.
Summing would refuse a flow that never exceeds the ceiling at any instant, and 19.3 says
**concurrent**. Two steps of 40 lanes pass; one step of 65 does not. Both pinned.

### 6. 19.4 is SUPERSEDED by Requirement 29, and that is recorded as a test.

19.4 demands unconditionally that every nested branch have a corresponding `CTRL_MERGE`.
29.1 permits a lane to terminate with no gather node, and 29.3 makes the refusal
conditional on the declared Gather Strategy. Building 19.4 as written would refuse
topologies Requirement 29 explicitly allows. `TestRequirement194IsSupersededNotForgotten`
exists so that reviving 19.4 has to argue with 29 first, which is the argument that
matters.

### 7. Depth is published in one unit, with the two readings kept apart.

`max_nesting_depth` counts **separators**, the unit `tether.depth` uses, because that is
the design's only precise statement of the number (`parse_depth("X.1.2") → 2`). The
operator-facing warning speaks in **levels** (`depth + 1`), because that is Requirement
19.2's wording. `level_count` already existed for exactly this and a test already pins
`level_count == depth + 1`, so the two readings cannot drift into independent definitions.

### 8. Local `lane_tethers` renamed `lane_ids` in the auto-wrap.

Importing a `lane_tethers` function into a module that already had a local list of that
name would leave one identifier meaning two things in one file. Renamed rather than
aliased, so neither name has to be remembered as the special one.

---

## Testing

`tests/test_nested_scatter_limits.py` — **54 tests**, 8 groups:

| Group | Covers |
|---|---|
| `TestALaneIsDefinedInExactlyOnePlace` | the shared rule, and the readout reading through it |
| `TestCountLanesNoLongerCountsTheGatherScope` | the correction, including the 64-vs-65 boundary it would have broken |
| `TestNestingDepthIsMeasured` | depth in separators, the maximum, unusable ids, deepest naming |
| `TestTheReadoutPublishesNesting` | the four new keys, and `exceeds_lane_limit` agreeing with its own count |
| `TestTheAutoWrapStillHasNoCeilingOfItsOwn` | the measured 70-lane starting point, and the ERROR log |
| `TestTheLaneCeilingRefusesAtPreflight` | 19.3 — both sides of the boundary, verbatim message, `is_ok`, per-step |
| `TestNestingIsAllowedAndOnlySurfaced` | 19.1 and 19.2's engine half |
| `TestRequirement194IsSupersededNotForgotten` | why 19.4 is not built |

Plus `TestRowTethersIsTheOneReaderOfTheTetherColumn`.

**19.1 needed care to test, because it is a permission.** A scatter over synthetic agent
names legitimately fails the agent-directive check, so a test asserting `issues == []`
would pass or fail for reasons unrelated to nesting. The assertion is therefore that **no
ERROR mentions nesting**, which is what 19.1 actually says.

### Revert-to-red, both performed

| Probe | Result |
|---|---|
| `lane_tethers` returns all distinct tethers (pre-4g rule) | **10 failed**, incl. `test_exactly_the_limit_is_allowed` — a legal 64-lane flow refused |
| depth notice promoted `WARN` → `ERROR` | **6 failed**, incl. `test_no_error_anywhere_mentions_depth_or_nesting` |

Both restored and re-verified green at 54/54 before gating.

### Gate

Recorded in the ledger entry with the observed numbers. `omni clean` → `omni qa` (whole
project) → full pytest → `omni smoke`, in that order and never chained.

---

## Limits, stated rather than left to be discovered

- **No live 8-lane run has ever been performed**, and this task does not change that.
  `omni smoke` runs a single-node flow with no scatter, so it exercises no lane at all.
  Every number above comes from the real auto-wrap and the real `preflight_check` called
  directly, or from hand-built rows.
- **`total_sum_readout` still has no caller.** The four new keys are published for the TUI
  task and are read by nothing yet. Fixing and extending a readout before it has a consumer
  is deliberate — it was already silent about depth, and a missing number is worse once
  someone is reading it — but it is not the same as being wired.
- **19.2's warning icon and 19.5's indentation are not built.** The engine now computes and
  publishes the depth; drawing it is the TUI task.
- **The `#cfg-tether-id` Input still does not validate**, so an operator can type `X.1` and
  silently author a nested topology. It now *warns* at pre-flight, which is new, but the
  authoring-time half of 19.3 — refusing the insertion — belongs to the workshop and is
  deliberately not stubbed here, so there is one place that decides.
- **The 64-lane number is Requirement 19.3 as written and is not validated against
  evidence.** Nobody has measured where a topology actually becomes unmanageable, and this
  task does not claim to have.
- The intermittent `test_demand_overprovisioning` full-suite hang remains **observed and
  not root-caused**, and is unrelated to this change.
