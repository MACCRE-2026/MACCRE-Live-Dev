"""tests/test_ctrl_wait_and_ungathered_lanes.py
================================================
Requirement 29 (lanes may terminate without merging) and Requirement 32 (`CTRL_WAIT`).

Two requirements in one file because they are one idea seen from two ends. 29 says a lane
may end without being collected; 32 says something may collect from a named lane later, at
a point the author picks. Neither is expressible while a merge is mandatory per branch,
which is what Requirement 19.4 required and this amendment superseded.

The load-bearing test in here is not any single assertion about `evaluate_wait`'s return
value. It is `test_the_wait_handler_refuses_rather_than_passing_the_payload_through` and
its sibling in the spec file: **before this work, a `CTRL_WAIT` node in a topology passed
its payload through and reported `completed`.** That is defect F3's shape — success over a
hold that never happened — reached by a different route.
"""
from __future__ import annotations

import pytest

from maccre_core.orchestration.deterministic_nodes import (
    TERMINAL_LANE_STATES,
    DeterministicNodeType,
    GatherStrategy,
    _handle_wait,
    _resolve_node_type,
    evaluate_wait,
    execute_deterministic_node,
)
from maccre_core.orchestration.topology_graph import (
    build_edges,
    detect_temporal_paradox,
    terminal_outputs_for_step,
    validate_gather_reachability,
)

TWO_LANES = {"X.1": ["A"], "X.2": ["B"]}


# ── Requirement 29.3: a declared gather that cannot be reached ───────────────


class TestGatherReachability:
    """The negative case first — a validator that refuses everything is useless."""

    def test_ungathered_is_never_refused(self) -> None:
        """The entire point of Requirement 29. `Ungathered` requires no gather node."""
        report = validate_gather_reachability(
            TWO_LANES, gather_strategy="Ungathered", gather_nodes=[]
        )

        assert report.refused is False

    def test_merge_with_a_reachable_gather_is_not_refused(self) -> None:
        rows = [
            {"Node_ID": "A", "Next_Node": "CTRL_MERGE_S0"},
            {"Node_ID": "B", "Next_Node": "CTRL_MERGE_S0"},
            {"Node_ID": "CTRL_MERGE_S0", "Next_Node": "END"},
        ]
        report = validate_gather_reachability(
            TWO_LANES,
            gather_strategy="Merge",
            gather_nodes=["CTRL_MERGE_S0"],
            edges=build_edges(rows),
        )

        assert report.refused is False
        assert report.unreachable_lanes == []

    def test_merge_with_no_gather_node_at_all_refuses_and_names_every_lane(self) -> None:
        """29.3. Knowable with no edges: nothing can reach a node that does not exist."""
        report = validate_gather_reachability(
            TWO_LANES, gather_strategy="Merge", gather_nodes=[]
        )

        assert report.refused is True
        assert set(report.unreachable_lanes) == {"X.1", "X.2"}

    def test_concat_is_treated_the_same_as_merge(self) -> None:
        report = validate_gather_reachability(
            TWO_LANES, gather_strategy="Concat", gather_nodes=[]
        )

        assert report.refused is True

    def test_only_the_lane_that_cannot_reach_is_named(self) -> None:
        """Naming *every* unreachable lane means naming *only* them, too."""
        rows = [
            {"Node_ID": "A", "Next_Node": "CTRL_MERGE_S0"},
            {"Node_ID": "B", "Next_Node": "END"},
            {"Node_ID": "CTRL_MERGE_S0", "Next_Node": "END"},
        ]
        report = validate_gather_reachability(
            TWO_LANES,
            gather_strategy="Merge",
            gather_nodes=["CTRL_MERGE_S0"],
            edges=build_edges(rows),
        )

        assert report.unreachable_lanes == ["X.2"]

    def test_a_gather_reached_through_a_chain_counts_as_reachable(self) -> None:
        """A lane is a chain, not a single node. Reachability has to follow the edges."""
        rows = [
            {"Node_ID": "A", "Next_Node": "A2"},
            {"Node_ID": "A2", "Next_Node": "A3"},
            {"Node_ID": "A3", "Next_Node": "CTRL_MERGE_S0"},
            {"Node_ID": "CTRL_MERGE_S0", "Next_Node": "END"},
        ]
        report = validate_gather_reachability(
            {"X.1": ["A", "A2", "A3"]},
            gather_strategy="Merge",
            gather_nodes=["CTRL_MERGE_S0"],
            edges=build_edges(rows),
        )

        assert report.refused is False

    def test_a_cycle_in_the_edges_does_not_hang_the_check(self) -> None:
        """This runs immediately before launch, on hand-authored input."""
        rows = [
            {"Node_ID": "A", "Next_Node": "A2"},
            {"Node_ID": "A2", "Next_Node": "A"},
        ]
        report = validate_gather_reachability(
            {"X.1": ["A", "A2"]},
            gather_strategy="Merge",
            gather_nodes=["CTRL_MERGE_S0"],
            edges=build_edges(rows),
        )

        assert report.refused is True

    def test_it_refuses_to_answer_without_edges_rather_than_guessing(self) -> None:
        """A validator that guesses is worse than one that says it cannot tell.

        With gather nodes present, reachability past the first hop is not derivable from
        names. A wrong `reachable` would pass exactly the flow 19.4 existed to catch.
        """
        with pytest.raises(ValueError, match="edges"):
            validate_gather_reachability(
                TWO_LANES, gather_strategy="Merge", gather_nodes=["CTRL_MERGE_S0"]
            )

    def test_the_strategy_is_read_case_insensitively(self) -> None:
        """A hand-authored `"merge"` must not read as an unknown strategy."""
        assert (
            validate_gather_reachability(TWO_LANES, "merge", []).refused
            is validate_gather_reachability(TWO_LANES, "Merge", []).refused
        )

    def test_the_refusal_names_the_lanes_and_the_strategy(self) -> None:
        message = validate_gather_reachability(TWO_LANES, "Merge", []).message()

        assert "X.1" in message
        assert "X.2" in message
        assert "Merge" in message

    def test_a_clean_report_says_so_rather_than_returning_empty(self) -> None:
        assert "accounted for" in validate_gather_reachability(
            TWO_LANES, "Ungathered", []
        ).message()

    def test_the_strategy_names_match_the_declared_enum(self) -> None:
        """Asserted against `GatherStrategy`, never against string literals.

        Two spellings of the strategy set is how the TUI and the engine came to disagree
        about node ids.
        """
        for strategy in GatherStrategy:
            report = validate_gather_reachability(TWO_LANES, strategy.value, [])
            assert report.strategy == strategy.value


# ── Requirement 29.4: each ungathered lane records its own output ────────────


class TestTerminalOutputsForStep:
    """29.4 — recorded separately, and nothing invented when a lane recorded nothing."""

    def test_each_lane_contributes_its_own_terminal_output(self) -> None:
        outputs = terminal_outputs_for_step(
            lanes=TWO_LANES,
            recorded_outputs={"A@X.1": "/a.md", "B@X.2": "/b.md"},
            gather_strategy="Ungathered",
        )

        assert outputs.pairs == [("A@X.1", "/a.md"), ("B@X.2", "/b.md")]
        assert outputs.complete is True
        assert outputs.distinct is True

    def test_the_terminal_is_the_last_node_of_the_lane_not_the_first(self) -> None:
        """A lane is a chain. The scatter named its head; the output comes from its tail."""
        outputs = terminal_outputs_for_step(
            lanes={"X.1": ["A", "A2", "A3"]},
            recorded_outputs={"A@X.1": "/head.md", "A3@X.1": "/tail.md"},
            gather_strategy="Ungathered",
        )

        assert outputs.pairs == [("A3@X.1", "/tail.md")]

    def test_lane_order_is_declared_order(self) -> None:
        """Never completion order. The register records what ordering by mtime cost."""
        outputs = terminal_outputs_for_step(
            lanes={"X.3": ["C"], "X.1": ["A"], "X.2": ["B"]},
            recorded_outputs={"A@X.1": "/a.md", "B@X.2": "/b.md", "C@X.3": "/c.md"},
            gather_strategy="Ungathered",
        )

        assert [ref for ref, _p in outputs.pairs] == ["C@X.3", "A@X.1", "B@X.2"]

    def test_a_lane_that_recorded_nothing_is_reported_not_omitted(self) -> None:
        """A silently shorter list reads as a smaller scatter."""
        outputs = terminal_outputs_for_step(
            lanes=TWO_LANES,
            recorded_outputs={"A@X.1": "/a.md"},
            gather_strategy="Ungathered",
        )

        assert outputs.pairs == [("A@X.1", "/a.md")]
        assert outputs.lanes_without_output == ["X.2"]
        assert outputs.complete is False

    def test_an_empty_recorded_path_counts_as_no_output(self) -> None:
        """An empty path is not an artifact, and must not be passed on as one."""
        outputs = terminal_outputs_for_step(
            lanes={"X.1": ["A"]},
            recorded_outputs={"A@X.1": "   "},
            gather_strategy="Ungathered",
        )

        assert outputs.pairs == []
        assert outputs.lanes_without_output == ["X.1"]

    def test_two_lanes_naming_the_same_artifact_is_surfaced_not_de_duplicated(self) -> None:
        """Defect E1's exact signature: eight lanes all reporting the shared ledger.

        De-duplicating here would produce a set that looks smaller but complete, which is
        how `Merged 8 sources` came to be literally true over one file.
        """
        outputs = terminal_outputs_for_step(
            lanes=TWO_LANES,
            recorded_outputs={"A@X.1": "/shared.md", "B@X.2": "/shared.md"},
            gather_strategy="Ungathered",
        )

        assert len(outputs.pairs) == 2, "both lanes still reported; nothing was dropped"
        assert outputs.duplicated_paths == ["/shared.md"]
        assert outputs.distinct is False

    def test_a_bare_node_name_in_recorded_outputs_is_not_matched_approximately(self) -> None:
        """Refs are matched through the Req 31 render, exactly."""
        outputs = terminal_outputs_for_step(
            lanes={"X.1": ["A"]},
            recorded_outputs={"A": "/a.md"},
            gather_strategy="Ungathered",
        )

        assert outputs.pairs == []
        assert outputs.lanes_without_output == ["X.1"]

    def test_an_empty_lane_is_reported_rather_than_skipped(self) -> None:
        outputs = terminal_outputs_for_step(
            lanes={"X.1": []}, recorded_outputs={}, gather_strategy="Ungathered"
        )

        assert outputs.lanes_without_output == ["X.1"]

    def test_no_lanes_at_all_is_empty_and_complete(self) -> None:
        outputs = terminal_outputs_for_step(
            lanes={}, recorded_outputs={}, gather_strategy="Ungathered"
        )

        assert outputs.pairs == []
        assert outputs.complete is True

    @pytest.mark.parametrize("strategy", ["Merge", "Concat"])
    def test_a_collected_strategy_refuses_to_answer_this_question(self, strategy: str) -> None:
        """For Merge/Concat the step output is the gather's output — Requirement 30.3.

        Returning per-lane outputs here would give a caller a second, different answer to
        the same question, which is how two representations of one thing begin.
        """
        with pytest.raises(ValueError, match="30.3"):
            terminal_outputs_for_step(
                lanes=TWO_LANES, recorded_outputs={}, gather_strategy=strategy
            )

    def test_the_message_states_what_is_missing_and_what_collided(self) -> None:
        outputs = terminal_outputs_for_step(
            lanes={"X.1": ["A"], "X.2": ["B"], "X.3": ["C"]},
            recorded_outputs={"A@X.1": "/same.md", "B@X.2": "/same.md"},
            gather_strategy="Ungathered",
        )
        message = outputs.message()

        assert "X.3" in message
        assert "/same.md" in message


# ── Requirement 32.4/32.5/32.6: the wait decision ───────────────────────────


class TestEvaluateWaitReleases:
    """The positive case first."""

    def test_all_targets_produced_releases_the_wait(self) -> None:
        outcome = evaluate_wait(
            targets=["A@X.1", "B@X.2"],
            lane_states={"X.1": "completed", "X.2": "completed"},
            recorded_outputs={"A@X.1": "/a.md", "B@X.2": "/b.md"},
        )

        assert outcome.status == "released"
        assert outcome.decided_immediately is True

    def test_the_satisfying_targets_are_recorded_in_declared_order(self) -> None:
        """32.6 — so the record is reproducible rather than race-ordered."""
        outcome = evaluate_wait(
            targets=["B@X.2", "A@X.1"],
            lane_states={"X.1": "completed", "X.2": "completed"},
            recorded_outputs={"A@X.1": "/a.md", "B@X.2": "/b.md"},
        )

        assert outcome.satisfied_by == ["B@X.2", "A@X.1"]

    def test_a_target_that_produced_while_its_lane_still_runs_still_counts(self) -> None:
        """The output is the fact. Lane state only matters when there is no output."""
        outcome = evaluate_wait(
            targets=["A@X.1"],
            lane_states={"X.1": "running"},
            recorded_outputs={"A@X.1": "/a.md"},
        )

        assert outcome.status == "released"

    def test_the_release_message_names_the_targets(self) -> None:
        outcome = evaluate_wait(
            targets=["A@X.1"],
            lane_states={"X.1": "running"},
            recorded_outputs={"A@X.1": "/a.md"},
        )

        assert "A@X.1" in outcome.message()


class TestEvaluateWaitWaits:
    """`waiting` is the one outcome that legitimately needs another look later."""

    def test_a_live_lane_with_no_output_yet_is_waiting(self) -> None:
        outcome = evaluate_wait(
            targets=["A@X.1"], lane_states={"X.1": "running"}, recorded_outputs={}
        )

        assert outcome.status == "waiting"
        assert outcome.outstanding == ["A@X.1"]

    def test_waiting_is_the_only_outcome_not_decided_immediately(self) -> None:
        """The flag has to mean something. If everything were immediate it would be noise."""
        outcome = evaluate_wait(
            targets=["A@X.1"], lane_states={"X.1": "running"}, recorded_outputs={}
        )

        assert outcome.decided_immediately is False

    def test_a_partial_release_still_waits_and_keeps_what_it_has(self) -> None:
        outcome = evaluate_wait(
            targets=["A@X.1", "B@X.2"],
            lane_states={"X.1": "completed", "X.2": "running"},
            recorded_outputs={"A@X.1": "/a.md"},
        )

        assert outcome.status == "waiting"
        assert outcome.satisfied_by == ["A@X.1"]
        assert outcome.outstanding == ["B@X.2"]

    def test_an_unrecognised_lane_state_is_treated_as_live_not_finished(self) -> None:
        """Reading an unknown state as *finished* would turn ignorance into a refusal.

        That is the same guessing 32.5 forbids, pointed the other way.
        """
        outcome = evaluate_wait(
            targets=["A@X.1"], lane_states={"X.1": "some_future_state"}, recorded_outputs={}
        )

        assert outcome.status == "waiting"


class TestEvaluateWaitIsUnsatisfiable:
    """32.4 and 32.5 — the lesson defect F3 already paid for."""

    def test_a_finished_lane_that_never_produced_is_unsatisfiable(self) -> None:
        outcome = evaluate_wait(
            targets=["A@X.1"], lane_states={"X.1": "completed"}, recorded_outputs={}
        )

        assert outcome.status == "unsatisfiable"

    def test_it_is_never_reported_as_a_timeout_or_a_completion(self) -> None:
        """The status must distinguish "can never arrive" from "is slow"."""
        outcome = evaluate_wait(
            targets=["A@X.1"], lane_states={"X.1": "completed"}, recorded_outputs={}
        )

        assert outcome.status not in {"timeout", "completed", "released"}

    def test_it_is_decided_immediately_rather_than_waited_out(self) -> None:
        """32.5. The queue already contains the fact; a 3600 s budget is not needed to find it."""
        outcome = evaluate_wait(
            targets=["A@X.1"], lane_states={"X.1": "completed"}, recorded_outputs={}
        )

        assert outcome.decided_immediately is True

    @pytest.mark.parametrize("state", sorted(TERMINAL_LANE_STATES))
    def test_every_terminal_lane_state_makes_an_unproduced_target_unsatisfiable(
        self, state: str
    ) -> None:
        """Parameterised over the constant, so a new terminal state cannot be forgotten."""
        outcome = evaluate_wait(
            targets=["A@X.1"], lane_states={"X.1": state}, recorded_outputs={}
        )

        assert outcome.status == "unsatisfiable"

    def test_a_lane_state_is_read_case_insensitively(self) -> None:
        outcome = evaluate_wait(
            targets=["A@X.1"], lane_states={"X.1": "COMPLETED"}, recorded_outputs={}
        )

        assert outcome.status == "unsatisfiable"

    def test_a_target_on_a_lane_this_job_does_not_have_is_unsatisfiable(self) -> None:
        outcome = evaluate_wait(
            targets=["A@X.99"], lane_states={"X.1": "running"}, recorded_outputs={}
        )

        assert outcome.status == "unsatisfiable"
        assert "X.99" in outcome.message()

    def test_a_malformed_target_is_unsatisfiable_rather_than_skipped(self) -> None:
        """Parsed through the Requirement 31 seam, so the reason comes from there."""
        outcome = evaluate_wait(
            targets=["A"], lane_states={"X.1": "running"}, recorded_outputs={}
        )

        assert outcome.status == "unsatisfiable"
        assert any("tether-qualified" in reason for _t, reason in outcome.unsatisfiable_because)

    def test_no_targets_at_all_is_unsatisfiable_not_released(self) -> None:
        """Releasing a wait on nothing would be a success over no work."""
        outcome = evaluate_wait(targets=[], lane_states={}, recorded_outputs={})

        assert outcome.status == "unsatisfiable"

    def test_unsatisfiable_wins_over_waiting(self) -> None:
        """Once one target can never arrive, waiting for the rest awaits an impossible release."""
        outcome = evaluate_wait(
            targets=["A@X.1", "B@X.2"],
            lane_states={"X.1": "failed", "X.2": "running"},
            recorded_outputs={},
        )

        assert outcome.status == "unsatisfiable"

    def test_the_reason_names_the_lane_and_the_state_it_reached(self) -> None:
        outcome = evaluate_wait(
            targets=["A@X.1"], lane_states={"X.1": "failed"}, recorded_outputs={}
        )
        message = outcome.message()

        assert "X.1" in message
        assert "failed" in message


# ── The dispatch hole this closed ───────────────────────────────────────────


class TestCtrlWaitNoLongerSilentlyNoOps:
    """The most valuable part of Requirement 32's partial delivery.

    A declared-but-unimplemented control node that passes its payload through and reports
    `completed` is Principle 3, and the register already carries two instances of this
    same dispatch hole — one of which spent real inference on a node named `FAILED`.
    """

    def test_ctrl_wait_resolves_to_its_own_node_type(self) -> None:
        assert _resolve_node_type("CTRL_WAIT") is DeterministicNodeType.WAIT

    def test_a_suffixed_ctrl_wait_node_id_also_resolves(self) -> None:
        """Hydration appends `_S{idx}`, so the real node id is never the bare name."""
        assert _resolve_node_type("CTRL_WAIT_S0") is DeterministicNodeType.WAIT

    def test_the_legacy_det_prefix_resolves_too(self) -> None:
        assert _resolve_node_type("DET_WAIT") is DeterministicNodeType.WAIT

    def test_it_no_longer_falls_through_to_the_anchor_passthrough(self) -> None:
        """The defect, stated as a test. `_handle_anchor` returns the payload unchanged."""
        with pytest.raises(NotImplementedError):
            execute_deterministic_node("CTRL_WAIT_S0", {"payload_path": "/p.md", "job_id": "j"})

    def test_the_refusal_names_the_node_and_the_requirement(self) -> None:
        with pytest.raises(NotImplementedError) as caught:
            _handle_wait("CTRL_WAIT_S0", "/p.md", "job_1", {}, [])

        text = str(caught.value)
        assert "CTRL_WAIT_S0" in text
        assert "evaluate_wait" in text

    def test_declared_targets_are_named_in_the_refusal_path(self) -> None:
        """So an author who configured targets sees them echoed rather than swallowed."""
        with pytest.raises(NotImplementedError):
            _handle_wait("CTRL_WAIT_S0", "/p.md", "j", {"wait_for_targets": "A@X.1"}, [])

    def test_no_node_type_value_is_a_prefix_of_another(self) -> None:
        """What made `_resolve_node_type`'s longest-prefix comment true by luck.

        The loop iterated enum declaration order and returned the first match while the
        comment claimed longest-prefix. It is now sorted by length, and this test is what
        keeps the property from silently mattering: without it, adding `CTRL_MERGE_ALL`
        would be swallowed by `CTRL_MERGE` and nothing would say so.
        """
        values = [t.value for t in DeterministicNodeType]
        for value in values:
            others = [v for v in values if v != value]
            assert not [v for v in others if v.startswith(value)], (
                f"{value!r} is a prefix of another node type; dispatch now depends on "
                "longest-match ordering, so verify _resolve_node_type still picks right"
            )


# ── The waits-key hole Requirement 31 recorded and left open ────────────────


class TestParadoxDetectionValidatesTheWaiterToo:
    """Recorded against this task by Requirement 31, and closed here.

    `detect_temporal_paradox` validated wait *targets* but never the *keys*, so a
    malformed waiter was `setdefault`-ed straight into the precedence graph and could sit
    in a reported cycle under a name no lane contained — a refusal naming a node the
    author cannot go and look at.
    """

    def test_a_waiter_on_a_lane_the_topology_never_spawns_is_reported(self) -> None:
        report = detect_temporal_paradox(
            lanes={"X.1": ["A"]}, waits={"GHOST@X.9": ["A@X.1"]}
        )

        assert report.paradox is True
        assert report.unresolvable_waiters
        waiter, reason = report.unresolvable_waiters[0]
        assert waiter == "GHOST@X.9"
        assert "X.9" in reason

    def test_an_unqualified_waiter_is_reported(self) -> None:
        report = detect_temporal_paradox(lanes={"X.1": ["A", "B"]}, waits={"B": ["A@X.1"]})

        assert report.paradox is True
        assert any("tether-qualified" in r for _w, r in report.unresolvable_waiters)

    def test_a_bad_waiter_is_named_in_the_message(self) -> None:
        report = detect_temporal_paradox(
            lanes={"X.1": ["A"]}, waits={"GHOST@X.9": ["A@X.1"]}
        )

        assert "GHOST@X.9" in report.message()

    def test_a_bad_waiter_appears_in_participants(self) -> None:
        report = detect_temporal_paradox(
            lanes={"X.1": ["A"]}, waits={"GHOST@X.9": ["A@X.1"]}
        )

        assert "GHOST@X.9" in report.participants

    def test_a_bad_waiter_does_not_become_a_graph_vertex(self) -> None:
        """It must not be able to appear in a cycle under a name no lane contains."""
        report = detect_temporal_paradox(
            lanes={"X.1": ["A"]}, waits={"GHOST@X.9": ["A@X.1"]}
        )

        assert all("GHOST@X.9" not in cycle for cycle in report.cycles)

    def test_a_valid_waiter_is_still_not_reported(self) -> None:
        """The negative case. A checker that flags every waiter is useless."""
        report = detect_temporal_paradox(
            lanes={"X.1": ["A", "B"]}, waits={"B@X.1": ["A@X.1"]}
        )

        assert report.unresolvable_waiters == []
        assert report.paradox is False
