# GRANULAR FUNCTIONAL LEDGER: TUI WIDGETS & MODAL DIALOGS (`maccre_tui/`)

**Analysis Timestamp:** 2026-07-24  
**Target Subsystem:** `maccre_tui/` and `maccre_tui/widgets/`  
**Compliance Standard:** Sovereign Engineering Doctrine Rev 19.0 (Omni-Compliant JIT, 5-Tier Data Sovereignty, Zero-Zombie Cleanup)

---

## EXECUTIVE ARCHITECTURAL SUMMARY

The `maccre_tui` module forms the graphical edge execution environment for MACCREv2. Built on top of Textual and Rich, it features a **Topology-First Layout** that coordinates graph building, state-driven visual feedback, financial token governance (FinOps), and live swarm telemetry. 

The architecture is divided into two primary component classes:
1. **Interactive Workshop & Visualizer Panels** (`macronode_workshop.py`, `topology_visualizer.py`, `macronode_builder_panel.py`, `node_catalog.py`, `information_panel.py`, `flow_monitor_overlay.py`).
2. **Modal Dialogs & Decision Gates** (`macro_editor_modal.py`, `session_manager_modal.py`, `project_canon_modal.py`, `splash_screen.py`, `onionbook_modal.py`, `finops_modals.py`).

---

## FILE-BY-FILE GRANULAR FUNCTIONAL LEDGER

### 1. `macro_editor_modal.py` (`MacroNodeEditorModal`)
Fullscreen modal screen for creating, editing, and previewing Template MacroNodes and structural augments.

### 2. `topology_visualizer.py` (`TopologyVisualizer`)
State-driven Rich `Tree`-based visualizer for DAG flow topologies, supporting pulse animations, tether labels, and nested MacroNode expansion.

### 3. `macronode_builder_panel.py` (`MacroNodeBuilderPanel`)
Embedded vertical panel replacement for building and customizing MacroNodes in place.

### 4. `macronode_workshop.py` (`MacroNodeWorkshop`)
Main right-side orchestration workshop combining `NodeCatalog`, `TopologyVisualizer`, and Flow Control buttons. Automatically tethers `CTRL_SCATTER` to `CTRL_MERGE`.

### 5. `session_manager_modal.py` (`SessionManagerModal` & `MacroNodeNameModal`)
Session state manager for inspecting FlowStasis (active/paused), Completed sessions, and DeadFlows (failed).

### 6. `information_panel.py` (`InformationPanel` & `InfoPane`)
Context-sensitive left-side guidance panel containing 6 collapsible info panes.

### 7. `flow_monitor_overlay.py` (`FlowMonitorOverlay`)
Live execution dashboard overlaying the `InformationPanel` during active flow runs.

### 8. `project_canon_modal.py` (`ProjectCanonModal`)
Modal screen for inspecting session memories, managing knowledge graph pins, and viewing unified session ledgers.

### 9. `node_catalog.py` (`NodeCatalog`)
Tabbed browser widget for selecting MacroNodes, Agents, and Control Nodes.

### 10. `splash_screen.py` (`BootSplashModal` & `LoadingSplashModal`)
Startup project selector (`BootSplashModal`) and threaded background loading screen (`LoadingSplashModal`).

### 11. `onionbook_modal.py` (`OnionBookModal` & `FinOpsBuddy`)
Financial ledger modal tracking token consumption, API costs, and project health ratios.

### 12. `finops_modals.py` (`BudgetProposalModal` & `BudgetWarningModal`)
Human-in-the-loop (HITL) financial approval modals invoked by `CTRL_REVIEW`.
