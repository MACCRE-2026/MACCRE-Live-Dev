# EXO_GANS (Formerly MACCREv2)
## Modular Autonomous Cognitive Computing and Routing Engine -- Human Exo-Cortex Project

> [!IMPORTANT]
> **Architectural Shift: Zero-Cleartext Auth & TUI Nexus Plex (Phase 5/6)**
> The system has evolved into its most secure and interactive state yet. We are now operating a fluid, terminal-based Textual interface (The Nexus Plex) underpinned by Zero-Cleartext Authentication. The system remains strictly governed by the **Omni CI/CD Gatekeeper** and executed via rigorous Sovereign Physical Laws.

---

## 1. Current Project Momentum (v2.5 - Textual TUI & Zero-Cleartext Era)

The current development trajectory focuses heavily on strict capability routing, credential security, and rich media processing.

- **Zero-Cleartext Auth**: We have successfully refactored `maccre_core/_net` clients (e.g., `gemini_client.py`, `live_client.py`, `UniversalRouter`) to use the `windows_vault.py` DPAPI bindings. Credentials are resolved JIT (Just-In-Time) milliseconds before HTTP dispatch and purged from system memory via C-level `ctypes.memset` in a strict `try/finally` wipe block. Keys never touch disk or stay resident in python memory.
- **TUI Nexus Plex**: The Textual-based interface (`maccre_tui/nexus_plex.py`) provides an interactive split-pane environment for orchestrating node flows, managing macros, and injecting real-time context without leaving the terminal.
- **Payload & Manual Intercept**: Real-time human interaction has been injected directly into the swarm loop via the `MANUAL` MacroNode intercept, allowing users to alter payloads and inject context precisely at the exact point of need.
- **Unified File Cabinet & Ingestion Evolution**: Legacy hoarding scripts have been subsumed into `maccre_core/tools/notebook_ingest.py`, generating dynamic concept categories via federated namespaces in our bespoke SovereignStore.
- **FinOps Media Master Pipeline**: High-cost generative media actions (via `render_executor.py` and `finops_tools.py`) are strictly gated by Human-in-the-Loop authorization hooks with detailed pre-flight cost estimations.

---

## 2. The Omni JIT Gatekeeper (Sovereign Prefix Mandate)

You must **never** invoke bare Python scripts (e.g., `python maccre.py` or `python run.py`) when initiating a swarm. 

The architecture is protected by **Omni**, a globally pathed CI/CD Tool-Daemon that intercepts execution to run Ruff/Pyright validation and eradicate hanging background zombie processes before the Python interpreter ever spins up.

**The Canonical Launcher:**
```bash
omni run
```
*This command automatically resolves the local virtual environment, hunts for zombies, and boots the Nexus Plex TUI via `run.py`.*

For the full operational doctrine on `omni build`, `omni qa`, and `omni clean`, refer to: [omni_system_state_doctrine.md](file:///B:/EXO_GANS/omni_system_state_doctrine.md).

---

## 3. Evolutionary Lineage: From 1stGen to Sovereign Edge

The foundational architecture of this project was forged using the original system prompts located at `C:\Users\wilke\.gemini\1stGen-GEMINI.md.bak`. Those 1stGen instructions instilled the extreme structural discipline—the Strangler Fig ABCs, the 5-Tier Datacenter, and the absolute Type Hinting mandates—that allowed this project to survive its chaotic early growth phases.

However, as the project evolved into the EXO_GANS framework and underwent the Omni Bifurcation, the Primary Antigravity Agent and the lead developer collaboratively rewrote the system instructions. By reflecting on the positive changes and evolutions the project has undergone, we reinforced the absolute best parts of the old doctrine while demonstrating the flexibility to evolve relentlessly when warranted. We stripped out deprecated constraints (like Google Workspace API dependencies and the official `google-genai` SDK) and replaced them with our bespoke Sovereign REST clients, SQLite WAL telemetry matrices, and TUI physics.

---

## 4. The 5-Tier Sovereign Datacenter

Because EXO_GANS is a file-driven edge ecosystem, understanding **where** files belong is critical. All active work product, logic, memory, and telemetry for a given run is siloed inside `__DATACENTER/<Project_Name>/` across 5 strict tiers:

1. **`01_Raw_Source/`**: Unstructured text, context dumps, and payload `.md` drops.
2. **`02_Dynamic_Context/`**: Parsed knowledge, `memory_pins/`, and ephemeral state vectors.
3. **`03_Agent_Ledgers/`**: Strict JSON files containing every thought, fetch, and API call.
4. **`04_Code_Artifacts/`**: Synthesized Python logic outputs.
5. **`05_Rendered_Media/`**: Compiled reports and visual media.

**Portability Doctrine (Law VIII):** All filesystem paths are runtime-computed using `get_maccre_root()` in `maccre_core/utils/path_resolver.py`. **Never hardcode an absolute path.**

---

## 5. Active Discoveries & Technical Notes

- **Parallel Advocates & Auto-Wrapping:** The routing engine successfully supports dynamic Auto-Wrapped MacroNodes and Parallel Advocates. The `GroupDialogueRunner` maintains conversational state isolation perfectly.
- **CSS Fluidity Engine:** The Nexus Plex TUI successfully uses fractional `1fr` widths, ensuring dynamic scaling across terminal sizes.
- **The MANUAL Cascade Bug (RESOLVED):** We resolved the previous critical routing failure for `MANUAL` cascade loops by implementing the TUI Manual Intercept pause events inside `swarm_worker.py`.

---
---

# ARCHIVED VERSIONS (Versioned Changelog)

*The following versions are deprecated and kept intact below to provide a firm anchor in time for later analysis.*

---

## ARCHIVE: v2.0 - The Textual TUI Era Shift

> [!IMPORTANT]
> **Architectural Shift: The Textual TUI Era has Begun.**
> The system has evolved beyond the pure, headless CLI era and the deprecated Flet GUI era. We are now operating a fluid, terminal-based Textual interface (The Nexus Plex). The system is strictly governed by the **Omni CI/CD Gatekeeper** and executed via rigorous Sovereign Physical Laws.

### Current Project Momentum
The current development trajectory is strictly defined by the Alphabet Oracle's 6-Phase Hardening Plan, located at: [Oracle_Hardening-Features-implementation_plan.md](file:///B:/EXO_GANS/Oracle_Hardening-Features-implementation_plan.md). 

### Active Discoveries & Technical Notes
- **Parallel Advocates & Auto-Wrapping:** The routing engine successfully supports dynamic Auto-Wrapped MacroNodes and Parallel Advocates (e.g., `CounterPartner` running alongside `Writer_Pipe`). The `GroupDialogueRunner` maintains conversational state isolation perfectly.
- **CSS Fluidity Engine:** The Nexus Plex TUI has successfully migrated to fractional `1fr` widths. The layout dynamically scales during terminal resizes (`Ctrl +`/`Ctrl -`), permanently ending the era of "squashed" vertical text anomalies.
- **The MANUAL Cascade Bug (PENDING PATCH):** There is currently a critical routing failure when assigning the user (`MANUAL`) to a cascade loop (e.g., `OSINTx3`). The failure occurs inside `maccre_core/orchestration/swarm_worker.py` at the `_load_agent_cfg` injection boundary. The engine attempts to pull a system prompt from the AI roster for `MANUAL`, triggering a `KeyError` because `MANUAL` is an organic user intercept, not a synthetic entity. This is prioritized for Phase 5/6 hardening.

---

## ARCHIVE: v1.0 - MACCREv2 Headless Phase 0

# MACCREv2 
## Modular Autonomous Cognitive Computing and Routing Engine -- Human Exo-Cortex Project 

> **Notice:** MACCREv2 has executed the Decapitation Protocol and achieved Phase 0 Operational Hardening. *The GUI era has ended.* The architecture is now a pure, headless, SQLite-brokered multi-agent swarm ecosystem executing within rigorous CI/CD constraints.

### Foundational Canon & Project History
All architectural documentation has been strictly curated and moved to the `_historical_documentation` directory.

If you are a new developer or an un-initiated agent seeking the operational rules and current architectural roadmap for exactly *how* this engine functions, you **must** read the files located in:
`_historical_documentation/03_Current_Canon`

Specifically:
- `OMNI_DAEMON_FOUNDING_DOCTRINE.md`: The absolute rules of the headless ecosystem.
- `MACCRE_Phase_Roadmap.md`: The 6-Phase evolution plan for moving to pure sovereign dependencies.
- `Sovereignty_Analysis.md`: The justification and physics of zero-dependency edge infrastructure.
- `Philosophical_Proposal.md`: The extrapolation toward crowd-compute Neural P2P swarming.

**Portability Doctrine (Law VIII):** All filesystem paths in MACCREv2 are runtime-computed using `get_maccre_root()` in `maccre_core/utils/path_resolver.py`. **Never hardcode an absolute path** in any source file. New installs: run `python setup_mcp.py` once to generate the correct `mcp_config.json` for your machine. See `_historical_documentation/02_Transitional_Logs/PHASE_HISTORY.md` Phase 19 for full remediation history.

### Legacy Code & Documentation
Any documents outlining `forge_smith.py`, Flet implementations, early tool-calling schemas, or outdated `ROADMAP.md` iterations have been moved to `_historical_documentation/01_Deprecated_GUI_Era` for context preservation. Do **not** use them to determine current workflows. All legacy code is archived similarly in `_archive`.

***

## 🌐 MACCREv2: Sovereign Operations & Telemetry Manual

Because MACCREv2 is a headless, file-driven edge ecosystem, understanding **where** files belong and **how** they flow through the engine is critical. Do not execute ad-hoc directory hunting. The engine adheres strictly to the **5-Tier Datacenter** doctrine.

### 1. The Global Entry Point (Project Initiation)
Everything begins at the root workspace.
- **`MACCRE_Global.xlsx`**: The master creator topology. You manually fill out this workbook at `B:\MACCREv2\MACCRE_Global.xlsx` to define new Agents, Memory Configurations, and Tool Pipelines.
- **Action:** Run `python maccre.py global`
- **Result:** The engine creates the Project Schema, instantiates SQLite databases (`swarm_queue.db` & `system_logs.db`), and builds the isolated `__DATACENTER/<Project_Name>/` vault.

### 2. The Datacenter Vault (`__DATACENTER/<Project_Name>/`)
All active work product, logic, memory, and telemetry for a given run is strictly siloed inside its own project environment.

#### **Input Pipelines (Where you put things):**
- **`01_Raw_Source/`**: Drop unstructured text, context dumps, or payload `.md` files here. `maccre.py ingest` will hash them to determine delta shifts.
- **`MACCRE_Session.xlsx`**: The actual "Task Execution" request. Manually copy the Swarm_Request template into the root of the project vault (e.g. `__DATACENTER/MyProject/MACCRE_Session.xlsx`), select your starting node, and launch.
- **Action:** Run `python maccre.py launch <Project_Name>`

#### **Execution & Artifact Pipelines (Where things go):**
When a Swarm is launched, the workflow mutates deterministically:
- **`CompletedSessions/`**: The moment a session launches, MACCRE makes a physical, immutably time-stamped clone of your `MACCRE_Session.xlsx` (e.g. `<SessionId>_Session.xlsx`). You can safely use these to instantly recreate historical swarms perfectly.
- **`03_Agent_Ledgers/`**: Contains raw markdown files containing every thought, API fetch, and file read generated by the Swarm during runtime, categorized by `Job_ID`.
- **`04_Code_Artifacts/` & `05_Rendered_Media/`**: Any physical work product outputs (synthesized python logic, rendered images, compiled reports) are saved directly here.

### 3. Dual-Tier Session Telemetry (`Op-logs` vs `Bug-logs`)
MACCREv2 has severed monolithic console logging. All logging is now entirely **Session-Isolated** and separated by machine/human readable tiers inside the project Datacenter:

- **`Op-logs/<Session_Id>.log`** (Operational / Human Readable)
  - Records high-level state shifts, node transitions, and total swarm costs. Format is clean prose.
- **`Bug-logs/<Session_Id>.log`** (Diagnostic / Machine Strict)
  - Retains heavy JSON metadata payloads of exact vector coordinates, raw exception stacks, and routing payload parameters. Used exclusively when breaking down complex failures.

**CLI Telemetry Overrides:**
- `python maccre.py --debug launch <Project>` (Toggles `Bug-logs` capture back ON if temporarily disabled in `logger.py`).
- `python maccre.py logs clear --project <Project_Name> --session all --type op` (Allows rapid destruction of heavy log caches globally or per session/project constraint).
