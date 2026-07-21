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
    ) -> None:
        """Mark a task completed and enqueue successor node(s).

        Args:
            row_id: Primary key of the completed task.
            job_id: Job identifier for provenance tracking.
            next_node_str: Pipe-separated successor node IDs (e.g. ``"NODE_A|NODE_B"``).
            new_payload_path: Path to the artifact produced by the completed node.
            actual_cost: API cost incurred for this node execution.
            source_payload_path: Original user payload path (propagated unchanged).
            max_recursion: Maximum allowed visits to the same node before FAILED routing.
            flow_line_id: Flow line identifier for scatter fan-out lineage tracking.
            flow_vector: Colon-delimited history of nodes traversed (telemetry lineage).
        """

    @abc.abstractmethod
    def release_task(self, row_id: int) -> None:
        """Return a locked task to 'open' state (used in worker finally blocks)."""

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
