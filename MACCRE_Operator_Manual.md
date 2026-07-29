# MACCREv2 Operator Manual
**Revision:** 2026-07-25 · Law Rev 19.0 Compliance

---

## Foreword: The Architect's Perspective

I am not a coder. I do not write in any languages. While I read them reasonably well and have a deep, long-term interest in electrical engineering and computer science, when it comes to math and code, I am syntactically disabled. For whatever reason, I have never been able to organize my thoughts natively into the abstract worlds of mathematics and programming languages. 

However, I highly respect the generations of worldwide frameworks and institutions that have been built and maintained via the rigorous minds dedicated to the refinement of human observation and prediction via the mathematic grindstone. My heroes include pioneers like Grace Hopper, Edsger Dijkstra, James Clerk Maxwell, and Michael Faraday. Their influence echoes heavily throughout the MACCRE design doctrine.

I believe that a person's ability to speak abstract languages and force their mind into rigid syntax structures should not determine the reach of their voice. Seven months ago, I began using AI to formalize my conceptual ontology into math and code. MACCRE is the direct result of formalizing my thoughts, my needs, and my impulses regarding AI into a usable platform—one where the user controls as much as possible, as economically as possible. 

MACCRE was built from my own inclinations and filtered through the different agents I designed after creating the `Prompt Engineer`. This system is a reflection of how I see the world, built by the agents who helped me express it.

---

## Part I — Core Architectural Concepts

### 1. System Vision & The "Do What You Feel" Agent Philosophy
MACCREv2 (Google Antigravity for Sovereign Edge) is an advanced multi-agent orchestration engine and TUI command center designed around deterministic scaffolding governing non-deterministic AI agents.

The bundled agents in this release were created using the `Prompt Engineer` in Chat Studio sessions. Rather than using standard industry practices (concise instructions at low temperatures), MACCRE leans into a "do what you feel" ethos. Instructions are dense, structured, and complex, and agents are run at high temperatures (`1.0` and above) to induce emergent reasoning, backed by rigid physical guardrails.

### 2. The 5-Tier Datacenter & Path Anchoring
All file paths are dynamically resolved at runtime via `get_maccre_root()` in `maccre_core/utils/path_resolver.py`, guaranteeing zero-configuration multi-drive and multi-OS portability.

Workspace data is partitioned across five deterministic datacenter silos inside `__DATACENTER/<projectName>/`:
- **`01_Raw_Source`**: Immutable ingestion zone for raw documents, payloads, and datasets.
- **`02_Dynamic_Context`**: Active project state machines, topologies, encrypted vault storage (`auth_vault.bin`), and session configs.
- **`03_Agent_Ledgers`**: Cognitive JSON ledgers (`[module_name]_telemetry.json`), execution traces, and build logs.
- **`04_Code_Artifacts`**: Sandboxed output generation zone for agent-produced Python code, markdown reports, and schemas.
- **`05_Rendered_Media`**: Generated media outputs including TTS `.wav` audio, Imagen 3 `.png` graphics, and FFmpeg `.mp4` video.

### 3. Sovereign Auth Layer & Key Ingestion
Authentication is fully localized and headless. No `.env` files are used.
- **Autonomous Key Ingestion (`key_ingestor.py`)**: Automatically scans input strings and clipboard contents for vendor API key formats (Gemini, Anthropic, OpenAI, Groq, xAI, Brave), routes them to vault storage, and purges Win32 clipboard buffers (`clear_windows_clipboard()`).
- **Federated Dual-Vault**: Utilizes native Windows DPAPI (`windows_vault.py` - `CryptProtectData`) bound to the OS user profile, with AES-128 Fernet encryption (`universal_vault.py` - `auth_vault.bin`) as cross-platform fallback.
- **CPython RAM Key Zeroing**: Plaintext API keys in memory are overwritten post-execution via `ctypes.memset`.

### 4. Local SQLite Architecture (C-Engine Concurrency)
- **`swarm_queue.db`**: Managed by `local_broker.py`. Handles scatter-gather state machines in WAL mode. Employs `UNIQUE(job_id, current_node)` and `INSERT OR IGNORE` to make fan-in gather routing strictly idempotent, with `BEGIN EXCLUSIVE` locks for atomic task fetching.
- **`thoughts.db`**: Unified matrix for storing agent cognitive scratchpads during schema-enforced inference.
- **`agent_library.db`**: Relational store for agent profiles, personas, and assigned tool sets.
- **`macronode_registry.db`**: Repository of nested topological clusters (MacroNodes) for modular drag-and-drop flow design.
- **4 Telemetry Databases (`telemetry_db.py`)**: `system_logs.db` (lifecycle & hardware), `user_interactions.db` (operator audit), `terminal_logs.db` (stdio capture), and `definitions.db` (schema & topology configs).

---

## Part II — Operational Mechanics & Flow Execution

### 1. Flow Execution & Telemetry
When a payload enters a topology, it traverses a Directed Acyclic Graph (DAG). `LocalMessageBroker` tracks payload hops on disk, updating `swarm_queue.db`. Telemetry (reasoning, API costs, latency) streams to `03_Agent_Ledgers` and `system_logs.db`.

### 2. Session Siloing & Canonization
Execution runs are siloed into unique `Session ID`s. Upon successful completion, operators can canonize a session using the CLI (`omni run maccre.py canonize --project <id> --session <id>`), locking state and elevating memory pins to `memory_pins.db`.

### 3. Bundled Topology: OSINT_Research_x3 MacroNode
The default release includes `OSINT_Research_x3`, demonstrating multi-pass research, adversarial dialogue, and synthesis:
- **Phase 1 (Dual-Pass Search)**: `OSINT_Analyst` runs `cascade_search(num_passes=2)`. Pass 1 retrieves primary web search hits; Pass 2 executes domain-exclusionary queries omitting Pass 1 domains.
- **Phase 2 (Adversarial Dialogue)**: `DialogueRunner` executes 3 conversational rounds between `OSINT_Analyst` (expert) and `Regular_Joe` (layman evaluator) to eliminate jargon and clarify missing context.
- **Phase 3 (Synthesis)**: `OSINT_Synth` ingests dialogue transcripts and writes an executive report to `04_Code_Artifacts/<job_id>/OSINT_Report.md`.

---

## Part III — TUI Navigation & Command Center Operations Manual

### 1. Launching the NexusPlex Command Center
Launch the app via the Omni Prefix Mandate:
```bash
omni run maccre_tui/nexus_plex.py
```

### 2. VCR Transport Control in Paused State (Step Injection & Live Node Chat)
Execution operates in 3 transport states (`Idle` -> `Running` -> `Paused`). When execution enters **PAUSED** state (triggered manually via `⏸`, an explicit `CTRL_PAUSE` node, or a financial review gate `CTRL_REVIEW`):
- The background worker thread (`FlowRunner`) blocks safely on a `FlowPauseEvent` lock.
- **Radio-Dot Navigation**: Completed steps display green dots, active step displays an amber pulse, pending steps display hollow dots.
- **Step Context Injection (`ContextInjectModalScreen`)**: Select any node along the flow line, click **Inject Context**, enter raw text or JSON, and save to `_injected_context`. Click **Resume** (`▶`) to unblock execution with the new context payload.
- **Node Live Chat (`NodeLiveChatModal`)**: Select a paused node and click **Node Live Chat** to open an interactive conversation directly with the agent node using its exact current memory state (`thoughts.db`).
- **Time-Travel Branching**: Select a completed step and click **Branch Flow** to roll back `flow_vector` pointers in `swarm_queue.db` and re-execute from that waypoint.

### 3. Agent Studio & Session Bridge Compiler (`AgentStudioChatScreen`)
A 3-panel modal arena (`ChatDashboardPane`, `ChatArenaPane`, `ChatBuilderPane`) for multi-agent discussions. The **Session Bridge Compiler** in Panel 3 parses multi-agent chat transcripts and automatically compiles them into executable Flow Sequence DAG topologies.

### 4. Keyboard Shortcuts Quick Reference
| Shortcut | Context | Action |
| :--- | :--- | :--- |
| `Ctrl+R` | Global App | Launch Flow Execution (`action_run_flow`) |
| `Space` | Global App | Toggle VCR Transport (Pause / Resume) |
| `F2` / `Double-Click` | TopologyVisualizer | Open Node Configuration Editor (`MacroNodeEditorModal`) |
| `Ctrl+E` | TopologyVisualizer | Toggle MacroNode Sub-Tree Expansion (`action_toggle_expand`) |
| `Ctrl+Up` / `Down` | TopologyVisualizer | Re-order Selected Node in Step Chain |
| `Ctrl+S` | Modal Screens | Save Configuration & Close Modal |
| `Escape` | Modal Screens | Dismiss Modal / Return to Main View |

### 5. Modal Dialog Screens Guide (21 Modals across 11 Modules)
- **`macro_editor_modal.py`**: `MacroNodeEditorModal` (template step ordering, system prompts, tool bindings).
- **`session_manager_modal.py`**: `SessionManagerModal` (session canonization & deadflow purging), `MacroNodeNameModal`.
- **`onionbook_modal.py`**: `OnionBookModal` (token burn velocity & cost ratios), `FinOpsBuddy`.
- **`finops_modals.py`**: `BudgetProposalModal` (HITL financial approval gate), `BudgetWarningModal`.
- **`project_canon_modal.py`**: `ProjectCanonModal` (semantic memory pin inspection & query).
- **`splash_screen.py`**: `BootSplashModal`, `LoadingSplashModal`.
- **`nexus_plex.py`**: `NewProjectModal`, `SelectProjectModal`, `SystemInstructionsModal`, `ContextInjectModalScreen`, `NodeLiveChatModal`, `FlowHistoryModalScreen`.
- **`file_cabinet_modal.py`**: `FileCabinetModalScreen` (datacenter ingestion).

---

## Part IV — Swarm Topology Engineering & Pre-Flight Validation

### 1. CSV Topology Schema Reference
Topologies are defined in `topology.csv` using 15 standard configuration columns:
`NODE_ID`, `AGENT_NAME`, `MODEL_OVERRIDE`, `INSTRUCTION_OVERRIDE`, `TEMPERATURE`, `MAX_TURNS`, `NEXT_NODE_SUCCESS`, `NEXT_NODE_FAILURE`, `WAIT_FOR`, `DIALOGUE_PARTNER`, `DIALOGUE_ROUNDS`, `TETHER_ID`, `TOOLS_ALLOWED`, `SCATTER_TARGETS`, `FAILBACK_ROUTE`.

### 2. MacroNode Expansion & Namespace Isolation
Node IDs starting with `MACRO:` are intercepted by `macro_factory.py` and expanded into underlying sub-graphs (`cascade`, `hologram`, `chord`, `crucible`). Node IDs within the sub-graph are isolated with instance prefixes (`<MacroID>_<NodeName>`) to prevent collisions.

### 3. 7-Point Pre-Flight DAG Topology Validation Protocol
Before executing, `TopologyEngine.validate()` performs 7 automated checks:
1. **Instruction Check**: Verifies non-empty prompt directives.
2. **Model Validation**: Ensures valid non-blank model string.
3. **Temperature Range Audit**: Checks values lie within $[0.0, 2.0]$.
4. **DAG Target Resolution**: Confirms `NEXT_NODE_` targets exist or match terminal sentinels (`STOP`, `DONE`, `TERMINATE`, `FAILED`, `HUMAN_GATE`, `END`).
5. **Wait_For Audit**: Validates dependency existence and warns if fan-in $>5$.
6. **Circular Deadlock Detection**: Performs DFS recursion on `WAIT_FOR` nodes to catch loops.
7. **Dialogue Partner Audit**: Confirms `DIALOGUE_PARTNER` is registered in `agent_roster.csv` when `DIALOGUE_ROUNDS > 0`.

---

## Part V — Tools, RAG & Media Operations Manual

### 1. Document Ingestion & Semantic Memory Pinning
Copy source documents into `01_Raw_Source/` and invoke `ingest_document()`. The system chunks text, retrieves OS Vault credentials, generates 256-dim embeddings via `gemini-embedding-001` (using standard `urllib`), and stores records in `memory_pins.db` (`SovereignPinStore`) and SQLite FTS5 tables (`BM25`).

### 2. Hybrid Search Usage & Research Orchestration
Call `execute_hybrid_synthesis(query, collection_name, extra_queries)` to execute parallel semantic vector search, SQLite FTS5 BM25 search, and live Brave web queries (`search_web` via pure `urllib`), fused via Reciprocal Rank Fusion (RRF).

### 3. Dual-Pipeline Media Render Executor
Construct a Director JSON manifest and invoke `execute_render_pipeline()`:
- **TTS Audio**: Voice profiles map to `generateContent` Gemini REST calls, saving WAV files to `05_Rendered_Media/audio/`.
- **Imagen 3 Graphics**: Generates image batches in `05_Rendered_Media/images/` with automatic API failover (`imagen-3.0-generate-001` -> `imagen-3.0-generate-002`).
- **FFmpeg Stitcher**: Builds slide concat manifests and executes `ffmpeg.exe` to synthesize synchronized `.mp4` video in `05_Rendered_Media/video/`.

### 4. Excel Workbook Intake & Materialization Pipeline
Operators can define complete swarms in `MACCRE_Swarm_Request.xlsx`. Call `check_workbook_completeness()` to run pre-flight section readiness scoring and token cost estimation, then call `materialise_from_sheet()` to generate `agent_roster.json` and `topology.json`.

---

## Part VI — State, Security & Sovereignty Operations

### 1. Step-by-Step 3-Tier Access Control & PIN Elevation
- **Tier 1 (Read-Only Baseline)**: Default zero-prompt read access for all queries.
- **Tier 2 (Salted SHA-256 PIN Elevation)**: Prompts operator for security PIN on non-sandboxed file modifications, verifying input via salted SHA-256 hashes.
- **Tier 3 (MCP Token Bypass)**: Headless FastMCP agents (`maccre_mcp.py`) pass `MACCRE_ELEVATION_TOKEN` via `activate_mcp_bypass()`.

### 2. Archive Trash Protocol (`trash_file()`)
File deletions invoke `access_control.trash_file(path)`, prepending `%Y%m%dT%H%M%SZ__` timestamp prefixes and moving files to `_archive/trash/` with audit logging in `system_logs.db`.

### 3. Omni CLI Command Reference
- `omni run <script_path>` — Clears zombie processes, resolves active Python 3.11+ interpreter, and cleanly executes script.
- `omni qa [path] [--smart]` — Runs native Ruff linter and Pyright static type checker across codebase.
- `omni build [script_path]` — Purges temporary build caches, executes QA suite, and compiles single-file executable binaries via PyInstaller.
- `omni clean [path]` — Eradicates `__pycache__` directories, SQLite WAL/SHM artifacts, temporary files, and zombie worker threads.

---

## Part VII — Hardware & The Edge

### 1. The S25 Edge Client & Local Models
MACCREv2 abstracts local vs. remote execution seamlessly. `environment_probe.py` probes host system hardware (VRAM, CPU cores, active Ollama services). While cloud Gemini REST APIs handle heavy context windows, the engine is fully primed for air-gapped local execution (`gemma3:9b`, `llama.cpp`) to run 100% off-grid as hardware scales.
