# CTRL_SCATTER Expansion Plan Review: Tools & RAG Oracle Domain Audit

**Author:** Specialist Oracle — Tools & RAG Domain (`maccre_core/tools/`, `tool_registry.py`, `rag_tools.py`, `render_executor.py`, `maccre_mcp.py`)  
**Date:** 2026-07-28  
**Target Documents:**  
- `b:\EXO_GANS\ctrl_scatter-expansion plan-v1.md`  
- `b:\EXO_GANS\ctrl_scatter-expansion plan-v2.md`  
- `b:\EXO_GANS\ctrl_scatter-expansion plan-v3.md`  

---

## 1. Executive Summary

The progression of `CTRL_SCATTER` planning from v1 to v3 represents a major evolution in MACCREv2's dynamic orchestration design. The transition moves from basic node auto-wrapping (v1) to practical UX/concurrency framing (v2) and finally to telemetric lineage tracking with `flow_vector` (v3).

However, from the perspective of **Tools, RAG, and Media Execution**, several critical security, thread-safety, and profile override gaps were identified in v3 that must be addressed prior to Phase 6 parallel execution.

---

## 2. Progression Analysis: v1 → v2 → v3

| Feature / Dimension | Expansion Plan v1 | Expansion Plan v2 | Expansion Plan v3 (FINAL) | Tools & RAG Oracle Evaluation |
|---|---|---|---|---|
| **Scatter Slotting & Auto-Wrap** | Synthesizes `SCATTER → Agents → MERGE` DAG at runtime. | Standardizes UI slotting modal in TUI; handles generic `CTRL_` fallback. | Retains auto-wrap DAG; adds compact collapsed view `[+] CTRL_SCATTER ⟩ N agents ⟩ MERGE`. | **Solid architecture**. Auto-wrap accurately bridges TUI flow steps into executable topologies. |
| **Tool Profile Overrides** | Explicitly includes `"Tools_Allowed"` in topo rows. | Omits detailed dictionary layout snippet. | Omits `"Tools_Allowed"` in v3 plan text snippet (lines 83-89). | **Regression in plan text**. Codebase (`flow_engine.py` L205) handles it, but plan text dropped it. |
| **Concurrency Ceiling** | Unspecified. | `MAX_SCATTER_AGENTS = 5` (assumed free tier API & WAL bottleneck). | `MAX_SCATTER_AGENTS = 8` (hard cap 12, paid Gemini API ~1000 RPM). | **Accurate API assessment**. Paid tier accommodates 8+ parallel calls effortlessly. |
| **Telemetry Lineage** | None. | None. | Introduces `flow_vector` string in `task_queue` (`SCATTER_A>Agent_B>MERGE`). | **Foundational addition**. Enables Phase 6 WAL sharding and Phase 7 Time-Travel RAG Replay. |
| **Parallel Tool Safety** | Not analyzed. | Sequential queue execution noted. | Sequential (Phase 4.75.7) vs Threaded (Phase 6) noted. | **Gaps exist**. Lacks thread safety specs for `_rag_client`, media rendering, and file I/O tools. |

---

## 3. Audit Findings & Omissions in Plan v3

### Finding A: Omission of `Tools_Allowed` in Plan Spec Snippet
- **Observation**: In `ctrl_scatter-expansion plan-v3.md` (lines 83-89), the synthesized agent row snippet reads:
  ```python
  {"Node_ID": "Agent_A", "Agent_Name": "Agent_A", "Next_Node": "CTRL_MERGE", ...}
  ```
  `Tools_Allowed` is missing, whereas `flow_engine.py` line 205 correctly populates `"Tools_Allowed": str(ovr.get("tools_allowed", ""))`.
- **Remediation**: Ensure plan documentation maintains `Tools_Allowed` as a first-class synthesized row attribute to prevent implementation regressions.

### Finding B: Thread-Safety Deficit in `rag_tools.py` Singleton
- **Observation**: `_get_rag_client()` uses global `_rag_client` without a `threading.Lock()`.
- **Impact**: In Phase 6 parallel scatter, multiple threads calling `query_local_memory()` or `ingest_document()` simultaneously will cause race conditions on OS Vault key retrieval and `GeminiClient` creation.
- **Remediation**: Insert `threading.Lock()` guard around lazy initialization in `rag_tools.py`.

### Finding C: RAG Context Isolation & Write Contention
- **Observation**: 
  1. Simultaneous `ingest_document()` calls into the same ChromaDB / SovereignPinStore collection during parallel scatter cause SQLite lock failures.
  2. `query_local_memory()` queries global memory without branch isolation filters.
- **Remediation**: Tag all ingested records with `"flow_vector": flow_vector` in metadata. Filter RAG queries by active `flow_vector` prefix to guarantee context hygiene across parallel agents.

### Finding D: Shared Tool Path Collisions (`write_file`, `render_executor.py`)
- **Observation**: Standard storage and media rendering tools write to fixed relative paths (`02_Dynamic_Context`, `05_Rendered_Media`). Parallel scatter execution will cause filename collisions and corrupted FFmpeg manifests.
- **Remediation**: Mandate node-scoped subdirectories for storage tools (`02_Dynamic_Context/<job_id>/<node_id>/`) and unique job/node stems for media renders (`05_Rendered_Media/<job_id>_<node_id>_<timestamp>`).

---

## 4. Tools & RAG Safety Mandates for Scatter Execution

1. **Default Tool Tiering**: Slotted scatter agents must be constrained to safe tool subsets (`text_tools`, `rag_tools`, `telemetry_tools`). Dangerous administrative tools (`mint_agent`, `build_topology`, `ignite_swarm`, `trash_file`) MUST be blocked unless explicitly declared in `tools_allowed`.
2. **Context Hygiene**: Dynamic context for each scatter node MUST be isolated under `02_Dynamic_Context/<job_id>/<node_id>/`.
3. **Lineage Tagging**: Embed `flow_vector` into all RAG ingestion metadata for auditability and perspective simulation.
4. **Preflight Validation**: Update `preflight_check()` in `flow_engine.py` to validate that all tool names listed in `tools_allowed` exist in `tool_registry.py`.

---

## 5. Verification & Omni QA Directives

- `omni qa maccre_core/tools/tool_registry.py`
- `omni qa maccre_core/tools/rag_tools.py`
- `omni qa maccre_core/orchestration/flow_engine.py`
