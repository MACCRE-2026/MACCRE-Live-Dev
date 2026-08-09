# Phase 4.99 User Test Actions — Orchestration & Swarm Engine Subsystem

**Author:** OrchestrationAndEngine_Oracle  
**Target Subsystem:** `maccre_core/orchestration/`  
**Execution Gateway:** `omni run` / `omni qa`  
**Date:** 2026-07-28  

---

### Action 1: High-Concurrency Fan-Out / Fan-In Scatter-Merge with Tether Isolation
* **Target Codebase Component:** `deterministic_nodes.py` (`CTRL_SCATTER`, `CTRL_MERGE`), `flow_engine.py` (`tether_id` isolation & `flow_vector` tracking), `local_broker.py` (SQLite WAL Scatter-Gather Task Queue).
* **Step-by-Step Operator Action:**
  1. Construct a flow sheet topology containing an entry node routing into a `CTRL_SCATTER` primitive configured to spawn 8 parallel agent sub-tasks (`Worker_Agent_1` through `Worker_Agent_8`).
  2. Execute the flow engine via `omni run maccre_core/orchestration/flow_engine.py --flow test_scatter_8way`.
  3. Observe worker process spawning, payload distribution, and queue insertion in `local_broker`.
  4. Monitor convergence at downstream `CTRL_MERGE` node.
* **Edge-Case / Stress Condition:**
  * **Max 8-Agent Scatter Contention:** 8 concurrent worker tasks writing results back to SQLite WAL simultaneously under heavy contention.
  * **Tether Isolation:** Auto-generation of unique `tether_id` (e.g., `tether_a1b2c3d4`) at `CTRL_SCATTER` to prevent payload leakage between concurrent flow executions.
  * **Out-of-Order Task Completion:** Worker 7 finishes before Worker 1; `CTRL_MERGE` must remain blocked until all 8 sibling tasks matching `tether_id` transition to `COMPLETED`.
* **Expected System Behavior & Engine Validation Criteria:**
  * `CTRL_SCATTER` creates 8 distinct queue items in `local_broker`, each tagged with identical `tether_id` and updated `flow_vector` breadcrumbs (`ROOT > CTRL_SCATTER_1 > Worker_Agent_N`).
  * `local_broker` executes claims and status transitions using `BEGIN EXCLUSIVE` SQLite transactions without raising `sqlite3.OperationalError: database is locked`.
  * `CTRL_MERGE` holds downstream execution until 100% of tasks associated with `tether_id` are finished, then consolidates the 8 payloads into a single structured array document for downstream processing.

---

### Action 2: Recursive Loop Boundary & Max Iteration Guardrail Test
* **Target Codebase Component:** `deterministic_nodes.py` (`CTRL_RECURSION`), `flow_engine.py` (DAG Cycle Resolution & State Context).
* **Step-by-Step Operator Action:**
  1. Define a cyclic workflow: `Node_A` -> `Node_B` -> `CTRL_RECURSION_1` -> `Node_A` with `max_recursion=5` and an iteration condition (`counter < 10`).
  2. Execute the flow with initial state payload `{"counter": 0}`.
  3. Track execution state across repeated back-edge jumps.
* **Edge-Case / Stress Condition:**
  * **Boundary Breach Condition:** Loop predicate (`counter < 10`) is deliberately NOT satisfied within 5 iterations.
  * **Cycle Validation Bypass:** `topology_engine.py` must distinguish explicit `CTRL_RECURSION` control loops from unauthorized infinite DAG cycles.
* **Expected System Behavior & Engine Validation Criteria:**
  * `topology_engine.py` preflight check identifies `CTRL_RECURSION` as a valid control node and passes DAG verification.
  * `flow_engine.py` increments `recursion_count` state context on each iteration.
  * Upon reaching iteration 5 (`iteration == max_recursion`), `CTRL_RECURSION` intercepts execution, logs boundary breach warning `[CTRL_RECURSION] Max recursion (5) reached — proceeding to fallback path`, breaks the loop, and forces execution downstream (or to `Next_Node_Fallback`), preventing stack overflow or infinite looping.
  * `flow_vector` captures exact iteration breadcrumbs (e.g., `ROOT > Node_A > Node_B > CTRL_RECURSION[iter:5] > Next_Node_Fallback`).

---

### Action 3: Quadrivector Failback Routing & Dynamic Keyword/Score Fallback Cascade
* **Target Codebase Component:** `deterministic_nodes.py` (`CTRL_CONDITIONAL_ROUTE`), `swarm_worker.py` (Payload Parsing & Evaluation).
* **Step-by-Step Operator Action:**
  1. Instantiate a flow with `CTRL_CONDITIONAL_ROUTE_1` configured with 4 routing vectors:
     * *Vector 1 (Structured):* Standard JSON schema check (`payload.status == "SUCCESS"`) -> `Node_Success`.
     * *Vector 2 (Keyword):* Substring search (`"CRITICAL_FAILURE"` in payload) -> `Node_Emergency_Repair`.
     * *Vector 3 (Score):* Semantic similarity threshold score (>0.85) -> `Node_High_Confidence`.
     * *Vector 4 (Fuzzy/Fallback):* Catch-all default node -> `Node_Default_Review`.
  2. Execute 4 distinct test payloads engineered to trigger each vector:
     * *Run A:* Unstructured malformed JSON payload missing `"status"`.
     * *Run B:* Plaintext string containing `"CRITICAL_FAILURE"`.
     * *Run C:* Text scoring low confidence (<0.50).
     * *Run D:* Ambiguous empty string.
* **Edge-Case / Stress Condition:**
  * Cascading multi-vector failure (Vector 1 fails JSON parse -> Vector 2 finds no keywords -> Vector 3 fails score -> Vector 4 fallback execution).
* **Expected System Behavior & Engine Validation Criteria:**
  * Run A: Gracefully recovers from JSON deserialization exception and evaluates Vector 2.
  * Run B: Route match on Vector 2 immediately dispatches to `Node_Emergency_Repair`.
  * Run C & D: Execution cascades cleanly through Vectors 1–3 and deterministically lands on Vector 4 (`Node_Default_Review`).
  * Telemetry log in `03_Agent_Ledgers` records exact Quadrivector decision path, evaluation scores, and final route selection.

---

### Action 4: Predicate Gate Evaluation with Asynchronous Prerequisite Wait & Timeout Halting
* **Target Codebase Component:** `deterministic_nodes.py` (`CTRL_GATE`), `flow_engine.py` (Prerequisite State Resolution), `local_broker.py`.
* **Step-by-Step Operator Action:**
  1. Set up a workflow where `Node_Consolidation` is gated by `CTRL_GATE_1` requiring completion of prerequisite nodes `["Task_Alpha", "Task_Beta", "Task_Gamma"]` with `timeout_seconds=30`.
  2. Perform **Test Run 1 (Timeout Stress):** Artificially delay `Task_Gamma` completion past 30 seconds.
  3. Perform **Test Run 2 (Fast Completion):** Complete all 3 tasks within 3 seconds.
* **Edge-Case / Stress Condition:**
  * Partial prerequisite completion (`Task_Alpha` and `Task_Beta` completed, `Task_Gamma` timed out or stuck in `PROCESSING`).
* **Expected System Behavior & Engine Validation Criteria:**
  * Test Run 1: `CTRL_GATE_1` detects missing `Task_Gamma` at the 30-second mark, logs `[CTRL_GATE] Prerequisite timeout expired for Task_Gamma`, halts downstream step dispatch, and flags task status as `FAILED_PREREQUISITE_TIMEOUT`.
  * Test Run 2: `CTRL_GATE_1` polling evaluates predicate to `True` as soon as `Task_Gamma` completes, releasing `Node_Consolidation` to the execution queue within <50ms.

---

### Action 5: Dynamic Next-Node Target Hydration & Missing Fallback Recovery
* **Target Codebase Component:** `flow_engine.py` (`_hydrate_topology`, comma-split target parsing, `step_config` passthrough), `topology_engine.py`.
* **Step-by-Step Operator Action:**
  1. Execute a flow step with dynamic `Next_Node` target string formatted with leading/trailing whitespace and comma separators: `" Node_Sub_A , Node_Sub_B , CTRL_CHECKPOINT_1 "`.
  2. Perform **Case A:** Pass a non-existent target node ID (`"Node_Missing_99"`) without fallback.
  3. Perform **Case B:** Pass a non-existent target node ID (`"Node_Missing_99"`) WITH `Next_Node_Fallback="CTRL_ANCHOR_FALLBACK"`.
* **Edge-Case / Stress Condition:**
  * Dynamic target node resolution at runtime after static DAG preflight has passed.
* **Expected System Behavior & Engine Validation Criteria:**
  * `_hydrate_topology` cleanly strips whitespace and splits target string into 3 separate downstream step specifications.
  * Case A: Flow engine catches unresolvable node `Node_Missing_99`, raises `TopologyExecutionError`, appends error log to `system_logs.db`, and transitions flow to `HALTED_MISSING_NODE` cleanly without process hangs.
  * Case B: Flow engine detects missing `Node_Missing_99`, intercepts execution, logs warning `[FLOW_ENGINE] Dynamic target missing. Routing to fallback CTRL_ANCHOR_FALLBACK`, and seamlessly resumes execution at `CTRL_ANCHOR_FALLBACK`.

---

### Action 6: Swarm Worker Crash Recovery & Zombie Task Reclaim in SQLite Queue
* **Target Codebase Component:** `swarm_worker.py` (Heartbeat & Exception Teardown), `local_broker.py` (Task Reclaim & Lock Expiry).
* **Step-by-Step Operator Action:**
  1. Launch `swarm_worker.py` listening on local broker queue.
  2. Submit a long-running execution task (`Node_Heavy_Processing`).
  3. Simulate an abrupt worker crash (`SIGKILL` or `sys.exit(1)`) while task is in `PROCESSING` state with lock timestamp `t_0`.
  4. Spin up a secondary worker node after lock timeout period (`reclaim_timeout_seconds=15`).
* **Edge-Case / Stress Condition:**
  * Abrupt process crash leaving orphaned `PROCESSING` status, active lock ID, and unclosed connection handles.
  * Concurrent reclaim race condition between two newly spawned replacement workers.
* **Expected System Behavior & Engine Validation Criteria:**
  * `local_broker` lock monitor detects expired lock timestamp (`t_current - t_0 > 15s`).
  * Expired lock is atomically cleared inside a `BEGIN EXCLUSIVE` transaction.
  * Task status is reset from `PROCESSING` to `PENDING` with `retry_count` incremented to `1`.
  * Secondary worker claims the reclaimed task, successfully completes execution (`SUCCESS`), and appends a zombie reclamation log to `03_Agent_Ledgers`.

---

### Action 7: 7-Point Pre-flight Topology Validation under Structural DAG Anomaly Injections
* **Target Codebase Component:** `topology_engine.py` (7-Point Pre-flight Verification Suite).
* **Step-by-Step Operator Action:**
  1. Construct a synthetic flow sheet topology containing 5 intentional structural anomaly injections:
     1. Unconnected orphan node (`Node_Orphan_1`).
     2. Uncontrolled cycle (missing `CTRL_RECURSION`).
     3. Missing entry node (no `CTRL_ANCHOR`).
     4. Target node referencing an unregistered Agent persona.
     5. Missing terminal state (omitted `CTRL_END`).
  2. Execute preflight validation: `omni run maccre_core/orchestration/topology_engine.py --validate-sheet synthetic_bad_flow`.
* **Edge-Case / Stress Condition:**
  * Multi-fault topology evaluation requiring full scan without premature abort.
* **Expected System Behavior & Engine Validation Criteria:**
  * `topology_engine.py` runs all 7 checks (Entry, Exit, Reachability, Cycle Safety, Target Resolution, Agent Persona Registration, Control Syntax).
  * Validator fails preflight with `ValidationResult(passed=False)` and outputs structured diagnosis detailing all 5 anomaly violations with exact line numbers and node IDs.
  * System prevents flow launch, ensuring zero hardware compute or token costs are incurred.

---

### Action 8: End-to-End Context Injection & Flow Lineage Breadcrumb Audit (`flow_vector`)
* **Target Codebase Component:** `flow_engine.py` (Step Context & Lineage Tracking), `telemetry_db.py` (`system_logs.db`).
* **Step-by-Step Operator Action:**
  1. Execute a multi-branch flow (`CTRL_ANCHOR` -> `Node_Extract` -> `CTRL_TRANSFORM` -> `CTRL_SCATTER` (2 sub-tasks) -> `CTRL_MERGE` -> `CTRL_END`).
  2. Inspect state context and payload metadata at each node execution step.
  3. Query `system_logs.db` for the resulting `flow_vector` lineage entries.
* **Edge-Case / Stress Condition:**
  * Long lineage strings containing special routing delimiters (`>`) and parallel sub-task branch identifiers.
* **Expected System Behavior & Engine Validation Criteria:**
  * Every executed step appends its node ID and execution scope to `flow_vector` (e.g., `ROOT > CTRL_ANCHOR > Node_Extract > CTRL_TRANSFORM > CTRL_SCATTER[tether_99] > SubTask_1 > CTRL_MERGE > CTRL_END`).
  * All step configuration context (`step_config`, `parent_tether_id`) persists cleanly across step boundaries.
  * Audit records in `system_logs.db` allow 100% deterministic post-mortem reconstruction of the execution trail.
