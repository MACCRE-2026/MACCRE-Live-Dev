# Comprehensive Phase 4.75.7 Audit & Architectural Roadmap Audit Report — TUI & Interface Domain

**Date:** 2026-07-28  
**Oracle Domain:** TUIAndInterface_Oracle (`maccre_tui/`)  
**Target Files:** `maccre_tui/nexus_plex.py`, `maccre_tui/widgets/topology_visualizer.py`, `Era2_architectural_roadmap.md`

---

## 1. Audit of Phase 4.75.7 Implementation

### A. `maccre_tui/nexus_plex.py`
- **CTRL_SCATTER Agent Slotting UI**: Integrated into `NodeConfigModal._compose_ctrl_fields()` (lines 2182-2231) and `_collect_ctrl_config()` (lines 2423-2426). Features:
  - Header counter: `Scatter Agent Slots (N/8)` with strict `MAX_SCATTER = 8` bounds.
  - Dropdown selector `#cfg-scatter-agent-select` and `+ Add Agent` button (`#btn-scatter-add-agent`).
  - Dynamic vertical list `#scatter-agent-list` mounting slotted agents with individual `⚙ Overrides` and `✕` remove buttons.
- **Roster Loading**: Lines 2198-2204 dynamically query the active project store via `get_agent_store(getattr(self, "active_project", "") or "GLOBAL").get_names()`, guaranteeing active project agent profiles are prioritized over global fallbacks.
- **Overrides Modal Integration**:
  - `on_button_pressed` (lines 2635-2661) intercepts `btn-scatter-ovr-{idx}` to launch `AgentProfileOverridesModal` for any slotted scatter agent.
  - Custom overrides are captured in `self._scatter_agent_overrides` and node-level overrides in `self._agent_overrides_dict`.
- **Save Handler & Flow Step Integration**:
  - `save()` (lines 2705-2734) aggregates node payload mode, custom instructions, tool overrides, profile overrides, and tether/scatter config.
  - Returned payload is processed by `_apply_config()` (lines 3975-3996) which updates `step.config`, `payload_mode`, `custom_instructions`, `agent_tools_overrides`, and workshop agent profiles.
- **Topology Load & Config Double-Click**:
  - `_handle_topology_double_click` (lines 3914-4010) extracts step configuration, baked tools, agent slots, and launches `NodeConfigModal`.

### B. `maccre_tui/widgets/topology_visualizer.py`
- **Default Expanded Tree**:
  - Line 386 (`tree.root.expand_all()`) and line 406 (`self._expand_states.get(node_id, True)`) ensure MacroNode inner topologies default to expanded upon loading.
- **Collapse Toggle**:
  - `toggle_expansion(node_id)` (lines 347-356) toggles `self._expand_states[node_id]` and re-renders tree nodes with updated expansion indicators (`[+]` vs `[-]`).
  - Mapped to `ctrl+e` key binding and node click events.
- **Condensed Summary Label**:
  - Lines 465-470 render collapsed MacroNodes with a clean condensed summary suffix:  
    `[+] MacroNode ⟩ N nodes ⟩ NextNode`

---

## 2. Roadmap Evaluation Across Phases 1 through 7

| Phase | Core TUI / Interface Focus | Audit Status | Key Artifacts & Features |
| :--- | :--- | :--- | :--- |
| **Phase 1** | NexusPlex 3-Panel Layout & VCR Transport | **100% Complete** | `nexus_plex.py`, `nexus_plex.css`, VCR Machine (Idle, Running, Paused), thread-safe `call_from_thread` |
| **Phase 2** | Session Manager, DLQ & Agent Studio | **100% Complete** | `session_manager_modal.py`, Dead Letter UI / Flow Stasis bridge, 3-panel `AgentStudioChatScreen` |
| **Phase 3** | Modals Stack, Roster & Workshop | **100% Complete** | 21 Modal screens (`project_canon_modal.py`, `onionbook_modal.py`, FinOps), `MacroNodeWorkshop` dual save |
| **Phase 4 / 4.75** | Control Nodes & Topology Architecture | **100% Complete** | 16/16 `CTRL_` node modal configs, tethering badges, Quadrivector failback routing UI, Phase 4.75.7 SCATTER slotting |
| **Phase 5** | Multimodal & FinOps Authorizations | **Ready for Horizon** | FinOps USD burn authorization modal linked to `ManualInputRequired` pause events |
| **Phase 6** | Overlays, Stage Editor & Visual Polish | **Cleanly Deferred** | 6.1 Overlay conversion, 6.2 Drag-and-Drop, 6.3 CTRL_WEBHOOK/EDGE_SYNC/CHAT, 6.8 Stage Editor, 6.9 Animated Wires, 6.10 Center DAG |
| **Phase 7** | Telemetric Memory & Replay UX | **Cleanly Deferred** | 7.1 Time-Travel Replay timeline scrubber widget, 7.2 Agent Trace observer, 7.3 Counterfactual Simulation UI |

---

## 3. Specialist Oracle Direct Answers

1. **Is Phase 4.75.7 properly and completely finished?**  
   **YES.** Code inspection confirms that all features required by Phase 4.75.7—including `CTRL_SCATTER` agent slotting, active project roster loading, profile overrides modal integration, config save handling, default expanded tree visualization, collapse toggling (`ctrl+e`), and condensed summary lines—are fully implemented, type-hinted, and compliant with Omni-Builder standards.

2. **Have all TUI & Interface items from previous phases (Phase 1 to 4.75.6) been completed?**  
   **YES.** All command center panes, VCR transport controls, 21 modals, Session Manager / Dead Letter UI, 16/16 `CTRL_` node configuration fields, agent overrides modal, tool checkmarks, tethering badges, and DAG tree features are 100% complete and operational.

3. **Are all Phase 6/7 TUI deferrals cleanly mapped and ready?**  
   **YES.** All Phase 6 (6.1–6.13) and Phase 7 (7.1–7.3) deferrals are clearly defined with explicit contracts (such as `flow_vector` telemetry column placement in Phase 4.75.7 powering Phase 6.13 WAL sharding and Phase 7 time-travel replay).
