# DRAFT DOCUMENTATION CONTRIBUTIONS: TUI & COMMAND CENTER SUBSYSTEM
**Domain Specialist:** TUIAndInterface_Oracle  
**Target Files:** `B:\EXO_GANS\README.md` & `B:\EXO_GANS\MACCRE_Operator_Manual.md`  
**Output Destination:** `B:\EXO_GANS\Analysis\Wave3\draft_tui_interface_docs.md`  

---

## PART 1: SECTION CONTRIBUTION FOR `B:\EXO_GANS\README.md`

### Textual NexusPlex TUI & Command Center Architecture

EXO_GANS features an advanced, terminal-native Command Center built on top of Textual and Rich. Located in `maccre_tui/nexus_plex.py` and styled via `nexus_plex.css`, the **NexusPlex** user interface provides a split-pane layout for designing multi-agent DAG topologies, executing workflows with time-travel inspection, and staging real-time multi-agent discussions.

#### 1. Split-Pane Command Center Layout
- **Left Pane (Telemetry & Copilot):** `InformationPanel` (6 accordions), `FlowMonitorOverlay` (live execution metrics), `NexusChat` (`NexusAgent` copilot).
- **Right Pane (Workshop & Topology Arena):** `NodeCatalog` (tabbed browser), `TopologyVisualizer` (Rich Tree rendering), VCR Control Toolbar (`#btn-vcr`, `#btn-stop`, `#btn-step`).

#### 2. Interactive VCR Transport State Machine
The core execution pipeline operates as a deterministic 3-state transport machine (`Idle` -> `Running` -> `Paused`):
- **Idle State**: Topologies editable, history inspectable.
- **Running State**: Background execution on `FlowRunner` worker thread; pulsing active nodes.
- **Paused State**: Triggered by operator `⏸` button, `CTRL_PAUSE` node, or `CTRL_REVIEW` budget warning. Worker thread blocks on `FlowPauseEvent` lock, enabling interactive step selection, context injection, and live node chat.

---

## PART 2: SECTION CONTRIBUTION FOR `B:\EXO_GANS\MACCRE_Operator_Manual.md`

### 1. Step-by-Step TUI Navigation & Execution Guide
Launch via `omni run maccre_tui/nexus_plex.py` (or `omni run run.py`).

### 2. VCR Transport Control in Paused State (Step Injection & Live Node Chat)
When execution enters **PAUSED** state:
- **Radio-Dot Navigation**: Completed steps (green dot), active step (amber pulse), pending steps (hollow).
- **Context Injection (`ContextInjectModalScreen`)**: Select step, enter custom context payload, save to `_injected_context`, and unblock worker.
- **Node Live Chat (`NodeLiveChatModal`)**: Chat mid-flow directly with an agent node using its isolated memory state (`thoughts.db`).

### 3. Agent Studio & Session Bridge Compiler (`AgentStudioChatScreen`)
3-panel modal arena (`ChatDashboardPane`, `ChatArenaPane`, `ChatBuilderPane`). The **Session Bridge Compiler** converts live multi-agent Chat Studio transcripts directly into executable Flow Sequence DAG topologies.
