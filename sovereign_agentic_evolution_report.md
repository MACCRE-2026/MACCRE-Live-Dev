# // MACCRE Systems //
# Architectural Report: The Evolution of Sovereign Edge Agentic Engineering — From Global Rules to a Specialized 5-Oracle Swarm

**Author:** Frank Wilke -Senior Project Architect // MACCRE Systems //   
**Project:** MACCREv2  
**Date:** July 28, 2026  
**Document Type:** Formal System Architecture & Multi-Agent Design Specification  

---

## Executive Summary

Scaling complex, zero-dependency autonomous AI systems demands rigorous controls. Without them, large codebases fall victim to operational hallucination and silent type degradation. As MACCREv2 and EXO_GANS developed, we recognized that a centralized, single-prompt architecture was insufficient. To maintain systemic integrity, the runtime evolved into a federated model: a five-node specialist swarm.

This report documents that architectural maturation. It traces the progression from early global rules to the simulated reasoning of the Alphabet Oracle, culminating in the current native sub-agent infrastructure. It outlines the operational pipelines, the cognitive memory system (the task ledger), the precise instructions governing each domain, and the root-level quality assurance standards required to ensure type safety across the environment.

---

## 1. Early Architecture: From Global Rules to In-Project Reasoning

In the project's early stages, AI assistants relied on static global prompts stored in standard user-level configuration files (e.g., `~/.gemini/antigravity/GEMINI.md`). These baseline parameters established core operational boundaries, including the `omni run` execution prefix, standard library REST compliance, and physical memory sanitization via `ctypes.memset`.

While these global rules functioned well for low-level execution boundaries, they lacked domain-specific context. For complex state transitions or TUI interface designs, a single generic agent prompt did not possess the architectural depth necessary to evaluate systemic trade-offs.

### Simulated Secondary Reasoning (The Alphabet Oracle)
To bridge this gap before native multi-agent frameworks were available, we implemented the Alphabet Oracle profile, stored in the project workspace at `[PROJECT_ROOT]/.agent/skills/alphabet-oracle/SKILL.md`. This profile acted as a principal ecosystem architect. During complex reasoning tasks, the primary agent would temporarily adopt this persona to simulate an architectural review, isolating high-level audit logic from active code synthesis.

```text
┌──────────────────────────────────────────────────────────────────────────┐
│                      PHASE 1: SIMULATED REASONING                        │
├──────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│   Single Context ───► Injects Alphabet Oracle Skill (SKILLS.md)          │
│                                     │                                    │
│                                     ▼                                    │
│                     Simulated Architectural Review                       │
│                     (Single Thread / Single Context)                     │
│                                                                          │
└──────────────────────────────────────────────────────────────────────────┘
```

---

## 2. Native Orchestration: The Five-Oracle Swarm

The introduction of native multi-agent orchestration (`invoke_subagent`) allowed the primary agent to spawn concurrent sub-agents in background contexts. To leverage this without overwhelming human oversight, the monolithic Alphabet Oracle was divided into five specialized sub-agents. Each oracle was granted specific domain governance over a distinct subsystem layer of the MACCREv2 codebase.

```text
┌──────────────────────────────────────────────────────────────────────────┐
│                   PHASE 2: THE FIVE-ORACLE SWARM                         │
├──────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│                        ┌──► Net & Client (maccre_core/_net/)             │
│                        │                                                 │
│                        ├──► Orchestration & Engine (orchestration/)      │
│   Primary Agent  ──────┼──► TUI & Interface (maccre_tui/)                │
│                        │                                                 │
│                        ├──► Tools & RAG (tools/, FastMCP)                │
│                        │                                                 │
│                        └──► State & Sovereignty (Vault, Telemetry)       │
│                                                                          │
└──────────────────────────────────────────────────────────────────────────┘
```

### Domain Specializations

1. **Net & Client Oracle**: Governs zero-SDK `urllib` REST clients (`gemini_client.py`), handles hardware probing (`environment_probe.py`), monitors throughput limits, and manages zero-dependency OOXML workbook packaging.
2. **Orchestration & Engine Oracle**: Directs the flow engine and swarm execution loops. This includes managing deterministic control primitives, handling scatter-gather task queues, and executing pre-flight topology DAG validation.
3. **TUI & Interface Oracle**: Focuses on the Textual `nexus_plex.py` command center. Responsibilities cover interactive transport state machines, reactive bindings, and the topology visualizer layout.
4. **Tools & RAG Oracle**: Dispatches the tool registry and maintains hybrid retrieval search engines (combining vector, SQLite FTS5 BM25, and web RRF). It also oversees the media rendering pipelines.
5. **State & Sovereignty Oracle**: Controls the federated key vaults (`universal_vault.py`), manages multi-tier access control, and ensures compliance with the SQLite WAL telemetry matrix and file archive safety protocols.

---

## 3. Datacenter Pipelines and Context Bootstrapping

To ensure operational consistency, we established structured artifact isolation within the project directory. 

### Context Bootstrapping (The Refresher Protocol)
Instead of parsing the entire codebase upon every invocation, each oracle runs a context bootstrapping protocol. The oracle reviews its assigned domain research ledgers from prior analysis phases:

*   **Phase 1 Ledgers**: Code audits logging function signatures, class definitions, and data structures.
*   **Phase 2 Flowcharts**: State machine diagrams detailing execution flow.
*   **Phase 3 Synthesis**: Cross-subsystem dependency graphs.

### Artifact Generation
After pulling context, oracles write dedicated markdown artifacts for their tasks to `[PROJECT_ROOT]/.oracle_artifacts/YYYY-MM-DD_<task_name>.md`. This practice preserves architectural decisions and edge-case evaluations across independent sessions.

---

## 4. System Directives and Oracle Instructions

### 4.1 Core Operating Guidelines (`~/.gemini/antigravity/GEMINI.md`)

```markdown
# SYSTEM KERNEL: OPERATIONAL GUIDELINES

You are the Primary Engineering Agent of MACCREv2 / EXO_GANS. Your objective is to write high-performance Python code that adheres to the established CI/CD pipeline and local environment constraints.

## I. ENVIRONMENT EXECUTION
You operate in an environment managed by the `omni` CI/CD tool.
- Execution Prefix: You must use omni for testing, linting, and execution. Bare Python invocation is prohibited.
- `omni run <path>`: Standard launcher.
- `omni qa [path]`: Runs Ruff and Pyright quality checks.
- `omni build [path]`: Purges cache and compiles via PyInstaller.

## II. AI INVOCATION LOOP
Separate generation from extraction:
- Generators: Standard API calls using temperature=1.0.
- Extractors: Force temperature=0.1 and pass a strict Pydantic BaseModel to response_schema.
- SDK Constraint: Avoid the official google-genai SDK. HTTP operations should flow through the custom REST Client using standard library urllib for edge compatibility.

## III. DATA ROUTING
- Ingestion logic reads from `01_Raw_Source` and `02_Dynamic_Context`.
- Output generation writes to `04_Code_Artifacts` and `05_Rendered_Media`.
- Cognitive audits route to `03_Agent_Ledgers` or the unified SQLite matrix.

## IV. PATH RESOLUTION
Avoid hardcoded absolute paths. Filesystem paths should derive at runtime from `get_maccre_root()`.
```

### 4.2 Representative Oracle Instructions

#### 1. Net & Client Oracle (`[PROJECT_ROOT]/.agent/skills/Specialists/NetAndClient_Oracle/SKILL.md`)
```markdown
---
name: NetAndClient_Oracle
description: Specialist for REST API Clients, Model Monitoring, Capability Classification, and OOXML Engine.
---

# ROLE: Net & Client Specialist
As the Net & Client Specialist for MACCREv2, your logic is derived from the overarching system guidelines. Your primary domain encompasses:
- Pure Python standard library Generative Language REST APIs.
- Hardware probing and model capability monitoring.
- Multi-tier inference routing.

# STARTUP PROTOCOL
Refresh your context from your assigned domain ledgers:
1. [PROJECT_ROOT]/Analysis/Wave1/01_net_subsystem_ledger.md
2. [PROJECT_ROOT]/Analysis/Wave2/flowchart_01_net_client.md
3. [PROJECT_ROOT]/.agent/skills/Specialists/NetAndClient_Oracle/task_ledger.md

# OPERATIONAL CONSTRAINTS
1. Execution Strictures: Direct Python execution is prohibited. All runtime and QA operations must route through the `omni` prefix.
2. Library Usage: Zero dependency on external SDKs for HTTP requests. Use standard library `urllib`.
3. Memory Sanitization: API key buffers must be cleared post-call using `ctypes.memset`.
4. Artifact Logging: After completing a task, write an artifact to `.oracle_artifacts/` and update `task_ledger.md`.
```

*(Note: The remaining four Oracles follow identical structured formatting, referencing their specific `[PROJECT_ROOT]` artifact paths and domain-specific operations.)*

---

## 5. Continuous Memory: The Task Ledger

A common friction point in autonomous swarms is the loss of context between agent sessions. To address this, each oracle directory maintains a localized, append-only history file at `[PROJECT_ROOT]/.agent/skills/Specialists/<Oracle_Name>/task_ledger.md`.

```text
┌──────────────────────────────────────────────────────────────────────────┐
│                         TASK LEDGER LIFECYCLE                            │
├──────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│   1. Oracle Spawned      ──► Reads task_ledger.md (Restores context)     │
│                                    │                                     │
│   2. Task Execution      ──► Audits codebase / runs tests                │
│                                    │                                     │
│   3. Documentation       ──► Writes artifact to `.oracle_artifacts/`     │
│                                    │                                     │
│   4. Ledger Update       ──► Appends summary bullet to `task_ledger.md`  │
│                                    │                                     │
│   5. Future Invocation   ──► Next instance reads updated ledger          │
│                                                                          │
└──────────────────────────────────────────────────────────────────────────┘
```

**Operational Benefits:**
*   **Historical traceability:** Logs dates, signature changes, and structural refactors sequentially.
*   **Context persistence:** When an oracle is spun up after a period of dormancy, the ledger prevents redundant work and context decay.
*   **Audit linkage:** Ledger entries point directly to full reports in `.oracle_artifacts/`, maintaining a clean paper trail.

---

## 6. Root-Level QA and the Problem of Success-Siloing

The final structural shift in the CI/CD pipeline addresses a vulnerability in how quality assurance gates (`omni qa`) are scoped.

During iterative development, running checks on isolated files saves time. However, in interconnected architectures, single-file checks create **success-siloing**:
1. **Hidden Type Errors**: A return tuple updated in `flow_engine.py` might pass an isolated check but break downstream unpacking in `swarm_worker.py`.
2. **Dangling Imports**: Removing a helper function can leave orphan import statements in unchecked consumer files.

To ensure systemic type safety, operations must target the entire workspace. Targeting specific files or directories with `omni qa` is no longer permitted. The entire system must validate cleanly (`omni qa .`) to guarantee cross-module integrity.

---

## 7. Conclusion

The transition from standard global prompts to the specialized five-oracle swarm represents a significant operational maturation. By isolating complex oversight into targeted sub-agent domains, we have reduced cognitive load and improved structural governance. Coupled with continuous memory ledgers and root-level QA requirements, this architecture provides a highly stable, edge-native foundation for MACCREv2 development.