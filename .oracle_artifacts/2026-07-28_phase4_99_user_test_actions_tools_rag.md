# Phase 4.99 User Test Actions & Verification Suite: Tools & RAG Subsystem

**Author:** Specialist Oracle — Tools & RAG Domain (`maccre_core/tools/`, `tool_registry.py`, `rag_tools.py`, `render_executor.py`, `sheet_parser.py`, `workbook_engine.py`, `maccre_mcp.py`)  
**Date:** 2026-07-28  
**Target Version:** MACCREv2 / EXO_GANS Release Candidate Phase 4.99  
**Domain Scope:** 61-Tool Master Dispatcher, Multi-Tiered Hybrid RAG (Vector + SQLite FTS5 BM25 + Brave Web RRF Fusion), Dual-Pipeline Media Render Executor (TTS / Imagen 3 / FFmpeg), Excel Workbook Intake Materializer, FastMCP Server, and Concurrency/Context Hygiene under `CTRL_SCATTER`.

---

## 1. Executive Summary & Verification Mandate

This artifact defines the canonical **Phase 4.99 User Test Actions** for the **Tools & RAG Domain**. Designed under the **Sovereign Edge Omni-Builder Doctrine**, these test actions simulate extreme operational stress, concurrent execution race conditions, multi-grounding search fusion, tool profile confinement violations, media rendering stem collisions, and FastMCP stdio buffer limits.

Each test action provides exact step-by-step operator instructions, specifies the target codebase components, details the high-stress edge conditions, and defines unambiguous system validation criteria.

---

## 2. Comprehensive Phase 4.99 User Test Actions Suite

### Test Action 1: Restricted Tool Profile Confinement & Tier-Based Override Validation
- **Target Codebase Component:** `maccre_core/tools/tool_registry.py` (`TOOL_DISPATCHER`, `get_tools_for_tier`), `maccre_core/orchestration/flow_engine.py` (`_hydrate_topology`), `maccre_core/tools/telemetry_tools.py`.
- **Step-by-Step Operator Action:**
  1. Define a topology where `Agent_Analyst` is restricted via `Tools_Allowed` to `["query_local_memory", "fts_search_memory"]` and `Agent_Render` is granted `["execute_render_pipeline", "read_local_codebase"]`.
  2. Execute a workflow where `Agent_Analyst` attempts to invoke an unauthorized system command tool (e.g., `execute_command` or `initialize_workspace`).
  3. Validate that `Agent_Render` can concurrently execute its authorized `read_local_codebase` tool.
- **Edge-Case / Stress Condition:** Restricted tool profile execution under topology hydration fallback (`Tools_Allowed` override resolution from CSV preset vs. agent roster profile vs. runtime override) and execution boundary enforcement.
- **Expected System Behavior & Validation Criteria:**
  - `TOOL_DISPATCHER` intercepts `Agent_Analyst`'s illegal tool invocation and raises a `PermissionError` / RBAC rejection payload without crashing the execution loop.
  - Telemetry matrix (`agent_thoughts.db`) logs a `TOOL_DENIED` event recording `Agent_Analyst`, the forbidden tool name, and the active `Tools_Allowed` manifest.
  - Authorized tools for `Agent_Render` execute successfully without side effects.

---

### Test Action 2: Multi-Grounding Hybrid RAG Search (Vector + SQLite FTS5 BM25 + Brave Web RRF Fusion)
- **Target Codebase Component:** `maccre_core/tools/rag_tools.py` (`iterative_scoped_search`, `query_local_memory`, `fts_search_memory`), `maccre_core/tools/hybrid_search.py`, `maccre_core/tools/web_search_tools.py`.
- **Step-by-Step Operator Action:**
  1. Ingest a specialized technical document into L2 project memory (`02_Dynamic_Context`).
  2. Issue a complex query via `iterative_scoped_search` that requires synthesized knowledge across local vector embeddings, SQLite FTS5 full-text keyword indexing, and live external web search via Brave Search API.
  3. Simulate a network drop / rate limit on the Brave Search API during execution.
- **Edge-Case / Stress Condition:** Multi-grounding search under high-query concurrency with mixed data sources (empty vector match falling back to FTS5 BM25, API web search rate limit / missing API key failing back gracefully to local hybrid RRF ranking).
- **Expected System Behavior & Validation Criteria:**
  - Reciprocal Rank Fusion (RRF) algorithm cleanly merges candidate rank lists from vector search and FTS5 BM25 search.
  - When Brave API fails or times out, the search engine logs a `WEB_SEARCH_FAILBACK` telemetry warning and seamlessly falls back to pure local hybrid RRF ranking without throwing `UnboundLocalError` or breaking result matrices.
  - Returns deduplicated document chunks with precise cosine similarity and BM25 scores.

---

### Test Action 3: Concurrent Multi-Threaded RAG Client Access & Vault Key Lock
- **Target Codebase Component:** `maccre_core/tools/rag_tools.py` (`_get_rag_client`, `_rag_lock`), `maccre_core/security/windows_vault.py`, `maccre_core/orchestration/key_ingestor.py`.
- **Step-by-Step Operator Action:**
  1. Trigger 16 parallel subagent threads executing `query_local_memory` and `vectorize_ledger` across different document sets simultaneously on a cold boot (uninitialized `_rag_client`).
  2. Monitor thread synchronization during the initial DPAPI/Fernet vault API key decryption and Gemini client instantiation.
- **Edge-Case / Stress Condition:** Thread lock contention on `_rag_client` lazy initialization during cold-boot key retrieval; verifying RAM key zeroing (`ctypes.memset`) after client acquisition.
- **Expected System Behavior & Validation Criteria:**
  - `_rag_lock` (`threading.Lock()`) in `rag_tools.py` ensures exactly **one** Gemini client singleton instance is created across all 16 threads without race conditions or `NoneType` errors.
  - All 16 vectorization tasks complete concurrently without SQLite WAL database lock errors.
  - Decrypted API key buffers in memory are zeroed out via `ctypes.memset` post-initialization.

---

### Test Action 4: Scatter-Gather Context Isolation & Lineage-Tagged Memory Ingestion (`CTRL_SCATTER`)
- **Target Codebase Component:** `maccre_core/tools/rag_tools.py` (`ingest_document`, `query_local_memory`), `maccre_core/orchestration/local_broker.py`, `maccre_core/orchestration/swarm_worker.py`.
- **Step-by-Step Operator Action:**
  1. Initiate a `CTRL_SCATTER` execution fan-out across 4 worker agents (`Worker_A`, `Worker_B`, `Worker_C`, `Worker_D`), each producing conflicting hypothesis documents tagged with their respective `flow_vector` lineage string (`SCATTER_0>Worker_A`, etc.).
  2. Perform a RAG query from `Worker_B` requesting context, explicitly specifying `flow_vector="SCATTER_0>Worker_B"`.
  3. Perform an aggregate query during the `CTRL_MERGE` phase without lineage filtering.
- **Edge-Case / Stress Condition:** Dynamic context isolation under scatter execution where multiple nodes write to `agent_thoughts.db` and SQLite WAL simultaneously; filtering RAG vector search by `flow_vector` lineage metadata.
- **Expected System Behavior & Validation Criteria:**
  - SQLite WAL handles concurrent writes from all 4 worker threads without locking errors.
  - `Worker_B` receives **only** contextual memories generated along its specific execution branch (`SCATTER_0>Worker_B`), eliminating cross-node context pollution during scatter.
  - The `CTRL_MERGE` node successfully accesses all 4 worker outputs when querying without lineage filters.

---

### Test Action 5: Dual-Pipeline Media Render Executor Stem Isolation & Failure Handling
- **Target Codebase Component:** `maccre_core/tools/render_executor.py` (`execute_render_pipeline`, `render_podcast_audio`, `render_video`), `maccre_core/utils/path_resolver.py`.
- **Step-by-Step Operator Action:**
  1. Execute two simultaneous multi-node rendering requests with identical output filename parameters across two separate agent sessions (Session X and Session Y).
  2. Simulate a missing FFmpeg system binary during the video filter graph assembly step.
- **Edge-Case / Stress Condition:** Media rendering output stem path collision under parallel execution; missing FFmpeg binary handling during complex video filter graph execution; absolute path compliance using `get_maccre_root() / "05_Rendered_Media"`.
- **Expected System Behavior & Validation Criteria:**
  - Output files are rendered into strictly isolated stems: `05_Rendered_Media/<job_id>_<node_id>_<timestamp>/`. No files are overwritten or truncated by concurrent jobs.
  - When FFmpeg is missing or fails, `render_executor.py` catches the process error, completes TTS audio rendering, and outputs a clear diagnostic fallback report in `04_Code_Artifacts/media_render_fallback.json` without crashing the agent pipeline.

---

### Test Action 6: Session Canonization, Memory Pruning & FlowStasis Pin Store Promotion
- **Target Codebase Component:** `maccre_core/tools/rag_tools.py` (`canonize_session`, `prune_semantic_memory`, `extract_from_canonized_ledger`).
- **Step-by-Step Operator Action:**
  1. Run a 50-turn interactive session generating extensive ephemeral L1 scratchpad thoughts and key decisions marked with FlowStasis integrity tags.
  2. Invoke `canonize_session()` to promote session memories to L2 project canon (`agent_thoughts.db`).
  3. Execute `prune_semantic_memory(similarity_threshold=0.92)` to clean up duplicate entries.
- **Edge-Case / Stress Condition:** Promotion of L1 ephemeral session memories into L2 project canon while deduplicating semantically redundant embedding vectors (>0.92 cosine similarity) without purging FlowStasis-tagged critical memory pins.
- **Expected System Behavior & Validation Criteria:**
  - `canonize_session()` successfully vectorizes and writes session history into `agent_thoughts.db` with source pointers.
  - `prune_semantic_memory()` removes redundant scratchpad vectors exceeding 0.92 similarity score while explicitly preserving all FlowStasis-pinned memories.
  - Subsequent RAG queries return clean, non-redundant context.

---

### Test Action 7: High-Fidelity Excel Workbook Intake & Swarm Materialization
- **Target Codebase Component:** `maccre_core/tools/sheet_parser.py`, `maccre_core/tools/workbook_engine.py`, `maccre_core/tools/admin_tools.py` (`initialize_workspace`).
- **Step-by-Step Operator Action:**
  1. Provide a malformed `MACCRE_Swarm_Request.xlsx` workbook missing optional sheet columns, containing non-standard tool names, and specifying extreme token cost budgets.
  2. Execute `check_workbook_completeness` followed by `materialise_from_sheet`.
- **Edge-Case / Stress Condition:** Materialization of multi-agent swarm workspace under incomplete sheet data; openpyxl vendoring fallback (`maccre_core._vendor`); pre-flight completeness scoring (`check_workbook_completeness`).
- **Expected System Behavior & Validation Criteria:**
  - `check_workbook_completeness` accurately calculates a readiness score (e.g., 78%) and highlights missing required vs optional parameters in a structured report.
  - `materialise_from_sheet` populates missing optional fields with canonical defaults, flags invalid tool names, and instantiates the 5-tier datacenter folder structure (`01_Raw_Source` through `05_Rendered_Media`) anchored strictly via `get_maccre_root()`.

---

### Test Action 8: FastMCP Stdio Server Tool Interface & Micro-Test Automation Harness
- **Target Codebase Component:** `maccre_core/tools/maccre_mcp.py`, `scripts/maccre_micro_test.py`, `maccre_core/tools/tool_registry.py`.
- **Step-by-Step Operator Action:**
  1. Launch the automated micro-test harness (`omni run scripts/maccre_micro_test.py`) to execute all 61 atomic tools exposed via the FastMCP stdio interface (`maccre_mcp.py`).
  2. Induce high-volume output payloads (e.g., querying large codebases via `read_local_codebase`) to stress stdio buffer limits under strict 30-second timeouts per call.
- **Edge-Case / Stress Condition:** Stdio buffer flooding under large JSON tool responses; strict isolation of stdout (preventing standard print statements from corrupting the FastMCP JSON-RPC stream); sub-30-second execution timeouts.
- **Expected System Behavior & Validation Criteria:**
  - All 61 FastMCP tools complete execution within the 30-second timeout window.
  - Standard stdout logs are strictly redirected or suppressed, ensuring 100% JSON-RPC compliance without protocol decoding errors.
  - The micro-test suite produces a clean PASS summary across all tool execution tiers.

---

## 3. Summary & Execution Roadmap

| Test Action ID | Focus Subsystem | Edge-Case Category | Key Validation Indicator |
|---|---|---|---|
| **TA-1** | Tool Registry & Dispatcher | RBAC Confinement & Profile Hydration Fallback | `TOOL_DENIED` telemetry logged; illegal calls blocked via `PermissionError`. |
| **TA-2** | Hybrid RAG & Search Fusion | Brave API Failure & RRF Rank Fusion Failback | Graceful failback to local vector+BM25 search without score disruption. |
| **TA-3** | RAG Engine & Key Vault | Cold-Boot Multithread Lock & Memory Zeroing | Single Gemini client instance; zero race conditions; RAM keys zeroed out. |
| **TA-4** | Scatter-Gather RAG Lineage | Context Isolation & Lineage Tag Filtering | `Worker_B` receives only `SCATTER_0>Worker_B` vectors; no context bleed. |
| **TA-5** | Media Render Executor | Stem Collision & Missing FFmpeg Fallback | `<job_id>_<node_id>_<timestamp>` path isolation; audio fallback report written. |
| **TA-6** | Session Canonization | Ephemeral Promotion & Semantic Pruning | >0.92 similarity vectors pruned; FlowStasis memory pins preserved. |
| **TA-7** | Sheet Parser & Materializer | Incomplete Workbook & Openpyxl Vendoring | Workspace initialized with `get_maccre_root()` path anchoring; completeness score calculated. |
| **TA-8** | FastMCP & Micro-Test | Stdio Protocol Hygiene & Sub-30s Timeout | 61 tools pass micro-test cleanly over JSON-RPC stdio stream. |
