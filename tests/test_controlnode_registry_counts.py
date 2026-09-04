# ┌─────────────────────────────────────────────────────────────────────────────┐
# │  MACCREv2 Test Infrastructure — control node registry self-consistency      │
# └─────────────────────────────────────────────────────────────────────────────┘
"""
tests/test_controlnode_registry_counts.py
=========================================
Stops the control node registry from lying about its own contents.

WHY THIS FILE EXISTS
--------------------
``maccre_core/controlnode_registry.py`` exists to be the single source of truth for
node types — the answer to *how many control nodes are there*. Until 2026-09-04 it
carried three hand-maintained numbers describing one list, and two of them were wrong:

* a section header reading ``Active (16)`` while the list held **17** ``active`` rows;
* ``_seed_builtins``' docstring claiming **23** builtin nodes while the list held **25**.

The measured cause was more specific than the original report. There are *two* active
blocks (8 core primitives plus 8 Wave 3 data-flow nodes, totalling 16), and the
seventeenth active row — ``CTRL_CONDITIONAL_ROUTE`` — sat **below the "Coming Soon"
divider** while carrying ``"status": "active"``. So the header and the row's own status
disagreed, and every reading of ``Active (16)`` undercounted by one.

That is Doctrine 4 — two representations of one thing will drift — in the file whose
whole purpose is to end hand-maintained node tables. And Doctrine 5: three claims about
behaviour with no test to fail when they went false.

THE FIX THIS FILE GUARDS
------------------------
Rather than re-synchronising three numbers, the numbers were **removed**. Section
headers are now descriptive, the seeder's docstring states no count, and
``ACTIVE_NODE_COUNT`` / ``COMING_SOON_NODE_COUNT`` / ``BUILTIN_NODE_COUNT`` are derived
from the list itself. Drift is structurally impossible rather than merely corrected.

These tests therefore assert two different kinds of thing:

1. that the derived counts are internally consistent — cheap, and catches a bad edit;
2. that **no literal count has reappeared** in the section headers or the seeder
   docstring, and that no row's status disagrees with the section it sits in. This is
   the one that matters, because it is the defect returning, not a symptom of it.
"""
from __future__ import annotations

import re
from collections import Counter
from pathlib import Path

import pytest

from maccre_core.controlnode_registry import (
    ACTIVE_NODE_COUNT,
    BUILTIN_NODE_COUNT,
    COMING_SOON_NODE_COUNT,
    _BUILTIN_NODES,
)

SRC = Path(__file__).resolve().parent.parent / "maccre_core" / "controlnode_registry.py"

#: Statuses a builtin row is permitted to carry.
VALID_STATUSES = {"active", "ComingSoon"}


@pytest.fixture(scope="module")
def source_text() -> str:
    return SRC.read_text(encoding="utf-8")


def _section_blocks(text: str) -> list[tuple[str, list[str]]]:
    """Split the builtin list into ``(header, [statuses])`` by divider comment.

    Parses the source rather than the imported object on purpose: the thing under
    test is whether the *comments* agree with the data, and the imported list has no
    comments in it.
    """
    lines = text.splitlines()
    start = next(i for i, ln in enumerate(lines) if ln.startswith("_BUILTIN_NODES"))
    end = next(i for i, ln in enumerate(lines[start:], start) if ln == "]")
    body = lines[start:end]

    headers: list[tuple[int, str]] = [
        (i, m.group(1).strip())
        for i, ln in enumerate(body)
        if (m := re.search(r"#\s*──\s*(.+?)\s*─{2,}", ln))
    ]
    blocks: list[tuple[str, list[str]]] = []
    for pos, (i, label) in enumerate(headers):
        stop = headers[pos + 1][0] if pos + 1 < len(headers) else len(body)
        chunk = "\n".join(body[i:stop])
        blocks.append((label, re.findall(r'"status":\s*"(\w+)"', chunk)))
    return blocks


class TestDerivedCountsAreConsistent:
    def test_the_totals_add_up(self) -> None:
        assert ACTIVE_NODE_COUNT + COMING_SOON_NODE_COUNT == BUILTIN_NODE_COUNT
        assert BUILTIN_NODE_COUNT == len(_BUILTIN_NODES)

    def test_counts_match_a_fresh_tally(self) -> None:
        tally = Counter(n["status"] for n in _BUILTIN_NODES)
        assert ACTIVE_NODE_COUNT == tally["active"]
        assert COMING_SOON_NODE_COUNT == tally["ComingSoon"]

    def test_every_row_carries_a_recognised_status(self) -> None:
        unknown = {
            n.get("name", "<unnamed>"): n.get("status")
            for n in _BUILTIN_NODES
            if n.get("status") not in VALID_STATUSES
        }
        assert not unknown, f"rows with an unrecognised status: {unknown}"

    def test_names_are_unique(self) -> None:
        """A duplicated name would make the registry ambiguous about a node type."""
        names = [n["name"] for n in _BUILTIN_NODES]
        dupes = [name for name, count in Counter(names).items() if count > 1]
        assert not dupes, f"duplicate control node names: {dupes}"

    def test_every_active_node_declares_a_handler(self) -> None:
        """An `active` node with no handler is Doctrine 3 waiting to happen.

        A node the registry advertises as dispatchable, that resolves to nothing, is
        how a recursion limiter once inserted a node named `FAILED` which was then
        claimed and ran real inference.
        """
        missing = [
            n["name"]
            for n in _BUILTIN_NODES
            if n["status"] == "active" and not (n.get("handler_module") and n.get("handler_func"))
        ]
        assert not missing, f"active nodes with no handler declared: {missing}"


class TestNoHandMaintainedCountReturns:
    """The defect itself, rather than its symptoms."""

    def test_section_headers_carry_no_literal_count(self, source_text: str) -> None:
        offenders = [
            label for label, _ in _section_blocks(source_text) if re.search(r"\(\s*\d+\s*\)", label)
        ]
        assert not offenders, (
            f"section header(s) carry a hand-maintained count: {offenders}. That number "
            f"will drift from the list beneath it — it already did, as 'Active (16)' "
            f"above 17 active rows. Use ACTIVE_NODE_COUNT / COMING_SOON_NODE_COUNT, "
            f"which are derived."
        )

    def test_the_seeder_docstring_carries_no_literal_count(self, source_text: str) -> None:
        match = re.search(
            r"def _seed_builtins.*?\"\"\"(.*?)\"\"\"", source_text, re.S
        )
        assert match, "could not locate _seed_builtins' docstring; the parser is stale"
        docstring = match.group(1)
        # Allow digits that are part of a historical note about the defect itself.
        claim = re.search(r"all (\d+) builtin", docstring)
        assert claim is None, (
            f"_seed_builtins' docstring claims a count again ({claim.group(1) if claim else '?'}). "
            f"It said 23 while the list held 25. The log line reports "
            f"len(_BUILTIN_NODES), which cannot drift."
        )

    def test_no_row_sits_under_a_section_that_contradicts_its_status(
        self, source_text: str
    ) -> None:
        """The specific misfiling that made every count wrong.

        ``CTRL_CONDITIONAL_ROUTE`` carried ``"status": "active"`` while sitting below
        the "Coming Soon" divider. Whichever number a reader trusted, one of them was
        wrong.
        """
        for label, statuses in _section_blocks(source_text):
            lowered = label.lower()
            if "coming soon" in lowered:
                stray = [s for s in statuses if s != "ComingSoon"]
                assert not stray, (
                    f"section {label!r} contains {stray} — a row whose status "
                    f"contradicts the section it is filed under"
                )
            elif "active" in lowered:
                stray = [s for s in statuses if s != "active"]
                assert not stray, (
                    f"section {label!r} contains {stray} — a row whose status "
                    f"contradicts the section it is filed under"
                )

    def test_every_row_falls_inside_a_labelled_section(self, source_text: str) -> None:
        """Guards the parser as much as the data.

        If rows drift above the first divider they would escape the section checks
        silently, which would make this whole file decorative.
        """
        counted = sum(len(statuses) for _, statuses in _section_blocks(source_text))
        assert counted == len(_BUILTIN_NODES), (
            f"section blocks account for {counted} rows but the list holds "
            f"{len(_BUILTIN_NODES)}. Either a row sits above the first divider, or "
            f"the divider format changed and this test's parser is stale — both need "
            f"eyes, because an unparsed row is an unchecked row."
        )
