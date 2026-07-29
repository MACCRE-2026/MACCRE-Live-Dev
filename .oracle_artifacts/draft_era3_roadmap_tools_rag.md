# MACCREv2 / EXO_GANS Era 3 Architectural Roadmap: Tools, RAG & Media Subsystems

**Specialist Oracle Domain:** `maccre_core/tools/` (`tool_registry.py`, `rag_tools.py`, `render_executor.py`, `design_tools.py`, `finops_tools.py`, `sync_tools.py`, `sheet_parser.py`, `workbook_engine.py`, `telemetry_tools.py`, `admin_tools.py`), `maccre_dashboard/`, `maccre_mcp.py`, `scripts/maccre_micro_test.py`.  
**Law Revision:** 19.0 Compliance  
**Date:** 2026-07-25  

---

## SECTION 1: Implemented Tools, RAG & Media Features (Era 1 & Era 2 Foundation)

The MACCREv2 / EXO_GANS platform currently operates a zero-cloud-dependency, sovereign tool and retrieval substrate. The verified production suite includes:

### 1.1 Master Tool Dispatcher & Universal Schema Generator (`tool_registry.py`)
- **61 Atomic Tool Dispatcher (`TOOL_DISPATCHER`)**: Single source of truth routing all 61 atomic engine tools across 11 functional modules.
- **Universal JSON Schema Generator (`generate_universal_json_schema`)**: Dynamically inspects type annotations and docstrings to produce standard OpenAPI/Gemini JSON tool definitions for model binding.
- **Tier-Based Gating (`get_tools_for_tier`)**: RBAC and safety filtering allocating safe execution subsets per agent role.

### 1.2 Sovereign Hybrid Search Engine (`rag_tools.py` & `hybrid_search.py`)
- **Tri-Fold Retrieval Synthesis**: Combines SQLite FTS5 BM25 lexical full-text search with 256-dimensional `sqlite-vec` semantic embeddings and live Brave Web Search (`search_web`).
- **Reciprocal Rank Fusion (RRF)**: Merges sparse BM25 ranks, dense vector cosine similarity scores, and web search results into a unified relevancy queue.
- **Multi-Tiered Memory Isolation**: Supports Session Memory (L1), Project Memory (L2), and Global Datacenter Memory (L3).
- **Cross-Project Federation (`query_foreign_memory`)**: Enables zero-copy querying of foreign project vector spaces with strict read-only isolation.
- **Hash-Based Deduplication**: Content-hash indexing preventing duplicate vector embedding generation.
- **Native Document Loaders (`key_ingestor.py`)**: High-speed text, markdown, code file, `pypdf`, and `python-docx` file ingestion.

### 1.3 Dual-Pipeline Media Render Executor (`render_executor.py`)
- **Synchronized Audio/Visual Render Pipeline**: Ingests Director JSON storyboards and produces synchronized podcast audio (`render_podcast_audio`) and video slideshows (`render_video`).
- **Sovereign REST Audio TTS Pipeline**: Generates natural multi-speaker speech via Gemini REST API (`gemini-2.5-flash` / audio synthesis endpoints).
- **Imagen 3 Image Pipeline**: Generates 1024x1024 / 16:9 visual assets directly into `05_Rendered_Media/images/`.
- **Edge FFmpeg Filter Graph Engine**: Assembles audio tracks, image frames, dynamic transitions, subtitles, and complex visual filter graphs into production MP4 deliverables without external cloud rendering dependencies.

### 1.4 Excel Workbook Intake Materializer (`sheet_parser.py` & `workbook_engine.py`)
- **High-Fidelity Workbook Parser**: Ingests `MACCRE_Swarm_Request.xlsx` workbooks, extracting swarm topologies, node definitions, system prompts, and tool flags (`parse_workbook`).
- **Automated Workspace Materializer (`materialise_from_sheet`)**: Converts parsed workbooks into ready-to-execute MACCRE project environments with all 5-tier datacenter directories.
- **Pre-Flight Completeness & FinOps Estimator**: Audits workbook readiness and generates pre-execution cost projections (`check_workbook_completeness`, `render_execution_plan`).

### 1.5 Swarm Design Engine & Diamond Loop (`design_tools.py`)
- **Natural Language Swarm Synthesizer**: Transforms user requirements into production swarm topologies.
- **Diamond Loop Compliance**: Enforces Generator (temp=1.0) vs. Critic (temp=0.1 + Pydantic `BaseModel` schema) separation using zero-dependency `urllib` calls via `maccre_core._net.gemini_client`.

### 1.6 FastMCP Stdio Server & Diagnostic Harness (`maccre_mcp.py` & `maccre_micro_test.py`)
- **FastMCP Protocol Server**: Exposes 28 core agent tools over stdio for external MCP clients (Cursor, Claude Desktop, Antigravity IDE).
- **Automated Diagnostic Harness**: 14-Phase micro-test suite validating all tool schemas, parameters, and return signatures within 30-second timeouts (`maccre_micro_test.py`).

### 1.7 FinOps & Cross-Device Synchronization (`finops_tools.py` & `sync_tools.py`)
- **Real-Time Cost Accounting**: Double-entry financial tracking (`PRICING_MATRIX`) recording input/output tokens and USD burn in `system_logs.db`.
- **Zero-Server Nugget Sync**: Exports and imports encrypted memory snapshots (`.nugget`) via Google Drive polling without central servers.

### 1.8 API-Level Reasoning & Thought Extraction (`gemini_client.py` & `swarm_worker.py`)
- **`thinkingConfig` Injection**: Native payload support for Gemini 3.x API-level hidden tree-search thinking (`Low`/`High`).
- **3-Tuple Return Architecture**: `UniversalRouter.generate()` returns `(output_text, cost, api_thought)` for dual-channel thought logging in `03_Agent_Ledgers`.

---

## SECTION 2: Unfinished & Future Tools/RAG Roadmap Items (Era 2 Carryover & Gaps)

Based on our synthesis of `ctrl_scatter-expansion plan-v3.md`, `Era2_architectural_roadmap.md`, `FeatureRequests.md`, `EXO_GANS_Wishlist_Architecture.md`, and `TUI_REFACTOR_PLAN.md`, the following tools, RAG, and media capabilities were scoped in Era 2 but remain to be fully realized:

### 2.1 CollectionLM Offline Knowledge Ingestion Engine
- **Concept**: Sovereign dataset compilation and offline RAG knowledge store building. Converts massive raw directory trees into vectorized, FTS5-indexed offline knowledge packs.
- **Status**: Partially implemented in `rag_tools.py` memory pins; needs bulk offline compiler CLI.

### 2.2 Multimodal Visual Extraction & "Visionary Scout" (Phase 5.1)
- **Concept**: Specialized agent role processing complex multi-panel media (e.g., comic panels, technical schematics) to extract visual bounding boxes, dialogue tags, and spatial layout metadata.
- **Triune Memory Linking**: Links synthetic text metadata in SQLite vector memory to raw binary paths in `01_Raw_Source`.
- **Status**: Scoped in `Era2_architectural_roadmap.md` §5.1 & `FeatureRequests.md`; unfulfilled.

### 2.3 Real-Time Voice Synthesis Streaming & Low-Latency Audio Stream
- **Concept**: Upgrading `render_executor.py` and `gemini_client.py` to support real-time audio chunk streaming over WebSockets/ZMQ rather than batch file rendering.
- **Status**: Scoped in `EXO_GANS_Wishlist_Architecture.md` Part 5 (Items 8–9); requires streaming REST/WebSocket transport.

### 2.4 Generative Temporal Extrapolation / Image-to-Video Animation (Phase 5.3)
- **Concept**: Multi-frame temporal prediction utilizing Image-to-Video (I2V) generative models to synthesize the 2 seconds preceding and 2 seconds following a static image panel, generating "live photos".
- **Status**: Scoped in `Era2_architectural_roadmap.md` §5.3 & `FeatureRequests.md`; unfulfilled.

### 2.5 Automated Tool Synthesis & "Generative Recruitment Engine"
- **Concept**: Evolving the Prompt Engineer into a passive context-monitoring node that dynamically generates system prompts, creates custom tool definitions, and registers synthesized agents/tools into `controlnode_registry.db` and `tool_registry.py` at runtime.
- **Status**: Scoped in `FeatureRequests.md`; unfulfilled.

### 2.6 Hybrid Exclusionary Search & Tri-Grounding Logic (Phase 3.1)
- **Concept**: Sequenced retrieval pipeline where Google Search runs first, followed by a Brave LLM search explicitly configured to ignore previously retrieved Google URLs. When all 3 groundings (Local Vector Memory, Google, Brave) are active, system prompts dynamically inject contextual weighting rules.
- **Status**: Scoped in `Era2_architectural_roadmap.md` §3.1 & `FeatureRequests.md`; unfulfilled.

### 2.7 S25 Ultra Edge Device Sync Node & Webhook Gating (`CTRL_EDGE_SYNC` / `CTRL_WEBHOOK`)
- **Concept**: Gated edge node dropping task payloads into a designated Google Drive exchange folder, paired with a dynamic polling watchdog to offload execution to localized edge LLMs (e.g., Galaxy S25 Ultra running local GGUF/Ollama models).
- **Status**: Scoped in `Era2_architectural_roadmap.md` §4.1/§6.3 & `FeatureRequests.md`; stubs seeded in `controlnode_registry.db`.

### 2.8 FinOps Onion High-Cost Authorization Modal (Phase 5.2)
- **Concept**: Interactive TUI overlay intercepting high-cost generative calls (Imagen 3 image batches, I2V video rendering, high-token deep reasoning loops) to present calculated USD estimates and require explicit operator sign-off before proceeding.
- **Status**: Scoped in `Era2_architectural_roadmap.md` §5.2; unfulfilled.

---

## SECTION 3: Proposed Era 3 Tools & RAG Architectural Goals

To achieve absolute sovereign edge dominance in Era 3, the Tools, RAG & Media subsystem will execute six major architectural evolutions:

### 3.1 CollectionLM Sovereign Knowledge Engine
- **Autonomous Knowledge Compiler**: Build a zero-cloud offline ingestion CLI (`omni run scripts/compile_collection_lm.py`) that ingests massive local codebases, research libraries, and documentation repositories into compressed, offline-capable knowledge packs (`.clm`).
- **Dynamic RRF Weight Tuning**: Implement an adaptive Reciprocal Rank Fusion algorithm that auto-adjusts weights between FTS5 BM25 lexical matches and `sqlite-vec` semantic similarity based on query density and domain type (e.g., code vs. prose).
- **RAG Benchmarking Suite**: Introduce automated ground-truth evaluation tools to measure retrieval precision, recall, and hallucination rates across local memory stores.

### 3.2 Autonomous Tool Factory & FastMCP Synthesizer
- **Self-Synthesizing Tool Engine**: Provide agents with meta-tools (`synthesize_mcp_tool`, `test_mcp_tool`, `register_mcp_tool`) allowing them to write Python functions, generate strict type hints, execute validation via `maccre_micro_test.py`, and dynamically register the resulting tools into both `tool_registry.py` and `maccre_mcp.py` without restarting the process.
- **Control Node Integration**: Automatically generate corresponding `CTRL_` handlers when new deterministic tools are created, expanding `controlnode_registry.db` programmatically.

### 3.3 Multimodal Real-Time Streaming Pipeline
- **Native Gemini 3.x Multimodal Streaming**: Upgrade `gemini_client.py` to support bi-directional WebSocket streaming for audio, video, and text frames.
- **Low-Latency Voice Agent Runtime**: Enable interactive voice conversation loops with sub-500ms latency, bypassing file-based audio generation for live operator dialogue.
- **Real-Time Video Context Inspection**: Stream webcam/screen video feeds directly into the RAG engine for live visual debugging and architectural inspection.

### 3.4 Synthetic Media Temporal & Spatial Render Suite
- **Generative "Live Photo" Pipeline**: Implement the full 4-second temporal extrapolation pipeline (2s past + 2s future) using Imagen 3 + Gemini 3.5 Image-to-Video models.
- **Hardware-Accelerated FFmpeg Filter Graphs**: Upgrade `render_executor.py` with GPU-accelerated FFmpeg filter graphs (`nvenc` / `qsv`), supporting dynamic pan-and-zoom (Ken Burns effect), animated overlays, and automated multi-track podcast mixing.

### 3.5 Distributed Sovereign Memory Mesh & P2P Nugget Exchange
- **Zero-Trust Memory Federation**: Extend `sync_tools.py` to form a peer-to-peer memory mesh across local LAN nodes and edge devices using encrypted `.nugget` exchanges.
- **RBAC-Enforced Telemetry Querying**: Provide fine-grained access control policies for cross-project and cross-device memory queries, ensuring sensitive project ledgers and `thoughts.db` remain cryptographically isolated.

### 3.6 Predictive FinOps & Hardware-Aware Compute Routing
- **Pre-Flight VRAM & Compute Probing**: Before dispatching massive context windows or local model inferences (e.g., Gemma 3:9b via Ollama), dynamically probe host system VRAM, CPU utilization, and API rate limits.
- **Adaptive Fallback Router**: Dynamically route tasks between low-cost local models and cloud Gemini 3.5 Pro APIs based on token budget constraints and hardware capacity.
- **Interactive FinOps Authorization Overlay**: Enforce explicit user approval via TUI overlays when estimated task costs exceed operator-defined threshold limits.

---

## SECTION 4: Subsystem File Inventory & Summary

| File | Subsystem Role | Key Functions / Components |
|------|----------------|----------------------------|
| `maccre_core/tools/tool_registry.py` | Master Tool Registry | `TOOL_DISPATCHER`, `get_tools_for_tier`, `generate_universal_json_schema` |
| `maccre_core/tools/rag_tools.py` | Hybrid RAG & Vector Engine | `ingest_document`, `query_local_memory`, `fts_search_memory`, `query_foreign_memory` |
| `maccre_core/tools/render_executor.py` | Dual Media Render Pipeline | `CloudMediaPipeline`, `execute_render_pipeline`, `render_podcast_audio`, `render_video` |
| `maccre_core/tools/design_tools.py` | Swarm Design Engine | `materialize_swarm_from_prompt`, Diamond Loop generator/critic |
| `maccre_core/tools/sheet_parser.py` | Excel Sheet Parser | `parse_workbook`, `materialise_from_sheet` |
| `maccre_core/tools/workbook_engine.py` | Workbook Validation Engine | `check_workbook_completeness`, `render_execution_plan` |
| `maccre_core/tools/finops_tools.py` | Token Cost & Financials | `PRICING_MATRIX`, `calculate_predicted_cost`, `reconcile_session_finops` |
| `maccre_core/tools/sync_tools.py` | Cross-Device Memory Sync | `export_project_nugget`, `import_project_nuggets` |
| `maccre_core/tools/telemetry_tools.py` | Telemetry & Confinement | `query_telemetry_matrix`, `query_thoughts`, `read_local_codebase` |
| `maccre_core/tools/admin_tools.py` | Swarm Lifecycle Admin | `initialize_workspace`, `mint_agent`, `build_topology`, `ignite_swarm` |
| `maccre_mcp.py` | FastMCP Stdio Server | 28 MCP tool definitions for external IDE clients |
| `scripts/maccre_micro_test.py` | Tool Diagnostic Harness | 14-Phase automated testing suite for MCP tool validation |
