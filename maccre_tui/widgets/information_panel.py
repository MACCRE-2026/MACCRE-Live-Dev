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
maccre_tui/widgets/information_panel.py
========================================
Information Panes — Context-sensitive left-side panel for the NexusPlex v2
Topology-First layout.

Contains collapsible sections:
  - MacroNode Details   (populated on macro selection)
  - Agent Details       (populated on agent selection)
  - Control Node Info   (populated on control node selection)
  - As-Wrapped Preview  (populated during/after flow execution)
  - User Instructions   (static guidance text)
"""
from __future__ import annotations

import json
import logging
from typing import Any

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.message import Message
from textual.widgets import (
    Collapsible,
    Label,
    RichLog,
)

logger = logging.getLogger(__name__)


# ── Messages ─────────────────────────────────────────────────────────────────

class InfoPaneMessage(Message):
    """Base message for info pane interactions."""


class InfoPaneExpandRequested(InfoPaneMessage):
    """User wants to expand an info pane into a modal."""

    def __init__(self, pane_id: str, content: str) -> None:
        super().__init__()
        self.pane_id = pane_id
        self.content = content


# ── Individual Info Pane ──────────────────────────────────────────────────────

class InfoPane(Collapsible):
    """A single collapsible information section.

    Wraps a RichLog with a title and optional action button.
    Remembers its content for modal expansion.
    """

    DEFAULT_CSS = """
    InfoPane {
        height: auto;
        max-height: 20;
        margin-bottom: 0;
        padding: 0;
    }
    InfoPane RichLog {
        height: auto;
        max-height: 16;
        min-height: 3;
        scrollbar-size: 1 1;
    }
    InfoPane .info-pane-empty {
        color: $text-muted;
        padding: 0 1;
    }
    """

    def __init__(
        self,
        pane_id: str,
        title: str = "Info",
        collapsed: bool = True,
        **kwargs: Any,
    ) -> None:
        super().__init__(title=title, collapsed=collapsed, **kwargs)
        self.pane_id = pane_id
        self._content_text: str = ""

    def compose(self) -> ComposeResult:
        yield RichLog(
            id=f"{self.pane_id}-body",
            wrap=True,
            markup=True,
            highlight=False,
        )

    def set_content(self, text: str) -> None:
        """Update the pane content and auto-expand if non-empty."""
        self._content_text = text
        try:
            body = self.query_one(f"#{self.pane_id}-body", RichLog)
            body.clear()
            if text:
                body.write(text)
                self.collapsed = False
            else:
                body.write("[dim]No data available.[/dim]")
        except Exception:  # noqa: BLE001
            pass

    def clear_content(self) -> None:
        """Reset the pane to empty state."""
        self.set_content("")
        self.collapsed = True

    @property
    def content_text(self) -> str:
        """Return the current content text for modal expansion."""
        return self._content_text


# ── Information Panel Container ──────────────────────────────────────────────

class InformationPanel(Vertical):
    """Container holding all info panes for the left side of NexusPlex v2.

    Provides methods to populate each pane from selection events.
    """

    DEFAULT_CSS = """
    InformationPanel {
        height: 1fr;
        overflow-y: scroll;
        border: solid $primary;
        padding: 0 1;
    }
    InformationPanel > Label.info-panel-header {
        text-style: bold;
        color: $accent;
        padding: 0 0 0 0;
    }
    """

    def compose(self) -> ComposeResult:
        yield Label("ℹ  Information", classes="info-panel-header")
        yield InfoPane(pane_id="macro-info", title="MacroNode Details", collapsed=True)
        yield InfoPane(pane_id="agent-info", title="Agent Details", collapsed=True)
        yield InfoPane(pane_id="ctrl-info", title="Control Node Info", collapsed=True)
        yield InfoPane(pane_id="flow-dict", title="Flow Dictionary", collapsed=True)
        yield InfoPane(pane_id="as-wrapped", title="As-Wrapped Preview", collapsed=True)
        yield InfoPane(
            pane_id="instructions",
            title="User Instructions",
            collapsed=True,
        )

    def on_mount(self) -> None:
        """Seed the instructions pane with static guidance."""
        try:
            # Iterate to find the instructions pane
            for pane in self.query(InfoPane):
                if pane.pane_id == "instructions":
                    pane.set_content(
                        "[b]Getting Started[/b]\n"
                        "1. Select a MacroNode or build one in the Workshop\n"
                        "2. Configure agents and control nodes\n"
                        "3. Launch from the Workshop controls\n\n"
                        "[dim]Tip: Click any node in the topology to inspect it.[/dim]"
                    )
                    pane.collapsed = True  # Start collapsed
                    break
        except Exception:  # noqa: BLE001
            pass

    # ── Public API for NexusPlex handlers ─────────────────────────────────

    def show_macro_details(self, macro_data: dict[str, Any]) -> None:
        """Populate the MacroNode info pane."""
        pane = self._get_pane("macro-info")
        if not pane:
            return

        lines: list[str] = [
            f"[b]{macro_data.get('name', 'Unknown')}[/b]",
            f"[dim]Template:[/dim] {macro_data.get('template_type', 'custom')}",
        ]
        desc = macro_data.get("description", "")
        if desc:
            lines.append(f"[dim]Description:[/dim] {desc}")

        slots = macro_data.get("agent_slots", [])
        if slots:
            lines.append(f"\n[b]Agent Slots ({len(slots)}):[/b]")
            for slot in slots:
                lines.append(f"  • {slot}")

        topo = macro_data.get("topology_rows", [])
        if topo:
            lines.append(f"\n[b]Topology ({len(topo)} nodes):[/b]")
            for row in topo[:8]:
                node = row.get("Node_ID", "?")
                nxt = row.get("Next_Node", "END")
                lines.append(f"  {node} → {nxt}")
            if len(topo) > 8:
                lines.append(f"  [dim]...and {len(topo) - 8} more[/dim]")

        pane.set_content("\n".join(lines))

    def show_agent_details(self, agent_data: dict[str, Any]) -> None:
        """Populate the Agent info pane."""
        pane = self._get_pane("agent-info")
        if not pane:
            return

        lines: list[str] = [
            f"[b]{agent_data.get('name', 'Unknown')}[/b]",
            f"[dim]Model:[/dim] {agent_data.get('model', 'default')}",
            f"[dim]Temperature:[/dim] {agent_data.get('temperature', 1.0)}",
        ]
        prompt = agent_data.get("system_instruction", "")
        if prompt:
            preview = prompt[:200] + ("..." if len(prompt) > 200 else "")
            lines.append(f"\n[b]System Instruction:[/b]\n[dim]{preview}[/dim]")

        tools = agent_data.get("tools", [])
        if tools:
            lines.append(f"\n[b]Tools ({len(tools)}):[/b]")
            for tool in tools[:6]:
                lines.append(f"  • {tool}")
            if len(tools) > 6:
                lines.append(f"  [dim]...and {len(tools) - 6} more[/dim]")

        pane.set_content("\n".join(lines))

    def show_control_node_details(self, node_data: dict[str, Any]) -> None:
        """Populate the Control Node info pane."""
        pane = self._get_pane("ctrl-info")
        if not pane:
            return

        lines: list[str] = [
            f"[b]{node_data.get('name', 'Unknown')}[/b]",
            f"[dim]Category:[/dim] {node_data.get('category', '')}",
            f"[dim]Status:[/dim] {node_data.get('status', 'active')}",
        ]
        desc = node_data.get("description", "")
        if desc:
            lines.append(f"\n{desc}")

        schema = node_data.get("config_schema")
        if schema and schema != "{}":
            if isinstance(schema, str):
                try:
                    schema = json.loads(schema)
                except json.JSONDecodeError:
                    pass
            if isinstance(schema, dict) and schema:
                lines.append("\n[b]Configuration:[/b]")
                for key, val in schema.items():
                    lines.append(f"  {key}: {val}")

        pane.set_content("\n".join(lines))

    def show_flow_dict_preview(self, dict_json: str) -> None:
        """Show the live flow dictionary preview as agents are added/configured."""
        pane = self._get_pane("flow-dict")
        if not pane:
            return
        try:
            data = json.loads(dict_json)
            agent_count = sum(1 for k in data if k != "_flow_meta")
            meta = data.get("_flow_meta", {})
            tether_count = len(meta.get("tethers", {}))
            header = f"[b]Flow Dictionary[/b] — {agent_count} agent(s)"
            if tether_count:
                header += f", {tether_count} tether(s)"
            formatted = json.dumps(data, indent=2)[:3000]
            pane.set_content(f"{header}\n```json\n{formatted}\n```")
            pane.collapsed = False
        except (json.JSONDecodeError, TypeError):
            pane.set_content(dict_json[:2000] if dict_json else "")

    def show_as_wrapped(self, topology_json: str) -> None:
        """Show the as-wrapped topology preview during/after execution."""
        pane = self._get_pane("as-wrapped")
        if not pane:
            return
        try:
            data = json.loads(topology_json)
            formatted = json.dumps(data, indent=2)[:2000]
            pane.set_content(f"[b]As-Wrapped Topology[/b]\n```\n{formatted}\n```")
        except (json.JSONDecodeError, TypeError):
            pane.set_content(topology_json[:2000] if topology_json else "")

    def clear_all(self) -> None:
        """Reset all panes."""
        for pane in self.query(InfoPane):
            pane.clear_content()

    def _get_pane(self, pane_id: str) -> InfoPane | None:
        """Get a specific InfoPane by its pane_id."""
        for pane in self.query(InfoPane):
            if pane.pane_id == pane_id:
                return pane
        return None
