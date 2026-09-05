# ┌─────────────────────────────────────────────────────────────────────────────┐
# │  MACCREv2 ENGINEERING DOCTRINE                             Law Rev: 19.0   │
# ├─────────────────────────────────────────────────────────────────────────────┤
# │  VI.  ABSTRACTION All I/O behind abc.ABC before any concrete driver.       │
# └─────────────────────────────────────────────────────────────────────────────┘
"""
maccre_core/orchestration/broker_interface.py
=============================================
Phase 0A — Strangler Fig ABC for the Scatter-Gather Message Broker.

Defines the ``MessageBroker`` interface contract that ``LocalMessageBroker``
(SQLite) implements today.  Future backends (Redis, RabbitMQ, in-memory mock)
implement this same interface without touching any consumer code.
"""
from __future__ import annotations

import abc
from typing import Any


class MessageBroker(abc.ABC):
    """Abstract interface for the MACCREv2 Scatter-Gather task broker.

    All swarm orchestration components (SwarmWorker, FlowRunner, admin_tools)
    MUST type-hint against this ABC, never against a concrete driver.
    """

    # ── Task Lifecycle ────────────────────────────────────────────────────────

    @abc.abstractmethod
    def fetch_and_lock_task(
        self,
        agent_id: str,
        topology_engine: Any,
    ) -> dict[str, Any] | None:
        """Atomically claim the oldest open task whose Gather Gate deps are met.

        Returns:
            A dict representing the task row, or ``None`` if no work is available.
        """

    @abc.abstractmethod
    def count_ready_tasks(
        self,
        job_id: str,
        topology_engine: Any = None,
        cap: int = 0,
    ) -> int:
        """Estimate how many open tasks are currently claimable for a job.

        Read-only **sizing hint** for the worker pool: it answers "roughly how
        much parallel work is available right now?" so the pool knows how many
        threads to spawn. It applies the same Gather Gate rules as
        :meth:`fetch_and_lock_task` but takes no locks and mutates nothing.

        This is deliberately *not* authoritative. Between this call and a
        worker's claim, another worker may take the task. The atomic claim
        inside :meth:`fetch_and_lock_task` remains the sole correctness
        authority; over-counting here costs at most a thread that finds no work
        and retires.

        Args:
            job_id: Job to size. Other jobs' tasks are ignored.
            topology_engine: Provider used to resolve each node's ``wait_for``.
                When ``None``, every open task counts as ready.
            cap: Stop counting once this many ready tasks are found. ``0`` or
                negative means count them all. Lets callers avoid scanning a
                large queue when they only care about the first N.

        Returns:
            Number of ready tasks, never more than ``cap`` when ``cap > 0``.
        """

    @abc.abstractmethod
    def route_task(
        self,
        row_id: int,
        job_id: str,
        next_node_str: str,
        new_payload_path: str,
        actual_cost: float = 0.0,
        source_payload_path: str = "",
        max_recursion: int = 3,
        status: str = "completed",
        flow_line_id: str = "",
        flow_vector: str = "",
        tether_id: str = "",
        output_path: str = "",
        payload_bytes: int = 0,
    ) -> None:
        """Mark a task completed and enqueue successor node(s).

        Args:
            row_id: Primary key of the completed task.
            job_id: Job identifier for provenance tracking.
            next_node_str: Pipe-separated successor node IDs (e.g. ``"NODE_A|NODE_B"``).
            new_payload_path: Path the **successor** should read. Not necessarily
                what the completed node produced — see ``output_path``.
            actual_cost: API cost incurred for this node execution.
            source_payload_path: Original user payload path (propagated unchanged).
            max_recursion: Maximum allowed visits to the same node before FAILED routing.
            status: Terminal status to write for the completed row.
            flow_line_id: Flow line identifier for scatter fan-out lineage tracking.
            flow_vector: Colon-delimited history of nodes traversed (telemetry lineage).
            tether_id: Scatter scope identifier. Isolates fan-in artifact gathering
                so lanes of one scatter do not gather across lanes of another.
            output_path: What the completed node itself **produced**, recorded
                separately from ``new_payload_path`` because the two diverge.
                Under ``Payload_Mode = "Unified Ledger"`` the successor reads the
                shared session ledger, so a single column serving both roles left
                every scatter lane claiming to have produced that one file — and a
                fan-in gathering "what each predecessor produced" got the same path
                N times. Implementations **must not** blank an existing value when
                this is empty: absent is honest, overwritten is lost.
            payload_bytes: Size in bytes of the payload the completed node **read**,
                measured before it executed. ``0`` means *not measured* — an
                unreadable path and a genuinely empty file both land there — so
                implementations **must not** overwrite a non-zero value with ``0``,
                for the same reason as ``output_path``: a later caller that did not
                measure must not erase a measurement an earlier one took.
        """

    @abc.abstractmethod
    def release_task(self, row_id: int) -> None:
        """Return a locked task to 'open' state so another worker can claim it."""

    @abc.abstractmethod
    def heartbeat_task(self, row_id: int) -> bool:
        """Refresh a held lock's ``locked_at``, proving the worker is still alive.

        Without this, lock age cannot distinguish a *slow* node from a *dead*
        one. A single LLM call can run for tens of seconds, so any reclaim
        timeout short enough to recover a crashed worker promptly is also short
        enough to steal a task from a healthy one. The heartbeat separates the
        two: a lock only goes stale when nothing is refreshing it.

        Implementations **must** scope the write to rows that are still locked.
        An unscoped update would resurrect the lock timestamp on a row that had
        already completed, if a heartbeat raced the completing write.

        Args:
            row_id: ``task_queue`` row whose lock should be refreshed.

        Returns:
            True if a locked row was refreshed. False means the row is no longer
            locked — it completed, was released, or was reclaimed — which is the
            caller's signal to stop heartbeating.
        """

    @abc.abstractmethod
    def pause_task(self, row_id: int) -> None:
        """Set a task to 'paused' state — worker will skip it until manual resume."""

    # ── Interrupt / Injection ─────────────────────────────────────────────────

    @abc.abstractmethod
    def update_session_ledger(self, job_id: str, ledger_path: str) -> None:
        """Update the current ledger path for a running session."""

    @abc.abstractmethod
    def update_session_step_index(self, job_id: str, step_index: int) -> None:
        """Update the current topology step index for a running session."""

    @abc.abstractmethod
    def inject_interrupt(self, job_id: str, override_text: str) -> None:
        """Push an urgent priority override into the running swarm."""

    @abc.abstractmethod
    def consume_pending_interrupts(self, job_id: str) -> list[str]:
        """Drain all pending interrupt texts for the given job.

        Returns:
            List of override text strings (empty if none pending).
        """

    @abc.abstractmethod
    def inject_task(
        self,
        job_id: str,
        payload_path: str,
        starting_node: str,
    ) -> None:
        """Enqueue a brand-new job at the given starting node(s).

        Args:
            job_id: Unique job identifier.
            payload_path: Path to the input payload document.
            starting_node: Comma-separated starting node ID(s).
        """

    # ── Telemetry ─────────────────────────────────────────────────────────────

    @abc.abstractmethod
    def broadcast_topology_event(self, event_type: str, payload: dict[str, str]) -> None:
        """Broadcast a topology lifecycle event (no-op when event bus is dormant)."""
