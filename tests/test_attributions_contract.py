# ┌─────────────────────────────────────────────────────────────────────────────┐
# │  MACCREv2 Test Infrastructure — attributions contract                       │
# └─────────────────────────────────────────────────────────────────────────────┘
"""
tests/test_attributions_contract.py
===================================
Keeps ``ATTRIBUTIONS.md`` honest, and keeps the shared doctrine from drifting back to
presenting a borrowed rule as native.

WHY THIS FILE EXISTS
--------------------
Three novelty claims were withdrawn on 2026-09-03 and 2026-09-04, each falsified by
this project's own search rather than by a reviewer:

* the restrictive trust default — falsified by IETF ``draft-bondar-wca-00`` §A.6, a
  formally verified property, and by *semantic laundering* (January 2026);
* the register format — falsified by Architecture Decision Records (Nygard, 2011);
* terminal states requiring evidence — falsified by assurance cases (GSN, OMG SACM),
  which are **stricter** than MACCRE's version.

Two of those three had been named by an independent analysis as MACCRE's strongest
differentiators.

The Entry Doctrine's Third Amendment responds by requiring a prior-art line on any entry
asserting a general principle, and by putting the convergences in ``ATTRIBUTIONS.md``.
**A doctrine requirement with no test is exactly the thing Doctrine 5 is about** — the
project has already been bitten by a config claiming coverage it did not provide, and by
a module docstring advertising a security control that returned ``True``. So the
attribution obligation gets a test, on the same standard.

WHAT IS AND IS NOT CHECKED
--------------------------
Checkable: that the log exists, that every convergence carries its incident and its
established name, that no entry accidentally claims novelty, and that the shared doctrine
names Biba.

Not checkable: whether the *content* of an attribution is correct, or whether an
unrecorded convergence exists. No test can find prior art. That is what the post-hoc
habit is for, and its failure mode is silent by nature.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
ATTRIBUTIONS = REPO_ROOT / "ATTRIBUTIONS.md"
REGISTER = REPO_ROOT / "FeatureRequests.md"

#: The shared standing doctrine. Outside the repository by design — it applies to both
#: MACCRE Systems workspaces — so its absence is an environment fact, not a defect.
SHARED_DOCTRINE = Path.home() / ".kiro" / "steering" / "maccre-systems-doctrine.md"

#: Every convergence must name its ancestor. Keyed by a phrase that must appear in the
#: log, valued by the established name that must appear near it.
REQUIRED_ATTRIBUTIONS = {
    "minimum trust of its inputs": "Biba",
    "launders its source's trust": "semantic laundering",
    "union of its inputs": "PROV",
    "non-deterministic execution": "durable execution",
    "durable substrate": "Obelisk",
    "Human-in-the-loop pause": "LangGraph",
    "append-only register": "Architecture Decision Records",
    "requires evidence, not assertion": "assurance cases",
    "hardware token": "FIDO2",
}

#: Phrasings that would re-introduce a novelty claim. Checked case-insensitively.
FORBIDDEN_CLAIMS = (
    "we invented",
    "novel contribution",
    "first to identify",
    "unique to maccre",
    "unprecedented",
)


@pytest.fixture(scope="module")
def attributions_text() -> str:
    if not ATTRIBUTIONS.is_file():
        pytest.fail(
            "ATTRIBUTIONS.md is missing. The Entry Doctrine's Third Amendment requires "
            "it, and three withdrawn claims are the reason."
        )
    return ATTRIBUTIONS.read_text(encoding="utf-8")


class TestTheLogIsStructurallyComplete:
    @pytest.mark.parametrize(("phrase", "ancestor"), sorted(REQUIRED_ATTRIBUTIONS.items()))
    def test_each_convergence_names_its_ancestor(
        self, phrase: str, ancestor: str, attributions_text: str
    ) -> None:
        assert phrase in attributions_text, (
            f"ATTRIBUTIONS.md no longer covers '{phrase}'. Convergences are append-only "
            f"for the same reason register entries are — a removed attribution is an "
            f"invitation to re-claim the idea."
        )
        assert ancestor in attributions_text, (
            f"'{phrase}' is present but its established name '{ancestor}' is not. An "
            f"attribution that does not name the source is not an attribution."
        )

    def test_every_convergence_records_its_originating_incident(
        self, attributions_text: str
    ) -> None:
        """The incident is the load-bearing half.

        Without it the log is a bibliography. With it, it is evidence about how the
        reasoning happened — which is the only claim this project makes.
        """
        headings = re.findall(r"^### \d+\. ", attributions_text, re.M)
        incidents = re.findall(r"\*\*The incident here:\*\*", attributions_text)
        assert len(headings) >= 9, f"expected at least 9 convergences, found {len(headings)}"
        assert len(incidents) == len(headings), (
            f"{len(headings)} convergences but {len(incidents)} incident lines. Every "
            f"convergence needs the specific failure that produced it here."
        )

    def test_every_convergence_disclaims_novelty(self, attributions_text: str) -> None:
        headings = re.findall(r"^### \d+\. ", attributions_text, re.M)
        claims = re.findall(r"\*\*Claim:\*\*", attributions_text)
        assert len(claims) == len(headings), (
            f"{len(headings)} convergences but {len(claims)} explicit Claim lines. The "
            f"non-claim is not implied by context; it is stated."
        )

    def test_searched_not_found_is_phrased_as_a_statement_about_the_search(
        self, attributions_text: str
    ) -> None:
        """The exact error that cost three claims.

        An analysis searched nine standards bodies, found nothing, and concluded the idea
        was unclaimed. The statement about where it looked was true; the conclusion was
        not. The phrasing has to carry that distinction or the lesson is lost.
        """
        assert "Searched, not found" in attributions_text or "searched, not found" in attributions_text
        assert "statement about the search" in attributions_text.lower(), (
            "the log must say that 'searched, not found' is a statement about the search "
            "rather than about the world — that distinction is the whole lesson"
        )

    @pytest.mark.parametrize("forbidden", FORBIDDEN_CLAIMS)
    def test_no_novelty_language_creeps_back(
        self, forbidden: str, attributions_text: str
    ) -> None:
        lowered = attributions_text.lower()
        # "novel contribution" appears legitimately when *disclaiming* it.
        occurrences = [
            m.start() for m in re.finditer(re.escape(forbidden), lowered)
        ]
        for pos in occurrences:
            window = lowered[max(0, pos - 120):pos + 120]
            negated = any(
                marker in window
                for marker in ("no ", "not ", "none", "claims no", "does not", "without")
            )
            assert negated, (
                f"'{forbidden}' appears in ATTRIBUTIONS.md without a nearby negation, "
                f"around: ...{attributions_text[max(0, pos - 100):pos + 100]}..."
            )


class TestTheDoctrineNamesItsAncestor:
    """Doctrine 1 presented a borrowed rule as native until 2026-09-04."""

    def test_doctrine_one_names_biba(self) -> None:
        if not SHARED_DOCTRINE.is_file():
            pytest.skip(
                "shared standing doctrine not present at its user-profile path on this "
                "machine; it applies to both MACCRE Systems workspaces and lives outside "
                "the repository by design"
            )
        text = SHARED_DOCTRINE.read_text(encoding="utf-8")
        assert "Biba" in text, (
            "Doctrine 1 no longer names the Biba integrity model. It presented the trust "
            "ceiling as native until 2026-09-04, which is precisely the claim that was "
            "falsified by a formally verified IETF property."
        )
        assert "PROV" in text, (
            "Doctrine 1's union-of-inputs corollary no longer points at W3C PROV. A "
            "private encoding of a 2013 Recommendation costs interoperability for nothing."
        )
        assert "ATTRIBUTIONS.md" in text, (
            "the doctrine must point at the attributions log, or the obligation has no "
            "home and decays into a habit nobody performs"
        )


class TestTheThirdAmendmentExists:
    """The register's own governing text has to carry the requirement."""

    def test_the_amendment_is_recorded(self) -> None:
        text = REGISTER.read_text(encoding="utf-8")
        assert "THIRD AMENDMENT" in text, (
            "the Entry Doctrine's Third Amendment is missing from the register"
        )
        assert "**Prior art:**" in text, (
            "no entry carries a Prior art field, so the amendment is unenforced prose"
        )

    def test_the_amendment_permits_a_negative_result(self) -> None:
        text = REGISTER.read_text(encoding="utf-8")
        assert "searched, none found" in text.lower(), (
            "the amendment must state that a negative search result is a legitimate "
            "answer, or entries will omit the field rather than record a null"
        )
