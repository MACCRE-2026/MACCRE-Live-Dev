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

Uses LEGACY widget IDs from FlowExecutionPanel so all existing NexusPlex
handlers work without modification:
  - #macro-select, #agent-select, #special-select
  - #macro-info-body, #agent-info-body, #special-info-body
  - #btn-add-macro, #btn-add-agent, #btn-add-special
"""
from __future__ import annotations

import logging
from typing import Any


from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.message import Message
from textual.widgets import (
    Button,
    Label,
    RichLog,
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
    """Tabbed catalog for browsing and adding MacroNodes, Agents, and Control Nodes.

    Widget IDs are intentionally set to match the legacy FlowExecutionPanel
    so that all existing NexusPlex handlers work without modification.
    """

    DEFAULT_CSS = """
    NodeCatalog {
        height: auto;
        border: solid $primary;
        padding: 0;
        margin-bottom: 1;
    }
    NodeCatalog > Label.catalog-title {
        height: 1;
        text-style: bold;
        color: $accent;
        padding: 0 1;
    }
    NodeCatalog TabbedContent {
        height: 14;
    }
    NodeCatalog ContentSwitcher {
        height: 10;
    }
    NodeCatalog TabPane {
        height: 10;
        padding: 0 1;
    }
    NodeCatalog .catalog-row {
        height: 3;
        layout: horizontal;
        margin-bottom: 1;
    }
    NodeCatalog .catalog-row Select {
        width: 80%;
    }
    NodeCatalog .catalog-row Button {
        width: 18%;
        min-width: 8;
        margin-left: 1;
    }
    NodeCatalog .info-panel-body {
        height: 5;
        scrollbar-size: 1 1;
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
                    yield Select([], prompt="Select MacroNode…", id="macro-select")
                    yield Button("+ Add", variant="primary", id="btn-add-macro",
                                 classes="flow-add-btn")
                yield RichLog(id="macro-info-body", classes="info-panel-body",
                              wrap=True, markup=True)
            with TabPane("Agents", id="tab-agents"):
                with Horizontal(classes="catalog-row"):
                    yield Select([], prompt="Select Agent…", id="agent-select")
                    yield Button("+ Add", variant="success", id="btn-add-agent",
                                 classes="flow-add-btn")
                yield RichLog(id="agent-info-body", classes="info-panel-body",
                              wrap=True, markup=True)
            with TabPane("Control", id="tab-ctrl"):
                with Horizontal(classes="catalog-row"):
                    yield Select([], prompt="Select Control Node…", id="special-select")
                    yield Button("+ Add", variant="warning", id="btn-add-special",
                                 classes="flow-add-btn")
                yield Static(
                    "[dim]Select a Control Node above to see its description.[/dim]",
                    id="special-info-body", classes="info-panel-body",
                )

    # ── Data Loading ──────────────────────────────────────────────────────

    def load_macronodes(self, macros: list[dict[str, Any]]) -> None:
        """Populate the MacroNode dropdown."""
        self._macro_data = {m["name"]: m for m in macros}
        opts = [(m["name"], m["name"]) for m in macros]
        try:
            self.query_one("#macro-select", Select).set_options(opts)
        except Exception:  # noqa: BLE001
            pass

    def load_agents(self, agents: list[str]) -> None:
        """Populate the Agent dropdown."""
        self._agent_data = {a: {"name": a} for a in agents}
        opts = [(a, a) for a in agents]
        try:
            self.query_one("#agent-select", Select).set_options(opts)
        except Exception:  # noqa: BLE001
            pass

    def load_control_nodes(self, nodes: list[dict[str, Any]]) -> None:
        """Populate the Control Node dropdown."""
        self._ctrl_data = {n["name"]: n for n in nodes if n.get("status") == "active"}
        opts = [(n["name"], n["name"]) for n in nodes if n.get("status") == "active"]
        try:
            self.query_one("#special-select", Select).set_options(opts)
        except Exception:  # noqa: BLE001
            pass
