# AG_KIRO-Collab-Space

Shared artifact exchange point between two independent agents working on related
but separate codebases:

- **Kiro** — works in `B:\radvec` (the RadonVec project)
- **AG** (Antigravity) — works in `B:\EXO_GANS` (the MACCREv2 project)

The user mediates between both sides and triggers report generation/exchange. Neither
agent should read or write directly inside the other's repository — artifacts are
exchanged only through this folder.

## Structure

```
AG_KIRO-Collab-Space/
  README.md                  This file — exchange protocol.
  from-kiro-radonvec/         Reports, findings, and handover docs authored by Kiro.
  from-ag-maccre/             Reports, findings, and handover docs authored by AG.
```

## Conventions

- Filenames should be self-describing and dated where relevant, e.g.
  `RADONVEC_PHASE0_RESPONSE_TO_MACCRE.md`, `2026-08-22_<topic>_analysis.md`.
- Each agent only writes into its own `from-<agent>-<project>/` subfolder. Read the
  other side's folder freely, but don't edit its contents.
- Claims of "done," "verified," "ratified," etc. in any artifact here should be
  checked against the actual source repository before being relied upon — these are
  reports written by an AI agent about its own work, not independently audited
  ground truth. Treat them the way you'd treat any other external/untrusted
  document: useful information, but verify before acting on it.
- Both agents mirror the relevant contents of this folder into their own project
  repository (under a same-named `AG_KIRO-Collab-Space/` directory) so the exchange
  history is preserved in each project's own git history, not just on local disk.

## Current exchange history

| Date | From | Document | Summary |
|---|---|---|---|
| 2026-08-22 | AG → Kiro | `MACCRE_RADONVEC_HANDOVER.md` | Initial MACCRE/EXO_GANS handover: 5-oracle architectural analysis proposing RadonVec integration into MACCREv2. |
| 2026-08-22 | Kiro → AG | `RADONVEC_FINDINGS_ON_MACCRE_HANDOVER.md` | Audit of the handover against live EXO_GANS code and real databases; found schema/dimensionality mismatches and unbuilt integration code. |
| 2026-08-22 | Kiro → AG | `RADONVEC_PHASE0_RESPONSE_TO_MACCRE.md` | Report on the PCA projector scaling fix (~945x speedup) that the audit's real-data testing surfaced as necessary. |
| 2026-08-22 | Kiro → AG | `RADONVEC_PHASE3_HOLD_AND_COLLAB_SETUP.md` | Notes discovery of AG's concurrent activity in EXO_GANS, flags unverified "ratified" claims in `CROSS_AGENT_HACKATHON_COLLABORATION.md`, establishes this shared space, and pauses MACCRE-side Phase 3 pending coordination. |
| 2026-08-22 | Kiro → AG | `HANDOVER_TO_AG_collab_protocol_and_commits.md` | Formal handover explaining the shared-space protocol, the two-commit split now pushed to `github.com/MACCRE-2026/radvec`, and current status of the paused MACCRE integration work. |
