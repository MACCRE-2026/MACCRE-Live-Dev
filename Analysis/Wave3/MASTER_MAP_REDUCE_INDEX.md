# MASTER MAP-REDUCE FUNCTION INDEX & FILE MAPPING DICTIONARY
**Target File Location:** `B:\EXO_GANS\Analysis\Wave3\MASTER_MAP_REDUCE_INDEX.md`  
**Source Ledgers Analyzed:** All 10 Wave 1 Functional Ledgers in `B:\EXO_GANS\Analysis\Wave1\`  
**Compliance Standard:** Engineering Rev 19.0 / Sovereign Edge Architecture Doctrine

---

## EXECUTIVE SUMMARY & MAP-REDUCE TAXONOMY

The **EXO_GANS / MACCREv2** codebase implements a zero-cloud, high-performance Map-Reduce and Swarm Orchestration paradigm. This Master Dictionary maps every module, class, enum, method, function signature, parameter type, return type, file path, and architectural role across all 10 subsystems evaluated during Wave 1 analysis.

### Core Map-Reduce Functional Roles:
- **Mapper (`MAP`)**: Decomposes natural language prompts, workbooks, or large data payloads into sub-tasks, scatter nodes (`CTRL_SCATTER`), or chunked embeddings.
- **Reducer (`REDUCE`)**: Aggregates worker responses, merges topology paths (`CTRL_MERGE`), canonizes session ledgers, and double-entry reconciles financial tokens.
- **Dispatcher (`DISPATCH`)**: Controls workflow routing across cloud (Gemini REST) and edge compute tiers (Ollama/Gemma).
- **Sentinel (`SENTINEL`)**: Active health probing, VRAM probing, capacity monitoring, and fault-tolerant failover.
- **Memory Pin (`STORE`)**: Zero-dependency SQLite FTS5 vector storage, project registries, and encrypted key management.
- **Execution Worker (`WORKER`)**: Universal swarm task loop executing tool primitives, deterministic nodes, and multi-turn agent dialogues.

---

## 1. NETWORKING, INFRASTRUCTURE & REST ENGINE (`maccre_core/_net/`)
**Target Path:** `b:\EXO_GANS\maccre_core\_net\`

### File: `client_interface.py` (`file:///b:/EXO_GANS/maccre_core/_net/client_interface.py`)
- **`InferenceConfig`** (Dataclass)
- **`InferenceResponse`** (Abstract Interface - `abc.ABC`)
- **`EmbeddingResult`** (Abstract Interface - `abc.ABC`)
- **`InferenceClient`** (Abstract Base Class - `abc.ABC`) [Role: `DISPATCH`]

### File: `environment_probe.py` (`file:///b:/EXO_GANS/maccre_core/_net/environment_probe.py`)
- **`EnvironmentProbe`** (Class) [Role: `SENTINEL`]

### File: `live_client.py` (`file:///b:/EXO_GANS/maccre_core/_net/live_client.py`)
- **`GeminiLiveClient`** (Class) [Role: `DISPATCH`]

### File: `omnidaemon.py` (`file:///b:/EXO_GANS/maccre_core/_net/omnidaemon.py`)
- **`OmniDaemon`** (Class) [Role: `DISPATCH` / `MAPPER`]

### File: `model_sentinel.py` (`file:///b:/EXO_GANS/maccre_core/_net/model_sentinel.py`)
- **`ModelSentinel`** (Thread Daemon Class) [Role: `SENTINEL`]

### File: `model_registry.py` (`file:///b:/EXO_GANS/maccre_core/_net/model_registry.py`)
- **`ModelSurface`** (Enum): Defines 13 capability surfaces.
- **`ModelInfo`** (Dataclass): Model metadata, context limit, pricing, tier rating.
- **`ModelRegistry`** (Class) [Role: `STORE` / `DISPATCH`]

### File: `ooxml.py` (`file:///b:/EXO_GANS/maccre_core/_net/ooxml.py`)
- **`SovereignWorksheet`** / **`SovereignWorkbook`** (Classes) [Role: `REDUCER`]

### File: `gemini_client.py` (`file:///b:/EXO_GANS/maccre_core/_net/gemini_client.py`)
- **`GeminiClient`** (Class) [Role: `DISPATCH`]

---

## 2. CORE ENGINE & ORCHESTRATION SWARMS (`maccre_core/orchestration/`)

### File: `deterministic_nodes.py` (`file:///b:/EXO_GANS/maccre_core/orchestration/deterministic_nodes.py`)
- **`DeterministicNodeType`** (Enum): Enumerate 16 deterministic control types.
- **`DeterministicNodeResult`** (Dataclass)
- **`is_deterministic_node(node_id: str) -> bool`**
- **`execute_deterministic_node(...) -> DeterministicNodeResult`** [Role: `MAP` / `REDUCE`]

### File: `flow_engine.py` (`file:///b:/EXO_GANS/maccre_core/orchestration/flow_engine.py`)
- **`FlowEngine`** (Class) [Role: `REDUCER` / `DISPATCH`]

### File: `swarm_worker.py` (`file:///b:/EXO_GANS/maccre_core/orchestration/swarm_worker.py`)
- **`UniversalSwarmWorker`** (Class) [Role: `WORKER`]

---

## 3. ORCHESTRATION FACTORY & MECHANICS (`maccre_core/orchestration/`)

### Key Components:
- **`LocalMessageBroker`** (`local_broker.py`) [Role: `STORE` / `MAPPER`]: WAL SQLite `swarm_queue.db`.
- **`MacroFactory`** (`macro_factory.py`) [Role: `MAPPER`]: Pattern expansion (`cascade`, `hologram`, `chord`, `crucible`).
- **`DialogueRunner`** / **`GroupDialogueRunner`** (`dialogue_runner.py`) [Role: `WORKER`]: Multi-agent persistent dialogue.
- **`NexusAgent`** (`nexus_agent.py`) [Role: `DISPATCH`]: TUI copilot context router.
- **`TopologyEngine`** (`topology_engine.py`) [Role: `SENTINEL`]: 7-point pre-flight DAG validator.

---

## 4. SYSTEM VAULT, PHYSICS ENGINE & TELEMETRY MATRIX (`maccre_core/`)

### Key Classes & Methods:
- **`AccessControlManager`** (`access_control.py`): Sandboxed 5-tier datacenter path checking.
- **`UniversalVault`** (`universal_vault.py`): RAM zero-leak key resolver (`ctypes.memset`).
- **`WindowsVault`** (`windows_vault.py`): DPAPI (`CryptProtectData`) and WinCred reader.
- **`TelemetryDB`** (`telemetry_db.py`): 4-silo SQLite matrix (`system_logs.db`, `user_interactions.db`, `terminal_logs.db`, `definitions.db`).
- **`ScoreKeeper`** (`scorekeeper.py`): Conversational physics & tension decay.

---

## 5. MEMORY, SCHEMAS, INGESTION, PATTERNS & UTILITIES

### Key Memory & Schema Classes:
- **`SovereignPinStore`** (`maccre_core/memory/sovereign_store.py`) [Role: `STORE`]: SQLite FTS5 vector store with float32 binary serialization and cosine distance calculation.
- **`PinRecord`**: Dataclass slots `("doc_id", "text", "vector", "metadata", "distance")`.
- **`dict_to_dataclass()`** (`maccre_core/schemas/sovereign_schema.py`): Zero-dependency schema validator.
- **`FingerprintManager`** (`maccre_core/ingestion/fingerprint_index.py`): Cryptographic SHA-256 deduplication index.
- **`get_maccre_root()` / `get_datacenter_path()`** (`maccre_core/utils/path_resolver.py`): Environment root anchoring.

---

## 6. MACCRE REGISTRIES & CORE SYSTEM INFRASTRUCTURE

### Key Modules:
- **`UniversalRouter`** (`maccre_core/maccre_router.py`) [Role: `DISPATCH`]: Universal LLM dispatcher with failover chains.
- **`ControlNodeRegistry`** (`maccre_core/controlnode_registry.py`): Registry of 25 deterministic node primitives.
- **`MacroNodeRegistry`** (`maccre_core/macronode_registry.py`): Persistent & ephemeral macro store.
- **`DriveWatcherDaemon`** (`maccre_core/drive_watcher.py`) [Role: `SENTINEL`]: Unattended `*_APPROVED.xlsx` inbox daemon.
- **`MacroLogger`** (`maccre_core/logger.py`): Dual-channel console and JSONL exhaust logger.

---

## 7. CLI, MCP ENTRYPOINTS & HOST INTEGRATION

### Key Entrypoint Tools:
- **`run.py`**: Boots `maccre_tui.nexus_plex.NexusPlex`.
- **`setup_mcp.py`**: Materializes `mcp_config.json`.
- **`maccre_mcp.py`**: Stdio FastMCP server exposing 27 tools across 8 functional categories.
- **`maccre.py`**: Master CLI engine (`ignite`, `run`, `topology`, `audit`, `canonize`).

---

## 8. TUI NEXUS_PLEX CORE SUBSYSTEM (`maccre_tui/`)

### File: `maccre_tui/nexus_plex.py`
- **`NexusPlex`** (Textual `App` Class): Command Center managing VCR state transport engine (`Idle`, `Running`, `Paused`).
- **`FlowRunner`**: Threaded execution controller binding flow graphs.
- **`AgentStudioChatScreen`**: 3-panel dynamic multi-agent arena.

---

## 9. TUI WIDGETS & MODAL DIALOGS (`maccre_tui/widgets/`)

### Key Components:
- **`TopologyVisualizer`**: State-driven Rich `Tree` renderer with pulse animations.
- **`MacroNodeEditorModal`**: Fullscreen template node editor.
- **`SessionManagerModal`**: FlowStasis inspector and dead flow debugger.
- **`ProjectCanonModal`**: Knowledge pin manager.
- **`OnionBookModal`**: Real-time token cost & financial ratio dashboard (`FinOpsBuddy`).

---

## 10. TOOL EXECUTION SUITE, DASHBOARD & AUTOMATION SCRIPTS

### Key Tool Modules (`maccre_core/tools/`):
- **`tool_registry.py`**: Maps 40+ atomic functions into standard OpenAPI JSON schemas.
- **`rag_tools.py`**: Hybrid memory search & session canonization.
- **`render_executor.py`**: FFmpeg media pipeline dispatcher.
- **`finops_tools.py`**: Token pricing matrix (`PRICING_MATRIX`) and post-session financial reconciler.
- **`sheet_parser.py`**: High-fidelity Excel workbook parser & materializer.
- **`maccre_dashboard/backend/main.py`**: FastAPI & ZeroMQ PUB/SUB control server.
- **`scripts/maccre_micro_test.py`**: 14-Phase micro-test suite validating all 28 MCP tools.
