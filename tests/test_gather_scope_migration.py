"""tests/test_gather_scope_migration.py
=======================================
Task 4c-1 — the gather gate reads through ``tether.in_gather_scope``.

**The point of this file is that it runs against a real ``LocalMessageBroker``, not a
stub.** ``test_tether.py`` proves ``in_gather_scope`` is the right rule; this proves the
broker applies it, and that an 8-lane gather closes both ways:

* with the **flat** tether the engine writes today — the migration must change nothing
* with the **hierarchical** per-lane tethers 4c-3 will write — the capability must work

The reason it is worth an integration test rather than a unit test is the failure mode.
If the scope rule is wrong, the gather gate never opens; the task stays ``open``, the pool
spawns workers that cannot claim it and each retires idle, and the run burns its
wall-clock budget with nothing in the log explaining why. That is the named Principle 2
incident — a blanked tether id put a scatter and its merge in different scopes and an
8-lane run deadlocked — and it is invisible to a stubbed test.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from maccre_core.orchestration.local_broker import LocalMessageBroker
from maccre_core.orchestration.tether import child_tether_ids

JOB = "gather-scope-probe"
LANE_NODES = [f"AGENT_{c}" for c in "ABCDEFGH"]
MERGE = "CTRL_MERGE"
LEGACY_TETHER = "scatter_84fe89ba"


class FakeTopology:
    """node_id -> wait_for string, the shape the broker asks for."""

    def __init__(self, wait_for: dict[str, str]) -> None:
        self._wait_for = wait_for

    def get_node_config(self, node_id: str) -> dict[str, Any]:
        if node_id not in self._wait_for:
            raise KeyError(node_id)
        return {"wait_for": self._wait_for[node_id]}


@pytest.fixture()
def broker(tmp_path: Path) -> Any:
    b = LocalMessageBroker(db_path=str(tmp_path / "swarm_queue.db"))
    yield b
    b.close()


def _seed(b: LocalMessageBroker, node: str, tether: str, status: str) -> None:
    """Insert one task_queue row directly, so the test controls the tethers exactly."""
    conn = b._get_conn()
    conn.execute(
        "INSERT INTO task_queue (job_id, payload_path, source_payload_path, current_node, "
        "loop_iteration_count, tether_id, lock_status) VALUES (?, ?, ?, ?, 0, ?, ?)",
        (JOB, f"/{node}.md", f"/{node}.md", node, tether, status),
    )
    conn.commit()


def _gate(b: LocalMessageBroker, merge_tether: str) -> str:
    """Evaluate the merge's gather gate as the broker itself would."""
    conn = b._get_conn()
    cursor = conn.cursor()
    task = {"job_id": JOB, "current_node": MERGE, "tether_id": merge_tether}
    return b._gather_gate_state(cursor, task, "|".join(LANE_NODES))


# ── The migration: the flat tether the engine writes today ───────────────────


class TestTheFlatTetherStillGathers:
    """If any of these break, every saved topology breaks. This is the licence for 4c-1."""

    def test_eight_flat_lanes_open_the_gate(self, broker: LocalMessageBroker) -> None:
        for node in LANE_NODES:
            _seed(broker, node, LEGACY_TETHER, "completed")

        assert _gate(broker, LEGACY_TETHER) == "ready"

    def test_seven_of_eight_keeps_the_gate_shut(self, broker: LocalMessageBroker) -> None:
        """The negative case. A gate that opens on partial completion is worse than none."""
        for node in LANE_NODES[:-1]:
            _seed(broker, node, LEGACY_TETHER, "completed")
        _seed(broker, LANE_NODES[-1], LEGACY_TETHER, "open")

        assert _gate(broker, LEGACY_TETHER) == "waiting"

    def test_a_failed_lane_is_reported_as_upstream_failed(
        self, broker: LocalMessageBroker
    ) -> None:
        for node in LANE_NODES[:-1]:
            _seed(broker, node, LEGACY_TETHER, "completed")
        _seed(broker, LANE_NODES[-1], LEGACY_TETHER, "failed")

        assert _gate(broker, LEGACY_TETHER) == "upstream_failed"

    def test_another_scatters_lanes_do_not_open_this_gate(
        self, broker: LocalMessageBroker
    ) -> None:
        """Why the gate is tether-scoped at all."""
        for node in LANE_NODES:
            _seed(broker, node, "scatter_ffffffff", "completed")

        assert _gate(broker, LEGACY_TETHER) == "waiting"


# ── The capability: per-lane hierarchical tethers, as 4c-3 will write them ────


class TestHierarchicalLanesGather:
    """What the flat scheme could not express: lane identity *and* one gather scope."""

    def test_eight_hierarchical_lanes_open_the_root_merges_gate(
        self, broker: LocalMessageBroker
    ) -> None:
        """**The assertion 4c-1 exists for.** Merge at `X`, lanes at `X.1`..`X.8`."""
        for node, lane in zip(LANE_NODES, child_tether_ids("X", 8)):
            _seed(broker, node, lane, "completed")

        assert _gate(broker, "X") == "ready"

    def test_seven_hierarchical_lanes_keep_it_shut(self, broker: LocalMessageBroker) -> None:
        lanes = child_tether_ids("X", 8)
        for node, lane in zip(LANE_NODES[:-1], lanes[:-1]):
            _seed(broker, node, lane, "completed")
        _seed(broker, LANE_NODES[-1], lanes[-1], "open")

        assert _gate(broker, "X") == "waiting"

    def test_lanes_of_a_different_root_do_not_open_it(
        self, broker: LocalMessageBroker
    ) -> None:
        for node, lane in zip(LANE_NODES, child_tether_ids("Y", 8)):
            _seed(broker, node, lane, "completed")

        assert _gate(broker, "X") == "waiting"

    def test_a_nested_merge_gathers_its_own_lanes(self, broker: LocalMessageBroker) -> None:
        """Merge at `X.1` gathering `X.1.1`..`X.1.4`, with `X.2`'s lanes also present."""
        inner = child_tether_ids("X.1", 4)
        for node, lane in zip(LANE_NODES[:4], inner):
            _seed(broker, node, lane, "completed")
        for node, lane in zip(LANE_NODES[4:], child_tether_ids("X.2", 4)):
            _seed(broker, node, lane, "completed")

        conn = broker._get_conn()
        task = {"job_id": JOB, "current_node": "CTRL_MERGE_INNER", "tether_id": "X.1"}
        state = broker._gather_gate_state(conn.cursor(), task, "|".join(LANE_NODES[:4]))

        assert state == "ready"

    def test_lane_ten_does_not_satisfy_lane_ones_gate(
        self, broker: LocalMessageBroker
    ) -> None:
        """The prefix trap, against a real database. `X.10` is not inside `X.1`."""
        _seed(broker, LANE_NODES[0], "X.10", "completed")

        conn = broker._get_conn()
        task = {"job_id": JOB, "current_node": "CTRL_MERGE_INNER", "tether_id": "X.1"}
        state = broker._gather_gate_state(conn.cursor(), task, LANE_NODES[0])

        assert state == "waiting"


# ── The other two call sites ─────────────────────────────────────────────────


class TestCompletedPayloadPathsRespectScope:
    """`get_completed_payload_paths` feeds the merge its inputs — E1's territory."""

    def test_flat_lanes_are_all_collected(self, broker: LocalMessageBroker) -> None:
        for node in LANE_NODES:
            _seed(broker, node, LEGACY_TETHER, "completed")

        found = broker.get_completed_payload_paths(JOB, LANE_NODES, LEGACY_TETHER)

        assert len(found) == 8

    def test_hierarchical_lanes_are_all_collected_by_the_root(
        self, broker: LocalMessageBroker
    ) -> None:
        """Eight lanes, eight **distinct** paths — the shape E1's fix demands."""
        for node, lane in zip(LANE_NODES, child_tether_ids("X", 8)):
            _seed(broker, node, lane, "completed")

        found = broker.get_completed_payload_paths(JOB, LANE_NODES, "X")

        assert len(found) == 8
        assert len(set(found.values())) == 8

    def test_another_scatters_lanes_are_excluded(self, broker: LocalMessageBroker) -> None:
        for node, lane in zip(LANE_NODES, child_tether_ids("Y", 8)):
            _seed(broker, node, lane, "completed")

        assert broker.get_completed_payload_paths(JOB, LANE_NODES, "X") == {}

    def test_an_empty_scope_collects_everything(self, broker: LocalMessageBroker) -> None:
        """Unchanged: the old query only added the filter `if tether_id`."""
        for node, lane in zip(LANE_NODES, child_tether_ids("X", 8)):
            _seed(broker, node, lane, "completed")

        assert len(broker.get_completed_payload_paths(JOB, LANE_NODES, "")) == 8


class TestCompletedByTetherRespectsScope:
    def test_flat_lanes_are_returned(self, broker: LocalMessageBroker) -> None:
        for node in LANE_NODES:
            _seed(broker, node, LEGACY_TETHER, "completed")

        assert len(broker.get_completed_by_tether(JOB, LEGACY_TETHER)) == 8

    def test_hierarchical_lanes_are_returned_for_the_root(
        self, broker: LocalMessageBroker
    ) -> None:
        for node, lane in zip(LANE_NODES, child_tether_ids("X", 8)):
            _seed(broker, node, lane, "completed")

        assert len(broker.get_completed_by_tether(JOB, "X")) == 8

    def test_open_rows_are_not_returned(self, broker: LocalMessageBroker) -> None:
        """It is `get_*completed*_by_tether`; the scope change must not widen the status."""
        for node, lane in zip(LANE_NODES, child_tether_ids("X", 8)):
            _seed(broker, node, lane, "open")

        assert broker.get_completed_by_tether(JOB, "X") == []

    def test_another_roots_lanes_are_excluded(self, broker: LocalMessageBroker) -> None:
        for node, lane in zip(LANE_NODES, child_tether_ids("Y", 8)):
            _seed(broker, node, lane, "completed")

        assert broker.get_completed_by_tether(JOB, "X") == []


# ── The sizing hint must keep mirroring the gate ─────────────────────────────


class TestCountReadyTasksStillMirrorsTheGate:
    """`count_ready_tasks` shares `_gather_gate_state`, and must keep sharing it.

    Two copies of the gather rule is how the pool came to size itself against a
    different notion of readiness than the claim path used.
    """

    def test_a_merge_whose_lanes_completed_counts_as_ready(
        self, broker: LocalMessageBroker
    ) -> None:
        for node, lane in zip(LANE_NODES, child_tether_ids("X", 8)):
            _seed(broker, node, lane, "completed")
        _seed(broker, MERGE, "X", "open")

        topo = FakeTopology({MERGE: "|".join(LANE_NODES)})

        assert broker.count_ready_tasks(JOB, topology_engine=topo) == 1

    def test_a_merge_whose_lanes_are_outstanding_counts_as_not_ready(
        self, broker: LocalMessageBroker
    ) -> None:
        lanes = child_tether_ids("X", 8)
        for node, lane in zip(LANE_NODES[:-1], lanes[:-1]):
            _seed(broker, node, lane, "completed")
        _seed(broker, LANE_NODES[-1], lanes[-1], "open")
        _seed(broker, MERGE, "X", "open")

        topo = FakeTopology({MERGE: "|".join(LANE_NODES), LANE_NODES[-1]: "none"})

        # The outstanding lane is itself claimable; the merge is not.
        assert broker.count_ready_tasks(JOB, topology_engine=topo) == 1
