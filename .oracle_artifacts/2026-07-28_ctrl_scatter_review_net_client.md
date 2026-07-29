# CTRL_SCATTER Expansion Plan Review — Net & Client Subsystem Audit

**Specialist Oracle:** NetAndClient_Oracle  
**Target Architecture:** MACCREv2 / EXO_GANS Sovereign Edge  
**Date:** 2026-07-28  
**Scope:** Evaluation of `ctrl_scatter-expansion plan-v1.md`, `v2.md`, and `v3.md` across REST Client compliance, API rate limits (RPM/TPM), Hardware Probing, Memory Footprint, Payload Sizing, and Model Sentinel Telemetry.

---

## 1. Progression Analysis (v1 → v2 → v3)

### Version 1 (`ctrl_scatter-expansion plan-v1.md`)
- **Focus:** Basic TUI slotting UI (`NexusPlex`) and dynamic macro node auto-wrapping in `flow_engine.py`.
- **Net & Client Perspective:** Purely sequential execution. Treated `CTRL_SCATTER` auto-wrapped topology as simple string node mapping. No consideration of HTTP connection overhead, rate limits, model health tracking, or hardware constraints.

### Version 2 (`ctrl_scatter-expansion plan-v2.md`)
- **Focus:** Introduced Scope Separation (Phase 4.75.7 vs Phase 6 deferrals) and concurrency analysis. Proposed `MAX_SCATTER_AGENTS = 5`.
- **Net & Client Perspective:** Flawed API bottleneck premise — assumed free-tier Gemini limits (~30 RPM). Focused heavily on single-writer SQLite WAL lock contentions while underestimating paid-tier network throughput.

### Version 3 (`ctrl_scatter-expansion plan-v3.md` - Current Revision)
- **Focus:** Integrated telemetry vector groundwork (`flow_vector` in `task_queue`), default expanded visualizer, visionary Phase 7 time-travel replay/perspectives, and corrected API rate limit assumptions. Proposed `MAX_SCATTER_AGENTS = 8` (hard cap 12).
- **Net & Client Perspective:** Accurate paid-tier Gemini API mapping (~1,000–2,000 RPM, 2M–4M TPM). Introduced solid grounding for future WAL sharding (§6.13) and vector-indexed execution traces (A5).

---

## 2. Domain Technical Evaluation (`maccre_core/_net/`)

### A. Zero-SDK `urllib` Compliance & Multi-Threading Socket Dynamics
- **Standard Library Transport (`gemini_client.py`):** Operates without `requests` or `httpx`, relying purely on `urllib.request`.
- **Parallel Network I/O (Phase 6 ThreadPoolExecutor):** Under CPython, socket I/O performed by `urllib` releases the GIL. Parallel execution of 8 agents will achieve **true concurrent HTTP socket transmission**.
- **Connection Overhead Risk:** Standard `urllib.request.urlopen()` initiates a fresh TLS 1.3 handshake per request unless sockets are reused. A burst of 8 parallel scatter requests will initiate 8 simultaneous TCP/TLS connections to `generativelanguage.googleapis.com`. Total setup overhead is ~100–200ms across threads, which is completely acceptable compared to standard LLM generation latencies (1.5s - 4.0s).

### B. Gemini Paid-Tier Rate Limits & Throughput (RPM / TPM)
- **Quota Calculations for `MAX_SCATTER_AGENTS = 8`:**
  - **RPM Consumption:** 8 slotted agents executing 1–3 LLM calls each = 8–24 total requests per scatter event. Against a 1,000 RPM paid-tier ceiling, this consumes **0.8% - 2.4%** of available capacity.
  - **TPM Consumption:** Assuming an average prompt context of 10,000 tokens (system prompt + payload) + 2,000 output tokens = 12,000 tokens per agent. 8 agents = 96,000 tokens per scatter step. Against a 2M–4M TPM limit, this represents **2.4% - 4.8%** of the minute quota.
- **Validation:** `MAX_SCATTER_AGENTS = 8` (with hard cap 12) is **100% valid, safe, and optimal** for cloud API transport.

### C. Memory Footprint & Payload Sizing
- **RAM Footprint:** Each worker thread consumes ~1–2 MB stack space + ~2–5 MB dict context (payload + prompt + response). 8 parallel agents require **~30–50 MB total RAM**, which is negligible on modern host hardware.
- **Network Payload Sizing:** In `scatter_mode = "full_copy"`, duplicating a 50 KB JSON payload across 8 agents yields 400 KB of cumulative outbound JSON data. Transmitting 400 KB over standard `urllib` HTTP POST bodies requires <15ms on broadband connections. Network payload sizing is NOT a bottleneck.

---

## 3. Omissions & Dropped Technical Requirements (v1/v2 → v3)

The audit identified **3 critical domain omissions** in v3 that must be addressed during implementation:

1. **RAM Key Zeroing (`ctypes.memset`) Thread-Safety Vulnerability:**
   - `gemini_client.py` and `universal_vault.py` call `wipe_string()` / `ctypes.memset()` to scrub sensitive API key buffers from memory post-request.
   - *Risk:* In Phase 6 parallel thread execution, if Thread 1 finishes early and wipes the shared in-memory key buffer while Thread 7 is currently constructing its `urllib` `Authorization` header, Thread 7 will encounter a memory access fault or transmit an empty key!
   - *Fix:* API key buffers MUST be passed as immutable thread-local strings or protected by a reference-counted key manager that delays zeroing until all parallel worker threads complete.

2. **Hardware Probing & Edge/Local Model (Ollama) Overload:**
   - `environment_probe.py` probes Ollama on `localhost:11434`.
   - *Omission:* v3 assumes all scattered agents run on cloud Gemini models. If a user sets `Model_Override` in agent slots to a local Ollama model (e.g. `gemma3:9b`), firing 8 parallel requests at local Ollama will cause severe VRAM Out-Of-Memory (OOM) crashes or context thrashing.
   - *Fix:* `flow_engine.py` auto-wrap MUST check `environment_probe.py` / `model_registry.py`. If slotted agents target local Ollama models, `MAX_SCATTER_AGENTS` MUST be dynamically constrained to `min(OLLAMA_NUM_PARALLEL, 2)`.

3. **Model Sentinel Telemetry Burst False Positives:**
   - `model_sentinel.py` tracks model health via a sliding window (`WINDOW_SIZE = 20`, 30% error threshold = `DEGRADED`).
   - *Risk:* If a transient Google API HTTP 503 network failure occurs during an 8-agent scatter burst, all 8 requests fail simultaneously. This single event pushes the error window to 8/20 = 40% error rate, triggering a false `MODEL_DEGRADED` state across the entire application.
   - *Fix:* Model Sentinel error recording must aggregate concurrent scatter failures into a single window metric or apply exponential jitter retry in `gemini_client.py` before reporting failures to Model Sentinel.

---

## 4. Strategic Optimization Proposals

1. **Jittered Retry in Zero-SDK HTTP Client (`gemini_client.py`):**
   Implement standard-library exponential backoff with randomized jitter inside `gemini_client.py` for transient HTTP 429 / 503 codes during parallel scatter requests.
2. **Thread-Safe Key Isolation:**
   Scope API key strings to thread-local contexts during parallel `ThreadPoolExecutor` scatter runs.
3. **Local Compute Guardrail:**
   Enforce dynamic down-throttling of scatter width when hardware probing detects local edge model routing.

---

## 5. Verification & Omni QA Directives

All new routing and client logic introduced for `CTRL_SCATTER` must satisfy strict Omni-Builder doctrine:
- `omni qa maccre_core/_net/gemini_client.py`
- `omni qa maccre_core/_net/environment_probe.py`
- `omni qa maccre_core/_net/model_sentinel.py`
