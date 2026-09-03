# Phase 6.12 — Parallel Agent Execution: Closeout

**Date:** 2026-08-30
**Domain:** `maccre_core/orchestration/`, `maccre_tui/`
**Baseline:** `f7b326f` on `main` (Aug 22 rollback target `a9f96dba`)
**Status:** Complete. Phase 6.13 (WAL sharding) gated — criteria at the end.

---

## What shipped

`CTRL_SCATTER` already fanned N tagged rows into `task_queue` correctly. What was
missing was anything to drain them in parallel: `flow_engine` ran
`while ...: worker.execute_cycle()` on one thread, so an 8-agent scatter took eight
sequential LLM round trips. The fan-out was real; the parallelism never was.

Node execution now runs on a demand-scaled `DynamicSwarmPool` (0 → N → 0). A linear
step runs on exactly one thread; a scatter step scales to its slotted agent count
and retires back to zero.

### Verification gate

| Gate | Result |
|---|---|
| `omni qa` (whole project, Ruff + Pyright) | PASS |
| `pytest tests` | **460 collected / 460 passed** |
| `omni smoke` (live Gemma inference, $0) | ALL CHECKS PASSED |

Test count went from **zero runnable** at the start (a single orphaned module
aborted collection repo-wide) to 460.

### The deliverable, proven

`tests/test_scatter_concurrency.py` proves 8-way concurrency with a
`threading.Barrier(8)`: every lane blocks on it, so the run can only complete if all
eight lanes are genuinely in flight at the same instant. A pool one thread short
deadlocks the barrier and fails loudly.

This replaced peak-counting, which conflated two different questions — *can* the
pool run N lanes at once (design) versus *does it reach N before the first lane
finishes* (timing) — and produced noisy results (4-lane measured 4 then 3; 8-lane 6,
7, then 5). The barrier has no timing assumptions. Wall-clock speedup is asserted
separately, since a barrier releases all lanes together and so says nothing about
elapsed time.

---

## State contract

| Object | Owner | Observers | Mutation rights |
|---|---|---|---|
| `cancel_event` | TUI (`nexus_plex`) | `flow_engine`, `DynamicSwarmPool`, workers | **Owner only** |
| `pause_event` | TUI (`nexus_plex`) | `flow_engine`, pool, workers | **Owner only** — one accepted violation, below |
| `DynamicSwarmPool._shutdown` | the pool | its own worker threads | Pool only (it created it) |
| `task_queue` row ownership | `LocalMessageBroker.fetch_and_lock_task` | everything else | The atomic `BEGIN EXCLUSIVE` claim is the **sole** authority |
| `TopologyEngine._overlays` | each engine instance | — | Its owner; the pool applies overlays per worker |
| `concurrency._SINKS` | `concurrency` module | — | Each thread touches only its own entry |

The observer rule is enforced by tests, not just documented: `TripwireEvent`
subclasses in `test_cycle_outcome.py` and `test_swarm_pool.py` assert zero
`.set()`/`.clear()` calls on received events, plus source guards banning the literal
strings `stop_event.set()`, `pause_event.clear()` and so on from the pool.

This matters because the aborted first attempt tried to retire threads by setting a
*caller's* stop event — on an object whose identity did not even match what the
worker closures had captured, so retirement never worked at all.

### Accepted violation

`flow_engine._wait_for_hitl_resume` calls `pause_event.clear()` on a TUI-owned
event. Preserved deliberately, documented at the call site, asserted by a test so it
stays deliberate.

The TUI's contract is "`pause_event` set == running", and the engine clears it to
park itself until the TUI re-sets it after writing `HITL_injection.md`. Removing the
`clear()` without simultaneously moving it into the TUI's `hitl_callback` would make
the engine spin straight past the HITL gate and resume with **no operator input** —
precisely the silent-skip class that caused the rollback.

Correct fix: the owner clears its own event inside `hitl_callback`. That is a TUI
change, deliberately not bundled into this refactor.

---

## Defects found and fixed

Fourteen, of which **nine were pre-existing** and latent rather than anything the
parallelism introduced. Sequential execution had been hiding them.

### Would have caused duplicate execution or data loss

**Shared SQLite connection across all threads** (`local_broker`). A connection holds
at most one transaction, so `BEGIN EXCLUSIVE` isolated nothing. Measured with a
4-thread / 12-task probe: **15 claims for 12 tasks — three tasks handed to two
workers each** — plus three threads dead with *"cannot start a transaction within a
transaction"*. Connections are now thread-local. Had the pool been wired onto the
baseline broker, an 8-agent scatter would have produced duplicate agent executions,
duplicate ledger writes and duplicate API spend.

**Mid-scan `commit()` in the atomic claim** (`local_broker`). Committing after
cancelling an upstream-failed task ended the exclusive transaction while the loop
kept iterating, so the later claim `UPDATE` ran unprotected and the TOCTOU race the
method exists to prevent came back.

**Torn unified ledger** (`flow_engine`). `swarm_worker` regenerates the ledger on
every node completion and hands the result straight to `route_task` as the *next*
node's input payload. A truncated read there does not raise — it silently feeds a
half-empty document to the next agent. Generation is now serialised per job and
written via `os.replace`.

**Lost context-cache registry entries** (`cache_manager`). A read-modify-write with
a network upload in the middle. Measured with 8 threads: **8 uploads for one
identical payload** (the `full_copy` scatter case, where every lane gets the same
context) and **1 of 8 registry entries surviving — seven paid caches leaked
untracked**. Now deduped per payload hash, with a re-read before insert.

**`_load_registry` silently wiping the registry.** It swallowed every exception and
returned `{}`, which the next save persisted over live data. One torn read meant
total loss with nothing logged.

### Would have corrupted logs or the display

**Global `sys.stdout` swap per node** (`swarm_worker`). `DynamicStreamHandler.emit()`
re-reads `sys.stdout` on *every* record, and `swarm_worker` contains no bare
`print()` — so the global swap was not an edge case in the logging path, it *was*
the logging path. Two concurrent nodes meant both nodes' output landing in whichever
log won the race while the loser's stayed empty. Replaced with per-thread routing
installed once and never reassigned.

**Double-open of the same log file.** Two `_FileTee` objects opened one path with
mode `"w"`; constructing the second truncated the first. One sink now serves both
streams.

**`setup_session_loggers` handler churn.** It closed and re-added every
`FileHandler` on a *shared* logger, and `execute_cycle` calls it on every claim —
so a second worker would close handlers a first was mid-write through. Now
idempotent per session. This also explains the three duplicate `TOOL_FIRED` rows in
the recorded baseline job.

**Indistinguishable worker identity.** A module-level `AGENT_ID` meant all eight
workers wrote the same `locked_by`, leaving no way to attribute a claim or a log
line.

### Would have silently dropped configuration

**Step config discarded after 5 seconds** (`topology_engine`).
`merge_config_overlay` wrote into `_cached_graph`, which `get_topology()` rebuilds
from disk once the 5 s TTL expires. Any node reached later ran **without its
configuration**, unlogged. Under a scatter, 5 s is one LLM call. Overlays are now
recorded separately and re-applied after every reload.

**Overlays reaching at most one worker.** Each worker owns its own `TopologyEngine`,
so an overlay applied to one is invisible to the others. The pool now applies them
to every worker it builds.

**`resume_flow` never applying step config at all.** The overlay logic lived inline
in `execute_flow` only, so a resumed flow ran its control nodes bare. Both paths now
share one driver.

### Found by the concurrency tests themselves

**Off-by-one in scaling.** `_scale_to_demand` compared the ready-task count against
*all* active workers, but a task being executed is `locked`, not `open` — so the
worker occupying lane 1 counted as spare capacity for lane 1. The pool always
settled one thread short: 8-lane reached 7, 4-lane reached 3.

**Demand-estimator thrash.** `count_ready_tasks` polled every 20 ms; each estimate
scans open rows and runs a Gather Gate lookup per row, and those reads contend with
the workers' `BEGIN EXCLUSIVE` claims. Measured: an 8-lane scatter took **4.25 s of
wall clock for 2.0 s of work — slower than sequential** — at peak concurrency 4.
Estimation is now throttled to 0.25 s while polling stays fast, so cancellation and
drain detection remain responsive. Same test now runs in 1.26 s.

**Scaling on a stale estimate.** Pairing a cached `ready` count with a live `active`
count double-counts: a worker spawned moments ago has not claimed yet, the cached
count still includes the task it is about to take, and the pool spawns a second
worker for work already spoken for. A linear 3-step flow opened two threads. The
pool now refuses to scale on a stale estimate.

### Introduced by this phase, then fixed

**Preflight hard-blocking every control-node flow.** `TopologyEngine.validate()`
demanded a system prompt and a model of every node. A `CTRL_*` node has
`Agent_Name=SYSTEM`, no persona and `Model_Override=none` *by design* — it runs a
deterministic handler and never reaches an LLM — so it collected two spurious
`ERROR`s. This was masked for review nodes, which preflight used to skip outright;
removing that bypass turned the latent rule into a hard block, because
`nexus_plex.py:4706` gates launch on `report.is_ok` and forces a "Proceed Anyway"
click. **That would have blocked the Phase 4.99 certification flow.** The exemption
is scoped to the two agent-shaped rules only — temperature and DAG integrity still
apply, which matters because control-node `next_node` is now configurable.

---

## Corrections to the rollback record

Two claims in `ROLLBACK_2026-08-29_PHASE_6.12_FAILURE.md` do not survive contact
with the source. Recorded so the next session does not act on bad premises.

**The `CTRL_REVIEW` hardcode was not introduced by Phase 6.12 and was not removed by
the rollback.** The document contrasts a "Before (Phase 6.12 — Broken)" hardcode
against an "After (Aug 19 — Working)" registry load. The rolled-back tree still
contained that hardcode at three sites, and the verified baseline job passed *with
it present*. Task A8 was therefore a doctrine and extensibility fix, not a bug fix.

**`flow_vector` telemetry is not populated.** The document's validation plan expects
a `flow_vector` value in `system_logs.db`. The baseline job has exactly three rows,
all `TOOL_FIRED` for `setup_session_loggers`, all with `flow_vector = ""`. There are
no `NODE_ROUTED` events. Any success criterion phrased in terms of `flow_vector`
cannot be evaluated today; the filesystem ledger is the authoritative evidence.

---

## Deviations from the approved plan

**A6 — did not debounce ledger regeneration.** The plan called for debouncing the
per-node-completion call. A debounce would skip regeneration while still returning
the path, so the caller would route the *previous* snapshot, missing the output of
the node that just finished. That trades correctness for CPU on the one artifact
that can least afford it. Serialisation alone is the correct fix; the write is
atomic, so readers are never blocked.

**C1 — derived the active-node set rather than tracking one.** The plan suggested a
tracked set. `_tick_animation` and `mark_all_completed` already read node state
directly, so a parallel set that drifted would leave a node pulsing forever or none
at all. Topologies are small; the scan is cheaper than the divergence risk.

**A8 — lane-internal review continuation is enabled, not exercised.** The plan
wanted `Next_Node` derived from flow position so a review node inside a scatter lane
continues the lane. For a top-level step, `END` is correct — it terminates the
macronode's internal DAG while the outer step loop advances. What the refactor adds
is a config-driven `next_node`, which is the mechanism a mid-lane review node needs.
Reaching it requires 6.13 multi-lane authoring.

---

## Known-latent, deliberately not wired

`local_broker.reclaim_zombie_locks` is **uncalled and unsafe as written**, and now
carries a `.. warning::` saying so. Its age test uses `created_at` — when the row
was *enqueued* — not lock-acquisition time, because there is no `locked_at` column.
Any task that waited longer than `timeout_seconds` (default 15 s) before being
claimed is treated as a zombie the instant a live worker picks it up, reset to
`open`, claimed again, and **executed twice**.

Harmless sequentially, where a claim followed enqueue almost immediately. Dangerous
at 8-wide scatter, where lanes routinely sit queued far longer than 15 s and a single
LLM call alone exceeds it. Do not wire it into the pool without first adding a
`locked_at` timestamp written by `fetch_and_lock_task` and moving the age test onto
it.

---

## Hard boundary

`task_queue` has `UNIQUE(job_id, current_node)`. Two scatter lanes given the same
node name inside one job collapse to a single row. This is a constraint to design
around, not a bug to fix in 6.12; `test_broker_contract.py` records it so 6.13's
multi-lane authoring cannot forget it.

---

## Phase 6.13 gate (WAL sharding)

Do not start until **all three** hold:

1. The mandatory integration tests pass **3 consecutive clean runs** at 8 agents.
2. **Zero** `database is locked` in telemetry across those runs.
3. Peak concurrency ≥ 8 confirmed.

If SQLite write contention is the *measured* bottleneck, 6.13 is justified.
Otherwise it is premature — and note that the largest throughput win in this phase
came from removing contention (throttling the demand estimator), not from adding
capacity.

`PRAGMA busy_timeout` is 5000 ms. Measure it under an 8-agent load before tuning.

---

## Process note

`omni qa` caught three defects that scoped `ruff`/`pyright` invocations had missed,
including one I introduced (a bulk edit that reached an `if __name__ == "__main__":`
block where `self` does not exist — which pytest could never have caught, since that
block is never imported). Two of the three "hangs" investigated during this work
were pytest's block-buffered file output, not hangs. `python -u` and
`-o faulthandler_timeout=N` give a definitive answer; `pytest-timeout` is not
installed.

The doctrine now carries this: `.kiro/steering/omni_pipeline_mandate.md`
(always-applied) records where omni lives, why a workspace search for it finds
nothing, and that `omni qa` has no pytest stage — the exact gap that let the previous
attempt report "all checks pass" while the suite could not be collected.
