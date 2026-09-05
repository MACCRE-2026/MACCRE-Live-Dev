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
import threading
from typing import Any, Collection, Literal, Optional


from maccre_core.utils.path_resolver import get_datacenter_path
from maccre_core.orchestration.broker_interface import MessageBroker
from maccre_core.orchestration.concurrency import DEFAULT_HEARTBEAT_SECONDS
from maccre_core.orchestration.topology_graph import (
    TetherQualifiedRef,
    is_terminal_target,
    parse_tether_qualified_ref,
)

#: Seconds a lock may go unrefreshed before :meth:`
#: LocalMessageBroker.reclaim_zombie_locks` treats it as abandoned.
#:
#: Expressed as a multiple of the heartbeat interval rather than as a bare number,
#: because the only thing that makes any threshold safe is its relationship to how
#: often a live worker checks in. At 24 missed beats a worker has been silent for
#: two minutes; a node that is merely slow keeps its lock indefinitely.
#:
#: The previous default was 15 s measured from *enqueue*, which under an 8-wide
#: scatter routinely elapsed before a lane was even claimed.
DEFAULT_ZOMBIE_TIMEOUT_SECONDS: float = DEFAULT_HEARTBEAT_SECONDS * 24

#: ``(job_id, node_id, tether_id)`` triples already reported as a tether scope
#: mismatch. The gather gate is evaluated on every poll tick for every open task,
#: so an undeduplicated warning would flood the log at roughly the poll rate.
_SCOPE_WARNED: set[tuple[str, str, str]] = set()
_SCOPE_WARN_LOCK = threading.Lock()

#: Result of evaluating a task's Gather Gate. See :meth:`LocalMessageBroker._gather_gate_state`.
GateState = Literal["ready", "waiting", "upstream_failed"]


def resolve_cross_lane_target(ref: str, known_lanes: Collection[str]) -> TetherQualifiedRef:
    """Resolve a cross-lane reference, or refuse. Requirement 31.5.

    The runtime half of Requirements 31.3 through 31.5, which are one rule stated three
    times: an approximately-correct lane address is worse than an absent one. Pre-launch
    validation (``topology_graph.validate_cross_lane_routes``) is the first statement of
    it; this is the second, and it lives **here** rather than in ``topology_graph``
    because the broker is what creates successor rows. A reference that cannot be
    resolved has to raise at the exact place the silent drop would otherwise happen —
    ``route_task`` already skips terminal sentinels without enqueueing anything, and an
    unresolvable ``GHOST@X.99`` taking that same quiet exit is indistinguishable from a
    lane that simply ended.

    Parsing is delegated to ``topology_graph.parse_tether_qualified_ref`` so there is one
    reading of the reference syntax rather than a broker-flavoured second one. That is
    the same reason this module already imports ``is_terminal_target`` instead of
    re-deriving the sentinel list.

    Args:
        ref: A tether-qualified reference, ``"NODE@TETHER"``.
        known_lanes: Tether IDs the running job actually has. A ``Collection`` rather
            than an ``Iterable`` because it is tested for membership, and an exhausted
            generator would make every lane look absent.

    Returns:
        The parsed reference, its lane confirmed present.

    Raises:
        topology_graph.TetherRefError: The reference is malformed. A ``ValueError``
            subclass, raised by the shared parse rather than re-detected here.
        LookupError: The reference is well-formed but names a lane this job does not
            have. Distinct from the parse failure because they call for different fixes:
            one is a typo in the syntax, the other a typo in the topology.
    """
    parsed = parse_tether_qualified_ref(ref)
    if parsed.tether_id not in known_lanes:
        available = ", ".join(sorted(known_lanes)) or "none"
        raise LookupError(
            f"cross-lane reference {ref!r} names lane {parsed.tether_id!r}, which this job does "
            f"not have (lanes present: {available}). Refusing rather than dropping it: a dropped "
            "route is indistinguishable from a lane that ended."
        )
    return parsed


class LocalMessageBroker(MessageBroker):
    """Zero-dependency SQLite Scatter-Gather State Machine."""

    def __init__(self, db_path: str | None = None) -> None:
        self.db_path = db_path or str(get_datacenter_path("swarm_queue.db"))
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        # Connections are per-thread — see _get_conn() for why. _all_conns exists
        # only so close() can tear down connections it does not own.
        self._local = threading.local()
        self._all_conns: list[sqlite3.Connection] = []
        self._conns_lock = threading.Lock()
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
            with self._conns_lock:
                conns = list(self._all_conns)
                self._all_conns.clear()
            for _conn in conns:
                try:
                    _conn.close()
                except Exception:
                    pass
            # Drop this thread's handle so a later _get_conn() reopens cleanly.
            if getattr(self._local, "conn", None) is not None:
                self._local.conn = None
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
        """Return this thread's SQLite connection, creating it on first use.

        **One connection per thread, not one per broker.** This is a correctness
        requirement, not an optimisation.

        A single ``sqlite3.Connection`` can only hold one transaction at a time,
        regardless of ``check_same_thread``. If two threads shared a connection,
        thread B's statements would silently join whatever transaction thread A
        had open — so the ``BEGIN EXCLUSIVE`` in :meth:`fetch_and_lock_task`
        would stop isolating anything and the TOCTOU race it exists to prevent
        would come straight back. Sharing also means one thread's ``commit()``
        or ``rollback()`` ends another thread's transaction.

        With a connection per thread, ``BEGIN EXCLUSIVE`` contends at the SQLite
        file level, which is exactly where the serialisation is wanted.

        ``row_factory`` is set here, once, rather than being reassigned by
        individual query methods — reassigning it on a shared connection is a
        cross-thread side effect, and every consumer in this module already
        tolerates ``sqlite3.Row`` (it supports positional indexing, iteration
        and unpacking).
        """
        conn: sqlite3.Connection | None = getattr(self._local, "conn", None)
        if conn is None:
            conn = sqlite3.connect(self.db_path, timeout=30.0)
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA journal_mode=WAL")
            # Wait rather than raising "database is locked" while another thread
            # holds the exclusive claim lock. Tuned against measured contention
            # in Phase 6.12B; see the risk register in the task artifact.
            conn.execute("PRAGMA busy_timeout=5000")
            self._local.conn = conn
            with self._conns_lock:
                self._all_conns.append(conn)
        return conn

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
                output_path          TEXT DEFAULT '',
                current_node         TEXT NOT NULL,
                lock_status          TEXT DEFAULT 'open',
                locked_by            TEXT,
                locked_at            TIMESTAMP,
                actual_cost          REAL DEFAULT 0.0,
                flow_line_id         TEXT DEFAULT '',
                tether_id            TEXT DEFAULT '',
                flow_vector          TEXT DEFAULT '',
                payload_bytes        INTEGER DEFAULT 0,
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
            # Phase 6.13 A1: lock-acquisition timestamp. Distinct from created_at,
            # which measures time in the queue, not time holding the lock.
            "ALTER TABLE task_queue ADD COLUMN locked_at TIMESTAMP",
            # Phase 6.13 E1: what this node actually produced, as distinct from
            # what it handed the next node. Those are the same value most of the
            # time, which is why one column served for both until it didn't:
            # under Payload_Mode = "Unified Ledger" the routing payload is the
            # shared session ledger, so overwriting payload_path with it erased
            # every lane's own output and an 8-lane merge gathered one file eight
            # times. payload_path stays the routing record; output_path is the
            # production record, and nothing overwrites it.
            "ALTER TABLE task_queue ADD COLUMN output_path TEXT DEFAULT ''",
            # Phase 6.13 #18: the size in bytes of the payload this node READ.
            #
            # Added because nothing in the system could measure a payload. No
            # tokenizer, no size column in any telemetry silo, and the queue held
            # paths without ever stat()-ing them. The step-boundary payload contract
            # enlarges what crosses a boundary, and `actual_cost` derives from the
            # provider's own promptTokenCount — so the bill would have moved with no
            # way to say by how much or where. This is the before-number.
            #
            # **0 means "not measured", not "empty".** A payload that genuinely does
            # not exist and one whose stat() failed both land here, and the worker
            # logs which at DEBUG. An empty file is 0 bytes too; the distinction is
            # not worth a second column, because a 0-byte payload and an unmeasured
            # one call for the same investigation.
            "ALTER TABLE task_queue ADD COLUMN payload_bytes INTEGER DEFAULT 0",
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
        cursor = conn.execute(
            "SELECT * FROM task_queue WHERE job_id = ? ORDER BY id DESC LIMIT 5",
            (job_id,)
        )
        tasks = [dict(row) for row in cursor.fetchall()]
        return {"job_id": job_id, "recent_tasks": tasks}

    # ── Worker Interface ──────────────────────────────────────────────────────

    @staticmethod
    def _resolve_wait_for(topology_engine: Any, node_id: str) -> str:
        """Resolve a node's ``wait_for`` string. Unknown nodes gate on nothing."""
        if topology_engine is None:
            return "none"
        try:
            config: dict[str, Any] = topology_engine.get_node_config(node_id)
            return str(config.get("wait_for", "none"))
        except Exception:
            return "none"

    def _gather_gate_state(
        self,
        cursor: sqlite3.Cursor,
        task: dict[str, Any],
        wait_for_str: str,
    ) -> GateState:
        """Evaluate one task's Gather Gate against the current queue.

        Pure read — issues SELECTs on the caller's cursor and returns a verdict.
        The caller decides what to do about it, which is what lets
        :meth:`fetch_and_lock_task` (which claims and cancels) and
        :meth:`count_ready_tasks` (which only counts) share one rule set instead
        of maintaining two copies that drift apart.

        Returns:
            ``"ready"`` when every prerequisite has completed (or there are
            none), ``"waiting"`` when at least one is outstanding, and
            ``"upstream_failed"`` when a prerequisite failed — in which case
            this task can never become ready.
        """
        if wait_for_str.strip().lower() in ("none", "", "null"):
            return "ready"

        required_nodes = [
            n.strip() for n in wait_for_str.replace("|", ",").split(",") if n.strip()
        ]
        if not required_nodes:
            return "ready"

        placeholders = ",".join(["?"] * len(required_nodes))
        task_tether_id = str(task.get("tether_id", "") or "")

        # Tether-scoped gather: when the current task carries a tether_id, only
        # check predecessor completion within the same scatter scope. Without
        # this, lane 2 of one scatter could satisfy lane 1's gate.
        if task_tether_id:
            cursor.execute(
                f"""
                SELECT current_node, lock_status
                FROM task_queue
                WHERE job_id = ? AND current_node IN ({placeholders})
                      AND tether_id = ?
                ORDER BY id ASC
                """,  # noqa: S608 - placeholders are generated '?' marks, not user data
                [task["job_id"], *required_nodes, task_tether_id],
            )
        else:
            cursor.execute(
                f"""
                SELECT current_node, lock_status
                FROM task_queue
                WHERE job_id = ? AND current_node IN ({placeholders})
                ORDER BY id ASC
                """,  # noqa: S608 - placeholders are generated '?' marks, not user data
                [task["job_id"], *required_nodes],
            )

        # Keep only the latest status for each node (ordered by id ASC above, so
        # later rows overwrite earlier ones).
        latest_status: dict[str, str] = {}
        for r in cursor.fetchall():
            latest_status[r[0]] = r[1]

        if not latest_status and task_tether_id:
            # The tether-scoped query matched nothing at all. Either the
            # predecessors have not been created yet (normal, early in a scatter)
            # or they exist under a *different* tether — a scope mismatch, which
            # this gate can never resolve on its own.
            #
            # The second case deserves a diagnostic because its symptom is
            # indistinguishable from ordinary waiting: the task stays `open`, the
            # pool keeps spawning workers that cannot claim it, and each retires
            # idle. That churn continues to the wall-clock timeout with nothing in
            # the log explaining it. Naming the mismatch once turns an hour of
            # silent spin into a one-line answer.
            self._warn_on_tether_scope_mismatch(
                cursor, task, required_nodes, task_tether_id, placeholders
            )
            return "waiting"

        if any(stat == "failed" for stat in latest_status.values()):
            return "upstream_failed"

        completed_count = sum(1 for stat in latest_status.values() if stat == "completed")
        if completed_count < len(required_nodes):
            return "waiting"
        return "ready"

    def _warn_on_tether_scope_mismatch(
        self,
        cursor: sqlite3.Cursor,
        task: dict[str, Any],
        required_nodes: list[str],
        task_tether_id: str,
        placeholders: str,
    ) -> None:
        """Log once when predecessors exist but under a different tether.

        Only reached when the scoped query found nothing, which after correct
        configuration never happens — so the extra read costs nothing on the
        healthy path.
        """
        node_id = str(task.get("current_node", ""))
        key = (str(task.get("job_id", "")), node_id, task_tether_id)
        with _SCOPE_WARN_LOCK:
            if key in _SCOPE_WARNED:
                return
            _SCOPE_WARNED.add(key)

        try:
            cursor.execute(
                f"""
                SELECT DISTINCT tether_id
                FROM task_queue
                WHERE job_id = ? AND current_node IN ({placeholders})
                """,  # noqa: S608 - placeholders are generated '?' marks, not user data
                [task["job_id"], *required_nodes],
            )
            found = sorted({str(r[0] or "") for r in cursor.fetchall()})
        except sqlite3.Error:
            return

        if not found:
            return  # predecessors genuinely not created yet — nothing to report

        import logging  # noqa: PLC0415
        logging.getLogger("maccre_core").warning(
            "[BROKER] Gather gate for %s cannot open: it waits on %d node(s) in "
            "tether %r, but those nodes exist under tether(s) %s. This is a scope "
            "mismatch, not a pending dependency — the gate will never open and the "
            "pool will spin on an unclaimable task.",
            node_id, len(required_nodes), task_tether_id, found,
        )

    def fetch_and_lock_task(
        self,
        agent_id: str,
        topology_engine: Any,
    ) -> Optional[dict[str, Any]]:
        """
        Atomically claim the oldest 'open' task whose Gather Gate dependencies
        are satisfied.  Uses BEGIN EXCLUSIVE so only one worker can enter this
        block at a time, eliminating the TOCTOU race condition.

        The claim is the **sole correctness authority** for who owns a task.
        :meth:`count_ready_tasks` is only a sizing hint and never grants
        ownership.

        Everything from ``BEGIN EXCLUSIVE`` to the single ``commit()`` runs in
        one transaction. Cancellations of tasks with failed upstreams are staged
        into that same transaction rather than committed mid-scan: committing
        early would release the exclusive lock while the loop was still
        iterating, so the subsequent claim UPDATE would run unprotected and the
        race this method exists to prevent would return.
        """
        conn = self._get_conn()
        cursor = conn.cursor()
        cursor.execute("BEGIN EXCLUSIVE")
        try:
            cursor.execute(
                "SELECT * FROM task_queue WHERE lock_status = 'open' ORDER BY created_at ASC"
            )
            open_tasks = cursor.fetchall()

            for row in open_tasks:
                task = dict(row)
                node_id: str = task["current_node"]

                # A terminal sentinel is an edge label, not a node. It should never
                # reach the queue, but if anything puts one there it must not be
                # executable: a row named 'FAILED' has no topology entry and no roster
                # entry, so a worker falls through to default agent handling and spends
                # real inference on it. Observed live — the resulting FAILED_*.md was
                # then captured as the step output and passed to the next step.
                if is_terminal_target(node_id):
                    import logging  # noqa: PLC0415
                    logging.getLogger("maccre_core").error(
                        "[BROKER] Refusing to execute terminal sentinel %r as a node "
                        "(row %s). Marking it cancelled. Something routed a sentinel "
                        "into the queue.",
                        node_id, task.get("id"),
                    )
                    cursor.execute(
                        "UPDATE task_queue SET lock_status = 'cancelled' WHERE id = ?",
                        (task["id"],),
                    )
                    continue

                wait_for_str = self._resolve_wait_for(topology_engine, node_id)
                gate = self._gather_gate_state(cursor, task, wait_for_str)

                if gate == "upstream_failed":
                    # A dependency failed. Abort this node to prevent ghost ledgers.
                    import logging  # noqa: PLC0415
                    logging.getLogger("maccre_core").error(
                        f"[BROKER] Upstream dependency for {node_id} failed. Aborting {node_id}."
                    )
                    cursor.execute(
                        "UPDATE task_queue SET lock_status = 'cancelled' WHERE id = ?",
                        (task["id"],),
                    )
                    continue

                if gate == "waiting":
                    continue

                # Claim the task atomically within the same EXCLUSIVE transaction.
                # locked_at is stamped here, alongside the status change, so the
                # status and the lock age can never diverge. Reclaim ages on this
                # column, never on created_at.
                cursor.execute(
                    "UPDATE task_queue SET lock_status = 'locked', locked_by = ?, "
                    "locked_at = CURRENT_TIMESTAMP WHERE id = ?",
                    (agent_id, task["id"]),
                )
                conn.commit()
                return task

            conn.commit()
            return None
        except Exception:
            # Never leave the exclusive lock held — it would block every other
            # worker thread until the connection was garbage collected.
            try:
                conn.rollback()
            except Exception:
                pass
            raise

    def count_ready_tasks(
        self,
        job_id: str,
        topology_engine: Any = None,
        cap: int = 0,
    ) -> int:
        """Estimate how many open tasks for *job_id* are currently claimable.

        Read-only sizing hint for :class:`DynamicSwarmPool`. Takes no locks,
        opens no transaction, and writes nothing — so it is safe to call from
        the orchestrating thread while workers are claiming.

        Deliberately advisory. See the ABC docstring: the count can be stale the
        instant it is returned, and the only cost of over-counting is a worker
        thread that finds no work and retires.
        """
        conn = self._get_conn()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT * FROM task_queue WHERE lock_status = 'open' AND job_id = ? "
            "ORDER BY created_at ASC",
            (job_id,),
        )
        open_tasks = cursor.fetchall()

        ready = 0
        for row in open_tasks:
            task = dict(row)
            wait_for_str = self._resolve_wait_for(topology_engine, task["current_node"])
            if self._gather_gate_state(cursor, task, wait_for_str) == "ready":
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
        """
        Mark the current task completed and enqueue successor nodes.

        ``source_payload_path`` is the *original* job payload — the user's input
        document.  It is propagated unchanged through every node hop so downstream
        agents always have access to the raw source alongside the previous ledger.

        ``output_path`` is what this node *produced*. ``new_payload_path`` is what
        the successor should *read*. Keeping them apart is the E1 fix: under
        ``Payload_Mode = "Unified Ledger"`` the successor reads the shared session
        ledger, so writing that value over the completing row's ``payload_path``
        destroyed the only record of what the node itself wrote. Eight scatter
        lanes then all reported ``unified_session_ledger.md`` and the merge
        combined one file eight times. An empty ``output_path`` is honest — it
        means the caller had nothing authoritative to record — and readers fall
        back to ``payload_path``, which preserves behaviour for older rows.

        ``payload_bytes`` is the size of the payload this node **read**, measured by
        the worker before execution. It follows the same don't-blank rule as
        ``output_path``: ``0`` leaves any existing value alone, because ``0`` means
        *not measured* and a later caller that simply did not measure must not erase
        a measurement an earlier one took.

        ``flow_line_id`` tracks scatter fan-out lineage so downstream nodes can
        identify which branch of a parallel scatter they belong to.

        ``tether_id`` isolates fan-in artifact gathering to matching scatter scopes.

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
                "SET lock_status = 'awaiting_orders', payload_path = ?, actual_cost = ?, "
                "locked_at = NULL, "
                "output_path = CASE WHEN ? = '' THEN output_path ELSE ? END, "
                "payload_bytes = CASE WHEN ? = 0 THEN payload_bytes ELSE ? END "
                "WHERE id = ?",
                (new_payload_path, actual_cost, output_path, output_path,
                 payload_bytes, payload_bytes, row_id),
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
        # An empty output_path leaves the existing value alone rather than blanking
        # it. A node that already recorded its output must not lose that record to a
        # later caller that simply did not supply one — and a *wrong* non-empty
        # value would be worse than the absent one it replaced.
        conn.execute(
            "UPDATE task_queue "
            "SET lock_status = ?, payload_path = ?, actual_cost = ?, "
            "completed_at = CURRENT_TIMESTAMP, locked_at = NULL, "
            "output_path = CASE WHEN ? = '' THEN output_path ELSE ? END, "
            "payload_bytes = CASE WHEN ? = 0 THEN payload_bytes ELSE ? END "
            "WHERE id = ?",
            (status, new_payload_path, actual_cost, output_path, output_path,
             payload_bytes, payload_bytes, row_id),
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
                        # Recursion means "this node already executed and is being asked
                        # to run again". Anything that has *not* completed is therefore
                        # not recursion, and must not increment the counter.
                        #
                        # This previously tested only for 'open', which left a real hole.
                        # When one lane of a scatter fails, the gather gate moves the merge
                        # row to 'cancelled' (see fetch_and_lock_task). Every remaining lane
                        # then arrived at a row that was neither 'open' nor 'completed',
                        # fell through to the ON CONFLICT below, and incremented
                        # loop_iteration_count. At eight lanes the count passed
                        # max_recursion and a convergent fan-in was misdiagnosed as runaway
                        # recursion. Observed live: CTRL_MERGE_S1 reached count=3, was
                        # rerouted, and never ran.
                        #
                        # 'paused' and 'awaiting_orders' matter too — reopening either would
                        # break a HITL gate the operator is standing at.
                        if existing_lock != "completed":
                            conn.execute(
                                "UPDATE task_queue SET payload_path=?, source_payload_path=?, tether_id=? "
                                "WHERE job_id=? AND current_node=?",
                                (new_payload_path, source_payload_path, tether_id, job_id, node),
                            )
                            continue

                        # ── True recursion guard ──────────────────────────────────────
                        # The node has completed and is being re-queued. Genuine recursion.
                        if existing_count >= max_recursion:
                            import logging  # noqa: PLC0415
                            logging.getLogger("maccre_core").error(
                                "[BROKER] Recursion limit reached for %s (count=%d >= %d). "
                                "Marking it failed; downstream gather gates will report "
                                "upstream_failed.",
                                node, existing_count, max_recursion,
                            )
                            # Mark the offending node failed. Do NOT insert a row named
                            # 'FAILED': that is a terminal sentinel, and this branch used to
                            # create one as a real queue row — three lines after the
                            # docstring promising "terminal sentinels; no new rows inserted".
                            # A worker then claimed it, found no topology or roster entry,
                            # fell through to default agent handling and spent real inference
                            # on it, writing a FAILED_*.md that the flow engine captured as
                            # the step's output and fed to the next step as input.
                            conn.execute(
                                "UPDATE task_queue SET lock_status = 'failed', "
                                "completed_at = CURRENT_TIMESTAMP, locked_at = NULL "
                                "WHERE job_id = ? AND current_node = ?",
                                (job_id, node),
                            )
                            continue

                    # ── First arrival or re-queue after completion ────────────────────
                    conn.execute(
                        "INSERT INTO task_queue "
                        "(job_id, payload_path, source_payload_path, current_node, "
                        "loop_iteration_count, flow_line_id, flow_vector, tether_id) "
                        "VALUES (?, ?, ?, ?, 0, ?, ?, ?) "
                        "ON CONFLICT(job_id, current_node) DO UPDATE SET "
                        "lock_status='open', "
                        "locked_at=NULL, "
                        "payload_path=excluded.payload_path, "
                        "flow_line_id=excluded.flow_line_id, "
                        "flow_vector=excluded.flow_vector, "
                        "tether_id=excluded.tether_id, "
                        "loop_iteration_count=task_queue.loop_iteration_count + 1",
                        (job_id, new_payload_path, source_payload_path, node, flow_line_id, flow_vector, tether_id),
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
        """Return a locked task to 'open' state so another worker can claim it.

        Clears ``locked_at`` alongside ``locked_by``, preserving the invariant
        that ``locked_at`` is non-NULL only while ``lock_status = 'locked'``.
        """
        conn = self._get_conn()
        conn.execute(
            "UPDATE task_queue SET lock_status = 'open', locked_by = NULL, "
            "locked_at = NULL WHERE id = ?",
            (row_id,),
        )
        conn.commit()

    def heartbeat_task(self, row_id: int) -> bool:
        """Refresh a held lock's ``locked_at``, proving the worker is still alive.

        The ``lock_status = 'locked'`` predicate is load-bearing, not defensive.
        The heartbeat runs on a separate daemon thread from the node it is
        vouching for, so it can fire *after* the node finished and committed its
        completion. Unscoped, that late beat would stamp a fresh ``locked_at``
        onto a completed row, breaking the invariant that only locked rows carry
        a lock age — and leaving a permanently "recently locked" completed task
        for any diagnostic to trip over.

        Returns:
            True if a locked row was refreshed; False if the row is no longer
            locked, which tells the heartbeat thread to stop.
        """
        conn = self._get_conn()
        cursor = conn.execute(
            "UPDATE task_queue SET locked_at = CURRENT_TIMESTAMP "
            "WHERE id = ? AND lock_status = 'locked'",
            (row_id,),
        )
        conn.commit()
        return cursor.rowcount > 0

    def reclaim_zombie_locks(
        self,
        timeout_seconds: float = DEFAULT_ZOMBIE_TIMEOUT_SECONDS,
        job_id: str | None = None,
    ) -> int:
        """Return locks held by dead workers to the queue.

        A lock is considered abandoned when nothing has refreshed it for
        *timeout_seconds*. Because :meth:`heartbeat_task` refreshes ``locked_at``
        every few seconds for as long as a node is running, a stale timestamp is
        evidence the *worker* stopped, not merely that the node is slow.

        What this used to get wrong
        --------------------------
        The age test keyed off ``created_at`` — when the row was *enqueued* — so
        it measured time spent waiting in the queue, not time spent holding the
        lock. Sequentially the two were nearly identical, since a task was
        claimed almost as soon as it was queued. Under an 8-wide scatter they
        diverge by however long a lane waits for a free worker, which routinely
        exceeded the old 15 s default. A freshly-claimed task therefore looked
        abandoned the instant it was picked up: reclaiming set it back to
        ``open``, a second worker claimed it, and the node ran twice — duplicate
        ledger writes and duplicate API spend, with no error anywhere.

        Two things had to exist before this could be correct, and now do:
        ``locked_at`` (Task A1) to measure the right interval, and
        :meth:`heartbeat_task` (Task A2) to keep a live worker's lock fresh.

        Args:
            timeout_seconds: Seconds without a refresh before a lock is treated
                as abandoned. The default is many heartbeat intervals wide, so a
                worker must miss a long run of beats before anything is taken
                from it.
            job_id: Restrict reclamation to one job. ``None`` sweeps every job,
                which is only appropriate for a cold-start cleanup — a running
                job should never reclaim across into another job's locks.

        Returns:
            Number of locks reclaimed.

        Note:
            Rows locked *before* the ``locked_at`` migration have a NULL
            timestamp and are deliberately never reclaimed: with no lock-age
            information the safe assumption is that the lock is live. Such a row
            has to be cleared with :meth:`release_task`.
        """
        sql = (
            "UPDATE task_queue SET lock_status = 'open', locked_by = NULL, "
            "locked_at = NULL "
            "WHERE lock_status = 'locked' AND locked_at IS NOT NULL AND "
            "((julianday('now') - julianday(locked_at)) * 86400.0) > ?"
        )
        params: list[Any] = [timeout_seconds]
        if job_id is not None:
            sql += " AND job_id = ?"
            params.append(job_id)

        conn = self._get_conn()
        cursor = conn.execute(sql, tuple(params))
        reclaimed_count = cursor.rowcount
        conn.commit()
        if reclaimed_count:
            import logging  # noqa: PLC0415
            logging.getLogger("maccre_core").warning(
                "[BROKER] Reclaimed %d abandoned lock(s) idle >%.0fs%s. "
                "A worker died without resolving its task.",
                reclaimed_count, timeout_seconds,
                f" for job {job_id}" if job_id else "",
            )
        return reclaimed_count

    def pause_task(self, row_id: int) -> None:
        """Set a task to 'paused' state — worker will skip it until manual resume."""
        conn = self._get_conn()
        conn.execute(
            "UPDATE task_queue SET lock_status = 'paused', locked_by = NULL, "
            "locked_at = NULL WHERE id = ?",
            (row_id,),
        )
        conn.commit()

    def resume_paused_task(
        self,
        job_id: str,
        new_payload_path: str = "",
        topology_engine: Any = None,
    ) -> bool:
        """Resume the first paused task for a job, optionally with injected context.

        A paused **pause node** cannot simply be reopened: the worker would run it
        again and it would pause again. It has to be completed and routed onward
        instead.

        Where "onward" is used to be hardcoded::

            # In a macro flow, the Next_Node is END. For now, we assume END.
            self.route_task(row_id, job_id, "END", payload, ...)

        That was correct only because the review auto-wrap also hardcoded
        ``Next_Node = "END"``. Now that a control node's successor is config-driven
        (``step.config["next_node"]``), the resume path has to read the same
        topology the worker would have read, or a review node with a configured
        successor would resume straight to END and silently drop the rest of the
        lane.

        Args:
            job_id: Job whose paused task should resume.
            new_payload_path: Optional injected context (the HITL payload).
            topology_engine: Provider used to look up the paused node's
                ``next_node``. When ``None`` or when the node is unknown, falls
                back to ``"END"`` — the previous behaviour.

        Returns:
            True if a paused task was found and resumed.
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

        node_upper = str(current_node).upper()
        if node_upper.startswith("CTRL_PAUSE") or node_upper.startswith("DET_PAUSE"):
            next_node = self._resolve_next_node(topology_engine, str(current_node))
            self.route_task(
                row_id, job_id, next_node, payload, source_payload_path=source_payload
            )
        else:
            conn.execute(
                "UPDATE task_queue SET lock_status = 'open', payload_path = ? WHERE id = ?",
                (payload, row_id),
            )
            conn.commit()
        return True

    @staticmethod
    def _resolve_next_node(topology_engine: Any, node_id: str) -> str:
        """Look up a node's configured successor, defaulting to ``"END"``."""
        if topology_engine is None:
            return "END"
        try:
            config: dict[str, Any] = topology_engine.get_node_config(node_id)
        except Exception:
            return "END"
        candidate = str(
            config.get("next_node_success", config.get("next_node", config.get("Next_Node", "")))
        ).strip()
        return candidate or "END"

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
                "locked_at=NULL, "
                "payload_path=excluded.payload_path, "
                "source_payload_path=excluded.source_payload_path, "
                "loop_iteration_count=task_queue.loop_iteration_count + 1",
                (job_id, payload_path, payload_path, node),
            )
        conn.commit()

    def get_completed_payload_paths(
        self,
        job_id: str,
        nodes: list[str],
        tether_id: str | None = None,
    ) -> dict[str, str]:
        """Map each completed node in *nodes* to the payload path it produced.

        Used to feed a deterministic fan-in node (``CTRL_MERGE``, ``CTRL_CONCAT``)
        the outputs of its upstream nodes. Those handlers take a
        ``predecessor_payloads`` list, and the worker had no way to build one — so
        it passed nothing and an 8-lane merge merged a single source.

        Reads ``output_path``, falling back to ``payload_path`` when it is empty.

        .. note::
           This previously read ``payload_path`` alone, on the stated reasoning
           that "``route_task`` writes ``new_payload_path`` onto the row it is
           closing, so the completed row is the authoritative record of what that
           node produced." That reasoning was wrong, and defect E1 is what it cost.
           ``new_payload_path`` is what the *successor reads*, which under
           ``Payload_Mode = "Unified Ledger"`` is the shared session ledger — the
           same value for every lane. Eight lanes therefore returned eight copies
           of one path, ``CTRL_MERGE`` reported ``Merged 8 sources``, and the
           document held eight identical sections. The lanes' real outputs were on
           disk the whole time and nothing recorded where.

           The fallback is load-bearing, not merely a legacy shim. It keeps rows
           written before the ``output_path`` column existed readable, and it is
           also the correct answer for the passthrough callers — ``CTRL_PAUSE``
           resolution here, and ``macro_factory``'s ephemeral spawn — where the
           routing payload genuinely *is* the node's output. What must never
           happen is a caller inventing a value: an absent ``output_path`` makes a
           fan-in gather nothing for that predecessor and say so, while a
           plausible-but-wrong one gets merged as though the lane had succeeded.

        Args:
            job_id: Job to search.
            nodes: Node ids to look for. Nodes with no completed row are simply
                absent from the result.
            tether_id: When given, restrict to that scatter scope so one scatter's
                lanes cannot be gathered by another's merge.

        Returns:
            ``{node_id: payload_path}``, containing only completed nodes with a
            non-empty path.
        """
        if not nodes:
            return {}

        placeholders = ",".join(["?"] * len(nodes))
        sql = (
            "SELECT current_node, COALESCE(NULLIF(output_path, ''), payload_path) "
            "FROM task_queue "
            f"WHERE job_id = ? AND current_node IN ({placeholders}) "  # noqa: S608
            "AND lock_status = 'completed'"
        )
        params: list[Any] = [job_id, *nodes]
        if tether_id:
            sql += " AND tether_id = ?"
            params.append(tether_id)
        # id ASC so a re-queued node's latest row wins, matching the convention in
        # _gather_gate_state.
        sql += " ORDER BY id ASC"

        conn = self._get_conn()
        found: dict[str, str] = {}
        for row in conn.execute(sql, tuple(params)).fetchall():
            node_id = str(row[0] or "")
            path = str(row[1] or "")
            if node_id and path:
                found[node_id] = path
        return found

    def get_payload_bytes_by_node(self, job_id: str) -> dict[str, int]:
        """What each node in a job was handed, in bytes. Phase 6.13 #18.

        The reader half of ``payload_bytes``. It exists in the same change as the
        column deliberately: a schema column with no consumer is the shape the
        doctrine names after the ``--smart`` flag — accepted, documented, and read by
        nothing — and this project has now found that shape three times.

        This is the number the step-boundary payload contract is measured against. Run
        a flow, record what each node received, change the contract, run it again, and
        compare. Without it the change would move the real bill (``actual_cost``
        derives from the provider's own ``promptTokenCount``) with no way to say by how
        much or where.

        Args:
            job_id: The job to report on.

        Returns:
            ``{node_id: bytes}`` for every row of the job that carries a measurement.
            **Nodes measured as 0 are omitted**, because ``0`` means *not measured*
            and including them would put unmeasured nodes and empty payloads in the
            same bucket as a real reading of zero. A caller wanting the full node list
            should ask the topology, which is the thing that actually knows it.
        """
        conn = self._get_conn()
        rows = conn.execute(
            "SELECT current_node, payload_bytes FROM task_queue "
            "WHERE job_id = ? AND payload_bytes > 0 ORDER BY id ASC",
            (job_id,),
        ).fetchall()
        return {str(row[0]): int(row[1]) for row in rows if row[0]}

    # ── Tether-Scoped Queries ──────────────────────────────────────────────────

    def get_completed_by_tether(self, job_id: str, tether_id: str) -> list[dict[str, Any]]:
        """Get all completed tasks for a given job that share the same tether_id."""
        conn = self._get_conn()
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

