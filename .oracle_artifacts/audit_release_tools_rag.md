# Tools & RAG Oracle — Release Candidate Audit Report

**Audit Target:** `B:\MACCRE_Release`  
**Artifact Target:** `B:\EXO_GANS\.oracle_artifacts\audit_release_tools_rag.md`  
**Ledger Target:** `B:\EXO_GANS\.agent\skills\Specialists\ToolsAndRAG_Oracle\task_ledger.md`  
**Audit Date:** 2026-07-25  

---

### EXECUTIVE SUMMARY
The **Tools & RAG Specialist Oracle** has completed a comprehensive audit of the `B:\MACCRE_Release` release candidate directory, focusing on `maccre_core/tools/`, `tool_registry.py`, `rag_tools.py`, `render_executor.py`, `sheet_parser.py`, `workbook_engine.py`, `maccre_mcp.py`, `maccre_dashboard/`, and `maccre_core/_vendor/`.

All primary architectural requirements under the **Sovereign Edge Omni-Builder Doctrine** are verified operational, zero-SDK compliant, and properly anchored.

---

### 1. ATOMIC TOOL DISPATCHER VERIFICATION (`tool_registry.py`)
- **61 Atomic Tools Dispatcher:** `TOOL_DISPATCHER` explicitly maps **61 atomic tool callables** across 15 operational categories (Text, Audio, Media, Agent, Storage, Memory/RAG, Telemetry/RBAC, Global Orchestration, FinOps, Topology Library, Swarm Design, Cross-Device Sync, Project Workbook, Web Access, CollectionLM Ingestion).
- **Single Source of Truth:** `TOOL_REGISTRY` is auto-generated via `list(TOOL_DISPATCHER.values())`, eliminating dual-declaration maintenance bugs.
- **Tier-Aware Selection:** `get_tools_for_tier(tier)` correctly splits tool sets into `"heavy"` (14 high-context tools) and `"fast"` (9 lightweight validation tools).
- **Universal JSON Schema Generator:** `generate_universal_json_schema()` dynamically inspects function signatures and type annotations to generate Anthropic Messages API and Ollama OpenAI-compatible tool definitions.

---

### 2. SOVEREIGN RAG ENGINE (`rag_tools.py`, `hybrid_search.py`, `web_tools.py`)
- **Tri-Fold Retrieval Architecture:**
  1. `query_local_memory`: Semantic vector search across project memory pins using Vault-managed `gemini-embedding-001` (256-dim embeddings).
  2. `fts_search_memory`: Full-text keyword search across ALL stored document text via SQLite FTS5 BM25.
  3. `iterative_scoped_search`: Two-stage dynamic search combining FTS scope discovery with vector similarity and exclusion set filtering (`excluded_ids`).
- **Live Web + Local Hybrid Fusion:** `execute_hybrid_synthesis()` (`hybrid_search.py`) runs parallel `ThreadPoolExecutor` queries against local `SovereignPinStore` vector DB and live Brave Search API (`search_web`). If `BRAVE_SEARCH_API_KEY` is missing from the Windows Credential Vault, web search degrades gracefully with a `[WEB_FAULT]` banner while retaining local semantic results.
- **Zero-SDK REST Architecture:** All RAG and web endpoints utilize standard library `urllib` and `GeminiClient` with OS Vault credential resolution.

---

### 3. DUAL-PIPELINE MEDIA RENDER EXECUTOR (`render_executor.py`, `audio_tools.py`, `media_tools.py`)
- **Abstract Pipeline Interface:** Governed by `BaseMediaPipeline(abc.ABC)` with concrete `CloudMediaPipeline`.
- **TTS Audio Generation:** `render_podcast_audio()` synthesizes multi-speaker audio via Gemini REST TTS (Fenrir, Aoede, etc.), resolving custom voice characteristics through `voice_roster.json` (`VoiceProfile`) or fallback role maps, outputting packed WAV audio.
- **Imagen 3 Image Generation:** `render_image()` and `render_image_batch()` handle image synthesis via Imagen 3 REST API (`generateImages`), featuring dynamic model drift detection that emits UDP JSON notifications to port `5555` for TUI GUI hooks.
- **Edge FFmpeg Complex Filter Graph Stitcher:** `render_video()` locates `ffmpeg.exe` via `shutil.which` or WinGet fallback paths (`Gyan.FFmpeg`), builds filter graph execution manifests (`build_ffmpeg_cmd`), and renders final H.264/AAC MP4 media strictly into `05_Rendered_Media`.

---

### 4. EXCEL WORKBOOK MATERIALIZER & VENDORING (`sheet_parser.py`, `workbook_engine.py`, `maccre_core/_vendor/`)
- **Workbook Parser (`sheet_parser.py`):** Replaces legacy CSV/JSON configs by parsing `MACCRE_Swarm_Request.xlsx` (Title at Row 1, Headers at Row 2, Data at Row 3+) into typed structures (`ParsedWorkbook`, `AgentDesign`, `NodeDesign`).
- **Workbook Completeness & FinOps Engine (`workbook_engine.py`):** `check_workbook_completeness()` validates section readiness (`PROJECT_DEFINITION`, `SWARM_REQUEST`, `AGENTS`, `TOPOLOGY`, `SESSION_CONFIG`), computes FinOps token cost estimates (~20,000 tokens/node avg), and returns structured execution plans.
- **Zero-Dependency `openpyxl` Vendoring:**
  - `maccre_core/_vendor/` contains vendored `openpyxl` (3.1.5) and `et_xmlfile` (2.0.0).
  - `maccre_core/__init__.py` injects `_vendor/` to the head of `sys.path`:
    ```python
    vendor_dir = os.path.join(os.path.dirname(__file__), '_vendor')
    if os.path.isdir(vendor_dir) and vendor_dir not in sys.path:
        sys.path.insert(0, vendor_dir)
    ```
  - Independent fallback `sys.path` injection is also present in `sheet_parser.py` and `workbook_engine.py` for standalone execution safety.

---

### 5. FASTMCP SERVER & DASHBOARD INTEGRATION (`maccre_mcp.py`, `maccre_dashboard/`)
- **FastMCP Stdio Isolation (`maccre_mcp.py`):** UTF-8 stdout/stderr re-encoding and logger redirection to `sys.stderr` prevents non-JSON-RPC output from corrupting the stdio transport pipe. Exposes 8 tool groups (System, Swarm, Knowledge, Storage, Render, Telemetry, FinOps, Admin).
- **Omni-Dashboard API (`maccre_dashboard/backend/main.py`):** Exposes FastAPI endpoints for health checks, topology compilation (writing to `MACCRE_LiveSession.xlsx`), and ZMQ PUB socket interrupts (`tcp://127.0.0.1:5557`) for real-time swarm pause/resume control.

---

### 6. DOMAIN FINDINGS & RECOMMENDATIONS
1. **Orphaned File Finding:** `maccre_core/tools/finop_tools.py` (41 lines) exists in the release candidate alongside `maccre_core/tools/finops_tools.py` (585 lines). `finop_tools.py` is not referenced in `tool_registry.py`.  
   *Recommendation:* Delete `finop_tools.py` before final release tag to prevent naming confusion.
2. **`openpyxl` Ingestion Standard:** Openpyxl vendoring injection in `maccre_core/__init__.py` functions cleanly without external virtual environment dependencies.
3. **Media Pipeline Datacenter Anchor:** Media outputs strictly write to `05_Rendered_Media` via `get_datacenter_path()`.
