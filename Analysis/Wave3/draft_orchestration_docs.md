# ORCHESTRATION & SWARM ENGINE SUBSYSTEM DOCUMENTATION DRAFT

> **Architectural Status:** Wave 3 Documentation Audit Compliant  
> **Source Verification:** `maccre_core/orchestration/` (`deterministic_nodes.py`, `flow_engine.py`, `swarm_worker.py`, `local_broker.py`, `macro_factory.py`, `dialogue_runner.py`, `topology_engine.py`)  

---

## PART 1: CONTRIBUTION TO `B:\EXO_GANS\README.MD`

### 3. Core Swarm Engine & Orchestration Architecture

MACCREv2 / EXO_GANS operates a graph-directed multi-agent swarm engine governed by local state machines, zero-cloud queuing, and explicit deterministic execution boundaries.

```
                  +-------------------------------------------------------+
                  |               FlowEngine (Supervisor)                 |
                  |  - Hydra Topology Compiler    - Lineage Ledger (WAL)  |
                  +--------------------------+----------------------------+
                                             |
                                             v
                  +-------------------------------------------------------+
                  |      TopologyEngine & 7-Point Pre-Flight Audit        |
                  +--------------------------+----------------------------+
                                             |
                                             v
                  +-------------------------------------------------------+
                  |    LocalMessageBroker (swarm_queue.db SQLite WAL)      |
                  |  - UNIQUE(job_id, node)       - BEGIN EXCLUSIVE Lock  |
                  +--------------------------+----------------------------+
                                             |
                                             v
                  +-------------------------------------------------------+
                  |               UniversalSwarmWorker                    |
                  |  - Token Execution              - Deterministic Bypass|
                  +------------+-------------------------------+----------+
                               |                               |
                               v                               v
                 [ AI Task / UniversalRouter ]       [ Deterministic Control Nodes ]
                 (Gemini REST / Ollama Local)        (16 CTRL_ Primitives / Python)
```

#### 3.1 Scaffolding Philosophy & Decoupled Execution
The swarm engine adheres strictly to the **Zero-Cloud Local State Machine** and **Deterministic Scaffolding** doctrines:
- **Zero Cloud Queueing**: Task queues, worker locks, dependency wait-states, and session lineage are stored entirely in a local SQLite WAL-mode database (`swarm_queue.db`), eliminating external brokers like Redis or RabbitMQ.
- **Deterministic Bypass**: Non-LLM structural operations (anchoring, conditional gating, payload scatter/merge, filtering, loops, cleanup) are defined with the `CTRL_` prefix (or legacy `DET_`). When `is_deterministic_node()` evaluates to `True`, execution routes directly to native Python handlers in `deterministic_nodes.py`, bypassing AI model invocation and saving API tokens.
- **Strangler-Fig Abstractions**: Execution components interact exclusively via abstract base classes (`MessageBroker`, `TopologyProvider`), enabling hardware-agnostic runtime substitution without mutating pipeline logic.

#### 3.2 FlowEngine Supervisorship
The `FlowEngine` serves as the top-level supervisor over worker loops (`UniversalSwarmWorker`):
- **Hydra Topology Compilation**: Loads and compiles `topology.csv` graphs dynamically into executable runtime flow structures.
- **State Machine Supervision**: Manages execution state transitions (`Idle` -> `Running` -> `Paused` -> `Terminated`/`Canonized`), ensuring safe worker thread execution and background interrupt processing.
- **Lineage Tracking**: Tracks exact node execution sequences using the `flow_vector` attribute stored inside `swarm_queue.db`, enabling time-travel auditing and execution step replay.
- **Unified Ledger Synthesis**: Assembles multi-turn execution results into clean session ledgers (`unified_session_ledger.md`) and thought audits (`unified_thoughts_ledger.md`) in `03_Agent_Ledgers` and `04_Code_Artifacts`.

#### 3.3 The 16 Deterministic ControlNode Primitives
All structural control logic executes through 16 deterministic primitives defined in `DeterministicNodeType` (`deterministic_nodes.py`):

| Primitive Enum | Node ID Pattern | Functional Specification |
| :--- | :--- | :--- |
| `ANCHOR` | `CTRL_ANCHOR` | Entry marker and pass-through payload anchor; returns input payload unaltered. |
| `RECURSION` | `CTRL_RECURSION` | Multi-pass loop counter; tracks iteration count and routes to loop body or exit node. |
| `PAUSE` | `CTRL_PAUSE` | Execution breakpoint; transitions task state to `paused` for manual operator intervention. |
| `GATE` | `CTRL_GATE` | Conditional barrier; holds downstream dispatch until all prerequisite `WAIT_FOR` nodes finish. |
| `CHECKPOINT` | `CTRL_CHECKPOINT` | Payload snapshot manager; writes current payload state to disk artifact storage. |
| `DELAY` | `CTRL_DELAY` | Wall-clock execution throttle; sleeps for a configurable duration (seconds). |
| `TRANSFORM` | `CTRL_TRANSFORM` | Formatting engine; applies static text wrappers or string template transformations to payloads. |
| `SCATTER` | `CTRL_SCATTER` | Fan-out distributor; splits or replicates payload across multiple downstream target nodes. |
| `MERGE` | `CTRL_MERGE` | Fan-in aggregator; consolidates multiple upstream payload files into a single structured document. |
| `CONCAT` | `CTRL_CONCAT` | Sequential concatenator; appends predecessor payloads end-to-end without header formatting. |
| `BRANCH` | `CTRL_BRANCH` | Substring match router; scans payload for keywords to select single target downstream node. |
| `FILTER` | `CTRL_FILTER` | Text sanitizer; applies regex pattern removal, section trimming, or payload truncation rules. |
| `CLEANUP` | `CTRL_CLEANUP` | Garbage collector; purges temporary runtime scratch files matching glob patterns. |
| `CONDITIONAL_ROUTE` | `CTRL_CONDITIONAL_ROUTE` | 4-vector fallback priority router (Structured -> Keyword -> Score -> Fuzzy). |
| `END` | `CTRL_END` | Terminal graph sink; marks flow execution as complete. |
| `PAYLOAD_INJECT` | `CTRL_PAYLOAD_INJECT` | Direct payload injector; overwrites current payload with static string/config data. |

#### 3.4 Quadrivector Failback Routing (`CTRL_CONDITIONAL_ROUTE`)
`CTRL_CONDITIONAL_ROUTE` implements a robust 4-stage priority evaluation hierarchy to route tasks dynamically without relying exclusively on brittle string matches:

1. **Structured Match**: Scans payload for explicit `[ROUTE_TO: TargetNode]` tags.
2. **Keyword Gate**: Evaluates payload against `keyword_map` dictionary using case-insensitive substring and regex patterns.
3. **Score Threshold**: Extracts floating-point evaluation tags `[SCORE: X.XX]` via regex and compares against `score_threshold` (default `0.7`).
4. **Fuzzy Match**: Computes string Levenshtein distance between payload text and available target names, accepting matches within `fuzzy_max_distance` (default `3`).
5. **Fallback**: If all 4 vectors fail to resolve, routes execution to `default_target` (defaults to `END`).

---

## PART 2: CONTRIBUTION TO `B:\EXO_GANS\MACCRE_OPERATOR_MANUAL.MD`

### Chapter 4: Swarm Topology Engineering & Execution Mechanics

#### 4.1 Step-by-Step DAG Topology Creation
1. **Identify Roles & Directives**: Select required agent personas from `agent_roster.csv` or define ad-hoc `INSTRUCTION_OVERRIDE` prompts.
2. **Map Execution Paths**: Establish sequence connections using `NEXT_NODE_SUCCESS` and `NEXT_NODE_FAILURE`.
3. **Insert Control Primitives**: Structure branching, fan-out, fan-in, or pause points using `CTRL_` nodes.
4. **Deploy & Authorize**: Save CSV to `02_Dynamic_Context/topology.csv`.

#### 4.2 7-Point Pre-Flight DAG Topology Validation Protocol
Before spending tokens, `TopologyEngine.validate()` executes a 7-point audit:
1. **Instruction Check**: Verifies non-empty prompt directives.
2. **Model Validation**: Ensures valid model string.
3. **Temperature Audit**: Checks range $[0.0, 2.0]$.
4. **DAG Target Resolution**: Verifies target existence or terminal sentinels (`STOP`, `DONE`, `TERMINATE`, `FAILED`, `HUMAN_GATE`, `END`).
5. **Wait_For Dependency Audit**: Verifies wait targets exist and warns if fan-in $>5$.
6. **Circular Cycle Detection**: DFS recursion on dependency graph to catch deadlocks.
7. **Dialogue Partner Roster Audit**: Verifies dialogue partner exists in `agent_roster.csv` when `DIALOGUE_ROUNDS > 0`.
