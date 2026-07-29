# GRANULAR FUNCTIONAL LEDGER: TOOL EXECUTION SUITE, DASHBOARD & KEY AUTOMATION SCRIPTS

**Target Document:** `B:\EXO_GANS\Analysis\Wave1\10_tools_dashboard_scripts_ledger.md`  
**System Architecture:** MACCREv2 / EXO_GANS Sovereign Edge Framework  
**Law Revision:** 19.0 Compliance  

---

## EXECUTIVE SUMMARY

This functional ledger provides a line-by-line, component-level architectural analysis of the **MACCREv2 Tool Execution Suite** (`maccre_core/tools/*`), **Omni-Dashboard** (`maccre_dashboard/`), and **Key Automation & Diagnostic Scripts** (`scripts/*`). 

---

## SECTION 1: TOOL EXECUTION SUITE (`maccre_core/tools/*`)

### 1.1 Tool Registration & Manifest Dispatch (`tool_registry.py`)
Central single-source-of-truth registry mapping all 40+ atomic functions into a unified tool dispatcher (`TOOL_DISPATCHER`, `get_tools_for_tier`, `generate_universal_json_schema`).

### 1.2 Sovereign RAG & Vector Engine (`rag_tools.py`)
Multi-tiered (L1 Session, L2 Project, L3 Global) hybrid memory engine combining OS Vault-authenticated 256-dim embeddings with SQLite FTS5 BM25 full-text indexing (`ingest_document`, `query_local_memory`, `fts_search_memory`, `iterative_scoped_search`, `canonize_session`, `import_foreign_vectors`).

### 1.3 Dual-Pipeline Media Render Executor (`render_executor.py`)
Converts Director JSON manifests into synchronized TTS audio and image slideshows via FFmpeg (`CloudMediaPipeline`, `execute_render_pipeline`, `render_podcast_audio`, `render_video`, `render_image`).

### 1.4 Swarm Design Engine & Diamond Loop (`design_tools.py`)
Transforms natural language requests into materialized MACCRE swarm workspaces using the Diamond Loop architecture (Generator temp=1.0, Critic temp=0.1 + Pydantic schema).

### 1.5 Admin & Swarm Lifecycle Orchestration (`admin_tools.py`)
Administrative project provisioning (`initialize_workspace`), agent roster management (`mint_agent`), topology compilation (`build_topology`), and inline swarm execution (`ignite_swarm`, `run_swarm`).

### 1.6 FinOps Engine & Pricing Matrix (`finops_tools.py`)
Real-time token cost calculation (`PRICING_MATRIX`), pre-flight estimation (`calculate_predicted_cost`), and post-session double-entry financial reconciliation (`reconcile_session_finops`).

### 1.7 Cross-Device Database Nugget Sync (`sync_tools.py`)
Zero-server cross-device synchronization of cognitive memory snapshots via Google Drive (`export_project_nugget`, `import_project_nuggets`).

### 1.8 Excel Sheet Parser & Materializer (`sheet_parser.py`)
High-fidelity parser converting `MACCRE_Swarm_Request.xlsx` workbooks into materialized swarm configurations and sidecar files (`parse_workbook`, `materialise_from_sheet`).

### 1.9 Workbook Completeness & FinOps Engine (`workbook_engine.py`)
Pre-flight validation and section readiness scoring for Excel workbooks (`check_workbook_completeness`, `render_execution_plan`).

### 1.10 Telemetry Matrix & RBAC Confinement (`telemetry_tools.py`)
RBAC-enforced telemetry querying (`query_telemetry_matrix`, `query_thoughts`) and workspace path boundary inspection (`read_local_codebase`).

---

## SECTION 2: MACCRE DASHBOARD (`maccre_dashboard/`)
- **FastAPI Backend (`backend/main.py`)**: Real-time REST API and ZeroMQ PUB/SUB control server (`tcp://127.0.0.1:5557`) for pause/resume/nudge interrupts, project switching, and topology compilation.
- **Frontend Architecture (`frontend/src/`)**: React Flow visual canvas (`Miniboard.tsx`), custom node rendering (`AgentNode.tsx`), live telemetry terminal (`SwarmMonitorTerminal.tsx`), and nudge modal (`NudgeModal.tsx`).

---

## SECTION 3: KEY AUTOMATION & DIAGNOSTIC SCRIPTS (`scripts/`)
- **Gemma 1 Local Swarm (`scripts/gemma1_swarm.py`)**: Demonstrates local air-gapped compute capabilities using Gemma 3:4b via Ollama REST API.
- **Autonomous Micro-Test Suite (`scripts/maccre_micro_test.py`)**: Comprehensive 14-Phase diagnostic harness testing all 28 MCP tool implementations directly under 30-second timeouts.
- **EXO_TEST Workbook Generator (`scripts/build_exo_test_workbook.py`)**: Generates and populates `__DATACENTER/EXO_TEST/MACCRE_Swarm_Request.xlsx` with the canonical 7-node production pipeline.
