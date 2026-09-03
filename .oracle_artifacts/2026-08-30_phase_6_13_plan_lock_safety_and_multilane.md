# Plan — Lock-Lifecycle Safety, Multi-Lane Authoring, and the Path to User Testing

**Date:** 2026-08-30
**Supersedes:** the "Phase 6.13" multi-lane draft in `6.12Troubles.md`
**Predecessor:** `.oracle_artifacts/2026-08-30_phase_6_12_parallel_execution_closeout.md`

---

## Naming: "6.13" currently means two different things

| Label | Document | Content |
|---|---|---|
| Era 2 **§6.13** | `Era2_architectural_roadmap.md` | WAL Sharding by Flow Line |
| "Phase 6.13" | `6.12Troubles.md` (draft) | Multi-Flow-Line Authoring & Visualization |

This plan treats **§6.13 = WAL sharding** (the roadmap is canonical) and calls the
authoring work **§6.14 Multi-Lane Authoring**. §6.13 stays gated on measurement; see
the closeout artifact for why its premise is currently unevidenced.

---

## Decisions locked

1. **Track B is engine-first.** Heterogeneous lane *execution* lands and is demoable
   before any authoring UI. Building an authoring experience for lanes the engine
   cannot execute is how the last attempt failed.
2. **UT-0 uses `gemini-3.7-flash`.** Cost accepted as minimal.
3. **Reclaim is made safe but not wired in.** A1–A4 fix the mechanism; whether to
   enable automatic reclaim is decided from UT-0's measured worker-death rate.

---

## Model probe verification (UT-0 prerequisite) — DONE

Live probe queried directly, since `scripts/model_capability_map.json` is only a
cold-start fallback and is 2.5-era.

**Result: the probe is healthy. 53 models, and it does see 3.7.**

```
--- gemini-3.x entries (live) ---
  models/gemini-3-flash-preview        models/gemini-3.1-pro-preview
  models/gemini-3.1-flash-lite         models/gemini-3.5-flash
  models/gemini-3.1-flash-lite-preview models/gemini-3.5-flash-lite
  models/gemini-3.1-flash-live-preview models/gemini-3.6-flash
  models/gemini-3.1-flash-tts-preview  models/gemini-3.7-flash   ← UT-0 target
  ...
```

`gemini-3.7-flash` is confirmed available. UT-0 is unblocked on model availability.

### Gap found while verifying (small, real)

`model_registry._FALLBACK_CHAINS` is hand-maintained and stops at **3.1**. The lookup
is:

```python
return _FALLBACK_CHAINS.get(normalized, [normalized])
```

A model absent from that table gets a chain of **one — itself — i.e. no failover at
all**. Live probe data supersedes the table, so this only bites when the probe fails.
But in that degraded mode a `gemini-3.7-flash` run has no fallback.

This is the same staleness class as the hand-maintained `special_nodes` list fixed in
Task A8: a literal table shadowing a registry that already knows better. Task **A6**
below.

---

## Track A — Lock lifecycle correctness

Must land before any user runs an 8-agent flow.

### The bug that makes this urgent

`execute_cycle`'s outer `except` routes a failed task to FAILED — but that
`route_task` call is **not itself guarded** and uses several locals pyright already
flags `possibly-unbound` (`flow_vector` among them). If it raises, the task stays
`locked` forever.

Under the pool that is worse than it was sequentially:

1. `_worker_loop` catches the exception, records it, retires the slot.
2. `_run_worker_pool`'s `is_drained` counts only `open` rows. A stranded `locked` row
   is not open.
3. `run_until_drained` returns `drained=True`; the step returns `"completed"`.

**Net effect: the flow reports success with a node that never ran.** That is the
rollback's signature failure, reachable today.

Separately: `release_task` is defined, its docstring says "used in worker finally
blocks", and **it is called nowhere in the codebase.** That finally block does not
exist.

### Task A1: Add `locked_at` and stamp it on claim
Add `locked_at TIMESTAMP` to the `task_queue` schema plus an `ALTER TABLE` migration
for existing databases. Stamp it inside `fetch_and_lock_task`'s claim `UPDATE`, in the
same `BEGIN EXCLUSIVE` transaction as the status change, so status and timestamp
cannot diverge.
**Tests:** claiming sets `locked_at`; it differs from `created_at` for a task that
waited in the queue; the migration is idempotent against a pre-existing DB.
**Demo:** `task_queue` can answer "how long has this lock been held" for the first
time.

### Task A2: Heartbeat, so a slow node is not mistaken for a dead one
Add `heartbeat_task(row_id)` to the `MessageBroker` ABC, `LocalMessageBroker` and
`MockMessageBroker` — keeping Task A2's signature-parity discipline, which has its own
guard test. Scope it `WHERE id = ? AND lock_status = 'locked'` so it can never
resurrect a completed row.

Add a `task_heartbeat(broker, row_id, interval)` context manager in `concurrency.py`
running a daemon thread, and wrap node execution in `execute_cycle` with it. A daemon
thread is required, not optional: a blocking 30-second LLM call cannot heartbeat from
its own call stack.
**Tests:** heartbeat advances `locked_at`; it does **not** touch a `completed` row;
the thread stops on context exit; cost is ~1.6 writes/sec at 8 workers on a 5 s
interval.
**Demo:** A node running longer than the reclaim timeout keeps its lock.

### Task A3: Fix `reclaim_zombie_locks`
Age on `locked_at`, not `created_at`. Add an optional `job_id` scope so reclaim cannot
reach across concurrent jobs. Raise the default timeout well above any plausible node
duration — with a heartbeat in place, staleness becomes a genuine death signal rather
than a slowness signal. Replace the `.. warning::` with the real contract.
**Tests:** a queued-then-claimed task is **not** reclaimed (the original bug, as an
explicit regression test); a stale heartbeat **is** reclaimed; a live heartbeat is
not; job scoping holds.
**Demo:** The 12-lane case that previously double-executed lane 9 leaves it alone.

### Task A4: Guarantee a claimed task is always resolved
Wrap the FAILED-route inside `execute_cycle`'s outer `except` in its own `try`,
falling back to `release_task(row_id)` — finally giving that method the caller its
docstring has always claimed. Log critically on that path.
**Tests:** inject a failure into `route_task` during the failure path and assert the
row ends `open`, not `locked`; assert no path leaves a claimed row unresolved.
**Demo:** A worker dying mid-node returns its task to the queue instead of stranding
it.

### Task A5: Make the drain check honest (no auto-reclaim yet)
Per decision 3, do **not** wire automatic reclaim. Instead make the failure *loud*:
treat "locked rows exist, zero workers alive" as **not drained**, and after a grace
period return a distinct `stalled` status that `_run_worker_pool` surfaces as an error
rather than `"completed"`.

This is the better-informed option. It converts a silent success into a visible
failure, and UT-0 then tells us whether it ever fires — which is exactly the data
needed to decide on auto-reclaim.
**Tests:** orphan a `locked` row with no workers alive, assert the step does **not**
report completed and does report stalled; assert a healthy flow never stalls.
**Demo:** The rollback's signature failure becomes impossible to hide.

### Task A6: Registry-derive the failover chains
Build the text-generation fallback chain from live registry data ordered by
capability, and keep the hardcoded table strictly as a cold-start fallback. Add a
test asserting every model in the table exists in the live surface list, so the table
cannot silently rot again.
**Tests:** `gemini-3.7-flash` resolves to a chain of length > 1; an unknown model
still degrades safely to itself.
**Demo:** A 3.7-flash run has real failover even when the probe is unavailable.

---

## UT-0 — Instrumented live 8-agent run

Engineering measurement, not user testing. Gated on Track A.

**Model:** `gemini-3.7-flash`. **Setup:** one 8-lane scatter, live inference.

**Instrument and record:**

| Metric | Why |
|---|---|
| `database is locked` count | Decides §6.13. Gate criterion #2 |
| `busy_timeout` retries / write conflicts | The direct contention measure |
| Peak concurrency | Gate criterion #3 |
| Wall clock vs sequential estimate | Real speedup, not simulated |
| **Worker deaths / stall events** | **Decides whether to enable auto-reclaim (decision 3)** |
| Cost per run | Budget baseline for UT-1 |
| Per-node latency spread | Whether 8-way bursts trip provider throttling |

Repeat 3× consecutively for gate criterion #1 — which the stubbed test suite does
**not** satisfy, since it has never made a real inference call under concurrency.

**Outputs:** a §6.13 go/no-go, and an auto-reclaim go/no-go.

---

## Track B — §6.14 Multi-Lane Authoring (engine-first)

### The ceiling being lifted
Scatter fans out 8 agents, but every lane is exactly one node, so every lane does the
same thing. Users cannot author per-lane topologies, see which lane a node belongs
to, or reference nodes by tether.

### B1: `FlowStep.children` + `lane_metadata`
`children: list[list[FlowStep]]`, `lane_metadata: dict[int, dict]`. The earlier
attempt at this (`TetherIDGenerator`) was rolled back and sits quarantined in
`_archive/phase_6_12_aborted/` — **re-derive it, do not copy it.**
**Tests:** nested round-trip through `to_dict`/`from_dict`; the A0 baseline's 3-step
flow still round-trips byte-identically.
**Demo:** A scatter step persists four empty lanes across save and reload.

### B2: Hierarchical tether IDs
`X → X.1, X.2, X.3`, nesting for scatter-within-scatter. Lane auto-naming
`{agent}.{tether}`, user-editable.
**Tests:** uniqueness under nesting; stability across save/load; and the recorded hard
boundary — `UNIQUE(job_id, current_node)` means lane node IDs **must** embed the
tether or same-named lanes collapse into one row. `test_broker_contract.py` already
records that constraint; extend it here.
**Demo:** A nested scatter produces collision-free lane identifiers.

### B3: Heterogeneous lane execution — the actual unlock
Make the scatter auto-wrap emit a per-lane **chain** from `step.children` with
tether-scoped node IDs, and make `CTRL_MERGE` wait on each lane's **terminal** node
rather than its single node.
**Tests:** three lanes of differing length converge correctly; the gather gate waits
for every terminal; an empty lane does not stall the merge; peak concurrency still
reaches lane count.
**Demo:** Three lanes with different topologies execute concurrently and merge with
the right artifacts. **This is the demo that proves the ceiling is lifted, and it
should land on its own before any UI work.**

### B4: `NodeConfigModal` refresh fixes
`container.refresh(layout=True)` after dynamic mount. Small, isolated, immediately
visible.
**Demo:** Agent slots and buttons appear at once; slotted agents show in the flow
sequence after save.

### B5: Multi-lane rendering in Active Flow Sequence
Collapsed by default; user-toggled vertical expansion; dotted filler aligning lanes
temporally at the merge; per-lane and global collapse. The multi-active visualiser
from Task C1 already supplies the "which nodes are live" signal.
**Tests:** widget tests for lanes of differing length; expand/collapse state; 8 lanes
render within the pane.
**Demo:** An 8-lane scatter's temporal misalignment is visually obvious.

### B6: Per-lane authoring
Double-click a node → catalog glows targeted → the next node added inserts after that
node on that lane. Needs `_selected_lane` / `_selected_node_id` selection state.
**Demo:** A user builds two lanes with different topologies and runs them.

### Held behind UT-1 feedback
- **B7** Enhanced `CTRL_MERGE`: synthesis agent, timeout, proceed-on-partial, straggler logging
- **B8** `NodeAppendix` structured 2D topology injection (ALL / Scoped)
- **B9** Tether hover tooltips + SHIFT+F7 notes modal

None gate user testing.

---

## User test rounds

### UT-1 — Parallel Execution Certification (Phase 4.99)
Gated on Track A + UT-0.

1. Linear 3-step flow — completes, payload passes between steps, exactly one thread.
2. 4-agent scatter — four lanes visible, `4/8` readout, merge waits for all.
3. 8-agent scatter — `8/8` readout, measured speedup over sequential.
4. `CTRL_REVIEW` mid-flow — pauses, HITL injection lands, step 3 consumes it.
5. Cancel mid-scatter — stops promptly, no orphaned rows.
6. **Kill a worker mid-node** — task is not stranded, flow either recovers or stalls
   loudly. *Only testable after Track A.*

### UT-2 — Multi-Lane Authoring
Gated on B1–B6.

1. Author 3 lanes with different topologies; verify each runs its own.
2. Insert a node into lane 2 only; verify lanes 1 and 3 unchanged.
3. Heterogeneous merge including one empty lane.
4. Nested scatter to whatever depth remains usable.
5. Save, reload, re-run — lane structure survives.

---

## Sizing

| Work | Estimate |
|---|---|
| Track A (A1–A6) | 1–2 days |
| UT-0 instrumented run ×3 | half a day |
| **UT-1 ready** | **~2–3 days** |
| Track B engine (B1–B3) | 3–4 days |
| Track B UI (B4–B6) | 3–5 days |
| **UT-2 ready** | **~2 weeks** |

---

## Standing constraints

- **`omni qa` is the gate**, whole project, after every change. It has no pytest
  stage — follow with `pytest tests` and check the **collected** count, then
  `omni smoke` for execution-path changes.
- `pyrightconfig.json` **excludes `maccre_tui`**, so TUI work is ruff-only. Widget
  tests and source guards are that layer's only real verification.
- Events: `cancel_event` and `pause_event` are **owned by the TUI**; engine, pool and
  workers may only read them. The pool owns `_shutdown` and may set only that.
- The `pause_event.clear()` inversion in `flow_engine._wait_for_hitl_resume` is
  accepted and test-asserted. The correct fix is a TUI change, out of scope here.
- `python -u` for pytest — redirected output is block-buffered, and
  `collected N items` with nothing after means *still running*, not hung.
  `-o faulthandler_timeout=N` is pytest's built-in; `pytest-timeout` is not installed.
