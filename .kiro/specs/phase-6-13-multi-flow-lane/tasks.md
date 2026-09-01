# Task Breakdown: Phase 6.13 — Multi-Flow-Lane Authoring & Visualization

## Overview

This document breaks down Phase 6.13 implementation into 46 discrete tasks organized across 8 phases. Total estimated effort: **248 hours** over an 8-week timeline with 3 parallel developer tracks after Week 2.

---

## Task Organization

### Critical Path
Tasks marked with 🔴 are **critical path blockers** that must complete before dependent tasks can start.

### Dependency Notation
- **Depends on**: Tasks that must complete first
- **Enables**: Tasks that can start after this completes
- **Parallel with**: Tasks that can be worked on simultaneously

### Effort Estimates
- **S** (Small): 2-4 hours
- **M** (Medium): 6-8 hours
- **L** (Large): 12-16 hours
- **XL** (Extra Large): 20-24 hours

---

## Phase 1: Data Model Enhancement (Week 1)

### 🔴 Task 1.1: Enhance FlowStep Dataclass
**Effort**: M (8 hours)  
**Owner**: Core Engine Developer  
**Depends on**: None (critical blocker)  
**Enables**: All subsequent tasks

**Acceptance Criteria**:
- [ ] Add `children: list[list[FlowStep]]` field with default empty list
- [ ] Add `lane_metadata: dict[int, dict]` field with default empty dict
- [ ] Add `tether_id: str | None` field
- [ ] Add `flow_line_id: str | None` field
- [ ] Update `__post_init__` to validate children structure
- [ ] Add docstring examples for nested structure

**Files Modified**:
- `maccre_core/orchestration/flow_engine.py`

**Test Coverage**:
- Unit test: FlowStep initialization with children
- Unit test: Default values for new fields

---

### Task 1.2: Implement FlowStep Serialization
**Effort**: M (6 hours)  
**Owner**: Core Engine Developer  
**Depends on**: Task 1.1  
**Enables**: Task 1.3, 7.1

**Acceptance Criteria**:
- [ ] Implement `FlowStep.to_dict()` with recursive child serialization
- [ ] Implement `FlowStep.from_dict()` classmethod with recursive deserialization
- [ ] Handle empty `children` lists gracefully
- [ ] Preserve `lane_metadata` structure in round-trip
- [ ] Add schema version field (`"schema_version": "2.0"`)

**Files Modified**:
- `maccre_core/orchestration/flow_engine.py`

**Test Coverage**:
- Unit test: `test_flow_step_serialization_with_children()`
- Unit test: `test_flow_step_round_trip_equivalence()`
- Unit test: `test_empty_children_serialization()`

---

### Task 1.3: Implement FlowStep Traversal Methods
**Effort**: S (4 hours)  
**Owner**: Core Engine Developer  
**Depends on**: Task 1.2  
**Enables**: Task 2.2, 4.2

**Acceptance Criteria**:
- [ ] Implement `get_all_nodes_flat()` with DFS traversal
- [ ] Implement `find_by_tether_id(tether_id)` with recursive search
- [ ] Handle circular references (log warning, don't infinite loop)
- [ ] Return `None` for not-found tether IDs

**Files Modified**:
- `maccre_core/orchestration/flow_engine.py`

**Test Coverage**:
- Unit test: `test_get_all_nodes_flat_with_nesting()`
- Unit test: `test_find_by_tether_id_success()`
- Unit test: `test_find_by_tether_id_not_found()`

---

### Task 1.4: Enhance TopologyNodeData Dataclass
**Effort**: S (3 hours)  
**Owner**: Core Engine Developer  
**Depends on**: None  
**Parallel with**: Task 1.1

**Acceptance Criteria**:
- [ ] Add `wait_for: list[str]` field (gather node dependencies)
- [ ] Add `tether_id: str | None` field
- [ ] Add `flow_line_id: str | None` field
- [ ] Add `parent_scatter_id: str | None` field
- [ ] Add `temporal_position: int | None` field
- [ ] Add `is_highlighted: bool` field

**Files Modified**:
- `maccre_core/orchestration/flow_engine.py`

**Test Coverage**:
- Unit test: TopologyNodeData initialization with new fields

---

## Phase 2: Tether ID Infrastructure (Week 1-2)

### 🔴 Task 2.1: Implement TetherIDGenerator
**Effort**: M (6 hours)  
**Owner**: Core Engine Developer  
**Depends on**: Task 1.1  
**Enables**: Task 2.2, 2.3

**Acceptance Criteria**:
- [ ] Implement `generate_root_id()` returning 'X', 'Y', 'Z', etc.
- [ ] Implement `generate_child_ids(parent_id, count)` returning hierarchical IDs
- [ ] Implement `parse_depth(tether_id)` to count nesting level
- [ ] Handle edge case: root_counter overflow (Z → AA)
- [ ] Thread-safe counter incrementing (use threading.Lock)

**Files Modified**:
- `maccre_core/orchestration/flow_engine.py`

**Test Coverage**:
- Unit test: `test_generate_root_id()`
- Unit test: `test_generate_child_ids_hierarchy()`
- Unit test: `test_parse_depth()`
- Unit test: `test_thread_safe_generation()` (concurrent calls)

---

### Task 2.2: Assign Tether IDs on Flow Build
**Effort**: M (8 hours)  
**Owner**: Core Engine Developer  
**Depends on**: Task 2.1, Task 1.3  
**Enables**: Task 4.2, 5.2

**Acceptance Criteria**:
- [ ] On flow build, assign root tether ID to first node
- [ ] When CTRL_SCATTER is added, generate child tether IDs for each lane
- [ ] Populate `lane_metadata` with `{"tether_id": "X.1", ...}` for each lane
- [ ] Propagate parent lane's tether ID to inserted child nodes
- [ ] Update tether IDs when scatter slots are reordered

**Files Modified**:
- `maccre_core/orchestration/flow_engine.py`

**Test Coverage**:
- Unit test: `test_assign_tether_ids_linear_flow()`
- Unit test: `test_assign_tether_ids_scatter()`
- Unit test: `test_assign_tether_ids_nested_scatter()`

---

### Task 2.3: Migration Logic for Legacy Flows
**Effort**: S (4 hours)  
**Owner**: Core Engine Developer  
**Depends on**: Task 2.1  
**Parallel with**: Task 2.2

**Acceptance Criteria**:
- [ ] Detect schema version 1.0 (pre-6.13) in `load_flow()`
- [ ] Assign default tether ID `LEGACY_X` to all nodes
- [ ] Log warning message recommending re-save
- [ ] Handle missing `children` field gracefully (default to `[]`)
- [ ] Ensure backward compatibility with existing flow_history.json files

**Files Modified**:
- `maccre_core/orchestration/flow_engine.py`

**Test Coverage**:
- Integration test: Load legacy flow and verify tether assignment
- Integration test: Legacy flow executes without errors

---

## Phase 3: Node Config Modal Reactivity (Week 2)

### Task 3.1: Refactor NodeConfigModal to Reactive Components
**Effort**: L (12 hours)  
**Owner**: TUI Developer  
**Depends on**: None  
**Enables**: Task 3.2, 3.3

**Acceptance Criteria**:
- [ ] Convert scatter agent list to `Reactive(list)` state
- [ ] Implement `watch_scatter_agents()` callback to trigger re-render
- [ ] Replace static agent slot rendering with dynamic composition
- [ ] Add loading spinner during async agent picker dialog

**Files Modified**:
- `maccre_tui/modals/node_config_modal.py`

**Test Coverage**:
- UI test: Add agent, verify immediate render (< 200ms)
- UI test: Remove agent, verify slot disappears

---

### Task 3.2: Implement Reactive Scatter Slot Rendering
**Effort**: M (8 hours)  
**Owner**: TUI Developer  
**Depends on**: Task 3.1  
**Enables**: Task 3.4

**Acceptance Criteria**:
- [ ] Render agent label, ⚙ Overrides button, ✕ Remove button for each slot
- [ ] Disable "+ Add Agent" button when slot count reaches 8
- [ ] Update slot counter header reactively
- [ ] Apply distinct styling to filled slots vs. empty slots

**Files Modified**:
- `maccre_tui/modals/node_config_modal.py`

**Test Coverage**:
- UI test: Add 8 agents, verify button disabled
- UI test: Remove agent, verify button re-enabled

**Related Requirement**: REQ-1 (CTRL_SCATTER Modal Reactive Rendering)

---

### Task 3.3: Wire Scatter Config to Active Flow Sequence
**Effort**: M (6 hours)  
**Owner**: TUI Developer  
**Depends on**: Task 3.2  
**Enables**: Task 4.1

**Acceptance Criteria**:
- [ ] On "Save" button click, post message to `ActiveFlowSequence` with scatter agents
- [ ] `ActiveFlowSequence` subscribes to `ScatterConfigSaved` message
- [ ] Display agent names beneath CTRL_SCATTER node label
- [ ] Format agent names as `{agent_name}.{tether_id}`

**Files Modified**:
- `maccre_tui/modals/node_config_modal.py`
- `maccre_tui/widgets/active_flow_sequence.py`

**Test Coverage**:
- Integration test: Configure scatter, verify agents appear in Active Flow Sequence

**Related Requirement**: REQ-2 (Active Flow Sequence Scatter Visualization)

---

### Task 3.4: Implement Scatter Agent Slot Reordering
**Effort**: L (14 hours)  
**Owner**: TUI Developer  
**Depends on**: Task 3.2  
**Parallel with**: Task 3.3

**Acceptance Criteria**:
- [ ] Implement drag-and-drop handler for agent slot rows
- [ ] Display horizontal insertion indicator while dragging
- [ ] Update `scatter_agents` list order on drop
- [ ] Regenerate tether IDs based on new order (X.1 → X.2 if reordered)
- [ ] Update lane_metadata with new tether mappings

**Files Modified**:
- `maccre_tui/modals/node_config_modal.py`

**Test Coverage**:
- UI test: Drag slot 2 to position 1, verify tether IDs update

**Related Requirement**: REQ-27 (CTRL_SCATTER Agent Slot Reordering)

---

## Phase 4: Multi-Lane Visualization (Week 3-4)

### 🔴 Task 4.1: Implement Lane Extraction from FlowSteps
**Effort**: M (8 hours)  
**Owner**: TUI Developer  
**Depends on**: Task 3.3  
**Enables**: Task 4.2, 4.3

**Acceptance Criteria**:
- [ ] Implement `_extract_lane_groups()` in `ActiveFlowSequence`
- [ ] Return list of scatter groups with nested lane structures
- [ ] Handle flows with multiple CTRL_SCATTER nodes
- [ ] Handle nested scatter (scatter within scatter)

**Files Modified**:
- `maccre_tui/widgets/active_flow_sequence.py`

**Test Coverage**:
- Unit test: Extract lanes from single scatter
- Unit test: Extract lanes from nested scatter

---

### 🔴 Task 4.2: Implement Multi-Lane Expanded View
**Effort**: XL (20 hours)  
**Owner**: TUI Developer  
**Depends on**: Task 4.1, Task 2.2  
**Enables**: Task 4.3, 4.4

**Acceptance Criteria**:
- [ ] Implement `render_multi_lane_view()` with one row per lane
- [ ] Display lane label `{agent_name}.{tether_id}` on left side
- [ ] Render node boxes horizontally for each lane
- [ ] Calculate max lane length for temporal alignment
- [ ] Implement vertical scrolling when lanes exceed viewport height
- [ ] Add expand/collapse toggle button (◧/◨)

**Files Modified**:
- `maccre_tui/widgets/active_flow_sequence.py`
- `maccre_tui/styles/active_flow_sequence.tcss` (NEW)

**Test Coverage**:
- UI test: Expand view with 3 lanes, verify 3 rows visible
- UI test: Collapse view, verify single row

**Related Requirements**: REQ-3 (Multi-Lane Expansion Toggle), REQ-10 (Tether ID Display)

---

### Task 4.3: Implement Heterogeneous Length Dashed Fillers
**Effort**: M (8 hours)  
**Owner**: TUI Developer  
**Depends on**: Task 4.2  
**Parallel with**: Task 4.4

**Acceptance Criteria**:
- [ ] Calculate max lane length across all lanes
- [ ] For lanes shorter than max, append dashed boxes
- [ ] Style dashed boxes with `border: dashed`, `dim white` color
- [ ] Display tooltip "Temporal alignment filler (no node)" on hover
- [ ] Make filler boxes non-interactive (no click handler)

**Files Modified**:
- `maccre_tui/widgets/active_flow_sequence.py`

**Test Coverage**:
- UI test: 3 lanes with lengths [2, 4, 3], verify lane 1 gets 2 fillers

**Related Requirement**: REQ-28 (Heterogeneous Lane Length Dashed Filler)

---

### Task 4.4: Implement Per-Lane Collapse
**Effort**: M (6 hours)  
**Owner**: TUI Developer  
**Depends on**: Task 4.2  
**Parallel with**: Task 4.3

**Acceptance Criteria**:
- [ ] Add individual ▾/▸ collapse button to each lane row
- [ ] Track collapsed lanes in `self.collapsed_lanes: set[int]`
- [ ] Render collapsed lane as `[N nodes]` summary
- [ ] Preserve global expand state when collapsing individual lanes

**Files Modified**:
- `maccre_tui/widgets/active_flow_sequence.py`

**Test Coverage**:
- UI test: Collapse lane 2, verify other lanes remain expanded

**Related Requirement**: REQ-3.6 (Individual Lane Expand/Collapse)

---

### Task 4.5: Dynamic Vertical Scaling for Active Flow Sequence
**Effort**: S (4 hours)  
**Owner**: TUI Developer  
**Depends on**: Task 4.2  
**Parallel with**: Task 4.4

**Acceptance Criteria**:
- [ ] Update CSS to use `height: auto; max-height: 70vh`
- [ ] Set `min-height: 10` to prevent collapse
- [ ] Add vertical scrollbar when content exceeds max-height
- [ ] Preserve horizontal width (no horizontal scroll)
- [ ] Test at 50%, 100%, 150% terminal zoom

**Files Modified**:
- `maccre_tui/styles/active_flow_sequence.tcss`

**Test Coverage**:
- UI test: Render 10 lanes, verify scrollbar appears
- UI test: Resize terminal, verify height adjusts

**Related Requirement**: REQ-20 (Active Flow Sequence Dynamic Vertical Scaling)

---

## Phase 5: Topology Visualizer Enhancements (Week 4)

### 🔴 Task 5.1: Enhance Topology Tree Rendering with Tether IDs
**Effort**: M (6 hours)  
**Owner**: TUI Developer  
**Depends on**: Task 2.2  
**Enables**: Task 5.2, 5.3

**Acceptance Criteria**:
- [ ] Update `_add_node_to_tree()` to append tether ID to label
- [ ] Format as `NodeName [dim](TetherID)[/dim]`
- [ ] Display tooltip with full tether ID + flow line ID on hover
- [ ] Apply state-based styling (ACTIVE=yellow, COMPLETE=green, FAILED=red)

**Files Modified**:
- `maccre_tui/widgets/topology_visualizer.py`

**Test Coverage**:
- UI test: Render tree, verify tether IDs visible
- UI test: Hover node, verify tooltip contains tether ID

**Related Requirement**: REQ-11 (Tether ID Display in TopologyVisualizer)

---

### 🔴 Task 5.2: Implement Node Double-Click Highlighting
**Effort**: M (8 hours)  
**Owner**: TUI Developer  
**Depends on**: Task 5.1, Task 2.2  
**Enables**: Task 5.3

**Acceptance Criteria**:
- [ ] Add double-click event handler to tree node labels
- [ ] Set `self.highlighted_node = tether_id` on double-click
- [ ] Apply cyan bold border to highlighted node
- [ ] Post `NodeHighlighted(tether_id)` message to Node Catalog
- [ ] Clear highlight on click elsewhere (background, different node)

**Files Modified**:
- `maccre_tui/widgets/topology_visualizer.py`
- `maccre_tui/widgets/node_catalog.py`

**Test Coverage**:
- UI test: Double-click node, verify cyan border applied
- UI test: Click background, verify highlight cleared

**Related Requirement**: REQ-4 (Per-Lane Node Highlighting)

---

### Task 5.3: Dynamic Vertical Scaling for Topology Visualizer
**Effort**: S (3 hours)  
**Owner**: TUI Developer  
**Depends on**: Task 5.1  
**Parallel with**: Task 5.2

**Acceptance Criteria**:
- [ ] Update CSS to use `height: 1fr; min-height: 10`
- [ ] Add vertical scrollbar when tree exceeds viewport
- [ ] Preserve horizontal width
- [ ] Test with collapsed and expanded tree branches

**Files Modified**:
- `maccre_tui/styles/topology_visualizer.tcss`

**Test Coverage**:
- UI test: Render 20-node tree, verify scrollbar appears

**Related Requirement**: REQ-21 (TopologyVisualizer Dynamic Vertical Scaling)

---

### Task 5.4: Implement Nested Scatter Indentation
**Effort**: S (4 hours)  
**Owner**: TUI Developer  
**Depends on**: Task 5.1  
**Parallel with**: Task 5.3

**Acceptance Criteria**:
- [ ] Increase indentation level for child lanes under CTRL_SCATTER
- [ ] Apply distinct styling to nested scatter nodes (e.g., italic, muted color)
- [ ] Display warning icon (⚠) for scatter depth > 3
- [ ] Group child lanes under parent scatter in tree structure

**Files Modified**:
- `maccre_tui/widgets/topology_visualizer.py`

**Test Coverage**:
- UI test: Render nested scatter, verify indentation increases
- UI test: Scatter depth 4, verify warning icon visible

**Related Requirement**: REQ-19 (Nested Scatter Support)

---

## Phase 6: Per-Lane Node Insertion (Week 5)

### 🔴 Task 6.1: Implement Per-Lane Node Insertion Logic
**Effort**: XL (18 hours)  
**Owner**: Core Engine Developer  
**Depends on**: Task 5.2, Task 2.2  
**Enables**: Task 6.2, 6.3

**Acceptance Criteria**:
- [ ] Implement `insert_node_after_highlighted(target_tether_id, new_node_name, config)`
- [ ] Find target node by tether ID
- [ ] Validate target is within scatter→merge boundary
- [ ] Determine lane index from parent scatter
- [ ] Insert new FlowStep into lane's child list
- [ ] Assign new node the parent lane's tether ID
- [ ] Recalculate temporal positions for lane

**Files Modified**:
- `maccre_core/orchestration/flow_engine.py`

**Test Coverage**:
- Unit test: `test_insert_node_after_highlighted_success()`
- Unit test: `test_insert_node_outside_boundary_fails()`
- Integration test: Insert node, save, load, verify structure preserved

**Related Requirement**: REQ-5 (Per-Lane Node Insertion)

---

### Task 6.2: Wire Node Catalog to Per-Lane Insertion
**Effort**: M (6 hours)  
**Owner**: TUI Developer  
**Depends on**: Task 6.1  
**Enables**: Task 6.3

**Acceptance Criteria**:
- [ ] Subscribe to `NodeHighlighted` message in Node Catalog
- [ ] Apply matching border color when node is highlighted
- [ ] On catalog node click, check if highlight active
- [ ] If highlight active, call `insert_node_after_highlighted()`
- [ ] If no highlight, append to end of flow (backward-compatible behavior)
- [ ] Clear highlight after successful insertion

**Files Modified**:
- `maccre_tui/widgets/node_catalog.py`
- `maccre_core/orchestration/flow_engine.py`

**Test Coverage**:
- Integration test: Highlight node, add from catalog, verify inserted on correct lane

**Related Requirement**: REQ-5.1 (Per-Lane Node Insertion)

---

### Task 6.3: Implement Scatter→Merge Boundary Validation
**Effort**: M (8 hours)  
**Owner**: Core Engine Developer  
**Depends on**: Task 6.1  
**Parallel with**: Task 6.2

**Acceptance Criteria**:
- [ ] Implement `_is_within_scatter_merge_boundary(node)`
- [ ] Walk up tree to find parent CTRL_SCATTER
- [ ] Walk down tree to find corresponding gather node
- [ ] Return True if node is between scatter and gather
- [ ] Display error toast if validation fails

**Files Modified**:
- `maccre_core/orchestration/flow_engine.py`

**Test Coverage**:
- Unit test: Node between scatter and merge returns True
- Unit test: Node after merge returns False

**Related Requirement**: REQ-5.2 (Insertion Boundary Validation)

---

## Phase 7: Wait-All Merge Logic (Week 5-6)

### 🔴 Task 7.1: Implement GatherNodeExecutor
**Effort**: XL (16 hours)  
**Owner**: Core Engine Developer  
**Depends on**: Task 1.2  
**Enables**: Task 7.2, 7.3, 7.4

**Acceptance Criteria**:
- [ ] Create `GatherNodeExecutor` class in `local_broker.py`
- [ ] Implement `execute_gather(gather_node, upstream_lanes, timeout, threshold)`
- [ ] Poll lane completion status in async loop
- [ ] Wait for all lanes to complete (100% threshold)
- [ ] Handle lane failures gracefully (mark as incomplete)
- [ ] Return merged payload dict

**Files Modified**:
- `maccre_core/orchestration/local_broker.py`

**Test Coverage**:
- Unit test: `test_execute_gather_wait_all()`
- Integration test: 3 lanes with staggered delays, verify waits for slowest

**Related Requirement**: REQ-7 (CTRL_MERGE Wait-All Deterministic Gather)

---

### 🔴 Task 7.2: Implement Gather Timeout and Fallback
**Effort**: L (12 hours)  
**Owner**: Core Engine Developer  
**Depends on**: Task 7.1  
**Enables**: Task 7.4

**Acceptance Criteria**:
- [ ] Add timeout check in gather loop
- [ ] If timeout expires, calculate completion ratio
- [ ] If ratio >= partial_threshold, proceed with partial merge
- [ ] Mark incomplete lanes as FAILED in TopologyVisualizer
- [ ] Log warning message with incomplete lane tether IDs

**Files Modified**:
- `maccre_core/orchestration/local_broker.py`

**Test Coverage**:
- Integration test: `test_gather_timeout_fallback()`
- Integration test: Timeout with 66% threshold, verify partial merge

**Related Requirement**: REQ-9 (CTRL_MERGE Fallback and Self-Heal)

---

### Task 7.3: Implement Merge Payload Strategies
**Effort**: M (8 hours)  
**Owner**: Core Engine Developer  
**Depends on**: Task 7.1  
**Parallel with**: Task 7.2

**Acceptance Criteria**:
- [ ] Implement `merge_structured(lane_outputs, expected_lanes)`
- [ ] Implement `merge_concat(lane_outputs, expected_lanes, delimiter)`
- [ ] Handle incomplete lanes (inject `{"status": "incomplete"}`)
- [ ] Support custom delimiters for concat mode

**Files Modified**:
- `maccre_core/orchestration/local_broker.py`

**Test Coverage**:
- Unit test: Merge 3 complete lanes structured
- Unit test: Merge 2 complete + 1 incomplete lanes concat

**Related Requirement**: REQ-7 (CTRL_MERGE Wait-All)

---

### Task 7.4: Add Gather Config Fields to NodeConfigModal
**Effort**: M (6 hours)  
**Owner**: TUI Developer  
**Depends on**: Task 7.2  
**Parallel with**: Task 7.3

**Acceptance Criteria**:
- [ ] Add "Timeout (seconds)" input field
- [ ] Add "Partial Merge Threshold (%)" input field
- [ ] Add "Synthesis Agent" dropdown (optional)
- [ ] Add "Merge Mode" radio buttons (Structured | Concat)
- [ ] Persist config to `gather_node.config` on save

**Files Modified**:
- `maccre_tui/modals/node_config_modal.py`

**Test Coverage**:
- UI test: Configure timeout, save, reload, verify persisted

**Related Requirements**: REQ-8 (Synthesis Agent Slot), REQ-9 (Fallback Config)

---

## Phase 8: Advanced Features (Week 6-7)

### Task 8.1: Implement TetherNotesModal UI
**Effort**: L (12 hours)  
**Owner**: TUI Developer  
**Depends on**: None  
**Enables**: Task 8.2, 8.3

**Acceptance Criteria**:
- [ ] Create `TetherNotesModal` class with draggable UI
- [ ] Display list of noted nodes with tether IDs
- [ ] Add "📋 Copy All Tether IDs" button
- [ ] Add "✕" button to remove individual entries
- [ ] Implement drag-by-title-bar positioning

**Files Modified**:
- `maccre_tui/modals/tether_notes_modal.py` (NEW)
- `maccre_tui/models/tether_notes.py` (NEW)

**Test Coverage**:
- UI test: Add 3 notes, verify list displays
- UI test: Remove note, verify list updates

**Related Requirement**: REQ-12 (TetherNotesModal Keyboard Shortcut)

---

### Task 8.2: Implement SHIFT+F7 Tether Note Mode
**Effort**: M (8 hours)  
**Owner**: TUI Developer  
**Depends on**: Task 8.1  
**Enables**: Task 8.3

**Acceptance Criteria**:
- [ ] Add SHIFT+F7 key binding to `NexusPlex`
- [ ] Enter "tether note mode" (change cursor, show status message)
- [ ] On node click, open TetherNotesModal with clicked node's data
- [ ] Exit tether note mode after click or on ESC key

**Files Modified**:
- `maccre_tui/nexus_plex.py`
- `maccre_tui/widgets/topology_visualizer.py`

**Test Coverage**:
- UI test: Press SHIFT+F7, click node, verify modal opens
- UI test: Press ESC, verify mode exits

**Related Requirement**: REQ-12 (TetherNotesModal Keyboard Shortcut)

---

### Task 8.3: Implement Tether Notes Docking
**Effort**: M (6 hours)  
**Owner**: TUI Developer  
**Depends on**: Task 8.2  
**Parallel with**: Task 8.4

**Acceptance Criteria**:
- [ ] Add "⬆ Dock" button to modal title bar
- [ ] On dock, collapse modal to header icon "📌 N notes"
- [ ] Add docked icon to TUI header (top-right position)
- [ ] On docked icon click, expand modal to previous position
- [ ] Update note count reactively when adding notes while docked

**Files Modified**:
- `maccre_tui/modals/tether_notes_modal.py`
- `maccre_tui/nexus_plex.py` (header rendering)

**Test Coverage**:
- UI test: Dock modal, verify icon appears in header
- UI test: Undock modal, verify returns to floating state

**Related Requirement**: REQ-13 (TetherNotesModal Docking)

---

### Task 8.4: Implement Clipboard Copy for Tether IDs
**Effort**: S (3 hours)  
**Owner**: TUI Developer  
**Depends on**: Task 8.1  
**Parallel with**: Task 8.3

**Acceptance Criteria**:
- [ ] Install `pyperclip` dependency
- [ ] Implement `_copy_tether_ids_to_clipboard()` using pyperclip
- [ ] Format tether IDs as newline-separated list
- [ ] Display toast notification "Tether IDs copied to clipboard"
- [ ] Handle clipboard access errors gracefully

**Files Modified**:
- `maccre_tui/modals/tether_notes_modal.py`
- `pyproject.toml` (add pyperclip dependency)

**Test Coverage**:
- UI test: Copy 3 tether IDs, verify clipboard contains newline-separated text

**Related Requirement**: REQ-12.5 (Copy All Tether IDs)

---

### Task 8.5: Implement Tether ID Grouping in Dropdowns
**Effort**: M (8 hours)  
**Owner**: TUI Developer  
**Depends on**: Task 2.2  
**Parallel with**: Task 8.1

**Acceptance Criteria**:
- [ ] Update node selection dropdowns to format as `NodeName (TetherID)`
- [ ] Group options by flow line ID with visual separator
- [ ] Sort nodes within each group by temporal position
- [ ] Apply grouping to "Route To", "Loop Target", etc. dropdowns

**Files Modified**:
- `maccre_tui/modals/node_config_modal.py`

**Test Coverage**:
- UI test: Open Route To dropdown, verify grouped by flow line

**Related Requirement**: REQ-14 (Node Selection Dropdowns with Tether ID Grouping)

---

### Task 8.6: Implement NodeAppendix Structured Argument - ALL Mode
**Effort**: L (14 hours)  
**Owner**: Core Engine Developer  
**Depends on**: Task 2.2  
**Parallel with**: Task 8.7

**Acceptance Criteria**:
- [ ] Add "NodeAppendix" argument type to structured arguments config
- [ ] Implement `generate_node_appendix_all(flow)` returning JSON structure
- [ ] Include all nodes with: node_id, role, tether_id, flow_line_id, temporal_position, next_nodes
- [ ] Organize hierarchically by flow line
- [ ] Prepend to agent system prompt as code block with header "## Topology Reference"

**Files Modified**:
- `maccre_core/orchestration/flow_engine.py`
- `maccre_tui/modals/node_config_modal.py` (add NodeAppendix option)

**Test Coverage**:
- Unit test: Generate appendix, verify all nodes included
- Integration test: Agent receives appendix in system prompt

**Related Requirement**: REQ-15 (NodeAppendix Structured Argument - ALL Mode)

---

### Task 8.7: Implement NodeAppendix Structured Argument - Scoped Mode
**Effort**: M (8 hours)  
**Owner**: Core Engine Developer  
**Depends on**: Task 2.2  
**Parallel with**: Task 8.6

**Acceptance Criteria**:
- [ ] Implement `generate_node_appendix_scoped(flow, current_node)`
- [ ] Include only nodes on same flow line as current node
- [ ] Include parent CTRL_SCATTER and child CTRL_MERGE as context boundaries
- [ ] Use same JSON schema as ALL mode (subset of nodes)

**Files Modified**:
- `maccre_core/orchestration/flow_engine.py`

**Test Coverage**:
- Unit test: Scoped appendix includes only lane nodes
- Unit test: Scoped appendix includes scatter and merge boundaries

**Related Requirement**: REQ-16 (NodeAppendix Structured Argument - Scoped Mode)

---

### Task 8.8: Implement Synthesis Agent Execution
**Effort**: L (12 hours)  
**Owner**: Core Engine Developer  
**Depends on**: Task 7.4  
**Parallel with**: Task 8.6

**Acceptance Criteria**:
- [ ] After lanes complete, check if synthesis agent configured
- [ ] Execute synthesis agent with structured arguments containing lane outputs
- [ ] Parse agent response for `ROUTE TO: $TetherID` directive
- [ ] If directive found, route execution to specified node
- [ ] If no directive, proceed with default merge behavior

**Files Modified**:
- `maccre_core/orchestration/local_broker.py`

**Test Coverage**:
- Integration test: Synthesis agent routes to node X.2
- Integration test: Synthesis agent without directive proceeds to merge

**Related Requirement**: REQ-8 (CTRL_MERGE Synthesis Agent Slot)

---

## Phase 9: Validation and Polish (Week 7-8)

### Task 9.1: Implement TopologyValidator Class
**Effort**: L (12 hours)  
**Owner**: Core Engine Developer  
**Depends on**: Task 6.3  
**Enables**: Task 9.2

**Acceptance Criteria**:
- [ ] Create `TopologyValidator` class
- [ ] Implement `validate(root_step)` returning list of error messages
- [ ] Validate scatter→gather pairing
- [ ] Validate gather wait-for references
- [ ] Validate nested scatter depth <= 3
- [ ] Validate total concurrent lanes <= 64

**Files Modified**:
- `maccre_core/orchestration/topology_validator.py` (NEW)

**Test Coverage**:
- Unit test: Valid topology returns empty error list
- Unit test: Orphaned scatter returns error
- Unit test: Invalid tether reference returns error

**Related Requirement**: REQ-24 (Multi-Lane Topology Validation)

---

### Task 9.2: Integrate Validator into Flow Execution
**Effort**: S (4 hours)  
**Owner**: Core Engine Developer  
**Depends on**: Task 9.1  
**Parallel with**: Task 9.3

**Acceptance Criteria**:
- [ ] Call `TopologyValidator.validate()` before flow execution
- [ ] If errors found, display error modal with list of issues
- [ ] Highlight invalid nodes in TopologyVisualizer with red border
- [ ] Block execution until errors resolved

**Files Modified**:
- `maccre_core/orchestration/flow_engine.py`
- `maccre_tui/widgets/topology_visualizer.py`

**Test Coverage**:
- Integration test: Invalid topology blocks execution

**Related Requirement**: REQ-24 (Multi-Lane Topology Validation)

---

### Task 9.3: Implement Telemetry Events
**Effort**: M (6 hours)  
**Owner**: Core Engine Developer  
**Depends on**: Task 7.1  
**Parallel with**: Task 9.2

**Acceptance Criteria**:
- [ ] Add `ScatterExecutionEvent` dataclass
- [ ] Add `GatherWaitEvent` dataclass
- [ ] Add `LaneTopologySnapshot` dataclass
- [ ] Record scatter execution with lane count and nesting depth
- [ ] Record gather wait duration and fallback behavior
- [ ] Write events to telemetry database

**Files Modified**:
- `maccre_core/telemetry/event_schema.py`
- `maccre_core/orchestration/local_broker.py`

**Test Coverage**:
- Integration test: Scatter execution writes telemetry event
- Integration test: Gather timeout writes fallback event

**Related Requirement**: REQ-26 (Telemetry for Multi-Lane Execution)

---

### Task 9.4: Fix Terminal Zoom Button Persistence
**Effort**: M (6 hours)  
**Owner**: TUI Developer  
**Depends on**: Task 4.2  
**Parallel with**: Task 9.3

**Acceptance Criteria**:
- [ ] Update button row CSS to use `position: sticky`
- [ ] Anchor top button row to `top: 0`
- [ ] Anchor bottom button row to `bottom: 0`
- [ ] Test at 50%, 100%, 150% zoom levels
- [ ] Verify buttons remain visible without horizontal scroll

**Files Modified**:
- `maccre_tui/styles/active_flow_sequence.tcss`
- `maccre_tui/widgets/active_flow_sequence.py`

**Test Coverage**:
- UI test: Zoom to 150%, verify buttons visible
- UI test: Scroll content, verify buttons remain anchored

**Related Requirement**: REQ-22 (Terminal Zoom Button Persistence)

---

### Task 9.5: Write User Documentation
**Effort**: M (8 hours)  
**Owner**: Documentation Lead  
**Depends on**: All Phase 8 tasks  
**Parallel with**: Task 9.4

**Acceptance Criteria**:
- [ ] Write "Multi-Lane Authoring Guide" with screenshots
- [ ] Document tether ID format and hierarchy
- [ ] Explain per-lane node insertion workflow
- [ ] Document gather node configuration (timeout, fallback)
- [ ] Add example: 3-lane research → analysis → synthesis flow

**Files Modified**:
- `docs/phase-6-13-user-guide.md` (NEW)

**Test Coverage**:
- Manual verification: Follow guide, reproduce all examples

---

### Task 9.6: Migration Testing
**Effort**: M (6 hours)  
**Owner**: QA Engineer  
**Depends on**: Task 2.3  
**Parallel with**: Task 9.5

**Acceptance Criteria**:
- [ ] Load 5 pre-6.13 flow_history.json files
- [ ] Verify flows load without errors
- [ ] Verify legacy flows execute correctly
- [ ] Verify legacy flows can be re-saved with tether IDs
- [ ] Document any breaking changes

**Files Modified**:
- `tests/integration/test_migration.py`

**Test Coverage**:
- Integration test: Load legacy flow, execute, verify success

**Related Requirement**: REQ-25 (Migration Support for Pre-6.13 Flows)

---

## Critical Path Summary

The **critical path** tasks that must complete sequentially:

1. **Task 1.1** (Enhance FlowStep) — 8 hours
2. **Task 2.1** (TetherIDGenerator) — 6 hours
3. **Task 2.2** (Assign Tether IDs) — 8 hours
4. **Task 4.2** (Multi-Lane Expanded View) — 20 hours
5. **Task 5.2** (Node Double-Click Highlighting) — 8 hours
6. **Task 6.1** (Per-Lane Node Insertion Logic) — 18 hours
7. **Task 7.2** (Gather Timeout and Fallback) — 12 hours

**Total Critical Path Duration**: 80 hours (10 days for 1 developer)

---

## Parallel Development Tracks

After **Week 2** (Task 2.2 complete), development can split into 3 parallel tracks:

### Track A: Core Engine (Developer 1)
- Tasks: 6.1, 6.3, 7.1, 7.2, 7.3, 8.6, 8.7, 8.8, 9.1, 9.3
- **Total**: 110 hours

### Track B: TUI/Visualization (Developer 2)
- Tasks: 4.1, 4.2, 4.3, 4.4, 4.5, 5.1, 5.2, 5.3, 5.4, 9.4
- **Total**: 89 hours

### Track C: Modal/Config UI (Developer 3)
- Tasks: 3.1, 3.2, 3.3, 3.4, 7.4, 8.1, 8.2, 8.3, 8.4, 8.5
- **Total**: 76 hours

This parallelization reduces calendar time from **31 weeks** (sequential) to **8 weeks** (3 developers).

---

## Roadmap Timeline

| Week | Track A (Core) | Track B (TUI) | Track C (Config) |
|------|----------------|---------------|------------------|
| **1** | 1.1, 1.2, 1.3 (18h) | 1.4 (3h) | — |
| **2** | 2.1, 2.2, 2.3 (18h) | — | 3.1, 3.2 (20h) |
| **3** | 6.3 (8h) | 4.1, 4.2 (28h) | 3.3, 3.4 (20h) |
| **4** | 6.1 (18h) | 4.3, 4.4, 4.5 (18h) | 7.4 (6h) |
| **5** | 7.1, 7.2 (28h) | 5.1, 5.2 (14h) | 8.1 (12h) |
| **6** | 7.3, 8.8 (20h) | 5.3, 5.4 (7h) | 8.2, 8.3, 8.4 (17h) |
| **7** | 8.6, 8.7 (22h) | 9.4 (6h) | 8.5 (8h) |
| **8** | 9.1, 9.3 (18h) | — | 9.5, 9.6 (14h) |

---

## Risk Mitigation

### Risk 1: FlowStep Serialization Breaks Existing Flows
**Mitigation**: Task 2.3 (Migration Logic) handles schema version detection and graceful degradation.

### Risk 2: UI Clutter with Many Lanes
**Mitigation**: Tasks 4.4 (Per-Lane Collapse) and 4.5 (Vertical Scaling) ensure UI remains usable at scale.

### Risk 3: Gather Node Deadlock
**Mitigation**: Task 7.2 (Timeout and Fallback) prevents indefinite waits with configurable timeouts.

### Risk 4: Tether ID Collisions
**Mitigation**: Task 2.1 (TetherIDGenerator) uses flow-scoped counters and thread-safe incrementing.

---

## Success Criteria

- [ ] All 46 tasks complete with passing tests
- [ ] 100% of 28 requirements satisfied
- [ ] Zero regressions in existing Phase 6.12 scatter execution
- [ ] User can author 4-lane heterogeneous topology in < 5 minutes (user testing)
- [ ] Gather nodes complete with 99% reliability in production telemetry

---

## Document Metadata

**Feature Name:** phase-6-13-multi-flow-lane  
**Total Tasks:** 46  
**Total Effort:** 248 hours  
**Timeline:** 8 weeks (3 parallel developers)  
**Critical Path:** 80 hours (10 days single developer)  
**Author:** Kiro AI Agent  
**Created:** 2025-01-24  
**Status:** Initial Draft — Awaiting User Review
