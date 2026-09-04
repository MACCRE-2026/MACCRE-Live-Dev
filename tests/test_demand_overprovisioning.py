# ┌─────────────────────────────────────────────────────────────────────────────┐
# │  MACCREv2 Test Infrastructure — demand estimator over-provisioning          │
# └─────────────────────────────────────────────────────────────────────────────┘
"""
tests/test_demand_overprovisioning.py
=====================================
Guards the demand estimator against sizing the pool as though a task nobody has
claimed yet were unattended.

THE OBSERVED FAILURE
--------------------
On a full-suite run of 2026-09-03 00:11, one test failed::

    tests/test_integration_mandatory.py::TestMandatoryMultiStepFlow::
        test_linear_flow_stays_single_threaded
    AssertionError: linear flow used slots {0, 1}

It passed 5/5 in isolation and five consecutive full-suite runs afterwards. A
timing bound that loosens under load is a measurement artifact — but that test
asserts something about *concurrency*, and an assertion about concurrency that
changes answer under load is a statement about the pool.

THE MECHANISM
-------------
``_scale_to_demand`` computed ``target = active + ready``. That double-counts every
live worker which has not claimed yet: the worker is in ``_active``, and the task
it is about to take is still ``open``, so it is still counted in ``ready``.

A guard already existed for the *stale* case — ``_cached_demand`` returns
``is_fresh=False`` inside ``demand_recheck_seconds`` and the scaler refuses to size
on it. Its comment even recorded this symptom: *"Measured on a linear 3-step flow,
which opened two threads for one task at a time."*

**But it closed the window inside the interval, not at the interval boundary.**
When the throttle expired the scaler took a *fresh* estimate, and if the spawned
worker still had not claimed, that estimate still counted its task.

And because ``active`` grew while ``ready`` did not, the target grew by one on
every recheck. This was **not** a one-off spare worker — it was a ramp toward
``max_workers`` for a single task, bounded only by the ceiling. Measured on a
single-task queue with construction slower than the recheck interval:

============================  =========  ========
Metric                        Before     After
============================  =========  ========
``workers_spawned``           **5**      1
``workers_that_never_worked`` **4**      0
claim attempts for 1 task     **11**     3
============================  =========  ========

with the decision record reading ``(0,1,True,1) (1,1,True,2) (2,1,True,3)
(3,1,True,4) (4,1,True,5)``. That is the same construction storm as defect F2 —
each worker building a ``TopologyEngine`` and a ``LocalMessageBroker`` that runs
schema DDL against the very SQLite file the one real claim needs — reached by a
different route. F2 was *paused, so demand stays high*; this is *unclaimed, so
demand stays high*.

It is load-sensitive by construction, which is why it surfaced only under a full
suite: worker construction is slower under load, so the gap between *spawned* and
*claimed* widens past ``demand_recheck_seconds``.

THE FIX
-------
Subtract the workers already committed to consuming a ready task::

    unclaimed = live workers that have not yet executed a node
    target    = active + max(0, ready - unclaimed)

This leaves the scatter case — the reason ``active + ready`` was chosen — intact.
:class:`TestTheFixDoesNotCostConcurrency` is the guard on that, and it matters more
than the guards on the defect: capping the pool at one worker would "fix"
over-provisioning and destroy the entire Phase 6.12 deliverable.

WHAT THESE TESTS DO NOT CLAIM
-----------------------------
Over-provisioning was never duplicated execution, and
:class:`TestOverProvisioningWasNeverDoubleExecution` asserts that separately. The
atomic claim in the broker was always the authority; the loser simply retired. The
cost was wasted construction and lock contention, not a task run twice. Conflating
the two would have misprioritised the fix.
"""
from __future__ import annotations

import threading
import time
from typing import Any, Optional

from maccre_core.orchestration.swarm_pool import DynamicSwarmPool
from maccre_core.orchestration.swarm_worker import CycleOutcome


class SingleTaskQueue:
    """A queue of *n* tasks, claimable one at a time.

    ``ready()`` reports a task as available until it is actually claimed, which is
    what the real ``count_ready_tasks`` does: it counts ``open`` rows, and a row
    stays open until a worker's ``BEGIN EXCLUSIVE`` takes it. That property is the
    whole reason the double-count was possible.
    """

    def __init__(self, tasks: int = 1) -> None:
        self._lock = threading.Lock()
        self._remaining = tasks
        self.completed = 0
        self.claims_attempted = 0

    def claim(self) -> bool:
        with self._lock:
            self.claims_attempted += 1
            if self._remaining <= 0:
                return False
            self._remaining -= 1
            return True

    def finish(self) -> None:
        with self._lock:
            self.completed += 1

    def ready(self) -> int:
        with self._lock:
            return max(0, self._remaining)

    def is_drained(self) -> bool:
        with self._lock:
            return self._remaining <= 0

    def add_tasks(self, count: int) -> None:
        """Inject work mid-run, for the burst-arrives-later guard."""
        with self._lock:
            self._remaining += count


class SlowToStartWorker:
    """A worker whose *construction* is slow, which then claims normally.

    The delay is in ``__init__`` deliberately. The defect is about the gap between
    a slot being reserved and its worker claiming, and in production that gap is
    filled by building a ``TopologyEngine`` and a ``LocalMessageBroker``. A delay
    in ``execute_cycle`` would model a slow *node* — a different thing, and it
    would not reproduce this.
    """

    def __init__(
        self,
        slot: int,
        queue: SingleTaskQueue,
        construction_delay: float,
        executed_slots: set[int],
        lock: threading.Lock,
    ) -> None:
        self.slot = slot
        self.queue = queue
        self.executed_slots = executed_slots
        self._lock = lock
        time.sleep(construction_delay)

    def execute_cycle(
        self,
        pause_event: Optional[Any] = None,
        stop_event: Optional[Any] = None,
    ) -> CycleOutcome:
        if stop_event is not None and stop_event.is_set():
            return CycleOutcome.STOPPED
        if self.queue.claim():
            with self._lock:
                self.executed_slots.add(self.slot)
            time.sleep(0.02)
            self.queue.finish()
            return CycleOutcome.WORKED
        return CycleOutcome.IDLE


def _build_pool(
    queue: SingleTaskQueue,
    construction_delay: float,
    recheck: float,
    executed_slots: set[int],
    max_workers: int = 8,
) -> DynamicSwarmPool:
    lock = threading.Lock()
    return DynamicSwarmPool(
        job_id="overprovision-probe",
        max_workers=max_workers,
        demand_estimator=lambda _cap: queue.ready(),
        worker_factory=lambda slot: SlowToStartWorker(
            slot, queue, construction_delay, executed_slots, lock
        ),
        poll_interval_seconds=0.01,
        demand_recheck_seconds=recheck,
        idle_sleep_seconds=0.01,
    )


class TestUnclaimedWorkersAreNotDoubleCounted:
    """The regression guards. Each fails if ``- unclaimed`` is removed."""

    def test_slow_construction_does_not_ramp_the_pool(self) -> None:
        """The headline guard. One task means one worker, however slow the build.

        ``construction_delay`` is far above ``demand_recheck_seconds``, so the
        first worker is guaranteed to be still unclaimed when the throttle
        expires — the exact condition that produced 5 workers for 1 task.
        """
        queue = SingleTaskQueue(tasks=1)
        executed: set[int] = set()
        pool = _build_pool(queue, construction_delay=0.30, recheck=0.05,
                           executed_slots=executed)

        result = pool.run_until_drained(queue.is_drained, timeout_seconds=30)

        assert result.drained is True
        assert queue.completed == 1
        assert result.workers_spawned == 1, (
            f"one task must need one worker, but {result.workers_spawned} were "
            f"spawned. Decisions: {pool._spawn_decisions}"  # noqa: SLF001
        )
        assert result.workers_that_never_worked == 0, (
            f"{result.workers_that_never_worked} worker(s) were built and found "
            f"nothing. That is the over-provisioning this guards against."
        )

    def test_no_decision_double_counts_an_unclaimed_worker(self) -> None:
        """Asserts the *cause* is gone, not merely the symptom.

        A decision of ``(active_before>=1, ready==1, is_fresh=True, target>active)``
        is the double-count in the act: one worker alive, one task still counted
        open because that worker has not claimed it, and a target derived by adding
        the two. Checking the decision record rather than the spawn count means a
        future change that merely masks the arithmetic still fails here.
        """
        queue = SingleTaskQueue(tasks=1)
        executed: set[int] = set()
        pool = _build_pool(queue, construction_delay=0.30, recheck=0.05,
                           executed_slots=executed)

        pool.run_until_drained(queue.is_drained, timeout_seconds=30)
        decisions = pool._spawn_decisions  # noqa: SLF001 - the instrument under test

        double_counted = [
            d for d in decisions
            if d[0] >= 1 and d[1] is not None and d[3] > d[0] + max(0, d[1] - d[0])
        ]
        assert not double_counted, (
            f"a scaling decision counted an unclaimed worker's task as spare "
            f"capacity: {double_counted}. All decisions: {decisions}"
        )

    def test_claim_attempts_stay_proportionate(self) -> None:
        """Wasted claims are lock contention, which is the production cost.

        Before the fix a single task drew 11 claim attempts, each a
        ``BEGIN EXCLUSIVE`` in production, contending with the one claim that
        mattered. This bounds that waste rather than leaving it unmeasured.
        """
        queue = SingleTaskQueue(tasks=1)
        executed: set[int] = set()
        pool = _build_pool(queue, construction_delay=0.30, recheck=0.05,
                           executed_slots=executed)
        pool.run_until_drained(queue.is_drained, timeout_seconds=30)

        assert queue.claims_attempted <= 5, (
            f"{queue.claims_attempted} claim attempts for a single task. Each is a "
            f"BEGIN EXCLUSIVE contending with real claims in production."
        )

    def test_fast_construction_was_never_affected(self) -> None:
        """The control that localised the defect to the recheck boundary."""
        queue = SingleTaskQueue(tasks=1)
        executed: set[int] = set()
        pool = _build_pool(queue, construction_delay=0.0, recheck=0.50,
                           executed_slots=executed)

        result = pool.run_until_drained(queue.is_drained, timeout_seconds=30)

        assert result.workers_spawned == 1
        assert result.workers_that_never_worked == 0
        assert queue.completed == 1


class TestTheFixDoesNotCostConcurrency:
    """The most important class here.

    Capping the pool at one worker would satisfy every test above and destroy the
    Phase 6.12 deliverable. ``active + ready`` was chosen for a reason: the
    estimator counts *open* tasks, so a worker busy on lane 1 is not spare capacity
    for the remaining lanes, and using ``ready`` alone left an 8-lane scatter
    settled at 7. These guard that the subtraction did not reintroduce that.
    """

    def test_a_real_burst_still_reaches_full_width(self) -> None:
        queue = SingleTaskQueue(tasks=8)
        executed: set[int] = set()
        pool = _build_pool(queue, construction_delay=0.0, recheck=0.05,
                           executed_slots=executed, max_workers=8)

        result = pool.run_until_drained(queue.is_drained, timeout_seconds=60)

        assert result.drained is True
        assert queue.completed == 8
        assert result.workers_spawned >= 4, (
            f"a genuine 8-task burst reached only {result.workers_spawned} "
            f"workers. The unclaimed subtraction has over-corrected and the pool "
            f"is now under-provisioning. Decisions: "
            f"{pool._spawn_decisions}"  # noqa: SLF001
        )

    def test_a_burst_arriving_after_a_claim_still_scales_up(self) -> None:
        """The mid-flight case: one worker claimed, then work appears.

        Guards the arithmetic's other edge. With one worker claimed
        (``unclaimed == 0``) and seven tasks open, the target must still be eight —
        the subtraction must not suppress scaling once workers have claimed.
        """
        queue = SingleTaskQueue(tasks=1)
        executed: set[int] = set()
        pool = _build_pool(queue, construction_delay=0.0, recheck=0.02,
                           executed_slots=executed, max_workers=8)

        added = threading.Event()

        def drain_probe() -> bool:
            if not added.is_set():
                queue.add_tasks(7)
                added.set()
                return False
            return queue.is_drained()

        result = pool.run_until_drained(drain_probe, timeout_seconds=60)

        assert added.is_set()
        assert result.drained is True
        assert queue.completed == 8
        assert result.workers_spawned >= 2, (
            f"work arriving mid-flight did not scale the pool: only "
            f"{result.workers_spawned} worker(s). Decisions: "
            f"{pool._spawn_decisions}"  # noqa: SLF001
        )


class TestOverProvisioningWasNeverDoubleExecution:
    """The cost was waste and contention, never a duplicated task."""

    def test_the_task_executes_exactly_once(self) -> None:
        """The atomic claim was always the authority, and still is.

        Asserted separately because "the pool opened five threads for one task"
        sounds like a correctness bug and was not one. Recording that distinction
        is what kept the fix proportionate.
        """
        queue = SingleTaskQueue(tasks=1)
        executed: set[int] = set()
        pool = _build_pool(queue, construction_delay=0.30, recheck=0.05,
                           executed_slots=executed)

        result = pool.run_until_drained(queue.is_drained, timeout_seconds=30)

        assert queue.completed == 1
        assert len(executed) == 1, f"more than one slot executed the task: {executed}"
        assert result.cycles_worked == 1


class TestSlotReuseIsADistinctPhenomenon:
    """Told apart from over-provisioning, because they need different fixes.

    The register entry recorded that the observed failure was *not distinguished*
    from slot-id reuse via ``_free_slots``. It is now: ``workers_that_never_worked``
    counts worker *instances* that never claimed, so a recycled slot handed to a
    worker that does claim never registers.
    """

    def test_a_recycled_slot_is_not_counted_as_a_wasted_worker(self) -> None:
        queue = SingleTaskQueue(tasks=4)
        executed: set[int] = set()
        pool = _build_pool(queue, construction_delay=0.0, recheck=0.50,
                           executed_slots=executed, max_workers=2)

        result = pool.run_until_drained(queue.is_drained, timeout_seconds=30)

        assert result.drained is True
        assert queue.completed == 4
        assert result.workers_that_never_worked == 0, (
            "slot reuse must not register as over-provisioning — the metric counts "
            "worker instances that never claimed, not distinct slot ids"
        )
