# 2026-09-05: The One Tether Seam (task 4b)

## Summary

`maccre_core/orchestration/tether.py` — a pure module that owns the tether ID: what a
lane is called, how deep it is nested, and **which gather scope it belongs to**.

This is the foundation for tasks 4c–4g. It replaces nothing yet: it has **zero
importers**, deliberately, so that 4c can move the fan-in gate onto it as a separate,
reviewable, smoke-gated change.

The module exists because a tether ID answers two different questions and the codebase
had no single answer to either — three representations, one of which was documented as a
completed 88-line class and defines no code. See
`.kiro_artifacts/2026-09-05_tether_model_divergence_and_task_revision.md`.

## Files Modified

- `maccre_core/orchestration/tether.py` — **new**, 380 lines. Pure: imports only
  `logging` and `typing`, and nothing from elsewhere in the orchestration package, so
  `flow_engine`, `local_broker`, `topology_graph` and the TUI can all read through it
  without a cycle.
- `tests/test_tether.py` — **new. 101 tests, eleven groups.**

## Function Signatures Added

```python
TETHER_LEVEL_SEPARATOR: str = "."
FORBIDDEN_IN_TETHER_ID: frozenset[str] = frozenset({"@", ">", ",", "|"})
NESTING_DEPTH_WARN_AT: int = 2       # Req 19.2, in the depth reading
MAX_CONCURRENT_LANES: int = 64      # Req 19.3; lanes, NOT threads
ROOT_TETHER_IDS: tuple[str, ...] = ("X", "Y", "Z")

class TetherIdError(ValueError):
    def __init__(self, tether_id: str, reason: str) -> None: ...

def validate_tether_id(tether_id: str) -> str: ...
def is_hierarchical(tether_id: str) -> bool: ...
def depth(tether_id: str) -> int: ...            # X->0, X.1->1, X.1.2->2
def level_count(tether_id: str) -> int: ...      # depth + 1, the prose reading
def lane_group(tether_id: str) -> str: ...       # THE function the fan-in gate turns on
def is_descendant_of(tether_id: str, ancestor: str) -> bool: ...
def root_tether_id(index: int) -> str: ...       # 0->X 1->Y 2->Z 3->AA 4->AB 29->BA
def child_tether_ids(parent: str, count: int) -> list[str]: ...
def count_lanes(tether_ids: Iterable[str]) -> int: ...
def lanes_by_group(tether_ids: Sequence[str]) -> dict[str, list[str]]: ...
```

## State Contracts

| Object | Owner | Observers | Mutation Rights |
|--------|-------|-----------|-----------------|
| every argument | caller | the functions above | **none** — read only |
| module constants | the module | everyone | **none** — read only |
| (no instance state exists) | — | — | — |

**There is deliberately no object with state here.** That is the point of the deviation
recorded below, and it is why there is no lock to document.

## Architecture Decisions

### `lane_group` is the whole design, and its legacy case is not a fallback

The flat tether **is** the gather scope. One value goes on the scatter, every lane and
the merge, and the gate matches on equality — so it can say "same scatter" but cannot say
"which lane". Giving each lane its own *flat* id would say which lane and destroy the
scope, and that failure is already measured: a blanked tether id put a scatter and its
merge in different scopes, the gather gate could never open, and an 8-lane run deadlocked.

A hierarchy carries both:

| Input | `lane_group` | Meaning |
|---|---|---|
| `"X.1"` | `"X"` | lane 1 gathers at scatter X |
| `"X.1.2"` | `"X.1"` | nested lane gathers one level up |
| `"X"` | `"X"` | a root scatter is its own scope |
| `"scatter_84fe89ba"` | `"scatter_84fe89ba"` | legacy flat, unchanged |
| `"tether_a"` | `"tether_a"` | legacy flat, unchanged |

**A root returning itself and a flat id returning itself are the same case, not two.** A
top-level scatter *is* its own gather scope — which is exactly the relationship the flat
scheme encoded for everything — so there is no legacy branch in `lane_group` to keep
correct. One `if separator in text`, and the migration property falls out of it.

That property is what makes 4c safe: for every id on disk `lane_group(t) == t`, so "same
lane group" degenerates *exactly* to the equality the gate already performs.
`test_equality_and_same_lane_group_agree_on_a_legacy_scatter` asserts it directly by
collecting the ten rows of a legacy 8-lane scatter both ways and comparing the sets.

### Generation is pure — a deliberate deviation from `design.md`

`design.md` specifies a stateful `TetherIDGenerator` with instance counters and a
`threading.Lock`. This module provides `root_tether_id(index)` and
`child_tether_ids(parent, count)` instead.

The argument is already in this codebase. `_default_tether_id`'s docstring records that
its predecessor was `f"scatter_{id(scatter_agents) % 9999:04d}"` — keyed on a CPython
object address — and that **the auto-wrap runs twice per step, once for pre-flight
validation and once for execution, so the tether validated was not necessarily the tether
executed.** It was replaced with a stable digest for exactly that reason.

A locked counter reintroduces the same class of problem in a milder form: the id a lane
receives depends on how many times the generator has been called, so it is not
reproducible across a validate-then-execute pair. Derivation needs no counter, no lock,
and gives the same answer every time. `test_it_is_pure_so_the_same_index_always_gives_the_same_id`
pins it.

### A defect my own test caught, worth recording

`root_tether_id`'s first bijective base-26 implementation started at `1`, which emitted
the single letters `"A".."Z"` for indices 3–28 — and **index 26 produced `"X"`, colliding
with root index 0.** Two different roots sharing one tether ID is precisely the class of
defect this module exists to remove, and it was caught by
`test_no_two_indices_collide` rather than by review. The offset now starts at `27`
(`"AA"`), the reason is a comment at the line, and the collision guard is a permanent test.

### `FORBIDDEN_IN_TETHER_ID` is derived from existing seams, not invented tidiness

Every character is there because something in this package would mis-parse it:

| Char | Owned by | What breaks |
|---|---|---|
| `@` | `parse_tether_qualified_ref` | a lane whose id contains `@` is unaddressable — the parser refuses two separators |
| `>` | `FLOW_VECTOR_SEPARATOR` | a tether containing it forges a lineage hop |
| `,` `|` | `parse_targets` (accepts both) | one lane splits into two names in `Wait_For` |

Asserted **against the other modules' constants**, not against literals:
`TestATetherIdCannotCollideWithAnotherSeam` imports `TETHER_SEPARATOR` and
`FLOW_VECTOR_SEPARATOR` from `topology_graph` and checks membership, then round-trips
every valid tether form through `parse_tether_qualified_ref`. That is the real invariant —
a lane this module accepts can be named in a cross-lane route.

### Requirement 19.2's prose contradicts its own worked example, and that is reconciled explicitly

19.2 says *"depth reaches 3 levels (root → child → grandchild)"*. `design.md` says
`parse_depth("X.1.2") → 2`. Both describe `X.1.2`, counted differently: 3 **levels**, 2
**separators**.

`depth()` counts separators, because that is the spec's only precise statement of the
number. `NESTING_DEPTH_WARN_AT = 2` is therefore in the depth reading, and `level_count()`
exists for the prose reading so neither has to be re-derived from the other at a call
site. `test_level_count_is_always_depth_plus_one` and
`test_the_prose_and_the_example_are_reconciled_not_chosen_between` pin the relationship,
so the two readings cannot drift into independent definitions — which is how this
divergence started in the first place.

### `is_descendant_of` compares levels, never string prefixes

`"X.10".startswith("X.1")` is `True`. A prefix test would fold lane 10 into lane 1's
gather scope on any scatter wider than nine lanes — an approximately-correct answer of
exactly the kind Principle 2 is about. The test asserts the prefix trap is real *and* that
the function is not fooled by it.

### `validate_tether_id` is deliberately permissive

It runs against ids that are **already saved**: `scatter_<sha1>`, `tether_a`, and anything
an operator typed into the Tether ID box. Refusing something a saved topology contains
would break that flow at launch. So only three things are refused: empty, a forbidden
character, and an empty level (`".X"`, `"X."`, `"X..1"`) which would make `lane_group`
return a meaningless parent. An interior space is **allowed** — it parses fine everywhere
and may already be on disk.

### Alternatives rejected

- **The stateful `TetherIDGenerator` from `design.md`.** Reintroduces a
  validate-then-execute mismatch the engine already fixed once, plus a lock.
- **Giving each lane its own flat id.** Expresses lane identity, destroys the gather
  scope, reproduces the measured 8-lane deadlock.
- **A schema-version flag to distinguish legacy from hierarchical ids.** Unnecessary:
  the presence of a separator is self-identifying, and a version field is a second
  representation of a fact the id already carries.
- **A migration pass rewriting saved tether IDs.** Irreversible, touches operator data,
  and unnecessary given `lane_group(t) == t`. `child_tether_ids` works on a flat parent,
  so a saved topology can gain per-lane tethers *in place* whose `lane_group` is the
  value the existing merge row already carries.
- **Refusing interior spaces or enforcing a character class.** Would refuse ids already
  on disk.
- **Putting this in `topology_graph`.** That module owns the *graph*; this owns an
  *identifier*. `topology_graph` is already 1,000+ lines across four requirements, and
  the TUI needs the tether functions without needing the graph.

## Testing

`tests/test_tether.py` — 101 tests:

| Group | Covers |
|---|---|
| `TestLaneGroupIsBackwardCompatible` | **the migration property**, parameterised over every id format on disk; equality vs lane-group agreement on a legacy 8-lane scatter; the new capability |
| `TestLaneGroupHierarchy` | lane → scatter, nested → one level up, walking up terminates |
| `TestDepthAndLevelCount` | separator counting, the design's worked example, `level_count == depth + 1`, prose/example reconciliation |
| `TestIsDescendantOf` | self, ancestor, sibling, other root, **the `X.10` vs `X.1` prefix trap**, legacy |
| `TestRootTetherId` | X/Y/Z against the constant, `Z → AA`, roll-over, purity, **no-collision**, negative refused |
| `TestChildTetherIds` | append a level, grandchildren, one-based, **generator/`lane_group` inverse**, legacy parent in place, zero, negative, purity |
| `TestValidateTetherId` | every on-disk format accepted, whitespace, interior space allowed, empty refused, **every forbidden char parameterised**, empty levels |
| `TestATetherIdCannotCollideWithAnotherSeam` | membership asserted against `topology_graph`'s constants; **round-trip through `parse_tether_qualified_ref`** |
| `TestCountLanes` | distinct counting, legacy ten-rows-is-one-lane, two scatters, malformed skipped, ceiling is not the thread cap |
| `TestLanesByGroup` | grouping, first-seen order, legacy, nested, malformed skipped |

### Gate observed 2026-09-05

| Step | Result |
|---|---|
| `omni clean` | 17:05 — 299 bytecode files |
| `omni qa` | **PASS, whole project** 17:06:24 |
| `pytest tests` | **1314 collected / 1312 passed / 2 xfailed / 0 failed** — 172.28 s |
| `omni smoke` | **NOT RUN**, and the reason is stated below |

Reconciles exactly against 1213 / 1211 / 2: `1213 + 101 = 1314`; `1211 + 101 = 1312`;
xfailed unchanged at 2 (Req 34.1 and Req 31.6).

**`omni smoke` was not run because nothing on an execution path changed.** `tether.py`
has **zero importers** — verified by its own newness, and it is imported only by its test
file. The last smoke passed after the most recent execution-path change
(`deterministic_nodes.py`, task #3). **4c is the change that requires smoke**, and it will
get it.

## Limits of this work

- **Nothing calls it.** Zero importers is the design of this task, not an oversight: 4c
  moves the gather gate onto `lane_group` as a separate change so that the riskiest edit
  in the repository is reviewable and smoke-gated on its own.
- **The migration property is proven in unit tests, not in a live run.** The claim that
  `lane_group` makes the gate change a no-op is asserted over the id *formats* observed on
  disk. It becomes a finding when an 8-lane gather is observed closing after 4c.
- **No per-lane tether has ever existed at runtime.** Every hierarchical id in these
  tests is hand-built. The engine still writes one flat tether per scatter group until 4c.
- **`MAX_CONCURRENT_LANES = 64` is Requirement 19.3 as authored and is not validated.**
  It is unrelated to `MAX_SCATTER_AGENTS` (8) and `SCATTER_HARD_CAP` (12), which bound
  threads; `test_the_ceiling_is_declared_and_is_not_the_thread_cap` pins that they are
  different numbers, not that 64 is the right one.
- **`NESTING_DEPTH_WARN_AT` has no consumer.** Requirement 19.2's warning is a TUI
  affordance (task #5); this only fixes what the number means.

## OPEN FINDING — the intermittent suite hang, now 3 occurrences in 8 runs

`test_demand_overprovisioning.py::TestTheFixDoesNotCostConcurrency::
test_a_real_burst_still_reaches_full_width` hung again during this task's gate. Third
occurrence today.

This one was caught live: started 17:06:45, stalled at 4 of 8 dots, still stalled at
17:13:48 (**7 minutes**), CPU climbing 158.5 s → 181.8 s across 30 s of wall (about
two-thirds of a core), 8 threads held. The path's ceiling is 90 s
(`timeout_seconds=60` plus a 30 s bounded `_join_all`), so it exceeded its own bound
roughly fivefold.

**Still not root-caused, and one observation worth recording without over-reading it:**
all **three** runs launched under the `faulthandler.dump_traceback_later` instrument have
completed healthily, while **three of five** uninstrumented runs hung. That is either
coincidence at this sample size or a sign that running via `pytest.main()` in-process
perturbs the timing enough to hide it. **I am not claiming the latter** — it is a
hypothesis with n=8, and the instrument remains the right tool for the next attempt.

Unchanged recommendation, still not done because it is outside 4b's scope: give that test
a hard per-test bound so it **fails loudly instead of hanging**. That is a strict
improvement regardless of cause, and converts an indefinite stall into a diagnosable
failure.
