# ┌─────────────────────────────────────────────────────────────────────────────┐
# │  MACCREv2 Test Infrastructure — Requirement 34: the step-boundary contract     │
# └─────────────────────────────────────────────────────────────────────────────┘
"""
tests/test_payload_contract.py
==============================
Real coverage for ``maccre_core/orchestration/payload_contract.py`` — the "3b with a
ceiling" step-boundary payload contract.

THE DECISION
------------
Three options were put to the operator. **3a** (the session ledger accompanying the
terminal output as a separate section) was rejected on a measured ground: **the ledger
already contains the upstream output**, being assembled from every agent ledger in the job,
so 3a would send the same prose twice at every hop — not linear growth across a multi-step
flow. **3b** identifies the upstream section *inside* the ledger instead. **3c** bounds it.
The operator chose the hybrid: *"basically 3b, until it gets too big and it turns 3c."*

WHAT IS NOT TESTED HERE, BECAUSE IT IS NOT BUILT
------------------------------------------------
**Nothing calls this module.** ``swarm_worker`` does not delegate to it, so no live flow
composes payloads this way. That is deliberate and it is recorded mechanically rather than
in prose: the ``strict=True`` marker for Requirement **34.1** in
``test_topological_semantic_spec.py`` is still red, and it asserts that ``swarm_worker``
references ``compose_step_payload``.

The reason for stopping short is specific. ``payload_bytes`` and per-node
``INFERENCE_COST`` attribution landed on 2026-09-05, and **no live flow has run since** — so
the *before* number for this contract does not exist and cannot be obtained once the
contract changes. Wiring is irreversible in exactly that one respect, so it waits for a
baseline run.
"""
from __future__ import annotations

import pytest

from maccre_core.orchestration.payload_contract import (
    ACCOMPANYING_CONTEXT_CHAR_CEILING,
    SECTION_SESSION_CONTEXT,
    SECTION_SOURCE_DOCUMENT,
    compose_step_payload,
    describe_step_payload,
    distil_truncated_context,
)

#: A ledger that is comfortably under the ceiling.
SMALL_LEDGER = (
    "## AGENT_A_S0\nThe first agent wrote this.\n\n"
    "## AGENT_B_S0\nThe second agent wrote this.\n"
)


class TestTheUpstreamOutputIsIdentifiedNotDuplicated:
    """Req 34.2 — the clause that makes 3b cheaper than 3a."""

    def test_the_upstream_prose_appears_exactly_once(self) -> None:
        composed = compose_step_payload(
            session_context=SMALL_LEDGER, upstream_node="AGENT_B_S0",
        )
        assert composed.count("The second agent wrote this.") == 1

    def test_the_upstream_node_is_named(self) -> None:
        """Lineage survives as an assertion in the document, not as a second copy."""
        composed = compose_step_payload(
            session_context=SMALL_LEDGER, upstream_node="AGENT_B_S0",
        )
        assert "AGENT_B_S0" in composed
        assert "immediate upstream output" in composed

    def test_the_whole_context_is_present_when_it_fits(self) -> None:
        composed = compose_step_payload(SMALL_LEDGER, "AGENT_B_S0")
        assert "The first agent wrote this." in composed
        assert "The second agent wrote this." in composed

    def test_the_context_section_is_labelled(self) -> None:
        assert SECTION_SESSION_CONTEXT in compose_step_payload(SMALL_LEDGER, "A_S0")


class TestTheSourceDocument:
    def test_it_is_included_when_supplied(self) -> None:
        composed = compose_step_payload(
            SMALL_LEDGER, "A_S0", source_document="the original user brief",
        )
        assert SECTION_SOURCE_DOCUMENT in composed
        assert "the original user brief" in composed

    def test_it_is_omitted_when_absent(self) -> None:
        """The first node's case: source and context are the same file.

        Emitting an empty labelled section would be a heading over nothing — the same
        defect shape as the ledger's memory-pins section, which rendered a heading only
        when it had rows.
        """
        composed = compose_step_payload(SMALL_LEDGER, "A_S0", source_document="")
        assert SECTION_SOURCE_DOCUMENT not in composed

    def test_the_source_precedes_the_context(self) -> None:
        """Matching the order agents have always received these in."""
        composed = compose_step_payload(SMALL_LEDGER, "A_S0", source_document="brief")
        assert composed.index(SECTION_SOURCE_DOCUMENT) < composed.index(SECTION_SESSION_CONTEXT)


class TestTheCeiling:
    """Req 34.3 — a named constant, in characters, honestly."""

    def test_the_ceiling_is_a_positive_integer(self) -> None:
        assert isinstance(ACCOMPANYING_CONTEXT_CHAR_CEILING, int)
        assert ACCOMPANYING_CONTEXT_CHAR_CEILING > 0

    def test_it_reuses_the_routers_large_context_threshold(self) -> None:
        """One notion of "this context is big" in the system, not two.

        The router's context-cache heuristic already treats 120,000 characters as its
        large-context trigger. Inventing a second number would be two representations of
        one judgement, free to drift.
        """
        assert ACCOMPANYING_CONTEXT_CHAR_CEILING == 120_000

    def test_it_stays_below_the_long_context_billing_tier(self) -> None:
        """Crossing 200,000 tokens changes the input *rate*, not just the volume.

        At ~4 chars/token the ceiling lands near 30k tokens — an order of magnitude below
        the tier boundary, so this contract cannot silently move a flow onto long-context
        pricing.
        """
        from maccre_core.tools.finops_tools import _LONG_CTX_THRESHOLD

        approx_tokens = ACCOMPANYING_CONTEXT_CHAR_CEILING / 4
        assert approx_tokens < _LONG_CTX_THRESHOLD

    def test_context_at_exactly_the_ceiling_is_not_truncated(self) -> None:
        """An off-by-one here would truncate a payload that fits."""
        exact = "z" * ACCOMPANYING_CONTEXT_CHAR_CEILING
        assert describe_step_payload(exact, "A_S0")["truncated"] is False


class TestTruncationIsHonest:
    """Req 34.4 — the clause that keeps a cut from masquerading as a summary."""

    @pytest.fixture()
    def oversized(self) -> str:
        return "line of prose\n" * (ACCOMPANYING_CONTEXT_CHAR_CEILING // 5)

    def test_an_oversized_context_is_truncated(self, oversized: str) -> None:
        report = describe_step_payload(oversized, "A_S0")
        assert report["truncated"] is True
        assert report["context_chars_removed"] > 0

    def test_the_payload_says_it_was_truncated(self, oversized: str) -> None:
        assert "TRUNCATED" in compose_step_payload(oversized, "A_S0")

    def test_the_payload_says_it_was_not_distilled(self, oversized: str) -> None:
        """The load-bearing half.

        A payload merely cut while implying it had been summarised would be a success
        claim over work that did not happen, inside the one document the next agent
        reasons from.
        """
        assert "NOT distilled" in compose_step_payload(oversized, "A_S0")

    def test_the_notice_states_how_much_was_removed(self, oversized: str) -> None:
        """"Some content was removed" is not a measurement."""
        composed = compose_step_payload(oversized, "A_S0")
        report = describe_step_payload(oversized, "A_S0")
        assert f"{report['context_chars_removed']:,}" in composed

    def test_the_result_respects_the_ceiling(self, oversized: str) -> None:
        report = describe_step_payload(oversized, "A_S0")
        assert report["context_chars_kept"] <= ACCOMPANYING_CONTEXT_CHAR_CEILING

    def test_a_notice_is_absent_when_nothing_was_cut(self) -> None:
        """No truncation, no notice. A standing caveat would be noise in every payload."""
        assert "TRUNCATED" not in compose_step_payload(SMALL_LEDGER, "A_S0")


class TestRetentionOrdering:
    """Req 34.5 — the newest end is kept, and the payload says which end went."""

    def test_the_newest_content_survives(self) -> None:
        filler = "f" * (ACCOMPANYING_CONTEXT_CHAR_CEILING * 2)
        composed = compose_step_payload(
            f"OLDEST_MARKER\n{filler}\nNEWEST_MARKER", "A_S0",
        )
        assert "NEWEST_MARKER" in composed

    def test_the_oldest_content_is_dropped(self) -> None:
        filler = "f" * (ACCOMPANYING_CONTEXT_CHAR_CEILING * 2)
        composed = compose_step_payload(
            f"OLDEST_MARKER\n{filler}\nNEWEST_MARKER", "A_S0",
        )
        assert "OLDEST_MARKER" not in composed

    def test_the_payload_states_which_end_was_kept(self) -> None:
        """Otherwise a reader cannot tell an early-flow gap from a late-flow one."""
        oversized = "g" * (ACCOMPANYING_CONTEXT_CHAR_CEILING * 2)
        composed = compose_step_payload(oversized, "A_S0")
        assert "most recent" in composed.lower()
        assert "oldest were dropped" in composed.lower()

    def test_the_cut_prefers_a_line_boundary(self) -> None:
        """So the section does not open mid-sentence."""
        body = "\n".join(f"turn {i} prose" for i in range(40_000))
        composed = compose_step_payload(body, "A_S0")
        context = composed.split(SECTION_SESSION_CONTEXT, 1)[1]
        first_line = context.strip().splitlines()[1]
        assert first_line.startswith("turn ")

    def test_an_unsplittable_blob_is_still_bounded(self) -> None:
        """A single line longer than the whole ceiling must not defeat the cut.

        Falling back to a hard character cut is correct here: an unsplittable blob is not
        a reason to emit nothing, nor a reason to exceed the ceiling.
        """
        blob = "h" * (ACCOMPANYING_CONTEXT_CHAR_CEILING * 2)
        report = describe_step_payload(blob, "A_S0")
        assert report["truncated"] is True
        assert report["context_chars_kept"] <= ACCOMPANYING_CONTEXT_CHAR_CEILING


class TestTheDistillationSeam:
    """Req 34.6 — named, unimplemented, and never conflated with truncation."""

    def test_it_returns_none(self) -> None:
        assert distil_truncated_context("some removed prose") is None

    def test_it_returns_none_for_empty_input_too(self) -> None:
        assert distil_truncated_context("") is None

    def test_it_does_not_fall_back_to_returning_its_input(self) -> None:
        """The ``None`` is load-bearing.

        A seam that quietly handed back the removed text would make "distilled" true by
        redefinition, and every message describing the payload would go false at the same
        moment.
        """
        removed = "the removed prose"
        assert distil_truncated_context(removed) != removed

    def test_the_report_states_that_nothing_was_distilled(self) -> None:
        """Reported rather than omitted: "we did not distil" is the fact that has to
        survive into any cost analysis of this change.
        """
        oversized = "i" * (ACCOMPANYING_CONTEXT_CHAR_CEILING * 2)
        assert describe_step_payload(oversized, "A_S0")["distilled"] is False


class TestTheMeasurementReport:
    """Req 34.7 — so a before-and-after comparison is possible at all."""

    def test_it_reports_every_documented_field(self) -> None:
        report = describe_step_payload(SMALL_LEDGER, "A_S0")
        for field in (
            "composed_chars", "context_chars", "context_chars_kept",
            "context_chars_removed", "truncated", "distilled", "ceiling",
        ):
            assert field in report

    def test_the_composed_size_matches_the_composed_payload(self) -> None:
        """A size that disagrees with the thing it measures is worse than no size."""
        report = describe_step_payload(SMALL_LEDGER, "A_S0", source_document="brief")
        composed = compose_step_payload(SMALL_LEDGER, "A_S0", source_document="brief")
        assert report["composed_chars"] == len(composed)

    def test_kept_plus_removed_accounts_for_the_whole_context(self) -> None:
        oversized = "j" * (ACCOMPANYING_CONTEXT_CHAR_CEILING * 3)
        report = describe_step_payload(oversized, "A_S0")
        assert report["context_chars_kept"] + report["context_chars_removed"] == (
            report["context_chars"]
        )

    def test_an_empty_context_is_reported_rather_than_rejected(self) -> None:
        """A step with no prior turns is a real case — the first one."""
        report = describe_step_payload("", "A_S0")
        assert report["context_chars"] == 0
        assert report["truncated"] is False


class TestItIsNotWiredYet:
    """The limit, asserted rather than trusted to a comment.

    Stated positively so it fails when wiring lands, which is the moment this file's
    "nothing calls this module" claim stops being true and needs deleting.
    """

    def test_the_worker_does_not_yet_delegate(self) -> None:
        from pathlib import Path

        source = (
            Path(__file__).resolve().parent.parent
            / "maccre_core" / "orchestration" / "swarm_worker.py"
        ).read_text(encoding="utf-8")
        assert "compose_step_payload(" not in source, (
            "swarm_worker now delegates — remove this test, remove the Req 34.1 xfail "
            "marker, and make sure a baseline run was recorded before the change"
        )
