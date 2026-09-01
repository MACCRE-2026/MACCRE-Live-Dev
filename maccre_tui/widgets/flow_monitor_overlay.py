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
maccre_tui/widgets/flow_monitor_overlay.py
==========================================
Flow Monitor Overlay — a live execution dashboard that replaces the
InformationPanel in the left pane during active flow execution.

Displays:
  - Stage readout (current pipeline stage)
  - Scrolling execution log via RichLog
  - Progress bar (completed / total nodes)
  - Current node metadata (agent, model, type)

Messages emitted:
  - FlowMonitorCollapsed  — user clicked Collapse; parent hides overlay
  - FlowMonitorExpanded   — user clicked Expand; parent shows overlay
"""
from __future__ import annotations

import logging

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.message import Message
from textual.widgets import Button, Label, ProgressBar, RichLog

logger = logging.getLogger(__name__)


# ── Messages ─────────────────────────────────────────────────────────────────


class FlowMonitorCollapsed(Message):
    """Emitted when the user clicks Collapse on the flow monitor overlay."""


class FlowMonitorExpanded(Message):
    """Emitted when the user requests the flow monitor overlay be shown."""


# ── Flow Monitor Overlay ─────────────────────────────────────────────────────


class FlowMonitorOverlay(Vertical):
    """Live execution dashboard overlaying the InformationPanel during flow runs.

    Renders a title bar, stage readout, scrolling execution log, progress row,
    and current-node metadata.  Emits ``FlowMonitorCollapsed`` /
    ``FlowMonitorExpanded`` so the parent layout can swap visibility with the
    InformationPanel.
    """

    DEFAULT_CSS = """
    FlowMonitorOverlay {
        height: 1fr;
        dock: top;
        border: solid $accent;
        padding: 0 1;
    }

    /* ── Title bar ─────────────────────────────────────── */
    FlowMonitorOverlay > Horizontal.monitor-title-bar {
        layout: horizontal;
        height: 3;
        margin-bottom: 1;
    }
    FlowMonitorOverlay > Horizontal.monitor-title-bar > Label {
        width: 70%;
        text-style: bold;
        color: $accent;
        padding: 1 0 0 0;
    }
    FlowMonitorOverlay > Horizontal.monitor-title-bar > Button {
        width: 30%;
        min-width: 12;
        height: 3;
    }

    /* ── Stage readout ─────────────────────────────────── */
    FlowMonitorOverlay > Label.monitor-stage {
        height: 2;
        padding: 0 1;
        color: $text;
        margin-bottom: 1;
    }

    /* ── Execution log ─────────────────────────────────── */
    FlowMonitorOverlay > RichLog#monitor-exec-log {
        height: 1fr;
        border: round $surface;
        scrollbar-size: 1 1;
        margin-bottom: 1;
    }

    /* ── Progress row ──────────────────────────────────── */
    FlowMonitorOverlay > Horizontal.monitor-progress-row {
        layout: horizontal;
        height: 3;
        margin-bottom: 1;
    }
    FlowMonitorOverlay > Horizontal.monitor-progress-row > Label {
        width: 30%;
        padding: 1 1 0 0;
    }
    FlowMonitorOverlay > Horizontal.monitor-progress-row > ProgressBar {
        width: 70%;
    }

    /* ── Current node info ─────────────────────────────── */
    FlowMonitorOverlay > Label.monitor-node-info {
        height: 2;
        padding: 0 1;
        color: $text-muted;
    }
    """

    def __init__(self, **kwargs: object) -> None:
        super().__init__(**kwargs)
        self._completed: int = 0
        self._total: int = 0
        #: Nodes currently executing, and the concurrency ceiling. Drives the
        #: ``N/8 active`` readout — see update_concurrency.
        self._active_nodes: list[str] = []
        self._concurrency_cap: int = 1

    # ── Compose ──────────────────────────────────────────────────────────────

    def compose(self) -> ComposeResult:
        with Horizontal(classes="monitor-title-bar"):
            yield Label("📊 Flow Monitor", id="monitor-title-label")
            yield Button("Collapse", id="btn-collapse-monitor", variant="default")

        yield Label("[dim]Stage: Idle[/dim]", id="monitor-stage-readout", classes="monitor-stage")

        yield RichLog(id="monitor-exec-log", wrap=True, markup=True, highlight=True)

        with Horizontal(classes="monitor-progress-row"):
            yield Label("0 / 0", id="monitor-progress-label")
            yield ProgressBar(total=100, show_eta=False, id="monitor-progress-bar")

        yield Label("[dim]Node: —[/dim]", id="monitor-node-info", classes="monitor-node-info")

    # ── Button handlers ──────────────────────────────────────────────────────

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle Collapse button click."""
        if event.button.id == "btn-collapse-monitor":
            self.post_message(FlowMonitorCollapsed())
            logger.debug("FlowMonitorOverlay: collapse requested")

    # ── Public API ───────────────────────────────────────────────────────────

    def write_log(self, text: str) -> None:
        """Append a line to the execution log."""
        try:
            log_widget = self.query_one("#monitor-exec-log", RichLog)
            log_widget.write(text)
        except Exception:  # noqa: BLE001
            pass

    def update_stage(self, stage_text: str) -> None:
        """Update the stage readout label."""
        try:
            stage_label = self.query_one("#monitor-stage-readout", Label)
            stage_label.update(f"[bold]Stage:[/bold] {stage_text}")
        except Exception:  # noqa: BLE001
            pass

    def update_progress(self, completed: int, total: int) -> None:
        """Update the progress bar and counter label."""
        self._completed = completed
        self._total = total
        try:
            progress_label = self.query_one("#monitor-progress-label", Label)
            progress_label.update(f"{completed} / {total}")
        except Exception:  # noqa: BLE001
            pass
        try:
            progress_bar = self.query_one("#monitor-progress-bar", ProgressBar)
            progress_bar.update(total=max(total, 1), progress=completed)
        except Exception:  # noqa: BLE001
            pass

    def set_current_node(self, node_id: str, agent_name: str, model: str) -> None:
        """Display a single executing node's metadata.

        The per-**step** readout. Under a scatter several nodes are live at once,
        which :meth:`update_concurrency` displays instead — and because that is
        called on every node start and finish, it naturally takes over the label
        for the duration of the burst.
        """
        self._active_nodes = []
        try:
            node_label = self.query_one("#monitor-node-info", Label)
            node_label.update(
                f"[bold]Node:[/bold] {node_id}  │  "
                f"[bold]Agent:[/bold] {agent_name}  │  "
                f"[bold]Model:[/bold] {model}"
            )
        except Exception:  # noqa: BLE001
            pass

    def update_concurrency(self, active_nodes: list[str], cap: int) -> None:
        """Show how many nodes are executing right now, as ``N/cap active``.

        The visible half of Phase 6.12. The monitor previously had one
        "current node" line, which cannot describe eight agents running at once —
        an operator watching an 8-lane scatter would see a single name and no
        indication that anything was parallel.

        Args:
            active_nodes: Node ids currently executing.
            cap: Concurrency ceiling for this step, so the reading is
                ``3/8`` rather than a bare count.
        """
        self._active_nodes = list(active_nodes)
        self._concurrency_cap = max(1, cap)
        count = len(self._active_nodes)

        # Amber while ramping, green at full width, dim when nothing is running.
        if count == 0:
            colour = "dim"
        elif count >= self._concurrency_cap:
            colour = "bold green"
        else:
            colour = "bold #ffa657"

        if count == 0:
            detail = "—"
        elif count == 1:
            detail = self._active_nodes[0]
        else:
            # Keep the line bounded; a 12-wide scatter would otherwise wrap badly.
            shown = ", ".join(self._active_nodes[:3])
            if count > 3:
                shown += f", +{count - 3} more"
            detail = shown

        try:
            node_label = self.query_one("#monitor-node-info", Label)
            node_label.update(
                f"[{colour}]{count}/{self._concurrency_cap} active[/{colour}]  │  {detail}"
            )
        except Exception:  # noqa: BLE001
            pass

    @property
    def active_node_count(self) -> int:
        """Nodes currently shown as executing."""
        return len(self._active_nodes)

    def request_expand(self) -> None:
        """Programmatic trigger: tell the parent to show the overlay."""
        self.post_message(FlowMonitorExpanded())
        logger.debug("FlowMonitorOverlay: expand requested")
