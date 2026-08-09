# Phase 4.75.7 Roadmap Audit & Domain Evaluation: Tools & RAG Oracle

**Author:** Specialist Oracle — Tools & RAG Domain (`maccre_core/tools/`, `tool_registry.py`, `rag_tools.py`, `render_executor.py`, `sheet_parser.py`, `maccre_mcp.py`)  
**Date:** 2026-07-28  
**Target Codebase Files:**  
- `b:\EXO_GANS\maccre_core\tools\rag_tools.py`  
- `b:\EXO_GANS\maccre_core\orchestration\flow_engine.py`  
- `b:\EXO_GANS\maccre_core\orchestration\key_ingestor.py`  
- `b:\EXO_GANS\Era2_architectural_roadmap.md`  

---

## 1. Executive Summary

Phase 4.75.7 implementation has been audited from the perspective of the **Tools & RAG Domain** (61-tool registry dispatcher, hybrid search engine, document loaders, dual-pipeline media render executor, and FinOps gates).

Key Audit Outcomes:
1. **Phase 4.75.7 Status:** **95% Complete**. `_get_rag_client()` in `rag_tools.py` is safely guarded with `threading.Lock()`, KnowledgeStore integration is standard across all vector tools, and `flow_vector` lineage telemetry groundwork is planted in `local_broker.py` and `swarm_worker.py`. However, a minor bug in `flow_engine.py` (line 422) overwrites topology row `Tools_Allowed` definitions with an empty string when `agent_tools_overrides` lacks an explicit entry.
2. **Historical Roadmap (Phases 1–4.75.6) Audit:** All core grounding, FTS5 BM25 search, RRF Brave web fusion, and tool dispatch items are complete, **with one critical gap**: Phase 3.1 specified `pypdf` and `python-docx` document loaders. These are **not implemented** in `rag_tools.py` (which still relies on plain text/markdown extensions). Furthermore, the roadmap text misattributed this loader requirement to `key_ingestor.py` (which is the API key DPAPI vault fingerprinting layer).
3. **Deferred Items Mapping (Phases 5, 6, 7):** All tool, media, FinOps, and RAG deferrals across Phase 5 (Visionary Scout visual extraction, FinOps Onion TUI burn approval modal, Image-to-Video temporal extrapolation), Phase 6 (ThreadPool parallel tool safety, WAL sharding by `flow_vector`), and Phase 7 (Time-Travel Replay and Counterfactual RAG Simulation) are cleanly and accurately mapped.

---

## 2. Phase 4.75.7 Codebase Audit

### 2.1 `maccre_core/tools/rag_tools.py`
- **Thread-Safety (`_get_rag_client`)**:
  - `_rag_lock = threading.Lock()` is instantiated at module scope (line 43).
  - `_get_rag_client()` correctly wraps lazy instantiation inside `with _rag_lock:` (line 50), preventing race conditions when parallel tasks or multi-threaded subagents request Gemini embedding clients concurrently.
- **Knowledge Store Integration**:
  - All RAG routines (`ingest_document`, `query_local_memory`, `fts_search_memory`, `iterative_scoped_search`, `ingest_global_archive`, `query_global_archive`, `query_foreign_memory`, `import_foreign_vectors`, `vectorize_ledger`, `canonize_session`, `prune_semantic_memory`, `ingest_project`) route through `get_knowledge_store(...)`.
  - Storage backend seamlessly abstracts `SovereignPinStore` (SQLite-backed) or ChromaDB legacy based on `MACCRE_MEMORY_BACKEND`.
- **SHA-256 Manifest Ingestion**:
  - `ingest_project()` compares file hashes against `02_Dynamic_Context/ingest_manifest.json`, eliminating redundant embedding API calls for unchanged documents.

### 2.2 `maccre_core/orchestration/flow_engine.py`
- **Single Agent & `CTRL_SCATTER` Auto-Wrapping**:
  - Single-node auto-wrapping populates `"Tools_Allowed": tools` from roster profile (line 154).
  - `CTRL_SCATTER` auto-wrapping populates `"Tools_Allowed": str(ovr.get("tools_allowed", ""))` for slotted agents (line 207).
- **Deficit in `_hydrate_topology` (Line 422)**:
  - **Issue**: Line 422 executes `tools_allowed = agent_tools_overrides.get(agent_name, "")`. If `agent_tools_overrides` does not contain `agent_name`, `tools_allowed` evaluates to `""`, ignoring any `Tools_Allowed` preset in `row_dict`.
  - **Impact**: Default tool assignments configured in macro node CSV topologies or preset agent profiles get discarded during topology hydration.
  - **Remediation**:
    ```python
    # flow_engine.py line 422
    tools_allowed = agent_tools_overrides.get(agent_name, str(row_dict.get("Tools_Allowed", "")))
    ```

---

## 3. Historical Roadmap Item Audit (Phases 1 to 4.75.6)

| Phase & Feature | Target Subsystem | Implementation Status | Findings & Notes |
|---|---|---|---|
| **Phase 1.1: FlowStasis Memory Pins** | `rag_tools.py` | **Complete** | `canonize_session()` and `extract_from_canonized_ledger()` vectorize session pins into project canon. |
| **Phase 2.1: Session Canonization** | `rag_tools.py` | **Complete** | Session memories promoted from L1 ephemeral DBs to L2 `agent_thoughts.db` & `agent_ledgers.db`. |
| **Phase 3.1: Hybrid RAG Search** | `rag_tools.py`, `hybrid_search.py` | **Complete** | Vector + SQLite FTS5 BM25 + Brave Web Search RRF fusion fully implemented and exposed in 61-tool registry. |
| **Phase 3.1: Document Loaders (`pypdf`, `python-docx`)** | `rag_tools.py` / `key_ingestor.py` | **UNMET (Gap)** | Missing binary parsers for PDF/DOCX files in `rag_tools.py`. `key_ingestor.py` is key fingerprinting, not document loading. |
| **Phase 4.75.3: Tool Assignments UI Checkmarks** | TUI / `flow_engine.py` | **Complete** | Tool assignments write to session `.dict` buffer and hydrate into execution topology. |
| **Phase 4.75.4: Quadrivector Failback Routing** | `deterministic_nodes.py` | **Complete** | Dual-pass structured output failback chain implemented for `CTRL_CONDITIONAL_ROUTE`. |

---

## 4. Evaluation of Deferred Roadmap Items (Phases 5, 6, 7)

### Phase 5: Multimodal Ingestion & High-Cost Authorizations
- **§5.1 The Visionary Scout (Visual Extraction)**: Mapped to process visual media in `01_Raw_Source`, extracting spatial bounding boxes and storing metadata in SQLite with hard URI pointers to source media. Cleanly deferred.
- **§5.2 FinOps Onion (TUI High-Cost Authorization Modal)**: Mapped to pause execution via `ManualInputRequired` before media renders or temporal extrapolation, calculating estimated USD burn for approval. Cleanly deferred.
- **§5.3 Generative Temporal Extrapolation**: Mapped to Imagen 3 / Image-to-Video models to generate 2-second pre/post live photo clips from static images. Cleanly deferred.

### Phase 6: Concurrency & Advanced Primitives
- **§6.3 Remaining CTRL_ Primitives**: `CTRL_WEBHOOK`, `CTRL_EDGE_SYNC`, `CTRL_CHAT`. Cleanly deferred.
- **§6.12 Parallel Execution Threading**: Mapped for `ThreadPoolExecutor` in `swarm_worker.py`. `_rag_lock` added in Phase 4.75.7 satisfies RAG client thread-safety; media render output paths in `render_executor.py` must be node-scoped (`05_Rendered_Media/<job_id>_<node_id>`) prior to Phase 6.
- **§6.13 WAL Sharding by Flow Line**: Uses `flow_vector` lineage column planted in Phase 4.75.7 as partition key. Cleanly deferred.

### Phase 7: Telemetric Memory Simulation
- **§7.1 Time-Travel Replay, §7.2 Agent Perspective Simulation, §7.3 Counterfactual Simulation**: All three sub-systems directly leverage the `flow_vector` telemetry string (`SCATTER_A>Agent_B>MERGE`) planted in Phase 4.75.7 to reconstruct node execution timelines and isolate agent trajectories. Cleanly deferred.

---

## 5. Summary Recommendation & Action Items

1. **Fix `flow_engine.py` Line 422**: Modify `_hydrate_topology` to fallback to `str(row_dict.get("Tools_Allowed", ""))` when `agent_tools_overrides` does not specify a key.
2. **Close Phase 3.1 Document Loader Gap**: Create `maccre_core/tools/doc_loaders.py` with `pypdf` and `python-docx` fallback readers, update `TEXT_EXTS` in `rag_tools.py`, and update `Era2_architectural_roadmap.md` §3.1 to clarify that document loading belongs in `rag_tools.py`/`doc_loaders.py` rather than `key_ingestor.py`.
3. **Pre-Phase 6 Path Isolation**: Update `render_executor.py` output paths to mandate job/node isolation (`05_Rendered_Media/<job_id>_<node_id>_<timestamp>`) to prevent file collisions during parallel scatter execution.
