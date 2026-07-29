# ERA 3 ARCHITECTURAL ROADMAP: NET & CLIENT SUBSYSTEM (`maccre_core._net`)

**Domain:** Sovereign Edge Network, REST API Client, Hardware Probing, Model Management, Multi-Tier Routing, & Native OOXML Engine.  
**Specialist Oracle:** Net & Client Specialist Oracle  
**Date:** 2026-07-25  

---

## EXECUTIVE OVERVIEW

The `maccre_core._net` subsystem constitutes the zero-dependency networking, inference routing, capacity monitoring, and document generation backbone of MACCREv2 / EXO_GANS. Built under **Law VI (Abstraction)** and **Law VIII (Data Sovereignty)**, it enforces zero reliance on third-party SDKs (`google-genai`, `requests`, `httpx`, `openpyxl`, `pydantic`), relying exclusively on pure Python standard library modules (`urllib.request`, `urllib.error`, `json`, `ssl`, `zipfile`, `xml.etree.ElementTree`).

This document synthesizes the implemented state of the Net & Client subsystem, audits remaining Era 2 roadmap items, and articulates the strategic Era 3 architectural goals.

---

## 1. IMPLEMENTED NET & CLIENT FEATURES

| Feature / Module | Implementation Detail | Architectural Significance |
|------------------|----------------------|----------------------------|
| **Sovereign REST Client** (`gemini_client.py`) | Pure `urllib.request` implementation for Google Generative Language REST API (`generateContent`, `streamGenerateContent`, `embedContent`, `batchEmbedContents`, File API, Context Caching, Model Listing). | Standard library compliance; 100% decoupling from third-party SDKs (`google-genai`). |
| **API-Level Thinking Payload Injection** (`gemini_client.py` & `ReFactor_Redux-1a933d9.txt`) | Dynamically injects `thinkingConfig` (`thinking_budget` / `thinking_level`) into `generationConfig` for Gemini 3.x models (`gemini-3.1-pro-preview`, `gemini-3.5-flash`, `gemini-omni-flash-preview`). Restructured call returns to 3-item tuple `(output_text, cost, api_thought)`. | Enables native server-side reasoning payloads alongside prompt-based CoT `<thought>` blocks. |
| **Hardware & Service Probe** (`environment_probe.py`) | Probes host hardware and local services: active Ollama instance health on `localhost:11434` (`GET /api/tags`) and CPU logical cores (`os.cpu_count()`). | Edge compute awareness; pre-flight check before local inference dispatch. |
| **Model Sentinel Telemetry** (`model_sentinel.py`) | Thread-safe background daemon querying `GET /v1beta/models`, tracking capacity, sliding-window latency, error rates, and live model additions/deletions. | Real-time health monitoring and dynamic capacity routing. |
| **Model Surface Taxonomy & Failover** (`model_registry.py`) | Catalogue classifying 55+ models into 13 distinct capability surfaces (`ModelSurface`), building intra-surface failover chains wired directly to `ModelSentinel`. | Autonomous fallback routing when primary models experience rate limits or outages. |
| **Sovereign OOXML Engine** (`ooxml.py`) | Zero-dependency `.xlsx` workbook builder reproducing `openpyxl`'s API surface using `zipfile` and `xml.etree.ElementTree`. | Native, zero-overhead spreadsheet generation for automated reporting. |
| **RAM Key Sanitization** (`gemini_client.py`, `live_client.py`) | Explicit memory sanitization zeroing out API key byte buffers post-call via `ctypes.memset`. | Security hygiene preventing key leakage in process memory dumps. |
| **Multi-Tier Inference Routing** (`omnidaemon.py`) | Schema-driven JSON converter dynamically routing calls across `local` (Ollama), `edge`, `hybrid`, and `cloud` tiers. | Strangler Fig abstraction isolating application logic from underlying provider endpoints. |
| **Gemini Live WebSocket Client** (`live_client.py`) | Stateful bi-directional WebSocket client for Gemini Live API (`bidiGenerateContent`) with modality locking (Text-only for Termux/Android compatibility) and key zeroing. | High-frequency interactive streaming support. |

---

## 2. UNFINISHED & FUTURE NET/CLIENT ROADMAP ITEMS

The following features were identified across the 12 Era 2 roadmap/plan files as incomplete or scheduled for expansion:

### A. Mobile Edge NPU Cluster Integration (`CTRL_EDGE_SYNC` / `DET_WEBHOOK`)
* **Source:** `Era2_architectural_roadmap.md` (§4.1, §6.3), `FeatureRequests.md` (L133), `TUI_REFACTOR_PLAN.md` (§6.3)
* **Status:** Specified in Control Node registry; hardware transport layer unfulfilled.
* **Scope:** Offloading inference tasks to edge devices (e.g. Samsung S25 Ultra running local NPU models). Payload is dropped to a synchronized folder (Google Drive/Local Edge Sync) paired with a watchdog node that scales polling frequency (every 5 minutes → 5 seconds during active bursts → decay back to 5 minutes).

### B. GeminiClient SSE Token Streaming & Mid-Generation Pause
* **Source:** `EXO_GANS_Wishlist_Architecture.md` (Part 3 & Part 5 item 8/9)
* **Status:** `gemini_client.py` has basic batch endpoints; streaming payload processing in execution loops is unfulfilled.
* **Scope:** Standard library Server-Sent Events (SSE) stream parser for `streamGenerateContent`. Enables real-time token rendering in Textual TUI widgets, mid-generation pause/inspection, and immediate cancelation on operator abort.

### C. Multi-Provider Model Routing & Local Ollama Sharding Failover
* **Source:** `ctrl_scatter-expansion plan-v3.md` (Concurrency analysis), `EXO_GANS_Wishlist_Architecture.md` (Part 4)
* **Status:** `ModelRegistry` builds intra-Gemini failover chains; multi-provider cross-tier failover (Gemini Cloud → Local Ollama Shard → Mobile Edge) remains un-wired.
* **Scope:** Dynamic failover across physical host targets when API rate limits (429/503) or network disconnects occur, routing high-priority scatter tasks to local Ollama clusters without task failure.

### D. Dynamic FinOps Cost Estimator & High-Cost Execution Pre-Flight Gates
* **Source:** `Era2_architectural_roadmap.md` (§5.2)
* **Status:** `system_logs.db` logs post-execution burn; pre-call estimation gates remain unfulfilled.
* **Scope:** Pre-call token/cost estimation interceptor for multimodal/generative heavies (image-to-video, 4K context sweeps). Intercepts request before `urllib` dispatch and emits `ManualInputRequired` pause with estimated USD burn.

### E. Multi-Tier Exclusionary Grounding Transport Routing
* **Source:** `Era2_architectural_roadmap.md` (§3.1), `FeatureRequests.md` (L137)
* **Status:** Grounding toggles designed; hybrid exclusionary search transport pipeline unfulfilled.
* **Scope:** Sequenced transport execution: Google Search REST call → entity extraction → Brave Search REST call with `-site:` exclusionary flags → Local `sqlite-vec` RAG injection, preventing duplicate internet search retrieval.

### F. Nexus Copilot Sovereign REST Integration (`antigravity-preview-05-2026`)
* **Source:** `FeatureRequests.md` (L175)
* **Status:** Proposed enhancement for Copilot topology creation & repair.
* **Scope:** Exposing `gemini_client.py` and `UniversalRouter` capabilities directly to Nexus Copilot inside the local `.venv` sandbox without importing external SDKs.

---

## 3. PROPOSED ERA 3 NET & CLIENT ARCHITECTURAL GOALS

Based on the synthesis of the 12 roadmap files, computational neuroscience motifs, and sovereign edge laws, the following 5 primary goals are established for Era 3:

### Goal 1: Zero-Dependency Pure Python HTTP/2 Multiplexing & Streaming Engine
* **Objective:** Upgrade `gemini_client.py` and `live_client.py` to support HTTP/2 multiplexing and streaming WebSockets using standard library `ssl` and `socket` wrappers.
* **Impact:** Eliminates connection setup overhead for high-concurrency `CTRL_SCATTER` fan-outs (8–12 concurrent threads) while providing native token streaming to the TUI without external HTTP libraries.

### Goal 2: S25 NPU Edge Swarm Peer-to-Peer Mesh (`CTRL_EDGE_SYNC` v2)
* **Objective:** Evolve `CTRL_EDGE_SYNC` from filesystem polling to an encrypted, zero-dependency peer-to-peer TCP/mDNS socket mesh between local host instances and mobile NPU clusters.
* **Impact:** Enables ultra-low latency hybrid execution where lightweight classification and gate evaluation (`CTRL_GATE`) run directly on mobile edge hardware (S25 Ultra / local NPU), reserving cloud Gemini 3.5/3.1 calls for heavy synthesis.

### Goal 3: Hardware-Aware Real-Time Swarm Load Balancer
* **Objective:** Integrate `EnvironmentProbe` and `ModelSentinel` metrics into `OmniDaemon` to build a dynamic compute load balancer.
* **Impact:** Automatically monitors local VRAM, CPU utilization, and Ollama queue depth alongside Gemini API rate limits (RPM/TPM). Dynamically routes parallel `CTRL_SCATTER` tasks to the optimal physical target (Local Ollama vs. Cloud Gemini) based on live hardware headroom.

### Goal 4: High-Throughput Multimodal Chunking & Temporal Extrapolation Engine
* **Objective:** Build standard library multipart REST streaming for massive multimodal payloads (image, audio, video frames) supporting Era 2 Phase 5 Generative Temporal Extrapolation.
* **Impact:** Enables sovereign processing and upload of multi-megabyte visual assets with chunked streaming and FinOps pre-flight cost enforcement.

### Goal 5: Ephemeral Memory Key Enclave & Process Security Hardening
* **Objective:** Expand `ctypes.memset` RAM key zeroing into a context-managed Ephemeral Memory Key Enclave (`with SovereignKeyEnclave(key_bytes): ...`).
* **Impact:** Guarantees that sensitive API keys and authorization tokens exist in unencrypted process memory only for the exact duration of the `urllib` socket write operation, immediately zeroing bytes upon socket closure or exception throw.
