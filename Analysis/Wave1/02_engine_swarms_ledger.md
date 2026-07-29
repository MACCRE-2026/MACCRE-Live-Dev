# Functional Ledger Report: MACCREv2 Core Engine Modules Analysis

**Target Modules Analyzed:**
1. `maccre_core/orchestration/deterministic_nodes.py` (41,120 bytes | 1,014 lines)
2. `maccre_core/orchestration/flow_engine.py` (69,925 bytes | 1,383 lines)
3. `maccre_core/orchestration/swarm_worker.py` (97,596 bytes | 1,685 lines)

---

# EXECUTIVE SUMMARY & SYSTEM ARCHITECTURE OVERVIEW

The `maccre_core/orchestration/` subsystem forms the sovereign execution engine of MACCREv2. It implements a multi-agent, graph-directed swarm orchestration pipeline governed by five core architectural tenets:
1. **Zero-Cloud Local State Machine (`LocalMessageBroker`)**: State, queue locks, task dependency management, and session history are backed by a local SQLite WAL-mode database (`swarm_queue.db`).
2. **Strangler-Fig Abstraction & Decoupled Execution**: Higher-level flow supervision (`FlowEngine`) is cleanly decoupled from low-level swarm worker loops (`UniversalSwarmWorker`) and non-LLM structural operations (`deterministic_nodes.py`).
3. **5-Tier Datacenter Path Anchoring**: File I/O strictly flows through canonical datacenter silos (`01_Raw_Source`, `02_Dynamic_Context`, `03_Agent_Ledgers`, `04_Code_Artifacts`, `05_Rendered_Media`) via runtime path resolution (`get_datacenter_path()`).
4. **The Diamond Loop Protocol**: Inference separates ideation/generation (`temperature=1.0`) from critical evaluation (`temperature=0.1` + strict JSON/Pydantic schemas), with integrated tool-execution loops and forensic thought auditing.
5. **Deterministic Control Primitive Interception**: Graph operations (fan-out scatter, fan-in merge, predicate gates, recursion counters, fallback routing, delay, cleanup) execute natively in Python without invoking LLM tokens.

---

# SECTION 1: DETAILED ANALYSIS — `deterministic_nodes.py`
*(41,120 bytes | 1,014 lines)*

## 1.1 Overview & Evaluation Contracts
`deterministic_nodes.py` defines structural, non-LLM control-flow primitives (`CTRL_` prefix, legacy `DET_` alias). When a topology node's `Node_ID` starts with `CTRL_` or `DET_`, `is_deterministic_node()` evaluates to `True`, prompting `UniversalSwarmWorker` to bypass the AI pipeline and route execution to `execute_deterministic_node()`.

### Key Evaluation Contracts:
- `is_deterministic_node(node_id: str) -> bool`: Checks if `node_id` starts with `CTRL_` or legacy `DET_` (case-insensitive, whitespace-trimmed).
- `_resolve_node_type(node_id: str) -> DeterministicNodeType | None`: Normalizes legacy `DET_` to `CTRL_` and performs longest-prefix matching against the `DeterministicNodeType` enum (16 supported types).
- `DeterministicNodeResult`: The standardized return contract object containing:
  - `output_payload_path: str` — Path to output ledger/artifact.
  - `next_node: str | None` — Single-target topology route override.
  - `next_nodes: list[str] | None` — Multi-target fan-out list (used by `CTRL_SCATTER` & `CTRL_CONDITIONAL_ROUTE`).
  - `should_pause: bool` — Signals worker to transition task status to `paused`.
  - `log_message: str` — Human-readable operational telemetry.
  - `payload_artifact: str` — JSON metadata (e.g., scatter chunk mapping).

- `execute_deterministic_node(...) -> DeterministicNodeResult`: Main dispatch function that looks up the node type in `_NODE_HANDLERS` dictionary and invokes the designated handler with `(node_id, payload_path, job_id, config, predecessor_payloads)`.

---

# SECTION 2: DETAILED ANALYSIS — `flow_engine.py`
*(69,925 bytes | 1,383 lines)*

## 2.1 Overview & Primary Data Structures
`flow_engine.py` acts as a Supervisor over `UniversalSwarmWorker`. It manages linear and graph execution of MacroNode chains, performs pre-flight validation, hydra-compiles topology CSV files dynamically, handles execution cycles & resume states, and synthesizes unified session ledgers.

---

# SECTION 3: DETAILED ANALYSIS — `swarm_worker.py`
*(97,596 bytes | 1,685 lines)*

## 3.1 Overview & System Identity
`UniversalSwarmWorker` is the core execution node of MACCREv2. It executes individual task cycles popped from `LocalMessageBroker`, binding LLM calls to `UniversalRouter`, managing memory engines, executing tool calls via `ToolExecutor`, and handling complex multi-agent execution modes.
