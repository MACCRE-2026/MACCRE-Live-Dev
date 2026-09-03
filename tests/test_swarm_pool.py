# ┌─────────────────────────────────────────────────────────────────────────────┐
# │  MACCREv2 Test Suite — Phase 6.12 Task B1: DynamicSwarmPool                  │
# └─────────────────────────────────────────────────────────────────────────────┘
"""
tests/test_swarm_pool.py
========================
Phase 6.12 Task B1 — the pool's scaling and lifecycle logic, in isolation.

No database, no network, no LLM: a stub worker is injected via
``worker_factory``, so what is under test is purely the pool's own behaviour —
demand scaling, retirement, event discipline, error containment.

The properties that matter:

* **0 → N → 0.** No idle threads between bursts, and real fan-out during one.
* **Events are read-only.** The pool observes ``pause_event`` and ``stop_event``
  and never mutates them. The Phase 6.12 post-mortem traced its central bug to an
  observer setting a stop event, and the aborted first version of this module
  tried to retire threads exactly that way.
* **A drain means drained.** ``run_until_drained`` must not return while a worker
  is still mid-node — a locked task is not an *open* task, so the queue can read
  as empty while work is in flight.
"""
from __future__ import annotations

import inspect
import threading
import time
from typing import Any, Optional

from maccre_core.orchestration.concurrency import SCATTER_HARD_CAP
from maccre_core.orchestration.swarm_pool import DynamicSwarmPool, PoolResult
from maccre_core.orchestration.swarm_worker import CycleOutcome


class StubQueue:
    """A thread-safe token queue standing in for ``task_queue``."""

    def __init__(self, tasks: int = 0, work_duration: float = 0.0) -> None:
        self._lock = threading.Lock()
        self._remaining = tasks
        self._in_flight = 0
        self.work_duration = work_duration
        self.completed = 0

    def claim(self) -> bool:
        with self._lock:
            if self._remaining <= 0:
                return False
            self._remaining -= 1
            self._in_flight += 1
            return True

    def finish(self) -> None:
        with self._lock:
            self._in_flight -= 1
            self.completed += 1

    def ready(self) -> int:
        with self._lock:
            return max(0, self._remaining)

    def is_drained(self) -> bool:
        """Mirrors the engine's check: counts *open* work only.

        Deliberately ignores in-flight work, which is exactly the transient the
        pool has to defend against.
        """
        with self._lock:
            return self._remaining <= 0

    def add(self, count: int) -> None:
        with self._lock:
            self._remaining += count


class StubWorker:
    """Claims from a :class:`StubQueue` and reports a real :class:`CycleOutcome`."""

    def __init__(
        self,
        slot: int,
        queue: StubQueue,
        tracker: "ConcurrencyTracker | None" = None,
        raise_on_cycle: int | None = None,
    ) -> None:
        self.slot = slot
        self.queue = queue
        self.tracker = tracker
        self.raise_on_cycle = raise_on_cycle
        self.cycles = 0
        #: Every event object handed to execute_cycle, for the tripwire tests.
        self.seen_events: list[tuple[Any, Any]] = []

    def execute_cycle(
        self,
        pause_event: Optional[Any] = None,
        stop_event: Optional[Any] = None,
    ) -> CycleOutcome:
        self.cycles += 1
        self.seen_events.append((pause_event, stop_event))

        if self.raise_on_cycle is not None and self.cycles >= self.raise_on_cycle:
            raise RuntimeError(f"stub worker slot {self.slot} exploded")

        if stop_event is not None and stop_event.is_set():
            return CycleOutcome.STOPPED
        if pause_event is not None and not pause_event.is_set():
            time.sleep(0.01)
            return CycleOutcome.PAUSED

        if not self.queue.claim():
            time.sleep(0.01)
            return CycleOutcome.IDLE

        if self.tracker is not None:
            with self.tracker:
                time.sleep(self.queue.work_duration)
        elif self.queue.work_duration:
            time.sleep(self.queue.work_duration)
        self.queue.finish()
        return CycleOutcome.WORKED


class ConcurrencyTracker:
    """Counts how many workers are simultaneously *inside* node execution."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.current = 0
        self.peak = 0

    def __enter__(self) -> "ConcurrencyTracker":
        with self._lock:
            self.current += 1
            self.peak = max(self.peak, self.current)
        return self

    def __exit__(self, *_exc: object) -> None:
        with self._lock:
            self.current -= 1


def make_pool(
    queue: StubQueue,
    tracker: ConcurrencyTracker | None = None,
    max_workers: int | None = 8,
    raise_on_cycle: int | None = None,
    **kwargs: Any,
) -> tuple[DynamicSwarmPool, list[StubWorker]]:
    """A pool wired to stub workers. Returns the pool and the workers it built."""
    built: list[StubWorker] = []

    def factory(slot: int) -> StubWorker:
        worker = StubWorker(slot, queue, tracker, raise_on_cycle)
        built.append(worker)
        return worker

    kwargs.setdefault("poll_interval_seconds", 0.01)
    pool = DynamicSwarmPool(
        job_id="job_b1",
        max_workers=max_workers,
        demand_estimator=lambda cap: min(queue.ready(), cap),
        worker_factory=factory,
        **kwargs,
    )
    return pool, built


# ── Construction and clamping ─────────────────────────────────────────────────


class TestPoolConstruction:
    def test_max_workers_is_clamped_to_the_hard_cap(self) -> None:
        pool = DynamicSwarmPool(job_id="j", max_workers=9999)
        assert pool.max_workers == SCATTER_HARD_CAP

    def test_none_max_workers_uses_the_shared_default(self) -> None:
        from maccre_core.orchestration.concurrency import MAX_SCATTER_AGENTS

        assert DynamicSwarmPool(job_id="j").max_workers == MAX_SCATTER_AGENTS

    def test_nonpositive_max_workers_never_yields_a_dead_pool(self) -> None:
        for value in (0, -1):
            assert DynamicSwarmPool(job_id="j", max_workers=value).max_workers >= 1

    def test_starts_with_no_threads(self) -> None:
        """0 → N → 0 begins at zero: no ghost threads waiting for work."""
        pool = DynamicSwarmPool(job_id="j")
        assert pool.active_worker_count() == 0
        assert pool.peak_concurrency == 0

    def test_error_budget_scales_with_the_ceiling(self) -> None:
        assert DynamicSwarmPool(job_id="j", max_workers=4).max_worker_errors == 12
        assert DynamicSwarmPool(job_id="j", max_worker_errors=1).max_worker_errors == 1

    def test_idle_sleep_default_is_far_below_the_worker_default(self) -> None:
        """A 3 s idle sleep would throttle scale-down and burst pickup alike."""
        assert DynamicSwarmPool(job_id="j").idle_sleep_seconds <= 0.5


# ── Draining ──────────────────────────────────────────────────────────────────


class TestDraining:
    def test_empty_queue_drains_immediately(self) -> None:
        queue = StubQueue(tasks=0)
        pool, _ = make_pool(queue)
        result = pool.run_until_drained(queue.is_drained, timeout_seconds=10)
        assert result.drained is True
        assert result.succeeded is True

    def test_single_task_runs_on_one_worker(self) -> None:
        """The linear-flow case: fan-out must not appear where there is none."""
        queue = StubQueue(tasks=1)
        tracker = ConcurrencyTracker()
        pool, _ = make_pool(queue, tracker)
        result = pool.run_until_drained(queue.is_drained, timeout_seconds=20)
        assert result.drained is True
        assert queue.completed == 1
        assert tracker.peak == 1, "a single ready task must not open extra threads"

    def test_all_tasks_are_executed_exactly_once(self) -> None:
        queue = StubQueue(tasks=24, work_duration=0.005)
        pool, _ = make_pool(queue)
        result = pool.run_until_drained(queue.is_drained, timeout_seconds=60)
        assert result.drained is True
        assert queue.completed == 24
        assert result.cycles_worked == 24

    def test_pool_returns_to_zero_workers(self) -> None:
        """The closing half of 0 → N → 0."""
        queue = StubQueue(tasks=12, work_duration=0.005)
        pool, _ = make_pool(queue)
        pool.run_until_drained(queue.is_drained, timeout_seconds=60)
        assert pool.active_worker_count() == 0

    def test_does_not_return_while_a_node_is_still_in_flight(self) -> None:
        """A locked task is not an *open* task.

        ``is_drained`` reports empty as soon as the last task is claimed, so
        without the in-flight check the pool would return while a node was still
        writing its ledger.
        """
        queue = StubQueue(tasks=1)
        release = threading.Event()
        entered = threading.Event()

        class SlowWorker(StubWorker):
            def execute_cycle(
                self,
                pause_event: Optional[Any] = None,
                stop_event: Optional[Any] = None,
            ) -> CycleOutcome:
                if not self.queue.claim():
                    time.sleep(0.01)
                    return CycleOutcome.IDLE
                entered.set()
                release.wait(timeout=10)
                self.queue.finish()
                return CycleOutcome.WORKED

        pool = DynamicSwarmPool(
            job_id="job_b1",
            max_workers=4,
            demand_estimator=lambda cap: min(queue.ready(), cap),
            worker_factory=lambda slot: SlowWorker(slot, queue),
            poll_interval_seconds=0.01,
        )

        outcome: list[PoolResult] = []

        def run() -> None:
            outcome.append(pool.run_until_drained(queue.is_drained, timeout_seconds=30))

        supervisor = threading.Thread(target=run, daemon=True)
        supervisor.start()
        assert entered.wait(timeout=10), "worker never started the node"
        # Queue reads as drained, but the node is mid-flight.
        assert queue.is_drained() is True
        time.sleep(0.2)
        assert not outcome, "returned while a node was still executing"
        release.set()
        supervisor.join(timeout=20)
        assert outcome and outcome[0].drained is True

    def test_work_appearing_later_is_picked_up(self) -> None:
        """Re-spawn after the pool has already scaled to zero.

        The extra work is injected deterministically at the first moment the queue
        reads as drained, rather than on an arbitrary poll number — otherwise the
        pool can legitimately finish before the injection ever happens, and the
        test measures poll timing instead of behaviour.
        """
        queue = StubQueue(tasks=1)
        pool, _ = make_pool(queue)

        class DrainWithLateWork:
            def __init__(self, extra: int) -> None:
                self.extra = extra
                self.injected = False

            def __call__(self) -> bool:
                if not self.injected and queue.is_drained():
                    queue.add(self.extra)
                    self.injected = True
                    return False
                return queue.is_drained()

        probe = DrainWithLateWork(extra=3)
        result = pool.run_until_drained(probe, timeout_seconds=30)
        assert probe.injected is True, "the late work was never injected"
        assert result.drained is True
        assert queue.completed == 4


# ── Demand scaling ────────────────────────────────────────────────────────────


class TestDemandScaling:
    def test_a_burst_of_work_reaches_real_concurrency(self) -> None:
        """The actual Phase 6.12 deliverable, in miniature.

        Work is slow enough that lanes must overlap for the peak to exceed 1. With
        the pre-6.12 single-threaded loop this could only ever be 1.
        """
        queue = StubQueue(tasks=8, work_duration=0.25)
        tracker = ConcurrencyTracker()
        pool, _ = make_pool(queue, tracker, max_workers=8)
        result = pool.run_until_drained(queue.is_drained, timeout_seconds=60)

        assert result.drained is True
        assert queue.completed == 8
        assert tracker.peak >= 4, f"only reached {tracker.peak} concurrent workers"
        assert result.peak_concurrency >= 4

    def test_concurrency_never_exceeds_the_ceiling(self) -> None:
        queue = StubQueue(tasks=40, work_duration=0.05)
        tracker = ConcurrencyTracker()
        pool, _ = make_pool(queue, tracker, max_workers=3)
        result = pool.run_until_drained(queue.is_drained, timeout_seconds=90)
        assert tracker.peak <= 3
        assert result.peak_concurrency <= 3
        assert queue.completed == 40

    def test_wall_clock_beats_sequential_execution(self) -> None:
        """Concurrency has to actually save time, not merely interleave."""
        task_count = 8
        duration = 0.2
        queue = StubQueue(tasks=task_count, work_duration=duration)
        pool, _ = make_pool(queue, max_workers=8)

        started = time.monotonic()
        result = pool.run_until_drained(queue.is_drained, timeout_seconds=60)
        elapsed = time.monotonic() - started

        sequential = task_count * duration
        assert result.drained is True
        assert elapsed < sequential * 0.6, (
            f"took {elapsed:.2f}s against a {sequential:.2f}s sequential baseline"
        )

    def test_no_estimator_falls_back_to_one_worker(self) -> None:
        """Absent a sizing hint, behave like the old single worker.

        Speculatively opening the full ceiling would mean eight API connections
        for a linear flow.
        """
        queue = StubQueue(tasks=6, work_duration=0.05)
        tracker = ConcurrencyTracker()
        pool = DynamicSwarmPool(
            job_id="job_b1",
            max_workers=8,
            demand_estimator=None,
            worker_factory=lambda slot: StubWorker(slot, queue, tracker),
            poll_interval_seconds=0.01,
        )
        result = pool.run_until_drained(queue.is_drained, timeout_seconds=60)
        assert result.drained is True
        assert tracker.peak == 1
        assert queue.completed == 6

    def test_a_broken_estimator_does_not_stall_the_pool(self) -> None:
        queue = StubQueue(tasks=4, work_duration=0.01)

        def exploding(_cap: int) -> int:
            raise RuntimeError("broker is down")

        pool = DynamicSwarmPool(
            job_id="job_b1",
            max_workers=8,
            demand_estimator=exploding,
            worker_factory=lambda slot: StubWorker(slot, queue),
            poll_interval_seconds=0.01,
        )
        result = pool.run_until_drained(queue.is_drained, timeout_seconds=30)
        assert result.drained is True
        assert queue.completed == 4

    def test_over_reported_demand_is_harmless(self) -> None:
        """The estimator is advisory; over-counting costs an idle thread only."""
        queue = StubQueue(tasks=2, work_duration=0.01)
        pool = DynamicSwarmPool(
            job_id="job_b1",
            max_workers=8,
            demand_estimator=lambda cap: cap,  # always claims full demand
            worker_factory=lambda slot: StubWorker(slot, queue),
            poll_interval_seconds=0.01,
        )
        result = pool.run_until_drained(queue.is_drained, timeout_seconds=30)
        assert result.drained is True
        assert queue.completed == 2

    def test_slots_are_distinct_while_concurrent(self) -> None:
        queue = StubQueue(tasks=16, work_duration=0.1)
        built: list[StubWorker] = []

        def factory(slot: int) -> StubWorker:
            worker = StubWorker(slot, queue)
            built.append(worker)
            return worker

        pool = DynamicSwarmPool(
            job_id="job_b1",
            max_workers=4,
            demand_estimator=lambda cap: min(queue.ready(), cap),
            worker_factory=factory,
            poll_interval_seconds=0.01,
        )
        pool.run_until_drained(queue.is_drained, timeout_seconds=60)
        assert all(0 <= w.slot < 4 for w in built), [w.slot for w in built]

    def test_one_worker_instance_per_spawn(self) -> None:
        """Workers are never shared between threads.

        A shared broker was measured handing the same task to two workers.
        """
        queue = StubQueue(tasks=10, work_duration=0.05)
        pool, built = make_pool(queue, max_workers=4)
        result = pool.run_until_drained(queue.is_drained, timeout_seconds=60)
        assert len(built) == result.workers_spawned
        assert len({id(w) for w in built}) == len(built)


# ── Event discipline (doctrine) ───────────────────────────────────────────────


class TripwireEvent(threading.Event):
    """Records every mutation attempt."""

    def __init__(self) -> None:
        super().__init__()
        self.mutations: list[str] = []

    def set(self) -> None:
        self.mutations.append("set")
        super().set()

    def clear(self) -> None:
        self.mutations.append("clear")
        super().clear()


class TestEventObserverDiscipline:
    def test_pool_never_mutates_the_stop_event(self) -> None:
        queue = StubQueue(tasks=5, work_duration=0.01)
        stop = TripwireEvent()
        pool, _ = make_pool(queue)
        pool.run_until_drained(queue.is_drained, stop_event=stop, timeout_seconds=30)
        assert stop.mutations == []

    def test_pool_never_mutates_the_pause_event(self) -> None:
        queue = StubQueue(tasks=5, work_duration=0.01)
        pause = TripwireEvent()
        pause.set()
        pause.mutations.clear()
        pool, _ = make_pool(queue)
        pool.run_until_drained(queue.is_drained, pause_event=pause, timeout_seconds=30)
        assert pause.mutations == []

    def test_pool_owns_a_separate_shutdown_event(self) -> None:
        """The pool signals its own threads with an event it created.

        That is the distinction the aborted first attempt got wrong: it tried to
        retire threads by setting a *caller's* stop event.
        """
        pool = DynamicSwarmPool(job_id="j")
        assert isinstance(pool._shutdown, threading.Event)

    def test_shutdown_source_never_touches_caller_events(self) -> None:
        source = inspect.getsource(DynamicSwarmPool)
        for forbidden in (
            "stop_event.set()",
            "stop_event.clear()",
            "pause_event.set()",
            "pause_event.clear()",
        ):
            assert forbidden not in source, f"pool mutates a caller event: {forbidden}"

    def test_events_are_forwarded_to_every_worker(self) -> None:
        queue = StubQueue(tasks=3, work_duration=0.01)
        pause = threading.Event()
        pause.set()
        stop = threading.Event()
        pool, built = make_pool(queue)
        pool.run_until_drained(
            queue.is_drained, pause_event=pause, stop_event=stop, timeout_seconds=30
        )
        assert built, "expected at least one worker"
        for worker in built:
            assert worker.seen_events, "worker never cycled"
            for seen_pause, seen_stop in worker.seen_events:
                assert seen_pause is pause
                assert seen_stop is stop


# ── Stop, pause, timeout ──────────────────────────────────────────────────────


class TestHaltPaths:
    def test_pre_set_stop_event_returns_stopped(self) -> None:
        queue = StubQueue(tasks=50, work_duration=0.01)
        stop = threading.Event()
        stop.set()
        pool, _ = make_pool(queue)
        result = pool.run_until_drained(queue.is_drained, stop_event=stop, timeout_seconds=30)
        assert result.stopped is True
        assert result.drained is False
        assert result.succeeded is False
        assert queue.completed == 0

    def test_stop_mid_run_halts_promptly(self) -> None:
        queue = StubQueue(tasks=500, work_duration=0.01)
        stop = threading.Event()
        pool, _ = make_pool(queue, max_workers=4)

        def stopper() -> None:
            time.sleep(0.25)
            stop.set()

        threading.Thread(target=stopper, daemon=True).start()
        started = time.monotonic()
        result = pool.run_until_drained(queue.is_drained, stop_event=stop, timeout_seconds=60)
        elapsed = time.monotonic() - started

        assert result.stopped is True
        assert elapsed < 20, f"took {elapsed:.1f}s to honour the stop"
        assert queue.completed < 500
        assert pool.active_worker_count() == 0

    def test_a_cleared_pause_event_holds_execution(self) -> None:
        queue = StubQueue(tasks=5, work_duration=0.01)
        pause = threading.Event()  # clear == held
        pool, _ = make_pool(queue, idle_retire_after=2)
        result = pool.run_until_drained(
            queue.is_drained, pause_event=pause, timeout_seconds=3
        )
        assert queue.completed == 0, "work executed while the flow was paused"
        assert result.drained is False

    def test_timeout_is_reported_not_raised(self) -> None:
        queue = StubQueue(tasks=1)
        blocked = threading.Event()

        class Blocking(StubWorker):
            def execute_cycle(
                self,
                pause_event: Optional[Any] = None,
                stop_event: Optional[Any] = None,
            ) -> CycleOutcome:
                blocked.wait(timeout=30)
                return CycleOutcome.IDLE

        pool = DynamicSwarmPool(
            job_id="job_b1",
            max_workers=2,
            demand_estimator=lambda cap: 1,
            worker_factory=lambda slot: Blocking(slot, queue),
            poll_interval_seconds=0.01,
        )
        result = pool.run_until_drained(queue.is_drained, timeout_seconds=0.5)
        blocked.set()
        assert result.timed_out is True
        assert result.succeeded is False

    def test_all_workers_are_joined_before_returning(self) -> None:
        queue = StubQueue(tasks=20, work_duration=0.02)
        pool, _ = make_pool(queue, max_workers=4)
        pool.run_until_drained(queue.is_drained, timeout_seconds=60)
        with pool._lock:
            threads = list(pool._threads)
        assert threads, "expected worker threads to have been spawned"
        assert not any(t.is_alive() for t in threads)


# ── Error containment ─────────────────────────────────────────────────────────


class TestErrorContainment:
    def test_a_raising_worker_does_not_raise_out_of_the_pool(self) -> None:
        queue = StubQueue(tasks=10, work_duration=0.01)
        pool, _ = make_pool(queue, raise_on_cycle=1, max_workers=2, max_worker_errors=2)
        result = pool.run_until_drained(queue.is_drained, timeout_seconds=30)
        assert result.errors, "worker failures should be reported, not swallowed"
        assert result.succeeded is False

    def test_persistent_worker_failure_aborts_rather_than_spinning(self) -> None:
        """Without an error budget the supervisor would respawn forever."""
        queue = StubQueue(tasks=100, work_duration=0.0)
        pool, _ = make_pool(queue, raise_on_cycle=1, max_workers=2, max_worker_errors=3)
        started = time.monotonic()
        result = pool.run_until_drained(queue.is_drained, timeout_seconds=30)
        elapsed = time.monotonic() - started
        assert result.aborted is True
        assert elapsed < 20
        assert len(result.errors) > 3

    def test_a_failing_worker_factory_is_contained(self) -> None:
        queue = StubQueue(tasks=5)

        def bad_factory(slot: int) -> StubWorker:
            raise RuntimeError("cannot build a worker")

        pool = DynamicSwarmPool(
            job_id="job_b1",
            max_workers=2,
            demand_estimator=lambda cap: 2,
            worker_factory=bad_factory,
            poll_interval_seconds=0.01,
            max_worker_errors=2,
        )
        result = pool.run_until_drained(queue.is_drained, timeout_seconds=20)
        assert result.aborted is True
        assert any("factory failed" in e for e in result.errors)

    def test_one_bad_worker_does_not_prevent_others_working(self) -> None:
        queue = StubQueue(tasks=6, work_duration=0.01)
        built: list[StubWorker] = []

        def factory(slot: int) -> StubWorker:
            # Only slot 0 explodes.
            worker = StubWorker(slot, queue, raise_on_cycle=1 if slot == 0 else None)
            built.append(worker)
            return worker

        pool = DynamicSwarmPool(
            job_id="job_b1",
            max_workers=4,
            demand_estimator=lambda cap: min(queue.ready(), cap),
            worker_factory=factory,
            poll_interval_seconds=0.01,
            max_worker_errors=50,
        )
        result = pool.run_until_drained(queue.is_drained, timeout_seconds=60)
        assert queue.completed == 6, "healthy workers should still drain the queue"
        assert result.drained is True


# ── Reuse across steps ────────────────────────────────────────────────────────


class TestReuse:
    def test_counters_reset_between_runs(self) -> None:
        """The flow engine calls the pool once per step on one instance."""
        queue = StubQueue(tasks=4, work_duration=0.01)
        pool, _ = make_pool(queue)
        first = pool.run_until_drained(queue.is_drained, timeout_seconds=30)
        assert first.cycles_worked == 4

        queue.add(3)
        second = pool.run_until_drained(queue.is_drained, timeout_seconds=30)
        assert second.cycles_worked == 3, "cycle count leaked from the previous run"
        assert second.drained is True

    def test_errors_do_not_leak_between_runs(self) -> None:
        queue = StubQueue(tasks=2, work_duration=0.0)
        pool, _ = make_pool(queue, raise_on_cycle=1, max_workers=1, max_worker_errors=1)
        first = pool.run_until_drained(queue.is_drained, timeout_seconds=20)
        assert first.errors

        healthy = StubQueue(tasks=2, work_duration=0.0)
        pool.worker_factory = lambda slot: StubWorker(slot, healthy)
        second = pool.run_until_drained(healthy.is_drained, timeout_seconds=20)
        assert second.errors == []
        assert second.drained is True

    def test_a_stopped_run_can_be_followed_by_a_clean_one(self) -> None:
        queue = StubQueue(tasks=6, work_duration=0.01)
        stop = threading.Event()
        stop.set()
        pool, _ = make_pool(queue)
        assert pool.run_until_drained(
            queue.is_drained, stop_event=stop, timeout_seconds=20
        ).stopped is True

        result = pool.run_until_drained(queue.is_drained, timeout_seconds=30)
        assert result.drained is True
        assert queue.completed == 6


# ── Result shape ──────────────────────────────────────────────────────────────


class TestPoolResult:
    def test_succeeded_requires_a_clean_drain(self) -> None:
        assert PoolResult(drained=True).succeeded is True
        assert PoolResult(drained=True, stopped=True).succeeded is False
        assert PoolResult(drained=True, timed_out=True).succeeded is False
        assert PoolResult(drained=True, aborted=True).succeeded is False
        assert PoolResult().succeeded is False

    def test_errors_default_is_not_shared_between_instances(self) -> None:
        a, b = PoolResult(), PoolResult()
        a.errors.append("boom")
        assert b.errors == []


# ── Phase 6.13 Task A5: the drain check must be honest ────────────────────────


class TestOrphanedLockStall:
    """A5 — an empty-and-idle queue is not proof the work got done.

    The pool declares a drain when nothing is claimable and no worker is running.
    A task a worker claimed and then abandoned satisfies both: it is ``locked``,
    so it is not ``open`` and does not count as claimable, and the worker that
    held it is gone, so nothing is active. That combination used to report as a
    clean drain, and the flow reported the step ``completed`` for a node that
    never executed — the rollback's signature failure.

    These tests use a ``locked_probe`` that reports held locks directly, which is
    what the flow engine now passes (``count_by_status("locked")``).
    """

    def test_a_held_lock_with_no_worker_is_not_a_drain(self) -> None:
        queue = StubQueue(tasks=0)
        pool, _ = make_pool(queue)

        result = pool.run_until_drained(
            queue.is_drained,
            timeout_seconds=10,
            locked_probe=lambda: 1,  # one row stuck locked, forever
            stall_grace_seconds=0.05,
        )

        assert result.drained is False, "an orphaned lock is not a clean drain"
        assert result.stalled is True
        assert result.succeeded is False

    def test_the_stall_reports_how_many_locks_were_held(self) -> None:
        """UT-0 needs the count to measure how often workers die."""
        queue = StubQueue(tasks=0)
        pool, _ = make_pool(queue)

        result = pool.run_until_drained(
            queue.is_drained,
            timeout_seconds=10,
            locked_probe=lambda: 3,
            stall_grace_seconds=0.05,
        )

        assert result.orphaned_locks == 3

    def test_a_clean_run_with_the_probe_still_drains(self) -> None:
        """The probe must not introduce false stalls on healthy flows."""
        queue = StubQueue(tasks=12, work_duration=0.005)
        pool, _ = make_pool(queue)

        result = pool.run_until_drained(
            queue.is_drained,
            timeout_seconds=60,
            locked_probe=lambda: 0,
            stall_grace_seconds=0.05,
        )

        assert result.drained is True
        assert result.stalled is False
        assert result.succeeded is True
        assert queue.completed == 12

    def test_a_transient_lock_reading_does_not_stall(self) -> None:
        """The grace period is required, not merely prudent.

        ``fetch_and_lock_task`` commits its claim before the pool counts the
        worker as active, so "locked but nobody active" happens legitimately on
        every single pickup. Without a grace period the pool would stall healthy
        flows constantly.
        """
        queue = StubQueue(tasks=0)
        pool, _ = make_pool(queue)
        readings = iter([2, 1, 0, 0, 0, 0, 0, 0])

        result = pool.run_until_drained(
            queue.is_drained,
            timeout_seconds=10,
            locked_probe=lambda: next(readings, 0),
            stall_grace_seconds=5.0,  # far longer than the transient
        )

        assert result.stalled is False
        assert result.drained is True

    def test_grace_period_resets_when_the_condition_clears(self) -> None:
        """A lock that comes and goes is work being picked up, not a stall."""
        queue = StubQueue(tasks=0)
        pool, _ = make_pool(queue)
        readings = iter([1, 0, 1, 0, 1, 0, 0, 0, 0, 0])

        result = pool.run_until_drained(
            queue.is_drained,
            timeout_seconds=10,
            locked_probe=lambda: next(readings, 0),
            stall_grace_seconds=0.5,
        )

        assert result.stalled is False
        assert result.drained is True

    def test_omitting_the_probe_preserves_the_old_behaviour(self) -> None:
        """Backward compatibility: no probe means no orphan detection.

        Documented rather than desirable — a caller that can count locks should
        always pass one.
        """
        queue = StubQueue(tasks=0)
        pool, _ = make_pool(queue)

        result = pool.run_until_drained(queue.is_drained, timeout_seconds=10)

        assert result.drained is True
        assert result.stalled is False

    def test_a_failing_probe_never_manufactures_a_stall(self) -> None:
        """A transient SQLite error must not fail a healthy flow."""
        queue = StubQueue(tasks=0)
        pool, _ = make_pool(queue)

        def exploding_probe() -> int:
            raise RuntimeError("database is locked")

        result = pool.run_until_drained(
            queue.is_drained,
            timeout_seconds=10,
            locked_probe=exploding_probe,
            stall_grace_seconds=0.05,
        )

        assert result.stalled is False
        assert result.drained is True

    def test_stall_returns_promptly_rather_than_burning_the_timeout(self) -> None:
        """A stall must be reported, not left to look like a timeout.

        The two need different responses: a timeout may want a longer budget,
        while a stall means a worker died.
        """
        queue = StubQueue(tasks=0)
        pool, _ = make_pool(queue)

        started = time.monotonic()
        result = pool.run_until_drained(
            queue.is_drained,
            timeout_seconds=30,
            locked_probe=lambda: 1,
            stall_grace_seconds=0.1,
        )
        elapsed = time.monotonic() - started

        assert result.stalled is True
        assert result.timed_out is False
        assert elapsed < 5.0, f"should stall quickly, took {elapsed:.1f}s"

    def test_stalled_is_not_confused_with_the_other_halt_reasons(self) -> None:
        queue = StubQueue(tasks=0)
        pool, _ = make_pool(queue)

        result = pool.run_until_drained(
            queue.is_drained,
            timeout_seconds=10,
            locked_probe=lambda: 1,
            stall_grace_seconds=0.05,
        )

        assert result.stalled is True
        assert result.stopped is False
        assert result.timed_out is False
        assert result.aborted is False

    def test_stall_does_not_auto_reclaim(self) -> None:
        """Locked decision: surface it loudly, do not silently retry.

        Automatic reclaim is deferred until UT-0 measures how often workers
        actually die. A pool that quietly reclaimed and re-ran the node would hide
        exactly the signal that measurement needs — and risks double execution.
        """
        queue = StubQueue(tasks=0)
        pool, _ = make_pool(queue)
        probe_calls: list[int] = []

        def probe() -> int:
            probe_calls.append(1)
            return 1

        pool.run_until_drained(
            queue.is_drained,
            timeout_seconds=10,
            locked_probe=probe,
            stall_grace_seconds=0.05,
        )

        # The probe is read-only; nothing in the pool writes to the queue. Check
        # executable lines only — the docstring discusses reclaim at length.
        source = inspect.getsource(DynamicSwarmPool.run_until_drained)
        body = source[source.index('"""', source.index('"""') + 3) + 3:]
        assert "reclaim" not in body.lower(), (
            "the pool must not reclaim locks; A5 surfaces stalls instead"
        )
        assert probe_calls, "the probe should have been consulted"


class TestFlowEngineSurfacesTheStall:
    """A5 — the engine must not translate a stall into ``"completed"``."""

    def test_engine_passes_a_locked_probe(self) -> None:
        """Without the probe the pool cannot see an orphan at all."""
        from maccre_core.orchestration.flow_engine import FlowRunner

        source = inspect.getsource(FlowRunner._run_worker_pool)
        assert "locked_probe" in source
        assert 'count_by_status("locked")' in source

    def test_engine_returns_a_distinct_stalled_status(self) -> None:
        from maccre_core.orchestration.flow_engine import FlowRunner

        source = inspect.getsource(FlowRunner._run_worker_pool)
        assert 'return "stalled"' in source

        # And it must be checked before the success return.
        assert source.index("result.stalled") < source.index('return "completed"')

    def test_a_stalled_step_marks_the_session_failed(self) -> None:
        """The old code could not do this because it never found out.

        Updated 2026-09-01: this asserted the literal branch
        ``pool_status == "stalled"``. Both loops now test membership of
        ``("stalled", "timeout", "abandoned")``, because a timed-out or abandoned
        step is the same category of "work did not finish" and each used to be
        handled differently or not at all. The guarantee under test is unchanged
        and now wider, so the assertion follows the guarantee rather than the
        syntax that happened to implement it.
        """
        from maccre_core.orchestration.flow_engine import FlowRunner

        for method in (
            FlowRunner.execute_flow,
            FlowRunner.resume_flow,
        ):
            source = inspect.getsource(method)
            assert '"stalled"' in source, (
                f"{method.__name__} ignores a stalled step"
            )
            assert 'pool_status in ("stalled", "timeout", "abandoned")' in source, (
                f"{method.__name__} no longer handles a stall alongside the other "
                f"unfinished statuses"
            )
            assert 'update_session_status(job_id, "failed")' in source, (
                f"{method.__name__} does not record a stall as a failure"
            )


# ── F2: a held flow must not be staffed ───────────────────────────────────────


class TestPausedPoolDoesNotChurn:
    """Defect F2 — pausing mid-run rebuilt a worker roughly twenty times a second.

    ``_worker_loop`` treated ``PAUSED`` and ``IDLE`` as one outcome and retired on
    either, on the stated reasoning that "the supervisor re-spawns when demand
    returns, so retiring eagerly is cheap". That holds for IDLE and inverts for
    PAUSED:

    * IDLE means nothing is claimable, so demand is zero and nothing re-spawns.
    * PAUSED means work exists and the operator is holding it, so demand — measured
      from *open* rows — stays high and the supervisor re-spawns on the next tick.

    Each re-spawn is a full worker construction: in production a
    ``TopologyEngine`` and a ``LocalMessageBroker`` that runs schema DDL against
    the same SQLite file a task claim needs. Observed live on run
    ``job_20260901-205047-40sp``, where the operator pressed pause with
    ``CTRL_MERGE_S0`` still open and the pool rebuilt workers until the process was
    killed — 257 s of CPU.

    ``test_a_cleared_pause_event_holds_execution`` above already covered this path
    and passed throughout, because it asserted that no *work* happened. Nothing
    asserted what the pause **cost**. These tests assert the cost.
    """

    def test_a_held_pool_does_not_spawn_repeatedly(self) -> None:
        """The headline regression. Bounded construction, not one per tick."""
        queue = StubQueue(tasks=5, work_duration=0.01)
        pause = threading.Event()  # clear == held
        pool, built = make_pool(
            queue, idle_retire_after=2, poll_interval_seconds=0.01
        )

        pool.run_until_drained(
            queue.is_drained, pause_event=pause, timeout_seconds=2.0
        )

        # Two seconds at a 0.01s tick is ~200 opportunities to re-spawn. The old
        # code took most of them; the scaler now declines while paused.
        assert len(built) <= 2, (
            f"built {len(built)} workers while held — the pause is churning"
        )

    def test_the_spawn_counter_agrees(self) -> None:
        """Belt and braces: the pool's own accounting, not just the factory's.

        ``_workers_spawned`` increments inside ``_spawn``, so it counts slot
        acquisitions even if a construction later fails. If these two ever
        disagree, the factory count is the one lying.
        """
        queue = StubQueue(tasks=5, work_duration=0.01)
        pause = threading.Event()
        pool, built = make_pool(queue, poll_interval_seconds=0.01)

        result = pool.run_until_drained(
            queue.is_drained, pause_event=pause, timeout_seconds=2.0
        )

        assert result.workers_spawned <= 2
        assert result.workers_spawned == len(built)

    def test_no_work_executes_while_held(self) -> None:
        """The original assertion still has to hold. Fixing cost must not cost correctness."""
        queue = StubQueue(tasks=5, work_duration=0.01)
        pause = threading.Event()
        pool, _ = make_pool(queue, poll_interval_seconds=0.01)

        result = pool.run_until_drained(
            queue.is_drained, pause_event=pause, timeout_seconds=1.5
        )

        assert queue.completed == 0
        assert result.drained is False

    def test_the_scaler_declines_while_held(self) -> None:
        """Unit-level: the gate is in the scaler, so assert it there directly.

        The behavioural tests above could also be satisfied by the worker holding
        its slot. This pins the supervisor's half, which is the part that actually
        stops the storm.
        """
        queue = StubQueue(tasks=8, work_duration=0.01)
        pause = threading.Event()  # clear == held
        pool, built = make_pool(queue)

        pool._scale_to_demand(pause, None)

        assert built == [], "the scaler staffed a pool the operator is holding"
        assert pool.active_worker_count() == 0

    def test_the_scaler_staffs_a_running_pool(self) -> None:
        """The complement. A gate that never opens is not a gate.

        Without this, ``return`` at the top of ``_scale_to_demand`` would pass
        every test above while disabling the pool entirely.
        """
        queue = StubQueue(tasks=8, work_duration=0.05)
        pause = threading.Event()
        pause.set()  # set == running
        pool, built = make_pool(queue)
        try:
            pool._scale_to_demand(pause, None)
            assert built, "the scaler refused to staff a running pool"
        finally:
            pool._shutdown.set()
            pool._join_all()

    def test_an_absent_pause_event_is_not_a_pause(self) -> None:
        """``None`` means nothing can hold us, which must not read as held.

        Most callers in the suite pass no pause event at all. Treating absent as
        paused would silently disable the pool for all of them.
        """
        assert DynamicSwarmPool._is_paused(None) is False

        queue = StubQueue(tasks=3, work_duration=0.01)
        pool, _ = make_pool(queue, poll_interval_seconds=0.01)
        result = pool.run_until_drained(queue.is_drained, timeout_seconds=30)

        assert result.drained is True
        assert queue.completed == 3

    def test_pause_state_has_one_reading(self) -> None:
        """The set/clear convention is inverted and easy to get backwards.

        Three call sites read it — the scaler, the poll backoff and the worker
        branch. They read it through one helper so they cannot disagree, which is
        the same rule that applies to node-id derivation.
        """
        held = threading.Event()
        running = threading.Event()
        running.set()

        assert DynamicSwarmPool._is_paused(held) is True
        assert DynamicSwarmPool._is_paused(running) is False


class TestPausedWorkerHoldsItsSlot:
    """F2, the worker's half — a brief pause must not force a full rebuild."""

    def test_a_paused_worker_survives_more_cycles_than_idle_retirement(self) -> None:
        """A paused worker keeps cycling past ``idle_retire_after``.

        With the two outcomes folded together, ``idle_retire_after=2`` retired a
        paused worker on its second pause poll. It should now stay until
        ``pause_hold_seconds``.
        """
        queue = StubQueue(tasks=1, work_duration=0.01)
        pause = threading.Event()  # held
        pool, built = make_pool(
            queue,
            max_workers=1,
            idle_retire_after=2,
            pause_hold_seconds=30.0,  # far longer than this test runs
            poll_interval_seconds=0.01,
        )
        # Staff the pool while running, then hold it.
        pause.set()
        pool._scale_to_demand(pause, None)
        assert len(built) == 1
        pause.clear()

        try:
            time.sleep(0.6)
            # The stub sleeps 0.01s per paused cycle, so ~0.6s is dozens of polls,
            # each of which used to count toward a 2-cycle retirement budget.
            assert built[0].cycles > 5, (
                f"worker only cycled {built[0].cycles} times — it retired"
            )
            assert pool.active_worker_count() == 1, "the paused worker gave up its slot"
        finally:
            pool._shutdown.set()
            pool._join_all()

    def test_a_long_pause_eventually_frees_the_slot(self) -> None:
        """Held is not parked forever.

        Retiring here is safe only because the scaler will not replace it, so this
        test is meaningless without ``test_the_scaler_declines_while_held``.
        """
        queue = StubQueue(tasks=1, work_duration=0.01)
        pause = threading.Event()
        pool, built = make_pool(
            queue,
            max_workers=1,
            pause_hold_seconds=0.15,
            poll_interval_seconds=0.01,
        )
        pause.set()
        pool._scale_to_demand(pause, None)
        assert len(built) == 1
        pause.clear()

        try:
            deadline = time.monotonic() + 5.0
            while pool.active_worker_count() > 0 and time.monotonic() < deadline:
                time.sleep(0.02)
            assert pool.active_worker_count() == 0, (
                "the worker never retired despite pause_hold_seconds elapsing"
            )
        finally:
            pool._shutdown.set()
            pool._join_all()

    def test_idle_retirement_is_unchanged(self) -> None:
        """The IDLE path was correct and must stay correct.

        An empty queue with no pause: workers find nothing, retire on
        ``idle_retire_after``, and the pool settles at zero. This is the 0 → N → 0
        contract the module exists to provide.
        """
        queue = StubQueue(tasks=0)
        pool, built = make_pool(
            queue, max_workers=4, idle_retire_after=2, poll_interval_seconds=0.01
        )

        result = pool.run_until_drained(queue.is_drained, timeout_seconds=30)

        assert result.drained is True
        assert pool.active_worker_count() == 0

    def test_a_cancel_is_honoured_promptly_while_held(self) -> None:
        """The escape hatch. A held flow must still be cancellable.

        This is the one that would have let the operator out of run
        ``40sp`` without killing the process — and it is why the poll backoff has
        to stay well under human patience.
        """
        queue = StubQueue(tasks=5, work_duration=0.01)
        pause = threading.Event()  # held from the start
        stop = threading.Event()
        pool, _ = make_pool(queue, poll_interval_seconds=0.01)

        def canceller() -> None:
            time.sleep(0.3)
            stop.set()

        threading.Thread(target=canceller, daemon=True).start()
        started = time.monotonic()
        result = pool.run_until_drained(
            queue.is_drained, pause_event=pause, stop_event=stop, timeout_seconds=30
        )
        elapsed = time.monotonic() - started

        assert result.stopped is True
        assert elapsed < 5, f"took {elapsed:.1f}s to honour a cancel while held"
        assert pool.active_worker_count() == 0

    def test_resuming_a_held_pool_gets_the_work_done(self) -> None:
        """End to end: hold, release, and the queue still drains.

        The whole point of declining to spawn while paused is that it costs
        nothing on resume. If the scaler's early return left the pool unable to
        recover, every test above would still pass.
        """
        queue = StubQueue(tasks=4, work_duration=0.01)
        pause = threading.Event()  # held
        pool, _ = make_pool(queue, max_workers=4, poll_interval_seconds=0.01)

        def resumer() -> None:
            time.sleep(0.4)
            pause.set()  # the TUI's job in production; the test stands in for it

        threading.Thread(target=resumer, daemon=True).start()
        result = pool.run_until_drained(
            queue.is_drained, pause_event=pause, timeout_seconds=30
        )

        assert result.drained is True, "the pool never recovered from the pause"
        assert queue.completed == 4


# ── F3: a hold nobody can release ─────────────────────────────────────────────


class TestAbandonedPause:
    """Defect F3 — the flow was held and nothing could ever release it.

    ``pause_event`` is owned by the TUI; the pool and the flow engine only observe
    it. Defect F1 crashed the Textual app *while the event was clear*, and the
    engine runs on its own thread, so it carried on with no UI. Nothing would ever
    set the event again.

    Before this, the pool had no way to find that out. It waited out
    ``timeout_seconds`` — one hour by default — and returned ``timed_out``, which
    neither step loop acted on, so the session was then recorded ``completed`` over
    an unexecuted ``CTRL_MERGE``. Live run ``job_20260901-205047-40sp`` was inside
    that window when it was killed.

    The pool still does not *guess*. It asks, via ``pause_owner_alive``, because the
    caller is the only party that can honestly answer.
    """

    def test_a_dead_owner_ends_the_run_promptly(self) -> None:
        queue = StubQueue(tasks=5, work_duration=0.01)
        pause = threading.Event()  # held
        pool, _ = make_pool(queue, poll_interval_seconds=0.01)

        started = time.monotonic()
        result = pool.run_until_drained(
            queue.is_drained,
            pause_event=pause,
            timeout_seconds=60,  # would otherwise sit here for a minute
            pause_owner_alive=lambda: False,
        )
        elapsed = time.monotonic() - started

        assert result.pause_abandoned is True
        assert elapsed < 5, f"took {elapsed:.1f}s to notice the owner was gone"

    def test_abandoned_is_distinct_from_timeout(self) -> None:
        """Folding this into ``timed_out`` would send the operator hunting a slow
        node when in fact their UI had died. Different cause, different fix."""
        queue = StubQueue(tasks=5, work_duration=0.01)
        pause = threading.Event()
        pool, _ = make_pool(queue, poll_interval_seconds=0.01)

        result = pool.run_until_drained(
            queue.is_drained,
            pause_event=pause,
            timeout_seconds=60,
            pause_owner_alive=lambda: False,
        )

        assert result.pause_abandoned is True
        assert result.timed_out is False
        assert result.drained is False
        assert result.stalled is False

    def test_a_live_owner_is_left_alone(self) -> None:
        """A deliberate long pause with a healthy UI must not be killed.

        This is why the check is a liveness question and not a timer. The operator
        pausing to read a ledger, or going to lunch, is legitimate.
        """
        queue = StubQueue(tasks=5, work_duration=0.01)
        pause = threading.Event()
        pool, _ = make_pool(queue, poll_interval_seconds=0.01)

        result = pool.run_until_drained(
            queue.is_drained,
            pause_event=pause,
            timeout_seconds=1.0,
            pause_owner_alive=lambda: True,
        )

        assert result.pause_abandoned is False
        assert result.timed_out is True, "should have ended on the budget, not the owner"

    def test_the_owner_is_not_consulted_while_running(self) -> None:
        """Only asked while held. A running flow's owner is irrelevant.

        Asking unconditionally would let a transiently-false predicate kill a
        perfectly healthy run.
        """
        queue = StubQueue(tasks=3, work_duration=0.01)
        asked: list[bool] = []

        def owner_alive() -> bool:
            asked.append(True)
            return False  # would abandon immediately if consulted

        pool, _ = make_pool(queue, poll_interval_seconds=0.01)
        result = pool.run_until_drained(
            queue.is_drained, timeout_seconds=30, pause_owner_alive=owner_alive
        )

        assert result.drained is True
        assert queue.completed == 3
        assert asked == [], "the owner was consulted despite the flow never being held"

    def test_absent_predicate_preserves_the_old_behaviour(self) -> None:
        """Opt-in. Callers that cannot answer get exactly what they got before."""
        queue = StubQueue(tasks=5, work_duration=0.01)
        pause = threading.Event()
        pool, _ = make_pool(queue, poll_interval_seconds=0.01)

        result = pool.run_until_drained(
            queue.is_drained, pause_event=pause, timeout_seconds=0.5
        )

        assert result.pause_abandoned is False
        assert result.timed_out is True

    def test_a_pause_ceiling_is_a_backstop_not_the_mechanism(self) -> None:
        """``max_pause_seconds`` exists for callers with no liveness signal.

        Off by default, deliberately: killing a flow because the operator went to
        lunch would be worse than the defect it guards against.
        """
        queue = StubQueue(tasks=5, work_duration=0.01)
        pause = threading.Event()
        pool, _ = make_pool(queue, poll_interval_seconds=0.01)

        result = pool.run_until_drained(
            queue.is_drained,
            pause_event=pause,
            timeout_seconds=60,
            max_pause_seconds=0.3,
        )

        assert result.pause_abandoned is True
        assert result.timed_out is False

    def test_a_resumed_hold_resets_the_clock(self) -> None:
        """Pausing twice must not accumulate towards the ceiling.

        Two ten-second pauses are not one twenty-second pause; treating them as
        one would kill a flow the operator had actively resumed.
        """
        queue = StubQueue(tasks=2, work_duration=0.01)
        pause = threading.Event()
        pause.set()  # running
        pool, _ = make_pool(queue, poll_interval_seconds=0.01)

        def toggler() -> None:
            for _ in range(3):
                pause.clear()
                time.sleep(0.15)
                pause.set()
                time.sleep(0.15)

        threading.Thread(target=toggler, daemon=True).start()
        result = pool.run_until_drained(
            queue.is_drained,
            pause_event=pause,
            timeout_seconds=30,
            max_pause_seconds=0.4,  # longer than any single hold above
        )

        assert result.pause_abandoned is False, "the hold clock did not reset on resume"
        assert result.drained is True
