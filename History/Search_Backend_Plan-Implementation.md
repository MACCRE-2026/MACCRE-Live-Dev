# Phase 3 Backend: Triple Index Search Implementation Plan

This document outlines the backend architectural changes required to execute the Triple Index Search topologies (Additive, Exclusionary, and Funnel) within the `maccre_core` orchestration pipeline.

## 1. Orchestration Interceptor (`swarm_worker.py`)

The core execution logic resides in `swarm_worker.py`. We will intercept the agent's `ai_studio_options` prior to the final LLM invocation via `maccre_router.py`.

The backend will parse the following flags from the agent profile:
- `grounding_google_search`
- `grounding_brave_search`
- `grounding_local_memory`
- `exclusionary_search`
- `funnel_search`

## 2. Topology Execution Pipelines

### A. Additive Merging (Parallel Injection)
*Active when: Core groundings are selected, but Exclusionary and Funnel are FALSE.*

- **Google Search:** Handled natively. We simply append `|google_search` to the agent's `tools_str`, and `maccre_router.py` will trigger Gemini's native API grounding.
- **Brave Search:** Handled via pre-injection. The orchestrator uses a lightweight LLM call to extract a 1-sentence search query from the `current_payload`. It then programmatically calls `brave_search()` and prepends the raw JSON results to the agent's `current_payload` under a `[BRAVE SEARCH CONTEXT]` header.
- **Local Memory:** Handled via pre-injection. The orchestrator queries the `memory_pins.db` using the exact same extracted query, and prepends the results under a `[LOCAL MEMORY CONTEXT]` header.
- **Result:** The agent receives a massively enriched payload containing Brave + Local Memory data, and still retains its native Google Search capability during the generation phase.

### B. Exclusionary Search (Adversarial Pipeline)
*Active when: `exclusionary_search` is TRUE.*

This is a multi-step sequential pipeline executed *before* the main agent starts generating:
1.  **Mainstream Consensus (Google):** The orchestrator spawns a hidden LLM call equipped with native Google Grounding. Its only prompt: *"Research the following topic and extract the 3 most prominent domains and 3 most common keywords representing the mainstream consensus."*
2.  **Adversarial Construction:** The orchestrator parses the output and builds a negative query string (e.g., `"{topic}" -site:wikipedia.org -site:nytimes.com -keyword1 -keyword2`).
3.  **Orthogonal Retrieval (Brave):** The orchestrator calls `brave_search()` using this adversarial query.
4.  **Fallback / Injection:** 
    - If Brave returns 0 results, the system logs a fallback warning and defaults to Additive Merging.
    - If successful, the orthogonal results are injected into the agent's payload as `[EXCLUSIONARY ORTHOGONAL CONTEXT]`. 
5.  **Contamination Prevention:** Native Google Grounding is intentionally disabled for the main agent generation pass to prevent re-contaminating the orthogonal data.

### C. Funnel Search (Iterative Batching)
*Active when: `funnel_search` is TRUE.*

1.  **Broad Discovery (Google):** The orchestrator spawns a hidden LLM call equipped with native Google Grounding. Prompt: *"Research this topic and extract 5 highly specific, niche entities (people, obscure hardware, specific company subsidiaries)."*
2.  **Entity Isolation:** The orchestrator iterates through the 5 entities.
3.  **Deep Dive (Brave):** It executes 5 targeted `brave_search()` queries, one for each entity (e.g., `"entity name" filetype:pdf OR forum`).
4.  **Delivery:** The aggregated, highly dense batch of technical data is injected into the payload as `[FUNNEL BATCH CONTEXT]` before the main agent execution.

## 3. FinOps & Cost Tracking

Because Exclusionary and Funnel searches require "hidden" LLM calls (to extract exclusions or entities), these calls cost tokens. 
- The token usage and cost of these pre-processing steps will be calculated via `maccre_router.py`.
- This pre-processing cost will be aggressively aggregated and added to the `total_cost` variable in `swarm_worker.py` so the final Unified Session Ledger accurately reflects the *true* cost of the Triple Index Search.

## User Review Required

> [!IMPORTANT]  
> Please review the backend pipelines. 
> 1. For **Exclusionary Search**, disabling the final native Google Grounding prevents the agent from accidentally pulling mainstream data back in while writing its report. Do you agree with this safety lock?
> 2. For **Brave and Local Memory**, using lightweight "pre-injection" context blocks is the most stable way to feed data to the agent without requiring the agent to manually invoke python tools. Are you comfortable with this injection method?
