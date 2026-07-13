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

### Phase 5: Control Node Evolution + Tethering + Session Dictionary
*(Active — see `implementation_plan.md` for detailed 40-item breakdown)*

#### 5.1 Control Node Implementations (7 Priority Nodes)
- Implement handlers in `deterministic_nodes.py` for: CTRL_MERGE, CTRL_SCATTER, CTRL_CONCAT, CTRL_BRANCH, CTRL_CONDITIONAL_ROUTE, CTRL_FILTER, CTRL_CLEANUP
- Update `controlnode_registry.py` seeds → status `active`, populate handler refs + config schemas
- Extend fan-in artifact collection in `swarm_worker.py` to run for CTRL_ nodes (tether-scoped)

#### 5.2 Node Tethering + Flow Lines
- `tether_id` system linking SCATTER↔sink pairs (MERGE, CONCAT, BRANCH, CONDITIONAL_ROUTE)
- `FlowLineID` parentage tracking with dot-delimited nesting for nested scatters
- Auto-tethering logic when sink nodes are added to topology
- CTRL_SCATTER companion auto-create option (pre-tethered MERGE/CONCAT/BRANCH/CONDITIONAL_ROUTE)
- `flow_line_id` column in `task_queue` table, tether-scoped Wait_For in broker

#### 5.3 Session Dictionary (Flow .dict)
- Extend Chat Studio `.dict` pattern to Flow sessions (`_flow_meta` + agent profiles)
- In-memory dict buffer built as nodes are added, displayed in InformationPanel
- `AgentProfileOverridesModal` — per-agent session-specific config (mirrors ChatBuilderPane)
- Tool Assignments checkmark selection in overrides modal
- Dict written on Launch, loaded on Resume, override precedence: dict > CSV > DB

#### 5.4 Dual-Pass Conditional Routing (Quadrivector Failback)
- Pass 1: Agent free-form response (unimpeded, normal temp)
- Pass 2: Same agent structured extraction (temp=0.1, `response_schema` with `route_to` field)
- Failback chain: Structured Output → Keyword Gate → Score Threshold → Fuzzy ROUTE_TO
- CTRL_CONDITIONAL_ROUTE config section in NodeConfig Modal

#### 5.5 Session Manager — Dual MacroNode Save
- "Save Topology as MacroNode" (fully configured) + "Save as MacroNode Template" (blank slots)
- `MacroNodeNameModal` naming popup (no canonization required)
- Source logic: completed session selected → use session; none selected → use Topology Visualizer
- `save_mode` field in MacroNode registry: `"configured"` vs `"template"`

#### 5.6 Topology Visualizer Expansion
- Intuitive color coding system (cyan agents, magenta CTRL_, blue tethers, yellow flow lines)
- Flow line branch rendering (FL_α_0, FL_α_1, etc.)
- Tether label rendering (⟨tether:α⟩ with Greek letter pairing)
- MacroNode inner topology expansion
- Double-click node → NodeConfig Modal
- Keyboard shortcuts for node repositioning (Ctrl+↑↓←→)

#### 5.7 Workshop Cleanup
- Remove duplicate Flow Monitor section from MacroNodeWorkshop
- Verify Flow Monitor collapse/expand button in header works during live flow + resume

---

### Phase 6: Polish, Overlays, & Advanced Topology UX
*(Deferred from Phase 5 — stretch goals and refinements)*

#### 6.1 NodeConfig Overlay Conversion
- Convert `NodeConfigModal` from modal screen to `NodeConfigOverlay(Vertical)` widget
- Overlay covers AgentBuilder area while leaving MacroNodeWorkshop visible
- Requires significant CSS/layout refactoring of `NexusPlex.compose()` right-pane structure

#### 6.2 Topology Visualizer — Drag-and-Drop
- Replace keyboard shortcuts with true drag-and-drop node repositioning
- Requires custom canvas widget or Tree widget extension beyond Textual's native capabilities
- Evaluate Textual's roadmap for canvas/drag support vs. custom implementation

#### 6.3 Remaining CTRL_ Node Placeholders
- Implement remaining control node stubs currently seeded in `controlnode_registry.db`:
  - `CTRL_WEBHOOK` — HTTP event trigger for external system integration
  - `CTRL_EDGE_SYNC` — Local Edge LLM pairing for offloading to edge devices via Google Drive polling
  - `CTRL_CHAT` — Interactive HITL chat node (DET_CHAT from Era 2 roadmap Phase 4)
    - Chat w/ Preceding Agent (Beginning/End)
    - Chat w/ Next Agent (Pre-Payload/Post-Payload)
    - Group Chat with ephemeral agent support
    - Injectable while session is paused
  - Any additional CTRL_ primitives identified during Phase 5 testing

#### 6.4 Template System Modernization
- Refactor existing template builders (cascade, hologram, chord, crucible) to use CTRL_ compositions where applicable
- Template skeleton preview in Topology Visualizer when template selected from catalog
- Guided template mode — user selects template pattern, Topology Visualizer shows the skeleton with empty slots to fill

#### 6.5 Nexus Copilot Sandbox Integration
- Nexus agent awareness of topology structure for intelligent debugging
- Nexus-driven topology modification suggestions
- DeadFlow analysis via Nexus with auto-repair capability

#### 6.6 Advanced Topology UX
- Paused-session Flow Line injection (clickable pointers between nodes for live topology modification)
- Red "✕" node removal while paused or pre-launch
- Topology diff view (show what changed between sessions)
- Topology versioning (undo/redo for topology edits)
