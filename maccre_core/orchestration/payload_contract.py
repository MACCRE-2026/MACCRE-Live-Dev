# ┌─────────────────────────────────────────────────────────────────────────────┐
# │  MACCREv2 ENGINEERING DOCTRINE                             Law Rev: 19.0   │
# ├─────────────────────────────────────────────────────────────────────────────┤
# │  I.   TYPING      All signatures: explicit Python 3.11+ type hints.        │
# │  II.  LINTING     Zero unused imports. No wildcards. 120-char line max.    │
# └─────────────────────────────────────────────────────────────────────────────┘
"""
maccre_core/orchestration/payload_contract.py
=============================================
**What a step hands the next step.** Requirement 34 — the "3b with a ceiling" contract.

THE DECISION THIS IMPLEMENTS
----------------------------
The operator chose, from three options, a **3b/3c hybrid**: the unified session ledger *is*
the payload, with the immediate upstream output identified **inside** it rather than passed
as a second copy — until the context grows too large, at which point the excess is truncated
and, eventually, semantically distilled back in. *"Basically 3b, until it gets too big and it
turns 3c."*

Option 3a (the ledger accompanying the terminal output as a separate section) was rejected
for a measured reason: **the ledger already contains the upstream output.** It is assembled
from every agent ledger in the job, so sending both would carry the same prose twice at
every hop, and across a multi-step flow that is not linear growth.

WHAT IS BUILT HERE, AND WHAT IS DELIBERATELY NOT
------------------------------------------------
Requirement 34 has seven criteria. **34.2 through 34.7 are implemented in this module.
34.1 is not, and that is the point.**

34.1 requires ``swarm_worker`` to *delegate* to this module — a change to what a live flow
actually sends. That change is irreversible in one specific way:

    ``payload_bytes`` and per-node ``INFERENCE_COST`` attribution both landed on
    2026-09-05 (tracker #18), and **no live flow has run since.** So the *before* number
    for this contract does not exist, and cannot be obtained once the contract changes.

So this module is complete, tested, and **not wired**, exactly as Requirement 33's
validators were. The still-red ``strict=True`` marker for 34.1 in
``tests/test_topological_semantic_spec.py`` *is* the record that wiring remains outstanding
— enforced mechanically rather than asserted in a comment somebody has to trust. It falls
when a baseline run has been taken and the wiring is done on purpose.

**Nothing in this module is called by any execution path today.** "Requirement 34 is
implemented" and "MACCRE composes payloads this way" are different claims, and only the
first is true.
"""
from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

__all__ = [
    "ACCOMPANYING_CONTEXT_CHAR_CEILING",
    "SECTION_SESSION_CONTEXT",
    "SECTION_SOURCE_DOCUMENT",
    "TRUNCATION_NOTICE",
    "compose_step_payload",
    "describe_step_payload",
    "distil_truncated_context",
]

#: Label for the original user input, unchanged through every hop.
#:
#: Matches the wording ``swarm_worker`` already uses, deliberately. Agents have been
#: reading ``[SOURCE DOCUMENT — original user input]`` for the life of the project, and a
#: new spelling for the same section would be a gratuitous change to every prompt.
SECTION_SOURCE_DOCUMENT = "[SOURCE DOCUMENT — original user input]"

#: Label for the accompanying session context.
SECTION_SESSION_CONTEXT = "[SESSION CONTEXT — all prior agent turns in this flow]"

#: Character ceiling for the accompanying context. Req 34.3.
#:
#: **Characters, not tokens, and the distinction is honest rather than lazy.** There is no
#: tokenizer in this repository; the only exact token count available is a network call
#: (``countTokens``) that is not on the execution path. A ceiling expressed in tokens would
#: therefore be a character count divided by a heuristic and *called* a token count, which
#: is a worse claim than the plain measurement.
#:
#: 120,000 characters is chosen to match a threshold the codebase already uses: the router's
#: context-cache heuristic treats 120,000 characters as its "large context" trigger. Reusing
#: that number rather than inventing a second one means there is **one** notion of "this
#: context is big" in the system. At roughly 4 chars/token it lands near 30k tokens, well
#: inside every model in the pricing matrix, and far below the 200,000-token long-context
#: billing tier where the input *rate* changes.
ACCOMPANYING_CONTEXT_CHAR_CEILING: int = 120_000

#: The notice inserted when context is cut. Req 34.4 and Req 34.6.
#:
#: It says **"not distilled"** explicitly. A payload that had been merely cut while implying
#: it had been summarised would be Principle 3 inside the one document the next agent
#: reasons from — the worst available place for a success claim over work that did not
#: happen. The phrase is a constant so the honesty cannot be softened at one call site.
TRUNCATION_NOTICE = (
    "[CONTEXT TRUNCATED — {removed:,} of {original:,} characters were removed to stay "
    "within the {ceiling:,}-character ceiling. The most recent turns were kept and the "
    "oldest were dropped. The removed content was NOT distilled or summarised; it is "
    "simply absent.]"
)


def distil_truncated_context(removed: str) -> str | None:
    """The seam where Era 4's semantic distillation will live. Req 34.6.

    Returns ``None``, always, and that is the implementation rather than a stub awaiting
    one line. Distillation is an **inference call per step boundary**: its cost cannot be
    measured today, and its value cannot be quantified until the payload manager daemon
    exists to say what a smaller payload bought. Building the expensive half before it can
    be measured is how the FinOps engine came to hold a hand-rolled cost calculator beside
    a response object that already carried the real numbers.

    Args:
        removed: The text that truncation dropped.

    Returns:
        ``None`` — no distillation is performed.

    Note:
        **This deliberately does not fall back to returning the input.** A seam that quietly
        handed back the removed text would make "distilled" true by redefinition, and every
        message describing the payload would become false at the same moment. The
        ``None`` is load-bearing, and a test asserts it.
    """
    if removed:
        logger.debug(
            "[PAYLOAD_CONTRACT] %d characters truncated and not distilled; the Era 4 "
            "distillation seam is deliberately unimplemented.",
            len(removed),
        )
    return None


def _bound_context(context: str) -> tuple[str, int]:
    """Trim *context* to the ceiling, keeping the newest content. Req 34.5.

    Returns:
        ``(bounded_text, characters_removed)``.

    Note:
        **The newest end is kept**, and the payload says so. Truncation that does not state
        which end it dropped leaves a reader unable to tell an early-flow gap from a
        late-flow one — and the session ledger is assembled oldest-first, so the most
        recent turns are the ones a successor most needs.

        The cut is made at a **line boundary** where one is available within the retained
        window, so the payload does not open mid-sentence. Falling back to a hard character
        cut is correct when a single line exceeds the whole ceiling: an unsplittable blob is
        not a reason to emit nothing.
    """
    if len(context) <= ACCOMPANYING_CONTEXT_CHAR_CEILING:
        return context, 0

    removed_count = len(context) - ACCOMPANYING_CONTEXT_CHAR_CEILING
    tail = context[-ACCOMPANYING_CONTEXT_CHAR_CEILING:]

    newline = tail.find("\n")
    if 0 <= newline < len(tail) - 1:
        # Drop the partial first line so the section starts cleanly.
        trimmed = tail[newline + 1:]
        return trimmed, len(context) - len(trimmed)
    return tail, removed_count


def compose_step_payload(
    session_context: str,
    upstream_node: str,
    source_document: str = "",
) -> str:
    """Build the payload a step hands the next step. Req 34.1–34.5.

    Args:
        session_context: The assembled session ledger — every prior agent turn.
        upstream_node: The node whose output the successor is downstream of. Named in the
            header so lineage is an assertion in the document rather than a separate copy
            of the same prose.
        source_document: The original user input. Omitted when it is the same file as the
            context, which is the first node's case.

    Returns:
        One payload string with labelled sections.

    Note:
        **The upstream output is identified, not duplicated** (Req 34.2). The session
        ledger already contains it — the ledger is assembled from every agent ledger in the
        job — so appending it again would send the same prose twice at every hop.
    """
    parts: list[str] = []

    if source_document:
        parts.append(f"{SECTION_SOURCE_DOCUMENT}\n{source_document}")

    bounded, removed = _bound_context(session_context)

    if removed:
        # Offered to the seam, which declines. The call is real rather than decorative:
        # when Era 4 implements it, this is the line that starts returning content, and
        # the notice below is what has to change with it.
        distilled = distil_truncated_context(session_context[:removed])
        if distilled is not None:  # pragma: no cover — Era 4
            bounded = f"{distilled}\n\n{bounded}"
        else:
            parts.append(TRUNCATION_NOTICE.format(
                removed=removed,
                original=len(session_context),
                ceiling=ACCOMPANYING_CONTEXT_CHAR_CEILING,
            ))

    header = (
        f"{SECTION_SESSION_CONTEXT}\n"
        f"The section written by `{upstream_node}` is your immediate upstream output.\n"
    )
    parts.append(f"{header}{bounded}")

    return "\n\n".join(parts)


def describe_step_payload(
    session_context: str,
    upstream_node: str,
    source_document: str = "",
) -> dict[str, Any]:
    """Measure what :func:`compose_step_payload` would produce. Req 34.7.

    Exists so a before-and-after comparison is possible at all, and so a caller can record
    the size without holding the payload. Pairs with ``task_queue.payload_bytes``.

    Returns:
        A dict whose ``distilled`` key is currently always ``False`` — reported rather than
        omitted, because "we did not distil" is the fact that has to survive into any cost
        analysis of this change.
    """
    composed = compose_step_payload(session_context, upstream_node, source_document)
    _, removed = _bound_context(session_context)
    return {
        "composed_chars": len(composed),
        "context_chars": len(session_context),
        "context_chars_kept": len(session_context) - removed,
        "context_chars_removed": removed,
        "truncated": removed > 0,
        "distilled": False,
        "ceiling": ACCOMPANYING_CONTEXT_CHAR_CEILING,
    }
