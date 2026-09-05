# ┌─────────────────────────────────────────────────────────────────────────────┐
# │  MACCREv2 ENGINEERING DOCTRINE                             Law Rev: 19.0   │
# ├─────────────────────────────────────────────────────────────────────────────┤
# │  I.   TYPING      All signatures: explicit Python 3.11+ type hints.        │
# │  II.  LINTING     Zero unused imports. No wildcards. 120-char line max.    │
# │  III. PATHS       Never hardcode absolute paths. Use get_maccre_root().     │
# │  VII. TEARDOWN    try/finally on all handles (omni clean compliance).      │
# │  VIII.TELEMETRY   No bare print(). logger only. JSON → 03_Agent_Ledgers.  │
# └─────────────────────────────────────────────────────────────────────────────┘
"""
maccre_core/orchestration/tether.py
===================================
Phase 6.13 — the tether ID, in one place.

A **tether ID** answers two different questions, and until now the codebase had no
single answer to either:

* **Which lane is this?** — lane identity, needed to address a node on a specific
  lane (``AGENT_A@X.2``) and to count lanes.
* **Which scatter does this lane belong to?** — the **gather scope**, which is what
  ``CTRL_MERGE`` fans in by.

Three representations, and the documented one did not exist
-----------------------------------------------------------
Before this module:

=========================================  ==============================  ==========
Where                                      Format                          Exists?
=========================================  ==============================  ==========
``design.md`` / ``IMPLEMENTATION_STATUS``  ``X`` → ``X.1`` → ``X.1.1``     **No**
``flow_engine._default_tether_id``         ``scatter_<sha1[:8]>``          Yes
``macronode_workshop`` (TUI)               ``tether_a``, ``tether_b``      Yes
=========================================  ==============================  ==========

The first was documented as a completed 88-line class at a named import path and
defines no code. The other two are live and disagree, and the TUI's value can
overwrite the engine's. That is Principle 4's named incident — a TUI building
``NAME_{i}`` while the engine built ``NAME_S{i}`` — repeated for an identifier that
is *acted on* rather than merely drawn: the gather gate scopes by it.

Why the hierarchy resolves it rather than replacing one flat scheme with another
-------------------------------------------------------------------------------
The flat form **is** the gather scope. One value is written to the scatter, every
lane, and the merge, and the gate matches on equality — so it can express "same
scatter" but cannot express "which lane". Giving each lane its own flat id would
express lane identity and destroy the scope, and *that* failure is already measured:
a blanked tether id put a scatter and its merge in different scopes, the gather gate
could never open, and an 8-lane run deadlocked.

A hierarchy carries both at once::

    X        the scatter, and what its CTRL_MERGE carries
    X.1      lane 1 of that scatter        lane_group("X.1")   == "X"
    X.1.1    lane 1 of a scatter inside lane X.1
                                          lane_group("X.1.1") == "X.1"

So the gate moves from *tether equality* to *same lane group*, and
:func:`lane_group` is the one function that decides it.

The migration property, which is the whole reason this is safe
--------------------------------------------------------------
:func:`lane_group` returns the **parent** for a hierarchical id and **the id itself**
for a flat one. For every topology already on disk — ``scatter_<sha1>`` or
``tether_a`` — ``lane_group(t) == t``, so "same lane group" degenerates *exactly* to
the equality the gate already performs. Nothing saved changes meaning.
:func:`is_hierarchical` is the only thing that distinguishes them, and it is one
character: does the id contain a level separator.

Generation is pure, and deliberately not the ``TetherIDGenerator`` the design asked for
---------------------------------------------------------------------------------------
``design.md`` specifies a stateful class with instance counters and a
``threading.Lock``. This module provides pure functions instead:
:func:`root_tether_id` takes the index, :func:`child_tether_ids` derives children
from the parent.

That is a deliberate deviation, and the argument for it is already in this codebase.
``_default_tether_id``'s docstring records that its predecessor was
``f"scatter_{id(scatter_agents) % 9999:04d}"`` — keyed on a CPython object address,
so **the tether validated by pre-flight was not necessarily the tether executed**,
because the auto-wrap runs twice per step. It was replaced with a stable digest for
exactly that reason. A locked counter reintroduces the same class of problem in a
milder form: the id a lane receives depends on how many times the generator has been
called, so it is not reproducible across a validate-then-execute pair, and the lock
is shared mutable state this package has already been bitten by. Derivation needs no
counter, no lock, and gives the same answer every time.

This module is pure: no I/O, no logging on the hot path, and no imports from
elsewhere in the orchestration package — so ``flow_engine``, ``local_broker``,
``topology_graph`` and the TUI can all read through it without a cycle.
"""
from __future__ import annotations

import logging
from typing import Iterable, Sequence

logger = logging.getLogger("maccre_core.tether")

__all__ = [
    "FORBIDDEN_IN_TETHER_ID",
    "MAX_CONCURRENT_LANES",
    "NESTING_DEPTH_WARN_AT",
    "ROOT_TETHER_IDS",
    "TETHER_LEVEL_SEPARATOR",
    "TetherIdError",
    "child_tether_ids",
    "count_lanes",
    "depth",
    "is_descendant_of",
    "is_hierarchical",
    "lane_group",
    "lanes_by_group",
    "level_count",
    "root_tether_id",
    "validate_tether_id",
]

#: Separates levels of the tether hierarchy. ``X.1.2`` is three levels.
#:
#: **Not** ``topology_graph.TETHER_SEPARATOR`` (``"@"``), which separates a *node* from
#: its lane in a reference like ``AGENT_A@X.2``. The two are different questions and
#: therefore different characters; :data:`FORBIDDEN_IN_TETHER_ID` is what keeps them
#: from colliding.
TETHER_LEVEL_SEPARATOR: str = "."

#: Characters a tether ID may not contain, because another seam already owns them.
#:
#: Every entry is here because something in this package would mis-parse it, not
#: because it looks untidy:
#:
#: * ``@`` — ``topology_graph.parse_tether_qualified_ref`` splits ``NODE@TETHER`` on it,
#:   and refuses a reference holding two. A tether containing ``@`` makes every
#:   reference to that lane unparseable.
#: * ``>`` — ``FLOW_VECTOR_SEPARATOR``. A tether containing it would forge a lineage hop.
#: * ``,`` and ``|`` — both accepted by ``topology_graph.parse_targets`` as target
#:   delimiters, so a tether containing either would split one lane into two names in
#:   ``Wait_For``.
FORBIDDEN_IN_TETHER_ID: frozenset[str] = frozenset({"@", ">", ",", "|"})

#: Depth at which Requirement 19.2 wants a nesting warning.
#:
#: **The requirement's prose and its own worked example disagree, so this reconciles
#: them explicitly rather than picking one silently.** 19.2 says *"depth reaches 3
#: levels (root → child → grandchild)"*; the design's example says
#: ``parse_depth("X.1.2") → 2``. Both describe the same tether — ``X.1.2`` is a
#: grandchild — counted differently: 3 *levels*, 2 *separators*.
#:
#: :func:`depth` counts separators, because that is the spec's only precise statement
#: of the number. This constant is therefore 2, and :func:`level_count` exists for the
#: prose sense so neither reading has to be re-derived at a call site.
NESTING_DEPTH_WARN_AT: int = 2

#: Requirement 19.3's ceiling on total concurrent lanes.
#:
#: **Unrelated to** ``concurrency.MAX_SCATTER_AGENTS`` (8) and
#: ``concurrency.SCATTER_HARD_CAP`` (12), which bound **threads**. A topology may
#: declare more lanes than the pool will ever run at once; ``flow_engine``'s readout
#: already draws that distinction and it is correct. This number is an authoring
#: limit and is **not** validated against evidence — it is Requirement 19.3 as written.
MAX_CONCURRENT_LANES: int = 64

#: Root tether IDs in order, as Requirement 18.4 and ``design.md`` name them.
#:
#: ``X``, ``Y``, ``Z``, then two letters from ``AA``. The letters carry no meaning; they
#: are reused from the design so that a topology authored against that document reads
#: the same way.
ROOT_TETHER_IDS: tuple[str, ...] = ("X", "Y", "Z")

_ALPHABET: str = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"


class TetherIdError(ValueError):
    """A tether ID that cannot be used without breaking a downstream seam.

    Carries *reason* as a bare predicate so a caller can compose a sentence about the
    offending id without printing it twice — the same shape as
    ``topology_graph.TetherRefError``, deliberately, so the two read alike.
    """

    def __init__(self, tether_id: str, reason: str) -> None:
        self.tether_id: str = tether_id
        self.reason: str = reason
        super().__init__(f"{tether_id!r} {reason}")


def validate_tether_id(tether_id: str) -> str:
    """Return *tether_id* normalised, or raise.

    **Deliberately permissive.** This runs against tether IDs that are *already saved*
    — ``scatter_<sha1>`` from the engine, ``tether_a`` from the TUI, and anything an
    operator typed into the Tether ID box. Refusing something a saved topology already
    contains would break that operator's flow at launch, so the only things refused are
    the ones that genuinely break a downstream parser:

    * empty, or whitespace only
    * a character in :data:`FORBIDDEN_IN_TETHER_ID`
    * an empty level — ``".X"``, ``"X."``, ``"X..1"`` — which would make
      :func:`lane_group` return a meaningless parent

    An interior space is **allowed**, because it parses fine everywhere and an operator
    may already have saved one.

    Args:
        tether_id: The id as authored or stored.

    Returns:
        The id with surrounding whitespace removed.

    Raises:
        TetherIdError: The id would break a seam named above.
    """
    text = str(tether_id or "").strip()
    if not text:
        raise TetherIdError(text, "is empty; a lane with no tether cannot be scoped")

    offending = sorted(c for c in FORBIDDEN_IN_TETHER_ID if c in text)
    if offending:
        raise TetherIdError(
            text,
            "contains " + ", ".join(repr(c) for c in offending)
            + ", which another seam parses as a separator",
        )

    if TETHER_LEVEL_SEPARATOR in text:
        levels = text.split(TETHER_LEVEL_SEPARATOR)
        if any(not level.strip() for level in levels):
            raise TetherIdError(
                text,
                f"has an empty level; every segment between {TETHER_LEVEL_SEPARATOR!r} "
                "must name something",
            )
    return text


def is_hierarchical(tether_id: str) -> bool:
    """True when *tether_id* names a lane inside a scatter, rather than a scatter.

    One character decides it: whether a level separator is present. That is what makes
    the legacy flat ids self-identifying, and therefore what makes :func:`lane_group`
    backward compatible without a version flag or a migration pass.
    """
    return TETHER_LEVEL_SEPARATOR in validate_tether_id(tether_id)


def depth(tether_id: str) -> int:
    """Nesting depth of *tether_id*, counted in separators.

    ``X`` → 0, ``X.1`` → 1, ``X.1.2`` → 2, matching the design's worked example
    ``parse_depth("X.1.2") → 2``. A flat legacy id such as ``scatter_ab12cd34`` is
    depth **0** — it names a scatter, and it has no lanes of its own to be nested in.

    See :func:`level_count` for the "3 levels" reading of the same tether.
    """
    return validate_tether_id(tether_id).count(TETHER_LEVEL_SEPARATOR)


def level_count(tether_id: str) -> int:
    """How many levels *tether_id* names, counting the root. ``X.1.2`` → 3.

    Exists so Requirement 19.2's prose ("3 levels") and the design's example
    (``parse_depth → 2``) can both be spoken without either being re-derived at a call
    site from the other. Always ``depth() + 1``, and a test pins that so the two cannot
    drift into independent definitions.
    """
    return depth(tether_id) + 1


def lane_group(tether_id: str) -> str:
    """The gather scope *tether_id* belongs to. **The function the fan-in gate turns on.**

    For a hierarchical id this is the parent — the scatter whose ``CTRL_MERGE`` should
    collect this lane. For a flat id it is **the id itself**, which is what makes the
    change to the gate a no-op for every topology already on disk:

    ==========================  =======================  ============================
    Input                       Returns                  Why
    ==========================  =======================  ============================
    ``"X.1"``                   ``"X"``                  lane 1 gathers at scatter X
    ``"X.1.2"``                 ``"X.1"``                nested; gathers one level up
    ``"X"``                     ``"X"``                  a root has no parent
    ``"scatter_ab12cd34"``      ``"scatter_ab12cd34"``   legacy flat: unchanged
    ``"tether_a"``              ``"tether_a"``           legacy flat: unchanged
    ==========================  =======================  ============================

    A root returning itself is not a fallback: a scatter at the top level *is* its own
    gather scope, which is exactly the relationship the flat scheme encoded for
    everything. So the flat case and the root case are the same case, and that is why
    there is no legacy branch here to keep correct.
    """
    text = validate_tether_id(tether_id)
    if TETHER_LEVEL_SEPARATOR not in text:
        return text
    return text.rsplit(TETHER_LEVEL_SEPARATOR, 1)[0]


def is_descendant_of(tether_id: str, ancestor: str) -> bool:
    """True when *tether_id* names a lane at or below *ancestor* in the hierarchy.

    Compared level by level, **never by string prefix**. ``"X.10"`` is not a descendant
    of ``"X.1"``, and a prefix test would say it was — an approximately-correct answer
    that would fold two lanes of an 8+ lane scatter into one gather scope.

    A tether is its own descendant, so ``is_descendant_of("X", "X")`` is True. That
    matches :func:`lane_group`'s treatment of a root and keeps "everything under X"
    from needing a separate "and X itself" clause at every call site.
    """
    own = validate_tether_id(tether_id).split(TETHER_LEVEL_SEPARATOR)
    theirs = validate_tether_id(ancestor).split(TETHER_LEVEL_SEPARATOR)
    if len(theirs) > len(own):
        return False
    return own[: len(theirs)] == theirs


def root_tether_id(index: int) -> str:
    """The *index*-th root tether ID. ``0`` → ``"X"``, ``1`` → ``"Y"``, ``2`` → ``"Z"``,
    ``3`` → ``"AA"``, ``4`` → ``"AB"``, ``29`` → ``"BA"``.

    Pure and derived, so the same index always gives the same id. The auto-wrap runs
    twice per step — once for pre-flight validation, once for execution — and a
    stateful counter would hand those two runs different ids for the same lane. That is
    not hypothetical: ``_default_tether_id`` records being changed away from an
    ``id()``-derived value for exactly this reason.

    Args:
        index: Zero-based root index.

    Returns:
        The root id.

    Raises:
        ValueError: *index* is negative. There is no root before the first.
    """
    if index < 0:
        raise ValueError(f"root tether index must be >= 0; got {index}")
    if index < len(ROOT_TETHER_IDS):
        return ROOT_TETHER_IDS[index]

    # Past Z, two letters from AA, then three, and so on. Bijective base-26, offset so
    # the sequence starts at "AA" (27) rather than "A" (1).
    #
    # That offset is load-bearing and was caught by `test_no_two_indices_collide`: the
    # first version started at 1, which emitted the single letters "A".."Z" for indices
    # 3..28 — and index 26 produced "X", colliding with root index 0. Two different
    # roots sharing one tether ID is the whole class of defect this module exists to
    # remove, so the guard is a permanent test rather than a comment.
    n = index - len(ROOT_TETHER_IDS) + 27
    out = ""
    while n > 0:
        n, rem = divmod(n - 1, 26)
        out = _ALPHABET[rem] + out
    return out


def child_tether_ids(parent: str, count: int) -> list[str]:
    """Tether IDs for *count* lanes spawned inside *parent*. Requirement 18.3.

    ``child_tether_ids("X", 3)`` → ``["X.1", "X.2", "X.3"]``.
    ``child_tether_ids("X.1", 2)`` → ``["X.1.1", "X.1.2"]``.

    One-based, because these are lane numbers an operator reads in a refusal message
    and in the TUI, and a lane called "lane 0" reads as an off-by-one every time.

    Works on a flat legacy parent too — ``child_tether_ids("scatter_ab12cd34", 2)``
    gives ``["scatter_ab12cd34.1", "scatter_ab12cd34.2"]`` — so a saved topology can
    gain per-lane tethers without first being renamed. Their
    :func:`lane_group` is the original flat id, which is the value the existing merge
    row already carries.

    Args:
        parent: The tether the lanes are spawned inside.
        count: How many lanes. Zero returns an empty list rather than raising, because
            a scatter with no targets is a topology defect for the validator to report,
            not something this function should decide.

    Returns:
        Lane tether IDs in declared order.

    Raises:
        TetherIdError: *parent* is not usable.
        ValueError: *count* is negative.
    """
    base = validate_tether_id(parent)
    if count < 0:
        raise ValueError(f"lane count must be >= 0; got {count}")
    return [f"{base}{TETHER_LEVEL_SEPARATOR}{i}" for i in range(1, count + 1)]


def count_lanes(tether_ids: Iterable[str]) -> int:
    """How many distinct lanes *tether_ids* names. For Requirement 19.3's ceiling.

    Counts **distinct** ids, so the ten rows of an 8-lane scatter (scatter + 8 lanes +
    merge) do not read as ten lanes. Malformed ids are skipped and logged rather than
    raising, because this is a count for a limit check and a validator elsewhere is the
    thing that should refuse a bad id by name.
    """
    seen: set[str] = set()
    for raw in tether_ids:
        try:
            seen.add(validate_tether_id(raw))
        except TetherIdError as exc:
            logger.warning(
                "[TETHER] Skipping unusable tether id while counting lanes: %s", exc
            )
    return len(seen)


def lanes_by_group(tether_ids: Sequence[str]) -> dict[str, list[str]]:
    """Group lane tethers by their gather scope, preserving first-seen order.

    ``["X.1", "X.2", "Y.1"]`` → ``{"X": ["X.1", "X.2"], "Y": ["Y.1"]}``.

    This is what a merge needs in order to know which lanes it is waiting on, and what
    a lane-limit check needs in order to count lanes per scatter. Ordering is
    first-seen rather than sorted, so a refusal or a readout reads the same way twice.
    """
    grouped: dict[str, list[str]] = {}
    for raw in tether_ids:
        try:
            lane = validate_tether_id(raw)
        except TetherIdError as exc:
            logger.warning("[TETHER] Skipping unusable tether id while grouping: %s", exc)
            continue
        grouped.setdefault(lane_group(lane), []).append(lane)
    return grouped
