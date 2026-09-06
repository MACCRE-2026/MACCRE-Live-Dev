"""tests/test_tether_is_not_reparented.py
=========================================
Task 4c-2 — a node's tether is a property of the node, not of whoever routed to it.

Only the entry task is seeded. Every other ``task_queue`` row is created by its router,
and until now it was stamped with the **router's** tether. While one flat tether covered a
whole scatter that was correct by accident: the scatter, all eight lanes and the merge
shared one value, so it did not matter who wrote it.

The moment lanes carry their own tethers it is fatal. ``CTRL_MERGE`` is created by whichever
lane finishes first and would be stamped with *that lane's* tether; the gather gate then
looks for lanes whose group matches ``X.1`` and finds none, and the run deadlocks. That is
the register's named incident — a scatter and its merge in different scopes, an 8-lane run
that never gathered — and ``swarm_worker``'s own fan-out comment records the live symptom:
*"a wrong non-empty tether makes it check a scope the predecessors are not in — so the gate
matches zero rows and can never open."*

Requirement 31.7 states this rule for cross-lane routes, where
``topology_graph.apply_cross_lane_route`` refuses to re-parent. This is that rule applied to
ordinary routing.

`TestTheDeadlockThisPrevents` is the group that matters: it builds the exact scenario end to
end against a real broker, and it fails if `target_tethers` is dropped.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from maccre_core.orchestration.local_broker import (
    LocalMessageBroker,
    _resolve_target_tether,
)
from maccre_core.orchestration.tether import child_tether_ids, lane_group

JOB = "reparent-probe"
LANES = [f"AGENT_{c}" for c in "ABCDEFGH"]
MERGE = "CTRL_MERGE"


@pytest.fixture()
def broker(tmp_path: Path) -> Any:
    b = LocalMessageBroker(db_path=str(tmp_path / "swarm_queue.db"))
    yield b
    b.close()


def _seed(b: LocalMessageBroker, node: str, tether: str, status: str = "completed") -> int:
    conn = b._get_conn()
    cur = conn.execute(
        "INSERT INTO task_queue (job_id, payload_path, source_payload_path, current_node, "
        "loop_iteration_count, tether_id, lock_status) VALUES (?, ?, ?, ?, 0, ?, ?)",
        (JOB, f"/{node}.md", f"/{node}.md", node, tether, status),
    )
    conn.commit()
    return int(cur.lastrowid or 0)


def _tether_of(b: LocalMessageBroker, node: str) -> str:
    row = b._get_conn().execute(
        "SELECT tether_id FROM task_queue WHERE job_id = ? AND current_node = ?",
        (JOB, node),
    ).fetchone()
    return "" if row is None else str(row[0] or "")


# ── The resolver ─────────────────────────────────────────────────────────────


class TestResolveTargetTether:
    def test_the_targets_own_tether_wins(self) -> None:
        assert _resolve_target_tether("CTRL_MERGE", {"CTRL_MERGE": "X"}, "X.1") == "X"

    def test_it_falls_back_to_the_router_when_the_target_is_unknown(self) -> None:
        """The pre-2026-09-06 behaviour, preserved deliberately so this cannot regress
        a caller with no topology to consult."""
        assert _resolve_target_tether("CTRL_MERGE", {"OTHER": "Y"}, "X.1") == "X.1"

    def test_it_falls_back_when_no_mapping_is_given(self) -> None:
        assert _resolve_target_tether("CTRL_MERGE", None, "X.1") == "X.1"

    def test_an_empty_mapped_value_falls_back_rather_than_blanking(self) -> None:
        """"The topology does not say" and "the topology says empty" want the same
        fallback, so an empty entry must not blank the tether."""
        assert _resolve_target_tether("CTRL_MERGE", {"CTRL_MERGE": "  "}, "X.1") == "X.1"

    def test_an_empty_router_tether_is_still_returned_when_nothing_else_is_known(self) -> None:
        assert _resolve_target_tether("N", None, "") == ""


# ── The deadlock this prevents ───────────────────────────────────────────────


class TestTheDeadlockThisPrevents:
    """Eight lanes at `X.1`..`X.8` routing to one merge that must end up at `X`."""

    def test_the_merge_is_created_with_its_own_tether_not_the_first_lanes(
        self, broker: LocalMessageBroker
    ) -> None:
        """**The assertion 4c-2 exists for.**"""
        lanes = child_tether_ids("X", 8)
        row_id = _seed(broker, LANES[0], lanes[0], status="locked")

        broker.route_task(
            row_id=row_id,
            job_id=JOB,
            next_node_str=MERGE,
            new_payload_path="/lane_a.md",
            tether_id=lanes[0],                 # the router's own lane
            target_tethers={MERGE: "X"},        # what the topology says
        )

        assert _tether_of(broker, MERGE) == "X"

    def test_without_the_mapping_the_merge_inherits_the_lane_and_that_is_the_bug(
        self, broker: LocalMessageBroker
    ) -> None:
        """The defect, pinned as behaviour so the fallback stays understood.

        This is not an aspiration — it is what every route did before 4c-2, and it is
        why `target_tethers` has to be supplied rather than optional in practice.
        """
        lanes = child_tether_ids("X", 8)
        row_id = _seed(broker, LANES[0], lanes[0], status="locked")

        broker.route_task(
            row_id=row_id,
            job_id=JOB,
            next_node_str=MERGE,
            new_payload_path="/lane_a.md",
            tether_id=lanes[0],
        )

        assert _tether_of(broker, MERGE) == "X.1"
        assert lane_group("X.1") != "X.1", "and X.1's group is X, so the gate would miss it"

    def test_eight_lanes_all_agree_on_the_merges_tether(
        self, broker: LocalMessageBroker
    ) -> None:
        """Every lane routes to the same merge; the last writer must not change it."""
        lanes = child_tether_ids("X", 8)
        for node, lane in zip(LANES, lanes):
            row_id = _seed(broker, node, lane, status="locked")
            broker.route_task(
                row_id=row_id,
                job_id=JOB,
                next_node_str=MERGE,
                new_payload_path=f"/{node}.md",
                tether_id=lane,
                target_tethers={MERGE: "X"},
            )

        assert _tether_of(broker, MERGE) == "X"

    def test_the_gather_gate_then_opens_on_all_eight_lanes(
        self, broker: LocalMessageBroker
    ) -> None:
        """End to end: route eight lanes, then evaluate the merge's gate for real.

        This is the whole point. If the merge had inherited a lane's tether, the gate
        would find no lanes whose group matched and the run would deadlock.
        """
        lanes = child_tether_ids("X", 8)
        for node, lane in zip(LANES, lanes):
            row_id = _seed(broker, node, lane, status="locked")
            broker.route_task(
                row_id=row_id,
                job_id=JOB,
                next_node_str=MERGE,
                new_payload_path=f"/{node}.md",
                tether_id=lane,
                target_tethers={MERGE: "X"},
                output_path=f"/{node}_out.md",
            )

        cursor = broker._get_conn().cursor()
        task = {"job_id": JOB, "current_node": MERGE, "tether_id": _tether_of(broker, MERGE)}

        assert broker._gather_gate_state(cursor, task, "|".join(LANES)) == "ready"

    def test_the_merge_collects_eight_distinct_lane_outputs(
        self, broker: LocalMessageBroker
    ) -> None:
        """Defect E1's shape, now through per-lane tethers."""
        lanes = child_tether_ids("X", 8)
        for node, lane in zip(LANES, lanes):
            row_id = _seed(broker, node, lane, status="locked")
            broker.route_task(
                row_id=row_id,
                job_id=JOB,
                next_node_str=MERGE,
                new_payload_path="/shared_ledger.md",
                tether_id=lane,
                target_tethers={MERGE: "X"},
                output_path=f"/{node}_out.md",
            )

        found = broker.get_completed_payload_paths(JOB, LANES, "X")

        assert len(found) == 8
        assert len(set(found.values())) == 8


# ── The flat model must be untouched ─────────────────────────────────────────


class TestTheFlatModelIsUnchanged:
    """Every topology on disk routes without `target_tethers`. Nothing may move."""

    def test_a_flat_scatter_still_stamps_one_tether_everywhere(
        self, broker: LocalMessageBroker
    ) -> None:
        flat = "scatter_84fe89ba"
        for node in LANES:
            row_id = _seed(broker, node, flat, status="locked")
            broker.route_task(
                row_id=row_id,
                job_id=JOB,
                next_node_str=MERGE,
                new_payload_path=f"/{node}.md",
                tether_id=flat,
            )

        assert _tether_of(broker, MERGE) == flat

    def test_a_flat_scatters_gate_still_opens(self, broker: LocalMessageBroker) -> None:
        flat = "scatter_84fe89ba"
        for node in LANES:
            row_id = _seed(broker, node, flat, status="locked")
            broker.route_task(
                row_id=row_id, job_id=JOB, next_node_str=MERGE,
                new_payload_path=f"/{node}.md", tether_id=flat,
                output_path=f"/{node}_out.md",
            )

        cursor = broker._get_conn().cursor()
        task = {"job_id": JOB, "current_node": MERGE, "tether_id": flat}

        assert broker._gather_gate_state(cursor, task, "|".join(LANES)) == "ready"

    def test_a_tetherless_linear_flow_still_routes_with_no_tether(
        self, broker: LocalMessageBroker
    ) -> None:
        row_id = _seed(broker, "NODE_01", "", status="locked")

        broker.route_task(
            row_id=row_id, job_id=JOB, next_node_str="NODE_02",
            new_payload_path="/p.md",
        )

        assert _tether_of(broker, "NODE_02") == ""

    def test_a_terminal_sentinel_still_creates_no_row(
        self, broker: LocalMessageBroker
    ) -> None:
        row_id = _seed(broker, "NODE_01", "X.1", status="locked")

        broker.route_task(
            row_id=row_id, job_id=JOB, next_node_str="END",
            new_payload_path="/p.md", tether_id="X.1", target_tethers={"END": "X"},
        )

        assert _tether_of(broker, "END") == "", "no row should exist for a sentinel"


# ── Fan-out gives each lane its own tether ───────────────────────────────────


class TestFanOutStampsEachLane:
    def test_a_scatter_stamps_each_lane_with_its_own_tether(
        self, broker: LocalMessageBroker
    ) -> None:
        """What 4c-3 will rely on: the scatter routes to eight lanes, each getting its own."""
        lanes = child_tether_ids("X", 8)
        mapping = dict(zip(LANES, lanes))
        row_id = _seed(broker, "CTRL_SCATTER", "X", status="locked")

        for node in LANES:
            broker.route_task(
                row_id=row_id, job_id=JOB, next_node_str=node,
                new_payload_path="/scattered.md", tether_id="X",
                target_tethers=mapping,
            )

        assert [_tether_of(broker, node) for node in LANES] == lanes

    def test_every_stamped_lane_gathers_back_at_the_scatter(
        self, broker: LocalMessageBroker
    ) -> None:
        lanes = child_tether_ids("X", 8)
        mapping = dict(zip(LANES, lanes))
        row_id = _seed(broker, "CTRL_SCATTER", "X", status="locked")
        for node in LANES:
            broker.route_task(
                row_id=row_id, job_id=JOB, next_node_str=node,
                new_payload_path="/scattered.md", tether_id="X",
                target_tethers=mapping,
            )

        for node in LANES:
            assert lane_group(_tether_of(broker, node)) == "X"


# ── The worker resolves the mapping from the topology ────────────────────────


class FakeTopology:
    def __init__(self, configs: dict[str, dict[str, Any]]) -> None:
        self._configs = configs

    def get_node_config(self, node_id: str) -> dict[str, Any]:
        if node_id not in self._configs:
            raise KeyError(node_id)
        return self._configs[node_id]


class TestWorkerTargetTetherResolution:
    """`_target_tethers` reads the topology, so the value cannot be the router's by
    accident."""

    @staticmethod
    def _worker(topo: Any) -> Any:
        from maccre_core.orchestration.swarm_worker import UniversalSwarmWorker

        w = object.__new__(UniversalSwarmWorker)
        w.topology = topo  # type: ignore[attr-defined]
        return w

    def test_it_resolves_each_target(self) -> None:
        w = self._worker(FakeTopology({
            "A": {"tether_id": "X.1"},
            "B": {"tether_id": "X.2"},
        }))

        assert w._target_tethers("A|B") == {"A": "X.1", "B": "X.2"}

    def test_it_accepts_both_delimiters(self) -> None:
        w = self._worker(FakeTopology({"A": {"tether_id": "X.1"}, "B": {"tether_id": "X.2"}}))

        assert w._target_tethers("A,B") == w._target_tethers("A|B")

    def test_an_unknown_target_is_absent_rather_than_guessed(self) -> None:
        """So `_resolve_target_tether` falls back, which is the old behaviour."""
        w = self._worker(FakeTopology({"A": {"tether_id": "X.1"}}))

        assert w._target_tethers("A|END") == {"A": "X.1"}

    def test_an_empty_topology_tether_is_omitted(self) -> None:
        w = self._worker(FakeTopology({"A": {"tether_id": "  "}}))

        assert w._target_tethers("A") == {}

    def test_no_topology_yields_no_mapping(self) -> None:
        assert self._worker(None)._target_tethers("A|B") == {}

    def test_a_raising_topology_does_not_break_routing(self) -> None:
        """Routing must not fail because a lookup did."""
        class Exploding:
            def get_node_config(self, node_id: str) -> dict[str, Any]:
                raise RuntimeError("topology unavailable")

        assert self._worker(Exploding())._target_tethers("A|B") == {}

    def test_an_empty_target_string_yields_no_mapping(self) -> None:
        assert self._worker(FakeTopology({}))._target_tethers("") == {}
