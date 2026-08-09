# Phase 4.99 User Test Actions: Net & Client Subsystem (`maccre_core._net`)

**Author:** NetAndClient_Oracle  
**Timestamp:** 2026-07-28T21:38:31-04:00  
**Target Domain:** Sovereign Edge Transport, REST API Client, Model Sentinel, Capability Classification, Hardware Probing & OOXML Engine  

---

## Overview & Scope
This test action suite defines 7 high-stress operational test scenarios for Phase 4.99 validation of MACCREv2 / EXO_GANS. The actions enforce strict adherence to the Sovereign Physical Laws: zero-SDK `urllib` REST compliance, RAM key zeroing (`ctypes.memset`), multi-agent scatter throughput under paid Gemini quotas (~1,000+ RPM / 2M+ TPM), local Ollama hardware probing, stateful WebSocket handling, dynamic model surface degradation failovers, and zero-dependency OOXML workbook packaging.

---

## Phase 4.99 User Test Action Suite

### Test Action 1: Zero-SDK `urllib` REST Scatter Burst under Paid Gemini API Quotas
- **Action Title & Target Component:** Paid-Tier Parallel REST Burst Validation (`maccre_core._net.gemini_client.GeminiClient` & `maccre_core.orchestration.swarm_worker.SwarmWorker` / `CTRL_SCATTER`)
- **Step-by-Step Operator Action:**
  1. Initiate an 8-node `CTRL_SCATTER` execution issuing concurrent heavy generative prompts via `GeminiClient.generate()`.
  2. Configure paid-tier Gemini API credentials to simulate sustained high-concurrency traffic (~1,000+ RPM / 2M+ TPM target).
  3. Monitor socket creation, headers (`User-Agent: MACCREv2-SovereignClient/4.1`), request body serialization, and JSON response parsing.
- **Edge-Case / Stress Condition:** High-concurrency burst forcing intermittent 429 HTTP (Rate Limit Exceeded) and 503 HTTP (Service Unavailable) status codes while underlying OS socket pools experience high load.
- **Expected System Behavior & Net/Client Domain Validation Criteria:**
  - 100% pure standard library `urllib.request` / `urllib.error` execution (zero dependency on `google-genai` SDK, `requests`, or `httpx`).
  - Native exponential backoff with jitter in `gemini_client.py` gracefully absorbs 429 status codes without worker deadlocks or unhandled HTTP exceptions.
  - Structured output schemas correctly enforced via diamond loop critics (`temp=0.1` + Pydantic `BaseModel`).
  - Throughput metrics and latency distributions accurately tracked in `ModelSentinel` telemetry logs.

---

### Test Action 2: Multi-Threaded RAM Key Zeroing (`ctypes.memset`) Memory Sanitation Audit
- **Action Title & Target Component:** Concurrent Key Sanitation & Heap Security (`maccre_core.orchestration.universal_vault.wipe_string` & `maccre_core._net.gemini_client` / `model_sentinel.py` / `live_client.py`)
- **Step-by-Step Operator Action:**
  1. Trigger a high-frequency multi-threaded API invocation sweep (50 parallel requests), injecting raw API keys into key provider callbacks.
  2. Ensure `wipe_string(raw_key)` is executed inside `finally` blocks immediately post-request.
  3. Inspect Python process heap memory dumps before, during, and after key sanitization.
- **Edge-Case / Stress Condition:** Race conditions on C-Python string buffer memory during parallel thread execution where `ctypes.memset(address, 0, length)` mutates string memory addresses simultaneously.
- **Expected System Behavior & Net/Client Domain Validation Criteria:**
  - Heap inspection confirms that raw API key character buffers are replaced with null bytes (`0x00`) post-call.
  - Zero `AccessViolationError`, C-level segmentation faults (SIGSEGV), or thread crashes occur during parallel key overwrites.
  - Exception paths in REST and WebSocket clients guarantee key sanitation even when socket connection or HTTP errors occur.

---

### Test Action 3: Hardware Probe Failover & Ollama Local Model Network Partition Override
- **Action Title & Target Component:** Dynamic Compute Matrix & Local Edge Fallback Probing (`maccre_core._net.environment_probe.get_environment_matrix` & `maccre_core._net.omnidaemon.OmniDaemon` / `model_registry.py`)
- **Step-by-Step Operator Action:**
  1. Execute `get_environment_matrix()` while Ollama service on `http://localhost:11434` is offline.
  2. Dynamically start Ollama mid-execution, followed by an artificial socket hang / network drop on port 11434.
  3. Mock restricted CPU environment where `os.cpu_count()` returns `None` or `1`.
- **Edge-Case / Stress Condition:** Ollama port returns partial HTTP 500 responses or socket hangs indefinitely during `/api/tags` probing, or local system VRAM saturates during edge model dispatch.
- **Expected System Behavior & Net/Client Domain Validation Criteria:**
  - `get_environment_matrix()` strictly enforces `timeout=1.0` on `urllib.request.urlopen`, safely catching `urllib.error.URLError` and `ConnectionError`.
  - Matrix dynamically sets `ollama_active = False` without raising unhandled exceptions or blocking workflow execution.
  - `OmniDaemon` seamlessly reroutes work from edge models to cloud Gemini API or local fallback surfaces based on probe results.

---

### Test Action 4: Gemini Live WebSocket API Drop & Stateful Re-connection Stress
- **Action Title & Target Component:** Real-Time Bi-Directional WebSocket Resilience (`maccre_core._net.live_client.GeminiLiveClient` & `google.genai.types.LiveConnectConfig`)
- **Step-by-Step Operator Action:**
  1. Establish an active WebSocket session using `GeminiLiveClient.run_session()` with model `gemini-2.0-flash`.
  2. Transmit continuous text modality streams while artificially severing TCP socket connectivity.
  3. Attempt requesting audio modality to test modality lockdown enforcement.
- **Edge-Case / Stress Condition:** Abrupt TCP socket disconnection during active streaming, session token expiration, and execution in non-desktop environments (Termux/Android).
- **Expected System Behavior & Net/Client Domain Validation Criteria:**
  - WebSocket client strictly locks `response_modalities` to `[types.Modality.TEXT]`, preventing `pyaudio`/`sounddevice` dependency crashes.
  - Disconnection exceptions are cleanly caught in `run_session()`'s `finally` block, triggering `wipe_string(raw_key)` to prevent credential leakage in async task context.
  - Structured event logs recorded to `03_Agent_Ledgers` without orphan socket leaks.

---

### Test Action 5: Model Sentinel Surface Degradation & Quadrivector Intra-Surface Failover
- **Action Title & Target Component:** Adaptive Health Telemetry & Capability Failover Routing (`maccre_core._net.model_sentinel.ModelSentinel` & `maccre_core._net.model_registry.ModelRegistry`)
- **Step-by-Step Operator Action:**
  1. Inject consecutive HTTP 500/503/429 errors into `ModelSentinel.record_call()` for primary model surface (`gemini-2.5-pro`).
  2. Observe Sentinel health score recalculation and subsequent routing decision by `ModelRegistry.get_optimal_model()`.
  3. Restore API status and verify automatic recovery re-elevation of primary tier.
- **Edge-Case / Stress Condition:** Complete failure of primary and secondary cloud models during multi-agent pipeline execution, forcing failover down to local edge surface or offline stasis.
- **Expected System Behavior & Net/Client Domain Validation Criteria:**
  - `ModelSentinel` marks primary surface as `DEGRADED` / `OFFLINE` when error rates exceed threshold (>30% failure or latency spike).
  - `ModelRegistry` automatically reroutes active calls to secondary capability surfaces (`gemini-2.5-flash` -> local edge Ollama) without throwing unhandled exceptions.
  - Real-time status changes persisted to `03_Agent_Ledgers/model_sentinel_telemetry.json`.

---

### Test Action 6: Vault Authentication Failure & Zero-SDK Error Recovery
- **Action Title & Target Component:** REST Client Auth Resilience & Credential Protection (`maccre_core._net.gemini_client.GeminiClient` & `maccre_core.orchestration.access_control`)
- **Step-by-Step Operator Action:**
  1. Pass corrupted, expired, or zero-byte API keys into `GeminiClient` during generation and streaming requests.
  2. Inspect exception object content, stack traces, and JSON log output during auth failure.
- **Edge-Case / Stress Condition:** HTTP 401 Unauthorized / HTTP 403 Forbidden responses returned by Google REST endpoints with malformed error bodies.
- **Expected System Behavior & Net/Client Domain Validation Criteria:**
  - `GeminiClient._call()` traps `urllib.error.HTTPError`, parses standard Google API error payloads, and raises typed sovereign exceptions (`AuthError`/`SovereignNetError`).
  - Raw API key strings are NEVER formatted into exception messages, log lines, or HTTP trace dumps.
  - `wipe_string()` executes unconditionally in `finally` blocks regardless of HTTP status code.

---

### Test Action 7: High-Throughput OOXML Workbook Materialization & Stream Integrity
- **Action Title & Target Component:** Zero-Dependency Excel Packaging Engine (`maccre_core._net.ooxml.OOXMLWorkbook`)
- **Step-by-Step Operator Action:**
  1. Provide a massive data matrix (10,000+ rows, 50+ columns containing formulas, dynamic styling, and raw text) to `OOXMLWorkbook`.
  2. Trigger zip stream compilation and write archive to `05_Rendered_Media/test_output.xlsx`.
  3. Validate spreadsheet structure using external zip verification and open in Excel/OpenOffice.
- **Edge-Case / Stress Condition:** Ingestion of invalid XML characters (`<`, `>`, `&`, control characters `0x00-0x1F`), memory pressure during string building, and write handle interruptions.
- **Expected System Behavior & Net/Client Domain Validation Criteria:**
  - Zero third-party dependencies (`openpyxl`, `xlsxwriter`, `pandas`).
  - Automatic escaping of XML entities prevents corrupted `.xlsx` archive structures.
  - File handles closed safely in `finally` context managers, preventing zombie file locks on workspace artifacts.
