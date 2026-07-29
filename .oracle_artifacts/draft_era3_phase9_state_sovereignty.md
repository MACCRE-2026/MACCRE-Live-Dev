# ERA 3 ARCHITECTURAL ROADMAP: PHASE 9 - STATE, SECURITY & SOVEREIGNTY CONTRIBUTION
**Domain Contribution:** State & Sovereignty Specialist Oracle (`StateAndSovereignty_Oracle`)  
**Target Modules:** `maccre_core/utils/path_resolver.py`, `maccre_core/access_control.py`, `maccre_core/telemetry_db.py`, `maccre_core/key_ingestor.py`, `maccre_core/universal_vault.py`, `omni` CLI  
**Theme:** Phase 9 — In-State Live Development & Antigravity Desktop Transition Bridge  
**Compliance Standard:** Sovereign Edge Omni-Builder Doctrine & Law Rev 19.0 Physical Laws  

---

## 1. EXECUTIVE SUMMARY & SUBSYSTEM VISION

Phase 9 establishes the **In-State Live Development & Antigravity Desktop Transition Bridge** within the State, Security & Sovereignty kernel (`maccre_core`). It governs the transition of external Google Antigravity desktop sessions and imported codebases into fully sovereign, 5-tier datacenter project environments (`01_Raw_Source` through `05_Rendered_Media`).

Within the State & Sovereignty subsystem, Phase 9 delivers:
1. **5-Tier Datacenter Transmutation Engine (`fork_datacenter()`)**: Safe cloning and structural mapping of external Antigravity `conversations\` and `brain\` directories into MACCRE-compliant project silos.
2. **1:1 Structural Mapping Matrix**: Rigorous mapping between Antigravity desktop file artifacts and MACCRE 5-tier datacenter silos.
3. **Omni CI/CD Test Topology Harness (`omni test`)**: Automated testing and validation of containerized frozen state deployment candidates prior to production promotion.
4. **Security, Path Anchoring & Elevation Integrity**: Enforcement of `get_maccre_root()` path anchoring, 3-tier PIN elevation for live development writes, and CPython RAM memory zeroing (`ctypes.memset`) on credential buffers.

---

## 2. 1:1 STRUCTURAL MAPPING MATRIX (ANTIGRAVITY vs MACCRE DATACENTER)

| Antigravity Desktop Asset | Antigravity File Path | MACCRE 5-Tier Datacenter Target Path | Data Sovereignty Tier |
| :--- | :--- | :--- | :--- |
| **Session Metadata** | `conversations/conversation_<id>.json` | `02_Dynamic_Context/{project}/as_wrapped_topology.json` | `02_Dynamic_Context` |
| **Full Trajectory Log** | `brain/<id>/.system_generated/logs/transcript_full.jsonl` | `03_Agent_Ledgers/{project}/[module]_telemetry.json` & `system_logs.db` | `03_Agent_Ledgers` |
| **Compact Trajectory** | `brain/<id>/.system_generated/logs/transcript.jsonl` | `user_interactions.db` & `terminal_logs.db` | Telemetry Silo |
| **Markdown Artifacts** | `brain/<id>/*.md` | `04_Code_Artifacts/` | `04_Code_Artifacts` |
| **Media Outputs** | `brain/<id>/*.png`, `*.mp4`, `*.wav` | `05_Rendered_Media/images/`, `video/`, `audio/` | `05_Rendered_Media` |
| **Scratch Space** | `brain/<id>/scratch/` | `02_Dynamic_Context/{project}/scratch/` | `02_Dynamic_Context` |
| **Source Code Repos** | External workspace directory | `01_Raw_Source/` & `04_Code_Artifacts/` | `01_Raw_Source` / `04_Code` |

---

## 3. DATACENTER TRANSMUTATION & IN-STATE SANDBOXING (`datacenter_router.py`)

### 3.1 Datacenter Forking & Transmutation Engine (`fork_datacenter()`)
- **Automated Directory Transmutation**: Scans target `%USERPROFILE%\.gemini\antigravity\` directories (`conversations/` and `brain/`) and creates a new project root under `get_maccre_root() / "__DATACENTER" / <imported_project_name>`.
- **Non-Destructive Collision Prevention**: Existing project directories are never overwritten raw. If a name collision occurs, `access_control.trash_file()` safely relocates the legacy folder to `_archive/trash/%Y%m%dT%H%M%SZ__<name>/` before creating the transmuted project structure.

### 3.2 Automated Omni CI/CD Test Topology Harness (`omni test`)
- **Containerized Frozen State Candidate Verification**: In-state live development candidates (code refactors, prompt updates, node changes) execute inside shadowed sandboxes (`02_Dynamic_Context/sandboxes/candidate_<id>/`) created via `shutil.copy2`.
- **`omni test [path]` Command Addition**: New `omni` CLI command running `omni qa` (Ruff/Pyright), executing built-in test topologies (`CTRL_TEST_HARNESS`), and validating 100% gate compliance before committing changes to production master.

### 3.3 Access Control Elevation & Key Hygiene
- **3-Tier PIN Elevation Interceptor**: Live development tool writes (`write_file`, code edits) targeting core `maccre_core/` files require Tier 2 PIN authorization or a valid Tier 3 FastMCP bypass token.
- **Transcript Credential Sanitization**: Key regex scanner (`key_ingestor.py`) scrubs raw API keys from imported Antigravity transcripts, routing keys to Windows DPAPI / Fernet key vaults and wiping memory via `ctypes.memset`.

---

## 4. PHASE 9 ROADMAP SECTION SPECIFICATIONS

### 4.1 Master Matrix Addition for Section 5
| Subsystem Scope | Implemented Bedrock | Phase 9 Strategic Addition |
| :--- | :--- | :--- |
| **State, Security & Sovereignty** | 5-tier datacenter silos, path anchoring `get_maccre_root()`, 3-tier access control PIN elevation, archive trash protocol (`trash_file()`), DPAPI/Fernet key vaults, 4-silo SQLite WAL telemetry, `omni` CLI. | 5-tier datacenter transmutation engine (`fork_datacenter()`), 1:1 Antigravity-to-MACCRE structural mapping matrix, `omni test` CI/CD candidate test harness, transcript key sanitization & RAM zeroing. |

### 4.2 Timeline Addition for Section 6
```
| PHASE 9: IN-STATE LIVE DEVELOPMENT & ANTIGRAVITY DESKTOP TRANSITION BRIDGE          |
|   - 5-tier datacenter project transmutation engine (fork_datacenter())              |
|   - 1:1 structural mapping matrix (conversations/ & brain/ -> 5-tier silos)         |
|   - Omni CI/CD candidate test topology harness (omni test [path])                    |
|   - In-state frozen deployment candidate sandboxing (shutil.copy2 & .git worktrees)  |
|   - Tier 2 PIN elevation & RAM key zeroing (ctypes.memset) on transcript ingest      |
```
