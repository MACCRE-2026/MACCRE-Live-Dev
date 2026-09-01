# MERGED — see `FeatureRequests.md`

**Merged:** 2026-08-31

This document's contents were consolidated into
[`FeatureRequests.md`](./FeatureRequests.md), which is now the single formal
register of user feature requests and verified-but-unscheduled defects.

A tracking copy lives at `.kiro_artifacts/FeatureRequests.md`.

## Where the three original items went

All three are now entries in `FeatureRequests.md` under the
**CONSOLIDATION — 2026-08-31** section, reformatted to that document's Entry
Doctrine and carrying a `**Verified:**` line that states whether the item was
reproduced in code or is still user-reported:

| Original item | Entry in `FeatureRequests.md` |
|---|---|
| 1. "Name MacroNode" modal has no Save/Cancel and explains nothing | *Session Manager — "Name MacroNode" modal is a dead end* |
| 2. "Name Session" input does not accept entry | *Session Manager — "Name Session" input does not accept entry* |
| 3. Session Manager alignment / Sovereign Importer readiness | *Session Manager / File Cabinet alignment for Sovereign Importer* |

Items 1 and 2 remain **user-reported and unreproduced**. Their stated causes are
leads to check, not findings — a distinction worth keeping, since three
consecutive engine defects during Phase 6.13 had plausible first hypotheses that
turned out to be wrong.

## Related entries added during consolidation

These were recorded at the same time because they bear directly on the Sovereign
Importer / File Cabinet contract:

- **A timed-out step does not stop the flow** — a session can report `completed`
  when a step timed out, so `completed` is not proof that every step ran. Any
  importer enumerating by status is affected.
- **Omniscience — spatial system interface for omni** — depends on the same stable
  datacenter read API this integration work is meant to define, and should not
  precede it.
- **Node-ID convention divergence between TUI and engine** — the TUI builds node
  ids with `_{i}` while the engine hydrates with `_S{i}`. Harmless while the TUI
  only draws; not harmless once anything acts on the rendered graph.

This file is retained as a redirect so existing references do not dangle. Add new
entries to `FeatureRequests.md`, not here.
