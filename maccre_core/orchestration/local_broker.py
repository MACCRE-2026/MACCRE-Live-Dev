# ┌─────────────────────────────────────────────────────────────────────────────┐
# │  MACCREv2 ENGINEERING DOCTRINE                             Law Rev: 19.0   │
# ├─────────────────────────────────────────────────────────────────────────────┤
# │  I.   TYPING      All signatures: explicit Python 3.11+ type hints.        │
# │  II.  LINTING     Zero unused imports. No wildcards. 120-char line max.    │
# │  III. PATHS       Never hardcode absolute paths. Use get_maccre_root().     │
# │                   Default params: def f(p:str='') -> None: p=p or root/x   │
# │  IV.  DATACENTER  5-Tier: 01_Raw_Source · 02_Dynamic_Context               │
# │                           03_Agent_Ledgers · 04_Code_Artifacts             │
# │                           05_Rendered_Media                                 │
# │  V.   DIAMOND     Gen: temp=1.0  ·  Critic: temp=0.1 + dataclass schema   │
# │  VI.  ABSTRACTION All I/O behind abc.ABC before any concrete driver.       │
# │  VII. TEARDOWN    try/finally on all handles (omni clean compliance).      │
# │  VIII.TELEMETRY   No bare print(). logger only. JSON → 03_Agent_Ledgers.  │
# └─────────────────────────────────────────────────────────────────────────────┘
"""
maccre_core/orchestration/local_broker.py
==========================================
Phase 10 Scatter-Gather State Machine.

The Gather Gate concurrency lock is offloaded entirely to the SQLite C-engine:
- UNIQUE(job_id, current_node) on the table schema prevents duplicate Fan-In rows
  at the storage layer.
- INSERT OR IGNORE makes route_task() idempotent for concurrent branches routing
  to the same Fan-In node (e.g. SYNTHESIZE).
- BEGIN EXCLUSIVE in fetch_and_lock_task() serialises worker races at the DB level,
  eliminating the Python-level TOCTOU race that previously required an application
  check-and-insert sequence.
"""
from __future__ import annotations

import atexit
import os
import json
import sqlite3
from typing import Any, Optional


from maccre_core.utils.path_resolver import get_datacenter_path
from maccre_core.orchestration.broker_interface import MessageBroker

class LocalMessageBroker(MessageBroker):
    """Zero-dependency SQLite Scatter-Gather State Machine."""

    def __init__(self, db_path: str | None = None) -> None:
        self.db_path = db_path or str(get_datacenter_path("swarm_queue.db"))
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        self._conn: sqlite3.Connection | None = None
        self._init_db()

        # Phase 22 ZMQ IPC Setup — optional (paused per EXO-GANS handover §1)
        # ZMQ is only required for the live audio session pipeline (Stream 4).
        # The core text queue runs on pure SQLite with no ZMQ dependency.
        self.pub_socket: Any = None
        self.sub_socket: Any = None
        try:
            import zmq  # type: ignore  # noqa: PLC0415
            self.zmq_ctx = zmq.Context.instance()
            self.pub_socket = self.zmq_ctx.socket(zmq.PUB)
            self.pub_socket.connect("tcp://127.0.0.1:5556")
            self.sub_socket = self.zmq_ctx.socket(zmq.SUB)
            self.sub_socket.connect("tcp://127.0.0.1:5557")
            self.sub_socket.setsockopt_string(zmq.SUBSCRIBE, "MACCRE.INTERRUPT")
        except ModuleNotFoundError:
            pass  # ZMQ dormant — text pipeline operates on SQLite only

        atexit.register(self.close)

    def close(self) -> None:
        """Tear down SQLite + ZMQ resources. Registered via atexit for reliable cleanup."""
        try:
            if self._conn:
                self._conn.close()
                self._conn = None
            if self.pub_socket:
                self.pub_socket.close()
                self.pub_socket = None
            if self.sub_socket:
                self.sub_socket.close()
                self.sub_socket = None
            if hasattr(self, "zmq_ctx") and self.zmq_ctx:
                self.zmq_ctx.term()
                self.zmq_ctx = None
        except Exception:
            pass
        # Unregister to avoid holding a reference to self after explicit close
        try:
            atexit.unregister(self.close)
        except Exception:
            pass

    # ── Schema Bootstrap ──────────────────────────────────────────────────────────

    def _get_conn(self) -> sqlite3.Connection:
        """Return the persistent SQLite connection, creating it if needed.

        Uses WAL journal mode for better concurrent read performance and
        check_same_thread=False for cross-thread safety (the broker is
        accessed from both the TUI main thread and worker threads).
        """
        if self._conn is None:
            self._conn = sqlite3.connect(
                self.db_path, check_same_thread=False, timeout=30.0
            )
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.execute("PRAGMA busy_timeout=5000")
        return self._conn

    def _init_db(self) -> None:
        conn = self._get_conn()
        conn.execute("""
            CREATE TABLE IF NOT EXISTS job_sessions (
                job_id               TEXT PRIMARY KEY,
                status               TEXT DEFAULT 'active',
                topology_csv         TEXT,
                current_ledger_path  TEXT DEFAULT '',
                current_step_index   INTEGER DEFAULT 0,
                created_at           TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at           TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS task_queue (
                id                   INTEGER PRIMARY KEY AUTOINCREMENT,
                job_id               TEXT NOT NULL,
                payload_path         TEXT NOT NULL,
                source_payload_path  TEXT DEFAULT '',
                current_node         TEXT NOT NULL,
                lock_status          TEXT DEFAULT 'open',
                locked_by            TEXT,
                actual_cost          REAL DEFAULT 0.0,
                flow_line_id         TEXT DEFAULT '',
                tether_id            TEXT DEFAULT '',
                flow_vector          TEXT DEFAULT '',
                created_at           TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(job_id, current_node)
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS interrupt_queue (
                id             INTEGER PRIMARY KEY AUTOINCREMENT,
                job_id         TEXT NOT NULL,
                override_text  TEXT NOT NULL,
                status         TEXT DEFAULT 'pending',
                created_at     TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        # Graceful schema upgrades for pre-existing databases
        for _col_sql in (
            "ALTER TABLE task_queue ADD COLUMN actual_cost REAL DEFAULT 0.0",
            "ALTER TABLE task_queue ADD COLUMN source_payload_path TEXT DEFAULT ''",
            "ALTER TABLE task_queue ADD COLUMN loop_iteration_count INTEGER DEFAULT 0",
            "ALTER TABLE task_queue ADD COLUMN completed_at TIMESTAMP",
            "ALTER TABLE task_queue ADD COLUMN flow_line_id TEXT DEFAULT ''",
            "ALTER TABLE task_queue ADD COLUMN tether_id TEXT DEFAULT ''",
            "ALTER TABLE task_queue ADD COLUMN flow_vector TEXT DEFAULT ''",
        ):
            try:
                conn.execute(_col_sql)
            except sqlite3.OperationalError:
                pass
        # Ensure the UNIQUE index exists on upgraded DBs whose schema predates it
        try:
            conn.execute(
                "CREATE UNIQUE INDEX IF NOT EXISTS idx_job_node "
                "ON task_queue (job_id, current_node)"
            )
        except sqlite3.OperationalError:
            pass
        conn.commit()

    # ── Session Management ────────────────────────────────────────────────────

    def create_session(self, job_id: str, topology_csv: str) -> None:
        """Create a new job session anchor."""
        conn = self._get_conn()
        conn.execute(
            "INSERT INTO job_sessions (job_id, status, topology_csv) VALUES (?, 'active', ?)",
            (job_id, topology_csv)
        )
        conn.commit()

    def update_session_status(self, job_id: str, status: str) -> None:
        """Update the lifecycle status of a session."""
        conn = self._get_conn()
        conn.execute(
            "UPDATE job_sessions SET status = ?, updated_at = CURRENT_TIMESTAMP WHERE job_id = ?",
            (status, job_id)
        )
        conn.commit()

    def update_session_ledger(self, job_id: str, ledger_path: str) -> None:
        """Track the most recent ledger path for the session."""
        conn = self._get_conn()
        conn.execute(
            "UPDATE job_sessions SET current_ledger_path = ?, updated_at = CURRENT_TIMESTAMP WHERE job_id = ?",
            (ledger_path, job_id)
        )
        conn.commit()

    def update_session_step_index(self, job_id: str, step_index: int) -> None:
        """Track the active MacroNode step index for resumption."""
        conn = self._get_conn()
        conn.execute(
            "UPDATE job_sessions SET current_step_index = ?, updated_at = CURRENT_TIMESTAMP WHERE job_id = ?",
            (step_index, job_id)
        )
        conn.commit()

    def get_resumable_sessions(self) -> list[dict[str, Any]]:
        """Retrieve sessions that crashed or were paused."""
        conn = self._get_conn()
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute(
            "SELECT * FROM job_sessions WHERE status IN ('failed', 'paused', 'cancelled', 'active', 'completed') ORDER BY updated_at DESC"
        )
        return [dict(row) for row in cursor.fetchall()]

    def rename_session(self, old_job_id: str, new_job_id: str) -> None:
        """Rename a session's datacenter folders and its DB references."""
        from maccre_core.utils.path_resolver import get_datacenter_path
        import os
        
        tiers = ["01_Raw_Source", "02_Dynamic_Context", "03_Agent_Ledgers", "04_Code_Artifacts", "05_Rendered_Media"]
        for tier in tiers:
            src = get_datacenter_path(tier, old_job_id)
            if src.exists():
                dst = get_datacenter_path(tier, new_job_id)
                try:
                    os.rename(src, dst)
                except Exception as e:
                    import logging
                    logging.getLogger(__name__).warning(f"Could not rename {src} to {dst}: {e}")
                    
        conn = self._get_conn()
        conn.execute("UPDATE job_sessions SET job_id = ?, updated_at = CURRENT_TIMESTAMP WHERE job_id = ?", (new_job_id, old_job_id))
        conn.execute("UPDATE task_queue SET job_id = ? WHERE job_id = ?", (new_job_id, old_job_id))
        conn.execute("UPDATE interrupt_queue SET job_id = ? WHERE job_id = ?", (new_job_id, old_job_id))
        
        cursor = conn.execute("SELECT current_ledger_path FROM job_sessions WHERE job_id = ?", (new_job_id,))
        row = cursor.fetchone()
        if row and row[0]:
            new_path = row[0].replace(old_job_id, new_job_id)
            conn.execute("UPDATE job_sessions SET current_ledger_path = ? WHERE job_id = ?", (new_path, new_job_id))
        conn.commit()
        
        try:
            from maccre_core.orchestration.memory_engine import CognitiveMemoryEngine
            CognitiveMemoryEngine().rename_pins(old_job_id, new_job_id)
        except Exception as e:
            import logging
            logging.getLogger(__name__).warning(f"Could not rename pins in memory engine: {e}")


    def update_session_topology(self, job_id: str, topology_json: str) -> None:
        """Patch the topology JSON string for a specific session."""
        conn = self._get_conn()
        conn.execute(
            "UPDATE job_sessions SET topology_csv = ?, updated_at = CURRENT_TIMESTAMP WHERE job_id = ?",
            (topology_json, job_id)
        )
        conn.commit()

    def mark_canonized(self, job_id: str) -> None:
        """Mark a session as canonized, locking it from further reruns."""
        conn = self._get_conn()
        conn.execute(
            "UPDATE job_sessions SET status = 'canonized', updated_at = CURRENT_TIMESTAMP WHERE job_id = ?",
            (job_id,)
        )
        conn.commit()

    def get_task_errors(self, job_id: str) -> dict[str, Any]:
        """Fetch the last known states and errors for a failed session for Nexus to inspect."""
        conn = self._get_conn()
        conn.row_factory = sqlite3.Row
        cursor = conn.execute(
            "SELECT * FROM task_queue WHERE job_id = ? ORDER BY id DESC LIMIT 5",
            (job_id,)
        )
        tasks = [dict(row) for row in cursor.fetchall()]
        return {"job_id": job_id, "recent_tasks": tasks}

    # ── Worker Interface ──────────────────────────────────────────────────────

    def fetch_and_lock_task(
        self,
        agent_id: str,
        topology_engine: Any,
    ) -> Optional[dict[str, Any]]:
        """
        Atomically claim the oldest 'open' task whose Gather Gate dependencies
        are satisfied.  Uses BEGIN EXCLUSIVE so only one worker process can
        enter this block at a time, eliminating the TOCTOU race condition.
        """
        conn = self._get_conn()
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("BEGIN EXCLUSIVE")

        cursor.execute(
            "SELECT * FROM task_queue WHERE lock_status = 'open' ORDER BY created_at ASC"
        )
        open_tasks = cursor.fetchall()

        for row in open_tasks:
            task = dict(row)
            node_id: str = task["current_node"]
            task_tether_id: str = str(task.get("tether_id", "") or "")

            # Resolve wait_for from topology — unknown nodes default to 'none'
            try:
                config: dict[str, Any] = topology_engine.get_node_config(node_id)
                wait_for_str: str = config.get("wait_for", "none")
            except Exception:
                wait_for_str = "none"

            # Gather Gate: skip if any upstream prerequisite is not yet completed
            if wait_for_str.lower() not in ("none", ""):
                required_nodes = [
                    n.strip()
                    for n in wait_for_str.replace("|", ",").split(",")
                    if n.strip()
                ]
                placeholders = ",".join(["?"] * len(required_nodes))

                # Tether-scoped gather: when the current task carries a tether_id,
                # only check predecessor completion within the same tether scope.
                if task_tether_id:
                    cursor.execute(
                        f"""
                        SELECT current_node, lock_status
                        FROM task_queue
                        WHERE job_id = ? AND current_node IN ({placeholders})
                              AND tether_id = ?
                        ORDER BY id ASC
                        """,
                        [task["job_id"]] + required_nodes + [task_tether_id],
                    )
                else:
                    cursor.execute(
                        f"""
                        SELECT current_node, lock_status
                        FROM task_queue
                        WHERE job_id = ? AND current_node IN ({placeholders})
                        ORDER BY id ASC
                        """,
                        [task["job_id"]] + required_nodes,
                    )
                rows = cursor.fetchall()
                
                # Keep only the latest status for each node
                latest_status = {}
                for r in rows:
                    latest_status[r[0]] = r[1]
                
                # Check if we should abort due to failure
                if any(stat == "failed" for stat in latest_status.values()):
                    # A dependency failed. We must abort this node to prevent ghost ledgers
                    import logging  # noqa: PLC0415
                    logging.getLogger("maccre_core").error(
                        f"[BROKER] Upstream dependency for {node_id} failed. Aborting {node_id}."
                    )
                    cursor.execute(
                        "UPDATE task_queue SET lock_status = 'cancelled' WHERE id = ?",
                        (task["id"],)
                    )
                    conn.commit()
                    continue
                
                # Check if all required nodes are completed
                completed_count = sum(1 for stat in latest_status.values() if stat == "completed")
                if completed_count < len(required_nodes):
                    continue

            # Claim the task atomically within the same EXCLUSIVE transaction
            cursor.execute(
                "UPDATE task_queue SET lock_status = 'locked', locked_by = ? WHERE id = ?",
                (agent_id, task["id"]),
            )
            conn.commit()
            return task

        conn.commit()
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
        status: str = "completed",
        flow_line_id: str = "",
        flow_vector: str = "",
    ) -> None:
        """
        Mark the current task completed and enqueue successor nodes.

        ``source_payload_path`` is the *original* job payload — the user's input
        document.  It is propagated unchanged through every node hop so downstream
        agents always have access to the raw source alongside the previous ledger.

        ``flow_line_id`` tracks scatter fan-out lineage so downstream nodes can
        identify which branch of a parallel scatter they belong to.

        Special targets:
          MANUAL  — pauses the task in 'awaiting_orders'; the GUI calls
                    resolve_manual_task() to dispatch it to dynamic agents.
          DONE / FAILED / STOP / TERMINATE — terminal sentinels; no new rows inserted.

        INSERT OR IGNORE makes standard routing idempotent so concurrent
        Fan-In branches that route to the same node (e.g. SYNTHESIZE) silently
        discard the duplicate at the SQLite C-engine level.
        """
        # ── LIVE SWARM INTERCEPT ──────────────────────────────────────────────
        if next_node_str.strip().upper() in ("CTRL_REVIEW", "DET_REVIEW"):
            conn = self._get_conn()
            conn.execute(
                "UPDATE task_queue "
                "SET lock_status = 'awaiting_orders', payload_path = ?, actual_cost = ? "
                "WHERE id = ?",
                (new_payload_path, actual_cost, row_id),
            )
            conn.commit()
            return

        # ── STANDARD DAG ROUTING ──────────────────────────────────────────────
        next_nodes = [
            n.strip()
            for n in next_node_str.replace("|", ",").split(",")
            if n.strip()
        ]
        conn = self._get_conn()
        conn.execute(
            "UPDATE task_queue "
            "SET lock_status = ?, payload_path = ?, actual_cost = ?, completed_at = CURRENT_TIMESTAMP "
            "WHERE id = ?",
            (status, new_payload_path, actual_cost, row_id),
        )
        for node in next_nodes:
                if node.upper() not in ("DONE", "FAILED", "STOP", "TERMINATE", "END"):
                    cursor = conn.execute(
                        "SELECT loop_iteration_count, lock_status FROM task_queue "
                        "WHERE job_id=? AND current_node=?",
                        (job_id, node),
                    )
                    existing = cursor.fetchone()

                    if existing:
                        existing_count: int = existing[0]
                        existing_lock: str = existing[1]

                        # ── Fan-in detection ──────────────────────────────────────────
                        # If the node is currently 'open' (never executed yet this cycle),
                        # this arrival is a convergent fan-in from a parallel upstream node,
                        # NOT a recursive self-call. Update payload only — do not increment
                        # loop_iteration_count so the recursion limit is not falsely tripped.
                        if existing_lock == "open":
                            conn.execute(
                                "UPDATE task_queue SET payload_path=?, source_payload_path=? "
                                "WHERE job_id=? AND current_node=?",
                                (new_payload_path, source_payload_path, job_id, node),
                            )
                            continue

                        # ── True recursion guard ──────────────────────────────────────
                        # Node has already executed (lock_status='completed') and is being
                        # re-queued. This is genuine recursion — check the limit.
                        if existing_count >= max_recursion:
                            import logging  # noqa: PLC0415
                            logging.getLogger("maccre_core").warning(
                                "[BROKER] Epistemic recursion limit reached for %s (count=%d). "
                                "Rerouting to FAILED.",
                                node, existing_count,
                            )
                            conn.execute(
                                "INSERT OR IGNORE INTO task_queue "
                                "(job_id, payload_path, source_payload_path, current_node) "
                                "VALUES (?, ?, ?, ?)",
                                (job_id, new_payload_path, source_payload_path, "FAILED"),
                            )
                            continue

                    # ── First arrival or re-queue after completion ────────────────────
                    conn.execute(
                        "INSERT INTO task_queue "
                        "(job_id, payload_path, source_payload_path, current_node, "
                        "loop_iteration_count, flow_line_id, flow_vector) "
                        "VALUES (?, ?, ?, ?, 0, ?, ?) "
                        "ON CONFLICT(job_id, current_node) DO UPDATE SET "
                        "lock_status='open', "
                        "payload_path=excluded.payload_path, "
                        "flow_line_id=excluded.flow_line_id, "
                        "flow_vector=excluded.flow_vector, "
                        "loop_iteration_count=task_queue.loop_iteration_count + 1",
                        (job_id, new_payload_path, source_payload_path, node, flow_line_id, flow_vector),
                    )
        conn.commit()

        # ── Radar Heartbeat: ZMQ PubSub ────────────────────────────────────────
        # Broadcast the routing decision instantly to the Live Session Manager.
        event_payload = {
            "job_id": job_id,
            "node": next_node_str,
            "status": "routed",
        }
        self.broadcast_topology_event("NODE_ROUTED", event_payload)

    def release_task(self, row_id: int) -> None:
        """Return a locked task to 'open' state (used in worker finally blocks)."""
        conn = self._get_conn()
        conn.execute(
            "UPDATE task_queue SET lock_status = 'open', locked_by = NULL WHERE id = ?",
            (row_id,),
        )
        conn.commit()

    def pause_task(self, row_id: int) -> None:
        """Set a task to 'paused' state — worker will skip it until manual resume."""
        conn = self._get_conn()
        conn.execute(
            "UPDATE task_queue SET lock_status = 'paused', locked_by = NULL WHERE id = ?",
            (row_id,),
        )
        conn.commit()

    def resume_paused_task(self, job_id: str, new_payload_path: str = "") -> bool:
        """Resume the first paused task for a job, optionally with injected context.

        Returns True if a paused task was found and resumed.
        """
        conn = self._get_conn()
        cursor = conn.execute(
            "SELECT id, payload_path, current_node, source_payload_path FROM task_queue "
            "WHERE job_id = ? AND lock_status = 'paused' LIMIT 1",
            (job_id,),
        )
        row = cursor.fetchone()
        if not row:
            return False
        row_id, old_payload, current_node, source_payload = row
        payload = new_payload_path or old_payload
        
        if str(current_node).upper().startswith("CTRL_PAUSE") or str(current_node).upper().startswith("DET_PAUSE"):
            # PAUSE nodes have no action other than pausing. 
            # If we reopen them, they'll just pause again. Route them to the next node.
            # In a macro flow, the Next_Node is END. For now, we assume END.
            self.route_task(row_id, job_id, "END", payload, source_payload_path=source_payload)
        else:
            conn.execute(
                "UPDATE task_queue SET lock_status = 'open', payload_path = ? WHERE id = ?",
                (payload, row_id),
            )
            conn.commit()
        return True

    def has_paused_tasks(self, job_id: str) -> bool:
        """Check if any tasks are in 'paused' state for a job."""
        conn = self._get_conn()
        cursor = conn.execute(
            "SELECT COUNT(*) FROM task_queue WHERE job_id = ? AND lock_status = 'paused'",
            (job_id,),
        )
        return cursor.fetchone()[0] > 0


    # ── Hot-Mic Priority Override Mechanics ───────────────────────────────────

    def inject_interrupt(self, job_id: str, override_text: str) -> None:
        """User or System pushes an urgent intercept directive into the swarm mid-flight."""
        conn = self._get_conn()
        conn.execute(
            "INSERT INTO interrupt_queue (job_id, override_text) VALUES (?, ?)",
            (job_id, override_text)
        )
        conn.commit()
            
    def consume_pending_interrupts(self, job_id: str) -> list[str]:
        """Worker checks right before inference to yank pending priorities.
        Uses ZMQ Reverse Channel when available, falls back to SQLite-only."""
        texts: list[str] = []
        if self.sub_socket is not None:
            try:
                import zmq  # type: ignore  # noqa: PLC0415
                while True:
                    topic, message = self.sub_socket.recv_multipart(flags=zmq.NOBLOCK)
                    payload = json.loads(message.decode("utf-8"))
                    if payload.get("job_id") in (job_id, "ALL"):
                        texts.append(payload.get("override_text", ""))
            except Exception:
                pass  # zmq.Again or socket unavailable — fall through to SQLite
            
        # Fallback to legacy SQLite interrupt queue to maintain backwards compatibility
        conn = self._get_conn()
        cursor = conn.execute(
            "SELECT id, override_text FROM interrupt_queue WHERE job_id=? AND status='pending'", 
            (job_id,)
        )
        rows = cursor.fetchall()
        if rows:
            ids = [r[0] for r in rows]
            texts.extend([r[1] for r in rows])
            placeholders = ",".join("?" * len(ids))
            conn.execute(
                f"UPDATE interrupt_queue SET status='processed' WHERE id IN ({placeholders})",
                ids
            )
            conn.commit()
        return texts

    def inject_task(
        self,
        job_id: str,
        payload_path: str,
        starting_node: str,
    ) -> None:
        """Enqueue a brand-new job at the given starting node (GUI / CLI entry point).

        ``source_payload_path`` is set to ``payload_path`` at injection time and
        propagated unchanged through every subsequent node so the original user
        document is always accessible to downstream agents.
        """
        starting_nodes = [n.strip() for n in starting_node.split(",") if n.strip()]
        if not starting_nodes:
            starting_nodes = ["ANCHOR"]
            
        conn = self._get_conn()
        for node in starting_nodes:
            conn.execute(
                "INSERT INTO task_queue "
                "(job_id, payload_path, source_payload_path, current_node, loop_iteration_count) "
                "VALUES (?, ?, ?, ?, 0) "
                "ON CONFLICT(job_id, current_node) DO UPDATE SET "
                "lock_status='open', "
                "payload_path=excluded.payload_path, "
                "source_payload_path=excluded.source_payload_path, "
                "loop_iteration_count=task_queue.loop_iteration_count + 1",
                (job_id, payload_path, payload_path, node),
            )
        conn.commit()

    # ── Tether-Scoped Queries ──────────────────────────────────────────────────

    def get_completed_by_tether(self, job_id: str, tether_id: str) -> list[dict[str, Any]]:
        """Get all completed tasks for a given job that share the same tether_id."""
        conn = self._get_conn()
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT * FROM task_queue WHERE job_id = ? AND tether_id = ? AND lock_status = 'completed'",
            (job_id, tether_id),
        ).fetchall()
        return [dict(row) for row in rows]

    # ── Stream 4: ZMQ PUB/SUB Live Event Bus ──────────────────────────────────
    def broadcast_topology_event(self, event_type: str, payload: dict[str, str]) -> None:
        """Broadcast a topology lifecycle event over ZMQ PUB (no-op when ZMQ dormant)."""
        if self.pub_socket is None:
            return  # ZMQ dormant — EXO-GANS text-only mode
        import logging as _log  # noqa: PLC0415
        try:
            topic = f"MACCRE.{event_type}".encode("utf-8")
            msg_bytes = json.dumps(payload).encode("utf-8")
            self.pub_socket.send_multipart([topic, msg_bytes])
        except Exception as e:
            _log.getLogger("maccre_core.local_broker").debug(
                "[ZMQ_STUB] broadcast_topology_event failed: %s", e
            )

