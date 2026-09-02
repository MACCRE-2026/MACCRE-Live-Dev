# ┌─────────────────────────────────────────────────────────────────────────────┐
# │  MACCREv2 ENGINEERING DOCTRINE                             Law Rev: 19.0   │
# ├─────────────────────────────────────────────────────────────────────────────┤
# │  I.   TYPING      All signatures: explicit Python 3.11+ type hints.        │
# │  II.  LINTING     Zero unused imports. No wildcards. 120-char line max.    │
# │  VI.  ABSTRACTION All I/O behind abc.ABC before any concrete driver.       │
# │  VII. TEARDOWN    try/finally on all handles (omni clean compliance).      │
# │  VIII.TELEMETRY   No bare print(). logger only.                            │
# └─────────────────────────────────────────────────────────────────────────────┘
"""
maccre_core/orchestration/swarm_pool.py
=======================================
Phase 6.12B — :class:`DynamicSwarmPool`, real parallel node execution.

Before this, ``flow_engine`` ran ``while ...: worker.execute_cycle()`` on a single
thread. ``CTRL_SCATTER`` correctly fanned out N tagged rows into ``task_queue``,
but that one loop drained them one at a time — so an 8-agent scatter took eight
sequential LLM round trips. The fan-out was real; the parallelism never was.

Design
------
**Demand-scaled, 0 → N → 0.** The pool holds no idle threads between bursts. A
supervisor loop asks the broker how much work is actually claimable and spawns up
to that many workers, capped by
:data:`~maccre_core.orchestration.concurrency.MAX_SCATTER_AGENTS`. Workers retire
themselves once they stop finding work. A linear step therefore runs on exactly
one thread; a scatter step scales up for the burst and back down after the gather.

**One worker instance per slot, never shared.** Each
:class:`~maccre_core.orchestration.swarm_worker.UniversalSwarmWorker` builds its
own broker, router, memory engine and tool executor. This is a correctness
requirement, not tidiness: ``LocalMessageBroker`` keeps SQLite connections
per-thread so that ``BEGIN EXCLUSIVE`` actually isolates the atomic task claim. A
shared broker was measured handing the *same task to two workers* — 12 tasks
produced 15 claims, and three threads died with "cannot start a transaction within
a transaction".

**Retirement is driven by observed outcome, not a synthetic signal.** A worker
that reports :attr:`~maccre_core.orchestration.swarm_worker.CycleOutcome.IDLE`
often enough exits. The aborted first attempt at this module instead tried to
retire threads by ``.set()``-ing a stop event — on an object whose identity did not
match what the worker closures had captured, so retirement never actually worked,
and the pattern itself violates the observer rule below.

**IDLE and PAUSED are different outcomes and must stay different (defect F2).**
Both mean "this worker did no work", and folding them together cost a runaway.
IDLE means nothing is claimable, so demand is zero and a retired slot stays
retired — retirement is free. PAUSED means work exists and the *operator* is
holding it, so demand stays high and a retired slot is refilled on the next tick,
rebuilding a ``TopologyEngine`` and a ``LocalMessageBroker`` every time. Two
rules keep them apart: the scaler refuses to spawn while paused, and a paused
worker holds its slot for ``pause_hold_seconds`` rather than counting toward idle
retirement. Observed live on run ``job_20260901-205047-40sp``.

State contract
--------------
=================  ==========================  ==============================
Object             Owner                       Mutation rights
=================  ==========================  ==============================
``cancel_event``   TUI / ``execute_flow``      Owner only — pool **reads**
``pause_event``    TUI / ``execute_flow``      Owner only — pool **reads**
``_shutdown``      ``DynamicSwarmPool``        Pool only (it owns this one)
``_active``        ``DynamicSwarmPool``        Pool, under ``_lock``
=================  ==========================  ==============================

The pool never calls ``.set()`` or ``.clear()`` on ``pause_event`` or
``stop_event``. Per ``orchestration_oracle_principles.md``, receiving an Event as
a parameter makes you an observer, and the Phase 6.12 post-mortem traced its
central bug to an observer setting a stop event — which cancelled the whole flow
instead of one step. When the pool needs to signal its *own* threads it uses
``_shutdown``, which it created and therefore owns.
"""
from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Optional, Protocol

from maccre_core.orchestration.concurrency import resolve_scatter_cap
from maccre_core.orchestration.swarm_worker import (
    CycleOutcome,
    NodeLifecycleCallback,
    UniversalSwarmWorker,
)

logger = logging.getLogger("maccre_core.swarm_pool")

__all__ = ["DynamicSwarmPool", "PoolResult", "SwarmWorkerLike"]


class SwarmWorkerLike(Protocol):
    """The only part of a worker the pool depends on.

    Narrow on purpose: tests substitute a stub with no database, no network and no
    LLM, and the pool's scaling logic is exercised without any of that.
    """

    def execute_cycle(
        self,
        pause_event: Optional[Any] = None,
        stop_event: Optional[Any] = None,
    ) -> CycleOutcome:
        """Claim and run at most one node. Returns what it did."""
        ...


@dataclass
class PoolResult:
    """Why :meth:`DynamicSwarmPool.run_until_drained` returned."""

    #: Queue emptied *and* every worker finished its in-flight node.
    drained: bool = False
    #: The caller's ``stop_event`` was set.
    stopped: bool = False
    #: Wall-clock budget exhausted.
    timed_out: bool = False
    #: Worker threads failed more often than the pool's error budget allows.
    aborted: bool = False
    #: Tasks were left ``locked`` with no worker alive to finish them.
    #:
    #: This is the state that previously reported as a clean drain. Nothing is
    #: claimable (so the queue reads empty), nothing is running (so there is
    #: nobody to wait for), yet a row is still held — meaning a node was claimed
    #: and never resolved. Treated as a failure, never as success.
    stalled: bool = False
    #: How many locks were still held when the stall was declared. Recorded for
    #: UT-0, which measures how often workers actually die.
    orphaned_locks: int = 0

    #: The flow was held, and whatever is supposed to release it demonstrably
    #: cannot any more (defect F3).
    #:
    #: ``pause_event`` is owned by the TUI; this pool and the flow engine only
    #: observe it. When the Textual app dies with the event clear — which is
    #: exactly what defect F1 caused — nothing will ever set it again, and every
    #: layer below waits for a resume that cannot arrive. Reported separately from
    #: ``timed_out`` because the responses differ: a timeout may only need a
    #: larger budget, while this needs the operator told that their UI died under
    #: a running flow.
    pause_abandoned: bool = False
    #: Highest number of workers simultaneously executing nodes. The headline
    #: Phase 6.12 metric — with the old single-threaded loop this could only ever
    #: be 1, whatever the scatter width.
    peak_concurrency: int = 0
    #: Total cycles that actually executed a node.
    cycles_worked: int = 0
    #: Threads spawned over the whole run (not the same as peak concurrency).
    workers_spawned: int = 0
    #: Unhandled worker exceptions, formatted.
    errors: list[str] = field(default_factory=list)

    @property
    def succeeded(self) -> bool:
        """True only for a clean drain."""
        return self.drained and not (
            self.stopped or self.timed_out or self.aborted or self.stalled
        )


class DynamicSwarmPool:
    """Runs swarm workers as threads, sized to the work actually available.

    Typical use from the flow engine::

        pool = DynamicSwarmPool(
            job_id=job_id,
            demand_estimator=lambda cap: broker.count_ready_tasks(job_id, topo, cap),
        )
        result = pool.run_until_drained(
            is_drained=lambda: open_task_count(job_id) == 0,
            pause_event=pause_event,
            stop_event=cancel_event,
        )

    The pool is single-use per call to :meth:`run_until_drained`, but the same
    instance may be reused for successive calls (the flow engine does this once
    per step).
    """

    def __init__(
        self,
        job_id: str,
        max_workers: int | None = None,
        demand_estimator: Callable[[int], int] | None = None,
        worker_factory: Callable[[int], SwarmWorkerLike] | None = None,
        on_node_start: NodeLifecycleCallback | None = None,
        on_node_finish: NodeLifecycleCallback | None = None,
        topology_overlays: dict[str, dict[str, Any]] | None = None,
        idle_sleep_seconds: float = 0.25,
        poll_interval_seconds: float = 0.05,
        demand_recheck_seconds: float = 0.25,
        idle_retire_after: int = 2,
        max_worker_errors: int | None = None,
        paused_poll_interval_seconds: float = 0.25,
        pause_hold_seconds: float = 5.0,
    ) -> None:
        """
        Args:
            job_id: Job being executed. Used for logging and passed to the
                demand estimator by the caller's closure.
            max_workers: Concurrency ceiling. Clamped through
                :func:`resolve_scatter_cap`, so it can never exceed
                ``SCATTER_HARD_CAP`` however it is configured.
            demand_estimator: ``(cap) -> ready_count``. Advisory only — a
                read-only sizing hint. Over-counting costs a thread that finds
                nothing and retires; the atomic claim in the broker remains the
                sole authority on who owns a task. ``None`` means "assume 1",
                which reproduces the previous single-threaded behaviour rather
                than guessing high.
            worker_factory: ``(slot) -> worker``. Defaults to constructing a real
                :class:`UniversalSwarmWorker` per slot. Injectable so tests can
                run the scaling logic without a database or an LLM.
            on_node_start: Fired when a node begins, with
                ``(step_index, node_id, slot)``.
            on_node_finish: Fired when a node ends, on every path including
                failure.
            topology_overlays: ``{node_id: config}`` applied to **every** worker's
                topology engine as it is built. Required because each worker owns
                its own ``TopologyEngine`` with its own cache: a ``FlowStep.config``
                overlay applied to one engine is invisible to the others, so
                without this a scatter lane's node config would reach at most one
                of N workers.
            idle_sleep_seconds: Passed to each worker. Deliberately far below the
                worker's own 3 s default: at 3 s a retiring thread would hold its
                slot for three seconds after the queue drained, and a thread
                spawned for a burst would take three seconds to notice work.
            poll_interval_seconds: Supervisor poll cadence, governing how quickly
                a stop or a drain is noticed.
            demand_recheck_seconds: Minimum gap between demand estimates.
                Deliberately decoupled from *poll_interval_seconds*: the estimator
                is a database query — ``count_ready_tasks`` scans open rows and
                runs a Gather Gate lookup per row — and those reads contend with
                the ``BEGIN EXCLUSIVE`` transaction workers use to claim. Sizing
                on every poll tick made claims queue behind the sizing queries; an
                8-lane scatter measured 4.25 s of wall clock for 2.0 s of work,
                i.e. slower than running it sequentially. Polling stays fast so
                cancellation stays responsive; sizing is throttled.
            idle_retire_after: Consecutive **idle** cycles before a worker exits.
                Idle means the queue had nothing claimable, so demand is zero and
                the supervisor will not immediately re-spawn — which is what makes
                retiring eagerly cheap. Deliberately **not** applied to a paused
                cycle, where demand stays high and eager retirement produced a
                construction storm; see *pause_hold_seconds*.
            max_worker_errors: Abort the run after this many unhandled worker
                exceptions. Defaults to ``3 * max_workers``. Prevents an
                immediately-crashing worker from being respawned forever.
            paused_poll_interval_seconds: Supervisor cadence while the flow is
                held. The normal 0.05 s tick runs the drain check — a SQLite
                ``COUNT`` — twenty times a second, which is the right price for
                noticing a drain promptly and the wrong price for watching a
                pause that may last minutes. Still fast enough that a cancel
                issued while paused is noticed within a quarter second.
            pause_hold_seconds: How long a worker keeps its slot while the flow is
                held before retiring. A brief pause should not tear the pool down
                and pay full ramp-up again on resume; a long one should not keep
                threads parked forever. Retiring after this is safe precisely
                because the scaler refuses to spawn while paused, so a retired
                slot stays retired until the operator resumes.
        """
        self.job_id = job_id
        self.max_workers = resolve_scatter_cap(max_workers)
        self.demand_estimator = demand_estimator
        self.worker_factory = worker_factory or self._default_worker_factory
        self.on_node_start = on_node_start
        self.on_node_finish = on_node_finish
        self.topology_overlays = dict(topology_overlays or {})
        self.idle_sleep_seconds = idle_sleep_seconds
        self.poll_interval_seconds = poll_interval_seconds
        self.demand_recheck_seconds = max(0.0, demand_recheck_seconds)
        self.idle_retire_after = max(1, idle_retire_after)
        self.max_worker_errors = (
            max_worker_errors if max_worker_errors is not None else 3 * self.max_workers
        )
        self.paused_poll_interval_seconds = max(
            poll_interval_seconds, paused_poll_interval_seconds
        )
        self.pause_hold_seconds = max(0.0, pause_hold_seconds)

        #: Pool-owned. The pool created it, so the pool may set it — unlike the
        #: caller's pause/stop events, which it only reads.
        self._shutdown = threading.Event()
        self._lock = threading.Lock()
        self._active: set[int] = set()
        self._threads: list[threading.Thread] = []
        self._free_slots: list[int] = []
        self._peak_concurrency = 0
        self._cycles_worked = 0
        self._workers_spawned = 0
        self._errors: list[str] = []
        self._last_demand: int | None = None
        self._last_demand_at: float = 0.0
        self._demand_calls = 0

    # ── Introspection ─────────────────────────────────────────────────────────

    @staticmethod
    def _is_paused(pause_event: Optional[Any]) -> bool:
        """Whether the operator currently has the flow held.

        One reading of the pause state, used by the supervisor, the scaler and the
        poll backoff alike. The convention is the TUI's and it is inverted from
        what the name suggests: **set means running**, clear means held. An absent
        event means nothing can pause us, so we are never paused.

        Read-only by contract. ``pause_event`` is owned by the TUI; this pool is an
        observer and must never ``set()`` or ``clear()`` it.
        """
        return pause_event is not None and not pause_event.is_set()

    def active_worker_count(self) -> int:
        """Workers currently alive and cycling."""
        with self._lock:
            return len(self._active)

    @property
    def peak_concurrency(self) -> int:
        """Highest simultaneous worker count observed so far."""
        with self._lock:
            return self._peak_concurrency

    # ── Worker construction ───────────────────────────────────────────────────

    def _default_worker_factory(self, slot: int) -> SwarmWorkerLike:
        """Build one real worker for *slot*.

        A fresh instance per slot, never a shared one: the worker's broker holds
        per-thread SQLite connections, and its router and tool executor carry
        per-call mutable state.
        """
        worker = UniversalSwarmWorker(
            slot=slot,
            on_node_start=self.on_node_start,
            on_node_finish=self.on_node_finish,
            idle_sleep_seconds=self.idle_sleep_seconds,
        )
        # Each worker owns its own TopologyEngine, so step config has to be
        # applied per worker. Flushing first makes the worker pick up the
        # topology.csv this step just wrote rather than a stale cached graph.
        topology = getattr(worker, "topology", None)
        if topology is not None:
            try:
                topology.flush_cache()
                for node_id, overlay in self.topology_overlays.items():
                    topology.merge_config_overlay(node_id, overlay)
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "[SWARM_POOL] Could not apply topology overlays to slot %d: %s",
                    slot, exc,
                )
        return worker

    # ── Worker thread body ────────────────────────────────────────────────────

    def _worker_loop(
        self,
        slot: int,
        pause_event: Optional[Any],
        stop_event: Optional[Any],
    ) -> None:
        """Build this slot's worker, then cycle until stopped or out of work.

        **Construction happens here, on the worker's own thread**, not on the
        supervisor thread that spawned it. A real worker builds a
        ``TopologyEngine`` and a ``LocalMessageBroker``, and the broker runs
        schema DDL against SQLite — which contends with the ``BEGIN EXCLUSIVE``
        claims already-running workers are issuing. Constructing serially on the
        supervisor thread therefore put per-worker I/O directly on the ramp-up
        critical path: measured on an 8-lane scatter, the pool could only get 6
        workers into their nodes before the first one finished. Building in
        parallel removes that from the critical path.
        """
        idle_streak = 0
        #: When this worker first observed the flow held, or None if running.
        paused_since: float | None = None
        try:
            try:
                worker = self.worker_factory(slot)
            except Exception as exc:  # noqa: BLE001
                with self._lock:
                    self._errors.append(f"slot {slot}: factory failed: {exc}")
                logger.exception(
                    "[SWARM_POOL] Could not construct worker for slot %d (job=%s).",
                    slot, self.job_id,
                )
                return

            while True:
                # Read-only checks. Never .set()/.clear() either caller event.
                if stop_event is not None and stop_event.is_set():
                    return
                if self._shutdown.is_set():
                    return

                outcome = worker.execute_cycle(
                    pause_event=pause_event, stop_event=stop_event
                )

                if outcome is CycleOutcome.STOPPED:
                    return
                if outcome is CycleOutcome.WORKED:
                    idle_streak = 0
                    paused_since = None
                    with self._lock:
                        self._cycles_worked += 1
                    continue

                # ── PAUSED is not IDLE (defect F2) ────────────────────────────
                # These were one branch, retiring on either. That reasoning holds
                # for IDLE and inverts for PAUSED, because the two say opposite
                # things about demand:
                #
                #   IDLE   — nothing is claimable. Demand is zero, so the
                #            supervisor will not re-spawn. Retiring is free.
                #   PAUSED — work exists and is being held. Demand stays high, so
                #            the supervisor re-spawns instantly. Retiring is a
                #            full worker rebuild, over and over.
                #
                # The scaler now refuses to spawn while paused, which is what
                # actually stops the storm. This branch handles the other half: do
                # not churn a worker that is merely waiting for the operator, and
                # do not park it forever either.
                if outcome is CycleOutcome.PAUSED:
                    now = time.monotonic()
                    if paused_since is None:
                        paused_since = now
                    elif now - paused_since >= self.pause_hold_seconds:
                        logger.debug(
                            "[SWARM_POOL] Worker slot %d retiring after %.1fs held "
                            "(job=%s). The scaler will not replace it until the "
                            "flow resumes.",
                            slot, now - paused_since, self.job_id,
                        )
                        return
                    # The worker's own execute_cycle already slept on the pause
                    # poll, so this loop is not hot.
                    continue

                # IDLE — nothing claimable. Retire; the supervisor re-spawns when
                # demand returns.
                paused_since = None
                idle_streak += 1
                if idle_streak >= self.idle_retire_after:
                    return
        except Exception as exc:  # noqa: BLE001
            # One worker dying must not take the pool with it. The supervisor's
            # error budget decides whether the run as a whole is doomed.
            with self._lock:
                self._errors.append(f"slot {slot}: {type(exc).__name__}: {exc}")
            logger.exception("[SWARM_POOL] Worker slot %d failed for job=%s.", slot, self.job_id)
        finally:
            with self._lock:
                self._active.discard(slot)
                self._free_slots.append(slot)
            logger.debug(
                "[SWARM_POOL] Worker slot %d retired (job=%s, active=%d).",
                slot, self.job_id, self.active_worker_count(),
            )

    # ── Scaling ───────────────────────────────────────────────────────────────

    def _estimate_demand(self) -> int | None:
        """How many *claimable* tasks are waiting right now.

        Advisory. A stale or wrong answer costs at most a thread that finds no
        work and retires — never a duplicated task, because the claim itself is
        atomic.

        Returns:
            A ready-task count, or ``None`` for "no information available".
            ``None`` is distinct from ``0``: zero means the queue is genuinely
            empty, while ``None`` means the pool cannot size itself and should
            fall back to single-threaded behaviour rather than guess.
        """
        if self.demand_estimator is None:
            return None
        try:
            return max(0, int(self.demand_estimator(self.max_workers)))
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "[SWARM_POOL] Demand estimator failed for job=%s (%s); "
                "falling back to single-threaded.",
                self.job_id, exc,
            )
            return None

    def _cached_demand(self) -> tuple[int | None, bool]:
        """Demand, re-estimated at most every ``demand_recheck_seconds``.

        The supervisor polls far faster than it needs to size, because polling
        also governs how quickly a stop or a drain is noticed. Estimating on every
        tick turned the sizing query into the bottleneck it was meant to inform —
        see ``demand_recheck_seconds``.

        Skipping the throttle while no worker is alive keeps start-up immediate:
        the first tick of a step must size straight away rather than idle for a
        quarter second.

        Returns:
            ``(ready, is_fresh)``. ``is_fresh`` is False when the cached value was
            reused, and callers **must not** scale on a stale value — see
            :meth:`_scale_to_demand`.
        """
        now = time.monotonic()
        fresh_enough = (now - self._last_demand_at) < self.demand_recheck_seconds
        if fresh_enough and self.active_worker_count() > 0:
            return self._last_demand, False
        self._last_demand = self._estimate_demand()
        self._last_demand_at = now
        self._demand_calls += 1
        return self._last_demand, True

    def _spawn(
        self,
        pause_event: Optional[Any],
        stop_event: Optional[Any],
    ) -> bool:
        """Start one worker thread. Returns False if a slot could not be taken."""
        with self._lock:
            if len(self._active) >= self.max_workers:
                return False
            if self._free_slots:
                slot = self._free_slots.pop(0)
            else:
                slot = len(self._active)
                # Guard against slot collision if bookkeeping ever drifts.
                while slot in self._active:
                    slot += 1
                if slot >= self.max_workers:
                    return False
            self._active.add(slot)
            self._peak_concurrency = max(self._peak_concurrency, len(self._active))
            self._workers_spawned += 1

        # The worker itself is built on its own thread — see _worker_loop. That
        # keeps the supervisor free of per-worker SQLite setup, which otherwise
        # serialises ramp-up. A construction failure surfaces as a worker error
        # and goes through the same budget as any other worker fault.
        thread = threading.Thread(
            target=self._worker_loop,
            args=(slot, pause_event, stop_event),
            name=f"swarm-{self.job_id}-t{slot}",
            daemon=True,
        )
        with self._lock:
            self._threads.append(thread)
        thread.start()
        logger.debug(
            "[SWARM_POOL] Spawned worker slot=%d for job=%s (active=%d/%d).",
            slot, self.job_id, self.active_worker_count(), self.max_workers,
        )
        return True

    def _scale_to_demand(
        self,
        pause_event: Optional[Any],
        stop_event: Optional[Any],
    ) -> None:
        """Top the pool up towards current demand.

        Scale *up* only. Scale-down is the workers' own decision, taken when they
        observe an idle cycle — the supervisor cannot know whether a worker is
        mid-LLM-call and must not try to pre-empt one.

        The target is ``active + ready``, **not** ``ready``. The demand estimator
        counts *open* tasks, and a task being executed right now is ``locked``
        rather than open — so a worker already busy on lane 1 is not spare
        capacity for the remaining lanes. Treating ``ready`` as the target
        directly leaves the pool one thread short of the scatter width: an 8-lane
        scatter settled at 7 and a 4-lane scatter at 3. Measured while building
        the Task B3 concurrency proof.

        ``max_workers`` still does the containment, so a long queue cannot inflate
        the pool past its ceiling.

        When the estimator reports ``None`` — absent, or raising — the pool holds
        at exactly one worker instead of guessing. Adding to ``active`` in that
        case would ramp to the ceiling one thread per poll and open the full set
        of API connections for what may be a linear flow.
        """
        # ── Never staff a pool the operator is holding (defect F2) ────────────
        # This is the storm-stopper, and it is the supervisor's job rather than the
        # worker's. A paused worker reports PAUSED and retires; demand, meanwhile,
        # is measured from *open* rows, and a paused task is still open. So the
        # estimate stayed high, this method spawned a replacement, that replacement
        # reported PAUSED and retired, and the cycle repeated — at a
        # ``poll_interval_seconds`` of 0.05 that is twenty full worker
        # constructions a second, each building a TopologyEngine and a
        # LocalMessageBroker that runs schema DDL against the very SQLite file a
        # claim needs. Observed live on run job_20260901-205047-40sp: the operator
        # pressed pause with one node still open and the pool rebuilt workers until
        # the process was killed.
        #
        # Demand is not the question while paused. The answer is "none, by
        # instruction", so return before paying for the estimate.
        if self._is_paused(pause_event):
            return

        # Already at the ceiling: nothing an estimate could tell us, so do not
        # pay for the query.
        if self.active_worker_count() >= self.max_workers:
            return

        ready, is_fresh = self._cached_demand()
        if ready is None:
            target = 1
        elif not is_fresh:
            # Never scale on a stale estimate. ``ready`` counts *unclaimed* tasks,
            # so pairing a cached count with a live ``active`` count double-counts:
            # a worker spawned moments ago has not claimed yet, the cached count
            # still includes the task it is about to take, and the pool spawns a
            # second worker for work already spoken for. Measured on a linear
            # 3-step flow, which opened two threads for one task at a time.
            return
        else:
            # At least one worker while work remains, or a queue whose head is
            # briefly gated would stall with nobody polling it.
            target = min(self.max_workers, max(1, self.active_worker_count() + ready))
        while self.active_worker_count() < target:
            if not self._spawn(pause_event, stop_event):
                break

    # ── Supervisor ────────────────────────────────────────────────────────────

    def run_until_drained(
        self,
        is_drained: Callable[[], bool],
        pause_event: Optional[Any] = None,
        stop_event: Optional[Any] = None,
        timeout_seconds: float = 3600.0,
        locked_probe: Optional[Callable[[], int]] = None,
        stall_grace_seconds: float = 30.0,
        pause_owner_alive: Optional[Callable[[], bool]] = None,
        max_pause_seconds: Optional[float] = None,
    ) -> PoolResult:
        """Run workers until the queue drains, or stop/timeout intervenes.

        Runs the supervisor on the **calling** thread, so the flow engine keeps
        its existing single-threaded control flow and only the node execution
        fans out.

        The orphaned-lock hole
        ----------------------
        ``is_drained`` asks "is anything claimable", which in practice means
        ``open task count == 0``. A task a worker has claimed is ``locked``, not
        ``open``, so it does not count — the queue can read as empty while a node
        is mid-flight. The pool therefore also waits for ``active_worker_count()``
        to reach zero before declaring a drain.

        Those two conditions together are still not sufficient. If a worker
        claimed a task and then died without resolving it, the row stays
        ``locked`` forever: nothing is claimable, nothing is running, and the pool
        used to call that a clean drain. The flow then reported success for a node
        that never executed.

        Passing *locked_probe* closes that hole. When the queue looks drained and
        no worker is alive, but locks are still held, the pool refuses to declare
        a drain and — once the condition outlives *stall_grace_seconds* — returns
        with :attr:`PoolResult.stalled` set.

        Deliberately **not** self-healing: the pool does not reclaim the lock and
        retry. A stall is surfaced loudly so it can be measured (UT-0 exists to
        find out how often workers really die) before any automatic recovery is
        wired in. Silent retry is how a double-executed node hides.

        Args:
            is_drained: ``() -> bool``, true when no claimable work remains.
            pause_event: Observed, never mutated. A clear event holds workers.
            stop_event: Observed, never mutated. A set event ends the run.
            timeout_seconds: Wall-clock budget for the whole call.
            locked_probe: ``() -> int``, count of rows still held ``locked`` for
                this job. Omitting it restores the old behaviour of treating an
                empty-and-idle queue as drained, which cannot detect an orphan.
                Callers that can count locks should always pass it.
            stall_grace_seconds: How long the orphan condition must persist before
                it is called a stall. A grace period is required, not merely
                prudent: ``fetch_and_lock_task`` commits its claim before the
                worker is counted as active, so "locked but nobody active" is a
                legitimate transient every single time a task is picked up.
            pause_owner_alive: ``() -> bool``, asked **only while the flow is
                held**: can whatever owns ``pause_event`` still release it? The
                pool does not guess at this — it cannot, since it is only an
                observer of an event someone else owns — so the caller supplies
                the answer. ``None`` means "unknowable", which preserves the
                previous behaviour of waiting indefinitely.
            max_pause_seconds: Hard ceiling on a continuous hold, as a backstop for
                when *pause_owner_alive* is unavailable. ``None`` by default and
                deliberately so: a deliberate long pause with a healthy UI is a
                legitimate thing to do, and killing a flow because the operator
                went to lunch would be worse than the defect this guards against.
                Prefer *pause_owner_alive*, which distinguishes the two.

        Returns:
            A :class:`PoolResult`.
        """
        self._shutdown.clear()
        with self._lock:
            self._threads.clear()
            self._free_slots.clear()
            self._peak_concurrency = 0
            self._cycles_worked = 0
            self._workers_spawned = 0
            self._errors.clear()
            self._last_demand = None
            self._last_demand_at = 0.0
            self._demand_calls = 0

        result = PoolResult()
        started_at = time.monotonic()
        #: When the "locks held, nobody active" condition was first seen, or None.
        orphan_since: float | None = None
        #: When the flow was first observed held, or None while it is running.
        held_since: float | None = None

        try:
            while True:
                if stop_event is not None and stop_event.is_set():
                    logger.info("[SWARM_POOL] Stop requested — halting job=%s.", self.job_id)
                    result.stopped = True
                    break

                if time.monotonic() - started_at > timeout_seconds:
                    logger.warning("[SWARM_POOL] Timeout reached for job=%s.", self.job_id)
                    result.timed_out = True
                    break

                with self._lock:
                    error_count = len(self._errors)
                if error_count > self.max_worker_errors:
                    logger.error(
                        "[SWARM_POOL] Error budget exhausted for job=%s (%d failures).",
                        self.job_id, error_count,
                    )
                    result.aborted = True
                    break

                try:
                    drained = bool(is_drained())
                except Exception as exc:  # noqa: BLE001
                    # Treat an unreadable queue as "not drained" and keep going;
                    # the timeout is the backstop.
                    logger.warning(
                        "[SWARM_POOL] Drain check failed for job=%s (%s).", self.job_id, exc
                    )
                    drained = False

                if drained:
                    # Only a real drain once nothing is mid-node. A locked task is
                    # not 'open', so the queue can read as empty while a node is
                    # still running.
                    if self.active_worker_count() == 0:
                        held = self._count_held_locks(locked_probe)
                        if held <= 0:
                            result.drained = True
                            break

                        # Nothing claimable, nothing running, yet locks are held.
                        # Either a claim that has not yet been counted as active
                        # (normal, resolves in milliseconds) or a worker that died
                        # holding the row (a stall). Time distinguishes them.
                        if orphan_since is None:
                            orphan_since = time.monotonic()
                            logger.debug(
                                "[SWARM_POOL] job=%s: %d lock(s) held with no active "
                                "worker; watching for %.0fs.",
                                self.job_id, held, stall_grace_seconds,
                            )
                        elif time.monotonic() - orphan_since > stall_grace_seconds:
                            logger.critical(
                                "[SWARM_POOL] job=%s STALLED: %d task(s) locked with "
                                "no worker alive for >%.0fs. A worker died without "
                                "resolving its task; these nodes did NOT run.",
                                self.job_id, held, stall_grace_seconds,
                            )
                            result.stalled = True
                            result.orphaned_locks = held
                            break
                    else:
                        # A worker is running again, so any earlier orphan reading
                        # was the expected claim transient. Start over.
                        orphan_since = None
                else:
                    orphan_since = None

                    # ── Is this hold still releasable? (defect F3) ─────────────
                    if self._is_paused(pause_event):
                        if held_since is None:
                            held_since = time.monotonic()
                        if pause_owner_alive is not None and not pause_owner_alive():
                            logger.critical(
                                "[SWARM_POOL] job=%s ABANDONED: the flow is held and "
                                "whatever owns the pause can no longer release it. "
                                "Held for %.0fs. Work remains and it will NOT be "
                                "reported as finished.",
                                self.job_id, time.monotonic() - held_since,
                            )
                            result.pause_abandoned = True
                            break
                        if (
                            max_pause_seconds is not None
                            and time.monotonic() - held_since > max_pause_seconds
                        ):
                            logger.critical(
                                "[SWARM_POOL] job=%s ABANDONED: held for %.0fs, past "
                                "the %.0fs ceiling, with nobody resuming it.",
                                self.job_id, time.monotonic() - held_since,
                                max_pause_seconds,
                            )
                            result.pause_abandoned = True
                            break
                    else:
                        held_since = None

                    self._scale_to_demand(pause_event, stop_event)

                # Back off while held. The fast tick exists so a drain or a cancel
                # is noticed promptly; neither can happen while the operator has
                # the flow paused, and the drain check is a SQLite COUNT that
                # contends with the claims workers issue. A quarter second still
                # notices a cancel immediately by human standards.
                time.sleep(
                    self.paused_poll_interval_seconds
                    if self._is_paused(pause_event)
                    else self.poll_interval_seconds
                )
        finally:
            # Retire every worker before returning, so the caller never observes
            # a node still writing artifacts after run_until_drained() returns.
            self._shutdown.set()
            self._join_all()

        with self._lock:
            result.peak_concurrency = self._peak_concurrency
            result.cycles_worked = self._cycles_worked
            result.workers_spawned = self._workers_spawned
            result.errors = list(self._errors)

        logger.info(
            "[SWARM_POOL] job=%s finished: drained=%s stopped=%s timed_out=%s "
            "stalled=%s pause_abandoned=%s peak_concurrency=%d cycles=%d "
            "spawned=%d errors=%d",
            self.job_id, result.drained, result.stopped, result.timed_out,
            result.stalled, result.pause_abandoned, result.peak_concurrency,
            result.cycles_worked, result.workers_spawned, len(result.errors),
        )
        return result

    def _count_held_locks(self, locked_probe: Optional[Callable[[], int]]) -> int:
        """Held-lock count, or 0 when unavailable.

        An unreadable probe must not manufacture a stall — a transient SQLite
        error would otherwise fail a healthy flow. Returning 0 keeps the old
        behaviour for that tick; the next poll tries again.
        """
        if locked_probe is None:
            return 0
        try:
            return int(locked_probe())
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "[SWARM_POOL] Locked-task probe failed for job=%s (%s).",
                self.job_id, exc,
            )
            return 0

    def _join_all(self, timeout_seconds: float = 30.0) -> None:
        """Wait for every worker thread to exit.

        Workers are daemon threads, so a hung one cannot block interpreter exit —
        but it is still reported, because a thread that outlives its pool is
        writing artifacts nobody is waiting for.
        """
        with self._lock:
            threads = list(self._threads)
        deadline = time.monotonic() + timeout_seconds
        for thread in threads:
            remaining = max(0.0, deadline - time.monotonic())
            thread.join(timeout=remaining)
            if thread.is_alive():
                logger.warning(
                    "[SWARM_POOL] Worker thread %s did not exit within the join budget.",
                    thread.name,
                )
