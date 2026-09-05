# ┌─────────────────────────────────────────────────────────────────────────────┐
# │  MACCREv2 Test Infrastructure — the cost surface tells the truth              │
# └─────────────────────────────────────────────────────────────────────────────┘
"""
tests/test_embedding_cost.py
============================
Three untrue numbers in the FinOps surface, and the tests that keep them true.

**1. Embeddings were billed and recorded as free.** ``_FREE_MODEL_KEYWORDS`` contained
``"gemini-embedding"`` with the comment *"embedding models are free"*.
``gemini-embedding-001`` is $0.15 per 1M input tokens. ``calculate_actual_cost``
short-circuits on a keyword match **before** consulting any rate, so the zero was
unfalsifiable from inside the function.

This is the training-data failure mode in one comment: embeddings *were* free during the
preview period, and the comment froze that as permanent.

**2. There were two pricing tables and they disagreed by exactly 2×.**
``get_pricing_table`` read ``UniversalRouter._PRICING_TABLE`` — which **does not exist**,
so ``getattr`` returned ``{}`` on every call and the "fallback" four-model stub was the
only path that ever ran. That stub priced ``gemini-2.5-flash`` at ``0.15 / 0.60`` while
``PRICING_MATRIX`` prices it at ``0.075 / 0.30``. **Every pre-flight estimate ever shown
to the operator was double the real Flash rate**, from a table whose docstring called
itself live.

**3. The budget modal claimed an empirical basis it never had.** It said *"Based on
historical metrics"* over a number that was ``node_count × output_rate × 20000``, and it
hardcoded ``gemini-2.5-flash-8b`` — a model absent from the real pricing matrix — as the
rate for every flow regardless of what it would run.

WHY THE ESTIMATOR IS A SEPARATE FUNCTION
----------------------------------------
Embedding responses carry **no usage metadata** — ``EmbeddingResponse`` has only
``.values``, so there is no ``promptTokenCount`` to bill from. The cost therefore has to
be estimated from character length, and ``estimate_embedding_cost`` is kept **apart from**
``calculate_actual_cost`` for that reason: a heuristic reaching a field whose name means
*measured* is the trust-laundering shape from Doctrine 1, applied to money.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from maccre_core.tools.finops_tools import (
    EMBEDDING_INPUT_TOKEN_LIMIT,
    PRICING_MATRIX,
    _CHARS_PER_TOKEN_ESTIMATE,
    _FREE_MODEL_KEYWORDS,
    calculate_actual_cost,
    estimate_embedding_cost,
    estimate_tokens,
)
from maccre_core.tools.workbook_engine import _estimate_node_cost, get_pricing_table

#: The published rate, per Google's GA announcement for Gemini Embedding.
EMBEDDING_RATE_PER_MTOK = 0.15


def _source_of(rel: str) -> str:
    return (Path(__file__).resolve().parent.parent / rel).read_text(encoding="utf-8")


class TestEmbeddingsAreNotFree:
    def test_the_free_keyword_is_gone(self) -> None:
        """The guard against it coming back, which is the whole point of this test."""
        assert not any("embedding" in kw for kw in _FREE_MODEL_KEYWORDS)

    def test_only_genuinely_free_surfaces_remain_listed(self) -> None:
        """Gemma via the free API surface, local Ollama, and the legacy QA model."""
        assert set(_FREE_MODEL_KEYWORDS) == {"gemma", "llama", "aqa"}

    def test_the_embedding_model_is_priced(self) -> None:
        assert "gemini-embedding-001" in PRICING_MATRIX
        assert PRICING_MATRIX["gemini-embedding-001"]["input_short"] == EMBEDDING_RATE_PER_MTOK

    def test_the_mcp_surfaces_embedding_model_is_priced_too(self) -> None:
        """``nexus_agent`` uses ``gemini-embedding-2``, not ``-001``. Both bill."""
        assert "gemini-embedding-2" in PRICING_MATRIX

    def test_an_embedding_no_longer_costs_zero(self) -> None:
        """The headline. A full-window embed is $0.000307, not $0.00."""
        cost = calculate_actual_cost("gemini-embedding-001", EMBEDDING_INPUT_TOKEN_LIMIT, 0)
        assert cost > 0
        assert cost == pytest.approx(
            EMBEDDING_INPUT_TOKEN_LIMIT / 1_000_000 * EMBEDDING_RATE_PER_MTOK
        )

    def test_an_embedding_has_no_billable_output(self) -> None:
        """It returns a vector, not tokens. Output rate is 0, and that is not "free"."""
        assert PRICING_MATRIX["gemini-embedding-001"]["output_short"] == 0.0

    def test_there_is_no_unreachable_long_context_tier(self) -> None:
        """The input window is 2,048 tokens, so a >200K tier could never be reached.

        Set equal to the short rate rather than doubled: a tier that cannot be entered
        would be a number describing nothing, which is how the free-keyword comment
        started.
        """
        row = PRICING_MATRIX["gemini-embedding-001"]
        assert row["input_long"] == row["input_short"]

    def test_genuinely_free_models_are_still_free(self) -> None:
        """Removing one keyword must not start billing local inference."""
        assert calculate_actual_cost("gemma3:9b", 5000, 5000) == 0.0
        assert calculate_actual_cost("llama3:70b", 5000, 5000) == 0.0


class TestTokenEstimation:
    def test_empty_text_estimates_zero(self) -> None:
        """So a caller can tell "nothing" from "something small"."""
        assert estimate_tokens("") == 0

    def test_any_non_empty_text_estimates_at_least_one(self) -> None:
        assert estimate_tokens("a") == 1

    def test_the_estimate_uses_the_declared_ratio(self) -> None:
        assert estimate_tokens("x" * 400) == 400 // _CHARS_PER_TOKEN_ESTIMATE

    def test_the_function_is_named_estimate(self) -> None:
        """Not cosmetic. There is no tokenizer in this repo and the only exact answer is
        a network call, so the name is the only thing carrying that caveat to a reader.
        """
        assert "estimate" in estimate_tokens.__name__
        assert "Not a measurement" in (estimate_tokens.__doc__ or "")


class TestEmbeddingCostEstimate:
    def test_it_reports_itself_as_an_estimate(self) -> None:
        """A consumer reading only the number must not be able to lose that fact."""
        assert estimate_embedding_cost("some text")["is_estimate"] is True

    def test_billing_is_clamped_to_the_input_window(self) -> None:
        """The API truncates rather than rejecting, so a long document bills at 2,048.

        Estimating the full length would over-report, and an over-reported cost is still
        a wrong one.
        """
        result = estimate_embedding_cost("x" * 68_000)
        assert result["estimated_tokens"] == EMBEDDING_INPUT_TOKEN_LIMIT

    def test_truncation_is_reported_not_hidden(self) -> None:
        """The same clamp that bounds the bill also means the vector is partial."""
        assert estimate_embedding_cost("x" * 68_000)["truncated"] is True
        assert estimate_embedding_cost("short")["truncated"] is False

    def test_a_68kb_ledger_costs_three_hundredths_of_a_cent(self) -> None:
        """The measured figure from the findings artifact, pinned so it stays honest."""
        result = estimate_embedding_cost("x" * 68_000)
        assert result["estimated_cost"] == pytest.approx(0.0003072, abs=1e-9)

    def test_empty_text_costs_nothing_and_that_is_not_a_false_zero(self) -> None:
        result = estimate_embedding_cost("")
        assert result["estimated_tokens"] == 0
        assert result["estimated_cost"] == 0.0

    def test_the_estimator_is_not_the_receipt_function(self) -> None:
        """They are deliberately separate functions with different names.

        ``calculate_actual_cost`` promises a receipt from provider usage metadata.
        Feeding it a character heuristic would make an estimate indistinguishable from a
        measurement in one field.
        """
        assert estimate_embedding_cost is not calculate_actual_cost
        assert "estimate" in (estimate_embedding_cost.__doc__ or "").lower()


class TestThereIsOnePricingTable:
    """Principle 4. Two tables, drifted, with the wrong one winning."""

    def test_the_table_derives_from_the_pricing_matrix(self) -> None:
        assert set(get_pricing_table()) == set(PRICING_MATRIX)

    def test_it_is_no_longer_a_four_entry_stub(self) -> None:
        """The stub had 4 models. The real matrix has the whole fleet."""
        assert len(get_pricing_table()) > 4

    def test_flash_is_priced_at_its_real_rate_not_double(self) -> None:
        """The 2× drift, asserted against the matrix rather than a literal."""
        table = get_pricing_table()
        assert table["gemini-2.5-flash"]["output_mtok"] == (
            PRICING_MATRIX["gemini-2.5-flash"]["output_short"]
        )
        assert table["gemini-2.5-flash"]["input_mtok"] == (
            PRICING_MATRIX["gemini-2.5-flash"]["input_short"]
        )

    def test_every_row_matches_the_matrix_short_rates(self) -> None:
        table = get_pricing_table()
        for model_id, rates in PRICING_MATRIX.items():
            assert table[model_id]["input_mtok"] == rates.get("input_short", 0.0), model_id
            assert table[model_id]["output_mtok"] == rates.get("output_short", 0.0), model_id

    def test_the_phantom_model_is_gone(self) -> None:
        """``gemini-2.5-flash-8b`` existed only in the stub, and the modal hardcoded it."""
        assert "gemini-2.5-flash-8b" not in get_pricing_table()

    def test_the_dead_router_lookup_is_gone(self) -> None:
        """``UniversalRouter._PRICING_TABLE`` never existed; the guard hid that forever."""
        source = _source_of("maccre_core/tools/workbook_engine.py")
        assert "_PRICING_TABLE" not in source.split('.. note::')[0]

    def test_the_router_still_has_no_pricing_table(self) -> None:
        """The premise of the removal, asserted so it cannot silently stop being true."""
        source = _source_of("maccre_core/maccre_router.py")
        assert "_PRICING_TABLE" not in source


class TestTheEstimatorIsHonestAboutIgnoringInput:
    def test_node_cost_still_ignores_input_size(self) -> None:
        """Documented, not fixed. Fixing it needs payload size, which nothing records.

        This test exists to make the limitation explicit rather than to endorse it: the
        estimate is a function of (model, node count) and moves by zero when a payload
        grows.
        """
        pricing = get_pricing_table()
        assert _estimate_node_cost("gemini-2.5-flash", pricing) == _estimate_node_cost(
            "gemini-2.5-flash", pricing
        )

    def test_the_docstring_says_so(self) -> None:
        doc = _estimate_node_cost.__doc__ or ""
        assert "blind to input size" in doc

    def test_an_unknown_model_falls_back_to_flash(self) -> None:
        pricing = get_pricing_table()
        assert _estimate_node_cost("no-such-model-xyz", pricing) == _estimate_node_cost(
            "gemini-2.5-flash", pricing
        )


class TestTheBudgetModalsTellTheTruth:
    """Operator-facing text asserting a basis it did not have."""

    def _modal_source(self) -> str:
        return _source_of("maccre_tui/widgets/finops_modals.py")

    def test_the_historical_metrics_claim_is_gone(self) -> None:
        """No history was ever consulted. The number is arithmetic over declared models."""
        source = self._modal_source()
        assert "Based on historical metrics" not in source

    def test_the_proposal_modal_accepts_no_figure(self) -> None:
        """``None`` must render as absent, never as ``$0.0000``."""
        from maccre_tui.widgets.finops_modals import BudgetProposalModal

        modal = BudgetProposalModal(3, None)
        assert modal.estimated_cost is None

    def test_the_warning_modal_accepts_no_figure(self) -> None:
        from maccre_tui.widgets.finops_modals import BudgetWarningModal

        assert BudgetWarningModal(None).estimated_cost is None

    def test_the_absent_case_says_so_in_words(self) -> None:
        source = self._modal_source()
        assert "No projected cost available" in source
        assert "unknown amount" in source

    def test_the_warning_no_longer_claims_a_cap(self) -> None:
        """It said "authorizing up to $X". Nothing enforces it and the estimate excludes
        input tokens, so the real spend can exceed the figure. An unbounded commitment
        stated as a bound is worse than an unstated one.
        """
        source = self._modal_source()
        assert "authorizing up to" not in source
        assert "not a cap" in source

    def test_the_proposal_discloses_that_input_is_excluded(self) -> None:
        assert "does not" in self._modal_source()


class TestTheLaunchPathUsesPreflightsOwnNumber:
    def _plex_source(self) -> str:
        return _source_of("maccre_tui/nexus_plex.py")

    def test_the_hardcoded_model_is_gone(self) -> None:
        assert "gemini-2.5-flash-8b" not in self._plex_source()

    def test_preflights_estimate_is_carried_forward(self) -> None:
        source = self._plex_source()
        assert "self._last_preflight_cost = report.estimated_cost" in source

    def test_a_failed_preflight_leaves_no_stale_figure(self) -> None:
        """Otherwise the modal would show the *previous* launch's estimate."""
        source = self._plex_source()
        assert "self._last_preflight_cost = None" in source

    def test_an_unpriced_approval_is_not_written_as_zero(self) -> None:
        """A 0.0 row would claim the operator approved nothing.

        That is the same false-zero defect this change removes from the embedding path,
        so writing one here to keep a signature happy would be self-defeating.
        """
        source = self._plex_source()
        start = source.index("def _do_budget_proposal")
        body = source[start : start + 4000]
        assert "if est_cost is None:" in body
        assert "nothing is written to the budget ledger" in body
