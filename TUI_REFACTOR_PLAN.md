# TUI Refactor — NexusPlex v2 (Codename: "Topology-First Architecture")

**Date:** 2026-07-11T15:44:00-04:00
**Commit Purpose:** Pre-refactor rollback point

---

## Why This Refactor

The MACCREv2 TUI has evolved through 6+ eras of iterative development. Each era added capabilities that the next era built upon, but the UI layout was designed for an earlier version of the system. The introduction of **Control Nodes** (formerly "DET nodes" / "Special Nodes") as first-class composable primitives — alongside the realization that MacroNode topologies are *compositions* of these primitives — has revealed that the current TUI layout is structurally misaligned with how the system actually works.

### The Strangler Fig Realization

Every improvement we made to the TUI forced backend upgrades that made the *next* improvement possible. The MacroNode Builder Panel's layout struggles led us to deeply audit the template system. That audit revealed that DET nodes were the missing composable primitives. That led to the Control Node registry. The Control Node registry led to the Topology Visualizer concept. And the Topology Visualizer naturally replaces both the linear Flow Line AND the MacroNode Builder — because building a MacroNode IS building a topology.

This is textbook Strangler Fig: the old system's struggles birthed the patterns that the new system will crystallize.

### What Changes

| Current | New |
|---------|-----|
| Left Pane: MacroNode Builder Panel + Nexus Copilot | Left Pane: Information Panes (collapsible) + Nexus Copilot |
| Right Pane: Agent Builder + Flow Execution Panel | Right Pane: Agent Builder + MacroNode Workshop (Node Catalog + Topology Visualizer + flow controls) |
| Flow Line: horizontal button sequence | Topology Visualizer: vertical tree/DAG with clickable nodes |
| Three dropdowns (Agent/Macro/Special) | Unified Node Catalog (from 3 registries) |
| DET_ prefix, "Special Nodes" | CTRL_ prefix, "Control Nodes" |
| Flow Registry (SQLite) | Deprecated — "Save to MacroNode Registry Only" |
| `flow_registry.py` | Deleted |
| `deterministic_nodes.py` DET_PREFIX | Dual-prefix support (CTRL_ primary, DET_ compat) |
| Hardcoded special nodes list | `controlnode_registry.db` (dynamic) |

### What Does NOT Change

- Agent Builder Panel (stays in right pane, same position)
- Nexus Copilot (stays in left pane bottom, same expand/collapse)
- All execution logic (swarm_worker, local_broker, flow_engine)
- All modals and their business logic (NodeConfigModal, SessionManagerModal, etc.)
- Agent library, MacroNode registry backend
- The render pipeline, FinOps system, dialogue runners

### Files Attached to This Commit

- `FeatureRequests.md` — Updated with Nexus Copilot Sandbox Enhancement entry
- `maccre_tui/nexus_plex.py` — Current state (pre-refactor)
- `maccre_tui/nexus_plex.css` — Current state (pre-refactor)
- `maccre_tui/widgets/macronode_builder_panel.py` — Will be superseded by MacroNode Workshop

---

## Phased Implementation Plan (Summary)

### Phase 0: Foundation (No UI Changes)
- Create `controlnode_registry.db` + `ControlNodeStore`
- Seed with all existing + planned Control Nodes
- Add `deprecated` column to `macronode_registry`
- Fix `nexus_plex.py` L2342 save handler bug
- Add CTRL_ prefix support alongside DET_ in `deterministic_nodes.py`

### Phase 1: Deprecation & Cleanup
- Remove Flow Registry (flow_registry.py, FlowRegistryModalScreen, all consumers)
- Rewire Session Manager "Save to Flow Registry" → "Save to MacroNode Registry"
- Remove 3 orphaned surfaces (EditAgentModal, AgentChatInputModalScreen, PhysicsMonitor)
- Fix 3 bugs found in surface audit

### Phase 2: Left Pane Transformation
- Replace MacroNodeBuilderPanel with collapsible Information Panes
- Reuse existing info panel logic from Flow Execution detail panels
- Match collapsed height to Nexus Copilot panel
- Context-sensitive expand/collapse behavior

### Phase 3: MacroNode Workshop (Right Pane)
- Build `topology_visualizer.py` as standalone module
- Build Node Catalog widget (unified agent/macro/control browser)
- Migrate flow control buttons from FlowExecutionPanel
- NodeConfiguration overlay (covers Agent Builder area)

### Phase 4: Integration
- Replace FlowExecutionPanel with MacroNode Workshop + Topology Visualizer
- Live execution highlighting on topology tree
- Flow Monitor as overlay panel
- Full DET_ → CTRL_ rename

### Phase 5: Evolution
- Implement new Control Node primitives (CTRL_MERGE, CTRL_SCATTER, etc.)
- Refactor template builders to use Control Node compositions
- Nexus Copilot sandbox integration
