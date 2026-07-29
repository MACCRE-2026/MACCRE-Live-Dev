# GRANULAR FUNCTIONAL LEDGER REPORT: MACCRE_CORE /_NET/ SUBSYSTEM

**Target Path:** `b:\EXO_GANS\maccre_core\_net\`
**Target Destination:** `B:\EXO_GANS\Analysis\Wave1\01_net_subsystem_ledger.md`
**Architectural Scope:** Sovereign Edge Network, REST Client, Model Management, Hardware Probing, and Native OOXML Engine.

---

## EXECUTIVE SUMMARY & ARCHITECTURAL OVERVIEW

The `maccre_core._net` subsystem constitutes the zero-dependency networking, inference routing, hardware probing, and document generation core of the MACCREv2 sovereign edge architecture. Operating under **Law VI (Abstraction)** and **Law VIII (Data Sovereignty)**, it replaces high-overhead third-party libraries (e.g., `google-genai` SDK, `requests`, `httpx`, `openpyxl`, `pydantic`) with pure Python standard library implementations (`urllib.request`, `urllib.error`, `json`, `ssl`, `zipfile`, `xml.etree.ElementTree`).

### Key Subsystem Components:
1. **`client_interface.py`**: Strangler Fig abstract base classes (`InferenceClient`, `InferenceResponse`, `EmbeddingResult`) defining contract interfaces for LLM inference providers.
2. **`environment_probe.py`**: Active hardware and service probing engine (checks Ollama service health on `localhost:11434` and CPU logical cores).
3. **`live_client.py`**: WebSocket wrapper for Gemini Live API (`bidiGenerateContent`) with modality locking (Text-only for Android/Termux compatibility) and key zeroing.
4. **`omnidaemon.py`**: Multi-tier inference orchestrator that converts dataclass schemas to JSON Schema and dynamically routes calls across `local`, `edge`, `hybrid`, and `cloud` compute tiers.
5. **`model_sentinel.py`**: Thread-safe active health monitor daemon running background probes (`GET /v1beta/models`), maintaining a sliding window of call telemetry, and detecting model additions/deletions.
6. **`model_registry.py`**: Capability-keyed model catalogue classifying 55+ models into 13 distinct capability surfaces (`ModelSurface`), building intra-surface failover chains and wiring with `ModelSentinel`.
7. **`ooxml.py`**: Sovereign OOXML workbook writer reproducing `openpyxl`'s API surface for `.xlsx` creation using `zipfile` and `xml.etree.ElementTree`.
8. **`gemini_client.py`**: Full REST API implementation for Google Generative Language endpoints (`generateContent`, `streamGenerateContent`, `embedContent`, `batchEmbedContents`, File API, Context Caching, Model Listing).

---

## DETAILED FILE-BY-FILE ANALYSIS

### 1. `client_interface.py` (5.4 KB, 136 Lines)
Abstract interface contracts enforcing Law VI.

### 2. `environment_probe.py` (2.8 KB, 51 Lines)
Probes local host hardware and active services.

### 3. `live_client.py` (1.9 KB, 45 Lines)
Manages stateful, bi-directional WebSocket connections to Gemini Live API.

### 4. `omnidaemon.py` (10.0 KB, 207 Lines)
Central inference routing daemon that bypasses third-party libraries.

### 5. `model_sentinel.py` (19.5 KB, 440 Lines)
Background thread daemon performing active health monitoring and capacity probing.

### 6. `model_registry.py` (24.3 KB, 526 Lines)
Multi-surface capability-keyed model catalogue.

### 7. `ooxml.py` (29.6 KB, 651 Lines)
Zero-dependency sovereign OOXML Workbook Writer.

### 8. `gemini_client.py` (34.0 KB, 807 Lines)
Primary sovereign HTTP client for Google Generative Language REST API endpoints.
