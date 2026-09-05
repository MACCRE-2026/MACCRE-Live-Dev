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
    "TERMINAL_SENTINELS",
    "build_edges",
    "describe",
    "entry_nodes",
    "is_terminal_target",
    "node_ids",
    "parse_targets",
    "terminal_nodes",
    "unreachable_nodes",
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
        participants: Every node reference implicated in any finding. Requirement
            33.3 — a refusal must name them rather than report a generic failure,
            because a generic failure sends the author searching eight lanes for the
            one that is wrong.
    """

    paradox: bool
    cycles: list[list[str]] = field(default_factory=list)
    unresolvable: list[tuple[str, str, str]] = field(default_factory=list)
    participants: list[str] = field(default_factory=list)

    def message(self) -> str:
        """A refusal a human can act on."""
        if not self.paradox:
            return "No temporal paradox detected."
        parts: list[str] = []
        for cycle in self.cycles:
            parts.append("unsatisfiable wait cycle: " + " -> ".join([*cycle, cycle[0]]))
        for waiter, target, reason in self.unresolvable:
            parts.append(f"{waiter} waits on {target}, which {reason}")
        return "; ".join(parts)


def _qualify(node_id: str, tether_id: str) -> str:
    """Render a tether-qualified reference the way Requirement 31.2 states it."""
    return f"{node_id}@{tether_id}"


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
    unresolvable: list[tuple[str, str, str]] = []
    for waiter, targets in waits.items():
        for target in targets:
            if "@" not in target:
                unresolvable.append(
                    (waiter, target, "is not tether-qualified (expected NODE@TETHER)")
                )
                continue
            node_id, _, tether_id = target.partition("@")
            if tether_id not in known:
                unresolvable.append(
                    (waiter, target, f"names lane {tether_id!r}, which the topology never spawns")
                )
            elif node_id not in known[tether_id]:
                unresolvable.append(
                    (waiter, target, f"names a node absent from lane {tether_id!r}")
                )

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
    for waiter, targets in waits.items():
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

    # Preserve first-seen order while de-duplicating, so a refusal reads the same way
    # twice. A set here would make the message non-deterministic.
    seen: set[str] = set()
    ordered_participants = [p for p in participants if not (p in seen or seen.add(p))]

    return ParadoxReport(
        paradox=bool(cycles or unresolvable),
        cycles=cycles,
        unresolvable=unresolvable,
        participants=ordered_participants,
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
