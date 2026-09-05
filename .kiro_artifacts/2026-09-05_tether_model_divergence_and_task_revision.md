# 2026-09-05: The Tether Model Divergence, and Why the Task List Changed

**Type:** Decision record + task-list revision rationale
**Raised:** 2026-09-05
**Status:** OPEN — 4a recorded; 4b–4g outstanding
**Supersedes:** nothing. Amends the Era 3 tracker's original task #4.

---

## Why this document exists

Era 3 tracker task #4 was *"Nested scatter with depth and lane limits"*. It cannot be
built as scoped. Requirement 19 and Requirement 18.3 define nesting depth and the 64-lane
limit **in terms of a hierarchical tether ID** — `X` → `X.1` → `X.1.1`, with a
`parse_depth` that counts levels. That hierarchy does not exist anywhere in the codebase.

Building depth and lane limits now would mean either computing them from a hierarchy that
is not there, or inventing a **fourth** tether representation. The operator's instruction
was to unify rather than defer: *"id rather stay on track by getting everything to honest
states along the way rather than defer things till later."*

So task #4 was removed and replaced by 4a–4g. This is the record of why.

---

## What was found: three representations of one identifier

| # | Where | Format | Scope | Exists? |
|---|---|---|---|---|
| 1 | `design.md`, `tasks.md`, `IMPLEMENTATION_STATUS.md`, `Multi_Lane_Flow_Builder_Implementation_Plan.md` | `X`, `X.1`, `X.1.1` via `TetherIDGenerator` + `parse_depth` | one per **lane**, hierarchical | **No. Zero Python files.** |
| 2 | `maccre_core/orchestration/flow_engine.py` `_default_tether_id` | `scatter_<sha1[:8]>` | one per **scatter group** — written to the scatter, every lane, and the merge | Yes, this is what runs |
| 3 | `maccre_tui/widgets/macronode_workshop.py` | `tether_a`, `tether_b`, … from `self._tether_counter` | one per scatter, per-widget counter | Yes |

This is **Doctrine 4's named incident, repeated.** The doctrine records: *"a TUI built node
ids as `NAME_{i}` while the engine built `NAME_S{i}`. Harmless while the TUI only drew
them; wrong the moment anything acted on what was drawn."* The same two components have
now done the same thing to tether IDs — and unlike node ids, the tether is **acted on**:
it is what the fan-in gather gate scopes by.

Representations 2 and 3 already collide in production. `topology_engine.py` carries a
comment about a fixed defect where a `CTRL_SCATTER` saved with a blank Tether ID field
carried `tether_id: ""` in its step config and **overwrote the real tether the auto-wrap
had written into the CSV**. That is the collision surface; the blank case was fixed, the
*non-blank* case still means the TUI's `tether_a` wins over the engine's `scatter_<sha1>`.

### Doctrine 5: the documentation claims it is done

`IMPLEMENTATION_STATUS.md` does not merely describe the hierarchy as planned. It marks it
complete, with line counts and an integration point:

- line 33: `✅ **Task 2.1**: Implemented TetherIDGenerator (6h)`
- line 35: `- Supports X → X.1, X.2 → X.1.1, X.1.2`
- line 39: `✅ **Task 2.2**: Assign Tether IDs on Flow Build (8h)`
- line 183: `- Depth parsing: parse_depth("X.1.2") → 2`
- line 233: `- TetherIDGenerator class (88 lines)`
- line 248: `- TetherIDGenerator integration (5 lines)`
- line 400: `- maccre_core.orchestration.flow_engine: TetherIDGenerator`

`grep TetherIDGenerator **/*.py` returns **no matches**. A second copy of the same claims
sits in `.kiro/specs/phase-6-13-multi-flow-lane/IMPLEMENTATION_STATUS.md`.

This is the `--smart` incident again, and worse in degree: a flag documented as
"Implemented" and never read cost a wrong belief about one option. Here an entire
identifier scheme is documented as an 88-line class at a named import path, and a reader
planning work against it — which is exactly what task #4 was — designs against a fiction.

---

## The defect this exposed, which I authored

`total_sum_readout` (written earlier this phase for Requirement 33) computes:

```python
lane_count = len(tethers)                                    # distinct Tether_ID values
"expected_peak_concurrency": min(lane_count, resolve_scatter_cap(max_workers))
```

Since the engine writes **one** tether across the whole scatter group, I reproduced this
against rows built the way the auto-wrap builds them — an 8-agent scatter, its 8 lanes, and
a merge:

```
engine tether for an 8-agent scatter: scatter_ef3031e2
source                : hydrated_topology
node_count            : 10
lane_count            : 1     <-- Requirement 33.5 "the number of Flow Lanes"
lane_tether_ids       : ['scatter_ef3031e2']
nodes_per_lane        : {'scatter_ef3031e2': 10}
expected_peak_concurr : 1     <-- max_workers=8 was passed; the pool will open 8
```

**Live corroboration.** Run `job_20260901-205047-40sp` recorded tether `scatter_84fe89ba`
on all eight lanes *and* the merge. The flat model is not a reading of the code, it is
observed behaviour.

Two things follow, and both are mine to own:

1. The pre-launch readout tells the operator an 8-way scatter will peak at **one thread**.
   My Requirement 33 register entry says I caught an *over*-promise in
   `expected_peak_concurrency` and fixed it. I left an *under*-promise, because the lane
   model underneath was wrong. Principle 3 in the one document the operator consults
   *instead of* watching the run.
2. **No test caught it** because every test supplies one-tether-per-lane rows — the model
   the spec describes, not the model the engine implements. Principle 6: the suite was
   green over a defect living in the seam between the spec's model and the engine's.

### A correction to the Requirements 29/31/32 record

I recorded those functions as *implemented and covered, not wired*. That was too kind.
`validate_gather_reachability`, `terminal_outputs_for_step` and `evaluate_wait` all take
`lanes={tether_id: [node, ...]}` — **one tether per lane**. Under the live model they would
receive a single entry for an eight-lane scatter, so `terminal_outputs_for_step` would
report one lane output where there are eight, and `evaluate_wait` could not address a lane
at all.

They were not merely **unwired**. They were **unwireable**, and the reason was not visible
from inside those tasks. Recorded here and carried into the register.

---

## Why unification is sequenced first

Requirement 19's two limits are uncomputable from the live format:

- **19.2, depth ≥ 3 warning** — `scatter_ef3031e2` has no depth. There is no level to count.
- **19.3, refuse > 64 concurrent lanes** — lanes are not individually identified, so they
  cannot be counted across nesting.

And wiring Requirements 29/31/32 has the same prerequisite. One change unblocks four
requirements; doing Requirement 19 first would produce a fourth representation and deepen
the divergence it is supposed to measure.

### The property that makes this safe: `lane_group`

The flat tether **is** the fan-in scope. Today the merge gathers by tether equality, and
all lanes plus the merge share one value. Naively giving each lane its own tether would
break the gather gate — and *that* is the named Principle 2 incident: *"a blanked tether id
put a scatter and its merge in different scopes, so the gather gate could never open and an
8-lane run deadlocked."* This is the highest-risk surface in the repository, and the cost of
getting it wrong is already measured.

The hierarchy supplies both facts at once, which the flat form could not:

- **lane identity** — `X.1` is *this* lane
- **gather scope** — `lane_group("X.1") == "X"` is *this scatter*

So the gather gate changes from *tether equality* to *same lane group*. And the seam
defines:

```
lane_group(t) = parent of t   for a hierarchical id   ("X.1"          -> "X")
lane_group(t) = t itself      for a flat/legacy id    ("scatter_abc1" -> "scatter_abc1")
```

**Every topology already on disk keeps working unchanged**, because for a flat tether
`lane_group(t) == t` and "same lane group" degenerates to the equality the gate already
performs. That is what makes this a migration rather than a break, and it is the reason
4b (build the seam) must land before 4c (change the gate).

---

## The revised task list

Task #4 removed. Replaced by:

| # | Task | Why it is in this position |
|---|---|---|
| 4a | Record the divergence and this revision | Documenting the task-list change is itself a deliverable, per the operator's instruction |
| 4b | Build the one tether seam — hierarchical IDs, depth, `lane_group` | Pure module, no I/O. `lane_group`'s legacy passthrough is what makes 4c safe |
| 4c | Wire the engine, without breaking the gather gate | Highest-risk change in the repo. Needs the full gate including `omni smoke` |
| 4d | Wire the TUI so it stops minting its own IDs | Closes the Doctrine 4 collision at the source |
| 4e | Fix `total_sum_readout`'s lane count and peak concurrency | The defect above. Truthful only once per-lane tethers exist |
| 4f | Correct the false completion claims | Doctrine 5. Append-only correction, never deletion |
| 4g | Requirement 19 — depth and lane limits | Only now can "depth" and "64 lanes" be computed from something real |

**"Honestly ready" for 4g means:** one tether generator with one caller path, per-lane
tether IDs observable in `task_queue`, the gather gate proven still to close on an 8-lane
scatter, `total_sum_readout` reporting 8 lanes and 8-way peak concurrency for an 8-agent
scatter, and the design documents no longer claiming a class that does not exist.

---

## What is NOT claimed here

- **No code has changed yet.** This document is 4a. 4b–4g are outstanding.
- **The gather-gate change is not yet proven safe.** The `lane_group` argument above is
  reasoning, not a test result. It becomes a finding when 4c has an 8-lane gather closing
  in a live run, and until then it is a design intent.
- **The 64-lane limit is not validated as a number.** It comes from Requirement 19.3 as
  authored. It is unrelated to `MAX_SCATTER_AGENTS` (8) and `SCATTER_HARD_CAP` (12), which
  bound *threads*, not lanes — `flow_engine`'s own docstring already distinguishes the two,
  and that distinction is correct and should survive unification.
- **No live run has happened since 2026-09-05's telemetry work**, so the Requirement 34.1
  baseline remains blocked and unaffected by this decision.
