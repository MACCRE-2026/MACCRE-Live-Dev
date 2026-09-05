"""tests/test_cross_lane_routing.py
====================================
Requirement 31 — cross-lane routing over the tether hierarchy.

The spec markers in ``test_topological_semantic_spec.py`` state the criteria in one line
each. This is the coverage: the negative cases first, the refusals by name, and — the
part that matters most for this requirement — the assertions that tie the parse to the
render and tie the two callers of the lane resolver to each other.

Requirement 31 is not really "add cross-lane routing". Most of it is Principle 4 applied
to a shape the codebase already had twice: ``detect_temporal_paradox`` parsed
``NODE@TETHER`` inline while ``_qualify`` rendered it separately, and the two had already
diverged. So a round-trip test and a same-diagnostic test are not decoration here; they
are the tests that fail if the two derivations reappear.
"""
from __future__ import annotations

import pytest

from maccre_core.orchestration.local_broker import resolve_cross_lane_target
from maccre_core.orchestration.topology_graph import (
    FLOW_VECTOR_SEPARATOR,
    TETHER_SEPARATOR,
    TetherQualifiedRef,
    TetherRefError,
    apply_cross_lane_route,
    detect_temporal_paradox,
    parse_tether_qualified_ref,
    record_crossing,
    validate_cross_lane_routes,
)

# A four-lane scatter, the shape Requirement 31.3's design note argues from.
FOUR_LANES = {"X.1": ["A"], "X.2": ["B"], "X.3": ["C"], "X.4": ["D"]}


# ── The parse and the render are one seam ────────────────────────────────────


class TestTheParseIsTheInverseOfTheRender:
    """Requirement 31.2, and the Principle 4 tie that keeps it that way."""

    @pytest.mark.parametrize(
        "node_id,tether_id",
        [
            ("AGENT_A", "X.2"),
            ("A", "X.1"),
            ("CTRL_MERGE_S1", "X.10"),
            ("NODE_01", "root"),
            ("a-node_with.punctuation", "X.3.1"),
        ],
    )
    def test_render_then_parse_returns_what_went_in(self, node_id: str, tether_id: str) -> None:
        """The round trip. Fails the moment either side grows its own separator."""
        rendered = TetherQualifiedRef(node_id=node_id, tether_id=tether_id).render()
        parsed = parse_tether_qualified_ref(rendered)

        assert parsed.node_id == node_id
        assert parsed.tether_id == tether_id
        assert parsed == TetherQualifiedRef(node_id=node_id, tether_id=tether_id)

    def test_parse_then_render_returns_the_same_string(self) -> None:
        """The other direction, so neither side can be the one that drifts."""
        assert parse_tether_qualified_ref("AGENT_A@X.2").render() == "AGENT_A@X.2"

    def test_the_render_uses_the_shared_separator(self) -> None:
        """Asserted against the constant, never a literal `@`.

        A literal here would pass while the constant said something else, which is the
        whole failure mode being guarded.
        """
        rendered = TetherQualifiedRef(node_id="A", tether_id="X.1").render()

        assert rendered == f"A{TETHER_SEPARATOR}X.1"
        assert rendered.count(TETHER_SEPARATOR) == 1

    def test_surrounding_whitespace_is_tolerated_on_both_components(self) -> None:
        """These references come from CSV and hand editing."""
        parsed = parse_tether_qualified_ref("  AGENT_A @ X.2  ")

        assert parsed.node_id == "AGENT_A"
        assert parsed.tether_id == "X.2"


class TestTheParseRefusesRatherThanDegrades:
    """Principle 2 — every one of these would have produced a usable-looking address."""

    def test_a_bare_node_name_is_refused_not_assigned_a_lane(self) -> None:
        with pytest.raises(TetherRefError) as caught:
            parse_tether_qualified_ref("AGENT_A")

        assert "tether-qualified" in caught.value.reason

    def test_an_empty_reference_is_refused(self) -> None:
        with pytest.raises(TetherRefError):
            parse_tether_qualified_ref("")

    def test_a_missing_node_is_refused_rather_than_returned_empty(self) -> None:
        """`"@X.1"` used to parse to node_id `""` and be accepted."""
        with pytest.raises(TetherRefError) as caught:
            parse_tether_qualified_ref("@X.1")

        assert "no node" in caught.value.reason

    def test_a_missing_lane_is_refused_rather_than_returned_empty(self) -> None:
        """The blanked tether ID from Principle 2's named incident, refused at the door.

        `"A@"` used to parse to tether_id `""`. An empty tether is what put a scatter and
        its merge in different scopes; a parser that hands one back is the mechanism.
        """
        with pytest.raises(TetherRefError) as caught:
            parse_tether_qualified_ref("A@")

        assert "no lane" in caught.value.reason

    def test_a_second_separator_is_refused_rather_than_swallowed_into_the_lane(self) -> None:
        """`"A@X.1@Y"` used to read as a lane literally named `X.1@Y`."""
        with pytest.raises(TetherRefError) as caught:
            parse_tether_qualified_ref("A@X.1@Y")

        assert "exactly one node in exactly one lane" in caught.value.reason

    def test_the_error_is_a_value_error(self) -> None:
        """Callers that do not care about the distinction keep working."""
        assert issubclass(TetherRefError, ValueError)

        with pytest.raises(ValueError):
            parse_tether_qualified_ref("AGENT_A")

    def test_the_error_carries_the_reference_and_a_bare_predicate(self) -> None:
        """So a caller can compose a sentence without printing the reference twice."""
        with pytest.raises(TetherRefError) as caught:
            parse_tether_qualified_ref("AGENT_A")

        assert caught.value.ref == "AGENT_A"
        assert not caught.value.reason.startswith("'AGENT_A'")
        assert "AGENT_A" in str(caught.value)


# ── Pre-launch validation: 31.3 and 31.4 ─────────────────────────────────────


class TestValidateCrossLaneRoutes:
    """A validator that fires on everything is useless, so the clean case comes first."""

    def test_a_route_between_two_real_lanes_is_not_refused(self) -> None:
        report = validate_cross_lane_routes(FOUR_LANES, routes=[("A@X.1", "B@X.2")])

        assert report.refused is False
        assert report.offences == []
        assert report.participants == []

    def test_no_routes_at_all_is_not_refused(self) -> None:
        assert validate_cross_lane_routes(FOUR_LANES, routes=[]).refused is False

    def test_a_lane_the_topology_never_spawns_is_refused_and_named(self) -> None:
        """31.3 — `X.9` in a four-lane scatter."""
        report = validate_cross_lane_routes(FOUR_LANES, routes=[("A@X.1", "Z@X.9")])

        assert report.refused is True
        route, ref, reason = report.offences[0]
        assert route == "A@X.1 -> Z@X.9"
        assert ref == "Z@X.9"
        assert "X.9" in reason
        assert "never spawns" in reason

    def test_a_node_absent_from_a_real_lane_is_refused_and_named(self) -> None:
        """31.4 — right lane, wrong node. A different fix from 31.3, so a different reason."""
        report = validate_cross_lane_routes(FOUR_LANES, routes=[("A@X.1", "B@X.3")])

        assert report.refused is True
        _route, ref, reason = report.offences[0]
        assert ref == "B@X.3"
        assert "absent" in reason
        assert "X.3" in reason

    def test_a_broken_source_end_is_refused_too(self) -> None:
        """A route *from* a node that does not exist is as broken as a route *to* one."""
        report = validate_cross_lane_routes(FOUR_LANES, routes=[("GHOST@X.9", "B@X.2")])

        assert report.refused is True
        assert [ref for _r, ref, _reason in report.offences] == ["GHOST@X.9"]

    def test_both_ends_broken_reports_both(self) -> None:
        report = validate_cross_lane_routes(FOUR_LANES, routes=[("GHOST@X.8", "Z@X.9")])

        assert [ref for _r, ref, _reason in report.offences] == ["GHOST@X.8", "Z@X.9"]

    def test_an_unqualified_route_target_is_refused_rather_than_guessed(self) -> None:
        report = validate_cross_lane_routes(FOUR_LANES, routes=[("A@X.1", "B")])

        assert report.refused is True
        assert any("tether-qualified" in reason for _r, _ref, reason in report.offences)

    def test_the_refusal_names_its_participants(self) -> None:
        report = validate_cross_lane_routes(
            FOUR_LANES, routes=[("A@X.1", "Z@X.9"), ("B@X.2", "Y@X.7")]
        )

        assert report.participants == ["Z@X.9", "Y@X.7"]

    def test_participants_are_de_duplicated_in_first_seen_order(self) -> None:
        report = validate_cross_lane_routes(
            FOUR_LANES, routes=[("A@X.1", "Z@X.9"), ("B@X.2", "Z@X.9")]
        )

        assert report.participants == ["Z@X.9"]
        assert len(report.offences) == 2, "both routes are still faults; only the naming dedupes"

    def test_participants_are_deterministic_across_runs(self) -> None:
        """A set here would make a refusal read differently twice."""
        routes = [("A@X.1", "Z@X.9"), ("B@X.2", "Y@X.7"), ("C@X.3", "W@X.6")]

        first = validate_cross_lane_routes(FOUR_LANES, routes=routes).participants
        second = validate_cross_lane_routes(FOUR_LANES, routes=routes).participants

        assert first == second


class TestTheRefusalMessage:
    """`message()` is a method, matching `ParadoxReport.message`. One spelling."""

    def test_the_message_names_the_route_and_the_offending_reference(self) -> None:
        report = validate_cross_lane_routes(FOUR_LANES, routes=[("A@X.1", "Z@X.9")])
        message = report.message()

        assert "A@X.1 -> Z@X.9" in message
        assert "Z@X.9" in message
        assert "X.9" in message

    def test_a_clean_configuration_says_so_rather_than_returning_empty(self) -> None:
        report = validate_cross_lane_routes(FOUR_LANES, routes=[("A@X.1", "B@X.2")])

        assert "No cross-lane routing fault" in report.message()

    def test_every_offence_appears_in_the_message(self) -> None:
        report = validate_cross_lane_routes(
            FOUR_LANES, routes=[("A@X.1", "Z@X.9"), ("B@X.2", "Y@X.7")]
        )
        message = report.message()

        assert "Z@X.9" in message
        assert "Y@X.7" in message


class TestOneResolverBehindFourCriteria:
    """31.3/31.4 and 33.2's cases 3/4 are the same check asked by two callers.

    Not "two checks that happen to agree today". If these diverge, one of the two
    callers has grown a private copy of the resolver again — which is exactly the
    history Requirement 31 was written on top of.
    """

    def test_a_missing_lane_reads_identically_to_both_callers(self) -> None:
        routed = validate_cross_lane_routes(
            {"X.1": ["A"], "X.2": ["B"]}, routes=[("A@X.1", "GHOST@X.9")]
        )
        waited = detect_temporal_paradox(
            lanes={"X.1": ["A"], "X.2": ["B"]}, waits={"A@X.1": ["GHOST@X.9"]}
        )

        assert routed.offences[0][2] == waited.unresolvable[0][2]

    def test_a_node_absent_from_its_lane_reads_identically_to_both_callers(self) -> None:
        routed = validate_cross_lane_routes(
            {"X.1": ["A"], "X.2": ["B"]}, routes=[("A@X.1", "NOT_THERE@X.2")]
        )
        waited = detect_temporal_paradox(
            lanes={"X.1": ["A"], "X.2": ["B"]}, waits={"A@X.1": ["NOT_THERE@X.2"]}
        )

        assert routed.offences[0][2] == waited.unresolvable[0][2]

    def test_an_unqualified_reference_reads_identically_to_both_callers(self) -> None:
        routed = validate_cross_lane_routes({"X.1": ["A", "B"]}, routes=[("A@X.1", "B")])
        waited = detect_temporal_paradox(lanes={"X.1": ["A", "B"]}, waits={"A@X.1": ["B"]})

        assert routed.offences[0][2] == waited.unresolvable[0][2]

    def test_the_paradox_detector_now_refuses_a_blank_tether(self) -> None:
        """A hole the shared parse closed. `"A@"` used to be accepted silently."""
        report = detect_temporal_paradox(lanes={"X.1": ["A"]}, waits={"A@X.1": ["A@"]})

        assert report.paradox is True
        assert any("no lane" in reason for _w, _t, reason in report.unresolvable)

    def test_the_paradox_detector_now_refuses_a_blank_node(self) -> None:
        report = detect_temporal_paradox(lanes={"X.1": ["A"]}, waits={"A@X.1": ["@X.1"]})

        assert report.paradox is True
        assert any("no node" in reason for _w, _t, reason in report.unresolvable)


# ── The runtime half: 31.5 ───────────────────────────────────────────────────


class TestResolveCrossLaneTarget:
    """It lives in `local_broker` because the broker is where the silent drop happens."""

    def test_a_reference_to_a_present_lane_resolves(self) -> None:
        parsed = resolve_cross_lane_target("B@X.2", known_lanes={"X.1", "X.2"})

        assert parsed.node_id == "B"
        assert parsed.tether_id == "X.2"

    def test_a_reference_to_an_absent_lane_raises_rather_than_no_opping(self) -> None:
        with pytest.raises(LookupError):
            resolve_cross_lane_target("GHOST@X.99", known_lanes={"X.1"})

    def test_the_lookup_error_names_the_reference_the_lane_and_what_is_available(self) -> None:
        """A refusal that does not say which lanes exist sends the author guessing."""
        with pytest.raises(LookupError) as caught:
            resolve_cross_lane_target("GHOST@X.99", known_lanes={"X.1", "X.2"})

        text = str(caught.value)
        assert "GHOST@X.99" in text
        assert "X.99" in text
        assert "X.1" in text
        assert "X.2" in text

    def test_no_known_lanes_at_all_still_refuses_by_name(self) -> None:
        with pytest.raises(LookupError) as caught:
            resolve_cross_lane_target("GHOST@X.99", known_lanes=set())

        assert "none" in str(caught.value)

    def test_a_malformed_reference_raises_the_parse_error_not_a_lookup_error(self) -> None:
        """Different wrongs call for different fixes: syntax typo vs topology typo."""
        with pytest.raises(TetherRefError):
            resolve_cross_lane_target("GHOST", known_lanes={"X.1"})

    def test_a_frozenset_of_lanes_works(self) -> None:
        """`Collection`, so membership is what is required — not a specific container."""
        parsed = resolve_cross_lane_target("B@X.2", known_lanes=frozenset({"X.2"}))

        assert parsed.tether_id == "X.2"

    def test_a_list_of_lanes_works(self) -> None:
        assert resolve_cross_lane_target("B@X.2", known_lanes=["X.2"]).tether_id == "X.2"

    def test_it_parses_through_the_shared_seam(self) -> None:
        """Same object the graph module returns, not a broker-flavoured lookalike."""
        assert isinstance(
            resolve_cross_lane_target("B@X.2", known_lanes={"X.2"}), TetherQualifiedRef
        )


# ── Routing does not re-parent: 31.7 ─────────────────────────────────────────


class TestApplyCrossLaneRoute:
    """Containment and routing are different relations, and fan-in scopes by containment."""

    def test_the_node_keeps_its_own_tether(self) -> None:
        node = apply_cross_lane_route(node_id="B", own_tether="X.2", from_tether="X.1")

        assert node.tether_id == "X.2"

    def test_the_origin_lane_is_recorded_not_substituted(self) -> None:
        node = apply_cross_lane_route(node_id="B", own_tether="X.2", from_tether="X.1")

        assert node.arrived_from == "X.1"
        assert node.node_id == "B"

    def test_routing_from_two_different_lanes_yields_the_same_containment(self) -> None:
        """The point of 31.7. A node's gather scope must not depend on who pointed at it."""
        from_one = apply_cross_lane_route(node_id="B", own_tether="X.2", from_tether="X.1")
        from_three = apply_cross_lane_route(node_id="B", own_tether="X.2", from_tether="X.3")

        assert from_one.tether_id == from_three.tether_id == "X.2"
        assert from_one.arrived_from != from_three.arrived_from

    def test_the_rendered_address_is_the_nodes_own_lane(self) -> None:
        node = apply_cross_lane_route(node_id="B", own_tether="X.2", from_tether="X.1")

        assert node.render() == "B@X.2"

    def test_an_empty_containment_tether_is_refused_rather_than_defaulted(self) -> None:
        """The named Principle 2 incident. Adopting `from_tether` here is the defect."""
        with pytest.raises(ValueError) as caught:
            apply_cross_lane_route(node_id="B", own_tether="", from_tether="X.1")

        assert "gather gate" in str(caught.value)

    def test_an_empty_node_id_is_refused(self) -> None:
        with pytest.raises(ValueError):
            apply_cross_lane_route(node_id="", own_tether="X.2", from_tether="X.1")

    def test_an_empty_origin_lane_is_refused(self) -> None:
        with pytest.raises(ValueError):
            apply_cross_lane_route(node_id="B", own_tether="X.2", from_tether="")

    def test_a_route_within_one_lane_is_refused_as_not_a_crossing(self) -> None:
        """It would record a crossing that never happened."""
        with pytest.raises(ValueError) as caught:
            apply_cross_lane_route(node_id="B", own_tether="X.2", from_tether="X.2")

        assert "not a cross-lane route" in str(caught.value)


# ── Lineage: 31.6 ────────────────────────────────────────────────────────────


class TestRecordCrossing:
    """The crossing is legible from tether-qualified entries, with no second notation."""

    def test_an_empty_vector_starts_with_the_qualified_node(self) -> None:
        node = apply_cross_lane_route(node_id="B", own_tether="X.2", from_tether="X.1")

        assert record_crossing("", node) == "B@X.2"

    def test_the_crossing_is_readable_from_two_adjacent_entries(self) -> None:
        node = apply_cross_lane_route(node_id="B", own_tether="X.2", from_tether="X.1")

        vector = record_crossing("A@X.1", node)

        assert vector == f"A@X.1{FLOW_VECTOR_SEPARATOR}B@X.2"
        assert "X.1" in vector, "provenance carries the lane it came from"

    def test_a_contradiction_between_lineage_and_route_raises(self) -> None:
        """Two records of the same fact disagreeing is a defect, not a thing to average."""
        node = apply_cross_lane_route(node_id="B", own_tether="X.2", from_tether="X.1")

        with pytest.raises(ValueError) as caught:
            record_crossing("A@X.7", node)

        assert "X.7" in str(caught.value)
        assert "X.1" in str(caught.value)

    def test_a_bare_previous_entry_is_appended_without_claiming_corroboration(self) -> None:
        """What `swarm_worker` writes today. Unverifiable, so nothing is asserted about it."""
        node = apply_cross_lane_route(node_id="B", own_tether="X.2", from_tether="X.1")

        assert record_crossing("NODE_01", node) == f"NODE_01{FLOW_VECTOR_SEPARATOR}B@X.2"

    def test_an_unparseable_previous_entry_does_not_crash_the_lineage(self) -> None:
        """Lineage is telemetry. A malformed history must not take down the flow."""
        node = apply_cross_lane_route(node_id="B", own_tether="X.2", from_tether="X.1")

        assert record_crossing("A@X.1@junk", node).endswith("B@X.2")

    def test_only_the_last_entry_is_checked(self) -> None:
        """Earlier hops were checked when they were appended; re-checking would refuse
        every legitimate multi-lane lineage."""
        node = apply_cross_lane_route(node_id="C", own_tether="X.3", from_tether="X.2")

        vector = record_crossing("A@X.1>B@X.2", node)

        assert vector == "A@X.1>B@X.2>C@X.3"
