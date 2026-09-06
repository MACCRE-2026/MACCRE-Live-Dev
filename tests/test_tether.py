"""tests/test_tether.py
=======================
The one tether seam (task 4b of the Era 3 tracker).

Most of this file exists to pin **one** property, and the rest follows from it:

    for every tether ID already on disk, lane_group(t) == t

That is what makes moving the fan-in gate from *tether equality* to *same lane group*
a no-op for every saved topology, and it is the reason this change is a migration
rather than a break. `TestLaneGroupIsBackwardCompatible` is the group that would fail
if that property were lost, and it is the most load-bearing group in the file.

The second thing pinned here is that a tether ID cannot collide with another seam's
separator. `topology_graph` parses `NODE@TETHER`, joins lineage with `>`, and splits
routing targets on `,` and `|`. A tether containing any of those makes a reference to
that lane unparseable, so they are refused with the reason naming the character.
"""
from __future__ import annotations

import pytest

from maccre_core.orchestration.tether import (
    FORBIDDEN_IN_TETHER_ID,
    MAX_CONCURRENT_LANES,
    NESTING_DEPTH_WARN_AT,
    ROOT_TETHER_IDS,
    TETHER_LEVEL_SEPARATOR,
    TetherIdError,
    child_tether_ids,
    count_lanes,
    depth,
    in_gather_scope,
    is_descendant_of,
    is_hierarchical,
    lane_group,
    lanes_by_group,
    level_count,
    root_tether_id,
    validate_tether_id,
)
from maccre_core.orchestration.topology_graph import (
    FLOW_VECTOR_SEPARATOR,
    TETHER_SEPARATOR,
    parse_tether_qualified_ref,
)

#: Every tether ID format that exists on disk today. The engine's digest form, the
#: TUI's counter form, and a hand-typed one.
LEGACY_TETHER_IDS = ["scatter_ab12cd34", "scatter_84fe89ba", "tether_a", "tether_b", "my tether"]


# ── The property the whole migration rests on ────────────────────────────────


class TestLaneGroupIsBackwardCompatible:
    """`lane_group(t) == t` for every id already saved, so the gate change is a no-op.

    The fan-in gate currently matches on tether equality. It is moving to "same lane
    group". If any legacy id returned something other than itself, that move would put
    a scatter and its merge in different scopes — which is the named Principle 2
    incident: the gather gate could never open and an 8-lane run deadlocked.
    """

    @pytest.mark.parametrize("legacy", LEGACY_TETHER_IDS)
    def test_a_legacy_flat_id_is_its_own_lane_group(self, legacy: str) -> None:
        assert lane_group(legacy) == legacy

    @pytest.mark.parametrize("legacy", LEGACY_TETHER_IDS)
    def test_a_legacy_flat_id_is_not_hierarchical(self, legacy: str) -> None:
        assert is_hierarchical(legacy) is False

    @pytest.mark.parametrize("legacy", LEGACY_TETHER_IDS)
    def test_a_legacy_flat_id_is_depth_zero(self, legacy: str) -> None:
        assert depth(legacy) == 0

    def test_equality_and_same_lane_group_agree_on_a_legacy_scatter(self) -> None:
        """The gate change, stated as the test that proves it changes nothing.

        A legacy 8-lane scatter writes one tether to the scatter, all eight lanes and
        the merge. Under equality the merge collects all of them; under lane-group
        matching it must collect exactly the same set.
        """
        merge_tether = "scatter_84fe89ba"
        rows = [merge_tether] * 10  # scatter + 8 lanes + merge, as the auto-wrap writes

        by_equality = [t for t in rows if t == merge_tether]
        by_lane_group = [t for t in rows if lane_group(t) == merge_tether]

        assert by_lane_group == by_equality
        assert len(by_lane_group) == 10

    def test_a_hierarchical_scatter_gathers_its_own_lanes_and_only_those(self) -> None:
        """The new capability, and the thing equality could not express."""
        lanes = child_tether_ids("X", 8)
        other = child_tether_ids("Y", 3)

        collected = [t for t in lanes + other if lane_group(t) == "X"]

        assert collected == lanes
        assert len(collected) == 8

    def test_a_root_is_its_own_lane_group(self) -> None:
        """Not a fallback. A top-level scatter *is* its own gather scope, which is the
        same relationship the flat scheme encoded for everything."""
        assert lane_group("X") == "X"


# ── Hierarchy ────────────────────────────────────────────────────────────────


class TestInGatherScope:
    """The rule the fan-in gate turns on. One function, three call sites in the broker.

    Before task 4c-1 this was `AND tether_id = ?` written into three separate SQL
    statements in `local_broker`. The first group below is the one that licenses the
    change: it must be a no-op for everything already on disk.
    """

    @pytest.mark.parametrize("legacy", LEGACY_TETHER_IDS)
    def test_it_is_a_no_op_for_every_legacy_id(self, legacy: str) -> None:
        """Identical to the equality test it replaced, for every id format on disk."""
        assert in_gather_scope(legacy, legacy) is True
        assert in_gather_scope(legacy, "scatter_ffffffff") is False

    def test_a_legacy_scatter_gathers_exactly_what_equality_gathered(self) -> None:
        """The ten rows of a legacy 8-lane scatter, filtered both ways."""
        merge_tether = "scatter_84fe89ba"
        rows = [merge_tether] * 10

        by_equality = [t for t in rows if t == merge_tether]
        by_scope = [t for t in rows if in_gather_scope(t, merge_tether)]

        assert by_scope == by_equality
        assert len(by_scope) == 10

    def test_a_merge_at_the_root_gathers_all_eight_lanes(self) -> None:
        """The capability equality could not express."""
        lanes = child_tether_ids("X", 8)

        assert [lane for lane in lanes if in_gather_scope(lane, "X")] == lanes

    def test_a_merge_does_not_gather_another_scatters_lanes(self) -> None:
        """The whole reason the gate is tether-scoped at all."""
        others = child_tether_ids("Y", 8)

        assert [lane for lane in others if in_gather_scope(lane, "X")] == []

    def test_a_node_in_its_own_lane_is_in_scope(self) -> None:
        """A chain inside one lane: a later node waits on an earlier one, both `X.1`."""
        assert in_gather_scope("X.1", "X.1") is True

    def test_a_nested_merge_gathers_its_own_lanes_only(self) -> None:
        assert in_gather_scope("X.1.1", "X.1") is True
        assert in_gather_scope("X.2.1", "X.1") is False

    def test_a_grandchild_is_not_in_the_roots_scope(self) -> None:
        """Gathering is one level, not transitive — `X`'s merge waits on `X.n`, and a
        nested scatter's lanes are gathered by the merge inside `X.1`."""
        assert in_gather_scope("X.1.1", "X") is False

    def test_lane_ten_is_not_in_lane_ones_scope(self) -> None:
        """The prefix trap, at the level that would actually corrupt a gather."""
        assert in_gather_scope("X.10", "X.1") is False

    def test_an_empty_scope_admits_everything(self) -> None:
        """What the deleted `else` branch of the gather gate did for tetherless flows."""
        assert in_gather_scope("X.1", "") is True
        assert in_gather_scope("", "") is True
        assert in_gather_scope("scatter_84fe89ba", "   ") is True

    def test_an_empty_row_tether_is_not_admitted_to_a_real_scope(self) -> None:
        """Preserves the old SQL: an empty `tether_id` never matched a non-empty filter."""
        assert in_gather_scope("", "X") is False

    def test_an_unusable_row_tether_is_not_admitted(self) -> None:
        """Not silently swept into a gather scope."""
        assert in_gather_scope("X@1", "X") is False

    def test_it_agrees_with_lane_group_by_construction(self) -> None:
        """The two must not drift: in_gather_scope is defined in terms of lane_group."""
        for lane in child_tether_ids("X", 4) + ["X", "scatter_84fe89ba", "X.1.2"]:
            expected = lane == "X" or lane_group(lane) == "X"
            assert in_gather_scope(lane, "X") is expected


class TestLaneGroupHierarchy:
    def test_a_lane_gathers_at_its_scatter(self) -> None:
        assert lane_group("X.1") == "X"

    def test_a_nested_lane_gathers_one_level_up(self) -> None:
        assert lane_group("X.1.2") == "X.1"

    def test_lane_group_is_idempotent_at_the_root(self) -> None:
        assert lane_group(lane_group("X.1")) == "X"

    def test_walking_up_terminates_at_the_root(self) -> None:
        current = "X.1.2.3"
        seen = [current]
        while lane_group(current) != current:
            current = lane_group(current)
            seen.append(current)

        assert seen == ["X.1.2.3", "X.1.2", "X.1", "X"]


class TestDepthAndLevelCount:
    @pytest.mark.parametrize(
        "tether,expected",
        [("X", 0), ("X.1", 1), ("X.1.2", 2), ("X.1.2.3", 3)],
    )
    def test_depth_counts_separators(self, tether: str, expected: int) -> None:
        assert depth(tether) == expected

    def test_depth_matches_the_designs_worked_example(self) -> None:
        """`design.md` states `parse_depth("X.1.2") -> 2`. That is the spec's only
        precise statement of the number, so it is the one implemented."""
        assert depth("X.1.2") == 2

    @pytest.mark.parametrize("tether", ["X", "X.1", "X.1.2", "scatter_ab12cd34"])
    def test_level_count_is_always_depth_plus_one(self, tether: str) -> None:
        """Pinned so the two readings cannot drift into independent definitions."""
        assert level_count(tether) == depth(tether) + 1

    def test_the_prose_and_the_example_are_reconciled_not_chosen_between(self) -> None:
        """Req 19.2 says "3 levels (root -> child -> grandchild)"; the design example
        says depth 2. Both describe `X.1.2`. The warning constant is stated in the
        depth reading, and this is the assertion that they refer to the same tether."""
        grandchild = "X.1.2"

        assert level_count(grandchild) == 3
        assert depth(grandchild) == NESTING_DEPTH_WARN_AT


class TestIsDescendantOf:
    def test_a_lane_is_a_descendant_of_its_scatter(self) -> None:
        assert is_descendant_of("X.1", "X") is True

    def test_a_nested_lane_is_a_descendant_of_the_root(self) -> None:
        assert is_descendant_of("X.1.2", "X") is True

    def test_a_tether_is_its_own_descendant(self) -> None:
        assert is_descendant_of("X", "X") is True

    def test_a_sibling_is_not_a_descendant(self) -> None:
        assert is_descendant_of("X.2", "X.1") is False

    def test_another_root_is_not_a_descendant(self) -> None:
        assert is_descendant_of("Y.1", "X") is False

    def test_an_ancestor_is_not_a_descendant_of_its_child(self) -> None:
        assert is_descendant_of("X", "X.1") is False

    def test_lane_ten_is_not_a_descendant_of_lane_one(self) -> None:
        """Compared level by level, never by string prefix.

        `"X.10".startswith("X.1")` is True, and a prefix test would fold lane 10 into
        lane 1's gather scope — an approximately-correct answer on any scatter wider
        than nine lanes.
        """
        assert "X.10".startswith("X.1"), "the prefix trap this guards is real"
        assert is_descendant_of("X.10", "X.1") is False

    def test_a_legacy_id_is_only_its_own_descendant(self) -> None:
        assert is_descendant_of("scatter_ab12cd34", "scatter_ab12cd34") is True
        assert is_descendant_of("scatter_ab12cd34", "scatter_ffffffff") is False


# ── Generation ───────────────────────────────────────────────────────────────


class TestRootTetherId:
    def test_the_first_three_roots_are_x_y_z(self) -> None:
        assert [root_tether_id(i) for i in range(3)] == ["X", "Y", "Z"]

    def test_the_roots_match_the_declared_constant(self) -> None:
        """Asserted against `ROOT_TETHER_IDS`, not against string literals."""
        assert tuple(root_tether_id(i) for i in range(len(ROOT_TETHER_IDS))) == ROOT_TETHER_IDS

    def test_past_z_it_goes_to_two_letters(self) -> None:
        """`design.md`'s stated overflow: Z -> AA."""
        assert root_tether_id(3) == "AA"
        assert root_tether_id(4) == "AB"

    def test_two_letter_roots_roll_over_correctly(self) -> None:
        assert root_tether_id(3 + 25) == "AZ"
        assert root_tether_id(3 + 26) == "BA"

    def test_it_is_pure_so_the_same_index_always_gives_the_same_id(self) -> None:
        """The reason this is not a stateful generator. The auto-wrap runs twice per
        step — once for pre-flight, once for execution — and a counter would hand those
        two runs different ids for the same lane."""
        assert [root_tether_id(i) for i in range(40)] == [root_tether_id(i) for i in range(40)]

    def test_no_two_indices_collide(self) -> None:
        ids = [root_tether_id(i) for i in range(200)]

        assert len(set(ids)) == len(ids)

    def test_a_negative_index_is_refused(self) -> None:
        with pytest.raises(ValueError):
            root_tether_id(-1)


class TestChildTetherIds:
    def test_children_append_a_level(self) -> None:
        assert child_tether_ids("X", 3) == ["X.1", "X.2", "X.3"]

    def test_grandchildren_append_another(self) -> None:
        """Requirement 18.3's worked example."""
        assert child_tether_ids("X.1", 2) == ["X.1.1", "X.1.2"]

    def test_lane_numbers_are_one_based(self) -> None:
        """These appear in refusals and in the TUI; a "lane 0" reads as an off-by-one."""
        assert child_tether_ids("X", 1) == ["X.1"]

    def test_every_child_gathers_at_its_parent(self) -> None:
        """The generator and `lane_group` are inverses, and this is the tie."""
        for child in child_tether_ids("X.1", 4):
            assert lane_group(child) == "X.1"

    def test_every_child_is_one_level_deeper_than_its_parent(self) -> None:
        for child in child_tether_ids("X.1", 3):
            assert depth(child) == depth("X.1") + 1

    def test_a_legacy_parent_can_gain_lanes_without_being_renamed(self) -> None:
        """So a saved topology migrates in place: the lanes become addressable and
        their lane_group is the flat id the existing merge row already carries."""
        lanes = child_tether_ids("scatter_84fe89ba", 8)

        assert lanes[0] == "scatter_84fe89ba.1"
        assert len(lanes) == 8
        for lane in lanes:
            assert lane_group(lane) == "scatter_84fe89ba"

    def test_zero_lanes_returns_empty_rather_than_raising(self) -> None:
        """A scatter with no targets is a topology defect for the validator to name,
        not something this function should decide."""
        assert child_tether_ids("X", 0) == []

    def test_a_negative_count_is_refused(self) -> None:
        with pytest.raises(ValueError):
            child_tether_ids("X", -1)

    def test_it_is_pure(self) -> None:
        assert child_tether_ids("X", 8) == child_tether_ids("X", 8)


# ── Validation ───────────────────────────────────────────────────────────────


class TestValidateTetherId:
    @pytest.mark.parametrize("legacy", LEGACY_TETHER_IDS)
    def test_everything_already_on_disk_is_accepted(self, legacy: str) -> None:
        """Deliberately permissive. Refusing a saved id would break a flow at launch."""
        assert validate_tether_id(legacy) == legacy

    @pytest.mark.parametrize("tether", ["X", "X.1", "X.1.2", "AA.12"])
    def test_hierarchical_ids_are_accepted(self, tether: str) -> None:
        assert validate_tether_id(tether) == tether

    def test_surrounding_whitespace_is_stripped(self) -> None:
        assert validate_tether_id("  X.1  ") == "X.1"

    def test_an_interior_space_is_allowed(self) -> None:
        """It parses fine everywhere, and an operator may already have saved one."""
        assert validate_tether_id("my tether") == "my tether"

    def test_an_empty_id_is_refused(self) -> None:
        with pytest.raises(TetherIdError) as caught:
            validate_tether_id("")

        assert "empty" in caught.value.reason

    def test_whitespace_only_is_refused(self) -> None:
        with pytest.raises(TetherIdError):
            validate_tether_id("   ")

    @pytest.mark.parametrize("char", sorted(FORBIDDEN_IN_TETHER_ID))
    def test_every_forbidden_character_is_refused_and_named(self, char: str) -> None:
        """Parameterised over the constant, so adding one cannot skip its guard."""
        with pytest.raises(TetherIdError) as caught:
            validate_tether_id(f"X{char}1")

        assert repr(char) in caught.value.reason

    @pytest.mark.parametrize("bad", [".X", "X.", "X..1", "..", "X.1."])
    def test_an_empty_level_is_refused(self, bad: str) -> None:
        """It would make `lane_group` return a meaningless parent."""
        with pytest.raises(TetherIdError) as caught:
            validate_tether_id(bad)

        assert "empty level" in caught.value.reason

    def test_the_error_is_a_value_error(self) -> None:
        assert issubclass(TetherIdError, ValueError)

    def test_the_error_carries_the_id_and_a_bare_predicate(self) -> None:
        """Same shape as `topology_graph.TetherRefError`, so the two read alike."""
        with pytest.raises(TetherIdError) as caught:
            validate_tether_id("")

        assert not caught.value.reason.startswith("''")


# ── The cross-seam invariant ─────────────────────────────────────────────────


class TestATetherIdCannotCollideWithAnotherSeam:
    """A tether that breaks `parse_tether_qualified_ref` makes its lane unaddressable."""

    def test_the_node_reference_separator_is_forbidden(self) -> None:
        assert TETHER_SEPARATOR in FORBIDDEN_IN_TETHER_ID

    def test_the_flow_vector_separator_is_forbidden(self) -> None:
        assert FLOW_VECTOR_SEPARATOR in FORBIDDEN_IN_TETHER_ID

    def test_the_routing_target_delimiters_are_forbidden(self) -> None:
        """Both, because `parse_targets` accepts either."""
        assert {",", "|"} <= FORBIDDEN_IN_TETHER_ID

    def test_the_level_separator_is_not_forbidden(self) -> None:
        """Obvious, and worth pinning: the two separators must stay different."""
        assert TETHER_LEVEL_SEPARATOR not in FORBIDDEN_IN_TETHER_ID

    @pytest.mark.parametrize("tether", ["X", "X.1", "X.1.2", "scatter_84fe89ba", "tether_a"])
    def test_every_valid_tether_survives_a_reference_round_trip(self, tether: str) -> None:
        """The real invariant: a lane this module accepts can be named in a route."""
        ref = parse_tether_qualified_ref(f"AGENT_A{TETHER_SEPARATOR}{tether}")

        assert ref.node_id == "AGENT_A"
        assert ref.tether_id == tether

    def test_a_hierarchical_lane_is_addressable_in_a_cross_lane_route(self) -> None:
        """`X.1` is what Reqs 29/31/32 assume a lane looks like."""
        for lane in child_tether_ids("X", 3):
            assert parse_tether_qualified_ref(f"B@{lane}").tether_id == lane


# ── Counting, for Requirement 19.3 ───────────────────────────────────────────


class TestCountLanes:
    def test_it_counts_distinct_ids(self) -> None:
        assert count_lanes(child_tether_ids("X", 8)) == 8

    def test_a_legacy_scatters_ten_rows_do_not_read_as_ten_lanes(self) -> None:
        """The defect this replaces: `len(distinct Tether_ID)` over the rows of an
        8-lane scatter gives 1, and over per-lane rows it must give 8 — but the ten
        rows of one legacy scatter must still give 1, not 10."""
        assert count_lanes(["scatter_84fe89ba"] * 10) == 1

    def test_it_counts_lanes_across_two_scatters(self) -> None:
        assert count_lanes(child_tether_ids("X", 8) + child_tether_ids("Y", 4)) == 12

    def test_nothing_is_zero(self) -> None:
        assert count_lanes([]) == 0

    def test_a_malformed_id_is_skipped_rather_than_raising(self) -> None:
        """This is a count for a limit check; naming a bad id is a validator's job."""
        assert count_lanes(["X.1", "", "X.2"]) == 2

    def test_the_ceiling_is_declared_and_is_not_the_thread_cap(self) -> None:
        """Req 19.3's 64 bounds *lanes*; MAX_SCATTER_AGENTS/SCATTER_HARD_CAP bound
        *threads*. Conflating them would make the readout over-promise concurrency."""
        from maccre_core.orchestration.concurrency import MAX_SCATTER_AGENTS, SCATTER_HARD_CAP

        assert MAX_CONCURRENT_LANES == 64
        assert MAX_CONCURRENT_LANES > SCATTER_HARD_CAP > MAX_SCATTER_AGENTS


class TestLanesByGroup:
    def test_lanes_are_grouped_by_their_gather_scope(self) -> None:
        grouped = lanes_by_group(["X.1", "X.2", "Y.1"])

        assert grouped == {"X": ["X.1", "X.2"], "Y": ["Y.1"]}

    def test_grouping_is_first_seen_order_so_it_reads_the_same_twice(self) -> None:
        ids = ["Y.1", "X.2", "X.1"]

        assert list(lanes_by_group(ids)) == ["Y", "X"]
        assert lanes_by_group(ids)["X"] == ["X.2", "X.1"]

    def test_a_legacy_scatter_groups_under_itself(self) -> None:
        grouped = lanes_by_group(["scatter_84fe89ba", "scatter_84fe89ba"])

        assert grouped == {"scatter_84fe89ba": ["scatter_84fe89ba"] * 2}

    def test_nested_lanes_group_under_their_own_parent(self) -> None:
        grouped = lanes_by_group(["X.1.1", "X.1.2", "X.2.1"])

        assert grouped == {"X.1": ["X.1.1", "X.1.2"], "X.2": ["X.2.1"]}

    def test_a_malformed_id_is_skipped(self) -> None:
        assert lanes_by_group(["X.1", "X@2"]) == {"X": ["X.1"]}
