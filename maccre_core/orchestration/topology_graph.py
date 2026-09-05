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
maccre_core/orchestration/topology_graph.py
===========================================
Phase 6.13 — the topology read as a graph, in one place.

A MACCRE topology is a directed graph. Three structural questions get asked of it
repeatedly:

* **Which nodes start it?** Needed to seed ``task_queue``.
* **Which nodes end it?** Needed for fan-in — a merge must wait on the *last*
  node of each lane, not merely on a node it happens to name.
* **Where does an edge point?** Needed by everything.

Before this module each caller answered those independently, and they disagreed.

The parsing disagreement
------------------------
``Next_Node`` is a delimited list, and the codebase held three incompatible
readings of it:

===================================  ==========================================
Reader                               Accepted delimiters
===================================  ==========================================
``local_broker.route_task``          ``,`` **and** ``|`` — the one that routes
``flow_engine._hydrate_topology``    ``,`` only
``topology_engine.validate``         ``,`` only
``deterministic_nodes`` loop target  ``.split("|")[0]`` — first pipe field only
===================================  ==========================================

So the component that actually creates successor rows was the most permissive,
while the components that hydrate and validate were stricter and differently
strict. A hand-authored ``Next_Node`` of ``"B|C"`` would route correctly at
execution time but hydrate into the single phantom token ``B|C_S0``. Authoring
topologies by hand and saving them as MacroNodes is a first-class workflow, so
"whichever parser you happen to reach decides what your graph means" is not a
survivable contract. :func:`parse_targets` is the one reading.

The entry-point disagreement
----------------------------
``_find_starting_nodes`` inferred entry points from ``Wait_For == "none"``. But
``Wait_For`` is the **gather gate** — "how many upstreams must complete before I
may run" — not a predecessor list. "I wait for nobody" and "nobody precedes me"
are different claims, and they diverge exactly where it hurts: the scatter
auto-wrap sets ``Wait_For: "none"`` on every lane, because a lane gathers from
nothing. Read as entry points, all eight lanes were seeded directly against the
raw job payload alongside the scatter meant to feed them, and every agent in an
8-wide scatter executed twice.

Reachability is a property of the edges, so it is computed from the edges:
a node is an entry point when no *other* node targets it.

Why this is a module and not three helpers
------------------------------------------
Topology is not patchwork; it is one structure that several layers project. The
engine seeds from it, the fan-in gate measures it, the visualiser draws it, and
telemetry will eventually sweep it. Every one of those consumers needs the same
answer to "what is the shape of this graph", and any consumer that re-derives it
privately is free to drift — which is what happened here. Keeping the derivation
in one pure, dependency-free module means a future visualisation or measurement
layer reads the same graph the engine executes, rather than a lookalike.

This module is deliberately pure: no I/O, no logging side effects on the hot
path, no imports from elsewhere in the orchestration package. It takes row dicts
and returns names.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping, Sequence

logger = logging.getLogger("maccre_core.topology_graph")

__all__ = [
    "FLOW_VECTOR_SEPARATOR",
    "TERMINAL_SENTINELS",
    "TETHER_SEPARATOR",
    "CrossLaneRouteReport",
    "GatherReachabilityReport",
    "TerminalOutputSet",
    "RoutedNode",
    "TetherQualifiedRef",
    "TetherRefError",
    "apply_cross_lane_route",
    "build_edges",
    "describe",
    "entry_nodes",
    "is_terminal_target",
    "node_ids",
    "parse_targets",
    "parse_tether_qualified_ref",
    "record_crossing",
    "terminal_nodes",
    "terminal_outputs_for_step",
    "unreachable_nodes",
    "validate_cross_lane_routes",
    "validate_gather_reachability",
]

#: Values that may appear as a routing target without naming a real node.
#:
#: Matches ``topology_engine.validate``'s ``_TERMINALS`` plus the extra spellings
#: ``local_broker.route_task`` already refuses to enqueue, so the graph agrees with
#: both. Compared case-insensitively.
TERMINAL_SENTINELS: frozenset[str] = frozenset({
    "",
    "DONE",
    "END",
    "FAILED",
    "HUMAN_GATE",
    "NONE",
    "NULL",
    "STOP",
    "TERMINATE",
})


def is_terminal_target(name: str) -> bool:
    """True when *name* ends a lane rather than naming a successor node."""
    return name.strip().upper() in TERMINAL_SENTINELS


def parse_targets(value: Any) -> list[str]:
    """Split a ``Next_Node`` / ``Wait_For`` field into real node names.

    Accepts both ``,`` and ``|`` as separators, because the broker that actually
    enqueues successors accepts both and a topology must mean the same thing to
    every reader. Terminal sentinels (``END``, ``FAILED``, ``DONE``, ...) are
    dropped: they are edge *labels*, not vertices, and counting them as nodes
    would give every terminating lane a phantom successor.

    Duplicates are removed while preserving first-appearance order, so a
    fan-out's declared ordering survives.

    Args:
        value: Raw field value. ``None`` and non-strings are tolerated and treated
            as empty, since these rows come from CSV, JSON and hand editing.

    Returns:
        Node names in declaration order, no duplicates, no sentinels.
    """
    if value is None:
        return []
    raw = str(value).replace("|", ",")
    seen: set[str] = set()
    out: list[str] = []
    for part in raw.split(","):
        name = part.strip()
        if not name or is_terminal_target(name):
            continue
        if name not in seen:
            seen.add(name)
            out.append(name)
    return out


def node_ids(rows: Sequence[Mapping[str, Any]]) -> list[str]:
    """Every ``Node_ID`` in *rows*, in row order, without duplicates.

    A duplicate ``Node_ID`` is reported rather than silently collapsed. It is
    always a defect — ``task_queue`` enforces ``UNIQUE(job_id, current_node)``, so
    two rows sharing a name become one row at execution time and one of the two
    nodes simply never runs as authored.
    """
    seen: set[str] = set()
    out: list[str] = []
    for row in rows:
        node_id = str(row.get("Node_ID", "") or "").strip()
        if not node_id:
            continue
        if node_id in seen:
            logger.warning(
                "[TOPOLOGY_GRAPH] Duplicate Node_ID %r; task_queue will collapse "
                "these into one row.", node_id,
            )
            continue
        seen.add(node_id)
        out.append(node_id)
    return out


def build_edges(rows: Sequence[Mapping[str, Any]]) -> dict[str, list[str]]:
    """Map each node to the successors its ``Next_Node`` names.

    Targets are returned as authored, including any that name no row in this
    topology. Validating existence belongs to ``topology_engine.validate``, which
    can produce a proper diagnostic; silently dropping them here would hide the
    defect from the layer whose job it is to report it.

    On a duplicate ``Node_ID`` the first row wins, matching what ``task_queue``'s
    ``UNIQUE(job_id, current_node)`` constraint does at execution time.
    """
    edges: dict[str, list[str]] = {}
    for row in rows:
        node_id = str(row.get("Node_ID", "") or "").strip()
        if not node_id or node_id in edges:
            continue
        edges[node_id] = parse_targets(row.get("Next_Node"))
    return edges


def entry_nodes(rows: Sequence[Mapping[str, Any]]) -> list[str]:
    """Nodes nothing else routes to — where execution begins.

    In-degree is counted over ``Next_Node`` edges only, and **self-edges are
    ignored**. A node that routes to itself is the loop/recursion primitive; it is
    still an entry point if nothing external reaches it, and treating its own
    back-edge as an inbound reference would make a single self-looping node
    unstartable.

    Only references *from nodes present in these rows* count. A dangling name in
    some other row cannot confer in-degree on anything, and a node named by
    nothing present is genuinely an entry.

    Returns:
        Entry node names in row order. Never empty for a non-empty topology — see
        the cycle fallback below.
    """
    edges = build_edges(rows)
    if not edges:
        return []

    present = set(edges)
    referenced: set[str] = set()
    for source, targets in edges.items():
        for target in targets:
            if target == source:
                continue  # self-loop: the recursion primitive, not a predecessor
            if target in present:
                referenced.add(target)

    entries = [node_id for node_id in edges if node_id not in referenced]
    if entries:
        return entries

    # Every node has an inbound edge, so the graph is one or more cycles with no
    # way in. Unstartable as authored. Seed the first row so the flow makes
    # progress and the operator sees a running job to diagnose, rather than a
    # silent no-op — matching the pre-existing fallback this replaced.
    first = next(iter(edges))
    logger.warning(
        "[TOPOLOGY_GRAPH] No entry node: every node is routed to by another "
        "(cyclic topology). Falling back to %r as the entry point.", first,
    )
    return [first]


def terminal_nodes(rows: Sequence[Mapping[str, Any]]) -> list[str]:
    """Nodes that end a lane — no successor other than a sentinel or themselves.

    This is the fan-in question. ``CTRL_MERGE`` must wait on the *last* node of
    each lane, and once a lane is a chain rather than a single node (Task B3) the
    last node is no longer the one the scatter named. Computing it from the edges
    means a lane can grow without the merge's gather gate needing to be rewritten.

    A node whose only successor is itself counts as terminal: an unbounded
    self-loop has no exit, and the recursion limit rather than the graph decides
    when it stops.
    """
    edges = build_edges(rows)
    return [
        node_id
        for node_id, targets in edges.items()
        if not [t for t in targets if t != node_id]
    ]


def unreachable_nodes(rows: Sequence[Mapping[str, Any]]) -> list[str]:
    """Nodes no traversal from the entry points can reach.

    Not used to gate execution — it is diagnostic. A node that cannot be reached
    is authored work that will never run, which on a hand-built topology is
    almost always a mistake worth surfacing rather than paying for in confusion.
    """
    edges = build_edges(rows)
    if not edges:
        return []

    reached: set[str] = set()
    stack: list[str] = list(entry_nodes(rows))
    while stack:
        node = stack.pop()
        if node in reached:
            continue
        reached.add(node)
        stack.extend(t for t in edges.get(node, []) if t in edges)

    return [node_id for node_id in edges if node_id not in reached]


def describe(rows: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    """Structural summary of a topology. For diagnostics and telemetry.

    One call answering "what shape is this graph" for any consumer that wants to
    render or measure it, so such a layer never has to re-derive the structure the
    engine executes.
    """
    materialised = list(rows)
    return {
        "nodes": node_ids(materialised),
        "edges": build_edges(materialised),
        "entry_nodes": entry_nodes(materialised),
        "terminal_nodes": terminal_nodes(materialised),
        "unreachable_nodes": unreachable_nodes(materialised),
    }


# ── Requirement 31: tether-qualified references and cross-lane routing ───────
#
# Added 2026-09-05. A tether ID names a lane; a node ID names a step. A route between
# lanes needs both, so ``AGENT_A@X.2`` is the address the routing graph works in — and
# the tether hierarchy stops being a containment tree alone and becomes a routing graph
# over one.
#
# ONE SEPARATOR, ONE PARSE, ONE RENDER
# ------------------------------------
# Requirement 33's paradox detector already parsed this shape, inline, with a bare
# ``"@" not in target`` test followed by ``partition("@")``, while ``_qualify`` rendered
# it from a separate ``f"{node_id}@{tether_id}"``. Two derivations of one structure, and
# they had already diverged: the inline parse accepted ``"@X.1"`` (no node), ``"A@"``
# (no lane) and read ``"A@X.1@Y"`` as a lane literally named ``X.1@Y``. The renderer
# could never produce any of the three.
#
# An empty tether ID is not hypothetical. Principle 2's named incident is a blanked
# tether id putting a scatter and its merge in different scopes, so the gather gate
# could never open and an 8-lane run deadlocked — an *empty* tether would merely have
# degraded visibly. A parser that hands back an empty tether instead of refusing is the
# mechanism that manufactures exactly that address.
#
# So: one constant for the separator, one parse, one render, a round-trip test tying
# them together, and Requirement 33's detector reads through the parse rather than
# keeping a private lookalike. ``_lane_fault`` below is the single resolver both the
# paradox detector and the cross-lane validator consult, which is why 31.3/31.4 and
# 33.2's cases 3 and 4 produce word-for-word identical diagnostics: they are the same
# check asked by two callers, not two checks that happen to agree today.

#: The one place the node/lane separator is written.
TETHER_SEPARATOR: str = "@"

#: Separator ``flow_vector`` lineage strings are joined with.
#:
#: Matches what ``swarm_worker`` writes today. **It is still a literal there**, so this
#: is a second derivation until :func:`record_crossing` is wired — the red Requirement
#: 31.6 marker in ``tests/test_topological_semantic_spec.py`` is what keeps that visible
#: rather than letting it settle in as permanent duplication.
FLOW_VECTOR_SEPARATOR: str = ">"


class TetherRefError(ValueError):
    """A reference that does not name exactly one node in exactly one lane.

    Carries *reason* as a bare predicate — ``"is not tether-qualified ..."`` — so a
    caller composing a sentence about the offending reference does not print the
    reference twice. ``str(exc)`` is the whole sentence, for anyone who lets it
    propagate.

    Subclasses ``ValueError`` because that is what a malformed string argument already
    means everywhere else in this package; callers that do not care about the
    distinction keep working.
    """

    def __init__(self, ref: str, reason: str) -> None:
        self.ref: str = ref
        self.reason: str = reason
        super().__init__(f"{ref!r} {reason}")


@dataclass(frozen=True)
class TetherQualifiedRef:
    """A node in a named lane. Requirement 31.2.

    Attributes:
        node_id: The step's ``Node_ID``. Never empty — :func:`parse_tether_qualified_ref`
            refuses rather than constructing one.
        tether_id: The lane's tether ID. Never empty, for the same reason.
    """

    node_id: str
    tether_id: str

    def render(self) -> str:
        """The reference as authored. Inverse of :func:`parse_tether_qualified_ref`."""
        return _qualify(self.node_id, self.tether_id)


@dataclass(frozen=True)
class RoutedNode:
    """A node that a cross-lane route arrived at. Requirement 31.7.

    Attributes:
        node_id: The node routed to.
        tether_id: Its **containment** tether — unchanged by the route. Routing and
            containment are different relations, and fan-in scopes by containment, so
            letting a route rewrite this would make a node's gather scope depend on who
            pointed at it.
        arrived_from: The tether the route came from. Recorded rather than substituted.
    """

    node_id: str
    tether_id: str
    arrived_from: str

    def render(self) -> str:
        """The node's own address — the lane it belongs to, not the one that called."""
        return _qualify(self.node_id, self.tether_id)


@dataclass(frozen=True)
class CrossLaneRouteReport:
    """Which cross-lane route targets a topology cannot honour. Requirements 31.3/31.4.

    Attributes:
        refused: True when any route names an address the topology will not contain at
            execution. The single question a launch gate needs answered.
        offences: ``(route, offending_ref, reason)`` per fault, where *route* is the
            ``source -> target`` pair as authored.
        participants: Every reference implicated, first-seen order, de-duplicated. Same
            obligation as :attr:`ParadoxReport.participants`: name them, because a
            generic refusal sends the author searching eight lanes for the one typo.
    """

    refused: bool
    offences: list[tuple[str, str, str]] = field(default_factory=list)
    participants: list[str] = field(default_factory=list)

    def message(self) -> str:
        """A refusal a human can act on.

        A **method**, not a property, because :meth:`ParadoxReport.message` is one and
        two spellings of "render the refusal" in one module is the drift this module
        exists to prevent.
        """
        if not self.refused:
            return "No cross-lane routing fault detected."
        return "; ".join(
            f"route {route} names {ref}, which {reason}" for route, ref, reason in self.offences
        )


def _qualify(node_id: str, tether_id: str) -> str:
    """Render a tether-qualified reference. The only place the separator is written."""
    return f"{node_id}{TETHER_SEPARATOR}{tether_id}"


def parse_tether_qualified_ref(ref: str) -> TetherQualifiedRef:
    """Read ``"AGENT_A@X.2"`` into its node and lane. Requirement 31.2.

    The inverse of :meth:`TetherQualifiedRef.render`, over the same
    :data:`TETHER_SEPARATOR`.

    Every rejection below is a reference that *would have produced a usable-looking
    address*: an empty node id, an empty tether id, or a lane whose name silently
    swallowed a second separator. Returning any of them would satisfy the caller's type
    expectations and be wrong downstream, which is the Principle 2 failure mode
    exactly — so this raises instead of degrading.

    Args:
        ref: The reference as authored. Surrounding whitespace is tolerated on the whole
            string and on each component, because these come from CSV and hand editing.

    Returns:
        The parsed reference, with both components non-empty.

    Raises:
        TetherRefError: The reference does not name exactly one node in exactly one lane.
    """
    text = str(ref or "").strip()
    separators = text.count(TETHER_SEPARATOR)
    if separators == 0:
        raise TetherRefError(
            text, f"is not tether-qualified (expected NODE{TETHER_SEPARATOR}TETHER)"
        )
    if separators > 1:
        raise TetherRefError(
            text,
            f"holds {separators} {TETHER_SEPARATOR!r} separators; a reference names "
            "exactly one node in exactly one lane",
        )
    node_id, _, tether_id = text.partition(TETHER_SEPARATOR)
    node_id, tether_id = node_id.strip(), tether_id.strip()
    if not node_id:
        raise TetherRefError(text, f"names no node before the {TETHER_SEPARATOR!r}")
    if not tether_id:
        raise TetherRefError(text, f"names no lane after the {TETHER_SEPARATOR!r}")
    return TetherQualifiedRef(node_id=node_id, tether_id=tether_id)


def _lane_fault(ref_text: str, known: Mapping[str, set[str]]) -> str:
    """Why *ref_text* cannot be resolved against *known* lanes, or ``""`` if it can.

    The single resolver behind Requirements 31.3, 31.4 and 33.2's cases 3 and 4. The
    reason strings are the diagnostic surface of all four, so they live here once.
    """
    try:
        ref = parse_tether_qualified_ref(ref_text)
    except TetherRefError as exc:
        return exc.reason
    if ref.tether_id not in known:
        return f"names lane {ref.tether_id!r}, which the topology never spawns"
    if ref.node_id not in known[ref.tether_id]:
        return f"names a node absent from lane {ref.tether_id!r}"
    return ""


def validate_cross_lane_routes(
    lanes: Mapping[str, Sequence[str]],
    routes: Sequence[tuple[str, str]],
) -> CrossLaneRouteReport:
    """Refuse routes naming an address no lane will occupy. Requirements 31.3 and 31.4.

    Both ends of every route are checked. A route *from* a node that does not exist is
    as broken as a route *to* one, and the offence names which end is at fault by
    quoting the reference rather than the position.

    Args:
        lanes: ``{tether_id: [node_id, ...]}`` — every lane the topology will spawn and
            the nodes it will contain. Order is irrelevant here (unlike
            :func:`detect_temporal_paradox`, where it carries the same-lane ordering).
        routes: ``(source_ref, target_ref)`` pairs, both tether-qualified.

    Returns:
        A :class:`CrossLaneRouteReport`. ``refused`` False is a statement about these
        routes against these lanes — not that the flow will succeed.
    """
    known: dict[str, set[str]] = {t: set(nodes) for t, nodes in lanes.items()}
    offences: list[tuple[str, str, str]] = []
    participants: list[str] = []

    for source, target in routes:
        route = f"{source} -> {target}"
        for ref_text in (source, target):
            reason = _lane_fault(ref_text, known)
            if reason:
                offences.append((route, ref_text, reason))
                participants.append(ref_text)

    seen: set[str] = set()
    ordered = [p for p in participants if not (p in seen or seen.add(p))]
    return CrossLaneRouteReport(refused=bool(offences), offences=offences, participants=ordered)


def apply_cross_lane_route(node_id: str, own_tether: str, from_tether: str) -> RoutedNode:
    """Route into a node without re-parenting it. Requirement 31.7.

    Containment and routing are different relations. The returned node keeps
    *own_tether*; *from_tether* is recorded as :attr:`RoutedNode.arrived_from` and never
    substituted. Conflating them would make a node's tether ID depend on who routed to
    it, and the tether ID is what fan-in scopes by — so the merge for lane ``X.2`` would
    start or stop seeing this node according to which other lane pointed at it.

    Args:
        node_id: The node being routed to.
        own_tether: Its containment tether. **Required**, and an empty one is refused
            rather than defaulted to *from_tether*.
        from_tether: The lane the route originates in.

    Returns:
        The routed node, containment intact.

    Raises:
        ValueError: A component is empty, or *from_tether* equals *own_tether* — which
            is not a cross-lane route and would record a crossing that never happened.
    """
    node = str(node_id or "").strip()
    own = str(own_tether or "").strip()
    origin = str(from_tether or "").strip()
    if not node:
        raise ValueError("a cross-lane route needs a node id; got an empty one")
    if not own:
        raise ValueError(
            f"node {node!r} has no containment tether id. Refusing rather than adopting "
            f"the routing lane {origin!r}: a blanked tether id is what put a scatter and "
            "its merge in different scopes, so the gather gate could never open."
        )
    if not origin:
        raise ValueError(f"a route into {node!r} needs the lane it came from; got an empty one")
    if origin == own:
        raise ValueError(
            f"{_qualify(node, own)} is not a cross-lane route: the origin lane {origin!r} is "
            "the node's own lane"
        )
    return RoutedNode(node_id=node, tether_id=own, arrived_from=origin)


def record_crossing(flow_vector: str, routed: RoutedNode) -> str:
    """Append a lane crossing to a ``flow_vector`` lineage string. Requirement 31.6.

    No new syntax. Entries are tether-qualified, so ``A@X.1>B@X.2`` states the crossing
    by itself and a downstream artifact's provenance carries the lane it came from
    without a second notation to keep in step.

    When the existing vector's last entry *is* tether-qualified and its lane disagrees
    with :attr:`RoutedNode.arrived_from`, the two records contradict each other and this
    raises. When the last entry is a bare node name — which is what ``swarm_worker``
    writes today — the crossing cannot be corroborated, and it is appended without any
    claim that it was.

    Args:
        flow_vector: The lineage so far. Empty starts a new one.
        routed: The node arrived at, from :func:`apply_cross_lane_route`.

    Returns:
        The extended lineage string.

    Raises:
        ValueError: The previous entry names a lane other than *routed.arrived_from*.
    """
    existing = str(flow_vector or "").strip()
    if not existing:
        return routed.render()

    previous = existing.rsplit(FLOW_VECTOR_SEPARATOR, 1)[-1].strip()
    if TETHER_SEPARATOR in previous:
        try:
            previous_ref = parse_tether_qualified_ref(previous)
        except TetherRefError:
            previous_ref = None  # unparseable history: cannot corroborate, do not claim to
        if previous_ref is not None and previous_ref.tether_id != routed.arrived_from:
            raise ValueError(
                f"lineage says the previous node ran in lane {previous_ref.tether_id!r} but the "
                f"route into {routed.node_id!r} claims to come from {routed.arrived_from!r}"
            )
    return f"{existing}{FLOW_VECTOR_SEPARATOR}{routed.render()}"


# ── Requirement 33: pre-launch paradox detection ─────────────────────────────
#
# Added 2026-09-04 by the topological-semantic amendment. A wait condition that no
# execution order can satisfy must be refused *before* launch, because at runtime it
# is indistinguishable from a slow node — and defect F3 already established what that
# costs: a hold nobody could release ran out a 3600-second budget and then reported
# `completed`.
#
# THE MECHANISM IS ONE CHECK, NOT FOUR
# ------------------------------------
# Requirement 33.2 lists four conditions to cover, and it would be natural to write
# four detectors. Two of them are the same thing:
#
#   * a wait on a node *downstream of itself within its own lane*, and
#   * a *cycle* of waits across two or more lanes
#
# are both cycles in a single **precedence graph**, once you write down both kinds of
# ordering constraint that exist:
#
#   sequence edge   node[i] --> node[i+1]   within a lane, execution is ordered
#   wait edge       target  --> waiter      a waiter cannot run before its target
#
# A lane `[WAIT_ON_B, B]` where `WAIT_ON_B` waits on `B` yields the sequence edge
# `WAIT_ON_B -> B` and the wait edge `B -> WAIT_ON_B`. That is a two-node cycle. Two
# lanes waiting on each other yield the same shape without any sequence edges. So one
# cycle detection covers both, and it will also catch three-lane and longer cycles
# nobody thought to enumerate — which is the argument for deriving the check from the
# model instead of listing the cases.
#
# The other two conditions are reference-validity errors rather than ordering
# contradictions, and are reported separately so a refusal can say *which* kind of
# wrong the topology is.


@dataclass(frozen=True)
class ParadoxReport:
    """Why a topology's wait conditions cannot be satisfied, if they cannot.

    Attributes:
        paradox: True when any unsatisfiable condition exists — a cycle *or* an
            unresolvable reference. The single question a launch gate needs answered.
        cycles: Each detected cycle, as the ordered list of participating
            tether-qualified node references.
        unresolvable: References that name a lane or node the topology does not
            contain, as ``(waiter, bad_target, reason)``.
        unresolvable_waiters: **Waiter** references that cannot be resolved, as
            ``(waiter, reason)``. Separate from :attr:`unresolvable` because there is no
            target to blame — the party doing the waiting is the one that does not exist.
            Added 2026-09-05: the keys were previously never validated, so a malformed
            waiter silently became a precedence-graph node and could take part in a cycle
            under a name no lane contained.
        participants: Every node reference implicated in any finding. Requirement
            33.3 — a refusal must name them rather than report a generic failure,
            because a generic failure sends the author searching eight lanes for the
            one that is wrong.
    """

    paradox: bool
    cycles: list[list[str]] = field(default_factory=list)
    unresolvable: list[tuple[str, str, str]] = field(default_factory=list)
    participants: list[str] = field(default_factory=list)
    unresolvable_waiters: list[tuple[str, str]] = field(default_factory=list)

    def message(self) -> str:
        """A refusal a human can act on."""
        if not self.paradox:
            return "No temporal paradox detected."
        parts: list[str] = []
        for cycle in self.cycles:
            parts.append("unsatisfiable wait cycle: " + " -> ".join([*cycle, cycle[0]]))
        for waiter, target, reason in self.unresolvable:
            parts.append(f"{waiter} waits on {target}, which {reason}")
        for waiter, reason in self.unresolvable_waiters:
            parts.append(f"the waiter {waiter} {reason}")
        return "; ".join(parts)


def detect_temporal_paradox(
    lanes: Mapping[str, Sequence[str]],
    waits: Mapping[str, Sequence[str]],
) -> ParadoxReport:
    """Refuse a configuration whose waits no execution order can satisfy.

    Args:
        lanes: ``{tether_id: [node_id, ...]}`` in **declared execution order** within
            each lane. Order is the whole basis of the same-lane check, so a caller
            passing an unordered collection would get a wrong answer — hence
            ``Sequence`` rather than a set.
        waits: ``{waiter_ref: [target_ref, ...]}`` using tether-qualified references
            (``"NODE@X.2"``), as produced by ``CTRL_WAIT`` configuration and by
            ``Wait_For`` gates that name another lane.

    Returns:
        A :class:`ParadoxReport`. ``paradox`` False means no contradiction was found —
        which is a statement about these two inputs, not a guarantee that the flow
        will succeed.
    """
    known: dict[str, set[str]] = {t: set(nodes) for t, nodes in lanes.items()}

    # ── Reference validity first: an unresolvable target cannot be graphed ────
    #
    # Through `_lane_fault`, which `validate_cross_lane_routes` also calls. This block
    # used to carry its own copy of the parse and its own copy of the three reason
    # strings; the copies are why Requirement 31 found this detector accepting `"@X.1"`
    # while `_qualify` could not produce it.
    unresolvable: list[tuple[str, str, str]] = []
    unresolvable_waiters: list[tuple[str, str]] = []
    for waiter, targets in waits.items():
        # The waiter itself, which went unchecked until 2026-09-05. An unresolvable waiter
        # was still `setdefault`-ed into the precedence graph below, so a typo'd name
        # became a real vertex and could sit in a reported cycle under a name no lane
        # contains — a refusal naming a node the author cannot find.
        waiter_reason = _lane_fault(waiter, known)
        if waiter_reason:
            unresolvable_waiters.append((waiter, waiter_reason))
        for target in targets:
            reason = _lane_fault(target, known)
            if reason:
                unresolvable.append((waiter, target, reason))

    # ── Build the precedence graph: "must happen before" ─────────────────────
    precedence: dict[str, set[str]] = {}

    def _edge(before: str, after: str) -> None:
        precedence.setdefault(before, set()).add(after)
        precedence.setdefault(after, set())

    for tether_id, nodes in lanes.items():
        ordered = list(nodes)
        for node_id in ordered:
            precedence.setdefault(_qualify(node_id, tether_id), set())
        for earlier, later in zip(ordered, ordered[1:]):
            _edge(_qualify(earlier, tether_id), _qualify(later, tether_id))

    resolvable_bad = {(w, t) for w, t, _ in unresolvable}
    bad_waiters = {w for w, _ in unresolvable_waiters}
    for waiter, targets in waits.items():
        if waiter in bad_waiters:
            # An unresolvable waiter is not a vertex. Adding it anyway is what let a
            # typo'd name appear in a reported cycle, which is a refusal naming a node
            # the author cannot go and look at.
            continue
        precedence.setdefault(waiter, set())
        for target in targets:
            if (waiter, target) in resolvable_bad:
                continue  # cannot order against a node that does not exist
            _edge(target, waiter)

    cycles = _find_cycles(precedence)

    participants: list[str] = []
    for cycle in cycles:
        participants.extend(cycle)
    for waiter, target, _reason in unresolvable:
        participants.extend((waiter, target))
    for waiter, _reason in unresolvable_waiters:
        participants.append(waiter)

    # Preserve first-seen order while de-duplicating, so a refusal reads the same way
    # twice. A set here would make the message non-deterministic.
    seen: set[str] = set()
    ordered_participants = [p for p in participants if not (p in seen or seen.add(p))]

    return ParadoxReport(
        paradox=bool(cycles or unresolvable or unresolvable_waiters),
        cycles=cycles,
        unresolvable=unresolvable,
        participants=ordered_participants,
        unresolvable_waiters=unresolvable_waiters,
    )


def _find_cycles(graph: Mapping[str, set[str]]) -> list[list[str]]:
    """Every cycle reachable in *graph*, as ordered node lists.

    Iterative depth-first search with an explicit stack. Recursion would be shorter
    and would blow the stack on a pathological topology, and this runs on
    operator-authored input immediately before launch — the one moment where a
    validator crashing is worse than the defect it was looking for.
    """
    WHITE, GREY, BLACK = 0, 1, 2
    colour: dict[str, int] = dict.fromkeys(graph, WHITE)
    found: list[list[str]] = []
    seen_signatures: set[frozenset[str]] = set()

    for root in graph:
        if colour[root] != WHITE:
            continue
        path: list[str] = []
        stack: list[tuple[str, bool]] = [(root, False)]
        while stack:
            node, processed = stack.pop()
            if processed:
                colour[node] = BLACK
                if path and path[-1] == node:
                    path.pop()
                continue
            if colour[node] == GREY:
                # Back edge — the cycle is the tail of the current path.
                if node in path:
                    cycle = path[path.index(node):]
                    signature = frozenset(cycle)
                    if cycle and signature not in seen_signatures:
                        seen_signatures.add(signature)
                        found.append(cycle)
                continue
            if colour[node] == BLACK:
                continue
            colour[node] = GREY
            path.append(node)
            stack.append((node, True))
            for target in sorted(graph.get(node, ())):
                stack.append((target, False))

    return found


# ── Requirement 29: lanes may terminate without merging ──────────────────────
#
# Added 2026-09-05. Requirement 19.4 made a `CTRL_MERGE` mandatory per scatter branch,
# which forbade the central case of the design it was written to serve: a lane that ends
# on its own. 19.4's instinct was still right — an *unintended* missing merge is a real
# authoring error — so the check survives as enforcement of a **declaration** rather than
# one mandatory shape. `GatherStrategy` is the declaration; these two functions are the
# enforcement.
#
# WHY REACHABILITY NEEDS THE EDGES, AND WHAT HAPPENS WHEN THEY ARE ABSENT
# ----------------------------------------------------------------------
# "Does this lane reach a gather" is a question about paths, not about names. With no
# gather nodes at all the answer is knowable without any edges — nothing can reach a node
# that does not exist. With gather nodes present it is **not** knowable from names alone,
# so `validate_gather_reachability` raises rather than returning a plausible answer. A
# validator that guesses is worse than one that says it cannot tell: this one gates
# launch, and a wrong "reachable" would let exactly the flow 19.4 existed to catch
# through.


@dataclass(frozen=True)
class GatherReachabilityReport:
    """Whether every lane can reach the gather its scatter declared. Requirement 29.3.

    Attributes:
        refused: True when the declared strategy needs a gather and some lane cannot
            reach one.
        unreachable_lanes: Tether IDs of the offending lanes. **Naming them is half the
            requirement** — a generic validation failure sends the author through eight
            lanes looking for the one that is wrong.
        strategy: The declared strategy, normalised.
    """

    refused: bool
    unreachable_lanes: list[str] = field(default_factory=list)
    strategy: str = ""

    def message(self) -> str:
        """A refusal a human can act on. A method, matching the other reports here."""
        if not self.refused:
            return f"Gather strategy {self.strategy!r}: every lane accounted for."
        lanes = ", ".join(self.unreachable_lanes)
        return (
            f"gather strategy {self.strategy!r} requires every lane to reach a gather node, "
            f"but these cannot: {lanes}"
        )


@dataclass(frozen=True)
class TerminalOutputSet:
    """Each lane's own terminal output, recorded separately. Requirement 29.4.

    Attributes:
        pairs: ``(tether_qualified_ref, output_path)`` per lane, in declared lane order.
            **Declared order, never completion order** — the register records what
            ordering by mtime cost: a 59-byte stub chosen over a 426 KB merge, every
            time, because the stub was written last.
        lanes_without_output: Lanes whose terminal node recorded nothing. Reported rather
            than omitted, because a silently shorter list reads as a smaller scatter.
        duplicated_paths: Paths reported by more than one lane. This is defect E1's exact
            signature — eight lanes all naming `unified_session_ledger.md` — so it is
            surfaced rather than de-duplicated into a plausible-looking set.
    """

    pairs: list[tuple[str, str]] = field(default_factory=list)
    lanes_without_output: list[str] = field(default_factory=list)
    duplicated_paths: list[str] = field(default_factory=list)

    @property
    def complete(self) -> bool:
        """True when every lane recorded an output. Not a claim that they are good."""
        return not self.lanes_without_output

    @property
    def distinct(self) -> bool:
        """True when no two lanes named the same artifact."""
        return not self.duplicated_paths

    def message(self) -> str:
        """What this set does and does not account for."""
        parts = [f"{len(self.pairs)} lane output(s) recorded separately"]
        if self.lanes_without_output:
            parts.append("no output from lane(s): " + ", ".join(self.lanes_without_output))
        if self.duplicated_paths:
            parts.append(
                "the same artifact was reported by more than one lane: "
                + ", ".join(self.duplicated_paths)
            )
        return "; ".join(parts)


def _normalise_strategy(gather_strategy: str) -> str:
    """Title-case a declared strategy so ``"merge"`` and ``"Merge"`` mean one thing."""
    return str(gather_strategy or "").strip().title()


def validate_gather_reachability(
    lanes: Mapping[str, Sequence[str]],
    gather_strategy: str,
    gather_nodes: Sequence[str],
    edges: Mapping[str, Sequence[str]] | None = None,
) -> GatherReachabilityReport:
    """Refuse a declared gather that some lane cannot reach. Requirement 29.3.

    Args:
        lanes: ``{tether_id: [node_id, ...]}`` in declared execution order.
        gather_strategy: ``"Merge"``, ``"Concat"`` or ``"Ungathered"``, matching
            ``deterministic_nodes.GatherStrategy``. Compared case-insensitively so a
            hand-authored ``"merge"`` is not read as an unknown strategy.
        gather_nodes: Node IDs of the gather nodes present in the topology.
        edges: ``{node_id: [successor, ...]}`` as produced by :func:`build_edges`.
            Required **only** when *gather_nodes* is non-empty.

    Returns:
        A :class:`GatherReachabilityReport`. ``Ungathered`` is never refused — that is
        the whole point of Requirement 29.

    Raises:
        ValueError: *gather_nodes* is non-empty and *edges* is ``None``. Reachability
            past the first hop is not derivable from names, and this gates launch, so it
            refuses to answer rather than guessing.
    """
    strategy = _normalise_strategy(gather_strategy)

    if strategy == "Ungathered":
        return GatherReachabilityReport(refused=False, strategy=strategy)

    if not lanes:
        return GatherReachabilityReport(refused=False, strategy=strategy)

    targets = [str(n).strip() for n in gather_nodes if str(n).strip()]

    # No gather node exists, so no lane can reach one. Knowable without any edges.
    if not targets:
        return GatherReachabilityReport(
            refused=True, unreachable_lanes=list(lanes), strategy=strategy
        )

    if edges is None:
        raise ValueError(
            f"gather strategy {strategy!r} names {len(targets)} gather node(s), so lane "
            "reachability depends on the routing edges. Pass `edges` (see build_edges); "
            "answering without them would be a guess, and this check gates launch."
        )

    wanted = set(targets)
    unreachable: list[str] = []
    for tether_id, nodes in lanes.items():
        reached: set[str] = set()
        stack = [str(n).strip() for n in nodes if str(n).strip()]
        found = False
        while stack:
            node = stack.pop()
            if node in reached:
                continue
            reached.add(node)
            if node in wanted:
                found = True
                break
            stack.extend(str(t).strip() for t in edges.get(node, ()))
        if not found:
            unreachable.append(tether_id)

    return GatherReachabilityReport(
        refused=bool(unreachable), unreachable_lanes=unreachable, strategy=strategy
    )


def terminal_outputs_for_step(
    lanes: Mapping[str, Sequence[str]],
    recorded_outputs: Mapping[str, str],
    gather_strategy: str,
) -> TerminalOutputSet:
    """Each ungathered lane's own terminal output. Requirement 29.4.

    Args:
        lanes: ``{tether_id: [node_id, ...]}`` in declared execution order. The **last**
            node of each lane is its terminal, which is why an ordered ``Sequence`` is
            required rather than a set.
        recorded_outputs: ``{tether_qualified_ref: output_path}`` as recorded by the
            queue. Refs are matched exactly, through the Requirement 31 render, so a lane
            whose output was filed under a bare node name reads as *no output* rather
            than being matched approximately.
        gather_strategy: Must normalise to ``"Ungathered"``.

    Returns:
        A :class:`TerminalOutputSet`. Lanes that recorded nothing and paths claimed by
        more than one lane are **reported**, never dropped or de-duplicated into
        something that looks complete.

    Raises:
        ValueError: *gather_strategy* is ``Merge`` or ``Concat``. For those the step's
            output is the gather node's output (Requirement 30.3), and returning per-lane
            outputs instead would hand the caller a different answer to the same
            question.
    """
    strategy = _normalise_strategy(gather_strategy)
    if strategy != "Ungathered":
        raise ValueError(
            f"gather strategy {strategy!r} collects its lanes, so the step's output is the "
            "gather node's output (Requirement 30.3), not the per-lane terminals. This "
            "function answers the Ungathered case only."
        )

    pairs: list[tuple[str, str]] = []
    missing: list[str] = []
    seen_paths: dict[str, int] = {}

    for tether_id, nodes in lanes.items():
        ordered = [str(n).strip() for n in nodes if str(n).strip()]
        if not ordered:
            missing.append(tether_id)
            continue
        ref = _qualify(ordered[-1], tether_id)
        path = str(recorded_outputs.get(ref, "") or "").strip()
        if not path:
            missing.append(tether_id)
            continue
        pairs.append((ref, path))
        seen_paths[path] = seen_paths.get(path, 0) + 1

    duplicated = [p for p, count in seen_paths.items() if count > 1]

    if missing:
        logger.error(
            "[TOPOLOGY_GRAPH] Ungathered step: %d of %d lane(s) recorded no terminal "
            "output (%s). Recorded separately as missing rather than omitted.",
            len(missing), len(lanes), ", ".join(missing),
        )
    if duplicated:
        logger.error(
            "[TOPOLOGY_GRAPH] Ungathered step: %d path(s) claimed by more than one lane "
            "(%s). This is defect E1's signature; not de-duplicated.",
            len(duplicated), ", ".join(duplicated),
        )

    return TerminalOutputSet(
        pairs=pairs, lanes_without_output=missing, duplicated_paths=duplicated
    )
