# FINDINGS: Audit of the MACCRE/EXO_GANS RadonVec Handover Artifacts

**Document ID:** `RADONVEC_FINDINGS_ON_MACCRE_HANDOVER.md`
**Author:** RadonVec Engineering (Kiro agent, `B:\radvec`)
**Subject:** Verification of `MACCRE_RADONVEC_HANDOVER.md` and the 5 Oracle RFC reports against the live `B:\EXO_GANS` codebase and real vector data
**Date:** 2026-08-22
**Status:** Findings final. No RadonVec code changes were made as a result of this audit alone; see the companion `RADONVEC_PHASE0_RESPONSE_TO_MACCRE.md` for what Phase 0 actually implemented.

---

## 1. Purpose

Before acting on `B:\radvec\MACCRE_RADONVEC_HANDOVER.md` (and the 5 Oracle RFC reports it references in `B:\EXO_GANS\.oracle_artifacts\`), we cross-checked their claims against the actual `B:\EXO_GANS` codebase and the actual SQLite databases under `__DATACENTER\`. This document records what was verified, what didn't match, and what's genuinely useful to carry forward.

This is a factual audit, not a criticism of the underlying architectural thinking. Several of the ideas in the reports (3-tier access control, `.rvf` binary framing, treating `system_logs.db` as a 3D telemetry volume) are good directions. The issue is that the handover package presents itself as a completed, ratified engineering deliverable ("OFFICIALLY ENDORSED & RATIFIED BY ALL 5 ORACLES," "RFC APPROVED & ARCHITECTURALLY COMMITTED") when it is, in fact, an architecture proposal with no corresponding implementation.

## 2. Method

1. Read `MACCRE_RADONVEC_HANDOVER.md` and the two most implementation-detailed oracle reports (`StateAndSovereignty_Oracle`, `ToolsAndRAG_Oracle`) in full.
2. Searched `B:\EXO_GANS\maccre_core\**\*.py` for any trace of the proposed RadonVec integration surface.
3. Opened the actual SQLite files the reports cite by path and compared their real schemas against the schemas quoted in the reports.
4. Located and inspected the only genuinely populated vector data found anywhere under `__DATACENTER\`, to establish real embedding dimensionality and vector count.
5. Spot-checked one code sample from the reports (`get_datacenter_path()` usage) against the real function signature.

## 3. Findings

### 3.1 None of the proposed RadonVec integration code exists in `maccre_core`

```
grep -r "radon|tomographic|Radon|Tomographic" B:\EXO_GANS\maccre_core\**\*.py
  →  0 matches
```

Specifically absent, despite being specified in full with type signatures in the oracle reports:
- `TomographicStateManager` (`maccre_core/orchestration/tomographic_state_manager.py`)
- `tomographic_memory_audit()`, `rebalance_vector_space()`, `radon_time_travel_slice()` (`maccre_core/tools/rag_tools.py`)
- `render_tomographic_timelapse()` (`maccre_core/tools/render_executor.py`)
- Any of the 4 new tool registrations in `tool_registry.py` / `maccre_mcp.py`

**Conclusion:** the handover describes planned work, not completed work. The "Status: ACTIVE & DISPATCHED" / "RFC APPROVED" language in the source documents should be read as "proposal accepted for future implementation," not "implemented and merged."

### 3.2 Schema mismatches between the reports and the real databases

The `StateAndSovereignty_Oracle` report quotes this schema for `thought_pins.db`:

```sql
CREATE TABLE pins (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    doc_id TEXT NOT NULL,
    collection TEXT NOT NULL,
    text TEXT NOT NULL DEFAULT '',
    vector_blob BLOB,
    ...
);
```

This part is accurate — it matches `maccre_core/memory/sovereign_store.py`'s real DDL. However, the report also treats `memory_pins.db` as having the *same* `pins`/`vector_blob` schema ("Schema: Identical to `thought_pins.db`"). We opened a real `memory_pins.db` and found a completely different table:

```sql
-- actual schema of B:\EXO_GANS\__DATACENTER\499_TEST\02_Dynamic_Context\memory_pins.db
CREATE TABLE memory_pins (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id TEXT NOT NULL,
    ledger_path TEXT NOT NULL,
    subject TEXT,
    predicate TEXT,
    object TEXT,
    significance TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

This is a knowledge-graph triple store (subject/predicate/object), not a vector store, and it has no `vector_blob` column at all in every instance we checked. Any code written against the report's assumed schema would fail immediately against real `memory_pins.db` files.

The genuinely vector-shaped `pins`/`vector_blob` table does exist, but under different filenames than the report implies for populated data — e.g. `nexus_memory.db`, `session_live_session_agent_ledgers.db` — not consistently at `memory_pins.db` or `thought_pins.db` (both of which were empty, zero-row tables in every instance we checked).

### 3.3 Real embedding dimensionality does not match the report

The `ToolsAndRAG_Oracle` report's math section states: "High-D Embeddings (256-D Gemini / 768-D Local)."

The only populated real vector data we could find anywhere under `__DATACENTER\` is in `GLOBAL\02_Dynamic_Context\nexus_memory.db`: **26 vectors, each 3072-dimensional**, unit-norm, with real (non-zero, non-synthetic-looking) float content — consistent with `gemini-embedding-001`'s actual default output size, not 256.

This matters directly for engineering decisions: 3072 dimensions is 4x larger than the 768 the reports plan around, and (before Phase 0's fix) fell squarely inside RadonVec's O(dim³) projector wall — see Section 4.

### 3.4 Sample code doesn't match the real function signature it calls

`StateAndSovereignty_Oracle`'s `TomographicStateManager` code sample calls:

```python
get_datacenter_path("02_Dynamic_Context", "radonvec_frames")
```

The real signature in `maccre_core/utils/path_resolver.py`:

```python
def get_datacenter_path(*subpaths: str) -> Path:
    project_name = os.environ.get("MACCRE_ACTIVE_PROJECT", "GLOBAL") or "GLOBAL"
    p = get_maccre_root() / "__DATACENTER" / project_name
    if subpaths:
        p = p.joinpath(*subpaths)
    return p
```

This actually works fine as written (the function does accept `*subpaths`), so this specific call would run — but the report's narrative around it ("Dynamically injects the active $projectName layer") undersells that project selection happens via an environment variable read at call time, which the sample code never sets or documents. Anyone copying the sample as-is would silently write frames into whatever `MACCRE_ACTIVE_PROJECT` happens to be set to (or `GLOBAL` by default), not necessarily the project they intended.

### 3.5 Benchmark numbers are modeled projections, not measurements

The 148:1 compression ratio, 6.48 MB/day, 194.40 MB/30-days, and 14.2ms scrub latency figures all appear in the reports' own tables under headers like "Storage Optimization Model" and are derived from an assumed "1 snapshot/min, 40MB/checkpoint" scenario — a hypothetical, not a measurement against a running system. This is stated nowhere as an assumption; it reads as a benchmark result. We did not attempt to validate these numbers because there is no corresponding implementation to measure yet.

### 3.6 What's genuinely good to carry forward

Setting the unbuilt-code issue aside, several ideas in the reports are worth keeping for a real Phase 3 integration:
- The 3-tier access model (read-only / PIN-elevated / MCP-bypass token) is a reasonable shape for gating a future `reinflate`/rollback operation that writes back into live state.
- Routing frame deletion through `trash_file()` instead of `os.remove()`/`Path.unlink()` is a good practice RadonVec's own CLI doesn't currently follow (its `reinflate --output` just calls `np.save` — not destructive today, but worth adopting if a rollback/delete path is ever added).
- The `.rvf` binary wire format idea (magic bytes + fixed header + CRC32) is a better direction than RadonVec's current ad-hoc `struct.pack("<ddH", ...)` header scheme in `radonvec/engine.py`.
- Treating `system_logs.db` execution telemetry (token ratio / latency / cost per node) as a 3D point cloud for swarm bottleneck visualization is a genuinely different, interesting application of the same math — distinct from vector search.

## 4. Why this matters for RadonVec specifically

Before this audit, we had already identified (via synthetic benchmarks) that `IncrementalPCAProjector`'s full covariance eigendecomposition scales as O(raw_dim³) and becomes unusable above a few hundred dimensions. This audit's discovery that MACCRE's real production embeddings are 3072-dimensional — not 256 or 768 as the reports assumed — confirmed that the real-world impact was worse than our synthetic tests suggested. We tested RadonVec directly against the actual 26-vector `nexus_memory.db` file and measured **11,995ms** to ingest 26 real vectors, before any fix.

Phase 0 (documented separately) addresses exactly this. See `RADONVEC_PHASE0_RESPONSE_TO_MACCRE.md`.

## 5. Recommendation

Treat `MACCRE_RADONVEC_HANDOVER.md` and the 5 oracle reports as an architecture proposal and roadmap, which is genuinely useful as that. Before any of the Phase 3 MACCRE-side integration work (the `TomographicStateManager`, the 4 new MCP tools, the DPAPI vault bridge) begins, the schema assumptions in Section 3.2 and the dimensionality assumption in Section 3.3 need to be reconciled against the real, current `sovereign_store.py` schema and real embedding sizes — otherwise the integration code will be built against data shapes that don't exist.
