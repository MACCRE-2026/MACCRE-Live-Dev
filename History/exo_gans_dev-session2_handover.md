# MACCREv2 Handover Report
### From: Primary Engineering Agent (be8f8ee8)
### To: Next Conversation Agent
**Generated:** 2026-06-07T20:33:50Z
**Project Root:** `B:\EXO_GANS`
**Git HEAD:** `da7935f`

---

## 1. WHAT THIS PROJECT IS

**EXO_GANS** is the MACCREv2 sovereign AI orchestration engine. It is a Python-native, SQLite-backed swarm pipeline that routes agentic tasks through a topology of nodes defined in XLSX workbooks. The core loop is:

```
Workbook (XLSX) → sheet_parser → topology.csv + agent_roster.csv
                                        ↓
                              LocalMessageBroker (SQLite WAL)
                                        ↓
                              SwarmWorker (agentic tool loop)
                                        ↓
                              04_Code_Artifacts/{job_id}/*.md
```

Key files:
- `maccre.py` — CLI entry point (`launch`, `global`, `run`, `status`, `audit`, etc.)
- `maccre_core/orchestration/swarm_worker.py` — The universal execution node
- `maccre_core/orchestration/local_broker.py` — SQLite WAL task queue
- `maccre_core/orchestration/topology_engine.py` — Pre-flight validator + DFS
- `maccre_core/orchestration/dialogue_runner.py` — Multi-turn debate engine
- `maccre_core/tools/sheet_parser.py` — XLSX → CSV materialiser
- `maccre_tui/nexus_plex.py` — Textual TUI topology builder
- `scripts/build_topology_tests.py` — T1-T7 test suite builder
- `scripts/build_exo_test_workbook.py` — EXO_TEST workbook builder

---

## 2. EVERYTHING DONE (CHRONOLOGICAL)

### Session 1 (this morning) — EXO_TEST Failures → Phase 1-4

#### Phase 1: Four Root-Cause Bug Fixes

**Bug 1 — DialogueRunner never fired**
- `maccre_core/tools/sheet_parser.py` — `dialogue_partner` and `dialogue_rounds`
  were parsed from XLSX but never written to `topology.csv`. Fields were missing
  from `NodeDesign` dataclass, `_parse_swarm_design()`, `_materialise_swarm()`,
  and the column mapping.
- **Fix:** Added both fields to the full pipeline: dataclass → parser → CSV writer.

**Bug 2 — Google Search grounding 400 error on dialogue nodes**
- `maccre_core/orchestration/swarm_worker.py` — `|google_search` was
  unconditionally appended to all node tool strings, including dialogue nodes.
  Gemini rejects search grounding on multi-turn sessions.
- **Fix:** Guard: skip injection when `dialogue_rounds > 0`.

**Bug 3 — `{SESSION_ID}` token never resolved**
- `maccre_core/orchestration/swarm_worker.py` — The `{SESSION_ID}` placeholder
  in `artifact_path`, `system_prompt`, and `payload` was passed literally to
  the filesystem instead of being replaced with `job_id` at runtime.
- **Fix:** `.replace("{SESSION_ID}", job_id)` at the point each field is loaded.

**Bug 4 — GRETCHEN_SYNTH escape hatch**
- `scripts/build_exo_test_workbook.py` — The synthesis instruction mentioned
  `read_file`, giving the model a lazy path instead of synthesising from 8
  injected artifacts.
- **Fix:** Rewrote instruction to mandate `write_file`, removed `read_file` from
  tools list, removed reference from instruction text.

**Artifact path mismatches (Phase 2b):**
- `draft_shepherd.md` vs `shepherd_draft.md` — fixed
- `gretchen_editorial_1.md` vs `gretchen_ed1.md` — fixed

**EXO_TEST verified result:** `job_3fa2961e` — 23/23 nodes, 8/8 artifacts
injected into fan-in, DialogueRunner 7 turns, zero WARNINGs, **$0.234**.

---

#### Phase 3: Pre-Flight Validation Hardening

**File:** `maccre_core/orchestration/topology_engine.py`

Five new pre-flight checks added to `validate()`:

| Check | What it catches |
|---|---|
| **5** | `wait_for` targets that don't exist in the topology |
| **5b** | `wait_for` lists with > 5 entries (context overflow risk) |
| **6** | Circular `wait_for` deadlock detection via DFS |
| **7** | `dialogue_partner` not in `agent_roster.csv` when `dialogue_rounds > 0` |

All checks use `{node, field, severity, detail}` dict structure — consistent
with existing checks, renders identically in the pre-flight table output.

---

#### Phase 4: Conditional Routing (`ROUTE_TO:`)

**File:** `maccre_core/orchestration/swarm_worker.py`

After `final_output_text` is set, a regex scanner runs:
```python
_ROUTE_TO_PATTERN = re.compile(r"ROUTE_TO:([A-Z][A-Z0-9_]*)", re.IGNORECASE)
```

If the target exists in the topology and is not a terminal sentinel
(`STOP`, `DONE`, `TERMINATE`, `FAILED`), `next_node` is overridden.
Bounded by the current node's `max_recursion`. Unknown targets silently ignored.

---

#### T1–T7 Topology Test Suite

**File:** `scripts/build_topology_tests.py`

| Test | Topology | What it proves | Result |
|---|---|---|---|
| **T1** | SOLO → STOP | Single node smoke test | ✅ PASS |
| **T2** | A → B(broken) → C | FAILURE_TARGET routing | ✅ PASS |
| **T3** | ROOT → [A,B] → MERGE | Fan-out / fan-in | ✅ PASS |
| **T4** | ROOT → [FAST, SLOW] → MERGE | Race condition / no premature fire | ✅ PASS |
| **T5** | INIT → REFINER → JUDGE | Bounded recursive loop via ROUTE_TO | ✅ PASS |
| **T6** | VALID + ORPHAN(broken) | Pre-flight aborts at $0.00 | ✅ PASS |
| **T7** | BRIEFER → DEBATER(dialogue) → VERDICT | DialogueRunner mid-chain | ✅ PASS |

---

#### Nexus_Plex TUI v1

**Files:** `maccre_tui/nexus_plex.py`, `maccre_tui/nexus_plex.css`

A 4-tab Textual TUI application for building and launching topologies without
writing code. Dark GitHub palette (`#0d1117` bg, `#58a6ff` accent).

| Tab | Key | Features |
|---|---|---|
| 📂 Projects (F1) | F1 | Browse/create project silos, auto-scaffold 6-dir structure |
| 🕸 Topology (F2) | F2 | Add/Edit/Delete nodes via modal, Save CSV |
| 🤖 Agents (F3) | F3 | Read-only agent_roster.csv viewer |
| 🚀 Launch (F4) | F4 | Subprocess launch, live log streaming, colour-coded output |

**Launch:** `.venv\Scripts\python.exe -m maccre_tui.nexus_plex`

---

### Session 2 (this afternoon) — job_id / session_id Alignment

#### Problem Identified

Three different ID formats and concepts were mixed:
1. `ignite_swarm()`: `job_{8-hex}` — opaque, unaudited
2. `global_command()`: creates `session_id = YYYYMMDD-HHMMSS-{4rand}` then
   wraps it as `_job_id = f"job_{session_id}"` — double-variable bridge
3. `swarm_worker.py`: `session_id = task.get("session_id", job_id)` — shadow
   variable that always fell back to `job_id` since queue has no `session_id` column

`{SESSION_ID}` workbook token resolved to `job_id` (correct) but the name
was misleading since it's the opaque `job_{8-hex}` format.

#### Changes Made

**`maccre.py` — `ignite_swarm()`**
- `job_id` now uses `generate_session_id()` format:
  `job_20260607-161715-a3k9` instead of `job_3fa2961e`
- Every launch now calls `register_project()` + `register_session()` so
  ALL paths (not just `global`) appear in `project_registry.db`
- Removed now-unused top-level `import uuid`

**`maccre.py` — `global_command()`**
- Bridge comment clarified; both paths now use same generator format

**`maccre.py` — job_resume paths (×2)**
- Same `generate_session_id('resume')` format applied

**`maccre_core/orchestration/swarm_worker.py`**
- Removed `session_id` shadow variable (was always `== job_id` via fallback)
- `setup_session_loggers()` now receives `job_id` directly

**`maccre_core/tools/admin_tools.py`**
- MCP-driven launches (`run_swarm` admin tool) now use `generate_session_id()`

**`maccre_core/maccre_router.py`**
- Hoisted `_resolved_schema: dict[str, Any] | None = None` to function scope
  (fixes Pyright `reportUnboundVariable` on edge routing path)
- Removed dead `tier` variable (F841)

**`ruff.toml`**
- Added `user_scripts/` to exclude list — third-party ingestion utilities,
  not EXO_GANS source. We should never lint or modify these.

**Smoke test result:** `job_20260607-202555-6ivg` — T1 PASS, new format visible
in ledger path, telemetry, and audit log.

---

#### QA State After All Changes

| Gate | Result |
|---|---|
| **Ruff** | ✅ 0 errors, 0 warnings |
| **Pyright** | 9 pre-existing stub errors: `zmq` (×6), `chromadb` (×3), `openpyxl` (×1 warning). These are environmental — packages installed in venv but no type stubs. Not regressions. |
| **Smoke test T1** | ✅ PASS |

---

## 3. GIT HISTORY (ALL COMMITS)

```
da7935f  refactor: unify job_id to timestamped format + universal audit registration
bf3a7c2  feat(routing): Phase 4 — conditional routing via ROUTE_TO:<NODE_ID>
efe4a48  feat(preflight): Phase 3 — 5 new pre-flight validation checks
[T7+TUI] feat: T7 PASS + Nexus_Plex TUI v1
4759601  feat: MACCREv2 EXO_TEST full pipeline — DialogueRunner + conditional routing groundwork
```

---

## 4. KNOWN OPEN ITEMS (NOT STARTED)

| Item | Priority | Notes |
|---|---|---|
| **DialogueRunner `artifact_path`** | Medium | When `artifact_path` is set on a dialogue node, DialogueRunner should write the full transcript to that file. Currently falls back to ledger, causing WARNING in T7. |
| **Nexus_Plex v2** | Next | Agent roster editor (add/edit/save), topology pre-flight button, session cost estimator, XLSX export |
| **Sovereign Time-Travel Wishlist** | Future | 7-item roadmap: checkpoint-on-failure, database forking, iterative re-runs from any checkpoint |
| **T7 pre-flight coverage** | Low | Add a T6-style test that specifically triggers pre-flight Check 7 (bad dialogue_partner) |
| **HybridSearch** | Deferred | Brave + Google two-phase search topology — deferred, not blocking |

---

## 5. INSTRUCTIONS FOR NEXT AGENT

### Step 0 — Orient yourself

```powershell
cd B:\EXO_GANS
git log --oneline -8
git status
```

Expected: clean working tree, HEAD at `da7935f`.

### Step 1 — Reset to a clean slate

```powershell
# Wipe all per-run data from previous test runs
.venv\Scripts\python.exe maccre.py clean
# Verify queue is empty
.venv\Scripts\python.exe maccre.py status
```

### Step 2 — Run full QA gate

```powershell
omni qa .
```

**Expected output:**
- Ruff: `All checks passed!` (0 errors)
- Pyright: exactly 9 pre-existing stub errors for `zmq`, `chromadb`, `openpyxl`
- No new errors introduced

If you see any NEW ruff or pyright errors not in those 9, stop and investigate
before running any tests.

### Step 3 — Run the EXO_TEST (verification of all fixes)

```powershell
# Build a fresh EXO_TEST workbook from scratch
.venv\Scripts\python.exe scripts\build_exo_test_workbook.py

# Optionally reset the project silo cleanly
.venv\Scripts\python.exe scripts\_reset_exo_test.py

# Launch EXO_TEST
.venv\Scripts\python.exe maccre.py launch EXO_TEST --yes
```

**What to verify in the output:**
1. `[IGNITION] Job job_YYYYMMDD-HHMMSS-xxxx queued` — new timestamped format ✓
2. Pre-flight: `✓ All topology nodes passed pre-flight` ✓
3. `[SWARM_READY]` with all agents and nodes listed ✓
4. DialogueRunner fires: look for `[DialogueRunner] Starting` in the log ✓
5. Fan-in: `Fan-in: injected 8 gathered artifact(s) into payload` ✓
6. Zero `WARNING: artifact not found` lines ✓
7. GRETCHEN_SYNTH writes `final_synthesis.md` via `write_file` tool ✓
8. `[SWARM_COMPLETE]` with cost ~$0.20-$0.25 ✓

**If EXO_TEST fails:** Check the ledger at
`__DATACENTER/EXO_TEST/03_Agent_Ledgers/job_XXXXXXXX/` for the specific
node that broke. Cross-reference with the 4 bug fixes in Section 2 above.

### Step 4 — Audit topology for persistent problems

After EXO_TEST completes, run the audit command:

```powershell
.venv\Scripts\python.exe maccre.py audit EXO_TEST
```

Look for:
- Any node with `lock_status = 'failed'`
- Cost anomalies (any single node > $0.05 is worth investigating)
- Missing artifact files in `04_Code_Artifacts/{job_id}/`

Also check the Op-log for the session:
```powershell
Get-Content "__DATACENTER\EXO_TEST\Op-logs\*.log" | Select-String "WARNING|ERROR|FAULT"
```

### Step 5 — Verify T1-T7 suite still passes

```powershell
# Build all topology tests fresh
.venv\Scripts\python.exe scripts\build_topology_tests.py

# Run T1 (smoke, cheap, fast)
.venv\Scripts\python.exe maccre.py launch T1_SMOKE --yes

# Run T6 (pre-flight, costs $0.00)
.venv\Scripts\python.exe maccre.py launch T6_PREFLIGHT --yes
```

For T2-T5, T7 — run them if time permits or if EXO_TEST raised concerns.

### Step 6 — Verify new job_id format in audit trail

```powershell
.venv\Scripts\python.exe -c "
from maccre_core.utils.session_manager import get_project_sessions
import json
rows = get_project_sessions('EXO_TEST')
for r in rows[:3]:
    print(r['session_id'], r['status'], r['actual_cost_usd'])
"
```

Expected: `session_id` values like `job_20260607-HHMMSS-xxxx` (timestamped,
readable). If you see `job_3fa2961e` (old 8-hex format), the alignment
didn't take for that run — investigate which launch path was used.

---

## 6. WHAT COMES NEXT — NEXUS DEVELOPMENT

After verification passes, the user and next agent will begin extending
**Nexus_Plex** (the TUI topology builder). Current state: v1, 4 tabs,
read-only agent view.

### Priority v2 features (discuss with user before starting):

**A — Agent Roster Editor**
- Add/Edit/Delete rows in `agent_roster.csv` from within the TUI
- Same modal pattern as NodeEditorModal in the Topology tab
- Validate model name against `model_registry` before saving

**B — Pre-flight Button**
- Wire the `topology_engine.validate()` call to a button in the Topology tab
- Display results in a scrollable log panel (green ✓ / red ✗)
- Should work without launching — just validate the CSV on disk

**C — Session Cost Estimator**
- In the Launch tab, show estimated cost before launching
- Read from the workbook `est_cost_usd` field in `project_registry.db`
- Display as a warning if > $1.00

**D — XLSX Export**
- "Export to Workbook" button in Topology tab
- Writes the current node table + agent roster back to `MACCRE_Swarm_Request.xlsx`
- Uses `openpyxl` — pattern already exists in `sheet_parser.py`

### Files to read before starting Nexus v2:
- `maccre_tui/nexus_plex.py` — full current TUI source
- `maccre_tui/nexus_plex.css` — CSS tokens and layout
- `maccre_core/orchestration/topology_engine.py` — pre-flight validation API
- `maccre_core/utils/session_manager.py` — project/session registry API

---

## 7. ENVIRONMENT NOTES

| Item | Value |
|---|---|
| Python | 3.11+ (venv at `.venv\`) |
| Activate | `omni` auto-activates, or `.venv\Scripts\activate` |
| Primary model | `gemini-2.5-flash` (most nodes), `gemini-2.5-pro` (critic nodes) |
| Local model | `gemma-3-4b-it` (pre-flight smoke test only) |
| API key | Windows Vault via `maccre_core/orchestration/windows_vault.py` |
| Active project env | `MACCRE_ACTIVE_PROJECT` (set by `launch` command) |
| DB path | `__DATACENTER/{project}/swarm_queue.db` |
| Audit DB | `project_registry.db` at MACCRE root |

### omni commands:
```powershell
omni qa .          # Ruff + Pyright on entire project
omni qa <file>     # Targeted QA
omni build .       # Purge + QA + PyInstaller (only for distribution)
omni clean         # Kill zombies, purge pycache
omni run           # Execute local entry point
```

---

## 8. QUICK REFERENCE — KEY INVARIANTS

Things that MUST remain true after any future change:

1. **`job_id` format is always `job_{YYYYMMDD-HHMMSS-{4rand}}`** — never raw
   uuid hex. Generated by `generate_session_id()` in `session_manager.py`.

2. **`{SESSION_ID}` token in workbooks resolves to `job_id`** — it's a
   workbook-author-facing alias. Do not rename or remove the replacement logic
   in `swarm_worker.py`.

3. **`user_scripts/` is excluded from ruff** — these are third-party ingestion
   utilities. Never lint or modify them.

4. **All 4 datacenter tiers are job-scoped:**
   - Ledgers: `03_Agent_Ledgers/{job_id}/`
   - Artifacts: `04_Code_Artifacts/{job_id}/`

5. **Pre-flight runs before any API call** — the `validate()` method in
   `topology_engine.py` must be called before `broker.inject_task()`.

6. **`session_id` shadow variable is gone** — `swarm_worker.py` passes
   `job_id` directly to `setup_session_loggers()`. Do not re-introduce it.

7. **Dialogue nodes never get `|google_search`** — the guard in `swarm_worker.py`
   skips grounding injection when `dialogue_rounds > 0`.
