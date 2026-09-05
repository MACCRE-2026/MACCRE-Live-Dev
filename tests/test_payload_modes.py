# ┌─────────────────────────────────────────────────────────────────────────────┐
# │  MACCREv2 Test Infrastructure — the payload mode seam                        │
# └─────────────────────────────────────────────────────────────────────────────┘
"""
tests/test_payload_modes.py
===========================
One place names a payload mode, and these tests are what keeps it one place.

WHAT WAS WRONG
--------------
``"Unified Ledger"``, ``"Preceding Node Only"`` and ``"Targeted Filter"`` were bare
string literals in seven files. Only **two** conditionals in the whole tree actually
read the value, both in ``swarm_worker``, and both compared with ``==`` against a
literal:

- line ~1023, on the **completing** node, testing only for ``Targeted Filter``
- line ~1874, on the **successor**, testing only for ``Unified Ledger``

``Preceding Node Only`` was read by nothing. It was offered in the UI and worked by
*falling through* — when the mode was not ``Unified Ledger`` the routing override
simply did not fire, leaving the payload at the completing node's own artifact, which
for an intra-step hop is exactly preceding-node-only. Accidentally correct.

THE CONSEQUENCE THAT MATTERED MOST
----------------------------------
Because the tests were equality against a literal, a topology carrying ``"Unifed
Ledger"`` did not fail and did not warn — it silently routed as ``Preceding Node
Only``. A typo selected a different contract. ``TestATypoNoLongerSelectsAContract``
is the test for that, and it is the one behaviour this migration deliberately changes.

WHY SOURCE-LEVEL ASSERTIONS APPEAR HERE
---------------------------------------
``TestTheLiteralsAreGone`` reads source text, which is normally a weak form of test.
It is the right form here: the defect being prevented is *a fourth spelling appearing
in an eighth file*, and that is a property of the source rather than of any behaviour.
The same reasoning already applies in ``test_controlnode_registry_counts.py``.
"""
from __future__ import annotations

import inspect
import logging
from pathlib import Path

import pytest

from maccre_core.orchestration.payload_modes import (
    AUTHORABLE_MODES,
    DEFAULT_PAYLOAD_MODE,
    PayloadMode,
    resolve_payload_mode,
)
from maccre_core.orchestration.topology_engine import TopologyEngine

#: The files that used to spell a mode out for themselves.
_MIGRATED_SOURCES = (
    "maccre_core/orchestration/topology_engine.py",
    "maccre_core/orchestration/swarm_worker.py",
    "maccre_core/orchestration/flow_engine.py",
    "maccre_core/orchestration/macro_factory.py",
    "maccre_core/tools/admin_tools.py",
    "maccre_tui/nexus_plex.py",
    "maccre_tui/undo_manager.py",
)


def _repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


def _source_of(rel: str) -> str:
    return (_repo_root() / rel).read_text(encoding="utf-8")


class TestTheModesAreNamedOnce:
    def test_there_are_exactly_three(self) -> None:
        """A fourth mode is the thing this module exists to make visible."""
        assert {m.value for m in PayloadMode} == {
            "Unified Ledger",
            "Preceding Node Only",
            "Targeted Filter",
        }

    def test_the_default_is_unified_ledger(self) -> None:
        """Not a preference — it is what a missing column has always resolved to.

        ``topology_engine`` double-defaulted a missing *and* an empty ``Payload_Mode``
        to ``Unified Ledger``, and ``admin_tools`` padded short rows with it. Any other
        default would change the behaviour of every topology that omits the column.
        """
        assert DEFAULT_PAYLOAD_MODE is PayloadMode.UNIFIED_LEDGER

    def test_only_two_modes_are_authorable(self) -> None:
        """``Targeted Filter`` is produced by a macro template, not chosen by hand."""
        assert AUTHORABLE_MODES == (
            PayloadMode.UNIFIED_LEDGER,
            PayloadMode.PRECEDING_NODE_ONLY,
        )
        assert PayloadMode.TARGETED_FILTER not in AUTHORABLE_MODES

    def test_a_non_authorable_mode_is_still_a_real_mode(self) -> None:
        """The asymmetry is the point: unofferable, and still carried by real nodes.

        ``macro_factory`` writes ``Targeted Filter`` onto consensus advocate rows, so
        anything that *renders* a node's current mode has to handle all three even
        though only two are offered.
        """
        assert set(AUTHORABLE_MODES) < set(PayloadMode)


class TestResolution:
    def test_an_enum_passes_through(self) -> None:
        for mode in PayloadMode:
            assert resolve_payload_mode(mode) is mode

    def test_each_value_resolves_to_its_mode(self) -> None:
        for mode in PayloadMode:
            assert resolve_payload_mode(mode.value) is mode

    def test_absent_and_blank_resolve_to_the_default(self) -> None:
        for value in (None, "", "   ", "\t\n"):
            assert resolve_payload_mode(value) is DEFAULT_PAYLOAD_MODE

    def test_resolution_is_case_insensitive(self) -> None:
        """Casing is not a declaration. Being strict would widen the typo surface."""
        assert resolve_payload_mode("unified ledger") is PayloadMode.UNIFIED_LEDGER
        assert resolve_payload_mode("PRECEDING NODE ONLY") is PayloadMode.PRECEDING_NODE_ONLY
        assert resolve_payload_mode("targeted filter") is PayloadMode.TARGETED_FILTER

    def test_surrounding_whitespace_is_tolerated(self) -> None:
        """A CSV cell is hand-edited more often than it is generated."""
        assert resolve_payload_mode("  Unified Ledger  ") is PayloadMode.UNIFIED_LEDGER

    def test_an_unrecognised_mode_warns_rather_than_raising(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Deliberately unlike ``resolve_gather_strategy``, which raises.

        This runs on the worker's hot path and a topology typo is not worth killing a
        running flow over. There, defaulting would silently gather lanes the author
        asked to leave alone; here, defaulting lands on the mode the author meant.
        """
        with caplog.at_level(logging.WARNING):
            assert resolve_payload_mode("Unifed Ledger") is DEFAULT_PAYLOAD_MODE

        assert any("Unrecognised payload mode" in r.message for r in caplog.records)

    def test_the_warning_names_the_node(self, caplog: pytest.LogCaptureFixture) -> None:
        """A warning that does not say where sends the author through the whole CSV."""
        with caplog.at_level(logging.WARNING):
            resolve_payload_mode("nonsense", context="AGENT_A_S0")

        joined = " ".join(r.getMessage() for r in caplog.records)
        assert "AGENT_A_S0" in joined

    def test_a_non_string_does_not_crash_the_resolver(self) -> None:
        """The value arrives from a CSV cell, a JSON round-trip and a UI select."""
        assert resolve_payload_mode(0) is DEFAULT_PAYLOAD_MODE
        assert resolve_payload_mode([]) is DEFAULT_PAYLOAD_MODE


class TestATypoNoLongerSelectsAContract:
    """The one behaviour this migration changes, asserted rather than buried.

    Before: ``"Unifed Ledger"`` compared unequal to ``"Unified Ledger"``, the routing
    override did not fire, and the node was routed as ``Preceding Node Only`` in
    silence. After: it resolves to the default and says so.
    """

    @pytest.fixture()
    def engine(self, tmp_path: Path) -> TopologyEngine:
        csv_path = tmp_path / "topology.csv"
        csv_path.write_text(
            "Node_ID,Agent_Name,Model_Override,Next_Node,Temperature,"
            "Instruction_Override,Wait_For,Failure_Target,Payload_Mode\n"
            "GOOD_S0,SYSTEM,none,TYPO_S0,0,,none,FAILED,Preceding Node Only\n"
            "TYPO_S0,SYSTEM,none,BLANK_S0,0,,none,FAILED,Unifed Ledger\n"
            "BLANK_S0,SYSTEM,none,MISSING_S0,0,,none,FAILED,\n"
            "MISSING_S0,SYSTEM,none,END,0,,none,FAILED,unified ledger\n",
            encoding="utf-8",
        )
        return TopologyEngine(csv_path=str(csv_path))

    def test_a_valid_mode_survives_the_seam(self, engine: TopologyEngine) -> None:
        assert engine.get_node_config("GOOD_S0")["payload_mode"] == "Preceding Node Only"

    def test_a_typo_resolves_to_the_default(self, engine: TopologyEngine) -> None:
        assert engine.get_node_config("TYPO_S0")["payload_mode"] == "Unified Ledger"

    def test_a_blank_cell_resolves_to_the_default(self, engine: TopologyEngine) -> None:
        """Unchanged — the seam preserves the old double default."""
        assert engine.get_node_config("BLANK_S0")["payload_mode"] == "Unified Ledger"

    def test_casing_is_normalised_to_the_canonical_spelling(
        self, engine: TopologyEngine
    ) -> None:
        """The stored value is canonical, so downstream readers see one spelling."""
        assert engine.get_node_config("MISSING_S0")["payload_mode"] == "Unified Ledger"


class TestPrecedingNodeOnlyIsNowARealBranch:
    """It was offered in the UI and read by no conditional anywhere.

    A mode that exists only as a fall-through cannot be conditioned on, and the
    operator's stated ``CTRL_REVIEW`` design is conditioned on precisely this one:
    *"if Unified Ledger is selected the downstream agents see an entry on the ledger
    from the user; if Preceding Node is selected then the node ledger preceding
    CTRL_REVIEW and the HITL injection pass downstream."*
    """

    def _worker_source(self) -> str:
        return _source_of("maccre_core/orchestration/swarm_worker.py")

    def test_the_mode_is_branched_on(self) -> None:
        source = self._worker_source()
        assert "PayloadMode.PRECEDING_NODE_ONLY" in source

    def test_both_reads_go_through_the_resolver(self) -> None:
        """Neither read compares against a literal any more."""
        source = self._worker_source()
        assert source.count("resolve_payload_mode(") >= 2

    def test_the_reads_are_identity_comparisons_not_string_equality(self) -> None:
        source = self._worker_source()
        assert "is PayloadMode.TARGETED_FILTER" in source
        assert "is PayloadMode.UNIFIED_LEDGER" in source

    def test_the_branch_does_not_change_the_routing_payload(self) -> None:
        """The new branch is explicit and deliberately behaviour-neutral.

        Preceding-node-only routing is *already* what the surrounding code produces —
        the completing node's own artifact or ledger. Making the mode explicit must
        state that, not redefine it, or this migration would silently change what
        every non-Unified-Ledger node passes downstream.
        """
        source = self._worker_source()
        start = source.index("elif payload_mode is PayloadMode.PRECEDING_NODE_ONLY")
        body = source[start : start + 1400]
        # The branch logs and nothing else. An assignment here would be a behaviour
        # change wearing a clarification's clothes.
        assert "routing_payload_path =" not in body


class TestTheLiteralsAreGone:
    """Doctrine 4 guard. Three spellings across seven files invited a fourth.

    Not a style rule: the two reads were equality tests, so a literal that drifted
    from the one the reader compared against was *undetectable*.
    """

    @pytest.mark.parametrize("rel", _MIGRATED_SOURCES)
    def test_no_file_spells_a_mode_for_itself(self, rel: str) -> None:
        source = _source_of(rel)
        for literal in ('"Unified Ledger"', '"Preceding Node Only"', '"Targeted Filter"'):
            assert literal not in source, f"{rel} still spells {literal} for itself"

    def test_the_seam_itself_is_allowed_to_hold_them(self) -> None:
        """Exactly one file may contain the strings, and it is the enum's own."""
        source = _source_of("maccre_core/orchestration/payload_modes.py")
        assert 'UNIFIED_LEDGER = "Unified Ledger"' in source
        assert 'PRECEDING_NODE_ONLY = "Preceding Node Only"' in source
        assert 'TARGETED_FILTER = "Targeted Filter"' in source

    def test_every_migrated_file_reads_through_the_seam(self) -> None:
        """A file with no literal and no import would be a file that lost the concept."""
        for rel in _MIGRATED_SOURCES:
            source = _source_of(rel)
            if rel.endswith("undo_manager.py"):
                # Carries whatever the modal produced and never named a mode itself,
                # so it is on the list to prove it stays that way.
                assert "payload_mode" in source
                continue
            assert "payload_modes import" in source, rel


class TestTheConfigModalCannotBeHandedAnInvalidValue:
    """Defect F1's class: a widget constructed with a value its options exclude.

    A ``Targeted Filter`` node reaching the config modal used to supply the ``Select``
    a ``value`` that was not among its two options. That is decided at construction,
    inside a compose, where a raise is an app-killing traceback rather than a message.
    """

    def _modal_source(self) -> str:
        return _source_of("maccre_tui/nexus_plex.py")

    def test_the_options_are_derived_from_the_authorable_set(self) -> None:
        source = self._modal_source()
        assert "for m in AUTHORABLE_MODES" in source

    def test_a_non_authorable_current_value_is_added_to_the_options(self) -> None:
        source = self._modal_source()
        assert "if _current not in AUTHORABLE_MODES" in source

    def test_the_select_value_is_the_resolved_mode(self) -> None:
        """So a typo'd stored value cannot reach the widget either."""
        source = self._modal_source()
        assert "_current = resolve_payload_mode(self.current_payload_mode)" in source


class TestTheHitlResumePassesItsTopology:
    """``resume_paused_task``'s ``topology_engine`` had no caller supplying it.

    Omitted, a paused pause node resolves its successor to ``"END"``. So every HITL
    resume from the TUI closed the lane at the pause node and dropped whatever the
    operator had authored after it — while the parameter's own docstring warned about
    exactly that. The ``--smart`` shape: documented, and never passed.
    """

    def test_the_parameter_still_exists_and_still_defaults_to_none(self) -> None:
        from maccre_core.orchestration.local_broker import LocalMessageBroker

        sig = inspect.signature(LocalMessageBroker.resume_paused_task)
        assert sig.parameters["topology_engine"].default is None

    def test_the_tui_supplies_it(self) -> None:
        source = _source_of("maccre_tui/nexus_plex.py")
        start = source.index("def _hitl_resume_with_context")
        body = source[start : start + 2600]
        assert "topology_engine=TopologyEngine()" in body

    def test_resolution_still_falls_back_to_end_without_an_engine(self) -> None:
        """The fallback is kept. A caller with no topology has nothing better to say."""
        from maccre_core.orchestration.local_broker import LocalMessageBroker

        assert LocalMessageBroker._resolve_next_node(None, "CTRL_PAUSE_MANUAL_S1") == "END"
