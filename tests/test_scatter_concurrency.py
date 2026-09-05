# ┌─────────────────────────────────────────────────────────────────────────────┐
# │  MACCREv2 Test Suite — Phase 6.12 Task B3: Scatter Concurrency Proof         │
# └─────────────────────────────────────────────────────────────────────────────┘
"""
tests/test_scatter_concurrency.py
=================================
Phase 6.12 Task B3 — the deliverable, measured.

This is the test the whole phase exists to make pass: a 4-lane and then an 8-lane
``CTRL_SCATTER`` executed through ``FlowRunner._run_worker_pool`` against the
**real** broker and the **real** ``task_queue``, asserting both that lanes overlap
and that the wall clock beats sequential execution.

What is real here: ``LocalMessageBroker``, the SQLite queue, ``BEGIN EXCLUSIVE``
task claiming, ``count_ready_tasks`` demand estimation, the ``wait_for`` gather
gate, ``DynamicSwarmPool`` scaling, and the flow engine's drain logic.

What is stubbed: the LLM call. A ``worker_factory`` supplies workers that claim
real tasks through the real broker and route them through real
``route_task`` calls, but sleep instead of calling a model. That keeps the test
free, fast and deterministic while still exercising every piece of concurrency
machinery. ``omni smoke`` covers the live inference path, but it drives
``execute_cycle`` directly and never enters the flow engine — so without this
file the pool integration has no end-to-end coverage at all.

Also covered: the provider rate-limit guard required by Era 2 roadmap §6.12.
"""
from __future__ import annotations

import inspect
import threading
import time
from pathlib import Path
from typing import Any, Optional

import pytest

from maccre_core.orchestration.concurrency import (
    DEFAULT_PROVIDER_RPM,
    RateLimiter,
    get_provider_rate_limiter,
    reset_provider_rate_limiters,
)
from maccre_core.orchestration.flow_engine import FlowRunner
from maccre_core.orchestration.local_broker import LocalMessageBroker
from maccre_core.orchestration.topology_engine import TopologyEngine
from maccre_core.utils.path_resolver import get_datacenter_path
from maccre_core.orchestration.swarm_worker import CycleOutcome

JOB = "job_b3_scatter"

#: Simulated per-node duration. Long enough that overlap is unambiguous, short
#: enough that an 8-lane run finishes in about a second when it really is parallel.
NODE_SECONDS = 0.30


class ConcurrencyTracker:
    """Counts workers simultaneously inside node execution."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.current = 0
        self.peak = 0
        self.executed: list[str] = []

    def __enter__(self) -> "ConcurrencyTracker":
        with self._lock:
            self.current += 1
            self.peak = max(self.peak, self.current)
        return self

    def __exit__(self, *_exc: object) -> None:
        with self._lock:
            self.current -= 1

    def record(self, node_id: str) -> None:
        with self._lock:
            self.executed.append(node_id)


#: Column order written by ``admin_tools.build_topology``.
TOPOLOGY_HEADER = (
    "Node_ID,Agent_Name,Model_Override,Next_Node,Temperature,Instruction_Override,"
    "Wait_For,Failure_Target,Max_Recursion,Artifact_Path,Live_Profile,"
    "Dialogue_Partner,Dialogue_Rounds,Payload_Mode,Tools_Allowed"
)


class ScatterTopology:
    """Builds a real ``topology.csv`` for a ``CTRL_SCATTER -> lanes -> CTRL_MERGE`` DAG.

    Mirrors what ``FlowRunner._get_macronode``'s scatter auto-wrap produces,
    including the ``wait_for`` gather gate on the merge node.

    Writing an actual CSV rather than stubbing a provider means the workers and
    ``_run_worker_pool``'s own gate resolver both read the topology through the
    real :class:`TopologyEngine`, so CSV parsing and gate resolution are covered
    too.
    """

    def __init__(self, lanes: list[str], step_index: int = 0) -> None:
        self.step = step_index
        self.scatter = f"CTRL_SCATTER_S{step_index}"
        self.merge = f"CTRL_MERGE_S{step_index}"
        self.lanes = [f"{name}_S{step_index}" for name in lanes]

    def write_csv(self) -> Path:
        """Write the DAG to the active project's ``topology.csv``."""
        csv_path = get_datacenter_path("02_Dynamic_Context", "topology.csv")
        csv_path.parent.mkdir(parents=True, exist_ok=True)

        rows = [
            # Scatter entry fans out to every lane.
            f"{self.scatter},SYSTEM,none,{','.join(self.lanes)},0,,none,FAILED,3,,FALSE,,0,Unified Ledger,",
        ]
        for lane in self.lanes:
            rows.append(
                f"{lane},{lane},none,{self.merge},1.0,,none,FAILED,3,,FALSE,,0,Unified Ledger,"
            )
        # The gather gate: the merge cannot be claimed until every lane completes.
        rows.append(
            f"{self.merge},SYSTEM,none,END,0,,{'|'.join(self.lanes)},FAILED,3,,FALSE,,0,Unified Ledger,"
        )

        # Next_Node holds a comma-separated fan-out list, so the field must be
        # quoted or DictReader will read it as extra columns.
        quoted = []
        for row in rows:
            parts = row.split(",")
            if len(parts) > 15:
                # Re-assemble with the Next_Node field quoted.
                head = parts[0:3]
                tail = parts[-11:]
                middle = ",".join(parts[3:-11])
                quoted.append(",".join([*head, f'"{middle}"', *tail]))
            else:
                quoted.append(row)

        csv_path.write_text(
            TOPOLOGY_HEADER + "\n" + "\n".join(quoted) + "\n", encoding="utf-8"
        )
        return csv_path


class ScatterWorker:
    """Claims real tasks and routes them, standing in for an LLM call.

    A lane either sleeps for *node_seconds* (used to measure speedup) or waits on
    a shared :class:`threading.Barrier` (used to prove width). The barrier is the
    stronger instrument: it can only trip if every lane is genuinely in flight at
    the same instant, so it turns "is this concurrent?" into a deterministic
    question with no timing assumptions.
    """

    def __init__(
        self,
        slot: int,
        db_path: str,
        topology: ScatterTopology,
        tracker: ConcurrencyTracker,
        node_seconds: float = NODE_SECONDS,
        barrier: threading.Barrier | None = None,
        barrier_timeout: float = 60.0,
    ) -> None:
        self.slot = slot
        self.names = topology
        self.tracker = tracker
        self.node_seconds = node_seconds
        self.barrier = barrier
        self.barrier_timeout = barrier_timeout
        # A real engine per worker, matching the production shape: each
        # UniversalSwarmWorker owns its own TopologyEngine.
        self.topology = TopologyEngine()
        self.topology.flush_cache()
        # A broker per worker, exactly as the real pool does: LocalMessageBroker
        # keeps SQLite connections per thread so BEGIN EXCLUSIVE isolates the claim.
        self.broker = LocalMessageBroker(db_path=db_path)
        self.worker_id = f"scatter_worker_t{slot}"

    def execute_cycle(
        self,
        pause_event: Optional[Any] = None,
        stop_event: Optional[Any] = None,
    ) -> CycleOutcome:
        if stop_event is not None and stop_event.is_set():
            return CycleOutcome.STOPPED
        if pause_event is not None and not pause_event.is_set():
            time.sleep(0.01)
            return CycleOutcome.PAUSED

        task = self.broker.fetch_and_lock_task(self.worker_id, self.topology)
        if task is None:
            time.sleep(0.01)
            return CycleOutcome.IDLE

        node_id = str(task["current_node"])
        config: dict[str, Any] = {}
        try:
            config = self.topology.get_node_config(node_id)
        except Exception:
            pass

        # Control nodes are instant; agent lanes are where the time goes.
        if node_id.startswith(("CTRL_", "DET_")):
            self.tracker.record(node_id)
        else:
            with self.tracker:
                self.tracker.record(node_id)
                if self.barrier is not None:
                    # Trips only when every lane is executing simultaneously. A
                    # pool that cannot reach full width raises BrokenBarrierError
                    # here, which the harness reports as a lane failure.
                    self.barrier.wait(timeout=self.barrier_timeout)
                elif self.node_seconds:
                    time.sleep(self.node_seconds)

        self.broker.route_task(
            row_id=int(task["id"]),
            job_id=str(task["job_id"]),
            next_node_str=str(config.get("next_node_success", "END")),
            new_payload_path=f"/artifact_{node_id}.md",
            source_payload_path=str(task.get("source_payload_path") or ""),
        )
        return CycleOutcome.WORKED


def run_scatter(
    lane_count: int,
    node_seconds: float = NODE_SECONDS,
    max_workers: int | None = None,
    use_barrier: bool = False,
) -> tuple[str, ConcurrencyTracker, float, ScatterTopology]:
    """Drive one scatter step through the real flow-engine pool driver.

    ``conftest`` points ``MACCRE_ROOT`` at a per-test ``tmp_path``, so
    ``get_datacenter_path`` already resolves into a throwaway datacenter. The
    queue must live at exactly the path ``_run_worker_pool`` resolves for itself,
    or the driver would poll a different database than the workers claim from.

    Returns:
        ``(status, tracker, elapsed_seconds, topology)``
    """
    lanes = [f"Agent{i}" for i in range(lane_count)]
    topology = ScatterTopology(lanes, step_index=0)
    topology.write_csv()

    db_path = str(get_datacenter_path("swarm_queue.db"))
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    tracker = ConcurrencyTracker()
    barrier = threading.Barrier(lane_count) if use_barrier else None

    control_broker = LocalMessageBroker(db_path=db_path)
    workers: list[ScatterWorker] = []
    try:
        # Seed the DAG at its entry node, exactly as _find_starting_nodes would.
        control_broker.inject_task(
            job_id=JOB, payload_path="/seed.md", starting_node=topology.scatter
        )

        def factory(slot: int) -> ScatterWorker:
            worker = ScatterWorker(
                slot, db_path, topology, tracker, node_seconds, barrier=barrier
            )
            workers.append(worker)
            return worker

        runner = FlowRunner.__new__(FlowRunner)
        topo_rows = [
            {"Node_ID": "CTRL_SCATTER"},
            *[{"Node_ID": name} for name in lanes],
            {"Node_ID": "CTRL_MERGE"},
        ]

        # Patch the pool construction to inject stub workers while leaving every
        # other part of _run_worker_pool — overlays, demand estimation, drain
        # detection, the HITL gate — running for real.
        from maccre_core.orchestration import flow_engine as flow_engine_module

        real_pool_cls = flow_engine_module.DynamicSwarmPool

        def pool_with_stub_workers(*args: Any, **kwargs: Any) -> Any:
            kwargs["worker_factory"] = factory
            kwargs["poll_interval_seconds"] = 0.02
            return real_pool_cls(*args, **kwargs)

        flow_engine_module.DynamicSwarmPool = pool_with_stub_workers  # type: ignore[assignment]
        started = time.monotonic()
        try:  # noqa: SIM105
            status = runner._run_worker_pool(
                job_id=JOB,
                step_index=0,
                broker=control_broker,
                topo_rows=topo_rows,
                step_config={"scatter_agents": lanes} if max_workers is None else {},
                current_payload="/seed.md",
                max_workers=max_workers,
                timeout_seconds=180.0,
            )
        finally:
            flow_engine_module.DynamicSwarmPool = real_pool_cls  # type: ignore[assignment]
        elapsed = time.monotonic() - started
        return status, tracker, elapsed, topology
    finally:
        for worker in workers:
            worker.broker.close()
        control_broker.close()


# ── The deliverable ───────────────────────────────────────────────────────────


class TestScatterReachesRealConcurrency:
    def test_four_lane_scatter_runs_all_lanes_simultaneously(
        self, tmp_path: Path
    ) -> None:
        """All 4 lanes must be in flight at the same instant.

        Barrier-based rather than timing-based. Each lane blocks on a
        ``Barrier(4)``, so the run can only complete if the pool genuinely had
        four lanes executing together — a pool one thread short deadlocks the
        barrier and the run fails instead of quietly reporting a lower peak.
        """
        status, tracker, _elapsed, topo = run_scatter(lane_count=4, use_barrier=True)

        assert status == "completed", f"pool returned {status}"
        assert tracker.peak == 4, (
            f"barrier tripped but peak was {tracker.peak} — accounting is wrong"
        )
        assert len([n for n in tracker.executed if n in topo.lanes]) == 4

    def test_eight_lane_scatter_runs_all_lanes_simultaneously(
        self, tmp_path: Path
    ) -> None:
        """The headline Phase 6.12 claim: 8 agents executing at once.

        With the pre-6.12 single-threaded loop this barrier could never trip,
        whatever the scatter width — the second lane would not start until the
        first had finished.
        """
        status, tracker, _elapsed, topo = run_scatter(lane_count=8, use_barrier=True)

        assert status == "completed", f"pool returned {status}"
        assert tracker.peak == 8, (
            f"barrier tripped but peak was {tracker.peak} — accounting is wrong"
        )
        assert len([n for n in tracker.executed if n in topo.lanes]) == 8

    def test_eight_lane_scatter_beats_sequential_wall_clock(
        self, tmp_path: Path
    ) -> None:
        """Concurrency has to save time, not merely interleave.

        Separate from the width proof above, because a barrier releases every lane
        together and so says nothing about elapsed time. Sleeping lanes measure
        the speedup that actually matters.

        The threshold is deliberately loose. Ramp-up is not instant — the pool
        learns the lane count only once the scatter entry node routes, and each
        worker then builds its own ``TopologyEngine`` and broker — so a short
        simulated node spends a visible fraction of the run ramping. Real nodes
        take seconds, which dwarfs that.

        ``node_seconds`` RAISED 0.25 → 1.0 ON 2026-09-04, FROM MEASUREMENT
        -----------------------------------------------------------------
        At 0.25 s this was the last load-sensitive test in the suite, failing under
        full-suite load and passing in isolation. It was recorded in the 4.99 status
        document §9 as an operator decision between loosening the bound, raising the
        node time, or accepting the flake. Raising the node time was chosen because it
        removes measurement noise **without weakening the assertion.**

        The arithmetic, since the baseline is computed rather than measured
        (``sequential = lane_count * node_seconds``). Eight lanes overlap, so::

            elapsed  ≈  node_seconds + O           where O is fixed ramp-up
            passes   iff  node_seconds + O < 0.6 * 8 * node_seconds
                     iff  O < 3.8 * node_seconds
                     iff  node_seconds > O / 3.8

        Measured in-suite at three durations, so O was observed rather than assumed:

        ===============  ==========  =================  ======
        ``node_seconds``  ``elapsed``  implied O          peak
        ===============  ==========  =================  ======
        0.25              0.813       0.563              **7**
        0.50              1.016       0.516              8
        1.00              1.547       0.547              8
        ===============  ==========  =================  ======

        **O is roughly constant at ~0.55 s**, which is what the model predicts and
        why the fix works: at 0.25 s the required minimum was ~0.15 s, leaving only
        1.8× margin, and an earlier failing run implied O ≈ 1.08 s — past the limit.
        At 1.0 s the assertion tolerates O up to 3.8 s, about 7× the measured value
        and 2.6× the worst ever observed.

        **And the second column mattered more than the first.** At 0.25 s peak
        concurrency reached only **7** — the run finished before the pool could ramp
        to 8. So the old duration was not merely measuring noisily, it was measuring a
        scenario that never achieved the concurrency the test exists to price. Both 0.5
        and 1.0 reach 8.

        Cost: about 1.5 s of suite time.
        """
        lane_count = 8
        node_seconds = 1.0
        status, tracker, elapsed, _topo = run_scatter(
            lane_count=lane_count, node_seconds=node_seconds
        )

        assert status == "completed", f"pool returned {status}"

        # Assert full width was reached NATURALLY, under demand scaling.
        #
        # Not redundant with the barrier proof above: that one *forces* eight lanes by
        # construction, because a Barrier(8) cannot release otherwise. This asserts the
        # pool arrives at eight on its own when the work justifies it — a different
        # claim, and the one that was quietly false at node_seconds=0.25.
        assert tracker.peak == lane_count, (
            f"only {tracker.peak} of {lane_count} lanes ran concurrently, so the "
            f"wall-clock ratio below is pricing a partially-ramped run"
        )

        sequential = lane_count * node_seconds
        overhead = elapsed - node_seconds
        assert elapsed < sequential * 0.6, (
            f"took {elapsed:.2f}s against a {sequential:.2f}s sequential baseline "
            f"(peak concurrency {tracker.peak}). Implied fixed overhead "
            f"{overhead:.2f}s against a budget of {3.8 * node_seconds:.2f}s — if the "
            f"overhead is what grew, raise node_seconds; if the peak is short, the "
            f"pool stopped reaching full width"
        )

    def test_concurrency_does_not_collapse_with_fast_nodes(
        self, tmp_path: Path
    ) -> None:
        """Guard against a regression that silently returns the engine to 1 thread.

        Peak is timing-sensitive when nodes are shorter than ramp-up, so the bound
        is loose on purpose — its job is to catch a collapse to serial execution,
        not to pin an exact width. The barrier tests above pin the width.
        """
        _status, tracker, _elapsed, _topo = run_scatter(
            lane_count=8, node_seconds=NODE_SECONDS
        )
        assert tracker.peak >= 3, f"peak concurrency collapsed to {tracker.peak}"

    def test_every_lane_executes_exactly_once(self, tmp_path: Path) -> None:
        """No lane lost, no lane duplicated.

        Duplication is the failure mode a shared broker connection produced
        before Task A2 made connections thread-local.
        """
        _status, tracker, _elapsed, topo = run_scatter(lane_count=8)
        lane_runs = [n for n in tracker.executed if not n.startswith(("CTRL_", "DET_"))]
        assert sorted(lane_runs) == sorted(topo.lanes)
        assert len(lane_runs) == len(set(lane_runs)), "a lane executed twice"

    def test_the_gather_gate_holds_until_every_lane_finishes(
        self, tmp_path: Path
    ) -> None:
        """CTRL_MERGE must be last. It carries ``wait_for`` on all lanes."""
        _status, tracker, _elapsed, topo = run_scatter(lane_count=8)
        assert topo.merge in tracker.executed, "the merge node never ran"
        assert tracker.executed[-1] == topo.merge, (
            f"merge was not last; order was {tracker.executed}"
        )

    def test_scatter_entry_runs_before_any_lane(self, tmp_path: Path) -> None:
        _status, tracker, _elapsed, topo = run_scatter(lane_count=4)
        assert tracker.executed[0] == topo.scatter

    def test_linear_step_stays_single_threaded(self, tmp_path: Path) -> None:
        """One lane must not open extra threads — a linear flow is still linear."""
        _status, tracker, _elapsed, _topo = run_scatter(lane_count=1)
        assert tracker.peak == 1

    def test_queue_is_fully_drained(self, tmp_path: Path) -> None:
        """No task may be left open or locked once the step reports completed."""
        status, _tracker, _elapsed, _topo = run_scatter(lane_count=4)
        db_path = str(get_datacenter_path("swarm_queue.db"))
        assert status == "completed"
        broker = LocalMessageBroker(db_path=db_path)
        try:
            leftover = broker._get_conn().execute(
                "SELECT current_node, lock_status FROM task_queue "
                "WHERE job_id = ? AND lock_status IN ('open', 'locked')",
                (JOB,),
            ).fetchall()
        finally:
            broker.close()
        assert [tuple(r) for r in leftover] == []

    def test_explicit_max_workers_caps_concurrency(self, tmp_path: Path) -> None:
        """An operator-set ceiling must win over the lane count."""
        _status, tracker, _elapsed, _topo = run_scatter(lane_count=8, max_workers=2)
        assert tracker.peak <= 2, f"peak was {tracker.peak}, expected at most 2"

    def test_scatter_width_derives_the_ceiling(self, tmp_path: Path) -> None:
        """4 slotted agents should open 4 threads, not the full ceiling of 8."""
        _status, tracker, _elapsed, _topo = run_scatter(lane_count=4)
        assert tracker.peak <= 4


# ── Provider rate-limit guard ─────────────────────────────────────────────────


class TestRateLimiter:
    @pytest.fixture(autouse=True)
    def _reset(self) -> None:
        reset_provider_rate_limiters()
        yield
        reset_provider_rate_limiters()

    def test_permits_up_to_the_limit_without_blocking(self) -> None:
        limiter = RateLimiter(max_per_minute=5, window_seconds=60.0)
        started = time.monotonic()
        for _ in range(5):
            assert limiter.acquire(timeout=1.0) is True
        assert time.monotonic() - started < 1.0

    def test_blocks_once_the_window_is_full(self) -> None:
        limiter = RateLimiter(max_per_minute=2, window_seconds=60.0)
        assert limiter.acquire(timeout=1.0) is True
        assert limiter.acquire(timeout=1.0) is True
        assert limiter.try_acquire() is False

    def test_a_slot_frees_as_the_window_slides(self) -> None:
        limiter = RateLimiter(max_per_minute=2, window_seconds=0.3)
        assert limiter.acquire(timeout=1.0) is True
        assert limiter.acquire(timeout=1.0) is True
        assert limiter.try_acquire() is False
        # Third acquire must succeed once the first two age out.
        assert limiter.acquire(timeout=5.0) is True

    def test_timeout_reserves_nothing(self) -> None:
        """A refused caller must not silently consume quota."""
        limiter = RateLimiter(max_per_minute=1, window_seconds=60.0)
        assert limiter.acquire(timeout=1.0) is True
        before = limiter.in_window
        assert limiter.acquire(timeout=0.1) is False
        assert limiter.in_window == before

    def test_limit_is_enforced_across_threads(self) -> None:
        """The property that matters: 8 workers share one budget.

        A per-thread or per-router limiter would let each thread spend the whole
        allowance.
        """
        limiter = RateLimiter(max_per_minute=6, window_seconds=60.0)
        granted: list[int] = []
        granted_lock = threading.Lock()
        start = threading.Barrier(8)

        def worker(slot: int) -> None:
            start.wait(timeout=15)
            for _ in range(3):
                if limiter.try_acquire():
                    with granted_lock:
                        granted.append(slot)

        threads = [threading.Thread(target=worker, args=(i,), daemon=True) for i in range(8)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=30)
            assert not t.is_alive()

        assert len(granted) == 6, f"granted {len(granted)} of a 6-request budget"

    def test_waiters_are_eventually_served(self) -> None:
        limiter = RateLimiter(max_per_minute=2, window_seconds=0.25)
        results: list[bool] = []
        results_lock = threading.Lock()
        start = threading.Barrier(4)

        def worker() -> None:
            start.wait(timeout=15)
            ok = limiter.acquire(timeout=10.0)
            with results_lock:
                results.append(ok)

        threads = [threading.Thread(target=worker, daemon=True) for _ in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=30)
            assert not t.is_alive()
        assert all(results), "a waiter was starved"
        assert len(results) == 4

    def test_zero_or_negative_limit_is_clamped(self) -> None:
        """A limiter permitting nothing would deadlock the swarm, not protect it."""
        for value in (0, -5):
            assert RateLimiter(max_per_minute=value).max_per_minute == 1

    def test_release_unused_returns_the_slot(self) -> None:
        limiter = RateLimiter(max_per_minute=1, window_seconds=60.0)
        assert limiter.acquire(timeout=1.0) is True
        assert limiter.try_acquire() is False
        limiter.release_unused()
        assert limiter.try_acquire() is True

    def test_stats_track_grants_and_waits(self) -> None:
        limiter = RateLimiter(max_per_minute=1, window_seconds=0.2)
        limiter.acquire(timeout=1.0)
        limiter.acquire(timeout=5.0)  # must wait for the window to slide
        stats = limiter.stats
        assert stats["granted"] == 2
        assert stats["waits"] >= 1
        assert stats["total_wait_seconds"] > 0


class TestProviderLimiterSingleton:
    @pytest.fixture(autouse=True)
    def _reset(self) -> None:
        reset_provider_rate_limiters()
        yield
        reset_provider_rate_limiters()

    def test_the_same_provider_returns_one_shared_limiter(self) -> None:
        """Process-wide by design: each worker builds its own router."""
        assert get_provider_rate_limiter("gemini") is get_provider_rate_limiter("gemini")

    def test_distinct_providers_get_distinct_budgets(self) -> None:
        assert get_provider_rate_limiter("gemini") is not get_provider_rate_limiter("groq")

    def test_provider_key_is_normalised(self) -> None:
        assert get_provider_rate_limiter("Gemini") is get_provider_rate_limiter(" gemini ")

    def test_default_rate_matches_the_era2_floor(self) -> None:
        assert DEFAULT_PROVIDER_RPM == 1000
        assert get_provider_rate_limiter("gemini").max_per_minute == DEFAULT_PROVIDER_RPM

    def test_environment_override_is_honoured(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("MACCRE_PROVIDER_RPM", "42")
        assert get_provider_rate_limiter("gemini").max_per_minute == 42

    def test_a_malformed_override_falls_back_to_the_default(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("MACCRE_PROVIDER_RPM", "not-a-number")
        assert get_provider_rate_limiter("gemini").max_per_minute == DEFAULT_PROVIDER_RPM

    def test_the_rate_cannot_be_redefined_mid_flight(self) -> None:
        first = get_provider_rate_limiter("gemini", max_per_minute=10)
        second = get_provider_rate_limiter("gemini", max_per_minute=9999)
        assert second is first
        assert second.max_per_minute == 10

    def test_concurrent_first_use_creates_only_one_limiter(self) -> None:
        seen: list[int] = []
        seen_lock = threading.Lock()
        start = threading.Barrier(8)

        def grab() -> None:
            start.wait(timeout=15)
            limiter = get_provider_rate_limiter("gemini")
            with seen_lock:
                seen.append(id(limiter))

        threads = [threading.Thread(target=grab, daemon=True) for _ in range(8)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=30)
        assert len(set(seen)) == 1, "a race produced more than one limiter"


class TestRouterIsGuarded:
    """The guard must sit on the one path every inference request takes."""

    def test_generate_acquires_a_slot(self) -> None:
        from maccre_core.maccre_router import UniversalRouter

        source = inspect.getsource(UniversalRouter.generate)
        assert "get_provider_rate_limiter()" in source
        assert ".acquire(" in source

    def test_the_guard_precedes_any_dispatch(self) -> None:
        """Acquire before routing, or the budget is spent after the fact."""
        from maccre_core.maccre_router import UniversalRouter

        source = inspect.getsource(UniversalRouter.generate)
        acquire_index = source.index("_rate_limiter.acquire(")
        # The temporal-awareness block is the first real work in the method.
        work_index = source.index("Anchor Temporal Awareness")
        assert acquire_index < work_index

    def test_failure_to_acquire_raises_rather_than_proceeding(self) -> None:
        from maccre_core.maccre_router import UniversalRouter

        source = inspect.getsource(UniversalRouter.generate)
        assert "raise RuntimeError(" in source
        assert "MACCRE_PROVIDER_RPM" in source, (
            "the error should tell the operator which knob to turn"
        )

    def test_the_wait_budget_is_bounded(self) -> None:
        from maccre_core import maccre_router

        assert maccre_router._RATE_LIMIT_WAIT_SECONDS > 0
        assert maccre_router._RATE_LIMIT_WAIT_SECONDS <= 600
