# ┌─────────────────────────────────────────────────────────────────────────────┐
# │  MACCREv2 Test Infrastructure — the topological semantic, specified          │
# └─────────────────────────────────────────────────────────────────────────────┘
"""
tests/test_topological_semantic_spec.py
=======================================
The executable half of the 2026-09-04 amendment to
``.kiro/specs/phase-6-13-multi-flow-lane/requirements.md``.

**These tests are written to fail.** They are the specification's teeth, added at the
same time as the specification, and they go green as Requirements 29 through 33 are
built. Every one is marked ``xfail(strict=True)``, which means:

* while the capability is missing, the suite stays green and the test reports ``xfail``;
* **the moment a capability starts working, the strict marker turns it into a failure**
  and forces the marker to be removed deliberately.

That second property is the reason for ``strict=True``. A plain skip would let a
capability land silently and leave the spec's claim unverified, which is the exact
Doctrine 5 failure this project has now recorded four times — a `--smart` flag accepted
and never read, a type-checker config naming unchecked targets, a security docstring over
a disabled gate, and a registry counting itself wrong.

WHY THE SPEC AND ITS TESTS ARRIVE TOGETHER
------------------------------------------
The Era 3 retcon established that this project's roadmap and its code had disagreed
about which era it was in, because Era 3 ran under spec discipline enforced only by the
operator's memory. Writing the tests in the same pass as the requirements is the
mechanical answer: a requirement with no failing test is a requirement nobody has to
satisfy.

WHAT IS DELIBERATELY NOT TESTED HERE
------------------------------------
The authoring surface. Requirement 33's readout, the Gather Strategy control and
`CTRL_WAIT` configuration all need a UI, and the authoring-ownership decision is still
open. Specifying a UI before its owner is settled is how two authoring surfaces over one
graph came to be proposed.
"""
from __future__ import annotations

from pathlib import Path

import pytest

# ── Requirement 29 — lanes may terminate without merging ─────────────────────


class TestReq29LanesMayTerminateUnmerged:
    """Supersedes Requirement 19.4, which made a merge mandatory per branch."""

    def test_scatter_carries_a_declared_gather_strategy(self) -> None:
        """29.2 — `Merge` / `Concat` / `Ungathered`, declared on the scatter."""
        from maccre_core.orchestration.deterministic_nodes import GatherStrategy

        assert {s.value for s in GatherStrategy} >= {"Merge", "Concat", "Ungathered"}

    @pytest.mark.xfail(strict=True, reason="Req 29.3: unreachable-gather refusal not built")
    def test_declared_merge_with_an_unreachable_gather_is_refused_by_name(self) -> None:
        """29.3 — refuse before launch, and *name every unreachable lane*.

        Naming matters as much as refusing. A generic validation failure sends the
        author looking through eight lanes for the one that is wrong.
        """
        from maccre_core.orchestration.topology_graph import validate_gather_reachability

        report = validate_gather_reachability(
            lanes={"X.1": ["A"], "X.2": ["B"]},
            gather_strategy="Merge",
            gather_nodes=[],
        )
        assert report.refused is True
        assert set(report.unreachable_lanes) == {"X.1", "X.2"}

    @pytest.mark.xfail(strict=True, reason="Req 29.4: Ungathered lane recording not built")
    def test_ungathered_lanes_record_their_outputs_separately(self) -> None:
        """29.4 — each lane's terminal output recorded on its own."""
        from maccre_core.orchestration.topology_graph import terminal_outputs_for_step

        outputs = terminal_outputs_for_step(step_index=0, gather_strategy="Ungathered")
        assert len(outputs) > 1
        assert len({path for _node, path in outputs}) == len(outputs)

    def test_pre_amendment_topologies_default_to_merge(self) -> None:
        """29.6 — saved MacroNodes keep their current behaviour.

        The hard-replacement alternative was rejected precisely because it would break
        every topology already on disk.
        """
        from maccre_core.orchestration.flow_engine import resolve_gather_strategy

        assert resolve_gather_strategy({"schema_version": "1.0"}) == "Merge"


# ── Requirement 30 — a step's output is a set ────────────────────────────────


class TestReq30StepOutputIsASet:
    """The generalisation of defect E2's fix."""

    def test_a_steps_output_is_an_ordered_set_of_node_path_pairs(self) -> None:
        """30.1 — ordered by declared topology position, never completion time.

        Completion order is a race. Declaration order is a fact about the topology, and
        the register already records what ordering-by-mtime cost: a 59-byte stub chosen
        over a 426 KB merge, every time, because the stub was written last.
        """
        from maccre_core.orchestration.flow_engine import StepOutputSet

        s = StepOutputSet(pairs=[("B_S0", "/b.md"), ("A_S0", "/a.md")])
        assert s.ordered_by == "declared_topology_position"

    def test_a_single_terminal_step_is_the_degenerate_case(self) -> None:
        """30.2 — E2's behaviour preserved, not special-cased."""
        from maccre_core.orchestration.flow_engine import StepOutputSet

        s = StepOutputSet(pairs=[("CTRL_MERGE_S0", "/merged.md")])
        assert s.single() == "/merged.md"

    def test_an_ungathered_multi_output_step_refuses_to_pick_one(self) -> None:
        """30.4 — the load-bearing clause of the whole amendment.

        Silently selecting one of eight outputs is Principle 2: a plausible artifact
        representing an eighth of the work, which downstream logic then acts on.
        """
        from maccre_core.orchestration.flow_engine import StepOutputSet

        s = StepOutputSet(pairs=[("A_S0", "/a.md"), ("B_S0", "/b.md")])
        with pytest.raises(ValueError, match="more than one"):
            s.single()

    def test_an_empty_output_set_logs_error_and_changes_nothing(self) -> None:
        """30.5 — no silent fallback, exactly as E2's fix established."""
        from maccre_core.orchestration.flow_engine import StepOutputSet

        s = StepOutputSet(pairs=[])
        assert s.is_empty() is True
        assert s.substitute_guess() is None


# ── Requirement 31 — cross-lane routing ──────────────────────────────────────


class TestReq31CrossLaneRouting:
    """Tether hierarchy from containment tree to routing graph."""

    @pytest.mark.xfail(strict=True, reason="Req 31.2: tether-qualified references not parsed")
    def test_a_route_target_may_be_tether_qualified(self) -> None:
        """31.2 — identify a node by node id *and* lane."""
        from maccre_core.orchestration.topology_graph import parse_tether_qualified_ref

        ref = parse_tether_qualified_ref("AGENT_A@X.2")
        assert ref.node_id == "AGENT_A"
        assert ref.tether_id == "X.2"

    @pytest.mark.xfail(strict=True, reason="Req 31.3: nonexistent-lane refusal not built")
    def test_a_route_to_a_lane_that_never_exists_is_refused_by_name(self) -> None:
        """31.3 — Principle 2. `X.9` in a four-lane scatter must fail at validation."""
        from maccre_core.orchestration.topology_graph import validate_cross_lane_routes

        report = validate_cross_lane_routes(
            lanes={"X.1": ["A"], "X.2": ["B"], "X.3": ["C"], "X.4": ["D"]},
            routes=[("A@X.1", "Z@X.9")],
        )
        assert report.refused is True
        assert "X.9" in report.message

    @pytest.mark.xfail(strict=True, reason="Req 31.5: silent-drop guard not built")
    def test_an_unresolvable_cross_lane_reference_never_no_ops(self) -> None:
        """31.5 — the runtime half of the same rule."""
        from maccre_core.orchestration.local_broker import resolve_cross_lane_target

        with pytest.raises(LookupError):
            resolve_cross_lane_target("GHOST@X.99", known_lanes={"X.1"})

    @pytest.mark.xfail(strict=True, reason="Req 31.7: re-parenting guard not built")
    def test_routing_into_a_lane_does_not_reparent_the_node(self) -> None:
        """31.7 — containment and routing are different relations.

        Conflating them would make a node's tether ID depend on who routed to it, and
        the tether ID is what fan-in scopes by.
        """
        from maccre_core.orchestration.topology_graph import apply_cross_lane_route

        node = apply_cross_lane_route(node_id="B", own_tether="X.2", from_tether="X.1")
        assert node.tether_id == "X.2"


# ── Requirement 32 — CTRL_WAIT ───────────────────────────────────────────────


class TestReq32CtrlWait:
    """Collect from a named agent on a named lane, at a chosen point."""

    def test_ctrl_wait_is_declared_in_the_registry(self) -> None:
        """32.1, declaration half — **passes today.**

        Not an xfail. `CTRL_WAIT` was added to the registry as `ComingSoon` the moment
        Requirement 32 was written, because that is the truth: specified, not built. The
        registry can only be the honest answer to *what control nodes are there* if a
        declared-but-unimplemented node appears in it with that status.

        This test also demonstrated why the xfail markers here are ``strict=True``. It
        began as an xfail, and adding the registry row turned it into an ``XPASS``, which
        strict mode converts into a failure — forcing this split into a declaration half
        that passes and an implementation half that does not, rather than letting a
        half-built capability sit under a stale marker.
        """
        from maccre_core.controlnode_registry import _BUILTIN_NODES

        row = next((n for n in _BUILTIN_NODES if n["name"] == "CTRL_WAIT"), None)
        assert row is not None, "CTRL_WAIT is specified in Requirement 32 but not declared"
        assert row["status"] == "ComingSoon", (
            "CTRL_WAIT's status should be ComingSoon until its handler exists. If it is "
            "now `active`, the implementation-half tests below should be un-xfailed."
        )

    @pytest.mark.xfail(strict=True, reason="Req 32.1: CTRL_WAIT handler does not exist")
    def test_ctrl_wait_has_a_handler(self) -> None:
        from maccre_core.orchestration import deterministic_nodes

        assert hasattr(deterministic_nodes, "_handle_wait")

    @pytest.mark.xfail(strict=True, reason="Req 32.4: unsatisfiable-wait status not built")
    def test_a_wait_whose_target_lane_finished_without_producing_is_unsatisfiable(
        self,
    ) -> None:
        """32.4 — a distinct terminal status. Never `completed`, never a plain timeout.

        Defect F3 was a hold nobody could release that ran out a 3600s budget and then
        reported `completed`. This is the same failure shape in a new place, and the
        status has to distinguish it or the operator cannot tell which happened.
        """
        from maccre_core.orchestration.deterministic_nodes import evaluate_wait

        outcome = evaluate_wait(
            targets=["A@X.1"],
            lane_states={"X.1": "completed"},
            recorded_outputs={},
        )
        assert outcome.status == "unsatisfiable"
        assert outcome.status != "timeout"

    @pytest.mark.xfail(strict=True, reason="Req 32.5: state-observed detection not built")
    def test_an_unsatisfiable_wait_is_detected_without_waiting_out_a_timeout(self) -> None:
        """32.5 — ask, rather than wait and guess. The `pause_owner_alive` pattern."""
        from maccre_core.orchestration.deterministic_nodes import evaluate_wait

        outcome = evaluate_wait(
            targets=["A@X.1"],
            lane_states={"X.1": "completed"},
            recorded_outputs={},
        )
        assert outcome.decided_immediately is True

    @pytest.mark.xfail(strict=True, reason="Req 32.6: satisfying-target record not built")
    def test_a_released_wait_records_which_targets_satisfied_it(self) -> None:
        """32.6 — in declared order, so the record is reproducible."""
        from maccre_core.orchestration.deterministic_nodes import evaluate_wait

        outcome = evaluate_wait(
            targets=["A@X.1", "B@X.2"],
            lane_states={"X.1": "completed", "X.2": "completed"},
            recorded_outputs={"A@X.1": "/a.md", "B@X.2": "/b.md"},
        )
        assert outcome.status == "released"
        assert outcome.satisfied_by == ["A@X.1", "B@X.2"]


# ── Requirement 33 — pre-launch validation and readout ───────────────────────


class TestReq33PreLaunchValidation:
    """Refuse the impossible, and describe the rest, before launch."""

    def test_a_wait_on_a_downstream_node_in_the_same_lane_is_a_paradox(self) -> None:
        """33.2 case 1 — the simplest impossible configuration."""
        from maccre_core.orchestration.topology_graph import detect_temporal_paradox

        report = detect_temporal_paradox(
            lanes={"X.1": ["WAIT_ON_B", "B"]},
            waits={"WAIT_ON_B@X.1": ["B@X.1"]},
        )
        assert report.paradox is True

    def test_a_cycle_of_waits_across_lanes_is_a_paradox(self) -> None:
        """33.2 case 2 — two lanes each waiting on the other."""
        from maccre_core.orchestration.topology_graph import detect_temporal_paradox

        report = detect_temporal_paradox(
            lanes={"X.1": ["A"], "X.2": ["B"]},
            waits={"A@X.1": ["B@X.2"], "B@X.2": ["A@X.1"]},
        )
        assert report.paradox is True

    def test_a_paradox_refusal_names_its_participants(self) -> None:
        """33.3 — never a generic validation failure."""
        from maccre_core.orchestration.topology_graph import detect_temporal_paradox

        report = detect_temporal_paradox(
            lanes={"X.1": ["A"], "X.2": ["B"]},
            waits={"A@X.1": ["B@X.2"], "B@X.2": ["A@X.1"]},
        )
        assert "A@X.1" in report.participants
        assert "B@X.2" in report.participants

    def test_the_readout_states_the_whole_configuration(self) -> None:
        """33.5 — lanes, nodes per lane, strategies, waits, routes, terminals, peak."""
        from maccre_core.orchestration.flow_engine import total_sum_readout

        readout = total_sum_readout(topology_rows=[], step_index=0)
        for field in (
            "lane_count",
            "lane_tether_ids",
            "nodes_per_lane",
            "gather_strategies",
            "waits",
            "cross_lane_routes",
            "terminal_node_count",
            "expected_peak_concurrency",
        ):
            assert field in readout

    def test_the_readout_is_derived_from_the_hydrated_topology(self) -> None:
        """33.6 — not from the authoring surface.

        The TUI once built ids as `NAME_{i}` while the engine built `NAME_S{i}`. A
        readout generated from what was *drawn* would be a second representation of the
        topology and would drift from what executes — Principle 4, in the one place
        whose job is to tell the operator the truth before they commit.
        """
        from maccre_core.orchestration.flow_engine import total_sum_readout

        readout = total_sum_readout(topology_rows=[], step_index=0)
        assert readout["source"] == "hydrated_topology"


# ── Requirement 34 — the step-boundary payload contract ──────────────────────


class TestReq34StepBoundaryPayloadContract:
    """3b with a ceiling: the ledger *is* the payload, bounded, honestly marked.

    Written red on 2026-09-05, before implementation, so each criterion has a test that
    fails until the capability exists — and `strict=True` so the moment one starts
    passing the marker itself breaks the gate and has to be removed deliberately.

    **The limitation these markers carry, recorded before the work rather than after:**
    the *before* number for this change was never captured and cannot be captured
    retroactively. `payload_bytes` and per-node `INFERENCE_COST` attribution both landed
    on 2026-09-05 and no live flow has run since. Once this is implemented, "what did the
    new contract cost" is answerable only against a baseline taken first.
    """

    @pytest.mark.xfail(strict=True, reason="Req 34.1: not wired — see the module docstring")
    def test_the_worker_composes_through_the_one_seam(self) -> None:
        """34.1 — extend the existing dual-payload block, do not add a second.

        Principle 4. `swarm_worker` already composes two documents into one payload with
        labelled sections; that block *is* accompany-not-replace, already exercised on
        every multi-hop flow. A second concatenation would be a second representation of
        "how a payload is assembled", and the two would drift.

        **This marker is deliberately the last to fall, and it is doing a job while red.**
        34.1 is the only criterion that cannot be satisfied by a pure module — it is a
        statement about the *worker delegating*, which means changing what a live flow
        sends. And that change is irreversible in one specific way: `payload_bytes` and
        per-node `INFERENCE_COST` attribution landed on 2026-09-05 with no live run since,
        so the **before** number does not exist and cannot be obtained once the contract
        changes.

        So this red marker *is* the "not wired yet" record, enforced mechanically rather
        than written in a comment somebody has to trust. It falls when a baseline run has
        been taken and the wiring is done deliberately.
        """
        source = (
            Path(__file__).resolve().parent.parent
            / "maccre_core" / "orchestration" / "swarm_worker.py"
        ).read_text(encoding="utf-8")
        assert "compose_step_payload(" in source

    def test_the_upstream_output_is_identified_not_duplicated(self) -> None:
        """34.2 — the ledger already contains it; sending it twice is the whole cost.

        The unified session ledger is assembled from every agent ledger in the job, so
        "terminal output plus the session ledger" would carry the upstream output twice
        at every hop.
        """
        from maccre_core.orchestration.payload_contract import compose_step_payload

        ledger = "## AGENT_A_S0\nupstream prose here\n\n## AGENT_B_S0\nlater prose\n"
        composed = compose_step_payload(
            session_context=ledger, upstream_node="AGENT_A_S0", source_document="",
        )
        assert composed.count("upstream prose here") == 1
        assert "AGENT_A_S0" in composed

    def test_the_ceiling_is_a_named_constant(self) -> None:
        """34.3 — not a literal at the point of use."""
        from maccre_core.orchestration.payload_contract import (
            ACCOMPANYING_CONTEXT_CHAR_CEILING,
        )

        assert isinstance(ACCOMPANYING_CONTEXT_CHAR_CEILING, int)
        assert ACCOMPANYING_CONTEXT_CHAR_CEILING > 0

    def test_truncation_says_it_truncated_and_did_not_distil(self) -> None:
        """34.4 — the honesty clause.

        A payload claiming to be distilled when it was merely cut would be Principle 3
        inside the document the next agent reasons from.
        """
        from maccre_core.orchestration.payload_contract import (
            ACCOMPANYING_CONTEXT_CHAR_CEILING,
            compose_step_payload,
        )

        oversized = "x" * (ACCOMPANYING_CONTEXT_CHAR_CEILING * 3)
        composed = compose_step_payload(
            session_context=oversized, upstream_node="A_S0", source_document="",
        )
        lowered = composed.lower()
        assert "truncated" in lowered
        assert "not distilled" in lowered

    def test_the_most_recent_turns_are_kept_and_it_says_so(self) -> None:
        """34.5 — a reader cannot otherwise know which end was dropped."""
        from maccre_core.orchestration.payload_contract import (
            ACCOMPANYING_CONTEXT_CHAR_CEILING,
            compose_step_payload,
        )

        oldest = "OLDEST_MARKER"
        newest = "NEWEST_MARKER"
        filler = "y" * (ACCOMPANYING_CONTEXT_CHAR_CEILING * 2)
        composed = compose_step_payload(
            session_context=f"{oldest}\n{filler}\n{newest}",
            upstream_node="A_S0", source_document="",
        )
        assert newest in composed
        assert oldest not in composed
        assert "most recent" in composed.lower()

    def test_the_distillation_seam_exists_and_is_honestly_empty(self) -> None:
        """34.6 — named, unimplemented, and never conflated with truncation.

        Deliberately asserts that the seam returns ``None``: Era 3 builds the place, and
        Era 4 fills it. A seam that quietly returned the truncated text would make
        "distilled" true by redefinition.
        """
        from maccre_core.orchestration.payload_contract import distil_truncated_context

        assert distil_truncated_context("some removed prose") is None

    def test_the_composed_payload_size_is_reported(self) -> None:
        """34.7 — so a before-and-after comparison is possible at all."""
        from maccre_core.orchestration.payload_contract import describe_step_payload

        report = describe_step_payload(
            session_context="short", upstream_node="A_S0", source_document="",
        )
        for field in ("composed_chars", "context_chars", "truncated", "distilled"):
            assert field in report
        assert report["distilled"] is False
