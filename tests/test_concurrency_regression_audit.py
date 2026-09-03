# ┌─────────────────────────────────────────────────────────────────────────────┐
# │  MACCREv2 Test Suite — Phase 6.12 Task D2: Concurrency Regression Audit      │
# └─────────────────────────────────────────────────────────────────────────────┘
"""
tests/test_concurrency_regression_audit.py
==========================================
Phase 6.12 Task D2 — every concurrency fix must have a test that goes red if the
fix is reverted.

This file is an **audit**, not a second copy of the suite. The bulk of the
protection already exists in the per-task files; duplicating it would create two
places to maintain one guarantee. What lives here is (a) the audit matrix, written
down so the coverage claim is checkable rather than asserted, and (b) the handful
of gaps the audit actually found.

Audit matrix
------------

======  ===================================================  ==========================================
Task    Fix                                                  Test that fails if reverted
======  ===================================================  ==========================================
A2      Thread-local SQLite connections                      ``test_broker_contract`` —
                                                             ``test_each_thread_gets_its_own_connection``,
                                                             ``test_concurrent_claims_never_hand_out_the_same_task``
A2      No mid-scan ``commit()`` in the exclusive claim       ``test_broker_contract`` —
                                                             ``test_cancels_upstream_failed_task_and_still_claims_in_one_call``
A2      ``count_ready_tasks`` mirrors the Gather Gate         ``test_broker_contract`` —
                                                             ``test_estimate_agrees_with_what_claiming_actually_yields``
A3      Per-slot worker identity                             ``test_worker_identity`` —
                                                             ``test_identity_is_not_a_module_global_any_more``,
                                                             ``test_distinct_slots_record_distinct_locked_by``
A4      One log sink per thread (no double-open)              ``test_concurrency_primitives`` —
                                                             ``test_single_handle_per_thread_so_stderr_cannot_truncate_stdout``
A4      Per-thread routing, not a global swap                 ``test_concurrency_primitives`` —
                                                             ``test_concurrent_threads_get_isolated_logs``
                                                             **plus the gap-fillers below**
A5      ``CycleOutcome`` distinguishes WORKED from IDLE       ``test_cycle_outcome`` —
                                                             ``test_did_work_is_true_only_for_worked``
A5      Worker never mutates a received Event                ``test_cycle_outcome`` —
                                                             ``TestEventObserverDiscipline``
A5      start/finish callbacks are paired                    ``test_cycle_outcome`` —
                                                             ``test_start_is_fired_inside_the_try_so_finish_always_pairs``
A6      Ledger generation serialised per job                  ``test_ledger_concurrency`` —
                                                             ``test_concurrent_generation_is_serialised``
A6      Ledger written atomically                            ``test_ledger_concurrency`` —
                                                             ``test_concurrent_generation_never_yields_a_torn_read``
A7      Context-cache dedupe + no lost registry entries       ``test_shared_state_hazards`` —
                                                             ``test_concurrent_identical_payloads_upload_once``,
                                                             ``test_concurrent_distinct_payloads_never_lose_a_registry_entry``
A7      Idempotent session loggers                           ``test_shared_state_hazards`` —
                                                             ``test_repeat_call_for_same_session_does_not_churn_handlers``
A8      Review resolves to the pause primitive               ``test_review_node_resolution``,
                                                             ``test_integration_mandatory``
B1      Pool never mutates a caller's Event                  ``test_swarm_pool`` —
                                                             ``TestEventObserverDiscipline``
B1      Drain waits for in-flight nodes                      ``test_swarm_pool`` —
                                                             ``test_does_not_return_while_a_node_is_still_in_flight``
B2      Sticky topology overlays survive a TTL reload         ``test_flow_pool_integration`` —
                                                             ``test_overlay_survives_a_ttl_reload``
B3      Scaling reaches full scatter width                   ``test_scatter_concurrency`` —
                                                             the barrier width proofs
B3      Demand estimation is throttled                       ``test_scatter_concurrency`` —
                                                             ``test_eight_lane_scatter_beats_sequential_wall_clock``
D1      Stale estimates never scale the pool                 ``test_integration_mandatory`` —
                                                             ``test_linear_flow_stays_single_threaded``
D1      Preflight accepts control nodes                      ``test_integration_mandatory`` —
                                                             ``TestPreflightAcceptsControlNodes``
======  ===================================================  ==========================================

Gaps the audit found
--------------------
A4's *integration* into ``swarm_worker`` was unguarded. The primitive was well
covered, but nothing asserted that the worker actually uses it, tears it down on
every exit path, or has not quietly gone back to reassigning ``sys.stdout``. Those
are filled below.
"""
from __future__ import annotations

import inspect
from pathlib import Path

import pytest

from maccre_core.orchestration.local_broker import LocalMessageBroker
from maccre_core.orchestration.swarm_worker import UniversalSwarmWorker

REPO_ROOT = Path(__file__).resolve().parent.parent


def _executable_lines(source: str) -> str:
    """Source with comment-only lines removed.

    Every guard here has to ignore comments, because the comments deliberately
    describe the very patterns being banned.
    """
    return "\n".join(
        line for line in source.splitlines() if not line.lstrip().startswith("#")
    )


# ── Gap: A4's integration into the worker ─────────────────────────────────────


class TestWorkerUsesThreadRouting:
    """The worker must use the per-thread tee, and must not swap global streams."""

    @pytest.fixture()
    def cycle_source(self) -> str:
        return inspect.getsource(UniversalSwarmWorker.execute_cycle)

    def test_the_worker_starts_a_thread_tee(self, cycle_source: str) -> None:
        assert "begin_thread_tee(agent_log_path)" in _executable_lines(cycle_source)

    def test_the_worker_tears_the_tee_down_in_a_finally(
        self, cycle_source: str
    ) -> None:
        """Must be in the ``finally``, not on the happy path.

        ``execute_cycle`` has several early returns — a pause, a deterministic
        completion, two dialogue manual-intercepts — plus the FAILED route and the
        exception path. A teardown anywhere else leaks the log handle and leaves
        the thread's output routed at a closed file.
        """
        executable = _executable_lines(cycle_source)
        assert "end_thread_tee()" in executable

        finally_index = executable.index("\n        finally:")
        teardown_index = executable.index("end_thread_tee()")
        assert teardown_index > finally_index, (
            "end_thread_tee() must run in the method's finally block"
        )

    def test_the_tee_is_torn_down_exactly_once(self, cycle_source: str) -> None:
        """Four redundant inline restores were removed in A4.

        They duplicated the ``finally`` and, worse, restored a *stale* snapshot of
        the process-wide streams.
        """
        executable = _executable_lines(cycle_source)
        assert executable.count("end_thread_tee()") == 1

    def test_the_global_stream_swap_has_not_returned(self, cycle_source: str) -> None:
        """The defect A4 removed.

        ``sys.stdout`` is process-wide. Two concurrent nodes each installing their
        own tee means the second overwrites the first, and both nodes' output lands
        in whichever log won the race while the loser's stays empty. It is also the
        whole logging path, because ``DynamicStreamHandler.emit()`` re-reads
        ``sys.stdout`` on every record and ``swarm_worker`` has no bare ``print``.
        """
        executable = _executable_lines(cycle_source)
        for banned in ("sys.stdout =", "sys.stderr =", "_FileTee("):
            assert banned not in executable, f"global stream swap is back: {banned}"

    def test_the_dead_tee_class_is_gone(self) -> None:
        source = (
            REPO_ROOT / "maccre_core" / "orchestration" / "swarm_worker.py"
        ).read_text(encoding="utf-8")
        assert "class _FileTee" not in source


# ── Gap: the broker must not go back to a shared connection ───────────────────


class TestBrokerConnectionDiscipline:
    """Measured defect: a shared connection handed the same task to two workers.

    12 tasks produced 15 claims, and three threads died with "cannot start a
    transaction within a transaction". ``BEGIN EXCLUSIVE`` cannot isolate anything
    when two threads share one connection, because a connection holds at most one
    transaction.
    """

    def test_connections_are_not_shared_across_threads(self) -> None:
        source = _executable_lines(inspect.getsource(LocalMessageBroker._get_conn))
        assert "check_same_thread=False" not in source, (
            "a cross-thread connection is back; BEGIN EXCLUSIVE stops isolating"
        )
        assert "self._local" in source, "connections are no longer thread-local"

    def test_row_factory_is_not_reassigned_per_query(self) -> None:
        """Mutating a live connection's ``row_factory`` is a cross-thread effect.

        One thread's SELECT would change the row type another thread receives
        mid-flight. It is set once at creation instead.
        """
        source = (
            REPO_ROOT / "maccre_core" / "orchestration" / "local_broker.py"
        ).read_text(encoding="utf-8")
        assignments = [
            line.strip()
            for line in source.splitlines()
            if "row_factory" in line
            and "=" in line
            and not line.lstrip().startswith("#")
        ]
        assert len(assignments) == 1, (
            f"row_factory should be assigned exactly once, found: {assignments}"
        )

    def test_the_claim_holds_one_transaction_end_to_end(self) -> None:
        """No ``commit()`` may run mid-scan.

        Committing after cancelling an upstream-failed task ended the exclusive
        transaction while the loop kept iterating, so the later claim ``UPDATE``
        ran unprotected and the TOCTOU race returned.
        """
        source = _executable_lines(
            inspect.getsource(LocalMessageBroker.fetch_and_lock_task)
        )
        begin_index = source.index('BEGIN EXCLUSIVE')
        cancel_index = source.index("lock_status = 'cancelled'")
        # The cancellation must be followed by `continue`, not a commit.
        after_cancel = source[cancel_index : cancel_index + 400]
        assert "continue" in after_cancel
        assert "conn.commit()" not in source[begin_index:cancel_index], (
            "a commit runs before the cancellation branch, inside the scan"
        )


# ── The suite itself must not quietly shrink ──────────────────────────────────


class TestRegressionSuiteIsPresent:
    """Each concurrency fix's guard file must exist.

    The rollback's root failure was that a single broken test module aborted
    collection repo-wide, so **zero** tests ran while three real defects sat in the
    tree. A missing guard file is the same class of silent loss.
    """

    GUARD_FILES = [
        "test_broker_contract.py",
        "test_concurrency_primitives.py",
        "test_ctrl_review_baseline.py",
        "test_cycle_outcome.py",
        "test_flow_pool_integration.py",
        "test_integration_mandatory.py",
        "test_ledger_concurrency.py",
        "test_review_node_resolution.py",
        "test_scatter_concurrency.py",
        "test_shared_state_hazards.py",
        "test_swarm_pool.py",
        "test_topology_visualizer_multi_active.py",
        "test_worker_identity.py",
    ]

    @pytest.mark.parametrize("filename", GUARD_FILES)
    def test_guard_file_exists(self, filename: str) -> None:
        assert (REPO_ROOT / "tests" / filename).is_file(), (
            f"{filename} is missing — a concurrency fix has lost its guard"
        )

    def test_no_guard_file_is_empty(self) -> None:
        for filename in self.GUARD_FILES:
            path = REPO_ROOT / "tests" / filename
            assert path.stat().st_size > 500, f"{filename} looks gutted"

    def test_the_aborted_attempt_stays_quarantined(self) -> None:
        """``_archive`` is excluded from ruff and pyright.

        The never-executed first attempt at this phase must not drift back into the
        live tree, where an import could resolve to code that has never run.
        """
        archive = REPO_ROOT / "_archive" / "phase_6_12_aborted"
        assert archive.is_dir()
        for orphan in ("concurrency.py", "swarm_pool.py"):
            assert (archive / orphan).is_file(), f"{orphan} left the archive"

    def test_the_live_modules_are_the_rewritten_ones(self) -> None:
        """Sanity: the live files are the greenfield rewrites, not the archived pair."""
        live = REPO_ROOT / "maccre_core" / "orchestration"
        for name in ("concurrency.py", "swarm_pool.py"):
            source = (live / name).read_text(encoding="utf-8")
            assert "Phase 6.12" in source
