# ┌─────────────────────────────────────────────────────────────────────────────┐
# │  MACCREv2 Test Suite — Defect F1: the VCR transport button's box            │
# └─────────────────────────────────────────────────────────────────────────────┘
"""
tests/test_vcr_transport_render.py
==================================
Defect **F1** — pressing pause crashed the entire TUI.

Observed live on run ``job_20260901-205047-40sp``. The operator pressed the VCR
pause button; the handler restyled it from ``vcr-btn--running`` to
``vcr-btn--paused``; the render raised

    ValueError: range() arg 3 must not be zero

out of ``rich._wrap.divide_line`` -> ``rich.cells.chop_cells``, and the Textual app
died. The flow engine runs on its own thread, so it carried on without a UI —
which is how this turned into defect F2's runaway and F3's unreleasable pause.

The cause is box arithmetic, not logic. ``MacroNodeWorkshop.DEFAULT_CSS`` pinned
the button to ``min-width: 4; max-width: 4``, every ``.vcr-btn--*`` state rule in
``nexus_plex.css`` declares ``border: solid``, and Textual's ``Button`` carries
``padding: 0 1``::

    content_width = outer - border(2) - padding(2)
    outer 4  ->  content 0    <- crash
    outer 6  ->  content 2    <- fixed

**Why no existing gate could have caught this.**

* ``pyrightconfig.json`` excludes ``maccre_tui`` — but that is not the reason. A
  content width of zero is a perfectly well-typed ``int``. No type checker
  catches a *value* that a third-party library divides by. De-excluding
  ``maccre_tui`` is worth doing for other reasons and would not have found this.
* The suite's other TUI tests deliberately drive state models with the DOM
  stubbed out (see ``tests/test_topology_visualizer_multi_active.py``), because
  that is where the defects had been. Geometry is invisible to that approach.

So this file tests the arithmetic itself, against the **real** declared CSS. It
deliberately does not restate the widths: a test carrying its own copy of the
numbers would pass while the widget crashed, which is the whole failure mode being
guarded against.
"""
from __future__ import annotations

import re

import pytest
from rich._wrap import divide_line

from maccre_tui.widgets.macronode_workshop import MacroNodeWorkshop

#: A ``solid`` border occupies one cell on each side.
BORDER_CELLS = 2
#: Textual's ``Button`` default padding is ``0 1`` — one cell each side.
BUTTON_PADDING_CELLS = 2
#: Total horizontal chrome between the outer box and the text.
CHROME_CELLS = BORDER_CELLS + BUTTON_PADDING_CELLS

#: The two labels the VCR button actually carries.
VCR_LABELS = ("\u23f8", "\u25b6")  # pause, play


def _declared_widths(css: str, selector: str) -> dict[str, int]:
    """Pull the width declarations for *selector* out of a Textual CSS string.

    Reads the live ``DEFAULT_CSS`` rather than a copy, so narrowing the real rule
    fails these tests instead of passing beside them.
    """
    block = re.search(
        re.escape(selector) + r"\s*\{(.*?)\}", css, re.DOTALL
    )
    assert block is not None, f"selector {selector!r} is no longer in the CSS"

    found: dict[str, int] = {}
    for prop in ("min-width", "max-width", "width"):
        hit = re.search(rf"(?<!-){re.escape(prop)}\s*:\s*(\d+)", block.group(1))
        if hit:
            found[prop] = int(hit.group(1))
    return found


class TestTheLibraryBehaviourThatCrashed:
    """Pin *why* the width matters, so the fix is not mistaken for arbitrary.

    If a future rich release stops raising here, these tests say so plainly rather
    than the constraint quietly becoming folklore.
    """

    def test_a_zero_content_width_raises(self) -> None:
        """The exact exception from the live crash, reproduced in one call."""
        with pytest.raises(ValueError, match="range\\(\\) arg 3 must not be zero"):
            divide_line("\u25b6", 0)

    @pytest.mark.parametrize("width", [1, 2, 4])
    def test_any_positive_content_width_is_safe(self, width: int) -> None:
        for label in VCR_LABELS:
            divide_line(label, width)  # must not raise

    def test_both_vcr_labels_fit_in_one_cell(self) -> None:
        """Neither glyph is the problem; the box was.

        Worth pinning because "the play triangle is too wide" is the intuitive
        wrong hypothesis, and acting on it would have changed the label and left
        the crash in place.
        """
        from rich.cells import cell_len

        for label in VCR_LABELS:
            assert cell_len(label) <= 2, f"{label!r} is unexpectedly wide"


class TestWorkshopVcrButtonHasRoomToRender:
    """F1 — the regression guard. Narrowing the button re-fails this."""

    SELECTOR = "MacroNodeWorkshop .vcr-btn"

    def _widths(self) -> dict[str, int]:
        return _declared_widths(MacroNodeWorkshop.DEFAULT_CSS, self.SELECTOR)

    def test_the_rule_still_exists(self) -> None:
        """If the override is deleted the button inherits ``.vcr-btn``'s wider
        ``min-width: 8`` and is safe — but this test should be updated
        deliberately rather than silently passing on an absent rule."""
        assert self._widths(), f"{self.SELECTOR} declares no width"

    def test_min_width_leaves_a_positive_content_box(self) -> None:
        widths = self._widths()
        min_width = widths.get("min-width")
        assert min_width is not None
        content = min_width - CHROME_CELLS
        assert content >= 1, (
            f"min-width {min_width} leaves {content} cells for the label after "
            f"{CHROME_CELLS} cells of border and padding. At zero, rendering the "
            f"button raises ValueError and takes the whole TUI with it."
        )

    def test_max_width_leaves_a_positive_content_box(self) -> None:
        """``max-width`` is the one that actually bit.

        ``min-width`` alone would have been harmless — Textual would have grown
        the button to fit. The hard ``max-width: 4`` cap is what forced the box
        below its own chrome.
        """
        widths = self._widths()
        max_width = widths.get("max-width")
        if max_width is None:
            pytest.skip("no max-width cap declared, so the box cannot be squeezed")
        content = max_width - CHROME_CELLS
        assert content >= 1, (
            f"max-width {max_width} caps the content box at {content} cells"
        )

    def test_the_declared_box_renders_every_label(self) -> None:
        """Close the loop: feed the real declared width to the real library call.

        This is the assertion that fails on the pre-fix CSS, and it fails with the
        production exception rather than a proxy for it.
        """
        widths = self._widths()
        outer = min(
            v for k, v in widths.items() if k in ("min-width", "max-width", "width")
        )
        content = outer - CHROME_CELLS
        for label in VCR_LABELS:
            divide_line(label, content)  # must not raise

    def test_the_arithmetic_is_stated_where_the_number_is(self) -> None:
        """The rule must carry its reasoning, or it gets 'tidied' back to 4.

        This project's register records the same lesson twice already: a bare
        number with no rationale beside it is an invitation to change it.
        """
        css = MacroNodeWorkshop.DEFAULT_CSS
        idx = css.find(self.SELECTOR)
        assert idx != -1
        preamble = css[max(0, idx - 1400):idx]
        assert "F1" in preamble, (
            "the vcr-btn width rule no longer cites the defect it exists to prevent"
        )
