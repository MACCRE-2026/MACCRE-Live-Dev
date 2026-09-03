# 2026-08-29: Phase 6.12 — Verified CTRL_REVIEW Baseline (Task A0)

## Summary

Records the known-good CTRL_REVIEW pause/resume/continue trace that every Phase 6.12
change is measured against. The previous Phase 6.12 attempt failed partly because no
version-controlled reference trace existed, so the regression could not be detected
until a human noticed flows "succeeding" after one node.

**Baseline job**: `job_20260829-163448-6crd`
**Project**: `499_TEST`
**Codebase**: `f7b326f` (working tree at Aug 22 rollback target
`a9f96dbadf5da59600576a70caea40be3e94894c`)
**Status**: PASS — three-step flow with a mid-flow HITL pause completed end to end.

This document is the human-readable record. The machine-checkable form is
`tests/test_ctrl_review_baseline.py`, which asserts the structural invariants that
make this trace possible. Task A8 (removing the CTRL_REVIEW hardcode) must leave
that test green.

---

## Flow Definition

Source: `__DATACENTER/499_TEST/autosave_flow.json`

```json
[
  {"macronode_name": "OSINT_Analyst", "agent_mapping": {}, "payload_mode": "Unified Ledger",
   "custom_instructions": "", "agent_tools_overrides": {"OSINT_Analyst": "none"}, "config": {}},
  {"macronode_name": "CTRL_REVIEW",   "agent_mapping": {}, "payload_mode": "Unified Ledger",
   "custom_instructions": "", "agent_tools_overrides": {}, "config": {}},
  {"macronode_name": "OSINT_Analyst", "agent_mapping": {}, "payload_mode": "Unified Ledger",
   "custom_instructions": "", "agent_tools_overrides": {}, "config": {}}
]
```

Three `FlowStep`s. No `config` on any step — so the baseline exercises the default
path only. Step 1 is a bare `CTRL_REVIEW` with an empty config dict.

---

## Node Table (from `unified_session_ledger.md`)

Recorded flow line: `OSINT_Analyst → CTRL_REVIEW → OSINT_Analyst`
Nodes executed: 3. Total cost: `$0.001940`.

| # | Node ID | Status | Cost | Started | Completed |
|---|---------|--------|------|---------|-----------|
| 1 | `AGENT_OSINT_Analyst_1613_S0` | completed | $0.000952 | 16:34:48 | 16:35:05 |
| 2 | `CTRL_PAUSE_MANUAL_S1`        | completed | $0.000000 | 16:35:05 | 16:36:15 |
| 3 | `AGENT_OSINT_Analyst_1613_S2` | completed | $0.000988 | 16:36:19 | 16:36:40 |

The 70-second gap on node 2 (16:35:05 → 16:36:15) is the human sitting at the HITL
prompt. That gap is the proof the pause was real and blocking, not a passthrough.

---

## Artifact List

`__DATACENTER/499_TEST/03_Agent_Ledgers/job_20260829-163448-6crd/`

| File | Bytes |
|------|-------|
| `AGENT_OSINT_Analyst_1613_S0_17.md` | 1840 |
| `AGENT_OSINT_Analyst_1613_S0_17_agent.log` | 6681 |
| `CTRL_PAUSE_MANUAL_S1_18.md` | 99 |
| `CTRL_PAUSE_MANUAL_S1_18_agent.log` | 1216 |
| `HITL_injection.md` | 51 |
| `AGENT_OSINT_Analyst_1613_S2_19.md` | 359 |
| `AGENT_OSINT_Analyst_1613_S2_19_agent.log` | 6333 |

`__DATACENTER/499_TEST/02_Dynamic_Context/job_20260829-163448-6crd/`
— `as_wrapped_topology.json` (3283 B), `topology_snapshot.csv` (312 B)

`__DATACENTER/499_TEST/04_Code_Artifacts/job_20260829-163448-6crd/`
— `unified_session_ledger.md` (3838 B), `unified_thoughts_ledger.md` (4263 B)

The trailing `_17` / `_18` / `_19` are the `task_queue` row ids, monotonically
increasing across the whole run. They confirm strict sequential ordering: one
task claimed at a time, which is exactly what Phase 6.12 changes.

### Pause artifact body (exact)

`CTRL_PAUSE_MANUAL_S1_18.md`:

```
# CTRL_PAUSE_MANUAL_S1

PAUSE node CTRL_PAUSE_MANUAL_S1: flow halted. Press Resume to continue.
```

### HITL content (exact)

`HITL_injection.md`:

```
What are the contents of the documents in Tranche 1
```

Step 2's output demonstrably answers that injected question, so the HITL payload
reached the resumed agent — the resume path carried context, it did not just unblock.

---

## How the pause actually fires (mechanism trace)

This is the part that matters for Task A8, and it is not what the rollback document
claimed.

1. `flow_engine.execute_flow` line 748 intercepts the step name `CTRL_REVIEW` and
   substitutes a synthetic single-row macro definition with
   `Node_ID = "CTRL_PAUSE_MANUAL"` and `Next_Node = "END"`.
2. `_hydrate_topology(step_index=1)` appends the step suffix, yielding
   `CTRL_PAUSE_MANUAL_S1`.
3. `swarm_worker` claims that task and calls
   `deterministic_nodes.execute_deterministic_node`.
4. `_resolve_node_type` prefix-matches `CTRL_PAUSE_MANUAL_S1` against the
   `DeterministicNodeType` enum. It matches `PAUSE = "CTRL_PAUSE"`.
5. `_handle_pause` returns `should_pause=True` with
   `log_message = "PAUSE node CTRL_PAUSE_MANUAL_S1: flow halted. Press Resume to continue."`
   — byte-identical to the recorded artifact above.
6. `swarm_worker` calls `broker.pause_task(row_id)`; the flow engine's poll loop sees
   `still_open == 0 and still_paused > 0`, fires `hitl_callback`, clears `pause_event`
   and blocks.
7. On resume, `local_broker.resume_paused_task` sees the node name starts with
   `CTRL_PAUSE` and routes it to `"END"` — with the in-code comment
   *"In a macro flow, the Next_Node is END. For now, we assume END."*
8. `END` terminates the macro node's internal DAG, not the flow. The outer
   `for idx in range(...)` step loop advances to step 2 and the third agent runs.

**The rename is load-bearing.** `CTRL_REVIEW` is not a member of
`DeterministicNodeType`. A node literally named `CTRL_REVIEW_S1` resolves to `None`,
and `execute_deterministic_node` falls back to `_handle_anchor` — a silent
passthrough with no pause. Any A8 refactor that stops producing a `CTRL_PAUSE*`
node ID silently deletes the HITL checkpoint.

---

## Corrections to the rollback record

Two claims in `ROLLBACK_2026-08-29_PHASE_6.12_FAILURE.md` do not survive contact
with the rolled-back source. Recording them so the next session does not act on
bad premises.

1. **The hardcode was not introduced by Phase 6.12 and was not removed by the
   rollback.** The document contrasts a "Before (Phase 6.12 — Broken)" hardcode
   against an "After (Aug 19 — Working)" registry load. The working tree at
   `f7b326f` still contains that hardcode, at three sites:
   `flow_engine.py:291` (preflight bypass), `:549` (`resume_flow`), `:748`
   (`execute_flow`). The baseline above passed *with the hardcode present*.
   The hardcode is therefore not the cause of the observed regression, and A8 is a
   doctrine/extensibility fix rather than a bug fix.

2. **`flow_vector` telemetry is not populated for this run.** The document's
   validation plan expects `flow_vector = "TestAgent_S0>CTRL_REVIEW_S1>TestAgent_S2"`
   in `system_logs.db`. The baseline job has exactly three rows in
   `system_logs.db`, all `action_type = TOOL_FIRED` for `setup_session_loggers`,
   all with `flow_vector = ""` and `tether_id = ""`. There are no `NODE_ROUTED`
   events. The authoritative evidence for this baseline is the filesystem ledger,
   not telemetry. Any success criterion phrased in terms of `flow_vector` cannot
   be evaluated today.

### What the hardcode does cost us

Not the linear case — the scatter case, plus configurability:

- `Next_Node` is pinned to `END`, so a review node placed inside a scatter lane
  terminates that lane's internal DAG instead of continuing to the lane's next node.
- `step.config` is discarded, so `auto_resume_after` and any other pause
  configuration a user sets in the Configure Node modal is silently ignored.
- Preflight validation is skipped entirely for review steps (line 291).

---

## Additional findings recorded while establishing the baseline

These are real, verified, and feed later tasks. None are fixed by A0.

| # | Finding | Evidence | Feeds |
|---|---------|----------|-------|
| F1 | `setup_session_loggers` fired 3× for one job | 3 telemetry rows at 16:34:49, 16:35:06, 16:36:20 — once per node claim | A7 (idempotent logger setup) |
| F2 | Auto-wrapped agent node IDs are not stable across processes | `flow_engine.py:135` derives the ID from `id(name) % 9999`, a CPython object address. Hence `1613`. A resume in a fresh process can compute a different ID and fail to match queued `current_node` rows | A8 / D1 risk register |
| F3 | `controlnode_registry` declares a handler for `CTRL_REVIEW` that does not exist | `handler_module="maccre_core.orchestration.local_broker"`, `handler_func="intercept_review_via_route_task"`; repo-wide grep finds the name only in the registry seed | A8 (reconcile pause mechanisms) |
| F4 | A fifth pause-ownership mechanism exists | `resume_paused_task` hardcodes `"END"` with a `"For now, we assume END"` comment (`local_broker.py:566-571`) | A8 |
| F5 | Orphaned Phase 6.13 test blocks the whole suite | `tests/unit/test_flow_step_multi_lane.py` imports `TetherIDGenerator` from `flow_engine`, which does not exist post-rollback. Pytest aborts during collection, so *zero* tests currently run | A1 (quarantine) |

F5 is worth dwelling on. The test suite has not been runnable since the rollback,
which means the previous attempt's "QA passes" signal was ruff/pyright only. That
is exactly the success-siloing the orchestration doctrine warns about.

---

## Machine-Checkable Form

`tests/test_ctrl_review_baseline.py` encodes the invariants above as assertions that
need no database, no network, and no LLM:

| Assertion | Guards against |
|-----------|----------------|
| `_resolve_node_type("CTRL_PAUSE_MANUAL_S1")` is `PAUSE` | Renaming the review node to something the dispatcher classifies as `None` |
| `execute_deterministic_node` on that ID returns `should_pause=True` | Losing the pause entirely |
| Its `log_message` equals the recorded artifact body byte for byte | Silent behavior drift in the pause handler |
| `_hydrate_topology` at `step_index=1` yields `CTRL_PAUSE_MANUAL_S1`, `Next_Node="END"`, `Wait_For="none"` | Step-suffixing or row-order regressions |
| `_find_starting_nodes` returns exactly `["CTRL_PAUSE_MANUAL_S1"]` | The review node not being injected as an entrypoint |
| `_resolve_node_type("CTRL_REVIEW_S1")` is `None` | Documents *why* the rename is load-bearing; if a future change adds a `REVIEW` enum member this test fails loudly and A8 gets a cleaner option |
| The recorded 3-step flow round-trips through `FlowStep.from_dict`/`to_dict` | Serialization drift when `children`/lane fields are reintroduced in 6.13 |

Agent node IDs are asserted by pattern (`AGENT_OSINT_Analyst_\d{4}_S0`), never by
the literal `1613`, because of F2.

---

## State Contracts

A0 introduces no shared mutable state. Recorded for continuity:

| Object | Owner | Observers | Mutation Rights |
|--------|-------|-----------|-----------------|
| `cancel_event` | `flow_engine.execute_flow()` caller (TUI) | `flow_engine`, `swarm_worker` | Owner only |
| `pause_event` | TUI (`nexus_plex`) | `flow_engine`, `swarm_worker` | **Contested** — `flow_engine` calls `pause_event.clear()` at the HITL gate (`:830`, `:611`) on an event it received as a parameter. Must be resolved in A8/B2 |

The `pause_event` row is a live doctrine violation in the baseline, not something
Phase 6.12 introduced. Flagging it now so B2 does not preserve it by accident while
"keeping HITL semantics verbatim."

---

## Architecture Decisions

- **Baseline is the filesystem ledger, not telemetry.** Telemetry has no node
  events for this job (see correction 2), so it cannot serve as the reference.
- **Assert the mechanism, not the LLM output.** The baseline's agent text depends on
  live web grounding and is not reproducible. The test asserts the control-flow
  invariants that made the trace possible.
- **No re-run.** Per the locked decision (1 = a), the 6crd run is accepted as
  sufficient A0 evidence. It is now recorded here rather than living only in a
  chat transcript.

## Testing

```
.venv\Scripts\python.exe -m pytest tests/test_ctrl_review_baseline.py -v
```

Blocked until A1 quarantines `tests/unit/test_flow_step_multi_lane.py` (F5) — that
module aborts collection for the entire suite.
