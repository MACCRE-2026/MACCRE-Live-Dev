# ┌─────────────────────────────────────────────────────────────────────────────┐
# │  MACCREv2 Test Infrastructure — Requirement 33 pre-launch validation        │
# └─────────────────────────────────────────────────────────────────────────────┘
"""
tests/test_prelaunch_validation.py
==================================
Real coverage for Requirement 33 — temporal-paradox detection and the total-sum
configuration readout.

``test_topological_semantic_spec.py`` holds one bootstrap assertion per acceptance
criterion, which is enough to make the spec executable and not enough to trust the
implementation. This file is the actual coverage: the cases the mechanism has to get
right, and the ones where getting it wrong would be silent.

WHY A PRECEDENCE GRAPH RATHER THAN FOUR DETECTORS
-------------------------------------------------
Requirement 33.2 enumerates four conditions, and two of them are the same thing once
both kinds of ordering constraint are written down:

    sequence edge   node[i] --> node[i+1]   execution within a lane is ordered
    wait edge       target  --> waiter      a waiter cannot precede its target

A lane ``[W, B]`` where ``W`` waits on ``B`` produces ``W -> B`` and ``B -> W``: a
two-node cycle. Two lanes waiting on each other produce the same shape with no
sequence edges. So one cycle detection covers both — **and covers three-lane and
longer cycles nobody enumerated**, which is the argument for deriving the check from
the model rather than from the list of examples.

The other two conditions are reference-validity errors, not ordering contradictions,
and are reported separately so a refusal can say which kind of wrong the topology is.
"""
from __future__ import annotations

from typing import Any

from maccre_core.orchestration.concurrency import MAX_SCATTER_AGENTS, SCATTER_HARD_CAP
from maccre_core.orchestration.flow_engine import total_sum_readout
from maccre_core.orchestration.topology_graph import detect_temporal_paradox


class TestParadoxDetectionCatchesRealShapes:
    """The cases Requirement 33.2 enumerates, plus the ones it implies."""

    def test_a_satisfiable_configuration_is_not_a_paradox(self) -> None:
        """The negative case first. A detector that fires on everything is useless."""
        report = detect_temporal_paradox(
            lanes={"X.1": ["A", "B"], "X.2": ["C"]},
            waits={"B@X.1": ["C@X.2"]},
        )
        assert report.paradox is False
        assert report.cycles == []
        assert report.unresolvable == []

    def test_an_upstream_wait_in_the_same_lane_is_fine(self) -> None:
        """Waiting on something *earlier* in your own lane is satisfiable.

        The mirror of the paradox case, and the one that would break if the
        same-lane check were written as "any same-lane wait is a paradox".
        """
        report = detect_temporal_paradox(
            lanes={"X.1": ["A", "WAIT_ON_A"]},
            waits={"WAIT_ON_A@X.1": ["A@X.1"]},
        )
        assert report.paradox is False

    def test_a_three_lane_cycle_is_caught(self) -> None:
        """Not enumerated in 33.2, and caught anyway.

        This is the payoff for modelling precedence instead of listing cases: a
        cycle of length three was never written down as a requirement and is
        detected by the same code.
        """
        report = detect_temporal_paradox(
            lanes={"X.1": ["A"], "X.2": ["B"], "X.3": ["C"]},
            waits={"A@X.1": ["B@X.2"], "B@X.2": ["C@X.3"], "C@X.3": ["A@X.1"]},
        )
        assert report.paradox is True
        assert len(report.cycles) >= 1
        assert {"A@X.1", "B@X.2", "C@X.3"} <= set(report.participants)

    def test_a_self_wait_is_a_paradox(self) -> None:
        """A node waiting on itself. Degenerate, and worth refusing explicitly."""
        report = detect_temporal_paradox(
            lanes={"X.1": ["A"]},
            waits={"A@X.1": ["A@X.1"]},
        )
        assert report.paradox is True

    def test_a_wait_on_a_lane_that_never_spawns_is_unresolvable(self) -> None:
        """33.2 case 3, and Principle 2 — an approximately-correct lane address.

        `X.9` in a two-lane scatter must be refused before launch. At runtime it
        would either no-op silently or resolve to something plausible.
        """
        report = detect_temporal_paradox(
            lanes={"X.1": ["A"], "X.2": ["B"]},
            waits={"A@X.1": ["GHOST@X.9"]},
        )
        assert report.paradox is True
        assert report.unresolvable
        waiter, target, reason = report.unresolvable[0]
        assert waiter == "A@X.1"
        assert target == "GHOST@X.9"
        assert "X.9" in reason

    def test_a_wait_on_a_node_absent_from_its_lane_is_unresolvable(self) -> None:
        """33.2 case 4 — right lane, wrong node."""
        report = detect_temporal_paradox(
            lanes={"X.1": ["A"], "X.2": ["B"]},
            waits={"A@X.1": ["NOT_THERE@X.2"]},
        )
        assert report.paradox is True
        assert any("absent" in reason for _w, _t, reason in report.unresolvable)

    def test_an_unqualified_reference_is_rejected_rather_than_guessed(self) -> None:
        """A bare node name has no lane, and guessing one would be Principle 2.

        Not enumerated in 33.2. Included because the alternative — assuming the
        waiter's own lane — is exactly the kind of plausible default that turns a
        typo into a silently different topology.
        """
        report = detect_temporal_paradox(
            lanes={"X.1": ["A", "B"]},
            waits={"A@X.1": ["B"]},
        )
        assert report.paradox is True
        assert any("tether-qualified" in reason for _w, _t, reason in report.unresolvable)

    def test_an_empty_configuration_is_not_a_paradox(self) -> None:
        report = detect_temporal_paradox(lanes={}, waits={})
        assert report.paradox is False

    def test_lanes_with_no_waits_are_never_a_paradox(self) -> None:
        """Sequence edges alone cannot cycle, since a lane is a list."""
        report = detect_temporal_paradox(
            lanes={"X.1": ["A", "B", "C"], "X.2": ["D", "E"]}, waits={}
        )
        assert report.paradox is False


class TestParadoxRefusalsAreActionable:
    """33.3 — name the participants. A generic failure is not a refusal."""

    def test_the_message_names_the_cycle_in_order(self) -> None:
        report = detect_temporal_paradox(
            lanes={"X.1": ["A"], "X.2": ["B"]},
            waits={"A@X.1": ["B@X.2"], "B@X.2": ["A@X.1"]},
        )
        message = report.message()
        assert "A@X.1" in message
        assert "B@X.2" in message
        assert "->" in message

    def test_the_message_explains_an_unresolvable_reference(self) -> None:
        report = detect_temporal_paradox(
            lanes={"X.1": ["A"]}, waits={"A@X.1": ["GHOST@X.7"]}
        )
        message = report.message()
        assert "GHOST@X.7" in message
        assert "X.7" in message

    def test_a_clean_configuration_says_so(self) -> None:
        report = detect_temporal_paradox(lanes={"X.1": ["A"]}, waits={})
        assert "No temporal paradox" in report.message()

    def test_participants_are_deterministic_across_runs(self) -> None:
        """The same refusal twice must read the same way.

        A set would make the message order arbitrary, which turns a diffable
        refusal into noise and makes a test asserting on it flaky.
        """
        args = {
            "lanes": {"X.1": ["A"], "X.2": ["B"], "X.3": ["C"]},
            "waits": {"A@X.1": ["B@X.2"], "B@X.2": ["C@X.3"], "C@X.3": ["A@X.1"]},
        }
        first = detect_temporal_paradox(**args).participants  # type: ignore[arg-type]
        second = detect_temporal_paradox(**args).participants  # type: ignore[arg-type]
        assert first == second

    def test_participants_are_unique(self) -> None:
        report = detect_temporal_paradox(
            lanes={"X.1": ["A"], "X.2": ["B"]},
            waits={"A@X.1": ["B@X.2", "GHOST@X.9"], "B@X.2": ["A@X.1"]},
        )
        assert len(report.participants) == len(set(report.participants))


class TestTotalSumReadout:
    """33.4–33.7 — describe the whole flow, from what will actually execute."""

    def test_an_empty_topology_still_returns_every_field(self) -> None:
        """An absent key and an empty one mean different things.

        Returning every key always means a consumer never has to distinguish
        "no lanes" from "this readout does not report lanes".
        """
        readout = total_sum_readout(topology_rows=[], step_index=0)
        for field in (
            "source",
            "step_index",
            "node_count",
            "lane_count",
            "lane_tether_ids",
            "nodes_per_lane",
            "gather_strategies",
            "waits",
            "cross_lane_routes",
            "terminal_node_count",
            "terminal_nodes",
            "expected_peak_concurrency",
        ):
            assert field in readout, f"readout is missing {field!r}"

    def test_hydrated_rows_are_labelled_hydrated(self) -> None:
        rows = [
            {"Node_ID": "CTRL_SCATTER_S0", "Next_Node": "A_S0"},
            {"Node_ID": "A_S0", "Next_Node": "END"},
        ]
        readout = total_sum_readout(topology_rows=rows, step_index=0)
        assert readout["source"] == "hydrated_topology"
        assert readout["node_count"] == 2

    def test_unhydrated_rows_are_reported_as_such_rather_than_labelled_hydrated(
        self,
    ) -> None:
        """**The clause that makes 33.6 more than a constant string.**

        The TUI once built node ids as ``NAME_{i}`` while the engine built
        ``NAME_S{i}``. A readout that labelled any input "hydrated" would be a
        second representation of the topology, free to drift from the executed one —
        in the one place whose entire job is to tell the operator the truth before
        they commit. So the label is checked against the suffix, not asserted.
        """
        rows = [{"Node_ID": "CTRL_SCATTER", "Next_Node": "A"}]
        readout = total_sum_readout(topology_rows=rows, step_index=0)
        assert readout["source"] == "unhydrated_topology_rows"

    def test_a_mixed_row_set_is_reported_as_unhydrated(self) -> None:
        """Partial hydration is not hydration."""
        rows = [{"Node_ID": "A_S0"}, {"Node_ID": "B"}]
        readout = total_sum_readout(topology_rows=rows, step_index=0)
        assert readout["source"] == "unhydrated_topology_rows"

    def test_the_suffix_check_respects_the_step_index(self) -> None:
        """Rows hydrated for step 0 are not hydrated for step 1."""
        rows = [{"Node_ID": "A_S0"}]
        assert total_sum_readout(rows, step_index=0)["source"] == "hydrated_topology"
        assert total_sum_readout(rows, step_index=1)["source"] == "unhydrated_topology_rows"

    def test_lanes_are_counted_from_tether_ids(self) -> None:
        rows = [
            {"Node_ID": "A_S0", "Tether_ID": "X.1"},
            {"Node_ID": "B_S0", "Tether_ID": "X.1"},
            {"Node_ID": "C_S0", "Tether_ID": "X.2"},
        ]
        readout = total_sum_readout(topology_rows=rows, step_index=0)
        assert readout["lane_count"] == 2
        assert readout["lane_tether_ids"] == ["X.1", "X.2"]
        assert readout["nodes_per_lane"] == {"X.1": 2, "X.2": 1}

    def test_a_linear_flow_has_no_lanes_and_a_peak_of_one(self) -> None:
        """An absent tether is not an error — a linear flow has one implicit lane."""
        rows = [{"Node_ID": "A_S0"}, {"Node_ID": "B_S0"}]
        readout = total_sum_readout(topology_rows=rows, step_index=0)
        assert readout["lane_count"] == 0
        assert readout["expected_peak_concurrency"] == 1

    def test_expected_peak_is_clamped_by_the_scatter_cap(self) -> None:
        """A 64-lane topology cannot expect 64-way concurrency.

        Written first as ``<= 8`` on the assumption that the readout would resolve the
        *lane count* as the pool's request. It does not, and it should not:
        ``resolve_scatter_cap(64)`` is ``SCATTER_HARD_CAP`` (12), while an unconfigured
        step is handed ``max_workers=None`` and peaks at ``MAX_SCATTER_AGENTS`` (8). The
        assertion is against the constant the run will actually honour rather than a
        literal, so a change to either ceiling cannot leave this test passing for the
        wrong reason.
        """
        rows = [
            {"Node_ID": f"A{i}_S0", "Tether_ID": f"X.{i}"} for i in range(64)
        ]
        readout = total_sum_readout(topology_rows=rows, step_index=0)
        assert readout["lane_count"] == 64
        assert readout["expected_peak_concurrency"] == MAX_SCATTER_AGENTS

    def test_the_peak_follows_the_pool_request_not_the_lane_count(self) -> None:
        """A step with 3 slotted agents peaks at 3 even across 64 lanes."""
        rows = [
            {"Node_ID": f"A{i}_S0", "Tether_ID": f"X.{i}"} for i in range(64)
        ]
        readout = total_sum_readout(topology_rows=rows, step_index=0, max_workers=3)
        assert readout["expected_peak_concurrency"] == 3

    def test_an_oversized_request_is_still_bounded_by_the_hard_cap(self) -> None:
        """The hard cap is the ceiling no configuration can raise."""
        rows = [
            {"Node_ID": f"A{i}_S0", "Tether_ID": f"X.{i}"} for i in range(64)
        ]
        readout = total_sum_readout(topology_rows=rows, step_index=0, max_workers=9999)
        assert readout["expected_peak_concurrency"] == SCATTER_HARD_CAP

    def test_the_peak_never_exceeds_the_number_of_lanes(self) -> None:
        """Two lanes cannot run 8 ways, whatever the pool would allow."""
        rows = [
            {"Node_ID": "A_S0", "Tether_ID": "X.1"},
            {"Node_ID": "B_S0", "Tether_ID": "X.2"},
        ]
        readout = total_sum_readout(topology_rows=rows, step_index=0, max_workers=8)
        assert readout["expected_peak_concurrency"] == 2

    def test_unbuilt_fields_are_empty_rather_than_fabricated(self) -> None:
        """Gather Strategy, waits and cross-lane routes are specified and unbuilt.

        Reporting a plausible default for a capability that does not exist would be
        Doctrine 3 in a readout — describing work that has not happened. The keys
        exist so the shape is stable; they stay empty until there is something true
        to put in them.
        """
        rows = [{"Node_ID": "A_S0", "Tether_ID": "X.1"}]
        readout = total_sum_readout(topology_rows=rows, step_index=0)
        assert readout["gather_strategies"] == {}
        assert readout["waits"] == {}
        assert readout["cross_lane_routes"] == []


# ── Task 4e: a lane and a gather scope are different facts ────────────────────


class TestLanesAreNotGatherScopes:
    """`lane_count` had been wrong twice for one 8-agent scatter, in opposite directions.

    Before per-lane tethers, one tether covered the whole scatter and the count was **1** —
    which, through `min(lane_count, cap)`, promised the operator **one thread for an 8-way
    run**. After per-lane tethers it was **9**, because the group tether carried by the
    scatter and its merge counted as a tenth lane.

    Requirement 33.5 asks for the number of Flow Lanes *and* their tether IDs. A lane is a
    tether with a parent; the group is the scope the lanes report into.
    """

    AGENTS = [f"AGENT_{c}" for c in "ABCDEFGH"]

    def _hierarchical_rows(self) -> list[dict[str, Any]]:
        """Scatter and merge on `X`, eight lanes on `X.1`..`X.8` — the shape 4c-3 emits."""
        rows: list[dict[str, Any]] = [
            {
                "Node_ID": "CTRL_SCATTER_S0",
                "Next_Node": ",".join(f"{a}_S0" for a in self.AGENTS),
                "Tether_ID": "X",
            }
        ]
        for i, agent in enumerate(self.AGENTS, start=1):
            rows.append(
                {"Node_ID": f"{agent}_S0", "Next_Node": "CTRL_MERGE_S0", "Tether_ID": f"X.{i}"}
            )
        rows.append({"Node_ID": "CTRL_MERGE_S0", "Next_Node": "END", "Tether_ID": "X"})
        return rows

    def _flat_rows(self) -> list[dict[str, Any]]:
        """One flat tether on every row — a hand-authored CSV, which the auto-wrap no
        longer produces but which can still be loaded."""
        rows = self._hierarchical_rows()
        for row in rows:
            row["Tether_ID"] = "scatter_abc12345"
        return rows

    def test_eight_lanes_are_counted_as_eight(self) -> None:
        readout = total_sum_readout(self._hierarchical_rows(), step_index=0)

        assert readout["lane_count"] == 8
        assert readout["lane_count_source"] == "lane_tethers"

    def test_the_group_tether_is_a_gather_scope_not_a_lane(self) -> None:
        readout = total_sum_readout(self._hierarchical_rows(), step_index=0)

        assert readout["lane_tether_ids"] == [f"X.{i}" for i in range(1, 9)]
        assert readout["gather_scopes"] == ["X"]
        assert "X" not in readout["lane_tether_ids"]

    def test_the_peak_is_no_longer_one_for_an_eight_way_run(self) -> None:
        """The defect this closes, stated as the number the operator sees."""
        readout = total_sum_readout(self._hierarchical_rows(), step_index=0, max_workers=8)

        assert readout["expected_peak_concurrency"] == 8

    def test_nodes_per_lane_covers_lanes_only(self) -> None:
        readout = total_sum_readout(self._hierarchical_rows(), step_index=0)

        assert readout["nodes_per_lane"] == {f"X.{i}": 1 for i in range(1, 9)}
        assert sum(readout["nodes_per_lane"].values()) == readout["node_count"] - 2

    def test_a_flat_topology_is_counted_from_the_scatter_fan_out(self) -> None:
        """**A second source of evidence, not a second definition.**

        A hand-authored CSV with one flat tether identifies no lane individually, so the
        tether column cannot answer the question. The scatter's fan-out width can, and it
        gives the same answer — 8 — so a legacy topology stops under-reporting its own
        concurrency. Before 4e this case reported `lane_count == 1` and a peak of 1.
        """
        readout = total_sum_readout(self._flat_rows(), step_index=0, max_workers=8)

        assert readout["lane_count"] == 8
        assert readout["lane_count_source"] == "scatter_fan_out"
        assert readout["expected_peak_concurrency"] == 8

    def test_a_flat_topology_reports_no_lane_tethers_rather_than_pretending(self) -> None:
        """Saying "8 lanes, none individually tethered" is the honest pair of facts."""
        readout = total_sum_readout(self._flat_rows(), step_index=0)

        assert readout["lane_tether_ids"] == []
        assert readout["gather_scopes"] == ["scatter_abc12345"]
        assert readout["lane_count"] == 8

    def test_a_linear_flow_still_reports_no_lanes_and_says_why(self) -> None:
        rows = [{"Node_ID": "A_S0"}, {"Node_ID": "B_S0"}]
        readout = total_sum_readout(rows, step_index=0)

        assert readout["lane_count"] == 0
        assert readout["lane_count_source"] == "none"
        assert readout["expected_peak_concurrency"] == 1

    def test_the_lane_count_source_is_always_one_of_the_three(self) -> None:
        """An unattributable count is a count nobody can check — the same reason
        `source` exists on this readout."""
        for rows in (self._hierarchical_rows(), self._flat_rows(), [{"Node_ID": "A_S0"}]):
            assert total_sum_readout(rows, step_index=0)["lane_count_source"] in (
                "lane_tethers", "scatter_fan_out", "none",
            )

    def test_lane_tethers_win_over_the_fan_out_when_both_are_present(self) -> None:
        """Per-lane tethers are the direct evidence; the fan-out is the fallback."""
        readout = total_sum_readout(self._hierarchical_rows(), step_index=0)

        assert readout["lane_count_source"] == "lane_tethers"

    def test_two_scatters_report_two_gather_scopes(self) -> None:
        rows = self._hierarchical_rows()
        rows.append({"Node_ID": "OTHER_S0", "Next_Node": "END", "Tether_ID": "Y.1"})

        readout = total_sum_readout(rows, step_index=0)

        assert readout["gather_scopes"] == ["X", "Y"]
        assert readout["lane_count"] == 9
