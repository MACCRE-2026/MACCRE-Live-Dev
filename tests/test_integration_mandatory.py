# ┌─────────────────────────────────────────────────────────────────────────────┐
# │  MACCREv2 Test Suite — Phase 6.12 Task D1: Mandatory Integration Tests       │
# └─────────────────────────────────────────────────────────────────────────────┘
"""
tests/test_integration_mandatory.py
===================================
The three integration tests ``orchestration_oracle_principles.md`` requires after
**any** ``flow_engine.py`` or ``swarm_*.py`` modification:

1. **Multi-step flow** (minimum 3 steps) — the step loop must not break early and
   the payload must pass between steps.
2. **CTRL_REVIEW flow** — ``pause_event`` handling and HITL integration.
3. **CTRL_SCATTER flow** — lane execution, gather synchronisation, concurrent
   worker management.

The doctrine describes running these by hand in the TUI. Automating them is the
point: the Phase 6.12 rollback happened because "all checks pass" meant lint and
types while the test suite could not even be collected, so nobody noticed that
flows terminated after one node.

These drive the **real** ``FlowRunner.execute_flow`` against a throwaway
datacenter — real broker, real SQLite queue, real topology CSV, real
``DynamicSwarmPool``, real routing and real ledger generation. Steps use ``CTRL_``
nodes, which are deterministic handlers rather than agents, so there is no LLM
call, no API key and no cost, and the results are exactly reproducible.

Scatter concurrency is proven in depth by ``tests/test_scatter_concurrency.py``
(barrier-based width proof at 4 and 8 lanes). Requirement 3 here covers the
scatter DAG travelling through ``execute_flow``, so that one command runs all
three mandated checks.
"""
from __future__ import annotations

import sqlite3
import threading
import time
from pathlib import Path
from typing import Any

import pytest

from maccre_core.orchestration.flow_engine import FlowRunner, FlowStep
from maccre_core.orchestration.local_broker import LocalMessageBroker
from maccre_core.utils.path_resolver import get_datacenter_path


@pytest.fixture()
def runner() -> FlowRunner:
    """A real FlowRunner against the per-test tmp datacenter from conftest."""
    return FlowRunner(project_name="TEST_PROJECT")


@pytest.fixture()
def seed_payload() -> str:
    """An initial payload document on disk."""
    path = get_datacenter_path("01_Raw_Source", "d1_seed.md")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("# Seed\n\nD1 integration seed payload.\n", encoding="utf-8")
    return str(path)


class FlowRecorder:
    """Collects every callback the engine emits during a run."""

    def __init__(self) -> None:
        self.job_ids: list[str] = []
        self.steps_completed: list[tuple[int, str]] = []
        self.nodes_started: list[tuple[Any, str, Any]] = []
        self.nodes_finished: list[tuple[Any, str, Any]] = []
        self.hitl_pauses: list[tuple[int, str, str]] = []
        self._lock = threading.Lock()

    # Engine-facing callbacks ------------------------------------------------

    def on_job_started(self, job_id: str) -> None:
        self.job_ids.append(job_id)

    def on_step_complete(self, step_index: int, output_path: str) -> None:
        self.steps_completed.append((step_index, output_path))

    def on_node_active(self, step_index: Any, node_id: str, slot: Any) -> None:
        with self._lock:
            self.nodes_started.append((step_index, node_id, slot))

    def on_node_finished(self, step_index: Any, node_id: str, slot: Any) -> None:
        with self._lock:
            self.nodes_finished.append((step_index, node_id, slot))

    # Convenience ------------------------------------------------------------

    @property
    def job_id(self) -> str:
        assert self.job_ids, "job_started_callback never fired"
        return self.job_ids[0]

    def started_nodes(self) -> list[str]:
        return [n for _, n, _ in self.nodes_started]

    def finished_nodes(self) -> list[str]:
        return [n for _, n, _ in self.nodes_finished]


def queue_rows(job_id: str) -> list[tuple[str, str]]:
    """``(current_node, lock_status)`` for every task row of *job_id*."""
    db_path = str(get_datacenter_path("swarm_queue.db"))
    with sqlite3.connect(db_path) as conn:
        return [
            (str(r[0]), str(r[1]))
            for r in conn.execute(
                "SELECT current_node, lock_status FROM task_queue WHERE job_id = ? "
                "ORDER BY id",
                (job_id,),
            )
        ]


def ledger_files(job_id: str) -> list[str]:
    """Names of the per-node markdown ledgers written for *job_id*."""
    ledger_dir = get_datacenter_path("03_Agent_Ledgers", job_id)
    if not ledger_dir.exists():
        return []
    return sorted(p.name for p in ledger_dir.glob("*.md"))


# ── Requirement 1: multi-step flow ────────────────────────────────────────────


class TestMandatoryMultiStepFlow:
    """Minimum three steps. Verifies the step loop and payload hand-off.

    This is the regression the rollback was about: the flow reported success after
    executing a single node.
    """

    STEPS = 3

    @pytest.fixture()
    def result(
        self, runner: FlowRunner, seed_payload: str
    ) -> tuple[str, FlowRecorder]:
        rec = FlowRecorder()
        steps = [FlowStep(macronode_name="CTRL_ANCHOR") for _ in range(self.STEPS)]
        final = runner.execute_flow(
            steps,
            initial_payload_path=seed_payload,
            job_started_callback=rec.on_job_started,
            step_callback=rec.on_step_complete,
            node_active_callback=rec.on_node_active,
            node_finished_callback=rec.on_node_finished,
        )
        return final, rec

    def test_all_three_steps_execute(
        self, result: tuple[str, FlowRecorder]
    ) -> None:
        """The step loop must not break early."""
        _final, rec = result
        assert rec.started_nodes() == [
            "CTRL_ANCHOR_S0",
            "CTRL_ANCHOR_S1",
            "CTRL_ANCHOR_S2",
        ]

    def test_every_started_node_also_finished(
        self, result: tuple[str, FlowRecorder]
    ) -> None:
        """Start/finish pairing — an unpaired start leaves a node lit forever."""
        _final, rec = result
        assert sorted(rec.finished_nodes()) == sorted(rec.started_nodes())

    def test_steps_run_in_order(self, result: tuple[str, FlowRecorder]) -> None:
        _final, rec = result
        assert [s for s, _, _ in rec.nodes_started] == [0, 1, 2]

    def test_step_callback_fires_once_per_step(
        self, result: tuple[str, FlowRecorder]
    ) -> None:
        _final, rec = result
        assert [idx for idx, _ in rec.steps_completed] == [0, 1, 2]

    def test_payload_passes_between_steps(
        self, result: tuple[str, FlowRecorder]
    ) -> None:
        """Each step's recorded output must be a real artifact on disk.

        A step that produced nothing, or that handed the next step a path that does
        not exist, is the silent-truncation failure mode.
        """
        _final, rec = result
        assert len(rec.steps_completed) == 3
        for idx, output_path in rec.steps_completed:
            assert output_path, f"step {idx} reported an empty payload path"
            assert Path(output_path).exists(), (
                f"step {idx} payload {output_path} does not exist"
            )

    def test_each_step_wrote_a_node_ledger(
        self, result: tuple[str, FlowRecorder]
    ) -> None:
        _final, rec = result
        names = ledger_files(rec.job_id)
        for suffix in ("S0", "S1", "S2"):
            assert any(f"CTRL_ANCHOR_{suffix}" in n for n in names), (
                f"no ledger for step {suffix}; got {names}"
            )

    def test_final_artifact_is_the_unified_ledger(
        self, result: tuple[str, FlowRecorder]
    ) -> None:
        final, _rec = result
        assert final, "execute_flow returned no artifact path"
        assert Path(final).exists()
        assert Path(final).name == "unified_session_ledger.md"
        assert Path(final).read_text(encoding="utf-8").strip()

    def test_queue_is_fully_drained(
        self, result: tuple[str, FlowRecorder]
    ) -> None:
        """Nothing may be left open, locked or paused."""
        _final, rec = result
        leftover = [
            row for row in queue_rows(rec.job_id)
            if row[1] in ("open", "locked", "paused")
        ]
        assert leftover == [], f"queue not drained: {leftover}"

    def test_linear_flow_stays_single_threaded(
        self, result: tuple[str, FlowRecorder]
    ) -> None:
        """A linear flow must not open a thread per step."""
        _final, rec = result
        slots = {slot for _, _, slot in rec.nodes_started}
        assert slots == {0}, f"linear flow used slots {slots}"


# ── Requirement 2: CTRL_REVIEW pause / resume ─────────────────────────────────


class TestMandatoryReviewFlow:
    """Agent -> CTRL_REVIEW -> Agent, the Phase 4.99 certification shape.

    Reproduces the verified Aug 29 baseline trace recorded in
    ``.oracle_artifacts/2026-08-29_phase_6_12_ctrl_review_baseline.md``, with
    ``CTRL_ANCHOR`` standing in for the two agent steps so no LLM is needed. What
    matters is the control flow: step 0 runs, the review node pauses the queue, the
    HITL callback fires, an injection resumes it, and step 2 still runs.
    """

    @pytest.fixture()
    def result(
        self, runner: FlowRunner, seed_payload: str
    ) -> tuple[str, FlowRecorder, list[str]]:
        rec = FlowRecorder()
        pause_event = threading.Event()
        pause_event.set()  # set == running, matching the TUI contract
        resumed: list[str] = []

        injection = get_datacenter_path("01_Raw_Source", "d1_hitl_injection.md")
        injection.parent.mkdir(parents=True, exist_ok=True)
        injection.write_text(
            "# HITL\n\nOperator-supplied context.\n", encoding="utf-8"
        )

        def on_hitl(step_index: int, job_id: str, payload: str) -> None:
            """Simulate the operator, the way the TUI actually does it.

            Resuming has to happen on **another thread**: the engine clears
            ``pause_event`` immediately after this callback returns, so a
            synchronous set here would be wiped and the flow would wait forever.
            The real TUI has the same shape — the callback opens a modal and the
            resume arrives later.
            """
            rec.hitl_pauses.append((step_index, job_id, payload))

            def resume_later() -> None:
                time.sleep(0.4)
                broker = LocalMessageBroker()
                try:
                    if broker.resume_paused_task(job_id, str(injection)):
                        resumed.append(job_id)
                finally:
                    broker.close()
                pause_event.set()

            threading.Thread(target=resume_later, daemon=True).start()

        steps = [
            FlowStep(macronode_name="CTRL_ANCHOR"),
            FlowStep(macronode_name="CTRL_REVIEW"),
            FlowStep(macronode_name="CTRL_ANCHOR"),
        ]
        final = runner.execute_flow(
            steps,
            initial_payload_path=seed_payload,
            pause_event=pause_event,
            job_started_callback=rec.on_job_started,
            step_callback=rec.on_step_complete,
            hitl_callback=on_hitl,
            node_active_callback=rec.on_node_active,
            node_finished_callback=rec.on_node_finished,
        )
        return final, rec, resumed

    def test_review_node_resolves_to_the_pause_primitive(
        self, result: tuple[str, FlowRecorder, list[str]]
    ) -> None:
        """The load-bearing rename from Task A8.

        ``CTRL_REVIEW`` is not a ``DeterministicNodeType``; it must reach the
        runtime as ``CTRL_PAUSE_MANUAL`` or it silently becomes a passthrough.
        """
        _final, rec, _resumed = result
        assert "CTRL_PAUSE_MANUAL_S1" in rec.started_nodes()

    def test_hitl_callback_fires(
        self, result: tuple[str, FlowRecorder, list[str]]
    ) -> None:
        """pause_event handling: the engine must surface the pause, not skip it."""
        _final, rec, _resumed = result
        assert len(rec.hitl_pauses) >= 1, "the flow never paused for review"
        assert rec.hitl_pauses[0][0] == 1, "pause reported against the wrong step"

    def test_the_paused_task_was_resumed(
        self, result: tuple[str, FlowRecorder, list[str]]
    ) -> None:
        _final, rec, resumed = result
        assert resumed, "resume_paused_task found nothing paused"

    def test_the_step_after_review_still_runs(
        self, result: tuple[str, FlowRecorder, list[str]]
    ) -> None:
        """The regression that forced the rollback: flows died at the review node."""
        _final, rec, _resumed = result
        assert "CTRL_ANCHOR_S2" in rec.started_nodes(), (
            f"flow terminated at the review node; ran {rec.started_nodes()}"
        )

    def test_the_recorded_baseline_trace_is_reproduced(
        self, result: tuple[str, FlowRecorder, list[str]]
    ) -> None:
        """S0 -> CTRL_PAUSE_MANUAL_S1 -> S2, in that order."""
        _final, rec, _resumed = result
        assert rec.started_nodes() == [
            "CTRL_ANCHOR_S0",
            "CTRL_PAUSE_MANUAL_S1",
            "CTRL_ANCHOR_S2",
        ]

    def test_the_pause_node_wrote_its_ledger(
        self, result: tuple[str, FlowRecorder, list[str]]
    ) -> None:
        """The baseline recorded a CTRL_PAUSE_MANUAL_S1 artifact."""
        _final, rec, _resumed = result
        names = ledger_files(rec.job_id)
        assert any("CTRL_PAUSE_MANUAL_S1" in n for n in names), names

    def test_nothing_is_left_paused(
        self, result: tuple[str, FlowRecorder, list[str]]
    ) -> None:
        _final, rec, _resumed = result
        still_paused = [r for r in queue_rows(rec.job_id) if r[1] == "paused"]
        assert still_paused == [], f"tasks left paused: {still_paused}"

    def test_the_flow_produced_a_final_artifact(
        self, result: tuple[str, FlowRecorder, list[str]]
    ) -> None:
        final, _rec, _resumed = result
        assert final and Path(final).exists()


# ── Requirement 3: CTRL_SCATTER through the flow engine ───────────────────────


class TestMandatoryScatterFlow:
    """Scatter DAG driven through ``execute_flow``.

    Depth of concurrency proof lives in ``tests/test_scatter_concurrency.py``,
    which pins width at 4 and 8 lanes with a barrier. This covers the same DAG
    arriving via the public entry point, so one command satisfies all three
    mandated checks.
    """

    @pytest.fixture()
    def result(
        self, runner: FlowRunner, seed_payload: str
    ) -> tuple[str, FlowRecorder]:
        rec = FlowRecorder()
        steps = [
            FlowStep(macronode_name="CTRL_ANCHOR"),
            FlowStep(macronode_name="CTRL_SCATTER"),
            FlowStep(macronode_name="CTRL_MERGE"),
        ]
        final = runner.execute_flow(
            steps,
            initial_payload_path=seed_payload,
            job_started_callback=rec.on_job_started,
            step_callback=rec.on_step_complete,
            node_active_callback=rec.on_node_active,
            node_finished_callback=rec.on_node_finished,
        )
        return final, rec

    def test_the_scatter_dag_completes(
        self, result: tuple[str, FlowRecorder]
    ) -> None:
        final, _rec = result
        assert final and Path(final).exists()

    def test_scatter_and_merge_both_execute(
        self, result: tuple[str, FlowRecorder]
    ) -> None:
        """Gather synchronisation: the merge node must be reached."""
        _final, rec = result
        started = rec.started_nodes()
        assert "CTRL_SCATTER_S1" in started, started
        assert "CTRL_MERGE_S2" in started, started

    def test_merge_runs_after_scatter(
        self, result: tuple[str, FlowRecorder]
    ) -> None:
        _final, rec = result
        started = rec.started_nodes()
        assert started.index("CTRL_SCATTER_S1") < started.index("CTRL_MERGE_S2")

    def test_every_node_finished(self, result: tuple[str, FlowRecorder]) -> None:
        _final, rec = result
        assert sorted(rec.finished_nodes()) == sorted(rec.started_nodes())

    def test_queue_is_fully_drained(
        self, result: tuple[str, FlowRecorder]
    ) -> None:
        _final, rec = result
        leftover = [
            row for row in queue_rows(rec.job_id)
            if row[1] in ("open", "locked", "paused")
        ]
        assert leftover == [], f"queue not drained: {leftover}"


# ── Preflight must not reject control-node flows ──────────────────────────────


class TestPreflightAcceptsControlNodes:
    """Regression guard for a defect Task A8 exposed.

    ``TopologyEngine.validate`` demanded a system prompt and a model of every
    node. A ``CTRL_*`` node has ``Agent_Name=SYSTEM``, no persona and
    ``Model_Override=none`` **by design** — it runs a handler in
    ``deterministic_nodes.py`` and never reaches an LLM — so it collected two
    spurious ERRORs.

    This was masked for review nodes, which preflight used to skip outright. A8
    removed that bypass, which turned the latent rule into a **hard block on
    launch**: ``nexus_plex`` gates on ``report.is_ok`` and forces a
    "Proceed Anyway" click. That would have blocked the Phase 4.99 certification
    flow.
    """

    def test_a_review_flow_passes_preflight(self, runner: FlowRunner) -> None:
        report = runner.preflight_check([FlowStep(macronode_name="CTRL_REVIEW")])
        errors = [i for i in report.issues if i["severity"] == "ERROR"]
        assert errors == [], f"review step rejected by preflight: {errors}"
        assert report.is_ok is True

    def test_a_three_step_control_flow_passes_preflight(
        self, runner: FlowRunner
    ) -> None:
        steps = [FlowStep(macronode_name="CTRL_ANCHOR") for _ in range(3)]
        report = runner.preflight_check(steps)
        assert report.is_ok is True, [i["detail"] for i in report.issues]

    def test_the_certification_shape_passes_preflight(
        self, runner: FlowRunner
    ) -> None:
        """Agent -> CTRL_REVIEW -> Agent, with control nodes standing in."""
        steps = [
            FlowStep(macronode_name="CTRL_ANCHOR"),
            FlowStep(macronode_name="CTRL_REVIEW"),
            FlowStep(macronode_name="CTRL_ANCHOR"),
        ]
        report = runner.preflight_check(steps)
        assert report.is_ok is True, [i["detail"] for i in report.issues]

    def test_control_nodes_are_still_dag_validated(self, runner: FlowRunner) -> None:
        """The exemption is scoped to the agent-shaped rules only.

        DAG integrity still applies, and matters more now that A8 made a control
        node's ``next_node`` configurable — a review step pointing at a node that
        does not exist must still be caught.
        """
        import inspect

        from maccre_core.orchestration.topology_engine import TopologyEngine

        source = inspect.getsource(TopologyEngine.validate)
        assert "is_control_node" in source
        # Scoped, not a blanket skip of the whole loop body.
        assert "if is_deterministic_node(node_id):\n                continue" not in source
