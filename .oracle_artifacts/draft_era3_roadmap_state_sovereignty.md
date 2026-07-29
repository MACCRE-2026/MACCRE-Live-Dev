# ERA 3 ARCHITECTURAL ROADMAP: STATE, SECURITY & SOVEREIGNTY SUBSYSTEM

**Specialist Oracle Domain:** `maccre_core/` (`path_resolver.py`, `access_control.py`, `telemetry_db.py`, `key_ingestor.py`, `universal_vault.py`, `windows_vault.py`, `logger.py`), `maccre.py`, `run.py`, `run_tui.py`, `setup_mcp.py`, `omni` CLI  
**Compliance Standard:** Sovereign Edge Omni-Builder Doctrine & Law Rev 19.0 Physical Laws  
**Date:** 2026-07-25  

---

## EXECUTIVE OVERVIEW

The State, Security & Sovereignty subsystem forms the foundational kernel of MACCREv2 / EXO_GANS. Governed by the **Sovereign Edge Omni-Builder Doctrine**, it enforces deterministic execution, zero-cloud data containment, zero-leak credential hygiene, non-destructive file operations, and continuous telemetric auditing across four physical laws:

- **Law I: Sovereign Prefix Mandate (`omni`)**: Direct execution of Python scripts via bare `python` is strictly banned. All execution, testing, linting, and compilation MUST route through the global `omni` daemon (`omni run`, `omni qa`, `omni build`, `omni clean`).
- **Law II: Strict Datacenter Silo Routing**: File I/O is strictly partitioned across 5 designated datacenter silos (`01_Raw_Source` through `05_Rendered_Media`). Destructive file deletions are outlawed; files are moved safely via `trash_file()`.
- **Law III: Zero-Leak RAM Key Purging**: API key credentials loaded from local key vaults are held in memory only for the duration of the request and immediately wiped post-call via CPython memory zeroing (`ctypes.memset`).
- **Law IV: Canonical Path Anchoring (`get_maccre_root`)**: Absolute file paths are strictly banned in source files. All relative paths derive at runtime from `get_maccre_root()` in `maccre_core/utils/path_resolver.py`.

---

## 1. IMPLEMENTED STATE, SECURITY & SOVEREIGNTY FEATURES

| Feature / Module | Implementation Detail | Architectural Significance |
|------------------|----------------------|----------------------------|
| **Dynamic Root Path Anchoring** (`path_resolver.py`) | Runtime resolution of `MACCRE_ROOT` environment variable with fallback to `Path(__file__).resolve().parent.parent.parent`. Enforces `def __init__(self, path: str = ""): self.path = path or str(get_maccre_root() / "subdir")`. | Multi-drive, multi-OS, directory-agnostic zero-configuration portability. |
| **5-Tier Datacenter Silo Topology** (`datacenter_router.py`) | Workspace isolated under `__DATACENTER/<projectName>/` into `01_Raw_Source`, `02_Dynamic_Context`, `03_Agent_Ledgers`, `04_Code_Artifacts`, `05_Rendered_Media`. | Strict data partitioning and deterministic asset management. |
| **3-Tier Access Control Elevation** (`access_control.py`) | Tier 1 (Read-Only baseline), Tier 2 (Salted SHA-256 PIN elevation for out-of-sandbox writes), Tier 3 (Headless FastMCP token bypass via `activate_mcp_bypass`). | Progressive privilege authorization preventing unprompted workspace mutation. |
| **Archive Trash Protocol** (`access_control.trash_file()`) | Moves deleted files to `_archive/trash/` prepended with ISO-8601 UTC timestamp (`%Y%m%dT%H%M%SZ__`) and logs `FILE_TRASHED` events in `system_logs.db`. | Non-destructive deletion enforcement and forensic auditability. |
| **Federated Key Vault Hierarchy** (`windows_vault.py` & `universal_vault.py`) | Dual-vault architecture: native Windows DPAPI (`CryptProtectData`/`CredReadW`) bound to OS user profile + Fernet AES-128 encrypted `auth_vault.bin` fallback. | Zero-cloud credential encryption without plain-text `.env` files. |
| **Autonomous Key Ingestion & Clipboard Sanitization** (`key_ingestor.py`) | Regex-fingerprints vendor keys (Gemini, Anthropic, OpenAI, Groq, xAI, Brave), routes to vault storage, and purges Win32 clipboard via `clear_windows_clipboard()`. | Zero-touch credential onboarding and clipboard leak prevention. |
| **CPython RAM Memory Zeroing** (`gemini_client.py`, `live_client.py`) | Overwrites plaintext API key byte buffers post-request using `ctypes.memset(id(s) + 32, 0, len(s))`. | Memory safety preventing credential extraction from process dumps. |
| **4-Silo SQLite WAL Telemetry Matrix** (`telemetry_db.py`) | Partitioned SQLite WAL databases: `system_logs.db` (lifecycle & hardware), `user_interactions.db` (HITL audit), `terminal_logs.db` (stdio capture), `definitions.db` (schemas & node configs). | High-concurrency, non-blocking telemetry logging. |
| **Omni CI/CD Gatekeeper Daemon** (`omni`) | Global CLI interceptor managing `omni run` (zombie cleanup & execution), `omni qa` (Ruff & Pyright checks), `omni build` (PyInstaller compilation), `omni clean` (cache & SQLite WAL purge). | Enforces strict code quality and execution discipline. |

---

## 2. UNFINISHED & FUTURE STATE/SECURITY ROADMAP ITEMS

### A. Zero-Trust Peer-to-Peer Encrypted Memory Sync (`sync_tools.py` v2)
* **Source:** `Era2_architectural_roadmap.md` (§6.3), `FeatureRequests.md` (L133)
* **Status:** Local `.nugget` file export/import implemented; encrypted peer-to-peer LAN/WAN sync unfulfilled.
* **Scope:** Cryptographically signed and encrypted memory snapshot sync across local nodes and mobile edge devices (e.g. S25 Ultra NPU clusters) without intermediary cloud servers.

### B. Hardware TPM 2.0 / Secure Enclave Vault Integration
* **Source:** `EXO_GANS_Wishlist_Architecture.md` (Part 4), `FeatureRequests.md` (L160)
* **Status:** Windows DPAPI and Fernet AES-128 implemented; hardware TPM 2.0 / Apple Silicon Secure Enclave integration unfulfilled.
* **Scope:** Binding Fernet master encryption keys directly to host hardware TPM 2.0 chips or Secure Enclaves, rendering stolen vault binaries un-decryptable on foreign hardware.

### C. Immutable Cryptographic Execution Lineage Auditing
* **Source:** `ctrl_scatter-expansion plan-v3.md` (Phase 7), `EXO_GANS_Wishlist_Architecture.md` (Part 1)
* **Status:** `flow_vector` string lineage logged in `swarm_queue.db`; cryptographic SHA-256 block hashing unfulfilled.
* **Scope:** Wrapping `flow_vector` lineage entries into a cryptographically chained Merkle tree log, creating tamper-evident execution proofs for multi-agent decisions.

### D. Multi-Tenant Project Datacenter Isolation & Sandboxing
* **Source:** `TUI_REFACTOR_PLAN.md` (§6.5), `FeatureRequests.md` (L183)
* **Status:** Single project active per TUI session; multi-tenant virtual sandboxing unfulfilled.
* **Scope:** Virtualized multi-tenant project isolation allowing parallel execution of isolated project swarms with strict cross-project memory access control.

---

## 3. PROPOSED ERA 3 STATE, SECURITY & SOVEREIGNTY GOALS

### Goal 1: Zero-Trust Cryptographic P2P Mesh & Node Attestation
* **Objective:** Establish an encrypted P2P mesh network using mDNS and TLS 1.3 mutual authentication for cross-device node coordination.
* **Impact:** Enables secure, air-gapped node-to-node task handoffs and memory sync across LAN and mobile edge devices without relying on third-party cloud brokers.

### Goal 2: Hardware TPM 2.0 & Ephemeral Key Enclave
* **Objective:** Bind vault encryption keys to hardware TPM 2.0 chips and encapsulate API key lifetimes inside context-managed `SovereignKeyEnclave` blocks using `ctypes.memset`.
* **Impact:** Guarantees absolute credential security: keys cannot be extracted from disk binaries or memory dumps.

### Goal 3: Tamper-Evident Merkle Execution Ledger
* **Objective:** Upgrade `system_logs.db` and `03_Agent_Ledgers` to generate SHA-256 Merkle tree root hashes for every completed session.
* **Impact:** Provides mathematical proof of agent execution paths, preventing retrospective tampering with cognitive logs or decision lineage.

### Goal 4: Automated Sovereignty Audit & Compliance Daemon (`omni audit`)
* **Objective:** Add `omni audit [path]` command to the global `omni` CLI daemon.
* **Impact:** Automatically scans codebases for SDK violations (unauthorized `google-genai` / `requests` imports), hardcoded absolute paths, un-sanitized key buffers, and un-anchored file I/O operations prior to build compilation.

### Goal 5: Multi-Tenant Workspace Sandboxing & Process Isolation
* **Objective:** Implement process-level sandboxing for project workspaces, isolating memory spaces, SQLite handles, and subprocess runners per project tenant.
* **Impact:** Prevents cross-project memory contamination and guarantees clean resource teardown upon session completion.
