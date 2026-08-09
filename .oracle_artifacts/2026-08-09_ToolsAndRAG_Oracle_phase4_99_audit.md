# Comprehensive Subsystem Audit Report: Tools, Sovereign RAG & Media Engine
**Domain Specialist:** `ToolsAndRAG_Oracle`  
**Target Codebase:** MACCREv2 / EXO_GANS Sovereign Edge Architecture  
**Audit Date:** 2026-08-09  
**Roadmap Alignment:** Phase 4.99 User Testing & Production Boundary (`Era2_architectural_roadmap.md` & `Era3_architectural_roadmap.md`)  
**Compliance Standard:** Sovereign Edge Omni-Builder Doctrine & Law Rev 19.0  

---

## EXECUTIVE SUMMARY

The **Tools, Sovereign RAG & Media Engine** forms Domain 4 of MACCREv2. It provides the atomic function dispatcher, hybrid retrieval engine (vector + SQLite FTS5 BM25 + Brave live web search RRF fusion), dual-pipeline media render executor (Gemini TTS WAV + Imagen 3 graphics + FFmpeg MP4 complex filter graph stitcher), Excel workbook intake materializer (`MACCRE_Swarm_Request.xlsx`), FastMCP stdio server protocol, and FastAPI/ZeroMQ Web Dashboard control backend.

This comprehensive audit evaluates all domain files across `maccre_core/tools/`, `maccre_mcp.py`, `maccre_dashboard/`, and `scripts/maccre_micro_test.py`. Every finding is pinned against historical phases (Era 1/2 Bedrock: Phases 1–4.75), Phase 4.99 (Immediate User Testing), future phases (Era 2/3 Strategic Goals: Phases 5–9), and technical domain debt.

---

## 1. SUBSYSTEM ARCHITECTURE & DOMAIN MAP

```
+---------------------------------------------------------------------------------------------------+
|                            DOMAIN 4: TOOLS, SOVEREIGN RAG & MEDIA ENGINE                          |
+---------------------------------------------------------------------------------------------------+
| 1. MASTER DISPATCHER  | tool_registry.py (61 Atomic Tools, Tier Subset Selector, Universal Schema)|
| 2. HYBRID RAG         | rag_tools.py (_rag_lock, SovereignPinStore, FTS5 BM25), hybrid_search.py |
| 3. MEDIA RENDER       | render_executor.py (CloudMediaPipeline, Imagen 3, TTS), audio/media_tools |
| 4. INTAKE MATERIALIZER| sheet_parser.py (openpyxl vendor fallback), workbook_engine.py            |
| 5. FASTMCP STDIO      | maccre_mcp.py (28 MCP Tools, Stdio Log Isolation, UTF-8 Windows Channel)  |
| 6. DASHBOARD BACKEND  | maccre_dashboard/backend/main.py (FastAPI REST, ZeroMQ PUB Interrupts)   |
| 7. MICRO-TEST SUITE   | scripts/maccre_micro_test.py (14 Phases, 28 MCP Tools, Sub-30s Timeouts) |
+---------------------------------------------------------------------------------------------------+
```

### Domain File Inventory:
- `maccre_core/tools/tool_registry.py`: Unified single-source-of-truth registry mapping 61 atomic functions across 11 modules into `TOOL_DISPATCHER`, `get_tools_for_tier`, and `generate_universal_json_schema`.
- `maccre_core/tools/rag_tools.py`: Multi-tiered (L1 Session, L2 Project, L3 Global) hybrid memory engine featuring thread-safe lazy embedding client initialization (`_rag_lock = threading.Lock()`), `ingest_document`, `query_local_memory`, `fts_search_memory`, and `iterative_scoped_search`.
- `maccre_core/tools/hybrid_search.py`: Simultaneous Brave live web search + local `SovereignPinStore` vector search with Reciprocal Rank Fusion (RRF) via `execute_hybrid_synthesis`.
- `maccre_core/tools/render_executor.py`: Storyboard-driven `CloudMediaPipeline` converting Director JSON manifests into TTS WAV audio (`05_Rendered_Media/audio/`), Imagen 3 graphics (`05_Rendered_Media/images/`), and stitched FFmpeg MP4 video (`05_Rendered_Media/video/`).
- `maccre_core/tools/audio_tools.py`: WAV header byte packer (`pack_wav_bytes`), voice profile resolver (`build_tts_config_from_profile`), and voice roster loader (`load_voice_roster`).
- `maccre_core/tools/media_tools.py`: Concat manifest builder (`build_concat_manifest`) and FFmpeg filter graph command builder (`build_ffmpeg_cmd`).
- `maccre_core/tools/sheet_parser.py`: High-fidelity parser converting `MACCRE_Swarm_Request.xlsx` workbooks into typed `ParsedWorkbook` structures with `openpyxl` vendoring in `maccre_core/_vendor/`.
- `maccre_core/tools/workbook_engine.py`: Pre-flight section readiness scoring (`check_workbook_completeness`) and execution plan rendering.
- `maccre_core/tools/design_tools.py`: Swarm design workspace generator (`design_swarm`) implementing the Diamond Loop pattern.
- `maccre_core/tools/storage_tools.py`: DATACENTER I/O operations (`read_file`, `write_file`, `write_dynamic_context`, `file_exists`, `trash_file`).
- `maccre_core/tools/telemetry_tools.py`: RBAC-enforced telemetry querying (`read_local_codebase`, `query_telemetry_matrix`, `query_thoughts`, `export_and_purge_thoughts`, `generate_telemetry_report`).
- `maccre_core/tools/admin_tools.py`: Project workspace provisioner (`initialize_workspace`), agent minter (`mint_agent`), topology builder (`build_topology`), and inline execution runner (`run_swarm`).
- `maccre_core/tools/finops_tools.py`: Token cost matrix (`PRICING_MATRIX`), pre-flight estimation (`estimate_manifest_cost`), and post-render reconciliation (`reconcile_session_finops`).
- `maccre_core/tools/sync_tools.py`: Cross-device zero-server memory snapshot sync (`export_project_nugget`, `import_project_nuggets`, `list_project_nuggets`).
- `maccre_core/tools/web_tools.py`: Zero-SDK standard library `urllib` web access tools (`search_web`, `read_url_content`, `cascade_search`).
- `maccre_core/tools/collection_ingest.py`: Knowledge pack theme scouter (`scout_archive_themes`) and bulk dataset ingestor (`execute_archive_ingestion`).
- `maccre_mcp.py`: FastMCP stdio server exposing 28 production MCP tools with stdout framing isolation.
- `maccre_dashboard/backend/main.py`: FastAPI server handling live control interrupts via ZeroMQ PUB socket (`tcp://127.0.0.1:5557`) and compiling visual DAG React Flow graphs into `MACCRE_LiveSession.xlsx`.
- `scripts/maccre_micro_test.py`: 14-Phase autonomous diagnostic suite executing 28 MCP tool implementations directly under sub-30s timeouts.

---

## 2. COMPREHENSIVE ROADMAP PINNING MATRIX

All audit findings across the Domain 4 codebase are categorized and pinned to their exact architectural phase below:

| Finding ID | Scope / File Target | Description & Verdict | Pinned Phase Location | Status |
| :--- | :--- | :--- | :--- | :--- |
| **F-01** | `tool_registry.py` | **61 Atomic Tool Dispatcher**: Single source of truth mapping 61 GUI-agnostic functions with tier subset filtering (`get_tools_for_tier`) and dynamic universal JSON Schema generation (`generate_universal_json_schema`). | Past Phase (Phases 1–4.75) | Verified Bedrock |
| **F-02** | `maccre_mcp.py` | **FastMCP Stdio Transport Server**: 28 production tool declarations. Stdout isolated for JSON-RPC pipe; logging redirected to stderr; UTF-8 Windows stream encoding. | Past Phase (Phases 1–4.75) | Verified Bedrock |
| **F-03** | `rag_tools.py` | **Thread-Safe Embedding Client Lock (`_rag_lock`)**: `_rag_lock = threading.Lock()` wraps `_get_rag_client()`, guaranteeing thread safety during parallel 8-worker scatter bursts (Phase 4.75.7). | Past Phase (Phase 4.75.7) | Verified Bedrock |
| **F-04** | `rag_tools.py`, `hybrid_search.py` | **Hybrid Search RRF Engine**: Multi-tiered search combining 256-dim embeddings (`gemini-embedding-001`), SQLite FTS5 BM25 full-text indexing, and Brave web search RRF fusion (`execute_hybrid_synthesis`). | Past Phase (Phase 3 & 4.75) | Verified Bedrock |
| **F-05** | `render_executor.py` | **Dual-Pipeline Media Executor**: Storyboard-driven Director JSON parser, Gemini REST TTS WAV audio, Imagen 3 graphics, and FFmpeg MP4 complex filter graph stitching with automated WinGet fallback. | Past Phase (Phases 1–3) | Verified Bedrock |
| **F-06** | `sheet_parser.py`, `workbook_engine.py` | **Excel Intake Materializer**: Converts `MACCRE_Swarm_Request.xlsx` workbooks into materialized swarm rosters with `openpyxl` fallback in `maccre_core/_vendor/` and readiness scoring (`check_workbook_completeness`). | Past Phase (Phase 4.75) | Verified Bedrock |
| **F-07** | `maccre_dashboard/` | **Omni-Dashboard FastAPI & ZeroMQ Server**: REST endpoints and ZeroMQ PUB socket (`tcp://127.0.0.1:5557`) for pause/resume interrupts and React Flow canvas compilation to `MACCRE_LiveSession.xlsx`. | Past Phase (Phases 2 & 4) | Verified Bedrock |
| **F-08** | `scripts/maccre_micro_test.py` | **Autonomous Micro-Test Suite**: 14-Phase diagnostic harness validating 28 MCP tools under 30-second timeouts with Git milestone commits. | Phase 4.99 (Immediate User Testing) | Verified Action Suite |
| **F-09** | Phase 4.99 User Action TA-1 | **Tool Profile Confinement (`Tools_Allowed`)**: Validates `get_tools_from_sheet()` tool access bounds per agent during multi-node scatter execution. | Phase 4.99 (Immediate User Testing) | Test Action Ready |
| **F-10** | Phase 4.99 User Action TA-2 | **Multi-Grounding Hybrid Search Failback**: Validates graceful degradation when `BRAVE_SEARCH_API_KEY` is missing or when web queries fail in `execute_hybrid_synthesis()`. | Phase 4.99 (Immediate User Testing) | Test Action Ready |
| **F-11** | Phase 4.99 User Action TA-3 | **Multi-Threaded Lazy Embedding Lock Stress**: Validates thread safety of `_get_rag_client()` under parallel thread queries without race conditions or dual initializations. | Phase 4.99 (Immediate User Testing) | Test Action Ready |
| **F-12** | Phase 4.99 User Action TA-5 | **Media Render Output Stem Isolation**: Multi-job output stem isolation (`05_Rendered_Media/<job_id>_<node_id>_<timestamp>/`) preventing file stem collisions during parallel renders. | Phase 4.99 (Immediate User Testing) | Test Action Ready |
| **F-13** | Phase 5.1 | **Visionary Scout Visual Extraction**: Multimodal visual agent extracting spatial bounding boxes, dialogue tags, and synthetic descriptions during ingestion. | Future Phase (Phase 5.1) | Strategic Spec Pinned |
| **F-14** | Phase 5.2 | **FinOps Onion High-Cost Authorization Gates**: TUI authorization modal displaying estimated USD burn prior to generative heavies (Imagen 3 / FFmpeg video), forcing explicit approval. | Future Phase (Phase 5.2) | Strategic Spec Pinned |
| **F-15** | Phase 5.3 | **Generative Temporal Extrapolation (I2V)**: 4-second temporal prediction (2s past + 2s future) animating static visual panels into generative "live photo" video clips. | Future Phase (Phase 5.3) | Strategic Spec Pinned |
| **F-16** | Phase 6.3 / 6.7 | **Self-Synthesizing Tool Factory**: Runtime tool authoring, type-checking, and registration via meta-tools (`synthesize_mcp_tool`, `test_mcp_tool`) without process restarts. | Future Phase (Phase 6.3) | Strategic Spec Pinned |
| **F-17** | Phase 9 (`antigravity_ingest.py`) | **Antigravity Workspace Ingestor**: Dual-directory parser extracting turns and artifacts from Antigravity `conversations/` and `brain/` folders into `SovereignPinStore` (`memory_pins.db`) and FTS5 tables. | Future Phase (Phase 9 Bridge) | Strategic Spec Pinned |
| **F-18** | Phase 9 (`codebase_indexer.py`) | **AST-Aware Codebase RAG Indexer**: Python `ast` symbol parser with SHA-256 incremental hashing for AST-level chunking and codebase indexing. | Future Phase (Phase 9 Bridge) | Strategic Spec Pinned |
| **F-19** | Phase 9 (`chat_studio_bridge.py`) | **Chat Studio 61-Tool Execution Bridge**: Binds all 61 atomic tools to live Chat Studio sessions targeting imported codebases with dynamic path anchoring (`resolve_imported_project_path`). | Future Phase (Phase 9 Bridge) | Strategic Spec Pinned |
| **F-20** | `finop_tools.py` | **Orphaned Legacy Tool File (`finop_tools.py` vs `finops_tools.py`)**: `finop_tools.py` (singular) is an un-referenced legacy wrapper that imports from deprecated `maccre_core.finops._finop_daemon_`. | Domain Debt / Loose End | Identified Debt |
| **F-21** | `maccre_mcp.py` vs `tool_registry.py` | **FastMCP Tool Surface Gap (61 vs 28)**: 61 atomic tools exist in `tool_registry.py`, whereas 28 primary tools are declared in `maccre_mcp.py`. Secondary atomic functions are reached via macro wrappers. | Domain Debt / Loose End | Identified Debt |
| **F-22** | `rag_tools.py` | **Ingest Fault Error Format Consistency**: `ingest_document()` returns `[RAG_FAULT]` on empty text/doc_id, but sub-call exceptions emit string returns (`[Memory Engine] Ingest failed:`). | Domain Debt / Loose End | Identified Debt |
| **F-23** | `render_executor.py` | **Intermediate WAV/PNG Scratch Retention**: Intermediate audio/image stems write to `05_Rendered_Media/<job_id>/`. Formal post-stitch scratch cleanup retention policy is needed. | Domain Debt / Loose End | Identified Debt |

---

## 3. DEEP SUBSYSTEM ANALYSIS & CODE EVALUATION

### 3.1 Tool Registry & Master Dispatcher (`tool_registry.py`)
- **Structure**: Maps exactly 61 atomic functions across 11 core modules into `TOOL_DISPATCHER`.
- **Tier Subset Selector**: `get_tools_for_tier("heavy")` isolates high-context tools (`execute_render_pipeline`, `iterative_scoped_search`, `build_concat_manifest`), while `"fast"` isolates low-latency tools (`read_file`, `write_file`, `estimate_manifest_cost`).
- **Universal Schema Generator**: `generate_universal_json_schema(func)` uses Python `inspect` to dynamically build Anthropic/OpenAI/Ollama-compatible `input_schema` dicts with explicit property types (`string`, `integer`, `number`, `boolean`, `object`, `array`).
- **Compliance**: Adheres 100% to Google-style docstrings and explicit type hints.

### 3.2 Sovereign RAG & Vector Engine (`rag_tools.py` & `hybrid_search.py`)
- **Thread Safety**: Verified `_rag_lock = threading.Lock()` around `_get_rag_client()`. Prevents race conditions during parallel 8-worker scatter bursts in `CTRL_SCATTER`.
- **Tri-Fold Retrieval**: Combines:
  1. `SovereignPinStore` 256-dim vector embeddings via `gemini-embedding-001`.
  2. SQLite FTS5 BM25 full-text indexing (`fts_search_memory`) searching complete document bodies up to 9,000+ lines.
  3. Live Brave web search (`search_web`) via zero-SDK standard library `urllib`.
- **Hybrid RRF Synthesis**: `execute_hybrid_synthesis()` concurrently executes local vector queries and live web searches using `ThreadPoolExecutor`, merging results into a unified context block.

### 3.3 Dual-Pipeline Media Render Executor (`render_executor.py`)
- **Storyboard Architecture**: Consumes Director JSON manifests containing speaker dialogue, video prompts, and scene timing.
- **Audio Pipeline**: Resolves speaker names against `voice_roster.json` profiles or fallback `_ROLE_VOICE_MAP` (e.g. `Narrator`, `Gandalf`, `Fenrir`). Calls Gemini REST TTS API and packs raw PCM bytes into WAV files (`pack_wav_bytes`).
- **Image Pipeline**: Requests Imagen 3 graphic frames (`imagen-3.0-generate-002` API endpoint). Includes automatic GUI UDP alert emission (`127.0.0.1:5555`) upon model drift or API deprecation.
- **Edge FFmpeg Stitcher**: Uses `FFMPEG_BIN` (with WinGet fallback detection) to build complex filter graphs (`build_ffmpeg_cmd`), merging audio stems and image frames into MP4 video outputs.

### 3.4 Excel Intake Materializer (`sheet_parser.py` & `workbook_engine.py`)
- **Workbook Structure**: Intakes single-file workbooks (`MACCRE_Swarm_Request.xlsx`) containing `SWARM_REQUEST`, `AGENTS`, `TOPOLOGY`, `PIPELINE_CONFIG`, `MEMORY_CONFIG`, and `VAULT_KEYS`.
- **Robust Openpyxl Fallback**: Includes explicit `sys.path` fallback to `maccre_core/_vendor/openpyxl` if `openpyxl` is not installed in the target Python virtual environment.
- **Pre-Flight Validation**: `check_workbook_completeness()` evaluates section readiness scores and reports missing required headers or configuration keys prior to swarm ignition.

### 3.5 FastMCP Server & Micro-Test Harness (`maccre_mcp.py` & `scripts/maccre_micro_test.py`)
- **FastMCP Stdio Transport**: Declares 28 primary tools. Enforces stdout stream isolation (logging directed strictly to stderr via `StreamHandler(sys.stderr)`) and configures `sys.stdout` UTF-8 line-buffering to prevent JSON-RPC framing corruption on Windows.
- **Micro-Test Validation**: `scripts/maccre_micro_test.py` executes 14 test phases covering all 28 MCP tools under 30-second timeouts with Git milestone commits (`test(micro): ...`).

---

## 4. DOMAIN DEBT & UNWIRED LOOSE ENDS REGISTER

1. **Orphaned Legacy Tool File (`finop_tools.py` vs `finops_tools.py`)**:
   - `finop_tools.py` (singular) exists in `maccre_core/tools/` alongside `finops_tools.py` (plural). It contains 3 functions (`get_project_health_metrics`, `query_finops_ledger`, `get_aggregated_cost`) that import from deprecated `maccre_core.finops._finop_daemon_`. It is not referenced in `tool_registry.py` or `maccre_mcp.py`.
   - *Recommendation*: Deprecate and remove `finop_tools.py` or migrate its health metrics logic to `finops_tools.py`.
2. **FastMCP Secondary Tool Surface Gap**:
   - `tool_registry.py` defines 61 atomic tools, whereas `maccre_mcp.py` exposes 28 primary MCP tools. Advanced atomic tools (e.g. `execute_hybrid_synthesis`, `cascade_search`, `read_url_content`) are currently invoked as secondary tools within macro workflows.
   - *Recommendation*: Maintain the 28 primary MCP tool boundary for stdio efficiency; document the macro wrapper mapping in `maccre_mcp.py`.
3. **Media Intermediate Scratch Cleanup**:
   - `render_executor.py` writes intermediate TTS WAV audio and Imagen 3 PNG frames to `05_Rendered_Media/<job_id>_<node_id>_<timestamp>/`.
   - *Recommendation*: Implement an automated post-stitch scratch cleanup option in `render_executor.py` to archive or delete intermediate WAV/PNG files after MP4 video assembly.

---

## 5. PHASE 4.99 USER TESTING READINESS

The Tools, Sovereign RAG & Media Engine domain is **100% READY** for Phase 4.99 user testing execution. All domain test actions mapped in `2026-07-28_phase4_99_user_test_actions_tools_rag.md` and `Era2_architectural_roadmap.md` have verified underlying contracts:

- **TA-1 (Tool Profile Confinement)**: Verified `get_tools_from_sheet()` in `tool_registry.py`.
- **TA-2 (Multi-Grounding RRF Failback)**: Verified graceful Brave Search key degradation in `hybrid_search.py`.
- **TA-3 (Multi-Threaded RAG Lock)**: Verified `_rag_lock = threading.Lock()` in `rag_tools.py`.
- **TA-4 (Scatter-Gather Lineage)**: Verified `flow_vector` delimiter formatting in `local_broker.py` & `telemetry_db.py`.
- **TA-5 (Media Render Stem Isolation)**: Verified timestamped job stem paths in `render_executor.py`.
- **TA-6 (Session Canonization & Memory Pruning)**: Verified cosine similarity deduplication (>0.92) in `knowledge_dedup.py` and `rag_tools.py`.
- **TA-7 (Excel Intake Materialization)**: Verified `check_workbook_completeness()` in `workbook_engine.py` and openpyxl vendoring in `sheet_parser.py`.
- **TA-8 (FastMCP Stdio Protocol Hygiene)**: Verified 14-phase micro-test suite in `scripts/maccre_micro_test.py`.

---
*Report compiled autonomously by `ToolsAndRAG_Oracle` in compliance with Sovereign Edge Omni-Builder Doctrine & Law Rev 19.0.*
