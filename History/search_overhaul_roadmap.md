# Search Overhaul Roadmap

This roadmap breaks down the complex "Multi-Tier Grounding Options & Hybrid Exclusionary Search" feature requests into manageable implementation phases.

## Phase 1: Grounding State Migration (Immediate Fix)
* **Goal:** Ensure all search capabilities are driven directly by the `agent_library.db` toggles rather than legacy manual tool strings or `agent_extras.json`.
* **Action:** Fix the `_GLOBAL_ARCHITECTURE` prompt pollution and ensure Google Search Grounding reads from `ai_studio_options["grounding_google_search"]`. 
* **Status:** Scheduled for immediate execution in current plan.

## Phase 2: Brave & Local Memory UI Integration
* **Goal:** Expand the Agent Builder UI in `nexus_plex.py`.
* **Action:** Add "Grounding with Brave Search" and "Grounding with Local Memory" toggles beneath the existing Google Search toggle. Update the save logic to store these in `ai_studio_options`.

## Phase 3: The Hybrid Exclusionary Pipeline (Google + Brave)
* **Goal:** Implement the complex, multi-step search routine when both Google and Brave are enabled.
* **Action:** 
  - Instead of simply attaching a `hybrid_search` tool, we will build a dedicated `ExclusionarySearchRouter` (or a specialized `MacroNode` loop).
  - **Step 1:** Agent fires Google Search.
  - **Step 2:** Agent evaluates Google results and extracts key sources/facts.
  - **Step 3:** Agent automatically fires a Brave Search, programmatically formatted to explicitly exclude the domains and facts discovered in Step 2.
  - **Step 4:** Synthesis of both result sets.
* **Testing:** This will require optimized prompt engineering to ensure the LLM correctly formulates the exclusionary Brave queries without hallucinating.

## Phase 4: Triune Search Logic (Google + Brave + Local)
* **Goal:** The ultimate, rigorous fact-checking topology.
* **Action:** 
  - When all three toggles are active, dynamically inject a "Triune Search Protocol" block into the agent's System Prompt.
  - **Prompt Engineering:** The injection must explicitly explain *why* the agent has Local Memory access (i.e., to cross-reference global facts against project-specific claims) and strict instructions *not* to hallucinate local project data as global reality.
  - The agent will use the `execute_hybrid_synthesis` tool (or a new variant) to simultaneously ping local ChromaDB vectors while executing the Hybrid Exclusionary Pipeline for external facts.

---

> [!NOTE]
> By keeping these complex routing behaviors anchored to simple boolean toggles in the Agent Builder, the TUI remains clean and user-friendly while the backend `swarm_worker.py` dynamically handles the heavy lifting.
