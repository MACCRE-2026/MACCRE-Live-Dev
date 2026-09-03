# 2026-09-01: F1 / F2 / F3 — The Pause Path

**Domain:** Orchestration & Engine (with one TUI change)
**Defects:** F1 (pause crashes the TUI), F2 (a held pool rebuilds workers forever),
F3 (a hold nobody can release ends in a false `completed`)
**Also closes:** register entry *A timed-out step does not stop the flow*
**Branch:** `phase/6.13-track-a-d-and-payload-lineage`
**Found by:** operator live testing, runs `job_20260901-204957-ico6` and
`job_20260901-205047-40sp`

---

## Summary

Three defects, one keypress. The operator pressed **pause** during an 8-agent
scatter and got a dead UI, a process burning 257 s of CPU, and a run that was one
hour of budget away from reporting success over an unexecuted merge.

They are worth reading in causal order rather than severity order, because each
enabled the next:

| # | Defect | What it did |
|---|---|---|
| **F1** | The VCR button's box was 4 cells against 4 cells of chrome | Rendering it in the paused state raised out of rich and killed the Textual app |
| **F2** | `PAUSED` and `IDLE` shared a retire branch | The supervisor rebuilt a full worker ~20×/s for as long as the flow was held |
| **F3** | `pause_event` is TUI-owned, and the TUI was dead | Nothing could release the hold; the pool waited out 3600 s, returned `timeout`, and **neither step loop acted on `timeout`** |

The operator's two runs were deliberately different — `ico6` **cancelled**, `40sp`
**paused** — which is what made the diagnosis fast. Cancel came out 9 completed / 1
cancelled with no orphans, i.e. **UT-1 test 5 passing**. Everything below is the
pause path only.

### A live confirmation that came free

Both runs are the first live evidence that **defect E1 is fixed**. Every lane
carries a distinct `output_path` naming its own ledger while `payload_path` is
uniformly the shared session ledger:

```
OSINT_Analyst_S0     payload=…/unified_session_ledger.md   output=…/OSINT_Analyst_S0_106.md
TopperBuddy_S0       payload=…/unified_session_ledger.md   output=…/TopperBuddy_S0_107.md
TopperAngry_S0       payload=…/unified_session_ledger.md   output=…/TopperAngry_S0_108.md
…8 lanes, 8 distinct outputs, 523 B – 22.7 KB on disk
```

Tether `scatter_84fe89ba` on all eight lanes **and** on `CTRL_MERGE_S0`, so D3c's
scope isolation is holding too.

**E2 is still unproven.** The merge never ran in either session, so there is no
`_merged.md` and no step boundary to observe. That remains the outstanding
obligation.

---

## F1 — the crash

`ValueError: range() arg 3 must not be zero`, from `rich._wrap.divide_line` →
`rich.cells.chop_cells`, rendering
`Button(id='btn-vcr', classes='vcr-btn--paused vcr-btn')`.

Pure box arithmetic:

```
content_width = outer - border(2) - padding(2)
outer 4  ->  content 0    <- chop_cells(word, 0) -> range(0, n, 0) -> ValueError
outer 6  ->  content 2    <- fixed
```

`MacroNodeWorkshop.DEFAULT_CSS` pinned `min-width: 4; max-width: 4`; all three
`.vcr-btn--*` rules in `nexus_plex.css` declare `border: solid`; Textual's `Button`
carries `padding: 0 1`. Environment: textual 8.2.7, rich 15.0.0.

**`max-width` is what bit.** `min-width: 4` alone would have been harmless — Textual
would have grown the button. The hard cap forced the box below its own chrome.

### Two hypotheses tried and discarded

1. *"The play glyph is too wide."* Both `⏸` (U+23F8) and `▶` (U+25B6) measure **1
   cell** under `rich.cells.cell_len`. Changing the label would have left the crash
   in place. Pinned by a test so it is not re-tried.
2. *"`pyrightconfig.json` excludes `maccre_tui`, which is why this escaped."* I said
   this earlier in the session and **withdrew it**. A content width of zero is a
   well-typed `int`; no type checker catches a value a library divides by.
   De-excluding the TUI is worth doing — measured at 112 real diagnostics, now its
   own register entry — and would not have found this.

### Which button, and why it mattered

There are **two** `#btn-vcr` declarations. The live one is `MacroNodeWorkshop`'s
(mounted at `nexus_plex.py:2896`). The other belongs to `FlowExecutionPanel`
(`nexus_plex.py:2743`), which is **defined and never instantiated** — and whose copy
inherits the safe `min-width: 8` from `nexus_plex.css`. Establishing which was live
was the step that made the arithmetic conclusive rather than plausible. The dead
duplicate now has its own register entry; it was not deleted in this pass.

---

## F2 — the runaway

The retire branch carried this comment:

> `# IDLE or PAUSED — nothing to do right now. Retire rather than spin; the
> supervisor re-spawns when demand returns.`

Correct for one of those outcomes and inverted for the other:

- **IDLE** — nothing claimable ⇒ demand 0 ⇒ a retired slot stays retired. Free.
- **PAUSED** — work exists, operator holding it. Demand is counted from *open* rows
  and a paused task is still open ⇒ demand stays high ⇒ the slot is refilled next
  tick. Each refill constructs a `TopologyEngine` **and** a `LocalMessageBroker` that
  runs schema DDL against the same SQLite file a claim needs.

### Measured, by reverting each half independently

| State | Worker constructions in 2 s @ 0.01 s tick |
|---|---|
| Both halves broken | **40, and unbounded** — scales with hold duration |
| Worker-hold only (scaler gate removed) | **8** — exactly `max_workers`, then the ceiling check bounds it |
| Both fixed | **≤ 2** |

Production ticks at 0.05 s and the operator's hold lasted minutes, which is the
thousands of cycles in their log. Either half alone would have prevented the
runaway; **the scaler gate is the load-bearing one.**

### The test that was already there

`test_a_cleared_pause_event_holds_execution` covered this exact path and **passed
throughout**, because it asserted that no *work* executed. Nothing asserted what the
pause **cost**. A correct assertion on the wrong axis is indistinguishable from
coverage — principle 6, in a single test.

---

## F3 — the false `completed`

Two holes.

**(a) The engine could not tell a long pause from an impossible one.** It still does
not guess; it **asks**. `run_until_drained` gained an optional `pause_owner_alive`
predicate, consulted *only while held*, and `nexus_plex` supplies
`lambda: self.is_running` at both call sites — the app being the only party that can
honestly answer. New `PoolResult.pause_abandoned` and a new `"abandoned"` step status
keep this distinct from a timeout: "your UI died" and "this node is slow" need
different responses.

`max_pause_seconds` exists as a backstop for callers with no liveness signal and is
**off by default on purpose**. Killing a flow because the operator went to lunch
would be worse than the defect it guards against.

**(b) `timeout` did not stop the flow.** Both loops branched on two of
`_run_worker_pool`'s four return values. The untested one fell through to the payload
capture, the step logged as complete, and the `finally` wrote `completed`. Nothing
was hidden — the status was in the function's own docstring. It simply had no branch.

Both loops now break on `("stalled", "timeout", "abandoned")`.

> **Operator authorisation.** The register held this at *Deferred (needs decision)*
> because it will fail flows that currently report success. Authorised in session on
> 2026-09-01 alongside F3, on the grounds that the two are one conversation.

### Two labels corrected while here

- `is_stalled = True` was being set for a timeout — an approximately-correct
  identifier that would have had a future reader believing a timed-out session
  stalled. Now `unfinished_as = pool_status`, and the `finally` logs it.
- `_wait_for_hitl_resume` returned a `bool` meaning *cancelled* **or** *timed out*
  **or** *there was no pause channel at all*, with the caller re-deriving which. It
  now returns the same status vocabulary as `_run_worker_pool`. A HITL gate with
  `pause_event=None` is `abandoned`, not `timeout`, because nothing can ever
  release it.

---

## Files Modified

| File | What changed |
|---|---|
| `maccre_core/orchestration/swarm_pool.py` | `_is_paused` seam; scaler declines while held; `PAUSED` split from `IDLE` with `pause_hold_seconds`; paused poll backoff; `PoolResult.pause_abandoned`; `pause_owner_alive` / `max_pause_seconds` |
| `maccre_core/orchestration/flow_engine.py` | both loops act on `timeout`/`abandoned`; `unfinished_as` replaces `is_stalled`; `_wait_for_hitl_resume` returns a status; `pause_owner_alive` threaded through `execute_flow`/`resume_flow`/`_run_worker_pool` |
| `maccre_tui/widgets/macronode_workshop.py` | VCR width 4 → 6, with the arithmetic recorded beside the number |
| `maccre_tui/nexus_plex.py` | `pause_owner_alive=lambda: self.is_running` at both flow call sites |
| `maccre_core/orchestration/datacenter_router.py` | `SUPERSEDED` header (see below) |
| `maccre_core/orchestration/hybrid_edge_sync.py` | corrected its false "Formerly" claim |
| `tests/test_swarm_pool.py` | 52 → 71 tests |
| `tests/test_flow_pool_integration.py` | 46 → 64 tests; four existing tests updated to the new HITL contract |
| `tests/test_vcr_transport_render.py` | **new**, 10 tests |

## Function Signatures Added / Changed

```python
# swarm_pool.py
@staticmethod
def _is_paused(pause_event: Optional[Any]) -> bool: ...

def run_until_drained(
    self, is_drained, pause_event=None, stop_event=None,
    timeout_seconds=3600.0, locked_probe=None, stall_grace_seconds=30.0,
    pause_owner_alive: Optional[Callable[[], bool]] = None,   # NEW
    max_pause_seconds: Optional[float] = None,                # NEW
) -> PoolResult: ...

DynamicSwarmPool(..., paused_poll_interval_seconds=0.25, pause_hold_seconds=5.0)

# flow_engine.py — return type changed from bool to a status string
@staticmethod
def _wait_for_hitl_resume(
    pause_event, cancel_event, deadline,
    pause_owner_alive: Callable[[], bool] | None = None,
) -> str:  # "resumed" | "cancelled" | "abandoned" | "timeout"
```

## State Contracts

No event ownership changed. The pool and the engine remain **observers** of
`pause_event` and `cancel_event`; the new `_is_paused` helper only reads. The
documented `_wait_for_hitl_resume` ownership inversion (the engine calling
`pause_event.clear()`) is untouched and still flagged at its call site.

| Object | Owner | Observers | Mutation rights |
|---|---|---|---|
| `pause_event` | TUI (`nexus_plex`) | pool, engine | Owner only — plus the one documented, deliberate `clear()` in `_wait_for_hitl_resume` |
| `cancel_event` | TUI / `execute_flow` | pool, workers | Owner only |
| `pause_owner_alive` | TUI (closure over `self.is_running`) | pool, engine | Read-only predicate; **called only while held** |
| `_shutdown` | `DynamicSwarmPool` | workers | Pool only |
| `paused_since` | worker thread | none | Thread-local |
| `held_since` | supervisor | none | Supervisor-local |

## Architecture Decisions

1. **Liveness question, not a timer.** A time ceiling cannot distinguish a
   deliberate long pause from an impossible one; a liveness predicate can. The
   ceiling is retained only as a backstop for callers who have no signal, and is
   off by default.
2. **The pool asks rather than guesses.** It is an observer of an event it does not
   own, so it has no standing to conclude anything about that event's owner. The
   caller supplies the answer.
3. **`abandoned` is its own status.** Folding it into `timeout` would send an
   operator hunting a slow node when their UI had died.
4. **`timeout` → `failed`, not a new session status.** `get_resumable_sessions`
   filters on a fixed status list, so a new value would have made timed-out sessions
   non-resumable — and a timeout is the *most* resumable kind of failure. Accepted
   cost: `failed` now covers four conditions and `job_sessions` has no reason
   column, so the distinction lives in the log. A reason column is a schema **and**
   contract change and belongs with the File Cabinet read API.
5. **A weaker `failed` bought a stronger `completed`.** A wrong `failed` is
   conservative; a wrong `completed` propagates. Given the choice, weaken `failed`.
6. **Both step loops changed together, as one membership test.** They have drifted
   before — only `execute_flow` applied the step config overlay — so the shape that
   keeps them aligned matters as much as the behaviour. Tests are parametrized over
   both.
7. **Kept, not deleted: `datacenter_router.py`.** Marked `SUPERSEDED` with what was
   cut and why, and retained as the reference implementation for the planned Drive
   *transport* layer. Transport over Drive is still the plan; locking over Drive is
   not. Deleting it is the operator's call.

## The edge-node clarification

Recorded because it cost real time and is the kind of thing that gets re-derived.

The F2 runaway was initially described as semi-intentional — a loop holding a socket
open so an edge node could join a swarm unexpectedly. It was not, and structurally
could not be: `_worker_loop` constructs and destroys *local, in-process* workers, and
there is no listener, port, or registration table anywhere in the pool.

**The join mechanism is the queue row.** A `task_queue` row with
`lock_status = 'open'` is claimable by anything that can reach that database and
issue `BEGIN EXCLUSIVE` — which is exactly what `hybrid_edge_sync`'s retirement note
says won. Throughout the runaway, `CTRL_MERGE_S0` sat open and claimable; the
spinning added nothing to that availability, and each rebuild ran schema DDL against
the file a joining node would have to claim through. The fix does not remove the
capability; it removes contention with it.

## Testing

**Gate, observed 2026-09-01:**

```
omni clean    purged .pytest_cache 1, .ruff_cache 1, bytecode 282
omni qa       PASSED (whole project, per pyrightconfig.json)
pytest        750 COLLECTED, 750 passed   (703 before this batch)
omni smoke    ALL CHECKS PASSED
```

**Reproduction-verified, all three.** Each fix was reverted and the new tests
confirmed to fail with the production signature:

- **F1** — restoring `min-width: 4` fails 3 tests, one of them with the identical
  frame (`rich/cells.py:338`) and message from the operator's traceback.
- **F2** — removing the scaler gate fails 3; removing both halves takes the measured
  construction count from ≤ 2 to 40 in two seconds.
- **F3** — the `timeout` and `abandoned` branches are asserted structurally over
  both loops, so deleting either branch fails.

**Two pre-existing tests were updated rather than worked around**, because their
contracts genuinely changed: `TestHitlResumeGate`'s four bool assertions became
status assertions, and `test_a_stalled_step_marks_the_session_failed` moved from the
literal `pool_status == "stalled"` to the membership form. Each carries a dated note
saying what changed and why the guarantee under test is unchanged.

One of my own new tests was wrong on first run and is worth recording:
`test_a_resume_is_reported_as_resumed` pre-set `pause_event`, which
`_wait_for_hitl_resume` immediately clears — the documented ownership inversion — so
it timed out. Fixed to set the event from a thread after the call starts. A test that
does not account for the inversion tests nothing.

### What is NOT verified

**No clean uninterrupted 8-lane run has happened yet.** These three fixes were
driven by a live run and gated by unit tests, but:

- **F1** is verified as *arithmetic*, not as pixels. Nobody has pressed pause in a
  live TUI since the fix. That is the confirming test and it takes ten seconds.
- **F2** is verified against a stub worker. The construction cost it removes is a
  real `LocalMessageBroker`, which the stub does not build.
- **F3**'s `pause_owner_alive` wiring in `nexus_plex.py` is **not covered by any
  test** — `maccre_tui` is outside both the pyright include list and the suite's
  reach here. It is two lines, and they are the two lines that make the whole
  mechanism live.
- **E2 remains unproven** and is unaffected by this work.

The obligations are unchanged: **press pause once**, then UT-0 ×3, then UT-1's six
tests. `scratch/_inspect_runaway.py` dumps any job's queue rows with both path
columns, which is the fastest way to read a run's outcome.
