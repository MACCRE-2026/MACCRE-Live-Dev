# Handover Report: MACCREv2 to EXO-GANS Pivot

**Date**: May 30, 2026
**Target**: Next Primary Engineering Agent

## 1. Strategic Pivot Summary

We are initiating a major strategic pivot in preparation for publishing the functional core of the MACCREv2 architecture to GitHub under the community-focused project name **EXO-GANS**.

The primary objective is to distill the existing architecture into a highly reliable, text-only pipeline dedicated to **agentic writing, research, and epistemic concept exploration.**

### Paused Subsystems (Do Not Modify / Do Not Delete)
- **Audio & Video Pipelines**: All TTS and visual rendering streams are considered vital long-term but are indefinitely sidelined. Focus is strictly on the text-based Live Orchestration.
- **Local & Edge Compute Nodes**: We are pausing the active use of local hardware (e.g., S25 Edge processing, local Ollama instances) until future hardware upgrades. The infrastructure will remain intact but dormant. All live orchestration will strictly utilize Cloud models.

## 2. Assessment of Current Local Model Infrastructure
*As an FYI regarding what you are inheriting, here is how the codebase is currently wired for local models before putting it on ice.*

The MACCREv2 network layer (`omnidaemon.py` and `maccre_router.py`) currently features a fully functional "Strangler Fig" routing system that intercepts generation requests and targets local APIs:
1. **Model Tag Parsing (`maccre_router.py`)**: Detects `edge-` tags for S25 routing (`tier="edge"`) and `gemma`/`llama` tags for local routing (`tier="local"`).
2. **The OmniDaemon (`omnidaemon.py`)**: Contains `_route_local` (localhost:11434) and `_route_edge` (Wi-Fi Edge Node) logic.
3. **Schema Injection**: Both local tiers successfully inject Pydantic/Sovereign Schemas into prompts to force structured JSON from local nodes.

**Status**: Highly functional but currently suspended. We will rely solely on the `_route_cloud` pathways moving forward.

## 3. The Nexus Agent (The Operator)
To run the EXO-GANS pipeline, we will build a specialized orchestrator agent named **"Nexus."** 

Nexus does *not* write Python or fix the pipeline. Its sole purpose is to operate the machine.

### Specifications & Constraints:
- **Core Loop**: Converses with the user -> Formats conversations -> Writes Workbooks -> Executes `maccre.py` to trigger predefined swarms or live agents.
- **Agent Minting**: Capable of using existing agent minting functions to spawn new persona nodes for the user dynamically.
- **Strict Silo (No Code Access)**: Nexus is hardcoded to *only* access the Global and Project-level datacenters (e.g., `01_Raw_Source` through `05_Rendered_Media`). It cannot read or modify the Python codebase.
- **UI / Ephemerality Engine**: Operates within a multi-window-plex chat interface. It has "tunable ephemerality," meaning its chat window supports conversation selection. The user can swap between active contexts or link specific conversation histories to the active state, keeping context strictly divided.
- **Logical Emulsions**: Employs a perfect mixture of probability (creative conversation) and determinism (strictly executing MACCRE doctrine tools).

## 4. The Final Systems Audit & Dev-Ops Action Plan
Before EXO-GANS can be packaged, you (the new dev-agent) and the user will conduct a dev-ops phase to verify 100% flawless execution of the text pipeline. 

### Required Actions for the New Agent:
1. **Deep Codebase Review (Multi-Pass)**: 
   - Perform a deep scan of the existing codebase to uncover hidden gems regarding deterministic agent minting. We want to leverage existing logic to radically simplify how Nexus mints agents.
2. **Hunt for Dead Ends**: 
   - Identify unwired dead ends. There are legacy functions that mathematically pass CI/CD (`omni qa`) but are effectively obsolete within the new text-only EXO-GANS scope. Catalog these so they can be isolated.
3. **Flawless Execution Verification**: 
   - Verify that routing, agent minting, and workbook creation via `maccre.py` work seamlessly using cloud models only. Ensure strict compliance with MACCRE design doctrine.

## 5. Roadmap Note
**Do not write the new EXO-GANS Publication Doctrine yet.** The new doctrine and publication documentation will be written *after* you and the user finish the deep codebase review and dev-ops audit outlined in Section 4.
