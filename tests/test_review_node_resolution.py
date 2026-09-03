# ┌─────────────────────────────────────────────────────────────────────────────┐
# │  MACCREv2 Test Suite — Phase 6.12 Task A8: Registry-Driven Review Nodes      │
# └─────────────────────────────────────────────────────────────────────────────┘
"""
tests/test_review_node_resolution.py
====================================
Phase 6.12 Task A8 — ``CTRL_REVIEW`` resolves through the registry, not a hardcode.

Three inline blocks used to special-case review nodes by name:

* ``preflight_check`` skipped them entirely ("bypass validation")
* ``resume_flow`` and ``execute_flow`` each substituted a literal
  ``{"Node_ID": "CTRL_PAUSE_MANUAL", "Next_Node": "END", ...}``

That violated Law III (registry-driven, no string special-casing), skipped
validation, and discarded ``step.config`` — so an operator-configured
``auto_resume_after`` was silently ignored.

**These tests are the safety net for a behaviour-preserving refactor.** The
verified Aug 29 baseline (``tests/test_ctrl_review_baseline.py``) asserts the
recorded trace; this module asserts that the *new* resolution path reproduces the
row the hardcode used to build, and then goes further than the hardcode could.
"""
from __future__ import annotations

import inspect
from pathlib import Path
from typing import Any

import pytest

from maccre_core.orchestration.deterministic_nodes import (
    NODE_ALIASES,
    DeterministicNodeType,
    _resolve_node_type,
    execute_deterministic_node,
    resolve_primitive_node_id,
)
from maccre_core.orchestration.flow_engine import FlowRunner
from maccre_core.orchestration.local_broker import LocalMessageBroker

# Imported for the equivalence assertion — one copy of these facts.
from tests.test_ctrl_review_baseline import (
    BASELINE_PAUSE_LOG_MESSAGE,
    BASELINE_REVIEW_TOPOLOGY_ROW,
    REVIEW_PAUSE_NODE_ID,
    REVIEW_PAUSE_NODE_ID_S1,
)


@pytest.fixture()
def runner() -> FlowRunner:
    """A real FlowRunner against the temporary datacenter from conftest."""
    return FlowRunner(project_name="TEST_PROJECT")


def _review_row(runner: FlowRunner, name: str, config: dict[str, Any] | None = None) -> dict[str, Any]:
    macro_def = runner._get_macronode(name, step_config=config or {})
    rows = macro_def.get("topology_rows", [])
    assert len(rows) == 1, f"{name} must auto-wrap to exactly one topology row"
    return rows[0]


# ── The alias table ───────────────────────────────────────────────────────────


class TestPrimitiveAliasing:
    def test_review_aliases_to_the_manual_pause_primitive(self) -> None:
        assert resolve_primitive_node_id("CTRL_REVIEW") == REVIEW_PAUSE_NODE_ID
        assert resolve_primitive_node_id("DET_REVIEW") == REVIEW_PAUSE_NODE_ID

    def test_aliasing_is_case_insensitive_and_whitespace_tolerant(self) -> None:
        assert resolve_primitive_node_id("  ctrl_review  ") == REVIEW_PAUSE_NODE_ID

    def test_non_aliased_names_pass_through_unchanged(self) -> None:
        """Safe to apply to every control node, which is the point."""
        for name in ("CTRL_PAUSE", "CTRL_GATE", "CTRL_SCATTER", "CTRL_MERGE"):
            assert resolve_primitive_node_id(name) == name

    def test_every_alias_target_classifies_as_a_real_primitive(self) -> None:
        """An alias pointing at an unclassifiable id would silently passthrough.

        ``execute_deterministic_node`` falls back to ``_handle_anchor`` for an
        unknown type, so a bad alias target deletes the node's behaviour without
        raising anything.
        """
        for source, target in NODE_ALIASES.items():
            assert _resolve_node_type(target) is not None, (
                f"alias {source} -> {target} resolves to no primitive"
            )

    def test_review_alias_target_is_specifically_pause(self) -> None:
        assert _resolve_node_type(NODE_ALIASES["CTRL_REVIEW"]) is DeterministicNodeType.PAUSE


# ── Equivalence with the removed hardcode ─────────────────────────────────────


class TestHardcodeEquivalence:
    """The refactor must be behaviour-preserving for the default case."""

    def test_ctrl_review_produces_the_baseline_node_id(self, runner: FlowRunner) -> None:
        assert _review_row(runner, "CTRL_REVIEW")["Node_ID"] == REVIEW_PAUSE_NODE_ID

    def test_ctrl_review_defaults_match_the_hardcoded_row(self, runner: FlowRunner) -> None:
        row = _review_row(runner, "CTRL_REVIEW")
        for key, expected in BASELINE_REVIEW_TOPOLOGY_ROW.items():
            assert row[key] == expected, f"{key} drifted from the recorded baseline"

    def test_det_review_now_resolves_instead_of_raising(self, runner: FlowRunner) -> None:
        """The legacy prefix used to need its own branch.

        The auto-wrap gate is ``is_deterministic_node()``, which admits ``DET_``;
        a literal ``startswith("CTRL_")`` would let ``DET_REVIEW`` fall through to
        ``KeyError`` now that the inline special-case is gone.
        """
        assert _review_row(runner, "DET_REVIEW")["Node_ID"] == REVIEW_PAUSE_NODE_ID

    def test_hydrated_node_id_matches_the_baseline(self, runner: FlowRunner) -> None:
        """End of the chain: resolution -> hydration -> the recorded node id."""
        rows = runner._hydrate_topology(
            [_review_row(runner, "CTRL_REVIEW")],
            agent_mapping={},
            payload_mode="Unified Ledger",
            step_index=1,
        )
        assert rows[0][0] == REVIEW_PAUSE_NODE_ID_S1
        assert rows[0][3] == "END"
        assert rows[0][6] == "none"

    def test_full_chain_reproduces_the_recorded_pause_message(
        self, runner: FlowRunner
    ) -> None:
        """Resolution -> hydration -> dispatch, asserted against the artifact.

        The recorded ``CTRL_PAUSE_MANUAL_S1_18.md`` body must still be produced
        byte for byte.
        """
        rows = runner._hydrate_topology(
            [_review_row(runner, "CTRL_REVIEW")], agent_mapping={}, step_index=1
        )
        node_id = rows[0][0]
        result = execute_deterministic_node(
            node_id, {"payload_path": "", "job_id": "job_a8"}, topology_config={}
        )
        assert result.should_pause is True
        assert result.log_message == BASELINE_PAUSE_LOG_MESSAGE

    def test_review_is_a_system_node_with_no_model(self, runner: FlowRunner) -> None:
        row = _review_row(runner, "CTRL_REVIEW")
        assert row["Agent_Name"] == "SYSTEM"
        assert row["Model_Override"] == "none"

    def test_review_declares_no_agent_slots(self, runner: FlowRunner) -> None:
        macro_def = runner._get_macronode("CTRL_REVIEW", step_config={})
        assert macro_def["agent_slots"] == []


# ── What the hardcode could not do ────────────────────────────────────────────


class TestConfigIsHonoured:
    """``step.config`` was discarded by the hardcode. It now drives the row."""

    def test_next_node_can_be_overridden(self, runner: FlowRunner) -> None:
        """The mechanism a review node inside a scatter lane needs.

        Pinned to ``END``, a mid-lane review node would close its lane's internal
        DAG instead of continuing to the lane's next node.
        """
        row = _review_row(runner, "CTRL_REVIEW", {"next_node": "AGENT_Synthesizer"})
        assert row["Next_Node"] == "AGENT_Synthesizer"

    def test_next_node_is_step_suffixed_when_hydrated(self, runner: FlowRunner) -> None:
        rows = runner._hydrate_topology(
            [_review_row(runner, "CTRL_REVIEW", {"next_node": "AGENT_Next"})],
            agent_mapping={},
            step_index=2,
        )
        assert rows[0][3] == "AGENT_Next_S2"

    def test_wait_for_can_be_overridden(self, runner: FlowRunner) -> None:
        row = _review_row(runner, "CTRL_REVIEW", {"wait_for": "LANE_A|LANE_B"})
        assert row["Wait_For"] == "LANE_A|LANE_B"

    def test_instruction_and_failure_target_are_configurable(
        self, runner: FlowRunner
    ) -> None:
        row = _review_row(
            runner,
            "CTRL_REVIEW",
            {"instruction_override": "check the citations", "failure_target": "CTRL_CLEANUP"},
        )
        assert row["Instruction_Override"] == "check the citations"
        assert row["Failure_Target"] == "CTRL_CLEANUP"

    def test_blank_config_values_fall_back_to_defaults(self, runner: FlowRunner) -> None:
        """An empty string from a UI field must not produce an empty Next_Node."""
        row = _review_row(runner, "CTRL_REVIEW", {"next_node": "   ", "wait_for": ""})
        assert row["Next_Node"] == "END"
        assert row["Wait_For"] == "none"

    def test_auto_resume_config_reaches_the_pause_handler(self) -> None:
        """The concrete capability the discarded config used to block."""
        result = execute_deterministic_node(
            REVIEW_PAUSE_NODE_ID_S1,
            {"payload_path": "", "job_id": "job_a8"},
            topology_config={"auto_resume_after": 0.01},
        )
        assert result.should_pause is False

    def test_config_does_not_leak_between_resolutions(self, runner: FlowRunner) -> None:
        configured = _review_row(runner, "CTRL_REVIEW", {"next_node": "AGENT_X"})
        plain = _review_row(runner, "CTRL_REVIEW", {})
        assert configured["Next_Node"] == "AGENT_X"
        assert plain["Next_Node"] == "END"


# ── The hardcodes must not come back ─────────────────────────────────────────


class TestNoNameSpecialCasing:
    """Law III guard. The rollback traced a real outage to exactly this pattern."""

    @pytest.mark.parametrize(
        "method",
        [FlowRunner.execute_flow, FlowRunner.resume_flow, FlowRunner.preflight_check],
    )
    def test_no_executable_review_name_check_remains(self, method: Any) -> None:
        source = inspect.getsource(method)
        offenders = [
            line.strip()
            for line in source.splitlines()
            if ("CTRL_REVIEW" in line or "DET_REVIEW" in line)
            and not line.lstrip().startswith("#")
        ]
        assert offenders == [], f"name special-casing is back: {offenders}"

    @pytest.mark.parametrize(
        "method", [FlowRunner.execute_flow, FlowRunner.resume_flow]
    )
    def test_no_inline_macro_def_literal_remains(self, method: Any) -> None:
        source = inspect.getsource(method)
        executable = "\n".join(
            line for line in source.splitlines() if not line.lstrip().startswith("#")
        )
        assert "CTRL_PAUSE_MANUAL" not in executable, (
            "the substituted macro definition literal is back"
        )

    def test_preflight_no_longer_bypasses_review_steps(self) -> None:
        """The bypass was a bare ``continue`` before the existence check.

        Checked against executable lines only — the surviving comment quotes the
        removed one, which is deliberate documentation.
        """
        source = inspect.getsource(FlowRunner.preflight_check)
        executable = [
            line for line in source.splitlines() if not line.lstrip().startswith("#")
        ]
        assert not any("bypass validation" in line for line in executable)
        # And the macro definition lookup must be the first thing in the loop body
        # that touches the step, with no early exit ahead of it.
        joined = "\n".join(executable)
        lookup_index = joined.index("macro_def = self._get_macronode(macro_name")
        assert "continue" not in joined[:lookup_index]

    def test_auto_wrap_gate_is_prefix_agnostic(self) -> None:
        source = inspect.getsource(FlowRunner._get_macronode)
        assert "is_deterministic_node(name)" in source
        assert 'name.upper().startswith("CTRL_")' not in source

    def test_as_wrapped_snapshot_uses_the_shared_predicate(self) -> None:
        """A hand-maintained set of 16 node names had fallen behind the registry."""
        source = inspect.getsource(FlowRunner.execute_flow)
        assert "is_deterministic_node(a_name)" in source
        assert "special_nodes = {" not in source


# ── Resume routing ────────────────────────────────────────────────────────────


class TestResumeRouting:
    """The resume path must read the same successor the topology declares."""

    class FakeTopology:
        def __init__(self, mapping: dict[str, str]) -> None:
            self._mapping = mapping

        def get_node_config(self, node_id: str) -> dict[str, Any]:
            if node_id not in self._mapping:
                raise KeyError(node_id)
            return {"next_node_success": self._mapping[node_id]}

    @pytest.fixture()
    def broker(self, tmp_path: Path) -> Any:
        b = LocalMessageBroker(db_path=str(tmp_path / "q.db"))
        yield b
        b.close()

    def _seed_paused(self, broker: LocalMessageBroker, node: str) -> None:
        broker.inject_task(job_id="job_a8", payload_path="/p.md", starting_node=node)
        conn = broker._get_conn()
        conn.execute(
            "UPDATE task_queue SET lock_status = 'paused' WHERE current_node = ?",
            (node,),
        )
        conn.commit()

    def _successors(self, broker: LocalMessageBroker) -> set[str]:
        return {
            r[0]
            for r in broker._get_conn().execute(
                "SELECT current_node FROM task_queue WHERE job_id = 'job_a8' "
                "AND lock_status = 'open'"
            )
        }

    def test_defaults_to_end_without_a_topology(self, broker: LocalMessageBroker) -> None:
        """Preserves the previous behaviour when no provider is supplied."""
        self._seed_paused(broker, REVIEW_PAUSE_NODE_ID_S1)
        assert broker.resume_paused_task("job_a8", "/hitl.md") is True
        # END is a terminal sentinel — no successor row is created.
        assert self._successors(broker) == set()

    def test_routes_to_the_configured_successor(self, broker: LocalMessageBroker) -> None:
        """Regression for 'For now, we assume END'.

        With a config-driven ``next_node``, assuming END would resume straight to
        the end of the lane and silently drop everything after the review node.
        """
        self._seed_paused(broker, REVIEW_PAUSE_NODE_ID_S1)
        topo = self.FakeTopology({REVIEW_PAUSE_NODE_ID_S1: "AGENT_After_S1"})
        assert broker.resume_paused_task("job_a8", "/hitl.md", topology_engine=topo) is True
        assert "AGENT_After_S1" in self._successors(broker)

    def test_unknown_node_falls_back_to_end(self, broker: LocalMessageBroker) -> None:
        self._seed_paused(broker, REVIEW_PAUSE_NODE_ID_S1)
        assert broker.resume_paused_task(
            "job_a8", "/hitl.md", topology_engine=self.FakeTopology({})
        ) is True
        assert self._successors(broker) == set()

    def test_hitl_payload_is_carried_onto_the_successor(
        self, broker: LocalMessageBroker
    ) -> None:
        """The baseline proves resume carries context, not just unblocks."""
        self._seed_paused(broker, REVIEW_PAUSE_NODE_ID_S1)
        topo = self.FakeTopology({REVIEW_PAUSE_NODE_ID_S1: "AGENT_After_S1"})
        broker.resume_paused_task("job_a8", "/HITL_injection.md", topology_engine=topo)
        payloads = {
            r[0]
            for r in broker._get_conn().execute(
                "SELECT payload_path FROM task_queue WHERE current_node = 'AGENT_After_S1'"
            )
        }
        assert payloads == {"/HITL_injection.md"}

    def test_non_pause_paused_task_is_simply_reopened(
        self, broker: LocalMessageBroker
    ) -> None:
        """Only pause nodes need completing; anything else just resumes."""
        self._seed_paused(broker, "AGENT_Dialogue_S0")
        assert broker.resume_paused_task("job_a8", "/hitl.md") is True
        statuses = dict(
            broker._get_conn().execute(
                "SELECT current_node, lock_status FROM task_queue WHERE job_id = 'job_a8'"
            )
        )
        assert statuses["AGENT_Dialogue_S0"] == "open"

    def test_returns_false_when_nothing_is_paused(
        self, broker: LocalMessageBroker
    ) -> None:
        assert broker.resume_paused_task("job_a8") is False


# ── Registry consistency ──────────────────────────────────────────────────────


class TestControlNodeRegistryEntry:
    def test_review_handler_actually_exists(self) -> None:
        """The seed row used to name a function that exists nowhere.

        ``local_broker.intercept_review_via_route_task`` was declared as
        ``CTRL_REVIEW``'s handler; a repo-wide search found the name only in the
        registry seed itself.
        """
        import importlib

        from maccre_core.controlnode_registry import _BUILTIN_NODES

        entry = next(n for n in _BUILTIN_NODES if n["name"] == "CTRL_REVIEW")
        module = importlib.import_module(entry["handler_module"])
        assert hasattr(module, entry["handler_func"]), (
            f"{entry['handler_module']}.{entry['handler_func']} does not exist"
        )

    def test_review_handler_is_the_pause_handler(self) -> None:
        from maccre_core.controlnode_registry import _BUILTIN_NODES

        entry = next(n for n in _BUILTIN_NODES if n["name"] == "CTRL_REVIEW")
        assert entry["handler_func"] == "_handle_pause"
        assert entry["handler_module"] == "maccre_core.orchestration.deterministic_nodes"

    def test_every_builtin_handler_resolves(self) -> None:
        """Cheap sweep — one dangling handler was already hiding in here."""
        import importlib

        from maccre_core.controlnode_registry import _BUILTIN_NODES

        missing: list[str] = []
        for entry in _BUILTIN_NODES:
            if entry.get("status") != "active":
                continue
            try:
                module = importlib.import_module(entry["handler_module"])
            except ImportError:
                missing.append(f"{entry['name']}: module {entry['handler_module']}")
                continue
            if not hasattr(module, entry["handler_func"]):
                missing.append(f"{entry['name']}: {entry['handler_func']}")
        assert missing == [], f"active control nodes with no handler: {missing}"
