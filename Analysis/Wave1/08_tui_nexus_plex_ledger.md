# GRANULAR FUNCTIONAL LEDGER: NEXUS_PLEX TUI APPLICATION & SUBSYSTEMS

**Target Ledger File:** `B:\EXO_GANS\Analysis\Wave1\08_tui_nexus_plex_ledger.md`  
**Analyzed Source Files:**
- `maccre_tui/nexus_plex.py` (248,406 bytes | 5,309 lines)
- `maccre_tui/nexus_plex.css` (22,888 bytes | 1,212 lines)
- `maccre_tui/app.py` (4,167 bytes | 106 lines)

---

## EXECUTIVE SUMMARY & SYSTEM ARCHITECTURE

`maccre_tui` contains the primary user interface layer for MACCREv2, built upon Textual (v2 App framework). The core application, `NexusPlex` (`nexus_plex.py`), provides a split-pane Agentic Command Center that integrates:
1. **Nexus Copilot** (`NexusAgent`): Real-time chat assistant with topology inspection and execution dispatch.
2. **Linear & Graph Flow Execution Engine** (`FlowRunner`): Step-by-step or parallel execution of MacroNodes, Agents, and Control Nodes with pre-flight checks, budget proposals, and duplicate-run detection.
3. **Interactive VCR Transport Engine**: Idle, Running, and Paused state machine allowing mid-flow context injection, live chat with active flow nodes, and time-travel branching.
4. **Agent Studio Chat** (`AgentStudioChatScreen`): A 3-panel arena (`ChatDashboardPane`, `ChatArenaPane`, `ChatBuilderPane`) for dynamic multi-agent discussions, custom dictionary configuration, and session bridge compilation to flow sequences.
5. **MacroNode Workshop & Builder**: Dynamic node catalog, tree visualization (`TopologyVisualizer`), and template editing (`MacroNodeEditorModal`).
6. **Datacenter & Knowledge Ingestion** (`FileCabinetModalScreen`, `OnionBookModal`, `ProjectCanonModal`): Ingestion into 5-tier datacenter structures (`01_Raw_Source` through `05_Rendered_Media`).

---

## 1. COMPONENT ANALYSIS: `maccre_tui/app.py` (LEGACY LIVE C2 CONSOLE)
Standalone entry point (`LiveSwarmTUI`) for live C2 agent telemetry and routing control. Connects to `LiveSessionManager` backend.

## 2. COMPONENT ANALYSIS: `maccre_tui/nexus_plex.css` (GLOBAL STYLESHEET)
Contains 1,212 lines of CSS rules defining visual hierarchy, split-pane layout grid, dark theme palette, modal dialogs, and interactive VCR transport controls.

## 3. COMPONENT ANALYSIS: `maccre_tui/nexus_plex.py` (CORE AGENTIC COMMAND CENTER)
Main entry point (5,309 lines) defining modal screens (`NewProjectModal`, `SelectProjectModal`, `SystemInstructionsModal`, `ContextInjectModalScreen`, `NodeLiveChatModal`, `FlowHistoryModalScreen`, etc.), `AgentStudioChatScreen` (3-panel arena), UI Header Widgets, `FlowExecutionPanel`, and root `NexusPlex` Textual app class with interactive VCR state machine.
