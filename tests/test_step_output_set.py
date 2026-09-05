# ┌─────────────────────────────────────────────────────────────────────────────┐
# │  MACCREv2 Test Infrastructure — Requirement 30: a step's output is a set     │
# └─────────────────────────────────────────────────────────────────────────────┘
"""
tests/test_step_output_set.py
=============================
Real coverage for Requirement 30 — a step's output modelled as an ordered set —
and for the two Requirement 29 pieces it cannot be implemented without:
``GatherStrategy`` (29.2) and ``resolve_gather_strategy``'s ``Merge`` default (29.6).

WHY REQ 29's ENUM ARRIVED WITH REQ 30
-------------------------------------
30.3 and 30.4 are both phrased *"AND the step's Gather Strategy is ..."*. There is no
honest way to implement the clause that carries the amendment — 30.4, the refusal to
pick — without the thing it branches on. Pulling forward exactly the two pieces 30
depends on, and no more, keeps 29.3's launch-time validator and 29.4's per-lane
recording where they belong (tracker #11) rather than half-building them here.

THE BOUNDARY THIS FILE PINS, AND WHY IT IS A BOUNDARY
----------------------------------------------------
A Gather Strategy is a **scatter's** declaration about its own lanes. A step with no
``CTRL_SCATTER`` has no lanes and therefore no strategy, so 30.3/30.4 do not reach it.
That matters because the ``Merge`` default (29.6) would otherwise be applied to a plain
divergent DAG, which would then be refused for having no merge node — changing the
behaviour of topologies Requirement 30 says nothing about, in the name of implementing
it. ``TestAPlainDivergentDagIsUntouched`` exists to fail if that boundary ever moves by
accident instead of by amendment.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import pytest

from maccre_core.orchestration.deterministic_nodes import GatherStrategy
from maccre_core.orchestration.flow_engine import (
    DECLARED_TOPOLOGY_POSITION,
    FlowRunner,
    StepOutputSet,
    resolve_gather_strategy,
    step_declares_a_gather_strategy,
)
from maccre_core.orchestration.local_broker import LocalMessageBroker

JOB = "job_step_output_set"


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


def _complete(broker_obj: LocalMessageBroker, node: str, produced: str) -> None:
    """Drive one node to ``completed`` with a recorded ``output_path``.

    Deliberately goes through ``inject_task`` / ``fetch_and_lock_task`` /
    ``route_task`` rather than writing the row directly. ``output_path`` exists
    because defect E1 proved the row is the only durable record of what a node
    produced; a test that writes the row itself would not exercise the write that
    matters.
    """
    broker_obj.inject_task(job_id=JOB, payload_path="/in.md", starting_node=node)
    task = broker_obj.fetch_and_lock_task("agent_1", FakeTopology({node: "none"}))
    assert task is not None
    broker_obj.route_task(
        row_id=int(task["id"]), job_id=JOB, next_node_str="END",
        new_payload_path=produced, status="completed", output_path=produced,
    )


def _scatter_rows(lanes: int, gather: str | None = "CTRL_MERGE") -> list[dict[str, Any]]:
    """One scatter, N lanes, and optionally a gather node.

    ``gather=None`` is the shape Requirement 29 made legal and 19.4 forbade: lanes
    that terminate on their own with nothing collecting them.
    """
    agents = [f"Agent{i}" for i in range(1, lanes + 1)]
    rows: list[dict[str, Any]] = [
        {"Node_ID": "CTRL_SCATTER", "Next_Node": ",".join(agents), "Wait_For": "none"}
    ]
    if gather is None:
        rows.extend(
            {"Node_ID": a, "Next_Node": "END", "Wait_For": "none"} for a in agents
        )
        return rows
    rows.extend(
        {"Node_ID": a, "Next_Node": gather, "Wait_For": "none"} for a in agents
    )
    rows.append({"Node_ID": gather, "Next_Node": "END", "Wait_For": "|".join(agents)})
    return rows


# ── The value object ─────────────────────────────────────────────────────────


class TestStepOutputSetIsAnOrderedSet:
    """Req 30.1 — ordered by declared topology position, never completion time."""

    def test_the_ordering_is_declared_position(self) -> None:
        s = StepOutputSet(pairs=[("B_S0", "/b.md"), ("A_S0", "/a.md")])
        assert s.ordered_by == DECLARED_TOPOLOGY_POSITION

    def test_the_ordering_cannot_be_declared_by_the_caller(self) -> None:
        """``ordered_by`` is a property, not a field, and this is the reason.

        As a field with a default it could be constructed as
        ``StepOutputSet(pairs=..., ordered_by="completion_time")`` — a caller able to
        *state* an ordering it did not perform, which is the shape of every label
        defect in the register.
        """
        with pytest.raises(TypeError):
            StepOutputSet(pairs=[], ordered_by="completion_time")  # type: ignore[call-arg]

    def test_the_set_preserves_the_order_it_was_given(self) -> None:
        s = StepOutputSet(pairs=[("B_S0", "/b.md"), ("A_S0", "/a.md")])
        assert s.nodes() == ["B_S0", "A_S0"]
        assert s.paths() == ["/b.md", "/a.md"]

    def test_the_set_does_not_alias_the_callers_list(self) -> None:
        """The Oracle principles name mutating a caller's list as a bug pattern.

        This object exists to be a stable record of what a step produced, so a later
        reorder of the caller's list must not rewrite history.
        """
        original = [("A_S0", "/a.md"), ("B_S0", "/b.md")]
        s = StepOutputSet(pairs=original)
        original.reverse()
        assert s.nodes() == ["A_S0", "B_S0"]

    def test_length_is_the_number_of_outputs(self) -> None:
        assert len(StepOutputSet(pairs=[])) == 0
        assert len(StepOutputSet(pairs=[("A_S0", "/a.md")])) == 1
        assert len(StepOutputSet(pairs=[("A_S0", "/a.md"), ("B_S0", "/b.md")])) == 2


class TestTheDegenerateCase:
    """Req 30.2 — one terminal is the single-element case, not a special case."""

    def test_a_single_output_is_returned(self) -> None:
        s = StepOutputSet(pairs=[("CTRL_MERGE_S0", "/merged.md")])
        assert s.single() == "/merged.md"

    def test_e2s_behaviour_is_the_degenerate_case_not_a_branch(self) -> None:
        """The 426 KB merge, reached through the same call as everything else."""
        s = StepOutputSet(pairs=[("CTRL_MERGE_S0", "/dc/CTRL_MERGE_S0_merged.md")])
        assert len(s) == 1
        assert s.single().endswith("_merged.md")


class TestRefusalToChoose:
    """Req 30.4 — the load-bearing clause of the whole amendment."""

    def test_more_than_one_output_refuses_to_yield_a_single(self) -> None:
        s = StepOutputSet(pairs=[("A_S0", "/a.md"), ("B_S0", "/b.md")])
        with pytest.raises(ValueError, match="more than one"):
            s.single()

    def test_the_refusal_names_the_candidates(self) -> None:
        """A refusal that does not say which nodes it saw sends the author hunting."""
        s = StepOutputSet(pairs=[("A_S0", "/a.md"), ("B_S0", "/b.md")])
        with pytest.raises(ValueError) as exc:
            s.single()
        assert "A_S0" in str(exc.value)
        assert "B_S0" in str(exc.value)

    def test_eight_lanes_refuse_just_as_two_do(self) -> None:
        """Nothing about the refusal is arity-specific.

        Eight is the case that matters: one lane of eight is an eighth of the work
        wearing the whole step's name.
        """
        s = StepOutputSet(pairs=[(f"A{i}_S0", f"/a{i}.md") for i in range(8)])
        with pytest.raises(ValueError, match="more than one"):
            s.single()

    def test_an_empty_set_and_a_crowded_one_fail_differently(self) -> None:
        """Two different problems must not share one message.

        "several outputs and no instruction" is an authoring question; "no output at
        all" is a run failure. A caller matching on the message has to be able to
        tell them apart.
        """
        with pytest.raises(ValueError) as empty:
            StepOutputSet(pairs=[]).single()
        with pytest.raises(ValueError) as crowded:
            StepOutputSet(pairs=[("A_S0", "/a.md"), ("B_S0", "/b.md")]).single()

        assert "no output" in str(empty.value)
        assert "more than one" not in str(empty.value)
        assert "more than one" in str(crowded.value)


class TestTheEmptySet:
    """Req 30.5 — no silent fallback, exactly as defect E2's fix established."""

    def test_an_empty_set_reports_itself_empty(self) -> None:
        assert StepOutputSet(pairs=[]).is_empty() is True

    def test_a_populated_set_is_not_empty(self) -> None:
        assert StepOutputSet(pairs=[("A_S0", "/a.md")]).is_empty() is False

    def test_there_is_no_substitute(self) -> None:
        """The canary. E2's helper produced a plausible artifact rather than nothing.

        A no-fallback rule is otherwise an absence, and an absence cannot be
        asserted. Naming it means a future change that adds a fallback has to come
        through here and redden this test.
        """
        assert StepOutputSet(pairs=[]).substitute_guess() is None
        assert StepOutputSet(pairs=[("A_S0", "/a.md")]).substitute_guess() is None


class TestTheAuditRecord:
    """Req 30.6 — the set survives in a form that can be read after the run."""

    def test_the_record_states_its_ordering(self) -> None:
        record = StepOutputSet(pairs=[("A_S0", "/a.md")]).as_record()
        assert record["ordered_by"] == DECLARED_TOPOLOGY_POSITION

    def test_the_record_holds_every_pair_in_order(self) -> None:
        record = StepOutputSet(
            pairs=[("B_S0", "/b.md"), ("A_S0", "/a.md")]
        ).as_record()
        assert record["count"] == 2
        assert record["outputs"] == [
            {"node_id": "B_S0", "output_path": "/b.md"},
            {"node_id": "A_S0", "output_path": "/a.md"},
        ]

    def test_an_empty_set_records_as_empty_rather_than_absent(self) -> None:
        """An absent record and an empty one mean different things."""
        record = StepOutputSet(pairs=[]).as_record()
        assert record["count"] == 0
        assert record["outputs"] == []


# ── Gather Strategy (Req 29.2, 29.6) ─────────────────────────────────────────


class TestGatherStrategy:
    """Req 29.2 — the declaration that replaced 19.4's prohibition."""

    def test_the_three_strategies_exist(self) -> None:
        assert {s.value for s in GatherStrategy} == {"Merge", "Concat", "Ungathered"}

    def test_ungathered_exists_because_19_4_forbade_it(self) -> None:
        """The case the superseded requirement made impossible."""
        assert GatherStrategy.UNGATHERED.value == "Ungathered"


class TestResolveGatherStrategy:
    """Req 29.6 — saved MacroNodes keep the behaviour they were authored against."""

    def test_a_pre_amendment_config_defaults_to_merge(self) -> None:
        assert resolve_gather_strategy({"schema_version": "1.0"}) == "Merge"

    def test_an_absent_config_defaults_to_merge(self) -> None:
        assert resolve_gather_strategy(None) == "Merge"
        assert resolve_gather_strategy({}) == "Merge"

    def test_a_blank_declaration_defaults_to_merge(self) -> None:
        assert resolve_gather_strategy({"gather_strategy": "   "}) == "Merge"

    def test_each_strategy_resolves_to_itself(self) -> None:
        for strategy in GatherStrategy:
            assert (
                resolve_gather_strategy({"gather_strategy": strategy.value})
                == strategy.value
            )

    def test_resolution_is_case_insensitive(self) -> None:
        """The authoring surface is a text field; casing is not a declaration."""
        assert resolve_gather_strategy({"gather_strategy": "ungathered"}) == "Ungathered"
        assert resolve_gather_strategy({"gather_strategy": "MERGE"}) == "Merge"

    def test_an_unrecognised_strategy_is_refused_not_defaulted(self) -> None:
        """Principle 2. Defaulting ``"ungatherd"`` to ``Merge`` would gather lanes
        the author explicitly asked to be left alone — the approximately-correct
        value in its most expensive form.
        """
        with pytest.raises(ValueError, match="unrecognised"):
            resolve_gather_strategy({"gather_strategy": "ungatherd"})

    def test_the_refusal_names_the_valid_options(self) -> None:
        with pytest.raises(ValueError) as exc:
            resolve_gather_strategy({"gather_strategy": "Gather"})
        for strategy in GatherStrategy:
            assert strategy.value in str(exc.value)


class TestWhenAStrategyApplies:
    """A Gather Strategy is a scatter's declaration. No scatter, no strategy."""

    def test_a_scatter_step_declares_one(self) -> None:
        assert step_declares_a_gather_strategy(_scatter_rows(2)) is True

    def test_a_linear_step_does_not(self) -> None:
        rows = [
            {"Node_ID": "A", "Next_Node": "B", "Wait_For": "none"},
            {"Node_ID": "B", "Next_Node": "END", "Wait_For": "none"},
        ]
        assert step_declares_a_gather_strategy(rows) is False

    def test_a_divergent_dag_without_a_scatter_does_not(self) -> None:
        """Two endpoints is not the same fact as two lanes."""
        rows = [
            {"Node_ID": "ROOT", "Next_Node": "L1,L2", "Wait_For": "none"},
            {"Node_ID": "L1", "Next_Node": "END", "Wait_For": "none"},
            {"Node_ID": "L2", "Next_Node": "END", "Wait_For": "none"},
        ]
        assert step_declares_a_gather_strategy(rows) is False

    def test_detection_is_by_prefix(self) -> None:
        """Matching how ``_resolve_node_type`` classifies, so a suffixed scatter counts."""
        rows = [{"Node_ID": "CTRL_SCATTER_WIDE", "Next_Node": "A", "Wait_For": "none"}]
        assert step_declares_a_gather_strategy(rows) is True

    def test_empty_rows_declare_nothing(self) -> None:
        assert step_declares_a_gather_strategy([]) is False


# ── The engine's use of the set ──────────────────────────────────────────────


class TestCaptureRecordsTheSet:
    """Req 30.6 through the engine, including when it refuses to choose."""

    def test_a_single_terminal_step_records_a_one_element_set(
        self, broker: LocalMessageBroker
    ) -> None:
        _complete(broker, "CTRL_MERGE_S0", "/dc/CTRL_MERGE_S0_merged.md")
        runner = FlowRunner()

        assert runner._capture_step_output(
            JOB, _scatter_rows(8), 0, broker
        ) == "/dc/CTRL_MERGE_S0_merged.md"
        assert runner._step_output_sets[0].nodes() == ["CTRL_MERGE_S0"]

    def test_a_refused_step_still_records_what_it_refused_to_choose_from(
        self, broker: LocalMessageBroker
    ) -> None:
        """The most important assertion in this file.

        A refusal that records nothing is indistinguishable after the run from a step
        that produced nothing — and the two call for opposite responses. The set is
        the only place the refusal is legible once the log has scrolled.
        """
        rows = _scatter_rows(3, gather=None)
        runner = FlowRunner()
        for node in runner._find_terminal_nodes(rows, 0):
            _complete(broker, node, f"/dc/{node}.md")

        captured = runner._capture_step_output(
            JOB, rows, 0, broker, {"gather_strategy": "Ungathered"}
        )

        assert captured is None
        assert runner._step_output_sets[0].nodes() == [
            "Agent1_S0", "Agent2_S0", "Agent3_S0",
        ]

    def test_the_recorded_set_is_in_declared_order_not_completion_order(
        self, broker: LocalMessageBroker
    ) -> None:
        """Completion order is a race; declaration order is a fact.

        Completed in reverse, so the two orderings disagree and the assertion can
        only pass for one reason.
        """
        rows = _scatter_rows(3, gather=None)
        runner = FlowRunner()
        declared = runner._find_terminal_nodes(rows, 0)
        for node in reversed(declared):
            _complete(broker, node, f"/dc/{node}.md")

        runner._capture_step_output(
            JOB, rows, 0, broker, {"gather_strategy": "Ungathered"}
        )

        assert runner._step_output_sets[0].nodes() == declared


class TestUngatheredRefusesAtTheStepBoundary:
    """Req 30.4 in the engine, which is where it has to hold."""

    def test_an_ungathered_multi_lane_step_hands_nothing_forward(
        self, broker: LocalMessageBroker
    ) -> None:
        rows = _scatter_rows(8, gather=None)
        runner = FlowRunner()
        for node in runner._find_terminal_nodes(rows, 0):
            _complete(broker, node, f"/dc/{node}.md")

        assert runner._capture_step_output(
            JOB, rows, 0, broker, {"gather_strategy": "Ungathered"}
        ) is None

    def test_the_refusal_is_logged_at_error_with_the_count(
        self, broker: LocalMessageBroker, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Not a warning. The next step is about to reuse a stale payload."""
        rows = _scatter_rows(8, gather=None)
        runner = FlowRunner()
        for node in runner._find_terminal_nodes(rows, 0):
            _complete(broker, node, f"/dc/{node}.md")

        with caplog.at_level(logging.ERROR):
            runner._capture_step_output(
                JOB, rows, 0, broker, {"gather_strategy": "Ungathered"}
            )

        refusals = [
            r for r in caplog.records
            if "Ungathered" in r.message and r.levelno >= logging.ERROR
        ]
        assert refusals, f"silent refusal; records were {[r.message for r in caplog.records]}"

    def test_a_single_lane_ungathered_step_is_still_the_degenerate_case(
        self, broker: LocalMessageBroker
    ) -> None:
        """``Ungathered`` does not mean "refuse always".

        One lane has exactly one output, so there is nothing to choose between and
        nothing to refuse. Refusing here would break a legitimate one-lane scatter.
        """
        rows = _scatter_rows(1, gather=None)
        runner = FlowRunner()
        _complete(broker, "Agent1_S0", "/dc/Agent1_S0.md")

        assert runner._capture_step_output(
            JOB, rows, 0, broker, {"gather_strategy": "Ungathered"}
        ) == "/dc/Agent1_S0.md"


class TestMergeAndConcatPassTheGathersOutput:
    """Req 30.3 — the gather node's output *is* the step's output."""

    def test_a_declared_merge_passes_the_merge_node_output(
        self, broker: LocalMessageBroker
    ) -> None:
        _complete(broker, "CTRL_MERGE_S0", "/dc/CTRL_MERGE_S0_merged.md")
        runner = FlowRunner()

        assert runner._capture_step_output(
            JOB, _scatter_rows(8), 0, broker, {"gather_strategy": "Merge"}
        ) == "/dc/CTRL_MERGE_S0_merged.md"

    def test_a_declared_concat_passes_the_concat_node_output(
        self, broker: LocalMessageBroker
    ) -> None:
        _complete(broker, "CTRL_CONCAT_S0", "/dc/CTRL_CONCAT_S0_joined.md")
        runner = FlowRunner()

        assert runner._capture_step_output(
            JOB,
            _scatter_rows(4, gather="CTRL_CONCAT"),
            0,
            broker,
            {"gather_strategy": "Concat"},
        ) == "/dc/CTRL_CONCAT_S0_joined.md"

    def test_a_declared_merge_with_no_merge_output_refuses(
        self, broker: LocalMessageBroker, caplog: pytest.LogCaptureFixture
    ) -> None:
        """The unreachable gather, caught at runtime because 29.3 is not built yet.

        Declared ``Merge``, nothing merged, several lane outputs sitting there. Handing
        the next step one of them would be exactly the fraction-as-the-whole failure,
        and a declared gather that never happened is an authoring error either way.
        """
        rows = _scatter_rows(4, gather=None)
        runner = FlowRunner()
        for node in runner._find_terminal_nodes(rows, 0):
            _complete(broker, node, f"/dc/{node}.md")

        with caplog.at_level(logging.ERROR):
            captured = runner._capture_step_output(
                JOB, rows, 0, broker, {"gather_strategy": "Merge"}
            )

        assert captured is None
        assert any("none of its" in r.message for r in caplog.records)

    def test_an_unrecognised_strategy_refuses_rather_than_guessing(
        self, broker: LocalMessageBroker, caplog: pytest.LogCaptureFixture
    ) -> None:
        rows = _scatter_rows(4, gather=None)
        runner = FlowRunner()
        for node in runner._find_terminal_nodes(rows, 0):
            _complete(broker, node, f"/dc/{node}.md")

        with caplog.at_level(logging.ERROR):
            captured = runner._capture_step_output(
                JOB, rows, 0, broker, {"gather_strategy": "Gather"}
            )

        assert captured is None
        assert any("cannot be resolved" in r.message for r in caplog.records)


class TestAPlainDivergentDagIsUntouched:
    """The boundary. No scatter means no Gather Strategy, so Req 30.3/30.4 do not reach.

    This is a regression guard with a purpose: extending 30.4's refusal to a plain
    divergent DAG would change the behaviour of topologies the amendment does not
    describe, and would do it in the name of implementing the amendment. If that
    becomes the right call, it should arrive as a spec change that reddens this test
    deliberately — not as a side effect.
    """

    ROWS = [
        {"Node_ID": "ROOT", "Next_Node": "L1,L2", "Wait_For": "none"},
        {"Node_ID": "L1", "Next_Node": "END", "Wait_For": "none"},
        {"Node_ID": "L2", "Next_Node": "END", "Wait_For": "none"},
    ]

    def test_it_still_resolves_by_declared_order(
        self, broker: LocalMessageBroker
    ) -> None:
        runner = FlowRunner()
        declared = runner._find_terminal_nodes(self.ROWS, 0)
        for node in reversed(declared):
            _complete(broker, node, f"/dc/{node}.md")

        assert runner._capture_step_output(JOB, self.ROWS, 0, broker) == (
            f"/dc/{declared[0]}.md"
        )

    def test_the_choice_is_still_stated_as_a_choice(
        self, broker: LocalMessageBroker, caplog: pytest.LogCaptureFixture
    ) -> None:
        runner = FlowRunner()
        for node in runner._find_terminal_nodes(self.ROWS, 0):
            _complete(broker, node, f"/dc/{node}.md")

        with caplog.at_level(logging.WARNING):
            runner._capture_step_output(JOB, self.ROWS, 0, broker)

        assert any("a choice, not" in r.message for r in caplog.records)

    def test_a_merge_declaration_does_not_leak_onto_it(
        self, broker: LocalMessageBroker
    ) -> None:
        """Even handed a config, a step with no scatter has no strategy to apply."""
        runner = FlowRunner()
        declared = runner._find_terminal_nodes(self.ROWS, 0)
        for node in declared:
            _complete(broker, node, f"/dc/{node}.md")

        assert runner._capture_step_output(
            JOB, self.ROWS, 0, broker, {"gather_strategy": "Merge"}
        ) == f"/dc/{declared[0]}.md"
