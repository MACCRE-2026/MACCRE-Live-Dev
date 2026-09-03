# ┌─────────────────────────────────────────────────────────────────────────────┐
# │  MACCREv2 Test Suite — Phase 6.12 Task C1: Multi-Active Visualizer           │
# └─────────────────────────────────────────────────────────────────────────────┘
"""
tests/test_topology_visualizer_multi_active.py
==============================================
Phase 6.12 Task C1 — the visualiser must show N nodes running at once.

``set_active_node`` marked the incoming node active **and demoted whatever was
already active to completed**. That is right for one-node-at-a-time execution and
actively wrong under a scatter: lane 2 starting would paint lane 1 as finished
while lane 1 was still mid-inference, so an 8-lane scatter would display a single
travelling dot and the operator would have no idea eight agents were running.

``mark_node_active`` / ``mark_node_finished`` separate the two events.

These tests drive the widget's state model directly rather than through a mounted
Textual app: ``_update_node_label`` and ``start_animation`` need a live DOM, so
they are stubbed. What is under test is the state machine and the derived
accessors, which is where the defect was.
"""
from __future__ import annotations

import inspect

import pytest

from maccre_tui.widgets.topology_visualizer import (
    NodeState,
    TopologyNodeData,
    TopologyVisualizer,
)


class HeadlessVisualizer(TopologyVisualizer):
    """A visualiser with the DOM-dependent parts neutralised.

    ``TopologyVisualizer.__init__`` is a Textual ``Widget.__init__``, which needs
    an active app for some operations, and ``_update_node_label`` walks the Tree.
    Bypassing construction keeps these tests to the state model.
    """

    def __init__(self) -> None:  # noqa: D107 - deliberately does not call super()
        self._topo_nodes: dict[str, TopologyNodeData] = {}
        self._tree_node_map: dict[str, object] = {}
        self._expand_states: dict[str, bool] = {}
        self._is_animating = False
        self._animation_frame = 0
        self._animation_timer = None
        self.label_updates: list[str] = []
        self.animation_starts = 0
        self.animation_stops = 0

    def _update_node_label(self, node_id: str) -> None:  # type: ignore[override]
        self.label_updates.append(node_id)

    def start_animation(self) -> None:  # type: ignore[override]
        self._is_animating = True
        self.animation_starts += 1

    def stop_animation(self) -> None:  # type: ignore[override]
        self._is_animating = False
        self.animation_stops += 1

    # ── helper ────────────────────────────────────────────────────────────────

    def seed(self, *node_ids: str) -> None:
        for node_id in node_ids:
            self._topo_nodes[node_id] = TopologyNodeData(node_id=node_id)
            self._tree_node_map[node_id] = object()


LANES = [f"AGENT_Lane{i}_S0" for i in range(8)]


@pytest.fixture()
def viz() -> HeadlessVisualizer:
    v = HeadlessVisualizer()
    v.seed("CTRL_SCATTER_S0", *LANES, "CTRL_MERGE_S0")
    return v


# ── The multi-active primitive ────────────────────────────────────────────────


class TestMarkNodeActive:
    def test_marks_the_node_active(self, viz: HeadlessVisualizer) -> None:
        viz.mark_node_active(LANES[0])
        assert viz._topo_nodes[LANES[0]].state is NodeState.ACTIVE

    def test_does_not_demote_an_already_active_node(
        self, viz: HeadlessVisualizer
    ) -> None:
        """The core C1 fix.

        ``set_active_node`` would have marked lane 0 completed here, while lane 0
        was still running.
        """
        viz.mark_node_active(LANES[0])
        viz.mark_node_active(LANES[1])
        assert viz._topo_nodes[LANES[0]].state is NodeState.ACTIVE
        assert viz._topo_nodes[LANES[1]].state is NodeState.ACTIVE

    def test_all_eight_lanes_can_be_active_together(
        self, viz: HeadlessVisualizer
    ) -> None:
        """Full scatter width lit simultaneously."""
        for lane in LANES:
            viz.mark_node_active(lane)
        assert viz.active_node_count == 8
        assert set(viz.active_nodes) == set(LANES)
        assert all(
            viz._topo_nodes[lane].state is NodeState.ACTIVE for lane in LANES
        )

    def test_repainting_the_label_is_requested(self, viz: HeadlessVisualizer) -> None:
        viz.mark_node_active(LANES[3])
        assert LANES[3] in viz.label_updates

    def test_unknown_node_is_ignored(self, viz: HeadlessVisualizer) -> None:
        """A step's DAG may not be rendered when its first callback fires."""
        viz.mark_node_active("NODE_THAT_DOES_NOT_EXIST")
        assert viz.active_node_count == 0
        assert viz.label_updates == []

    def test_starts_the_pulse_on_first_active_node(
        self, viz: HeadlessVisualizer
    ) -> None:
        assert viz._is_animating is False
        viz.mark_node_active(LANES[0])
        assert viz._is_animating is True
        assert viz.animation_starts == 1

    def test_does_not_restart_the_pulse_for_each_lane(
        self, viz: HeadlessVisualizer
    ) -> None:
        for lane in LANES:
            viz.mark_node_active(lane)
        assert viz.animation_starts == 1

    def test_a_dom_less_animation_failure_does_not_propagate(self) -> None:
        """Callbacks arrive from worker threads; the pulse is cosmetic."""

        class Unmountable(HeadlessVisualizer):
            def start_animation(self) -> None:
                raise RuntimeError("widget is not mounted")

        v = Unmountable()
        v.seed(LANES[0])
        v.mark_node_active(LANES[0])
        assert v._topo_nodes[LANES[0]].state is NodeState.ACTIVE


class TestMarkNodeFinished:
    def test_marks_the_node_completed(self, viz: HeadlessVisualizer) -> None:
        viz.mark_node_active(LANES[0])
        viz.mark_node_finished(LANES[0])
        assert viz._topo_nodes[LANES[0]].state is NodeState.COMPLETED

    def test_leaves_sibling_lanes_untouched(self, viz: HeadlessVisualizer) -> None:
        """Finishing lane 3 of 8 must not disturb the other seven."""
        for lane in LANES[:4]:
            viz.mark_node_active(lane)
        viz.mark_node_finished(LANES[2])

        assert viz._topo_nodes[LANES[2]].state is NodeState.COMPLETED
        assert viz.active_node_count == 3
        assert set(viz.active_nodes) == {LANES[0], LANES[1], LANES[3]}

    def test_accepts_a_terminal_state(self, viz: HeadlessVisualizer) -> None:
        viz.mark_node_active(LANES[0])
        viz.mark_node_finished(LANES[0], NodeState.FAILED)
        assert viz._topo_nodes[LANES[0]].state is NodeState.FAILED

    def test_pause_is_a_valid_terminal_state(self, viz: HeadlessVisualizer) -> None:
        """A HITL gate should read as paused, not completed."""
        viz.mark_node_active("CTRL_MERGE_S0")
        viz.mark_node_finished("CTRL_MERGE_S0", NodeState.PAUSED)
        assert viz._topo_nodes["CTRL_MERGE_S0"].state is NodeState.PAUSED

    def test_pulse_keeps_running_while_any_lane_is_active(
        self, viz: HeadlessVisualizer
    ) -> None:
        for lane in LANES[:3]:
            viz.mark_node_active(lane)
        viz.mark_node_finished(LANES[0])
        assert viz._is_animating is True
        assert viz.animation_stops == 0

    def test_pulse_stops_once_the_last_lane_finishes(
        self, viz: HeadlessVisualizer
    ) -> None:
        for lane in LANES[:3]:
            viz.mark_node_active(lane)
        for lane in LANES[:3]:
            viz.mark_node_finished(lane)
        assert viz._is_animating is False
        assert viz.animation_stops == 1

    def test_unknown_node_is_ignored(self, viz: HeadlessVisualizer) -> None:
        viz.mark_node_finished("NODE_THAT_DOES_NOT_EXIST")
        assert viz.label_updates == []

    def test_finishing_a_node_twice_is_harmless(self, viz: HeadlessVisualizer) -> None:
        """Callback delivery is best-effort; a duplicate must not corrupt state."""
        viz.mark_node_active(LANES[0])
        viz.mark_node_finished(LANES[0])
        viz.mark_node_finished(LANES[0])
        assert viz._topo_nodes[LANES[0]].state is NodeState.COMPLETED
        assert viz.active_node_count == 0


# ── Derived accessors ─────────────────────────────────────────────────────────


class TestActiveAccessors:
    def test_counts_are_zero_on_a_fresh_topology(self, viz: HeadlessVisualizer) -> None:
        assert viz.active_node_count == 0
        assert viz.active_nodes == []
        assert viz.active_node is None

    def test_active_nodes_preserves_topology_order(
        self, viz: HeadlessVisualizer
    ) -> None:
        """Order matters for a readout that lists what is running."""
        viz.mark_node_active(LANES[5])
        viz.mark_node_active(LANES[1])
        assert viz.active_nodes == [LANES[1], LANES[5]]

    def test_active_node_returns_one_of_the_active_lanes(
        self, viz: HeadlessVisualizer
    ) -> None:
        """Legacy single-node accessor stays usable under a scatter."""
        viz.mark_node_active(LANES[2])
        viz.mark_node_active(LANES[6])
        assert viz.active_node in (LANES[2], LANES[6])

    def test_count_tracks_the_full_scatter_lifecycle(
        self, viz: HeadlessVisualizer
    ) -> None:
        """The 1/8 -> 8/8 -> 1/8 shape the C2 readout displays."""
        viz.mark_node_active("CTRL_SCATTER_S0")
        assert viz.active_node_count == 1
        viz.mark_node_finished("CTRL_SCATTER_S0")

        for lane in LANES:
            viz.mark_node_active(lane)
        assert viz.active_node_count == 8

        for lane in LANES:
            viz.mark_node_finished(lane)
        viz.mark_node_active("CTRL_MERGE_S0")
        assert viz.active_node_count == 1

    def test_accessors_are_derived_not_a_parallel_set(self) -> None:
        """A second container would be a second thing to keep correct.

        ``_tick_animation`` and ``mark_all_completed`` read node state directly,
        so a set that drifted from it would leave a node pulsing forever.
        """
        source = inspect.getsource(TopologyVisualizer.active_nodes.fget)  # type: ignore[union-attr]
        assert "self._topo_nodes" in source
        assert "NodeState.ACTIVE" in source


# ── Compatibility wrapper ─────────────────────────────────────────────────────


class TestSetActiveNodeCompatibility:
    def test_still_demotes_the_previous_node(self, viz: HeadlessVisualizer) -> None:
        """Behaviour preserved for the per-step highlighting path."""
        viz.set_active_node(LANES[0])
        viz.set_active_node(LANES[1])
        assert viz._topo_nodes[LANES[0]].state is NodeState.COMPLETED
        assert viz._topo_nodes[LANES[1]].state is NodeState.ACTIVE
        assert viz.active_node_count == 1

    def test_demotes_every_active_node_not_just_one(
        self, viz: HeadlessVisualizer
    ) -> None:
        """If it is called after a scatter, it must not leave lanes stuck active."""
        for lane in LANES[:4]:
            viz.mark_node_active(lane)
        viz.set_active_node("CTRL_MERGE_S0")
        assert viz.active_nodes == ["CTRL_MERGE_S0"]

    def test_carries_a_warning_against_concurrent_use(self) -> None:
        """The docstring is the guard against reintroducing the defect."""
        doc = inspect.getdoc(TopologyVisualizer.set_active_node) or ""
        assert "mark_node_active" in doc
        assert "concurrency" in doc.lower()


# ── Existing behaviour that must survive ──────────────────────────────────────


class TestMarkAllCompleted:
    def test_clears_every_active_lane(self, viz: HeadlessVisualizer) -> None:
        for lane in LANES:
            viz.mark_node_active(lane)
        viz.mark_all_completed()
        assert viz.active_node_count == 0
        assert all(
            viz._topo_nodes[lane].state is NodeState.COMPLETED for lane in LANES
        )

    def test_stops_the_pulse(self, viz: HeadlessVisualizer) -> None:
        viz.mark_node_active(LANES[0])
        viz.mark_all_completed()
        assert viz._is_animating is False

    def test_preserves_a_failed_node(self, viz: HeadlessVisualizer) -> None:
        """A post-flow sweep must not paint over a real failure."""
        viz.mark_node_active(LANES[0])
        viz.mark_node_finished(LANES[0], NodeState.FAILED)
        viz.mark_all_completed()
        assert viz._topo_nodes[LANES[0]].state is NodeState.FAILED
