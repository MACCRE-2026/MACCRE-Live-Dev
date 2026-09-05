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
        #: Row ids passed to :meth:`heartbeat_task`, in call order. Lets a test
        #: assert that a long-running node actually refreshed its lock.
        self.heartbeat_calls: list[int] = []
        self._session_ledgers: dict[str, str] = {}
        self._session_step_index: dict[str, int] = {}

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

    def count_ready_tasks(
        self,
        job_id: str,
        topology_engine: Any = None,
        cap: int = 0,
    ) -> int:
        """Count open tasks for *job_id*.

        The mock has no Gather Gate, so every open task counts as ready. That is
        the correct mock behaviour: pool sizing tests want to control the count
        directly, not re-test the broker's dependency resolution.
        """
        ready = 0
        for task in self._tasks:
            if task["lock_status"] == "open" and task["job_id"] == job_id:
                ready += 1
                if cap > 0 and ready >= cap:
                    break
        return ready

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
        # Mark current task completed
        for task in self._tasks:
            if task["id"] == row_id:
                task["lock_status"] = status
                # Mirror the real broker: an empty output_path leaves any
                # existing value alone rather than blanking it.
                if output_path:
                    task["output_path"] = output_path
                # Same rule for payload_bytes, where 0 means "not measured". A mock
                # that blanked it would let a test pass against behaviour the real
                # broker does not have — which is the only thing a mock can get
                # seriously wrong.
                if payload_bytes:
                    task["payload_bytes"] = payload_bytes
                break

        self.route_calls.append({
            "row_id": row_id,
            "job_id": job_id,
            "next_node_str": next_node_str,
            "new_payload_path": new_payload_path,
            "actual_cost": actual_cost,
            "status": status,
            "flow_line_id": flow_line_id,
            "flow_vector": flow_vector,
            "tether_id": tether_id,
            "output_path": output_path,
            "payload_bytes": payload_bytes,
        })

        # Enqueue successor nodes
        for raw_node in next_node_str.split("|"):
            node = raw_node.strip()
            if node and node.upper() != "END":
                self._tasks.append({
                    "id": self._next_id,
                    "job_id": job_id,
                    "payload_path": new_payload_path,
                    "source_payload_path": source_payload_path or new_payload_path,
                    "output_path": "",
                    "current_node": node,
                    "lock_status": "open",
                    "locked_by": None,
                    "flow_line_id": flow_line_id,
                    "flow_vector": flow_vector,
                    "tether_id": tether_id,
                    "created_at": "2026-01-01T00:00:00Z",
                })
                self._next_id += 1

    def update_session_ledger(self, job_id: str, ledger_path: str) -> None:
        self._session_ledgers[job_id] = ledger_path

    def update_session_step_index(self, job_id: str, step_index: int) -> None:
        self._session_step_index[job_id] = step_index

    def release_task(self, row_id: int) -> None:
        for task in self._tasks:
            if task["id"] == row_id:
                task["lock_status"] = "open"
                task["locked_by"] = None
                task["locked_at"] = None
                break

    def heartbeat_task(self, row_id: int) -> bool:
        """Refresh a held lock. Mirrors the real broker's locked-only scoping."""
        for task in self._tasks:
            if task["id"] == row_id:
                if task.get("lock_status") != "locked":
                    return False
                self.heartbeat_calls.append(row_id)
                task["locked_at"] = f"beat-{len(self.heartbeat_calls)}"
                return True
        return False

    def pause_task(self, row_id: int) -> None:
        for task in self._tasks:
            if task["id"] == row_id:
                task["lock_status"] = "paused"
                task["locked_by"] = None
                task["locked_at"] = None
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
                "flow_line_id": "",
                "flow_vector": "",
                "tether_id": "",
                "created_at": "2026-01-01T00:00:00Z",
            })
            self._next_id += 1

    def broadcast_topology_event(self, event_type: str, payload: dict[str, str]) -> None:
        self._events.append((event_type, payload))
