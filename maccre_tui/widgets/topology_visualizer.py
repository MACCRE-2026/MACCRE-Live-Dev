# ┌─────────────────────────────────────────────────────────────────────────────┐
# │  MACCREv2 ENGINEERING DOCTRINE                             Law Rev: 19.0   │
# ├─────────────────────────────────────────────────────────────────────────────┤
# │  I.   TYPING      All signatures: explicit Python 3.11+ type hints.        │
# │  II.  LINTING     Zero unused imports. No wildcards. 120-char line max.    │
# │  III. PATHS       Never hardcode absolute paths. Use get_maccre_root().     │
# │  IV.  DATACENTER  5-Tier Data Sovereignty.                                 │
# │  VI.  ABSTRACTION All I/O behind abc.ABC before any concrete driver.       │
# │  VII. TEARDOWN    try/finally on all handles (omni clean compliance).      │
# └─────────────────────────────────────────────────────────────────────────────┘
"""
maccre_tui/widgets/topology_visualizer.py
==========================================
Topology Visualizer — Rich Tree-based DAG visualization for NexusPlex v2.

Displays the topology graph using Textual's Tree widget with custom state-driven
styling. Supports:
  - Node state visualization (idle, active, completed, failed)
  - Pulsing animation for active nodes via set_interval
  - Click-to-select for node inspection
  - Orthogonal dimension display (branches, loops, scatter/gather)
  - Color coding for node types, control categories, and states (Task 34)
  - Flow line branch rendering with nested indentation (Task 35)
  - Tether label badges on scatter/merge nodes (Task 36)
  - MacroNode inner topology expansion toggle (Task 37)
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from rich.text import Text
from textual.app import ComposeResult
from textual.containers import Vertical
from textual.events import Key
from textual.message import Message
from textual.widgets import Label, Static, Tree
from textual.widgets.tree import TreeNode

logger = logging.getLogger(__name__)


# ── Node State ───────────────────────────────────────────────────────────────

class NodeState(Enum):
    """Visual state of a topology node."""
    IDLE = "idle"
    QUEUED = "queued"
    ACTIVE = "active"
    COMPLETED = "completed"
    FAILED = "failed"
    PAUSED = "paused"


# ── Node Data ────────────────────────────────────────────────────────────────

@dataclass
class TopologyNodeData:
    """Data attached to each tree node for rendering and state tracking."""
    node_id: str
    role: str = ""
    next_nodes: list[str] = field(default_factory=list)
    wait_for: list[str] = field(default_factory=list)
    state: NodeState = NodeState.IDLE
    is_control_node: bool = False
    step_index: int = -1
    flow_line_id: str = ""
    tether_id: str = ""
    is_macronode: bool = False
    inner_steps: list[dict[str, Any]] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def display_label(self) -> str:
        """Generate the display label with state indicator."""
        return self.node_id


# ── State Symbols ────────────────────────────────────────────────────────────

_STATE_SYMBOLS: dict[NodeState, tuple[str, str]] = {
    NodeState.IDLE: ("○", "dim"),
    NodeState.QUEUED: ("◌", "yellow dim"),
    NodeState.ACTIVE: ("●", "bold green"),
    NodeState.COMPLETED: ("✓", "dim green"),
    NodeState.FAILED: ("✗", "bold red"),
    NodeState.PAUSED: ("⏸", "bold yellow"),
}

_PULSE_FRAMES: list[str] = ["●", "◉", "○", "◉"]


# ── Node Color Coding (Task 34) ──────────────────────────────────────────────

_NODE_COLORS: dict[str, str] = {
    # Node types
    "agent": "#58a6ff",                  # Blue for agent nodes
    "macronode": "#d2a8ff",              # Purple for macronode containers
    # Control nodes by category
    "CTRL_SCATTER": "#f0883e",           # Orange for scatter
    "CTRL_MERGE": "#f0883e",             # Orange for merge (same as scatter pair)
    "CTRL_BRANCH": "#e3b341",            # Gold for deterministic branch
    "CTRL_CONDITIONAL_ROUTE": "#ffa657", # Amber for probabilistic route
    "CTRL_FILTER": "#79c0ff",            # Light blue for filter
    "CTRL_CLEANUP": "#7ee787",           # Green for cleanup
    "CTRL_CONCAT": "#79c0ff",            # Light blue for concat
    "CTRL_REVIEW": "#f85149",            # Red for HITL review
    "CTRL_PAUSE": "#f85149",             # Red for HITL pause
    "CTRL_CHECKPOINT": "#7ee787",        # Green for checkpoint
    "CTRL_RECURSION": "#d2a8ff",         # Purple for recursion
    "CTRL_PAYLOAD_INJECT": "#79c0ff",    # Light blue
    "CTRL_END": "#8b949e",               # Gray for end
    # States (used as override when state is non-idle)
    "running": "#ffa657",                # Amber pulse for active
    "completed": "#3fb950",              # Green for completed
    "failed": "#f85149",                 # Red for failed
    "paused": "#e3b341",                 # Gold for paused
    "pending": "#8b949e",                # Gray for pending
}

# Map NodeState enum values to _NODE_COLORS state keys for override lookup
_STATE_TO_COLOR_KEY: dict[NodeState, str] = {
    NodeState.ACTIVE: "running",
    NodeState.COMPLETED: "completed",
    NodeState.FAILED: "failed",
    NodeState.PAUSED: "paused",
    NodeState.QUEUED: "pending",
}


def _resolve_node_color(ndata: TopologyNodeData) -> str:
    """Resolve the hex color for a node based on state override, then node_id prefix match."""
    # State override takes priority for non-idle nodes
    color_key = _STATE_TO_COLOR_KEY.get(ndata.state)
    if color_key and color_key in _NODE_COLORS:
        return _NODE_COLORS[color_key]

    # MacroNode type
    if ndata.is_macronode:
        return _NODE_COLORS.get("macronode", "#d2a8ff")

    # Prefix match against CTRL_ keys (longest prefix wins)
    upper_id = ndata.node_id.upper()
    best_match = ""
    best_color = _NODE_COLORS.get("agent", "#58a6ff")  # default = agent blue
    for key, color in _NODE_COLORS.items():
        if upper_id.startswith(key.upper()) and len(key) > len(best_match):
            best_match = key
            best_color = color

    return best_color


# ── Messages ─────────────────────────────────────────────────────────────────

class TopologyNodeSelected(Message):
    """Fired when a user clicks on a topology node."""

    def __init__(self, node_data: TopologyNodeData) -> None:
        super().__init__()
        self.node_data = node_data


class TopologyNodeDoubleClicked(Message):
    """Fired on double-click for config/edit."""

    def __init__(self, node_data: TopologyNodeData) -> None:
        super().__init__()
        self.node_data = node_data


# ── Topology Visualizer Widget ───────────────────────────────────────────────

class TopologyVisualizer(Vertical):
    """Rich Tree-based topology DAG visualizer.

    Renders the flow topology as a vertical tree with state-driven
    node styling and optional animation for active nodes.
    """

    DEFAULT_CSS = """
    TopologyVisualizer {
        height: 1fr;
        min-height: 10;
        border: solid $primary;
        padding: 0;
        margin-bottom: 1;
    }
    TopologyVisualizer > Label.topo-title {
        height: 1;
        text-style: bold;
        color: $accent;
        padding: 0 1;
    }
    TopologyVisualizer > Tree {
        height: 1fr;
        min-height: 6;
        scrollbar-size: 1 1;
    }
    TopologyVisualizer > .topo-empty {
        height: 3;
        color: $text-muted;
        padding: 1 2;
    }
    """

    # NOTE: Textual BINDINGS on a parent Vertical don't fire when the Tree
    # child has focus.  All keyboard shortcuts are handled via on_key() below.

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._topo_nodes: dict[str, TopologyNodeData] = {}
        self._tree_node_map: dict[str, TreeNode[TopologyNodeData]] = {}
        self._animation_timer: object | None = None
        self._animation_frame: int = 0
        self._is_animating: bool = False
        self._expand_states: dict[str, bool] = {}  # Task 37: MacroNode expansion tracking

    def compose(self) -> ComposeResult:
        yield Label("⬡  Topology", classes="topo-title")
        yield Tree("Flow", id="topo-tree")
        yield Static(
            "[dim]No topology loaded. Select a MacroNode or build one.[/dim]",
            classes="topo-empty",
            id="topo-empty-msg",
        )

    def on_mount(self) -> None:
        """Initialize the tree in collapsed state."""
        tree = self.query_one("#topo-tree", Tree)
        tree.show_root = False
        tree.guide_depth = 3

    # ── Public API ────────────────────────────────────────────────────────

    def load_topology(self, steps: list[dict[str, Any]]) -> None:
        """Load a topology from a list of step dicts (from topology_rows or flow steps).

        Each dict should have: Node_ID, Next_Node, Wait_For (optional),
        Role (optional), and any other metadata.
        """
        self._topo_nodes.clear()
        self._tree_node_map.clear()

        for i, step in enumerate(steps):
            node_id = str(step.get("Node_ID", step.get("node_id", f"Node_{i}")))
            next_node_raw = str(step.get("Next_Node", step.get("next_node", "END")))
            next_nodes = [n.strip() for n in next_node_raw.split("|") if n.strip()]
            wait_for_raw = str(step.get("Wait_For", step.get("wait_for", "")))
            wait_for = [w.strip() for w in wait_for_raw.split(",") if w.strip()]

            is_ctrl = node_id.upper().startswith("CTRL_") or node_id.upper().startswith("DET_")

            # Task 35/36: Extract flow_line_id and tether_id from step metadata
            flow_line_id = str(step.get("flow_line_id", "") or "")
            tether_id_val = str(step.get("tether_id", "") or "")
            # Nested config may also carry tether_id
            if not tether_id_val:
                cfg = step.get("config", {})
                if isinstance(cfg, dict):
                    tether_id_val = str(cfg.get("tether_id", "") or "")

            # Task 37: Detect MacroNode (has inner_steps or type=macronode)
            node_type = str(step.get("type", "") or "").lower()
            inner_steps_raw: list[dict[str, Any]] = step.get("inner_steps", []) or []
            is_macro = node_type == "macronode" or bool(inner_steps_raw)

            self._topo_nodes[node_id] = TopologyNodeData(
                node_id=node_id,
                role=str(step.get("Role", step.get("role", node_id))),
                next_nodes=next_nodes,
                wait_for=wait_for,
                is_control_node=is_ctrl,
                step_index=i,
                flow_line_id=flow_line_id,
                tether_id=tether_id_val,
                is_macronode=is_macro,
                inner_steps=inner_steps_raw,
                metadata=step,
            )

        self._rebuild_tree()
        # Hide empty message
        try:
            self.query_one("#topo-empty-msg", Static).display = len(self._topo_nodes) == 0
        except Exception:  # noqa: BLE001
            pass

    def clear(self) -> None:
        """Clear the topology."""
        self._topo_nodes.clear()
        self._tree_node_map.clear()
        tree = self.query_one("#topo-tree", Tree)
        tree.clear()
        try:
            self.query_one("#topo-empty-msg", Static).display = True
        except Exception:  # noqa: BLE001
            pass
        self.stop_animation()
        self._expand_states.clear()

    def set_node_state(self, node_id: str, state: NodeState) -> None:
        """Update the visual state of a specific node."""
        if node_id in self._topo_nodes:
            self._topo_nodes[node_id].state = state
            self._update_node_label(node_id)

    def set_active_node(self, node_id: str) -> None:
        """Set a node as active, marking previous as completed."""
        for nid, ndata in self._topo_nodes.items():
            if ndata.state == NodeState.ACTIVE:
                ndata.state = NodeState.COMPLETED
                self._update_node_label(nid)
        if node_id in self._topo_nodes:
            self._topo_nodes[node_id].state = NodeState.ACTIVE
            self._update_node_label(node_id)

    def mark_all_completed(self) -> None:
        """Mark all nodes as completed (post-flow)."""
        for nid, ndata in self._topo_nodes.items():
            if ndata.state in (NodeState.ACTIVE, NodeState.QUEUED, NodeState.IDLE):
                ndata.state = NodeState.COMPLETED
                self._update_node_label(nid)
        self.stop_animation()

    def start_animation(self) -> None:
        """Start the pulsing animation for active nodes."""
        if not self._is_animating:
            self._is_animating = True
            self._animation_frame = 0
            self._animation_timer = self.set_interval(0.2, self._tick_animation)

    def stop_animation(self) -> None:
        """Stop the pulsing animation."""
        self._is_animating = False
        if self._animation_timer is not None:
            try:
                self._animation_timer.stop()  # type: ignore[union-attr]
            except Exception:  # noqa: BLE001
                pass
            self._animation_timer = None

    # ── MacroNode Expansion (Task 37) ─────────────────────────────────────────

    def toggle_expansion(self, node_id: str) -> None:
        """Toggle the expansion state of a MacroNode's inner topology."""
        if node_id not in self._topo_nodes:
            return
        ndata = self._topo_nodes[node_id]
        if not ndata.is_macronode:
            return
        self._expand_states[node_id] = not self._expand_states.get(node_id, False)
        logger.debug("MacroNode '%s' expansion toggled to %s", node_id, self._expand_states[node_id])
        self._rebuild_tree()

    def is_expanded(self, node_id: str) -> bool:
        """Return whether a MacroNode is currently expanded."""
        return self._expand_states.get(node_id, False)

    # ── Internal ──────────────────────────────────────────────────────────

    def _rebuild_tree(self) -> None:
        """Reconstruct the tree from the node graph."""
        tree = self.query_one("#topo-tree", Tree)
        tree.clear()
        self._tree_node_map.clear()

        if not self._topo_nodes:
            return

        # Find root nodes (not referenced as Next_Node by anyone, or index 0)
        all_next: set[str] = set()
        for ndata in self._topo_nodes.values():
            all_next.update(ndata.next_nodes)

        roots = [nid for nid in self._topo_nodes if nid not in all_next]
        if not roots:
            roots = [next(iter(self._topo_nodes))]

        visited: set[str] = set()
        for root_id in roots:
            self._add_subtree(tree.root, root_id, visited)

        tree.root.expand_all()

    def _add_subtree(
        self, parent: TreeNode[Any], node_id: str, visited: set[str]
    ) -> None:
        """Recursively add a node and its children to the tree."""
        if node_id in visited or node_id not in self._topo_nodes:
            if node_id in visited and node_id in self._topo_nodes:
                # Back-edge (loop) — show as reference
                label = self._render_label(self._topo_nodes[node_id], is_backref=True)
                parent.add_leaf(label, data=self._topo_nodes[node_id])
            return

        visited.add(node_id)
        ndata = self._topo_nodes[node_id]
        label = self._render_label(ndata)
        tree_node = parent.add(label, data=ndata)
        self._tree_node_map[node_id] = tree_node

        # Task 37: Render inner MacroNode topology when expanded (default: expanded)
        if ndata.is_macronode and self._expand_states.get(node_id, True) and ndata.inner_steps:
            for inner_step in ndata.inner_steps:
                inner_id = str(inner_step.get("Node_ID", inner_step.get("node_id", "?")))
                inner_label = Text.assemble(
                    ("  ├─ ", "dim"),
                    (inner_id, "dim italic"),
                )
                tree_node.add_leaf(inner_label)

        for next_id in ndata.next_nodes:
            if next_id.upper() != "END":
                self._add_subtree(tree_node, next_id, visited)

    def _render_label(
        self, ndata: TopologyNodeData, is_backref: bool = False
    ) -> Text:
        """Create a Rich Text label for a node with state styling.

        Integrates:
          - Task 34: Color coding via _resolve_node_color()
          - Task 35: Flow line ID prefix with nesting indentation
          - Task 36: Tether badge suffix
          - Task 37: MacroNode [+]/[-] expansion indicator
        """
        symbol, base_style = _STATE_SYMBOLS.get(ndata.state, ("?", ""))
        node_color = _resolve_node_color(ndata)

        if is_backref:
            return Text.assemble(
                ("↩ ", "bold yellow"),
                (ndata.node_id, "dim italic"),
                (" (loop)", "dim yellow"),
            )

        parts: list[tuple[str, str]] = []

        # Task 35: Flow line branch prefix
        if ndata.flow_line_id:
            # Nested flow lines (containing ".") get extra indentation
            indent = "  " if "." in ndata.flow_line_id else ""
            parts.append((f"{indent}{ndata.flow_line_id}: ", "dim cyan italic"))

        # State symbol
        parts.append((f"{symbol} ", base_style))

        # Task 37: MacroNode expansion indicator
        if ndata.is_macronode:
            is_expanded = self._expand_states.get(ndata.node_id, True)
            expand_char = "[-]" if is_expanded else "[+]"
            parts.append((f"{expand_char} ", f"{node_color} bold"))

        # Node name with color coding (Task 34)
        display_name = ndata.role if ndata.role else ndata.node_id
        if ndata.is_control_node:
            parts.append((display_name, f"{node_color} bold"))
        else:
            parts.append((display_name, node_color))

        # Condensed collapsed summary for MacroNodes
        if ndata.is_macronode and not self._expand_states.get(ndata.node_id, True):
            inner_count = len(ndata.inner_steps) if ndata.inner_steps else 0
            next_display = ", ".join(n for n in ndata.next_nodes if n.upper() != "END") or "END"
            parts.append((f" ⟩ {inner_count} nodes ⟩ {next_display}", "dim italic"))
            return Text.assemble(*parts)

        # Task 36: Tether badge
        if ndata.tether_id:
            parts.append((f" [tether:{ndata.tether_id}]", "dim #f0883e italic"))

        # Task 40: Recursion iteration display
        if ndata.node_id.upper().startswith("CTRL_RECURSION"):
            cur_iter = ndata.metadata.get("current_iteration", 0)
            max_iter = ndata.metadata.get("max_recursion", ndata.metadata.get("Max_Recursion", 0))
            if max_iter:
                parts.append((f" [iter {cur_iter}/{max_iter}]", "dim #d2a8ff"))

        if ndata.role and ndata.role != ndata.node_id:
            parts.append((f" ({ndata.role})", "dim"))

        # Show flow arrows for next nodes
        if ndata.next_nodes and ndata.next_nodes != ["END"]:
            display_targets: list[str] = []
            for n in ndata.next_nodes:
                if n.upper() == "END":
                    continue
                # Look up role for display if available
                if n in self._topo_nodes:
                    display_targets.append(self._topo_nodes[n].role or n)
                else:
                    display_targets.append(n)
            if display_targets:
                parts.append((f" → {', '.join(display_targets)}", "dim cyan"))

        return Text.assemble(*parts)

    def _update_node_label(self, node_id: str) -> None:
        """Re-render a single node's label after state change."""
        if node_id in self._tree_node_map and node_id in self._topo_nodes:
            tree_node = self._tree_node_map[node_id]
            tree_node.set_label(self._render_label(self._topo_nodes[node_id]))

    def _tick_animation(self) -> None:
        """Animation frame tick — pulse active nodes."""
        self._animation_frame = (self._animation_frame + 1) % len(_PULSE_FRAMES)
        symbol = _PULSE_FRAMES[self._animation_frame]

        for nid, ndata in self._topo_nodes.items():
            if ndata.state == NodeState.ACTIVE and nid in self._tree_node_map:
                tree_node = self._tree_node_map[nid]
                active_color = _NODE_COLORS.get("running", "#ffa657")
                parts: list[tuple[str, str]] = []
                # Task 35: Flow line prefix in animation frames too
                if ndata.flow_line_id:
                    indent = "  " if "." in ndata.flow_line_id else ""
                    parts.append((f"{indent}{ndata.flow_line_id}: ", "dim cyan italic"))
                parts.append((f"{symbol} ", f"bold {active_color}"))
                # Task 37: MacroNode indicator during animation
                if ndata.is_macronode:
                    expand_char = "[-]" if self._expand_states.get(nid, True) else "[+]"
                    parts.append((f"{expand_char} ", f"{active_color} bold"))
                parts.append((ndata.node_id, f"bold {active_color}"))
                # Task 36: Tether badge
                if ndata.tether_id:
                    parts.append((f" [tether:{ndata.tether_id}]", "dim #f0883e italic"))
                if ndata.role and ndata.role != ndata.node_id:
                    parts.append((f" ({ndata.role})", "dim"))
                tree_node.set_label(Text.assemble(*parts))

    # ── Event Handlers ────────────────────────────────────────────────────

    def on_tree_node_selected(self, event: Tree.NodeSelected[TopologyNodeData]) -> None:
        """Handle node click — toggle macronode expansion, show brief info."""
        if not event.node.data or not isinstance(event.node.data, TopologyNodeData):
            return
        nd = event.node.data
        # Toggle macronode expansion on click
        if nd.is_macronode:
            self.toggle_expansion(nd.node_id)
        label = nd.role or nd.node_id
        kind = "CTRL" if nd.is_control_node else ("MacroNode" if nd.is_macronode else "Agent")
        self.notify(f"{label} ({kind})  [F2 → Configure]", timeout=3)

    def on_key(self, event: Key) -> None:
        """Handle keyboard shortcuts for the topology tree.

        Textual BINDINGS on a Vertical parent don't fire when the Tree child
        has focus.  We intercept key events directly instead.
        """
        key = event.key
        if key == "ctrl+e":
            self.action_toggle_expand()
            event.prevent_default()
            event.stop()
        elif key == "ctrl+up":
            self.action_move_node_up()
            event.prevent_default()
            event.stop()
        elif key == "ctrl+down":
            self.action_move_node_down()
            event.prevent_default()
            event.stop()
        elif key == "f2":
            self.action_open_config()
            event.prevent_default()
            event.stop()

    @property
    def node_count(self) -> int:
        """Return the number of nodes in the topology."""
        return len(self._topo_nodes)

    @property
    def active_node(self) -> str | None:
        """Return the currently active node ID, if any."""
        for nid, ndata in self._topo_nodes.items():
            if ndata.state == NodeState.ACTIVE:
                return nid
        return None

    # ── Keyboard Actions (Task 39) ───────────────────────────────────────

    def action_move_node_up(self) -> None:
        """Swap the selected node with the one above it."""
        tree = self.query_one("#topo-tree", Tree)
        cursor = tree.cursor_node
        if not cursor or not cursor.data or not isinstance(cursor.data, TopologyNodeData):
            return
        nid = cursor.data.node_id
        keys = list(self._topo_nodes.keys())
        idx = keys.index(nid) if nid in keys else -1
        if idx > 0:
            keys[idx - 1], keys[idx] = keys[idx], keys[idx - 1]
            self._topo_nodes = {k: self._topo_nodes[k] for k in keys}
            self._rebuild_tree()

    def action_move_node_down(self) -> None:
        """Swap the selected node with the one below it."""
        tree = self.query_one("#topo-tree", Tree)
        cursor = tree.cursor_node
        if not cursor or not cursor.data or not isinstance(cursor.data, TopologyNodeData):
            return
        nid = cursor.data.node_id
        keys = list(self._topo_nodes.keys())
        idx = keys.index(nid) if nid in keys else -1
        if 0 <= idx < len(keys) - 1:
            keys[idx], keys[idx + 1] = keys[idx + 1], keys[idx]
            self._topo_nodes = {k: self._topo_nodes[k] for k in keys}
            self._rebuild_tree()

    def action_toggle_expand(self) -> None:
        """Toggle MacroNode inner topology expansion."""
        tree = self.query_one("#topo-tree", Tree)
        cursor = tree.cursor_node
        if not cursor or not cursor.data or not isinstance(cursor.data, TopologyNodeData):
            return
        nid = cursor.data.node_id
        if cursor.data.is_macronode:
            self.toggle_expansion(nid)

    def action_open_config(self) -> None:
        """Open config modal for the selected node."""
        tree = self.query_one("#topo-tree", Tree)
        cursor = tree.cursor_node
        if not cursor or not cursor.data or not isinstance(cursor.data, TopologyNodeData):
            return
        self.post_message(TopologyNodeDoubleClicked(cursor.data))
