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
