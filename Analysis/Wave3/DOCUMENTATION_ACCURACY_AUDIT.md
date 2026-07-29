# MASTER 5-ORACLE ARCHITECTURAL ACCURACY AUDIT REPORT

**Target Files Audited:** `B:\EXO_GANS\MACCRE_Operator_Manual.md` & `B:\EXO_GANS\README.md`  
**Auditing Swarm:** All 5 Specialist Oracles (`NetAndClient`, `OrchestrationAndEngine`, `TUIAndInterface`, `ToolsAndRAG`, `StateAndSovereignty`)  
**Audit Date:** 2026-07-25  

---

## EXECUTIVE AUDIT SUMMARY

A comprehensive 5-domain architectural audit of `MACCRE_Operator_Manual.md` and `README.md` was conducted against the physical codebase in `b:\EXO_GANS\maccre_core\` and `b:\EXO_GANS\maccre_tui\`.

Overall, the high-level philosophy (**Sovereign Edge Omni-Builder Doctrine**, **Deterministic Scaffolding**, **5-Tier Datacenter Isolation**, **Zero-Cloud Local State Machine**, **Omni CI/CD Gatekeeper**) is accurately documented. However, the Oracles identified **key discrepancies, undocumented features, and historical inaccuracies** across all 5 domains.

---

## DOMAIN 1: NET & CLIENT SUBSYSTEM (`NetAndClient_Oracle`)

### Accurate Claims:
- **Strangler Fig Contract (`client_interface.py`)**: Abstract base classes `InferenceClient`, `InferenceResponse`, `EmbeddingResult` enforce Law VI (Abstraction).
- **Surface Taxonomy (`model_registry.py`)**: Classifies 55+ Gemini models into 13 capability surfaces (`TEXT_GENERATION`, `DEEP_RESEARCH`, `TTS`, `IMAGEN`, `VIDEO`, etc.) with failover chains.
- **Active Health Sentinel (`model_sentinel.py`)**: Background thread daemon (`get_sentinel()`) probes models every 1800s, tracks latency/errors in sliding deque (maxlen=20), and fires events (`MODEL_ADDED`, `MODEL_DIED`, `MODEL_DEGRADED`).
- **Pure REST Implementation (`gemini_client.py`)**: 100% standard library `urllib.request` REST client for standard API calls.

### Discrepancies & Omissions:
- **Undocumented WebSocket Exception**: `README.md` claims zero third-party SDK dependencies. However, `live_client.py` uses `google.genai` SDK for stateful WebSocket connections (`client.aio.live.connect`), explicitly noting a `# SOVEREIGNTY EXCEPTION` (Live API WebSocket protocol has no standard REST equivalent).
- **Write-Only OOXML Scope**: `ooxml.py` is strictly a **WRITE-ONLY** `.xlsx` zip builder; `openpyxl` remains on the read path if Excel parsing is required.
- **Hardware Probe Scope**: `environment_probe.py` checks Ollama `localhost:11434` health and CPU logical cores (`os.cpu_count() >= 8`), but currently hardcodes `"model": "gemma"` in Ollama requests.

---

## DOMAIN 2: ORCHESTRATION & ENGINE SUBSYSTEM (`OrchestrationAndEngine_Oracle`)

### Accurate Claims:
- **Deterministic Control**: `FlowEngine` governs DAG execution paths using explicit `CTRL_` primitives (`CTRL_GATE`, `CTRL_SCATTER`, `CTRL_MERGE`, `CTRL_PAUSE`).
- **SQLite WAL Concurrency Queue**: `swarm_queue.db` managed by `local_broker.py` using `UNIQUE(job_id, current_node)`, `INSERT OR IGNORE`, and `BEGIN EXCLUSIVE` locks for thread-safe fan-in/fan-out serialization.
- **OSINT_Research_x3 MacroNode**: Accurately describes `CASCADE` protocol with dual-pass exclusionary search and 3-turn dialogue synthesis between `OSINT_Analyst` and `Regular_Joe`.
- **Time-Travel Replay**: Node lineage tracked via `flow_vector` in SQLite.

### Discrepancies & Omissions:
- **Quadrivector Failback Details**: Manual describes `CTRL_GATE`, but omits `CTRL_CONDITIONAL_ROUTE`'s full 4-vector matching specification (Payload JSON path, Keyword regex, LLM Confidence score, Fuzzy String Edit distance).
- **16 Deterministic Primitives**: Manual focuses on 6 primitives, omitting `CTRL_CONCAT`, `CTRL_PAYLOAD_INJECT`, `CTRL_FILTER`, `CTRL_CLEANUP`, `CTRL_RETRY`, etc.

---

## DOMAIN 3: TUI & INTERFACE SUBSYSTEM (`TUIAndInterface_Oracle`)

### Accurate Claims:
- **NexusPlex Command Center**: Split-pane layout hierarchy (Left Pane: InfoPanel/Overlay/Chat; Right Pane: Workshop/Visualizer) styled by `nexus_plex.css`.
- **VCR Transport State Machine**: 3-state transport machine (`Idle` $\rightarrow$ `Running` $\rightarrow$ `Paused`) with blocked worker thread on pause.
- **TopologyVisualizer Rich Tree**: Pulsing animation frames (`●`), completion (`✓`), failure (`✗`), tether badges (`[tether:id]`), and `[+]`/`[-]` MacroNode toggles.

### Discrepancies & Omissions:
- **Modal Taxonomy Clarification**: Ledgers cite 11 operational workflow modal modules, while code analysis reveals 21 total `ModalScreen` Python classes.
- **Paused State Capabilities**: Manual omits that when `PAUSED`, operators can select steps via radio-dots to inject context (`ContextInjectModalScreen`) or live chat with nodes (`NodeLiveChatModal`).
- **Session Bridge Compiler**: Manual omits `ChatBuilderPane`'s compiler which converts live multi-agent Chat Studio transcripts directly into executable Flow Sequence DAG topologies.

---

## DOMAIN 4: TOOLS & RAG SUBSYSTEM (`ToolsAndRAG_Oracle`)

### Accurate Claims:
- **Datacenter Output Routing**: Tools write outputs to `05_Rendered_Media` and `04_Code_Artifacts`.
- **Semantic Memory Pins**: Accurately describes `memory_pins.db` semantic concept pinning (`SovereignPinStore` SQLite WAL + FTS5 BM25 + vector search).

### Discrepancies & Omissions:
- **Historical Discrepancy (Excel Support)**: Manual (Part III.1) claims Excel workbooks are historical legacy. Code truth reveals `sheet_parser.py` and `workbook_engine.py` are active Phase 5 & 6 intake pipelines for `MACCRE_Swarm_Request.xlsx`.
- **Master Tool Registry Dispatch**: Omits `tool_registry.py`'s master dispatcher (61 atomic tools mapped, tier filtering, dynamic OpenAPI JSON schema generation).
- **Sovereign RAG Hybrid Search**: Omits `hybrid_search.py` (parallel Brave live web search via standard `urllib` + vector + SQLite FTS5 BM25 Reciprocal Rank Fusion).
- **Dual-Pipeline Media Render Executor**: Omits `render_executor.py` (Gemini REST TTS audio + Imagen 3 image generation with model drift warnings + edge FFmpeg complex filter graph video stitcher).

---

## DOMAIN 5: STATE & SOVEREIGNTY SUBSYSTEM (`StateAndSovereignty_Oracle`)

### Accurate Claims:
- **Path Anchoring**: Runtime root resolution via `get_maccre_root()` in `path_resolver.py`.
- **5-Tier Datacenter Silos**: Accurately lists `01_Raw_Source` through `05_Rendered_Media`.
- **Key Ingestion**: `key_ingestor.py` regex pattern fingerprinting for 6 provider key types.
- **Omni Pipeline**: Bare `python` execution banned; mandates `omni run` and `omni qa`.

### Discrepancies & Omissions:
- **Vault Conflation**: Manual conflates `universal_vault.py` (keyring + AES-128 Fernet `auth_vault.bin`) with `windows_vault.py` (native Windows DPAPI `CryptProtectData` + `CredReadW`).
- **RAM Key Zeroing & Clipboard Sanitization**: Omits `wipe_string()` CPython memory zeroing (`ctypes.memset`) and Win32 clipboard clearing (`clear_windows_clipboard()`).
- **4-Silo Telemetry Matrix**: Omits 3 of the 4 telemetry databases (`user_interactions.db`, `terminal_logs.db`, `definitions.db`), documenting only `system_logs.db`.
- **Archive Trash Protocol**: Omits `access_control.py`'s explicit `trash_file()` protocol (`_archive/trash/` with `%Y%m%dT%H%M%SZ__` timestamp prefix).
- **Omni Commands**: Omits `omni build` (PyInstaller compilation) and `omni clean` (cache & SQLite WAL purge).

---

## MASTER AUDIT VERDICT TABLE

| Subsystem Scope | Accuracy Score | Core Correction Needed |
| :--- | :---: | :--- |
| **Net & Client** | 88% | Document Gemini Live WebSocket SDK exception & write-only OOXML scope |
| **Orchestration & Engine** | 92% | Document `CTRL_CONDITIONAL_ROUTE` quadrivector failback & 16 control nodes |
| **TUI & Interface** | 90% | Document Paused-state interactive step injection & Session Bridge Compiler |
| **Tools & RAG** | 85% | Correct Excel claims (active intake pipeline) & document `hybrid_search.py` |
| **State & Sovereignty** | 86% | Clarify DPAPI vs. Fernet vault, RAM zeroing, 4-silo telemetry matrix, `trash_file()` |
