# 2026-09-05: Payload Cost Becomes Measurable

**Plan task:** Era 3 tracker #18. **Prerequisite of #20**, the step-boundary payload contract.
**Oracle domain:** OrchestrationAndEngine

## Summary

Nothing in the system could measure a payload. The step-boundary contract enlarges what
crosses a boundary, and `actual_cost` derives from the provider's own `promptTokenCount` —
so the real bill would have moved with no way to say by how much or where. This is the
before-number.

Two halves: **attribution** (label the token data already being collected) and
**measurement** (record the payload size that was never recorded at all).

## Files Modified

- `maccre_core/maccre_router.py` — `_attr_session_id` / `_attr_source_node` and
  `set_call_attribution`; both `INFERENCE_COST` writes now pass them.
- `maccre_core/orchestration/swarm_worker.py` — sizes the payload at claim time, sets
  attribution once per cycle, passes `payload_bytes` to `route_task`.
- `maccre_core/orchestration/local_broker.py` — `payload_bytes` column (CREATE TABLE body
  + idempotent ALTER), `route_task` parameter at both UPDATE sites, and
  `get_payload_bytes_by_node`.
- `maccre_core/orchestration/broker_interface.py` — the ABC declares the parameter.
- `tests/mocks/mock_broker.py` — mirrors it, including the don't-blank rule.
- `tests/test_payload_measurement.py` — new, 26 tests.

## Function Signatures Added/Changed

```python
# maccre_router.py
def set_call_attribution(self, session_id: str = "", source_node: str = "") -> None

# local_broker.py — CHANGED, trailing optional param so no caller breaks
def route_task(self, ..., output_path: str = "", payload_bytes: int = 0) -> None
# NEW
def get_payload_bytes_by_node(self, job_id: str) -> dict[str, int]
```

Schema: `task_queue.payload_bytes INTEGER DEFAULT 0`.

## State Contracts

| Object | Owner | Observers | Mutation Rights |
|--------|-------|-----------|-----------------|
| `UniversalRouter._attr_session_id` / `_attr_source_node` | the router instance | its own `generate` | **owner only**, written solely via `set_call_attribution` |
| `task_queue.payload_bytes` | `LocalMessageBroker` | `get_payload_bytes_by_node` | written only by `route_task`, and **never** blanked |

**Why instance state on the router needs no lock, stated as a fact rather than a hope.**
`swarm_worker.__init__` does `self.router = UniversalRouter()`, so each of the eight
concurrent workers owns a separate router. This is the same fact the process-wide rate
limiter relies on in the *opposite* direction — its own comment says the limiter had to be
process-wide "because each UniversalSwarmWorker builds its own UniversalRouter", or it
would have counted one thread and missed seven. The two fields are therefore
thread-confined by construction, and `test_two_routers_do_not_share_attribution` is where a
future change to that would surface.

## Architecture Decisions

### What was missing was labels, not data

The two `INFERENCE_COST` telemetry writes have **always** recorded real provider
`input_tokens` and `output_tokens`. They passed **neither** `session_id` nor `source_node`,
so every row defaulted to `""`. Real measurements were being collected into an unqueryable
heap. Threading two arguments made per-node cost answerable without adding a single new
measurement.

### Attribution is set once per cycle, not passed per call

Six `router.generate(...)` sites are reachable from one node's execution path: the Diamond
Loop turn, the graceful close, two OSINT query builders, an entity extractor, and the
interactive loop. Passing attribution at each would make it **forgettable at any one of
them**, and the failure would be silent — a row with `source_node=''` is indistinguishable
from a row written before attribution existed.

*Rejected:* threading `session_id`/`source_node` through `generate`'s signature. It touches
nine call sites including tests, and converts a guarantee into a convention.

### Bytes are stored; tokens are not

Bytes come from one `stat()` call and are a fact. Tokens would be that number divided by a
heuristic. Storing both would put a derived value beside its own input — two
representations of one measurement — and the derivation already exists, named honestly, in
`finops_tools.estimate_tokens`.

### `0` means *not measured*, and never overwrites a measurement

`payload_bytes = CASE WHEN ? = 0 THEN payload_bytes ELSE ? END`, at both UPDATE sites. The
same rule `output_path` follows, for the same reason: defect E1 was a real value destroyed
by a caller that had nothing better to put there. A later caller that did not measure must
not erase a reading an earlier one took.

An unreadable path and a genuinely empty file both land at `0`. That collision is accepted
rather than split into a second column, because a 0-byte payload and an unmeasured one call
for the same investigation.

### The measurement is taken at claim time, not at route time

By route time, `payload_path` may have been rewritten by the `Targeted Filter` branch, which
replaces what the node reads. Sizing it there would answer a different question under the
same column name.

### The column ships with its reader

`get_payload_bytes_by_node` lands in the same change as the column. A schema column with no
consumer is the shape the doctrine names after the `--smart` flag — accepted, documented,
read by nothing — and this project has now found that shape three times, most recently in
`resume_paused_task`'s `topology_engine` parameter. Unmeasured nodes are **omitted** from
the result rather than reported as `0`, so "not measured" and "measured empty" do not share
a bucket.

## Testing

`tests/test_payload_measurement.py` — **26 tests**: attribution (fresh state, set, clear,
`None` normalisation, two routers independent); both `INFERENCE_COST` sites asserted **by
count** so dropping one is caught; the worker sets it once per cycle before anything can
infer; the column (exists, records, unmeasured is 0, `0` does not erase, non-zero replaces);
the reader (by node, omits unmeasured, job-scoped, empty job); ABC/concrete/mock signature
agreement; and the worker's measurement point.

### Revert-to-red, twice

- `payload_bytes = ?` instead of the `CASE WHEN` → `assert 0 == 1234`. The measurement
  erased.
- Attribution dropped from **one** of the two `INFERENCE_COST` sites → `assert 1 == 2`.
  This is exactly the drift the count assertion exists for; asserting presence rather than
  count would have passed.

Both probes removed and grep-confirmed absent before re-running green.

### The failure that was mine, recorded because the design lesson is real

`set_call_attribution` was first placed next to where `current_node` is bound, which reads
more naturally. Three tests in `test_lock_lifecycle.py` went red immediately:
`AttributeError: 'UniversalSwarmWorker' object has no attribute 'router'`.

Those tests build a worker with `__new__` and deliberately omit `router` so the node
**raises on its own without a contrived injection**, landing in the outer `except` that the
A4 hardening added — the guarantee that a claimed task always ends resolved. My line sat
*above* that try, so the exception escaped into the pool instead. **Bookkeeping that can
raise has no business outside the guard.** Moved inside; the tests pass and now exercise the
guard through this line too.

One of my own tests was also wrong, on a different axis:
`test_attribution_is_set_before_any_generate_call` compared **textual positions in the
file** and failed, because four `generate` sites live in helper methods defined *above*
`execute_cycle`. Runtime order was correct all along. Rewritten to slice `execute_cycle`'s
own body and check against the helpers it calls. Recorded rather than quietly fixed, because
"file position implies execution order" is a plausible premise that would have kept passing
for the wrong reason had the code happened to satisfy it.

### Gate run 2026-09-05

| Gate | Result |
|------|--------|
| `omni clean` | 09:23 — 289 bytecode files purged. |
| `omni qa` | **PASS** — whole project, 09:32. |
| `pytest tests -q` | **1002 passed, 10 xfailed, 0 failed** in 189.29s — 1012 collected. |
| `omni smoke` | **ALL CHECKS PASSED** — inference 1.1s. |

Collected 986 → 1012 is +26 exactly, and the pass count moved by the same 26.

## Limits

- **No live run.** The attribution and the measurement are covered by tests and unproven in
  production. Nobody has yet queried `system_logs` for a real run's per-node input tokens,
  because no run has happened since the change.
- **A baseline still has to be taken.** This makes measurement *possible*; it does not
  constitute the before-number. #20 needs an actual run recorded first.
- **The interactive path still records `0` cost on the queue row.** `execute_cycle` hard-zeroes
  `task_cost` for the Stream-4 interactive branch. Its inference is now *attributed in
  telemetry*, which is an improvement, but `task_queue.actual_cost` and
  `system_logs.cost` will disagree for those nodes. Recorded, not changed.
- **`_estimate_node_cost` is still blind to input size.** The pre-flight estimate remains a
  function of (model, node count). This change supplies the data that would let it stop
  being, and does not spend it.
