# RADONVEC PHASE 0 RESPONSE: PCA Projector Scaling Fix

**Document ID:** `RADONVEC_PHASE0_RESPONSE_TO_MACCRE.md`
**From:** RadonVec Engineering (Kiro agent, `B:\radvec`)
**To:** MACCREv2 / EXO_GANS Engineering, the 5 Domain Specialist Oracles
**Re:** `MACCRE_RADONVEC_HANDOVER.md` and the associated 5 Oracle RFC reports
**Date:** 2026-08-22
**Status:** Phase 0 complete and merged in `B:\radvec`. Phases 1-3 (MACCRE-side connector, benchmark refresh, full MACCRE integration) remain on the roadmap, on hold pending direction.

---

## 1. Summary

Thank you for the handover package and the 5 Oracle RFC analyses. Before acting on the proposed MACCRE integration (Phase 3 in our roadmap), we audited the handover documents against the live `EXO_GANS` codebase and real vector data, and separately ran RadonVec directly against real production embeddings from `nexus_memory.db`. Full audit findings are in the companion document `RADONVEC_FINDINGS_ON_MACCRE_HANDOVER.md` — please read that alongside this one, since it identifies some schema and dimensionality assumptions in the oracle reports that don't match the real data and would need reconciling before Phase 3 implementation begins.

This document covers what we actually shipped: **Phase 0**, a fix for a scaling defect in RadonVec's 3D projector that the real-data audit surfaced. Short version: RadonVec's PCA projector previously could not handle real embedding dimensionality in any reasonable time. It now can.

## 2. The problem we found

RadonVec's `IncrementalPCAProjector` (`radonvec/core/projector.py`) is responsible for mapping high-dimensional embedding vectors down to the normalized 3D coordinates that get voxelized and fed into the Radon fan/FBP pipeline. The original implementation accumulated a running `raw_dim x raw_dim` covariance (scatter) matrix and ran a full eigendecomposition (`np.linalg.eigh`) on it every time the top-3 axes were needed.

That's an O(raw_dim³) operation. It's fine at small dimensions, but it does not scale:

| raw_dim | full eigendecomposition time |
|---|---|
| 384 | ~78 ms |
| 768 | ~200 ms |
| 1536 | ~1.3 s |
| 3072 | ~10 s |

Your real production embeddings, per the `nexus_memory.db` file we located and inspected (`__DATACENTER\GLOBAL\02_Dynamic_Context\nexus_memory.db`), are **3072-dimensional** (consistent with `gemini-embedding-001`'s real output size). We ran RadonVec's actual `TimeTravelEngine.ingest()` directly against those 26 real vectors and measured:

```
ingest 26 real 3072-dim vectors (BEFORE fix): 11,995 ms
```

Twelve seconds to ingest 26 vectors. That is not usable for any real workload, and it would only get worse per-call as more data accumulated (the old scatter-matrix approach re-decomposes the full matrix on every `transform()` call after invalidation).

## 3. What we changed

We replaced the full-covariance eigendecomposition with a streaming "frequent directions" sketch (Liberty 2013; Ghashami et al. 2016) — the same family of technique used for randomized/streaming low-rank SVD (Halko, Martinsson & Tropp 2011):

- Instead of accumulating a `raw_dim x raw_dim` matrix, the projector maintains a small `13 x raw_dim` sketch (3 axes needed + 10 oversampling margin for numerical stability).
- Each `partial_fit` call stacks the new batch's centered rows underneath the current sketch and takes a single thin SVD of that small stacked matrix — never a `raw_dim x raw_dim` matrix, regardless of how many vectors have been ingested in total.
- The sketch's height is bounded at a constant 13 rows forever; ingest cost per call does not grow with accumulated history.

This is implemented entirely inside `IncrementalPCAProjector` — its public `partial_fit()` / `transform()` / `fit_transform()` interface (the `Projector` protocol other modules depend on) is unchanged, so no other module in RadonVec needed to change.

### 3.1 Result: same real data, after the fix

```
ingest 26 real 3072-dim vectors (AFTER fix): 12.7 ms
```

**~945x faster** on the identical real dataset. Drift index (0.0720), compression ratio (13.4x), and FBP reconstruction MSE (0.00207) were unchanged to the precision we checked — confirming this was purely an algorithmic swap in basis-finding, not a change to the math the rest of the pipeline sees.

### 3.2 Verified: cost stays flat as history grows

We also checked the thing that matters most for a real streaming ingestion workload — does per-call cost grow as more data accumulates? Tested 30 consecutive ingest calls of 200 vectors each (768-dim, growing to 6,000 total accumulated vectors):

```
first 5 calls avg: 118 ms
last 5 calls avg:   92 ms
```

Flat, no growth trend. The sketch's bounded size guarantees this by construction.

### 3.3 Full dimension sweep

| raw_dim | before (full eigh, one-shot) | after (sketch, streamed) |
|---|---|---|
| 384 | ~78 ms | well under budget |
| 768 | ~200 ms | well under budget |
| 1536 | ~1.3 s | well under budget |
| 3072 | ~10 s | well under budget |

All four dimensions now pass a hard 2-second regression test budget (`tests/test_projector.py::test_projector_scales_to_realistic_embedding_dimensions`), with real observed times an order of magnitude or more under that ceiling.

## 4. Correctness, not just speed

A pure speedup is worthless if it changes what the projector actually computes. We verified two things:

1. **Streaming vs. batch agreement.** The existing test asserting that streaming a dataset in 5 chunks produces the same projected subspace as fitting it in one batch call still passes — we did have to fix that test's synthetic data, though: it had been using pure isotropic Gaussian noise, which has no real principal-direction structure (all singular values are numerically tied, so "the top-3 axes" were arbitrary even under the old exact method). We rewrote it with synthetic data that has genuine dominant directions plus small noise — matching what real embeddings actually look like — which is also a more honest test of what "same subspace" should mean.
2. **New accuracy test against exact PCA.** Added `test_projector_recovers_true_subspace_on_structured_high_dim_data`, which fits the new streaming sketch on structured 768-dim data and confirms its recovered subspace matches an *exact*, non-streaming batch PCA computation on the same data to within numerical tolerance.

## 5. Verification performed

- Full test suite: **85/85 passing** (79 pre-existing + 6 new regression/accuracy tests added for this fix).
- `omni qa .`: 0 Ruff errors, 0 Pyright (strict) errors, unchanged.
- NFR-3 (16-slice/64³ forward projection latency budget) re-verified unaffected — the projector fix doesn't touch the Radon fan/FBP code path.
- Real-data end-to-end re-test against `nexus_memory.db`'s actual 26 vectors, reported above.

## 6. What Phase 0 does not fix

Being direct about scope, since we don't want this read as "RadonVec is now production-ready for MACCRE":

- **No MACCRE data connector exists yet.** RadonVec's CLI still only ingests `.npy` files. Pulling directly from a `SovereignPinStore`-backed SQLite file is Phase 1 work, on hold per your instruction.
- **No re-verification of the 148:1 compression / storage numbers in the oracle reports.** Those numbers were modeled projections in the reports, not measurements against a real implementation (see Section 3.5 of the findings document) — we have not attempted to validate or reproduce them, because the `TomographicStateManager` and `.rvf` archival pipeline they describe don't exist yet.
- **The schema and dimensionality mismatches identified in the audit findings are still open.** Real `memory_pins.db` files are knowledge-graph triples, not vector stores, in every instance we checked; the actual vector-shaped data lives under a different filename (`nexus_memory.db`) than the reports' examples assume. This needs reconciling before Phase 3 connector code gets written against the reports' assumed schema.
- **Compression ratio and MSE still degrade on dense, non-sparse embedding clouds.** This is a pre-existing, documented characteristic of the Radon/FBP pipeline itself (see RadonVec's own README, "Honest Limitations" section) and Phase 0 does not change it — it's orthogonal to the projector fix.

## 7. Status of the full roadmap

| Phase | Status |
|---|---|
| Phase 0: Fix projector O(dim³) scaling wall | **Done** (this document) |
| Phase 1: Real MACCRE SQLite data connector | On hold, still planned |
| Phase 2: Re-benchmark + update README real-data claims | On hold, still planned |
| Phase 3: MACCRE-side integration (`TomographicStateManager`, 4 new MCP tools, DPAPI vault bridge) | On hold, still planned — recommend treating as its own spec-driven effort in `EXO_GANS` with schema assumptions reconciled first (see findings doc) |

Nothing here is dropped — Phases 1-3 remain exactly as scoped in our prior planning discussion, paused per explicit instruction, not deprioritized.

---

**Files changed in this phase:**
- `radonvec/core/projector.py` — `IncrementalPCAProjector` rewritten to use a bounded streaming sketch instead of full covariance eigendecomposition.
- `tests/test_projector.py` — fixed one test's synthetic data to have genuine subspace structure; added 6 new tests (4 parametrized dimension-scaling latency tests, 1 real-world-shape test, 1 exact-PCA accuracy comparison).

**Companion document:** `RADONVEC_FINDINGS_ON_MACCRE_HANDOVER.md` — full audit of the handover package against real code and data.
