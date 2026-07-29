# Granular Functional Ledger Report: Orchestration Architecture

**Target Modules Analyzed:** `access_control.py`, `datacenter_router.py`, `hybrid_edge_sync.py`, `key_ingestor.py`, `live_session_manager.py`, `telemetry_db.py`, `tool_executor.py`, `universal_vault.py`, `windows_vault.py`, `memory_engine.py`, `roster_loader.py`, `queues.py`, `scorekeeper.py`, `session_registry.py`, `stream_executor.py`

---

## 1. Access Control & Deletion Safety (`access_control.py`)
3-tier access control model governing file write access, PIN authentication, MCP token bypass, and timestamped trash protocol (`_archive/trash/`).

## 2. Universal & System Vault Operations (`universal_vault.py` & `windows_vault.py`)
Federated vault combining OS Vault (`keyring`), Fernet AES-128 fallback (`auth_vault.bin`), CPython RAM buffer wiping (`ctypes.memset`), and native Windows DPAPI / Credential Manager integration (`CryptProtectData`, `CredReadW`).

## 3. Autonomous Key Fingerprinting (`key_ingestor.py`)
Regex pattern recognition routing vendor API keys (Gemini, Anthropic, OpenAI, Groq, xAI, Brave) into protected DPAPI vault storage with automatic clipboard sanitization.

## 4. Telemetry Database & Event Matrix (`telemetry_db.py`)
Four-silo SQLite WAL engine maintaining `system_logs.db`, `user_interactions.db`, `terminal_logs.db`, and `definitions.db` with composite schemas and idempotent migrations.

## 5. Session Management, Queues & Physics (`live_session_manager.py`, `queues.py`, `scorekeeper.py`, `session_registry.py`)
File-based IPC queue (`JsonFileQueue`), conversational physics engine (`ScoreKeeper`), turn routing presets, and single-use UUID consumption validation.

## 6. Tool Execution, Datacenter Routing & Observer Memory (`tool_executor.py`, `datacenter_router.py`, `hybrid_edge_sync.py`, `memory_engine.py`, `roster_loader.py`, `stream_executor.py`)
Tool argument parsing and path sandboxing (`04_Code_Artifacts/<session_id>/`), 5-tier datacenter tree enforcement, LLM semantic triplet extraction into `memory_pins.db`, global agent roster loading, and streaming TTS audio dispatch.
