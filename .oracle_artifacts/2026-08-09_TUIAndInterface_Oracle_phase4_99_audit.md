# COMPREHENSIVE PHASE 4.99 SUBSYSTEM AUDIT: TUI & INTERFACE ORACLE

**Specialist Oracle:** `TUIAndInterface_Oracle`  
**Target Domain:** `maccre_tui/` (`nexus_plex.py`, `nexus_plex.css`, `app.py`, `macro_editor_modal.py`, `widgets/*`)  
**Audit Timestamp:** 2026-08-09T16:25:00-04:00  
**Compliance Standard:** Sovereign Edge Omni-Builder Doctrine (Rev 19.0)  
**Roadmap Reference:** `B:\EXO_GANS\Era2_architectural_roadmap.md` & `B:\EXO_GANS\Era3_architectural_roadmap.md`  

---

## 1. EXECUTIVE SUMMARY

The **TUI & Interface Oracle** has executed a granular, line-by-line architectural and functional audit of the entire Textual NexusPlex command center and graphical edge layer (`maccre_tui/`). This audit specifically evaluated system readiness for **Phase 4.99** (the Immediate Production Boundary & User Testing Phase) as established in Era 2 and Era 3 Roadmaps.

### Key Audit Findings:
1. **Phase 4.99 Core Features (100% Functional Verification)**:
   - **`NodeConfigModal` 8-Agent Scatter Slotting**: Supports up to `MAX_SCATTER = 8` agent slots per scatter node, dynamic active project roster dropdowns with `GLOBAL` fallback, per-agent profile override modals (`AgentProfileOverridesModal`), individual slot removal buttons ("✕"), and complete configuration coverage across all 16/16 `CTRL_` primitives.
   - **VCR Transport State Machine**: Tri-state state machine (`idle`, `running`, `paused`) with clean thread-blocking synchronization via `threading.Event`, radio-dot navigation, and step context injection.
   - **Live Node Chat Context Injection**: Single-node context inspection and live chat via `NodeLiveChatModal`, supporting staged payload extraction, hot context injection, and resumption.
   - **Rich Tree `TopologyVisualizer`**: Default expanded MacroNode hierarchy with `Ctrl+E` keyboard collapse/expand toggles, 0.2s node pulse animation for active step, tether label badges (`[tether:id]`), and state-driven color coding.
   - **Agent Studio 3-Panel Arena (`AgentStudioChatScreen`)**: 3-panel layout, session bridge compilation to flow sequences, and `.dict` profile management.
   - **Session Manager (`SessionManagerModal`)**: Full management of FlowStasis (Paused), Completed sessions, and DeadFlows (Failed).

2. **Identified Edge Vulnerabilities & Domain Debt**:
   - **Modal Stack Re-entrancy Vulnerability (Phase 4.99 Edge)**: Rapid double-clicking on topology tree nodes or shortcut triggers (`F2`, `TopologyNodeDoubleClicked`) lacks a modal re-entrancy guard, allowing duplicate screens (e.g. `NodeConfigModal`) to stack on Textual's screen stack.
   - **Direct Main Thread I/O (Phase 6 Asynchronous Worker Debt)**: File system reads, JSON parsing, and database polling inside UI event handlers (`on_mount`, `Select.Changed`) execute synchronously on Textual's main event loop instead of offloading to `@work(thread=True)` workers.
   - **Path Resolution Sovereign Law VIII Debt**: Direct `Path(__file__).parent.parent.resolve()` calls in `AgentStudioChatScreen`, `nexus_plex.py`, and `splash_screen.py` instead of anchoring via `get_maccre_root()`.

---

## 2. SUBSYSTEM AUDIT BREAKDOWN BY FILE

| Subsystem File | Function / Component Scope | Audit Status | Key Observations & Findings |
| :--- | :--- | :--- | :--- |
| `maccre_tui/nexus_plex.py` | `NexusPlex`, `NodeConfigModal`, `AgentProfileOverridesModal`, `AgentStudioChatScreen`, VCR Transport, Copilot | **VERIFIED / WARN** | Core 3-panel command center operates cleanly. `NodeConfigModal` supports 8 scatter slots and 16/16 `CTRL_` fields. **Warning:** Lacks modal re-entrancy guard on double-click; manual `Path(__file__)` resolution present. |
| `maccre_tui/nexus_plex.css` | Global TUI stylesheet (1,212 lines) | **VERIFIED** | Comprehensive CSS styling for split-pane layout, dark theme, VCR transport controls, modal dialogs, and scatter agent rows. |
| `maccre_tui/app.py` | Legacy `LiveSwarmTUI` live console | **VERIFIED** | Standalone C2 console for live session telemetry monitoring. |
| `maccre_tui/macro_editor_modal.py` | `MacroNodeEditorModal` | **VERIFIED** | Fullscreen modal for editing and previewing MacroNode templates. |
| `maccre_tui/widgets/topology_visualizer.py` | `TopologyVisualizer` Rich Tree | **VERIFIED** | Default expanded MacroNode hierarchy, `Ctrl+E` toggle, 0.2s node pulse timer, tether badges (`[tether:id]`), color coding. |
| `maccre_tui/widgets/session_manager_modal.py` | `SessionManagerModal`, `MacroNodeNameModal` | **VERIFIED** | Tri-column stasis/completed/deadflow manager, session renaming, canonization trigger, macro/template saving. |
| `maccre_tui/widgets/information_panel.py` | `InformationPanel` (6 accordion panes) | **VERIFIED** | Collapsible guidance panel replacing legacy builder panel. |
| `maccre_tui/widgets/flow_monitor_overlay.py` | `FlowMonitorOverlay` | **VERIFIED** | Real-time execution monitor overlaying InformationPanel during active flows. |
| `maccre_tui/widgets/macronode_workshop.py` | `MacroNodeWorkshop` | **VERIFIED** | Right-side workshop binding NodeCatalog, TopologyVisualizer, and auto-tethering logic. |
| `maccre_tui/widgets/node_catalog.py` | `NodeCatalog` | **VERIFIED** | Tabbed browser for selecting MacroNodes, Agents, and Control Nodes. |
| `maccre_tui/widgets/project_canon_modal.py` | `ProjectCanonModal` | **VERIFIED** | Memory pin browser and unified session ledger inspector. |
| `maccre_tui/widgets/onionbook_modal.py` | `OnionBookModal` | **VERIFIED** | Token burn and financial cost tracking ledger modal. |
| `maccre_tui/widgets/finops_modals.py` | `BudgetProposalModal`, `BudgetWarningModal` | **VERIFIED** | HITL cost approval modals invoked by `CTRL_REVIEW`. |
| `maccre_tui/widgets/splash_screen.py` | `BootSplashModal`, `LoadingSplashModal` | **VERIFIED** | Startup project selector and threaded splash screen loader. |

---

## 3. PHASE 4.99 PRODUCTION BOUNDARY FEATURE AUDIT

### 3.1 `NodeConfigModal` 8-Agent Scatter Slotting (`CTRL_SCATTER`)
- **Capacity Guardrail**: Hard cap of `MAX_SCATTER = 8` agent slots per scatter node (`nexus_plex.py:2192`). Adding a 9th agent is disabled with `disabled=len(self._scatter_agents) >= MAX_SCATTER`.
- **Active Roster Ingestion**: Queries active project agent store with fallback to `GLOBAL` roster (`_all_roster_agents`).
- **Per-Slot Profile Overrides**: Each slotted agent row features an "⚙ Overrides" button launching `AgentProfileOverridesModal` to configure thinking levels, model IDs, temperature, tools allowed, and custom system instructions.
- **Dynamic Slot Removal**: Individual "✕" button per slotted agent row with immediate slot list re-indexing.
- **16/16 Control Primitive Coverage**: `_compose_ctrl_fields` covers all 16 `CTRL_` node types (`CTRL_ANCHOR`, `CTRL_PAUSE`, `CTRL_DELAY`, `CTRL_CHECKPOINT`, `CTRL_RECURSION`, `CTRL_TRANSFORM`, `CTRL_SCATTER`, `CTRL_MERGE`, `CTRL_CONCAT`, `CTRL_BRANCH`, `CTRL_FILTER`, `CTRL_CLEANUP`, `CTRL_CONDITIONAL_ROUTE`, `CTRL_END`, `CTRL_PAYLOAD_INJECT`, `CTRL_REVIEW`).

### 3.2 Interactive VCR Transport State Machine
- **Tri-State Transitions**: Switches cleanly between `idle`, `running`, and `paused` states (`nexus_plex.py:3542-3586`).
- **Thread Blocking**: `_flow_pause_event.clear()` cleanly halts background worker threads without deadlocks; `_flow_pause_event.set()` resumes execution.
- **Radio-Dot Navigation**: Allows clicking left/right radio dots on active flow steps to select execution insertion points (`_enter_paused_state`, `_refresh_paused_flow_line`).
- **Mid-Flow Context Injection**: Injects custom payload text before/after selected node prior to resuming execution (`_open_paused_injection_modal`).

### 3.3 Live Node Chat Context Injection (`NodeLiveChatModal`)
- **Staged Payload Extraction**: Extracts payload from preceding node or pending payload file (`nexus_plex.py:4588-4605`).
- **Live Node Discussion**: Displays staged payload (up to 2,000 chars preview) and allows 1:1 chat with the active node's designated agent.
- **Hot Context Injection**: Modified response text is saved into `_injected_context` and ready for resumption when `▶` is pressed.

### 3.4 Rich Tree `TopologyVisualizer`
- **Default Hierarchy Unrolling**: Inner MacroNode topologies default to expanded display (`_expand_states.get(node_id, True)`).
- **`Ctrl+E` Keyboard Toggle**: Intercepts `Ctrl+E` keypress to expand or collapse MacroNode inner steps on the selected tree node (`topology_visualizer.py:555-558, 615-624`).
- **Condensed Collapsed Summary**: Displays `[+] MacroNode ⟩ N nodes ⟩ NextNode` when collapsed.
- **0.2s Node Pulse Animation**: `_tick_animation` updates active node labels every 200ms with smooth pulsing frames (`●`, `◉`, `○`, `◉`).
- **Tether Badges & Color Scheme**: Visualizes `[tether:id]` badges in orange (`#f0883e`) and color-codes agents (blue), macronodes (purple), branch (gold), and cleanup (green).

---

## 4. ROADMAP PINNING MATRIX

All audit findings across the TUI & Interface domain have been mapped and pinned to their canonical phases in Era 2 and Era 3 Roadmaps:

| Audit Finding / Feature | Roadmap Category | Canonical Roadmap Phase | Priority / Impact |
| :--- | :--- | :--- | :--- |
| **8-Agent Scatter Slotting (`NodeConfigModal`)** | Past / Current Completed | **Phase 4.75.7 / Phase 4.99** | **Verified (Production Ready)** |
| **VCR Transport Pause / Resume / Step** | Past / Current Completed | **Phase 1.1 / Phase 4.99** | **Verified (Production Ready)** |
| **Live Node Chat Context Injection** | Past / Current Completed | **Phase 4.0 / Phase 4.99** | **Verified (Production Ready)** |
| **TopologyVisualizer Tree `Ctrl+E` Toggle** | Past / Current Completed | **Phase 4.75.5 / Phase 4.99** | **Verified (Production Ready)** |
| **Session Manager Stasis / Canonization** | Past / Current Completed | **Phase 2.1 / Phase 4.99** | **Verified (Production Ready)** |
| **Modal Stack Re-entrancy Protection** | Phase 4.99 Edge Issue | **Phase 4.99 (Immediate Test Edge)** | **High (Fix Recommended)** |
| **Path Anchoring Sovereign Law VIII Debt** | Domain Debt | **TUI Domain Debt / Sovereign Law VIII** | **Medium (Refactor Recommended)** |
| **Event-Driven `@work` Async State Container** | Future Phase | **Phase 6.0 (Phase 6 TUI Polish)** | **Planned Era 3 Strategic Goal** |
| **`NodeConfig` Overlay Conversion** | Future Phase | **Phase 6.1 (Phase 6 TUI Polish)** | **Planned Era 3 Stretch Goal** |
| **Drag-and-Drop Topology Canvas** | Future Phase | **Phase 6.2 (Phase 6 TUI Polish)** | **Planned Era 3 Stretch Goal** |
| **Marching-Ants Animated Flow Wires** | Future Phase | **Phase 6.9 (Phase 6 TUI Polish)** | **Planned Era 3 Stretch Goal** |
| **Center-Justified Flow Tree** | Future Phase | **Phase 6.10 (Phase 6 TUI Polish)** | **Planned Era 3 Stretch Goal** |
| **Time-Travel Lineage Scrubber** | Future Phase | **Phase 7.1 (Phase 7 Telemetric Memory)** | **Planned Era 3 Strategic Goal** |
| **In-State Live Dev Chat Studio Terminal** | Future Phase | **Phase 9.3 (Phase 9 Desktop Transition)**| **Planned Era 3 Horizon Goal** |

---

## 5. RECOMMENDED ACTION PLAN & REMEDIATION

1. **Implement Modal Re-entrancy Guard (Phase 4.99 Edge Fix)**:
   Add a simple re-entrancy check in `NexusPlex.push_screen()` calls or a helper `_push_modal_guarded()`:
   ```python
   def _push_modal_guarded(self, modal: ModalScreen, callback: Any = None) -> None:
       if any(isinstance(s, modal.__class__) for s in self.screen_stack):
           return
       self.push_screen(modal, callback)
   ```

2. **Remediate Manual Path Anchoring (Sovereign Law VIII Compliance)**:
   Replace all instances of `Path(__file__).parent.parent.resolve()` in `nexus_plex.py`, `AgentStudioChatScreen`, and `splash_screen.py` with `get_maccre_root()` imported from `maccre_core.utils.path_resolver`.

3. **Prepare Event-Driven Textual Workers for Phase 6.0**:
   Annotate synchronous I/O methods in `SessionManagerModal` and `AgentStudioChatScreen` with `@work(thread=True)` to decouple Textual event loop rendering from filesystem/database disk reads.

---

*Report compiled and certified by TUIAndInterface_Oracle.*
