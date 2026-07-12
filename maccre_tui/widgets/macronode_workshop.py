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
maccre_tui/widgets/macronode_workshop.py
=========================================
MacroNode Workshop — Right-side panel for topology construction and execution.

Combines:
  - NodeCatalog (tabbed browser for MacroNodes, Agents, Control Nodes)
  - TopologyVisualizer (Rich Tree DAG)
  - Flow Control buttons (Launch, Stop, Resume, Rewind, etc.)
  - Flow Monitor (execution log + context injection)

This panel replaces the old FlowExecutionPanel.
"""
from __future__ import annotations

import logging
from typing import Any

from textual import on
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.message import Message
from textual.widgets import (
    Button,
    Input,
    Label,
    RichLog,
)

from maccre_tui.widgets.node_catalog import CatalogSelectionChanged, NodeAddRequested, NodeCatalog
from maccre_tui.widgets.topology_visualizer import TopologyNodeSelected, TopologyVisualizer

logger = logging.getLogger(__name__)


# ── Messages ─────────────────────────────────────────────────────────────────

class WorkshopFlowLaunch(Message):
    """User wants to launch the flow."""

    def __init__(self, steps: list[dict[str, Any]]) -> None:
        super().__init__()
        self.steps = steps


class WorkshopFlowStop(Message):
    """User wants to stop the flow."""


class WorkshopFlowResume(Message):
    """User wants to resume a paused flow."""


class WorkshopNodeConfigRequested(Message):
    """User double-clicked or requested config for a node."""

    def __init__(self, node_id: str, node_data: dict[str, Any]) -> None:
        super().__init__()
        self.node_id = node_id
        self.node_data = node_data


# ── MacroNode Workshop ───────────────────────────────────────────────────────

class MacroNodeWorkshop(Vertical):
    """Right-side workshop for building and executing MacroNode topologies."""

    DEFAULT_CSS = """
    MacroNodeWorkshop {
        width: 1fr;
        height: 100%;
        overflow-y: auto;
    }
    MacroNodeWorkshop > .workshop-title {
        text-style: bold;
        color: $accent;
        padding: 0 1;
        background: $boost;
    }
    MacroNodeWorkshop .flow-controls {
        height: auto;
        padding: 0 1;
        margin-bottom: 0;
    }
    MacroNodeWorkshop .flow-controls Button {
        margin-right: 1;
    }
    MacroNodeWorkshop .flow-monitor-section {
        height: 1fr;
        min-height: 10;
        border-top: solid $primary;
    }
    MacroNodeWorkshop .flow-monitor-section RichLog {
        height: 1fr;
        min-height: 8;
    }
    MacroNodeWorkshop .input-row {
        height: auto;
        padding: 0 1;
    }
    MacroNodeWorkshop .input-row Input {
        width: 1fr;
    }
    MacroNodeWorkshop .input-row Button {
        min-width: 4;
    }
    MacroNodeWorkshop .flow-stage-readout {
        padding: 0 1;
        color: $text-muted;
    }
    MacroNodeWorkshop .topo-actions {
        height: auto;
        padding: 0 1;
    }
    MacroNodeWorkshop .topo-actions Button {
        margin-right: 1;
    }
    MacroNodeWorkshop .session-name-input {
        width: 30;
        margin-left: 1;
    }
    """

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._flow_steps: list[dict[str, Any]] = []

    def compose(self) -> ComposeResult:
        yield Label("⚙  MacroNode Workshop", classes="workshop-title")

        # Node Catalog
        yield NodeCatalog()

        # Topology Visualizer
        yield TopologyVisualizer()

        # Topology Actions
        with Horizontal(classes="topo-actions"):
            yield Button("Remove Last", variant="warning", id="btn-ws-remove-last")
            yield Button("Clear", variant="error", id="btn-ws-clear-topo")
            yield Input(
                placeholder="Session Name…",
                id="ws-session-name",
                classes="session-name-input",
                disabled=True,
            )

        # Flow Controls
        with Horizontal(classes="flow-controls"):
            yield Button("Launch Flow", variant="success", id="btn-ws-launch")
            yield Button("Stop", variant="error", id="btn-ws-stop", disabled=True)
            yield Button("Resume", variant="success", id="btn-ws-resume", disabled=True)
            yield Button("Rewind", variant="warning", id="btn-ws-rewind")
            yield Button("Create Payload", variant="primary", id="btn-ws-payload")
            yield Button("Session Mgr", variant="primary", id="btn-ws-sessions")
            yield Button("Chat Studio", variant="default", id="btn-ws-chat")
            yield Button("File Cabinet", variant="warning", id="btn-ws-files")

        # Flow Monitor
        with Vertical(classes="flow-monitor-section"):
            with Horizontal():
                yield Label("Flow Monitor", classes="workshop-title")
                yield Button("Copy", id="btn-ws-copy-monitor")
            yield Label("Stage: [dim]Idle[/dim]", id="ws-stage-readout", classes="flow-stage-readout")
            yield RichLog(id="ws-execution-log", wrap=True, highlight=True, markup=True)

            with Horizontal(classes="input-row"):
                yield Input(placeholder="Inject context to flow...", id="ws-input")
                yield Button("↗", id="btn-ws-expand-input", variant="primary")

    # ── Catalog Integration ───────────────────────────────────────────────

    @on(NodeAddRequested)
    def _handle_node_add(self, event: NodeAddRequested) -> None:
        """Add a node from the catalog to the topology."""
        step: dict[str, Any] = {
            "Node_ID": event.node_id,
            "type": event.node_type,
        }
        step.update(event.node_data)

        # Set default Next_Node
        if self._flow_steps:
            # Point last node to this new one
            self._flow_steps[-1]["Next_Node"] = event.node_id
        step["Next_Node"] = "END"

        self._flow_steps.append(step)
        self._sync_visualizer()
        logger.info(f"[Workshop] Added {event.node_type}: {event.node_id}")

    @on(CatalogSelectionChanged)
    def _handle_catalog_preview(self, event: CatalogSelectionChanged) -> None:
        """Forward catalog selection to parent for info panel population."""
        # The parent NexusPlex will handle populating InformationPanel
        self.post_message(event)

    @on(TopologyNodeSelected)
    def _handle_topo_node_selected(self, event: TopologyNodeSelected) -> None:
        """Forward topology node selection."""
        self.post_message(event)

    # ── Topology Actions ──────────────────────────────────────────────────

    @on(Button.Pressed, "#btn-ws-remove-last")
    def _remove_last(self) -> None:
        if self._flow_steps:
            self._flow_steps.pop()
            if self._flow_steps:
                self._flow_steps[-1]["Next_Node"] = "END"
            self._sync_visualizer()

    @on(Button.Pressed, "#btn-ws-clear-topo")
    def _clear_topo(self) -> None:
        self._flow_steps.clear()
        self._sync_visualizer()
        try:
            name_input = self.query_one("#ws-session-name", Input)
            name_input.disabled = True
            name_input.value = ""
        except Exception:  # noqa: BLE001
            pass

    # ── Internal ──────────────────────────────────────────────────────────

    def _sync_visualizer(self) -> None:
        """Push the current flow steps to the topology visualizer."""
        try:
            viz = self.query_one(TopologyVisualizer)
            if self._flow_steps:
                viz.load_topology(self._flow_steps)
            else:
                viz.clear()
        except Exception:  # noqa: BLE001
            pass

    # ── Public API ────────────────────────────────────────────────────────

    def load_flow(self, steps: list[dict[str, Any]]) -> None:
        """Load a pre-built flow into the workshop."""
        self._flow_steps = list(steps)
        self._sync_visualizer()

    def get_flow_steps(self) -> list[dict[str, Any]]:
        """Return the current flow steps."""
        return list(self._flow_steps)

    def write_monitor_log(self, text: str) -> None:
        """Write to the flow monitor log."""
        try:
            self.query_one("#ws-execution-log", RichLog).write(text)
        except Exception:  # noqa: BLE001
            pass

    def set_stage_readout(self, text: str) -> None:
        """Update the stage readout label."""
        try:
            self.query_one("#ws-stage-readout", Label).update(text)
        except Exception:  # noqa: BLE001
            pass

    def populate_catalog(
        self,
        macros: list[dict[str, Any]] | None = None,
        agents: list[str] | None = None,
        ctrl_nodes: list[dict[str, Any]] | None = None,
    ) -> None:
        """Populate the node catalog with data."""
        try:
            catalog = self.query_one(NodeCatalog)
            if macros is not None:
                catalog.load_macronodes(macros)
            if agents is not None:
                catalog.load_agents(agents)
            if ctrl_nodes is not None:
                catalog.load_control_nodes(ctrl_nodes)
        except Exception:  # noqa: BLE001
            pass
