# Phase 3.1: Triple Index Search & Agent Chat Upgrades

This implementation plan focuses on surfacing the Triple Index Search capabilities to the user interface, resolving TUI rendering bugs, and overhauling the Agent Chat logging and functionality based on your feedback.

## Open Questions
> [!IMPORTANT]
> - Do you want the `agent_chat_ledger.md` to continually append across multiple different chat sessions within the same project, or should it generate a unique filename (e.g., `agent_chat_<timestamp>.md`) for each distinct chat session launched?

## Proposed Changes

---
### 1. TUI Scaling and Layout Fixes
The current agent editor modal suffers from rendering issues at normal terminal scaling, hiding the toggles and instruction text boxes.

#### [MODIFY] `maccre_tui/maccre.tcss` (or `nexus_plex.py` styling)
- Rework the container sizing for the Agent Editor modal. Use dynamic layouts (like `1fr` and `auto`) instead of fixed heights to ensure all elements (toggles, instruction boxes) flow naturally and are visible at standard zoom levels.

---
### 2. Triple Index Search Toggles & Logic
The backend pipelines for Exclusionary and Funnel searches are already stubbed in `swarm_worker.py`. We need to expose them safely to the user.

#### [MODIFY] `maccre_tui/nexus_plex.py` (Agent Editor Modal)
- Add 5 new Checkboxes to the Agent Editor:
  1. **Grounding: Google Search**
  2. **Grounding: Brave Search**
  3. **Grounding: Local Memory**
  4. **Mode: Exclusionary Search**
  5. **Mode: Funnel Search**
- Implement reactive event handlers (`@on(Checkbox.Changed)`) to dynamically enable/disable the Exclusionary and Funnel toggles. They will only be clickable if **2 or more** of the Grounding checkboxes are active.

#### [MODIFY] `maccre_core/orchestration/swarm_worker.py`
- Remove the forced `|google_search` tool appending for native Google API calls, as native cloud agents handle this directly via API parameters.

---
### 3. Agent Chat Unified Ledger
Agent Chat sessions currently lack proper centralized telemetry. We will intercept the chat streams to live-write a dedicated markdown ledger.

#### [MODIFY] `maccre_core/orchestration/live_session_manager.py` (or Chat Handler)
- Bypass the 03 individual agent ledgers entirely for Live Chat sessions.
- Implement a unified live-writer that appends to `04_Code_Artifacts/agent_chat_ledger.md` in real-time.
- Ensure the live writer strictly formats the output, providing clear visual delineation between raw agent thoughts, tool execution blocks, and the final chat response rendered to the user.

---
### 4. Agent Chat Clipboard Tooling
You requested the ability to quickly pull chat snippets out of the TUI.

#### [MODIFY] `maccre_tui/nexus_plex.py` (Agent Chat Modal)
- Add a **"Copy Chat"** button next to the "Start/Stop Session" controls.
- Bind the button to an event that extracts the plain text from the RichLog and utilizes `pyperclip.copy()` to push the entire chat history straight to your system clipboard for easy sharing.

## Verification Plan
1. **Visual Testing:** Launch the TUI at standard resolution to verify the Agent Editor doesn't hide the checkboxes or text boxes.
2. **Logic Testing:** Test the toggle logic in the Agent Editor to ensure Exclusion/Funnel cannot be activated without $\ge$ 2 Groundings.
3. **Chat Logging:** Start a live Agent Chat, send a message, and verify `04_Code_Artifacts/agent_chat_ledger.md` is generated and live-updating with proper formatting.
4. **Clipboard:** Click the "Copy Chat" button and verify the text appears in the system clipboard.
