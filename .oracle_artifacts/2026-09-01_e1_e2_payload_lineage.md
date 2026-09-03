# 2026-09-01: E1 / E2 — Payload Lineage at Two Handoffs

**Domain:** Orchestration & Engine
**Defects:** E1 (fan-in gathered one file eight times), E2 (a step's output did not
cross the step boundary)
**Branch:** `phase/6.13-track-a-d-and-payload-lineage`
**Precondition commit:** `762f614` (Track A + Track D checkpoint, gate recorded)

---

## Summary

Two defects, one failure class: **an artifact losing its identity at a handoff.**

Both were found by reading an agent's ledger on live run
`job_20260831-041428-6goe`, not by the test suite. The suite was green at 665 tests
while both were present, because both live in a seam — E1 between what a node
writes and what the queue records, E2 between what a step produces and what the
next step is handed. No stubbed test visited either. This is doctrine principle 6
in its purest form, and it is the second time this phase it has been demonstrated.

The downstream symptom was a single agent politely reporting that it had been
handed nothing usable:

> `CTRL_MERGE_S0` merge acknowledged. Eight sources have been integrated. To
> determine who seems to know the most about roses [...] I require the actual
> content of the merged sources.

It was right on both counts, and its being right was the whole diagnosis.

### E1 — the fan-in gathered one file eight times

Every lane's queue row reported `payload_path = unified_session_ledger.md`. Five
links, and **only the second is the root cause**:

| # | Location | What happens |
|---|---|---|
| 1 | `swarm_worker.py` (~1840) | lane finishes; `routing_payload_path` = that lane's own ledger `<node>_<row_id>.md` |
| 2 | `swarm_worker.py` (~1856) | the Unified Ledger branch **replaces** it with the shared session ledger, because that is what the *successor* should read. Correct for routing — and it discarded the only reference to what the lane produced |
| 3 | `local_broker.route_task` | writes the routing payload onto the row it is closing, so the row stops recording the lane's output |
| 4 | `local_broker.get_completed_payload_paths` | asks "what did each predecessor produce", reads `payload_path`, gets one path eight times |
| 5 | `deterministic_nodes._handle_merge` | builds a section per path, logs `Merged 8 sources` — literally true, semantically empty, eight identical `## Source: unified_session_ledger` headings |

**The handover recorded link 3 as the cause and suggested an `output_path` column
might be needed. That was directionally right and mechanically wrong.** The
overwrite in `route_task` is real, but the lane's own path is already gone before
`route_task` is called. A column alone would have recorded whatever the worker
handed it, which was the shared ledger. Both had to change.

Note also what link 4's docstring said, verbatim, before this change:

> A completing node's row carries its *output* in `payload_path`, because
> `route_task` writes `new_payload_path` onto the row it is closing. So the
> completed row is the authoritative record of what that node produced.

A stated, load-bearing, wrong assumption, sitting directly above the query it
justified. Principle 5: the claim had no test that would fail when it went false.

### E2 — the step boundary took the newest file, which is always the wrong one

The merge row correctly pointed at `CTRL_MERGE_S0_merged.md` (426 KB). The next
step was queued with `CTRL_MERGE_S0_93.md`, the merge's 59-byte ledger stub, at a
billed cost of $0.000046.

`_find_final_ledger_path` globbed `03_Agent_Ledgers/<job_id>/*.md` and returned the
newest by mtime. Three things were wrong beyond the obvious:

1. **It was not a race it sometimes lost — it is one it always lost.**
   `_handle_merge` writes the artifact, then the worker writes the node's ledger
   stub *after* the handler returns. The stub is therefore always newer.
2. **It accepted `topology_rows` and never read them.** The "final node of the DAG"
   its docstring promised was never consulted. The parameter was dead.
3. **Its directory scope was the job, not the step.** A step-2 lookup could return
   a file step 1 wrote, and `*.md` also matches `thoughts_and_tools_*` and scatter
   chunk files.

Meanwhile `topology_graph.terminal_nodes()` already existed, with a test asserting
`terminal_nodes(scatter_rows(8)) == ["CTRL_MERGE"]`. The engine had the answer and
was guessing anyway.

---

## Files Modified

| File | What changed |
|---|---|
| `maccre_core/orchestration/local_broker.py` | `output_path` column (CREATE TABLE body + ALTER migration); `route_task` records it at both UPDATE sites; `get_completed_payload_paths` reads it with a documented fallback; the falsified docstring replaced with a record of what it cost |
| `maccre_core/orchestration/broker_interface.py` | `output_path` on the ABC signature, with the "must not blank an existing value" requirement stated |
| `maccre_core/orchestration/swarm_worker.py` | captures `node_output_path` **before** the Unified Ledger swap (the root cause); passes `output_path` at all five `route_task` call sites |
| `maccre_core/orchestration/deterministic_nodes.py` | `_handle_merge` and `_handle_concat` de-duplicate inputs, warn loudly on collapse, and count distinct sources |
| `maccre_core/orchestration/flow_engine.py` | `_find_final_ledger_path` **deleted**; `_find_terminal_nodes` and `_capture_step_output` added; all three call sites replaced |
| `tests/mocks/mock_broker.py` | `output_path` parity with the ABC and the real broker |
| `tests/test_payload_lineage.py` | **new**, 38 tests |
| `tests/test_lock_lifecycle.py` | corrected the docstring that asserted the claim E1 falsified |

## Function Signatures Added / Changed

```python
# local_broker.py, broker_interface.py, tests/mocks/mock_broker.py — all three together
def route_task(
    self, row_id, job_id, next_node_str, new_payload_path,
    actual_cost=0.0, source_payload_path="", max_recursion=3,
    status="completed", flow_line_id="", flow_vector="", tether_id="",
    output_path="",                      # NEW — what the node produced
) -> None: ...

# flow_engine.py — new
def _find_terminal_nodes(
    self, topology_rows: list[dict[str, Any]], step_index: int = 0
) -> list[str]:
    """Sink Node_IDs of a MacroNode DAG, hydrated with the step suffix."""

def _capture_step_output(
    self, job_id: str, topology_rows: list[dict[str, Any]],
    step_index: int, broker: LocalMessageBroker,
) -> str | None:
    """The artifact this step's terminal node recorded. None means none."""

# flow_engine.py — REMOVED
def _find_final_ledger_path(self, job_id, topology_rows) -> str | None: ...
```

`output_path` is appended last and defaults to `""`, because `macro_factory` calls
`route_task(row_id, job_id, next, payload)` positionally. A required parameter, or
one inserted mid-signature, would have broken macro expansion rather than the thing
under test. A test asserts this for all three implementations.

## State Contracts

No `threading.Event`, `queue.Queue` or other shared mutable object was added,
changed, or observed differently. The `pause_event` ownership inversion recorded in
the 6.12 closeout is untouched.

| Object | Owner | Observers | Mutation rights |
|---|---|---|---|
| `task_queue.output_path` (SQLite column) | `LocalMessageBroker.route_task` | `get_completed_payload_paths`, `_capture_step_output` | Write-once per node completion. An empty argument leaves the stored value alone, so no caller can blank another's record |
| `node_output_path` (local, `execute_cycle`) | the worker thread | none | Thread-local; bound once before routing, never reassigned |
| `cancel_event` / `pause_event` | `flow_engine.execute_flow` | pool, workers | Unchanged by this work |

## Architecture Decisions

**1. A second column, rather than making one column mean one thing.**
The alternative was to stop the clobber and leave `payload_path` as the single
record. Rejected: `payload_path` would still be dual-purpose (input while open,
output once closed), and that ambiguity is what let a wrong value in unnoticed.
Two names for two facts. Principle 4 argues against two representations of *one*
thing — this is the opposite, one representation of two things.

**2. `COALESCE(NULLIF(output_path,''), payload_path)` rather than a backfill.**
The fallback is load-bearing, not a legacy shim. Three callers legitimately never
supply an output — `macro_factory`'s ephemeral spawn and FAILED routes, and the
`CTRL_PAUSE` resolver — because for them the routing payload *is* the passthrough
output. It also keeps a session resumed across the change readable. What must never
happen is a caller *inventing* a value, which is why the failure path passes `""`
explicitly.

**3. No silent fallback at the step boundary.**
`_capture_step_output` returning `None` leaves `current_payload` unchanged and logs
at ERROR. Keeping the mtime glob as a fallback was rejected outright: a silent
retreat to the defective path means the defect can return with the suite green.
Marking it a new terminal condition and failing the flow was also rejected — that
is the same shape as the open timeout decision, and it is the operator's call, not
mine. Carrying the previous payload forward is wrong but *visible*, which is the
distinction principle 2 draws.

**4. Divergent terminals resolve by declared topology order.**
`terminal_nodes()` can return more than one node. Picking by completion time or
mtime would hand the next step a different document on each run. The log says
plainly that this is a choice rather than a fact, and suggests authoring a
`CTRL_MERGE` if the next step needs all of them.

**5. The merge de-duplicates and says so.**
Strictly redundant once the root cause is fixed. Kept because the original failure
was silent: `Merged 8 sources` over one file read as success to every log reader.
The count now reflects distinct sections written, and a collapse produces a WARNING
naming the shortfall. `_handle_concat` got the same treatment — it shares the input
contract, so it shared the defect, and only escaped observation because no live flow
used it.

**6. Not fixed, deliberately.** The Unified Ledger branch reads the *successor's*
`payload_mode`, not the completing node's. That is correct — "payload mode" is a
property of what a node wants to receive. It is recorded here because it reads like
a bug and is not.

**7. Out of scope, deliberately.** `timeout` is still unhandled in both step loops,
so a timed-out step still lets the flow continue and records `completed`. That is an
open operator decision with a register entry; changing it will fail flows that
currently report success, which is the point of asking first.

## Testing

`tests/test_payload_lineage.py` — 38 tests. Both headline tests were verified by
**reverting each fix and confirming they fail with the live signature**, because a
test that has never failed is not yet evidence:

- E1 reverted (`SELECT payload_path`): three tests fail, all eight lanes reporting
  `unified_session_ledger.md`.
- E2 reverted (mtime glob reinstated): `test_a_newer_stub_on_disk_does_not_win`
  fails by selecting `CTRL_MERGE_S0_93.md` over `CTRL_MERGE_S0_merged.md` — the
  same two filenames as the live run.

Coverage of note:

- `TestOutputPathMigration` — legacy table gains the column without dropping rows;
  idempotent across repeated opens; a pre-column row still reads through the
  fallback. Mirrors Track A's `locked_at` tests.
- `TestGatherReturnsDistinctOutputs` — asserts **distinctness**, not count. Counting
  eight was never the test that would have caught this; the broken code returned
  eight too.
- `TestWorkerPreservesItsOwnOutput` — source-order guards. The behavioural cost of
  that one line is only observable through a live model call, so the ordering is
  asserted structurally: capture must precede the Unified Ledger swap, or E1
  returns with every test green.
- `TestMergeProducesDistinctSections` — the first assertions in this repo about
  merged *content*. Previously nothing checked it, which is why an agent found this
  before the suite did.
- `TestTheGlobIsGone` — asserts `_find_final_ledger_path` no longer exists and
  neither step loop globs. Two ways to answer one question is how the TUI and the
  engine came to disagree about node ids.

### Gate, as observed on 2026-09-01

```
omni clean    zombie hunt clean; purged .pytest_cache 1, .ruff_cache 1, bytecode 259
omni qa       PASSED (whole project, per pyrightconfig.json)
pytest        703 COLLECTED, 703 passed          (665 baseline + 38 new)
omni smoke    ALL CHECKS PASSED
```

**Baseline note, recorded because it contradicts the handover.** On the untouched
tree this session, pytest was **665 collected, 664 passed, 1 failed** —
`test_eight_lane_scatter_beats_sequential_wall_clock`, at 1.70 s against a bound of
1.20 s. It passes in isolation and 32/32 within its own file, and the companion
barrier test pinning `peak == 8` passes in the full run, so scatter width is intact
and this is a load-sensitive threshold rather than a concurrency regression. It
passed in both post-change full runs. Left untouched: loosening or marking it is an
operator decision. The handover's "665 tests passing" is true only on an unloaded
machine.

### What is NOT verified

**No live 8-lane scatter has been run.** Both defects lived in the seam between the
authoring UI and the engine, and `omni smoke` exercises a single node. Static
analysis, 703 unit tests and a one-node smoke are not a live run, and principle 6
exists because exactly this combination was green while six real defects sat in this
code path.

The proof obligations are unchanged and remain open:

- **UT-0 runs 2 and 3.** Run 1 was measured while every agent ran twice and the
  merge combined one source, so it is not a valid baseline.
- **UT-1, six tests**, especially test 6 (kill a worker mid-node).
- The specific E1/E2 acceptance shape: an 8-lane scatter whose merged document
  contains **eight distinct** `## Source:` sections naming eight different lanes,
  and whose following step receives that document rather than the 59-byte stub.

Until that run exists, the honest status of E1 and E2 is *fixed and gated, not yet
reproduced as fixed in production.*
