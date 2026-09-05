# ┌─────────────────────────────────────────────────────────────────────────────┐
# │  MACCREv2 Test Infrastructure — payload cost becomes measurable                │
# └─────────────────────────────────────────────────────────────────────────────┘
"""
tests/test_payload_measurement.py
=================================
Phase 6.13 tracker #18. **The prerequisite of the step-boundary payload contract.**

WHY THIS HAD TO LAND FIRST
--------------------------
The 3b contract enlarges what crosses a step boundary. ``actual_cost`` derives from the
provider's own ``promptTokenCount`` (``maccre_router``), so the real bill **moves on its
own with no code change** — and ``_get_rates`` has a long-context tier at 200,000 tokens,
so past that the *rate* changes too.

Landing the contract first would therefore have raised the bill while leaving nothing able
to say by how much or where. That is a success claim over unmeasured work, which is the
one thing Era 3 has spent its length removing.

WHAT WAS AND WASN'T MISSING
---------------------------
The token counts were never missing. The two ``INFERENCE_COST`` telemetry writes have
always recorded real provider ``input_tokens`` and ``output_tokens`` — and always passed
**neither** ``session_id`` nor ``source_node``, so every row defaulted to ``""``. The data
was being collected into an unqueryable heap. **Only the labels were absent.**

What genuinely did not exist was payload size: no tokenizer anywhere, and ``task_queue``
held paths without ever calling ``stat()`` on one.

TWO DESIGN CHOICES THESE TESTS PIN
----------------------------------
**Attribution is set once per cycle, not passed per call.** ``swarm_worker`` has six
``router.generate(...)`` sites on one node's path. Threading two arguments through six
sites would make attribution forgettable at any one of them, and the failure would be
silent — a row with ``source_node=''`` is indistinguishable from a row written before
attribution existed. Instance state on the router is safe because a router is **per
worker**: ``swarm_worker.__init__`` does ``self.router = UniversalRouter()``, which is the
same fact the process-wide rate limiter relies on in the opposite direction.

**Bytes are stored; tokens are not.** Bytes come from one ``stat()`` call and are a fact.
Tokens would be that number divided by a heuristic, and storing both would put a derived
value beside its own input. The derivation lives in ``finops_tools.estimate_tokens``, where
it is already named an estimate.
"""
from __future__ import annotations

import inspect
from pathlib import Path
from typing import Any

import pytest

from maccre_core.maccre_router import UniversalRouter
from maccre_core.orchestration.broker_interface import MessageBroker
from maccre_core.orchestration.local_broker import LocalMessageBroker

JOB = "job_payload_measurement"


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


def _complete(
    broker_obj: LocalMessageBroker,
    node: str,
    produced: str = "/dc/out.md",
    payload_bytes: int = 0,
) -> int:
    """Drive one node to ``completed``, optionally recording a payload measurement."""
    broker_obj.inject_task(job_id=JOB, payload_path="/in.md", starting_node=node)
    task = broker_obj.fetch_and_lock_task("agent_1", FakeTopology({node: "none"}))
    assert task is not None
    row_id = int(task["id"])
    broker_obj.route_task(
        row_id=row_id, job_id=JOB, next_node_str="END",
        new_payload_path=produced, status="completed", output_path=produced,
        payload_bytes=payload_bytes,
    )
    return row_id


def _source_of(rel: str) -> str:
    return (Path(__file__).resolve().parent.parent / rel).read_text(encoding="utf-8")


# ── Attribution ──────────────────────────────────────────────────────────────


class TestTheRouterCanBeAttributed:
    def test_a_fresh_router_is_unattributed(self) -> None:
        """Empty string, not ``None``.

        The columns are ``NOT NULL DEFAULT ''`` and ``""`` already means
        "unattributed" in every row written before this existed. ``None`` would be a
        second spelling of one absence.
        """
        router = UniversalRouter()
        assert router._attr_session_id == ""
        assert router._attr_session_id == router._attr_source_node

    def test_attribution_can_be_set(self) -> None:
        router = UniversalRouter()
        router.set_call_attribution(session_id=JOB, source_node="AGENT_A_S0")
        assert router._attr_session_id == JOB
        assert router._attr_source_node == "AGENT_A_S0"

    def test_attribution_can_be_cleared_back_to_unattributed(self) -> None:
        """A worker reused across nodes must not carry the previous node's label."""
        router = UniversalRouter()
        router.set_call_attribution(session_id=JOB, source_node="AGENT_A_S0")
        router.set_call_attribution()
        assert router._attr_session_id == ""
        assert router._attr_source_node == ""

    def test_none_normalises_to_empty_rather_than_reaching_the_column(self) -> None:
        router = UniversalRouter()
        router.set_call_attribution(session_id=None, source_node=None)  # type: ignore[arg-type]
        assert router._attr_session_id == ""
        assert router._attr_source_node == ""

    def test_two_routers_do_not_share_attribution(self) -> None:
        """The whole basis for using instance state instead of a lock.

        A router is per worker — ``swarm_worker.__init__`` constructs its own — so
        eight concurrent lanes hold eight routers and cannot overwrite one another.
        If this ever became shared state, this test is where it would show up.
        """
        a, b = UniversalRouter(), UniversalRouter()
        a.set_call_attribution(session_id="job_a", source_node="A_S0")
        b.set_call_attribution(session_id="job_b", source_node="B_S0")
        assert a._attr_session_id == "job_a"
        assert b._attr_session_id == "job_b"


class TestBothInferenceCostSitesAreAttributed:
    """Two sites logging one event type have drifted before, so both are asserted."""

    def _router_source(self) -> str:
        return _source_of("maccre_core/maccre_router.py")

    def test_every_inference_cost_write_passes_a_session_id(self) -> None:
        source = self._router_source()
        occurrences = source.count('action_type="INFERENCE_COST"')
        assert occurrences == 2, f"expected 2 INFERENCE_COST sites, found {occurrences}"
        assert source.count("session_id=self._attr_session_id") == occurrences

    def test_every_inference_cost_write_passes_a_source_node(self) -> None:
        source = self._router_source()
        assert source.count("source_node=self._attr_source_node") == 2

    def test_the_worker_sets_attribution_once_per_cycle(self) -> None:
        """Set from the claimed task, so it cannot disagree with the row being worked."""
        source = _source_of("maccre_core/orchestration/swarm_worker.py")
        assert (
            "self.router.set_call_attribution(session_id=job_id, source_node=current_node)"
            in source
        )

    def test_attribution_is_set_before_anything_in_the_cycle_can_infer(self) -> None:
        """Order matters, but the axis is **execution order inside the cycle**.

        Written first against textual position in the whole file, which failed — and
        the failure was the test's fault, not the code's. Four ``router.generate(...)``
        sites sit *textually earlier* than ``execute_cycle`` because they live in
        helper methods defined above it: ``_run_interactive_diamond_loop`` and
        ``_apply_triple_index_search``. Both are **called from** the cycle, after
        attribution is set, so runtime order was correct all along.

        Recorded rather than quietly corrected, because "file position implies
        execution order" is a plausible-looking premise that would have kept passing
        for the wrong reason if the code had happened to satisfy it.

        The real property: within ``execute_cycle``'s own body, attribution is set
        before any inference can be reached — whether inline or through a helper.
        """
        source = _source_of("maccre_core/orchestration/swarm_worker.py")
        cycle = source[source.index("def execute_cycle("):]

        set_at = cycle.index("self.router.set_call_attribution(")
        for reaches_inference in (
            "self.router.generate(",
            "self._run_interactive_diamond_loop(",
            "self._apply_triple_index_search(",
        ):
            assert set_at < cycle.index(reaches_inference), reaches_inference


# ── Payload size ─────────────────────────────────────────────────────────────


class TestThePayloadSizeColumn:
    def test_the_column_exists(self, broker: LocalMessageBroker) -> None:
        conn = broker._get_conn()
        cols = {row[1] for row in conn.execute("PRAGMA table_info(task_queue)").fetchall()}
        assert "payload_bytes" in cols

    def test_a_measurement_is_recorded(self, broker: LocalMessageBroker) -> None:
        row_id = _complete(broker, "AGENT_A_S0", payload_bytes=68_000)
        conn = broker._get_conn()
        value = conn.execute(
            "SELECT payload_bytes FROM task_queue WHERE id = ?", (row_id,)
        ).fetchone()[0]
        assert value == 68_000

    def test_an_unmeasured_node_records_zero(self, broker: LocalMessageBroker) -> None:
        row_id = _complete(broker, "AGENT_B_S0")
        conn = broker._get_conn()
        value = conn.execute(
            "SELECT payload_bytes FROM task_queue WHERE id = ?", (row_id,)
        ).fetchone()[0]
        assert value == 0

    def test_zero_does_not_erase_an_existing_measurement(
        self, broker: LocalMessageBroker
    ) -> None:
        """The don't-blank rule, and the reason it is not merely defensive.

        ``0`` means *not measured*. A later caller that simply did not measure must not
        erase a reading an earlier one took — the same rule ``output_path`` follows,
        and for the same reason: defect E1 was a real value destroyed by a caller that
        had nothing better to put there.
        """
        row_id = _complete(broker, "AGENT_C_S0", payload_bytes=1234)
        broker.route_task(
            row_id=row_id, job_id=JOB, next_node_str="END",
            new_payload_path="/dc/again.md", status="completed", payload_bytes=0,
        )
        conn = broker._get_conn()
        value = conn.execute(
            "SELECT payload_bytes FROM task_queue WHERE id = ?", (row_id,)
        ).fetchone()[0]
        assert value == 1234

    def test_a_later_measurement_replaces_an_earlier_one(
        self, broker: LocalMessageBroker
    ) -> None:
        """Non-zero overwrites. A re-queued node read a different payload."""
        row_id = _complete(broker, "AGENT_D_S0", payload_bytes=1000)
        broker.route_task(
            row_id=row_id, job_id=JOB, next_node_str="END",
            new_payload_path="/dc/again.md", status="completed", payload_bytes=2000,
        )
        conn = broker._get_conn()
        value = conn.execute(
            "SELECT payload_bytes FROM task_queue WHERE id = ?", (row_id,)
        ).fetchone()[0]
        assert value == 2000


class TestTheColumnHasAReader:
    """A schema column with no consumer is the ``--smart`` shape, found three times now."""

    def test_measurements_are_readable_by_node(self, broker: LocalMessageBroker) -> None:
        _complete(broker, "AGENT_A_S0", payload_bytes=100)
        _complete(broker, "AGENT_B_S0", payload_bytes=200)
        assert broker.get_payload_bytes_by_node(JOB) == {
            "AGENT_A_S0": 100,
            "AGENT_B_S0": 200,
        }

    def test_unmeasured_nodes_are_omitted_not_reported_as_zero(
        self, broker: LocalMessageBroker
    ) -> None:
        """Including them would put "not measured" and "measured empty" in one bucket."""
        _complete(broker, "AGENT_A_S0", payload_bytes=100)
        _complete(broker, "AGENT_B_S0")  # unmeasured
        result = broker.get_payload_bytes_by_node(JOB)
        assert result == {"AGENT_A_S0": 100}
        assert "AGENT_B_S0" not in result

    def test_another_job_is_not_included(self, broker: LocalMessageBroker) -> None:
        _complete(broker, "AGENT_A_S0", payload_bytes=100)
        broker.inject_task(job_id="other_job", payload_path="/in.md", starting_node="X_S0")
        assert set(broker.get_payload_bytes_by_node(JOB)) == {"AGENT_A_S0"}

    def test_a_job_with_no_measurements_reads_empty(
        self, broker: LocalMessageBroker
    ) -> None:
        """Empty rather than raising: a flow that recorded nothing is a real answer."""
        assert broker.get_payload_bytes_by_node("never_ran") == {}


class TestTheInterfaceAndTheMockAgree:
    """Three declarations of one signature. They have drifted before."""

    def test_the_abc_declares_the_parameter(self) -> None:
        sig = inspect.signature(MessageBroker.route_task)
        assert "payload_bytes" in sig.parameters
        assert sig.parameters["payload_bytes"].default == 0

    def test_the_concrete_broker_matches(self) -> None:
        sig = inspect.signature(LocalMessageBroker.route_task)
        assert sig.parameters["payload_bytes"].default == 0

    def test_the_mock_matches(self) -> None:
        from tests.mocks.mock_broker import MockMessageBroker

        sig = inspect.signature(MockMessageBroker.route_task)
        assert sig.parameters["payload_bytes"].default == 0

    def test_the_mock_honours_the_dont_blank_rule(self) -> None:
        """A mock that blanked it would let a test pass against behaviour the real
        broker does not have, which is the only thing a mock can get seriously wrong.
        """
        source = _source_of("tests/mocks/mock_broker.py")
        assert "if payload_bytes:" in source


class TestTheWorkerMeasuresWhatItWasGiven:
    def _worker_source(self) -> str:
        return _source_of("maccre_core/orchestration/swarm_worker.py")

    def test_the_size_comes_from_a_stat_call(self) -> None:
        assert "Path(payload_path).stat().st_size" in self._worker_source()

    def test_an_unreadable_payload_does_not_fail_the_node(self) -> None:
        """A missing payload is reported by the reader, not by the measurer."""
        source = self._worker_source()
        start = source.index("payload_bytes: int = 0")
        body = source[start : start + 900]
        assert "except OSError:" in body

    def test_the_measurement_is_taken_before_execution(self) -> None:
        """Not re-measured at route time.

        By then the Targeted Filter branch may have rewritten ``payload_path``, so
        sizing it again would answer a different question under the same column name.
        """
        source = self._worker_source()
        measured_at = source.index("payload_bytes: int = 0")
        targeted_filter_at = source.index("PayloadMode.TARGETED_FILTER")
        assert measured_at < targeted_filter_at

    def test_the_measurement_reaches_route_task(self) -> None:
        assert "payload_bytes=payload_bytes," in self._worker_source()
