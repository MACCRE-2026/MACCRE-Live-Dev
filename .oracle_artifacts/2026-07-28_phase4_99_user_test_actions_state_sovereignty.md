# Phase 4.99 High-Stress User Test Actions: State & Sovereignty Domain

**Author:** StateAndSovereignty_Oracle  
**Date:** 2026-07-28  
**Target Domain:** `local_broker.py`, `telemetry_db.py`, `path_resolver.py`, `access_control.py`, `universal_vault.py`, `windows_vault.py`, `omni` CI/CD, 5-tier datacenter silos, 4-silo SQLite WAL telemetry matrix, `flow_vector` lineage logging, `trash_file()` archive protocol.  

---

## Executive Summary

This artifact defines 8 high-stress operational test scenarios for Phase 4.99 validation of MACCREv2 / EXO_GANS. The actions enforce strict adherence to the Sovereign Physical Laws: 5-tier datacenter silos, 4-silo SQLite WAL telemetry matrix, DPAPI / Fernet key vaults with CPython RAM key zeroing (`ctypes.memset`), non-destructive archive trash protocol (`trash_file()`), `get_maccre_root()` anchoring, 3-tier access control PIN elevation, and `omni` CI/CD gatekeeping.

---

## Phase 4.99 High-Stress User Test Actions Suite

### Action 1: Concurrent SQLite WAL Lock & Scatter-Gather Queue Stress Test
- **Target Codebase Component**: `maccre_core/orchestration/local_broker.py` & `maccre_core/orchestration/telemetry_db.py`
- **Step-by-Step Operator Action**:
  1. Spawn 20 parallel worker threads pushing task items to `local_broker.py` queues while simultaneously logging events via `log_system_event()`.
  2. Execute continuous high-throughput `publish_message()` and `poll_messages()` operations across multiple worker tethers.
  3. Monitor SQLite connection pools, `PRAGMA journal_mode=WAL` settings, and write latencies.
- **Edge-Case / Stress Condition**: High-concurrency database write contention (>100 writes/sec) across parallel worker threads without triggering `sqlite3.OperationalError: database is locked` (SQLITE_BUSY).
- **Expected System Behavior & Domain Validation Criteria**:
  - `_wal_conn` context manager sets `PRAGMA journal_mode=WAL;` and `PRAGMA synchronous=NORMAL;` on every connection open.
  - Zero `SQLITE_BUSY` exceptions logged; 100% of telemetry events and queue items successfully committed to `system_logs.db` and broker tables.
  - Transaction lock holding duration stays < 15ms.

---

### Action 2: Multi-Tether Synthetic Node UNIQUE Index Collision & Lineage Delimiter Validation Test
- **Target Codebase Component**: `maccre_core/orchestration/local_broker.py` & `maccre_core/orchestration/telemetry_db.py`
- **Step-by-Step Operator Action**:
  1. Enqueue tasks from multiple concurrent subagent tethers sharing identical synthetic node IDs (e.g. `node_01` in Tether A and `node_01` in Tether B).
  2. Validate `flow_vector` lineage chain construction using the standard `>` delimiter (e.g., `root_node > synth_01 > child_node`).
  3. Query `system_logs.db` for lineage records filtered by `tether_id`.
- **Edge-Case / Stress Condition**: Synthetic node ID collision across parallel tethers where non-tethered UNIQUE database indices would trigger integrity faults.
- **Expected System Behavior & Domain Validation Criteria**:
  - Composite key constraint `(tether_id, node_id)` isolates task instances and prevents UNIQUE collision across tethers.
  - `flow_vector` string correctly formats multi-hop delegations with `>` delimiter without string truncation or formatting corruption.
  - Querying `system_logs.db` by `tether_id` yields isolated execution traces with zero cross-tether record leakage.

---

### Action 3: Strict 5-Tier Datacenter Silo Boundary & Out-of-Bounds Path Rejection Test
- **Target Codebase Component**: `maccre_core/utils/path_resolver.py` & `maccre_core/orchestration/access_control.py`
- **Step-by-Step Operator Action**:
  1. Execute `get_maccre_root()` and `get_datacenter_path()` across varying environment variable configurations (`MACCRE_ROOT` set and unset).
  2. Instruct agent tools to access all 5 datacenter silos (`01_Raw_Source` through `05_Rendered_Media`).
  3. Intentionally trigger file write attempts targeting paths outside the project root (e.g., `C:\Windows\System32\` or relative `../../etc/passwd`).
- **Edge-Case / Stress Condition**: Path traversal attacks (`../`, symlink resolution) attempting to escape project root or write outside designated silos.
- **Expected System Behavior & Domain Validation Criteria**:
  - `get_maccre_root()` dynamically anchors to root via runtime `__file__` traversal or `MACCRE_ROOT` override.
  - `is_datacenter_path()` and `requires_elevation()` flag out-of-bounds targets and enforce security elevation checks.
  - Ingestion tools strictly restrict inputs to `01_Raw_Source` and `02_Dynamic_Context`, while output tools restrict writes to `04_Code_Artifacts` and `05_Rendered_Media`.

---

### Action 4: 3-Tier Security Elevation (Read-Only, Salted PIN Elevation, and MCP Token Bypass) Test
- **Target Codebase Component**: `maccre_core/orchestration/access_control.py` & `maccre_core/orchestration/universal_vault.py`
- **Step-by-Step Operator Action**:
  1. **Tier 1 Verification**: Execute read operations on system code without elevation (assert permitted).
  2. **Tier 2 Verification**: Attempt a write to a path outside `__DATACENTER`. Confirm `request_elevation()` returns `[ELEVATION_PIN_REQUIRED]`.
  3. Enter an invalid PIN into `verify_elevation_pin()` (confirm returns `False` and `ELEVATION_RESULT: DENIED` logged in `system_logs.db`).
  4. Submit valid PIN (`maccre_salt_1234` SHA-256 hash or vault override) to confirm single-use session elevation.
  5. **Tier 3 Verification**: Set `MACCRE_ELEVATION_TOKEN` env var and invoke `activate_mcp_bypass(token)`. Verify system writes execute without PIN prompt.
- **Edge-Case / Stress Condition**: PIN brute-force attempts, session expiry, and unauthenticated MCP token submission.
- **Expected System Behavior & Domain Validation Criteria**:
  - Tier 1 permits baseline read-only introspection without restriction.
  - Tier 2 requires salted SHA-256 PIN match (`hashlib.sha256(b"maccre_salt_" + pin)`); failed attempts log `ELEVATION_RESULT: DENIED`.
  - Tier 3 MCP bypass activates only when `MACCRE_ELEVATION_TOKEN` matches, logging `MCP_BYPASS_ACTIVATED` and bypassing PIN prompts for Antigravity IDE sessions.

---

### Action 5: Non-Destructive Archive Trash Protocol (`trash_file()`) Verification Test
- **Target Codebase Component**: `maccre_core/orchestration/access_control.py`
- **Step-by-Step Operator Action**:
  1. Generate temporary test files across datacenter silos.
  2. Call `trash_file(path, reason="Phase 4.99 Deletion Safety Audit")`.
  3. Attempt direct un-sanctioned file deletion via `os.remove()` or `Path.unlink()` across agent tools to test policy enforcement.
  4. Inspect `_archive/trash/` directory and `system_logs.db`.
- **Edge-Case / Stress Condition**: Attempting to trash non-existent files, locked files, or duplicate filenames deleted within the same second.
- **Expected System Behavior & Domain Validation Criteria**:
  - Hard file deletion (`os.remove`) is forbidden; all deletions route through `trash_file()`.
  - Files are relocated to `_archive/trash/` prefixed with UTC timestamp: `YYYYMMDDTHHMMSSZ__filename`.
  - Function returns `[TRASH_SUCCESS]` and logs `FILE_TRASHED` to `system_logs.db`. Non-existent targets return `[TRASH_FAULT]` cleanly.

---

### Action 6: Federated Key Vault (DPAPI / Fernet) & RAM CPython Buffer Zeroing (`ctypes.memset`) Test
- **Target Codebase Component**: `maccre_core/orchestration/windows_vault.py` & `maccre_core/orchestration/universal_vault.py`
- **Step-by-Step Operator Action**:
  1. Store API secrets using Windows DPAPI (`protect_string()`) and retrieve via `get_provider_credential()`.
  2. Simulate non-Windows environment (or missing DPAPI) to test fallback to `FernetVaultAdapter`.
  3. Pass sensitive plaintext credential strings to `wipe_string(target)` post-invocation.
  4. Inspect string memory address via `ctypes.string_at(id(target), sys.getsizeof(target))` immediately after wiping.
- **Edge-Case / Stress Condition**: CPython string heap memory dump attack post-LLM invocation; headless Linux container deployment.
- **Expected System Behavior & Domain Validation Criteria**:
  - DPAPI saves encrypted binary blobs to `__DATACENTER/.vault/<name>.bin`.
  - Non-Windows environments fallback to AES-128 `FernetVaultAdapter` writing to `auth_vault.bin`.
  - `wipe_string()` executes `ctypes.memset(address, 0, buffer_size)`, overwriting the CPython string memory buffer with `\x00` null bytes.

---

### Action 7: 4-Silo SQLite WAL Telemetry Matrix Lineage & Teardown Audit Test
- **Target Codebase Component**: `maccre_core/orchestration/telemetry_db.py` & `maccre_core/tools/telemetry_tools.py`
- **Step-by-Step Operator Action**:
  1. Run a multi-node workflow generating telemetry across all 4 silos (`system_logs.db`, `user_interactions.db`, `terminal_logs.db`, `definitions.db`).
  2. Inspect DB schemas and verify universal header fields (`id`, `session_id`, `project_id`, `agent_id`, `source_node`, `timestamp`) and `flow_vector` lineage values.
  3. Execute `omni clean` to test WAL checkpoint flushing and lock file cleanup.
- **Edge-Case / Stress Condition**: Sudden process termination during active WAL transaction; missing database files on startup.
- **Expected System Behavior & Domain Validation Criteria**:
  - `init_all_silos()` automatically and idempotently initializes all 4 database schemas on startup.
  - Universal header columns are accurately populated across all silos.
  - `definitions.db` logs promoted topologies into `topology_library` with 8-column CSV parity.
  - `omni clean` flushes WAL journals, closes open handles, and purges `.db-wal`/`.db-shm` artifacts cleanly.

---

### Action 8: Omni CI/CD Execution Interceptor & Zero-Zombie Teardown Validation Test
- **Target Codebase Component**: `omni` CLI daemon & CI/CD pipeline
- **Step-by-Step Operator Action**:
  1. Execute system tools using the canonical prefix: `omni run <script>`, `omni qa .`, `omni build`, `omni clean`.
  2. Intentionally spawn an orphaned background process simulating a zombie task.
  3. Execute `omni clean` to trigger zombie hunting and cache purging.
- **Edge-Case / Stress Condition**: Direct un-intercepted bare Python execution attempts; active database locks during `omni clean`.
- **Expected System Behavior & Domain Validation Criteria**:
  - `omni qa` enforces absolute type hints, zero unused imports, max line length 120, and Pyright static analysis compliance.
  - `omni run` resolves active Python virtual environment and executes scripts cleanly.
  - `omni clean` eradicates `__pycache__`, SQLite WAL/SHM artifacts, and terminates orphan zombie processes without deadlocks.
