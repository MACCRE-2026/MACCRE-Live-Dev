# Era 3 Architectural Roadmap — Phase 9 Draft Contribution
## Subsystem 4: Tools, Sovereign RAG & Media Engine Roadmap

> **Author**: Tools & RAG Specialist Oracle (`ToolsAndRAG_Oracle`)  
> **Date**: 2026-07-25  
> **Phase Target**: Phase 9 — In-State Live Development & Antigravity Desktop Transition Bridge  
> **Compliance**: Sovereign Edge Omni-Builder Doctrine (Law Rev 19.0)  

---

### 1. PHASE 9 OVERVIEW & VISION (TOOLS & RAG DIMENSION)

Phase 9 establishes the **In-State Live Development & Antigravity Desktop Transition Bridge**, empowering MACCREv2 / EXO_GANS to seamlessly ingest Antigravity desktop workspaces (`conversations\`, `brain\`, skills, and scratch artifacts) and execute full-suite live development directly against legacy and imported project codebases.

From the **Tools, Sovereign RAG & Media Engine** perspective, Phase 9 delivers three core technological capabilities:

```
+-----------------------------------------------------------------------------------+
|               PHASE 9: TOOLS, SOVEREIGN RAG & LIVE DEV ARCHITECTURE               |
+-----------------------------------------------------------------------------------+
| 1. ANTIGRAVITY WORKSPACE INGESTION ENGINE (`antigravity_ingestor.py`)              |
|    - Dual-directory parser (`conversations/` JSON logs & `brain/` markdown/artifacts) |
|    - Multi-turn conversation chunker with metadata tagging (`turn_id`, `role`)   |
|    - Direct upsert into `SovereignPinStore` (`memory_pins.db`) & SQLite FTS5 BM25 |
|                                                                                   |
| 2. AST-AWARE CODEBASE RAG INDEXER (`codebase_indexer.py`)                        |
|    - Structural code parser preserving function/class boundaries                  |
|    - Incremental SHA-256 hash manifest (zero redundant embedding API costs)       |
|    - Dual RRF synthesis fusing AST symbol FTS5 + 256-dim vector embeddings        |
|                                                                                   |
| 3. CHAT STUDIO 61-TOOL EXECUTION BRIDGE (`chat_studio_bridge.py`)                 |
|    - Full 61 atomic tool registry binding for active Chat Studio sessions         |
|    - Dynamic project-root path anchoring (`resolve_imported_project_path`)        |
|    - Tier-aware access control & safe file modification hooks                     |
+-----------------------------------------------------------------------------------+
```

---

### 2. SUBSYSTEM BEDROCK & EXTENSIONS FOR PHASE 9

#### 2.1 Antigravity Workspace Ingestion Engine
- **Conversation Log Parser**: Reads Antigravity conversation JSON files from `conversations\`, extracting turns, user prompts, agent responses, and tool call traces.
- **Brain Artifact Indexer**: Scans `brain\` artifacts (`.md` reports, architecture diagrams, scratch scripts) and tags them with metadata (`artifact_id`, `created_at`, `source_dir`).
- **SovereignPinStore Indexing**: Vectorizes text blocks via `gemini-embedding-001` (256-dim floats) and builds full-text FTS5 BM25 search tables in `memory_pins.db`.

#### 2.2 Imported Codebase & Legacy Project RAG Indexer
- **AST-Aware Chunking**: Replaces naive line-based text splitting with structural parsing (Python `ast`, regex symbol extractors for JS/TS/Rust/C++), ensuring function and class definitions are never split mid-block.
- **SHA-256 Incremental Change Detection**: Tracks `file_hash` in `indexed_file_hashes` SQLite table to prevent re-embedding unmodified source files.
- **Tri-Fold Hybrid RRF Search**: Fuses local code symbol FTS5 search, 256-dim semantic vector retrieval, and live Brave web search into a unified context block via Reciprocal Rank Fusion ($k=60$).

#### 2.3 Chat Studio Live Development & 61-Tool Suite Dispatcher
- **Universal Tool Dispatch**: Exposes all 61 atomic tools from `maccre_core/tools/tool_registry.py` to active Chat Studio sessions.
- **Dynamic Active Project Anchoring**: Wraps storage, RAG, and telemetry tools with runtime project root resolution (`MACCRE_ACTIVE_PROJECT`), ensuring code reads, edits, and searches target the imported codebase root.
- **3-Tier Elevation Integrity**: Requires explicit Tier 2 PIN elevation or validated MCP tokens before executing destructive filesystem actions (`write_file`, `trash_file`) against live imported repositories.

---

### 3. ERA 3 ROADMAP MATRIX UPDATES FOR SECTION 4

| Subsystem Scope | Implemented Bedrock (Era 1 & 2) | Unfinished / Carryover Items | Era 3 Phase 9 Strategic Goals |
| :--- | :--- | :--- | :--- |
| **Tools, RAG & Media Engine** | 61 atomic tool dispatcher (`tool_registry.py`), Sovereign RAG FTS5 BM25 + 256-dim vector + Brave web RRF fusion (`hybrid_search.py`), dual-pipeline media render executor (TTS/Imagen 3/FFmpeg stitcher), Excel workbook intake materializer. | CollectionLM offline knowledge ingestion CLI, Visionary Scout visual extraction (Phase 5.1), real-time voice streaming, temporal extrapolation I2V (Phase 5.3), auto-tool synthesis. | **Phase 9 Bridge**: Ingestion of Antigravity `conversations/` & `brain/` into `SovereignPinStore`, AST-aware codebase RAG indexer with SHA-256 incremental hashing, Chat Studio 61-tool execution bridge targeting imported legacy codebases. |

---

### 4. PHASE 9 ROADMAP SECTION ADDITION (FOR SECTION 6)

```
| PHASE 9: IN-STATE LIVE DEVELOPMENT & ANTIGRAVITY TRANSITION BRIDGE             |
|   - Antigravity conversations/ & brain/ directory ingestion into memory_pins.db  |
|   - AST-aware codebase chunking & SHA-256 incremental RAG indexing               |
|   - Chat Studio 61-tool execution engine targeting imported project codebases     |
|   - Dynamic project-root path resolution (resolve_imported_project_path)          |
|   - Tier 2 access control PIN elevation hooks for live dev write operations      |
```
