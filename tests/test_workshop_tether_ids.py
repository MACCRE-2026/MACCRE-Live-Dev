"""tests/test_workshop_tether_ids.py
=====================================
Task 4d — the TUI stops minting its own tether IDs.

`macronode_workshop` generated `tether_a`, `tether_b`, ... from a private counter while the
engine generated `scatter_<sha1[:8]>`. Two sources for one identifier, and the TUI's value
can reach the engine through `cfg["tether_id"]` and become the group tether. That split is
Principle 4's named incident — a TUI building `NAME_{i}` while the engine built `NAME_S{i}`,
*"harmless while the TUI only drew them; wrong the moment anything acted on what was
drawn"* — and a tether **is** acted on: it is what the fan-in gather gate scopes by.

The old scheme also had a defect past 26 that was not merely an ugly name.
`chr(96 + n)` walks off the alphabet: the 27th scatter in one session produced `tether_{`
and the **28th produced `tether_|`**, a tether containing a routing-target delimiter that
`parse_targets` splits — so `Wait_For` would read one lane as two.
`TestTheAlphabetOverflowIsGone` is the regression guard.

**What is stubbed, and what is not.** These tests drive the real `_handle_node_add` on a real
`MacroNodeWorkshop` instance. Only two things are replaced, both because they require a
running Textual app rather than because they are inconvenient: `post_message` and
`_emit_dict_update`. `_sync_visualizer` is left alone — it already swallows the `query_one`
failure. The tether assignment itself, the `_pending_scatters` pairing and the
`FlowDictBuffer` write are all the production code.
"""
from __future__ import annotations

from typing import Any

import pytest

from maccre_core.flow_dict import FlowDictBuffer
from maccre_core.orchestration.tether import (
    FORBIDDEN_IN_TETHER_ID,
    child_tether_ids,
    in_gather_scope,
    lane_group,
    root_tether_id,
    validate_tether_id,
)
from maccre_tui.widgets.macronode_workshop import MacroNodeWorkshop
from maccre_tui.widgets.node_catalog import NodeAddRequested


class _Workshop:
    """A real `MacroNodeWorkshop` with only its app-dependent hooks replaced."""

    def __init__(self) -> None:
        self.w = object.__new__(MacroNodeWorkshop)
        self.w._flow_steps = []
        self.w._flow_dict = FlowDictBuffer()
        self.w._tether_counter = 0
        self.w._pending_scatters = []
        self.messages: list[Any] = []
        self.w.post_message = self.messages.append  # type: ignore[method-assign]
        self.w._emit_dict_update = lambda: None  # type: ignore[method-assign]

    def add(self, node_id: str, node_type: str = "control") -> dict[str, Any]:
        MacroNodeWorkshop._handle_node_add(
            self.w, NodeAddRequested(node_id=node_id, node_type=node_type, node_data={})
        )
        return self.w._flow_steps[-1]


@pytest.fixture()
def workshop() -> _Workshop:
    return _Workshop()


# ── One generator ────────────────────────────────────────────────────────────


class TestTheWorkshopUsesTheSeamsGenerator:
    def test_the_first_scatter_gets_the_first_root_tether(self, workshop: _Workshop) -> None:
        """`X`, not `tether_a`."""
        step = workshop.add("CTRL_SCATTER")

        assert step["tether_id"] == root_tether_id(0)
        assert step["tether_id"] == "X"

    def test_successive_scatters_walk_the_seams_sequence(self, workshop: _Workshop) -> None:
        """Asserted against `root_tether_id`, never against literals."""
        tethers = [workshop.add(f"CTRL_SCATTER_{i}")["tether_id"] for i in range(4)]

        assert tethers == [root_tether_id(i) for i in range(4)]
        assert tethers == ["X", "Y", "Z", "AA"]

    def test_it_no_longer_produces_the_old_prefix(self, workshop: _Workshop) -> None:
        assert not workshop.add("CTRL_SCATTER")["tether_id"].startswith("tether_")

    def test_the_tether_lands_in_both_places_the_engine_reads(
        self, workshop: _Workshop
    ) -> None:
        """`step["tether_id"]` feeds hydration; `step["config"]["tether_id"]` feeds the
        auto-wrap. Both mattered before and both still do."""
        step = workshop.add("CTRL_SCATTER")

        assert step["config"]["tether_id"] == step["tether_id"]

    def test_every_generated_tether_is_wellformed(self, workshop: _Workshop) -> None:
        for i in range(30):
            tether = workshop.add(f"CTRL_SCATTER_{i}")["tether_id"]
            assert validate_tether_id(tether) == tether

    def test_the_counter_resets_with_the_flow(self, workshop: _Workshop) -> None:
        """A new flow starts at `X` again, so tethers stay readable per session."""
        workshop.add("CTRL_SCATTER_1")
        workshop.add("CTRL_SCATTER_2")
        workshop.w.reset_flow_dict()

        assert workshop.add("CTRL_SCATTER_3")["tether_id"] == root_tether_id(0)


# ── The regression the old scheme actually had ───────────────────────────────


class TestTheAlphabetOverflowIsGone:
    """`chr(96 + n)` past 26 produced characters other seams parse as separators."""

    def test_the_twenty_eighth_scatter_no_longer_contains_a_routing_delimiter(self) -> None:
        """The concrete defect: `chr(96 + 28)` is `'|'`, which `parse_targets` splits.

        A tether of `tether_|` would make `Wait_For` read one lane as two.
        """
        assert chr(96 + 28) == "|", "the character this guards against"
        assert "|" in FORBIDDEN_IN_TETHER_ID

        shop = _Workshop()
        tethers = [shop.add(f"CTRL_SCATTER_{i}")["tether_id"] for i in range(30)]

        assert tethers[27] == root_tether_id(27)
        assert not any(c in FORBIDDEN_IN_TETHER_ID for t in tethers for c in t)

    def test_thirty_scatters_are_all_distinct(self) -> None:
        shop = _Workshop()
        tethers = [shop.add(f"CTRL_SCATTER_{i}")["tether_id"] for i in range(30)]

        assert len(set(tethers)) == 30


# ── The pairing the engine depends on ────────────────────────────────────────


class TestScatterMergePairingStillHolds:
    """The merge must end up on the **same** tether as its scatter — the group tether.

    4c-3 puts the merge on the group and the lanes beneath it. If the workshop paired them
    to different values, the authored topology would deadlock before the engine ever saw it.
    """

    def test_a_merge_pairs_to_the_scatters_tether(self, workshop: _Workshop) -> None:
        scatter = workshop.add("CTRL_SCATTER")
        merge = workshop.add("CTRL_MERGE")

        assert merge["tether_id"] == scatter["tether_id"]
        assert merge["config"]["tether_id"] == scatter["tether_id"]

    def test_pairing_is_last_in_first_out_across_two_scatters(
        self, workshop: _Workshop
    ) -> None:
        first = workshop.add("CTRL_SCATTER_1")
        second = workshop.add("CTRL_SCATTER_2")
        inner_merge = workshop.add("CTRL_MERGE_1")
        outer_merge = workshop.add("CTRL_MERGE_2")

        assert inner_merge["tether_id"] == second["tether_id"]
        assert outer_merge["tether_id"] == first["tether_id"]

    def test_concat_also_pairs(self, workshop: _Workshop) -> None:
        scatter = workshop.add("CTRL_SCATTER")

        assert workshop.add("CTRL_CONCAT")["tether_id"] == scatter["tether_id"]

    def test_a_merge_with_no_pending_scatter_stays_untethered(
        self, workshop: _Workshop
    ) -> None:
        """A plain fan-in outside any scatter. An invented tether would scope it wrongly."""
        assert workshop.add("CTRL_MERGE")["tether_id"] == ""

    def test_the_scatter_announces_its_tether_to_the_operator(
        self, workshop: _Workshop
    ) -> None:
        scatter = workshop.add("CTRL_SCATTER")
        hints = [m for m in workshop.messages if hasattr(m, "tether_id")]

        assert hints and hints[-1].tether_id == scatter["tether_id"]


# ── The cross-component tie ──────────────────────────────────────────────────


class TestATuiTetherWorksAsAnEngineGroupTether:
    """The point of having one generator: what the TUI authors, the engine can use.

    This is the assertion that would have caught the original divergence — it fails if the
    TUI's value cannot serve as a group tether the engine derives lanes from.
    """

    def test_the_engine_can_derive_lanes_from_a_workshop_tether(
        self, workshop: _Workshop
    ) -> None:
        group = workshop.add("CTRL_SCATTER")["tether_id"]

        lanes = child_tether_ids(group, 8)

        assert lanes == [f"{group}.{i}" for i in range(1, 9)]
        assert all(lane_group(lane) == group for lane in lanes)

    def test_those_lanes_gather_at_the_paired_merge(self, workshop: _Workshop) -> None:
        """End to end across both components: TUI pairs, engine derives, gate accepts."""
        workshop.add("CTRL_SCATTER")
        merge_tether = workshop.add("CTRL_MERGE")["tether_id"]

        lanes = child_tether_ids(merge_tether, 8)

        assert all(in_gather_scope(lane, merge_tether) for lane in lanes)

    def test_two_workshop_scatters_do_not_share_a_gather_scope(
        self, workshop: _Workshop
    ) -> None:
        first = workshop.add("CTRL_SCATTER_1")["tether_id"]
        second = workshop.add("CTRL_SCATTER_2")["tether_id"]

        assert not any(
            in_gather_scope(lane, first) for lane in child_tether_ids(second, 8)
        )
