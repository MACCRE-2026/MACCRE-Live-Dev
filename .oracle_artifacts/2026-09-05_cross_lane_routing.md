# 2026-09-05: Cross-Lane Routing (Requirement 31)

## Summary

Requirement 31 turns the tether hierarchy from a containment tree into a **routing graph
over a containment tree**: a route target may name a node *and* its lane, an address
naming a lane no execution will occupy is refused before launch and again at runtime, and
routing into a lane does **not** re-parent the node it arrives at.

Six of seven criteria are implemented and covered. **31.6 is implemented as a pure
function and is not wired**, and a red `xfail(strict=True)` marker is what records that.

The larger part of this work was not new capability. Most of Requirement 31 is **Principle
4 applied to a shape the codebase already carried twice**: Requirement 33's
`detect_temporal_paradox` parsed `NODE@TETHER` inline while `_qualify` rendered it from a
separate f-string, and the two had already diverged. The parse accepted three references
the renderer could never produce. Consolidating them is what closed 31.3 and 31.4 and
simultaneously closed two silent holes in 33.

## Files Modified

- `maccre_core/orchestration/topology_graph.py` — new Requirement 31 section inserted
  **before** the Requirement 33 section, because 33 now depends on it. Added
  `TETHER_SEPARATOR`, `FLOW_VECTOR_SEPARATOR`, `TetherRefError`, `TetherQualifiedRef`,
  `RoutedNode`, `CrossLaneRouteReport`, `parse_tether_qualified_ref`, `_lane_fault`,
  `validate_cross_lane_routes`, `apply_cross_lane_route`, `record_crossing`. `_qualify`
  **moved** into that section and now writes the separator from the constant.
  `detect_temporal_paradox`'s reference-validity block reduced from its own inline parse
  plus its own three reason strings to one `_lane_fault` call. `__all__` extended.
- `maccre_core/orchestration/local_broker.py` — added module-level
  `resolve_cross_lane_target`. Import from `topology_graph` widened from
  `is_terminal_target` to also take `TetherQualifiedRef` and `parse_tether_qualified_ref`.
  `Collection` added to the `typing` import.
- `tests/test_topological_semantic_spec.py` — four Req 31 markers removed after XPASS;
  one new red marker added for 31.6; the 31.3 assertion corrected from `report.message`
  to `report.message()`.
- `tests/test_cross_lane_routing.py` — **new. 55 tests, nine groups.**

## Function Signatures Added

```python
# topology_graph.py
TETHER_SEPARATOR: str = "@"
FLOW_VECTOR_SEPARATOR: str = ">"

class TetherRefError(ValueError):
    def __init__(self, ref: str, reason: str) -> None: ...

@dataclass(frozen=True)
class TetherQualifiedRef:
    node_id: str
    tether_id: str
    def render(self) -> str: ...

@dataclass(frozen=True)
class RoutedNode:
    node_id: str
    tether_id: str      # containment — never rewritten by a route
    arrived_from: str
    def render(self) -> str: ...

@dataclass(frozen=True)
class CrossLaneRouteReport:
    refused: bool
    offences: list[tuple[str, str, str]]
    participants: list[str]
    def message(self) -> str: ...          # a METHOD, matching ParadoxReport.message

def parse_tether_qualified_ref(ref: str) -> TetherQualifiedRef: ...
def _lane_fault(ref_text: str, known: Mapping[str, set[str]]) -> str: ...
def validate_cross_lane_routes(
    lanes: Mapping[str, Sequence[str]],
    routes: Sequence[tuple[str, str]],
) -> CrossLaneRouteReport: ...
def apply_cross_lane_route(node_id: str, own_tether: str, from_tether: str) -> RoutedNode: ...
def record_crossing(flow_vector: str, routed: RoutedNode) -> str: ...

# local_broker.py
def resolve_cross_lane_target(ref: str, known_lanes: Collection[str]) -> TetherQualifiedRef: ...
```

## State Contracts

| Object | Owner | Observers | Mutation Rights |
|--------|-------|-----------|-----------------|
| `lanes`, `routes` (mappings/sequences) | caller | `validate_cross_lane_routes` | **none** — read only, copied into a local `dict[str, set[str]]` on entry |
| `known_lanes` | caller | `resolve_cross_lane_target` | **none** — membership tested only |
| `known` (resolved lane index) | `validate_cross_lane_routes` / `detect_temporal_paradox` local | `_lane_fault` | owner only, dies with the call |
| all four dataclasses | the function that returns them | everyone | **frozen** — no mutation possible |

No `threading.Event`, `queue.Queue`, connection or broker handle is taken by any function
added here. `resolve_cross_lane_target` is deliberately module-level rather than a
`LocalMessageBroker` method precisely so it holds no connection: it is a decision about a
string, and giving it `self` would invite it to grow a query.

## Architecture Decisions

### One separator, one parse, one render — and it was already broken

`detect_temporal_paradox` tested `"@" not in target` then `target.partition("@")`.
`_qualify` rendered `f"{node_id}@{tether_id}"`. Three literal separators, two derivations.
The parse accepted, silently:

| Reference | Old inline parse gave | The renderer can produce it? |
|---|---|---|
| `"@X.1"` | `node_id=""`, accepted | never |
| `"A@"` | `tether_id=""`, accepted | never |
| `"A@X.1@Y"` | a lane named `X.1@Y` | never |

`"A@"` is not a hypothetical defect. **Principle 2's named incident is a blanked tether id
putting a scatter and its merge in different scopes**, so the gather gate could never open
and an 8-lane run deadlocked — while an *empty* tether would merely have degraded visibly.
A parser that hands back an empty tether is the mechanism that manufactures that exact
address. `parse_tether_qualified_ref` refuses all three, and
`test_render_then_parse_returns_what_went_in` plus
`test_parse_then_render_returns_the_same_string` are what stop the two derivations
reappearing.

### `_lane_fault` is one resolver behind four criteria

31.3, 31.4 and 33.2's cases 3 and 4 are the same question — "can this reference be
resolved against these lanes" — asked by two callers. They now share one function and
therefore produce **word-for-word identical diagnostics**, asserted directly by
`TestOneResolverBehindFourCriteria`, which compares the reason string from
`validate_cross_lane_routes` against the one from `detect_temporal_paradox` for the same
fault. That is the test that fails if either caller grows a private copy again.

### The `message` convention clash, resolved by evidence rather than preference

The 31.3 marker as authored asserted `report.message` — an attribute. `ParadoxReport.message`
in the same module is a **method**, and three already-passing tests in
`test_prelaunch_validation.py` call `report.message()`.

**The marker was the thing that was wrong, not the shipped code.** Making the new report's
`message` a property to satisfy the marker would have put two spellings of "render the
refusal" in one module — the precise drift `topology_graph` exists to prevent. The
assertion was corrected to `report.message()`; **what it asserts (that the refusal names
`X.9`) is unchanged**, and the reasoning is recorded in the test's own docstring so a
future reader does not have to take a silent edit on trust.

Recorded plainly because editing a red marker to make it pass is a suspicious shape by
default: the edit here is to the *calling convention*, not to the criterion.

### Both ends of a route are validated

A route *from* a node that does not exist is as broken as a route *to* one, so
`validate_cross_lane_routes` checks source and target. The offence names the offending
reference rather than the position, so a report reads the same whichever end is wrong.

### `resolve_cross_lane_target` lives in `local_broker`, not `topology_graph`

31.5 is the runtime half of 31.3/31.4. It belongs where the silent drop would otherwise
happen: `route_task` already skips terminal sentinels without enqueueing anything, and an
unresolvable `GHOST@X.99` taking that same quiet exit would be **indistinguishable from a
lane that simply ended**. Parsing is delegated to `topology_graph` so the broker does not
grow a second reading of the syntax — the same reason this module already imports
`is_terminal_target` rather than re-deriving the sentinel list.

`TetherRefError` (malformed) and `LookupError` (well-formed, absent lane) are kept
distinct because they call for different fixes: a typo in the syntax versus a typo in the
topology.

### `apply_cross_lane_route` refuses an empty containment tether rather than defaulting

The obvious convenience — fall back to `from_tether` when `own_tether` is empty — is
exactly the deadlock above. It raises, and the error text names the incident.
`from_tether == own_tether` also raises, because that is not a crossing and recording one
would be a false lineage entry.

### 31.6 adds no new syntax, and its duplication is marked rather than accepted

`record_crossing` joins tether-qualified entries with `FLOW_VECTOR_SEPARATOR`, so
`A@X.1>B@X.2` states the crossing by itself. When the previous entry is tether-qualified
and its lane contradicts `arrived_from`, it raises; when the previous entry is a bare node
name — **which is what `swarm_worker` writes today** — the crossing cannot be corroborated
and is appended **without any claim that it was**.

`swarm_worker` still builds `flow_vector` from a literal `">"`, so `FLOW_VECTOR_SEPARATOR`
is a second derivation right now. That is a real Principle 4 violation, not a hypothetical,
and rather than let it settle in silently there is a **red `xfail(strict=True)` marker**
asserting the worker composes through the seam. It falls when the wiring lands and the
literal goes away.

### Alternatives rejected

- **Making `CrossLaneRouteReport.message` a property.** Would have satisfied the marker as
  authored and broken the module's one convention. Rejected; the marker was corrected.
- **A second `_qualify`-style parse local to Requirement 31.** The cheap path, and the
  exact defect being fixed.
- **Leaving `detect_temporal_paradox`'s inline parse alone** so Requirement 31 touched
  nothing existing. Rejected: it would have left the module with a strict parser and a
  permissive one, which is worse than the single permissive one it had.
- **Skipping 31.6 entirely** and deferring it to the wiring task. Rejected because it has
  no marker, so its absence would have been recorded nowhere. An unrecorded gap is not a
  gap anybody finds again.
- **Editing `swarm_worker`'s `">"` literal to import the constant** without wiring
  `record_crossing`. Half-wiring an execution path for cosmetic consistency, with no
  baseline run available. Rejected.
- **Parsing the `waits` *keys* in `detect_temporal_paradox`.** They are currently
  unparsed, so a malformed waiter key silently becomes a precedence-graph node. A real
  Principle 2 hole, **out of Requirement 31's scope**, and it belongs with tracker #3
  where `CTRL_WAIT` gets a real `waits` producer. Recorded rather than changed, so that
  work has it in hand.

## Testing

`tests/test_cross_lane_routing.py` — 55 tests:

| Group | Covers |
|---|---|
| `TestTheParseIsTheInverseOfTheRender` | round trip both directions, separator asserted against the **constant** not a literal, whitespace |
| `TestTheParseRefusesRatherThanDegrades` | bare name, empty, empty node, empty lane, double separator, `ValueError` subclassing, bare-predicate `reason` |
| `TestValidateCrossLaneRoutes` | clean case **first**, 31.3, 31.4, broken source end, both ends, participants dedupe/determinism |
| `TestTheRefusalMessage` | route + reference named, clean case says so, every offence present |
| `TestOneResolverBehindFourCriteria` | the two callers produce identical reasons; the two holes 33 no longer has |
| `TestResolveCrossLaneTarget` | resolves, `LookupError`, error names available lanes, empty lane set, malformed → parse error, `Collection` tolerance |
| `TestApplyCrossLaneRoute` | 31.7, origin recorded, **same containment from two different origins**, empty-tether refusal, same-lane refusal |
| `TestRecordCrossing` | empty vector, crossing readable, contradiction raises, bare/unparseable history tolerated, only last entry checked |

### Gate observed 2026-09-05

| Step | Result |
|---|---|
| `omni clean` | 14:49 — 294 bytecode files, 1 `.pytest_cache`, 1 `.ruff_cache` |
| `omni qa` | **PASS, whole project** 14:50–14:50:56 |
| `pytest tests` | **1152 collected / 1144 passed / 8 xfailed / 0 failed** — 179.03 s |
| `omni smoke` | **ALL CHECKS PASSED** — inference 0.9 s, $0.00 |

Reconciles exactly against the previous gate (1096 / 1085 / 11 xfailed):
`1096 + 55 new tests + 1 new marker = 1152`; `1085 + 55 + 4 markers turned pass = 1144`;
xfailed `11 - 4 + 1 = 8`.

`omni smoke` was run because `local_broker.py` is on the execution path — its import
statement changed, even though the new function has no caller.

The 8 remaining red markers: Req 34.1 (1), Req 31.6 (1), Req 29.3/29.4 (2), Req 32 (4).

## Limits of this work

- **Nothing calls any of it.** `validate_cross_lane_routes` is not invoked by pre-flight,
  `resolve_cross_lane_target` is not invoked by `route_task`, and `record_crossing` is not
  invoked by `swarm_worker`. Six criteria are *implemented and covered*, not *in force*.
  No operator currently sees a cross-lane refusal.
- **31.3/31.4's intended home is validation point 7, which already exists.** The
  pre-flight pipeline in `Analysis/Wave2/flowchart_02_orchestration_engine.md` already has
  *"7. Dynamic Route Targets Exist?"*. Wiring extends that check; it does not add an
  eighth. Adding a parallel mechanism would be the same defect this requirement fixed.
- **No cross-lane route has ever executed.** There is no authoring surface for one yet, so
  every assertion here is about pure functions over hand-built inputs. The requirement is
  satisfied as *mechanism*, and the live behaviour is unobserved.
- **31.6's separator duplication is live right now**, not deferred cleanly. The red marker
  is the mitigation, not a fix.
- **A process correction, recorded because I stated the wrong cause earlier.** The suite
  stall I previously attributed to `omni clean` racing a pytest run **reproduced with no
  clean anywhere near it** (clean 14:49:36, qa 14:50:56, pytest 14:51:00, stalled at
  14:51:34 and spun for 16.5 min at 541 s CPU with zero test progress). What both
  incidents share is a **foreground pytest run whose tool call was interrupted**; the same
  suite with output redirected to a file completed in 179 s. I also wrongly localised it to
  `test_demand_overprovisioning.py` from its scratch directories — that module passes 8/8
  in 3.6 s alone, and the directories were merely the last `tmp_path` dirs *created*, not
  the running test. **The pipe mechanism is a hypothesis, not a finding**; what is verified
  is the suite's health, that module's innocence, and that both stalls followed an
  interrupted run. Practice changed to `Start-Process` with file redirection and polling.
