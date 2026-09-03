# ┌─────────────────────────────────────────────────────────────────────────────┐
# │  MACCREv2 Test Suite — Phase 6.12 Task A0: CTRL_REVIEW Baseline Regression   │
# └─────────────────────────────────────────────────────────────────────────────┘
"""
tests/test_ctrl_review_baseline.py
==================================
Phase 6.12 Task A0 — machine-checkable form of the verified CTRL_REVIEW baseline.

The reference run is ``job_20260829-163448-6crd`` (project ``499_TEST``), recorded in
``.oracle_artifacts/2026-08-29_phase_6_12_ctrl_review_baseline.md``. It executed a
three-step flow with a real blocking HITL pause in the middle:

    OSINT_Analyst  ->  CTRL_REVIEW  ->  OSINT_Analyst
    (_S0)              (_S1, paused)     (_S2)

This module asserts the structural invariants that made that trace possible, using
no database, no network, and no LLM. Task A8 replaces the hardcoded ``CTRL_REVIEW``
intercept in ``flow_engine.py`` with registry-driven resolution; **these assertions
must stay green through that refactor.**

Why these particular assertions: ``CTRL_REVIEW`` is not a member of
``DeterministicNodeType``. The pause only fires because ``flow_engine`` renames the
node to ``CTRL_PAUSE_MANUAL``, which prefix-matches ``PAUSE = "CTRL_PAUSE"``. A node
literally named ``CTRL_REVIEW_S1`` resolves to ``None`` and
``execute_deterministic_node`` falls back to ``_handle_anchor`` — a silent
passthrough. So the rename is load-bearing, and losing it deletes the HITL
checkpoint without raising anything.

Agent node IDs are asserted by *pattern*, never by the literal ``1613`` seen in the
baseline: ``flow_engine._get_macronode`` derives them from ``id(name) % 9999``, a
CPython object address, so they are not stable across processes.
"""
from __future__ import annotations

import re
from typing import Any

from maccre_core.orchestration.deterministic_nodes import (
    DeterministicNodeType,
    _resolve_node_type,
    execute_deterministic_node,
)
from maccre_core.orchestration.flow_engine import FlowRunner, FlowStep

# ── Recorded baseline constants ───────────────────────────────────────────────
# Importable by A8's own tests so there is exactly one copy of these facts.

BASELINE_JOB_ID = "job_20260829-163448-6crd"
BASELINE_PROJECT = "499_TEST"

#: The node the flow engine substitutes for a ``CTRL_REVIEW`` step, pre-suffix.
REVIEW_PAUSE_NODE_ID = "CTRL_PAUSE_MANUAL"

#: Same node after ``_hydrate_topology`` appends the step suffix (review was step 1).
REVIEW_PAUSE_NODE_ID_S1 = "CTRL_PAUSE_MANUAL_S1"

#: Body of ``CTRL_PAUSE_MANUAL_S1_18.md``, byte for byte, minus the markdown heading.
BASELINE_PAUSE_LOG_MESSAGE = (
    "PAUSE node CTRL_PAUSE_MANUAL_S1: flow halted. Press Resume to continue."
)

#: Contents of ``HITL_injection.md``.
BASELINE_HITL_INJECTION = "What are the contents of the documents in Tranche 1"

#: ``__DATACENTER/499_TEST/autosave_flow.json`` verbatim.
BASELINE_FLOW_DEFINITION: list[dict[str, Any]] = [
    {
        "macronode_name": "OSINT_Analyst",
        "agent_mapping": {},
        "payload_mode": "Unified Ledger",
        "custom_instructions": "",
        "agent_tools_overrides": {"OSINT_Analyst": "none"},
        "config": {},
    },
    {
        "macronode_name": "CTRL_REVIEW",
        "agent_mapping": {},
        "payload_mode": "Unified Ledger",
        "custom_instructions": "",
        "agent_tools_overrides": {},
        "config": {},
    },
    {
        "macronode_name": "OSINT_Analyst",
        "agent_mapping": {},
        "payload_mode": "Unified Ledger",
        "custom_instructions": "",
        "agent_tools_overrides": {},
        "config": {},
    },
]

#: Node IDs in execution order, as patterns (see module docstring re: instability).
BASELINE_NODE_ID_PATTERNS = [
    r"^AGENT_OSINT_Analyst_\d{4}_S0$",
    r"^CTRL_PAUSE_MANUAL_S1$",
    r"^AGENT_OSINT_Analyst_\d{4}_S2$",
]

#: Ledger artifacts the run produced, as patterns. The trailing integer is the
#: ``task_queue`` row id, which is monotonic across the job.
BASELINE_ARTIFACT_PATTERNS = [
    r"^AGENT_OSINT_Analyst_\d{4}_S0_\d+\.md$",
    r"^CTRL_PAUSE_MANUAL_S1_\d+\.md$",
    r"^HITL_injection\.md$",
    r"^AGENT_OSINT_Analyst_\d{4}_S2_\d+\.md$",
]

#: The synthetic macro definition ``flow_engine`` substitutes for a review step.
#: A8 must keep producing a topology row that is *equivalent* to this, though it
#: may legitimately derive ``Next_Node`` from flow position instead of pinning END.
BASELINE_REVIEW_TOPOLOGY_ROW: dict[str, Any] = {
    "Node_ID": REVIEW_PAUSE_NODE_ID,
    "Model_Override": "none",
    "Wait_For": "none",
    "Next_Node": "END",
}


def _bare_runner() -> FlowRunner:
    """A ``FlowRunner`` with no ``__init__`` side effects.

    ``FlowRunner.__init__`` opens the MacroNode stores. ``_hydrate_topology`` and
    ``_find_starting_nodes`` are pure with respect to ``self``, so bypassing
    construction keeps this module free of database and filesystem dependencies.
    """
    return FlowRunner.__new__(FlowRunner)


# ── The load-bearing rename ───────────────────────────────────────────────────


class TestPauseClassification:
    """The renamed review node must classify as PAUSE, and CTRL_REVIEW must not."""

    def test_review_pause_node_classifies_as_pause(self) -> None:
        assert _resolve_node_type(REVIEW_PAUSE_NODE_ID_S1) is DeterministicNodeType.PAUSE

    def test_unsuffixed_review_pause_node_also_classifies_as_pause(self) -> None:
        assert _resolve_node_type(REVIEW_PAUSE_NODE_ID) is DeterministicNodeType.PAUSE

    def test_ctrl_review_itself_is_unclassifiable(self) -> None:
        """Documents *why* the rename exists.

        If a future change adds a ``REVIEW`` member to ``DeterministicNodeType``,
        this fails loudly — which is the signal that A8 may resolve review steps
        directly instead of renaming them.
        """
        assert _resolve_node_type("CTRL_REVIEW_S1") is None
        assert _resolve_node_type("DET_REVIEW_S1") is None


class TestPauseBehavior:
    """The pause must actually block, with the exact recorded message."""

    def _run(self, node_id: str = REVIEW_PAUSE_NODE_ID_S1) -> Any:
        task = {"payload_path": "", "job_id": BASELINE_JOB_ID}
        return execute_deterministic_node(node_id, task, topology_config={})

    def test_pause_requests_a_halt(self) -> None:
        assert self._run().should_pause is True

    def test_pause_message_matches_recorded_artifact(self) -> None:
        assert self._run().log_message == BASELINE_PAUSE_LOG_MESSAGE

    def test_pause_passes_payload_through_unchanged(self) -> None:
        task = {"payload_path": "/some/prior/ledger.md", "job_id": BASELINE_JOB_ID}
        result = execute_deterministic_node(
            REVIEW_PAUSE_NODE_ID_S1, task, topology_config={}
        )
        assert result.output_payload_path == "/some/prior/ledger.md"

    def test_auto_resume_config_bypasses_the_halt(self) -> None:
        """Guards the config path A8 must start honouring.

        The baseline never exercised this (its review step had an empty config), but
        the handler supports it. A8 stops discarding ``step.config``, so this asserts
        the behaviour that will then become reachable.
        """
        task = {"payload_path": "", "job_id": BASELINE_JOB_ID}
        result = execute_deterministic_node(
            REVIEW_PAUSE_NODE_ID_S1,
            task,
            topology_config={"auto_resume_after": 0.01},
        )
        assert result.should_pause is False


# ── Topology hydration ────────────────────────────────────────────────────────


class TestReviewTopologyHydration:
    """Step-suffixing and row shape for the review step (step index 1)."""

    def _hydrate(self) -> list[str]:
        rows = _bare_runner()._hydrate_topology(
            [dict(BASELINE_REVIEW_TOPOLOGY_ROW)],
            agent_mapping={},
            payload_mode="Unified Ledger",
            custom_instructions="",
            step_index=1,
            agent_tools_overrides={},
        )
        assert len(rows) == 1, "review step must hydrate to exactly one topology row"
        return rows[0]

    def test_node_id_gains_step_suffix(self) -> None:
        assert self._hydrate()[0] == REVIEW_PAUSE_NODE_ID_S1

    def test_next_node_end_is_not_suffixed(self) -> None:
        # END and FAILED are sentinels, not nodes — suffixing them breaks routing.
        assert self._hydrate()[3] == "END"

    def test_wait_for_stays_none(self) -> None:
        assert self._hydrate()[6] == "none"

    def test_row_has_full_csv_width(self) -> None:
        # 16 columns: Node_ID, Agent_Name, Model_Override, Next_Node, Temperature,
        # Instruction_Override, Wait_For, Failure_Target, Max_Recursion,
        # Artifact_Path, Live_Profile, Dialogue_Partner, Dialogue_Rounds,
        # Payload_Mode, Tools_Allowed, Tether_ID
        #
        # Tether_ID (index 15) was added in Phase 6.13 Task D3. The scatter
        # auto-wrap had been computing a tether and writing it into every row dict
        # since Phase 6.12, but this flatten step had no slot for it, so it never
        # reached the CSV and every task_queue row carried an empty tether.
        assert len(self._hydrate()) == 16

    def test_a_review_row_carries_an_empty_tether(self) -> None:
        # A standalone control node belongs to no scatter scope, so its tether is
        # legitimately blank — but the column must be present and addressable.
        assert self._hydrate()[15] == ""

    def test_payload_mode_is_carried_into_the_row(self) -> None:
        assert self._hydrate()[13] == "Unified Ledger"

    def test_review_node_is_the_step_entrypoint(self) -> None:
        starts = _bare_runner()._find_starting_nodes(
            [dict(BASELINE_REVIEW_TOPOLOGY_ROW)], step_index=1
        )
        assert starts == [REVIEW_PAUSE_NODE_ID_S1]


# ── Flow definition round-trip ────────────────────────────────────────────────


class TestBaselineFlowDefinition:
    """The recorded autosave_flow.json must survive FlowStep serialization."""

    def test_three_steps_with_review_in_the_middle(self) -> None:
        steps = [FlowStep.from_dict(d) for d in BASELINE_FLOW_DEFINITION]
        assert [s.macronode_name for s in steps] == [
            "OSINT_Analyst",
            "CTRL_REVIEW",
            "OSINT_Analyst",
        ]

    def test_round_trip_is_lossless(self) -> None:
        for recorded in BASELINE_FLOW_DEFINITION:
            assert FlowStep.from_dict(recorded).to_dict() == recorded

    def test_review_step_carried_an_empty_config(self) -> None:
        # The baseline exercised the default path only. Any A8 behaviour change that
        # depends on a populated config must not alter this case.
        assert FlowStep.from_dict(BASELINE_FLOW_DEFINITION[1]).config == {}

    def test_first_step_tool_override_survives(self) -> None:
        step = FlowStep.from_dict(BASELINE_FLOW_DEFINITION[0])
        assert step.agent_tools_overrides == {"OSINT_Analyst": "none"}


# ── Recorded trace shape ──────────────────────────────────────────────────────


class TestRecordedTraceShape:
    """Self-consistency of the recorded constants.

    These are cheap, but they stop the recorded baseline from silently drifting if
    someone edits the constants without re-reading the artifact directory.
    """

    def test_node_order_is_agent_pause_agent(self) -> None:
        assert len(BASELINE_NODE_ID_PATTERNS) == 3
        assert re.match(BASELINE_NODE_ID_PATTERNS[1], REVIEW_PAUSE_NODE_ID_S1)

    def test_pause_message_names_the_suffixed_node(self) -> None:
        assert REVIEW_PAUSE_NODE_ID_S1 in BASELINE_PAUSE_LOG_MESSAGE

    def test_hitl_injection_is_a_question_about_tranche_1(self) -> None:
        # Step 2's recorded output answers this, proving the resume carried context
        # rather than merely unblocking the queue.
        assert BASELINE_HITL_INJECTION.strip()
        assert "Tranche 1" in BASELINE_HITL_INJECTION

    def test_hitl_artifact_is_expected_among_the_ledger_outputs(self) -> None:
        assert any(
            re.match(p, "HITL_injection.md") for p in BASELINE_ARTIFACT_PATTERNS
        )
