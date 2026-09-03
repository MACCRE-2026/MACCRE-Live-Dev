# ┌─────────────────────────────────────────────────────────────────────────────┐
# │  MACCREv2 Test Suite — Phase 6.13 Task A6: Model Failover Chains            │
# └─────────────────────────────────────────────────────────────────────────────┘
"""
tests/test_model_failover_chains.py
===================================
Phase 6.13 Task A6 — degraded-mode routing must still have somewhere to go.

``ModelRegistry.get_failover_chain`` has two paths. When the live probe has
succeeded it derives a chain from real provider data, which is healthy and
self-updating. When the probe has *not* succeeded it falls back to a
hand-maintained table, and that table was written in the 3.1 era.

The lookup used to be::

    return _FALLBACK_CHAINS.get(normalized, [normalized])

so a model absent from the table received a chain containing only itself — no
failover at all. The API now serves ``gemini-3.7-flash`` (confirmed live: 53
models, 3.5 / 3.6 / 3.7 all present), none of which the table knows. A run pinned
to 3.7 therefore had zero failover the moment the probe was unavailable.

This is the same failure shape as the hand-maintained ``special_nodes`` list
fixed earlier in Phase 6.12: a literal table shadowing a registry that already
knew better. The fix is the same in spirit — treat the table as *tier exemplars*
for cold start, and derive coverage from it rather than requiring exact hits.

These tests are offline. They exercise the degraded path deliberately, because
that is the path that was broken; the live path needs credentials and is covered
by ``omni smoke``.
"""
from __future__ import annotations

from typing import Any

import pytest

from maccre_core._net.model_registry import (
    _FALLBACK_CHAINS,
    _TIER_ORDER,
    ModelRegistry,
    ModelSurface,
    _build_fallback_chain,
    _classify_tier,
    _known_fallback_models,
)

#: Models the live probe confirmed on 2026-08-30 that the table does not list.
#: Hardcoded rather than probed so the test stays offline and deterministic.
NEWER_THAN_THE_TABLE = [
    "gemini-3.7-flash",
    "gemini-3.6-flash",
    "gemini-3.5-flash",
    "gemini-3.5-flash-lite",
    "gemini-3.1-flash-lite",
    "gemini-flash-latest",
]


@pytest.fixture()
def degraded_registry() -> Any:
    """A registry that believes its live probe failed, without touching the network."""
    reg = ModelRegistry.__new__(ModelRegistry)
    reg._probe_ok = False
    reg._sentinel = None
    reg._by_surface = {}
    reg._surface_of = {}
    reg._gc_models = []
    # _maybe_refresh must not attempt a probe.
    reg._maybe_refresh = lambda: None  # type: ignore[method-assign]
    return reg


class TestTheOriginalGap:
    """A6 — the specific defect: no failover for anything newer than the table."""

    def test_the_table_does_not_list_current_models(self) -> None:
        """Establishes the premise, so the tests below are not vacuous.

        If the table is ever brought up to date this test fails loudly, which is
        the right prompt to re-check what "newer than the table" now means.
        """
        for model in NEWER_THAN_THE_TABLE:
            assert model not in _FALLBACK_CHAINS, (
                f"{model} is now in the table; refresh NEWER_THAN_THE_TABLE"
            )

    @pytest.mark.parametrize("model", NEWER_THAN_THE_TABLE)
    def test_an_unlisted_model_still_gets_real_failover(self, model: str) -> None:
        """The fix. Previously each of these returned a chain of exactly one."""
        chain = _build_fallback_chain(model)

        assert len(chain) > 1, (
            f"{model} has no failover in degraded mode — chain was {chain}"
        )
        assert chain[0] == model, "the requested model must lead its own chain"

    def test_the_registry_uses_the_derived_chain_in_degraded_mode(
        self, degraded_registry: Any
    ) -> None:
        """End to end through the public API, not just the helper."""
        chain = degraded_registry.get_failover_chain("gemini-3.7-flash")

        assert chain[0] == "gemini-3.7-flash"
        assert len(chain) > 1

    def test_a_fully_qualified_name_is_normalised(
        self, degraded_registry: Any
    ) -> None:
        """The provider returns ``models/`` prefixes; callers may pass them through."""
        chain = degraded_registry.get_failover_chain("models/gemini-3.7-flash")

        assert chain[0] == "gemini-3.7-flash"
        assert len(chain) > 1


class TestDerivedChainQuality:
    """A6 — a chain of length > 1 is necessary but not sufficient."""

    def test_a_flash_model_falls_back_to_flash_peers(self) -> None:
        """Failover must stay in tier, not silently drop to a weaker model first."""
        chain = _build_fallback_chain("gemini-3.7-flash")

        assert _classify_tier(chain[1]) == "flash", (
            f"first fallback for a flash model should be flash, got {chain[1]}"
        )

    def test_a_pro_model_falls_back_to_pro_peers(self) -> None:
        chain = _build_fallback_chain("gemini-9-pro-preview")

        assert len(chain) > 1
        assert _classify_tier(chain[1]) == "pro"

    def test_a_chain_eventually_drops_a_tier(self) -> None:
        """A tier-wide outage must not leave the chain stranded inside it."""
        chain = _build_fallback_chain("gemini-3.7-flash")
        tiers = {_classify_tier(m) for m in chain}

        assert len(tiers) > 1, f"chain never leaves its tier: {chain}"

    def test_the_requested_model_is_never_duplicated(self) -> None:
        for model in NEWER_THAN_THE_TABLE + list(_FALLBACK_CHAINS):
            chain = _build_fallback_chain(model)
            assert chain.count(model) == 1, f"{model} repeated in {chain}"

    def test_chains_contain_no_duplicates_at_all(self) -> None:
        for model in NEWER_THAN_THE_TABLE + list(_FALLBACK_CHAINS):
            chain = _build_fallback_chain(model)
            assert len(chain) == len(set(chain)), f"duplicates in {chain}"

    def test_derivation_is_deterministic(self) -> None:
        """Routing must not vary run to run; set iteration order would do that."""
        for _ in range(5):
            assert _build_fallback_chain("gemini-3.7-flash") == _build_fallback_chain(
                "gemini-3.7-flash"
            )


class TestCuratedEntriesAreRespected:
    """A6 — deriving coverage must not discard the table's hand-tuned orderings."""

    @pytest.mark.parametrize("model", sorted(_FALLBACK_CHAINS))
    def test_an_exact_table_hit_is_returned_verbatim(self, model: str) -> None:
        assert _build_fallback_chain(model) == _FALLBACK_CHAINS[model]

    def test_the_returned_list_is_a_copy(self) -> None:
        """A caller mutating its chain must not corrupt the module table."""
        model = next(iter(_FALLBACK_CHAINS))
        original = list(_FALLBACK_CHAINS[model])

        chain = _build_fallback_chain(model)
        chain.append("mutated")

        assert _FALLBACK_CHAINS[model] == original


class TestTableStalenessGuards:
    """A6 — the table may lag, but it must stay internally coherent.

    A live "do these models still exist upstream?" check needs credentials and a
    network round trip, so it belongs to ``omni smoke`` rather than the unit
    suite. What *can* be checked offline is that the table has not rotted into an
    inconsistent state — which is what would silently degrade the derived chains
    that now depend on it.
    """

    def test_every_key_leads_its_own_chain(self) -> None:
        for model, chain in _FALLBACK_CHAINS.items():
            assert chain and chain[0] == model, (
                f"{model}'s chain should start with itself, got {chain}"
            )

    def test_no_chain_is_a_dead_end(self) -> None:
        for model, chain in _FALLBACK_CHAINS.items():
            assert len(chain) > 1, f"{model} has no fallback in the table"

    def test_every_tier_the_order_defines_has_at_least_one_exemplar(self) -> None:
        """The derivation pool must be able to serve the tiers it drops into.

        ``experimental`` and ``unknown`` are catch-alls rather than real tiers, so
        they are not required to be populated.
        """
        covered = {_classify_tier(m) for m in _known_fallback_models()}
        for tier in ("pro", "flash", "lite"):
            assert tier in covered, f"no cold-start exemplar for the {tier} tier"
            assert tier in _TIER_ORDER

    def test_known_models_are_deduplicated(self) -> None:
        known = _known_fallback_models()
        assert len(known) == len(set(known))

    def test_table_keys_appear_before_chain_only_members(self) -> None:
        """Preserves the table's preference ordering in the derivation pool."""
        known = _known_fallback_models()
        assert known[: len(_FALLBACK_CHAINS)] == list(_FALLBACK_CHAINS)


class TestDegradedModeDoesNotCrossSurfaces:
    """A6 — a text model must never fail over into TTS, image or video."""

    def test_no_derived_chain_contains_a_non_text_model(self) -> None:
        forbidden = ("tts", "image", "video", "veo-", "embedding", "transcribe")

        for model in NEWER_THAN_THE_TABLE:
            for candidate in _build_fallback_chain(model):
                assert not any(token in candidate for token in forbidden), (
                    f"{model}'s chain leaked a non-text model: {candidate}"
                )

    def test_text_generation_is_the_surface_under_test(self) -> None:
        """Guard on the assumption the table encodes, which is text-only."""
        assert ModelSurface.TEXT_GENERATION.value
