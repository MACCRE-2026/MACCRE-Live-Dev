"""Requirement 19 — nested scatter depth and the concurrent-lane ceiling.

Task 4g. Two constants had been declared in ``tether.py`` with **no consumer**:
``MAX_CONCURRENT_LANES`` (64) and ``NESTING_DEPTH_WARN_AT`` (2). Requirement 19 is
what they were declared for, and neither was read by anything.

The gap was reachable rather than theoretical, and both halves were measured before
anything was written:

* ``_get_macronode`` takes ``len(scatter_agents)`` straight from step config with no
  ceiling of its own. A probe with **70 slotted agents produced 70 lanes and 72
  topology rows, accepted in silence**, while the readout promised a peak of 12
  threads.
* Nesting to depth 2 is reachable **today, without a nested scatter node**: an
  operator who types a hierarchical value such as ``X.1`` into the Tether ID box gets
  lanes ``X.1.1``..``X.1.N`` from the auto-wrap. Nothing warned.

What Requirement 19 asks for, and which half lands where
-------------------------------------------------------

===== =========================================================== ================
Req   Asks                                                        Built by 4g?
===== =========================================================== ================
19.1  Flow_Engine SHALL **allow** nested scatter                  Yes — asserted
19.2  TopologyVisualizer shows a warning icon at 3 levels         Engine half only
19.3  Flow_Engine SHALL **reject** >64 concurrent lanes           Yes
19.4  Validate nested branches have a matching CTRL_MERGE         **SUPERSEDED**
19.5  Visualizer indents child lanes by depth                     TUI task
===== =========================================================== ================

19.2's icon and 19.5's indentation are TUI work. The engine's half is to *compute and
publish the depth*, which it now does as ``total_sum_readout["max_nesting_depth"]``, so
the visualizer reads the engine's number instead of counting dots in a label it drew
itself — the ``NAME_{i}`` / ``NAME_S{i}`` divergence, avoided in advance rather than
repaired afterwards.

**19.4 is superseded by Requirement 29.3 and is deliberately not built.** 19.4 demands
unconditionally that every nested branch have a corresponding ``CTRL_MERGE``; 29.1
allows a lane to terminate with no gather node at all, and 29.3 makes the refusal
conditional on the declared Gather Strategy. Building 19.4 as written would refuse
topologies Requirement 29 explicitly permits.

Depth warns, lanes refuse — and that asymmetry is the requirement's own
----------------------------------------------------------------------
19's user story asks to nest *"until complexity becomes unmanageable"* and for the
system to *"not artificially limit my authoring capability but naturally surface when I
have exceeded manageable complexity."* Surfacing is a warning. The lane ceiling is the
one refusal, because it alone bounds a resource.
"""
from __future__ import annotations

from typing import Any

import pytest

from maccre_core.orchestration.flow_engine import (
    FlowRunner,
    FlowStep,
    row_tethers,
    total_sum_readout,
)
from maccre_core.orchestration.tether import (
    MAX_CONCURRENT_LANES,
    NESTING_DEPTH_WARN_AT,
    count_lanes,
    deepest_tethers,
    depth,
    lane_tethers,
    max_nesting_depth,
)

# The substring that identifies Requirement 19.3's refusal, and nothing else. Kept as one
# constant because several tests must agree on what "the lane-limit error" means; two
# copies of a message fragment is how a test comes to pass against the wrong error.
LANE_LIMIT_TEXT = f"Exceeded maximum concurrent lane limit ({MAX_CONCURRENT_LANES})"
NESTING_TEXT = "Nested scatter depth"


class _Unregistered:
    """A macronode store that has nothing in it, so the auto-wrap path is taken."""

    def load(self, *_a: object, **_k: object) -> object:
        raise KeyError("not registered")


def _bare_runner() -> FlowRunner:
    """A ``FlowRunner`` with only what the auto-wrap needs.

    ``__new__`` rather than ``__init__`` deliberately: ``_get_macronode`` consults exactly
    two collaborators, and a fully constructed runner would drag a project directory into
    a test about arithmetic on tether strings.
    """
    runner = FlowRunner.__new__(FlowRunner)
    runner.macronode_store = _Unregistered()  # type: ignore[attr-defined]
    runner.global_store = _Unregistered()     # type: ignore[attr-defined]
    return runner


def _scatter_rows(count: int, tether: str | None = None) -> list[dict[str, Any]]:
    """Rows from the **real** auto-wrap for a *count*-wide scatter, hydrated for step 0."""
    cfg: dict[str, Any] = {"scatter_agents": [f"AGENT_{i:02d}" for i in range(count)]}
    if tether is not None:
        cfg["tether_id"] = tether
    macro = _bare_runner()._get_macronode("CTRL_SCATTER", step_config=cfg)
    rows: list[dict[str, Any]] = macro["topology_rows"]
    for row in rows:
        row["Node_ID"] = f"{row['Node_ID']}_S0"
    return rows


def _nested_rows() -> list[dict[str, Any]]:
    """A two-level topology: scatter X with lanes X.1/X.2, and a scatter inside X.1.

    Hand-built rather than auto-wrapped, because the auto-wrap synthesises **one** scatter
    per step — a genuinely nested pair of scatter nodes is an authored topology today.
    That is itself part of what 19.1 has to allow.
    """
    return [
        {"Node_ID": "CTRL_SCATTER_S0", "Next_Node": "A_S0,B_S0", "Tether_ID": "X"},
        {"Node_ID": "A_S0", "Next_Node": "CTRL_SCATTER_INNER_S0", "Tether_ID": "X.1"},
        {"Node_ID": "B_S0", "Next_Node": "CTRL_MERGE_S0", "Tether_ID": "X.2"},
        {"Node_ID": "CTRL_SCATTER_INNER_S0", "Next_Node": "C_S0,D_S0", "Tether_ID": "X.1"},
        {"Node_ID": "C_S0", "Next_Node": "CTRL_MERGE_INNER_S0", "Tether_ID": "X.1.1"},
        {"Node_ID": "D_S0", "Next_Node": "CTRL_MERGE_INNER_S0", "Tether_ID": "X.1.2"},
        {"Node_ID": "CTRL_MERGE_INNER_S0", "Next_Node": "CTRL_MERGE_S0", "Tether_ID": "X.1"},
        {"Node_ID": "CTRL_MERGE_S0", "Next_Node": "END", "Tether_ID": "X"},
    ]


@pytest.fixture()
def runner() -> FlowRunner:
    """A real ``FlowRunner`` against the per-test tmp datacenter from conftest.

    Pre-flight writes ``topology.csv`` and reads the roster, so it needs the real thing.
    """
    return FlowRunner(project_name="TEST_PROJECT")


class TestALaneIsDefinedInExactlyOnePlace:
    """4e settled "a lane is a tether with a parent" inside the readout. 4g needed the
    same rule at pre-flight, so it moved into ``tether.lane_tethers`` rather than being
    written twice.

    A second copy would not have been cosmetic: the ceiling would refuse one number while
    the readout displayed another, for the same topology, in the same modal.
    """

    def test_a_lane_is_a_tether_with_a_parent(self) -> None:
        assert lane_tethers(["X", "X.1", "X.2"]) == ["X.1", "X.2"]

    def test_a_gather_scope_is_not_a_lane(self) -> None:
        """The group tether is a scope. This is the 4e defect, pinned at the seam."""
        assert "X" not in lane_tethers(["X", "X.1", "X.2"])

    def test_a_nested_lane_is_still_a_lane(self) -> None:
        assert lane_tethers(["X.1", "X.1.1", "X.1.2"]) == ["X.1", "X.1.1", "X.1.2"]

    def test_a_flat_tether_names_no_lane(self) -> None:
        """Correct rather than a gap: the flat scheme never identified a lane."""
        assert lane_tethers(["scatter_84fe89ba"]) == []

    def test_lanes_are_distinct_and_in_first_seen_order(self) -> None:
        assert lane_tethers(["X.2", "X.1", "X.2"]) == ["X.2", "X.1"]

    def test_an_unusable_tether_is_skipped_not_raised(self) -> None:
        """This feeds a count; refusing a bad id *by name* is a validator's job."""
        assert lane_tethers(["X.1", "X@2", "X.3"]) == ["X.1", "X.3"]

    def test_the_readout_reports_through_the_shared_rule(self) -> None:
        """The number the operator reads and the number the ceiling tests are one number."""
        rows = _nested_rows()
        readout = total_sum_readout(rows, step_index=0)

        assert readout["lane_tether_ids"] == lane_tethers(row_tethers(rows))
        assert readout["lane_count"] == count_lanes(row_tethers(rows))


class TestCountLanesNoLongerCountsTheGatherScope:
    """``count_lanes`` counted **distinct tether ids** until 4g corrected it.

    Its docstring named Requirement 19.3's ceiling, so it was the function the limit would
    have been built on — and it would have re-introduced the exact defect 4e had just
    removed from the readout. Nothing consumed it, so no behaviour regressed; the
    definition was simply written before "a lane is a tether with a parent" was settled.
    """

    def test_the_group_tether_no_longer_inflates_the_count(self) -> None:
        """The whole tether column of an 8-lane scatter is 9 ids and 8 lanes."""
        column = ["X"] + [f"X.{i}" for i in range(1, 9)] + ["X"]

        assert len(set(column)) == 9  # what it used to answer
        assert count_lanes(column) == 8  # what a lane count is

    def test_the_ceiling_would_have_fired_one_lane_early(self) -> None:
        """Concretely: 64 real lanes plus their scope read as 65 under the old rule."""
        column = ["X"] + [f"X.{i}" for i in range(1, 65)]

        assert len(set(column)) == MAX_CONCURRENT_LANES + 1
        assert count_lanes(column) == MAX_CONCURRENT_LANES

    def test_a_flat_column_counts_no_lanes(self) -> None:
        """Changed 2026-09-06 (4g): this answered 1 while counting distinct ids."""
        assert count_lanes(["scatter_84fe89ba"] * 10) == 0

    def test_lanes_across_two_scatters_still_add_up(self) -> None:
        assert count_lanes([f"X.{i}" for i in range(1, 9)] + ["Y.1", "Y.2"]) == 10

    def test_it_agrees_with_lane_tethers_by_construction(self) -> None:
        for column in (["X", "X.1"], ["scatter_a"], [], ["X.1.1", "X.1", "X"]):
            assert count_lanes(column) == len(lane_tethers(column))


class TestNestingDepthIsMeasured:
    """The engine's half of 19.2. Counted in **separators**, the unit ``depth`` uses."""

    def test_a_flat_topology_is_depth_zero(self) -> None:
        assert max_nesting_depth(["scatter_84fe89ba"]) == 0

    def test_an_ordinary_scatter_is_depth_one(self) -> None:
        assert max_nesting_depth(["X", "X.1", "X.2"]) == 1

    def test_a_grandchild_is_depth_two_which_is_three_levels(self) -> None:
        """19.2's "3 levels (root -> child -> grandchild)" is 2 separators."""
        assert max_nesting_depth(["X", "X.1", "X.1.1"]) == 2
        assert max_nesting_depth(["X.1.1"]) == NESTING_DEPTH_WARN_AT

    def test_the_maximum_is_taken_not_the_last(self) -> None:
        assert max_nesting_depth(["X.1.1.1", "X.1", "X"]) == 3

    def test_no_tethers_is_depth_zero_rather_than_an_error(self) -> None:
        assert max_nesting_depth([]) == 0

    def test_one_unusable_id_cannot_make_a_topology_look_flat(self) -> None:
        assert max_nesting_depth(["X@1", "X.1.1"]) == NESTING_DEPTH_WARN_AT

    def test_the_deepest_tethers_are_named_so_a_warning_can_point_at_them(self) -> None:
        """A warning reporting only a number is noticed; one naming lanes is actionable."""
        assert deepest_tethers(["X", "X.1", "X.1.1", "X.1.2"]) == ["X.1.1", "X.1.2"]

    def test_deepest_tethers_are_distinct_and_in_first_seen_order(self) -> None:
        assert deepest_tethers(["X.2.1", "X.1.1", "X.2.1"]) == ["X.2.1", "X.1.1"]


class TestTheReadoutPublishesNesting:
    """So the visualizer reads the engine's number instead of deriving its own."""

    def test_the_readout_reports_the_depth(self) -> None:
        readout = total_sum_readout(_nested_rows(), step_index=0)

        assert readout["max_nesting_depth"] == 2

    def test_the_readout_names_the_deepest_lanes(self) -> None:
        readout = total_sum_readout(_nested_rows(), step_index=0)

        assert readout["deepest_lane_tethers"] == ["X.1.1", "X.1.2"]

    def test_the_deepest_list_holds_lanes_not_scopes(self) -> None:
        """At depth 1 the scatter's own tether is deepest-but-not-a-lane, so it is out."""
        readout = total_sum_readout(_scatter_rows(2), step_index=0)

        assert readout["max_nesting_depth"] == 1
        assert all(t not in readout["gather_scopes"] for t in readout["deepest_lane_tethers"])

    def test_the_readout_states_the_limit_rather_than_assuming_it_is_known(self) -> None:
        readout = total_sum_readout(_scatter_rows(2), step_index=0)

        assert readout["lane_limit"] == MAX_CONCURRENT_LANES

    def test_exceeds_lane_limit_agrees_with_the_count_it_is_derived_from(self) -> None:
        for width in (2, MAX_CONCURRENT_LANES, MAX_CONCURRENT_LANES + 1):
            readout = total_sum_readout(_scatter_rows(width), step_index=0)
            assert readout["exceeds_lane_limit"] is (
                readout["lane_count"] > MAX_CONCURRENT_LANES
            )

    def test_a_flow_within_the_limit_does_not_claim_to_exceed_it(self) -> None:
        readout = total_sum_readout(_scatter_rows(8), step_index=0)

        assert readout["exceeds_lane_limit"] is False

    def test_a_linear_flow_reports_depth_zero_and_no_breach(self) -> None:
        readout = total_sum_readout([{"Node_ID": "A_S0"}], step_index=0)

        assert readout["max_nesting_depth"] == 0
        assert readout["deepest_lane_tethers"] == []
        assert readout["exceeds_lane_limit"] is False


class TestTheAutoWrapStillHasNoCeilingOfItsOwn:
    """The measured starting point, kept as a test so it cannot quietly change.

    The auto-wrap deliberately does **not** refuse: by the time execution reaches it the
    operator has either overridden pre-flight or pre-flight did not run, and failing the
    build there would take their flow away after they explicitly chose to proceed.
    """

    def test_seventy_slotted_agents_still_produce_seventy_lanes(self) -> None:
        rows = _scatter_rows(70)

        assert count_lanes(row_tethers(rows)) == 70
        assert len(rows) == 72  # scatter + 70 lanes + merge

    def test_the_over_limit_run_is_recorded_at_error_level(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """An overridden 70-lane run must not read like a 4-lane one in the log."""
        with caplog.at_level("ERROR", logger="maccre_core.orchestration.flow_engine"):
            _scatter_rows(70)

        assert any(
            "over the limit" in r.message or "over the limit" in str(r.msg)
            for r in caplog.records
        )

    def test_a_run_within_the_limit_logs_no_such_error(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        with caplog.at_level("ERROR", logger="maccre_core.orchestration.flow_engine"):
            _scatter_rows(8)

        assert not any("over the limit" in str(r.msg) for r in caplog.records)


class TestTheLaneCeilingRefusesAtPreflight:
    """Requirement 19.3, at the seam that actually reaches the operator.

    ``preflight_check`` is wired: ``nexus_plex.action_launch_flow`` calls it, renders the
    report and gates launch on ``is_ok``. That distinguishes this from
    ``total_sum_readout``, which is still consumed by nothing.
    """

    @staticmethod
    def _lane_errors(report: Any) -> list[dict[str, str]]:
        return [
            i for i in report.issues
            if i["severity"] == "ERROR" and LANE_LIMIT_TEXT in i["detail"]
        ]

    def _check(self, runner: FlowRunner, width: int) -> Any:
        step = FlowStep(
            macronode_name="CTRL_SCATTER",
            config={"scatter_agents": [f"AGENT_{i:02d}" for i in range(width)]},
        )
        return runner.preflight_check([step])

    def test_one_lane_over_the_limit_is_refused(self, runner: FlowRunner) -> None:
        report = self._check(runner, MAX_CONCURRENT_LANES + 1)

        assert len(self._lane_errors(report)) == 1

    def test_exactly_the_limit_is_allowed(self, runner: FlowRunner) -> None:
        """The boundary, both sides, because an off-by-one here refuses a legal flow."""
        report = self._check(runner, MAX_CONCURRENT_LANES)

        assert self._lane_errors(report) == []

    def test_the_message_is_the_requirement_verbatim(self, runner: FlowRunner) -> None:
        """19.3 names the exact text, which an operator may have been told to expect."""
        report = self._check(runner, 70)

        assert self._lane_errors(report)[0]["detail"].startswith(LANE_LIMIT_TEXT)

    def test_the_refusal_carries_the_evidence_as_well_as_the_rule(
        self, runner: FlowRunner
    ) -> None:
        """"Over the limit" without "by how much, and where" is not actionable."""
        detail = self._lane_errors(self._check(runner, 70))[0]["detail"]

        assert "70 lanes" in detail
        assert "step 0" in detail

    def test_the_refusal_blocks_the_launch(self, runner: FlowRunner) -> None:
        """``is_ok`` is what ``nexus_plex`` gates on, so this is the operative assertion."""
        assert self._check(runner, 70).is_ok is False

    def test_a_normal_eight_lane_scatter_is_not_refused(self, runner: FlowRunner) -> None:
        """The shape every existing flow uses must be untouched by the ceiling."""
        assert self._lane_errors(self._check(runner, 8)) == []

    def test_a_linear_flow_is_not_refused(self, runner: FlowRunner) -> None:
        report = runner.preflight_check([FlowStep(macronode_name="CTRL_ANCHOR")])

        assert self._lane_errors(report) == []

    def test_lanes_are_counted_per_step_not_summed_across_the_flow(
        self, runner: FlowRunner
    ) -> None:
        """Steps run in sequence, so 40 + 40 is never 80 lanes at one instant.

        Summing would refuse a flow that never exceeds the ceiling at any moment, and
        19.3 says *concurrent*.
        """
        steps = [
            FlowStep(
                macronode_name="CTRL_SCATTER",
                config={"scatter_agents": [f"{p}{i:02d}" for i in range(40)]},
            )
            for p in ("A", "B")
        ]
        report = runner.preflight_check(steps)

        assert self._lane_errors(report) == []

    def test_the_offending_step_is_named_when_only_one_step_is_over(
        self, runner: FlowRunner
    ) -> None:
        steps = [
            FlowStep(
                macronode_name="CTRL_SCATTER",
                config={"scatter_agents": [f"A{i:02d}" for i in range(4)]},
            ),
            FlowStep(
                macronode_name="CTRL_SCATTER",
                config={"scatter_agents": [f"B{i:02d}" for i in range(70)]},
            ),
        ]
        errors = self._lane_errors(runner.preflight_check(steps))

        assert len(errors) == 1
        assert "step 1" in errors[0]["detail"]


class TestNestingIsAllowedAndOnlySurfaced:
    """Requirements 19.1 and 19.2's engine half.

    19.1 is a *permission*, which makes it awkward to test: the assertion has to be that
    no refusal mentions nesting, **not** that pre-flight produced no errors at all. A
    scatter over synthetic agent names legitimately fails the agent-directive check, and a
    test asserting ``issues == []`` would pass or fail for reasons that have nothing to do
    with nesting.
    """

    @staticmethod
    def _nesting_issues(report: Any, severity: str) -> list[dict[str, str]]:
        return [
            i for i in report.issues
            if i["severity"] == severity and NESTING_TEXT in i["detail"]
        ]

    def _nested_step_report(self, runner: FlowRunner) -> Any:
        """A hierarchical operator tether nests the auto-wrap's lanes: X.1 -> X.1.1, X.1.2.

        This is the reachable-today path, not a contrived one.
        """
        step = FlowStep(
            macronode_name="CTRL_SCATTER",
            config={"scatter_agents": ["AGENT_00", "AGENT_01"], "tether_id": "X.1"},
        )
        return runner.preflight_check([step])

    def test_nesting_is_never_an_error(self, runner: FlowRunner) -> None:
        """19.1 — permitted. The refusal, if any, must not be about nesting."""
        assert self._nesting_issues(self._nested_step_report(runner), "ERROR") == []

    def test_no_error_anywhere_mentions_depth_or_nesting(self, runner: FlowRunner) -> None:
        """Stronger than the above and independent of my own message wording."""
        errors = [
            i for i in self._nested_step_report(runner).issues
            if i["severity"] == "ERROR"
        ]

        assert not any(
            word in i["detail"].lower()
            for i in errors
            for word in ("nest", "depth", "too deep")
        )

    def test_depth_is_surfaced_as_a_warning(self, runner: FlowRunner) -> None:
        assert len(self._nesting_issues(self._nested_step_report(runner), "WARN")) == 1

    def test_the_warning_names_the_nested_tethers(self, runner: FlowRunner) -> None:
        detail = self._nesting_issues(self._nested_step_report(runner), "WARN")[0]["detail"]

        assert "X.1.1" in detail
        assert "X.1.2" in detail

    def test_the_warning_speaks_in_levels_matching_the_requirement(
        self, runner: FlowRunner
    ) -> None:
        """19.2 says "3 levels"; ``depth`` says 2. The operator-facing text uses levels."""
        detail = self._nesting_issues(self._nested_step_report(runner), "WARN")[0]["detail"]

        assert "3 levels" in detail

    def test_the_warning_says_it_is_not_a_block(self, runner: FlowRunner) -> None:
        """Otherwise a WARN in a report whose ERRORs block reads as a near-refusal."""
        detail = self._nesting_issues(self._nested_step_report(runner), "WARN")[0]["detail"]

        assert "not a block" in detail

    def test_an_unnested_scatter_raises_no_nesting_warning(
        self, runner: FlowRunner
    ) -> None:
        """Depth 1 is every ordinary scatter. Warning on it would make the notice noise."""
        step = FlowStep(
            macronode_name="CTRL_SCATTER",
            config={"scatter_agents": ["AGENT_00", "AGENT_01"]},
        )
        report = runner.preflight_check([step])

        assert self._nesting_issues(report, "WARN") == []

    def test_a_linear_flow_raises_no_nesting_warning(self, runner: FlowRunner) -> None:
        report = runner.preflight_check([FlowStep(macronode_name="CTRL_ANCHOR")])

        assert self._nesting_issues(report, "WARN") == []

    def test_a_deeply_nested_topology_is_still_only_warned_about(self) -> None:
        """Four levels is further than 19.2 contemplates and is still not a refusal."""
        assert max_nesting_depth(["X.1.1.1"]) == 3
        assert depth("X.1.1.1") >= NESTING_DEPTH_WARN_AT


class TestRequirement194IsSupersededNotForgotten:
    """19.4 demands every nested branch have a ``CTRL_MERGE``. Requirement 29 contradicts
    it: 29.1 lets a lane terminate with no gather node, and 29.3 makes the refusal
    conditional on the declared Gather Strategy.

    Recorded as a test rather than a comment so that reviving 19.4 has to argue with 29
    first, which is the argument that matters.
    """

    def test_a_lane_may_terminate_without_a_merge(self) -> None:
        """29.1, expressed against the tether model: a lane with no merge is well-formed."""
        rows = [
            {"Node_ID": "CTRL_SCATTER_S0", "Next_Node": "A_S0,B_S0", "Tether_ID": "X"},
            {"Node_ID": "A_S0", "Next_Node": "END", "Tether_ID": "X.1"},
            {"Node_ID": "B_S0", "Next_Node": "END", "Tether_ID": "X.2"},
        ]
        readout = total_sum_readout(rows, step_index=0)

        assert readout["lane_count"] == 2
        assert readout["exceeds_lane_limit"] is False

    def test_the_ungathered_strategy_exists_for_exactly_this(self) -> None:
        from maccre_core.orchestration.flow_engine import GatherStrategy

        assert "Ungathered" in [s.value for s in GatherStrategy]


class TestRowTethersIsTheOneReaderOfTheTetherColumn:
    """Both the readout and pre-flight need the tether column. Extracting it twice would
    let them disagree over something as small as a whitespace-only cell, which is enough
    to make a refusal and a readout report different counts for one topology.
    """

    def test_it_returns_distinct_tethers_in_first_seen_order(self) -> None:
        rows = [{"Tether_ID": "X.2"}, {"Tether_ID": "X.1"}, {"Tether_ID": "X.2"}]

        assert row_tethers(rows) == ["X.2", "X.1"]

    def test_a_blank_cell_is_not_a_lane_called_empty_string(self) -> None:
        assert row_tethers([{"Tether_ID": ""}, {"Tether_ID": "   "}, {}]) == []

    def test_no_rows_is_empty_rather_than_an_error(self) -> None:
        assert row_tethers([]) == []

    def test_it_does_not_referee_validity(self) -> None:
        """Reporting what the rows contain is this function's job; judging is downstream."""
        assert row_tethers([{"Tether_ID": "X@1"}]) == ["X@1"]
        assert lane_tethers(row_tethers([{"Tether_ID": "X@1"}])) == []
