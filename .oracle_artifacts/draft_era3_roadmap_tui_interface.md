# ERA 3 ARCHITECTURAL ROADMAP: TUI, SUBSYSTEMS & COMMAND CENTER
**Domain Contribution:** TUI & Interface Specialist Oracle  
**Target Module:** `maccre_tui/` (`nexus_plex.py`, `nexus_plex.css`, `widgets/*`, modals stack)  
**Compliance Standard:** Sovereign Engineering Doctrine Rev 19.0 (Omni-Compliant JIT, 5-Tier Data Sovereignty, Zero-Zombie Teardown)

---

## EXECUTIVE SUMMARY & DOMAIN VISION

The `maccre_tui` subsystem forms the primary edge command-and-control surface for MACCREv2 / EXO_GANS. Built upon Textual (v2 App framework) and Rich, it provides a topology-first, state-driven interface for multi-agent swarm orchestration, deterministic Control Node (`CTRL_`) wiring, FinOps token governance, dynamic RAG ingestion, and live execution telemetry.

This document synthesizes current implemented achievements, categorizes deferred Phase 6/7 roadmap features, and defines the proposed Era 3 architectural goals for the Sovereign Edge Command Center.

---

## SECTION 1: IMPLEMENTED TUI & INTERFACE FEATURES (ERA 1 / ERA 2 BEDROCK)

The current production TUI reflects a comprehensive refactor into a **Topology-First Architecture**, abandoning static linear sequences in favor of composable directed acyclic graph (DAG) topologies.

### 1.1 NexusPlex Split-Pane Command Center Layout
- **Root Layout (`nexus_plex.py` & `nexus_plex.css`)**: Standardized split-pane layout grid anchored by `CustomHeader` and `Footer`.
- **Left Pane (`#left-pane`)**:
  - `InformationPanel`: Houses 6 collapsible, context-sensitive guidance panes (Overview, Flow Controls, MacroNode Builder, FinOps & Budget, Knowledge Ingestion, System Telemetry).
  - `FlowMonitorOverlay`: Live execution dashboard overlaying information panes during active flow runs with animated stage readouts and step-by-step progress tracking.
  - `NexusChat`: Real-time copilot chat interface with topology awareness, command dispatch, and interactive context injection.
- **Right Pane (`#right-pane`)**:
  - `AgentBuilderPanel` / `MacroNodeBuilderPanel`: Embedded configuration controls for agent profile crafting and in-place MacroNode design.
  - `MacroNodeWorkshop`: Core orchestration workshop housing the `NodeCatalog`, `TopologyVisualizer`, and VCR transport toolbar.

### 1.2 Interactive VCR Transport State Machine
- **State Architecture**: Tri-state machine (`Idle`, `Running`, `Paused` / `FlowStasis`).
- **Idle State**: Topology is fully editable; VCR pause button disabled; Flow Monitor hidden.
- **Running State**: Topology nodes pulse with live execution state; Flow Monitor active; background `FlowRunner` worker executing step queue.
- **Paused State (FlowStasis)**: Execution thread blocked cleanly via `threading.Event`; flow line becomes interactive with step selection indicators.
- **Paused-Mode Operations Stack**:
  1. *Node Inspection & Output Review*: Inspect exact intermediate payloads and agent scratchpads.
  2. *Step Context Injection*: Open `ContextInjectModalScreen` to append mid-flow instructions into `_injected_context`.
  3. *Live Node Chat*: Launch `NodeLiveChatModal` to initiate direct, real-time dialogue with a specific paused step node state.
  4. *Time-Travel Branching*: Select completed step radio-dots on the topology view to set branch targets and re-execute prior steps.

### 1.3 Agent Studio 3-Panel Arena (`AgentStudioChatScreen`)
- **Panel 1 (`ChatDashboardPane`)**: Project selector dropdown, session history selection list, multi-agent roster checkboxes, and session creation controls.
- **Panel 2 (`ChatArenaPane`)**: Main chat stream (`RichLog`), typing indicator label, multi-line `TextArea` input, send/paste controls, and `Notebook` selection list for KnowledgeStore grounding.
- **Panel 3 (`ChatBuilderPane`)**: Agent profile & dictionary selector, system instructions override textarea, LLM model selector (`gemini-3.1-pro-preview`, `gemini-3.5-flash`, etc.), FinOps parameters (temperature, thinking level, search toggles), and Session Bridge Compiler.
- **Session Bridge Compiler**: Compiles multi-agent conversation threads directly into executable flow sequences in `.dict` / topology formats.

### 1.4 Rich Tree `TopologyVisualizer` Widget
- **State-Driven Rendering (`topology_visualizer.py`)**: Built on Rich `Tree`, visualizing DAG topologies with color-coded nodes:
  - *Cyan*: Agent nodes
  - *Magenta*: Control nodes (`CTRL_`)
  - *Blue*: Tether pairings (`[tether:id]`)
  - *Yellow*: Flow line branch identifiers
- **Pulse Animation Engine**: 0.2s interval timer (`_tick_animation()`) cycling active node symbols (`● -> ◉ -> ○ -> ◉`) with amber highlight during execution.
- **Default Expanded Hierarchy**: Tree defaults to fully expanded view; collapsible via `[-]` toggle. Collapsed state renders a single-line summary (`[+] CTRL_SCATTER ⟩ N agents ⟩ CTRL_MERGE`).
- **Interactive Event Intercept**: Double-click or `F2` opens `NodeConfigModal`; `Ctrl+Up`/`Ctrl+Down` reorders nodes in memory.

### 1.5 The 21 Modal Dialog Screens Catalog
The application houses 21 specialized modal screens providing human-in-the-loop (HITL) decision gates and management tools:
1. `BootSplashModal`: Project startup and initialization selector.
2. `LoadingSplashModal`: Threaded background loading and asset verification screen.
3. `NewProjectModal`: Project creation wizard enforcing 5-tier datacenter structure.
4. `SelectProjectModal`: Workspace project switcher scanning physical directories.
5. `SystemInstructionsModal`: Global system prompt override screen.
6. `AgentStudioChatScreen`: 3-panel multi-agent chat arena and compiler.
7. `MacroNodeEditorModal`: Fullscreen modal for editing MacroNode templates.
8. `SessionManagerModal`: History dashboard for FlowStasis, Completed, and DeadFlow entries.
9. `MacroNodeNameModal`: Naming modal for dual MacroNode saving (configured vs. template).
10. `ProjectCanonModal`: Knowledge graph pin manager and memory canonization.
11. `FileCabinetModalScreen`: 5-tier document and media ingestion workspace.
12. `OnionBookModal`: FinOps financial ledger and budget health tracking.
13. `BudgetProposalModal`: HITL financial approval modal for high-cost tasks.
14. `BudgetWarningModal`: Token burn warning and threshold notification modal.
15. `ContextInjectModalScreen`: Paused mid-flow context injection editor.
16. `NodeLiveChatModal`: Paused step interactive node chat modal.
17. `FlowHistoryModalScreen`: Duplicate-run guard and session execution history.
18. `NodeConfigModal`: Interactive node configuration modal with helper-based field rendering (`_compose_ctrl_fields` / `_collect_ctrl_config`) providing 16/16 `CTRL_` node coverage (including `CTRL_SCATTER` agent slotting UI, `CTRL_GATE` predicate builder, `CTRL_TRANSFORM` template editor, `CTRL_CONDITIONAL_ROUTE` vector selector, etc.).
19. `AgentProfileOverridesModal`: Session-specific agent parameter and tool override dialog.
20. `FlowRegistryModalScreen`: Legacy flow recipe browser (deprecated/superseded by MacroNode Store).
21. `AgentChatInputModalScreen`: Single-agent quick chat input modal.

---

## SECTION 2: UNFINISHED & FUTURE TUI ROADMAP ITEMS (PHASE 6 & PHASE 7 DEFERRALS)

Derived from the 12 roadmap documents, the following features remain planned for completion across future work packages:

### 2.1 Visual Graph Drag-and-Drop Wiring Canvas
- **Visual Canvas Replacement**: Replace keyboard shortcut node moving (`Ctrl+Up/Down`) with interactive mouse drag-and-drop node reordering and graph wiring.
- **Custom Canvas Widget**: Implement a custom canvas renderable handling mouse drag coordinates, node selection highlights, and dynamic snapping.

### 2.2 Real-Time Multi-Agent Audio Chat Overlay
- **Voice Stream Integration**: Integrate Gemini Multimodal Live WebSocket audio stream into the Agent Studio Chat Arena (`ChatArenaPane`).
- **Interactive Audio Visualizer**: Render real-time waveform meters and voice activity overlays for human-agent spoken dialogue.

### 2.3 Advanced Telemetry & FinOps Visual Charts
- **In-Memory Telemetry Buffer**: Off-thread polling of `system_logs.db`, `thoughts.db`, and `onionbook_modal.py` state.
- **Sparkline & Bar Chart Widgets**: Native Rich/Textual sparkline rendering of token burn rates, latency per node, API cost distributions, and hardware VRAM/CPU probing metrics.

### 2.4 Mobile TUI Remote Bridge & WebSockets C2 Console
- **Remote C2 Architecture**: Evolve `maccre_tui/app.py` (`LiveSwarmTUI`) into a secure WebSocket client/server remote bridge.
- **Mobile-Responsive TUI**: Enable light web/terminal monitoring and HITL pause approvals from mobile devices over WSS.

### 2.5 NodeConfig Overlay Conversion
- **Inline Overlay Architecture**: Convert `NodeConfigModal` from a screen overlay into an inline `NodeConfigOverlay(Vertical)` widget.
- **Layout Persistence**: Position overlay directly over `AgentBuilderPanel` while keeping `MacroNodeWorkshop` and `TopologyVisualizer` visible and interactive.

### 2.6 Animated Flow Wires & Center-Justified Flow Tree
- **Marching-Ants Wire Animation**: Render dashed Unicode box-drawing connectors (`─── → ────`) that animate along active flow lines (0.2s tick). Color-code by type (cyan=normal, orange=scatter, yellow=gate, red=review).
- **Center-Justified Tree Layout**: Replace left-aligned tree indentation with a center-justified DAG layout visually displaying fan-out splays cleanly across horizontal pane width.

### 2.7 Flow Stage Editor & Node Swap/Replace UX
- **Stage Model**: Organize DAG into horizontal execution stages where all stage nodes execute in parallel up to `MAX_SCATTER_AGENTS = 8`.
- **Node Swap Mechanics**: Highlight node → select replacement from catalog to swap in place.
- **Instant Node Removal**: Red "✕" icon on topology nodes for instant removal during pause or pre-launch.

### 2.8 Nexus Copilot Sovereign Sandbox Integration
- **Local `.venv` Sandbox Provisioning**: Provision Nexus Copilot with safe code execution capabilities using the local virtual environment without external dependencies.
- **Automated Topology Validation & DeadFlow Repair**: Sandbox-based validation of MacroNode skeletons (`build_from_template()`) and automatic fix proposals for failed queue states in `DeadFlow Registry`.

### 2.9 Generative Recruitment Engine & Prompt Engineer UI
- **Passive Context Monitor**: Passive UI widget tracking total session context window growth.
- **Recruitment Roster**: Display dynamically generated specialized agents crafted by the Prompt Engineer, allowing one-click promotion to the Global `agent_library.db`.

---

## SECTION 3: PROPOSED ERA 3 TUI & INTERFACE ARCHITECTURAL GOALS

Looking ahead to Era 3, the TUI infrastructure will evolve to meet extreme edge performance and deep cognitive inspection requirements.

### 3.1 Event-Driven Asynchronous State Container & Off-Thread Rendering
- **Problem**: Large session ledgers and complex SQLite queries can cause frame stutter on Textual's main event loop during rapid UI updates.
- **Era 3 Solution**: Implement an in-memory event-driven **State Container** updated asynchronously by Textual Workers (`@work(thread=True)`). The UI renders exclusively from the instantaneous in-memory buffer, achieving smooth 60 FPS terminal interaction regardless of database size.

### 3.2 Dynamic Neural Topology & Spatial Redstone Canvas
- **Biological Circuit Motifs**: Transition `TopologyVisualizer` into a spatial neural circuit representation mapping directly to biological motifs:
  - *Divergent Projections* (`CTRL_SCATTER`)
  - *Spatial/Temporal Convergent Summation* (`CTRL_MERGE` / `CTRL_CONCAT`)
  - *Synaptic Gating & Neuromodulation* (`CTRL_GATE` with `SET_GATE` domino coordination)
  - *Lateral Inhibition / Winner-Take-All* (`CTRL_BRANCH` & `CTRL_CONDITIONAL_ROUTE`)
- **Ganglia Handles**: Visual representation of MacroNodes as autonomous Ganglia with entry (afferent) and exit (efferent) nerve handles for modular drag-and-drop composition.

### 3.3 Sovereign Time-Travel Replay & Counterfactual Visual Scrubbing
- **`flow_vector` Scrubber**: Integrate a scrubbable timeline bar leveraging the `flow_vector` lineage schema (`CTRL_SCATTER_S0:Agent_A_S0`) to step backward/forward through completed session histories.
- **Counterfactual Diff Viewer**: Visual side-by-side comparison pane displaying original agent execution outputs vs. counterfactual model outputs for identical input payloads.

### 3.4 Unified Sovereign Workspace & Multi-Tenant Datacenter Switcher
- **Live Datacenter Inspector**: Real-time filesystem scanner enforcing the 5-tier Data Sovereignty structure (`01_Raw_Source` through `05_Rendered_Media`).
- **Zero-Zombie Session Switching**: Instant switching between project datacenters with automatic background worker cleanup and zero orphaned database locks.
