# Net & Client Specialist Oracle Audit Report: Phase 4.99 & Era 2/3 Roadmap Alignment

**Author:** `NetAndClient_Oracle`  
**Date:** 2026-08-09  
**Domain Scope:** `maccre_core/_net/` (`gemini_client.py`, `environment_probe.py`, `model_sentinel.py`, `model_registry.py`, `omnidaemon.py`, `ooxml.py`, `client_interface.py`, `live_client.py`)  
**Verification Status:** `omni qa .` Clean (0 errors, 0 warnings)  

---

## 1. Executive Summary & Verification Baseline

The `maccre_core._net` subsystem constitutes the zero-dependency networking, inference routing, hardware probing, and document generation core of the MACCREv2 sovereign edge architecture.

A full system-wide quality gate check (`omni qa .`) was executed prior to audit synthesis, confirming:
- **Ruff Linter:** 100% pass across all files.
- **Pyright Type Checker:** 0 errors, 0 warnings.
- **Zero-SDK REST Standard:** 100% pure Python `urllib.request` REST compliance across `gemini_client.py`, `model_sentinel.py`, `model_registry.py`, `environment_probe.py`, and `omnidaemon.py` (with 1 documented WebSocket exception in `live_client.py`).

This audit evaluated all 8 domain modules against **Phase 4.99** (Immediate User Testing & Production Boundary) and the strategic goals of **Era 2** & **Era 3** roadmaps.

---

## 2. Detailed Codebase Audit Findings & Loose End Analysis

### Finding 1: `OmniDaemon` Plaintext API Key Memory Persistence
- **File:** `maccre_core/_net/omnidaemon.py` (Line 81)
- **Description:** `OmniDaemon.__init__` assigns `self.api_key = get_provider_credential("MACCRE_Sovereign")`. Storing the plaintext API key string as an instance attribute retains credentials in Python heap memory indefinitely without calling `wipe_string()`. This violates Sovereign Edge Law VII (Teardown & Memory Sanitization).
- **Risk Impact:** High. API keys remain exposed in process memory dumps.
- **Roadmap Pinning:** **Phase 4.99 (Immediate User Testing / Production Boundary)**.

### Finding 2: `ModelSentinel` Rate-Limit False-Degradation in 8-Agent Scatter Bursts
- **File:** `maccre_core/_net/model_sentinel.py` (Lines 75–117)
- **Description:** `ModelHealth` uses a sliding window of 20 calls with a 30% error threshold (`DEGRADED_THRESHOLD = 0.30`). During high-concurrency 8-agent parallel scatter bursts (~1,000+ RPM), transient 429 rate-limit responses or momentary TCP drops can cause 2–3 requests to fail simultaneously. This prematurely trips `MODEL_DEGRADED` or `QUOTA_EXHAUSTED` events, degrading healthy models across the entire application.
- **Risk Impact:** High. Prevents full paid-tier throughput during 8-agent scatter bursts.
- **Roadmap Pinning:** **Phase 4.99 (Immediate User Testing / Production Boundary)**.

### Finding 3: Incomplete Dataclass JSON Schema Converter in `OmniDaemon`
- **File:** `maccre_core/_net/omnidaemon.py` (Lines 36–74)
- **Description:** `_dataclass_to_json_schema` handles primitive types (`str`, `int`, `float`, `bool`) but maps `list` and `dict` as flat `"array"` / `"object"` types without inner element schemas or recursive dataclass parsing.
- **Risk Impact:** Medium. Quadrivector Structured Output (Pass 2) for complex nested schemas may omit validation rules for array items.
- **Roadmap Pinning:** **Phase 4.99 (Immediate User Testing / Production Boundary)**.

### Finding 4: Fragile Network Exception Handling in Hardware Probe
- **File:** `maccre_core/_net/environment_probe.py` (Lines 34–40)
- **Description:** `get_environment_matrix()` catches `(urllib.error.URLError, ConnectionError)` when probing Ollama port 11434, but misses Python 3.11 `TimeoutError`, `socket.timeout`, `http.client.RemoteDisconnected`, or `OSError`. Severed or hanging sockets can emit unhandled exceptions.
- **Risk Impact:** Medium. Could destabilize startup or background probing when Ollama is in a hung state.
- **Roadmap Pinning:** **Phase 4.99 (Immediate User Testing / Production Boundary)**.

### Finding 5: Lack of VRAM & GPU Memory Probing in `environment_probe.py`
- **File:** `maccre_core/_net/environment_probe.py` (Lines 43–48)
- **Description:** Hardware heuristic only checks logical CPU core count (`os.cpu_count() >= 8`). It does not probe available GPU VRAM or host RAM headroom before routing local inference tasks to Ollama.
- **Risk Impact:** Medium. Local 8-agent scatter bursts can cause VRAM thrashing or OOM crashes on edge devices.
- **Roadmap Pinning:** **Phase 6 (Era 3 §1.3 — Hardware-Aware Real-Time Load Balancer)**.

### Finding 6: Hardcoded Model Identifiers & Provider Tokens in `OmniDaemon`
- **File:** `maccre_core/_net/omnidaemon.py` (Lines 88, 130)
- **Description:** `_route_local` hardcodes payload model to `"gemma"`. `_route_edge` uses hardcoded header `"Authorization": "Bearer edge-token"`.
- **Risk Impact:** Low/Debt. Restricts dynamic local model selection and edge auth configuration.
- **Roadmap Pinning:** **Net & Client Domain Debt / Loose End** (To align with Phase 8 `CTRL_EDGE_SYNC` v2).

### Finding 7: Gemini Live Client Reconnect & Resilience Gaps
- **File:** `maccre_core/_net/live_client.py` (Lines 26–44)
- **Description:** `GeminiLiveClient` handles single session connections with modality locked to `[types.Modality.TEXT]`. It lacks automatic WebSocket reconnect, ping/pong heartbeat monitoring, or exponential backoff on connection drop.
- **Risk Impact:** Medium. Long-running TUI live chat sessions fail on transient network hiccups.
- **Roadmap Pinning:** **Phase 8 (Era 3 §1.2 / 8.1 — Edge Mesh & Live WebSocket Resilience)**.

### Finding 8: `ThinkingConfig` & 3-Tuple Return Integration Gaps in Router
- **Files:** `maccre_core/_net/client_interface.py`, `gemini_client.py`, `omnidaemon.py`
- **Description:** `GeminiClient` natively injects `thinkingConfig` and `GeminiResponse` extracts `scratchpad_thought`. However, `OmniDaemon.generate()` does not expose `thinking_config` or return the 3-item tuple `(output_text, cost, api_thought)` required by Phase 9 `JsonlTranscriptTranslator`.
- **Risk Impact:** Low/Future. Blocks Phase 9 transcript translation.
- **Roadmap Pinning:** **Phase 9 (Era 3 §1.3 — JSONL Transcript Translator)**.

### Finding 9: Sovereign OOXML Writer Scope Boundaries
- **File:** `maccre_core/_net/ooxml.py`
- **Description:** 100% zero-dependency `.xlsx` generation is operational for writing workbooks, styling, merging, and data validations. Intake operations (`sheet_parser.py`) remain dependent on vendored `openpyxl`.
- **Risk Impact:** None (by design). Scope is write-only.
- **Roadmap Pinning:** **Past Phase (Phase 1D Bedrock / Phase 4.99 Tier 2 Action 2)**.

---

## 3. Comprehensive Roadmap Pinning Matrix

| # | Finding / Component | Past Phase | Phase 4.99 (Immediate Boundary) | Future Phase (Era 3) | Domain Debt / Loose End |
|---|---------------------|:----------:|:------------------------------:|:--------------------:|:-----------------------:|
| 1 | `OmniDaemon` Plaintext API Key Memory Persistence | | **FIX REQUIRED** | | |
| 2 | `ModelSentinel` Burst False-Degradation | | **FIX REQUIRED** | | |
| 3 | `OmniDaemon` Nested Dataclass JSON Schema Converter | | **ENHANCE** | | |
| 4 | `environment_probe.py` Socket Exception Resilience | | **FIX REQUIRED** | | |
| 5 | `environment_probe.py` Hardware VRAM Probing | | | **Phase 6** (§6.12/Era3 §1.3) | |
| 6 | Hardcoded Edge Token & Local Model ID in `OmniDaemon` | | | | **Domain Debt** |
| 7 | `live_client.py` WebSocket Reconnect & Modality Lock | | | **Phase 8** (Live Resilience) | |
| 8 | `thinkingConfig` 3-Tuple Return Contract in Daemon | | | **Phase 9** (Transcript Translator) | |
| 9 | `ooxml.py` Write-Only Scope | **Phase 1D** | Verified in User Test 2 | Era 3 Native Reader | |
| 10| `gemini_client.py` urllib REST Paid-Tier Throughput | **Phase 4.1** | Verified for 8-Agent Scatter | Era 3 HTTP/2 | |

---

## 4. Phase 4.99 User Testing Alignment & Execution Checklist

All 7 Net & Client User Testing Actions specified in `2026-07-28_phase4_99_user_test_actions_net_client.md` are aligned with the Phase 4.99 execution plan:

1. **User Action 1 (8-Agent Scatter Burst)**: Stress test `GeminiClient` urllib throughput under 8 concurrent worker threads with latency tracking in `ModelSentinel`.
2. **User Action 2 (ctypes.memset Key Zeroing under Concurrency)**: Validate `wipe_string()` thread-safety during parallel key requests.
3. **User Action 3 (Hardware Probe Network Drop)**: Simulate Ollama port 11434 drop and verify fallback to Cloud tier without unhandled exceptions.
4. **User Action 4 (Gemini Live WebSocket Resilience)**: Validate `[types.Modality.TEXT]` lockdown and credential zeroing in `finally` blocks.
5. **User Action 5 (Model Sentinel Surface Degradation)**: Verify intra-surface failover when primary model reports errors.
6. **User Action 6 (Vault Credential Wiping)**: Verify DPAPI/Fernet key retrieval and immediate buffer clearing.
7. **User Action 7 (OOXML Packaging Stress)**: Generate multi-sheet workbook with formulas, merged cells, and dropdown data validations via `ooxml.py`.

---

## 5. Conclusion & Action Plan

The Net & Client subsystem is structurally sound, type-safe, and 95%+ zero-SDK compliant. To guarantee 100% success during Phase 4.99 user testing, the following immediate items are recommended for resolution prior to production release:

1. Refactor `OmniDaemon.__init__` to avoid storing `self.api_key` as a persistent string attribute; retrieve key dynamically per call and wipe buffers immediately.
2. Upgrade `environment_probe.py` exception block to catch `(urllib.error.URLError, ConnectionError, TimeoutError, OSError)`.
3. Adjust `ModelHealth.DEGRADED_THRESHOLD` or burst window evaluation during `CTRL_SCATTER` execution to prevent false-degradation triggers.
4. Extend `_dataclass_to_json_schema` in `omnidaemon.py` to handle nested lists and dict schemas for Quadrivector structured output generation.
