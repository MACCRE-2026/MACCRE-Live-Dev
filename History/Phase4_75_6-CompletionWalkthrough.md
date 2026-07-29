# Phase 4.75.6: Post-TUI Refactor CTRL_ Node Completion — Walkthrough

## Summary

Implemented all 5 work packages from the Phase 4.75.6 implementation plan, closing every gap identified in the Post-TUI Refactor analysis documents. 8 files modified, 3 subagents used for parallel execution.

---

## WP1: Registry Hygiene

### [controlnode_registry.py](file:///B:/EXO_GANS/maccre_core/controlnode_registry.py)

| Change | Detail |
|--------|--------|
| **CTRL_CONDITIONAL_ROUTE** | `"ComingSoon"` → `"active"`, handler refs pointed to `_handle_conditional_route` |
| **CTRL_REVIEW** | handler_func updated to `"intercept_review_via_route_task"`, description clarified |
| **CTRL_END** (NEW) | Category: Flow Control, status: active, handler: `_handle_end` |
| **CTRL_PAYLOAD_INJECT** (NEW) | Category: Data Flow, status: active, handler: `_handle_payload_inject` |
| Seed comment | Active count: 14 → **17** (2 new + 1 activated) |

> [!IMPORTANT]
> The existing `controlnode_registry.db` was deleted to force a re-seed on next TUI startup.

### [deterministic_nodes.py](file:///B:/EXO_GANS/maccre_core/orchestration/deterministic_nodes.py)

- Added `DeterministicNodeType.END` and `PAYLOAD_INJECT` enum values
- Added `_handle_end()` — semantic passthrough terminal node
- Added `_handle_payload_inject()` — writes `config["inject_content"]` to `{node_id}_injected.md`
- Both registered in `_NODE_HANDLERS`

---

## WP2: Configure Node Modal Completion

### [nexus_plex.py](file:///B:/EXO_GANS/maccre_tui/nexus_plex.py) — NodeConfigModal

**Refactored** the growing `if/elif` compose chain and save chain into two clean helpers:

- `_compose_ctrl_fields(_json)` → Yields appropriate config widgets per CTRL_ type
- `_collect_ctrl_config()` → Reads widget values and returns merged config dict

**New fields added (~20 total):**

| Node | Fields Added |
|------|-------------|
| CTRL_ANCHOR | `anchor_label` |
| CTRL_END | Static label (no config needed) |
| CTRL_PAUSE | `pause_message`, `auto_resume_after` |
| CTRL_DELAY | `delay_seconds` |
| CTRL_CHECKPOINT | `checkpoint_label` |
| CTRL_RECURSION | `Max_Recursion`, `loop_target` |
| CTRL_TRANSFORM | `template` (TextArea) |
| CTRL_CONCAT | `concat_delimiter` |
| CTRL_CLEANUP | `glob_patterns`, `cleanup_dir` |
| CTRL_MERGE | `merge_delimiter` (added to existing merge_mode) |
| CTRL_FILTER | `strip_sections` (added to existing max_chars + regex_remove) |
| CTRL_CONDITIONAL_ROUTE | `available_targets`, `fuzzy_max_distance` (added to existing fields) |
| CTRL_PAYLOAD_INJECT | `inject_content` (TextArea) |
| CTRL_GATE | `gate_id`, `initial_state`, `predicate_type`, `predicate_target`, `predicate_operator`, `predicate_value`, `on_true`, `on_false` |

**Result: 16/16 active nodes with dedicated config fields.**

---

## WP3: Handler Upgrades

### [deterministic_nodes.py](file:///B:/EXO_GANS/maccre_core/orchestration/deterministic_nodes.py)

| Handler | Enhancement |
|---------|------------|
| `_handle_pause` | Reads `pause_message` (appended to log_message), `auto_resume_after` (>0 → timed gate via `time.sleep`) |
| `_handle_checkpoint` | Reads `checkpoint_label` → filename becomes `{node_id}_{label}_checkpoint.md` |
| `_handle_delay` | New `delay_seconds` config field takes priority over `Instruction_Override` |
| `_handle_transform` | New `template` config field takes priority over `Instruction_Override` |
| `_handle_recursion` | New `loop_target` config field takes priority over `Instruction_Override` |
| **`_handle_gate` (OVERHAUL)** | Full predicate-based "Floating If" system |

### Gate System Architecture

New helper functions added:
- `_read_gate_state(job_id, gate_id)` — reads from `gate_states.json`
- `_write_gate_state(job_id, gate_id, state)` — persists to `gate_states.json`
- `_evaluate_predicate(predicate, payload_path, job_id, config)` — evaluates predicate logic
- `_execute_gate_action(action, node_id, payload_path, job_id, config)` — executes PASS/BLOCK/ROUTE_TO/SET_GATE

**Supported predicate types:** `payload_exists`, `payload_contains`, `artifact_exists`, `gate_state`
**Supported actions:** `PASS`, `BLOCK`, `ROUTE_TO:<node>`, `SET_GATE:<gate_id>=<state>`

---

## WP4: Tethering Expansion

### [macronode_workshop.py](file:///B:/EXO_GANS/maccre_tui/widgets/macronode_workshop.py)
- CTRL_CONCAT now auto-tethers to pending scatter (same as MERGE pattern)
- CTRL_BRANCH now auto-tethers to pending scatter

### [flow_dict.py](file:///B:/EXO_GANS/maccre_core/flow_dict.py)
- `set_tether()` accepts new `parent_tether: str = ""` parameter for nested scatter hierarchy tracking

---

## WP5: flow_line_id Wiring

### [swarm_worker.py](file:///B:/EXO_GANS/maccre_core/orchestration/swarm_worker.py)
- Deterministic node dispatch now handles 3 branches:
  1. `next_nodes` (plural) → per-target fan-out with `flow_line_id = "{current}.{tether_id}.{idx}"`
  2. `next_node` (singular) → propagates existing `flow_line_id`
  3. Default topology routing → propagates existing `flow_line_id`

### [local_broker.py](file:///B:/EXO_GANS/maccre_core/orchestration/local_broker.py)
- `route_task()` accepts `flow_line_id: str = ""` parameter
- Writes `flow_line_id` into INSERT/UPSERT for downstream task_queue rows

### [broker_interface.py](file:///B:/EXO_GANS/maccre_core/orchestration/broker_interface.py)
- ABC `route_task()` signature updated with `flow_line_id` parameter

---

## Roadmap Updates

### [Era2_architectural_roadmap.md](file:///B:/EXO_GANS/Era2_architectural_roadmap.md)
Added **§6.7 CTRL_GATE Advanced Predicates** to Phase 6 with deferred items:
- Multi-predicate arrays with `predicate_logic: all|any`
- `flow_state`, `counter_threshold`, `expression` predicate types
- `SCATTER_TO` action type

---

## QA Results

| File | Status |
|------|--------|
| `controlnode_registry.py` | ✅ Ruff + Pyright passed |
| `deterministic_nodes.py` | ✅ Ruff + Pyright passed |
| `nexus_plex.py` | ✅ Ruff + Pyright passed |
| `macronode_workshop.py` | ✅ Ruff + Pyright passed |
| `flow_dict.py` | ✅ Ruff + Pyright passed |
| `broker_interface.py` | ✅ Ruff + Pyright passed |
| `local_broker.py` | ✅ Ruff + Pyright passed |
| `swarm_worker.py` | ⚠️ 5 pre-existing Ruff issues (none from this change) |

## Pre-existing Bugs Fixed (Checkpoint 107)

Two bugs from the previous checkpoint were also fixed in this session's early work:

1. **Dual NodeConfigModal** — Topology Visualizer double-click now uses the same full agent+baked-tool extraction pipeline as the Active Flow Sequence click handler
2. **Empty Flow Monitor** — `write_agent_log` restructured to combine both log writes into a single `call_from_thread` callback, preventing silent failures
