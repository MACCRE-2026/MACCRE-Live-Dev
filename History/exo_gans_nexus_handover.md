# EXO_GANS / MACCREv2 - Agent Handover Document

Welcome, Primary Engineering Agent. You are picking up the development of the MACCREv2 OMNI-BUILDER architecture. Here is the current state of the codebase, recent features we just shipped, and the immediate focus for the next session.

## System Architecture Context
- **Doctrine Compliance:** All code MUST adhere strictly to the MACCREv2 Physical Laws (explicit typing, no hardcoded absolute paths using `get_maccre_root()`, strict 5-Tier Data Sovereignty, and OmniBuilder CI/CD tool paths).
- **Core Orchestration:** The `LiveSessionManager` orchestrates multi-agent swarms. The TUI is powered by Textual in `nexus_plex.py`. Background tasks (like `swarm_worker.py`) stream LLM output and broadcast events over a `JsonFileQueue`.

## Recently Completed: The Conversational Physics Engine
We recently overhauled the live chat mode to stop runaway LLM loops ("endless meta-chatter") and reinforce persona adherence. We implemented:

1. **Dynamic Bidding (ScoreKeeper):** Instead of broadcasting a prompt to all active agents, `ScoreKeeper.py` uses a bidding heuristic based on previous turn count and current "tension" to selectively route the chat turn to a single optimal agent. 
2. **Hidden Internal Monologues:** Agents are forced to wrap their cognitive process in `<thought>...</thought>` tags before outputting their public `<chat>...</chat>`. 
3. **Data Sovereignty (Database Triples):** The streaming engine dynamically parses out the hidden `<thought>` blocks and routes them directly to the `03_Agent_Ledgers` (JSON database triples) so background reasoning is preserved without polluting the TUI.
4. **Unified Chat Logging:** The `LiveSessionManager` intercepts all messages and logs a full transcript of the active session to `04_Code_Artifacts/unified_chat_{job_id}.md`.
5. **HITL Auto-Trigger (Human-In-The-Loop):** A hardcoded safeguard halts the active swarm and requests user input after 5 uninterrupted agent turns. A new `HITL_Pause` MacroNode was also added to the `macronode_registry.db` to allow visual configuration in the Flow Editor.

## Next Steps / Open Items
When picking up from here, the user will likely want to focus on:
1. **Flow Editor Integration:** Visualizing the new `HITL_Pause` MacroNode parameter (Turn Count) directly in the Textual TUI (`nexus_plex.py`).
2. **Physics Tuning:** The `ScoreKeeper` variables (tension decay, dominance, and topic affinity) might need to be fine-tuned or wired up to a fast local LLM (e.g., Gemma 3) for semantic relevance checks.
3. **Robust Data Triples:** Ensure the forensic RAG tools (`maccre_core/tools/rag_tools.py`) correctly parse the new JSON internal monologue format in `03_Agent_Ledgers`.

> [!IMPORTANT]
> When executing OmniBuilder actions, remember that any background Python subprocess must have its stdout/stderr captured or redirected carefully to prevent deadlocks, and you must use `omni qa .` and `omni build .` to validate the environment.
