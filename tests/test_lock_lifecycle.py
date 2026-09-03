# ┌─────────────────────────────────────────────────────────────────────────────┐
# │  MACCREv2 Test Suite — Phase 6.13 Track A: Lock Lifecycle                   │
# └─────────────────────────────────────────────────────────────────────────────┘
"""
tests/test_lock_lifecycle.py
============================
Phase 6.13 Track A — the lifecycle of a ``task_queue`` lock.

Track A exists because ``reclaim_zombie_locks`` aged its "is this worker dead?"
test off ``created_at`` — the moment the row was *enqueued* — rather than the
moment the lock was *acquired*. Sequentially those two timestamps were nearly
identical, because a task was claimed almost as soon as it was queued. Under an
8-wide scatter they diverge badly: lanes sit queued for many seconds while other
lanes occupy the pool, so a freshly-claimed task could be judged a zombie the
instant a worker picked it up, handed to a second worker, and executed twice.

Task A1 introduces ``locked_at`` and establishes the invariant these tests pin
down:

    ``locked_at`` is non-NULL if and only if ``lock_status = 'locked'``.

Every transition *into* the locked state stamps it, and every transition *out of*
it clears it, so lock age can never be read from a row that is not actually
locked.
"""
from __future__ import annotations

import inspect
import sqlite3
import time
from pathlib import Path
from typing import Any

import pytest

from maccre_core.orchestration.broker_interface import MessageBroker
from maccre_core.orchestration.concurrency import (
    DEFAULT_HEARTBEAT_SECONDS,
    HeartbeatMonitor,
    task_heartbeat,
)
from maccre_core.orchestration.local_broker import (
    DEFAULT_ZOMBIE_TIMEOUT_SECONDS,
    LocalMessageBroker,
)
from tests.mocks.mock_broker import MockMessageBroker

JOB = "job_lock_lifecycle"


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
    b = LocalMessageBroker(db_path=str(tmp_path / "swarm_queue.db"))
    yield b
    b.close()


def _row(broker_obj: LocalMessageBroker, node: str) -> dict[str, Any]:
    cur = broker_obj._get_conn().execute(
        "SELECT * FROM task_queue WHERE job_id = ? AND current_node = ?",
        (JOB, node),
    )
    fetched = cur.fetchone()
    assert fetched is not None, f"no task_queue row for node {node!r}"
    return dict(fetched)


class TestLockedAtColumn:
    """A1 — the column exists, and a claim stamps it."""

    def test_column_exists_on_a_fresh_database(
        self, broker: LocalMessageBroker
    ) -> None:
        cols = {
            r[1]
            for r in broker._get_conn().execute("PRAGMA table_info(task_queue)")
        }
        assert "locked_at" in cols

    def test_a_queued_task_has_no_lock_timestamp(
        self, broker: LocalMessageBroker
    ) -> None:
        broker.inject_task(job_id=JOB, payload_path="/p.md", starting_node="SOLO")
        assert _row(broker, "SOLO")["locked_at"] is None

    def test_claiming_stamps_locked_at(self, broker: LocalMessageBroker) -> None:
        broker.inject_task(job_id=JOB, payload_path="/p.md", starting_node="SOLO")
        broker.fetch_and_lock_task("agent_1", FakeTopology({"SOLO": "none"}))

        row = _row(broker, "SOLO")
        assert row["lock_status"] == "locked"
        assert row["locked_at"] is not None

    def test_locked_at_reflects_claim_time_not_enqueue_time(
        self, broker: LocalMessageBroker
    ) -> None:
        """The whole point of A1, expressed as a single assertion.

        A task that waits in the queue before being claimed must report a
        ``locked_at`` strictly later than its ``created_at``. This is the
        property ``reclaim_zombie_locks`` needed and did not have: keyed off
        ``created_at``, a task queued for longer than the reclaim timeout looked
        like a zombie the moment it was picked up.

        SQLite's ``CURRENT_TIMESTAMP`` has one-second granularity, so the wait
        here must exceed a second to be observable at all.
        """
        broker.inject_task(job_id=JOB, payload_path="/p.md", starting_node="SLOW")
        time.sleep(1.2)
        broker.fetch_and_lock_task("agent_1", FakeTopology({"SLOW": "none"}))

        row = _row(broker, "SLOW")
        assert row["locked_at"] > row["created_at"], (
            f"locked_at {row['locked_at']!r} should postdate "
            f"created_at {row['created_at']!r}"
        )

    def test_lock_age_is_measured_from_the_claim(
        self, broker: LocalMessageBroker
    ) -> None:
        """Age computed off ``locked_at`` must be ~0 right after a claim.

        Computed off ``created_at`` for the same row it would be >1s, which is
        precisely the bug. This asserts the difference numerically rather than
        by ordering.
        """
        broker.inject_task(job_id=JOB, payload_path="/p.md", starting_node="SLOW")
        time.sleep(1.2)
        broker.fetch_and_lock_task("agent_1", FakeTopology({"SLOW": "none"}))

        lock_age, queue_age = broker._get_conn().execute(
            "SELECT (julianday('now') - julianday(locked_at)) * 86400.0, "
            "       (julianday('now') - julianday(created_at)) * 86400.0 "
            "FROM task_queue WHERE job_id = ? AND current_node = 'SLOW'",
            (JOB,),
        ).fetchone()

        assert lock_age < 1.0, f"a just-claimed lock should be young, got {lock_age}s"
        assert queue_age > 1.0, "the row really did wait in the queue"


class TestMigration:
    """A1 — pre-existing databases gain the column without losing data."""

    def test_migration_adds_the_column_to_a_legacy_table(
        self, tmp_path: Path
    ) -> None:
        """Build a task_queue with no locked_at, then let the broker upgrade it."""
        db = tmp_path / "legacy.db"
        conn = sqlite3.connect(str(db))
        conn.execute("""
            CREATE TABLE task_queue (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                job_id        TEXT NOT NULL,
                payload_path  TEXT NOT NULL,
                current_node  TEXT NOT NULL,
                lock_status   TEXT DEFAULT 'open',
                locked_by     TEXT,
                created_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(job_id, current_node)
            )
        """)
        conn.execute(
            "INSERT INTO task_queue (job_id, payload_path, current_node) "
            "VALUES ('legacy_job', '/legacy.md', 'OLD_NODE')"
        )
        conn.commit()
        conn.close()

        b = LocalMessageBroker(db_path=str(db))
        try:
            cols = {
                r[1] for r in b._get_conn().execute("PRAGMA table_info(task_queue)")
            }
            assert "locked_at" in cols

            surviving = b._get_conn().execute(
                "SELECT current_node FROM task_queue WHERE job_id = 'legacy_job'"
            ).fetchone()
            assert surviving is not None
            assert surviving[0] == "OLD_NODE", "the migration must not drop rows"
        finally:
            b.close()

    def test_migration_is_idempotent(self, tmp_path: Path) -> None:
        """Opening the same database repeatedly must not raise or duplicate."""
        db = tmp_path / "repeat.db"
        for _ in range(3):
            b = LocalMessageBroker(db_path=str(db))
            b.close()

        b = LocalMessageBroker(db_path=str(db))
        try:
            names = [
                r[1] for r in b._get_conn().execute("PRAGMA table_info(task_queue)")
            ]
            assert names.count("locked_at") == 1
        finally:
            b.close()


class TestInvariantOnRelease:
    """A1 — every transition out of 'locked' clears the timestamp.

    Without this, a completed or released row keeps a stale lock age. Reclaim's
    ``WHERE lock_status = 'locked'`` filter would mask it, but any future
    diagnostic asking "how long has this been held" would read a fossil.
    """

    def _claim(self, broker_obj: LocalMessageBroker, node: str) -> int:
        broker_obj.inject_task(job_id=JOB, payload_path="/p.md", starting_node=node)
        task = broker_obj.fetch_and_lock_task(
            "agent_1", FakeTopology({node: "none"})
        )
        assert task is not None
        assert _row(broker_obj, node)["locked_at"] is not None
        return int(task["id"])

    def test_release_task_clears_locked_at(
        self, broker: LocalMessageBroker
    ) -> None:
        row_id = self._claim(broker, "REL")
        broker.release_task(row_id)

        row = _row(broker, "REL")
        assert row["lock_status"] == "open"
        assert row["locked_by"] is None
        assert row["locked_at"] is None

    def test_pause_task_clears_locked_at(self, broker: LocalMessageBroker) -> None:
        row_id = self._claim(broker, "PAUSE")
        broker.pause_task(row_id)

        row = _row(broker, "PAUSE")
        assert row["lock_status"] == "paused"
        assert row["locked_at"] is None

    def test_routing_to_terminal_clears_locked_at(
        self, broker: LocalMessageBroker
    ) -> None:
        row_id = self._claim(broker, "ROUTE")
        broker.route_task(
            row_id=row_id,
            job_id=JOB,
            next_node_str="DONE",
            new_payload_path="/out.md",
            status="completed",
        )

        row = _row(broker, "ROUTE")
        assert row["lock_status"] == "completed"
        assert row["locked_at"] is None

    def test_routing_to_review_clears_locked_at(
        self, broker: LocalMessageBroker
    ) -> None:
        """The CTRL_REVIEW intercept is a separate UPDATE and was easy to miss."""
        row_id = self._claim(broker, "REVIEW_SRC")
        broker.route_task(
            row_id=row_id,
            job_id=JOB,
            next_node_str="CTRL_REVIEW",
            new_payload_path="/out.md",
            status="completed",
        )

        row = _row(broker, "REVIEW_SRC")
        assert row["lock_status"] == "awaiting_orders"
        assert row["locked_at"] is None

    def test_requeue_after_completion_clears_locked_at(
        self, broker: LocalMessageBroker
    ) -> None:
        """The ON CONFLICT re-queue path resets to 'open'; age must reset too."""
        row_id = self._claim(broker, "LOOP")
        broker.route_task(
            row_id=row_id,
            job_id=JOB,
            next_node_str="LOOP",
            new_payload_path="/out.md",
            status="completed",
        )

        row = _row(broker, "LOOP")
        assert row["lock_status"] == "open"
        assert row["locked_at"] is None


class TestHeartbeatBroker:
    """A2 — the broker-side heartbeat primitive."""

    def _claim(self, broker_obj: LocalMessageBroker, node: str = "BEAT") -> int:
        broker_obj.inject_task(job_id=JOB, payload_path="/p.md", starting_node=node)
        task = broker_obj.fetch_and_lock_task(
            "agent_1", FakeTopology({node: "none"})
        )
        assert task is not None
        return int(task["id"])

    def test_heartbeat_advances_locked_at(
        self, broker: LocalMessageBroker
    ) -> None:
        row_id = self._claim(broker)
        before = _row(broker, "BEAT")["locked_at"]

        time.sleep(1.2)  # CURRENT_TIMESTAMP granularity is one second
        assert broker.heartbeat_task(row_id) is True

        assert _row(broker, "BEAT")["locked_at"] > before

    def test_heartbeat_keeps_a_slow_node_out_of_reclaim_range(
        self, broker: LocalMessageBroker
    ) -> None:
        """The behaviour the heartbeat exists for, stated directly.

        A node running well past any reclaim timeout stays young *as measured by
        lock age*, because it keeps refreshing. This is what lets the reclaim
        threshold be short enough to be useful without stealing live work.
        """
        row_id = self._claim(broker)
        for _ in range(3):
            time.sleep(0.6)
            assert broker.heartbeat_task(row_id) is True

        (lock_age,) = broker._get_conn().execute(
            "SELECT (julianday('now') - julianday(locked_at)) * 86400.0 "
            "FROM task_queue WHERE id = ?",
            (row_id,),
        ).fetchone()
        assert lock_age < 1.0, (
            f"a heartbeating node held the lock ~1.8s but should read young, "
            f"got {lock_age}s"
        )

    def test_heartbeat_does_not_resurrect_a_completed_row(
        self, broker: LocalMessageBroker
    ) -> None:
        """The scoping predicate, which is load-bearing rather than defensive.

        The heartbeat thread is separate from the node, so a beat can fire just
        after the node committed its completion. Unscoped, that late beat would
        stamp a lock age onto a finished row.
        """
        row_id = self._claim(broker, "DONE_RACE")
        broker.route_task(
            row_id=row_id,
            job_id=JOB,
            next_node_str="DONE",
            new_payload_path="/out.md",
            status="completed",
        )

        assert broker.heartbeat_task(row_id) is False

        row = _row(broker, "DONE_RACE")
        assert row["lock_status"] == "completed"
        assert row["locked_at"] is None

    def test_heartbeat_reports_false_for_a_released_row(
        self, broker: LocalMessageBroker
    ) -> None:
        row_id = self._claim(broker, "REL_RACE")
        broker.release_task(row_id)
        assert broker.heartbeat_task(row_id) is False

    def test_heartbeat_reports_false_for_an_unknown_row(
        self, broker: LocalMessageBroker
    ) -> None:
        assert broker.heartbeat_task(999_999) is False


class TestHeartbeatMonitor:
    """A2 — the daemon-thread context manager."""

    class _RecordingBroker:
        """Counts beats; can be told to fail or to report the lock lost."""

        def __init__(self, *, alive: bool = True, raises: bool = False) -> None:
            self.calls = 0
            self._alive = alive
            self._raises = raises

        def heartbeat_task(self, row_id: int) -> bool:
            self.calls += 1
            if self._raises:
                raise RuntimeError("database is locked")
            return self._alive

    def test_monitor_beats_while_the_block_runs(self) -> None:
        rec = self._RecordingBroker()
        with task_heartbeat(rec, row_id=1, interval=0.05) as monitor:
            time.sleep(0.4)
            assert monitor.is_running
        assert rec.calls >= 3, f"expected several beats, got {rec.calls}"
        assert monitor.beats >= 3

    def test_monitor_stops_on_block_exit(self) -> None:
        """A heartbeat outliving its node would vouch for a dead worker."""
        rec = self._RecordingBroker()
        with task_heartbeat(rec, row_id=1, interval=0.05) as monitor:
            time.sleep(0.15)
        assert not monitor.is_running

        settled = rec.calls
        time.sleep(0.25)
        assert rec.calls == settled, "the thread kept beating after the block exited"

    def test_monitor_stops_when_the_block_raises(self) -> None:
        rec = self._RecordingBroker()
        with pytest.raises(ValueError):
            with task_heartbeat(rec, row_id=1, interval=0.05) as monitor:
                time.sleep(0.1)
                raise ValueError("node blew up")
        assert not monitor.is_running

    def test_monitor_stops_when_the_lock_is_lost(self) -> None:
        """No point refreshing a row that is no longer locked."""
        rec = self._RecordingBroker(alive=False)
        with task_heartbeat(rec, row_id=1, interval=0.05) as monitor:
            time.sleep(0.3)
        assert monitor.lock_lost is True
        assert rec.calls == 1, "should stop after the first negative report"

    def test_a_failing_heartbeat_never_escapes(self) -> None:
        """A lost refresh is a degradation; killing a healthy node is not.

        Transient SQLite contention must be retried, not raised — the node this
        heartbeat vouches for is running fine.
        """
        rec = self._RecordingBroker(raises=True)
        with task_heartbeat(rec, row_id=1, interval=0.05) as monitor:
            time.sleep(0.3)
        assert monitor.errors >= 2, "should have retried after failing"
        assert monitor.beats == 0

    def test_monitor_thread_is_a_daemon(self) -> None:
        """A wedged heartbeat must not be able to hold the process open."""
        rec = self._RecordingBroker()
        monitor = HeartbeatMonitor(rec, row_id=1, interval=0.05)
        monitor.start()
        try:
            assert monitor._thread is not None
            assert monitor._thread.daemon is True
        finally:
            monitor.stop()

    def test_stop_is_idempotent(self) -> None:
        rec = self._RecordingBroker()
        monitor = HeartbeatMonitor(rec, row_id=1, interval=0.05)
        monitor.start()
        monitor.stop()
        monitor.stop()
        assert not monitor.is_running


class TestBrokerSignatureParity:
    """A2 — the mock must not drift from the interface.

    ``test_broker_contract`` already guards this class of drift; this adds the
    new method explicitly so a future signature change to ``heartbeat_task``
    cannot pass tests against a stale double.
    """

    def test_interface_declares_heartbeat_task(self) -> None:
        assert hasattr(MessageBroker, "heartbeat_task")
        assert "heartbeat_task" in MessageBroker.__abstractmethods__

    def test_implementations_agree_on_the_signature(self) -> None:
        expected = inspect.signature(MessageBroker.heartbeat_task)
        for impl in (LocalMessageBroker, MockMessageBroker):
            assert inspect.signature(impl.heartbeat_task) == expected, (
                f"{impl.__name__}.heartbeat_task drifted from the interface"
            )

    def test_mock_records_beats_and_respects_lock_state(self) -> None:
        mock = MockMessageBroker()
        mock.inject_task(job_id=JOB, payload_path="/p.md", starting_node="M")
        row_id = mock._tasks[0]["id"]

        # Not yet locked -> nothing to refresh.
        assert mock.heartbeat_task(row_id) is False

        mock._tasks[0]["lock_status"] = "locked"
        assert mock.heartbeat_task(row_id) is True
        assert mock.heartbeat_calls == [row_id]


# ── A4: a claimed task must always end up resolved ────────────────────────────


class _ResolutionBroker:
    """Records how ``execute_cycle`` disposed of the task it claimed.

    ``route_task`` can be told to fail, which is the scenario A4 exists for: the
    FAILED-route runs *because* something already went wrong, and it reads several
    locals that are only bound on the happy path.
    """

    def __init__(self, task: dict[str, Any], *, route_raises: bool = False) -> None:
        self._task: dict[str, Any] | None = dict(task)
        self._route_raises = route_raises
        self.route_calls: list[dict[str, Any]] = []
        self.release_calls: list[int] = []
        self.heartbeat_calls: list[int] = []

    # ── the three methods execute_cycle reaches on this path ──────────────────

    def fetch_and_lock_task(self, agent_id: str, topology_engine: Any) -> Any:
        task, self._task = self._task, None
        return task

    def route_task(self, *args: Any, **kwargs: Any) -> None:
        self.route_calls.append({"args": args, "kwargs": kwargs})
        if self._route_raises:
            raise RuntimeError("route_task exploded on the failure path")

    def release_task(self, row_id: int) -> None:
        self.release_calls.append(row_id)

    def heartbeat_task(self, row_id: int) -> bool:
        self.heartbeat_calls.append(row_id)
        return True

    def update_session_ledger(self, job_id: str, ledger_path: str) -> None:
        pass

    def update_session_step_index(self, job_id: str, step_index: int) -> None:
        pass


def _drive_failure_path(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    route_raises: bool,
) -> _ResolutionBroker:
    """Run ``execute_cycle`` on a task guaranteed to blow up mid-node.

    The worker is built with ``__new__`` and left deliberately incomplete, so the
    node raises on its own without a contrived injection — which is a fair
    approximation of a real mid-node crash, and lands in exactly the outer
    ``except`` A4 hardens.

    A ``studio_session_`` job id plus ``MACCRE_CUSTOM_LEDGER`` keeps everything
    inside *tmp_path* and skips the thread tee. The tee is skipped on purpose:
    installing it under pytest wraps the per-test capture object, which
    ``concurrency.install_thread_routing`` documents as unsafe from worker
    threads.
    """
    from maccre_core.orchestration import swarm_worker as sw

    monkeypatch.setenv("MACCRE_CUSTOM_LEDGER", str(tmp_path / "ledger.md"))
    monkeypatch.setattr(sw, "setup_session_loggers", lambda *a, **k: None, raising=False)

    task = {
        "id": 4242,
        "job_id": "studio_session_a4",
        "payload_path": str(tmp_path / "payload.md"),
        "current_node": "EXPLODE",
        "source_payload_path": str(tmp_path / "payload.md"),
        "flow_line_id": "",
        "flow_vector": "",
        "tether_id": "",
    }
    (tmp_path / "payload.md").write_text("payload", encoding="utf-8")

    broker = _ResolutionBroker(task, route_raises=route_raises)

    worker = sw.UniversalSwarmWorker.__new__(sw.UniversalSwarmWorker)
    worker.slot = 0
    worker.worker_id = sw.resolve_worker_id(0)
    worker.broker = broker  # type: ignore[assignment]
    worker.topology = None
    worker.on_node_start = None
    worker.on_node_finish = None
    worker.project_name = "GLOBAL"
    worker.idle_sleep_seconds = 0.0
    worker.pause_poll_seconds = 0.0
    worker._is_sleeping = False

    worker.execute_cycle()
    return broker


class TestClaimedTaskIsAlwaysResolved:
    """A4 — the hole that let a flow report success with a node that never ran."""

    def test_a_crashing_node_routes_to_failed(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Baseline: the ordinary failure path still resolves the task."""
        broker = _drive_failure_path(tmp_path, monkeypatch, route_raises=False)

        assert broker.route_calls, "a crashing node must still route its task"
        assert broker.release_calls == [], "no fallback needed when routing works"

    def test_a_failing_failed_route_falls_back_to_release(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The A4 fix, stated as its consequence.

        Before this, an exception inside the FAILED-route escaped into the pool.
        The worker retired its slot, the row stayed ``locked``, the drain check
        (which counts only ``open`` rows) saw nothing outstanding, and the step
        reported ``completed`` for a node that never executed.
        """
        broker = _drive_failure_path(tmp_path, monkeypatch, route_raises=True)

        assert broker.route_calls, "the route was attempted"
        assert broker.release_calls == [4242], (
            "a failed FAILED-route must release the lock rather than strand it"
        )

    def test_the_exception_does_not_escape_into_the_pool(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """``_drive_failure_path`` returning at all is the assertion.

        ``route_task`` raises inside the handler for another exception; if that
        were unguarded it would propagate out of ``execute_cycle``.
        """
        broker = _drive_failure_path(tmp_path, monkeypatch, route_raises=True)
        assert broker.release_calls == [4242]

    def test_release_task_now_has_a_caller(self) -> None:
        """``release_task``'s docstring claimed a caller that did not exist.

        It advertised "used in worker finally blocks" while being invoked from
        nowhere in the codebase. A4 supplies the real caller; this guards against
        it being quietly dropped again.
        """
        source = inspect.getsource(
            __import__(
                "maccre_core.orchestration.swarm_worker", fromlist=["x"]
            ).UniversalSwarmWorker.execute_cycle
        )
        assert "release_task" in source

    def test_the_failed_route_is_guarded(self) -> None:
        """Structural guard: the FAILED-route must sit inside its own try.

        A behavioural test proves the current code works; this pins the shape, so
        a future edit cannot un-guard the route while the behavioural test above
        still passes for some other reason.
        """
        source = inspect.getsource(
            __import__(
                "maccre_core.orchestration.swarm_worker", fromlist=["x"]
            ).UniversalSwarmWorker.execute_cycle
        )
        tail = source[source.index("Routing task to"):]
        route_at = tail.index("self.broker.route_task")
        assert "try:" in tail[:route_at], (
            "the FAILED-route must be wrapped in its own try/except"
        )


class TestReclaimZombieLocks:
    """A3 — reclaim must distinguish a dead worker from a queued or slow one."""

    def _claim(self, broker_obj: LocalMessageBroker, node: str) -> int:
        task = broker_obj.fetch_and_lock_task(
            "agent_1", FakeTopology({node: "none"})
        )
        assert task is not None
        return int(task["id"])

    def test_a_queued_then_claimed_task_is_not_reclaimed(
        self, broker: LocalMessageBroker
    ) -> None:
        """The original bug, as a regression test.

        This is the exact shape that caused double execution: a task sits in the
        queue longer than the reclaim timeout (because other lanes are occupying
        the pool), then gets claimed. Aged off ``created_at`` it was judged a
        zombie the moment a worker picked it up. Aged off ``locked_at`` it is
        correctly seen as freshly claimed.
        """
        broker.inject_task(job_id=JOB, payload_path="/p.md", starting_node="LATE")
        time.sleep(1.5)  # longer than the timeout used below
        self._claim(broker, "LATE")

        reclaimed = broker.reclaim_zombie_locks(timeout_seconds=1.0)

        assert reclaimed == 0, (
            "a task that merely waited in the queue must not be reclaimed — "
            "reclaiming it is what caused nodes to execute twice"
        )
        assert _row(broker, "LATE")["lock_status"] == "locked"

    def test_an_abandoned_lock_is_reclaimed(
        self, broker: LocalMessageBroker
    ) -> None:
        broker.inject_task(job_id=JOB, payload_path="/p.md", starting_node="DEAD")
        self._claim(broker, "DEAD")
        time.sleep(1.5)  # nothing heartbeats: the worker is gone

        assert broker.reclaim_zombie_locks(timeout_seconds=1.0) == 1

        row = _row(broker, "DEAD")
        assert row["lock_status"] == "open"
        assert row["locked_by"] is None
        assert row["locked_at"] is None, "a reclaimed row must not keep a lock age"

    def test_a_heartbeating_lock_is_never_reclaimed(
        self, broker: LocalMessageBroker
    ) -> None:
        """The A2/A3 pairing: a slow node holds its lock as long as it checks in.

        Total hold time here is ~2 s against a 1 s timeout. Without the heartbeat
        this row would be reclaimed; with it, it is not.
        """
        broker.inject_task(job_id=JOB, payload_path="/p.md", starting_node="SLOW")
        row_id = self._claim(broker, "SLOW")

        for _ in range(4):
            time.sleep(0.5)
            broker.heartbeat_task(row_id)
            assert broker.reclaim_zombie_locks(timeout_seconds=1.0) == 0

        assert _row(broker, "SLOW")["lock_status"] == "locked"

    def test_stopping_the_heartbeat_makes_the_lock_reclaimable(
        self, broker: LocalMessageBroker
    ) -> None:
        """The other half: once beats stop, the lock does go stale.

        Together with the test above this is the whole point of Track A — lock
        staleness now tracks worker liveness rather than elapsed time.
        """
        broker.inject_task(job_id=JOB, payload_path="/p.md", starting_node="DYING")
        row_id = self._claim(broker, "DYING")
        broker.heartbeat_task(row_id)

        time.sleep(1.5)  # the worker has died; no further beats
        assert broker.reclaim_zombie_locks(timeout_seconds=1.0) == 1

    def test_reclaim_can_be_scoped_to_one_job(
        self, broker: LocalMessageBroker
    ) -> None:
        """A running job must not reach into another job's locks."""
        broker.inject_task(job_id=JOB, payload_path="/p.md", starting_node="MINE")
        broker.inject_task(
            job_id="other_job", payload_path="/p.md", starting_node="THEIRS"
        )
        broker.fetch_and_lock_task("agent_1", FakeTopology({"MINE": "none"}))
        broker.fetch_and_lock_task("agent_2", FakeTopology({"THEIRS": "none"}))
        time.sleep(1.5)

        assert broker.reclaim_zombie_locks(timeout_seconds=1.0, job_id=JOB) == 1

        assert _row(broker, "MINE")["lock_status"] == "open"
        theirs = broker._get_conn().execute(
            "SELECT lock_status FROM task_queue WHERE job_id = 'other_job'"
        ).fetchone()
        assert theirs[0] == "locked", "another job's lock must be untouched"

    def test_unscoped_reclaim_sweeps_every_job(
        self, broker: LocalMessageBroker
    ) -> None:
        broker.inject_task(job_id=JOB, payload_path="/p.md", starting_node="A")
        broker.inject_task(job_id="other_job", payload_path="/p.md", starting_node="B")
        broker.fetch_and_lock_task("agent_1", FakeTopology({"A": "none"}))
        broker.fetch_and_lock_task("agent_2", FakeTopology({"B": "none"}))
        time.sleep(1.5)

        assert broker.reclaim_zombie_locks(timeout_seconds=1.0) == 2

    def test_only_locked_rows_are_touched(
        self, broker: LocalMessageBroker
    ) -> None:
        broker.inject_task(job_id=JOB, payload_path="/p.md", starting_node="OPEN_ONE")
        time.sleep(1.5)

        assert broker.reclaim_zombie_locks(timeout_seconds=0.5) == 0
        assert _row(broker, "OPEN_ONE")["lock_status"] == "open"

    def test_a_legacy_null_timestamp_is_not_reclaimed(
        self, broker: LocalMessageBroker
    ) -> None:
        """Rows locked before the migration carry no lock age.

        With no information about when the lock was taken, the safe assumption is
        that it is live. Guessing the other way is what double-executed nodes.
        """
        broker.inject_task(job_id=JOB, payload_path="/p.md", starting_node="LEGACY")
        row_id = self._claim(broker, "LEGACY")
        conn = broker._get_conn()
        conn.execute("UPDATE task_queue SET locked_at = NULL WHERE id = ?", (row_id,))
        conn.commit()
        time.sleep(1.2)

        assert broker.reclaim_zombie_locks(timeout_seconds=0.5) == 0
        assert _row(broker, "LEGACY")["lock_status"] == "locked"

    def test_default_timeout_is_many_heartbeat_intervals(self) -> None:
        """The threshold is only meaningful relative to the beat interval.

        A default anywhere near the heartbeat interval would reclaim live work on
        a single missed beat. The old default was 15 s measured from the wrong
        column entirely.
        """
        assert DEFAULT_ZOMBIE_TIMEOUT_SECONDS >= DEFAULT_HEARTBEAT_SECONDS * 10
        assert DEFAULT_ZOMBIE_TIMEOUT_SECONDS > 60.0

    def test_the_docstring_no_longer_warns_it_is_unsafe(self) -> None:
        """The old ``.. warning::`` said "do not wire this up". It is now fixed.

        Guards against the fix being reverted while the warning stays absent, or
        the warning being reinstated while the code is correct.
        """
        doc = LocalMessageBroker.reclaim_zombie_locks.__doc__ or ""
        assert ".. warning::" not in doc
        assert "locked_at" in doc, "the contract should state what it ages on"

    def test_reclaim_does_not_age_on_created_at(self) -> None:
        """Structural guard on the actual SQL."""
        source = inspect.getsource(LocalMessageBroker.reclaim_zombie_locks)
        sql_part = source[source.index("sql = "):]
        assert "julianday(locked_at)" in sql_part
        assert "created_at" not in sql_part


# ── Tether scope consistency: the gather-gate deadlock ────────────────────────


class TestTetherScopeConsistency:
    """The gather gate deadlocks when scopes disagree, so they must not.

    Found live. A ``CTRL_SCATTER`` stamped its lanes with one tether while the
    ``CTRL_MERGE`` gathered on another. All eight lanes completed; the merge waited
    forever. Its symptom is indistinguishable from ordinary waiting — the row stays
    ``open``, so the pool keeps spawning workers, each fails to claim it, goes idle
    and retires. That spawn/retire churn runs to the wall-clock timeout.

    The scopes diverged because ``merge_config_overlay`` blanket-``update``\\d the
    step config over the topology, and the authoring UI writes every empty field as
    ``""``. Only *control* nodes receive overlays, so the scatter's tether was
    blanked while the lanes' — read straight from topology.csv — was not.
    """

    def _seed(self, broker_obj: LocalMessageBroker, lane_tether: str,
              merge_tether: str) -> None:
        """Two lanes and a merge, with the tethers under test."""
        broker_obj.inject_task(
            job_id=JOB, payload_path="/p.md", starting_node="L1, L2, GATHER"
        )
        conn = broker_obj._get_conn()
        for node, tether in (("L1", lane_tether), ("L2", lane_tether),
                             ("GATHER", merge_tether)):
            conn.execute(
                "UPDATE task_queue SET tether_id = ? "
                "WHERE job_id = ? AND current_node = ?",
                (tether, JOB, node),
            )
        conn.execute(
            "UPDATE task_queue SET lock_status = 'completed' "
            "WHERE job_id = ? AND current_node IN ('L1','L2')",
            (JOB,),
        )
        conn.commit()

    def _gather_topology(self) -> FakeTopology:
        return FakeTopology({"GATHER": "L1|L2"})

    def test_matching_tethers_let_the_merge_be_claimed(
        self, broker: LocalMessageBroker
    ) -> None:
        self._seed(broker, lane_tether="scope_a", merge_tether="scope_a")

        task = broker.fetch_and_lock_task("agent_1", self._gather_topology())

        assert task is not None
        assert task["current_node"] == "GATHER"

    def test_mismatched_tethers_deadlock_the_gate(
        self, broker: LocalMessageBroker
    ) -> None:
        """Documents *why* consistency is mandatory, not merely tidy.

        Both lanes are completed. The merge is still unclaimable, because its
        tether-scoped predecessor query matches zero rows. No amount of waiting
        changes that.
        """
        self._seed(broker, lane_tether="scatter", merge_tether="scatter_84fe89ba")

        task = broker.fetch_and_lock_task("agent_1", self._gather_topology())

        assert task is None, (
            "a scope mismatch is unrecoverable — this is the deadlock, asserted so "
            "the cause stays visible if it ever returns"
        )

    def test_an_empty_tether_is_safer_than_a_wrong_one(
        self, broker: LocalMessageBroker
    ) -> None:
        """Why the worker no longer invents a ``"scatter"`` scope.

        With no tether the gate checks predecessors unscoped, which works. With a
        *wrong* tether it checks a scope the predecessors are not in, which cannot.
        So falling back to nothing is strictly better than falling back to a
        plausible-looking literal.
        """
        self._seed(broker, lane_tether="scope_a", merge_tether="")

        task = broker.fetch_and_lock_task("agent_1", self._gather_topology())

        assert task is not None, "an unscoped gather must still open"

    def test_the_mismatch_is_reported(
        self, broker: LocalMessageBroker, caplog: pytest.LogCaptureFixture
    ) -> None:
        """A silent hour of spinning is the real defect; name it once."""
        import logging

        from maccre_core.orchestration import local_broker as lb

        lb._SCOPE_WARNED.clear()
        self._seed(broker, lane_tether="scatter", merge_tether="scatter_84fe89ba")

        with caplog.at_level(logging.WARNING, logger="maccre_core"):
            broker.fetch_and_lock_task("agent_1", self._gather_topology())

        assert any("scope mismatch" in r.message.lower() for r in caplog.records), (
            f"expected a scope-mismatch warning, got {[r.message for r in caplog.records]}"
        )

    def test_the_mismatch_warning_is_not_repeated(
        self, broker: LocalMessageBroker, caplog: pytest.LogCaptureFixture
    ) -> None:
        """The gate runs every poll tick; an undeduped warning would flood."""
        import logging

        from maccre_core.orchestration import local_broker as lb

        lb._SCOPE_WARNED.clear()
        self._seed(broker, lane_tether="scatter", merge_tether="scatter_84fe89ba")

        with caplog.at_level(logging.WARNING, logger="maccre_core"):
            for _ in range(5):
                broker.fetch_and_lock_task("agent_1", self._gather_topology())

        hits = [r for r in caplog.records if "scope mismatch" in r.message.lower()]
        assert len(hits) == 1, f"warned {len(hits)} times, expected once"

    def test_absent_predecessors_are_not_reported_as_a_mismatch(
        self, broker: LocalMessageBroker, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Early in a scatter the lanes genuinely do not exist yet.

        That is ordinary waiting and must stay quiet, or the diagnostic becomes
        noise and gets ignored.
        """
        import logging

        from maccre_core.orchestration import local_broker as lb

        lb._SCOPE_WARNED.clear()
        broker.inject_task(job_id=JOB, payload_path="/p.md", starting_node="GATHER")
        conn = broker._get_conn()
        conn.execute(
            "UPDATE task_queue SET tether_id = 'scope_a' WHERE job_id = ?", (JOB,)
        )
        conn.commit()

        with caplog.at_level(logging.WARNING, logger="maccre_core"):
            task = broker.fetch_and_lock_task("agent_1", self._gather_topology())

        assert task is None
        assert not [r for r in caplog.records if "scope mismatch" in r.message.lower()]


class TestOverlaysDoNotBlankTopologyValues:
    """The root cause: an empty authoring field is not an override."""

    def _engine(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Any:
        from maccre_core.orchestration.topology_engine import TopologyEngine

        engine = TopologyEngine.__new__(TopologyEngine)
        engine._cached_graph = {
            "CTRL_SCATTER_S0": {"tether_id": "scatter_84fe89ba", "wait_for": "none"}
        }
        engine._last_pull_time = float("inf")  # never reload from disk
        engine._cache_ttl_seconds = 1e9
        engine._overlays = {}
        return engine

    def test_a_blank_overlay_value_does_not_erase_the_topology_value(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The exact config the authoring UI produces for an empty field.

        ``_collect_ctrl_config`` writes ``cfg[key] = <widget>.value.strip()``, so a
        blank Tether ID box arrives as ``""``.
        """
        engine = self._engine(tmp_path, monkeypatch)
        engine.merge_config_overlay(
            "CTRL_SCATTER_S0", {"tether_id": "", "scatter_mode": "full_copy"}
        )

        cfg = engine._cached_graph["CTRL_SCATTER_S0"]
        assert cfg["tether_id"] == "scatter_84fe89ba", (
            "a blank field must not destroy the topology's tether"
        )
        assert cfg["scatter_mode"] == "full_copy", "real overrides still apply"

    def test_a_populated_overlay_value_still_overrides(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        engine = self._engine(tmp_path, monkeypatch)
        engine.merge_config_overlay("CTRL_SCATTER_S0", {"tether_id": "operator_set"})

        assert engine._cached_graph["CTRL_SCATTER_S0"]["tether_id"] == "operator_set"

    def test_whitespace_is_treated_as_blank(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        engine = self._engine(tmp_path, monkeypatch)
        engine.merge_config_overlay("CTRL_SCATTER_S0", {"tether_id": "   "})

        assert engine._cached_graph["CTRL_SCATTER_S0"]["tether_id"] == "scatter_84fe89ba"

    def test_non_string_values_are_untouched(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Only empty *strings* are dropped; 0 and False are real values."""
        engine = self._engine(tmp_path, monkeypatch)
        engine.merge_config_overlay(
            "CTRL_SCATTER_S0", {"auto_resume_after": 0, "enabled": False}
        )

        cfg = engine._cached_graph["CTRL_SCATTER_S0"]
        assert cfg["auto_resume_after"] == 0
        assert cfg["enabled"] is False

    def test_an_all_blank_overlay_records_nothing(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        engine = self._engine(tmp_path, monkeypatch)
        engine.merge_config_overlay("CTRL_SCATTER_S0", {"tether_id": "", "x": ""})

        assert engine._overlays == {}


# ── Deterministic fan-in: the merge must receive its lanes' outputs ────────────


def _seed_completed_lanes(
    broker_obj: LocalMessageBroker,
    lanes: list[str],
    tether: str,
    complete_order: list[str] | None = None,
) -> None:
    """Create and complete scatter lanes the way production does.

    The lane rows must be created **by a scatter routing to them**, not injected
    directly: :meth:`route_task` stamps ``tether_id`` on the *successor* rows it
    inserts, never on the row it is closing. A directly-injected lane therefore has
    no tether, and a tether-scoped lookup would correctly find nothing — which is a
    fixture artefact, not the behaviour under test.

    Completion is then applied with SQL so *completion* order can be varied
    independently of *declaration* order.
    """
    broker_obj.inject_task(job_id=JOB, payload_path="/in.md", starting_node="SCATTER")
    scatter = broker_obj.fetch_and_lock_task(
        "scatter_agent", FakeTopology({"SCATTER": "none"})
    )
    assert scatter is not None
    broker_obj.route_task(
        row_id=int(scatter["id"]),
        job_id=JOB,
        next_node_str=",".join(lanes),
        new_payload_path="/in.md",
        status="completed",
        tether_id=tether,
    )

    conn = broker_obj._get_conn()
    for lane in (complete_order or lanes):
        conn.execute(
            "UPDATE task_queue SET lock_status = 'completed', payload_path = ? "
            "WHERE job_id = ? AND current_node = ?",
            (f"/out/{lane}.md", JOB, lane),
        )
    conn.commit()


class TestCompletedPayloadLookup:
    """The broker query that feeds a deterministic fan-in node."""

    def _complete(
        self, broker_obj: LocalMessageBroker, node: str, out_path: str, tether: str
    ) -> None:
        task = broker_obj.fetch_and_lock_task("agent_1", FakeTopology({node: "none"}))
        assert task is not None
        broker_obj.route_task(
            row_id=int(task["id"]),
            job_id=JOB,
            next_node_str="GATHER",
            new_payload_path=out_path,
            status="completed",
            tether_id=tether,
        )

    def test_a_completed_node_reports_its_output_path(
        self, broker: LocalMessageBroker
    ) -> None:
        """A completed row records what the node produced, so it can be looked up.

        .. note::
           This docstring used to read: "``route_task`` writes the new payload onto
           the row it closes, so the completed row is the authoritative record of
           what that node produced." That reasoning was wrong and it cost defect
           E1. ``new_payload_path`` is what the *successor reads*; under
           ``Payload_Mode = "Unified Ledger"`` that is one shared file for every
           lane. The record now lives in its own ``output_path`` column, and the
           tests that pin that distinction are in
           ``tests/test_payload_lineage.py``.

           The cases below still pass ``new_payload_path`` alone, which exercises
           the documented fallback rather than the new column. That is deliberate
           coverage of the legacy read path, not an oversight.
        """
        broker.inject_task(job_id=JOB, payload_path="/in.md", starting_node="L1")
        self._complete(broker, "L1", "/out/L1.md", "scope_a")

        found = broker.get_completed_payload_paths(JOB, ["L1"])
        assert found == {"L1": "/out/L1.md"}

    def test_all_lanes_of_a_scatter_are_returned(
        self, broker: LocalMessageBroker
    ) -> None:
        lanes = [f"L{i}" for i in range(1, 9)]
        broker.inject_task(
            job_id=JOB, payload_path="/in.md", starting_node=", ".join(lanes)
        )
        for lane in lanes:
            self._complete(broker, lane, f"/out/{lane}.md", "scope_a")

        found = broker.get_completed_payload_paths(JOB, lanes)
        assert len(found) == 8, f"expected all 8 lanes, got {sorted(found)}"

    def test_incomplete_nodes_are_absent(self, broker: LocalMessageBroker) -> None:
        broker.inject_task(job_id=JOB, payload_path="/in.md", starting_node="L1, L2")
        self._complete(broker, "L1", "/out/L1.md", "scope_a")

        found = broker.get_completed_payload_paths(JOB, ["L1", "L2"])
        assert "L1" in found
        assert "L2" not in found

    def test_the_tether_scopes_the_lookup(self, broker: LocalMessageBroker) -> None:
        """One scatter's merge must not gather another scatter's lanes."""
        _seed_completed_lanes(broker, ["L1", "L2"], "scope_a")
        conn = broker._get_conn()
        conn.execute(
            "UPDATE task_queue SET tether_id = 'scope_b' "
            "WHERE job_id = ? AND current_node = 'L2'",
            (JOB,),
        )
        conn.commit()

        assert broker.get_completed_payload_paths(
            JOB, ["L1", "L2"], tether_id="scope_a"
        ) == {"L1": "/out/L1.md"}

    def test_an_unscoped_lookup_ignores_tethers(
        self, broker: LocalMessageBroker
    ) -> None:
        """Correct for a plain fan-in that sits outside any scatter."""
        _seed_completed_lanes(broker, ["L1", "L2"], "scope_a")
        conn = broker._get_conn()
        conn.execute(
            "UPDATE task_queue SET tether_id = 'scope_b' "
            "WHERE job_id = ? AND current_node = 'L2'",
            (JOB,),
        )
        conn.commit()

        assert len(broker.get_completed_payload_paths(JOB, ["L1", "L2"])) == 2

    def test_other_jobs_are_not_gathered(self, broker: LocalMessageBroker) -> None:
        broker.inject_task(job_id=JOB, payload_path="/in.md", starting_node="L1")
        broker.inject_task(job_id="other", payload_path="/in.md", starting_node="L1")
        self._complete(broker, "L1", "/out/mine.md", "scope_a")

        assert broker.get_completed_payload_paths("other", ["L1"]) == {}

    def test_an_empty_node_list_is_safe(self, broker: LocalMessageBroker) -> None:
        assert broker.get_completed_payload_paths(JOB, []) == {}


class TestDeterministicFanInWiring:
    """A fan-in handler is useless without its inputs.

    ``execute_deterministic_node``'s fourth parameter, ``predecessor_payloads``,
    was never passed — it defaulted to ``[]``, so ``_handle_merge`` merged only the
    node's own payload. An 8-lane scatter logged ``Merged 1 sources``.

    The AI-node fan-in injection further down ``execute_cycle`` cannot cover this:
    deterministic nodes return before reaching it, so it has never applied to
    ``CTRL_MERGE`` at all.
    """

    def _worker(self, broker_obj: LocalMessageBroker) -> Any:
        from maccre_core.orchestration.swarm_worker import (
            UniversalSwarmWorker,
            resolve_worker_id,
        )

        worker = UniversalSwarmWorker.__new__(UniversalSwarmWorker)
        worker.slot = 0
        worker.worker_id = resolve_worker_id(0)
        worker.broker = broker_obj
        worker.topology = None
        return worker

    def test_the_dispatch_passes_predecessor_payloads(self) -> None:
        """Structural guard: the argument must actually be supplied."""
        source = inspect.getsource(
            __import__(
                "maccre_core.orchestration.swarm_worker", fromlist=["x"]
            ).UniversalSwarmWorker.execute_cycle
        )
        call_at = source.index("execute_deterministic_node(")
        tail = source[call_at:call_at + 300]
        assert "_det_predecessors" in tail, (
            "execute_deterministic_node must receive predecessor payloads"
        )

    def test_all_lanes_are_gathered_in_declared_order(
        self, broker: LocalMessageBroker
    ) -> None:
        """Order follows ``wait_for``, not completion time.

        A merge whose section order depended on which lane finished first would
        produce a different document on every run.
        """
        lanes = [f"L{i}" for i in range(1, 9)]
        # Complete in reverse, so declaration order and completion order differ.
        _seed_completed_lanes(
            broker, lanes, "scope_a", complete_order=list(reversed(lanes))
        )

        worker = self._worker(broker)
        paths = worker._gather_predecessor_payloads(
            {"tether_id": "scope_a", "current_node": "GATHER"},
            {"wait_for": "|".join(lanes)},
            JOB,
        )

        assert paths == [f"/out/{lane}.md" for lane in lanes]

    def test_eight_lanes_yield_eight_payloads(
        self, broker: LocalMessageBroker
    ) -> None:
        """The headline regression: 8 in, 8 gathered — not 1."""
        lanes = [f"L{i}" for i in range(1, 9)]
        _seed_completed_lanes(broker, lanes, "scope_a")

        worker = self._worker(broker)
        paths = worker._gather_predecessor_payloads(
            {"tether_id": "scope_a", "current_node": "GATHER"},
            {"wait_for": "|".join(lanes)},
            JOB,
        )
        assert len(paths) == 8

    def test_a_node_with_no_wait_for_gathers_nothing(
        self, broker: LocalMessageBroker
    ) -> None:
        """True of every deterministic node except the fan-in ones."""
        worker = self._worker(broker)
        for wait_for in ("none", "", "null", None):
            assert worker._gather_predecessor_payloads(
                {"tether_id": "", "current_node": "CTRL_PAUSE"},
                {"wait_for": wait_for},
                JOB,
            ) == []

    def test_a_comma_delimited_wait_for_is_accepted(
        self, broker: LocalMessageBroker
    ) -> None:
        _seed_completed_lanes(broker, ["L1", "L2"], "scope_a")

        worker = self._worker(broker)
        paths = worker._gather_predecessor_payloads(
            {"tether_id": "scope_a", "current_node": "GATHER"},
            {"wait_for": "L1,L2"},
            JOB,
        )
        assert len(paths) == 2

    def test_a_foreign_tether_gathers_nothing(
        self, broker: LocalMessageBroker
    ) -> None:
        _seed_completed_lanes(broker, ["L1"], "scope_a")

        worker = self._worker(broker)
        assert worker._gather_predecessor_payloads(
            {"tether_id": "scope_b", "current_node": "GATHER"},
            {"wait_for": "L1"},
            JOB,
        ) == []

    def test_a_partial_gather_is_reported(
        self, broker: LocalMessageBroker, caplog: pytest.LogCaptureFixture
    ) -> None:
        """The gate should have held the node; a shortfall means they disagree."""
        import logging

        _seed_completed_lanes(broker, ["L1", "L2"], "scope_a", complete_order=["L1"])

        worker = self._worker(broker)
        with caplog.at_level(logging.WARNING):
            paths = worker._gather_predecessor_payloads(
                {"tether_id": "scope_a", "current_node": "GATHER"},
                {"wait_for": "L1|L2"},
                JOB,
            )

        assert len(paths) == 1
        assert any("1/2" in r.message or "missing" in r.message for r in caplog.records)


# ── Fan-in vs recursion, and the manufactured FAILED node ─────────────────────


class TestFanInIsNotRecursion:
    """A convergent fan-in must never be mistaken for runaway recursion.

    Found live on an 8-lane scatter where one lane failed.

    ``route_task``'s fan-in detection skipped the recursion counter only when the
    target row was ``open``. But when a lane fails, the gather gate moves the merge
    row to ``cancelled`` (``fetch_and_lock_task``'s ``upstream_failed`` branch). Every
    remaining lane then arrived at a row that was neither ``open`` nor ``completed``,
    fell through to the ``ON CONFLICT`` clause, and incremented
    ``loop_iteration_count``. At eight lanes the count passed ``max_recursion=3`` and
    the merge was rerouted as though it were recursing. It never ran.
    """

    def _arrive(self, broker_obj: LocalMessageBroker, source: str, target: str) -> None:
        """Route *source* -> *target*, as one lane completing would.

        The source row is addressed directly rather than via
        ``fetch_and_lock_task``, which claims the *oldest* open task — after the
        first arrival that is the fan-in target itself, and routing it to itself
        would be genuine recursion rather than the fan-in under test.
        """
        broker_obj.inject_task(job_id=JOB, payload_path="/in.md", starting_node=source)
        found = broker_obj._get_conn().execute(
            "SELECT id FROM task_queue WHERE job_id = ? AND current_node = ?",
            (JOB, source),
        ).fetchone()
        assert found is not None, f"no row for {source}"
        broker_obj.route_task(
            row_id=int(found[0]),
            job_id=JOB,
            next_node_str=target,
            new_payload_path=f"/out/{source}.md",
            status="completed",
            tether_id="scope_a",
        )

    def _count(self, broker_obj: LocalMessageBroker, node: str) -> tuple[str, int]:
        cur = broker_obj._get_conn().execute(
            "SELECT lock_status, loop_iteration_count FROM task_queue "
            "WHERE job_id = ? AND current_node = ?",
            (JOB, node),
        )
        found = cur.fetchone()
        assert found is not None
        return str(found[0]), int(found[1])

    def test_eight_lanes_converging_do_not_increment_the_counter(
        self, broker: LocalMessageBroker
    ) -> None:
        for i in range(1, 9):
            self._arrive(broker, f"L{i}", "GATHER")

        status, count = self._count(broker, "GATHER")
        assert count == 0, f"a fan-in must not look like recursion, got count={count}"
        assert status == "open"

    def test_a_cancelled_target_does_not_accrue_recursion(
        self, broker: LocalMessageBroker
    ) -> None:
        """The exact live sequence: gate cancels the merge, more lanes arrive."""
        self._arrive(broker, "L1", "GATHER")
        conn = broker._get_conn()
        conn.execute(
            "UPDATE task_queue SET lock_status = 'cancelled' "
            "WHERE job_id = ? AND current_node = 'GATHER'",
            (JOB,),
        )
        conn.commit()

        for i in range(2, 9):
            self._arrive(broker, f"L{i}", "GATHER")

        _status, count = self._count(broker, "GATHER")
        assert count == 0, (
            f"a gate-cancelled row must not accrue recursion counts, got {count}"
        )

    def test_a_paused_target_is_not_reopened(
        self, broker: LocalMessageBroker
    ) -> None:
        """Reopening a paused row would walk straight through a HITL gate."""
        self._arrive(broker, "L1", "GATHER")
        conn = broker._get_conn()
        conn.execute(
            "UPDATE task_queue SET lock_status = 'paused' "
            "WHERE job_id = ? AND current_node = 'GATHER'",
            (JOB,),
        )
        conn.commit()

        self._arrive(broker, "L2", "GATHER")

        status, _count = self._count(broker, "GATHER")
        assert status == "paused"

    def test_genuine_recursion_is_still_counted(
        self, broker: LocalMessageBroker
    ) -> None:
        """The guard must keep working for the case it exists for.

        A node that has *completed* and is re-queued is really recursing.
        """
        broker.inject_task(job_id=JOB, payload_path="/in.md", starting_node="LOOP")
        topo = FakeTopology({"LOOP": "none"})
        for _ in range(2):
            task = broker.fetch_and_lock_task("agent_1", topo)
            assert task is not None
            broker.route_task(
                row_id=int(task["id"]),
                job_id=JOB,
                next_node_str="LOOP",
                new_payload_path="/out/loop.md",
                status="completed",
            )

        _status, count = self._count(broker, "LOOP")
        assert count >= 1, "a completed node re-queued is genuine recursion"

    def test_the_recursion_limit_marks_the_node_failed(
        self, broker: LocalMessageBroker
    ) -> None:
        """And does NOT create a node named FAILED."""
        broker.inject_task(job_id=JOB, payload_path="/in.md", starting_node="LOOP")
        topo = FakeTopology({"LOOP": "none"})
        for _ in range(6):
            task = broker.fetch_and_lock_task("agent_1", topo)
            if task is None:
                break
            broker.route_task(
                row_id=int(task["id"]),
                job_id=JOB,
                next_node_str="LOOP",
                new_payload_path="/out/loop.md",
                status="completed",
                max_recursion=3,
            )

        status, _count = self._count(broker, "LOOP")
        assert status == "failed", f"expected the looping node to fail, got {status!r}"

        sentinel = broker._get_conn().execute(
            "SELECT COUNT(*) FROM task_queue WHERE job_id = ? AND current_node = 'FAILED'",
            (JOB,),
        ).fetchone()
        assert sentinel[0] == 0, (
            "the recursion limit must not manufacture a node named FAILED"
        )


class TestTerminalSentinelsAreNotExecutable:
    """A sentinel is an edge label, not a node — and must never run.

    Live consequence when one did: a row named ``FAILED`` was claimed, had no
    topology or roster entry, fell through to default agent handling, and **spent
    real inference**. The resulting ``FAILED_81.md`` was then captured by the flow
    engine as the step's output and handed to the next step as its input payload.
    """

    @pytest.mark.parametrize(
        "sentinel", ["FAILED", "DONE", "END", "STOP", "TERMINATE", "failed", "End"]
    )
    def test_a_sentinel_row_is_never_claimed(
        self, broker: LocalMessageBroker, sentinel: str
    ) -> None:
        conn = broker._get_conn()
        conn.execute(
            "INSERT INTO task_queue (job_id, payload_path, current_node) VALUES (?, ?, ?)",
            (JOB, "/in.md", sentinel),
        )
        conn.commit()

        task = broker.fetch_and_lock_task("agent_1", FakeTopology({}))

        assert task is None, f"a row named {sentinel!r} must not be executable"

    def test_a_sentinel_row_is_cancelled_not_left_open(
        self, broker: LocalMessageBroker
    ) -> None:
        """Left open, the pool would spin on it until the wall-clock timeout."""
        conn = broker._get_conn()
        conn.execute(
            "INSERT INTO task_queue (job_id, payload_path, current_node) VALUES (?, ?, ?)",
            (JOB, "/in.md", "FAILED"),
        )
        conn.commit()

        broker.fetch_and_lock_task("agent_1", FakeTopology({}))

        status = conn.execute(
            "SELECT lock_status FROM task_queue WHERE job_id = ? AND current_node = 'FAILED'",
            (JOB,),
        ).fetchone()
        assert status[0] == "cancelled"

    def test_a_real_node_beside_a_sentinel_still_runs(
        self, broker: LocalMessageBroker
    ) -> None:
        """The guard must skip the sentinel, not abandon the scan."""
        conn = broker._get_conn()
        conn.execute(
            "INSERT INTO task_queue (job_id, payload_path, current_node) VALUES (?, ?, ?)",
            (JOB, "/in.md", "FAILED"),
        )
        conn.commit()
        broker.inject_task(job_id=JOB, payload_path="/in.md", starting_node="REAL")

        task = broker.fetch_and_lock_task("agent_1", FakeTopology({"REAL": "none"}))

        assert task is not None
        assert task["current_node"] == "REAL"

    def test_routing_to_a_sentinel_creates_no_row(
        self, broker: LocalMessageBroker
    ) -> None:
        """The documented contract, asserted."""
        broker.inject_task(job_id=JOB, payload_path="/in.md", starting_node="N")
        task = broker.fetch_and_lock_task("agent_1", FakeTopology({"N": "none"}))
        assert task is not None
        broker.route_task(
            row_id=int(task["id"]),
            job_id=JOB,
            next_node_str="FAILED",
            new_payload_path="/out/n.md",
            status="failed",
        )

        count = broker._get_conn().execute(
            "SELECT COUNT(*) FROM task_queue WHERE job_id = ? AND current_node = 'FAILED'",
            (JOB,),
        ).fetchone()
        assert count[0] == 0
