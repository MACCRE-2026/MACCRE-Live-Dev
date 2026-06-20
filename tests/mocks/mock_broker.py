# ┌─────────────────────────────────────────────────────────────────────────────┐
# │  MACCREv2 Test Infrastructure — Mock Message Broker                         │
# └─────────────────────────────────────────────────────────────────────────────┘
"""
tests/mocks/mock_broker.py
==========================
Phase 2C — Mock MessageBroker for deterministic testing.

Implements the ``MessageBroker`` ABC with an in-memory task queue,
eliminating the need for SQLite during unit tests.
"""
from __future__ import annotations

from typing import Any


from maccre_core.orchestration.broker_interface import MessageBroker


class MockMessageBroker(MessageBroker):
    """In-memory MessageBroker for unit tests.

    Maintains a simple list-based task queue with atomic-ish semantics.
    All operations are synchronous and deterministic.

    Usage::

        broker = MockMessageBroker()
        broker.inject_task("job_1", "/tmp/payload.txt", "NODE_A")
        task = broker.fetch_and_lock_task("agent_1", mock_topology)
        assert task is not None
        assert task["current_node"] == "NODE_A"
    """

    def __init__(self) -> None:
        self._tasks: list[dict[str, Any]] = []
        self._next_id = 1
        self._interrupts: list[dict[str, Any]] = []
        self._events: list[tuple[str, dict[str, str]]] = []
        self.route_calls: list[dict[str, Any]] = []

    def fetch_and_lock_task(
        self,
        agent_id: str,
        topology_engine: Any,
    ) -> dict[str, Any] | None:
        for task in self._tasks:
            if task["lock_status"] == "open":
                task["lock_status"] = "locked"
                task["locked_by"] = agent_id
                return dict(task)
        return None

    def route_task(
        self,
        row_id: int,
        job_id: str,
        next_node_str: str,
        new_payload_path: str,
        actual_cost: float = 0.0,
        source_payload_path: str = "",
        max_recursion: int = 3,
    ) -> None:
        # Mark current task completed
        for task in self._tasks:
            if task["id"] == row_id:
                task["lock_status"] = "completed"
                break

        self.route_calls.append({
            "row_id": row_id,
            "job_id": job_id,
            "next_node_str": next_node_str,
            "new_payload_path": new_payload_path,
            "actual_cost": actual_cost,
        })

        # Enqueue successor nodes
        for node in next_node_str.split("|"):
            node = node.strip()
            if node and node.upper() != "END":
                self._tasks.append({
                    "id": self._next_id,
                    "job_id": job_id,
                    "payload_path": new_payload_path,
                    "source_payload_path": source_payload_path or new_payload_path,
                    "current_node": node,
                    "lock_status": "open",
                    "locked_by": None,
                    "created_at": "2026-01-01T00:00:00Z",
                })
                self._next_id += 1

    def release_task(self, row_id: int) -> None:
        for task in self._tasks:
            if task["id"] == row_id:
                task["lock_status"] = "open"
                task["locked_by"] = None
                break

    def pause_task(self, row_id: int) -> None:
        for task in self._tasks:
            if task["id"] == row_id:
                task["lock_status"] = "paused"
                task["locked_by"] = None
                break

    def inject_interrupt(self, job_id: str, override_text: str) -> None:
        self._interrupts.append({
            "job_id": job_id,
            "override_text": override_text,
            "status": "pending",
        })

    def consume_pending_interrupts(self, job_id: str) -> list[str]:
        texts: list[str] = []
        remaining: list[dict[str, Any]] = []
        for intr in self._interrupts:
            if intr["job_id"] in (job_id, "ALL") and intr["status"] == "pending":
                texts.append(intr["override_text"])
                intr["status"] = "processed"
            remaining.append(intr)
        self._interrupts = remaining
        return texts

    def inject_task(
        self,
        job_id: str,
        payload_path: str,
        starting_node: str,
    ) -> None:
        starting_nodes = [n.strip() for n in starting_node.split(",") if n.strip()]
        if not starting_nodes:
            starting_nodes = ["ANCHOR"]

        for node in starting_nodes:
            self._tasks.append({
                "id": self._next_id,
                "job_id": job_id,
                "payload_path": payload_path,
                "source_payload_path": payload_path,
                "current_node": node,
                "lock_status": "open",
                "locked_by": None,
                "created_at": "2026-01-01T00:00:00Z",
            })
            self._next_id += 1

    def broadcast_topology_event(self, event_type: str, payload: dict[str, str]) -> None:
        self._events.append((event_type, payload))
