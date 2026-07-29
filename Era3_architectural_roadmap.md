# MACCREv2 / EXO_GANS: Era 3 Master Architectural Roadmap

> **Authoring Swarm:** 5 Specialist Alphabet Oracles (`NetAndClient_Oracle`, `OrchestrationAndEngine_Oracle`, `TUIAndInterface_Oracle`, `ToolsAndRAG_Oracle`, `StateAndSovereignty_Oracle`)  
> **Source Analysis Scope:** 12 Active & Historical Roadmap Documents (`ctrl_scatter-expansion plan-v3.md`, `Era2_architectural_roadmap.md`, `Phase4_75_6-CompletionWalkthrough.md`, `ctrl_neural_topology_assessment.md`, `neural_topology_assessment.md`, `FeatureRequests.md`, `EXO_GANS_Wishlist_Architecture.md`, `TUI_REFACTOR_PLAN.md`, `PhASE5-implementation_plan-FinalDraft.md`, `DETplanning-TUI Refactor-FinalDraft.md`, `MajorAgentChat-Victory_d6adb53.md`, `ReFactor_Redux-1a933d9.txt`)  
> **Date:** 2026-07-25 · **Compliance Standard:** Sovereign Edge Omni-Builder Doctrine & Law Rev 19.0  

---

## EXECUTIVE SUMMARY & SYSTEM VISION

MACCREv2 / EXO_GANS has evolved from a linear Flow Line pipeline into an unrolled Directed Acyclic Graph (DAG) orchestration engine. It rejects the paradigm of ceding control flow to non-deterministic LLMs, acting instead as an iron-clad **General Contractor** that enforces rigid, auditable, deterministic scaffolding around cognitive AI sub-contractors.

This document unifies all historical achievements (Era 1 & Era 2), audits carryover items from prior development phases, and establishes the definitive **Era 3 Architectural Roadmap** (Phases 6 through 9).

```
+-----------------------------------------------------------------------------------+
|                        ERA 3 SOVEREIGN EDGE ARCHITECTURE                          |
+-----------------------------------------------------------------------------------+
| 1. NET & CLIENT         - Pure urllib REST, ModelSentinel, Ollama & S25 NPU Mesh  |
| 2. SWARM ENGINE         - 17 CTRL_ Primitives, Quadrivector Failback, WAL Queues   |
| 3. NEXUS PLEX TUI       - Topology-First, Paused VCR Stepping, 60FPS State Buffer|
| 4. TOOLS, RAG & MEDIA   - 61 Tool Dispatcher, FTS5+Vector RRF, Temporal Video Ext  |
| 5. STATE & SOVEREIGNTY  - 5 Datacenter Silos, 3-Tier PIN Elevation, omni audit daemon|
| 6. PHASE 9 BRIDGE       - In-State Live Dev, Antigravity Desktop Import & Living Git|
+-----------------------------------------------------------------------------------+
```

---

## MASTER SUBSYSTEM STATUS & ERA 3 ROADMAP MATRIX

| Subsystem Scope | Implemented Bedrock (Era 1 & 2) | Unfinished / Carryover Items | Era 3 Strategic Goals & Phase 9 Addition |
| :--- | :--- | :--- | :--- |
| **Net & Client** | Pure `urllib` REST client, Gemini 3.x `thinkingConfig`, `ModelSentinel` latency tracking, 55+ model surface taxonomy, zero-dep OOXML builder, RAM key zeroing (`ctypes.memset`). | Mobile S25 NPU edge sync, GeminiClient SSE streaming, multi-provider model failover, FinOps pre-flight cost gates. | HTTP/2 pure Python multiplexing, zero-dependency P2P S25 NPU mesh, hardware-aware load balancer, **Phase 9 Bi-Directional JSONL-to-REST Translator & `DeploymentCandidateTester`**. |
| **Orchestration & Engine** | 17 deterministic `CTRL_` primitives, `FlowEngine` supervisorship, SQLite WAL scatter-gather queue (`swarm_queue.db`), Quadrivector failback routing, 7-point pre-flight validator. | Live graph cell patching, `ThreadPoolExecutor` parallel scatter, SQLite WAL sharding by flow line, multi-predicate `CTRL_GATE` arrays. | Time-travel branch isolation replay, agent perspective simulation, counterfactual flow execution, biological neural circuit motifs, **Phase 9 `shutil.copy2` Candidate Sandboxes & Trajectory Replay as `CTRL_` DAGs**. |
| **TUI & Command Center** | NexusPlex split-pane grid, interactive VCR transport state machine (Idle/Running/Paused FlowStasis), step context injection, live node chat, Agent Studio 3-panel arena, Session Bridge Compiler, Rich Tree `TopologyVisualizer` (0.2s pulse), 21 modals. | Drag-and-drop wiring canvas, real-time multi-agent audio chat overlay, sparkline telemetry charts, mobile TUI C2 bridge, `NodeConfig` overlay conversion, marching-ants flow wires. | Event-driven asynchronous state container (`@work(thread=True)` 60FPS rendering), dynamic neural topology canvas, time-travel scrubber, **Phase 9 In-State Live Dev Chat Studio & File Cabinet Antigravity Importer**. |
| **Tools, RAG & Media** | 61 atomic tool dispatcher, Sovereign RAG FTS5 BM25 + vector + Brave web RRF fusion (`hybrid_search.py`), dual-pipeline media render executor (TTS/Imagen 3/FFmpeg stitcher), Excel workbook intake materializer. | CollectionLM offline ingestion CLI, Visionary Scout visual extraction (Phase 5.1), real-time voice streaming, temporal extrapolation I2V (Phase 5.3), auto-tool synthesis. | CollectionLM sovereign knowledge compiler, self-synthesizing tool factory, multimodal real-time streaming, **Phase 9 Workspace Ingestion (`antigravity_ingestor.py`) & AST-Aware Codebase RAG Indexer**. |
| **State & Sovereignty** | 5-tier datacenter silos (`01_Raw_Source` ... `05_Rendered_Media`), runtime path anchoring (`get_maccre_root()`), 3-tier access control PIN elevation, archive trash protocol (`trash_file()`), DPAPI + Fernet key vaults, 4-silo SQLite WAL telemetry matrix, `omni` CLI. | Encrypted P2P memory nugget sync, hardware TPM 2.0 enclave vault, Merkle tree cryptographic execution logging, multi-tenant workspace sandboxing. | Zero-trust P2P node attestation mesh, TPM 2.0 hardware key binding, Merkle proof-of-execution ledgers, automated `omni audit` daemon, **Phase 9 5-Tier Datacenter Transmutation Engine (`fork_datacenter()`) & 1:1 Antigravity Structural Mapping**. |

---

## SECTION 1: NET & CLIENT SUBSYSTEM ROADMAP (`maccre_core._net`)

### 1.1 Implemented Bedrock
- **Sovereign REST Client (`gemini_client.py`)**: Pure standard library `urllib.request` implementation for Google Generative Language REST API (`generateContent`, `streamGenerateContent`, `embedContent`, File API, Context Caching, Model Listing). Zero third-party SDK dependencies (`google-genai`, `requests`, `httpx`).
- **Thinking Config Injection (`gemini_client.py` & `ReFactor_Redux-1a933d9.txt`)**: Native API-level `thinkingConfig` (`thinking_budget`/`thinking_level`) for Gemini 3.x models (`gemini-3.1-pro-preview`, `gemini-3.5-flash`), returning 3-item tuples `(output_text, cost, api_thought)`.
- **Model Sentinel & Surface Taxonomy (`model_sentinel.py`, `model_registry.py`)**: Thread-safe daemon probing models every 1800s, tracking latency/errors in `system_logs.db`, and managing failover chains across 13 capability surfaces.
- **Sovereign OOXML Builder (`ooxml.py`)**: Zero-dependency `.xlsx` workbook generator built on standard library `zipfile` and `xml.etree.ElementTree`.
- **RAM Key Sanitization**: API key byte buffers zeroed out post-call via `ctypes.memset`.

### 1.2 Unfinished & Carryover Items
- **Mobile Edge NPU Cluster Integration (`CTRL_EDGE_SYNC`)**: Offloading inference tasks to mobile devices (e.g. Samsung S25 Ultra NPU) via folder sync watchdog.
- **GeminiClient SSE Token Streaming**: Standard library Server-Sent Events (SSE) stream parser for `streamGenerateContent`.
- **Multi-Provider Cross-Tier Failover**: Fallback routing from Gemini Cloud APIs to local Ollama clusters upon 429/503 rate limits.
- **FinOps Pre-Flight Estimation Gates**: Pre-call cost interceptor emitting `ManualInputRequired` pauses prior to high-burn execution.

### 1.3 Era 3 Architectural Goals & Phase 9 Expansion
1. **Zero-Dependency Pure Python HTTP/2 Multiplexing Engine**: Upgrade `gemini_client.py` to support HTTP/2 multiplexing and streaming WebSockets using standard library `ssl` and `socket` wrappers.
2. **S25 NPU Edge Swarm Peer-to-Peer Mesh**: Encrypted socket mesh between host instances and mobile NPU clusters for sub-100ms local gate evaluations (`CTRL_GATE`).
3. **Hardware-Aware Real-Time Load Balancer**: Dynamic compute routing balancing local VRAM/CPU headroom against cloud Gemini API rate limits.
4. **Phase 9 JSONL Transcript Translator (`JsonlTranscriptTranslator`)**: Bi-directional translator converting Antigravity `transcript_full.jsonl` files into standard REST payloads and mapping Gemini 3-tuples `(output_text, cost, api_thought)` into structured turn entries.
5. **Phase 9 Automated Candidate Tester (`DeploymentCandidateTester`)**: Zero-SDK automated pre-flight testing harness for evaluating candidate model endpoints prior to production promotion.

---

## SECTION 2: SWARM ENGINE & ORCHESTRATION ROADMAP (`maccre_core/orchestration/`)

### 2.1 Implemented Bedrock
- **17 Deterministic ControlNode Primitives (`deterministic_nodes.py`)**: Token-free structural nodes (`CTRL_ANCHOR`, `CTRL_RECURSION`, `CTRL_PAUSE`, `CTRL_GATE`, `CTRL_CHECKPOINT`, `CTRL_DELAY`, `CTRL_TRANSFORM`, `CTRL_SCATTER`, `CTRL_MERGE`, `CTRL_CONCAT`, `CTRL_BRANCH`, `CTRL_FILTER`, `CTRL_CLEANUP`, `CTRL_CONDITIONAL_ROUTE`, `CTRL_END`, `CTRL_PAYLOAD_INJECT`, `CTRL_REVIEW`).
- **Quadrivector Failback Routing (`CTRL_CONDITIONAL_ROUTE`)**: 4-stage priority router: Structured Output Pass 2 -> Keyword Gate -> Score Threshold -> Fuzzy Levenshtein Match ($\le 2$) -> Default Target.
- **SQLite WAL Scatter-Gather Queue (`local_broker.py`)**: Zero-cloud task queue (`swarm_queue.db`) using `UNIQUE(job_id, current_node)` and `INSERT OR IGNORE` for idempotent fan-in gathering, `flow_line_id` parentage tracking, and `flow_vector` lineage logging.
- **7-Point Pre-Flight Validator (`topology_engine.py`)**: Pre-execution audit verifying prompt presence, valid model IDs, temperature bounds ($[0.0, 2.0]$), target node existence, wait-for tethers, circular deadlock safety, and dialogue partner roster alignment.

### 2.2 Unfinished & Carryover Items
- **Mid-Execution Live Graph Cell Patching**: Dynamic modification of running topology graphs (`patch_node()`) without restarting flow sessions.
- **ThreadPoolExecutor Parallel Scatter**: Parallel thread dispatch (`max_workers=8`) for multi-branch `CTRL_SCATTER` execution.
- **SQLite WAL Sharding by Flow Line**: Partitioning `task_queue` across dedicated DB files (`swarm_queue_fl_<id>.db`) to eliminate write contention.
- **Multi-Predicate `CTRL_GATE` Arrays**: Complex gate evaluation supporting `predicates[]` arrays (`all`/`any` logic).

### 2.3 Era 3 Architectural Goals & Phase 9 Expansion
1. **Sovereign Time-Travel Replay & Branch Isolation**: Parsing `flow_vector` lineage strings to reconstruct step-by-step session timelines, step through historical payload entry/exit snapshots, and execute zero-cloud database forks (`shutil.copy2`).
2. **Agent Perspective Simulation ("Fly on the Wall")**: Reconstructing an agent's chronological operational trace across disparate scatter branches, compiling synthetic context vectors that future agents absorb as telemetric memory.
3. **Biological Neural Circuit & Ganglia Evolution**: Formalizing MacroNodes as autonomous processing hubs (ganglia), establishing Hebbian topological learning (`fork_synthesizer.py`), and enabling dopaminergic inter-gate neuromodulation via `SET_GATE` commands.
4. **Phase 9 Frozen State Sandboxing (`CandidateSandboxManager`)**: Clones active state via `shutil.copy2` into isolated candidate sandboxes (`02_Dynamic_Context/sandboxes/candidate_<id>/`) to test self-improvements with zero side effects on production databases.
5. **Phase 9 Antigravity Trajectory Replay Engine (`TrajectoryCompiler`)**: Converts raw Antigravity tool call streams and transcripts into optimized `CTRL_` ControlNode DAG topologies.
6. **Phase 9 Living Local Git System Evolution**: Integrates an embedded Git engine (`git_engine.py`) into `flow_engine.py` that automatically commits successful in-state candidate deployments and session milestones.

---

## SECTION 3: TEXTUAL NEXUSPLEX TUI & COMMAND CENTER ROADMAP (`maccre_tui/`)

### 3.1 Implemented Bedrock
- **Split-Pane Command Center (`nexus_plex.py`/`nexus_plex.css`)**: Responsive layout containing the 6-accordion `InformationPanel`, live `FlowMonitorOverlay`, `NexusChat` copilot, `NodeCatalog`, `TopologyVisualizer`, and VCR transport toolbar.
- **Interactive VCR Transport State Machine**: Tri-state control (`Idle`, `Running`, `Paused`/`FlowStasis`). In **Paused State**, worker threads block on a `FlowPauseEvent` lock, enabling radio-dot step selection, mid-flow context injection (`ContextInjectModalScreen`), live single-node chat (`NodeLiveChatModal`), and time-travel step branching.
- **Agent Studio 3-Panel Arena (`AgentStudioChatScreen`)**: Unstructured multi-agent chat arena (`ChatDashboardPane`, `ChatArenaPane`, `ChatBuilderPane`) with a built-in **Session Bridge Compiler** converting chat transcripts into executable Flow Sequence DAG topologies.
- **Rich Tree `TopologyVisualizer` (`topology_visualizer.py`)**: Dynamic Rich Tree rendering with 0.2s pulsing active node animation, color-coded node states, tether badges (`[tether:id]`), and default expanded hierarchy unrolling.
- **21 Modal Screens Catalog**: Comprehensive fullscreen modal stack covering template editing, session canonization, FinOps ledgers, and 16/16 `CTRL_` node configuration fields.

### 3.2 Unfinished & Carryover Items
- **Visual Graph Drag-and-Drop Wiring Canvas**: Replacing keyboard shortcut node moving (`Ctrl+Up`/`Down`) with interactive mouse drag-and-drop node reordering and graph wiring.
- **Real-Time Multi-Agent Audio Chat Overlay**: Gemini Multimodal Live WebSocket audio stream integration into `ChatArenaPane` with waveform visualizers.
- **Sparkline & Bar Chart Telemetry Widgets**: Native Rich/Textual sparkline rendering of token burn rates, node latency, and hardware VRAM/CPU metrics.
- **Mobile TUI Remote Bridge**: Evolving `LiveSwarmTUI` into a secure WSS remote bridge for mobile web/terminal C2 monitoring.

### 3.3 Era 3 Architectural Goals & Phase 9 Expansion
1. **Event-Driven Asynchronous State Container**: Offloading database polling to Textual Workers (`@work(thread=True)`) and rendering UI exclusively from an in-memory state buffer to achieve smooth 60 FPS terminal performance.
2. **Dynamic Neural Topology Canvas**: Spatial circuit visualizer mapping `CTRL_` primitives to biological motifs (axonal scatter, dendritic merge, synaptic gating) and MacroNodes to autonomous Ganglia handles.
3. **Phase 9 In-State Live Development Chat Studio (`AgentStudioChatScreen`)**: Fully wired to the 61 tool dispatcher (`tool_registry.py`), project `.venv`, and `omni run` launcher with a non-blocking `LiveConsoleOutput` terminal widget for real-time code execution.
4. **Phase 9 Antigravity File Cabinet Importer (`SessionManagerModal`)**: Upgraded session manager modal featuring an auto-discovery wizard for local Antigravity `conversations/` and `brain/` directories, transmuted into 5-tier project silos with immediate RAG indexing.

---

## SECTION 4: TOOLS, SOVEREIGN RAG & MEDIA ENGINE ROADMAP (`maccre_core/tools/`)

### 4.1 Implemented Bedrock
- **61 Atomic Tool Dispatcher (`tool_registry.py`)**: Central registry mapping 61 GUI-agnostic functions across 11 modules with tier-aware filtering (`get_tools_for_tier`) and dynamic OpenAPI/Anthropic/OpenAI/Ollama schema generation (`generate_universal_json_schema`).
- **Sovereign RAG Hybrid Search Engine (`rag_tools.py`, `hybrid_search.py`)**: Tri-fold retrieval engine combining `SovereignPinStore` 256-dim vector embeddings (`gemini-embedding-001`), SQLite FTS5 BM25 full-text indexing, and live Brave web search fused via Reciprocal Rank Fusion (RRF).
- **Dual-Pipeline Media Render Executor (`render_executor.py`)**: Storyboard-driven media generator converting Director manifests into TTS WAV audio (`05_Rendered_Media/audio/`), Imagen 3 graphics (`05_Rendered_Media/images/` with automated `imagen-3.0-generate-002` API failover), and stitched FFmpeg MP4 video (`05_Rendered_Media/video/`).
- **Excel Workbook Intake Materializer (`sheet_parser.py`, `workbook_engine.py`)**: Active intake engine converting `MACCRE_Swarm_Request.xlsx` workbooks into materialized agent rosters and topology JSON configurations with pre-flight section readiness scoring (`check_workbook_completeness`).

### 4.2 Unfinished & Carryover Items
- **CollectionLM Offline Knowledge Ingestion CLI**: Bulk dataset compiler turning massive directory trees into vectorized, offline-capable knowledge packs (`.clm`).
- **Visionary Scout Multimodal Extraction (Phase 5.1)**: Specialized visual agent extracting bounding boxes, dialogue tags, and spatial layout metadata from multi-panel media.
- **Generative Temporal Extrapolation (Phase 5.3)**: Image-to-Video (I2V) 4-second temporal prediction (2s past + 2s future) generating "live photo" animations from static visual panels.
- **Automated Tool Synthesis & Recruitment Engine**: Passive context-monitoring node dynamically generating system prompts, writing Python tools, and registering them into `tool_registry.py` and `maccre_mcp.py` at runtime.

### 4.3 Era 3 Architectural Goals & Phase 9 Expansion
1. **CollectionLM Sovereign Knowledge Engine**: Zero-cloud offline knowledge pack compiler with adaptive RRF weight tuning and automated retrieval benchmarking.
2. **Self-Synthesizing Tool Factory**: Equipping agents with meta-tools (`synthesize_mcp_tool`, `test_mcp_tool`) to author, type-check, test via `maccre_micro_test.py`, and register new tools without process restarts.
3. **Phase 9 Antigravity Workspace Ingestor (`antigravity_ingestor.py`)**: Dedicated dual-directory parser extracting turns and artifacts from Antigravity `conversations/` and `brain/` folders directly into `SovereignPinStore` (`memory_pins.db`) and FTS5 BM25 tables.
4. **Phase 9 AST-Aware Codebase RAG Indexer (`codebase_indexer.py`)**: Structural code parser using Python `ast` and symbol extractors to chunk code at function/class boundaries with SHA-256 incremental hashing to prevent redundant API calls.
5. **Phase 9 Chat Studio 61-Tool Execution Bridge (`chat_studio_bridge.py`)**: Binds all 61 atomic tools to live Chat Studio sessions targeting imported project codebases with dynamic path anchoring (`resolve_imported_project_path`).

---

## SECTION 5: STATE, SECURITY & SOVEREIGNTY ROADMAP (`maccre_core/`)

### 5.1 Implemented Bedrock
- **5-Tier Datacenter Silo Topology**: Workspace isolation under `__DATACENTER/<projectName>/` into `01_Raw_Source`, `02_Dynamic_Context`, `03_Agent_Ledgers`, `04_Code_Artifacts`, and `05_Rendered_Media`.
- **Dynamic Path Anchoring (`path_resolver.py`)**: Runtime resolution of `MACCRE_ROOT` via `get_maccre_root()`, enforcing `def __init__(self, path: str = ""): self.path = path or str(get_maccre_root() / "subdir")`.
- **3-Tier Access Control Matrix (`access_control.py`)**: Progressive elevation hierarchy enforcing Tier 1 read-only baseline, Tier 2 salted SHA-256 PIN elevation for non-sandboxed modifications, and Tier 3 headless MCP token bypass (`activate_mcp_bypass`).
- **Archive Trash Protocol (`access_control.trash_file()`)**: Destructive file deletions are prohibited; files are timestamped (`%Y%m%dT%H%M%SZ__`) and relocated to `_archive/trash/` with audit logging in `system_logs.db`.
- **4-Silo SQLite WAL Telemetry Matrix (`telemetry_db.py`)**: Dedicated WAL databases (`system_logs.db`, `user_interactions.db`, `terminal_logs.db`, `definitions.db`).
- **Federated Vault & RAM Key Purging**: Windows DPAPI integration (`windows_vault.py`), Fernet AES-128 fallback (`universal_vault.py`), key regex pattern fingerprinting (`key_ingestor.py`), Win32 clipboard clearing (`clear_windows_clipboard()`), and CPython RAM memory zeroing (`ctypes.memset`).
- **Omni CI/CD Gatekeeper (`omni`)**: Global JIT gatekeeper enforcing `omni run`, `omni qa`, `omni build`, and `omni clean`.

### 5.2 Unfinished & Carryover Items
- **Encrypted Peer-to-Peer Memory Sync**: P2P snapshot sync across local nodes and mobile edge devices without cloud servers.
- **Hardware TPM 2.0 / Secure Enclave Vault Integration**: Binding Fernet master keys directly to host hardware TPM 2.0 chips.
- **Merkle Tree Execution Lineage Auditing**: Wrapping `flow_vector` entries into tamper-evident SHA-256 Merkle logs.
- **Multi-Tenant Workspace Sandboxing**: Process-isolated execution for parallel multi-tenant project swarms.

### 5.3 Era 3 Architectural Goals & Phase 9 Expansion
1. **Zero-Trust Cryptographic P2P Mesh & Node Attestation**: Encrypted P2P mesh using mDNS and TLS 1.3 mutual authentication for air-gapped node coordination.
2. **Hardware TPM 2.0 & Ephemeral Key Enclave**: TPM 2.0 key binding paired with context-managed `SovereignKeyEnclave` RAM zeroing blocks.
3. **Automated Sovereignty Audit Daemon (`omni audit`)**: New `omni audit` command scanning codebases for unauthorized SDK imports, hardcoded absolute paths, un-sanitized key buffers, and un-anchored file I/O operations prior to build compilation.
4. **Phase 9 5-Tier Datacenter Transmutation Engine (`fork_datacenter()`)**: Safe cloning and structural transmutation of external Antigravity `conversations/` and `brain/` directories into MACCRE-compliant 5-tier datacenter project silos.
5. **Phase 9 Omni CI/CD Test Topology Harness (`omni test`)**: Command addition to `omni` CLI daemon executing built-in test topologies (`CTRL_TEST_HARNESS`) to validate containerized frozen state deployment candidates before production promotion.

---

## SECTION 6: PHASED IMPLEMENTATION TIMELINE FOR ERA 3

```
+-----------------------------------------------------------------------------------+
|                            ERA 3 EXECUTION TIMELINE                               |
+-----------------------------------------------------------------------------------+
| PHASE 6: HIGH-PERFORMANCE ENGINE & TUI REFINEMENT                                  |
|   - ThreadPoolExecutor parallel scatter execution (max_workers=8)                 |
|   - SQLite WAL sharded task queues (swarm_queue_fl_<id>.db)                        |
|   - Event-driven asynchronous TUI state container (@work(thread=True) 60FPS UI)   |
|   - NodeConfig overlay conversion & inline control node field editing             |
|   - CollectionLM bulk offline knowledge compiler CLI                              |
|                                                                                   |
| PHASE 7: NEURAL CIRCUIT MOTIFS & TIME-TRAVEL REPLAY                               |
|   - Biological circuit motif mapping (axonal scatter, synaptic gating)            |
|   - Time-travel lineage scrubber & counterfactual visual diff viewer             |
|   - Multi-predicate CTRL_GATE arrays & dopaminergic SET_GATE modulation           |
|   - Self-synthesizing tool factory & FastMCP dynamic registration                 |
|   - Visionary Scout multimodal visual extraction (Phase 5.1)                      |
|                                                                                   |
| PHASE 8: ZERO-TRUST EDGE MESH & TEMPORAL EXTRAPOLATION                            |
|   - S25 NPU mobile edge P2P socket mesh (CTRL_EDGE_SYNC v2)                       |
|   - Hardware TPM 2.0 / Secure Enclave vault binding                               |
|   - Cryptographic Merkle tree proof-of-execution ledgers                          |
|   - Generative Temporal Extrapolation (2s past + 2s future live photo I2V)        |
|   - Automated omni audit sovereignty compliance daemon                            |
|                                                                                   |
| PHASE 9: IN-STATE LIVE DEVELOPMENT & ANTIGRAVITY DESKTOP TRANSITION BRIDGE        |
|   - Deprecation of Antigravity desktop in favor of in-state live development      |
|   - Interactive live tool execution & venv code runner in AgentStudioChatScreen   |
|   - 5-tier datacenter project transmutation engine (fork_datacenter())              |
|   - 1:1 structural mapping matrix (conversations/ & brain/ -> 5-tier silos)         |
|   - shutil.copy2 frozen state candidate sandboxes & omni test candidate harness   |
|   - Living local Git model for system evolution & commit-on-flow serialization   |
|   - Antigravity workspace ingestor (conversations/ & brain/ -> memory_pins.db)     |
|   - AST-aware codebase RAG indexer with SHA-256 incremental hashing               |
+-----------------------------------------------------------------------------------+
```

---

## SECTION 7: COMPETITIVE PARADIGM COMPARISON MATRIX

| Architectural Dimension | LangGraph | CrewAI | AutoGen / AG2 | MACCREv2 / EXO_GANS (Era 3) |
| :--- | :--- | :--- | :--- | :--- |
| **Control Model** | Pre-compiled Directed Cyclic Graph | Role-driven sequential / hierarchical flows | Async message-passing actor model | **Queue-Unrolled Sovereign DAG (FlowEngine Supervisor)** |
| **Routing Scaffolding** | Non-deterministic agent code functions | Implicit agent supervisor | Emergent conversational handoffs | **17 Native `CTRL_` Deterministic Primitives (Zero-Token)** |
| **Conditional Gating** | Code-level conditional edges | None | Message handler logic | **Predicate `CTRL_GATE` + `SET_GATE` Dopaminergic Modulation** |
| **Scatter / Gather** | `Send()` Map-Reduce API | Implicit task sequencing | Concurrent actor messaging | **`CTRL_SCATTER` / `CTRL_MERGE` with `tether_id` Parentage Scoping** |
| **Failback Routing** | Standard try/except | Retry loops | Agent retry prompt | **Quadrivector Failback Chain (Structured -> Keyword -> Score -> Fuzzy)** |
| **State Persistence** | External DB dependency (Postgres/Redis) | External SQLite task/flow DB | Ephemeral in-memory history | **100% Local Durable SQLite WAL + 5-Tier Datacenter Silos** |
| **Time-Travel & Replay** | Superstep Checkpointer abstraction | Limited UUID flow forks | Manual session replay | **Native `flow_vector` Lineage Replay + Scrubber + Counterfactual Diffing** |
| **System Evolution & Self-Dev**| Static code execution | Static agent workflows | Static python scripts | **Phase 9 In-State Live Development + Living Local Git + Frozen State Sandboxes** |
| **Data Sovereignty & SDKs**| Bound to LangChain ecosystem | Cloud/SaaS telemetry dependencies | Ephemeral cloud API dependencies | **100% Sovereign (Zero Third-Party SDKs, Pure `urllib`, `omni` CI/CD)** |

---

## SECTION 8: PHASE 9 DETAILED ARCHITECTURAL SPECIFICATIONS

### 8.1 Overview & Transition Strategy
Phase 9 formalizes the transition of MACCREv2 / EXO_GANS from relying on external Antigravity desktop/CLI sessions to achieving **In-State Live Development**. 

In this target status, the system is actively improved, refactored, and built from within NexusPlex TUI / Agent Studio. Proposed changes (code refactors, system prompt updates, node topology enhancements) are compiled into locally containerized frozen state deployment candidates, automatically evaluated against built-in test topologies via `omni test`, and committed directly into the live codebase using an embedded local Git engine.

### 8.2 1:1 Structural Mapping Matrix (Antigravity Desktop ➔ MACCRE Datacenter)

| Antigravity Desktop Asset | Antigravity File Path | MACCRE 5-Tier Datacenter Target Path | Data Sovereignty Tier |
| :--- | :--- | :--- | :--- |
| **Session Metadata** | `conversations/conversation_<id>.json` | `02_Dynamic_Context/{project}/as_wrapped_topology.json` | `02_Dynamic_Context` |
| **Full Trajectory Log** | `brain/<id>/.system_generated/logs/transcript_full.jsonl` | `03_Agent_Ledgers/{project}/[module]_telemetry.json` & `system_logs.db` | `03_Agent_Ledgers` |
| **Compact Trajectory** | `brain/<id>/.system_generated/logs/transcript.jsonl` | `user_interactions.db` & `terminal_logs.db` | Telemetry Silo |
| **Markdown Artifacts** | `brain/<id>/*.md` | `04_Code_Artifacts/` | `04_Code_Artifacts` |
| **Media Outputs** | `brain/<id>/*.png`, `*.mp4`, `*.wav` | `05_Rendered_Media/images/`, `video/`, `audio/` | `05_Rendered_Media` |
| **Scratch Space** | `brain/<id>/scratch/` | `02_Dynamic_Context/{project}/scratch/` | `02_Dynamic_Context` |
| **Source Code Repos** | External workspace directory | `01_Raw_Source/` & `04_Code_Artifacts/` | `01_Raw_Source` / `04_Code` |

### 8.3 In-State Live Development Chat Studio (`AgentStudioChatScreen`)
- **Interactive Tool Execution**: Binds all 61 atomic tools from `tool_registry.py` directly to active Chat Studio sessions.
- **Workspace `.venv` & `omni` Runner**: Enables agents in the arena to compile, test (`omni qa`), and run python code scripts via a non-blocking `@work(thread=True)` worker harness.
- **`LiveConsoleOutput` Terminal Widget**: Collapsible TUI widget rendering real-time stdout/stderr, ANSI colorized execution outputs, and exit codes directly inside `ChatArenaPane`.

### 8.4 File Cabinet Upgrade & Workspace Importer (`SessionManagerModal`)
- **Antigravity Auto-Discovery**: Auto-detects local Google Antigravity installations (`%USERPROFILE%\.gemini\antigravity\`), scanning `conversations/` and `brain/<id>/` directories.
- **5-Tier Datacenter Transmutation Engine (`fork_datacenter()`)**: Safely transmutes external Antigravity sessions and legacy codebases into MACCRE-compliant project silos (`01_Raw_Source` through `05_Rendered_Media`).
- **AST-Aware Codebase RAG Indexer (`codebase_indexer.py`)**: Chunks code at structural function/class boundaries and uses a SHA-256 hash manifest to prevent redundant API embedding calls.

### 8.5 Frozen State Sandboxing & Living Local Git System Evolution
- **`shutil.copy2` Database Sandboxes (`CandidateSandboxManager`)**: Candidate changes execute in `ExecutionMode.IN_STATE_TEST` against cloned SQLite queue databases (`candidate_swarm_queue.db`) inside shadowed directories (`02_Dynamic_Context/sandboxes/candidate_<id>/`).
- **Omni CI/CD Test Topology Harness (`omni test`)**: Automated command running `omni qa` and executing test topologies (`CTRL_TEST_HARNESS`).
- **Living Local Git Model (`git_engine.py`)**: Every successful in-state candidate deployment or session milestone generates an atomic local Git commit, unifying `flow_vector` lineage strings with Git commit SHA-256 hashes for immutable system auditability.
