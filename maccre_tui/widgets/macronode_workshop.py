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

The Flow Monitor is handled by FlowMonitorOverlay in the left pane.

Uses LEGACY widget IDs from FlowExecutionPanel so that all existing
NexusPlex handlers work without any modification. This is the canonical
replacement for FlowExecutionPanel.
"""
from __future__ import annotations

import logging
from typing import Any

from maccre_core.flow_dict import FlowDictBuffer
from maccre_core.orchestration.tether import root_tether_id

from textual import on
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.message import Message
from textual.widgets import (
    Button,
    Input,
    Label,
    Static,
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


class WorkshopDictUpdated(Message):
    """Fired when the flow dict buffer changes, so parent can refresh preview."""

    def __init__(self, preview_json: str) -> None:
        super().__init__()
        self.preview_json = preview_json


class WorkshopNodeConfigRequested(Message):
    """User double-clicked or requested config for a node."""

    def __init__(self, node_id: str, node_data: dict[str, Any]) -> None:
        super().__init__()
        self.node_id = node_id
        self.node_data = node_data


class ScatterCompanionHint(Message):
    """Hint that a CTRL_SCATTER was added and needs a companion sink node."""

    def __init__(self, tether_id: str, scatter_node: str) -> None:
        super().__init__()
        self.tether_id = tether_id
        self.scatter_node = scatter_node


# ── MacroNode Workshop ───────────────────────────────────────────────────────

class MacroNodeWorkshop(Vertical):
    """Right-side workshop for building and executing MacroNode topologies.

    All widget IDs match the legacy FlowExecutionPanel so existing NexusPlex
    handlers (launch, stop, resume, VCR, payload, etc.) work unchanged.
    """

    DEFAULT_CSS = """
    MacroNodeWorkshop {
        width: 1fr;
        height: 100%;
        overflow-y: auto;
        padding: 0 1;
    }
    MacroNodeWorkshop > .workshop-title {
        height: 1;
        text-style: bold;
        color: $accent;
        padding: 0 1;
        background: $boost;
        margin-bottom: 1;
    }
    MacroNodeWorkshop .flow-controls {
        height: 3;
        layout: horizontal;
        margin-bottom: 1;
    }
    MacroNodeWorkshop #flow-line-container {
        height: auto;
        min-height: 8;
        overflow-x: auto;
    }
    MacroNodeWorkshop .flow-controls Button {
        margin: 0 1 0 0;
    }
    MacroNodeWorkshop .panel-section {
        height: auto;
        padding: 0;
    }
    MacroNodeWorkshop .topo-actions {
        height: 3;
        layout: horizontal;
        margin-bottom: 1;
    }
    MacroNodeWorkshop .topo-actions Button {
        margin-right: 1;
    }
    MacroNodeWorkshop .session-name-input {
        width: 30;
        margin-left: 1;
    }
    /* Defect F1 — do not narrow this below 6.
     *
     * These were min-width/max-width 4, and pressing pause crashed the whole
     * TUI. The three .vcr-btn--* state rules in nexus_plex.css each declare
     * `border: solid`, and Textual's Button carries `padding: 0 1`, so the box
     * arithmetic is:
     *
     *     content_width = outer - border(2) - padding(2)
     *     outer 4  ->  content 0   <- crash
     *     outer 5  ->  content 1
     *     outer 6  ->  content 2   <- chosen
     *
     * At content 0, rich's divide_line() calls chop_cells() with a step of
     * zero and raises `ValueError: range() arg 3 must not be zero` out of the
     * render, killing the app. Observed live on run
     * job_20260901-205047-40sp: the operator pressed pause, the button
     * restyled to .vcr-btn--paused, the render raised, and the Textual app
     * died while the flow engine thread carried on without it.
     *
     * 6 rather than 5 so a label glyph that a terminal treats as double-width
     * still fits. tests/test_vcr_transport_render.py pins this.
     */
    MacroNodeWorkshop .vcr-btn {
        min-width: 6;
        max-width: 6;
    }
    MacroNodeWorkshop .input-row {
        height: 3;
        layout: horizontal;
    }
    MacroNodeWorkshop .input-row Input {
        width: 90%;
    }
    MacroNodeWorkshop .input-row Button {
        width: 8%;
        min-width: 4;
    }
    MacroNodeWorkshop .btn-proceed-anyway {
        margin: 0 1;
    }
    MacroNodeWorkshop .hidden {
        display: none;
    }
    """

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._flow_steps: list[dict[str, Any]] = []
        self._flow_dict = FlowDictBuffer()
        self._tether_counter: int = 0
        self._pending_scatters: list[str] = []

    def compose(self) -> ComposeResult:
        yield Label("⚙  MacroNode Workshop", classes="workshop-title")

        # ── Node Catalog (tabbed: MacroNodes | Agents | Control) ──────
        yield NodeCatalog()

        # ── Topology Visualizer ───────────────────────────────────────
        yield TopologyVisualizer()

        # ── Topology Actions (legacy IDs) ─────────────────────────────
        with Horizontal(classes="topo-actions", id="flow-line-actions"):
            yield Button("Remove Last Node", variant="warning", id="btn-remove-last")
            yield Button("Clear Flow", variant="error", id="btn-clear-flow")
            yield Input(
                placeholder="Name Session...",
                id="main-name-session-input",
                classes="session-name-input",
                disabled=True,
            )

        # ── Active Flow Sequence (legacy flow-line) ───────────────────
        yield Label("Active Flow Sequence", id="active-flow-sequence-label")
        with Horizontal(classes="flow-controls", id="flow-line-container"):
            yield Button("⏸", id="btn-vcr", classes="vcr-btn vcr-btn--idle", disabled=True)
            with Horizontal(id="active-flow-sequence"):
                yield Static("No flow loaded.", classes="flow-seq-text")

        # ── Flow Controls (legacy IDs) ────────────────────────────────
        with Horizontal(classes="flow-controls"):
            yield Button("Launch Flow", variant="success", id="btn-launch-flow")
            yield Button("Stop Flow", variant="error", id="btn-stop-flow", disabled=True)
            yield Button("Resume Flow", variant="success", id="btn-resume-flow", disabled=True)
            yield Button("Rewind Flow", variant="warning", id="btn-rewind-flow", disabled=False)
            yield Button("Create Payload", variant="primary", id="btn-create-payload")
            yield Button("Session Manager", variant="primary", id="btn-session-manager")
            yield Button("Chat Studio", variant="default", id="btn-agent-chat")
            yield Button("File Cabinet", variant="warning", id="btn-file-cabinet")

        # ── Pre-flight Override + Context Injection (legacy IDs) ──────
        yield Button(
            "\u26a0 Proceed Anyway", id="btn-proceed-anyway",
            variant="warning", classes="btn-proceed-anyway hidden",
        )
        with Horizontal(classes="input-row"):
            yield Input(placeholder="Inject context to flow...", id="fe-input")
            yield Button("\u2197", id="btn-expand-input", variant="primary", classes="btn-icon")


    # ── Catalog Integration ───────────────────────────────────────────────

    @on(NodeAddRequested)
    def _handle_node_add(self, event: NodeAddRequested) -> None:
        """Add a node from the catalog to the topology."""
        step: dict[str, Any] = {
            "Node_ID": event.node_id,
            "type": event.node_type,
            "tether_id": "",
            "flow_line_id": "",
        }
        step.update(event.node_data)

        # Set default Next_Node
        if self._flow_steps:
            self._flow_steps[-1]["Next_Node"] = event.node_id
        step["Next_Node"] = "END"

        # ── Tether field defaults for CTRL_ nodes ────────────────────
        if event.node_id.startswith("CTRL_"):
            step.setdefault("config", {})

            if event.node_id.startswith("CTRL_SCATTER"):
                # ── Auto-assign a tether ID, through the one seam. Task 4d. ──
                #
                # This was `f"tether_{chr(96 + self._tether_counter)}"` — a private
                # generator giving `tether_a`, `tether_b`, ... It is replaced by
                # `tether.root_tether_id`, which the engine also reads, so the TUI and the
                # engine stop being two sources of tether IDs. That split is Principle 4's
                # named incident: a TUI building `NAME_{i}` while the engine built
                # `NAME_S{i}`, harmless while the TUI only drew them and wrong the moment
                # anything acted on what was drawn. A tether **is** acted on — it is what
                # the fan-in gather gate scopes by.
                #
                # The old scheme also had a real defect past 26, not merely an ugly name.
                # `chr(96 + n)` walks off the end of the alphabet: the 27th scatter in one
                # session produced `tether_{`, and the **28th produced `tether_|`** — a
                # tether containing a routing-target delimiter, which `parse_targets`
                # splits, so `Wait_For` would read one lane as two. `root_tether_id`
                # carries on into `AA`, `AB`, ... and is covered by a no-collision test.
                tether_id = root_tether_id(self._tether_counter)
                self._tether_counter += 1
                step["tether_id"] = tether_id
                step["config"].update({
                    "scatter_targets": [],
                    "scatter_mode": "full_copy",
                    "tether_id": tether_id,
                })
                self._pending_scatters.append(tether_id)
                logger.info("[Workshop] CTRL_SCATTER assigned tether_id=%s", tether_id)
                # Notify user to add a companion CTRL_MERGE
                self.post_message(
                    ScatterCompanionHint(tether_id=tether_id, scatter_node=event.node_id)
                )

            elif event.node_id.startswith("CTRL_MERGE"):
                # Auto-tether to most recent un-paired CTRL_SCATTER
                if self._pending_scatters:
                    tether_id = self._pending_scatters.pop()
                    step["tether_id"] = tether_id
                    step["config"]["tether_id"] = tether_id
                    step["config"]["merge_mode"] = "structured"
                    logger.info("[Workshop] CTRL_MERGE auto-tethered to %s", tether_id)
                else:
                    step["config"]["merge_mode"] = "structured"
                    logger.warning("[Workshop] CTRL_MERGE added with no pending SCATTER to tether")

            elif event.node_id.startswith("CTRL_CONCAT"):
                step["config"]["delimiter"] = "\n---\n"
                if self._pending_scatters:
                    tether_id = self._pending_scatters.pop()
                    step["tether_id"] = tether_id
                    step["config"]["tether_id"] = tether_id
                    logger.info("[Workshop] CTRL_CONCAT auto-tethered to %s", tether_id)
                else:
                    logger.warning("[Workshop] CTRL_CONCAT added with no pending SCATTER to tether")

            elif event.node_id.startswith("CTRL_BRANCH"):
                step["config"].update({
                    "keyword_map": {},
                    "default_target": "END",
                })
                if self._pending_scatters:
                    tether_id = self._pending_scatters.pop()
                    step["tether_id"] = tether_id
                    step["config"]["tether_id"] = tether_id
                    logger.info("[Workshop] CTRL_BRANCH auto-tethered to %s", tether_id)
                else:
                    logger.warning("[Workshop] CTRL_BRANCH added with no pending SCATTER to tether")

            elif event.node_id.startswith("CTRL_CONDITIONAL_ROUTE"):
                step["config"].update({
                    "route_vectors": ["structured", "keyword", "score", "fuzzy"],
                    "keyword_map": {},
                    "score_threshold": 0.7,
                    "default_target": "END",
                })

            elif event.node_id.startswith("CTRL_FILTER"):
                step["config"].update({
                    "strip_sections": [],
                    "max_chars": 0,
                    "regex_remove": "",
                })

            elif event.node_id.startswith("CTRL_CLEANUP"):
                step["config"].update({
                    "glob_patterns": ["*.tmp", "*.bak"],
                    "cleanup_dir": "",
                })

            # Store config in flow dict buffer
            self._flow_dict.set_node_config(event.node_id, step["config"])
            self._emit_dict_update()

        self._flow_steps.append(step)
        self._sync_visualizer()

        # Auto-register agent in flow dict buffer (non-CTRL_ nodes only)
        if event.node_type == "agent" and not event.node_id.startswith("CTRL_"):
            self._flow_dict.ensure_agent(event.node_id)
            self._emit_dict_update()

        logger.info("[Workshop] Added %s: %s", event.node_type, event.node_id)

    @on(CatalogSelectionChanged)
    def _handle_catalog_preview(self, event: CatalogSelectionChanged) -> None:
        """Forward catalog selection to parent for info panel population."""
        self.post_message(event)

    @on(TopologyNodeSelected)
    def _handle_topo_node_selected(self, event: TopologyNodeSelected) -> None:
        """Forward topology node selection."""
        self.post_message(event)

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

    def get_flow_dict(self) -> FlowDictBuffer:
        """Return the flow dict buffer."""
        return self._flow_dict

    def set_agent_override(self, agent_name: str, profile: dict[str, Any]) -> None:
        """Set an agent override in the flow dict buffer."""
        self._flow_dict.set_agent_profile(agent_name, profile)
        self._emit_dict_update()

    # Alias for consistency with NexusPlex callers
    update_agent_profile = set_agent_override

    def reset_flow_dict(self, session_name: str = "") -> None:
        """Reset the flow dict buffer (e.g., on Clear Flow)."""
        self._flow_dict = FlowDictBuffer(session_name=session_name)
        self._tether_counter = 0
        self._pending_scatters = []
        self._emit_dict_update()

    def load_flow_dict(self, buf: FlowDictBuffer) -> None:
        """Load an existing FlowDictBuffer (e.g., on Resume Session)."""
        self._flow_dict = buf
        self._emit_dict_update()

    def _emit_dict_update(self) -> None:
        """Post a dict-updated message with JSON preview."""
        self.post_message(WorkshopDictUpdated(self._flow_dict.to_json()))



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
