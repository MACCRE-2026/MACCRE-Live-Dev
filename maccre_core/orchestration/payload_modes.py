# ┌─────────────────────────────────────────────────────────────────────────────┐
# │  MACCREv2 ENGINEERING DOCTRINE                             Law Rev: 19.0   │
# ├─────────────────────────────────────────────────────────────────────────────┤
# │  I.   TYPING      All signatures: explicit Python 3.11+ type hints.        │
# │  II.  LINTING     Zero unused imports. No wildcards. 120-char line max.    │
# └─────────────────────────────────────────────────────────────────────────────┘
"""
maccre_core/orchestration/payload_modes.py
==========================================
**The one place a payload mode is named.**

A payload mode answers one question: *which document does a node read?* Before this
module the answer was spelled out as bare string literals — ``"Unified Ledger"``,
``"Preceding Node Only"``, ``"Targeted Filter"`` — duplicated across seven files:
``topology_engine``, ``swarm_worker``, ``flow_engine``, ``macro_factory``,
``admin_tools``, ``nexus_plex`` and ``undo_manager``.

Three spellings of one concept across seven files is the condition under which a
fourth appears, and one nearly did: the mode is compared with ``==`` against a
literal in the two places that matter, so a topology carrying ``"Unifed Ledger"``
did not fail, did not warn, and quietly routed as though *Preceding Node Only* had
been chosen. A typo silently selected a different contract.

WHY THIS MODULE HAS NO IMPORTS FROM THE ORCHESTRATION GRAPH
-----------------------------------------------------------
``topology_engine`` is the normalisation seam every read passes through, and
``flow_engine`` imports ``topology_engine``. Putting the enum in ``flow_engine``
would therefore have made the seam import its own consumer. This module deliberately
depends on nothing but the standard library, so every one of the seven files can read
through it without an import cycle.

WHAT THIS MODULE DOES NOT DECIDE
--------------------------------
It names the modes and normalises a value to one of them. It does **not** say what
each mode *does* at a step boundary — that is the open payload-contract decision
recorded in the register, and it is deliberately not encoded here. A module that
answered it implicitly would settle by accident a question that is explicitly the
operator's.
"""
from __future__ import annotations

import logging
from enum import Enum

logger = logging.getLogger(__name__)

__all__ = [
    "AUTHORABLE_MODES",
    "DEFAULT_PAYLOAD_MODE",
    "PayloadMode",
    "resolve_payload_mode",
]


class PayloadMode(Enum):
    """Which document a node reads. The complete set — there is no fourth."""

    #: The assembled session ledger: every agent turn in the flow so far, in one
    #: document at ``04_Code_Artifacts/<job_id>/unified_session_ledger.md``.
    #: The default everywhere, and the only mode with a behavioural read today.
    UNIFIED_LEDGER = "Unified Ledger"

    #: Only the immediately preceding node's own artifact or ledger.
    #:
    #: **Offered in the UI and, until this module, read by nothing.** It worked by
    #: falling through: when the mode was not ``Unified Ledger`` the routing override
    #: simply did not fire, leaving ``routing_payload_path`` at the completing node's
    #: own product — which for an intra-step hop *is* preceding-node-only. Accidentally
    #: correct, which is the dangerous kind: any change to the default routing path
    #: would have silently redefined this mode, and that is precisely what defect E1
    #: was.
    PRECEDING_NODE_ONLY = "Preceding Node Only"

    #: A filtered ledger holding the setup phase, this agent's own prior drafts, and
    #: the aggregator's reviews addressed to it. Built by
    #: ``flow_engine.generate_targeted_ledger``.
    #:
    #: **Asymmetric with the other two, and worth knowing before changing anything
    #: here:** ``Targeted Filter`` is read on the *completing* node and rewrites what
    #: that node itself reads, whereas ``Unified Ledger`` is read on the *successor*
    #: and rewrites what the next node will read. Two modes on the same field with
    #: opposite subjects.
    TARGETED_FILTER = "Targeted Filter"


#: What a missing, blank or unrecognised value resolves to.
#:
#: ``Unified Ledger`` and not ``Preceding Node Only``, because that is what
#: ``topology_engine`` has always defaulted a missing or empty ``Payload_Mode``
#: column to, and what ``admin_tools.build_topology`` pads short rows with. Changing
#: the default would change the behaviour of every topology that omits the column.
DEFAULT_PAYLOAD_MODE = PayloadMode.UNIFIED_LEDGER

#: The modes an operator can choose in the node config modal.
#:
#: ``TARGETED_FILTER`` is **absent deliberately**: it is produced only by
#: ``macro_factory``'s consensus template for ``synthesis-blind`` variations, and it
#: describes a recursion mechanic rather than an authoring choice. It is still a real
#: mode a node can carry, which is why anything *rendering* the current value has to
#: accept all three even though only two are offered.
AUTHORABLE_MODES: tuple[PayloadMode, ...] = (
    PayloadMode.UNIFIED_LEDGER,
    PayloadMode.PRECEDING_NODE_ONLY,
)


def resolve_payload_mode(value: object, *, context: str = "") -> PayloadMode:
    """Normalise any authored or stored value to a :class:`PayloadMode`.

    Accepts a :class:`PayloadMode`, a string, ``None``, or anything else, because the
    value arrives from a CSV cell, a JSON round-trip, a UI select and a macro template
    — and one of those has always been able to hand over a typo.

    Matching is case-insensitive. The authoring surface is a text field and a CSV
    column; casing is not a declaration, and being strict about it would only widen
    the typo surface this function exists to narrow.

    Args:
        value: Whatever was authored or stored.
        context: Optional identifier — a node id is ideal — included in the warning
            so an unrecognised mode can be found rather than merely known about.

    Returns:
        The matching mode, or :data:`DEFAULT_PAYLOAD_MODE`.

    Note:
        **An unrecognised value warns and defaults; it does not raise.** This runs on
        the worker's hot path, and a topology typo is not worth killing a running
        flow over. It is a deliberate contrast with
        ``flow_engine.resolve_gather_strategy``, which *does* raise on an
        unrecognised Gather Strategy — because there, defaulting would silently
        gather lanes the author asked to leave alone, whereas here defaulting lands
        on the mode the author almost certainly meant.

        **This is a behaviour change for malformed values, and it is the point.**
        Previously an unrecognised mode was compared unequal to ``"Unified Ledger"``,
        no override fired, and the node was routed as ``Preceding Node Only`` in
        silence. Now it resolves to the default and says so. A topology reading
        ``"Unifed Ledger"`` will therefore route differently than it did before —
        differently, and as authored.
    """
    if isinstance(value, PayloadMode):
        return value

    text = str(value or "").strip()
    if not text:
        return DEFAULT_PAYLOAD_MODE

    for mode in PayloadMode:
        if text.casefold() == mode.value.casefold():
            return mode

    where = f" on {context}" if context else ""
    logger.warning(
        "[PAYLOAD_MODE] Unrecognised payload mode %r%s; using %s. Valid modes are %s. "
        "Before this was checked, an unrecognised mode routed as %r without saying so.",
        text, where, DEFAULT_PAYLOAD_MODE.value, [m.value for m in PayloadMode],
        PayloadMode.PRECEDING_NODE_ONLY.value,
    )
    return DEFAULT_PAYLOAD_MODE
