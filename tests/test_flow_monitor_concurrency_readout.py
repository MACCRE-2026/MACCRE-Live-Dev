# ┌─────────────────────────────────────────────────────────────────────────────┐
# │  MACCREv2 Test Suite — Phase 6.12 Tasks C2 + C3: Concurrency Readout         │
# └─────────────────────────────────────────────────────────────────────────────┘
"""
tests/test_flow_monitor_concurrency_readout.py
==============================================
Phase 6.12 Tasks C2 and C3 — the operator has to be able to see the parallelism.

C2 gives ``FlowMonitorOverlay`` an ``N/cap active`` readout. The monitor
previously had a single "current node" line, which cannot describe eight agents
running at once: watching an 8-lane scatter you would see one name and no
indication anything was parallel.

C3 wires the engine's per-node callbacks through both TUI launch paths so the
readout and the visualiser actually receive events.

``pyrightconfig.json`` **excludes** ``maccre_tui``, so TUI code gets ruff but no
type checking from ``omni qa``. These tests are the only real verification this
layer has, which is why they include import and wiring guards as well as
behaviour.
"""
from __future__ import annotations

import inspect
from pathlib import Path

import pytest

from maccre_core.orchestration.concurrency import MAX_SCATTER_AGENTS
from maccre_tui.widgets.flow_monitor_overlay import FlowMonitorOverlay

REPO_ROOT = Path(__file__).resolve().parent.parent


class FakeLabel:
    """Captures the markup written to a Textual Label."""

    def __init__(self) -> None:
        self.text = ""

    def update(self, text: str) -> None:
        self.text = text


class HeadlessMonitor(FlowMonitorOverlay):
    """A monitor with the DOM replaced by a dict of fake labels.

    ``FlowMonitorOverlay.__init__`` is a Textual container constructor and
    ``query_one`` needs a mounted app, so both are bypassed. What is under test is
    the readout logic.
    """

    def __init__(self) -> None:  # noqa: D107 - deliberately does not call super()
        self._completed = 0
        self._total = 0
        self._active_nodes: list[str] = []
        self._concurrency_cap = 1
        self.labels: dict[str, FakeLabel] = {
            "#monitor-node-info": FakeLabel(),
            "#monitor-stage-readout": FakeLabel(),
            "#monitor-progress-label": FakeLabel(),
        }
        self._hidden = False

    def query_one(self, selector: str, _widget_type: object = None) -> object:  # type: ignore[override]
        if selector in self.labels:
            return self.labels[selector]
        raise LookupError(selector)

    def has_class(self, name: str) -> bool:  # type: ignore[override]
        return self._hidden and name == "hidden"

    @property
    def node_info(self) -> str:
        return self.labels["#monitor-node-info"].text


LANES = [f"AGENT_Lane{i}_S0" for i in range(8)]


@pytest.fixture()
def monitor() -> HeadlessMonitor:
    return HeadlessMonitor()


# ── C2: the readout ───────────────────────────────────────────────────────────


class TestConcurrencyReadout:
    def test_reports_count_over_cap(self, monitor: HeadlessMonitor) -> None:
        monitor.update_concurrency(LANES[:3], cap=8)
        assert "3/8 active" in monitor.node_info

    def test_full_width_reads_eight_of_eight(self, monitor: HeadlessMonitor) -> None:
        """The reading that says the Phase 6.12 deliverable is working."""
        monitor.update_concurrency(LANES, cap=8)
        assert "8/8 active" in monitor.node_info

    def test_single_node_reads_one_and_names_it(
        self, monitor: HeadlessMonitor
    ) -> None:
        monitor.update_concurrency([LANES[0]], cap=8)
        assert "1/8 active" in monitor.node_info
        assert LANES[0] in monitor.node_info

    def test_idle_reads_zero_with_a_placeholder(
        self, monitor: HeadlessMonitor
    ) -> None:
        monitor.update_concurrency([], cap=8)
        assert "0/8 active" in monitor.node_info
        assert "—" in monitor.node_info

    def test_full_width_is_coloured_green(self, monitor: HeadlessMonitor) -> None:
        monitor.update_concurrency(LANES, cap=8)
        assert "bold green" in monitor.node_info

    def test_partial_width_is_coloured_amber(self, monitor: HeadlessMonitor) -> None:
        """Visually distinguishes "ramping" from "at full width"."""
        monitor.update_concurrency(LANES[:4], cap=8)
        assert "#ffa657" in monitor.node_info

    def test_idle_is_dim(self, monitor: HeadlessMonitor) -> None:
        monitor.update_concurrency([], cap=8)
        assert "[dim]" in monitor.node_info

    def test_long_lane_lists_are_truncated(self, monitor: HeadlessMonitor) -> None:
        """A 12-wide scatter would otherwise wrap the line badly."""
        monitor.update_concurrency(LANES, cap=8)
        assert "+5 more" in monitor.node_info
        assert LANES[0] in monitor.node_info
        assert LANES[7] not in monitor.node_info

    def test_three_lanes_are_all_named(self, monitor: HeadlessMonitor) -> None:
        monitor.update_concurrency(LANES[:3], cap=8)
        for lane in LANES[:3]:
            assert lane in monitor.node_info
        assert "more" not in monitor.node_info

    def test_cap_is_never_zero(self, monitor: HeadlessMonitor) -> None:
        """A 0 cap would render "0/0" and divide-by-zero any future percentage."""
        monitor.update_concurrency([], cap=0)
        assert "0/1 active" in monitor.node_info

    def test_count_over_cap_still_renders(self, monitor: HeadlessMonitor) -> None:
        """Defensive: the readout must not lie or crash if accounting drifts."""
        monitor.update_concurrency(LANES, cap=4)
        assert "8/4 active" in monitor.node_info

    def test_active_count_is_exposed(self, monitor: HeadlessMonitor) -> None:
        monitor.update_concurrency(LANES[:5], cap=8)
        assert monitor.active_node_count == 5

    def test_the_scatter_lifecycle_is_visible(self, monitor: HeadlessMonitor) -> None:
        """1/8 -> 8/8 -> 1/8, the shape an operator should see."""
        readings: list[str] = []
        monitor.update_concurrency(["CTRL_SCATTER_S0"], cap=8)
        readings.append(monitor.node_info)
        monitor.update_concurrency(LANES, cap=8)
        readings.append(monitor.node_info)
        monitor.update_concurrency(["CTRL_MERGE_S0"], cap=8)
        readings.append(monitor.node_info)

        assert "1/8 active" in readings[0]
        assert "8/8 active" in readings[1]
        assert "1/8 active" in readings[2]

    def test_a_missing_label_does_not_raise(self, monitor: HeadlessMonitor) -> None:
        """Readout updates arrive during teardown too; they must never raise."""
        monitor.labels.clear()
        monitor.update_concurrency(LANES[:2], cap=8)

    def test_set_current_node_clears_the_multi_list(
        self, monitor: HeadlessMonitor
    ) -> None:
        """The per-step path takes the label back for a single-node step."""
        monitor.update_concurrency(LANES, cap=8)
        monitor.set_current_node("AGENT_Solo_S1", "Solo", "gemini-2.5-flash")
        assert monitor.active_node_count == 0
        assert "AGENT_Solo_S1" in monitor.node_info
        assert "active" not in monitor.node_info


# ── C3: callback wiring ───────────────────────────────────────────────────────


class TestNexusPlexWiring:
    """Source guards. The TUI is not type-checked, so wiring is verified textually."""

    @staticmethod
    def _nexus_source() -> str:
        return (REPO_ROOT / "maccre_tui" / "nexus_plex.py").read_text(encoding="utf-8")

    def test_both_launch_paths_pass_the_node_callbacks(self) -> None:
        """execute_flow and resume_flow are separate call sites — both must wire."""
        source = self._nexus_source()
        assert source.count("node_active_callback=_on_node_active") == 2
        assert source.count("node_finished_callback=_on_node_finished") == 2

    def test_both_paths_define_the_handlers(self) -> None:
        source = self._nexus_source()
        assert source.count("def _on_node_active(") == 2
        assert source.count("def _on_node_finished(") == 2

    def test_handlers_marshal_onto_the_tui_thread(self) -> None:
        """Engine callbacks fire from worker threads.

        Textual widgets may only be touched from the app's own thread, so every
        handler has to hop via ``call_from_thread``.
        """
        source = self._nexus_source()
        assert "self.call_from_thread(self._mark_node_active" in source
        assert "self.call_from_thread(self._mark_node_finished" in source

    def test_the_app_defines_the_marshalled_targets(self) -> None:
        source = self._nexus_source()
        assert "def _mark_node_active(" in source
        assert "def _mark_node_finished(" in source
        assert "def _sync_concurrency_readout(" in source

    def test_marked_nodes_use_the_multi_active_api(self) -> None:
        """Not ``set_active_node``, which would demote sibling lanes."""
        source = self._nexus_source()
        assert ".mark_node_active(node_id)" in source
        assert ".mark_node_finished(node_id)" in source

    def test_readout_is_derived_from_the_visualizer(self) -> None:
        """One source of truth for what is running, not two counters."""
        source = self._nexus_source()
        sync_start = source.index("def _sync_concurrency_readout(")
        sync_body = source[sync_start : sync_start + 1400]
        assert "viz.active_nodes" in sync_body
        assert "monitor.update_concurrency(active, MAX_SCATTER_AGENTS)" in sync_body

    def test_the_readout_cap_is_the_shared_constant(self) -> None:
        source = self._nexus_source()
        assert (
            "from maccre_core.orchestration.concurrency import MAX_SCATTER_AGENTS"
            in source
        )
        assert MAX_SCATTER_AGENTS == 8

    def test_node_handlers_swallow_widget_errors(self) -> None:
        """A missing widget must not fail the node being reported."""
        source = self._nexus_source()
        for name in ("_mark_node_active", "_mark_node_finished"):
            start = source.index(f"def {name}(")
            body = source[start : start + 900]
            assert "except Exception:" in body, f"{name} does not guard widget access"

    def test_per_step_highlight_still_uses_the_single_active_api(self) -> None:
        """The per-step path is unchanged; only per-node updates are new."""
        source = self._nexus_source()
        start = source.index("def _highlight_active_node(")
        body = source[start : start + 1200]
        assert "viz.set_active_node(macronode_name)" in body


class TestFlowEngineExposesTheCallbacks:
    """The engine side of the C3 contract."""

    def test_both_entry_points_accept_the_callbacks(self) -> None:
        from maccre_core.orchestration.flow_engine import FlowRunner

        for method in (FlowRunner.execute_flow, FlowRunner.resume_flow):
            params = inspect.signature(method).parameters
            assert "node_active_callback" in params
            assert "node_finished_callback" in params
            assert params["node_active_callback"].default is None
            assert params["node_finished_callback"].default is None

    def test_the_worker_fires_them_with_step_node_and_slot(self) -> None:
        """The readout needs the node id; the slot identifies which lane."""
        from maccre_core.orchestration.swarm_worker import UniversalSwarmWorker

        source = inspect.getsource(UniversalSwarmWorker._fire_lifecycle)
        assert "parse_step_index(node_id), node_id, self.slot" in source
