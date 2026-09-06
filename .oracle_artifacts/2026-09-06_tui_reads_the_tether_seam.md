# 2026-09-06: The TUI Stops Minting Its Own Tether IDs (task 4d)

## Summary

`macronode_workshop` generated `tether_a`, `tether_b`, ... from a private counter. It now
calls `tether.root_tether_id`, the same generator the engine reads. **This closes the tether
unification**: there is one source of tether IDs, and the three-way divergence recorded in
`.kiro_artifacts/2026-09-05_tether_model_divergence_and_task_revision.md` is resolved.

The change also removes a real defect, not just an inconsistency. `chr(96 + n)` walks off
the end of the alphabet: the 27th scatter in one authoring session produced `tether_{`, and
the **28th produced `tether_|`** — a tether containing a routing-target delimiter that
`topology_graph.parse_targets` splits, so `Wait_For` would read one lane as two.

## Files Modified

- `maccre_tui/widgets/macronode_workshop.py` — the `CTRL_SCATTER` branch of
  `_handle_node_add` calls `root_tether_id(self._tether_counter)` and increments after.
  Imports `root_tether_id` from `maccre_core.orchestration.tether`.
- `tests/test_workshop_tether_ids.py` — **new. 16 tests, four groups.**

## State Contracts

| Object | Owner | Observers | Mutation Rights |
|--------|-------|-----------|-----------------|
| `_tether_counter` | `MacroNodeWorkshop` | none | owner only; reset by `reset_flow_dict` |
| `_pending_scatters` | `MacroNodeWorkshop` | none | owner only — LIFO, pushed by scatter, popped by merge/concat/branch |

No new shared state. `root_tether_id` is pure, so the counter remains the widget's only
state and the generator holds none of its own.

## Architecture Decisions

### The counter becomes an index into the seam, not a private encoding

`self._tether_counter` survives — the widget still needs to know how many scatters it has
issued — but it is now an **index passed to** `root_tether_id` rather than an input to a
private `chr()` expression. The increment moved to *after* the call so index 0 maps to `X`,
which is what Requirement 18.4 names as the root tether.

That keeps the diff to two lines and means the TUI has no opinion about what a tether looks
like, which is the whole point.

### The alphabet overflow was a real defect, and it is now a named regression test

Measured rather than assumed:

| Scatter # | Old value | Problem |
|---|---|---|
| 27 | `tether_{` | outside the alphabet, no longer readable as a sequence |
| **28** | **`tether_\|`** | **contains a routing-target delimiter** — `parse_targets` accepts `,` and `\|`, so `Wait_For` splits one lane into two names |
| 29, 30 | `tether_}`, `tether_~` | as 27 |

`test_the_twenty_eighth_scatter_no_longer_contains_a_routing_delimiter` asserts
`chr(96 + 28) == "|"` *and* that `"|"` is in `FORBIDDEN_IN_TETHER_ID`, so the guard states
the hazard it exists for rather than just checking a value. Revert-to-red confirmed
`test_every_generated_tether_is_wellformed` fails under the old scheme — direct evidence
that it produced a tether `validate_tether_id` rejects, within 30 scatters.

This is remote in practice — 28 scatters in one unsaved session — but it is the exact defect
class `FORBIDDEN_IN_TETHER_ID` was derived to prevent, reached by a route nobody was
watching.

### Scatter↔merge pairing was left alone, and that is correct

The `_pending_scatters` LIFO already assigns the merge **the same tether as its scatter**,
which is precisely what 4c-3 requires: the merge sits on the *group* tether and the lanes
beneath it. Nothing needed to change, and `TestScatterMergePairingStillHolds` pins it —
including LIFO ordering across two scatters, and that a merge with no pending scatter stays
**untethered** rather than inventing a scope.

### Authoring-time validation of the operator's Tether ID box was deliberately not added

`nexus_plex`'s `#cfg-tether-id` `Input` still stores whatever is typed, unvalidated. 4c-3
already handles a bad value truthfully at launch: `child_tether_ids` refuses it, the
auto-wrap substitutes the generated tether and logs at ERROR naming the value and the reason.

Validating in the modal would move that feedback earlier, which is a genuine UX improvement
— and it belongs with the TUI wiring task, not here. Adding it now would mean a second
place deciding what a valid tether is, on the day the point of the change is that there is
one. Recorded as a deliberate non-goal with its reason, not an oversight.

### Alternatives rejected

- **Removing TUI tether generation entirely** and letting the engine's
  `_default_tether_id` supply everything. Rejected: the workshop needs a handle *at
  authoring time* to pair a scatter with its companion merge via `_pending_scatters`. With
  no tether there is nothing to pair on, and the pairing is a real feature.
- **Having the TUI call `_default_tether_id`** (the engine's digest over the agent set).
  Rejected: at the moment a `CTRL_SCATTER` node is added the agent slots are empty
  (`"scatter_targets": []`), so the digest would be over nothing and every scatter would
  collide. The auto-wrap can use it because by then the agents are known; the workshop
  cannot.
- **Keeping `tether_` as a prefix** for readability. Rejected: it is a second naming
  convention, and `X`/`Y`/`Z` is what Requirement 18.4 and the design document name.

## Testing

`tests/test_workshop_tether_ids.py` — 16 tests driving the **real** `_handle_node_add` on a
real `MacroNodeWorkshop`.

**What is stubbed and why:** only `post_message` and `_emit_dict_update`, both because they
need a running Textual app. `_sync_visualizer` is left alone — it already swallows the
`query_one` failure. The tether assignment, the `_pending_scatters` pairing and the
`FlowDictBuffer` write are all production code. Stated in the module docstring so a reader
knows the boundary.

| Group | Covers |
|---|---|
| `TestTheWorkshopUsesTheSeamsGenerator` | first scatter is `X`; the sequence asserted **against `root_tether_id`, never literals**; the old prefix is gone; the tether lands in **both** places the engine reads; 30 tethers all well-formed; the counter resets with the flow |
| `TestTheAlphabetOverflowIsGone` | **the 28th scatter and the `\|` delimiter**; 30 distinct tethers |
| `TestScatterMergePairingStillHolds` | merge pairs to its scatter; **LIFO across two scatters**; concat pairs; an unpaired merge stays untethered; the operator is told the tether |
| `TestATuiTetherWorksAsAnEngineGroupTether` | the engine derives lanes from a workshop tether; those lanes gather at the paired merge; two workshop scatters do not share a scope |

That last group is the assertion that would have caught the original divergence: it fails
if the TUI's value cannot serve as a group tether the engine derives lanes from.

### Revert-to-red, performed

Restoring `f"tether_{chr(96 + self._tether_counter)}"` failed **6 tests**, including
`test_every_generated_tether_is_wellformed` and the 28th-scatter guard. **All 10 pairing and
cross-component tests stayed green**, which is right — pairing is independent of the
generator, so the probe reddened exactly the assertions about *which* generator runs.

### Gate observed 2026-09-06

| Step | Result |
|---|---|
| `omni clean` | 12:25 — 303 bytecode files |
| `omni qa` | **PASS, whole project** 12:27:05 |
| `pytest tests` | **1420 collected / 1417 passed / 3 xfailed / 0 failed** — 206.41 s |
| `omni smoke` | **ALL CHECKS PASSED** — inference 1.4 s, $0.00 |

Reconciles exactly against 1404 / 1401 / 3: `1404 + 16 = 1420`; `1401 + 16 = 1417`;
xfailed unchanged at 3 (Req 34.1, Req 31.6, the 4e lane-count marker).

**`omni smoke` does not exercise this change** and is not claimed to. Smoke runs the engine
with no TUI, so it confirms the new `maccre_tui → maccre_core.orchestration.tether` import
did not break the engine, nothing more. It was run because it is free and because the import
is new, not because it covers the change.

**`omni qa` does not type-check this file.** `pyrightconfig.json` excludes `maccre_tui`
entirely, so the only static check this code received is Ruff. The 16 tests are therefore
the whole of its verification, which is why they drive the real method rather than asserting
on source text.

## Limits of this work

- **No TUI was launched.** The tests call `_handle_node_add` directly with two hooks
  stubbed. Nobody has added a `CTRL_SCATTER` in a running workshop and seen `X` appear on
  the node, and the tether badge in `topology_visualizer` renders whatever it is given —
  unverified against a real screen.
- **The operator's Tether ID box is still unvalidated at authoring time** (see above). The
  engine substitutes and logs, so a bad value is handled, but the operator learns at launch
  rather than while typing.
- **`_default_tether_id` and `root_tether_id` both still exist**, and that is intended, not
  a remaining duplication: they answer different questions. `_default_tether_id` names a
  scatter *by its agent set* so the same scatter gets the same tether on every call —
  needed because the auto-wrap runs twice per step. `root_tether_id` names the *n*-th lane
  group an author has created. The engine uses the first when the operator supplied nothing;
  the workshop uses the second because at node-add time there are no agents to hash.
- **Nothing verifies that a TUI-authored tether survives to `task_queue`.** The chain is
  workshop → `cfg["tether_id"]` → auto-wrap group tether → hydration → queue row, and only
  its two ends are covered. The full path needs a live run.
- **The `_pending_scatters` LIFO is unchanged and still only pairs one companion.** A
  scatter whose merge is added much later, or two scatters closed out of order, pair by
  recency rather than by structure. Pre-existing, out of scope, and recorded in
  `ctrl_node_analysis` already.
