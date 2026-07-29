# MACCREv2 Phase History & Bifurcation Log

This document is the canonical chronological record of MACCREv2 architectural milestones, pivots, and bifurcation events. It supplements `ReadMe.md` (which documents *laws*) with the *narrative* of how those laws came to exist.

---

## Phase 1–8: Foundation & Early Swarm Architecture
*(Pre-documentation era — reconstructed from file timestamps and commit artifacts)*

- Established the 5-Tier Datacenter (`__DATACENTER`) as the sovereign data boundary.
- Built the first `LocalMessageBroker` (SQLite WAL Scatter-Gather State Machine) to replace fragile in-memory queues.
- Introduced the Diamond Loop (Generator temp 1.0 / Critic temp 0.1) as the core reasoning discipline.
- Established the `topology.csv` DAG routing system and `swarm_worker.py` ephemeral daemon pattern.
- ChromaDB integrated as the local vector store for RAG ingestion (`ingest_document`, `query_local_memory`).

---

## Phase 9: The MCP Era & Windows Vault
*(March 2026)*

- Integrated `mcp_server_v5.py` for Model Context Protocol tool exposure.
- Replaced all environment-variable credential patterns with `windows_vault.py` — a zero-dependency `advapi32.dll` native ctypes interface to the Windows Credential Manager.
- Established `key_vault.py` and cryptographic token management.

---

## Phase 10: Dual-Pipeline & Scatter-Gather Hardening
*(March–April 2026)*

- Implemented the `BEGIN EXCLUSIVE` Gather Gate in `local_broker.py` — eliminates TOCTOU race conditions at the SQLite C engine level.
- `AgentResponse(BaseModel)` with `response_schema` enforcement replaces all `<scratchpad>` regex parsing permanently.
- `thoughts.db` introduced as the first-class subconscious silo — RBAC-isolated from all standard agent tooling.
- `telemetry_db.py` codifies the four-silo telemetry matrix (`system_logs`, `user_interactions`, `terminal_logs`, `thoughts`).

---

## Phase 11: Sovereign Media Pipeline
*(April 2026)*

- `render_executor.py` integrates Google Cloud TTS, ElevenLabs, and FFmpeg for multi-voice podcast generation.
- `the_director.json` persona established with `MANUAL` success target to enforce HITL workflow.
- `finops_tools.py` introduces the pricing matrix and pre-flight cost estimation (`estimate_manifest_cost`).

---

## Phase 12: Global State, FinOps Reconciliation & The Ouroboros
*(April 2026)*

### Mission Control GUI Era (Archived)
- `mission_control.py` (Flet 0.82.2) built as a sovereign control plane with globally-stateful sidebar navigation, Render Bay, FinOps Ledger, and Live Swarm views.
- L1/L2 Memory Architecture implemented: `merge_session_to_project` in `rag_tools.py` enables zero-compute vector promotion from ephemeral session collections to project-level master graphs.
- Double-Entry FinOps Reconciliation Engine: `reconcile_session_finops` in `finops_tools.py` compares `FINOPS_PROJECTION` events against actual execution costs in `system_logs.db`.
- `ouroboros_monitor.py` and `gui_ouroboros_hypervisor.py` built as ambient watchdogs for deadlock detection, crash triage (Gemini 2.5 Pro structured output), and live-fix directive generation.

### The GUI Trap Recognition
During Phase 12 Chaos Engineering, the Architect recognized a systemic architectural drift: the Flet GUI had begun to own MACCRE state, with every UI feature requiring backend accommodation. Flet version locking, `page.overlay` setter restrictions, `FilePicker` plugin registration, `border.all()` API changes, and event loop isolation had become critical-path dependencies consuming engineering cycles that should have gone to the cognitive engine itself.

**The Architect's reflection (verbatim, 2026-04-05):**

> *"MACCRE is supposed to be modular, and it mostly is, but it was meant to be the backend for configurable micro-service gui states for production and writing pipelines. As we've gone, I've been subconsciously adding features that draw MACCRE itself into being a sovereign OS and lost sight of what I was doing and started building a monolithic GUI again... MACCRE stands for Multi-Agent-Conversational-Concept-Refinement-Engine. I almost forgot that while riffing the last few weeks."*

### The Decapitation Protocol (2026-04-05)
**Status:** Executed.

The Alphabet Oracle issued the Decapitation Protocol directive. Antigravity executed it.

**Actions taken:**
- All `gui_*.py` files and `mission_control.py` moved to `_archive/legacy_gui/` (7 files preserved for analysis).
- `maccre.py` created as the new canonical headless CLI entry point (`omni qa` Exit 0, Ruff + Pyright PASS).
- `ReadMe.md` updated: version header reflects Decapitation Protocol; **Law 14: Headless Sovereignty** added as permanent architectural doctrine.
- This `PHASE_HISTORY.md` created as the living historical record.

**New architecture:**

```
python maccre.py ignite <payload>   →  Injects payload into SQLite WAL
python maccre.py status             →  Reads WAL queue, prints table
python maccre.py canonize           →  L1→L2 vector memory promotion
python -m maccre_core.orchestration.swarm_worker  →  Processes queue
```

MACCRE is now what it was always meant to be: a headless engine that operates like `ffmpeg` or `git`.

---

## Bifurcation Event: The Omni Tool-Daemon (2026-04-05)
**Status:** Greenlit / Parallel Track — not active development.

During Phase 12 Chaos Engineering, the `omni` CI/CD CLI was expanded with the Ouroboros Hypervisor to include ambient process monitoring, SQLite deadlock scanning, and LLM-driven triage. In doing so, `omni` crossed from a *passive tool* to an *active system observer*.

The Architect recognized this emergent agency and greenlit `omni`'s evolution into a standalone, system-level entity: **The Omni Tool-Daemon** — a Zero-Dependency Monolith providing JIT script security auditing (AST fingerprinting, local LLM gray-area analysis) and ambient OS monitoring (ETW/eBPF kernel hooks, local TTS-vocalized threat reporting).

Development is a parallel track, explicitly decoupled from MACCREv2 active sprints.

- **Founding Doctrine:** `B:\MACCREv2\OMNI_DAEMON_FOUNDING_DOCTRINE.md`
- **Feature Request:** `B:\MACCREv2\Feature_Requests\Omni_Tool_Daemon_20260405_Phase12.md`

---

*This document is append-only. Each phase entry is a permanent record.*
*Last updated: 2026-04-06 — Phase 13 Orchestrator Paradigm.*

---

## Phase 11: Multi-Tenant Hardware Authentication (2026-04-05)
**Objective:** Evolve MACCRE into a sovereign, multi-tenant black box.
**Action:** Implemented `MACCRE_ACTIVE_PROJECT` environment variables to cleanly sandbox RAG, Render, and Telemetry DBs from polluting cross-project namespaces. Migrated from native Keyring to raw DPAPI vaulting for headless keys. Implemented a steganographic Alternate Data Stream (ADS) hardware auth check in the `TopologyEngine`, refusing to boot a pipeline that lacked the physical USB-verified clearance.

---

## Phase 12: Universal Auth & Polyglot Schema Engine (2026-04-06)
**Objective:** Untether MACCRE from Google’s API layer and enforce strict schemas natively.
**Action:** Expanded the `maccre_router.py` to seamlessly execute logic across Gemini, Anthropic (Claude), OpenAI, Groq, and Ollama (Gemma3) pipelines. Handled Pydantic schema coercion dynamically via `tool_choice` or `response_format` depending on the Vendor SDK. Added `key_ingestor.py` to fingerprint raw strings via Regex and sort them securely into DPAPI without human configuration.

---

## Phase 13: Orchestrator Paradigm & Synaptic Bridging (2026-04-06)
**Objective:** Eradicate manual file wrangling by elevating the Global Nexus Agent to the Master Orchestrator, and enabling intentional Context Osmosis.
**Action:** 
- **The Nexus Shell:** The `maccre.py chat` CLI was bound to an autonomic tool-loop, giving the Nexus agent admin-level clearance to mint agents, build topologies, and launch swarms using natural language.
- **MCP Unification:** Built `maccre_mcp.py` to expose `chat_with_nexus` to IDEs (Windsurf/Cursor), allowing Antigravity to direct the underlying Python swarm without writing custom scripts.
- **Synaptic Bridge:** Overhauled `rag_tools.py` with `query_foreign_memory` and `import_foreign_vectors`, restricted by a dynamic `project_schema.json`. Allowed surgical extraction of context from foreign RAG databases while strictly stopping accidental context bleeding.

---

## Phase 14: Security Hardening — Conditional Release & Trash Protocol
*(April 2026)*

**Objective:** Implement a PIN-based elevation layer and a mandatory soft-delete protocol before any destructive file operation.

**Actions taken:**
- ccess_control.py — equest_elevation() tool added. A session PIN is established at Nexus TUI startup; sensitive operations require the PIN to be presented in the same session. PIN lives in memory only — never written to disk.
- 	rash_file() — all file deletions now route to __DATACENTER/__TRASH_BIN/<TIMESTAMP>_<filename>. Permanent deletion requires a second explicit confirmation. The "scorched earth" pattern is gated.
- ToolExecutor microservice created — centralises tool-call parsing, replaces fragmented per-module dispatch logic.
- Legacy GUI modules (mission_control.py, orge_smith.py, 
exus_agent.py) moved to _archive/legacy_gui/ with full metadata preservation.
- OperationsLogger dual-channel telemetry: uild_pipeline.log for OmniBuilder events,  3_Agent_Ledgers/ for cognitive events.

---

## Phase 15: The Diamond Loop Engine — Autonomous Swarm Design
*(April 2026)*

**Objective:** Enable Nexus to design, configure, and materialise complete swarm pipelines from a single natural-language conversation.

**Actions taken:**
- design_tools.py — design_swarm() tool implemented with the full Diamond Loop architecture:
  - Leg 1: gemini-2.5-pro at temp=1.0 for creative swarm ideation (6,000 char feed cap)
  - Leg 2: gemini-2.5-pro at temp=0.1 with esponse_schema=SwarmDesign for verified extraction (8,192 output token headroom)
  - JSON repair loop: gemini-2.5-flash recovers from truncated responses before propagating a DESIGN_FAULT
- SwarmDesign, AgentDesign, NodeDesign Pydantic schemas established as the internal swarm specification types
- _materialise_swarm() — atomically writes workspace, agent ROM cartridges, persona cards, and topology CSV from a verified SwarmDesign
- Epoch-based unique suffix (_ts_suffix) added to project names to prevent collision
- design_swarm registered in TOOL_DISPATCHER and Nexus tool palette
- Nexus routing instruction: *"Call design_swarm IMMEDIATELY upon receiving a swarm description. Do NOT ask clarifying questions yourself."*

---

## Phase 16: Nexus TUI Hardening — Tool Loop & Short-Circuit
*(April 2026)*

**Objective:** Eliminate spin-loops on empty model responses and make tool output the terminal result that the user sees — not a prompt for further LLM generation.

**Actions taken:**
- 
exus_tui.py — Terminal-result short-circuit: [SWARM_READY], [ADMIN_SUCCESS], [SWARM_COMPLETE], and [SHEET_READY] prefixes are rendered directly to the TUI without a follow-up LLM call.
- Boolean nudge flag replaced with _empty_count integer: empty #1 → specific tool hint; empty #2 → final warning; empty #3 → fallback prose. No infinite spin.
- Tool loop iteration cap increased from 5 to 8 to accommodate multi-node swarm execution chains.
- Intent-based routing keywords mapped to specific tool hints in the nudge system.
- MACCRE_ACTIVE_PROJECT environment variable scopes all tool calls to the active project silo.

---

## Phase 17: Spreadsheet Sovereignty — Drive Inbox & Sheet Parser
*(April 2026)*

**Objective:** Replace terminal-only swarm configuration with a portable, human-readable, machine-parseable Excel workbook as the universal project specification format.

**Why the shift:** Terminal-based swarm configuration required the user to be present at the MACCREv2 terminal to define and launch swarms. The spreadsheet model enables async configuration (design on phone, execute on PC), collaboration (share the xlsx), portability (the file IS the project spec), and human readability (non-technical contributors can understand and modify agent configurations without learning CLI syntax).

**The GUI that was archived vs. the intake surface that was built:**
The Flet GUI (Phases 9–12) was a windowed application that owned MACCRE state. Its archival was correct — it was becoming a monolith. The spreadsheet is not a GUI. It is a configuration document with a defined schema. The watcher daemon is a headless listener. There is no display server dependency. The Nexus TUI remains the primary interactive interface; the spreadsheet is the async intake channel.

**Actions taken:**
- scripts/generate_template.py — generates MACCRE_Swarm_Request.xlsx with 7 sheets:
  - **SWARM_REQUEST** — project metadata, payload, compute defaults
  - **AGENTS** — full AI Studio parameter parity per agent (16 columns including TEMPERATURE, TOP_P, TOP_K, MAX_OUTPUT_TOKENS, THINKING_BUDGET, SEARCH_GROUNDING, BRAVE_SEARCH, URL_CONTEXT, SAFETY_LEVEL)
  - **TOPOLOGY** — node DAG with per-node compute and model overrides
  - **PIPELINE_CONFIG** — FFmpeg, TTS, and Imagen render settings
  - **MEMORY_CONFIG** — ChromaDB collection, embedding, and retrieval settings
  - **VAULT_KEYS** — Windows Credential Manager references (no plaintext secrets)
  - **INSTRUCTIONS** — human-readable usage guide (never parsed)
- maccre_core/tools/sheet_parser.py — parse_workbook() and materialise_from_sheet(). Parser anchors on column names, not positions — column reordering is safe. Extended AI Studio params stored in gent_extras.json in  2_Dynamic_Context for future router enhancement.
- maccre_core/drive_watcher.py — watchdog daemon with polling fallback. Detects new .xlsx files in the configured inbox, parses → materialises → ignites → runs → notifies.
- design_tools.py — ill_swarm_sheet() appended: Diamond Loop output written to a pre-formatted xlsx, materialized in the project silo simultaneously.
- maccre.py — watch subcommand added.
- 	ool_registry.py, 
exus_tui.py — ill_swarm_sheet registered and routed.
- Dependencies added: openpyxl>=3.1.5, watchdog>=4.0.0, win10toast>=0.9, setuptools>=70.0.

---

## Phase 18 (Active): Cross-Device Sovereignty — Database Nugget Protocol
*(April 2026)*

**Objective:** Enable any MACCRE device to pick up any project where any other device left it, with complete semantic memory and thought audit trail.

**Status:** Implementation pending. Architecture designed. See ROADMAP.md Phase 19 for full specification.

**Design decisions locked:**
- Nuggets pushed to G:\My Drive\__DataCenter\<PROJECT>\_nuggets\ after each swarm completion
- ChromaDB export: JSON vector snapshots keyed by device hostname
- SQLite export: WAL checkpoint + gzip for 	houghts.db and swarm_queue.db
- Import: import_foreign_vectors + ledger replay via existing tooling
- Swarm execution is permanently device-bound — nuggets are read-only reference data for foreign devices
- python maccre.py sync --project <NAME> is the manual pull command


---

## Phase 19: Project Root Anchoring — Portability Mandate
*(April 2026)*

**Objective:** Eradicate all hardcoded absolute filesystem paths (`B:/MACCREv2/...`) from the source codebase and replace them with runtime-computed, drive-letter-agnostic anchors.

**Trigger:** During MCP server integration work, it was identified that ~15 source files contained hardcoded `B:/MACCREv2` path literals as module-level constants or default parameter values. These would silently break on any machine where the project is cloned to a different drive, directory, or operating system.

**The Doctrine:** All filesystem paths in MACCREv2 MUST be derived at runtime from a single canonical anchor: `get_maccre_root()` in `maccre_core/utils/path_resolver.py`. This function implements a two-tier priority cascade:
1. `MACCRE_ROOT` environment variable (highest priority — injected by `mcp_config.json` and `setup_mcp.py`)
2. `Path(__file__).resolve().parent` traversal (fallback — always correct for in-repo execution)

**The Pattern:** Default parameter values that reference filesystem paths use the empty-string + `or` idiom to avoid hardcoded values in function signatures while remaining pyright-compliant:
```python
def __init__(self, path: str = "") -> None:
    self.path = path or str(get_maccre_root() / "subdir")
```

**Files remediated (8):**
- `maccre_core/orchestration/google_auth.py` — `token.json`, `credentials.json`
- `maccre_core/orchestration/datacenter_router.py` — `__DATACENTER` default
- `maccre_core/orchestration/memory_engine.py` — `06_Memory_Pins` default
- `maccre_core/orchestration/session_registry.py` — `__GLOBAL_LEDGER` constant
- `maccre_core/_net/model_sentinel.py` — `model_capability_map.json` default
- `maccre_core/tools/venv_executor.py` — `_REPO_ROOT` literal
- `maccre_core/tools/factory_reset.py` — `_REPO_ROOT` literal
- `maccre_core/tools/bootstrap_personas.py` — `_DC_CONTEXT` literal

**New artifacts:**
- `setup_mcp.py` — portable one-time setup script; auto-detects project root, venv Python, and Antigravity config dir; generates correct `mcp_config.json` for any machine without manual path editing.

**Law added:** Law VIII — Project Root Anchoring has been appended to `GEMINI.md` as a permanent architectural constraint for all future AI engineering work on this codebase.

---

*This document is append-only. Each phase entry is a permanent record.*
*Last updated: 2026-04-25 — Phase 19 Project Root Anchoring.*
