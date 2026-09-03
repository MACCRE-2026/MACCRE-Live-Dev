# ┌─────────────────────────────────────────────────────────────────────────────┐
# │  MACCREv2 Test Suite — Phase 6.12 Task A5: Observable Cycle Outcome          │
# └─────────────────────────────────────────────────────────────────────────────┘
"""
tests/test_cycle_outcome.py
===========================
Phase 6.12 Task A5 — ``execute_cycle`` must report *what it did*, not just
"didn't stop".

The baseline returned a bare ``bool`` in which "claimed a task and ran a node"
and "found nothing to do" were both ``True``. A demand-scaled pool cannot decide
whether to retire a thread without telling those apart, so the return type is now
:class:`CycleOutcome`.

Also covered: the worker is an **observer** of ``pause_event`` and ``stop_event``.
Per ``orchestration_oracle_principles.md`` it may only read them. The original
Phase 6.12 post-mortem traced its central bug to an observer calling ``.set()`` on
an event it had merely received, which cancelled the entire flow instead of one
step.

Workers here are built with ``__new__`` rather than ``__init__``: the real
constructor builds a router, a broker, a memory engine and a tool executor, which
means databases and credential lookups. The early-exit paths under test touch only
a handful of attributes, all set explicitly below.
"""
from __future__ import annotations

import threading
from typing import Any

import pytest

from maccre_core.orchestration.swarm_worker import (
    CycleOutcome,
    UniversalSwarmWorker,
    parse_step_index,
    resolve_worker_id,
)


class StubBroker:
    """Minimal broker: hands out a fixed script of claim results."""

    def __init__(self, tasks: list[dict[str, Any] | None] | None = None) -> None:
        self.tasks = list(tasks or [])
        self.claim_calls: list[str] = []

    def fetch_and_lock_task(self, agent_id: str, topology_engine: Any) -> Any:
        self.claim_calls.append(agent_id)
        if self.tasks:
            return self.tasks.pop(0)
        return None


def make_worker(
    tasks: list[dict[str, Any] | None] | None = None,
    slot: int | None = None,
    on_node_start: Any = None,
    on_node_finish: Any = None,
) -> UniversalSwarmWorker:
    """A worker with no constructor side effects, wired for early-exit paths."""
    worker = UniversalSwarmWorker.__new__(UniversalSwarmWorker)
    worker.slot = slot
    worker.worker_id = resolve_worker_id(slot)
    worker.broker = StubBroker(tasks)  # type: ignore[assignment]
    worker.topology = None
    worker.on_node_start = on_node_start
    worker.on_node_finish = on_node_finish
    # Zero sleeps so the tests do not pay the production idle delay.
    worker.idle_sleep_seconds = 0.0
    worker.pause_poll_seconds = 0.0
    worker._is_sleeping = False
    return worker


# ── The outcome type ──────────────────────────────────────────────────────────


class TestCycleOutcome:
    def test_all_four_states_exist(self) -> None:
        assert {o.name for o in CycleOutcome} == {"WORKED", "IDLE", "PAUSED", "STOPPED"}

    def test_only_stopped_is_falsy(self) -> None:
        """Preserves the old bool contract for ``if not execute_cycle(): break``."""
        assert bool(CycleOutcome.WORKED) is True
        assert bool(CycleOutcome.IDLE) is True
        assert bool(CycleOutcome.PAUSED) is True
        assert bool(CycleOutcome.STOPPED) is False

    def test_did_work_is_true_only_for_worked(self) -> None:
        """The distinction the baseline bool could not express."""
        assert CycleOutcome.WORKED.did_work is True
        assert CycleOutcome.IDLE.did_work is False
        assert CycleOutcome.PAUSED.did_work is False
        assert CycleOutcome.STOPPED.did_work is False

    def test_worked_and_idle_are_both_truthy_but_distinguishable(self) -> None:
        """Exactly the pool's retirement decision.

        Truthiness alone cannot drive scale-down, which is why the bare bool was
        insufficient.
        """
        assert bool(CycleOutcome.WORKED) == bool(CycleOutcome.IDLE)
        assert CycleOutcome.WORKED.did_work != CycleOutcome.IDLE.did_work


# ── Step index recovery ───────────────────────────────────────────────────────


class TestParseStepIndex:
    def test_parses_the_hydrated_suffix(self) -> None:
        assert parse_step_index("CTRL_PAUSE_MANUAL_S1") == 1
        assert parse_step_index("AGENT_OSINT_Analyst_1613_S0") == 0
        assert parse_step_index("AGENT_OSINT_Analyst_1613_S2") == 2

    def test_handles_multi_digit_steps(self) -> None:
        assert parse_step_index("NODE_S10") == 10
        assert parse_step_index("NODE_S123") == 123

    def test_returns_none_without_a_suffix(self) -> None:
        assert parse_step_index("CTRL_MERGE") is None
        assert parse_step_index("END") is None
        assert parse_step_index("") is None

    def test_only_matches_a_trailing_suffix(self) -> None:
        """``_S3`` in the middle of a name is part of the name, not a step."""
        assert parse_step_index("AGENT_S3_REPORT") is None

    def test_tolerates_surrounding_whitespace(self) -> None:
        assert parse_step_index("  NODE_S4  ") == 4


# ── Early-exit outcomes ───────────────────────────────────────────────────────


class TestEarlyExitOutcomes:
    def test_set_stop_event_yields_stopped(self) -> None:
        stop = threading.Event()
        stop.set()
        worker = make_worker()
        assert worker.execute_cycle(stop_event=stop) is CycleOutcome.STOPPED

    def test_stopped_short_circuits_before_claiming(self) -> None:
        """Cancellation must not consume a task on its way out."""
        stop = threading.Event()
        stop.set()
        worker = make_worker(tasks=[{"id": 1}])
        worker.execute_cycle(stop_event=stop)
        assert worker.broker.claim_calls == []  # type: ignore[attr-defined]

    def test_clear_pause_event_yields_paused(self) -> None:
        pause = threading.Event()  # clear == held at the gate
        worker = make_worker()
        assert worker.execute_cycle(pause_event=pause) is CycleOutcome.PAUSED

    def test_paused_does_not_claim(self) -> None:
        pause = threading.Event()
        worker = make_worker(tasks=[{"id": 1}])
        worker.execute_cycle(pause_event=pause)
        assert worker.broker.claim_calls == []  # type: ignore[attr-defined]

    def test_set_pause_event_allows_claiming(self) -> None:
        """A *set* pause event means "running", matching baseline semantics."""
        pause = threading.Event()
        pause.set()
        worker = make_worker()
        assert worker.execute_cycle(pause_event=pause) is CycleOutcome.IDLE
        assert worker.broker.claim_calls == [worker.worker_id]  # type: ignore[attr-defined]

    def test_empty_queue_yields_idle(self) -> None:
        worker = make_worker()
        assert worker.execute_cycle() is CycleOutcome.IDLE

    def test_idle_is_truthy_so_legacy_loops_keep_running(self) -> None:
        worker = make_worker()
        assert bool(worker.execute_cycle()) is True

    def test_claim_uses_the_slot_identity(self) -> None:
        worker = make_worker(slot=5)
        worker.execute_cycle()
        assert worker.broker.claim_calls == [resolve_worker_id(5)]  # type: ignore[attr-defined]

    def test_stop_takes_precedence_over_pause(self) -> None:
        stop = threading.Event()
        stop.set()
        pause = threading.Event()  # also gating
        worker = make_worker()
        assert (
            worker.execute_cycle(pause_event=pause, stop_event=stop)
            is CycleOutcome.STOPPED
        )


# ── Sleep parameterisation ────────────────────────────────────────────────────


class TestSleepParameterisation:
    def test_idle_sleep_is_configurable(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Was hardcoded to ``time.sleep(3)``.

        At 3 s a retiring pool thread would hold its slot for up to three seconds
        after the queue drained, and a thread spawned for a burst would take up to
        three seconds to notice work.
        """
        slept: list[float] = []
        monkeypatch.setattr(
            "maccre_core.orchestration.swarm_worker.time.sleep", slept.append
        )
        worker = make_worker()
        worker.idle_sleep_seconds = 0.25
        worker.execute_cycle()
        assert slept == [0.25]

    def test_pause_poll_is_configurable(self, monkeypatch: pytest.MonkeyPatch) -> None:
        slept: list[float] = []
        monkeypatch.setattr(
            "maccre_core.orchestration.swarm_worker.time.sleep", slept.append
        )
        worker = make_worker()
        worker.pause_poll_seconds = 0.05
        worker.execute_cycle(pause_event=threading.Event())
        assert slept == [0.05]

    def test_constructor_defaults_match_baseline_timings(self) -> None:
        import inspect

        params = inspect.signature(UniversalSwarmWorker.__init__).parameters
        assert params["idle_sleep_seconds"].default == 3.0
        assert params["pause_poll_seconds"].default == 1.0


# ── Observer discipline (doctrine) ────────────────────────────────────────────


class TestEventObserverDiscipline:
    """The worker receives events as parameters, so it may only read them.

    This is the rule the original Phase 6.12 post-mortem identified as the root
    cause of its central bug.
    """

    def _tripwire_event(self) -> Any:
        class TripwireEvent(threading.Event):
            def __init__(self) -> None:
                super().__init__()
                self.mutations: list[str] = []

            def set(self) -> None:
                self.mutations.append("set")
                super().set()

            def clear(self) -> None:
                self.mutations.append("clear")
                super().clear()

        return TripwireEvent()

    def test_worker_never_mutates_stop_event(self) -> None:
        stop = self._tripwire_event()
        stop.set()
        stop.mutations.clear()
        worker = make_worker()
        worker.execute_cycle(stop_event=stop)
        assert stop.mutations == []

    def test_worker_never_mutates_pause_event_when_gating(self) -> None:
        pause = self._tripwire_event()
        worker = make_worker()
        worker.execute_cycle(pause_event=pause)
        assert pause.mutations == []

    def test_worker_never_mutates_pause_event_when_running(self) -> None:
        pause = self._tripwire_event()
        pause.set()
        pause.mutations.clear()
        worker = make_worker()
        worker.execute_cycle(pause_event=pause)
        assert pause.mutations == []

    def test_worker_leaves_event_state_unchanged(self) -> None:
        pause = threading.Event()
        pause.set()
        stop = threading.Event()
        worker = make_worker()
        worker.execute_cycle(pause_event=pause, stop_event=stop)
        assert pause.is_set() is True
        assert stop.is_set() is False


# ── Lifecycle callbacks ───────────────────────────────────────────────────────


class TestLifecycleCallbacks:
    def test_no_callback_fires_on_an_idle_cycle(self) -> None:
        """A node did not start, so nothing may claim one did.

        The pool's active-node accounting would drift permanently if IDLE cycles
        emitted start events.
        """
        events: list[tuple[Any, ...]] = []
        worker = make_worker(
            on_node_start=lambda *a: events.append(("start", *a)),
            on_node_finish=lambda *a: events.append(("finish", *a)),
        )
        worker.execute_cycle()
        assert events == []

    def test_no_callback_fires_when_stopped_or_paused(self) -> None:
        events: list[tuple[Any, ...]] = []
        worker = make_worker(
            on_node_start=lambda *a: events.append(("start", *a)),
            on_node_finish=lambda *a: events.append(("finish", *a)),
        )
        stop = threading.Event()
        stop.set()
        worker.execute_cycle(stop_event=stop)
        worker.execute_cycle(pause_event=threading.Event())
        assert events == []

    def test_fire_passes_step_index_node_id_and_slot(self) -> None:
        seen: list[tuple[Any, ...]] = []
        worker = make_worker(slot=3, on_node_start=lambda *a: seen.append(a))
        worker._fire_lifecycle(worker.on_node_start, "AGENT_X_S7", "on_node_start")
        assert seen == [(7, "AGENT_X_S7", 3)]

    def test_fire_passes_none_step_for_unsuffixed_nodes(self) -> None:
        seen: list[tuple[Any, ...]] = []
        worker = make_worker(slot=0, on_node_start=lambda *a: seen.append(a))
        worker._fire_lifecycle(worker.on_node_start, "CTRL_MERGE", "on_node_start")
        assert seen == [(None, "CTRL_MERGE", 0)]

    def test_a_raising_callback_does_not_propagate(self) -> None:
        """Callbacks marshal onto the TUI event loop; a broken observer must not
        be able to fail the node it is observing."""

        def explode(*_args: Any) -> None:
            raise RuntimeError("TUI is gone")

        worker = make_worker(on_node_start=explode)
        worker._fire_lifecycle(worker.on_node_start, "NODE_S0", "on_node_start")

    def test_absent_callbacks_are_a_no_op(self) -> None:
        worker = make_worker()
        worker._fire_lifecycle(None, "NODE_S0", "on_node_start")

    def test_start_is_fired_inside_the_try_so_finish_always_pairs(self) -> None:
        """Source-level check of the pairing invariant.

        If the start callback fired before the ``try`` that owns the ``finally``,
        an exception in between would emit a start with no matching finish and the
        visualiser would keep a node lit forever.
        """
        import inspect

        source = inspect.getsource(UniversalSwarmWorker.execute_cycle)
        try_index = source.index("\n        try:")
        start_index = source.index("self.on_node_start")
        finish_index = source.index("self.on_node_finish")
        finally_index = source.index("\n        finally:")
        assert start_index > try_index, "start callback must fire inside the try"
        assert finish_index > finally_index, "finish callback must fire in the finally"
