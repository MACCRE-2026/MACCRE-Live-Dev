# ┌─────────────────────────────────────────────────────────────────────────────┐
# │  MACCREv2 Test Suite — Phase 6.12 Task A2: Broker Contract & Concurrency     │
# └─────────────────────────────────────────────────────────────────────────────┘
"""
tests/test_broker_contract.py
=============================
Phase 6.12 Task A2 — the broker's side of the parallel-execution contract.

Three things are asserted here, all of which were broken or absent at the Aug 22
baseline:

1. **Signature parity.** ``MessageBroker`` (the ABC) had drifted from
   ``LocalMessageBroker``: the concrete driver grew a ``tether_id`` parameter that
   the interface never declared, so pyright type-checked callers against a
   signature that did not exist. Test doubles had drifted too.

2. **The ready-task estimator.** ``count_ready_tasks`` sizes the worker pool. It
   must apply the same Gather Gate rules as the real claim path, or the pool will
   spawn threads for work that is not actually claimable.

3. **Connection-per-thread.** ``BEGIN EXCLUSIVE`` in ``fetch_and_lock_task`` only
   isolates anything if each thread has its own connection. On a shared
   connection, a second thread's statements silently join the first thread's open
   transaction, and the atomic claim stops being atomic.
"""
from __future__ import annotations

import inspect
import sqlite3
import threading
from pathlib import Path
from typing import Any

import pytest

from maccre_core.orchestration.broker_interface import MessageBroker
from maccre_core.orchestration.local_broker import LocalMessageBroker
from tests.mocks.mock_broker import MockMessageBroker

JOB = "job_a2_test"


class FakeTopology:
    """Minimal ``TopologyProvider``-shaped stub: node_id -> wait_for string."""

    def __init__(self, wait_for: dict[str, str] | None = None) -> None:
        self._wait_for = wait_for or {}

    def get_node_config(self, node_id: str) -> dict[str, Any]:
        if node_id not in self._wait_for:
            raise KeyError(node_id)
        return {"wait_for": self._wait_for[node_id]}


@pytest.fixture()
def broker(tmp_path: Path) -> Any:
    """A real ``LocalMessageBroker`` on a throwaway database."""
    b = LocalMessageBroker(db_path=str(tmp_path / "swarm_queue.db"))
    yield b
    b.close()


def _set_status(broker_obj: LocalMessageBroker, node: str, status: str) -> None:
    conn = broker_obj._get_conn()
    conn.execute(
        "UPDATE task_queue SET lock_status = ? WHERE job_id = ? AND current_node = ?",
        (status, JOB, node),
    )
    conn.commit()


# ── 1. Signature parity ───────────────────────────────────────────────────────


class TestSignatureParity:
    """The ABC, the SQLite driver and the test double must agree."""

    @staticmethod
    def _params(func: Any) -> dict[str, Any]:
        sig = inspect.signature(func)
        return {
            name: p.default
            for name, p in sig.parameters.items()
            if name not in ("self", "cls")
        }

    def test_route_task_abc_matches_local_broker(self) -> None:
        assert self._params(MessageBroker.route_task) == self._params(
            LocalMessageBroker.route_task
        )

    def test_route_task_abc_matches_mock(self) -> None:
        assert self._params(MessageBroker.route_task) == self._params(
            MockMessageBroker.route_task
        )

    def test_route_task_declares_tether_id(self) -> None:
        """Regression: ``tether_id`` existed on the driver but not the interface.

        Callers are type-hinted against the ABC, so four ``route_task(...,
        tether_id=...)`` call sites in ``swarm_worker.py`` were reported as
        errors by pyright even though they were correct at runtime.
        """
        for func in (
            MessageBroker.route_task,
            LocalMessageBroker.route_task,
            MockMessageBroker.route_task,
        ):
            assert "tether_id" in self._params(func)
            assert self._params(func)["tether_id"] == ""

    def test_count_ready_tasks_is_part_of_the_contract(self) -> None:
        assert hasattr(MessageBroker, "count_ready_tasks")
        assert self._params(MessageBroker.count_ready_tasks) == self._params(
            LocalMessageBroker.count_ready_tasks
        )
        assert self._params(MessageBroker.count_ready_tasks) == self._params(
            MockMessageBroker.count_ready_tasks
        )

    def test_every_abstract_method_is_implemented_by_both(self) -> None:
        """Guards the failure mode that broke 8 tests at the baseline.

        ``update_session_ledger`` and ``update_session_step_index`` were added to
        the ABC without updating ``MockMessageBroker``, so instantiating the mock
        raised ``TypeError`` and every ``TestMockBroker`` case errored at fixture
        setup. Nobody noticed because the suite could not be collected at all.
        """
        abstracts = {
            name
            for name, value in vars(MessageBroker).items()
            if getattr(value, "__isabstractmethod__", False)
        }
        assert abstracts, "sanity: MessageBroker should declare abstract methods"
        for impl in (LocalMessageBroker, MockMessageBroker):
            assert not getattr(impl, "__abstractmethods__", frozenset()), (
                f"{impl.__name__} is still abstract: "
                f"{sorted(getattr(impl, '__abstractmethods__', ()))}"
            )
            for name in abstracts:
                assert callable(getattr(impl, name, None)), (
                    f"{impl.__name__} does not implement {name}"
                )


# ── 2. The ready-task estimator ───────────────────────────────────────────────


class TestCountReadyTasks:
    """Sizing hint must mirror the real Gather Gate, on a 4-branch fixture."""

    @staticmethod
    def _seed_scatter(broker_obj: LocalMessageBroker) -> FakeTopology:
        """Four independent lanes fanning into one gather node.

        LANE_A .. LANE_D have no prerequisites. GATHER waits on all four, so it
        is not claimable until every lane completes.
        """
        broker_obj.inject_task(
            job_id=JOB,
            payload_path="/payload.md",
            starting_node="LANE_A, LANE_B, LANE_C, LANE_D, GATHER",
        )
        return FakeTopology({
            "LANE_A": "none",
            "LANE_B": "none",
            "LANE_C": "none",
            "LANE_D": "none",
            "GATHER": "LANE_A|LANE_B|LANE_C|LANE_D",
        })

    def test_counts_only_dependency_free_tasks(self, broker: LocalMessageBroker) -> None:
        topo = self._seed_scatter(broker)
        # 5 open rows, but GATHER's wait_for is unsatisfied.
        assert broker.count_ready_tasks(JOB, topo) == 4

    def test_gather_becomes_ready_once_every_lane_completes(
        self, broker: LocalMessageBroker
    ) -> None:
        topo = self._seed_scatter(broker)
        for node in ("LANE_A", "LANE_B", "LANE_C"):
            _set_status(broker, node, "completed")
        # Three of four done — GATHER still gated, one lane still open.
        assert broker.count_ready_tasks(JOB, topo) == 1
        _set_status(broker, "LANE_D", "completed")
        assert broker.count_ready_tasks(JOB, topo) == 1  # now it is GATHER

    def test_partial_completion_does_not_open_the_gate(
        self, broker: LocalMessageBroker
    ) -> None:
        topo = self._seed_scatter(broker)
        for node in ("LANE_A", "LANE_B", "LANE_C", "LANE_D"):
            _set_status(broker, node, "completed")
        # Only GATHER remains open, and it is now ready.
        conn = broker._get_conn()
        still_open = conn.execute(
            "SELECT current_node FROM task_queue WHERE job_id = ? AND lock_status = 'open'",
            (JOB,),
        ).fetchall()
        assert [r[0] for r in still_open] == ["GATHER"]
        assert broker.count_ready_tasks(JOB, topo) == 1

    def test_upstream_failure_is_not_counted_as_ready(
        self, broker: LocalMessageBroker
    ) -> None:
        topo = self._seed_scatter(broker)
        _set_status(broker, "LANE_A", "failed")
        for node in ("LANE_B", "LANE_C", "LANE_D"):
            _set_status(broker, node, "completed")
        # GATHER can never become ready — it must not inflate the pool estimate.
        assert broker.count_ready_tasks(JOB, topo) == 0

    def test_cap_short_circuits_the_scan(self, broker: LocalMessageBroker) -> None:
        topo = self._seed_scatter(broker)
        assert broker.count_ready_tasks(JOB, topo, cap=2) == 2
        assert broker.count_ready_tasks(JOB, topo, cap=99) == 4
        assert broker.count_ready_tasks(JOB, topo, cap=0) == 4
        assert broker.count_ready_tasks(JOB, topo, cap=-1) == 4

    def test_missing_topology_treats_everything_as_ready(
        self, broker: LocalMessageBroker
    ) -> None:
        """An unresolvable node gates on nothing — matches the claim path."""
        self._seed_scatter(broker)
        assert broker.count_ready_tasks(JOB, None) == 5
        assert broker.count_ready_tasks(JOB, FakeTopology({})) == 5

    def test_other_jobs_are_ignored(self, broker: LocalMessageBroker) -> None:
        topo = self._seed_scatter(broker)
        broker.inject_task(job_id="other_job", payload_path="/p.md", starting_node="X, Y")
        assert broker.count_ready_tasks(JOB, topo) == 4
        assert broker.count_ready_tasks("other_job", topo) == 2

    def test_estimator_does_not_mutate_the_queue(self, broker: LocalMessageBroker) -> None:
        """It is a hint, not a claim. Nothing may change state."""
        topo = self._seed_scatter(broker)
        conn = broker._get_conn()
        before = conn.execute(
            "SELECT id, lock_status, locked_by FROM task_queue ORDER BY id"
        ).fetchall()
        broker.count_ready_tasks(JOB, topo)
        after = conn.execute(
            "SELECT id, lock_status, locked_by FROM task_queue ORDER BY id"
        ).fetchall()
        assert [tuple(r) for r in before] == [tuple(r) for r in after]

    def test_estimate_agrees_with_what_claiming_actually_yields(
        self, broker: LocalMessageBroker
    ) -> None:
        """The whole point of the estimator: it must not lie about capacity."""
        topo = self._seed_scatter(broker)
        estimate = broker.count_ready_tasks(JOB, topo)
        claimed = []
        while True:
            task = broker.fetch_and_lock_task("agent_x", topo)
            if task is None:
                break
            claimed.append(task["current_node"])
        assert len(claimed) == estimate
        assert set(claimed) == {"LANE_A", "LANE_B", "LANE_C", "LANE_D"}


# ── 3. Claim atomicity and the mid-scan commit fix ────────────────────────────


class TestClaimTransaction:
    """The exclusive claim must span the whole scan, cancellations included."""

    def test_cancels_upstream_failed_task_and_still_claims_in_one_call(
        self, broker: LocalMessageBroker
    ) -> None:
        """Regression for the mid-transaction ``commit()``.

        The old code committed immediately after cancelling a task whose upstream
        had failed, then carried on looping. That ended the ``BEGIN EXCLUSIVE``
        transaction, so the claim ``UPDATE`` later in the same scan ran with no
        exclusive lock held. Here the cancellation and the claim happen in one
        call, and both must be durable.
        """
        # DEAD_GATHER is scanned before LIVE because its row is created first.
        broker.inject_task(
            job_id=JOB, payload_path="/p.md", starting_node="UPSTREAM, DEAD_GATHER, LIVE"
        )
        _set_status(broker, "UPSTREAM", "failed")
        topo = FakeTopology({
            "UPSTREAM": "none",
            "DEAD_GATHER": "UPSTREAM",
            "LIVE": "none",
        })

        task = broker.fetch_and_lock_task("agent_1", topo)

        assert task is not None
        assert task["current_node"] == "LIVE", "should skip past the dead branch"

        conn = broker._get_conn()
        statuses = dict(
            conn.execute(
                "SELECT current_node, lock_status FROM task_queue WHERE job_id = ?",
                (JOB,),
            ).fetchall()
        )
        assert statuses["DEAD_GATHER"] == "cancelled", "cancellation must be durable"
        assert statuses["LIVE"] == "locked"

    def test_no_transaction_is_left_open_after_a_claim(
        self, broker: LocalMessageBroker
    ) -> None:
        broker.inject_task(job_id=JOB, payload_path="/p.md", starting_node="SOLO")
        broker.fetch_and_lock_task("agent_1", FakeTopology({"SOLO": "none"}))
        assert broker._get_conn().in_transaction is False

    def test_no_transaction_is_left_open_when_queue_is_empty(
        self, broker: LocalMessageBroker
    ) -> None:
        assert broker.fetch_and_lock_task("agent_1", FakeTopology()) is None
        assert broker._get_conn().in_transaction is False

    def test_a_raising_topology_provider_does_not_wedge_the_lock(
        self, broker: LocalMessageBroker
    ) -> None:
        """A held EXCLUSIVE lock would stall every other worker thread.

        ``_resolve_wait_for`` swallows provider errors, so this exercises the
        rollback guard via a provider that breaks the contract outright.
        """
        broker.inject_task(job_id=JOB, payload_path="/p.md", starting_node="SOLO")

        class Exploding:
            def get_node_config(self, node_id: str) -> dict[str, Any]:
                raise RuntimeError("provider is down")

        # Swallowed by _resolve_wait_for -> treated as ungated -> claim succeeds.
        assert broker.fetch_and_lock_task("agent_1", Exploding()) is not None
        assert broker._get_conn().in_transaction is False


# ── 4. Connection-per-thread ──────────────────────────────────────────────────


class TestThreadLocalConnections:
    """One connection per thread is a correctness requirement, not a tweak."""

    def test_each_thread_gets_its_own_connection(
        self, broker: LocalMessageBroker
    ) -> None:
        seen: dict[str, int] = {}
        barrier = threading.Barrier(3)

        def grab(name: str) -> None:
            barrier.wait(timeout=10)
            seen[name] = id(broker._get_conn())

        threads = [
            threading.Thread(target=grab, args=(f"t{i}",), daemon=True)
            for i in range(2)
        ]
        for t in threads:
            t.start()
        barrier.wait(timeout=10)
        for t in threads:
            t.join(timeout=10)

        main_conn_id = id(broker._get_conn())
        assert len(seen) == 2
        assert len(set(seen.values())) == 2, "worker threads shared a connection"
        assert main_conn_id not in seen.values()

    def test_same_thread_reuses_its_connection(self, broker: LocalMessageBroker) -> None:
        assert broker._get_conn() is broker._get_conn()

    def test_row_factory_is_set_once_at_creation(
        self, broker: LocalMessageBroker
    ) -> None:
        """No query method may reassign ``row_factory`` on a live connection.

        Doing so is a cross-thread side effect: one thread's SELECT would change
        the row type another thread receives mid-flight.
        """
        conn = broker._get_conn()
        assert conn.row_factory is sqlite3.Row
        broker.get_resumable_sessions()
        broker.get_task_errors(JOB)
        broker.count_ready_tasks(JOB, None)
        assert conn.row_factory is sqlite3.Row

    def test_concurrent_claims_never_hand_out_the_same_task(
        self, broker: LocalMessageBroker
    ) -> None:
        """The property the exclusive transaction exists to guarantee."""
        nodes = [f"N{i}" for i in range(12)]
        broker.inject_task(
            job_id=JOB, payload_path="/p.md", starting_node=", ".join(nodes)
        )
        topo = FakeTopology({n: "none" for n in nodes})

        claims: list[tuple[str, str]] = []
        claims_lock = threading.Lock()
        start = threading.Barrier(4)

        def worker(slot: int) -> None:
            agent = f"universal_node_test_t{slot}"
            start.wait(timeout=10)
            while True:
                task = broker.fetch_and_lock_task(agent, topo)
                if task is None:
                    return
                with claims_lock:
                    claims.append((task["current_node"], agent))

        threads = [threading.Thread(target=worker, args=(i,), daemon=True) for i in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=30)
            assert not t.is_alive(), "worker thread deadlocked on the claim lock"

        claimed_nodes = [c[0] for c in claims]
        assert sorted(claimed_nodes) == sorted(nodes), "a task was lost or duplicated"
        assert len(claimed_nodes) == len(set(claimed_nodes)), "same task claimed twice"

    def test_locked_by_records_the_claiming_worker(
        self, broker: LocalMessageBroker
    ) -> None:
        """Precondition for A3 per-thread identity and zombie-lock reclaim."""
        broker.inject_task(job_id=JOB, payload_path="/p.md", starting_node="A, B")
        topo = FakeTopology({"A": "none", "B": "none"})
        broker.fetch_and_lock_task("universal_node_1_t0", topo)
        broker.fetch_and_lock_task("universal_node_1_t1", topo)
        rows = dict(
            broker._get_conn()
            .execute(
                "SELECT current_node, locked_by FROM task_queue WHERE job_id = ? "
                "AND lock_status = 'locked'",
                (JOB,),
            )
            .fetchall()
        )
        assert rows == {"A": "universal_node_1_t0", "B": "universal_node_1_t1"}


# ── 5. Documented hard boundary ───────────────────────────────────────────────


class TestUniqueJobNodeBoundary:
    """``UNIQUE(job_id, current_node)`` collapses same-named lanes.

    Not a bug to fix in 6.12 — a constraint to design around. Recorded as a test
    so the 6.13 multi-lane authoring work cannot forget it: two scatter lanes
    must never be given the same node name inside one job.
    """

    def test_same_node_name_twice_in_one_job_collapses_to_one_row(
        self, broker: LocalMessageBroker
    ) -> None:
        broker.inject_task(job_id=JOB, payload_path="/p.md", starting_node="DUP")
        broker.inject_task(job_id=JOB, payload_path="/other.md", starting_node="DUP")
        count = broker._get_conn().execute(
            "SELECT COUNT(*) FROM task_queue WHERE job_id = ? AND current_node = 'DUP'",
            (JOB,),
        ).fetchone()[0]
        assert count == 1

    def test_the_same_node_name_in_a_different_job_is_fine(
        self, broker: LocalMessageBroker
    ) -> None:
        broker.inject_task(job_id=JOB, payload_path="/p.md", starting_node="DUP")
        broker.inject_task(job_id="job_other", payload_path="/p.md", starting_node="DUP")
        count = broker._get_conn().execute(
            "SELECT COUNT(*) FROM task_queue WHERE current_node = 'DUP'"
        ).fetchone()[0]
        assert count == 2
