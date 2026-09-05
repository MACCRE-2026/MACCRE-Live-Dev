# ┌─────────────────────────────────────────────────────────────────────────────┐
# │  MACCREv2 Test Infrastructure — the ledger's memory-pins section              │
# └─────────────────────────────────────────────────────────────────────────────┘
"""
tests/test_ledger_memory_pins.py
================================
Phase 6.13 tracker #19, **and a correction to the claim that raised it.**

THE DEFECT
----------
``_generate_unified_ledger_unlocked`` collected memory pins by globbing
``02_Dynamic_Context/memory_pins/pin_*_{job_id}*.json``. **No code anywhere writes that
filename.** The only pin-JSON writer emits ``global_pin_{doc_id}.json``
(``rag_tools.py:396``), which cannot match a glob anchored on ``pin_*``. The collector had
therefore never returned a row, and the real per-session pins — written by
``CognitiveMemoryEngine.extract_from_canonized_ledger`` into the ``memory_pins`` table —
were never read.

THE CORRECTION, RECORDED BECAUSE IT WAS RECORDED WRONG FIRST
------------------------------------------------------------
The finding was first written up as *"the section is a heading with a table header and no
rows, always"*, and on that basis it was called a dependency of the step-boundary payload
contract — a decorative heading inside a document about to be handed forward as a payload.

**That was false.** The emit site is guarded by ``if memory_pins:``, so an empty collection
renders **nothing at all**. The consequence was a *missing* section, not a broken one, and
there was never a decorative heading in any payload. The defect is dead code reading a
pattern nothing writes, which is a real Principle 5 problem and a smaller one.
``TestTheSectionIsAbsentRatherThanDecorative`` is the test that would have caught the
overstatement.

WHY THE SECTION IS STILL EMPTY DURING A RUN, AND WHY THAT IS CORRECT
--------------------------------------------------------------------
Pins are extracted at **canonization**, which happens after a flow finishes. This function
runs on every node completion *during* the flow. So at every point it executes there
genuinely are no pins for that job, and an empty section is the truthful output. Fixing the
source does not make the section appear mid-run — it makes it appear when a ledger is
regenerated after canonization, which is the only moment the claim would be true.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import pytest

from maccre_core.orchestration.memory_engine import SovereignPinStore

JOB = "job_ledger_pins"


def _source_of(rel: str) -> str:
    return (Path(__file__).resolve().parent.parent / rel).read_text(encoding="utf-8")


def _ledger_source() -> str:
    """Just the assembly body, so assertions cannot match unrelated code."""
    source = _source_of("maccre_core/orchestration/flow_engine.py")
    start = source.index("def _generate_unified_ledger_unlocked")
    return source[start : source.index("def thoughts_ledger_path")]


@pytest.fixture()
def pin_store(tmp_path: Path) -> SovereignPinStore:
    return SovereignPinStore(str(tmp_path / "memory_pins.db"))


class TestTheDeadGlobIsGone:
    def test_the_ledger_no_longer_globs_for_pin_json(self) -> None:
        """The pattern nothing writes."""
        assert 'glob(f"pin_*_{job_id}*.json")' not in _ledger_source()

    def test_no_writer_ever_produced_that_filename(self) -> None:
        """The premise of the removal, asserted so it cannot silently stop being true.

        If some future code starts writing ``pin_<x>_<job>.json``, this fails and the
        removal deserves re-examination rather than assumption.

        Written first as ``'f"pin_{' not in source``, which was too broad and failed on
        ``doc_id=f"pin_{doc_id}"`` in ``collection_ingest`` — a **vector-store record
        id**, not a filename. Narrowed to JSON *filename* literals, because that is the
        only thing the dead glob could ever have matched. Recorded because the broad
        version would have blocked an unrelated identifier from ever using the prefix.
        """
        json_pin_filename = re.compile(r'f"pin_[^"]*\.json"')
        for rel in (
            "maccre_core/tools/rag_tools.py",
            "maccre_core/tools/collection_ingest.py",
            "maccre_core/tools/antigravity_ingest.py",
        ):
            source = _source_of(rel)
            assert not json_pin_filename.search(source), rel

    def test_the_actual_pin_json_writer_uses_a_different_prefix(self) -> None:
        """Positive half: name what *is* written, so the mismatch is legible."""
        assert 'global_pin_{doc_id}.json' in _source_of("maccre_core/tools/rag_tools.py")

    def test_the_ledger_reads_the_pin_table_instead(self) -> None:
        body = _ledger_source()
        assert "memory_pins.db" in body
        assert "get_pins_by_job(job_id)" in body

    def test_the_database_is_existence_checked_before_opening(self) -> None:
        """The store's constructor runs CREATE TABLE IF NOT EXISTS.

        Generating a ledger must not bring a database into being as a side effect, and
        this function runs on *every node completion*.
        """
        body = _ledger_source()
        assert "_pins_db.exists()" in body

    def test_a_pins_failure_cannot_break_ledger_assembly(self) -> None:
        """The ledger is the next node's input payload.

        Losing it to a failed optional lookup would be far worse than losing the pins,
        so the read is wrapped and degrades to an empty section.
        """
        body = _ledger_source()
        start = body.index("_pins_db.exists()")
        assert "except Exception" in body[start : start + 1200]


class TestTheSectionIsAbsentRatherThanDecorative:
    """The correction. This is the test the overstated claim needed."""

    def test_the_heading_is_guarded_by_having_pins(self) -> None:
        """An empty collection renders nothing — no heading, no table header.

        The original write-up claimed a heading over an empty table and called that a
        blocker for the payload contract. The guard is why that was wrong.
        """
        body = _ledger_source()
        guard = body.index("if memory_pins:")
        heading = body.index("## Extracted Knowledge Triplets")
        assert guard < heading

    def test_the_heading_appears_only_inside_the_guard(self) -> None:
        """One emit site, and it is the guarded one."""
        assert _ledger_source().count("## Extracted Knowledge Triplets") == 1


class TestThePinTableRoundTrip:
    """The reader the ledger now uses, exercised directly."""

    def test_pins_are_readable_by_job(self, pin_store: SovereignPinStore) -> None:
        pin_store.store_triplets(
            JOB,
            "/dc/04_Code_Artifacts/job/unified_session_ledger.md",
            [
                {
                    "subject": "StepOutputSet",
                    "predicate": "refuses to choose between",
                    "object": "multiple terminal outputs",
                    "significance": "one of eight is a fraction wearing the whole name",
                }
            ],
        )
        pins = pin_store.get_pins_by_job(JOB)
        assert len(pins) == 1
        assert pins[0]["subject"] == "StepOutputSet"

    def test_the_rows_carry_the_fields_the_ledger_renders(
        self, pin_store: SovereignPinStore
    ) -> None:
        """The ledger table renders subject/predicate/object/significance."""
        pin_store.store_triplets(
            JOB, "/dc/l.md",
            [{"subject": "a", "predicate": "b", "object": "c", "significance": "d"}],
        )
        row: dict[str, Any] = pin_store.get_pins_by_job(JOB)[0]
        for field in ("subject", "predicate", "object", "significance"):
            assert field in row

    def test_another_job_is_not_returned(self, pin_store: SovereignPinStore) -> None:
        pin_store.store_triplets(
            JOB, "/dc/l.md",
            [{"subject": "mine", "predicate": "p", "object": "o", "significance": "s"}],
        )
        pin_store.store_triplets(
            "other", "/dc/o.md",
            [{"subject": "theirs", "predicate": "p", "object": "o", "significance": "s"}],
        )
        assert [p["subject"] for p in pin_store.get_pins_by_job(JOB)] == ["mine"]

    def test_a_job_with_no_pins_reads_empty(self, pin_store: SovereignPinStore) -> None:
        """Which is what every mid-run job looks like, correctly.

        Pins are extracted at canonization — after the flow finishes — so during a run
        there are genuinely none, and the section's absence is the truthful output
        rather than a symptom.
        """
        assert pin_store.get_pins_by_job("never_canonized") == []
