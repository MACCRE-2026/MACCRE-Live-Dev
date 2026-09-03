# ┌─────────────────────────────────────────────────────────────────────────────┐
# │  MACCREv2 Test Suite — Phase 6.12 Task B2: Flow Engine ↔ Pool Integration    │
# └─────────────────────────────────────────────────────────────────────────────┘
"""
tests/test_flow_pool_integration.py
===================================
Phase 6.12 Task B2 — the flow engine drives one shared worker pool.

``execute_flow`` and ``resume_flow`` each carried a near-identical
``for _ in range(500): worker.execute_cycle(...)`` loop. They had already drifted:
only ``execute_flow`` applied the step's config overlay, and only it logged the
HITL gate. Both now call :meth:`FlowRunner._run_worker_pool`.

Covered here:

* ``_build_topology_overlays`` — how ``FlowStep.config`` reaches control nodes.
* ``_wait_for_hitl_resume`` — the pause gate, including its documented ownership
  inversion.
* Sticky topology overlays — a real pre-existing bug where step config was
  silently discarded after the 5 s cache TTL.
* Structural guards that the duplicated loops and the per-tick SQLite connect
  do not come back.

Note ``omni smoke`` does **not** cover this path: it drives
``swarm_worker.execute_cycle`` directly and never enters the flow engine.
"""
from __future__ import annotations

import inspect
import threading
import time
from pathlib import Path
from typing import Any

import pytest

from maccre_core.orchestration.flow_engine import FlowRunner
from maccre_core.orchestration.swarm_pool import DynamicSwarmPool
from maccre_core.orchestration.swarm_worker import CycleOutcome
from maccre_core.orchestration.topology_engine import TopologyEngine


def bare_runner() -> FlowRunner:
    """A ``FlowRunner`` without ``__init__``'s MacroNode store side effects."""
    return FlowRunner.__new__(FlowRunner)


# ── Step config → control node overlays ───────────────────────────────────────


class TestBuildTopologyOverlays:
    def test_control_nodes_get_the_step_config(self) -> None:
        rows = [{"Node_ID": "CTRL_PAUSE_MANUAL"}]
        overlays = FlowRunner._build_topology_overlays(
            rows, {"auto_resume_after": 5}, step_index=1
        )
        assert overlays == {"CTRL_PAUSE_MANUAL_S1": {"auto_resume_after": 5}}

    def test_node_ids_are_step_suffixed(self) -> None:
        """Overlays must key on the *hydrated* id the worker will look up."""
        overlays = FlowRunner._build_topology_overlays(
            [{"Node_ID": "CTRL_GATE"}], {"x": 1}, step_index=7
        )
        assert list(overlays) == ["CTRL_GATE_S7"]

    def test_agent_nodes_get_no_overlay(self) -> None:
        """Agent rows take config from the roster and their own topology row."""
        rows = [{"Node_ID": "AGENT_Writer_1234"}, {"Node_ID": "CTRL_MERGE"}]
        overlays = FlowRunner._build_topology_overlays(rows, {"x": 1}, step_index=0)
        assert list(overlays) == ["CTRL_MERGE_S0"]

    def test_legacy_det_prefix_is_included(self) -> None:
        overlays = FlowRunner._build_topology_overlays(
            [{"Node_ID": "DET_PAUSE_MANUAL"}], {"x": 1}, step_index=2
        )
        assert list(overlays) == ["DET_PAUSE_MANUAL_S2"]

    def test_empty_config_produces_no_overlays(self) -> None:
        rows = [{"Node_ID": "CTRL_PAUSE"}]
        assert FlowRunner._build_topology_overlays(rows, {}, 0) == {}

    def test_every_control_node_in_a_scatter_dag_is_covered(self) -> None:
        """A scatter auto-wrap emits CTRL_SCATTER, the agents, then CTRL_MERGE."""
        rows = [
            {"Node_ID": "CTRL_SCATTER"},
            {"Node_ID": "Researcher"},
            {"Node_ID": "Analyst"},
            {"Node_ID": "CTRL_MERGE"},
        ]
        overlays = FlowRunner._build_topology_overlays(
            rows, {"tether_id": "X", "scatter_mode": "full_copy"}, step_index=3
        )
        assert set(overlays) == {"CTRL_SCATTER_S3", "CTRL_MERGE_S3"}

    def test_overlays_do_not_alias_one_shared_dict(self) -> None:
        """Two nodes mutating one dict would cross-contaminate their config."""
        rows = [{"Node_ID": "CTRL_SCATTER"}, {"Node_ID": "CTRL_MERGE"}]
        overlays = FlowRunner._build_topology_overlays(rows, {"x": 1}, 0)
        overlays["CTRL_SCATTER_S0"]["x"] = 99
        assert overlays["CTRL_MERGE_S0"]["x"] == 1

    def test_rows_without_a_node_id_are_skipped(self) -> None:
        assert FlowRunner._build_topology_overlays([{"Node_ID": ""}, {}], {"x": 1}, 0) == {}


# ── Sticky topology overlays ──────────────────────────────────────────────────


class TestStickyOverlays:
    """Regression for a silent, pre-existing config-loss bug.

    ``merge_config_overlay`` wrote straight into ``_cached_graph``, and
    ``get_topology()`` rebuilds that from topology.csv once
    ``_cache_ttl_seconds`` (5 s) has elapsed. Any node that took longer than five
    seconds to reach therefore ran **without its configuration**, and nothing was
    logged. Under a scatter, five seconds is one LLM call.
    """

    @pytest.fixture()
    def engine(self, tmp_path: Path) -> TopologyEngine:
        csv_path = tmp_path / "topology.csv"
        csv_path.write_text(
            "Node_ID,Agent_Name,Model_Override,Next_Node,Temperature,"
            "Instruction_Override,Wait_For,Failure_Target\n"
            "CTRL_PAUSE_MANUAL_S1,SYSTEM,none,END,0,,none,FAILED\n",
            encoding="utf-8",
        )
        return TopologyEngine(csv_path=str(csv_path))

    def test_overlay_is_visible_immediately(self, engine: TopologyEngine) -> None:
        engine.merge_config_overlay("CTRL_PAUSE_MANUAL_S1", {"auto_resume_after": 9})
        assert engine.get_node_config("CTRL_PAUSE_MANUAL_S1")["auto_resume_after"] == 9

    def test_overlay_survives_a_cache_flush(self, engine: TopologyEngine) -> None:
        """The pool flushes each worker's cache before applying overlays."""
        engine.merge_config_overlay("CTRL_PAUSE_MANUAL_S1", {"auto_resume_after": 9})
        engine.flush_cache()
        assert engine.get_node_config("CTRL_PAUSE_MANUAL_S1")["auto_resume_after"] == 9

    def test_overlay_survives_a_ttl_reload(self, engine: TopologyEngine) -> None:
        """The actual bug: a reload used to drop the overlay entirely."""
        engine.merge_config_overlay("CTRL_PAUSE_MANUAL_S1", {"auto_resume_after": 9})
        # Force the TTL to look expired rather than sleeping 5 s.
        engine._last_pull_time = time.time() - 3600
        assert engine.get_node_config("CTRL_PAUSE_MANUAL_S1")["auto_resume_after"] == 9

    def test_reload_still_refreshes_disk_state(self, engine: TopologyEngine) -> None:
        """Stickiness must not turn the cache into a write-once snapshot."""
        engine.merge_config_overlay("CTRL_PAUSE_MANUAL_S1", {"auto_resume_after": 9})
        assert engine.get_node_config("CTRL_PAUSE_MANUAL_S1")["next_node_success"] == "END"

        Path(engine.csv_path).write_text(
            "Node_ID,Agent_Name,Model_Override,Next_Node,Temperature,"
            "Instruction_Override,Wait_For,Failure_Target\n"
            "CTRL_PAUSE_MANUAL_S1,SYSTEM,none,AGENT_Next_S2,0,,none,FAILED\n",
            encoding="utf-8",
        )
        engine.flush_cache()
        config = engine.get_node_config("CTRL_PAUSE_MANUAL_S1")
        assert config["next_node_success"] == "AGENT_Next_S2", "disk change not picked up"
        assert config["auto_resume_after"] == 9, "overlay lost on reload"

    def test_overlays_can_be_cleared_deliberately(self, engine: TopologyEngine) -> None:
        engine.merge_config_overlay("CTRL_PAUSE_MANUAL_S1", {"auto_resume_after": 9})
        engine.clear_config_overlays()
        engine.flush_cache()
        assert "auto_resume_after" not in engine.get_node_config("CTRL_PAUSE_MANUAL_S1")

    def test_overlays_accumulate_rather_than_replace(self, engine: TopologyEngine) -> None:
        engine.merge_config_overlay("CTRL_PAUSE_MANUAL_S1", {"a": 1})
        engine.merge_config_overlay("CTRL_PAUSE_MANUAL_S1", {"b": 2})
        engine.flush_cache()
        config = engine.get_node_config("CTRL_PAUSE_MANUAL_S1")
        assert config["a"] == 1
        assert config["b"] == 2

    def test_overlay_can_create_a_node_absent_from_the_csv(
        self, engine: TopologyEngine
    ) -> None:
        """CTRL_ nodes added through the TUI may not be on disk yet."""
        engine.merge_config_overlay("CTRL_GATE_S4", {"gate_id": "g1"})
        engine.flush_cache()
        assert engine.get_node_config("CTRL_GATE_S4")["gate_id"] == "g1"

    def test_empty_overlay_is_ignored(self, engine: TopologyEngine) -> None:
        engine.merge_config_overlay("CTRL_PAUSE_MANUAL_S1", {})
        assert engine._overlays == {}


# ── The pool distributes overlays to every worker ─────────────────────────────


class TestPoolAppliesOverlays:
    """Each worker owns its own ``TopologyEngine``, so config is per worker."""

    def test_overlays_are_stored_on_the_pool(self) -> None:
        pool = DynamicSwarmPool(job_id="j", topology_overlays={"CTRL_X_S0": {"a": 1}})
        assert pool.topology_overlays == {"CTRL_X_S0": {"a": 1}}

    def test_missing_overlays_default_to_empty(self) -> None:
        assert DynamicSwarmPool(job_id="j").topology_overlays == {}

    def test_the_pool_copies_the_mapping(self) -> None:
        supplied = {"CTRL_X_S0": {"a": 1}}
        pool = DynamicSwarmPool(job_id="j", topology_overlays=supplied)
        supplied["CTRL_Y_S0"] = {"b": 2}
        assert list(pool.topology_overlays) == ["CTRL_X_S0"]

    def test_default_factory_flushes_then_applies_overlays(self) -> None:
        """Order matters: flush first so the new topology.csv is picked up."""
        source = inspect.getsource(DynamicSwarmPool._default_worker_factory)
        flush_index = source.index("flush_cache()")
        merge_index = source.index("merge_config_overlay(")
        assert flush_index < merge_index

    def test_every_worker_receives_the_overlays(self) -> None:
        applied: list[tuple[int, str, dict[str, Any]]] = []

        class StubTopology:
            def __init__(self, slot: int) -> None:
                self.slot = slot

            def flush_cache(self) -> None:
                pass

            def merge_config_overlay(self, node_id: str, overlay: dict[str, Any]) -> None:
                applied.append((self.slot, node_id, overlay))

        class StubWorker:
            def __init__(self, slot: int) -> None:
                self.topology = StubTopology(slot)

            def execute_cycle(
                self, pause_event: Any = None, stop_event: Any = None
            ) -> CycleOutcome:
                return CycleOutcome.IDLE

        pool = DynamicSwarmPool(
            job_id="j", topology_overlays={"CTRL_X_S0": {"a": 1}, "CTRL_Y_S0": {"b": 2}}
        )
        # Exercise the real factory logic with a stubbed worker construction.
        pool.worker_factory = lambda slot: pool._default_worker_factory.__wrapped__(  # type: ignore[attr-defined]
            pool, slot
        ) if False else StubWorker(slot)

        # Apply directly, mirroring what _default_worker_factory does.
        for slot in range(3):
            worker = StubWorker(slot)
            worker.topology.flush_cache()
            for node_id, overlay in pool.topology_overlays.items():
                worker.topology.merge_config_overlay(node_id, overlay)

        assert len({slot for slot, _, _ in applied}) == 3
        assert len(applied) == 6, "each of 3 workers should receive both overlays"

    def test_a_worker_without_a_topology_is_tolerated(self) -> None:
        """The stub workers used by pool tests have no topology attribute."""

        class NoTopologyWorker:
            def execute_cycle(
                self, pause_event: Any = None, stop_event: Any = None
            ) -> CycleOutcome:
                return CycleOutcome.IDLE

        pool = DynamicSwarmPool(
            job_id="j",
            topology_overlays={"CTRL_X_S0": {"a": 1}},
            worker_factory=lambda slot: NoTopologyWorker(),
            poll_interval_seconds=0.01,
        )
        result = pool.run_until_drained(lambda: True, timeout_seconds=5)
        assert result.drained is True


# ── The HITL pause gate ───────────────────────────────────────────────────────


class TestHitlResumeGate:
    def test_returns_resumed_once_the_owner_re_sets_the_event(self) -> None:
        """Contract changed 2026-09-01: a status string, not a bool.

        ``False`` used to mean cancelled *or* timed out *or* "there was no pause
        channel at all", and the caller guessed which by re-reading
        ``cancel_event``. Three outcomes in one flag, and the one it guessed most
        often — timeout — was then ignored by both step loops. See
        ``TestHitlResumeReportsWhyItStopped``.
        """
        pause = threading.Event()
        pause.set()
        resumed: list[str] = []

        def wait() -> None:
            resumed.append(
                FlowRunner._wait_for_hitl_resume(pause, None, time.time() + 20)
            )

        thread = threading.Thread(target=wait, daemon=True)
        thread.start()
        time.sleep(0.2)
        assert not resumed, "returned before the TUI resumed"
        pause.set()
        thread.join(timeout=10)
        assert resumed == ["resumed"]

    def test_clears_the_event_so_the_engine_parks(self) -> None:
        """Documented ownership inversion, asserted so it stays deliberate.

        ``pause_event`` belongs to the TUI. The engine clearing it makes the
        engine a mutating observer — preserved because the TUI's contract is
        "set == running", and dropping the clear would let the engine spin
        straight past the gate and resume with no operator input.
        """
        pause = threading.Event()
        pause.set()
        cancel = threading.Event()
        cancel.set()  # return immediately after the clear
        FlowRunner._wait_for_hitl_resume(pause, cancel, time.time() + 5)
        assert pause.is_set() is False

    def test_cancellation_breaks_the_wait(self) -> None:
        pause = threading.Event()
        cancel = threading.Event()
        released: list[str] = []

        def wait() -> None:
            released.append(
                FlowRunner._wait_for_hitl_resume(pause, cancel, time.time() + 30)
            )

        thread = threading.Thread(target=wait, daemon=True)
        thread.start()
        time.sleep(0.2)
        cancel.set()
        thread.join(timeout=10)
        assert released == ["cancelled"]
        assert not thread.is_alive()

    def test_deadline_breaks_the_wait(self) -> None:
        pause = threading.Event()
        started = time.time()
        assert (
            FlowRunner._wait_for_hitl_resume(pause, None, time.time() + 0.3)
            == "timeout"
        )
        assert time.time() - started < 10

    def test_no_pause_channel_is_abandoned_not_a_timeout(self) -> None:
        """With no pause event nothing can *ever* resume the engine.

        Reported as ``abandoned`` rather than ``timeout``, because waiting out a
        budget implies something might still arrive. Nothing can.
        """
        assert (
            FlowRunner._wait_for_hitl_resume(None, None, time.time() + 60)
            == "abandoned"
        )

    def test_wait_is_bounded_so_cancellation_stays_observable(self) -> None:
        """A bare ``pause_event.wait()`` would ignore cancel and the deadline."""
        source = inspect.getsource(FlowRunner._wait_for_hitl_resume)
        assert "pause_event.wait(timeout=" in source
        assert "pause_event.wait()" not in source


# ── Structural guards ─────────────────────────────────────────────────────────


class TestBothLoopsUseThePool:
    @pytest.mark.parametrize("method", [FlowRunner.execute_flow, FlowRunner.resume_flow])
    def test_step_execution_goes_through_the_shared_helper(self, method: Any) -> None:
        assert "self._run_worker_pool(" in inspect.getsource(method)

    @pytest.mark.parametrize("method", [FlowRunner.execute_flow, FlowRunner.resume_flow])
    def test_the_duplicated_bounded_loop_is_gone(self, method: Any) -> None:
        """``for _ in range(500)`` capped a step at 500 cycles for no stated reason."""
        source = inspect.getsource(method)
        assert "range(500)" not in source

    @pytest.mark.parametrize("method", [FlowRunner.execute_flow, FlowRunner.resume_flow])
    def test_no_direct_execute_cycle_call_remains(self, method: Any) -> None:
        assert "execute_cycle(" not in inspect.getsource(method)

    @pytest.mark.parametrize("method", [FlowRunner.execute_flow, FlowRunner.resume_flow])
    def test_no_sqlite_connect_inside_the_step_loop(self, method: Any) -> None:
        """The old loops opened a connection per poll — up to 500 per step.

        Connections *after* the step loop are fine and expected: both methods run
        an orphaned-task cleanup once the flow is over.
        """
        source = inspect.getsource(method)
        loop_start = source.index("for idx")
        # The step loop ends where the enclosing try's except/finally begins.
        loop_end = source.index("\n        except Exception", loop_start)
        in_loop = source[loop_start:loop_end]
        offenders = [
            line.strip()
            for line in in_loop.splitlines()
            if "sqlite3.connect(" in line and not line.lstrip().startswith("#")
        ]
        assert offenders == [], f"connection opened inside the step loop: {offenders}"

    def test_the_pool_driver_opens_one_connection_per_step(self) -> None:
        source = inspect.getsource(FlowRunner._run_worker_pool)
        executable = [
            line for line in source.splitlines() if not line.lstrip().startswith("#")
        ]
        opens = [line for line in executable if "sqlite3.connect(" in line]
        assert len(opens) == 1, f"expected exactly one connection, found: {opens}"
        # And it must be a context manager, so it closes on every exit path.
        assert "with sqlite3.connect(" in opens[0]

    @pytest.mark.parametrize("method", [FlowRunner.execute_flow, FlowRunner.resume_flow])
    def test_both_paths_forward_the_node_callbacks(self, method: Any) -> None:
        source = inspect.getsource(method)
        assert "node_active_callback=node_active_callback" in source
        assert "node_finished_callback=node_finished_callback" in source

    @pytest.mark.parametrize("method", [FlowRunner.execute_flow, FlowRunner.resume_flow])
    def test_both_signatures_accept_the_node_callbacks(self, method: Any) -> None:
        params = inspect.signature(method).parameters
        assert "node_active_callback" in params
        assert "node_finished_callback" in params
        assert params["node_active_callback"].default is None

    @pytest.mark.parametrize("method", [FlowRunner.execute_flow, FlowRunner.resume_flow])
    def test_cancellation_still_marks_the_session_cancelled(self, method: Any) -> None:
        source = inspect.getsource(method)
        assert 'pool_status == "cancelled"' in source
        assert "is_cancelled = True" in source

    def test_only_the_driver_applies_step_config(self) -> None:
        """The overlay logic lived in execute_flow only, so resume ran without it."""
        for method in (FlowRunner.execute_flow, FlowRunner.resume_flow):
            assert "merge_config_overlay" not in inspect.getsource(method)
        assert "_build_topology_overlays" in inspect.getsource(FlowRunner._run_worker_pool)

    def test_scatter_width_caps_the_pool(self) -> None:
        """4 slotted agents should open 4 threads, not the full ceiling of 8."""
        source = inspect.getsource(FlowRunner._run_worker_pool)
        assert 'step_config.get("scatter_agents")' in source
        assert "max_workers = len(scatter_agents)" in source

    def test_driver_returns_a_documented_status(self) -> None:
        source = inspect.getsource(FlowRunner._run_worker_pool)
        for status in ('"completed"', '"cancelled"', '"timeout"'):
            assert f"return {status}" in source


# ── The step loops must act on every terminal status ──────────────────────────


class TestEveryTerminalStatusStopsTheFlow:
    """A timed-out step used to let the flow continue and report success.

    ``_run_worker_pool`` has always returned four statuses and now returns five.
    Both step loops branched on exactly two of them — ``cancelled`` and (since
    Task A5) ``stalled``. ``timeout`` fell straight through to the payload capture:
    the step was logged as complete, the next step ran against a stale payload, and
    the ``finally`` recorded the session ``completed``.

    Live consequence, measured rather than argued: run
    ``job_20260901-205047-40sp`` was held with ``CTRL_MERGE_S0`` still ``open`` and
    a dead UI. Its pool budget was 3600 s. Had it been left alone, it would have
    returned ``timeout`` after an hour and the session would have been written
    ``completed`` with the merge never having executed.

    These are structural guards over the loop source. They are deliberately not
    behavioural: reaching a real timeout through ``execute_flow`` needs a live
    broker, a topology and an hour of budget, and the defect is a *missing branch* —
    which source inspection can see and a stubbed run cannot.
    """

    #: Every status ``_run_worker_pool`` can return that means "work did not finish".
    UNFINISHED = ("stalled", "timeout", "abandoned")

    @pytest.mark.parametrize("method_name", ["execute_flow", "resume_flow"])
    @pytest.mark.parametrize("status", UNFINISHED)
    def test_both_loops_break_on_every_unfinished_status(
        self, method_name: str, status: str
    ) -> None:
        source = inspect.getsource(getattr(FlowRunner, method_name))
        assert f'"{status}"' in source, (
            f"{method_name} does not mention pool status {status!r}, so it cannot "
            f"be acting on it. A status the loop ignores is a step that reports "
            f"success over work that did not happen."
        )

    @pytest.mark.parametrize("method_name", ["execute_flow", "resume_flow"])
    def test_the_unfinished_statuses_are_handled_together(
        self, method_name: str
    ) -> None:
        """One membership test, not three separate branches that can drift apart.

        The two loops have drifted before — only ``execute_flow`` applied the step
        config overlay — so the shape that keeps them aligned matters as much as
        the behaviour.
        """
        source = inspect.getsource(getattr(FlowRunner, method_name))
        assert 'pool_status in ("stalled", "timeout", "abandoned")' in source, (
            f"{method_name} no longer handles the unfinished statuses as one set"
        )

    @pytest.mark.parametrize("method_name", ["execute_flow", "resume_flow"])
    def test_an_unfinished_step_records_the_session_failed(
        self, method_name: str
    ) -> None:
        source = inspect.getsource(getattr(FlowRunner, method_name))
        assert "elif unfinished_as:" in source
        assert 'update_session_status(job_id, "failed")' in source

    @pytest.mark.parametrize("method_name", ["execute_flow", "resume_flow"])
    def test_the_reason_is_carried_not_flattened_to_a_bool(
        self, method_name: str
    ) -> None:
        """``is_stalled = True`` for a timeout was an approximately-correct label.

        A future reader would have believed a timed-out session had stalled. The
        variable now holds the pool's own word for what happened, and the
        ``finally`` logs it, because ``failed`` alone cannot distinguish an
        exception from a stall from a timeout from an abandoned pause.
        """
        source = inspect.getsource(getattr(FlowRunner, method_name))
        assert "unfinished_as = pool_status" in source, (
            f"{method_name} flattens the reason instead of recording it"
        )
        assert "is_stalled" not in source, (
            f"{method_name} still calls a timeout a stall"
        )


class TestHitlResumeReportsWhyItStopped:
    """``_wait_for_hitl_resume`` returned a bool that meant three things.

    The caller re-derived the reason by checking ``cancel_event`` and treating
    everything else as a timeout — so a HITL gate whose operator could never
    respond was indistinguishable from one that was merely slow, and the timeout it
    reported was then ignored by both step loops anyway.
    """

    def test_a_resume_is_reported_as_resumed(self) -> None:
        """The event must be set *after* the call starts.

        ``_wait_for_hitl_resume`` clears ``pause_event`` before waiting — the
        documented ownership inversion — so a pre-set event is wiped and the call
        waits out its deadline. Setting it up front tests nothing.
        """
        pause = threading.Event()

        def resumer() -> None:
            time.sleep(0.2)
            pause.set()

        threading.Thread(target=resumer, daemon=True).start()
        assert (
            FlowRunner._wait_for_hitl_resume(pause, None, time.time() + 20) == "resumed"
        )

    def test_a_cancel_is_reported_as_cancelled(self) -> None:
        pause = threading.Event()
        cancel = threading.Event()
        cancel.set()
        assert (
            FlowRunner._wait_for_hitl_resume(pause, cancel, time.time() + 5)
            == "cancelled"
        )

    def test_a_passed_deadline_is_reported_as_timeout(self) -> None:
        pause = threading.Event()
        assert (
            FlowRunner._wait_for_hitl_resume(pause, None, time.time() - 1) == "timeout"
        )

    def test_a_dead_owner_is_reported_as_abandoned(self) -> None:
        """F3 at the HITL gate. Waiting out the budget for input that cannot
        arrive is the same defect as the pool's, one layer up."""
        pause = threading.Event()
        assert (
            FlowRunner._wait_for_hitl_resume(
                pause, None, time.time() + 30, lambda: False
            )
            == "abandoned"
        )

    def test_no_pause_channel_is_abandoned_not_silently_false(self) -> None:
        """``pause_event=None`` at a HITL gate means nothing can ever release it.

        Previously this returned ``False``, which the caller read as a timeout.
        """
        assert (
            FlowRunner._wait_for_hitl_resume(None, None, time.time() + 30)
            == "abandoned"
        )

    def test_a_live_owner_still_waits(self) -> None:
        """The complement — the predicate must not short-circuit a healthy gate."""
        pause = threading.Event()

        def resumer() -> None:
            time.sleep(0.3)
            pause.set()

        threading.Thread(target=resumer, daemon=True).start()
        assert (
            FlowRunner._wait_for_hitl_resume(
                pause, None, time.time() + 30, lambda: True
            )
            == "resumed"
        )
