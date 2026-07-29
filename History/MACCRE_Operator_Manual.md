# MACCREv2 Operator Manual
**Revision:** 2026-04-28 · Law Rev 19.0

---

## Part I — Concepts

### What MACCRE Is
MACCREv2 is a headless, terminal-first **swarm orchestration engine**. You define a pipeline of AI agents (a *topology*), give each agent a persona and a role, drop in a payload, and fire. Agents execute in sequence, passing their output downstream until the pipeline terminates.

### The Three Durable Objects
| Object | Where it lives | Purpose |
|---|---|---|
| **Agent Roster** | `agent_roster.csv` (per-project) | Who the agents are — name, model, persona, tools |
| **Topology** | `topology.csv` (per-project) | How they connect — node order, routing, overrides |
| **Workbook** | `MACCRE_Global.xlsx` (root) | The operator control surface — edit, then fire |

The workbook is **always a disposable snapshot**. The CSVs are the durable source of truth. Running `workbook refresh` re-generates the workbook from live disk state.

### The DATACENTER (5-Tier Layout)
```
__DATACENTER/
  <ProjectName>/
    01_Raw_Source/        ← Drop source files + input.md here
    02_Dynamic_Context/   ← topology.csv lives here
    03_Agent_Ledgers/     ← Tool audits, launch failures, thoughts
    04_Code_Artifacts/    ← Agent output files
    05_Rendered_Media/    ← Audio/video render output
    Op-logs/              ← Human-readable session logs
    Bug-logs/             ← JSON debug logs
    CompletedSessions/    ← Archived workbooks per session
```

---

## Part II — CLI Reference (`python maccre.py`)

### `new` — Provision a project silo
```
python maccre.py new <ProjectName>
```
Creates the full 5-tier DATACENTER directory tree, initialises blank SQLite databases, and writes a fresh `MACCRE_Session.xlsx` into the silo. Run this once per project.

**After running:**
1. Drop source documents into `__DATACENTER/<Project>/01_Raw_Source/`
2. Run `ingest` to vectorise them
3. Fill the workbook and `launch`

---

### `workbook refresh` — Regenerate the Global Workbook
```
python maccre.py workbook refresh [--project <Name>] [--out <path>]
```
Generates `MACCRE_Global.xlsx` at the project root with **live data injected**:
- AGENTS sheet pre-populated from `agent_roster.csv`
- TOPOLOGY sheet pre-populated from `topology.csv`
- PROJECT_NAME pre-filled from `--project`
- START_NODE pre-filled from first row of topology
- EXECUTION_PLAN stamped with live READY / PARTIAL / INCOMPLETE status and colour coding
- MODEL dropdowns sourced from all 55 registered models
- PROJECT_DEFINITION dropdown lists every existing silo

> **Close the workbook in Excel before refreshing.** Excel locks the file.

---

### `workbook fire` — Execute from the Global Workbook
```
python maccre.py workbook fire [--workbook <path>] [--project <Name>] [--yes]
```
Parses the open workbook, materialises agents + topology into the project silo, injects the payload, and starts the swarm. A **Swarm Watcher** window opens automatically showing live thoughts and responses.

`--yes` skips the confirmation prompt (useful for scripting).

---

### `launch` — Execute a project's Session Workbook
```
python maccre.py launch <ProjectName> [--workbook <path>] [--yes] [--resume] [--from-node <NODE>]
```
Full session launch: reads `MACCRE_Session.xlsx` from the project silo, validates topology, materialises, runs the swarm. Respects SESSION_CONFIG hooks.

| Flag | Effect |
|---|---|
| `--resume` | Skip materialise — drain the existing pending queue |
| `--from-node NODE` | Insert a fresh queue row at NODE then resume (checkpoint restart) |
| `--yes` | Skip confirmation prompt |
| `--workbook PATH` | Use a specific xlsx instead of the default |

**SESSION_CONFIG hooks (set in workbook):**
- `INGEST_BEFORE_RUN=TRUE` — vectorise `01_Raw_Source` before the swarm runs
- `INGEST_AFTER_RUN=TRUE` — vectorise `04_Code_Artifacts` after the swarm
- `CANONIZE_AFTER_RUN=TRUE` — promote session thoughts to project memory

---

### `global` — Execute from the Global Workbook (full pipeline)
```
python maccre.py global [--workbook <path>] [--yes] [--skip-preflight]
```
Reads `MACCRE_Global.xlsx`, checks completeness, materialises all actionable sections, runs the swarm, and writes a session record. Identical to `workbook fire` but uses the legacy global pipeline path.

---

### `run` — Direct fire, no workbook
```
python maccre.py run <ProjectName> "<payload text or @file.md>" [--node <NODE>] [--yes]
```
Fastest path. Writes the payload directly to `01_Raw_Source/input.md`, validates topology, and fires. No workbook interaction required.

**Payload resolution order:**
1. `@/path/to/file.md` — reads that file
2. A valid filesystem path — reads that file
3. Any other string — written as-is to `input.md`

```bash
# Examples
python maccre.py run NewsNexus "Summarize key operational findings" --node OSINT --yes
python maccre.py run ResearchProject @brief.md --yes
```

---

### `ingest` — Vectorise project sources
```
python maccre.py ingest <ProjectName>
```
Bulk-ingests all files in `01_Raw_Source/` into the project's ChromaDB vector store using SHA-256 deduplication. Only new or changed files are processed.

---

### `topology list` — List saved topologies
```
python maccre.py topology list [--project <Name>]
```
Displays all topologies saved to the global or project library (name, node count, creation date, description).

### `topology save` — Save current topology to library
```
python maccre.py topology save --name "<Name>" [--project <Name>] [--description "<text>"]
```
Snapshots the current `topology.csv` + `agent_roster.csv` into the topology library for reuse. Saved to both the project silo and the GLOBAL library.

### `topology load` — Load a saved topology
```
python maccre.py topology load --name "<Name>" --project <TargetProject> [--yes]
```
Overwrites `topology.csv` and `agent_roster.csv` in the target project with the named saved topology.

### `topology delete` — Remove a saved topology
```
python maccre.py topology delete --name "<Name>" [--project <Name>]
```

---

### `audit` — Inspect tool audit ledgers
```
python maccre.py audit <ProjectName> [--job <job_id>] [--node <NODE>] [--tail <N>]
```
Reads forensic tool-call sidecars from `03_Agent_Ledgers/`. Every tool invocation in a swarm run is logged verbatim here.

```bash
python maccre.py audit NewsNexus                        # all audits for project
python maccre.py audit NewsNexus --node OSINT --tail 80 # last 80 lines of OSINT audits
python maccre.py audit NewsNexus --job job_a1b2c3d4     # specific job
```

---

### `brief` — Session context brief
```
python maccre.py brief [--project <Name>]
```
Prints a formatted brief: git log, 7-day cost, Sentinel health, recent sessions.

---

### `status` — Queue status
```
python maccre.py status
```
Reads the SQLite task queue directly and prints the last 15 job rows with current node, lock status, and actual cost.

---

### `canonize` — Promote session to project memory
```
python maccre.py canonize <ProjectName> <session_id>
```
Exports L1 thoughts from the session and merges session artifacts into the project's long-term knowledge store.

---

### `intercept` — Hot-mic priority override
```
python maccre.py intercept --session <session_id> --message "<instruction>"
```
Injects a live priority instruction into a running swarm session. The worker picks it up on the next polling cycle.

---

### `logs clear` — Purge session logs
```
python maccre.py logs clear <ProjectName> [--session <id>|all] [--type op|bug|all]
```

---

### `sessions list / kill` — Process registry
```
python maccre.py sessions list   # show active swarm PIDs
python maccre.py sessions kill   # SIGTERM all registered swarm processes
```

---

### `smoke` — Pre-flight smoke test
```
python maccre.py smoke
```
Runs the pre-flight smoke test standalone. Exits 0 on pass, 1 on fail.

---

### `pattern submit / list / poll` — Swarm patterns
```
python maccre.py pattern list
python maccre.py pattern submit --name <pattern> --payload "<text>" [--project <Name>]
python maccre.py pattern poll --job-id <id>
```
Fires a named pattern topology (e.g. `research_sweep`, `code_review`, `simulation_swarm`) into an isolated silo and polls for the HUMAN_GATE result.

---

### `ignite` — Raw queue injection
```
python maccre.py ignite "<payload_path>" [--node <NODE>]
```
Low-level: injects a payload path directly into the swarm queue at a given node. Used internally; prefer `run` for operator use.

---

## Part III — Global Workbook Sheet Reference

### `PROJECT_DEFINITION`
| Field | Required | Notes |
|---|---|---|
| PROJECT_NAME | ✅ | Must match an existing silo or a new name will be auto-provisioned |
| DESCRIPTION | — | Free text, used in session records |
| SESSION_LABEL | — | Tag appended to the session ID (e.g. `chapter_2_outline`) |
| SAVE_TO_LIBRARY | — | TRUE = snapshot agents + topology to library on successful fire |
| LINKED_PROJECTS | — | Comma-separated project names for Synaptic Bridge memory federation |

---

### `AGENTS`
Each row defines one agent. Fill as many rows as needed.

| Column | Required | Notes |
|---|---|---|
| AGENT_NAME | ✅ | Unique identifier. Used in TOPOLOGY's AGENT_NAME column |
| MODEL | ✅ | Select from dropdown (all 55 registered models) |
| ROLE | — | Short role label (e.g. `Researcher`, `Critic`) |
| PERSONA | ✅ | Full system prompt. This is the agent's identity and instructions |
| TEMPERATURE | — | 0.0–2.0. Default 1.0 for generators, 0.1 for critics/extractors |
| TOOLS | — | Pipe-separated tool names: `google_search\|write_file\|read_file` |
| TOP_P / TOP_K | — | Sampling parameters |
| MAX_OUTPUT_TOKENS | — | Cap agent response length |
| THINKING_BUDGET | — | Token budget for internal reasoning (Flash Thinking models) |
| SEARCH_GROUNDING | — | TRUE = enable Google Search grounding (Gemini feature) |
| RESPONSE_FORMAT | — | `markdown`, `json`, `text` |
| SAFETY_LEVEL | — | `standard`, `strict`, `permissive` |
| COMPUTE_TIER | — | `cloud`, `edge`, `local` |

**Agent Persona Patterns:**

```
# Generator (creative/research) — high temperature
You are [NAME], a [role]. Your sole objective is [specific goal].
Write in [style]. Do not hedge. Do not summarise what you are doing—just do it.
Output format: [markdown/json/structured].

# Critic/Extractor — low temperature, structured output
You are [NAME], a rigorous [role]. Your task is to extract [specific data]
from the input and return it as structured JSON matching this schema: {...}.
Never invent data. If a field is absent, return null.

# Synthesiser — medium temperature
You are [NAME]. You receive multiple upstream agent outputs and synthesise
them into a single coherent [deliverable]. Prioritise [criteria].
Resolve conflicts by [rule]. Max output: [N] words.
```

---

### `TOPOLOGY`
Each row is a node in the pipeline. Rows execute in the order they are routed (via NEXT_NODE), not necessarily top-to-bottom.

| Column | Required | Notes |
|---|---|---|
| NODE_ID | ✅ | Unique string. Convention: `SCREAMING_SNAKE` (e.g. `OSINT_GOOGLE`) |
| AGENT_NAME | ✅ | Must match an AGENT_NAME from the AGENTS sheet |
| NEXT_NODE | ✅ | NODE_ID of the next node, or `DONE` / `FAILED` to terminate |
| MODEL_OVERRIDE | — | Override the agent's default model for this node only |
| TEMPERATURE | — | Override the agent's default temperature for this node |
| MAX_RECURSION | — | Max times this node may re-execute (default 3) |
| INSTRUCTION_OVERRIDE | — | Append extra instructions to the agent's persona for this node |

**Routing keywords:**
- `DONE` — normal pipeline termination
- `FAILED` — error termination path
- Any valid NODE_ID — continues the pipeline

**Node Combination Recipes:**

```
# Linear pipeline (A → B → C)
NODE_A  │ AGENT_A │ NODE_B
NODE_B  │ AGENT_B │ NODE_C
NODE_C  │ AGENT_C │ DONE

# Fan-out to parallel paths (use WAIT_FOR to re-merge)
FORK    │ COORDINATOR │ PATH_A,PATH_B   ← agent routes dynamically
PATH_A  │ RESEARCHER_A │ MERGER
PATH_B  │ RESEARCHER_B │ MERGER
MERGER  │ SYNTHESISER  │ DONE           ← Wait_For: PATH_A,PATH_B

# Retry / self-correction loop
WRITER  │ AGENT  │ CRITIC
CRITIC  │ CRITIC │ DONE (if approved) or WRITER (if revision needed)
# Critic's INSTRUCTION_OVERRIDE: "If quality >= 8/10 output ROUTE:DONE, else ROUTE:WRITER"

# Research → Synthesis → Output
OSINT_GOOGLE  │ RESEARCHER │ OSINT_BRAVE
OSINT_BRAVE   │ RESEARCHER │ SYNTHESISER
SYNTHESISER   │ SYNTHESISER│ WRITER
WRITER        │ WRITER     │ DONE
```

> **Critical rule:** Every NEXT_NODE value must be a NODE_ID that exists in the topology, or one of the terminal keywords `DONE` / `FAILED`. The pre-flight topology validator will catch broken links before the swarm fires.

---

### `SWARM_REQUEST`
The per-run launch parameters. Filled once per fire.

| Column | Required | Notes |
|---|---|---|
| PROJECT_NAME | ✅ | Pre-filled from `--project` flag. Must match a silo |
| DESCRIPTION | — | Human note for this run |
| COMPUTE_TIER | — | `cloud` (default), `edge`, `local` |
| PAYLOAD_TEXT | ✅* | Inline text payload. Use this OR PAYLOAD_PATH |
| PAYLOAD_PATH | ✅* | Absolute or relative path to a `.md` file. Use this OR PAYLOAD_TEXT |
| START_NODE | ✅ | Pre-filled from first topology node. Change to restart from mid-pipeline |
| OUTPUT_FOLDER | — | Override the default output directory |
| NOTIFY_WEBHOOK | — | POST result summary to this URL on completion |

*At least one of PAYLOAD_TEXT or PAYLOAD_PATH is required.

---

### `SESSION_CONFIG`
Lifecycle hooks for the session. Only meaningful when using `launch` (not `workbook fire`).

| Setting | Values | Effect |
|---|---|---|
| PROJECT_NAME | text | Must match the project silo |
| SESSION_LABEL | text | Tag appended to session ID |
| INGEST_BEFORE_RUN | TRUE/FALSE | Vectorise `01_Raw_Source` before swarm |
| INGEST_AFTER_RUN | TRUE/FALSE | Vectorise `04_Code_Artifacts` after swarm |
| CANONIZE_AFTER_RUN | TRUE/FALSE | Promote session memory to project knowledge |
| OUTPUT_FORMATS | `md,txt,json` | Comma-separated list of output formats |

---

### `EXECUTION_PLAN`
**Read-only during operation.** Automatically stamped by `workbook refresh` with live status. Do not edit manually.

| Status | Colour | Meaning |
|---|---|---|
| READY | 🟩 Green | All required fields present, section will execute |
| PARTIAL | 🟨 Amber | Optional fields missing but can still run (e.g. no payload yet) |
| INCOMPLETE | 🟥 Red | Required fields missing — swarm will not fire |

The NOTES column shows the first diagnostic hint (e.g. `No payload (PAYLOAD_TEXT or PAYLOAD_PATH) — swarm will not run`).

---

### `PIPELINE_CONFIG`
Advanced key/value runtime settings. Rarely needed for standard operation.

---

### `VAULT_KEYS`
Reference table for credential names. These are read by the engine at runtime.

| KEY_NAME | VAULT_REF | Notes |
|---|---|---|
| GEMINI_API_KEY | MACCRE_Sovereign | Required for all cloud inference |
| BRAVE_SEARCH_API_KEY | BRAVE_SEARCH_API_KEY | Required for OSINT_BRAVE web search |
| DRIVE_CREDS | MACCRE_Drive | Google Drive service-account credentials |

---

### `SESSION_LOG`
**Read-only.** Populated by `workbook refresh` with the last N completed sessions: session ID, project, cost, timestamp, status.

---

## Part IV — The Swarm Watcher

When any swarm fires via the CLI, a **Swarm Watcher** console window opens automatically showing:

```
◈ MACCRE SWARM WATCHER  │  job: job_a1b2c3d4  │  project: NewsNexus  │  elapsed: 00:02:33
─────────────────────────────────────────────────────────────────────────────────────────
◈ THOUGHTS & ERRORS              │  ◈ RESPONSES & EVENTS
─────────────────────────────────┼──────────────────────────────────────────────────────
[22:01:15] [OSINT] reasoning...  │  [22:01:58] [OSINT] TOOL_FIRED: google_search
[22:01:45] [ERROR] rate limit    │  [22:01:59] [OSINT] NODE_ROUTED: OSINT → SYNTHESISER
─────────────────────────────────────────────────────────────────────────────────────────
TOPOLOGY:  ✓OSINT_GOOGLE ──► ✓OSINT_BRAVE ──► ▶SYNTHESISER ──► ○DONE
 Node 3/4  │  $0.0023 spent  │  status: pending  │  [Q] detach  [↑/↓] scroll thoughts
```

**Keys:**
- `↑ / ↓` — scroll the THOUGHTS panel
- `← / →` — scroll the RESPONSES panel  
- `Q` or `ESC` — detach (watcher closes, swarm continues in background)

---

## Part V — Failure & Recovery

### Failure-to-Launch Log
Any exception during `ignite_swarm()` writes a JSON record to:
```
__DATACENTER/03_Agent_Ledgers/launch_failures.jsonl
```
Each record contains: `timestamp`, `job_id`, `payload_path`, `starting_node`, `error` (with full Python traceback).

### Mid-Pipeline Recovery
If a swarm crashes mid-run, restart from the failed node:
```bash
python maccre.py launch <Project> --from-node <FAILED_NODE> --yes
```
This injects a new queue row at the specified node and drains the queue, skipping all upstream nodes.

### Stale WAL Locks
If a swarm crashes leaving SQLite locked:
```bash
python maccre.py sessions list   # identify zombie processes
python maccre.py sessions kill   # SIGTERM all registered swarm PIDs
omni clean .                     # purge cache and zombie processes
```

### Topology Validation Errors
The pre-flight validator runs automatically before every `launch` and `run`. If it fails:
```
[LAUNCH] ✗ Pre-flight FAILED — fix the errors above before re-running.
  (Set MACCRE_SKIP_VALIDATE=1 to bypass for dynamic topologies.)
```
Fix the broken NEXT_NODE references in the TOPOLOGY sheet, refresh the workbook, and re-fire. Set `MACCRE_SKIP_VALIDATE=1` only for topologies with agent-driven dynamic routing.

---

## Part VI — Standard Operator Workflows

### Workflow A: New Project from Scratch
```bash
# 1. Provision the silo
python maccre.py new MyProject

# 2. Drop source files
# Copy research docs, briefs, etc. into:
# __DATACENTER/MyProject/01_Raw_Source/

# 3. Vectorise sources
python maccre.py ingest MyProject

# 4. Generate workbook with live data
python maccre.py workbook refresh --project MyProject

# 5. Fill the workbook:
#    - AGENTS: define personas and tools
#    - TOPOLOGY: wire the pipeline
#    - SWARM_REQUEST: paste your payload or set PAYLOAD_PATH
#    - Check EXECUTION_PLAN — all sections should be READY

# 6. Fire (close the workbook in Excel first)
python maccre.py workbook fire --project MyProject
```

### Workflow B: Reload a Saved Topology
```bash
# List what's in the library
python maccre.py topology list

# Load a proven topology into your project
python maccre.py topology load --name "research_sweep_v3" --project MyProject --yes

# Refresh the workbook to pull the loaded topology into the sheets
python maccre.py workbook refresh --project MyProject
```

### Workflow C: Quick Fire Without a Workbook
```bash
python maccre.py run MyProject "Analyse the competitive landscape for MACCRE" --node OSINT --yes
```

### Workflow D: Save a Successful Topology to Library
```bash
# After a successful run, snapshot it for reuse
python maccre.py topology save --name "osint_synthesis_v1" --project MyProject \
  --description "Two-node OSINT fan-out with Gemini synthesis"
```

### Workflow E: Checkpoint Restart
```bash
# Swarm crashed at SYNTHESISER — restart just that node forward
python maccre.py launch MyProject --from-node SYNTHESISER --yes
```

---

## Part VII — Model Selection Guide

| Tier | Models | Best For |
|---|---|---|
| **Flash** | `gemini-2.5-flash`, `gemini-3.1-flash` | High-volume nodes, tool-calling, fast iteration |
| **Pro** | `gemini-2.5-pro`, `gemini-3.1-pro` | Complex reasoning, synthesis, long-context |
| **Thinking** | `gemini-2.5-flash-thinking` | Critic nodes, structured extraction, verification |
| **Edge/Local** | Gemma 3 variants via Ollama | Tagging, hot-mic detection, cost-sensitive nodes |

**Diamond Loop rule:**
- Generator nodes (creative/research) → `temperature=1.0`, Flash or Pro
- Critic/Extractor nodes → `temperature=0.1`, Thinking models preferred

---

## Quick Reference Card

```
PROVISION     python maccre.py new <Project>
INGEST        python maccre.py ingest <Project>
REFRESH WB    python maccre.py workbook refresh --project <Project>
FIRE WB       python maccre.py workbook fire
QUICK FIRE    python maccre.py run <Project> "<payload>" --node <NODE> --yes
RESUME        python maccre.py launch <Project> --from-node <NODE> --yes
STATUS        python maccre.py status
AUDIT         python maccre.py audit <Project> [--node <NODE>] [--tail 80]
BRIEF         python maccre.py brief --project <Project>
SAVE TOPO     python maccre.py topology save --name "<Name>" --project <Project>
LOAD TOPO     python maccre.py topology load --name "<Name>" --project <Project> --yes
KILL ZOMBIES  python maccre.py sessions kill
CANONIZE      python maccre.py canonize <Project> <session_id>
HOT-MIC       python maccre.py intercept --session <id> --message "<instruction>"
```
