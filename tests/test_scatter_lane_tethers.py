"""tests/test_scatter_lane_tethers.py
=====================================
Task 4c-3 — the scatter auto-wrap gives every lane its own tether.

**This is the change that produces the first hierarchical tether at runtime.** 4b built the
seam, 4c-1 taught the gather gate to read through it, 4c-2 stopped routing from re-parenting
nodes, and none of those altered a single value a live flow writes. This one does.

The shape it must produce, for an 8-agent scatter:

    CTRL_SCATTER   X          the group, and its own gather scope
    AGENT_A        X.1        \\
    ...                       |  eight individually addressable lanes
    AGENT_H        X.8        /
    CTRL_MERGE     X          the gather scope the lanes belong to

The load-bearing invariant is the last two lines together: **the merge must sit on the
group tether, not on a lane.** A merge on a lane tether is the deadlock 4c-2 exists to
prevent — the gate would look for lanes whose group matched `X.1` and find none.
`TestTheMergeStillGathersEveryLane` is the group that would catch that.
"""
from __future__ import annotations

from typing import Any

import pytest

from maccre_core.orchestration.flow_engine import (
    FlowRunner,
    _default_tether_id,
    total_sum_readout,
)
from maccre_core.orchestration.tether import (
    TETHER_LEVEL_SEPARATOR,
    child_tether_ids,
    count_lanes,
    depth,
    in_gather_scope,
    lane_group,
    validate_tether_id,
)

AGENTS = [f"AGENT_{c}" for c in "ABCDEFGH"]


class _NoStore:
    """A MacroNode store that knows nothing, so `_get_macronode` reaches the auto-wrap."""

    def load(self, name: str) -> dict[str, Any]:
        raise KeyError(name)


def _wrap(agents: list[str], cfg_extra: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    """Run the real scatter auto-wrap and return its topology rows."""
    runner = FlowRunner.__new__(FlowRunner)
    runner.macronode_store = _NoStore()  # type: ignore[attr-defined]
    runner.global_store = _NoStore()  # type: ignore[attr-defined]
    cfg: dict[str, Any] = {"scatter_agents": agents}
    cfg.update(cfg_extra or {})
    return FlowRunner._get_macronode(runner, "CTRL_SCATTER", cfg)["topology_rows"]


def _tether(rows: list[dict[str, Any]], node_id: str) -> str:
    return next(r["Tether_ID"] for r in rows if r["Node_ID"] == node_id)


def _lane_tethers(rows: list[dict[str, Any]]) -> list[str]:
    return [r["Tether_ID"] for r in rows if r["Node_ID"].startswith("AGENT_")]


# ── The shape ────────────────────────────────────────────────────────────────


class TestTheAutoWrapAssignsPerLaneTethers:
    def test_each_lane_gets_a_distinct_tether(self) -> None:
        lanes = _lane_tethers(_wrap(AGENTS))

        assert len(lanes) == 8
        assert len(set(lanes)) == 8

    def test_lanes_are_children_of_the_group_in_declared_order(self) -> None:
        rows = _wrap(AGENTS)
        group = _tether(rows, "CTRL_SCATTER")

        assert _lane_tethers(rows) == child_tether_ids(group, 8)

    def test_lane_numbers_are_one_based(self) -> None:
        rows = _wrap(AGENTS)
        group = _tether(rows, "CTRL_SCATTER")

        assert _tether(rows, "AGENT_A") == f"{group}{TETHER_LEVEL_SEPARATOR}1"

    def test_every_lane_is_one_level_deeper_than_the_group(self) -> None:
        rows = _wrap(AGENTS)
        group = _tether(rows, "CTRL_SCATTER")

        for lane in _lane_tethers(rows):
            assert depth(lane) == depth(group) + 1

    def test_every_lane_tether_is_wellformed(self) -> None:
        """It has to survive `Wait_For`, `flow_vector` and `NODE@TETHER` parsing."""
        for lane in _lane_tethers(_wrap(AGENTS)):
            assert validate_tether_id(lane) == lane

    @pytest.mark.parametrize("count", [1, 2, 3, 8, 12])
    def test_the_lane_count_follows_the_agent_count(self, count: int) -> None:
        agents = [f"AGENT_{i}" for i in range(count)]

        assert len(set(_lane_tethers(_wrap(agents)))) == count

    def test_a_single_agent_scatter_still_gets_a_lane_tether(self) -> None:
        """Degenerate but real: one lane is still a lane, and still addressable."""
        rows = _wrap(["SOLO"])

        assert _tether(rows, "SOLO") == f"{_tether(rows, 'CTRL_SCATTER')}.1"


# ── The invariant that prevents the deadlock ─────────────────────────────────


class TestTheMergeStillGathersEveryLane:
    """The merge must sit on the **group** tether. A lane tether here deadlocks the run."""

    def test_the_merge_is_on_the_group_tether(self) -> None:
        rows = _wrap(AGENTS)

        assert _tether(rows, "CTRL_MERGE") == _tether(rows, "CTRL_SCATTER")

    def test_the_merge_is_not_on_any_lane_tether(self) -> None:
        rows = _wrap(AGENTS)

        assert _tether(rows, "CTRL_MERGE") not in _lane_tethers(rows)

    def test_every_lane_is_in_the_merges_gather_scope(self) -> None:
        """The assertion the whole 4c sequence was building toward."""
        rows = _wrap(AGENTS)
        merge = _tether(rows, "CTRL_MERGE")

        assert all(in_gather_scope(lane, merge) for lane in _lane_tethers(rows))

    def test_every_lane_maps_back_to_the_merge_via_lane_group(self) -> None:
        rows = _wrap(AGENTS)
        merge = _tether(rows, "CTRL_MERGE")

        assert {lane_group(lane) for lane in _lane_tethers(rows)} == {merge}

    def test_the_merge_still_waits_on_the_agent_node_ids(self) -> None:
        """Tethers changed; the `Wait_For` contract did not."""
        rows = _wrap(AGENTS)
        wait_for = next(r["Wait_For"] for r in rows if r["Node_ID"] == "CTRL_MERGE")

        assert set(wait_for.split("|")) == set(AGENTS)

    def test_two_scatters_do_not_share_a_gather_scope(self) -> None:
        """Different agent sets produce different groups, so lanes cannot cross-gather."""
        first = _wrap(AGENTS)
        second = _wrap([f"OTHER_{c}" for c in "ABCDEFGH"])
        merge_one = _tether(first, "CTRL_MERGE")

        assert _tether(second, "CTRL_MERGE") != merge_one
        assert not any(in_gather_scope(lane, merge_one) for lane in _lane_tethers(second))


# ── Reproducibility ──────────────────────────────────────────────────────────


class TestTheWrapIsReproducible:
    """The auto-wrap runs **twice per step** — once for pre-flight, once for execution.

    `_default_tether_id`'s docstring records why that matters: its predecessor was keyed on
    a CPython object address, so the tether validated was not necessarily the tether
    executed. Lane tethers derive from it, so they inherit the requirement.
    """

    def test_two_calls_produce_identical_tethers(self) -> None:
        assert _lane_tethers(_wrap(AGENTS)) == _lane_tethers(_wrap(AGENTS))

    def test_the_group_tether_is_the_documented_derivation(self) -> None:
        """Asserted against `_default_tether_id`, not a literal digest."""
        rows = _wrap(AGENTS)

        assert _tether(rows, "CTRL_SCATTER") == _default_tether_id(AGENTS)

    def test_a_different_agent_order_is_a_different_scatter(self) -> None:
        """The digest is over the ordered agent set, so this is a distinct scope."""
        reversed_agents = list(reversed(AGENTS))

        assert _default_tether_id(reversed_agents) != _default_tether_id(AGENTS)


# ── The operator-supplied tether ─────────────────────────────────────────────


class TestAnOperatorSuppliedTether:
    def test_it_becomes_the_group_and_the_lanes_derive_from_it(self) -> None:
        rows = _wrap(AGENTS, {"tether_id": "X"})

        assert _tether(rows, "CTRL_SCATTER") == "X"
        assert _tether(rows, "CTRL_MERGE") == "X"
        assert _lane_tethers(rows) == [f"X.{i}" for i in range(1, 9)]

    def test_a_blank_field_falls_back_to_the_generated_tether(self) -> None:
        """The authoring UI writes the key even when empty — a *present* empty string."""
        rows = _wrap(AGENTS, {"tether_id": "   "})

        assert _tether(rows, "CTRL_SCATTER") == _default_tether_id(AGENTS)

    @pytest.mark.parametrize("bad", ["a,b", "a|b", "a@b", "a>b", "X..1"])
    def test_an_unusable_tether_is_replaced_rather_than_propagated(self, bad: str) -> None:
        """A tether containing another seam's separator would corrupt `Wait_For`.

        This was already true before 4c-3 and merely silent. `child_tether_ids` refuses it,
        so the auto-wrap substitutes the generated tether and logs at ERROR. Propagating
        would be the approximately-correct identifier Principle 2 forbids; failing the
        build would take away an operator's flow over a field they can fix.
        """
        rows = _wrap(AGENTS, {"tether_id": bad})
        group = _tether(rows, "CTRL_SCATTER")

        assert group == _default_tether_id(AGENTS)
        assert validate_tether_id(group) == group
        assert _lane_tethers(rows) == child_tether_ids(group, 8)

    def test_the_substituted_group_still_gathers_its_lanes(self) -> None:
        """A fallback that broke the gather would be worse than the bad tether."""
        rows = _wrap(AGENTS, {"tether_id": "a,b"})
        merge = _tether(rows, "CTRL_MERGE")

        assert all(in_gather_scope(lane, merge) for lane in _lane_tethers(rows))

    def test_a_hierarchical_operator_tether_nests_one_level_deeper(self) -> None:
        """An operator naming `X.1` gets `X.1.1`..`X.1.8` — Requirement 18.3's shape."""
        rows = _wrap(AGENTS, {"tether_id": "X.1"})

        assert _lane_tethers(rows) == [f"X.1.{i}" for i in range(1, 9)]
        assert depth(_tether(rows, "AGENT_A")) == 2


# ── What this changed about the readout, and what it did not ─────────────────


class TestTheReadoutConsequences:
    """4c-3 moves two numbers in `total_sum_readout`. One is now right; one is not."""

    @staticmethod
    def _readout(agents: list[str]) -> dict[str, Any]:
        rows = _wrap(agents)
        for row in rows:
            row["Node_ID"] = f"{row['Node_ID']}_S0"
        return total_sum_readout(rows, step_index=0, max_workers=len(agents))

    def test_expected_peak_concurrency_is_now_correct(self) -> None:
        """**Fixed as a side effect, and worth pinning.**

        Before 4c-3 an 8-agent scatter had one distinct tether, so
        `min(lane_count, resolve_scatter_cap(8))` was `min(1, 8) == 1` — the pre-launch
        readout promised the operator a single thread for an 8-way run. With per-lane
        tethers the same expression yields 8.
        """
        assert self._readout(AGENTS)["expected_peak_concurrency"] == 8

    def test_the_lanes_are_now_individually_named_in_the_readout(self) -> None:
        """Eight lanes, and the group reported separately as a gather scope.

        Updated 2026-09-06 by task 4e. This asserted 9 `lane_tether_ids` — 8 lanes plus
        the group — which described the readout's state after 4c-3 rather than what
        Requirement 33.5 asks for. `lane_tether_ids` now holds lanes only.
        """
        readout = self._readout(AGENTS)

        assert len(readout["lane_tether_ids"]) == 8
        assert count_lanes(readout["lane_tether_ids"]) == 8
        assert readout["gather_scopes"] == [_default_tether_id(AGENTS)]

    def test_lane_count_reports_eight_lanes_for_an_eight_lane_scatter(self) -> None:
        """Requirement 33.5 asks for **the number of Flow Lanes**. Closed by task 4e.

        `lane_count = len(distinct Tether_ID)` had been wrong twice for this same scatter
        and in opposite directions: **1** while one tether covered the whole thing, then
        **9** once lanes had their own and the group counted as a tenth. A lane is now a
        tether with a parent, and the group — carried by the scatter and its merge — is
        reported as a gather scope instead.
        """
        readout = self._readout(AGENTS)

        assert readout["lane_count"] == 8
        assert readout["lane_count_source"] == "lane_tethers"

    def test_nodes_per_lane_excludes_the_control_nodes(self) -> None:
        """The scatter and merge are on the scope, not in a lane, so they are absent.

        The difference between this sum and `node_count` is exactly those two nodes — a
        gap that is informative rather than a miscount, which is why it is asserted.
        """
        readout = self._readout(AGENTS)

        assert sum(readout["nodes_per_lane"].values()) == 8
        assert readout["node_count"] == 10
