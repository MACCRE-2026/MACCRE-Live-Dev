# Comprehensive Subsystem Audit Report: Orchestration & Swarm Engine (`maccre_core/orchestration/`)
**Oracle Domain:** `OrchestrationAndEngine_Oracle`  
**Target Subsystem:** `maccre_core/orchestration/` (`swarm_worker.py`, `flow_engine.py`, `deterministic_nodes.py`, `local_broker.py`, `macro_factory.py`, `dialogue_runner.py`, `topology_engine.py`)  
**Audit Context:** Phase 4.99 User Testing Action List & Era 2 / Era 3 Architectural Roadmap Alignment  
**Date:** 2026-08-09  
**Compliance Standard:** Sovereign Edge Omni-Builder Doctrine & Law Rev 19.0  

---

## 1. EXECUTIVE SUMMARY & SUBSYSTEM IDENTITY

The `maccre_core/orchestration/` subsystem serves as the sovereign execution engine and control plane of MACCREv2 / EXO_GANS. It operates on a queue-unrolled, zero-cloud Directed Acyclic Graph (DAG) state machine backed by SQLite WAL databases (`swarm_queue.db`, `system_logs.db`).

### Key Structural Pillars Evaluated:
1. **`UniversalSwarmWorker` (`swarm_worker.py`)**: Core node loop executing task cycles, binding LLM calls to `UniversalRouter`, managing memory engines, executing tool calls via `ToolExecutor`, and driving multi-agent execution modes (Single, Dialogue, Live Session).
2. **`FlowEngine` (`flow_engine.py`)**: Supervisory engine managing linear and unrolled DAG executions of MacroNode chains, pre-flight validation, hydra-compilation of topology CSV files, execution cycle controls (VCR Pause, Step, Resume), and unified session ledger synthesis.
3. **`DeterministicNodes` (`deterministic_nodes.py`)**: 17 non-LLM control primitives (`CTRL_` prefix) executing structural graph operations (fan-out scatter, fan-in merge, predicate gates, recursion counters, fallback routing, delay, cleanup, transform) without consuming LLM tokens.
4. **`LocalMessageBroker` (`local_broker.py`)**: Concurrency-hardened SQLite Scatter-Gather state machine managing task locks via `BEGIN EXCLUSIVE` transactions, `flow_line_id` parentage tracking, `tether_id` isolation, and `flow_vector` lineage logging.
5. **`MacroFactory` (`macro_factory.py`)**: Parameterised MacroNode template catalog (`cascade`, `hologram`, `chord`, `crucible`) and legacy `MACRO:` prefix interception.
6. **`DialogueRunner` (`dialogue_runner.py`)**: Multi-turn dialogue state engine supporting pair and group agent conversations with context retention.
7. **`TopologyEngine` (`topology_engine.py`)**: Sovereign local control plane, CSV parser, RAM TTL cache, and 7-point pre-flight DAG validator.

---

## 2. DETAILED AUDIT FINDINGS & DEEP-DIVE ANALYSIS

### 2.1 CRITICAL BROKER BUG: Missing `tether_id` in `route_task()` & Storage Layer Disconnect
- **File & Line Scope:** `local_broker.py` (L133, L388-503), `swarm_worker.py` (L635-665, L828-834)
- **Defect Mechanism:** 
  1. `task_queue` schema defines a `tether_id` column, and `fetch_and_lock_task()` & `get_completed_by_tether()` query against `tether_id`.
  2. However, `LocalMessageBroker.route_task()` **signature does NOT accept `tether_id` as a parameter** and does NOT populate `tether_id` in its SQL `INSERT / UPDATE` queries.
  3. In `swarm_worker.py` (L635), during `CTRL_SCATTER` execution, `tether_id` is computed (`tether_id = str(config.get("tether_id", "scatter"))`), BUT when calling `broker.route_task()`, `tether_id` is omitted.
  4. Consequently, `task_queue.tether_id` remains the empty string `""` for ALL tasks.
  5. When `CTRL_MERGE` or fan-in nodes attempt tether-scoped gather via `self.broker.get_completed_by_tether(job_id=job_id, tether_id=_tether_id)`, the query `SELECT * FROM task_queue WHERE job_id = ? AND tether_id = ? AND lock_status = 'completed'` returns **0 rows**.
- **Impact on Phase 4.99 User Testing:** 8-agent scatter bursts using node tethering fail during fan-in artifact collection because `_peer_nodes` evaluates to empty set, producing empty or broken merged payloads.
- **Remediation Required:**
  - Add `tether_id: str = ""` to `route_task()` signature in `broker_interface.py` and `local_broker.py`.
  - Include `tether_id` in `INSERT INTO task_queue` and `ON CONFLICT DO UPDATE` statements in `local_broker.py`.
  - Pass `tether_id` in `swarm_worker.py` calls to `broker.route_task()`.

---

### 2.2 Task Queue Schema Constraint & Concurrency Collision (`UNIQUE(job_id, current_node)`)
- **File & Line Scope:** `local_broker.py` (L136, L490-502)
- **Defect Mechanism:**
  1. `task_queue` table enforces `UNIQUE(job_id, current_node)`.
  2. `route_task()` executes `INSERT ... ON CONFLICT(job_id, current_node) DO UPDATE SET lock_status='open', payload_path=excluded.payload_path, flow_line_id=excluded.flow_line_id, flow_vector=excluded.flow_vector...`
  3. When an 8-agent scatter burst launches parallel sub-tasks, if two parallel branches attempt to route to nodes with identical names, or if recursive re-queuing occurs, the `ON CONFLICT` clause overwrites `flow_line_id` and `flow_vector` of the existing row.
- **Impact:** Scoped scatter branches with duplicate agent names overwrite each other's state in single-table SQLite queues.
- **Remediation Required:** Ensure unique node ID naming (`flow_line_id` composite keys) during DAG synthesis; full database file partitioning per flow line is planned for Phase 6.13 (WAL Sharding by Flow Line).

---

### 2.3 Worker Process Crash Recovery & Zombie Lock Timeout
- **File & Line Scope:** `local_broker.py` (L287-386), `swarm_worker.py` (L529-540)
- **Defect Mechanism:**
  1. `fetch_and_lock_task()` sets `lock_status = 'locked'` and records `locked_by = agent_id`.
  2. If a worker process dies unexpectedly (e.g. `SIGKILL` or unhandled C-extension crash), `lock_status` remains `'locked'` in `task_queue` indefinitely.
  3. There is currently no active lock expiration or heartbeat monitor to reclaim locked tasks after a timeout (e.g. 15s).
- **Impact:** Prevents clean verification of Phase 4.99 Tier 3 Action 2 ("Worker Process Crash Recovery & Zombie Lock Reclaim").
- **Remediation Required:** Implement `reclaim_zombie_locks(timeout_seconds: float = 15.0)` in `local_broker.py` that resets stale `'locked'` tasks back to `'open'` and increments `loop_iteration_count`.

---

### 2.4 Quadrivector Failback vs. Inline `ROUTE_TO:` Regex Parsing
- **File & Line Scope:** `deterministic_nodes.py` (L821-960), `swarm_worker.py` (L1503-1557)
- **Defect Mechanism:**
  1. `CTRL_CONDITIONAL_ROUTE` in `deterministic_nodes.py` implements the full 4-vector cascade (Pass 1 Structured -> Pass 2 Keyword -> Pass 3 Score -> Pass 4 Fuzzy Levenshtein).
  2. In `swarm_worker.py` (L1505), inline model-directed routing uses `_ROUTE_TO_PATTERN = re.compile(r"ROUTE_TO:\s*([A-Za-z0-9_,\s\[\]{}]+)")`. If the model outputs a slightly misspelled node target (e.g. `ROUTE_TO:OSINT_Analyst_v2`), `swarm_worker` checks exact match or agent name match, but does NOT invoke fuzzy Levenshtein matching.
- **Impact:** Minor prompt variance in free-form LLM outputs can cause conditional routes to be ignored instead of fuzzy-matched.
- **Remediation Required:** Integrate `_try_fuzzy_route()` from `deterministic_nodes.py` into `swarm_worker.py`'s `ROUTE_TO:` fallback logic.

---

### 2.5 Single-Threaded Worker Loop vs. Parallel Scatter Threading
- **File & Line Scope:** `swarm_worker.py` (L508-537, L1686-1692)
- **Defect Mechanism:**
  1. `UniversalSwarmWorker` executes cycles sequentially in a single thread per worker process.
  2. For 8-agent scatter bursts, concurrent execution currently requires launching 8 distinct OS processes (`python swarm_worker.py` or `omni run`).
- **Impact:** Multi-worker execution relies on process-level concurrency rather than in-process multi-threading.
- **Remediation Required:** Planned for Phase 6.12 (`ThreadPoolExecutor` parallel scatter dispatch with `max_workers=8`).

---

## 3. ARCHITECTURAL ROADMAP PINNING MATRIX

Every audit finding, component state, and pending enhancement has been evaluated against `B:\EXO_GANS\Era2_architectural_roadmap.md` and `B:\EXO_GANS\Era3_architectural_roadmap.md` and pinned to its canonical phase:

| Audit Finding / Engine Feature | Target Domain Subsystem | Roadmap Phase Pinning | Implementation Status & Rationale |
| :--- | :--- | :--- | :--- |
| **`tether_id` Parameter Missing in `route_task()`** | `local_broker.py` & `swarm_worker.py` | **Phase 4.99** *(Immediate Fix)* | **Critical Bug.** Unpopulated `tether_id` breaks 8-agent scatter fan-in artifact collection. Must fix immediately for Phase 4.99 User Testing. |
| **Zombie Task Lock Reclaim Monitor** | `local_broker.py` | **Phase 4.99** *(Immediate Fix)* | **Required for Test Suite.** Tier 3 Action 2 requires auto-reclaiming tasks locked >15s after worker crash. |
| **Quadrivector Failback Alignment in `swarm_worker`** | `swarm_worker.py` | **Phase 4.99** *(Immediate Fix)* | **Integration Gap.** Aligning inline `ROUTE_TO:` parsing with `_try_fuzzy_route()` ensures 100% Quadrivector compliance. |
| **17 Deterministic Control Primitives (`CTRL_`)** | `deterministic_nodes.py` | **Phase 4.75.6** *(Past Phase)* | **Completed.** All 17 `CTRL_` handlers operational (`ANCHOR`, `RECURSION`, `PAUSE`, `GATE`, `CHECKPOINT`, `DELAY`, `TRANSFORM`, `SCATTER`, `MERGE`, `CONCAT`, `BRANCH`, `FILTER`, `CLEANUP`, `CONDITIONAL_ROUTE`, `END`, `PAYLOAD_INJECT`, `REVIEW`). |
| **7-Point Pre-Flight Topology Validator** | `topology_engine.py` | **Phase 4.75.6** *(Past Phase)* | **Completed.** Pre-execution audit verifying prompts, models, temperatures, DAG targets, wait-for tethers, cycles, and dialogue partners. |
| **SQLite WAL Scatter-Gather Task Queue** | `local_broker.py` | **Phase 4.75.7** *(Past Phase)* | **Completed Bedrock.** Concurrency-hardened queue with `BEGIN EXCLUSIVE` transactions and `flow_vector` lineage columns. |
| **8-Agent Scatter Slotting & DAG Auto-Wrap** | `flow_engine.py` | **Phase 4.75.7** *(Past Phase)* | **Completed Bedrock.** Dynamic auto-wrapping of `CTRL_SCATTER` steps into `CTRL_SCATTER` → 8 agents → `CTRL_MERGE` DAGs. |
| **`flow_vector` Lineage Logging (`>`)** | `swarm_worker.py` | **Phase 4.75.7** *(Past Phase)* | **Completed Bedrock.** Lineage string construction (`ROOT>SCATTER_0>Worker_A>MERGE_0`) saved per task row. |
| **`ThreadPoolExecutor` Parallel Scatter Execution** | `swarm_worker.py` | **Phase 6.12** *(Future Phase)* | **Planned.** Thread-pool dispatch (`max_workers=8`) for multi-branch `CTRL_SCATTER` within single worker processes. |
| **SQLite WAL Sharding by Flow Line** | `local_broker.py` | **Phase 6.13** *(Future Phase)* | **Planned.** Partitioning `task_queue` into dedicated per-flow-line database files (`swarm_queue_fl_<id>.db`) to eliminate write lock contention. |
| **Multi-Predicate `CTRL_GATE` Arrays (`predicates[]`)** | `deterministic_nodes.py` | **Phase 6.7** *(Future Phase)* | **Planned.** Expanding `CTRL_GATE` from single predicates to `predicates[]` arrays with `all`/`any` combinator logic. |
| **Time-Travel Replay & Branch Isolation** | `flow_engine.py` & TUI | **Phase 7.1** *(Future Phase)* | **Planned.** Parsing `flow_vector` lineage strings to scrub timelines and step through historical payload entry/exit snapshots. |
| **Agent Perspective Simulation ("Fly on the Wall")** | `flow_engine.py` & Memory | **Phase 7.2** *(Future Phase)* | **Planned.** Reconstructing an agent's operational trace across scatter branches into synthetic grounding context. |
| **Biological Neural Circuit & Ganglia Evolution** | `flow_engine.py` | **Phase 7.3** *(Future Phase)* | **Planned.** Formalizing MacroNodes as ganglia hubs and enabling dopaminergic inter-gate modulation via `SET_GATE`. |
| **Frozen State Sandboxing (`CandidateSandboxManager`)** | `flow_engine.py` | **Phase 9.5** *(Future Phase)* | **Planned.** Database cloning (`shutil.copy2`) into shadowed directories (`02_Dynamic_Context/sandboxes/candidate_<id>/`) for in-state testing. |

---

## 4. ACTIONABLE REMEDIATION PLAN FOR PHASE 4.99 USER TESTING

To guarantee 100% flawless execution of Phase 4.99 Omni-Actions (especially 8-Agent Scatter Burst & Lineage Audit and Worker Process Crash Recovery), the following code enhancements must be executed:

1. **Wire `tether_id` into `local_broker.py` & `swarm_worker.py`**:
   - Update `route_task()` signature: `def route_task(self, row_id: int, job_id: str, next_node_str: str, new_payload_path: str, actual_cost: float = 0.0, source_payload_path: str = "", max_recursion: int = 3, status: str = "completed", flow_line_id: str = "", tether_id: str = "", flow_vector: str = "") -> None`.
   - Update SQL `INSERT` and `ON CONFLICT DO UPDATE` queries in `local_broker.py` to persist `tether_id`.
   - Update `swarm_worker.py` (L642) to pass `tether_id=tether_id` when invoking `broker.route_task()`.

2. **Implement Zombie Task Lock Reclaim in `local_broker.py`**:
   - Add `reclaim_zombie_locks(timeout_seconds: float = 15.0) -> int` to `LocalMessageBroker`.
   - Execute `UPDATE task_queue SET lock_status = 'open', locked_by = NULL WHERE lock_status = 'locked' AND (strftime('%s', 'now') - strftime('%s', updated_at)) > timeout_seconds`.
   - Call `reclaim_zombie_locks()` automatically inside `fetch_and_lock_task()`.

3. **Integrate Fuzzy Levenshtein Fallback in `swarm_worker.py`**:
   - Import `_try_fuzzy_route` from `deterministic_nodes.py` in `swarm_worker.py`.
   - Fall back to `_try_fuzzy_route` when exact node ID and agent name lookups fail during `ROUTE_TO:` tag resolution.

---

## 5. CONCLUSION & VERIFICATION MANDATE

The `maccre_core/orchestration/` subsystem is structurally robust, with all 17 deterministic control primitives, Quadrivector failback logic, and 7-point pre-flight validation operational. Resolving the `tether_id` routing parameter disconnect and instantiating zombie lock reclamation will achieve 100% readiness for Phase 4.99 User Testing. All future engine enhancements (ThreadPoolExecutor scatter, WAL sharding, time-travel replay) are cleanly mapped to Era 3 Phases 6 through 9.
