# Wave 3 Documentation Additions: State, Security & Sovereignty

---

## PART 1: DRAFT SECTION FOR `B:\EXO_GANS\README.md`

### State, Security & Sovereignty Architecture

#### 1. Sovereign Edge Omni-Builder Doctrine & Physical Laws
- **Law I: Sovereign Prefix Mandate (`omni`)**: All execution, linting, testing, and compilation MUST be routed through `omni` (`omni run`, `omni qa`, `omni build`, `omni clean`).
- **Law II: Strict Datacenter Silo Routing**: File I/O partitioned across 5 datacenter silos (`01_Raw_Source` through `05_Rendered_Media`). Destructive deletions replaced by `trash_file()`.
- **Law III: Zero-Leak RAM Key Purging**: API keys purged post-execution via CPython memory zeroing (`ctypes.memset`).
- **Law IV: Canonical Path Anchoring (`get_maccre_root`)**: Dynamic runtime path resolution via `get_maccre_root()` in `maccre_core/utils/path_resolver.py`.

#### 2. The 5-Tier Datacenter Silo Topology
Workspace isolated inside `__DATACENTER/<projectName>/`:
- `01_Raw_Source` — Ingestion documents
- `02_Dynamic_Context` — Active states, topologies, encrypted vault (`auth_vault.bin`)
- `03_Agent_Ledgers` — JSON cognitive ledgers & build logs
- `04_Code_Artifacts` — Python code, markdown reports, schemas
- `05_Rendered_Media` — TTS audio, Imagen graphics, FFmpeg video

#### 3. Omni CI/CD Gatekeeper Pipeline
- `omni run <path>` — Clears zombie processes, executes script cleanly.
- `omni qa [path]` — Native Ruff linting and Pyright type checking.
- `omni build [path]` — Purges caches, runs QA, compiles via PyInstaller.
- `omni clean [path]` — Eradicates build caches, SQLite WAL/SHM artifacts, and zombie threads.

---

## PART 2: DRAFT SECTION FOR `B:\EXO_GANS\MACCRE_Operator_Manual.md`

### State, Security & Sovereignty Operations

#### 1. Step-by-Step 3-Tier Access Control & PIN Elevation
- **Tier 1**: Baseline read-only access.
- **Tier 2**: Salted SHA-256 PIN elevation for out-of-sandbox write operations.
- **Tier 3**: Headless MCP token bypass (`activate_mcp_bypass`).

#### 2. Archive Trash Protocol (`trash_file()`)
Moves deleted files to `_archive/trash/` with a `%Y%m%dT%H%M%SZ__` timestamp prefix and logs `FILE_TRASHED` events in `system_logs.db`.

#### 3. 4-Silo SQLite WAL Telemetry Matrix
- `system_logs.db` — Lifecycle events, execution states, exceptions, hardware metrics.
- `user_interactions.db` — Operator prompts, PIN auth logs, button clicks.
- `terminal_logs.db` — Stdio capture, console exhaust streams.
- `definitions.db` — Schema definitions, topological node configs, macro-node registries.

#### 4. Federated Vault & RAM Key Purging
Dual-vault hierarchy (`windows_vault.py` Windows DPAPI + `universal_vault.py` AES-128 Fernet). `key_ingestor.py` fingerprinting and Win32 clipboard clearing (`clear_windows_clipboard()`). Plaintext RAM zeroing via `ctypes.memset`.
