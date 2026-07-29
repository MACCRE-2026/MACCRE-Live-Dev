# EXO_GANS / MACCREv2 (Sovereign Edge Orchestrator)

> **v0.1.0-alpha** — *Active Solo Development · Law Rev 19.0 Compliance*

EXO_GANS (MACCREv2) is a Sovereign Edge multi-agent orchestrator built around a strict, deterministic control flow architecture.

It was built to solve a fundamental flaw in modern agentic software: as AI models become more capable, frameworks built around them increasingly cede workflow routing and state control to non-deterministic intelligence. EXO_GANS rejects this paradigm. It acts as an iron-clad General Contractor, providing rigid, auditable, deterministic scaffolding around highly specialized AI sub-contractors.

---

## 1. Core Philosophy: The Sovereign Edge Omni-Builder Doctrine

The framework operates under four inviolable physical laws:

- **Law I: Sovereign Prefix Mandate (`omni`)**: Direct execution of Python scripts via bare `python` is strictly prohibited. All execution, linting, testing, and compilation MUST be routed through the global `omni` daemon (`omni run`, `omni qa`, `omni build`, `omni clean`).
- **Law II: Strict Datacenter Silo Routing**: All file I/O operations are strictly partitioned across 5 designated datacenter silos (`01_Raw_Source` through `05_Rendered_Media`). Hard destructive file deletions are outlawed; files are moved safely using `access_control.trash_file()`.
- **Law III: Zero-Leak RAM Key Purging**: API key credentials loaded from local key vaults are held in memory only for the duration of the API call and immediately wiped post-execution via CPython memory zeroing (`ctypes.memset`).
- **Law IV: Canonical Path Anchoring (`get_maccre_root`)**: Absolute file paths are strictly banned in source files. All relative paths derive at runtime from `get_maccre_root()` in `maccre_core/utils/path_resolver.py`.

---

## 2. System Architecture & 6-Plane Overview

```
                                  [ OPERATOR / INTERFACE LAYER ]
                                +----------------------------------+
                                |  Textual NexusPlex TUI & Copilot |
                                |  FastAPI / React Miniboard       |
                                +----------------+-----------------+
                                                 |
                                                 v
                                   [ CONTROL & ROUTING PLANE ]
                                +----------------------------------+
                                | FlowEngine Supervisorship        |
                                | TopologyEngine & 7-Point Audit   |
                                +----------------+-----------------+
                                                 |
                                                 v
                                   [ STATE MACHINE & BROKER ]
                                +----------------------------------+
                                | LocalMessageBroker (swarm_queue) |
                                | SQLite WAL Concurrency Locks     |
                                +----------------+-----------------+
                                                 |
                                                 v
                                  [ EXECUTION & WORKER LOOPS ]
                                +----------------------------------+
                                | UniversalSwarmWorker Loop        |
                                | UniversalRouter (Net / Models)   |
                                +--------+----------------+--------+
                                         |                |
                     +-------------------+                +-------------------+
                     |                                                        |
                     v                                                        v
      [ COGNITIVE & TOOL PLANE ]                               [ STATE & SECURITY PLANE ]
+----------------------------------+                      +----------------------------------+
| 61 Atomic Tool Dispatcher        |                      | 5-Tier Datacenter Silos          |
| Sovereign RAG Hybrid Search      |                      | Federated OS/Fernet Vault        |
| Dual-Pipeline Media Render Exec  |                      | 4-Silo Telemetry Matrix          |
+----------------------------------+                      +----------------------------------+
```

---

## 3. Subsystem Architecture

### 3.1 Net & Client Subsystem (`maccre_core/_net/`)
- **Zero-SDK REST Mandate**: All Gemini model inference (`gemini_client.py`), batch embedding generation, and model metadata requests flow through a custom standard library REST client (`GeminiClient`) using Python's native `urllib`. Core REST operations use zero third-party dependencies. *(Exception: `live_client.py` utilizes the official SDK strictly for Gemini Live API WebSockets).*
- **Surface Taxonomy (`model_registry.py`)**: Categorizes 55+ Gemini models into 13 specialized capability surfaces (`TEXT_GENERATION`, `DEEP_RESEARCH`, `TTS`, `IMAGEN`, `VIDEO`, etc.) with automated surface failover chains.
- **Active Model Sentinel (`model_sentinel.py`)**: Background thread daemon (`get_sentinel()`) that probes active model endpoints every 1800s, tracking latency and error rates in `system_logs.db` to automatically re-route tasks around degraded API surfaces.
- **Hardware Probing & Ollama Matrix (`environment_probe.py`)**: Probes host system hardware (VRAM, CPU cores, active Ollama services) to dynamically route cognitive tasks between cloud Gemini APIs and air-gapped local models (`gemma3:9b`, `llama.cpp`).
- **Sovereign OOXML Builder (`ooxml.py`)**: Write-only OOXML `.xlsx` spreadsheet generator built on standard library `zipfile` and `xml.etree.ElementTree`, enabling zero-dependency workbook creation.

### 3.2 Swarm Engine & Orchestration Subsystem (`maccre_core/orchestration/`)
- **FlowEngine Supervisorship (`flow_engine.py`)**: Manages multi-agent execution cycles, handles state transitions (`Idle` -> `Running` -> `Paused` -> `Canonized`), tracks node lineage via `flow_vector`, and synthesizes unified session ledgers.
- **The 16 Deterministic ControlNode Primitives (`deterministic_nodes.py`)**: Executes structural control logic (`CTRL_ANCHOR`, `CTRL_RECURSION`, `CTRL_PAUSE`, `CTRL_GATE`, `CTRL_CHECKPOINT`, `CTRL_DELAY`, `CTRL_TRANSFORM`, `CTRL_SCATTER`, `CTRL_MERGE`, `CTRL_CONCAT`, `CTRL_BRANCH`, `CTRL_FILTER`, `CTRL_CLEANUP`, `CTRL_CONDITIONAL_ROUTE`, `CTRL_END`, `CTRL_PAYLOAD_INJECT`) in native Python without invoking LLM models.
- **Quadrivector Failback Routing (`CTRL_CONDITIONAL_ROUTE`)**: 4-stage priority fallback hierarchy (Structured `[ROUTE_TO:]` Tag -> Keyword Regex Gate -> Confidence Score Threshold -> Fuzzy Levenshtein Match -> Default Target).
- **SQLite WAL Scatter-Gather Queue (`local_broker.py`)**: SQLite-backed zero-cloud task queue (`swarm_queue.db`) using `UNIQUE(job_id, current_node)` and `INSERT OR IGNORE` to guarantee idempotent fan-in gather routing, and `BEGIN EXCLUSIVE` locks to prevent worker thread races.
- **7-Point Pre-Flight Topology Audit (`topology_engine.py`)**: Validates prompts, model IDs, temperature ranges, DAG target references, wait-for dependencies, circular deadlock loops, and dialogue partner roster registrations prior to flow execution.

### 3.3 Textual NexusPlex Command Center (`maccre_tui/`)
- **Split-Pane Terminal UI (`nexus_plex.py`)**: Terminal-native interface built on Textual and Rich featuring an accordion `InformationPanel`, live `FlowMonitorOverlay`, `NexusChat` copilot, tabbed `NodeCatalog`, and interactive `TopologyVisualizer`.
- **Interactive VCR Transport State Machine**: Controls execution flow in 3 states (`Idle`, `Running`, `Paused`). In **Paused State** (triggered manually or by `CTRL_PAUSE`/`CTRL_REVIEW`), the worker thread blocks on a `FlowPauseEvent` lock, enabling step injection (`ContextInjectModalScreen`), live single-node chat (`NodeLiveChatModal`), and time-travel step branching.
- **Agent Studio & Session Bridge Compiler (`AgentStudioChatScreen`)**: 3-panel arena for unstructured multi-agent brainstorming (`ChatDashboardPane`, `ChatArenaPane`, `ChatBuilderPane`) with a built-in compiler that parses chat transcripts into executable Flow Sequence DAG topologies.
- **21 Modal Dialog Screens**: Fullscreen modals covering template editing (`MacroNodeEditorModal`), session canonization (`SessionManagerModal`), financial ledgers (`OnionBookModal`), and project memory inspection (`ProjectCanonModal`).

### 3.4 Tools, Sovereign RAG & Media Engine (`maccre_core/tools/`)
- **61 Atomic Tool Dispatcher (`tool_registry.py`)**: Central registry mapping 61 GUI-agnostic functions across 11 modules with tier-aware filtering (`get_tools_for_tier`) and dynamic OpenAPI/Anthropic/OpenAI/Ollama schema generation (`generate_universal_json_schema`).
- **Sovereign RAG Hybrid Search (`rag_tools.py`, `hybrid_search.py`)**: Tri-fold retrieval engine combining `SovereignPinStore` 256-dim vector embeddings (`gemini-embedding-001`), SQLite FTS5 BM25 full-text indexing, and live Brave web search fused via Reciprocal Rank Fusion (RRF).
- **Dual-Pipeline Media Render Executor (`render_executor.py`)**: Converts Director JSON manifests into synchronized TTS audio (`05_Rendered_Media/audio/`), Imagen 3 graphics (`05_Rendered_Media/images/` with automated `imagen-3.0-generate-002` API failover), and stitched FFmpeg `.mp4` video (`05_Rendered_Media/video/`).
- **Excel Workbook Intake Pipeline (`sheet_parser.py`, `workbook_engine.py`)**: Active intake engine converting `MACCRE_Swarm_Request.xlsx` workbooks into materialized agent rosters and topology JSON configurations with pre-flight readiness scoring (`check_workbook_completeness`).

### 3.5 State, Security & Sovereignty Architecture (`maccre_core/`)
- **3-Tier Access Control Matrix (`access_control.py`)**: Progressive elevation hierarchy enforcing Tier 1 read-only baseline, Tier 2 salted SHA-256 PIN elevation for non-sandboxed modifications, and Tier 3 headless MCP token bypass (`activate_mcp_bypass`).
- **Archive Trash Protocol (`trash_file()`)**: Destructive file deletions are prohibited; files are timestamped (`%Y%m%dT%H%M%SZ__`) and relocated to `_archive/trash/` with audit logging in `system_logs.db`.
- **4-Silo SQLite WAL Telemetry Matrix (`telemetry_db.py`)**: Four dedicated SQLite WAL databases (`system_logs.db`, `user_interactions.db`, `terminal_logs.db`, `definitions.db`) for system lifecycle auditing, human-in-the-loop tracking, stdio capture, and metadata storage.
- **Federated OS/Fernet Vault (`windows_vault.py`, `universal_vault.py`, `key_ingestor.py`)**: Native Windows DPAPI integration (`CryptProtectData`), Fernet AES-128 fallback (`auth_vault.bin`), automatic key regex pattern ingestion, Win32 clipboard sanitization, and CPython RAM memory zeroing (`ctypes.memset`).
- **Omni CI/CD Gatekeeper (`omni`)**: Global JIT gatekeeper enforcing `omni run` execution, `omni qa` Ruff/Pyright quality checks, `omni build` PyInstaller compilation, and `omni clean` cache/zombie thread purging.

---

## 4. Project Status & Contributing

This project is in active, daily solo development. It is highly opinionated and tailored to a specific architectural vision.

- **Issues**: Bug reports and architectural discussions are welcome.
- **Pull Requests**: Please do not submit unsolicited PRs. Open an issue to discuss your proposed changes first. See [CONTRIBUTING.md](CONTRIBUTING.md) for details.

---

## 5. Licensing (AGPLv3 Dual-License)

This software is released under the **GNU Affero General Public License v3.0 (AGPLv3)**.

### Why AGPLv3?
EXO_GANS is designed to be free and open for developers, researchers, and hobbyists to use, modify, and learn from. However, if a commercial entity wishes to run this software over a network (e.g., as a backend SaaS or internal proprietary infrastructure), the AGPL requires them to open-source their entire modified stack.

**Commercial Licensing:**  
If your organization's legal policies prohibit the use of AGPL-licensed code, or if you wish to use EXO_GANS in a proprietary commercial product without open-sourcing your stack, a commercial license is required. Please contact the author directly to negotiate commercial terms.
