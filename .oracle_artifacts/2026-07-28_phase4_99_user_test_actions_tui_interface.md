# Phase 4.99 User Test Actions: TUI & Interface Domain

**Domain Specialist Oracle:** `TUIAndInterface_Oracle`  
**Date:** 2026-07-28  
**Target Subsystem:** `maccre_tui/` (`nexus_plex.py`, `nexus_plex.css`, `widgets/topology_visualizer.py`, `widgets/session_manager_modal.py`, `NodeConfigModal`, `AgentProfileOverridesModal`, VCR Transport State Machine, 21 Modals Stack)  
**Execution Context:** Omni CI/CD Framework (`omni run`, `omni qa`)

---

## Executive Summary

This document defines 7 high-stress, comprehensive **User Test Actions** for Phase 4.99 from the perspective of the `TUIAndInterface` domain. These test scenarios target edge-case stress conditions, re-entrancy vulnerabilities, DOM dynamic mounting bounds, state persistence across nested modals, VCR transport controls during multi-threaded execution, and layout responsiveness.

---

## Phase 4.99 High-Stress User Test Actions

### Test Action 1: CTRL_SCATTER 8-Agent Maximum Slotting & Roster Overflow Stress
* **Target Codebase Component**: `maccre_tui/nexus_plex.py` -> `NodeConfigModal` (`_compose_ctrl_fields`, `_scatter_agents`, `#scatter-slot-header`, `MAX_SCATTER = 8`), Roster `Select` dropdowns, `#btn-add-scatter-agent`, `#btn-remove-scatter-agent`.
* **Step-by-Step Operator TUI Action**:
  1. Open `NexusPlex` TUI (`omni run maccre_tui/app.py`).
  2. Double-click a `CTRL_SCATTER` node in the `TopologyVisualizer` tree (or select node and press `F2`).
  3. In `NodeConfigModal`, scroll to the Control Node Config section for `CTRL_SCATTER`.
  4. Select an agent from the active project roster dropdown and click `+ Add Slot`.
  5. Repeat step 4 rapidly until 8 agent slots are mounted in the modal container.
  6. Attempt to select an agent and click `+ Add Slot` a 9th time.
  7. Click `Remove` on intermediate slots (e.g., Slot #3 and Slot #5), then modify profile overrides (`⚙ Overrides`) for Slot #2.
  8. Click `Save`.
* **Edge-Case / Stress Condition**:
  * Attempting to exceed `MAX_SCATTER` (8 agents); rapid button clicking causing container dynamic re-composition race conditions; index shifting when deleting intermediate slots while child overrides exist.
* **Expected System Behavior & TUI Domain Validation Criteria**:
  * The slot header dynamically updates counter (`Scatter Agent Slots (8/8)`).
  * Upon reaching 8 slots, `#btn-add-scatter-agent` and the roster `Select` widget are automatically set to `disabled=True`, preventing slotting beyond `MAX_SCATTER`.
  * A Textual `Toast/Notify` notification informs the operator of the maximum slot limit.
  * Deleting intermediate slots re-indexes remaining slots cleanly without stale DOM keys or index out-of-bound errors when saving configuration dictionary.

---

### Test Action 2: Rapid Double-Clicking & Modal Stacking / Re-Entrancy Prevention
* **Target Codebase Component**: `maccre_tui/nexus_plex.py` (`TopologyVisualizer` node double-click handler `on_tree_node_selected`, `F2` action, modal stack `push_screen`).
* **Step-by-Step Operator TUI Action**:
  1. Focus the `TopologyVisualizer` widget in `NexusPlex`.
  2. Rapidly double-click multiple topology tree nodes (or rapidly hit `F2` while a modal transition is in progress).
  3. Simultaneously trigger keyboard shortcut `Ctrl+S` or click `#btn-session-manager` to launch `SessionManagerModal` while `NodeConfigModal` is instantiating.
* **Edge-Case / Stress Condition**:
  * Modal re-entrancy / double-pushed `ModalScreen` instances on the Textual screen stack, leading to frozen background overlays, dual input focus, or orphaned child screens.
* **Expected System Behavior & TUI Domain Validation Criteria**:
  * Re-entrancy guard flags in `NexusPlex` block duplicate `push_screen` calls while a modal push transition is pending.
  * Exactly one modal (`NodeConfigModal` or `SessionManagerModal`) is active on the screen stack.
  * Focus is captured exclusively by the active top-level modal. Pressing `Esc` or clicking `Cancel` cleanly pops the modal back to `NexusPlex` primary view without leaving zombie backdrops or input locks.

---

### Test Action 3: Topology Tree Collapse/Expansion Toggle (`Ctrl+E`) & Summary Bar Density
* **Target Codebase Component**: `maccre_tui/widgets/topology_visualizer.py` (`TopologyVisualizer.action_toggle_expand`, `on_key` intercept for `ctrl+e`, condensed summary line widget).
* **Step-by-Step Operator TUI Action**:
  1. Load a complex flow topology containing nested MacroNodes and scatter children.
  2. Hit `Ctrl+E` repeatedly in rapid succession to toggle between full tree expansion and collapsed summary line mode.
  3. Attempt node re-ordering shortcuts (`Ctrl+Up` / `Ctrl+Down`) while the visualizer is in collapsed summary mode.
  4. Toggle `Ctrl+E` back to expanded view.
* **Edge-Case / Stress Condition**:
  * High-frequency keyboard toggling (`Ctrl+E`) while asynchronous node execution status pulses (0.2s timer) are actively updating node styling in background threads.
* **Expected System Behavior & TUI Domain Validation Criteria**:
  * In collapsed state, `TopologyVisualizer` renders a single condensed summary line (`[Topology: N nodes, M control nodes]`).
  * `Ctrl+E` toggles expansion state atomically without thread corruption or lost node data.
  * Node re-ordering operations in collapsed mode either update the underlying topology array cleanly or notify the operator that re-ordering requires expanded view, preserving tree integrity upon re-expansion.

---

### Test Action 4: Mid-Scatter VCR Transport Controls (Pause/Resume/Step State Machine)
* **Target Codebase Component**: `maccre_tui/nexus_plex.py` (`#btn-vcr-play`, `#btn-vcr-pause`, `#btn-vcr-step`, `#btn-vcr-stop`), `FlowEngine` VCR state machine, live node chat pane, step context injection.
* **Step-by-Step Operator TUI Action**:
  1. Start execution of a workflow containing a `CTRL_SCATTER` node.
  2. While scatter workers are executing concurrently, click `#btn-vcr-pause` (or press Pause shortcut).
  3. Inspect node status radio-dots and agent log stream in the right execution panel.
  4. Enter a custom context string into the Live Node Chat input pane and hit `Send` to inject step context.
  5. Click `#btn-vcr-step` once to advance a single scatter sub-task node.
  6. Click `#btn-vcr-play` to resume full asynchronous flow.
* **Edge-Case / Stress Condition**:
  * Intercepting multi-threaded scatter workers mid-execution; thread-safe state transition (`PAUSED` state synchronization between UI event loop and SQLite WAL scatter-gather queue).
* **Expected System Behavior & TUI Domain Validation Criteria**:
  * VCR status badge transitions from `[RUNNING]` to `[PAUSED]`. Worker threads pause execution cleanly at the next step yield boundary without throwing thread exception backtraces.
  * Injected step context is cleanly appended into payload metadata for the target node.
  * `#btn-vcr-step` executes exactly one node step and returns flow state to `PAUSED`. `#btn-vcr-play` resumes background execution without duplicate event dispatch or lost node context.

---

### Test Action 5: Session Management: Dynamic Rename, Canonization, & Hot-Reload
* **Target Codebase Component**: `maccre_tui/widgets/session_manager_modal.py`, `maccre_tui/nexus_plex.py` (`SessionBridgeCompiler`, `#btn-compile-session`, session tree view loader).
* **Step-by-Step Operator TUI Action**:
  1. Open `SessionManagerModal` (`Ctrl+S` or `#btn-session-manager`).
  2. Select an active session from the session tree list and click `Rename Session`.
  3. Enter a target name containing spaces and special characters (`Phase 4.99 Stress Test Session [CANON]`).
  4. Click `Compile & Canonize` (`#btn-compile-session`) to trigger the `SessionBridgeCompiler`.
  5. Switch active session selection in `SessionManagerModal` while live execution log telemetry is actively streaming.
* **Edge-Case / Stress Condition**:
  * Renaming active session directories on the filesystem while log handlers have open file descriptors; path resolution via `get_maccre_root()`; switching sessions mid-stream.
* **Expected System Behavior & TUI Domain Validation Criteria**:
  * Session rename operation sanitizes special characters safely and updates `get_maccre_root()` relative session directory anchors without breaking log handlers.
  * `SessionBridgeCompiler` compiles raw JSON state into markdown canon artifacts asynchronously via `call_from_thread()`, keeping UI smooth.
  * Switching sessions cleanly detaches old log stream and attaches new log stream without cross-session log bleed or unhandled file exceptions.

---

### Test Action 6: Agent Profile Overrides Modal Form Persistence & Rollback Integrity
* **Target Codebase Component**: `maccre_tui/nexus_plex.py` (`AgentProfileOverridesModal`, `NodeConfigModal`), agent profile validation schema.
* **Step-by-Step Operator TUI Action**:
  1. Double-click an Agent Node in `TopologyVisualizer` to open `NodeConfigModal`.
  2. Select an agent from dropdown and click `⚙ Overrides` to open `AgentProfileOverridesModal`.
  3. Modify System Prompt override text, switch Model provider (`gemini-2.5-pro` vs `gemma3:9b`), set Temperature to boundary value (`0.0` or `1.0`), and change Max Tokens.
  4. Click `Save Overrides` to return to `NodeConfigModal`.
  5. In `NodeConfigModal`, click `Cancel`.
  6. Re-open `NodeConfigModal` for the same node and check agent overrides.
* **Edge-Case / Stress Condition**:
  * Nested modal state propagation vs outer modal cancellation (ensuring changes in child modal do not commit if parent modal is cancelled); boundary values for numerical inputs.
* **Expected System Behavior & TUI Domain Validation Criteria**:
  * Cancelling the parent `NodeConfigModal` rolls back all nested overrides, leaving original node config intact.
  * Saving `NodeConfigModal` persists the nested overrides dictionary into the node state. Form validation blocks non-numeric inputs for max tokens / temperature with clear error notices.

---

### Test Action 7: Multi-Modal Navigation & 21-Modal Cascade Navigation Integrity
* **Target Codebase Component**: All 21 Modal Screens in `maccre_tui/` (`macro_editor_modal.py`, `onionbook_modal.py`, `finops_modals.py`, `project_canon_modal.py`, `NodeConfigModal`, `SessionManagerModal`, etc.), Textual screen stack and layout CSS.
* **Step-by-Step Operator TUI Action**:
  1. Open each modal sequentially using global hotkeys (`Ctrl+M` Macro Editor, `Ctrl+O` Onionbook, `Ctrl+F` FinOps, `Ctrl+P` Project Canon, etc.).
  2. Rapidly cycle through fields using `Tab` / `Shift+Tab`, then dismiss via `Esc`.
  3. Trigger terminal window resize (e.g. collapse height/width to small size, then restore) while a modal is mounted.
* **Edge-Case / Stress Condition**:
  * Terminal resize causing CSS layout clipping or container overflows; key event interception leaking through unmounted modals; screen focus state loss upon modal unmount.
* **Expected System Behavior & TUI Domain Validation Criteria**:
  * Percentage-based dynamic layout dimensions (`width: 95%`, `max-width: 160`, `max-height: 95vh`) prevent layout breakdown or clipped text during resize.
  * Dismissing any modal cleanly returns input focus to the active pane in `NexusPlex` (`TopologyVisualizer` or `NexusInput`).
  * No memory leaks, duplicate screen instances, or dangling event watchers remain in Textual app stack.

---

## Validation Summary Checklist for Phase 4.99 Execution

| Test Action ID | Subsystem Target | Stress Focus | Status |
| :--- | :--- | :--- | :--- |
| **TA-TUI-01** | `NodeConfigModal` / `CTRL_SCATTER` | MAX_SCATTER (8) Slotting Overflow & Roster Mutex | Pending Operator QA |
| **TA-TUI-02** | `NexusPlex` Modal Stack | Double-Click & Hotkey Re-Entrancy Protection | Pending Operator QA |
| **TA-TUI-03** | `TopologyVisualizer` Tree | `Ctrl+E` Collapse/Expand & Node Move Integrity | Pending Operator QA |
| **TA-TUI-04** | VCR Transport & Live Chat | Mid-Scatter Pause/Resume & Step Context Injection | Pending Operator QA |
| **TA-TUI-05** | `SessionManagerModal` & Bridge Compiler | Dynamic Session Rename, Canonization & Hot-Reload | Pending Operator QA |
| **TA-TUI-06** | `AgentProfileOverridesModal` | Nested Modal State Cancellation Rollback & Schema Validation | Pending Operator QA |
| **TA-TUI-07** | 21-Modal Cascade & Responsive CSS | Key Intercept Isolation & Terminal Resize Responsiveness | Pending Operator QA |
