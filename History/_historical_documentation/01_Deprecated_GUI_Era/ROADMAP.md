# MACCREv2 — Future Roadmap
**Maintained from Phase 19 | April 2026**

This document is the forward-looking engineering roadmap. It is not a wish list — every item has been assessed for technical feasibility and sequenced by dependency. The Strangler Fig principle applies: each phase delivers working software before the next begins.

For completed phase history, see `PHASE_HISTORY.md`.
For current architecture laws, see `ReadMe.md`.

---

## Phase 19 (Active): Cross-Device Database Sync — "The Nugget Protocol"

**Theme:** Every device running MACCREv2 contributes to a shared cognitive graph. No device is an island.

**Deliverables:**
- `maccre_core/tools/sync_tools.py` — `export_project_nugget()` and `import_project_nuggets()` tools
- `python maccre.py sync --project <NAME>` CLI subcommand
- Automatic post-swarm nugget export to `G:\My Drive\__DataCenter\<PROJECT>\_nuggets\`
- Watcher daemon emits a nugget export on every `RUN_COMPLETE` event
- ChromaDB vector snapshot: collections serialized to JSON, pushed to Drive
- SQLite WAL checkpoint + gzip export for `thoughts.db` and `swarm_queue.db`
- On import: foreign vectors merged via existing `import_foreign_vectors`, ledger entries replayed
- Device ID derived from machine hostname + Drive account — no manual registration

**Key constraint:** Swarms execute ONLY on the device where the triggering workbook was created. Nuggets are read-only reference data for other devices.

---

## Phase 20: Project Root Workbook + APPROVED Trigger

**Theme:** Every project is self-describing. Every swarm run is human-approved.

**Deliverables:**
- `initialize_workspace()` updated to copy `MACCRE_Swarm_Request.xlsx` template into project root on creation
- File existence check before every swarm run — Nexus regenerates missing template automatically
- Drive watcher updated: watches for `*_APPROVED.xlsx` pattern anywhere in `__DATACENTER` (recursive) — replaces current inbox-folder approach
- Approval is a human action (rename from Explorer, Google Drive, or Nexus TUI command)
- PIN elevation gate on Nexus `approve_workbook()` tool — Nexus cannot self-approve
- Archive of executed workbooks: renamed to `<PROJECT>_<TIMESTAMP>_EXECUTED.xlsx` in `04_Code_Artifacts/`

---

## Phase 21: Conversational Sheet Filling — Incremental Structured Outputs

**Theme:** Nexus designs swarms in conversation, the xlsx fills as you talk — not at the end.

**Deliverables:**
- Decompose `fill_swarm_sheet()` into sub-schema partial updates: `fill_project_metadata()`, `fill_agent_row()`, `fill_node_row()`
- Each responds to a single conversational turn with a Pydantic schema write to the xlsx
- Nexus confirms each field value aloud before writing: *"I'm writing Arcanus_The_Lorekeeper to row 3 of AGENTS with temperature 0.1 — confirm?"*
- Structured output sub-schemas use `gemini-2.5-flash` with `response_schema` for each atomic write
- Live xlsx preview via `read_file()` call after each write — Nexus can describe the current state
- User can override any cell verbally: *"Change Kaelen's temperature to 0.8"*

---

## Phase 22: Central Casting Library

**Theme:** Reuse the best agents across any project without redesigning them.

**Deliverables:**
- `MACCRE_Agent_Library.xlsx` created in `GLOBAL/04_Code_Artifacts/` — identical schema to AGENTS sheet
- `save_agent_to_library(agent_name)` — appends current agent to the library
- `inject_agent_from_library(agent_name, target_project)` — copies matching row into project workbook AGENTS sheet
- `list_library_agents()` — Nexus can browse available agents conversationally
- Library syncs to Google Drive as part of GLOBAL nugget exports — available on all devices
- Nexus proactively suggests library agents when designing new swarms: *"You seem to want a chapter-writing agent. Kaelen_The_Storyforger in the library is a match — inject?"*

---

## Phase 23: Full Datacenter Visibility — The Index Tool

**Theme:** Nexus can see, read, and reason about every artifact in the datacenter — including binaries.

**Deliverables:**
- `maccre_core/tools/index_tools.py` — `index_datacenter()` and `query_datacenter_index()` tools
- Text/JSON/CSV files: full content ingested into ChromaDB (existing flow)
- SQLite databases: schema introspection (`PRAGMA table_info`, row counts, sample rows) → ingested as structured metadata
- Binary files (MP4, WAV, PNG): `python-magic` MIME type + `ffprobe` metadata (duration, codec, resolution, bitrate) ingested as structured context with file path reference
- Agent ledgers (JSON): auto-ingested into `GLOBAL` project memory after each swarm
- Incremental re-indexing: file modification timestamps compared against last-indexed timestamp — only changed files re-ingested
- `index_datacenter()` is on-demand (not automatic on startup) to avoid cold-start latency
- Results stored in a dedicated ChromaDB collection: `datacenter_index`

---

## Phase 24: S25 Mobile — Spreadsheet GUI + Local Gemma Runner

**Theme:** Full MACCRE capability from a Samsung Galaxy S25 — design, configure, and monitor swarms from anywhere.

**Architecture Decision:** Grist (Apache 2.0, Python + TypeScript) or Univer (MIT, TypeScript) wrapped in Capacitor as an Android APK, with Google AI Edge SDK (MediaPipe) providing on-device Gemma inference.

**Deliverables:**
- **Mobile Workbook Editor:** Custom Grist/Univer Android app that edits exactly `MACCRE_Swarm_Request.xlsx` — not a general-purpose spreadsheet
- **Save-to-Drive:** One-tap upload to `G:\My Drive\__DataCenter\<PROJECT>\` with optional `_APPROVED` suffix to trigger the PC watcher
- **On-Device Gemma:** Google AI Edge SDK with `gemma3-1b` for swarm field suggestions, agent persona drafting, and TOPOLOGY instruction generation — all running on the S25 Hexagon NPU at ~30–40 tok/sec
- **AI Panel:** Embedded side-panel in the spreadsheet app — type a description, Gemma fills AGENTS and TOPOLOGY rows, you review and approve
- **Swarm Status Monitor:** Read-only view of watcher telemetry and swarm queue from the Drive sync, polling `watcher_telemetry.json`
- **Nugget Viewer:** Browse project databases and work products synced to Drive
- **Compute routing:** `local` tier → S25 Gemma; `cloud` tier → Gemini API via S25 internet; rendering always routes to PC (FFmpeg, Imagen, TTS)

**NPU Notes:** Snapdragon 8 Elite's Hexagon NPU is accessed via NNAPI delegate in MediaPipe LLM Inference API. Gemma 3 1B at INT4 quantization: ~40 tok/sec, ~1.5GB RAM. Gemma 3 4B at Q4: ~12 tok/sec, ~5GB RAM.

---

## Phase 25: Gemma Fine-Tuning from Project Ledgers

**Theme:** The swarm gets smarter with every project it completes.

**Deliverables:**
- `maccre_core/tools/finetune_tools.py` — dataset extraction from `thoughts.db` and agent ledger JSON
- Extracts high-quality instruction-response pairs from completed swarm nodes (instruction\_override → node\_output)
- Formats as Alpaca/ShareGPT JSONL fine-tuning datasets
- `python maccre.py finetune --project <NAME> --model gemma3:9b` — triggers LoRA fine-tuning via Ollama or direct `llama.cpp` training on PC GPU
- Fine-tuned weights committed to `__DATACENTER/GLOBAL/04_Code_Artifacts/models/<RUN_ID>/`
- Fine-tuned model available as a `compute_tier=local` override in the workbook AGENTS sheet
- On S25: same dataset synced to Drive → PC handles training → fine-tuned GGUF pushed back to Drive → S25 pulls and loads via Ollama Android (when available) or MediaPipe custom model path

---

## Phase 26: Omni Tool-Daemon (Parallel Track)

**Theme:** MACCRE's ambient process guardian evolves into a sovereign system-level entity.

This phase has its own founding doctrine at `B:\MACCREv2\OMNI_DAEMON_FOUNDING_DOCTRINE.md`. It is explicitly decoupled from MACCREv2 active sprints and proceeds only after Phase 23.

**Scope:** JIT script security auditing (AST fingerprinting, local LLM gray-area analysis), ambient OS monitoring (ETW kernel hooks), local TTS-vocalized threat reporting, and ZMQ PUB/SUB event bus replacing current SQLite polling in `local_broker.py`.

---

## Backlog (No Active Phase Assigned)

These items are technically sound but require revenue or ecosystem maturity before prioritization:

| Item | Dependency |
|---|---|
| Vertex AI Search swap (Strangler Fig escalation) | Customer contract requiring SLA |
| AlloyDB pgvector for ChromaDB | Same |
| Google Cloud Pub/Sub for Drive queue | Phase 19 nugget protocol must mature first |
| Enterprise SSO / multi-user MACCRE instances | Phase 24 mobile must ship first |
| Real-time collaborative workbook editing (Google Sheets native) | Phase 21 must ship first |
| Desktop GUI for swarm visualization (passive SQLite WAL consumer) | Phase 23 datacenter index must exist |

---

*"Cloud is getting us there. Sovereignty comes as the product earns it." — The Strangler Fig Doctrine*

*This roadmap is a living document. Each phase completes with a `PHASE_HISTORY.md` entry before the next begins.*
