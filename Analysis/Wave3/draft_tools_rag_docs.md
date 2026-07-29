# WAVE 3 DOCUMENTATION DRAFT: TOOLS, RAG & MEDIA SUBSYSTEM

**Author:** Tools & RAG Specialist Oracle (`ToolsAndRAG_Oracle`)  
**Target Integration Files:** `B:\EXO_GANS\README.md` & `B:\EXO_GANS\MACCRE_Operator_Manual.md`  

---

## PART 1: CONTRIBUTION TO `README.md`

### Subsystem Overview: Tools, Sovereign RAG & Media Engine

#### 1. Master Tool Registry & Dispatcher (`maccre_core/tools/tool_registry.py`)
- **61 Atomic Tool Functions**: Central single-source-of-truth dispatcher (`TOOL_DISPATCHER`, `TOOL_REGISTRY`) mapping 61 GUI-agnostic functions across 11 sub-modules.
- **Tier-Aware Routing (`get_tools_for_tier`)**: `"heavy"` tools for Gemini 2.5 Pro / Pro models vs. `"fast"` tools for Flash / Lite.
- **Universal JSON Schema Generator (`generate_universal_json_schema`)**: Uses `inspect` to generate OpenAPI/Anthropic/OpenAI/Ollama compatible tool schemas from Python docstrings.

#### 2. Sovereign RAG Hybrid Search Engine (`maccre_core/tools/rag_tools.py`, `maccre_core/tools/hybrid_search.py`)
- **SovereignPinStore**: Zero-dependency SQLite WAL vector store (`memory_pins.db`) + FTS5 BM25 keyword search.
- **256-Dim Embeddings**: Generated via `gemini-embedding-001` using standard `urllib` REST client.
- **Tri-Fold Hybrid Search (`execute_hybrid_synthesis`)**: Parallel vector search + SQLite FTS5 BM25 + Brave live web search (`urllib`), fused via Reciprocal Rank Fusion (RRF).

#### 3. Dual-Pipeline Media Render Executor (`maccre_core/tools/render_executor.py`)
- **TTS Audio Branch**: Synthesizes WAV audio files into `05_Rendered_Media/audio/`.
- **Imagen 3 Image Branch**: Renders image batches into `05_Rendered_Media/images/` with dynamic fallback from `imagen-3.0-generate-001` to `imagen-3.0-generate-002`.
- **Edge FFmpeg Filter Graph Stitcher**: Resolves `ffmpeg.exe` and stitches audio/image assets into synchronized `.mp4` video in `05_Rendered_Media/video/`.

#### 4. Excel Workbook Intake & Materialization Pipeline (`maccre_core/tools/sheet_parser.py`, `maccre_core/tools/workbook_engine.py`)
- **ParsedWorkbook Struct (`sheet_parser.py`)**: Parses `MACCRE_Swarm_Request.xlsx` workbooks into typed swarm structures.
- **Completeness & FinOps Engine (`workbook_engine.py`)**: Pre-flight section readiness scoring (`check_workbook_completeness`) and token cost estimation.

---

## PART 2: CONTRIBUTION TO `MACCRE_Operator_Manual.md`

### Part V — Tools, RAG & Media Operations Manual

#### V.1 Document Ingestion & Semantic Memory Pinning
Ingest documents to `01_Raw_Source/` using `ingest_document()`. Generates 256-dim embeddings, stores binary vector blobs in `memory_pins.db`, and indexes FTS5 BM25 search.

#### V.2 Hybrid Search Usage & Research Orchestration
Execute `execute_hybrid_synthesis(query, collection_name, extra_queries)` to run parallel local vector search + live Brave web search via standard `urllib`.

#### V.3 FFmpeg Video Render Pipeline & Director Manifest Execution
Construct Director JSON manifests and run `execute_render_pipeline()` to output synchronized TTS audio (`05_Rendered_Media/audio/`), Imagen 3 graphics (`05_Rendered_Media/images/`), and FFmpeg `.mp4` video (`05_Rendered_Media/video/`).

#### V.4 Excel Workbook Request Template Materialization
Pass `MACCRE_Swarm_Request.xlsx` to `check_workbook_completeness()` for pre-flight audit, then call `materialise_from_sheet()` to generate `agent_roster.json` and `topology.json`.
