# ERA 3 ARCHITECTURAL ROADMAP: PHASE 9 ADDITION (NET & CLIENT SUBSYSTEM)

**Domain:** `maccre_core._net` (Sovereign REST Client, Model Sentinel, Transcripts, Deployment Testing)  
**Authoring Specialist:** Net & Client Specialist Oracle  
**Date:** 2026-07-25  
**Compliance Standard:** Sovereign Edge Omni-Builder Doctrine & Law Rev 19.0  

---

## EXECUTIVE SUMMARY & PHASE 9 VISION

Phase 9 establishes the **In-State Live Development & Antigravity Desktop Transition Bridge**. It completes the transition from external desktop dependencies to an internal, sovereign **Chat Studio session** embedded directly in the MACCRE TUI, anchored to local virtual environments (`.venv`) and 5-tier datacenter silos (`01_Raw_Source` through `05_Rendered_Media`).

Within the `maccre_core._net` subsystem, Phase 9 delivers:
1. **Bi-Directional JSONL <-> 3-Tuple REST Translation Engine:** Native mapping between `transcript_full.jsonl` conversation records and `gemini_client.py` 3-tuple returns `(output_text, cost, api_thought)` and REST `thinkingConfig` payloads.
2. **Automated Deployment Candidate Testing Engine:** Zero-SDK automated pre-flight testing of deployment candidates, validating endpoint latency, thinking payload injection, and RAM key sanitization before production topology promotion.
3. **Zero-SDK REST Transport Bridge for In-State Chat Studio:** Direct `urllib`-based streaming and state synchronization supporting live Chat Studio sessions without external CLI or SDK reliance.

---

## SUBSYSTEM STATUS & ROADMAP MATRIX (PHASE 9 UPDATE)

| Subsystem Scope | Implemented Bedrock | Phase 9 Strategic Addition |
| :--- | :--- | :--- |
| **Net & Client** (`maccre_core._net`) | Pure `urllib` REST client, `thinkingConfig` 3-tuple returns `(output_text, cost, api_thought)`, `ModelSentinel` capacity tracking, RAM key zeroing (`ctypes.memset`). | Bi-directional JSONL (`transcript_full.jsonl`) translation engine, automated zero-SDK deployment candidate testing harness, Chat Studio native REST transport bridge. |

---

## SECTION 9: PHASE 9 DETAILED ROADMAP SPECIFICATIONS

### 9.1 Net & Client Subsystem Scope
* **Native Chat Studio Transport Bridge:** Direct coupling of `maccre_tui` Chat Studio sessions to `gemini_client.py` and `OmniDaemon` using standard library `urllib` transport, bypassing external process invocation.
* **Datacenter Path Anchoring:** All session ledgers, transcript logs, and telemetry are anchored via `get_maccre_root()`, enforcing strict compliance with Law IV (Datacenter Silos) and Law VIII (Path Anchoring).

### 9.2 Bi-Directional Conversation JSONL <-> REST Payload Translator (`gemini_client.py`)
* **Ingest Translation (JSONL -> REST Payload):**
  - Parses `transcript_full.jsonl` multi-turn history into standard REST `contents[]` payloads.
  - Extracts system roles into `systemInstruction` parts.
  - Formats thought content into native Gemini 3.x `thinkingConfig` (`thinkingBudget`, `includeThoughts`).
* **Egress Translation (REST 3-Tuple -> JSONL Record):**
  - Restructures `GeminiResponse` output into JSONL turn entries containing `(output_text, cost, api_thought)`.
  - Computes USD cost via `ModelSentinel` pricing catalog and attaches prompt/candidate token metrics.
  - Retains raw grounding sources and tool call structures in JSONL metadata.

### 9.3 Automated Deployment Candidate Testing Harness (`deployment_tester.py`)
* **Pre-Flight Candidate Validation:** Automated suite verifying model candidates before topology registration.
* **Zero-SDK REST Compatibility:** Uses pure standard library `urllib.request` to test live endpoints, verifying `thinkingConfig` parsing, sliding-window latency, and HTTP response codes.
* **RAM Sanitization Inspection:** Verifies API key memory buffers are zeroed via `ctypes.memset` post-test call.

### 9.4 Architectural Edge Cases & Mitigations
* **Memory Hygiene:** Context-managed `SovereignKeyEnclave` wrappers around JSONL transcript processing buffers to prevent RAM key exposure.
* **Offline Resiliency:** Automatic fallback from Gemini Cloud REST endpoints to local Ollama endpoints (`http://localhost:11434`) via `environment_probe.py` upon network failure.
* **Token Window Management:** Pre-flight REST token counting (`countTokens`) and context window truncation prior to sending large transcript payloads.

---

## IMPLEMENTATION TIMELINE FOR PHASE 9

```
+-----------------------------------------------------------------------------------+
|                        PHASE 9 EXECUTION TIMELINE                                 |
+-----------------------------------------------------------------------------------+
| PHASE 9.1: BI-DIRECTIONAL TRANSCRIPT TRANSLATOR                                  |
|   - Implement JsonlTranscriptTranslator in maccre_core/_net/gemini_client.py     |
|   - Unit test JSONL <-> (output_text, cost, api_thought) 3-tuple roundtrips       |
|                                                                                   |
| PHASE 9.2: AUTOMATED DEPLOYMENT CANDIDATE TEST HARNESS                           |
|   - Implement DeploymentCandidateTester in maccre_core/_net/deployment_tester.py  |
|   - Integrate zero-SDK candidate probing into omni qa / omni run pipeline         |
|                                                                                   |
| PHASE 9.3: CHAT STUDIO REST TRANSPORT BRIDGE INTEGRATION                          |
|   - Wire maccre_tui Chat Studio session directly to GeminiClient REST transport  |
|   - Verify datacenter anchoring (03_Agent_Ledgers/ & system_logs.db logging)     |
+-----------------------------------------------------------------------------------+
```
