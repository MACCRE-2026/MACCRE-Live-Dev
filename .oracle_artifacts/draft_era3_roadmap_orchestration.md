# Era 3 Swarm Engine & Orchestration Architectural Roadmap
**Domain:** Orchestration & Swarm Engine Infrastructure (`maccre_core/orchestration/`)  
**Author:** Orchestration & Engine Specialist Oracle  
**Status:** Era 3 Architectural Synthesis & Roadmap Blueprint  

---

## 1. Executive Summary & Subsystem Foundation

The `maccre_core/orchestration/` subsystem forms the sovereign execution engine of MACCREv2 / EXO_GANS. It operates as a multi-agent, graph-directed swarm orchestration pipeline governed by five core architectural tenets:

1. **Zero-Cloud Local Queue State Machine (`LocalMessageBroker`)**: Execution state, queue locks, task dependency management, and session histories are persisted in local SQLite WAL-mode databases (`swarm_queue.db`).
2. **Strangler-Fig Abstraction & Decoupled Supervision**: Flow supervision (`FlowEngine`) is decoupled from low-level swarm worker execution loops (`UniversalSwarmWorker`) and non-LLM control primitives (`deterministic_nodes.py`).
3. **5-Tier Datacenter Path Anchoring**: All filesystem operations dynamically resolve relative to `get_maccre_root()` and `get_datacenter_path()` (`01_Raw_Source`, `02_Dynamic_Context`, `03_Agent_Ledgers`, `04_Code_Artifacts`, `05_Rendered_Media`).
4. **The Diamond Loop Protocol**: Inference strictly separates ideation/generation (`temperature=1.0`) from critical extraction/evaluation (`temperature=0.1` + Pydantic schema validation), with full logging of both prompt-based (`<thought>`) and native API-level (`api_thought` via `thinkingConfig`) reasoning.
5. **Biological Neural Circuit Motifs**: Deterministic control primitives (`CTRL_`) act as biological circuit motifs (axonal scatter, dendritic merge, synaptic gating, lateral inhibition), while MacroNodes function as self-contained enteric ganglia.

---

## 2. Category 1: Implemented Swarm Engine & ControlNode Features

The current production runtime exhibits a fully realized, topology-first orchestration layer:

### 2.1 Complete 17-Primitive `CTRL_` Control Node Suite (`deterministic_nodes.py`)
All deterministic nodes execute natively in Python without consuming LLM tokens:
- **`CTRL_SCATTER`**: Axonal fan-out projection; splits payloads across 2–10 agent slots with `tether_id` and `flow_line_id` parentage assignment.
- **`CTRL_MERGE`**: Spatial dendritic summation; collects and structures outputs from all flow lines bound to a shared `tether_id` (`## Source: {node}`).
- **`CTRL_CONCAT`**: Temporal dendritic summation; flat string concatenation with configurable delimiters (`concat_delimiter`).
- **`CTRL_BRANCH`**: Winner-Take-All (WTA) keyword router; scans payload for matching tokens and routes to designated target paths.
- **`CTRL_CONDITIONAL_ROUTE`**: Multi-layered WTA router featuring the **Quadrivector Failback Chain** (Structured Output Pass 2 → Keyword Gate → Score Threshold → Fuzzy ROUTE_TO Levenshtein distance ≤ 2).
- **`CTRL_FILTER`**: Feedforward inhibition; strips unwanted payload sections via predicate rules (`strip_sections`, `max_chars`, `regex_remove`).
- **`CTRL_CLEANUP`**: Glial waste removal; deletes temporary workspace files matching glob patterns.
- **`CTRL_PAUSE`**: Persistent breakpoint; halts worker loop, logs custom `pause_message`, and supports `auto_resume_after` timed sleeps.
- **`CTRL_DELAY`**: Configurable sleep primitive for rate-limiting or external IO synchronization.
- **`CTRL_CHECKPOINT`**: Long-Term Potentiation (LTP); snapshots payload state to `{node_id}_{label}_checkpoint.md`.
- **`CTRL_RECURSION`**: Recurrent excitation loop; maintains feedback cycles with hard refractory counters (`Max_Recursion`, `loop_target`).
- **`CTRL_TRANSFORM`**: Signal shaping; reshapes payload content using string templates.
- **`CTRL_ANCHOR`**: Soma / cell body integration point; named junction for topological routing references.
- **`CTRL_REVIEW`**: Neuromodulatory human-in-the-loop (HITL) gate; interrupts execution for manual operator approval.
- **`CTRL_GATE`**: Synaptic gate; predicate-based "Floating If" evaluating `payload_exists`, `payload_contains`, `artifact_exists`, or `gate_state`, executing `PASS`, `BLOCK`, `ROUTE_TO:<node>`, or inter-gate neuromodulation via `SET_GATE:<id>=<state>`.
- **`CTRL_END`**: Terminal passthrough node signaling flow completion.
- **`CTRL_PAYLOAD_INJECT`**: Content injector writing custom text to downstream execution steps.

### 2.2 FlowEngine Supervisorship & Hydra-Compilation (`flow_engine.py`)
- Dynamic compilation of CSV/JSON topologies into executable DAGs.
- `CTRL_` auto-wrapping: automatically synthesizes scatter→agents→merge topologies when `CTRL_` steps are placed directly in linear flow sequences.
- Pre-flight graph hydration, node namespace isolation (`{macronode}_{agent}_{uuid}`), cycle management, and resume-from-disk capabilities.

### 2.3 SQLite WAL Scatter-Gather Task Queue (`local_broker.py`)
- Zero-cloud, high-concurrency message broker using SQLite WAL mode (`swarm_queue.db`).
- Strict transaction isolation (`BEGIN EXCLUSIVE`) with busy-timeout resiliency.
- `flow_line_id` parentage tracking (`FL_alpha_0`, `FL_alpha_0.FL_beta_1`) for nested scatter/gather scoping.
- `flow_vector` colon-delimited lineage string (`SCATTER_A:Agent_B:MERGE_A`) tracking complete task ancestry.

### 2.4 7-Point Pre-Flight DAG Topology Validation (`topology_engine.py`)
Pre-execution validation protocol guaranteeing:
1. Single root/entry point existence.
2. Valid edge target references (`Next_Node` targets exist).
3. Dependency loop safety (uncapped recursion detection).
4. `Wait_For` tether integrity (sink nodes reference active sources).
5. Roster alignment (`Agent_Name` maps to `agent_library.db` or `CTRL_` primitive).
6. Datacenter path availability.
7. Payload schema compatibility.

### 2.5 Session Dictionary & Agent Overrides (`Flow-$Session.dict`)
- Flow-level session dictionary specifying global metadata (`_flow_meta`) and per-agent profile overrides.
- `AgentProfileOverridesModal` allowing per-session tuning of system prompts, models, temperature, thinking levels, and tool assignments without mutating the global agent library.
- Strict precedence resolution: `Flow Dict > Topology CSV > Agent Library DB`.

---

## 3. Category 2: Unfinished & Deferred Engine Roadmap Items

The following features represent active engineering initiatives deferred to upcoming Phase 6 updates:

### 3.1 Dynamic Neural Topology Adaptation & Live Graph Rewiring
- **Mid-Execution Cell Patching**: Dynamic modification of running topology graphs via `topology_engine.py` (`patch_node()`). Allows changing an active node's model, instructions, or target paths without restarting the flow session.
- **`rewrite_topology_node` Tool**: Exposing live graph patching to the Nexus Copilot agent for autonomous, mid-flight workflow optimization.

### 3.2 Autonomous Scatter Autoscaling & Parallel Threading
- **ThreadPoolExecutor Parallelism**: Refactoring `swarm_worker.py` to dispatch scatter targets across a thread pool (`max_workers=MAX_SCATTER_AGENTS`, default 8, hard cap 12) for true parallel API execution.
- **API Rate-Limit Guarding**: Multi-threaded throttle management respecting paid Gemini 3.x RPM/TPM limits across parallel worker threads.

### 3.3 SQLite WAL Sharding by Flow Line
- **Per-Flow-Line Database Partitioning**: To eliminate write contention during parallel scatter execution, shard `task_queue` and telemetry across separate WAL database files (`swarm_queue_fl_<id>.db`).
- **Shard Manifest Management**: Centralized master DB tracking active shards, merging ledger records upon flow line completion.

### 3.4 High-Order Recursion & Multi-Predicate Gating
- **Multi-Predicate Gating Arrays**: `CTRL_GATE` upgrade supporting `predicates[]` with `predicate_logic: all|any`.
- **Advanced Predicate Types**: `flow_state` (upstream completion checks), `counter_threshold` (numeric comparison), `expression` (Python context evaluation).
- **`SCATTER_TO` Action**: Dynamic fan-out triggering upon gate evaluation.

### 3.5 Interactive HITL & Paused-Session Live Topology Injection
- **Paused-Session Topology Modifiers**: Clickable insertion pointers on paused flow lines enabling operators to inject agents, MacroNodes, or `CTRL_` nodes mid-stream.
- **Node Removal Controls**: Red "✕" node deletion buttons active during pause or pre-flight states.

### 3.6 Future Control Primitives
- **`CTRL_WEBHOOK`**: HTTP event trigger primitive.
- **`CTRL_EDGE_SYNC`**: Google Drive folder watchdog polling for local edge LLM responses (e.g., S25 Ultra integration).
- **`CTRL_CHAT`**: Interactive HITL node variants (Chat w/ Preceding Agent, Chat w/ Next Agent, Ephemeral Group Chat).

### 3.7 Advanced Probabilistic Steering
- Swarm worker regex parser expansion to intercept dynamic LLM steering commands (`SPAWN_NODE`, `SKIP_TO`, `FORK`).

---

## 4. Category 3: Proposed Era 3 Swarm Engine Architectural Goals

Era 3 establishes the next evolutionary leap for Sovereign Edge orchestration:

### Goal 3.1: Sovereign Time-Travel Replay & Branch Isolation
- **`flow_vector` Lineage Parsing**: Utilizing the `flow_vector` ancestry schema planted in Phase 4.75.7 to isolate any scatter branch's full operational history.
- **Timeline Reconstruction & Scrubber**: Step-by-step state replay using entry/exit payload snapshots from `03_Agent_Ledgers`. Operators can scrub through historical runs node-by-node.
- **Zero-Cloud Database Forking**: instant checkpointing via local file cloning (`shutil.copy2(swarm_queue.db, checkpoint.db)`).

### Goal 3.2: Agent Perspective Simulation & "Fly on the Wall" Telemetry Grounding
- **Chronological Agent Tracing**: Filtering session ledgers by agent identity across disparate scatter branches to evaluate behavioral consistency.
- **Observer Telemetry Injection ("Fly on the Wall")**: Compiling an agent's complete operational trace into synthetic context vectors. Future agents absorb decision context, payload evolutions, and outcomes without having participated in the original flow.

### Goal 3.3: Counterfactual Swarm Simulation & Divergent Replay
- **Path Replay with Model Variants**: Re-running exact historical payload sequences through alternative agent configurations (e.g., swapping `gemini-3.5-flash` with `gemini-3.1-pro-preview` or adjusting system prompts).
- **Side-by-Side Visual Diffing**: Node-by-node comparisons of original vs. counterfactual outputs to quantify quality and performance deltas.

### Goal 3.4: Biological Neural Circuit Motifs & Ganglia Evolution
- **Enteric Ganglia Autonomy**: Formalizing MacroNodes as autonomous processing hubs (ganglia) capable of local feedback loops and internal gating.
- **Hebbian Topological Learning**: Automatically evaluating completed execution ledgers via a Diamond Loop Critic (`fork_synthesizer.py`), promoting high-performing DAG topologies directly to `definitions.db` (`topology_library`).
- **Dopaminergic Inter-Gate Modulation**: Utilizing `SET_GATE` commands to create topological logic networks where upstream state changes dynamically modulate downstream synaptic transmission probabilities across the swarm.

### Goal 3.5: Generative Swarm Recruitment Engine
- Evolving the Prompt Engineer from an active generator into a silent, passive context monitor.
- Contextual analysis of live session context windows to automatically conceptualize, construct, and register specialized sub-agents into a dynamic "Recruitment Roster" for testing and promotion.

### Goal 3.6: FinOps-Gated Multimodal Ingestion & Temporal Extrapolation
- **Visionary Scout Spatial Extraction**: Multi-modal ingestion of static media (e.g., comic panels), extracting narrative text, dialogue tags, and spatial bounding boxes into `memory.db` (sqlite-vec + FTS5).
- **The FinOps Onion**: Interactive TUI authorization overlay calculating estimated USD burn for high-cost generative operations before execution.
- **Generative Temporal Extrapolation**: Image-to-Video generative pipelines using extracted spatial/dialogue context as temporal prompts to predict and animate 2 seconds prior to and 2 seconds following a static image ("live photo" effect).

---

## 5. Architectural Comparison & Competitive Position

| Dimension | LangGraph | CrewAI | AutoGen / AG2 | MACCREv2 / EXO_GANS (Era 3) |
|---|---|---|---|---|
| **Architecture** | Directed Cyclic Graph | Role-based Crews | Actor Model | **Queue-Unrolled Sovereign DAG** |
| **State Model** | In-Memory Typed State | Task/Flow SQLite | Conversation History | **Durable SQLite Queue Row + Datacenter File System** |
| **Control Primitives** | Code functions | Python Decorators | Message Routing | **17 Native `CTRL_` Deterministic Nodes (Zero-Token)** |
| **Gating Mechanics** | Edge functions | None | None | **Predicate `CTRL_GATE` + `SET_GATE` Neuromodulation** |
| **Scatter / Gather** | `Send()` Map-Reduce | Supervisor Implicit | Concurrent Agent | **`CTRL_SCATTER` / `CTRL_MERGE` with `tether_id` Scoping** |
| **Conditional Routing**| Code functions | Decorators | Message handlers | **Quadrivector Failback Chain (Structured → Keyword → Score → Fuzzy)** |
| **Time Travel** | Checkpointer abstraction | Limited SQLite | Manual replay | **Native `flow_vector` Lineage Replay + `copy2` DB Forking** |
| **Data Sovereignty** | External DB dependency | External DB dependency | Ephemeral | **100% Local (SQLite WAL, FTS5, sqlite-vec, Zero-Cloud)** |
