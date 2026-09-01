# Phase 6.12 — RESUME HERE

Written 2026-08-30 before a terminal restart. Everything below is on disk; nothing
depends on chat session memory.

---

## One-line status

Phases **6.12A, 6.12B and 6.12C are complete and were verified green**
(`omni qa` + 410 pytest + `omni smoke`). Phase **6.12D is in progress**: D1's test
file is written but **has never been run to completion**.

---

## First three commands after the restart

```powershell
cd B:\EXO_GANS
omni qa
.\.venv\Scripts\python.exe -u -m pytest tests\test_integration_mandatory.py -q --no-header -o faulthandler_timeout=120
.\.venv\Scripts\python.exe -u -m pytest tests -q --no-header -o faulthandler_timeout=180
```

Expected: `omni qa` passes. The full suite was **410 passed** before D1 was added;
D1 adds ~26 tests, so expect ~436 collected **if D1 is green**. D1 has never run,
so treat any failure there as new and unverified.

### Terminal lessons learned the hard way

- **`python -u`**, always. pytest output redirected to a file is block-buffered, so
  a file showing only `collected N items` means *still running*, **not hung**. This
  wasted real time twice.
- `-o faulthandler_timeout=N` is pytest's **built-in** faulthandler and dumps all
  thread stacks on a genuine overrun. `pytest-timeout` is **not installed**.
- The shell does **not** reliably execute multi-line `foreach` loops. One command
  per invocation.
- `test_swarm_pool.py::TestHaltPaths::test_timeout_is_reported_not_raised` legitimately
  takes ~30 s. The full suite is ~70 s. Slow is not hung.

---

## Uncommitted state

Nothing has been committed. `git status` will show a large working tree. Baseline is
`f7b326f` on `main`.

### Files created

Source:
- `maccre_core/orchestration/concurrency.py`
- `maccre_core/orchestration/swarm_pool.py`

Tests:
- `tests/test_broker_contract.py`
- `tests/test_concurrency_primitives.py`
- `tests/test_ctrl_review_baseline.py`
- `tests/test_cycle_outcome.py`
- `tests/test_flow_monitor_concurrency_readout.py`
- `tests/test_flow_pool_integration.py`
- `tests/test_integration_mandatory.py`  ← **NEVER RUN**
- `tests/test_ledger_concurrency.py`
- `tests/test_review_node_resolution.py`
- `tests/test_scatter_concurrency.py`
- `tests/test_shared_state_hazards.py`
- `tests/test_swarm_pool.py`
- `tests/test_topology_visualizer_multi_active.py`

Docs / steering:
- `.kiro/steering/omni_pipeline_mandate.md` (inclusion: always)
- `.oracle_artifacts/2026-08-29_phase_6_12_ctrl_review_baseline.md`
- `_archive/phase_6_12_aborted/README.md`

### Files modified

`maccre_core/logger.py`, `maccre_core/controlnode_registry.py`,
`maccre_core/maccre_router.py`, `maccre_core/orchestration/broker_interface.py`,
`maccre_core/orchestration/cache_manager.py`,
`maccre_core/orchestration/deterministic_nodes.py`,
`maccre_core/orchestration/flow_engine.py`,
`maccre_core/orchestration/local_broker.py`,
`maccre_core/orchestration/swarm_worker.py`,
`maccre_core/orchestration/topology_engine.py`,
`maccre_tui/nexus_plex.py`, `maccre_tui/undo_manager.py`,
`maccre_tui/widgets/flow_monitor_overlay.py`,
`maccre_tui/widgets/topology_visualizer.py`,
`tests/mocks/mock_broker.py`,
`.kiro/steering/orchestration_oracle_principles.md`

### Quarantined to `_archive/phase_6_12_aborted/`

`concurrency.py`, `swarm_pool.py` (the never-executed originals),
`node_history.py`, `topology_validator.py`, `test_flow_step_multi_lane.py`,
`test_topology_validator.py`. `_archive` is excluded from both `ruff.toml` and
`pyrightconfig.json`.

### Cleanup owed

`scratch/_d1_probe.py` is a throwaway probe and should be deleted. Its finding is
already recorded below.

---

## Exactly where D1 stopped

`tests/test_integration_mandatory.py` is written and covers all three checks
`orchestration_oracle_principles.md` mandates. It drives the **real**
`FlowRunner.execute_flow` against the per-test tmp datacenter — real broker, real
SQLite queue, real topology CSV, real `DynamicSwarmPool`, real routing, real ledger
generation — using `CTRL_*` steps so there is **no LLM call, no API key and no
cost**.

Four test classes:
1. `TestMandatoryMultiStepFlow` — 3 × `CTRL_ANCHOR`. Step loop doesn't break early,
   payload passes between steps, per-step ledgers written, queue drained, linear
   flow stays on slot 0.
2. `TestMandatoryReviewFlow` — `CTRL_ANCHOR → CTRL_REVIEW → CTRL_ANCHOR`.
   Reproduces the recorded baseline trace
   `CTRL_ANCHOR_S0 → CTRL_PAUSE_MANUAL_S1 → CTRL_ANCHOR_S2`.
3. `TestMandatoryScatterFlow` — scatter DAG through `execute_flow`. Depth of the
   concurrency proof stays in `tests/test_scatter_concurrency.py`.
4. `TestPreflightAcceptsControlNodes` — regression guard for the defect below.

### The one thing to watch in D1

`TestMandatoryReviewFlow` resumes the paused task **from a separate thread after a
0.4 s sleep**, deliberately. `_run_worker_pool` calls `hitl_callback(...)` and then
immediately calls `_wait_for_hitl_resume`, which **clears** `pause_event` before
waiting. A synchronous `pause_event.set()` inside the callback would therefore be
wiped and the flow would wait until its deadline. The real TUI has the same shape
(the callback opens a modal; the resume arrives later). If that test hangs, this is
why — the sleep may need to be longer than the pool's poll cadence, not shorter.

---

## Defect found and fixed while writing D1 — verify this survived

`TopologyEngine.validate()` demanded a system prompt **and** a model of every node.
A `CTRL_*` node has `Agent_Name=SYSTEM`, no persona and `Model_Override=none`
**by design** — it runs a handler in `deterministic_nodes.py` and never reaches an
LLM — so every control node collected two spurious `ERROR`s.

This was masked for review nodes because preflight used to skip them outright.
Task A8 removed that bypass, which turned the latent rule into a **hard block on
launch**: `nexus_plex.py:4706` gates on `not report.is_ok` and forces a
"Proceed Anyway" click. That would have blocked the Phase 4.99 certification flow
(Agent → CTRL_REVIEW → Agent).

**Measured before the fix:** 3 × `CTRL_ANCHOR` → `is_ok=False`, 3 errors.
Single `CTRL_REVIEW` → `is_ok=False`, 1 error.
**After:** all `is_ok=True`, 0 issues.

The fix is scoped to the two agent-shaped rules only — temperature and DAG
integrity still apply to control nodes, which matters because A8 made their
`next_node` configurable. Do **not** widen it to a blanket `continue`; there is a
test asserting exactly that.

---

## Remaining work

### D1 — run it, fix what breaks
Nothing else to write unless the run reveals problems.

### D2 — audit, don't duplicate
Confirm reverting any single A3–A7 fix turns a test red. Most coverage already
exists across `test_broker_contract`, `test_concurrency_primitives`,
`test_ledger_concurrency`, `test_shared_state_hazards`, `test_worker_identity`.
This is a gap audit, not new bulk.

### D3 — closeout
- `omni qa`, full pytest (check the **collected** count), `omni smoke`.
- Write the task artifact to `.oracle_artifacts/` including the state-contract
  table below.
- Append a ledger entry to
  `.agent/skills/Specialists/OrchestrationAndEngine_Oracle/task_ledger.md`.
- Record the Phase 6.13 gate criteria.

---

## State contract (for the D3 artifact)

| Object | Owner | Observers | Mutation rights |
|---|---|---|---|
| `cancel_event` | TUI (`nexus_plex`) | `flow_engine`, `DynamicSwarmPool`, workers | Owner only |
| `pause_event` | TUI (`nexus_plex`) | `flow_engine`, pool, workers | Owner only — **one accepted violation, below** |
| `DynamicSwarmPool._shutdown` | the pool | its own worker threads | Pool only (it created it) |
| `task_queue` row ownership | `LocalMessageBroker.fetch_and_lock_task` | everything else | The atomic `BEGIN EXCLUSIVE` claim is the sole authority |

### Accepted doctrine violation — carry this into the artifact

`flow_engine._wait_for_hitl_resume` calls `pause_event.clear()` on an event owned
by the TUI. Preserved deliberately and documented at the call site.

The TUI's contract is "`pause_event` set == running", and the engine clears it to
park itself until the TUI re-sets it after writing `HITL_injection.md`. Removing the
`clear()` without simultaneously moving it into the TUI's `hitl_callback` would make
the engine spin straight past the HITL gate and resume with **no operator input** —
precisely the silent-skip class that caused the Phase 6.12 rollback.

Correct fix: the owner clears its own event inside `hitl_callback`. That is a TUI
change, deliberately not bundled into the 6.12 refactor.

---

## Phase 6.13 gate (WAL sharding) — do not start until all three hold

1. D1 passes **3 consecutive clean runs** at 8 agents.
2. **Zero** `database is locked` in telemetry across those runs.
3. Peak concurrency ≥ 8 confirmed.

If SQLite write contention is the *measured* bottleneck, 6.13 is justified.
Otherwise it is premature.

Related, already recorded: `local_broker.reclaim_zombie_locks` is **uncalled and
unsafe as written**. Its age test uses `created_at` (enqueue time), not lock
acquisition — there is no `locked_at` column — so any task that waited longer than
`timeout_seconds` (default 15 s) before being claimed is treated as a zombie the
moment a live worker picks it up, reopened, and executed **twice**. Harmless while
uncalled. Do not wire it into the pool without first adding `locked_at`. There is a
`.. warning::` on the method.
