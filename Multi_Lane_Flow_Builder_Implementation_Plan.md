# Multi-Lane Flow Builder - Implementation Plan

**Project**: MACCRE Enhanced Multi-Lane Flow Builder UX v2.0  
**Document Version**: 1.0  
**Date**: 2024  
**Status**: Planning Complete - Ready for Implementation

---

## Table of Contents

1. [Executive Summary](#executive-summary)
2. [Architecture Overview](#architecture-overview)
3. [Phase 1: Core Visual Feedback System](#phase-1-core-visual-feedback-system)
4. [Phase 2: Always-Expanded Lane View](#phase-2-always-expanded-lane-view)
5. [Phase 3: Position Marker System](#phase-3-position-marker-system)
6. [Phase 4: Enhanced Tether ID System](#phase-4-enhanced-tether-id-system)
7. [Phase 5: Configured Node History](#phase-5-configured-node-history)
8. [Phase 6: Undo/Redo System](#phase-6-undoredo-system)
9. [Phase 7: Batch Configuration](#phase-7-batch-configuration)
10. [Phase 8: Color Palette System](#phase-8-color-palette-system)
11. [Phase 9: Concurrency Management](#phase-9-concurrency-management)
12. [Phase 10: Layout Reorganization](#phase-10-layout-reorganization)
13. [Testing Strategy](#testing-strategy)
14. [Deployment Checklist](#deployment-checklist)

---

## Executive Summary

This implementation plan transforms the MACCRE TUI's Active Flow Sequence from a basic linear view into a comprehensive 2D multi-lane canvas with intelligent visual feedback, spatial position selection, and advanced configuration management.

**Key Objectives:**
1. Make node insertion spatially intuitive with visual position markers
2. Remove scatter collapse/expand - lanes always visible
3. Implement user-friendly tether ID naming convention
4. Add node configuration history with 50-entry rolling database
5. Provide undo/redo for all flow operations
6. Enable batch configuration across similar nodes
7. Implement 5 theme palettes + dynamic routing colors
8. Support nested scatters with concurrency management

**Estimated Timeline**: 8-12 weeks (depending on team size)

**Dependencies**:
- Python 3.12+
- Textual 0.47+
- SQLite3
- Existing MACCRE codebase

---

## Architecture Overview

### Modified Components

```
maccre_tui/
├── nexus_plex.py          # Main TUI (MAJOR changes)
├── nexus_plex.css         # Styling (MAJOR changes)
├── widgets/
│   ├── topology_visualizer.py  # (Minor updates)
│   └── position_marker.py      # NEW widget
└── modals/
    ├── batch_config_modal.py   # NEW modal
    └── theme_selector_modal.py # NEW modal

maccre_core/
├── orchestration/
│   ├── flow_engine.py      # Concurrency probing
│   └── tether_generator.py # Enhanced naming (NEW)
└── database/
    └── node_history.py     # NEW database manager

__DATACENTER/
└── node_history.db        # NEW database

config/
└── color_palettes.json    # NEW palette definitions
```

### Data Flow

```
User Action → UI State → Position Markers → Add Button State
                ↓
         FlowStep Creation
                ↓
    Tether ID Generation (Enhanced)
                ↓
         Save to History DB
                ↓
    Push to Undo Stack → Refresh UI → Update Topology
```

---

## Phase 1: Core Visual Feedback System

**Goal**: Implement catalog selection states with visual feedback

**Duration**: 1-2 weeks

**Priority**: HIGH (Foundation for all other phases)

### Tasks

#### Task 1.1: Add Selection State Tracking

**File**: `maccre_tui/nexus_plex.py`

**Changes**:
```python
# Add to __init__ method
self._catalog_selected_node: str | None = None
self._catalog_selection_type: str | None = None  # 'macronode', 'agent', 'control'
self._selected_positions: list[tuple[int, int | None, str]] = []  # [(step_idx, lane_idx, position_type)]
self._ui_state: str = "idle"  # 'idle', 'node_selected', 'position_selected'
```

**New Methods**:
```python
def _set_catalog_selection(self, node_name: str, node_type: str) -> None:
    """User selected node from catalog"""
    self._catalog_selected_node = node_name
    self._catalog_selection_type = node_type
    self._ui_state = "node_selected"
    self._update_catalog_border_style("selected")
    self._refresh_active_flow_sequence()  # Will show markers
    self._update_add_button_state()

def _set_position_selection(self, step_idx: int, lane_idx: int | None, position_type: str) -> None:
    """User clicked position marker"""
    position = (step_idx, lane_idx, position_type)
    if position in self._selected_positions:
        self._selected_positions.remove(position)
    else:
        self._selected_positions.append(position)
    
    if self._selected_positions:
        self._ui_state = "position_selected"
    else:
        self._ui_state = "node_selected"
    
    self._refresh_active_flow_sequence()  # Update marker highlights
    self._update_add_button_state()

def _clear_selection_state(self) -> None:
    """Reset to idle state"""
    self._catalog_selected_node = None
    self._catalog_selection_type = None
    self._selected_positions.clear()
    self._ui_state = "idle"
    self._update_catalog_border_style("normal")
    self._refresh_active_flow_sequence()  # Hide markers
    self._update_add_button_state()

def _update_catalog_border_style(self, state: str) -> None:
    """Update catalog container border based on state"""
    try:
        # Find the node catalog container widget
        # Implementation depends on current widget structure
        pass
    except Exception:
        pass

def _update_add_button_state(self) -> None:
    """Enable/disable Add button based on selection state"""
    try:
        # Update button for each node type (MacroNode, Agent, Control)
        for btn_id in ["#btn-add-macro", "#btn-add-agent", "#btn-add-special"]:
            try:
                add_btn = self.query_one(btn_id, Button)
                
                if self._ui_state == "idle":
                    add_btn.disabled = True
                    add_btn.tooltip = "Select a node and position(s) to add"
                    add_btn.remove_class("active")
                
                elif self._ui_state == "node_selected":
                    add_btn.disabled = True
                    add_btn.tooltip = "Click position marker(s) ⊕ to place node"
                    add_btn.remove_class("active")
                
                elif self._ui_state == "position_selected":
                    add_btn.disabled = False
                    count = len(self._selected_positions)
                    if count > 1:
                        add_btn.label = f"+ Add to {count} Positions"
                    else:
                        add_btn.label = "+ Add"
                    add_btn.tooltip = f"Add {self._catalog_selected_node} to {count} position(s)"
                    add_btn.add_class("active")
            except:
                pass
    except Exception:
        pass
```

#### Task 1.2: Update CSS for Visual States

**File**: `maccre_tui/nexus_plex.css`

**Add**:
```css
/* Node Catalog Border States */
.node-catalog-pane {
    border: solid #30363d;
    transition: border-color 0.3s ease, box-shadow 0.3s ease;
}

.node-catalog-pane.catalog-selected {
    border: solid #00d9ff;
    box-shadow: 0 0 10px #00d9ff;
    animation: catalog-pulse 1s ease-in-out infinite;
}

@keyframes catalog-pulse {
    0%, 100% { box-shadow: 0 0 10px #00d9ff; }
    50% { box-shadow: 0 0 20px #00d9ff; }
}

/* Add Button States */
.flow-add-btn {
    transition: border-color 0.3s ease, box-shadow 0.3s ease;
}

.flow-add-btn.active {
    border: solid #00ff00;
    background: #00ff00 20%;
    box-shadow: 0 0 15px #00ff00;
    animation: button-glow 1s ease-in-out infinite;
}

@keyframes button-glow {
    0%, 100% { box-shadow: 0 0 15px #00ff00; }
    50% { box-shadow: 0 0 25px #00ff00; }
}
```

#### Task 1.3: Hook Selection Events

**Modify existing catalog selection handlers**:
```python
@on(Select.Changed, "#macro-select")
def on_macro_selected(self, event: Select.Changed) -> None:
    if event.value and event.value != Select.BLANK:
        self._set_catalog_selection(str(event.value), "macronode")

@on(Select.Changed, "#agent-select")
def on_agent_selected(self, event: Select.Changed) -> None:
    if event.value and event.value != Select.BLANK:
        self._set_catalog_selection(str(event.value), "agent")

@on(Select.Changed, "#special-select")
def on_special_selected(self, event: Select.Changed) -> None:
    if event.value and event.value != Select.BLANK:
        self._set_catalog_selection(str(event.value), "control")
```

#### Task 1.4: Implement Click-Outside Detection

**Add global click handler**:
```python
def on_click(self, event: events.Click) -> None:
    """Detect clicks outside catalog to clear selection"""
    if self._ui_state == "idle":
        return
    
    # Check if click is within catalog pane or active flow sequence
    clicked_widget = event.widget
    
    # Walk up parent tree to find if we're in catalog or flow area
    current = clicked_widget
    in_catalog_area = False
    in_flow_area = False
    
    while current:
        if hasattr(current, 'id'):
            if 'catalog' in str(current.id).lower():
                in_catalog_area = True
                break
            if 'flow' in str(current.id).lower() or 'active' in str(current.id).lower():
                in_flow_area = True
                break
        current = current.parent if hasattr(current, 'parent') else None
    
    # Clear selection if clicked outside both areas
    if not in_catalog_area and not in_flow_area:
        self._clear_selection_state()
```

### Testing - Phase 1

**Manual Tests**:
1. Select MacroNode from dropdown → Verify catalog border glows cyan
2. Click outside catalog → Verify selection clears, border returns to normal
3. Select Agent → Verify Add button shows greyed state with tooltip
4. Multiple selection/deselection cycles → Verify no memory leaks or stale state

**Acceptance Criteria**:
- [ ] Catalog border glows cyan when any node selected
- [ ] Add button stays disabled when only catalog node selected
- [ ] Clicking outside catalog clears all selection state
- [ ] CSS animations smooth and not janky
- [ ] No console errors or exceptions

---

## Phase 2: Always-Expanded Lane View

**Goal**: Remove expand/collapse toggle, make scatter lanes always visible

**Duration**: 1-2 weeks

**Priority**: HIGH (Required for position markers in lanes)

### Tasks

#### Task 2.1: Remove Expand/Collapse Logic

**File**: `maccre_tui/nexus_plex.py`

**Remove**:
- `on_scatter_toggle_button()` method
- All references to `_ui_expanded` attribute on FlowStep
- Expand/collapse button from scatter node rendering

**Modify `_render_scatter_lanes()`**:
```python
def _render_scatter_lanes(self, scatter_step: Any, idx: int, uid: str) -> Vertical:
    """Render CTRL_SCATTER with always-visible lanes"""
    name = scatter_step.macronode_name
    
    # Top controls (no expand button)
    btn_del = Button("✕", id=f"fdelete-{idx}-{uid}", classes="flow-del-btn")
    btn_left = Button("◀", id=f"fmoveleft-{idx}-{uid}", classes="flow-move-btn")
    btn_right = Button("▶", id=f"fmoveright-{idx}-{uid}", classes="flow-move-btn")
    
    # Scatter node button with lane count
    lane_count = len(scatter_step.children) if hasattr(scatter_step, "children") else 0
    scatter_label = f"{name} [{lane_count} lanes]"
    btn_scatter = Button(
        scatter_label,
        variant="warning",
        id=f"anode-{idx}-{uid}",
        classes="active-node-btn scatter-node-btn"
    )
    
    top_row = Horizontal(btn_del, classes="flow-node-top")
    middle_row = Horizontal(btn_left, btn_scatter, btn_right, classes="flow-node-bottom")
    
    widgets = [top_row, middle_row]
    
    # ALWAYS render lanes if they exist
    if hasattr(scatter_step, "children") and scatter_step.children:
        lanes_view = self._render_lanes_expanded(scatter_step.children, idx, uid)
        widgets.append(lanes_view)
    
    scatter_container = Vertical(*widgets, classes="flow-node-wrapper scatter-wrapper")
    return scatter_container
```

#### Task 2.2: Update CSS for Dynamic Height

**File**: `maccre_tui/nexus_plex.css`

**Ensure these styles**:
```css
#active-flow-sequence {
    width: 1fr;
    height: auto;
    min-height: 10;
    max-height: 70vh;  /* 70% of viewport height */
    padding: 1 1;
    overflow-x: scroll;
    overflow-y: auto;
    border: solid #30363d;
    background: #0d1117;
}

.scatter-wrapper {
    height: auto;
    width: auto;
    border: thick #e0af68;
    background: #1a1b26;
    padding: 1;
    margin: 0 1;
}

.scatter-lanes-container {
    height: auto;
    width: auto;
    border: solid #7aa2f7;
    background: #16161e;
    padding: 1 2;
    margin-top: 1;
    overflow: visible;
}

.lane-row {
    height: auto;
    min-height: 3;
    margin-bottom: 1;
    padding: 0 1;
    background: #1a1b26;
    border: solid #7aa2f7;
}
```

#### Task 2.3: Handle Deeply Nested Scatters

**Add visual indentation for nested scatters**:
```python
def _render_lanes_expanded(self, lanes: list[list[Any]], parent_idx: int, uid: str, nesting_level: int = 0) -> Vertical:
    """Render expanded view with nesting level support"""
    max_length = max((len(lane) for lane in lanes), default=0) if lanes else 0
    
    lane_rows = []
    for lane_idx, lane in enumerate(lanes):
        # Lane label with nesting indentation
        first_step = lane[0] if lane else None
        if first_step and hasattr(first_step, "tether_id"):
            lane_label = f"{'  ' * nesting_level}Lane {lane_idx + 1} [{first_step.tether_id}]"
        else:
            lane_label = f"{'  ' * nesting_level}Lane {lane_idx + 1}"
        
        label_widget = Label(lane_label, classes="lane-label")
        
        # Build lane node widgets
        lane_widgets = []
        for step_idx, step in enumerate(lane):
            node_name = step.macronode_name if hasattr(step, "macronode_name") else str(step)
            
            # Check if this is a nested scatter
            if node_name.startswith("CTRL_SCATTER") and hasattr(step, "children") and step.children:
                # Render nested scatter recursively with increased nesting level
                nested_scatter = self._render_scatter_lanes(step, f"{parent_idx}-{lane_idx}-{step_idx}", f"{uid}-nested", nesting_level + 1)
                lane_widgets.append(nested_scatter)
            else:
                # Regular node button
                node_btn = Button(
                    node_name,
                    id=f"lane-node-{parent_idx}-{lane_idx}-{step_idx}-{uid}",
                    classes="lane-node-btn",
                    variant="default"
                )
                lane_widgets.append(node_btn)
            
            # Arrow between nodes
            if step_idx < len(lane) - 1:
                lane_widgets.append(Static("→", classes="lane-arrow"))
        
        # Add fillers for alignment
        filler_count = max_length - len(lane)
        for _ in range(filler_count):
            if lane:
                lane_widgets.append(Static("→", classes="lane-arrow dim"))
            filler_btn = Button("···", classes="lane-filler-btn", disabled=True)
            lane_widgets.append(filler_btn)
        
        # Lane row
        lane_nodes = Horizontal(*lane_widgets, classes="lane-nodes-row")
        lane_row = Horizontal(label_widget, lane_nodes, classes="lane-row")
        lane_rows.append(lane_row)
    
    lanes_container = Vertical(*lane_rows, classes="scatter-lanes-container")
    return lanes_container
```

### Testing - Phase 2

**Manual Tests**:
1. Create scatter with 4 lanes → Verify all lanes visible immediately
2. Add nested scatter in lane → Verify nested lanes render with indentation
3. Scroll vertically when many lanes → Verify smooth scrolling
4. Check performance with 8 lanes * 5 nodes each → Should remain responsive

**Acceptance Criteria**:
- [ ] No expand/collapse button on scatter nodes
- [ ] All lanes visible immediately on scatter node
- [ ] Active Flow Sequence scrolls vertically when lanes exceed viewport
- [ ] Nested scatters render correctly with visual indentation
- [ ] No layout glitches or overflow issues

---

## Phase 3: Position Marker System

**Goal**: Implement ⊕ circle-plus markers at valid insertion points

**Duration**: 2-3 weeks

**Priority**: HIGH (Core interaction mechanism)

### Tasks

#### Task 3.1: Create PositionMarker Component

**File**: `maccre_tui/nexus_plex.py` (add as nested class or separate widget)

**Simple inline implementation**:
```python
# In _refresh_active_flow_sequence(), create markers as Static widgets
def _create_position_marker(self, marker_id: str, visible: bool = True) -> Static:
    """Create a position marker widget"""
    marker = Static("⊕", classes="position-marker")
    marker.marker_id = marker_id  # Custom attribute
    
    if visible:
        marker.add_class("visible")
    
    # Check if this marker is selected
    if self._is_marker_selected(marker_id):
        marker.add_class("marker-selected")
    else:
        marker.add_class("marker-available")
    
    return marker

def _is_marker_selected(self, marker_id: str) -> bool:
    """Check if marker is in selected positions"""
    # Parse marker_id and check against self._selected_positions
    position_info = self._parse_marker_id(marker_id)
    position_tuple = (position_info["step_idx"], position_info.get("lane_idx"), position_info["position"])
    return position_tuple in self._selected_positions
```

#### Task 3.2: Add CSS for Position Markers

**File**: `maccre_tui/nexus_plex.css`

```css
.position-marker {
    width: 3;
    height: 1;
    content-align: center middle;
    text-style: bold;
    display: none;
    padding: 0;
    margin: 0 1;
}

.position-marker.visible {
    display: block;
}

.position-marker.marker-available {
    color: #7aa2f7;
    background: transparent;
}

.position-marker.marker-available:hover {
    color: #bb9af7;
    background: #3b4252;
    animation: marker-pulse 0.5s ease-in-out;
}

.position-marker.marker-selected {
    color: #00ff00;
    background: #1e3a1e;
    box-shadow: 0 0 5px #00ff00;
}

@keyframes marker-pulse {
    0%, 100% { transform: scale(1); }
    50% { transform: scale(1.3); }
}
```

#### Task 3.3: Generate Marker Positions

```python
def _get_valid_marker_positions(self) -> list[dict]:
    """Calculate all valid position markers"""
    if self._ui_state == "idle":
        return []
    
    positions = []
    
    # Start marker (before first node)
    positions.append({
        "id": "main-before-0",
        "step_idx": -1,
        "lane_idx": None,
        "position": "before"
    })
    
    # Main flow positions
    for i, step in enumerate(self.active_flow_steps):
        # After each main node
        positions.append({
            "id": f"main-after-{i}",
            "step_idx": i,
            "lane_idx": None,
            "position": "after"
        })
        
        # Lane positions (if scatter node)
        if hasattr(step, "children") and step.children:
            for lane_idx, lane in enumerate(step.children):
                # Lane start
                positions.append({
                    "id": f"lane-{i}-{lane_idx}-start",
                    "step_idx": i,
                    "lane_idx": lane_idx,
                    "position": "start"
                })
                
                # After each node in lane
                for node_idx in range(len(lane)):
                    positions.append({
                        "id": f"lane-{i}-{lane_idx}-after-{node_idx}",
                        "step_idx": i,
                        "lane_idx": lane_idx,
                        "node_idx": node_idx,
                        "position": "after"
                    })
    
    return positions

def _parse_marker_id(self, marker_id: str) -> dict:
    """Parse marker ID to position dict"""
    parts = marker_id.split("-")
    
    if parts[0] == "main":
        position = parts[1]  # "before" or "after"
        step_idx = int(parts[2]) if position == "after" else -1
        return {
            "step_idx": step_idx,
            "lane_idx": None,
            "position": position
        }
    elif parts[0] == "lane":
        # lane-{step_idx}-{lane_idx}-{position}-{node_idx?}
        return {
            "step_idx": int(parts[1]),
            "lane_idx": int(parts[2]),
            "position": parts[3],
            "node_idx": int(parts[4]) if len(parts) > 4 and parts[4].isdigit() else None
        }
```

#### Task 3.4: Integrate Markers into Flow Rendering

**Modify `_refresh_active_flow_sequence()`**:
```python
def _refresh_active_flow_sequence(self) -> None:
    """Rebuild flow with position markers"""
    container = self.query_one("#active-flow-sequence", VerticalScroll)
    container.remove_children()
    
    flow_widgets = []
    show_markers = (self._ui_state != "idle")
    
    # Start marker
    if show_markers:
        marker = self._create_position_marker("main-before-0", visible=True)
        flow_widgets.append(marker)
    
    # Nodes with markers
    for i, step in enumerate(self.active_flow_steps):
        uid = f"node-{i}"
        
        # Render node (scatter or regular)
        if step.macronode_name.startswith("CTRL_SCATTER"):
            node_widget = self._render_scatter_lanes(step, i, uid)
        else:
            node_widget = self._render_regular_node(step, i, uid)
        
        flow_widgets.append(node_widget)
        
        # After marker
        if show_markers:
            marker = self._create_position_marker(f"main-after-{i}", visible=True)
            flow_widgets.append(marker)
        
        # Arrow
        if i < len(self.active_flow_steps) - 1:
            flow_widgets.append(Static("→", classes="flow-arrow"))
    
    # Mount all
    horizontal = Horizontal(*flow_widgets, classes="flow-sequence-row")
    container.mount(horizontal)
```

**Add markers inside lanes** in `_render_lanes_expanded()`:
```python
# Within lane rendering loop, add markers between nodes
for step_idx, step in enumerate(lane):
    # Start marker if first node
    if step_idx == 0 and show_markers:
        marker = self._create_position_marker(
            f"lane-{parent_idx}-{lane_idx}-start",
            visible=True
        )
        lane_widgets.append(marker)
    
    # Node button
    node_btn = Button(...)
    lane_widgets.append(node_btn)
    
    # After marker
    if show_markers:
        marker = self._create_position_marker(
            f"lane-{parent_idx}-{lane_idx}-after-{step_idx}",
            visible=True
        )
        lane_widgets.append(marker)
    
    # Arrow
    if step_idx < len(lane) - 1:
        lane_widgets.append(Static("→", classes="lane-arrow"))
```

#### Task 3.5: Handle Marker Clicks

```python
@on(Static.Pressed)
def on_marker_clicked(self, event: Static.Pressed) -> None:
    """Handle position marker clicks"""
    widget = event.widget
    
    # Check if this is a position marker
    if not hasattr(widget, 'marker_id'):
        return
    
    marker_id = widget.marker_id
    position_info = self._parse_marker_id(marker_id)
    
    # Toggle selection
    position_tuple = (
        position_info["step_idx"],
        position_info.get("lane_idx"),
        position_info["position"]
    )
    
    if position_tuple in self._selected_positions:
        self._selected_positions.remove(position_tuple)
    else:
        self._selected_positions.append(position_tuple)
    
    # Update UI state
    if self._selected_positions:
        self._ui_state = "position_selected"
    else:
        self._ui_state = "node_selected"
    
    self._refresh_active_flow_sequence()
    self._update_add_button_state()
```

#### Task 3.6: Implement Multi-Position Add

**Modify add button handlers**:
```python
@on(Button.Pressed, "#btn-add-macro")  # And similar for agent, control
def add_macro_to_flow(self) -> None:
    """Add MacroNode to selected positions"""
    if self._ui_state != "position_selected" or not self._catalog_selected_node:
        return
    
    from maccre_core.orchestration.flow_engine import FlowStep
    
    # Create node instance
    node_name = self._catalog_selected_node
    
    # Sort positions by step index (insert from back to front to maintain indices)
    sorted_positions = sorted(
        self._selected_positions,
        key=lambda p: (p[0], p[1] if p[1] is not None else -1),
        reverse=True
    )
    
    # Insert at each position
    for step_idx, lane_idx, position_type in sorted_positions:
        new_step = FlowStep(macronode_name=node_name)
        
        if lane_idx is None:
            # Main flow insertion
            if position_type == "before" and step_idx == -1:
                self.active_flow_steps.insert(0, new_step)
            elif position_type == "after":
                self.active_flow_steps.insert(step_idx + 1, new_step)
        else:
            # Lane insertion
            parent_step = self.active_flow_steps[step_idx]
            if hasattr(parent_step, "children") and parent_step.children:
                lane = parent_step.children[lane_idx]
                if position_type == "start":
                    lane.insert(0, new_step)
                elif position_type == "after":
                    node_idx = self._get_node_idx_from_position(position_type)
                    lane.insert(node_idx + 1, new_step)
    
    # Log action
    count = len(sorted_positions)
    self.write_agent_log(f"[green]Added {node_name} to {count} position(s)[/green]")
    
    # Clear selection and refresh
    self._clear_selection_state()
    self._refresh_active_flow_sequence()
    self._update_topology_visualizer()
```

### Testing - Phase 3

**Manual Tests**:
1. Select catalog node → Verify markers appear at all valid positions
2. Click single marker → Verify it glows green, Add button activates
3. Click multiple markers → Verify all glow green, button shows "Add to N Positions"
4. Click Add → Verify nodes inserted at all selected positions
5. Test lane markers → Verify markers appear inside scatter lanes
6. Deselect catalog → Verify all markers disappear

**Unit Tests**:
```python
# tests/unit/test_position_markers.py
def test_marker_id_parsing():
    """Test marker ID parsing logic"""
    nexus = NexusPlex()
    
    # Main flow marker
    result = nexus._parse_marker_id("main-after-3")
    assert result["step_idx"] == 3
    assert result["lane_idx"] is None
    
    # Lane marker
    result = nexus._parse_marker_id("lane-2-1-after-0")
    assert result["step_idx"] == 2
    assert result["lane_idx"] == 1
    assert result["node_idx"] == 0
```

**Acceptance Criteria**:
- [ ] Markers appear when catalog node selected
- [ ] Markers disappear when selection cleared
- [ ] Clicking marker toggles selection (visual feedback)
- [ ] Multiple markers can be selected
- [ ] Add button correctly adds to all selected positions
- [ ] Lane markers work correctly for nested scatters

---

## Phase 4: Enhanced Tether ID System

**Goal**: Implement semantic, user-friendly tether IDs

**Duration**: 2-3 weeks

**Priority**: MEDIUM (Enhances UX but not blocking)

### Tasks

#### Task 4.1: Create TetherIDGenerator with Naming

**File**: `maccre_core/orchestration/tether_generator.py` (NEW)

```python
import hashlib
import string
from typing import Optional

class EnhancedTetherIDGenerator:
    """Generate user-friendly tether IDs with semantic naming"""
    
    def __init__(self, session_name: str = ""):
        self.session_name = self._sanitize_name(session_name)
        self._id_counter = {}  # Track IDs per parent to avoid collisions
    
    def _sanitize_name(self, name: str) -> str:
        """Sanitize name for use in tether ID"""
        # Remove special chars, keep alphanumeric and dots
        allowed = string.ascii_letters + string.digits + "._"
        sanitized = "".join(c for c in name if c in allowed)
        # Limit length
        return sanitized[:20] if sanitized else "Flow"
    
    def _calculate_entropy_hash(self, *components: str) -> str:
        """Generate short entropy suffix based on components"""
        combined = "|".join(components)
        hash_bytes = hashlib.sha256(combined.encode()).digest()
        
        # Convert to base36 (0-9, a-z)
        base36_chars = string.digits + string.ascii_lowercase
        hash_int = int.from_bytes(hash_bytes[:3], 'big')  # Use first 3 bytes
        
        result = ""
        while hash_int > 0:
            result = base36_chars[hash_int % 36] + result
            hash_int //= 36
        
        # Scale length based on input entropy
        entropy = len(set(combined))  # Unique characters as entropy measure
        if entropy > 20:
            return result[:4]  # High entropy, short hash
        elif entropy > 10:
            return result[:5]
        else:
            return result[:6]  # Low entropy, longer hash
    
    def generate_root_id(self, macronode_name: Optional[str] = None) -> str:
        """Generate root-level tether ID"""
        if not self.session_name:
            # Fallback to legacy system
            return "X"
        
        if macronode_name:
            sanitized_macro = self._sanitize_name(macronode_name)
            return f"{self.session_name}.{sanitized_macro}"
        
        return self.session_name
    
    def generate_lane_ids(
        self,
        parent_tether: str,
        lane_count: int,
        lane_names: Optional[list[str]] = None,
        macronode_name: str = ""
    ) -> list[str]:
        """Generate tether IDs for scatter lanes"""
        lane_ids = []
        
        # Sanitize macronode name for component
        macro_component = self._sanitize_name(macronode_name) if macronode_name else "Scatter"
        
        for i in range(lane_count):
            # Use custom lane name if provided
            if lane_names and i < len(lane_names) and lane_names[i]:
                lane_component = self._sanitize_name(lane_names[i])
            else:
                lane_component = f"L{i + 1}"
            
            # Generate entropy hash
            hash_suffix = self._calculate_entropy_hash(
                parent_tether,
                macro_component,
                lane_component,
                str(i)
            )
            
            # Construct tether ID
            tether_id = f"{parent_tether}.{macro_component}.{lane_component}.{hash_suffix}"
            lane_ids.append(tether_id)
        
        return lane_ids
    
    def parse_tether_depth(self, tether_id: str) -> int:
        """Calculate nesting depth from tether ID"""
        return tether_id.count(".")
```

#### Task 4.2: Integrate into FlowStep Configuration

**Modify node configuration handler** in `nexus_plex.py`:
```python
def handle_config(result: dict | None):
    if result:
        # ... existing config handling ...
        
        # Enhanced tether ID generation for scatter nodes
        if node.macronode_name.startswith("CTRL_SCATTER") and "scatter_agents" in node.config:
            scatter_agents = node.config.get("scatter_agents", [])
            lane_names = node.config.get("lane_names", [])  # NEW: User-provided lane names
            
            if scatter_agents and not node.children:
                # Generate semantic tether IDs
                parent_tether = node.tether_id or self.session_name
                
                tether_gen = EnhancedTetherIDGenerator(self.session_name)
                child_tethers = tether_gen.generate_lane_ids(
                    parent_tether,
                    len(scatter_agents),
                    lane_names=lane_names,
                    macronode_name=node.macronode_name
                )
                
                # Initialize lane structure
                node.children = [[] for _ in scatter_agents]
                node.lane_metadata = {}
                
                for i, (agent_name, child_tether) in enumerate(zip(scatter_agents, child_tethers)):
                    node.lane_metadata[i] = {
                        "agent_name": agent_name,
                        "custom_name": lane_names[i] if i < len(lane_names) else f"L{i+1}",
                        "tether_id": child_tether,
                    }
                
                self.write_agent_log(
                    f"[cyan]CTRL_SCATTER configured: {', '.join(child_tethers)}[/cyan]"
                )
```

#### Task 4.3: Add Lane Naming UI to NodeConfigModal

**File**: `maccre_tui/modals/node_config_modal.py` (or inline in nexus_plex.py)

**Add to scatter configuration section**:
```python
# In NodeConfigModal compose method
if self.node_name.startswith("CTRL_SCATTER"):
    yield Label("Lane Custom Names (Optional)")
    
    for i in range(8):  # Max 8 lanes
        yield Horizontal(
            Label(f"Lane {i+1}:"),
            Input(
                placeholder=f"Default: L{i+1}",
                id=f"lane-name-{i}",
                classes="lane-name-input"
            )
        )
```

**On save, collect lane names**:
```python
def save_config(self):
    result = {}
    # ... existing config collection ...
    
    # Collect lane names for scatter nodes
    if self.node_name.startswith("CTRL_SCATTER"):
        lane_names = []
        for i in range(8):
            try:
                inp = self.query_one(f"#lane-name-{i}", Input)
                lane_names.append(inp.value.strip())
            except:
                pass
        result["lane_names"] = lane_names
    
    self.dismiss(result)
```

### Testing - Phase 4

**Manual Tests**:
1. Configure scatter node with custom lane names → Verify tethers use names
2. Leave lane names blank → Verify default L1, L2, etc. used
3. Check tether ID length with long names → Should be truncated appropriately
4. Configure nested scatter → Verify hierarchical tether structure

**Unit Tests**:
```python
# tests/unit/test_enhanced_tether_ids.py
def test_semantic_tether_generation():
    gen = EnhancedTetherIDGenerator("PersonaGen")
    
    # Generate lane IDs with custom names
    lane_ids = gen.generate_lane_ids(
        "PersonaGen.SCATTER",
        4,
        lane_names=["Analyst", "Critic", "Creative", "Editor"],
        macronode_name="CTRL_SCATTER"
    )
    
    assert len(lane_ids) == 4
    assert "Analyst" in lane_ids[0]
    assert "Critic" in lane_ids[1]
    # Verify entropy hash is 4-6 chars
    for lid in lane_ids:
        parts = lid.split(".")
        assert 4 <= len(parts[-1]) <= 6
```

**Acceptance Criteria**:
- [ ] Tether IDs include session name as prefix
- [ ] Lane names appear in tether IDs when provided
- [ ] Default lane names (L1, L2) used when custom names not provided
- [ ] Entropy hash scaling works (4-6 chars based on name uniqueness)
- [ ] Nested scatter tethers maintain hierarchy

---

## Phase 5: Configured Node History

**Goal**: Implement 50-entry rolling database for node configurations

**Duration**: 2-3 weeks

**Priority**: MEDIUM (Quality of life improvement)

### Tasks

#### Task 5.1: Create Database Schema

**File**: `maccre_core/database/node_history.py` (NEW)

```python
import sqlite3
import json
from pathlib import Path
from datetime import datetime
from typing import Optional

class NodeHistoryManager:
    """Manage configured node history database"""
    
    def __init__(self, db_path: Optional[Path] = None):
        if db_path is None:
            from maccre_core.utils.path_helpers import get_maccre_root
            db_path = get_maccre_root() / "__DATACENTER" / "node_history.db"
        
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_database()
    
    def _init_database(self):
        """Create tables if not exist"""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS configured_nodes (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                    node_name TEXT NOT NULL,
                    node_type TEXT NOT NULL,
                    serialized_config TEXT NOT NULL,
                    config_summary TEXT,
                    session_name TEXT,
                    project_name TEXT
                )
            """)
            
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_timestamp 
                ON configured_nodes(timestamp DESC)
            """)
            
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_node_type 
                ON configured_nodes(node_type)
            """)
    
    def add_configured_node(
        self,
        node_name: str,
        node_type: str,
        config_dict: dict,
        session_name: str = "",
        project_name: str = ""
    ):
        """Add node to history, maintain 50-entry limit"""
        # Generate summary
        summary = self._generate_summary(node_name, node_type, config_dict)
        
        with sqlite3.connect(self.db_path) as conn:
            # Check count
            count = conn.execute("SELECT COUNT(*) FROM configured_nodes").fetchone()[0]
            
            # Delete oldest if at limit
            if count >= 50:
                conn.execute("""
                    DELETE FROM configured_nodes
                    WHERE id = (SELECT id FROM configured_nodes ORDER BY timestamp ASC LIMIT 1)
                """)
            
            # Insert new entry
            conn.execute("""
                INSERT INTO configured_nodes 
                (node_name, node_type, serialized_config, config_summary, session_name, project_name)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (
                node_name,
                node_type,
                json.dumps(config_dict),
                summary,
                session_name,
                project_name
            ))
    
    def get_recent_nodes(self, limit: int = 50) -> list[dict]:
        """Get most recent configured nodes"""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute("""
                SELECT * FROM configured_nodes
                ORDER BY timestamp DESC
                LIMIT ?
            """, (limit,))
            
            return [dict(row) for row in cursor.fetchall()]
    
    def get_node_by_id(self, node_id: int) -> Optional[dict]:
        """Get specific node configuration"""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute("""
                SELECT * FROM configured_nodes WHERE id = ?
            """, (node_id,))
            
            row = cursor.fetchone()
            return dict(row) if row else None
    
    def _generate_summary(self, node_name: str, node_type: str, config: dict) -> str:
        """Generate human-readable summary"""
        if node_type == "agent":
            tools_count = len(config.get("agent_tools_overrides", {}))
            payload_mode = config.get("payload_mode", "Unified Ledger")
            has_instructions = bool(config.get("custom_instructions"))
            return f"{node_name} (Payload: {payload_mode}, Tools: {tools_count}, Instructions: {'Yes' if has_instructions else 'No'})"
        
        elif node_type == "macronode":
            # Count internal nodes if available
            internal_count = len(config.get("topology_rows", []))
            lane_count = len(config.get("scatter_agents", []))
            if lane_count:
                return f"{node_name} ({internal_count} nodes, {lane_count} lanes)"
            return f"{node_name} ({internal_count} nodes)"
        
        elif node_type == "control":
            # Extract key config params
            key_params = []
            for key in ["timeout", "max_iterations", "scatter_agents"]:
                if key in config:
                    key_params.append(f"{key}={config[key]}")
            return f"{node_name} ({', '.join(key_params)})" if key_params else node_name
        
        return node_name
```

#### Task 5.2: Add History UI Section to Node Catalog

**File**: `maccre_tui/nexus_plex.py`

**Add to compose method**:
```python
# After Node Catalog dropdowns
yield Label("▼ Configured Node History", classes="history-section-header")
yield ListView(id="node-history-list", classes="node-history-list")
```

**Add refresh method**:
```python
def _refresh_node_history_list(self):
    """Populate node history list"""
    try:
        from maccre_core.database.node_history import NodeHistoryManager
        history_mgr = NodeHistoryManager()
        
        recent_nodes = history_mgr.get_recent_nodes(limit=50)
        
        history_list = self.query_one("#node-history-list", ListView)
        history_list.clear()
        
        for entry in recent_nodes:
            item = ListItem(
                Label(entry["config_summary"]),
                id=f"history-{entry['id']}",
                classes="history-item"
            )
            history_list.append(item)
    
    except Exception as e:
        self.write_agent_log(f"[red]Failed to load node history: {e}[/red]")
```

**Handle history item clicks**:
```python
@on(ListView.Selected, "#node-history-list")
def on_history_item_selected(self, event: ListView.Selected) -> None:
    """User selected node from history"""
    try:
        # Extract history ID from item ID
        item_id = event.item.id
        history_id = int(item_id.replace("history-", ""))
        
        # Load node config from database
        from maccre_core.database.node_history import NodeHistoryManager
        history_mgr = NodeHistoryManager()
        entry = history_mgr.get_node_by_id(history_id)
        
        if entry:
            # Deserialize config
            config_dict = json.loads(entry["serialized_config"])
            
            # Set catalog selection
            self._set_catalog_selection(entry["node_name"], entry["node_type"])
            
            # Store config for later use when node is added
            self._pending_history_config = config_dict
            
            self.write_agent_log(
                f"[cyan]Selected from history: {entry['config_summary']}[/cyan]"
            )
    
    except Exception as e:
        self.write_agent_log(f"[red]Failed to load history item: {e}[/red]")
```

#### Task 5.3: Hook Save Events

**Modify node configuration save handler**:
```python
def handle_config(result: dict | None):
    if result:
        # ... existing config handling ...
        
        # Save to history database
        try:
            from maccre_core.database.node_history import NodeHistoryManager
            history_mgr = NodeHistoryManager()
            
            # Determine node type
            if node.macronode_name.startswith("CTRL_"):
                node_type = "control"
            elif hasattr(node, "topology_rows") or hasattr(node, "config") and "topology_rows" in node.config:
                node_type = "macronode"
            else:
                node_type = "agent"
            
            # Save to database
            history_mgr.add_configured_node(
                node_name=node.macronode_name,
                node_type=node_type,
                config_dict=node.to_dict(),
                session_name=self.active_session_name,
                project_name=self.active_project
            )
            
            # Refresh history UI
            self._refresh_node_history_list()
        
        except Exception as e:
            logger.error(f"Failed to save node to history: {e}")
```

### Testing - Phase 5

**Manual Tests**:
1. Configure and save a node → Verify it appears in history list
2. Save 51 nodes → Verify oldest is removed (FIFO)
3. Click history item → Verify catalog selection and position markers appear
4. Add from history → Verify configuration is applied to new node

**Database Tests**:
```python
# tests/unit/test_node_history_db.py
def test_rolling_50_limit():
    """Test that database maintains 50-entry limit"""
    import tempfile
    from pathlib import Path
    
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test_history.db"
        mgr = NodeHistoryManager(db_path)
        
        # Add 60 nodes
        for i in range(60):
            mgr.add_configured_node(
                f"TestNode{i}",
                "agent",
                {"index": i}
            )
        
        # Should only have 50
        recent = mgr.get_recent_nodes(100)
        assert len(recent) == 50
        
        # Oldest should be node 10 (0-9 deleted)
        oldest = recent[-1]
        assert "TestNode10" in oldest["node_name"] or oldest["id"] >= 11
```

**Acceptance Criteria**:
- [ ] History section appears in Node Catalog
- [ ] Configured nodes automatically added to history
- [ ] Database maintains 50-entry limit (FIFO)
- [ ] Clicking history item enables catalog selection
- [ ] Summary text accurately describes node configuration

---

## Phase 6: Undo/Redo System

**Goal**: Implement undo/redo stack for flow modifications

**Duration**: 1-2 weeks

**Priority**: MEDIUM (Nice to have, not blocking)

### Tasks

#### Task 6.1: Create Action Stack

**File**: `maccre_tui/nexus_plex.py`

**Add to __init__**:
```python
from dataclasses import dataclass
from datetime import datetime
from copy import deepcopy

@dataclass
class FlowAction:
    """Represents a flow modification action"""
    action_type: str  # 'add_node', 'delete_node', 'move_node', 'configure_node'
    timestamp: datetime
    before_state: list  # Serialized FlowSteps
    after_state: list   # Serialized FlowSteps
    metadata: dict      # Extra info (node name, position, etc.)

# In __init__
self._undo_stack: list[FlowAction] = []
self._redo_stack: list[FlowAction] = []
self._max_undo_stack_size = 100
```

**Add action recording method**:
```python
def _record_action(self, action_type: str, metadata: dict):
    """Record action for undo/redo"""
    from maccre_core.orchestration.flow_engine import FlowStep
    
    # Serialize current state
    after_state = [step.to_dict() for step in self.active_flow_steps]
    
    # Get before state from last action or empty
    if self._undo_stack:
        before_state = self._undo_stack[-1].after_state
    else:
        before_state = []
    
    action = FlowAction(
        action_type=action_type,
        timestamp=datetime.now(),
        before_state=before_state,
        after_state=after_state,
        metadata=metadata
    )
    
    # Add to undo stack
    self._undo_stack.append(action)
    
    # Limit stack size
    if len(self._undo_stack) > self._max_undo_stack_size:
        self._undo_stack.pop(0)
    
    # Clear redo stack (new action invalidates redo)
    self._redo_stack.clear()
    
    # Update UI
    self._update_undo_redo_buttons()
```

#### Task 6.2: Implement Undo/Redo Logic

```python
def undo(self):
    """Undo last action"""
    if not self._undo_stack:
        self.write_agent_log("[yellow]Nothing to undo[/yellow]")
        return
    
    from maccre_core.orchestration.flow_engine import FlowStep
    
    action = self._undo_stack.pop()
    
    # Restore before state
    self.active_flow_steps = [
        FlowStep.from_dict(step_dict) for step_dict in action.before_state
    ]
    
    # Add to redo stack
    self._redo_stack.append(action)
    
    # Refresh UI
    self._refresh_active_flow_sequence()
    self._update_topology_visualizer()
    self._update_undo_redo_buttons()
    
    # Log
    self.write_agent_log(
        f"[cyan]Undid: {action.action_type} ({action.metadata.get('description', '')})[/cyan]"
    )

def redo(self):
    """Redo last undone action"""
    if not self._redo_stack:
        self.write_agent_log("[yellow]Nothing to redo[/yellow]")
        return
    
    from maccre_core.orchestration.flow_engine import FlowStep
    
    action = self._redo_stack.pop()
    
    # Restore after state
    self.active_flow_steps = [
        FlowStep.from_dict(step_dict) for step_dict in action.after_state
    ]
    
    # Add back to undo stack
    self._undo_stack.append(action)
    
    # Refresh UI
    self._refresh_active_flow_sequence()
    self._update_topology_visualizer()
    self._update_undo_redo_buttons()
    
    # Log
    self.write_agent_log(
        f"[cyan]Redid: {action.action_type} ({action.metadata.get('description', '')})[/cyan]"
    )

def _update_undo_redo_buttons(self):
    """Enable/disable undo/redo buttons based on stack state"""
    try:
        undo_btn = self.query_one("#btn-undo", Button)
        redo_btn = self.query_one("#btn-redo", Button)
        
        undo_btn.disabled = len(self._undo_stack) == 0
        redo_btn.disabled = len(self._redo_stack) == 0
    except:
        pass
```

#### Task 6.3: Hook into Modification Actions

**Modify node addition**:
```python
def add_macro_to_flow(self) -> None:
    # ... existing add logic ...
    
    # Record action
    self._record_action(
        "add_node",
        {"description": f"Added {node_name}", "node_name": node_name}
    )
```

**Modify node deletion**:
```python
def action_delete_flow_node(self, event: Button.Pressed) -> None:
    # ... existing delete logic ...
    
    # Record action
    self._record_action(
        "delete_node",
        {"description": f"Deleted {deleted_node.macronode_name}", "node_name": deleted_node.macronode_name}
    )
```

**Modify node movement**:
```python
def action_move_flow_node(self, event: Button.Pressed) -> None:
    # ... existing move logic ...
    
    # Record action
    self._record_action(
        "move_node",
        {"description": f"Moved node {action}", "action": action}
    )
```

**Modify node configuration**:
```python
def handle_config(result: dict | None):
    if result:
        # ... existing config logic ...
        
        # Record action
        self._record_action(
            "configure_node",
            {"description": f"Configured {node.macronode_name}", "node_name": node.macronode_name}
        )
```

#### Task 6.4: Add Keyboard Bindings

```python
BINDINGS = [
    # ... existing bindings ...
    ("ctrl+z", "undo", "Undo"),
    ("ctrl+y", "redo", "Redo"),
    ("ctrl+shift+z", "redo", "Redo"),
]

def action_undo(self) -> None:
    """Handle Ctrl+Z"""
    self.undo()

def action_redo(self) -> None:
    """Handle Ctrl+Y or Ctrl+Shift+Z"""
    self.redo()
```

#### Task 6.5: Add Undo/Redo Buttons to UI

**In compose method, add toolbar buttons**:
```python
yield Horizontal(
    Button("↶ Undo", id="btn-undo", variant="default", disabled=True),
    Button("↷ Redo", id="btn-redo", variant="default", disabled=True),
    classes="undo-redo-toolbar"
)

@on(Button.Pressed, "#btn-undo")
def on_undo_button(self) -> None:
    self.undo()

@on(Button.Pressed, "#btn-redo")
def on_redo_button(self) -> None:
    self.redo()
```

### Testing - Phase 6

**Manual Tests**:
1. Add node → Press Ctrl+Z → Verify node removed
2. Delete node → Undo → Verify node restored
3. Undo 3 times → Redo 2 times → Verify correct state
4. Make change after undo → Verify redo stack clears
5. Perform 101 actions → Verify oldest is discarded

**Unit Tests**:
```python
# tests/unit/test_undo_redo.py
def test_undo_redo_cycle():
    """Test undo/redo preserves flow state"""
    # Would need to mock NexusPlex or extract logic
    pass
```

**Acceptance Criteria**:
- [ ] Ctrl+Z undoes last action
- [ ] Ctrl+Y or Ctrl+Shift+Z redoes last undone action
- [ ] Undo/Redo buttons enabled/disabled appropriately
- [ ] Redo stack clears after new action
- [ ] Stack limit (100) enforced
- [ ] All action types (add/delete/move/configure) work with undo/redo

---

## Phase 7: Batch Configuration

**Goal**: Apply configuration to multiple similar nodes

**Duration**: 1-2 weeks

**Priority**: LOW (Advanced feature)

### Tasks

#### Task 7.1: Create Batch Config Modal

**File**: `maccre_tui/modals/batch_config_modal.py` (NEW or inline)

```python
from textual.app import ComposeResult
from textual.containers import Container, Vertical, Horizontal
from textual.widgets import Label, Button, Checkbox
from textual.screen import ModalScreen

class BatchConfigModal(ModalScreen[list[int]]):
    """Modal to select similar nodes for batch configuration"""
    
    def __init__(self, current_node_name: str, matching_nodes: list[dict], **kwargs):
        super().__init__(**kwargs)
        self.current_node_name = current_node_name
        self.matching_nodes = matching_nodes  # [{"index": i, "name": str, "path": str}]
    
    def compose(self) -> ComposeResult:
        with Container(classes="dialog", id="batch-config-dialog"):
            yield Label("Apply Configuration to Similar Nodes", classes="dialog-title")
            yield Label(f"Current Node: {self.current_node_name}")
            yield Label(f"Found {len(self.matching_nodes)} matching node(s)")
            
            with Horizontal(classes="batch-select-controls"):
                yield Button("☐ Select All", id="btn-select-all", variant="default")
                yield Button("☑ Deselect All", id="btn-deselect-all", variant="default")
            
            with Vertical(id="batch-node-list", classes="batch-node-list"):
                for node_info in self.matching_nodes:
                    yield Horizontal(
                        Checkbox(value=False, id=f"check-{node_info['index']}"),
                        Label(f"{node_info['name']} ({node_info['path']})"),
                        classes="batch-node-item"
                    )
            
            with Horizontal(classes="dialog-buttons"):
                yield Button("Cancel", id="btn-cancel", variant="default")
                yield Button("Apply to Selected (0)", id="btn-apply", variant="success")
    
    @on(Button.Pressed, "#btn-select-all")
    def select_all(self) -> None:
        """Select all checkboxes"""
        for node_info in self.matching_nodes:
            try:
                checkbox = self.query_one(f"#check-{node_info['index']}", Checkbox)
                checkbox.value = True
            except:
                pass
        self._update_apply_button()
    
    @on(Button.Pressed, "#btn-deselect-all")
    def deselect_all(self) -> None:
        """Deselect all checkboxes"""
        for node_info in self.matching_nodes:
            try:
                checkbox = self.query_one(f"#check-{node_info['index']}", Checkbox)
                checkbox.value = False
            except:
                pass
        self._update_apply_button()
    
    @on(Checkbox.Changed)
    def on_checkbox_changed(self) -> None:
        """Update apply button when selection changes"""
        self._update_apply_button()
    
    def _update_apply_button(self) -> None:
        """Update apply button label with selected count"""
        selected_count = sum(
            1 for node_info in self.matching_nodes
            if self.query_one(f"#check-{node_info['index']}", Checkbox).value
        )
        
        btn_apply = self.query_one("#btn-apply", Button)
        btn_apply.label = f"Apply to Selected ({selected_count})"
        btn_apply.disabled = (selected_count == 0)
    
    @on(Button.Pressed, "#btn-cancel")
    def cancel(self) -> None:
        self.dismiss([])
    
    @on(Button.Pressed, "#btn-apply")
    def apply(self) -> None:
        """Return list of selected node indices"""
        selected_indices = [
            node_info["index"]
            for node_info in self.matching_nodes
            if self.query_one(f"#check-{node_info['index']}", Checkbox).value
        ]
        self.dismiss(selected_indices)
```

#### Task 7.2: Add Batch Config Button to NodeConfigModal

**Modify NodeConfigModal footer**:
```python
# In NodeConfigModal compose method, add button
with Horizontal(classes="dialog-buttons"):
    yield Button("⚙ Apply to Similar...", id="btn-batch-config", variant="default")
    yield Button("Cancel", id="btn-cancel", variant="default")
    yield Button("Save", id="btn-save", variant="success")
```

**Handle batch config button**:
```python
@on(Button.Pressed, "#btn-batch-config")
def open_batch_config(self) -> None:
    """Open batch configuration sub-modal"""
    # Find matching nodes in parent app
    app = self.app
    matching_nodes = app._find_matching_nodes(
        self.node_name,
        current_node_index=getattr(self, '_current_node_index', None)
    )
    
    if not matching_nodes:
        app.notify("No other nodes of this type found", severity="warning")
        return
    
    def handle_batch_selection(selected_indices: list[int]):
        if selected_indices:
            # Store for later use when Save is clicked
            self._batch_selected_indices = selected_indices
            app.notify(f"Will apply to {len(selected_indices)} node(s) on save", severity="information")
    
    app.push_screen(BatchConfigModal(self.node_name, matching_nodes), handle_batch_selection)
```

#### Task 7.3: Implement Find Matching Nodes

**In nexus_plex.py**:
```python
def _find_matching_nodes(self, node_name: str, current_node_index: int | None = None) -> list[dict]:
    """Find all nodes with same name/type as given node"""
    matching = []
    
    def search_nodes(steps: list, path: str = "Main Flow"):
        for i, step in enumerate(steps):
            # Skip current node being configured
            if current_node_index is not None and i == current_node_index and path == "Main Flow":
                continue
            
            # Check for match
            if step.macronode_name == node_name:
                matching.append({
                    "index": i,
                    "name": step.macronode_name,
                    "path": path,
                    "step": step  # Keep reference for later
                })
            
            # Search in lanes
            if hasattr(step, "children") and step.children:
                for lane_idx, lane in enumerate(step.children):
                    lane_path = f"{path} → Lane {lane_idx + 1}"
                    for node_idx, lane_step in enumerate(lane):
                        if lane_step.macronode_name == node_name:
                            matching.append({
                                "index": f"{i}-{lane_idx}-{node_idx}",
                                "name": lane_step.macronode_name,
                                "path": lane_path,
                                "step": lane_step
                            })
    
    search_nodes(self.active_flow_steps)
    return matching
```

#### Task 7.4: Apply Batch Configuration

**Modify save handler in NodeConfigModal**:
```python
def save(self) -> None:
    """Save configuration and apply to batch if selected"""
    # ... collect config as usual ...
    
    result = {
        "name": self.node_name,
        "config": collected_config,
        # ... other fields ...
    }
    
    # Add batch indices if any selected
    if hasattr(self, '_batch_selected_indices'):
        result["batch_apply_to"] = self._batch_selected_indices
    
    self.dismiss(result)
```

**Handle in parent**:
```python
def handle_config(result: dict | None):
    if result:
        # Apply to primary node
        # ... existing config logic ...
        
        # Apply to batch nodes if specified
        if "batch_apply_to" in result:
            batch_indices = result["batch_apply_to"]
            self._apply_config_to_batch(
                batch_indices,
                result["config"]
            )

def _apply_config_to_batch(self, indices: list, config: dict):
    """Apply configuration to multiple nodes"""
    applied_count = 0
    
    for idx in indices:
        try:
            if isinstance(idx, str) and "-" in idx:
                # Lane node: "step_idx-lane_idx-node_idx"
                parts = idx.split("-")
                step_idx, lane_idx, node_idx = map(int, parts)
                target_step = self.active_flow_steps[step_idx].children[lane_idx][node_idx]
            else:
                # Main flow node
                target_step = self.active_flow_steps[int(idx)]
            
            # Apply config (merge, don't overwrite unique fields like tether_id)
            if "payload_mode" in config:
                target_step.payload_mode = config["payload_mode"]
            if "custom_instructions" in config:
                target_step.custom_instructions = config["custom_instructions"]
            if "agent_tools_overrides" in config:
                target_step.agent_tools_overrides.update(config["agent_tools_overrides"])
            
            applied_count += 1
        
        except Exception as e:
            logger.error(f"Failed to apply batch config to index {idx}: {e}")
    
    self.write_agent_log(f"[green]Applied configuration to {applied_count} node(s)[/green]")
    
    # Refresh UI
    self._refresh_active_flow_sequence()
```

### Testing - Phase 7

**Manual Tests**:
1. Configure node → Click "Apply to Similar" → Verify matching nodes listed
2. Select multiple nodes → Click Apply → Save → Verify config applied to all
3. Configure control node → Verify only control nodes shown in batch list
4. No matching nodes → Verify appropriate message shown

**Acceptance Criteria**:
- [ ] Batch config modal lists all matching nodes
- [ ] Select All/Deselect All buttons work
- [ ] Apply button shows selected count
- [ ] Configuration applied to all selected nodes on save
- [ ] Unique fields (tether_id) not overwritten
- [ ] Undo works for batch configuration

---

## Phase 8: Color Palette System

**Goal**: Implement 5 theme palettes + dynamic routing colors

**Duration**: 2-3 weeks

**Priority**: LOW (Visual polish)

### Tasks

#### Task 8.1: Define Color Palettes

**File**: `config/color_palettes.json` (NEW)

```json
{
  "palettes": {
    "tokyo_night": {
      "name": "Tokyo Night",
      "background": "#0d1117",
      "surface": "#1a1b26",
      "panel": "#24283b",
      "text_primary": "#c0caf5",
      "text_muted": "#666666",
      "primary": "#7aa2f7",
      "accent": "#bb9af7",
      "success": "#9ece6a",
      "warning": "#e0af68",
      "error": "#f7768e"
    },
    "solarized_light": {
      "name": "Solarized Light",
      "background": "#fdf6e3",
      "surface": "#eee8d5",
      "panel": "#ebe7da",
      "text_primary": "#586e75",
      "text_muted": "#93a1a1",
      "primary": "#268bd2",
      "accent": "#6c71c4",
      "success": "#859900",
      "warning": "#b58900",
      "error": "#dc322f"
    },
    "dracula": {
      "name": "Dracula",
      "background": "#282a36",
      "surface": "#44475a",
      "panel": "#50516a",
      "text_primary": "#f8f8f2",
      "text_muted": "#6272a4",
      "primary": "#8be9fd",
      "accent": "#bd93f9",
      "success": "#50fa7b",
      "warning": "#ffb86c",
      "error": "#ff5555"
    },
    "gruvbox_dark": {
      "name": "Gruvbox Dark",
      "background": "#282828",
      "surface": "#3c3836",
      "panel": "#504945",
      "text_primary": "#ebdbb2",
      "text_muted": "#928374",
      "primary": "#83a598",
      "accent": "#d3869b",
      "success": "#b8bb26",
      "warning": "#fabd2f",
      "error": "#fb4934"
    },
    "nord": {
      "name": "Nord",
      "background": "#2e3440",
      "surface": "#3b4252",
      "panel": "#434c5e",
      "text_primary": "#eceff4",
      "text_muted": "#4c566a",
      "primary": "#88c0d0",
      "accent": "#b48ead",
      "success": "#a3be8c",
      "warning": "#ebcb8b",
      "error": "#bf616a"
    }
  },
  "routing_colors": [
    "#FF4444", "#FF8800", "#FFDD00", "#88FF00",
    "#00FF44", "#00FF88", "#00FFDD", "#0088FF",
    "#4400FF", "#8800FF", "#DD00FF", "#FF0088",
    "#FF6B6B", "#FFA500", "#FFD700", "#00CED1",
    "#9370DB", "#FF69B4"
  ]
}
```

#### Task 8.2: Create Theme Selector Modal

**File**: `maccre_tui/modals/theme_selector_modal.py` (NEW)

```python
from textual.app import ComposeResult
from textual.containers import Container, Vertical
from textual.widgets import Label, Button, RadioSet, RadioButton
from textual.screen import ModalScreen

class ThemeSelectorModal(ModalScreen[str]):
    """Modal to select UI theme"""
    
    def __init__(self, current_theme: str, palettes: dict, **kwargs):
        super().__init__(**kwargs)
        self.current_theme = current_theme
        self.palettes = palettes
    
    def compose(self) -> ComposeResult:
        with Container(classes="dialog"):
            yield Label("Appearance Settings", classes="dialog-title")
            
            with RadioSet(id="theme-radio-set"):
                for palette_id, palette in self.palettes.items():
                    yield RadioButton(
                        palette["name"],
                        value=(palette_id == self.current_theme),
                        id=f"theme-{palette_id}"
                    )
            
            with Horizontal(classes="dialog-buttons"):
                yield Button("Cancel", id="btn-cancel", variant="default")
                yield Button("Apply", id="btn-apply", variant="success")
    
    @on(Button.Pressed, "#btn-cancel")
    def cancel(self) -> None:
        self.dismiss(None)
    
    @on(Button.Pressed, "#btn-apply")
    def apply(self) -> None:
        """Return selected theme ID"""
        radio_set = self.query_one("#theme-radio-set", RadioSet)
        selected = radio_set.pressed_button
        
        if selected:
            theme_id = selected.id.replace("theme-", "")
            self.dismiss(theme_id)
        else:
            self.dismiss(None)
```

#### Task 8.3: Implement Theme Loading

**In nexus_plex.py**:
```python
def __init__(self):
    # ... existing init ...
    self._load_theme_palettes()
    self._load_user_theme_preference()

def _load_theme_palettes(self):
    """Load color palettes from config"""
    import json
    from pathlib import Path
    
    palette_path = Path(__file__).parent.parent / "config" / "color_palettes.json"
    
    try:
        with open(palette_path) as f:
            palette_data = json.load(f)
            self._palettes = palette_data["palettes"]
            self._routing_colors = palette_data["routing_colors"]
    except Exception as e:
        logger.error(f"Failed to load palettes: {e}")
        # Fallback to tokyo_night
        self._palettes = {"tokyo_night": {...}}  # Hardcoded fallback
        self._routing_colors = ["#FF4444", ...]

def _load_user_theme_preference(self):
    """Load user's selected theme from preferences"""
    import json
    from pathlib import Path
    
    pref_path = Path.home() / ".maccre" / "user_preferences.json"
    
    try:
        if pref_path.exists():
            with open(pref_path) as f:
                prefs = json.load(f)
                self._current_theme = prefs.get("theme", "tokyo_night")
        else:
            self._current_theme = "tokyo_night"
    except:
        self._current_theme = "tokyo_night"
    
    self._apply_theme(self._current_theme)

def _apply_theme(self, theme_id: str):
    """Apply theme colors to UI"""
    if theme_id not in self._palettes:
        theme_id = "tokyo_night"
    
    palette = self._palettes[theme_id]
    
    # Update CSS variables (if Textual supports, otherwise hardcode CSS files per theme)
    # For now, generate dynamic CSS
    css_overrides = f"""
    Screen {{
        background: {palette['background']};
    }}
    Container {{
        background: {palette['surface']};
        color: {palette['text_primary']};
    }}
    Button {{
        background: {palette['panel']};
        border: solid {palette['primary']};
    }}
    /* ... etc for all components ... */
    """
    
    # Apply CSS (Textual's approach depends on version)
    # May need to reload app with new CSS file

def _save_theme_preference(self, theme_id: str):
    """Save theme preference to disk"""
    import json
    from pathlib import Path
    
    pref_path = Path.home() / ".maccre" / "user_preferences.json"
    pref_path.parent.mkdir(exist_ok=True)
    
    try:
        prefs = {}
        if pref_path.exists():
            with open(pref_path) as f:
                prefs = json.load(f)
        
        prefs["theme"] = theme_id
        
        with open(pref_path, "w") as f:
            json.dump(prefs, f, indent=2)
    except Exception as e:
        logger.error(f"Failed to save theme preference: {e}")
```

#### Task 8.4: Add Routing Color Assignment

```python
def _assign_lane_color(self, lane_index: int, parent_scatter_index: int) -> str:
    """Assign routing color to lane"""
    # Rotate through routing colors with offset per scatter node
    color_index = (parent_scatter_index * 7 + lane_index) % len(self._routing_colors)
    color = self._routing_colors[color_index]
    
    # Ensure contrast against current theme background
    return self._ensure_contrast(color, self._palettes[self._current_theme]["background"])

def _ensure_contrast(self, color: str, bg_color: str, min_ratio: float = 4.5) -> str:
    """Ensure routing color has sufficient contrast"""
    # Calculate luminance and contrast ratio
    # If insufficient, try next color in routing palette
    # (Detailed implementation of WCAG contrast algorithm)
    pass  # Implement using algorithm from plan
```

#### Task 8.5: Add Theme Toggle to UI

**Add settings button to toolbar**:
```python
# In compose method
yield Button("🎨 Theme", id="btn-theme-settings", variant="default")

@on(Button.Pressed, "#btn-theme-settings")
def open_theme_settings(self) -> None:
    """Open theme selector modal"""
    def handle_theme_selection(theme_id: str | None):
        if theme_id:
            self._apply_theme(theme_id)
            self._save_theme_preference(theme_id)
            self.notify(f"Theme changed to {self._palettes[theme_id]['name']}", severity="information")
    
    self.push_screen(
        ThemeSelectorModal(self._current_theme, self._palettes),
        handle_theme_selection
    )
```

### Testing - Phase 8

**Manual Tests**:
1. Open theme selector → Verify all 5 themes listed
2. Switch to Solarized Light → Verify colors update
3. Restart TUI → Verify theme persists
4. Create scatter with 8 lanes → Verify unique routing colors assigned
5. Switch theme → Verify routing colors maintain contrast

**Acceptance Criteria**:
- [ ] 5 theme palettes available
- [ ] Theme selection persists across sessions
- [ ] Routing colors assigned to lanes automatically
- [ ] Contrast validation ensures visibility
- [ ] Theme changes apply without restart

---

## Phase 9: Concurrency Management

**Goal**: Probe system capabilities and manage execution channels

**Duration**: 2-3 weeks

**Priority**: HIGH (Performance critical)

### Tasks

#### Task 9.1: Create System Capability Prober

**File**: `maccre_core/orchestration/system_probe.py` (NEW)

```python
import requests
from typing import Optional

class SystemCapabilityProbe:
    """Probe system for model availability and concurrency limits"""
    
    @staticmethod
    def probe_local_models() -> dict:
        """Check for local model availability"""
        result = {
            "ollama": False,
            "vllm": False,
            "max_local_channels": 0
        }
        
        # Check Ollama
        try:
            response = requests.get("http://localhost:11434/api/tags", timeout=2)
            if response.status_code == 200:
                result["ollama"] = True
                # Estimate concurrency based on available models
                models = response.json().get("models", [])
                result["max_local_channels"] = min(len(models) * 2, 16)
        except:
            pass
        
        # Check VLLM (if applicable)
        # ... similar check ...
        
        # Check GPU memory (if CUDA available)
        try:
            import torch
            if torch.cuda.is_available():
                gpu_mem_gb = torch.cuda.get_device_properties(0).total_memory / 1e9
                # Estimate channels based on memory (rough heuristic)
                result["max_local_channels"] = max(
                    result["max_local_channels"],
                    int(gpu_mem_gb / 8)  # Assume 8GB per concurrent model
                )
        except:
            pass
        
        return result
    
    @staticmethod
    def determine_max_concurrency() -> int:
        """Determine maximum concurrent execution channels"""
        local_info = SystemCapabilityProbe.probe_local_models()
        
        if local_info["max_local_channels"] > 0:
            # Use local capacity
            return local_info["max_local_channels"]
        else:
            # Default to cloud-safe limit
            return 8
```

#### Task 9.2: Integrate Probing into Flow Engine

**File**: `maccre_core/orchestration/flow_engine.py`

**Modify FlowRunner**:
```python
class FlowRunner:
    def __init__(self, ...):
        # ... existing init ...
        self._max_concurrency = self._probe_system_concurrency()
        self._active_channels = []  # Track active execution threads
    
    def _probe_system_concurrency(self) -> int:
        """Probe system and determine concurrency limit"""
        from maccre_core.orchestration.system_probe import SystemCapabilityProbe
        return SystemCapabilityProbe.determine_max_concurrency()
    
    def _execute_scatter_with_concurrency(self, scatter_step: FlowStep, ...):
        """Execute scatter lanes with concurrency management"""
        scatter_agents = scatter_step.config.get("scatter_agents", [])
        
        # Create task queue
        tasks = [
            {"lane_idx": i, "agent": agent}
            for i, agent in enumerate(scatter_agents)
        ]
        
        # Execute with channel pool
        results = []
        with concurrent.futures.ThreadPoolExecutor(max_workers=self._max_concurrency) as executor:
            futures = []
            
            for task in tasks:
                future = executor.submit(
                    self._execute_lane,
                    scatter_step,
                    task["lane_idx"],
                    ...
                )
                futures.append((task["lane_idx"], future))
            
            # Collect results as they complete
            for lane_idx, future in futures:
                result = future.result()
                results.append((lane_idx, result))
        
        return results
```

#### Task 9.3: Implement Dependency Weight Calculation

```python
def _calculate_dependency_weight(self, tether_id: str, topology: list[FlowStep]) -> int:
    """Calculate how many downstream nodes depend on this tether"""
    weight = 0
    
    def count_dependencies(steps: list[FlowStep]):
        nonlocal weight
        for step in steps:
            # Check if step waits for this tether
            wait_for = step.config.get("wait_for", "")
            if tether_id in wait_for:
                weight += 1
            
            # Recurse into lanes
            if hasattr(step, "children") and step.children:
                for lane in step.children:
                    count_dependencies(lane)
    
    count_dependencies(topology)
    return weight

def _prioritize_lanes_by_weight(self, scatter_step: FlowStep, topology: list[FlowStep]) -> list[int]:
    """Return lane indices sorted by dependency weight (highest first)"""
    lane_weights = []
    
    for lane_idx, lane in enumerate(scatter_step.children):
        if lane:
            first_step = lane[0]
            tether_id = first_step.tether_id if hasattr(first_step, "tether_id") else ""
            weight = self._calculate_dependency_weight(tether_id, topology)
            lane_weights.append((lane_idx, weight))
    
    # Sort by weight descending
    lane_weights.sort(key=lambda x: x[1], reverse=True)
    return [lane_idx for lane_idx, _ in lane_weights]
```

#### Task 9.4: Display Concurrency Info in UI

**Add to TUI startup**:
```python
def on_mount(self) -> None:
    # ... existing mount logic ...
    
    # Probe and display concurrency info
    from maccre_core.orchestration.system_probe import SystemCapabilityProbe
    probe_result = SystemCapabilityProbe.probe_local_models()
    
    if probe_result["ollama"]:
        max_concurrent = probe_result["max_local_channels"]
        self.write_nexus_log(
            f"[green]Local models detected (Ollama)[/green] - Max concurrency: {max_concurrent}"
        )
    else:
        self.write_nexus_log(
            "[yellow]No local models detected - Using cloud-safe concurrency limit: 8[/yellow]"
        )
```

### Testing - Phase 9

**Manual Tests**:
1. Run TUI with Ollama running → Verify local model detection message
2. Run TUI without Ollama → Verify cloud-safe limit message
3. Execute scatter with 10 lanes on 8-channel limit → Verify queuing behavior
4. Check logs for dependency weight calculations

**Unit Tests**:
```python
# tests/unit/test_concurrency_probe.py
def test_ollama_detection():
    """Test Ollama detection (requires mock)"""
    # Mock requests.get to return Ollama response
    pass

def test_dependency_weight_calculation():
    """Test weight calculation logic"""
    # Create test topology with dependencies
    pass
```

**Acceptance Criteria**:
- [ ] System probes for local models on startup
- [ ] Concurrency limit determined automatically
- [ ] Scatter execution respects channel pool
- [ ] High-weight lanes prioritized
- [ ] UI displays detected concurrency info

---

## Phase 10: Layout Reorganization

**Goal**: Move flow controls above Active Flow Sequence

**Duration**: 1 week

**Priority**: HIGH (Fixes Add button cutoff issue)

### Tasks

#### Task 10.1: Reorganize Compose Method

**File**: `maccre_tui/nexus_plex.py`

**Current layout (approximate)**:
```
- Node Catalog
- Topology Visualizer
- Active Flow Sequence
- Flow Control Buttons (below)
```

**New layout**:
```
- Node Catalog
- Flow Control Buttons (above Active Flow Sequence)
- Active Flow Sequence (larger)
- Context/Payload Input
- (Topology Visualizer removed or modal)
```

**Modify compose method**:
```python
def compose(self) -> ComposeResult:
    # ... existing header/navigation ...
    
    # Node Catalog Section
    with Vertical(id="node-catalog-section"):
        yield Label("Node Catalog", classes="section-title")
        # ... macro/agent/control tabs ...
        yield Label("▼ Configured Node History")
        yield ListView(id="node-history-list")
    
    # Flow Controls Toolbar (MOVED HERE - above flow sequence)
    with Horizontal(id="flow-controls-toolbar", classes="flow-toolbar"):
        yield Button("Remove Last Node", id="btn-remove-last", variant="error")
        yield Button("Clear Flow", id="btn-clear-flow", variant="error")
        yield Button("↶ Undo", id="btn-undo", variant="default", disabled=True)
        yield Button("↷ Redo", id="btn-redo", variant="default", disabled=True)
        yield Input(placeholder="Name Session...", id="session-name-input")
    
    with Horizontal(id="flow-controls-toolbar-2", classes="flow-toolbar"):
        yield Button("Launch Flow", id="btn-launch-flow", variant="success")
        yield Button("Stop Flow", id="btn-stop-flow", variant="error")
        yield Button("Resume", id="btn-resume-flow", variant="default")
        yield Button("Rewind", id="btn-rewind-flow", variant="default")
        yield Button("Create Payload", id="btn-create-payload", variant="primary")
        yield Button("Chat Studio", id="btn-chat-studio", variant="default")
        yield Button("File Cabinet", id="btn-file-cabinet", variant="default")
        yield Button("🎨 Theme", id="btn-theme-settings", variant="default")
    
    # Active Flow Sequence (EXPANDED HEIGHT)
    with VerticalScroll(id="active-flow-sequence", classes="flow-sequence-container"):
        yield Label("Active Flow Sequence")
        # ... flow nodes ...
    
    # Context/Payload Input
    with Vertical(id="context-input-section"):
        yield Label("Context/Payload")
        yield TextArea(placeholder="Inject context to flow...", id="context-input")
```

#### Task 10.2: Update CSS Layout

**File**: `maccre_tui/nexus_plex.css`

```css
/* Reorganized layout */
#node-catalog-section {
    height: 25vh;
    overflow-y: auto;
    border: solid #30363d;
    padding: 1;
}

#flow-controls-toolbar,
#flow-controls-toolbar-2 {
    height: auto;
    padding: 1;
    border: solid #30363d;
    background: #1a1b26;
}

#active-flow-sequence {
    height: 60vh;  /* Increased from previous */
    max-height: 70vh;
    overflow-x: scroll;
    overflow-y: auto;
    border: solid #30363d;
    background: #0d1117;
}

#context-input-section {
    height: 10vh;
    border: solid #30363d;
    padding: 1;
}
```

#### Task 10.3: Remove/Hide Topology Visualizer

**Option 1: Complete removal**:
```python
# Comment out or remove TopologyVisualizer from compose
# yield TopologyVisualizer(id="topology-viz")
```

**Option 2: Move to modal**:
```python
# Add button to open topology in modal
yield Button("📊 Topology View", id="btn-topology-modal", variant="default")

@on(Button.Pressed, "#btn-topology-modal")
def open_topology_modal(self) -> None:
    """Open topology visualizer in modal overlay"""
    class TopologyModal(ModalScreen):
        def compose(self):
            with Container(classes="dialog topology-dialog"):
                yield TopologyVisualizer(id="modal-topology-viz")
                yield Button("Close", id="btn-close")
        
        @on(Button.Pressed, "#btn-close")
        def close(self):
            self.dismiss()
    
    self.push_screen(TopologyModal())
```

#### Task 10.4: Test Layout Responsiveness

**Verify**:
- All buttons visible without scrolling
- Add button fully visible (no 25% cutoff)
- Active Flow Sequence has sufficient height
- Resize terminal window → verify layout adapts

### Testing - Phase 10

**Manual Tests**:
1. Open TUI → Verify buttons are above flow sequence
2. Add many nodes → Verify Add button remains visible
3. Resize terminal to small size → Verify no critical UI elements hidden
4. Expand scatter with 8 lanes → Verify scrolling works

**Acceptance Criteria**:
- [ ] Flow control buttons above Active Flow Sequence
- [ ] Add button 100% visible (no cutoff)
- [ ] Active Flow Sequence height increased
- [ ] Topology Visualizer removed or moved to modal
- [ ] Layout responsive to terminal size changes

---

## Testing Strategy

### Unit Tests

**Coverage Goals**: 70%+ for new code

**Test Files**:
- `tests/unit/test_position_markers.py`
- `tests/unit/test_enhanced_tether_ids.py`
- `tests/unit/test_node_history_db.py`
- `tests/unit/test_undo_redo.py`
- `tests/unit/test_batch_config.py`
- `tests/unit/test_concurrency_probe.py`

### Integration Tests

**Scenarios**:
1. Full flow creation with multi-position add
2. Undo/redo across multiple operations
3. Batch configuration across nested scatters
4. Theme switching preserves layout

### Manual Testing Checklist

**Phase 1-3 (Core UX)**:
- [ ] Catalog selection states work correctly
- [ ] Position markers appear and disappear appropriately
- [ ] Multi-position add works
- [ ] Lane markers work in nested scatters
- [ ] Click outside clears selection

**Phase 4-6 (Configuration)**:
- [ ] Tether IDs use semantic naming
- [ ] Node history saves and loads correctly
- [ ] Undo/redo preserves exact state
- [ ] Keyboard shortcuts work

**Phase 7-8 (Advanced)**:
- [ ] Batch config applies to all selected nodes
- [ ] Theme switching works without restart
- [ ] Routing colors maintain contrast

**Phase 9-10 (Performance & Layout)**:
- [ ] Concurrency detection works
- [ ] Layout has no cutoff issues
- [ ] Large flows (50+ nodes) remain responsive

---

## Deployment Checklist

### Pre-Release

- [ ] All 36 Phase 6.13 tests passing
- [ ] New tests for all phases passing
- [ ] Manual testing complete
- [ ] Performance profiling (no regressions)
- [ ] Documentation updated

### Database Migrations

- [ ] Backup existing `__DATACENTER` databases
- [ ] Create `node_history.db` schema
- [ ] Test database on clean install

### Configuration Files

- [ ] Ship `config/color_palettes.json`
- [ ] Create default `~/.maccre/user_preferences.json` on first run
- [ ] Validate all JSON schemas

### Backward Compatibility

- [ ] Old flow files load correctly
- [ ] Legacy tether IDs migrate gracefully
- [ ] No breaking changes to FlowStep serialization

### Rollback Plan

- [ ] Tag current stable version before deployment
- [ ] Document rollback procedure
- [ ] Keep old CSS/layout as backup files

---

## Implementation Notes

### Dependencies Added

None (all features use existing dependencies)

### Breaking Changes

**None** - All changes are additive or internal refactoring

### Performance Considerations

- Position markers: Only render when needed (not all the time)
- Node history: Limit to 50 entries (prevent database bloat)
- Undo stack: Limit to 100 actions (prevent memory bloat)
- Topology updates: Only on flow changes (not on every UI interaction)

### Future Enhancements (Post-v2.0)

- Drag-and-drop node placement
- Visual flow diff tool
- Flow templates library
- Collaborative editing (multi-user)
- Project Faraday 3D visualization integration

---

## Conclusion

This implementation plan provides a comprehensive roadmap for transforming the MACCRE TUI into a sophisticated multi-lane flow builder. Each phase is designed to be independently testable and deployable, allowing for iterative development and early feedback.

**Estimated Total Timeline**: 8-12 weeks

**Recommended Implementation Order**:
1. Phase 1-3 (Foundation - 4-6 weeks)
2. Phase 10 (Layout - 1 week) - Can be done early to fix Add button cutoff
3. Phase 4, 6, 9 (Core features - 4-5 weeks)
4. Phase 5, 7, 8 (Polish - 3-4 weeks)

Good luck with implementation! 🚀
