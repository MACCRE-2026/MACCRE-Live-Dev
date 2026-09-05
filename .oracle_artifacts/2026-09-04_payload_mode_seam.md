# 2026-09-04: The Payload Mode Seam — and two defects found by building it

**Plan task:** Era 3 tracker #9, **first of two parts**
**Oracle domain:** OrchestrationAndEngine

## Summary

Task #9 is "the payload contract as one design", which the register defines as three
things: **(a)** `Payload_Mode` honoured at a step boundary, **(b)** `Preceding Node Only`
actually implemented, **(c)** the HITL injection accompanying the payload rather than
replacing it.

This artifact covers **the foundation and (b)**. It deliberately stops short of (a) and
(c), which are one semantic decision that changes what every existing multi-step flow
passes — and that decision is the operator's, not mine. What is built here is needed
under every possible answer to it.

Two real defects were found while mapping the contract, and both are fixed here.

## Files Modified

- `maccre_core/orchestration/payload_modes.py` — **new.** `PayloadMode`,
  `DEFAULT_PAYLOAD_MODE`, `AUTHORABLE_MODES`, `resolve_payload_mode`.
- `maccre_core/orchestration/swarm_worker.py` — both behavioural reads now resolve
  through the seam; `PRECEDING_NODE_ONLY` is an explicit branch.
- `maccre_core/orchestration/topology_engine.py` — the normalisation seam resolves.
- `maccre_core/orchestration/flow_engine.py` — four literal defaults replaced.
- `maccre_core/orchestration/macro_factory.py` — the `Targeted Filter` template value.
- `maccre_core/tools/admin_tools.py` — the `_DEFAULTS` padding entry.
- `maccre_tui/nexus_plex.py` — modal default, `Select` options, and the HITL resume fix.
- `tests/test_payload_modes.py` — new, 35 tests.

## The map that made this tractable

Established before changing anything, because the literals appeared in seven files and
the important fact turned out to be how few of them mattered:

| | Count | Where |
|---|---|---|
| **Behavioural reads** | **2** | `swarm_worker` only |
| Writes (defaults, UI options, serialisation, templates, padding) | ~25 | the other six files |

- `swarm_worker` ~L1023 — reads the **completing** node's mode, tests only for
  `Targeted Filter`, and rewrites what **that node itself** reads.
- `swarm_worker` ~L1874 — reads the **successor's** mode, tests only for
  `Unified Ledger`, and rewrites what the **next node** reads.

Two modes on one field with **opposite subjects**. That asymmetry is now documented on
the enum members, because it is the single most confusing thing about this contract and
nothing stated it anywhere.

## Function Signatures Added

```python
class PayloadMode(Enum):
    UNIFIED_LEDGER      = "Unified Ledger"
    PRECEDING_NODE_ONLY = "Preceding Node Only"
    TARGETED_FILTER     = "Targeted Filter"

DEFAULT_PAYLOAD_MODE = PayloadMode.UNIFIED_LEDGER
AUTHORABLE_MODES: tuple[PayloadMode, ...] = (UNIFIED_LEDGER, PRECEDING_NODE_ONLY)

def resolve_payload_mode(value: object, *, context: str = "") -> PayloadMode
```

## State Contracts

Nothing here holds shared mutable state. `payload_modes.py` imports **only the standard
library** — deliberately, because `topology_engine` is the seam every read passes through
and `flow_engine` imports `topology_engine`, so hosting the enum in `flow_engine` would
have made the seam import its own consumer.

## Architecture Decisions

### A typo used to select a different contract — this is the one behaviour change

Both reads were `==` against a literal. A topology carrying `"Unifed Ledger"` did not
fail, did not warn, and **routed as `Preceding Node Only`**, because the override tested
equality and the else-branch was the whole of the other mode. A single transposed letter
silently changed which document the next agent read.

`resolve_payload_mode` now matches case-insensitively against the three known values and
falls back to the default **with a warning naming the node**. So that topology now routes
as `Unified Ledger` — differently than before, and as authored.

Recorded as a behaviour change rather than filed as a cleanup, because it is one.

### The resolver warns; `resolve_gather_strategy` raises. Both are right

A deliberate asymmetry between two functions written a day apart:

- `resolve_gather_strategy` **raises** on an unrecognised value, because defaulting to
  `Merge` would gather lanes the author explicitly asked to leave alone — the wrong
  behaviour is indistinguishable from the right one until someone reads the output.
- `resolve_payload_mode` **warns and defaults**, because it runs on the worker's hot path
  for every node, and defaulting lands on the mode the author almost certainly meant.

The rule that produces both: raise when the default could silently do the opposite of
what was asked; warn when it lands on the likely intent.

### `Preceding Node Only` is now an explicit branch that changes nothing

It was offered in the UI and read by **no conditional anywhere**. It worked by falling
through: when the mode was not `Unified Ledger` the override did not fire, leaving the
payload at the completing node's own artifact — which for an intra-step hop *is*
preceding-node-only. Accidentally correct, which is the dangerous kind, because any
change to the default routing path would have silently redefined the mode. **Defect E1
was exactly that: a change to the default path with unexamined consequences for a mode
nobody had written down.**

The new branch logs and does nothing else. `test_the_branch_does_not_change_the_routing_payload`
asserts there is no assignment in its body — a behaviour change wearing a
clarification's clothes is precisely what must not happen here. What it buys is that the
mode can now be **conditioned on**, which the operator's stated `CTRL_REVIEW` design
requires and a fall-through cannot provide.

### The config modal could be handed a value its options excluded

`Targeted Filter` is written onto consensus advocate rows by `macro_factory` and is
**not** offered by the config modal's `Select`. Opening the modal on such a node supplied
a `value` absent from the option list — decided at construction, inside a `compose`,
where a raise is an app-killing traceback rather than a message. That is **defect F1's
class exactly**: a widget-construction fault in a render nobody was watching.

Options are now built from `AUTHORABLE_MODES`, and a non-authorable current value is
appended labelled `(not authorable)`. Two modes remain offerable; three remain
renderable.

### Source-level assertions, and why they earn their place here

`TestTheLiteralsAreGone` reads source text and parametrises over the seven files. Usually
weak; correct here, because the defect being prevented is *a fourth spelling appearing in
an eighth file*, which is a property of the source rather than of any behaviour — and
because the reads were equality tests, a drifted literal was **undetectable at runtime**.
The same reasoning already governs `test_controlnode_registry_counts.py`.

`test_every_migrated_file_reads_through_the_seam` guards the other direction: a file with
neither a literal nor an import would be a file that lost the concept. `undo_manager` is
on the list as the deliberate exception — it never named a mode and carries whatever the
modal produced.

## The second defect: the HITL resume never passed its topology

`LocalMessageBroker.resume_paused_task` takes a `topology_engine` so a paused **pause
node** can be completed and routed to its configured successor. Omitted, it falls back to
`"END"`.

`_hitl_resume_with_context` — **the only production caller** — omitted it. So every HITL
resume from the TUI closed the lane at the pause node and silently dropped whatever the
operator had authored after it.

The parameter's own docstring warns about this failure in detail. That makes it the
`--smart` shape from the doctrine: a documented mechanism with no caller supplying it,
and no test that fails when the claim goes false.

**Verified rather than assumed that a plain `TopologyEngine` is sufficient here.** The
concern was that a control node's successor is config-driven via `merge_config_overlay`,
which does not touch `topology.csv` — so a fresh CSV-reading engine might resolve the
wrong successor. Reading `_get_macronode`'s control-node auto-wrap settled it:
`next_node = str(cfg.get("next_node", "END"))` is written **into the topology row**, and
`_hydrate_topology` writes that row to the CSV with the step suffix. The overlay carries
the *other* config fields — scatter targets, gate predicates, `auto_resume_after` — not
the successor. So the CSV is authoritative for this lookup, and no overlay is needed.

This is a behaviour change and a defect fix, not a semantic choice: the intended
behaviour is documented on the parameter and the fallback is what was wrong.

## Testing

`tests/test_payload_modes.py` — **35 tests**: the three modes and the default's
justification; the authorable/renderable split; resolution (enum passthrough, each value,
absent/blank/whitespace, case-insensitivity, non-string input, the warning, the warning
naming the node); the typo behaviour change driven **functionally through a real
`TopologyEngine`** over a four-row CSV (valid / typo / blank / wrong-case); the explicit
`Preceding Node Only` branch including the no-assignment guard; the literals-are-gone
parametrisation; the modal `Select`; and the HITL resume.

### Revert-to-red proof

`topology_engine`'s resolve call was reverted to the old literal expression. **Three
tests reddened** — `assert 'X' == 'Unified Ledger'` for the typo and blank cases, and
`assert 'unified ledger' == 'Unified Ledger'` for the casing case. Probe removed and
confirmed absent by grep before re-running green.

### Gate run 2026-09-04

| Gate | Result |
|------|--------|
| `omni clean` | 21:57 — nothing to terminate; 286 bytecode files purged. |
| `omni qa` | **PASS** — whole project, 21:58. |
| `pytest tests -q` | **938 passed, 10 xfailed, 0 failed** in 209.52s — 948 collected. |
| `omni smoke` | **ALL CHECKS PASSED** — inference 0.9s, $0.00. |

Collected 913 → 948: +35 tests, exactly. The 903 → 938 pass count moved by the same 35,
so **nothing that was passing changed behaviour under test** — which is the claim the
migration most needed to support.

## Limits, and what is deliberately not done

- **(a) and (c) are not built.** Whether a step boundary honours `Payload_Mode`, and what
  the HITL injection accompanies, are one decision that changes what every existing
  multi-step flow passes and costs. The register records arguments both ways and a
  recommended middle option. Presented to the operator rather than chosen here.
- **No live run.** The two behaviour changes — typo resolution and the HITL successor —
  are covered by tests and unproven in production. The HITL one in particular is TUI
  wiring, and TUI wiring is outside the Pyright include list; `test_the_tui_supplies_it`
  is a source assertion, not an execution.
- **A fan-out consults only lane 0's payload mode.** `next_node.split(",")[0]` — found
  while mapping, real, and **not fixed here** because the right answer depends on (a).
  Raised as its own register entry.
- **`payload_mode` is per-node in the CSV but per-step in the flow model.**
  `_hydrate_topology` stamps one `FlowStep.payload_mode` onto every row of the macro, so
  a TUI-authored step cannot vary mode between its own nodes; only `macro_factory` rows
  can. Recorded, not changed — it bears directly on (a).
