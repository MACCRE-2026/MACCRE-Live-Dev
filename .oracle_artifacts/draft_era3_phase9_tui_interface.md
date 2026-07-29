# ERA 3 ARCHITECTURAL ROADMAP: PHASE 9 - TUI & INTERFACE CONTRIBUTION
**Domain Contribution:** TUI & Interface Specialist Oracle (`TUIAndInterface_Oracle`)  
**Target Modules:** `maccre_tui/nexus_plex.py` (`AgentStudioChatScreen`), `maccre_tui/widgets/session_manager_modal.py` (`SessionManagerModal`), `maccre_tui/nexus_plex.css`  
**Theme:** In-State Live Development & Antigravity Desktop Transition Bridge  
**Compliance Standard:** Sovereign Edge Omni-Builder Doctrine Rev 19.0 (`omni` JIT Gatekeeper, 5-Tier Data Sovereignty, Zero-Zombie Worker Threads)

---

## 1. EXECUTIVE SUMMARY & SUBSYSTEM VISION

Phase 9 establishes the **In-State Live Development & Antigravity Desktop Transition Bridge** within the MACCRE Textual Command Center (`maccre_tui`). It bridges standalone external development workflows and Google Antigravity desktop sessions directly into the sovereign, 5-tier datacenter environment.

By enhancing `AgentStudioChatScreen` and `SessionManagerModal`, Phase 9 converts the TUI from an orchestration-only control center into a **live, in-state development environment** capable of interactive code execution, virtual environment (`venv`) dispatch, multi-agent pair programming, and automated workspace transmutation.

---

## 2. COMPONENT 1: IN-STATE LIVE DEVELOPMENT CHAT STUDIO (`AgentStudioChatScreen`)

### 2.1 Overview & Architecture
`AgentStudioChatScreen` currently provides a 3-panel chat arena (`ChatDashboardPane`, `ChatArenaPane`, `ChatBuilderPane`) with a Session Bridge Compiler for generating Flow Topologies. Phase 9 upgrades this screen into an **Interactive Live Development Studio** fully wired to:
1. **The 61 Atomic Tool Dispatcher (`maccre_core/tools/tool_registry.py`)**: Allowing agents in the chat arena to invoke local python tools, file I/O, search, and system probes dynamically.
2. **Workspace Virtual Environment (`venv`) & `omni` Launcher**: Enabling agents to compile, lint (`omni qa`), and run code scripts in real-time via `omni run`.
3. **5-Tier Project Datacenter Silos**: Locking file operations to active project paths (`__DATACENTER/<active_project>/`).

### 2.2 UI & State Architecture Upgrades
- **`ChatArenaPane` Live Execution Terminal Widget**: Addition of a responsive `LiveConsoleOutput` widget (collapsible Rich `Log` / `Static` log view) below the main chat stream displaying real-time stdout/stderr, ANSI colorized execution outputs, and exit codes.
- **Asynchronous Execution Harness**: Tool execution and subprocess commands run on Textual Workers via `@work(thread=True, exclusive=False)`, streaming tokens and execution lines back to the TUI main loop thread-safely via `self.call_from_thread()`.
- **3-Tier Access Control Interceptor**: If an agent in Chat Studio attempts an operation requiring Tier 2 elevation (e.g. modifying project code outside sandbox or executing system commands), execution pauses and pops `PinElevationModal` asynchronously without crashing or hanging the chat thread.

---

## 3. COMPONENT 2: ANTIGRAVITY DESKTOP TRANSITION BRIDGE & FILE CABINET UPGRADE (`SessionManagerModal`)

### 3.1 Overview & Architecture
`SessionManagerModal` (the File Cabinet / Session Manager) currently manages FlowStasis, Completed flows, and DeadFlows. Phase 9 expands this modal to include an **Antigravity Desktop Transition Bridge & Project Ingestion Engine**.

### 3.2 Importer & Transmutation Pipeline
- **Antigravity Directory Discovery**: Auto-detects local Google Antigravity desktop installations at `%USERPROFILE%\.gemini\antigravity\` (or `appDataDir`), scanning:
  - `conversations/`: Historical conversation logs and turn metadata.
  - `brain/<conversation-id>/`: Generated markdown artifacts, scratch scripts, diagrams, and diffs.
- **5-Tier Datacenter Transmutation**:
  - Automatically creates a new project directory under `get_maccre_root() / "__DATACENTER" / <imported_project_name>`.
  - Ingests raw code bases, existing scripts, and repos into `01_Raw_Source/` and `04_Code_Artifacts/`.
  - Ingests Antigravity conversation transcripts into `02_Dynamic_Context/antigravity_chats/`.
  - Maps Antigravity artifacts and scratch scripts into `04_Code_Artifacts/` and agent ledgers into `03_Agent_Ledgers/`.
- **Automated RAG Vector Indexing**: Upon transmutation completion, triggers `hybrid_search.py` (FTS5 BM25 + `SovereignPinStore` vector embeddings) to index imported source code and context immediately.

### 3.3 UI Workflow in `SessionManagerModal`
- **Import Button & Action Bar**: New `#btn-import-antigravity` and `#btn-import-project` buttons launching the `ProjectImportWizardModal`.
- **Interactive Progress & Telemetry Modal (`ProjectImportProgressModal`)**: Renders real-time multi-stage progress bars and execution logs showing scan, transmutation, file placement, and vector indexing states.

---

## 4. DOMAIN QUESTIONS & ARCHITECTURAL EDGE CASES

### Edge Case 1: Textual Main Event Loop Deadlock during Long-Running Tool Execution
- **Risk**: Calling synchronous python tools or `omni run` commands directly on the Textual thread will freeze the TUI interface, making UI unresponsive.
- **Solution**: Enforce strict `@work(thread=True)` execution wrappers for all agent tool invocations in `AgentStudioChatScreen`. UI updates MUST use `call_from_thread(widget.update, data)`.

### Edge Case 2: Cross-Platform Path Resolution for Antigravity Directories
- **Risk**: Hardcoded Windows paths (`C:\Users\...`) breaking on Linux/macOS environments.
- **Solution**: Use `path_resolver.py` and `Path.home() / ".gemini" / "antigravity"` to resolve user home and appData directories across all platforms.

### Edge Case 3: Concurrent SQLite WAL Lock Contention in Telemetry DBs
- **Risk**: Background swarm execution workers writing to `system_logs.db` while `AgentStudioChatScreen` live tools write telemetry.
- **Solution**: Ensure all SQLite DB handles use WAL mode with `busy_timeout=30.0` and thread-local connection pooling via `maccre_core.telemetry_db`.

### Edge Case 4: Asynchronous PIN Elevation Interception
- **Risk**: Tool calls requesting elevated file write permissions in non-modal background tasks causing silent failures.
- **Solution**: Implement a non-blocking toast/event interceptor in `AgentStudioChatScreen` that queues PIN elevation prompts directly into the modal UI layer and halts the specific tool thread until validated.

---

## 5. ROADMAP INTEGRATION SPECIFICATION FOR `Era3_architectural_roadmap.md`

### 5.1 Updates to Section 3 (Textual NexusPlex TUI & Command Center)
Add Section 3.4:
```markdown
### 3.4 Phase 9 Strategic Addition: Live Development & Antigravity Bridge
- **In-State Live Dev Chat Studio (`AgentStudioChatScreen`)**: Fully wired to 61 tool dispatcher (`tool_registry.py`), project `venv`, and `omni run` launcher for interactive code generation, linting, and execution within `ChatArenaPane`.
- **Antigravity Desktop Transition Bridge (`SessionManagerModal`)**: Automated discovery and transmutation of Google Antigravity `conversations\` and `brain\` artifacts into 5-tier datacenter projects (`01_Raw_Source` through `05_Rendered_Media`) with immediate hybrid RAG indexing.
```

### 5.2 Updates to Section 6 (Phased Implementation Timeline)
Append Phase 9 to Section 6:
```markdown
| PHASE 9: IN-STATE LIVE DEVELOPMENT & ANTIGRAVITY DESKTOP TRANSITION BRIDGE          |
|   - Interactive live tool execution & venv code runner in AgentStudioChatScreen      |
|   - Non-blocking Textual worker thread harness (@work(thread=True)) & LiveConsole    |
|   - Antigravity conversation & brain artifact auto-discovery engine                 |
|   - 5-tier datacenter project transmutation & automated hybrid RAG indexing         |
|   - SessionManagerModal import wizard & ProjectImportProgressModal telemetry UI      |
```
