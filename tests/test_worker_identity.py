# ┌─────────────────────────────────────────────────────────────────────────────┐
# │  MACCREv2 Test Suite — Phase 6.12 Task A3: Per-Worker Identity               │
# └─────────────────────────────────────────────────────────────────────────────┘
"""
tests/test_worker_identity.py
=============================
Phase 6.12 Task A3 — each concurrent worker must be individually identifiable.

At the Aug 22 baseline the worker's identity was a single module-level constant,
``AGENT_ID = f"universal_node_{os.getpid()}"``. That was adequate while exactly one
worker ran per process. Phase 6.12 runs up to ``MAX_SCATTER_AGENTS`` workers as
threads inside one process, so all of them would have written the *same*
``locked_by`` value and used the *same* log prefix — leaving no way to attribute a
claim or a log line to the thread that produced it.

Identity now lives on the instance (``self.worker_id``), derived from a pool slot.

These tests deliberately avoid constructing ``UniversalSwarmWorker``: its
``__init__`` builds a router, a broker, a memory engine and a tool executor, which
means databases and credential lookups. The identity contract is tested through
``resolve_worker_id`` plus the broker's ``locked_by`` attribution, which is what
actually matters downstream.
"""
from __future__ import annotations

import inspect
import os
import re
import threading
from pathlib import Path
from typing import Any

import pytest

from maccre_core.orchestration.local_broker import LocalMessageBroker
from maccre_core.orchestration.swarm_worker import (
    PROCESS_WORKER_ID,
    UniversalSwarmWorker,
    resolve_worker_id,
)

JOB = "job_a3_test"


class FakeTopology:
    def get_node_config(self, node_id: str) -> dict[str, Any]:
        return {"wait_for": "none"}


@pytest.fixture()
def broker(tmp_path: Path) -> Any:
    b = LocalMessageBroker(db_path=str(tmp_path / "swarm_queue.db"))
    yield b
    b.close()


# ── Identity derivation ───────────────────────────────────────────────────────


class TestResolveWorkerId:
    def test_process_id_has_the_historical_format(self) -> None:
        assert PROCESS_WORKER_ID == f"universal_node_{os.getpid()}"

    def test_none_slot_preserves_the_pre_6_12_identity_exactly(self) -> None:
        """Backward compatibility is deliberate.

        Every existing construction site calls ``UniversalSwarmWorker()`` with no
        slot. Those workers must keep the old identity string so existing ledgers,
        telemetry rows and log greps continue to match.
        """
        assert resolve_worker_id(None) == PROCESS_WORKER_ID
        assert resolve_worker_id() == PROCESS_WORKER_ID

    def test_slots_produce_distinct_ids(self) -> None:
        ids = [resolve_worker_id(slot) for slot in range(8)]
        assert len(set(ids)) == 8

    def test_slot_id_format(self) -> None:
        assert resolve_worker_id(0) == f"{PROCESS_WORKER_ID}_t0"
        assert resolve_worker_id(7) == f"{PROCESS_WORKER_ID}_t7"

    def test_slot_ids_are_prefixed_by_the_process_id(self) -> None:
        """Lets telemetry group a process's workers without extra bookkeeping."""
        for slot in range(8):
            assert resolve_worker_id(slot).startswith(PROCESS_WORKER_ID)

    def test_id_shape_is_greppable(self) -> None:
        assert re.fullmatch(r"universal_node_\d+_t\d+", resolve_worker_id(3))
        assert re.fullmatch(r"universal_node_\d+", resolve_worker_id(None))

    def test_slot_zero_is_not_confused_with_no_slot(self) -> None:
        """``slot=0`` is falsy — a naive ``if slot:`` check would collapse it."""
        assert resolve_worker_id(0) != resolve_worker_id(None)


# ── Constructor contract ──────────────────────────────────────────────────────


class TestWorkerConstructorContract:
    """Checked by signature, not by instantiation (see module docstring)."""

    def test_accepts_an_optional_slot(self) -> None:
        params = inspect.signature(UniversalSwarmWorker.__init__).parameters
        assert "slot" in params
        assert params["slot"].default is None

    def test_existing_call_sites_stay_valid(self) -> None:
        """``UniversalSwarmWorker()`` must remain legal — 6 call sites rely on it."""
        sig = inspect.signature(UniversalSwarmWorker.__init__)
        sig.bind(object())  # raises TypeError if slot became required

    def test_slot_can_be_passed_positionally_or_by_name(self) -> None:
        sig = inspect.signature(UniversalSwarmWorker.__init__)
        sig.bind(object(), 3)
        sig.bind(object(), slot=3)

    def test_identity_is_not_a_module_global_any_more(self) -> None:
        """The regression guard for this whole task.

        If ``AGENT_ID`` reappears at module scope, some code path has gone back to
        a single process-wide identity and concurrent attribution is broken again.
        """
        import maccre_core.orchestration.swarm_worker as sw

        assert not hasattr(sw, "AGENT_ID"), (
            "module-level AGENT_ID is back — worker identity must be per-instance"
        )

    def test_execute_cycle_claims_with_the_instance_identity(self) -> None:
        """Cheap source assertion: the claim must not use a global."""
        source = inspect.getsource(UniversalSwarmWorker.execute_cycle)
        assert "fetch_and_lock_task(" in source
        claim_region = source.split("fetch_and_lock_task(", 1)[1][:120]
        assert "self.worker_id" in claim_region


# ── Downstream effect: locked_by attribution ──────────────────────────────────


class TestLockAttribution:
    """The point of per-slot identity: you can tell who holds what."""

    def test_distinct_slots_record_distinct_locked_by(
        self, broker: LocalMessageBroker
    ) -> None:
        broker.inject_task(job_id=JOB, payload_path="/p.md", starting_node="A, B")
        topo = FakeTopology()

        broker.fetch_and_lock_task(resolve_worker_id(0), topo)
        broker.fetch_and_lock_task(resolve_worker_id(1), topo)

        rows = dict(
            broker._get_conn()
            .execute(
                "SELECT current_node, locked_by FROM task_queue "
                "WHERE job_id = ? AND lock_status = 'locked'",
                (JOB,),
            )
            .fetchall()
        )
        assert rows == {"A": resolve_worker_id(0), "B": resolve_worker_id(1)}
        assert len(set(rows.values())) == 2

    def test_baseline_identity_would_have_been_indistinguishable(
        self, broker: LocalMessageBroker
    ) -> None:
        """Demonstrates the defect A3 fixes, so the fix cannot silently regress."""
        broker.inject_task(job_id=JOB, payload_path="/p.md", starting_node="A, B")
        topo = FakeTopology()

        # Simulate the old behaviour: every worker passes the same process id.
        broker.fetch_and_lock_task(PROCESS_WORKER_ID, topo)
        broker.fetch_and_lock_task(PROCESS_WORKER_ID, topo)

        holders = {
            r[0]
            for r in broker._get_conn().execute(
                "SELECT locked_by FROM task_queue WHERE job_id = ? "
                "AND lock_status = 'locked'",
                (JOB,),
            )
        }
        assert len(holders) == 1, "baseline: two workers, one indistinguishable identity"

    def test_eight_concurrent_slots_are_all_attributable(
        self, broker: LocalMessageBroker
    ) -> None:
        """Full 8-wide scatter shape: every claim traceable to exactly one slot."""
        nodes = [f"LANE_{i}" for i in range(8)]
        broker.inject_task(
            job_id=JOB, payload_path="/p.md", starting_node=", ".join(nodes)
        )
        topo = FakeTopology()
        start = threading.Barrier(8)

        def claim(slot: int) -> None:
            start.wait(timeout=10)
            broker.fetch_and_lock_task(resolve_worker_id(slot), topo)

        threads = [
            threading.Thread(target=claim, args=(i,), daemon=True) for i in range(8)
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=30)
            assert not t.is_alive()

        rows = broker._get_conn().execute(
            "SELECT current_node, locked_by FROM task_queue WHERE job_id = ? "
            "AND lock_status = 'locked'",
            (JOB,),
        ).fetchall()

        assert len(rows) == 8, "every lane should have been claimed exactly once"
        holders = [r[1] for r in rows]
        assert len(set(holders)) == 8, "each slot must hold exactly one lane"
        assert set(holders) == {resolve_worker_id(i) for i in range(8)}
