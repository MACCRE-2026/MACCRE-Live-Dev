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
maccre_tui/widgets/node_catalog.py
===================================
Node Catalog — Unified browser for MacroNodes, Agents, and Control Nodes.

Replaces the separate Select dropdowns from FlowExecutionPanel with a
single tabbed catalog widget. Items can be dragged/clicked to add to
the topology.
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
    Label,
    Select,
    Static,
    TabbedContent,
    TabPane,
)

logger = logging.getLogger(__name__)


# ── Messages ─────────────────────────────────────────────────────────────────

class NodeAddRequested(Message):
    """User wants to add a node to the topology."""

    def __init__(self, node_type: str, node_id: str, node_data: dict[str, Any]) -> None:
        super().__init__()
        self.node_type = node_type   # "macronode" | "agent" | "control"
        self.node_id = node_id
        self.node_data = node_data


class CatalogSelectionChanged(Message):
    """User selected a node in the catalog (for preview)."""

    def __init__(self, node_type: str, node_id: str, node_data: dict[str, Any]) -> None:
        super().__init__()
        self.node_type = node_type
        self.node_id = node_id
        self.node_data = node_data


# ── Node Catalog ─────────────────────────────────────────────────────────────

class NodeCatalog(Vertical):
    """Tabbed catalog for browsing and adding MacroNodes, Agents, and Control Nodes."""

    DEFAULT_CSS = """
    NodeCatalog {
        height: auto;
        max-height: 16;
        border: solid $primary;
        padding: 0;
    }
    NodeCatalog > Label.catalog-title {
        text-style: bold;
        color: $accent;
        padding: 0 1;
    }
    NodeCatalog TabbedContent {
        height: auto;
        max-height: 14;
    }
    NodeCatalog TabPane {
        height: auto;
        padding: 0 1;
    }
    NodeCatalog .catalog-row {
        height: auto;
        padding: 0;
    }
    NodeCatalog Select {
        width: 1fr;
    }
    NodeCatalog .catalog-add-btn {
        min-width: 8;
        margin-left: 1;
    }
    NodeCatalog .catalog-status {
        color: $text-muted;
        padding: 0 1;
    }
    """

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._macro_data: dict[str, dict[str, Any]] = {}
        self._agent_data: dict[str, dict[str, Any]] = {}
        self._ctrl_data: dict[str, dict[str, Any]] = {}

    def compose(self) -> ComposeResult:
        yield Label("📦  Node Catalog", classes="catalog-title")
        with TabbedContent():
            with TabPane("MacroNodes", id="tab-macros"):
                with Horizontal(classes="catalog-row"):
                    yield Select([], prompt="Select MacroNode…", id="catalog-macro-select")
                    yield Button("+ Add", variant="primary", id="btn-catalog-add-macro",
                                 classes="catalog-add-btn")
            with TabPane("Agents", id="tab-agents"):
                with Horizontal(classes="catalog-row"):
                    yield Select([], prompt="Select Agent…", id="catalog-agent-select")
                    yield Button("+ Add", variant="success", id="btn-catalog-add-agent",
                                 classes="catalog-add-btn")
            with TabPane("Control", id="tab-ctrl"):
                with Horizontal(classes="catalog-row"):
                    yield Select([], prompt="Select Control Node…", id="catalog-ctrl-select")
                    yield Button("+ Add", variant="warning", id="btn-catalog-add-ctrl",
                                 classes="catalog-add-btn")
        yield Static("", id="catalog-status", classes="catalog-status")

    # ── Data Loading ──────────────────────────────────────────────────────

    def load_macronodes(self, macros: list[dict[str, Any]]) -> None:
        """Populate the MacroNode dropdown."""
        self._macro_data = {m["name"]: m for m in macros}
        opts = [(m["name"], m["name"]) for m in macros]
        try:
            self.query_one("#catalog-macro-select", Select).set_options(opts)
        except Exception:  # noqa: BLE001
            pass

    def load_agents(self, agents: list[str]) -> None:
        """Populate the Agent dropdown."""
        self._agent_data = {a: {"name": a} for a in agents}
        opts = [(a, a) for a in agents]
        try:
            self.query_one("#catalog-agent-select", Select).set_options(opts)
        except Exception:  # noqa: BLE001
            pass

    def load_control_nodes(self, nodes: list[dict[str, Any]]) -> None:
        """Populate the Control Node dropdown."""
        self._ctrl_data = {n["name"]: n for n in nodes if n.get("status") == "active"}
        opts = [(n["name"], n["name"]) for n in nodes if n.get("status") == "active"]
        try:
            self.query_one("#catalog-ctrl-select", Select).set_options(opts)
        except Exception:  # noqa: BLE001
            pass

    # ── Selection Handlers ────────────────────────────────────────────────

    @on(Select.Changed, "#catalog-macro-select")
    def _on_macro_changed(self, event: Select.Changed) -> None:
        if event.value and event.value != Select.BLANK:
            name = str(event.value)
            data = self._macro_data.get(name, {"name": name})
            self.post_message(CatalogSelectionChanged("macronode", name, data))

    @on(Select.Changed, "#catalog-agent-select")
    def _on_agent_changed(self, event: Select.Changed) -> None:
        if event.value and event.value != Select.BLANK:
            name = str(event.value)
            data = self._agent_data.get(name, {"name": name})
            self.post_message(CatalogSelectionChanged("agent", name, data))

    @on(Select.Changed, "#catalog-ctrl-select")
    def _on_ctrl_changed(self, event: Select.Changed) -> None:
        if event.value and event.value != Select.BLANK:
            name = str(event.value)
            data = self._ctrl_data.get(name, {"name": name})
            self.post_message(CatalogSelectionChanged("control", name, data))

    # ── Add Handlers ─────────────────────────────────────────────────────

    @on(Button.Pressed, "#btn-catalog-add-macro")
    def _on_add_macro(self) -> None:
        try:
            sel = self.query_one("#catalog-macro-select", Select)
            if sel.value and sel.value != Select.BLANK:
                name = str(sel.value)
                data = self._macro_data.get(name, {"name": name})
                self.post_message(NodeAddRequested("macronode", name, data))
                self._set_status(f"Added MacroNode: {name}")
        except Exception:  # noqa: BLE001
            pass

    @on(Button.Pressed, "#btn-catalog-add-agent")
    def _on_add_agent(self) -> None:
        try:
            sel = self.query_one("#catalog-agent-select", Select)
            if sel.value and sel.value != Select.BLANK:
                name = str(sel.value)
                data = self._agent_data.get(name, {"name": name})
                self.post_message(NodeAddRequested("agent", name, data))
                self._set_status(f"Added Agent: {name}")
        except Exception:  # noqa: BLE001
            pass

    @on(Button.Pressed, "#btn-catalog-add-ctrl")
    def _on_add_ctrl(self) -> None:
        try:
            sel = self.query_one("#catalog-ctrl-select", Select)
            if sel.value and sel.value != Select.BLANK:
                name = str(sel.value)
                data = self._ctrl_data.get(name, {"name": name})
                self.post_message(NodeAddRequested("control", name, data))
                self._set_status(f"Added Control Node: {name}")
        except Exception:  # noqa: BLE001
            pass

    def _set_status(self, msg: str) -> None:
        """Update the status bar."""
        try:
            self.query_one("#catalog-status", Static).update(f"[dim]{msg}[/dim]")
        except Exception:  # noqa: BLE001
            pass
