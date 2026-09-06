# ┌─────────────────────────────────────────────────────────────────────────────┐
# │  MACCREv2 Test Suite — Phase 6.13 Track D: Topology as a Graph              │
# └─────────────────────────────────────────────────────────────────────────────┘
"""
tests/test_topology_graph.py
============================
Phase 6.13 Track D — the topology read as a graph, and the three defects that
came from not doing so.

All three were found by UT-0, the first live 8-agent scatter. The run reported
``drained=True stalled=False errors=0`` and "Linear Flow Complete" while doing
something else entirely, which is why they are pinned down here rather than left
to a stubbed topology that never disagrees with itself.

**D1 — every lane seeded as an entry point.** ``_find_starting_nodes`` inferred
entry points from ``Wait_For == "none"``. ``Wait_For`` is the gather gate, not a
predecessor list, and the scatter auto-wrap sets it to ``"none"`` on every lane
because a lane gathers from nothing. Nine entry points were queued for a 10-node
DAG, so all eight agents ran against the raw payload in parallel with the scatter
meant to feed them.

**D2 — the scatter routed to unhydrated names.** ``scatter_targets`` came from
step config as bare names while the topology was hydrated to ``_S0``. The broker
created rows for both sets. Combined with D1: 16 inference calls for 8 lanes.

**D3 — ``Tether_ID`` dropped in flattening.** Computed by the auto-wrap, written
into every row dict, and discarded by ``_hydrate_topology``'s fixed column list.
Every queue row carried an empty tether, so the tether-scoped fan-in was
unreachable and an 8-lane merge gathered 1 source.
"""
from __future__ import annotations

from typing import Any

import pytest

from maccre_core.orchestration.tether import lane_group
from maccre_core.orchestration.topology_graph import (
    TERMINAL_SENTINELS,
    build_edges,
    describe,
    entry_nodes,
    is_terminal_target,
    node_ids,
    parse_targets,
    terminal_nodes,
    unreachable_nodes,
)


def row(node_id: str, next_node: str = "END", wait_for: str = "none") -> dict[str, Any]:
    return {"Node_ID": node_id, "Next_Node": next_node, "Wait_For": wait_for}


#: The shape the scatter auto-wrap emits: one scatter, N lanes, one merge.
#: Every lane carries ``Wait_For: "none"`` — that is not a mistake in the fixture,
#: it is the production value, and it is what broke D1.
def scatter_rows(lanes: int = 8) -> list[dict[str, Any]]:
    agents = [f"Agent{i}" for i in range(1, lanes + 1)]
    rows = [row("CTRL_SCATTER", next_node=",".join(agents), wait_for="none")]
    rows.extend(row(a, next_node="CTRL_MERGE", wait_for="none") for a in agents)
    rows.append(row("CTRL_MERGE", next_node="END", wait_for="|".join(agents)))
    return rows


class TestParseTargets:
    """One reading of a delimited routing field."""

    def test_comma_delimited(self) -> None:
        assert parse_targets("A,B,C") == ["A", "B", "C"]

    def test_pipe_delimited(self) -> None:
        """``route_task`` has always accepted pipes; hydration did not.

        A hand-authored ``Next_Node`` of ``"B|C"`` used to hydrate into the single
        token ``B|C_S0`` — a node that does not exist — so neither successor ran.
        """
        assert parse_targets("A|B|C") == ["A", "B", "C"]

    def test_mixed_delimiters(self) -> None:
        assert parse_targets("A,B|C") == ["A", "B", "C"]

    def test_whitespace_is_stripped(self) -> None:
        assert parse_targets("  A , B |  C  ") == ["A", "B", "C"]

    @pytest.mark.parametrize("sentinel", sorted(s for s in TERMINAL_SENTINELS if s))
    def test_sentinels_are_not_nodes(self, sentinel: str) -> None:
        """Sentinels label an edge's end, they are not vertices.

        Counting them would give every terminating lane a phantom successor and
        make no node terminal.
        """
        assert parse_targets(sentinel) == []

    def test_sentinels_are_case_insensitive(self) -> None:
        assert parse_targets("end") == []
        assert parse_targets("Failed") == []

    def test_sentinels_are_dropped_from_a_mixed_list(self) -> None:
        assert parse_targets("A,END,B") == ["A", "B"]

    def test_duplicates_removed_order_preserved(self) -> None:
        assert parse_targets("B,A,B,C,A") == ["B", "A", "C"]

    def test_empty_and_none_are_safe(self) -> None:
        for value in ("", "   ", None, ",,|,"):
            assert parse_targets(value) == []

    def test_non_string_is_tolerated(self) -> None:
        """Rows arrive from CSV, JSON and hand editing."""
        assert parse_targets(42) == ["42"]

    def test_is_terminal_target(self) -> None:
        assert is_terminal_target("END")
        assert is_terminal_target(" done ")
        assert not is_terminal_target("Testy")


class TestEntryNodes:
    """D1 — an entry point is a node nothing else routes to."""

    def test_linear_chain_has_one_entry(self) -> None:
        rows = [row("A", "B"), row("B", "C"), row("C", "END")]
        assert entry_nodes(rows) == ["A"]

    def test_scatter_has_exactly_one_entry(self) -> None:
        """The D1 regression test.

        Under the old ``Wait_For``-based rule this returned nine entries — the
        scatter plus all eight lanes — because every lane declares it waits for
        nobody. Only the scatter is actually an entry point.
        """
        assert entry_nodes(scatter_rows(8)) == ["CTRL_SCATTER"]

    @pytest.mark.parametrize("lanes", [1, 2, 4, 8, 12])
    def test_scatter_width_does_not_change_the_answer(self, lanes: int) -> None:
        assert entry_nodes(scatter_rows(lanes)) == ["CTRL_SCATTER"]

    def test_wait_for_none_on_a_downstream_node_is_not_an_entry(self) -> None:
        """States the conflation directly.

        ``B`` waits for nobody *and* is routed to by ``A``. Those are different
        facts; only the second one decides whether B starts the flow.
        """
        rows = [row("A", "B"), row("B", "END", wait_for="none")]
        assert entry_nodes(rows) == ["A"]

    def test_genuine_parallel_entries_are_all_returned(self) -> None:
        """Multiple real roots must survive — this is a legitimate topology."""
        rows = [row("A", "C"), row("B", "C"), row("C", "END")]
        assert entry_nodes(rows) == ["A", "B"]

    def test_entries_are_returned_in_row_order(self) -> None:
        rows = [row("Z", "C"), row("A", "C"), row("C", "END")]
        assert entry_nodes(rows) == ["Z", "A"]

    def test_a_self_loop_is_still_an_entry(self) -> None:
        """Self-edges are the recursion primitive, not a predecessor.

        Counting a node's own back-edge as inbound would make a single
        self-looping node unstartable.
        """
        assert entry_nodes([row("A", "A")]) == ["A"]

    def test_a_self_looping_node_mid_chain_is_not_an_entry(self) -> None:
        rows = [row("A", "B"), row("B", "B")]
        assert entry_nodes(rows) == ["A"]

    def test_pipe_delimited_edges_confer_in_degree(self) -> None:
        """Otherwise B and C look like roots and get seeded twice over."""
        rows = [row("A", "B|C"), row("B", "END"), row("C", "END")]
        assert entry_nodes(rows) == ["A"]

    def test_a_pure_cycle_falls_back_rather_than_returning_nothing(self) -> None:
        """No node has in-degree zero, so the flow would never start.

        Returning nothing would produce a silent no-op job. Nominating a node
        gives the operator a running flow to diagnose, matching the fallback the
        previous implementation had for the same situation.
        """
        rows = [row("A", "B"), row("B", "A")]
        assert entry_nodes(rows) == ["A"]

    def test_dangling_targets_do_not_create_entries_or_crash(self) -> None:
        """A target naming no row is a validation error, not a graph question."""
        rows = [row("A", "GHOST"), row("B", "A")]
        assert entry_nodes(rows) == ["B"]

    def test_empty_topology(self) -> None:
        assert entry_nodes([]) == []

    def test_rows_without_a_node_id_are_skipped(self) -> None:
        rows = [{"Next_Node": "A"}, row("A", "END")]
        assert entry_nodes(rows) == ["A"]


class TestTerminalNodes:
    """The fan-in question — needed by Task B3's per-lane chains."""

    def test_linear_chain(self) -> None:
        rows = [row("A", "B"), row("B", "C"), row("C", "END")]
        assert terminal_nodes(rows) == ["C"]

    def test_scatter_terminates_at_the_merge(self) -> None:
        assert terminal_nodes(scatter_rows(8)) == ["CTRL_MERGE"]

    def test_lanes_of_differing_length_each_report_their_last_node(self) -> None:
        """Task B3's requirement, stated as a graph property.

        Once a lane is a chain, the node the scatter named is no longer the node
        the merge must wait for. Computing terminals from the edges means a lane
        can grow without rewriting the gather gate.
        """
        rows = [
            row("S", "L1a,L2a"),
            row("L1a", "L1b"),
            row("L1b", "END"),
            row("L2a", "END"),
        ]
        assert set(terminal_nodes(rows)) == {"L1b", "L2a"}

    def test_a_node_with_no_next_node_is_terminal(self) -> None:
        assert terminal_nodes([{"Node_ID": "A"}]) == ["A"]

    def test_a_self_only_loop_is_terminal(self) -> None:
        """An unbounded self-loop has no exit; the recursion limit stops it."""
        assert terminal_nodes([row("A", "A")]) == ["A"]

    def test_all_sentinel_spellings_terminate(self) -> None:
        rows = [row("A", "DONE"), row("B", "STOP"), row("C", "TERMINATE")]
        assert set(terminal_nodes(rows)) == {"A", "B", "C"}


class TestEdgesAndNodes:
    def test_build_edges_maps_each_node_to_its_targets(self) -> None:
        rows = [row("A", "B|C"), row("B", "END"), row("C", "END")]
        assert build_edges(rows) == {"A": ["B", "C"], "B": [], "C": []}

    def test_node_ids_preserve_order(self) -> None:
        assert node_ids([row("Z"), row("A"), row("M")]) == ["Z", "A", "M"]

    def test_duplicate_node_ids_collapse_to_the_first(self) -> None:
        """Mirrors ``UNIQUE(job_id, current_node)``.

        Two rows sharing a Node_ID become one queue row at execution time, so one
        of the two nodes never runs as authored. The graph reports what will
        actually happen rather than what was written.
        """
        rows = [row("A", "B"), row("A", "C"), row("B"), row("C")]
        assert node_ids(rows) == ["A", "B", "C"]
        assert build_edges(rows)["A"] == ["B"]


class TestDiagnostics:
    def test_unreachable_nodes_are_reported(self) -> None:
        rows = [row("A", "B"), row("B", "END"), row("ORPHAN_X", "ORPHAN_Y"),
                row("ORPHAN_Y", "ORPHAN_X")]
        assert set(unreachable_nodes(rows)) == {"ORPHAN_X", "ORPHAN_Y"}

    def test_a_healthy_topology_has_nothing_unreachable(self) -> None:
        assert unreachable_nodes(scatter_rows(8)) == []

    def test_describe_summarises_the_structure(self) -> None:
        """One call for any layer that wants to render or measure the graph.

        A visualisation or telemetry layer re-deriving structure privately is how
        it ends up describing a graph the engine is not executing.
        """
        summary = describe(scatter_rows(4))

        assert summary["entry_nodes"] == ["CTRL_SCATTER"]
        assert summary["terminal_nodes"] == ["CTRL_MERGE"]
        assert summary["unreachable_nodes"] == []
        assert len(summary["nodes"]) == 6  # scatter + 4 lanes + merge
        assert summary["edges"]["CTRL_SCATTER"] == [
            "Agent1", "Agent2", "Agent3", "Agent4"
        ]


# ── The three defects, at the flow_engine seam where they actually bit ─────────


def _runner() -> Any:
    """A ``FlowRunner`` with no constructor side effects.

    The three methods under test are effectively pure — they read rows and config
    and return rows and names — so none of the store/workbook wiring the real
    constructor performs is needed.
    """
    from maccre_core.orchestration.flow_engine import FlowRunner

    return FlowRunner.__new__(FlowRunner)


class TestD1EntryPointSeeding:
    """D1 — ``_find_starting_nodes`` must seed the scatter only."""

    def test_a_scatter_step_seeds_one_entrypoint(self) -> None:
        """UT-0 seeded nine. Cost: every agent executed twice."""
        starts = _runner()._find_starting_nodes(scatter_rows(8), step_index=0)
        assert starts == ["CTRL_SCATTER_S0"]

    def test_lanes_are_not_seeded(self) -> None:
        starts = _runner()._find_starting_nodes(scatter_rows(8), step_index=0)
        for i in range(1, 9):
            assert f"Agent{i}_S0" not in starts

    def test_the_step_suffix_is_applied(self) -> None:
        starts = _runner()._find_starting_nodes(scatter_rows(2), step_index=3)
        assert starts == ["CTRL_SCATTER_S3"]

    def test_a_linear_baseline_is_unchanged(self) -> None:
        """The graph rule must not disturb ordinary flows.

        This is the 3-step linear shape the A0 baseline exercises; it seeded one
        entry point before and must still seed exactly that one.
        """
        rows = [row("S1", "S2"), row("S2", "S3"), row("S3", "END")]
        assert _runner()._find_starting_nodes(rows, step_index=1) == ["S1_S1"]

    def test_a_single_node_step_is_unchanged(self) -> None:
        rows = [row("CTRL_PAUSE_MANUAL", "END")]
        starts = _runner()._find_starting_nodes(rows, step_index=2)
        assert starts == ["CTRL_PAUSE_MANUAL_S2"]

    def test_an_empty_topology_keeps_its_fallback(self) -> None:
        assert _runner()._find_starting_nodes([], step_index=0) == ["OSINT_S0"]

    def test_a_cyclic_topology_still_starts(self) -> None:
        rows = [row("A", "B"), row("B", "A")]
        assert _runner()._find_starting_nodes(rows, step_index=0) == ["A_S0"]

    def test_a_hand_authored_diamond(self) -> None:
        """The workflow the user is heading for: hand-built, saved as a MacroNode."""
        rows = [
            row("SPLIT", "LEFT,RIGHT"),
            row("LEFT", "JOIN"),
            row("RIGHT", "JOIN"),
            row("JOIN", "END", wait_for="LEFT|RIGHT"),
        ]
        assert _runner()._find_starting_nodes(rows, step_index=0) == ["SPLIT_S0"]


class TestD2ScatterTargetHydration:
    """D2 — routing targets in step config must carry the step suffix."""

    def test_scatter_targets_are_hydrated(self) -> None:
        """UT-0 logged bare targets while the topology described ``_S0`` ones.

        The broker created rows for both, so each lane existed twice.
        """
        from maccre_core.orchestration.flow_engine import FlowRunner

        overlays = FlowRunner._build_topology_overlays(
            [row("CTRL_SCATTER", "Agent1,Agent2")],
            {"scatter_targets": ["Agent1", "Agent2"], "scatter_mode": "full_copy"},
            0,
        )
        assert overlays["CTRL_SCATTER_S0"]["scatter_targets"] == [
            "Agent1_S0", "Agent2_S0"
        ]

    def test_the_hydrated_targets_match_the_topology_node_ids(self) -> None:
        """The property that actually matters: one set of lane rows, not two."""
        from maccre_core.orchestration.flow_engine import FlowRunner

        rows = scatter_rows(4)
        hydrated = _runner()._hydrate_topology(rows, {}, step_index=0)
        topology_node_ids = {r[0] for r in hydrated}

        overlays = FlowRunner._build_topology_overlays(
            rows, {"scatter_targets": [f"Agent{i}" for i in range(1, 5)]}, 0
        )
        targets = set(overlays["CTRL_SCATTER_S0"]["scatter_targets"])

        assert targets <= topology_node_ids, (
            f"scatter would route outside the topology: {targets - topology_node_ids}"
        )

    def test_non_routing_config_is_left_alone(self) -> None:
        """Suffixing ``scatter_mode`` or a delimiter would corrupt it silently."""
        from maccre_core.orchestration.flow_engine import FlowRunner

        cfg = {
            "scatter_mode": "full_copy",
            "merge_delimiter": "\n---\n",
            "auto_resume_after": 30,
            "tether_id": "tether_a",
        }
        overlays = FlowRunner._build_topology_overlays(
            [row("CTRL_MERGE", "END")], cfg, 0
        )
        applied = overlays["CTRL_MERGE_S0"]

        assert applied["scatter_mode"] == "full_copy"
        assert applied["merge_delimiter"] == "\n---\n"
        assert applied["auto_resume_after"] == 30
        assert applied["tether_id"] == "tether_a"

    def test_terminal_sentinels_in_config_are_not_suffixed(self) -> None:
        from maccre_core.orchestration.flow_engine import FlowRunner

        overlays = FlowRunner._build_topology_overlays(
            [row("CTRL_PAUSE_MANUAL", "END")], {"next_node": "END"}, 0
        )
        assert overlays["CTRL_PAUSE_MANUAL_S0"]["next_node"] == "END"

    def test_the_original_config_is_not_mutated(self) -> None:
        """Overlays are per-node copies; the step's config is shared."""
        from maccre_core.orchestration.flow_engine import FlowRunner

        cfg = {"scatter_targets": ["Agent1"]}
        FlowRunner._build_topology_overlays(
            [row("CTRL_SCATTER", "Agent1")], cfg, 0
        )
        assert cfg["scatter_targets"] == ["Agent1"]

    def test_agent_rows_get_no_overlay(self) -> None:
        from maccre_core.orchestration.flow_engine import FlowRunner

        overlays = FlowRunner._build_topology_overlays(
            [row("Agent1", "CTRL_MERGE")], {"scatter_mode": "full_copy"}, 0
        )
        assert overlays == {}


class TestD3TetherIdSurvivesHydration:
    """D3 — the tether must reach the CSV, and therefore the queue."""

    #: Column index of Tether_ID in the canonical row order.
    TETHER_COL = 15

    def test_tether_id_is_carried_through(self) -> None:
        """It was computed, written into the row dict, and dropped here."""
        rows = [{**row("CTRL_SCATTER", "Agent1"), "Tether_ID": "tether_a"}]
        hydrated = _runner()._hydrate_topology(rows, {}, step_index=0)

        assert hydrated[0][self.TETHER_COL] == "tether_a"

    def test_every_row_of_a_scatter_shares_one_tether(self) -> None:
        """Scatter, lanes and merge must agree or the fan-in scopes nothing."""
        rows = [{**r, "Tether_ID": "tether_a"} for r in scatter_rows(4)]
        hydrated = _runner()._hydrate_topology(rows, {}, step_index=0)

        tethers = {r[self.TETHER_COL] for r in hydrated}
        assert tethers == {"tether_a"}

    def test_a_missing_tether_yields_empty_not_an_error(self) -> None:
        hydrated = _runner()._hydrate_topology([row("A", "END")], {}, step_index=0)
        assert hydrated[0][self.TETHER_COL] == ""

    def test_the_row_has_the_full_column_count(self) -> None:
        """``build_topology`` accepts 6-16 columns; hydration emits all 16."""
        hydrated = _runner()._hydrate_topology([row("A", "END")], {}, step_index=0)
        assert len(hydrated[0]) == 16

    def test_build_topology_accepts_the_hydrated_width(self) -> None:
        """Guards the two halves of the schema against drifting apart."""
        import inspect

        from maccre_core.tools import admin_tools

        source = inspect.getsource(admin_tools.build_topology)
        assert '"Tether_ID"' in source
        assert "> 16" in source

    def test_topology_engine_exposes_the_tether(self) -> None:
        """Reaching the CSV is not enough; node_config must surface it."""
        import inspect

        from maccre_core.orchestration import topology_engine

        source = inspect.getsource(topology_engine)
        assert "'TETHER_ID'" in source or '"TETHER_ID"' in source
        assert '"tether_id"' in source


class TestNextNodePipeDelimiter:
    """Hardening for hand-authored topologies."""

    NEXT_COL = 3

    def test_a_pipe_delimited_next_node_hydrates_into_separate_targets(self) -> None:
        """Previously became the single phantom token ``B|C_S0``.

        ``route_task`` accepts pipes, so the topology was executable in principle;
        hydration was the only reader that disagreed, and it silently produced a
        node nobody would ever run.
        """
        hydrated = _runner()._hydrate_topology(
            [row("A", "B|C")], {}, step_index=0
        )
        assert hydrated[0][self.NEXT_COL] == "B_S0,C_S0"

    def test_a_comma_delimited_next_node_is_unchanged(self) -> None:
        hydrated = _runner()._hydrate_topology(
            [row("A", "B,C")], {}, step_index=0
        )
        assert hydrated[0][self.NEXT_COL] == "B_S0,C_S0"

    def test_terminal_targets_are_not_suffixed(self) -> None:
        hydrated = _runner()._hydrate_topology([row("A", "END")], {}, step_index=0)
        assert hydrated[0][self.NEXT_COL] == "END"


class _MissingStore:
    """A MacroNode store that holds nothing.

    ``_get_macronode`` catches ``KeyError`` specifically to fall through to its
    auto-wrap branches, so a miss has to be signalled that way.
    """

    def load(self, name: str) -> dict[str, Any]:
        raise KeyError(name)


def _autowrap_runner() -> Any:
    """A ``FlowRunner`` whose stores are empty, so ``CTRL_`` names auto-wrap."""
    from maccre_core.orchestration.flow_engine import FlowRunner

    runner = FlowRunner.__new__(FlowRunner)
    runner.macronode_store = _MissingStore()  # type: ignore[assignment]
    runner.global_store = _MissingStore()  # type: ignore[assignment]
    return runner


class TestD3BlankTetherFallback:
    """D3, second attempt — carrying the column was necessary but not sufficient.

    The first fix plumbed ``Tether_ID`` from the auto-wrap through to the queue.
    The live re-run still showed ``tether_id = ''`` on every row and a merge
    gathering 1 source, because the value being plumbed was already empty.

    ``_collect_ctrl_config`` in the authoring UI does::

        cfg["tether_id"] = self.query_one("#cfg-tether-id", Input).value.strip()

    so saving a ``CTRL_SCATTER`` with the Tether ID box blank stores ``""`` — a
    key that is *present*. The auto-wrap then read it with
    ``cfg.get("tether_id", <generated>)``, and a present-but-empty key returns
    ``""`` rather than the default, so the generated tether never applied.

    The same trap sat on the worker's scatter route, which is what stamps the
    tether onto every lane row.
    """

    def test_a_blank_tether_falls_back_to_a_generated_one(self) -> None:
        """The exact config the authoring UI produces for an empty field."""
        runner = _autowrap_runner()

        macro = runner._get_macronode(
            "CTRL_SCATTER",
            {"scatter_agents": ["A", "B"], "tether_id": ""},
        )
        tethers = {str(r.get("Tether_ID") or "") for r in macro["topology_rows"]}

        assert tethers, "auto-wrap produced no rows"
        assert "" not in tethers, "a blank tether disables tether-scoped fan-in"
        # Updated 2026-09-06 (task 4c-3). This asserted `len(tethers) == 1` — "scatter,
        # lanes and merge must agree" — which was the right test while one flat tether
        # covered a whole scatter. Lanes now carry their own (`X.1`, `X.2`), so the
        # strings no longer match and were never the point: the intent is that every row
        # belongs to ONE gather scope, which is what the fan-in actually depends on.
        # `lane_group` collapses a lane to its group and a group to itself, so this is the
        # same claim stated in terms of the thing that matters, and it is strictly
        # stronger — it would still fail if a lane were tethered under a different group.
        assert {lane_group(t) for t in tethers} == {lane_group(next(iter(tethers)))}, (
            f"scatter, lanes and merge must share one gather scope: {tethers}"
        )

    def test_a_missing_tether_key_also_falls_back(self) -> None:
        runner = _autowrap_runner()

        macro = runner._get_macronode("CTRL_SCATTER", {"scatter_agents": ["A", "B"]})
        assert all(r.get("Tether_ID") for r in macro["topology_rows"])

    def test_whitespace_only_tether_is_treated_as_blank(self) -> None:
        runner = _autowrap_runner()

        macro = runner._get_macronode(
            "CTRL_SCATTER", {"scatter_agents": ["A"], "tether_id": "   "}
        )
        assert all(str(r.get("Tether_ID", "")).strip() for r in macro["topology_rows"])

    def test_an_operator_supplied_tether_is_respected(self) -> None:
        runner = _autowrap_runner()

        macro = runner._get_macronode(
            "CTRL_SCATTER",
            {"scatter_agents": ["A", "B"], "tether_id": "tether_a"},
        )
        # Updated 2026-09-06 (task 4c-3): the operator's name becomes the **group**
        # tether, carried by the scatter and the merge, and the lanes are its children.
        # Previously every row carried the literal string.
        rows = macro["topology_rows"]
        tethers = {str(r.get("Tether_ID") or "") for r in rows}

        assert {lane_group(t) for t in tethers} == {"tether_a"}
        assert {str(r["Tether_ID"]) for r in rows if r["Node_ID"] in ("A", "B")} == {
            "tether_a.1", "tether_a.2",
        }

    def test_the_generated_tether_is_stable_across_calls(self) -> None:
        """The previous default was keyed on ``id()`` of a freshly built list.

        The auto-wrap runs twice per step — once for pre-flight, once for
        execution — so an address-derived tether meant the scope validated was not
        necessarily the scope executed.
        """
        from maccre_core.orchestration.flow_engine import _default_tether_id

        first = _default_tether_id(["A", "B", "C"])
        second = _default_tether_id(["A", "B", "C"])
        assert first == second

    def test_different_agent_sets_get_different_tethers(self) -> None:
        """Two scatters in one job must not collapse into one gather scope."""
        from maccre_core.orchestration.flow_engine import _default_tether_id

        assert _default_tether_id(["A", "B"]) != _default_tether_id(["C", "D"])

    def test_the_generated_tether_survives_hydration(self) -> None:
        """End to end: blank config in, real tether in the CSV row out."""
        runner = _autowrap_runner()

        macro = runner._get_macronode(
            "CTRL_SCATTER",
            {"scatter_agents": ["A", "B"], "tether_id": ""},
        )
        hydrated = runner._hydrate_topology(
            macro["topology_rows"], {}, step_index=0
        )

        tethers = {str(r[15] or "") for r in hydrated}
        assert "" not in tethers
        # Updated 2026-09-06 (task 4c-3): per-lane tethers, one gather scope. Hydration
        # must carry the lane identity through to the CSV column, not flatten it — which
        # is the half of this test that still matters, since Tether_ID was once dropped
        # entirely by the flatten step.
        assert {lane_group(t) for t in tethers} == {lane_group(next(iter(tethers)))}
        assert len(tethers) == 3, f"group + 2 lanes should survive hydration: {tethers}"

    def test_the_worker_scatter_route_never_stamps_a_blank_tether(self) -> None:
        """Structural guard on the route that tethers every lane.

        ``.get("tether_id", "scatter")`` returned ``""`` for a present-but-empty
        key, so the fallback could not fire and the whole scatter lost its scope.
        """
        import inspect

        from maccre_core.orchestration.swarm_worker import UniversalSwarmWorker

        source = inspect.getsource(UniversalSwarmWorker.execute_cycle)
        assert 'config.get("tether_id", "scatter")' not in source, (
            "a .get default cannot rescue a present-but-empty tether"
        )
