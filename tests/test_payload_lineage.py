# ┌─────────────────────────────────────────────────────────────────────────────┐
# │  MACCREv2 Test Suite — Phase 6.13 E1/E2: Payload Lineage                    │
# └─────────────────────────────────────────────────────────────────────────────┘
"""
tests/test_payload_lineage.py
=============================
Phase 6.13 defects **E1** and **E2** — an artifact losing its identity at a
handoff.

Both were found by reading an agent's ledger on live run
``job_20260831-041428-6goe``, not by the suite. The suite was green at 665 tests
while both were present, because both live in a seam: E1 between what a node
writes and what the queue records, E2 between what a step produces and what the
next step is handed. Nothing stubbed visits either.

**E1 — the merge received eight copies of one document.**
Every scatter lane's row reported ``payload_path = unified_session_ledger.md``.
The chain was five links long and only the second is the root cause:

1. a lane finishes; the worker sets ``routing_payload_path`` to that lane's own
   ledger, ``<node>_<row_id>.md``
2. the Unified Ledger branch then replaces it with the shared session ledger,
   because that is what the *successor* should read. Correct for routing, and it
   discarded the only in-memory reference to what the lane produced
3. ``route_task`` wrote the routing payload onto the row it was closing, so the
   row stopped recording the lane's output
4. the fan-in asked "what did each predecessor produce" and got one path, eight
   times
5. ``_handle_merge`` built a section per path and logged ``Merged 8 sources`` —
   literally true, semantically empty, eight identical
   ``## Source: unified_session_ledger`` headings

The fix separates the two roles: ``payload_path`` is what the successor reads,
``output_path`` is what the node produced, and nothing overwrites the latter.

**E2 — the merge's output never crossed the step boundary.**
The merge row correctly pointed at ``CTRL_MERGE_S0_merged.md`` (426 KB) and the
next step was queued with ``CTRL_MERGE_S0_93.md``, the merge's 59-byte ledger
stub. ``_find_final_ledger_path`` globbed the job's ledger directory and took the
newest mtime; the stub is written *after* the merge artifact, so it is always
newer. This was not a race the glob sometimes lost — it is one it always lost.

The fix asks the topology which node ends the step, then asks the queue what that
node recorded.
"""
from __future__ import annotations

import inspect
import logging
import sqlite3
from pathlib import Path
from typing import Any

import pytest

from maccre_core.orchestration.broker_interface import MessageBroker
from maccre_core.orchestration.deterministic_nodes import execute_deterministic_node
from maccre_core.orchestration.flow_engine import FlowRunner
from maccre_core.orchestration.local_broker import LocalMessageBroker
from maccre_core.utils.path_resolver import get_datacenter_path
from tests.mocks.mock_broker import MockMessageBroker

JOB = "job_payload_lineage"

#: The path every lane wrongly claimed to have produced under E1.
UNIFIED = "/dc/04_Code_Artifacts/job/unified_session_ledger.md"


class FakeTopology:
    """Minimal ``TopologyProvider``-shaped stub: node_id -> wait_for string."""

    def __init__(self, wait_for: dict[str, str] | None = None) -> None:
        self._wait_for = wait_for or {}

    def get_node_config(self, node_id: str) -> dict[str, Any]:
        if node_id not in self._wait_for:
            raise KeyError(node_id)
        return {"wait_for": self._wait_for[node_id]}


@pytest.fixture()
def broker(tmp_path: Path) -> Any:
    b = LocalMessageBroker(db_path=str(tmp_path / "swarm_queue.db"))
    yield b
    b.close()


def _row(broker_obj: LocalMessageBroker, node: str) -> dict[str, Any]:
    cur = broker_obj._get_conn().execute(
        "SELECT * FROM task_queue WHERE job_id = ? AND current_node = ?",
        (JOB, node),
    )
    fetched = cur.fetchone()
    assert fetched is not None, f"no task_queue row for node {node!r}"
    return dict(fetched)


def _complete_lane(
    broker_obj: LocalMessageBroker,
    node: str,
    *,
    routes_to: str,
    reads_next: str,
    produced: str,
    tether: str = "scope_a",
) -> None:
    """Complete *node* exactly as a live lane does under Unified Ledger mode.

    ``reads_next`` is what the successor is handed; ``produced`` is what the node
    itself wrote. E1 is entirely the consequence of those two being conflated, so
    every test here keeps them deliberately different.

    Two deliberate mechanics, both matching production rather than convenience:

    * The row is addressed by node name, not via ``fetch_and_lock_task``, which
      claims the *oldest* open task. Relying on claim order to match declaration
      order would make these tests pass for a reason unrelated to what they check.
    * ``tether`` is stamped **onto the row** before routing. ``route_task`` stamps
      the tether on the rows it *creates*, not on the row it closes, so in a live
      run a lane's tether arrives from the ``CTRL_SCATTER`` that routed to it.
      ``inject_task`` has no scatter in front of it, so the test supplies what the
      scatter would have.
    """
    conn = broker_obj._get_conn()
    found = conn.execute(
        "SELECT id FROM task_queue WHERE job_id = ? AND current_node = ?",
        (JOB, node),
    ).fetchone()
    assert found is not None, f"no row for {node}"
    conn.execute(
        "UPDATE task_queue SET tether_id = ? WHERE job_id = ? AND current_node = ?",
        (tether, JOB, node),
    )
    conn.commit()

    broker_obj.route_task(
        row_id=int(found[0]),
        job_id=JOB,
        next_node_str=routes_to,
        new_payload_path=reads_next,
        status="completed",
        tether_id=tether,
        output_path=produced,
    )


# ── E1, schema ────────────────────────────────────────────────────────────────


class TestOutputPathColumn:
    """E1 — the queue gains a place to record what a node produced."""

    def test_column_exists_on_a_fresh_database(
        self, broker: LocalMessageBroker
    ) -> None:
        cols = {r[1] for r in broker._get_conn().execute("PRAGMA table_info(task_queue)")}
        assert "output_path" in cols

    def test_it_defaults_to_empty_not_null(self, broker: LocalMessageBroker) -> None:
        """An absent output is ``''``, which the read path treats as "fall back".

        NULL would work too, but the column's siblings (``source_payload_path``,
        ``tether_id``, ``flow_vector``) all use ``''``, and one convention beats
        two.
        """
        broker.inject_task(job_id=JOB, payload_path="/in.md", starting_node="N1")
        assert _row(broker, "N1")["output_path"] == ""


class TestOutputPathMigration:
    """E1 — a database written before the column gains it without losing rows.

    Mirrors Track A's ``locked_at`` migration tests, because it is the same
    mechanism: the column is declared in the CREATE TABLE body *and* appended to
    the ALTER list, so fresh and pre-existing databases converge.
    """

    def test_migration_adds_the_column_to_a_legacy_table(self, tmp_path: Path) -> None:
        db = tmp_path / "legacy.db"
        conn = sqlite3.connect(str(db))
        conn.execute("""
            CREATE TABLE task_queue (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                job_id        TEXT NOT NULL,
                payload_path  TEXT NOT NULL,
                current_node  TEXT NOT NULL,
                lock_status   TEXT DEFAULT 'open',
                locked_by     TEXT,
                created_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(job_id, current_node)
            )
        """)
        conn.execute(
            "INSERT INTO task_queue (job_id, payload_path, current_node) "
            "VALUES ('legacy_job', '/legacy.md', 'OLD_NODE')"
        )
        conn.commit()
        conn.close()

        b = LocalMessageBroker(db_path=str(db))
        try:
            cols = {r[1] for r in b._get_conn().execute("PRAGMA table_info(task_queue)")}
            assert "output_path" in cols

            surviving = b._get_conn().execute(
                "SELECT current_node FROM task_queue WHERE job_id = 'legacy_job'"
            ).fetchone()
            assert surviving is not None
            assert surviving[0] == "OLD_NODE", "the migration must not drop rows"
        finally:
            b.close()

    def test_migration_is_idempotent(self, tmp_path: Path) -> None:
        db = tmp_path / "repeat.db"
        for _ in range(3):
            LocalMessageBroker(db_path=str(db)).close()

        b = LocalMessageBroker(db_path=str(db))
        try:
            names = [r[1] for r in b._get_conn().execute("PRAGMA table_info(task_queue)")]
            assert names.count("output_path") == 1
        finally:
            b.close()

    def test_a_legacy_row_still_reports_through_the_fallback(
        self, tmp_path: Path
    ) -> None:
        """Rows written before the column must stay readable.

        Their output lives in ``payload_path`` and nowhere else, so the read path
        coalesces. This is what makes the fix non-breaking for a resumed session
        whose earlier steps ran on the old code.
        """
        db = tmp_path / "legacy_read.db"
        conn = sqlite3.connect(str(db))
        conn.execute("""
            CREATE TABLE task_queue (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                job_id        TEXT NOT NULL,
                payload_path  TEXT NOT NULL,
                current_node  TEXT NOT NULL,
                lock_status   TEXT DEFAULT 'open',
                locked_by     TEXT,
                created_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(job_id, current_node)
            )
        """)
        conn.execute(
            "INSERT INTO task_queue (job_id, payload_path, current_node, lock_status) "
            "VALUES (?, '/out/legacy_L1.md', 'L1', 'completed')",
            (JOB,),
        )
        conn.commit()
        conn.close()

        b = LocalMessageBroker(db_path=str(db))
        try:
            assert b.get_completed_payload_paths(JOB, ["L1"]) == {
                "L1": "/out/legacy_L1.md"
            }
        finally:
            b.close()


# ── E1, the broker contract ───────────────────────────────────────────────────


class TestRouteTaskRecordsProduction:
    """E1 — closing a row records what the node produced, not only what it routed."""

    def test_the_two_paths_are_stored_separately(
        self, broker: LocalMessageBroker
    ) -> None:
        """The headline invariant. Conflating these two values *is* E1."""
        broker.inject_task(job_id=JOB, payload_path="/in.md", starting_node="L1")
        _complete_lane(
            broker, "L1",
            routes_to="CTRL_MERGE", reads_next=UNIFIED, produced="/out/L1_85.md",
        )

        row = _row(broker, "L1")
        assert row["payload_path"] == UNIFIED, "successor still reads the unified ledger"
        assert row["output_path"] == "/out/L1_85.md", "the lane's own output survives"

    def test_an_empty_output_path_does_not_blank_an_existing_one(
        self, broker: LocalMessageBroker
    ) -> None:
        """A later caller with nothing to record must not erase the record.

        ``macro_factory`` and the ``CTRL_PAUSE`` resolver both route without
        supplying an output, and the failure path passes ``""`` deliberately. None
        of them should be able to delete a value a node already earned.
        """
        broker.inject_task(job_id=JOB, payload_path="/in.md", starting_node="L1")
        _complete_lane(
            broker, "L1",
            routes_to="NEXT", reads_next=UNIFIED, produced="/out/L1_85.md",
        )
        assert _row(broker, "L1")["output_path"] == "/out/L1_85.md"

        # Re-close the same row with no output supplied.
        row_id = int(_row(broker, "L1")["id"])
        broker.route_task(
            row_id=row_id, job_id=JOB, next_node_str="DONE",
            new_payload_path=UNIFIED, status="completed", output_path="",
        )
        assert _row(broker, "L1")["output_path"] == "/out/L1_85.md"

    def test_a_failed_node_records_no_output(
        self, broker: LocalMessageBroker
    ) -> None:
        """An absent value degrades visibly; a plausible one gets merged.

        This is the worker's failure path: the node blew up, so there is nothing
        authoritative to record. The gather must then find nothing for it rather
        than pick up its input document and merge that as though it were a result.
        """
        broker.inject_task(job_id=JOB, payload_path="/in.md", starting_node="L1")
        task = broker.fetch_and_lock_task("agent_1", FakeTopology({"L1": "none"}))
        assert task is not None
        broker.route_task(
            row_id=int(task["id"]), job_id=JOB, next_node_str="FAILED",
            new_payload_path="/in.md", status="failed", output_path="",
        )

        assert _row(broker, "L1")["output_path"] == ""
        # 'failed' is not 'completed', so the gather excludes it outright.
        assert broker.get_completed_payload_paths(JOB, ["L1"]) == {}

    def test_the_review_intercept_also_records_output(
        self, broker: LocalMessageBroker
    ) -> None:
        """``CTRL_REVIEW`` parks a row rather than closing it, and still produced.

        Missed here, a HITL step would lose its lineage the moment an operator
        stood at the gate.
        """
        broker.inject_task(job_id=JOB, payload_path="/in.md", starting_node="L1")
        task = broker.fetch_and_lock_task("agent_1", FakeTopology({"L1": "none"}))
        assert task is not None
        broker.route_task(
            row_id=int(task["id"]), job_id=JOB, next_node_str="CTRL_REVIEW",
            new_payload_path=UNIFIED, output_path="/out/L1_85.md",
        )

        row = _row(broker, "L1")
        assert row["lock_status"] == "awaiting_orders"
        assert row["output_path"] == "/out/L1_85.md"


class TestBrokerSignatureParity:
    """E1 — the ABC, the real broker and the mock must move together.

    ``tests/test_broker_contract.py`` already enforces this, but it is worth an
    explicit assertion about *this* parameter: the mock is git-ignored, so a
    content search for ``output_path`` does not find it and it is the copy most
    likely to be forgotten.
    """

    @staticmethod
    def _params(func: Any) -> list[str]:
        return list(inspect.signature(func).parameters)

    def test_all_three_declare_output_path(self) -> None:
        for impl in (
            MessageBroker.route_task,
            LocalMessageBroker.route_task,
            MockMessageBroker.route_task,
        ):
            assert "output_path" in self._params(impl), impl.__qualname__

    def test_it_is_keyword_optional_everywhere(self) -> None:
        """Existing positional callers must keep working.

        ``macro_factory`` calls ``route_task(row_id, job_id, next, payload)``
        positionally, so a required parameter here would have broken macro
        expansion rather than the thing under test.
        """
        for impl in (
            MessageBroker.route_task,
            LocalMessageBroker.route_task,
            MockMessageBroker.route_task,
        ):
            param = inspect.signature(impl).parameters["output_path"]
            assert param.default == "", impl.__qualname__


# ── E1, the gather ────────────────────────────────────────────────────────────


class TestGatherReturnsDistinctOutputs:
    """E1 — the regression that reproduces the live failure end to end."""

    def _seed_eight_lanes(self, broker_obj: LocalMessageBroker) -> list[str]:
        lanes = [f"L{i}" for i in range(1, 9)]
        broker_obj.inject_task(
            job_id=JOB, payload_path="/in.md", starting_node=", ".join(lanes)
        )
        for i, lane in enumerate(lanes, start=85):
            _complete_lane(
                broker_obj, lane,
                routes_to="CTRL_MERGE",
                # Every lane hands the merge the SAME shared ledger. This is the
                # production behaviour under Payload_Mode = "Unified Ledger" and
                # it is not a bug — it is what made the bug invisible.
                reads_next=UNIFIED,
                produced=f"/out/{lane}_{i}.md",
            )
        return lanes

    def test_eight_lanes_yield_eight_distinct_paths(
        self, broker: LocalMessageBroker
    ) -> None:
        """The exact shape of the live defect, asserted on distinctness.

        The pre-fix code returned eight entries too — all of them
        ``unified_session_ledger.md``. Counting them was never the test that would
        have caught this; counting *distinct* ones is.
        """
        lanes = self._seed_eight_lanes(broker)
        found = broker.get_completed_payload_paths(JOB, lanes)

        assert len(found) == 8
        assert len(set(found.values())) == 8, (
            f"lanes collapsed to {sorted(set(found.values()))} — this is E1"
        )
        assert UNIFIED not in found.values(), (
            "a lane reported the shared session ledger as its own output"
        )

    def test_each_lane_reports_its_own_ledger(
        self, broker: LocalMessageBroker
    ) -> None:
        lanes = self._seed_eight_lanes(broker)
        found = broker.get_completed_payload_paths(JOB, lanes)

        for i, lane in enumerate(lanes, start=85):
            assert found[lane] == f"/out/{lane}_{i}.md"

    def test_the_tether_still_scopes_the_lookup(
        self, broker: LocalMessageBroker
    ) -> None:
        """Track D's isolation must survive the E1 change.

        One scatter's merge gathering another's lanes was D3c, and it deadlocked
        an 8-lane run. Re-asserted here because the SELECT was rewritten.
        """
        broker.inject_task(job_id=JOB, payload_path="/in.md", starting_node="L1, L2")
        _complete_lane(
            broker, "L1", routes_to="CTRL_MERGE", reads_next=UNIFIED,
            produced="/out/L1.md", tether="scope_a",
        )
        _complete_lane(
            broker, "L2", routes_to="CTRL_MERGE", reads_next=UNIFIED,
            produced="/out/L2.md", tether="scope_b",
        )

        assert broker.get_completed_payload_paths(
            JOB, ["L1", "L2"], tether_id="scope_a"
        ) == {"L1": "/out/L1.md"}


class TestWorkerPreservesItsOwnOutput:
    """E1 — the worker must capture its output before routing rewrites it.

    A structural guard, in the manner of ``TestDeterministicFanInWiring``. The
    behavioural cost of this line is only observable through a live model call, so
    the ordering is asserted on the source instead: ``node_output_path`` has to be
    bound *before* the Unified Ledger branch, or it captures the shared ledger and
    E1 returns with every test still green.
    """

    @staticmethod
    def _cycle_source() -> str:
        from maccre_core.orchestration.swarm_worker import UniversalSwarmWorker

        return inspect.getsource(UniversalSwarmWorker.execute_cycle)

    def test_the_output_is_captured_before_the_unified_ledger_swap(self) -> None:
        source = self._cycle_source()
        capture_at = source.find("node_output_path = routing_payload_path")
        swap_at = source.find("Routing via Unified Ledger")

        assert capture_at != -1, "the worker no longer captures its own output"
        assert swap_at != -1, "the Unified Ledger branch moved; re-verify this guard"
        assert capture_at < swap_at, (
            "node_output_path is bound after the Unified Ledger override, so it "
            "captures the shared ledger — this is E1 exactly"
        )

    def test_route_task_is_given_the_captured_output(self) -> None:
        source = self._cycle_source()
        assert "output_path=node_output_path" in source, (
            "the AI-node route_task call must pass the captured output"
        )

    def test_deterministic_routes_record_their_artifact(self) -> None:
        """All three deterministic branches, including the fan-out loop.

        ``CTRL_MERGE``'s own output is what the *next step* reads (defect E2), so
        a deterministic node that failed to record it would move the failure one
        boundary along rather than fix it.
        """
        source = self._cycle_source()
        assert source.count("output_path=det_result.output_payload_path") == 3, (
            "expected the scatter fan-out, single-target and default-topology "
            "routes each to record det_result.output_payload_path"
        )


# ── E1, the merge document ────────────────────────────────────────────────────


def _write(path: Path, text: str) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return str(path)


class TestMergeProducesDistinctSections:
    """E1 — the document a downstream agent actually reads.

    Nothing asserted anything about merged *content* before. The defect was found
    by an agent complaining about the document, which is a slower and more
    expensive test than this one.
    """

    def test_eight_distinct_sources_give_eight_distinct_sections(
        self, tmp_path: Path
    ) -> None:
        job = "merge_job"
        paths = [
            _write(tmp_path / f"lane_{i}.md", f"Lane {i} findings about roses.")
            for i in range(1, 9)
        ]

        result = execute_deterministic_node(
            "CTRL_MERGE_S0",
            {"payload_path": "", "job_id": job},
            {"merge_mode": "structured"},
            paths,
        )

        merged = Path(result.output_payload_path).read_text(encoding="utf-8")
        headings = [ln for ln in merged.splitlines() if ln.startswith("## Source:")]
        assert len(headings) == 8
        assert len(set(headings)) == 8, f"duplicate headings: {headings}"
        for i in range(1, 9):
            assert f"Lane {i} findings about roses." in merged

    def test_the_section_heading_names_the_lane(self, tmp_path: Path) -> None:
        """``## Source: OSINT_Analyst_S0_85`` identifies which lane wrote it.

        Under E1 every heading read ``## Source: unified_session_ledger``, which
        is what made the merged document unusable even though it was 426 KB.
        """
        job = "merge_job"
        path = _write(tmp_path / "OSINT_Analyst_S0_85.md", "OSINT findings.")

        result = execute_deterministic_node(
            "CTRL_MERGE_S0", {"payload_path": "", "job_id": job}, {}, [path]
        )

        merged = Path(result.output_payload_path).read_text(encoding="utf-8")
        assert "## Source: OSINT_Analyst_S0_85" in merged

    def test_the_merge_writes_where_the_queue_will_be_told_to_look(
        self, tmp_path: Path
    ) -> None:
        """``<node_id>_merged.md``, and it is the returned output path.

        E2 depends on this being the value recorded in the queue, so it is pinned
        here rather than assumed.
        """
        job = "merge_job"
        path = _write(tmp_path / "lane.md", "content")

        result = execute_deterministic_node(
            "CTRL_MERGE_S0", {"payload_path": "", "job_id": job}, {}, [path]
        )

        expected = get_datacenter_path("03_Agent_Ledgers", job) / "CTRL_MERGE_S0_merged.md"
        assert Path(result.output_payload_path) == expected
        assert expected.exists()


class TestMergeRefusesToInflateItsCount:
    """E1, doctrine 3 — a success line conditional on counted work.

    The root cause is fixed upstream, so these inputs should not occur. They are
    asserted anyway because the original failure was *silent*: ``Merged 8 sources``
    over one file read as success to every log reader and to the operator.
    """

    def test_eight_identical_paths_collapse_to_one_section(
        self, tmp_path: Path
    ) -> None:
        job = "merge_job"
        shared = _write(tmp_path / "unified_session_ledger.md", "The whole session.")

        result = execute_deterministic_node(
            "CTRL_MERGE_S0", {"payload_path": "", "job_id": job}, {}, [shared] * 8
        )

        merged = Path(result.output_payload_path).read_text(encoding="utf-8")
        headings = [ln for ln in merged.splitlines() if ln.startswith("## Source:")]
        assert len(headings) == 1, "eight references to one file are one source"
        # Message reworded 2026-09-02 to name the destination file, because defect
        # E2 was the next step reading a *different* file in the same directory.
        assert "1 distinct source(s)" in result.log_message

    def test_the_collapse_is_reported_loudly(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        """The log line E1 needed and did not have."""
        job = "merge_job"
        shared = _write(tmp_path / "unified_session_ledger.md", "The whole session.")

        with caplog.at_level(logging.WARNING):
            execute_deterministic_node(
                "CTRL_MERGE_S0", {"payload_path": "", "job_id": job}, {}, [shared] * 8
            )

        assert any(
            "8 predecessor payload(s) resolved to 1 distinct source(s)" in r.message
            for r in caplog.records
        ), f"no collapse warning in {[r.message for r in caplog.records]}"

    def test_distinct_sources_are_not_reported_as_a_collapse(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        """The guard must stay quiet on the healthy path.

        A warning that fires on every run is a warning nobody reads.
        """
        job = "merge_job"
        paths = [_write(tmp_path / f"l{i}.md", f"c{i}") for i in range(3)]

        with caplog.at_level(logging.WARNING):
            execute_deterministic_node(
                "CTRL_MERGE_S0", {"payload_path": "", "job_id": job}, {}, paths
            )

        assert not [r for r in caplog.records if "duplicate" in r.message]

    def test_concat_has_the_same_guard(self, tmp_path: Path) -> None:
        """``CTRL_CONCAT`` shares the input contract, so it shared the defect.

        No live flow used it, which is the only reason E1 was observed on
        ``CTRL_MERGE`` alone.
        """
        job = "concat_job"
        shared = _write(tmp_path / "shared.md", "ONCE")

        result = execute_deterministic_node(
            "CTRL_CONCAT_S0", {"payload_path": "", "job_id": job}, {}, [shared] * 5
        )

        merged = Path(result.output_payload_path).read_text(encoding="utf-8")
        assert merged.count("ONCE") == 1


# ── E2, the step boundary ─────────────────────────────────────────────────────


def _scatter_rows(lanes: int = 8) -> list[dict[str, Any]]:
    """The shape the scatter auto-wrap emits: one scatter, N lanes, one merge."""
    agents = [f"Agent{i}" for i in range(1, lanes + 1)]
    rows: list[dict[str, Any]] = [
        {"Node_ID": "CTRL_SCATTER", "Next_Node": ",".join(agents), "Wait_For": "none"}
    ]
    rows.extend(
        {"Node_ID": a, "Next_Node": "CTRL_MERGE", "Wait_For": "none"} for a in agents
    )
    rows.append(
        {"Node_ID": "CTRL_MERGE", "Next_Node": "END", "Wait_For": "|".join(agents)}
    )
    return rows


class TestFindTerminalNodes:
    """E2 — the engine can name the node that ends a step.

    ``_find_final_ledger_path`` accepted ``topology_rows`` and never read them, so
    the "final node of the DAG" it promised was never consulted. This is the mirror
    of ``_find_starting_nodes``, and it hydrates through the same expression.
    """

    def test_a_scatter_step_terminates_at_its_merge(self) -> None:
        assert FlowRunner()._find_terminal_nodes(_scatter_rows(8), 0) == [
            "CTRL_MERGE_S0"
        ]

    def test_the_step_suffix_is_applied(self) -> None:
        """Hydration must match what the engine actually queued.

        The TUI/engine ``_{i}`` versus ``_S{i}`` divergence is an open register
        entry; this seam must not add a third spelling.
        """
        assert FlowRunner()._find_terminal_nodes(_scatter_rows(2), 3) == [
            "CTRL_MERGE_S3"
        ]

    def test_a_linear_chain_terminates_at_its_last_node(self) -> None:
        rows = [
            {"Node_ID": "A", "Next_Node": "B", "Wait_For": "none"},
            {"Node_ID": "B", "Next_Node": "C", "Wait_For": "none"},
            {"Node_ID": "C", "Next_Node": "END", "Wait_For": "none"},
        ]
        assert FlowRunner()._find_terminal_nodes(rows, 0) == ["C_S0"]

    def test_an_empty_topology_names_nothing(self) -> None:
        """No invented fallback.

        ``_find_starting_nodes`` nominates ``OSINT_S{i}`` when it must seed
        *something* or nothing runs at all. There is no equivalent excuse on the
        output side: guessing which node produced the step's artifact is how E2
        behaved.
        """
        assert FlowRunner()._find_terminal_nodes([], 0) == []


class TestCaptureStepOutput:
    """E2 — the next step reads what the terminal node recorded."""

    def _complete_merge(
        self, broker_obj: LocalMessageBroker, node: str, produced: str
    ) -> None:
        broker_obj.inject_task(job_id=JOB, payload_path="/in.md", starting_node=node)
        task = broker_obj.fetch_and_lock_task("agent_1", FakeTopology({node: "none"}))
        assert task is not None
        broker_obj.route_task(
            row_id=int(task["id"]), job_id=JOB, next_node_str="END",
            new_payload_path=produced, status="completed", output_path=produced,
        )

    def test_the_merge_artifact_crosses_the_boundary(
        self, broker: LocalMessageBroker
    ) -> None:
        """E2's headline: the 426 KB document, not the 59-byte stub."""
        self._complete_merge(broker, "CTRL_MERGE_S0", "/dc/CTRL_MERGE_S0_merged.md")

        captured = FlowRunner()._capture_step_output(
            JOB, _scatter_rows(8), 0, broker
        )
        assert captured == "/dc/CTRL_MERGE_S0_merged.md"

    def test_a_newer_stub_on_disk_does_not_win(
        self, broker: LocalMessageBroker, tmp_path: Path
    ) -> None:
        """The exact live failure, reproduced against the filesystem.

        ``_handle_merge`` writes the artifact and the worker then writes the node's
        ledger stub, so the stub always has the newer mtime. The old glob sorted by
        mtime and therefore *always* chose the stub. Both files exist here, in the
        directory the glob used to search, and the recorded output must still win.
        """
        ledger_dir = get_datacenter_path("03_Agent_Ledgers", JOB)
        ledger_dir.mkdir(parents=True, exist_ok=True)
        artifact = ledger_dir / "CTRL_MERGE_S0_merged.md"
        artifact.write_text("x" * 4096, encoding="utf-8")
        stub = ledger_dir / "CTRL_MERGE_S0_93.md"
        stub.write_text("# CTRL_MERGE_S0\n\nMERGE: 8 sources merged.\n", encoding="utf-8")
        assert stub.stat().st_mtime >= artifact.stat().st_mtime

        self._complete_merge(broker, "CTRL_MERGE_S0", str(artifact))

        captured = FlowRunner()._capture_step_output(
            JOB, _scatter_rows(8), 0, broker
        )
        assert captured == str(artifact)
        assert Path(captured).stat().st_size > 1000, "the stub was handed on again"

    def test_another_step_s_artifact_is_not_picked_up(
        self, broker: LocalMessageBroker
    ) -> None:
        """The glob was scoped to the job directory, not the step.

        Step 2's lookup could therefore return a file step 1 wrote. Node ids carry
        the step suffix, so the queue read cannot.
        """
        self._complete_merge(broker, "CTRL_MERGE_S0", "/dc/step0_merged.md")
        self._complete_merge(broker, "CTRL_MERGE_S1", "/dc/step1_merged.md")

        runner = FlowRunner()
        assert runner._capture_step_output(JOB, _scatter_rows(2), 0, broker) == (
            "/dc/step0_merged.md"
        )
        assert runner._capture_step_output(JOB, _scatter_rows(2), 1, broker) == (
            "/dc/step1_merged.md"
        )

    def test_no_completed_terminal_returns_none(
        self, broker: LocalMessageBroker
    ) -> None:
        """Nothing is fabricated. The caller carries the old payload and says so.

        A returned path here would be a guess, and downstream logic *acts* on the
        payload it is handed — it would be fed to a model at real cost.
        """
        broker.inject_task(
            job_id=JOB, payload_path="/in.md", starting_node="CTRL_MERGE_S0"
        )
        assert (
            FlowRunner()._capture_step_output(JOB, _scatter_rows(8), 0, broker) is None
        )

    def test_a_stalled_terminal_returns_none(
        self, broker: LocalMessageBroker
    ) -> None:
        """A node claimed and never finished produced nothing.

        Track A gave stalls their own terminal status precisely so this case stops
        looking like success; the step boundary has to agree.
        """
        broker.inject_task(
            job_id=JOB, payload_path="/in.md", starting_node="CTRL_MERGE_S0"
        )
        task = broker.fetch_and_lock_task(
            "agent_1", FakeTopology({"CTRL_MERGE_S0": "none"})
        )
        assert task is not None  # left 'locked', i.e. stalled

        assert (
            FlowRunner()._capture_step_output(JOB, _scatter_rows(8), 0, broker) is None
        )

    def test_the_failure_is_logged_as_an_error(
        self, broker: LocalMessageBroker, caplog: pytest.LogCaptureFixture
    ) -> None:
        broker.inject_task(
            job_id=JOB, payload_path="/in.md", starting_node="CTRL_MERGE_S0"
        )
        with caplog.at_level(logging.ERROR):
            FlowRunner()._capture_step_output(JOB, _scatter_rows(8), 0, broker)

        assert any(
            "produced no recorded output" in r.message for r in caplog.records
        ), f"silent miss; records were {[r.message for r in caplog.records]}"

    def test_divergent_terminals_resolve_by_declared_order(
        self, broker: LocalMessageBroker
    ) -> None:
        """A DAG with two endpoints has no single output, so the choice is stated.

        Deterministic by topology order — never by completion time or mtime, or the
        same flow would hand the next step a different document on each run.
        """
        rows = [
            {"Node_ID": "ROOT", "Next_Node": "L1,L2", "Wait_For": "none"},
            {"Node_ID": "L1", "Next_Node": "END", "Wait_For": "none"},
            {"Node_ID": "L2", "Next_Node": "END", "Wait_For": "none"},
        ]
        runner = FlowRunner()
        declared = runner._find_terminal_nodes(rows, 0)
        assert set(declared) == {"L1_S0", "L2_S0"}

        # Complete them in the reverse of declared order, so completion time and
        # declaration order disagree.
        for node in reversed(declared):
            self._complete_merge(broker, node, f"/dc/{node}.md")

        captured = runner._capture_step_output(JOB, rows, 0, broker)
        assert captured == f"/dc/{declared[0]}.md"

    def test_divergent_terminals_are_reported(
        self, broker: LocalMessageBroker, caplog: pytest.LogCaptureFixture
    ) -> None:
        rows = [
            {"Node_ID": "ROOT", "Next_Node": "L1,L2", "Wait_For": "none"},
            {"Node_ID": "L1", "Next_Node": "END", "Wait_For": "none"},
            {"Node_ID": "L2", "Next_Node": "END", "Wait_For": "none"},
        ]
        runner = FlowRunner()
        for node in runner._find_terminal_nodes(rows, 0):
            self._complete_merge(broker, node, f"/dc/{node}.md")

        with caplog.at_level(logging.WARNING):
            runner._capture_step_output(JOB, rows, 0, broker)

        assert any("terminal nodes with output" in r.message for r in caplog.records)


class TestTheGlobIsGone:
    """E2 — the defective helper must not survive alongside its replacement.

    Two ways to answer one question is how the TUI and the engine came to disagree
    about node ids. Leaving ``_find_final_ledger_path`` in place would invite a
    future call site to pick the wrong one.
    """

    def test_the_mtime_glob_helper_no_longer_exists(self) -> None:
        assert not hasattr(FlowRunner, "_find_final_ledger_path")

    def test_neither_step_loop_globs_the_ledger_directory(self) -> None:
        for method in (FlowRunner.execute_flow, FlowRunner.resume_flow):
            source = inspect.getsource(method)
            assert 'glob("*.md")' not in source, method.__qualname__
            assert "_capture_step_output" in source, method.__qualname__


class TestMergeDoesNotRestateTheSessionLedger:
    """The merged document was more than half a verbatim second copy.

    ``_handle_merge`` includes its own ``payload_path`` as a section when that path
    is not already among the predecessors. Sound under "Preceding Node" routing,
    where it is the upstream document the lanes worked from.

    Under "Unified Ledger" routing it is the *session ledger* — an aggregate of every
    node's output, which already contains all of these predecessors. Measured on run
    ``job_20260902-132101-tjrd``: eight lanes totalled ~32 KB, the merged document
    came to 68 KB, and the log honestly reported nine distinct files. The count was
    never wrong; the content was doubled, and a downstream agent pays for every byte
    of it twice.
    """

    def test_the_session_ledger_is_omitted_when_predecessors_are_present(
        self, tmp_path: Path
    ) -> None:
        job = "merge_job"
        lanes = [
            _write(tmp_path / f"Lane{i}_S0_{i}.md", f"Lane {i} findings.")
            for i in range(1, 4)
        ]
        # The session ledger genuinely contains all of them, as in production.
        ledger = _write(
            tmp_path / "unified_session_ledger.md",
            "\n".join(f"Lane {i} findings." for i in range(1, 4)),
        )

        result = execute_deterministic_node(
            "CTRL_MERGE_S0",
            {"payload_path": ledger, "job_id": job},
            {"merge_mode": "structured"},
            lanes,
        )

        merged = Path(result.output_payload_path).read_text(encoding="utf-8")
        headings = [ln for ln in merged.splitlines() if ln.startswith("## Source:")]
        assert len(headings) == 3, f"expected the 3 lanes only, got {headings}"
        assert "## Source: unified_session_ledger" not in merged
        for i in range(1, 4):
            assert f"Lane {i} findings." in merged
            assert merged.count(f"Lane {i} findings.") == 1, (
                f"lane {i} appears more than once — the ledger was restated"
            )

    def test_a_non_ledger_primary_payload_is_still_included(
        self, tmp_path: Path
    ) -> None:
        """The omission is narrow on purpose.

        Only the session ledger is a superset of its own predecessors. Any other
        primary payload is genuine upstream context and dropping it would lose
        information — which would be a worse defect than the duplication.
        """
        job = "merge_job"
        lanes = [_write(tmp_path / "Lane1_S0_1.md", "Lane 1 findings.")]
        upstream = _write(tmp_path / "research_brief.md", "The original brief.")

        result = execute_deterministic_node(
            "CTRL_MERGE_S0",
            {"payload_path": upstream, "job_id": job},
            {"merge_mode": "structured"},
            lanes,
        )

        merged = Path(result.output_payload_path).read_text(encoding="utf-8")
        assert "## Source: research_brief" in merged
        assert "The original brief." in merged
        assert "## Source: Lane1_S0_1" in merged

    def test_the_session_ledger_is_kept_when_there_is_nothing_else(
        self, tmp_path: Path
    ) -> None:
        """A merge with no gathered predecessors must not produce an empty document.

        Omitting the only content available would turn a redundancy fix into data
        loss — the exact trade E1 was about.
        """
        job = "merge_job"
        ledger = _write(tmp_path / "unified_session_ledger.md", "The whole session.")

        result = execute_deterministic_node(
            "CTRL_MERGE_S0", {"payload_path": ledger, "job_id": job}, {}, []
        )

        merged = Path(result.output_payload_path).read_text(encoding="utf-8")
        assert "The whole session." in merged

    def test_the_log_message_names_the_destination(self, tmp_path: Path) -> None:
        """"Merged 8 sources" said nothing about *where*.

        Defect E2 was the next step reading a different file in the same directory,
        so the artifact's name is the load-bearing part of that line.
        """
        job = "merge_job"
        lanes = [_write(tmp_path / "Lane1_S0_1.md", "content")]

        result = execute_deterministic_node(
            "CTRL_MERGE_S0", {"payload_path": "", "job_id": job}, {}, lanes
        )

        assert "CTRL_MERGE_S0_merged.md" in result.log_message
        assert "1 distinct source(s)" in result.log_message
