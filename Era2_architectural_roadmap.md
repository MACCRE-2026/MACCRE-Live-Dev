# MACCREv2 Era 2 Master Architectural Roadmap
*Consolidated and re-indexed based on the June 2026 Codebase Audit & Feature Requests.*

---

## Phase 1: Sovereign Time-Travel & Nexus Integration
*Objective: Solidify the queue-based unrolled DAG architecture by embracing its natural state machine advantages (SQLite file-state over in-memory state), and integrate Nexus for deep recursive debugging.*

### 1.1 FlowStasis (Pause, Save, & Resume)
- **State Serialization:** Instead of database forking, we adhere to the canonization method: every launch is an isolated session branch, and `memory_pins.db` serves as the final sovereign project state. Memory pins are extracted from the unified session ledger and vectorized.
- **FlowStasis Entries:** Implement the ability to pause and save a running state explicitly as a `FlowStasis` entry in the Session Manager, which can be safely loaded and resumed at a later time.

### 1.2 DeadFlow Registry & Nexus Copilot
- **Checkpoint-on-Failure:** Isolate failed queue states and save them directly to a `DeadFlow Registry`.
- **Recursive Fix Pathway:** The Nexus agent in the TUI will be equipped to evaluate and correct entries in the `DeadFlow Registry`, saving the repaired states back as `FlowStasis` entries that can be manually resumed from the Session Manager.
- **Live Topology Patching:** Update `topology_engine.py` to allow rewriting individual cells in `topology.csv` mid-execution, taking effect on the next node fetch.

---

## Phase 2: TUI Maturation & Session Management
*Objective: Standardize the TUI infrastructure and build out the interfaces for session management and node configuration.*

### 2.1 The Dead Letter UI & Session Manager
- **Session Manager:** Build a UI to review failed, paused, or cancelled sessions (FlowStasis/DeadFlow entries). Operators must be able to categorize them, rename them, manually resume them, or trigger a Canonization pipeline to the project memory database.

### 2.2 Standardized TUI Interactions
- **Unified Welcome Screen:** Force explicit Project and Session selection (or creation) upon TUI startup before granting access to the main dashboard.
- **Standardized Modal Catalog:** Refactor existing Modals to inherit from a unified `ModalCatalog` for cross-session consistency and reduced code duplication.
- **Interactive Node Configuration:** Allow operators to click a node on the active Flow Line to configure its specific payload options (e.g., toggling between receiving the full Unified Ledger vs. just the preceding Node's Ledger).

---

## Phase 3: Advanced Grounding & Tooling
*Objective: Enhance the ingestion pipeline with new document loaders and finalize complex search routing logic.*

### 3.1 Multi-Tier Grounding & Hybrid Exclusionary Search
- **Hybrid Search Logic:** Implement coordination between Google Search and Brave LLM indexing. If both are active, the system must perform Google searches first, synthesize findings, and then execute a Brave search explicitly excluding known information.
- **Tri-Grounding Prompt Injection:** When Local Memory, Google, and Brave are all active, dynamically inject the system prompt with strict instructions on how to weight project-local truth versus global internet facts.
- **Document Loaders:** Implement `pypdf` and `python-docx` loaders in `key_ingestor.py` to close the gap with competitor ingestion pipelines.

---

## Phase 4: Deterministic Orchestration (The Engine Refactor)
*Objective: Replace hardcoded routing logic in Python backend files with visual, first-class deterministic nodes, enabling users to build loops and branches visually.*

We will need to have a new DET_CHAT node. This node will be multi-function and use variants of the Agent Chat modal:
1. When added to a Flow Line it can be configured to: Chat w/ Preceding Agent, Chat with Next Agent, or Group Chat. 
1a. Chat w/ Preceding Agent starts the chat at either the beginning or the end of the preceding node. The user will select either Beginning or End during configuration.
1b. Chat with Next Agent starts the chat with the agent in the next node at either before they have read the payload from the preceding node or after the agent has read the payload from the preceding node. The user will select either Pre-Payload or Post-Payload.
1c. Group Chat starts a group chat where all agents that are forward of DET_CHAT are pre-selected in a paused group chat. The user should be able to de-select a pre-selected agent and add any agent to the chat that exists in \__DATACENTER\GLOBAL\agent_library.db and select whether or not to add that agent to the Flow Line or if the agent (one that is not pre-selected) is Ephemeral to the chat (an ephemeral agents chat responses will still be kept in the chat ledger, the agent just isnt added to the Flow Line). If an agent (that is not pre-selected) is to be added to the Flow Line then the remaining Flow Line should be displayed with clickable pointers that point to the spaces between the nodes on the Flow Line, the user can click the pointer that points to where the user wants the agent to be added in the remaining Flow sequence. 
2. The DET_CHAT node should also be able to be configured and injected by the user while a session has been paused in the TUI. 
3. In general, when a session is paused in the TUI the Flow Line should receive the same clickable pointers in the remaining portion of the Flow Line. If (while a session is paused) a user selects a MacroNode, Agent, or Special Node from the Flow Execution panel and presses their respective Add button then the user should be prompted visually (a small non-modal, non-interactive popup and flashing the pointers between the nodes on the Flow Line) to select a position on the Flow Line. If the user has not selected anything but clicks a pointer in between nodes then a similar small popup should inform the user to add a MacroNode, Agent, or Special Node, and after a user presses the respective Add button then the selected node should show up in the position that was first clicked.
4. While a session is paused (or before it is first launched) in the TUI, the Flow Line should have a little red "x" above each node so that it can be removed from the Flow Line.

### 4.1 Foundational Control Nodes
- **Branching & Aggregation:** Implement `DET_FAN_OUT` to dynamically spawn parallel sub-tasks and `DET_SYNTHESIZE` to await multiple prerequisite branches before merging payloads.
- **Filtering & Extraction:** Implement `DET_FILTER_IN` (regex conditional passing) and `DET_EXTRACT` (regex capture group isolation).
- **Edge Integration:** Implement `DET_WEBHOOK` for HTTP event triggers, and a Local Edge LLM Sync node pairing to offload tasks to edge devices (e.g., an S25 Ultra) via Google Drive polling.

### 4.2 Macros & Iteration Awareness
- **Flows as Macros:** Allow users to save an entire Flow Line (including nested DET logic) as a single reusable "MacroNode" in the registry.
- **Iteration-Aware Augments:** Enable the system to check `loop_iteration_count` and dynamically append `Iteration_Augments` to an agent's prompt to adjust its behavior during recursive cycles.

---

## Phase 4.75: TUI Refactor — Topology-First Architecture (Control Node Evolution)
*Objective: Rebuild the TUI around composable topology primitives (CTRL_ nodes), replacing the linear Flow Line paradigm with a visual DAG builder that supports fan-out, fan-in, tethered parallel branches, and deterministic conditional routing.*

*This phase emerged organically from the Phase 4 deterministic orchestration work. The introduction of Control Nodes as first-class composable primitives — alongside the realization that MacroNode topologies are compositions of these primitives — revealed that the TUI layout was structurally misaligned with the system's actual capabilities. Full breakdown in `TUI_REFACTOR_PLAN.md`.*

### 4.75.1 Foundation & Cleanup (TUI Refactor Phases 0–4)
- Created `controlnode_registry.db` + `ControlNodeStore` with seed builtins
- Removed Flow Registry, orphaned surfaces, DET_ → CTRL_ prefix rename
- Replaced MacroNodeBuilderPanel with collapsible InformationPanel panes
- Built MacroNode Workshop (NodeCatalog + TopologyVisualizer + flow controls)
- Integrated live execution highlighting, Flow Monitor overlay, session resume

### 4.75.2 Control Node Implementations
- 7 priority CTRL_ node handlers: MERGE, SCATTER, CONCAT, BRANCH, CONDITIONAL_ROUTE, FILTER, CLEANUP
- Node Tethering system (`tether_id`) linking SCATTER↔sink pairs with FlowLineID parentage tracking
- Dot-delimited nesting for arbitrarily deep nested scatter/gather topologies
- SCATTER, BRANCH can source tethers; MERGE, CONCAT, BRANCH, CONDITIONAL_ROUTE can sink tethers

### 4.75.3 Session Dictionary & Agent Overrides
- Extended Chat Studio `.dict` pattern to Flow sessions (JSON: `_flow_meta` + per-agent profiles)
- AgentProfileOverridesModal for session-specific agent configuration without modifying base profiles
- Tool Assignments checkmark UI for per-agent tool provisioning
- Dict written on Launch, loaded on Resume; override precedence: dict > topology CSV > agent_library.db

### 4.75.4 Dual-Pass Conditional Routing (Quadrivector Failback)
- Pass 1: Agent free-form response → Pass 2: Same agent at temp=0.1 with structured `response_schema`
- Failback chain: Structured Output → Keyword Gate → Score Threshold → Fuzzy ROUTE_TO
- Eliminates the ROUTE_TO tag reliability problem that plagued text-scraping conditional routing

### 4.75.5 Topology Visualizer & Workshop Completion
- Color-coded DAG visualization (cyan agents, magenta controls, blue tethers, yellow flow lines)
- Flow line branch rendering with Greek-letter tether pairing
- MacroNode inner topology expansion, double-click → NodeConfig
- Dual MacroNode save buttons (configured vs. template) with naming modal

### 4.75.6 Post-TUI Refactor CTRL_ Node Completion
- **Registry Hygiene:** Fix CTRL_CONDITIONAL_ROUTE status (`ComingSoon` → `active`), fix CTRL_REVIEW handler reference, formalize phantom nodes (CTRL_END, CTRL_PAYLOAD_INJECT) into registry with handlers
- **Configure Node Modal Completion:** Refactor compose/save into helpers; add ~20 new config fields across 13 node types achieving 16/16 node coverage. Key additions: CTRL_GATE predicate fields, CTRL_TRANSFORM template textarea, CTRL_RECURSION max/target, CTRL_PAUSE message, CTRL_PAYLOAD_INJECT content editor
- **Handler Upgrades:** Enhance `_handle_pause` (pause_message, auto_resume_after), `_handle_checkpoint` (checkpoint_label), and overhaul `_handle_gate` into a predicate-based "Floating If" with gate_id, initial_state, predicate evaluation, on_true/on_false actions, and inter-gate `SET_GATE` coordination via persisted gate state
- **Tethering Expansion:** Extend auto-tethering in MacroNode Workshop to support SCATTER↔CONCAT and SCATTER↔BRANCH pairing; add nested tether hierarchy tracking with `parent_tether` in FlowDictBuffer
- **`flow_line_id` Wiring:** Fix swarm_worker to handle `det_result.next_nodes` (plural) for scatter fan-out; propagate `flow_line_id` through `broker.route_task()`; assign dot-delimited flow_line_ids (`main.tether_a.0`) during scatter execution


### 4.75.7 CTRL_SCATTER Agent Slotting & Telemetry Vector Schema Groundwork
- **NodeConfigModal Agent Slotting UI:** `NexusPlex` `NodeConfigModal` supports up to `MAX_SCATTER = 8` agent slots per scatter node, dynamic active project roster querying with `GLOBAL` fallback, per-agent profile override modals (`AgentProfileOverridesModal`), and dynamic slot mounting/removal.
- **FlowEngine Auto-Wrap & DAG Synthesis:** `FlowEngine._get_macronode()` auto-wraps `CTRL_SCATTER` steps into entry, slotted parallel agent, and fan-in `CTRL_MERGE` DAG nodes (`Wait_For: "|".join(scatter_agents)`). Auto-wraps generic `CTRL_` nodes into single-node topologies and bypasses preflight checks for control primitives.
- **Topology Visualizer Enhancements:** Inner MacroNode topologies default to expanded display (`_expand_states.get(node_id, True)`), featuring `Ctrl+E` collapse toggles and condensed summary line formatting (`[+] MacroNode ⟩ N nodes ⟩ NextNode`).
- **Telemetry Vector Lineage & Tether Isolation:** `local_broker.py` `task_queue` and `telemetry_db.py` `system_logs.db` upgraded with `flow_vector` and `tether_id` schema columns. `SwarmWorker` builds lineage vector strings using `>` delimiter (`ROOT>SCATTER_0>Worker_A>MERGE_0`) and isolates gather payloads by `tether_id`.
- **RAG Client Thread Safety:** `rag_tools.py` instantiated `_rag_lock = threading.Lock()` around `_get_rag_client()`, guaranteeing thread-safe lazy embedding client initialization during parallel subagent scatter bursts.

---

## Phase 4.99: User Testing Action List (Mathematically Comprehensive Feature Test)
*Objective: Execute a mathematically comprehensive, 5-Oracle-aligned feature test suite before proceeding into Phase 5. Map-Reduce 38 domain test scenarios into single multi-scope TUI actions and siloed edge validations.*

### 4.99.1 Map-Reduce Domain Overlap Matrix

```
┌─────────────────────────────────────────────────────────────────────────────────────────────┐
│                           PHASE 4.99 MAP-REDUCE OVERLAP MATRIX                              │
├─────────────────────────────────────┬───────────────────┬───────────────────────────────────┤
│ Tier / Overlap Level                │ Scope Coverage    │ Test Action Focus                 │
├─────────────────────────────────────┼───────────────────┼───────────────────────────────────┤
│ Tier 1: 5-Scope Omni-Actions        │ ALL 5 ORACLES     │ • 8-Agent Scatter Burst & Lineage │
│ (Hits all domains simultaneously)   │ (TUI+Eng+Tools+   │ • Quadrivector Routing & Live HITL│
│                                     │  Net+State)       │   Context Injection               │
├─────────────────────────────────────┼───────────────────┼───────────────────────────────────┤
│ Tier 2: 4-Scope High-Overlap        │ 4 ORACLES         │ • Session Canonization & Bridge   │
│                                     │ (TUI+Tools+State+ │ • Excel Intake Swarm Materializer │
│                                     │  Net)             │                                   │
├─────────────────────────────────────┼───────────────────┼───────────────────────────────────┤
│ Tier 3: 3-Scope / 2-Scope Mid       │ 3 or 2 ORACLES    │ • Dual-Pipeline Media Isolation   │
│                                     │ (Tools+State+Net /│ • FastMCP Stdio & Micro-Tests     │
│                                     │  Eng+State)       │ • Recursive Loop & Crash Reclaim  │
├─────────────────────────────────────┼───────────────────┼───────────────────────────────────┤
│ Tier 4: Single-Scope Targeted Edge   │ 1 ORACLE          │ • Modal Re-entrancy & Terminal Res│
│                                     │ (Targeted Domain) │ • 7-Point Preflight Anomaly Test  │
│                                     │                   │ • WebSocket Drop & Modality Lock  │
│                                     │                   │ • 3-Tier Security PIN Elevation   │
└─────────────────────────────────────┴───────────────────┴───────────────────────────────────┘
```

---

### 4.99.2 Siloed Overlap Categorization

#### Tier 1: 5-Scope Omni-Actions (Simultaneously Stressing All 5 Oracle Subsystems)
- **Omni-Action 1: High-Concurrency 8-Agent Scatter Burst & Lineage Audit**
  - *TUI*: `NodeConfigModal` 8-slot allocation, active roster dropdowns, per-agent `AgentProfileOverridesModal`, `Ctrl+E` tree collapse toggle, VCR transport status monitoring.
  - *Engine*: `CTRL_SCATTER` auto-wrap DAG synthesis, `tether_id` isolation, 8 parallel worker claims, `CTRL_MERGE` fan-in wait.
  - *Tools & RAG*: Restricted tool profiles (`Tools_Allowed`), hybrid search, `_rag_lock` thread-safety, RAG context lineage filtering.
  - *Net & Client*: Zero-SDK `urllib` paid-tier REST burst (~1,000+ RPM), `ModelSentinel` latency tracking, `ctypes.memset` RAM key zeroing under parallel workers.
  - *State & Sovereignty*: 5-tier datacenter output (`03_Agent_Ledgers`), SQLite WAL concurrency (`task_queue`, `system_logs.db`), composite tether indexing, `flow_vector` lineage logging (`>`).

- **Omni-Action 2: Quadrivector Failback Routing with Edge Hardware Failover & Live Context Injection**
  - *TUI*: VCR Pause state transition, Live Node Chat input pane context injection, radio-dot execution status updating.
  - *Engine*: `CTRL_CONDITIONAL_ROUTE` Quadrivector failback (Structured → Keyword → Score → Fuzzy), predicate gate evaluation.
  - *Net & Client*: Hardware probing (`environment_probe.py`), local Ollama port 11434 detection/fallback, ModelSentinel health recalculation.
  - *Tools & RAG*: Dynamic context update, restricted tool execution, RAG hybrid search failback.
  - *State & Sovereignty*: 4-silo telemetry matrix logging (`user_interactions.db`, `system_logs.db`), DPAPI vault key retrieval & RAM wiping.

#### Tier 2: 4-Scope High-Overlap Actions (TUI + Tools + State + Net)
- **4-Scope Action 1: Session Canonization, Semantic Memory Pruning & Bridge Compilation**
  - Promote L1 ephemeral scratchpad thoughts to L2 project canon (`agent_thoughts.db`), deduplicate vectors (>0.92 cosine similarity) while preserving FlowStasis pins, compile markdown canon via `SessionBridgeCompiler`, and hot-reload session trees in `SessionManagerModal`.
- **4-Scope Action 2: Excel Intake Swarm Materialization & Workspace Seeding**
  - Intake malformed `MACCRE_Swarm_Request.xlsx`, run `check_workbook_completeness`, fallback to vendored openpyxl (`maccre_core._vendor`), and instantiate 5-tier datacenter folders anchored strictly via `get_maccre_root()`.

#### Tier 3: 3-Scope & 2-Scope Mid-Overlap Actions
- **3-Scope Action 1 (Tools + State + Net): Dual-Pipeline Media Render Stem Isolation & FFmpeg Failback**
  - Execute parallel TTS/Imagen 3 render requests with identical output names, verifying isolated stems (`05_Rendered_Media/<job_id>_<node_id>_<timestamp>/`) and audio fallback reports when FFmpeg is missing.
- **3-Scope Action 2 (Tools + State + Net): FastMCP Stdio Protocol Hygiene & Micro-Test Automation**
  - Run `omni run scripts/maccre_micro_test.py` across all 61 atomic tools, enforcing sub-30s timeouts and stdout isolation over FastMCP JSON-RPC stdio streams.
- **2-Scope Action 1 (Engine + State): Recursive Loop Boundary & Max Iteration Guardrail**
  - Execute cyclic workflow (`Node_A` -> `Node_B` -> `CTRL_RECURSION` -> `Node_A`), verifying `max_recursion` boundary interception, fallback routing, and iteration breadcrumbs.
- **2-Scope Action 2 (Engine + State): Worker Process Crash Recovery & Zombie Lock Reclaim**
  - Abruptly kill worker process during `PROCESSING` state; verify `local_broker` lock monitor reclaims zombie task after 15s timeout, resets to `PENDING`, and increments retry count.

#### Tier 4: Single-Scope Targeted Edge Actions
- **TUI Edge**: Test modal double-click re-entrancy prevention (`push_screen` guard) and 21-modal cascade navigation under terminal window resizing.
- **Engine Edge**: Run 7-point preflight topology validation (`topology_engine.py`) against synthetic multi-fault DAG sheets (orphans, cycles, missing anchors).
- **Net Edge**: Trigger Gemini Live WebSocket TCP socket drops, validating text-only modality lockdown (`[types.Modality.TEXT]`) and credential zeroing in `finally` blocks.
- **State Edge**: Test 3-tier access control PIN elevation (`access_control.py`) and non-destructive file deletion via `trash_file()` archive protocol.

---

### 4.99.3 Sequential TUI Operator Execution Plan

Below is the linear, step-by-step sequence of TUI operator commands and GUI interactions that fully satisfies all 38 test actions from all 5 Oracles in a single comprehensive testing run:

1. **Environment Initialization & Gatekeeper Check:**
   ```bash
   omni clean .
   omni qa .
   omni run maccre_tui/app.py
   ```
2. **Workspace Seeding & Workbook Intake (Tier 2 Action 2):**
   - In `NexusPlex`, press `Ctrl+P` (Project Canon Modal) or `Ctrl+S` (Session Manager).
   - Ingest `MACCRE_Swarm_Request.xlsx`. Verify readiness score report and 5-tier datacenter folder generation under `get_maccre_root()`.
3. **Topology Design & 8-Agent Scatter Slotting (Tier 1 Omni-Action 1 & TUI Edge):**
   - Click `MacroNode Workshop` and load `CTRL_SCATTER`.
   - Press `F2` or double-click to open `NodeConfigModal`. Rapidly double-click to verify modal re-entrancy protection.
   - Slot 8 agents from the active project roster dropdown. Verify the 9th attempt is blocked (`Scatter Agent Slots (8/8)` disabled).
   - Click `⚙ Overrides` on Slot #2 to launch `AgentProfileOverridesModal`. Set Model to `gemini-2.5-pro`, temp to `0.2`, set custom instructions, and save.
   - Click `Save` on `NodeConfigModal`. Verify synthesized DAG (`CTRL_SCATTER` → 8 Agents → `CTRL_MERGE`) mounts in `TopologyVisualizer`.
4. **Tree Visualizer Density & Expansion Test (Tier 1 Omni-Action 1 & TUI Edge):**
   - Press `Ctrl+E` in `NexusPlex` to toggle tree collapse. Verify condensed summary line formatting (`[+] MacroNode ⟩ 8 nodes ⟩ CTRL_MERGE`). Press `Ctrl+E` again to expand.
5. **Execution Launch & VCR Transport Mid-Scatter Intercept (Tier 1 Omni-Action 1 & Omni-Action 2):**
   - Click `#btn-vcr-play` (or press VCR Play shortcut) to start flow execution.
   - While the 8 scatter workers run concurrently, click `#btn-vcr-pause`.
   - Observe worker threads yield state cleanly to `[PAUSED]`.
   - In the right-hand **Live Node Chat** input pane, type a custom context string: `Injecting dynamic priority context for scatter branch` and press `Send`.
   - Click `#btn-vcr-step` to step a single sub-task node, then click `#btn-vcr-play` to resume.
6. **Concurrency, Grounding & Security Verification (Tier 1 Omni-Action 1 & 3-Scope Action 1):**
   - Monitor `ModelSentinel` latency & throughput logs during the 8-agent paid-tier REST burst.
   - Verify `_rag_lock` thread-safety during concurrent RAG queries and check that decrypted API keys are wiped via `ctypes.memset`.
   - Check `03_Agent_Ledgers` to confirm `flow_vector` lineage breadcrumbs use the `>` delimiter (`ROOT>SCATTER_0>Worker_A>MERGE_0`) and gather payloads are isolated by `tether_id`.
7. **Quadrivector Failback & Local Edge Hardware Probing (Tier 1 Omni-Action 2 & Net Edge):**
   - Inject an un-structured payload into `CTRL_CONDITIONAL_ROUTE`.
   - Verify failback cascade: Pass 1 JSON Schema → Pass 2 Keyword Search → Pass 3 Score Threshold → Pass 4 Catch-All.
   - Simulate an Ollama service network drop on port 11434. Verify `environment_probe.py` sets `ollama_active = False` without throwing unhandled exceptions.
8. **Recursive Loop & Crash Recovery Stress (Tier 3 / 2-Scope Actions):**
   - Trigger a `CTRL_RECURSION` loop with `max_recursion=5`. Verify loop boundary log interception at iteration 5.
   - In a terminal, send `SIGKILL` to a running worker process. Wait 15 seconds; verify `local_broker` lock monitor reclaims the zombie task and resets status to `PENDING`.
9. **Session Canonization & Teardown (Tier 2 Action 1 & FastMCP):**
   - Press `Ctrl+S` (Session Manager Modal). Rename session to `Phase 4.99 Full System Test`.
   - Click `Compile & Canonize`. Verify L1 scratchpad thoughts are promoted to L2 `agent_thoughts.db` and semantically deduplicated (>0.92 cosine similarity) while FlowStasis pins are preserved.
   - Exit `NexusPlex`. Run FastMCP automated micro-tests:
     ```bash
     omni run scripts/maccre_micro_test.py
     ```
   - Verify all 61 atomic tools pass JSON-RPC stdio protocol tests cleanly within 30 seconds.

---

## Phase 5: Multimodal Ingestion & High-Cost Authorizations (The Horizon Goal)

*Objective: Execute the Alphabet Oracle's design for semantic visual ingestion, temporal extrapolation, and introduce FinOps gates for generative heavies.*

### 5.1 The Visionary Scout
- **Visual Extraction:** Implement an agent role dedicated to processing images (e.g., comic panels) during File Cabinet ingestion, extracting spatial bounding boxes, dialogue tags, and synthetic descriptions.
- **Triune Memory Linking:** Store the synthetic metadata in the sovereign SQLite database for fast RAG, but retain a hard URI pointer to the raw media in the `01_Raw_Source` tier.

### 5.2 The FinOps Onion & High-Cost Authorizations
- **TUI Authorization Modal:** When a high-cost execution (e.g., media rendering or temporal extrapolation) emits a `ManualInputRequired` pause, display a FinOps modal showing estimated USD burn, forcing explicit user Approval or Adjustment before proceeding.

### 5.3 Generative Temporal Extrapolation
- **Image-to-Video Animation:** Leverage Image-to-Video generative pipelines using the extracted context as a temporal prompt to predict and animate the 2 seconds leading up to a static panel and the 2 seconds following it, creating a generative "live photo" effect.

---

## Phase 6: TUI Polish, Overlays, & Advanced Topology UX
*Objective: Complete the Phase 4.75 stretch goals — convert key modals to overlays, add drag-and-drop topology editing, implement remaining CTRL_ node primitives, and build advanced topology UX features.*

### 6.1 NodeConfig Overlay Conversion
- Convert `NodeConfigModal` from modal screen to `NodeConfigOverlay(Vertical)` widget that covers the AgentBuilder area while leaving MacroNodeWorkshop visible
- Significant CSS/layout refactoring of `NexusPlex.compose()` right-pane structure

### 6.2 Topology Visualizer — Drag-and-Drop
- Replace keyboard shortcuts (Ctrl+↑↓←→) with true drag-and-drop node repositioning
- Custom canvas widget or Textual Tree extension for native drag support

### 6.3 Remaining CTRL_ Node Primitives
- `CTRL_WEBHOOK` — HTTP event trigger for external system integration
- `CTRL_EDGE_SYNC` — Local Edge LLM pairing for offloading to edge devices via Google Drive polling
- `CTRL_CHAT` — Interactive HITL chat node with variants: Chat w/ Preceding Agent, Chat w/ Next Agent, Group Chat with ephemeral agent support, injectable while paused
- Complete all remaining stubs in `controlnode_registry.db`

### 6.4 Template System Modernization
- Refactor template builders (cascade, hologram, chord, crucible) to use CTRL_ node compositions
- Template skeleton preview in Topology Visualizer when browsing catalog
- Guided template mode with fillable skeleton slots

### 6.5 Nexus Copilot Sandbox
- Nexus topology-aware debugging and modification suggestions
- DeadFlow analysis with auto-repair proposals

### 6.6 Advanced Topology UX
- Paused-session live injection (clickable pointers between nodes)
- Red "✕" node removal while paused or pre-launch
- Topology diff view and versioning (undo/redo)

### 6.7 CTRL_GATE Advanced Predicates (Deferred from Phase 4.75.6)
- **Multi-predicate arrays:** Support `predicates[]` array on CTRL_GATE with `predicate_logic: all|any` combinator. Requires dynamic list widget in NodeConfigModal for add/remove predicate rows.
- **Advanced predicate types:**
  - `flow_state` — evaluate overall flow execution state (e.g., check if a specific upstream node has completed)
  - `counter_threshold` — compare an internal counter against a configurable threshold
  - `expression` — evaluate arbitrary Python expressions against flow context variables
- **`SCATTER_TO` gate action:** When a gate evaluates to true, scatter the payload to multiple downstream targets (combines gate logic with SCATTER fan-out in a single node)

### 6.8 Flow Stage Editor (Deferred from Phase 4.75.7)
- **Flow Stage model:** Topology represented as ordered list of horizontal stages. Nodes on the same stage execute in parallel; the flow waits for all to complete before advancing to the next stage.
- **Stage operations:** Select a stage → add/remove nodes (up to `MAX_SCATTER_AGENTS` per stage). Visual reordering on add.
- **Node swap/replace:** Select a node → add another node to swap into its position.
- **Wiring:** Adding nodes downstream auto-configures `Wait_For` and `Next_Node` connections between stages.

### 6.9 Animated Flow Wires (Deferred from Phase 4.75.7)
- **Wire types:** Dashed lines for inactive flow, solid for active, color-coded by flow type (scatter=orange, normal=cyan, gate=yellow, review=red)
- **Marching-ants animation:** 4-segment dashed pattern that progresses along the wire path like a progress bar. Wires that bend and snake to their destination.
- **Implementation:** Custom Rich `Renderable` or `Strip`-based rendering for Unicode box-drawing wire characters with state-driven styling.

### 6.10 Center-Justified Flow Tree (Deferred from Phase 4.75.7)
- Replace the current vertical `Tree` widget (left-aligned, indented) with a center-justified DAG layout.
- Custom widget (not Textual Tree) — a `Static` or Canvas-style widget rendering Rich Text blocks with calculated horizontal positions.
- Center-justification based on the widest stage. Responsive to pane width changes.
- Scatter fan-out visually splays from parent → children → merge convergence.

### 6.11 Node Swap & Removal UX (Deferred from Phase 4.75.7)
- Select a node in the topology → highlight it with a selection border
- Add another node → swap into the selected node's position
- Red "✕" removal button on selected nodes (both pre-launch and while paused)
- Topology version stack for undo/redo

### 6.12 Parallel Execution Threading (Deferred from Phase 4.75.7)
- **ThreadPoolExecutor** in `swarm_worker.py` with `max_workers=MAX_SCATTER_AGENTS` (default 8, configurable, hard cap 12)
- Each scatter target runs in its own thread for true parallel API calls
- SQLite WAL mode handles concurrent reads; writes serialize via WAL journal — mitigated by §6.13 WAL sharding
- Merge node polls completion via existing `Wait_For` check
- Rate limit guard: respect Gemini 3.x paid-tier RPM limits (~1000-2000 RPM) across all concurrent threads

### 6.13 WAL Sharding by Flow Line (Deferred from Phase 4.75.7)
- Scale SQLite write throughput by sharding `task_queue` and telemetry tables across per-flow-line database files
- Each shard is its own WAL-mode SQLite file — eliminating write contention between parallel flow lines
- Broker routes reads/writes by `flow_line_id` → shard DB path
- `shard_manifest` table in main DB tracks active shards and their flow_line_id mapping
- Shards merge back into main DB on flow completion (or remain isolated for branch analysis)
- `flow_vector` column (planted in Phase 4.75.7) serves as the partition key for shard assignment
- Telemetry scaling metadata tracks per-shard write ops, task counts, and merge status

---

## Phase 7: Telemetric Memory Simulation
*Objective: Leverage the `flow_vector` telemetry schema and session ledger artifacts to enable time-travel replay, agent perspective tracing, and counterfactual simulation through completed sessions.*

### 7.1 Time-Travel Replay
- **Branch isolation:** Filter `flow_vector` by prefix to extract a single scatter branch's complete execution history
- **Timeline reconstruction:** Order by `created_at` timestamps to replay the exact sequence of events across any branch
- **State snapshots:** Each task row captures `payload_path` at entry and exit — providing payload state at every node boundary
- **TUI integration:** Scrubber/timeline widget to step through a completed session node-by-node

### 7.2 Agent Perspective Simulation
- **Agent trace:** Filter `flow_vector` entries containing a specific agent name → reconstruct every node that agent touched, in chronological order
- **Cross-branch correlation:** If the same agent appears in multiple scatter branches, correlate its inputs/outputs across branches to study behavioral consistency
- **"Fly on the wall" mode:** Feed an observer agent the complete telemetry trace of a target agent's journey — the observer absorbs the decision context, payload evolution, and outcome without having been present. A telemetric memory that can be injected as grounding context into any future agent.

### 7.3 Counterfactual Simulation
- **Path replay:** Send a **different** agent through a completed agent's exact routing path
- Replay the exact same payload sequence and node routing that Agent_A experienced, but route it through Agent_B (different model, different system prompt, different tools)
- Compare outputs at each node to study how different agent configurations would have handled the same flow
- Uses `flow_vector` to reconstruct exact routing and ledger artifacts to replay exact payloads
- **Diff view:** Side-by-side comparison of original agent output vs. counterfactual agent output at each node
