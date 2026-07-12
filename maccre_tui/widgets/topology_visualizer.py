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
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from rich.text import Text
from textual.app import ComposeResult
from textual.containers import Vertical
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
        height: auto;
        min-height: 8;
        max-height: 100%;
        border: solid $primary;
        padding: 0;
    }
    TopologyVisualizer > Label.topo-title {
        text-style: bold;
        color: $accent;
        padding: 0 1;
    }
    TopologyVisualizer > Tree {
        height: auto;
        min-height: 6;
        max-height: 100%;
        scrollbar-size: 1 1;
    }
    TopologyVisualizer > .topo-empty {
        color: $text-muted;
        padding: 1 2;
    }
    """

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._nodes: dict[str, TopologyNodeData] = {}
        self._tree_node_map: dict[str, TreeNode[TopologyNodeData]] = {}
        self._animation_timer: object | None = None
        self._animation_frame: int = 0
        self._is_animating: bool = False

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
        self._nodes.clear()
        self._tree_node_map.clear()

        for i, step in enumerate(steps):
            node_id = str(step.get("Node_ID", step.get("node_id", f"Node_{i}")))
            next_node_raw = str(step.get("Next_Node", step.get("next_node", "END")))
            next_nodes = [n.strip() for n in next_node_raw.split("|") if n.strip()]
            wait_for_raw = str(step.get("Wait_For", step.get("wait_for", "")))
            wait_for = [w.strip() for w in wait_for_raw.split(",") if w.strip()]

            is_ctrl = node_id.upper().startswith("CTRL_") or node_id.upper().startswith("DET_")

            self._nodes[node_id] = TopologyNodeData(
                node_id=node_id,
                role=str(step.get("Role", step.get("role", node_id))),
                next_nodes=next_nodes,
                wait_for=wait_for,
                is_control_node=is_ctrl,
                step_index=i,
                metadata=step,
            )

        self._rebuild_tree()
        # Hide empty message
        try:
            self.query_one("#topo-empty-msg", Static).display = len(self._nodes) == 0
        except Exception:  # noqa: BLE001
            pass

    def clear(self) -> None:
        """Clear the topology."""
        self._nodes.clear()
        self._tree_node_map.clear()
        tree = self.query_one("#topo-tree", Tree)
        tree.clear()
        try:
            self.query_one("#topo-empty-msg", Static).display = True
        except Exception:  # noqa: BLE001
            pass
        self.stop_animation()

    def set_node_state(self, node_id: str, state: NodeState) -> None:
        """Update the visual state of a specific node."""
        if node_id in self._nodes:
            self._nodes[node_id].state = state
            self._update_node_label(node_id)

    def set_active_node(self, node_id: str) -> None:
        """Set a node as active, marking previous as completed."""
        for nid, ndata in self._nodes.items():
            if ndata.state == NodeState.ACTIVE:
                ndata.state = NodeState.COMPLETED
                self._update_node_label(nid)
        if node_id in self._nodes:
            self._nodes[node_id].state = NodeState.ACTIVE
            self._update_node_label(node_id)

    def mark_all_completed(self) -> None:
        """Mark all nodes as completed (post-flow)."""
        for nid, ndata in self._nodes.items():
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

    # ── Internal ──────────────────────────────────────────────────────────

    def _rebuild_tree(self) -> None:
        """Reconstruct the tree from the node graph."""
        tree = self.query_one("#topo-tree", Tree)
        tree.clear()
        self._tree_node_map.clear()

        if not self._nodes:
            return

        # Find root nodes (not referenced as Next_Node by anyone, or index 0)
        all_next: set[str] = set()
        for ndata in self._nodes.values():
            all_next.update(ndata.next_nodes)

        roots = [nid for nid in self._nodes if nid not in all_next]
        if not roots:
            roots = [next(iter(self._nodes))]

        visited: set[str] = set()
        for root_id in roots:
            self._add_subtree(tree.root, root_id, visited)

        tree.root.expand_all()

    def _add_subtree(
        self, parent: TreeNode[Any], node_id: str, visited: set[str]
    ) -> None:
        """Recursively add a node and its children to the tree."""
        if node_id in visited or node_id not in self._nodes:
            if node_id in visited and node_id in self._nodes:
                # Back-edge (loop) — show as reference
                label = self._render_label(self._nodes[node_id], is_backref=True)
                parent.add_leaf(label, data=self._nodes[node_id])
            return

        visited.add(node_id)
        ndata = self._nodes[node_id]
        label = self._render_label(ndata)
        tree_node = parent.add(label, data=ndata)
        self._tree_node_map[node_id] = tree_node

        for next_id in ndata.next_nodes:
            if next_id.upper() != "END":
                self._add_subtree(tree_node, next_id, visited)

    def _render_label(
        self, ndata: TopologyNodeData, is_backref: bool = False
    ) -> Text:
        """Create a Rich Text label for a node with state styling."""
        symbol, style = _STATE_SYMBOLS.get(ndata.state, ("?", ""))

        if is_backref:
            return Text.assemble(
                ("↩ ", "bold yellow"),
                (ndata.node_id, "dim italic"),
                (" (loop)", "dim yellow"),
            )

        parts: list[tuple[str, str]] = [(f"{symbol} ", style)]

        if ndata.is_control_node:
            parts.append((ndata.node_id, f"{style} bold"))
        else:
            parts.append((ndata.node_id, style))

        if ndata.role and ndata.role != ndata.node_id:
            parts.append((f" ({ndata.role})", "dim"))

        # Show flow arrows for next nodes
        if ndata.next_nodes and ndata.next_nodes != ["END"]:
            targets = ", ".join(n for n in ndata.next_nodes if n.upper() != "END")
            if targets:
                parts.append((f" → {targets}", "dim cyan"))

        return Text.assemble(*parts)

    def _update_node_label(self, node_id: str) -> None:
        """Re-render a single node's label after state change."""
        if node_id in self._tree_node_map and node_id in self._nodes:
            tree_node = self._tree_node_map[node_id]
            tree_node.set_label(self._render_label(self._nodes[node_id]))

    def _tick_animation(self) -> None:
        """Animation frame tick — pulse active nodes."""
        self._animation_frame = (self._animation_frame + 1) % len(_PULSE_FRAMES)
        symbol = _PULSE_FRAMES[self._animation_frame]

        for nid, ndata in self._nodes.items():
            if ndata.state == NodeState.ACTIVE and nid in self._tree_node_map:
                tree_node = self._tree_node_map[nid]
                parts: list[tuple[str, str]] = [
                    (f"{symbol} ", "bold green"),
                    (ndata.node_id, "bold green"),
                ]
                if ndata.role and ndata.role != ndata.node_id:
                    parts.append((f" ({ndata.role})", "dim"))
                tree_node.set_label(Text.assemble(*parts))

    # ── Event Handlers ────────────────────────────────────────────────────

    def on_tree_node_selected(self, event: Tree.NodeSelected[TopologyNodeData]) -> None:
        """Handle node click — post selection message."""
        if event.node.data and isinstance(event.node.data, TopologyNodeData):
            self.post_message(TopologyNodeSelected(event.node.data))

    @property
    def node_count(self) -> int:
        """Return the number of nodes in the topology."""
        return len(self._nodes)

    @property
    def active_node(self) -> str | None:
        """Return the currently active node ID, if any."""
        for nid, ndata in self._nodes.items():
            if ndata.state == NodeState.ACTIVE:
                return nid
        return None
