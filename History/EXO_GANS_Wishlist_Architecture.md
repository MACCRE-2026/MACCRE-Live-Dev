# EXO_GANS: Competitive Landscape, Architecture Analysis & Feature Wishlist
## MACCREv2 vs LangGraph, CrewAI, AutoGen, Haystack, Agno & MAF

> Analysis Date: 2026-05-31 | Stars current as of May 2026
> EXO_GANS codebase measured: 161 Python files · 30,721 net code lines

---

## PART 1 — Full Competitive Landscape (7 Frameworks)

| Framework | Stars | Architecture | Mid-Run Topology | Time Travel | DB Fork | Checkpoint Re-run | RAG |
|---|---|---|---|---|---|---|---|
| **LangGraph** | ~33,400 | Directed cyclic graph | ⚠️ Conditional edges (pre-compiled) | ✅ Native | ✅ Native | ✅ Native | Ecosystem via LangChain |
| **CrewAI** | ~52,500 | Role-based Crews + event Flows | ❌ Static per kickoff | ⚠️ Flow-level UUID fork | ⚠️ Less precise | ✅ Task-level SQLite | Knowledge class, agent-level |
| **AutoGen / AG2** | ~58,000 | Actor model (async message-passing) | ⚠️ Emergent swarm routing | ⚠️ Indirect (session replay) | ❌ Manual | ✅ Manual save_state() | Tool-calling only |
| **Microsoft MAF** | ~28,000 | Graph + actor (SK + AutoGen merged) | ⚠️ Limited | ✅ Superstep CheckpointManager | ⚠️ Limited | ✅ CheckpointManager | Plugin-based |
| **Haystack** | ~25,400 | Composable serializable DAG | ❌ Static at runtime | ✅ Snapshot-based resume | ❌ Manual copy | ✅ Snapshot resume | **🥇 BEST IN TIER** |
| **Agno** | ~36,000 | Pythonic Agent class + Workflows | ⚠️ Limited | ❌ Not native | ❌ Not native | ⚠️ Session continuity | Agentic RAG, Knowledge class |
| **OpenAI Agents SDK** | ~19,100 | Sequential handoff | ❌ Static | ❌ Not supported | ❌ Not supported | ❌ Not supported | Tool-calling only |
| **EXO_GANS** | — | Queue-unrolled DAG (sovereign) | ⚠️ **Tweak** (see Part 3) | ⚠️ **Tweak** (see Part 3) | ⚠️ **Tweak** (see Part 3) | ⚠️ **Tweak** (see Part 3) | Native FTS5+sqlite-vec |

> [!IMPORTANT]
> EXO_GANS is the only framework with native FinOps cost logging, RBAC thought capture,
> cross-project memory federation, and a no-code workbook UI. These don't exist in any competitor.

---

## Ranking by Checkpoint/Replay Sophistication

1. 🥇 **LangGraph** — Immutable checkpoint tree, full time-travel, multiple backend savers
2. 🥈 **Microsoft MAF** — Superstep CheckpointManager, approaching LangGraph parity
3. 🥉 **Haystack** — Snapshot JSON resume, solid but pipeline-scoped not agent-scoped
4. **CrewAI** — Task-level SQLite, Flow-state fork, adequate for sequential workflows
5. **AutoGen/AG2** — Manual save/load, debugging via conversation log replay
6. **Agno** — Session DB continuity only, no versioned checkpoint tree
7. **OpenAI Agents SDK** — None

---

## Ranking by RAG Pipeline Capability

1. 🥇 **Haystack** — Built for this. Native document stores, re-rankers, hybrid search, YAML-serializable
2. 🥈 **Agno** — Agentic RAG first-class, Knowledge class, dynamic retrieval
3. 🥉 **CrewAI** — Knowledge class + pluggable vector stores (Chroma, Pinecone, Qdrant, Weaviate)
4. **LangGraph** — Framework-agnostic via LangChain ecosystem (powerful but not native)
5. **EXO_GANS** — Native sqlite-vec + FTS5 + hash dedup + cross-project federation (sovereign, but no PDF/DOCX loaders)
6. **AutoGen/AG2** — Tool-calling pattern only
7. **OpenAI Agents SDK** — Tool-calling only

---

## PART 2 — Architecture Philosophy Comparison

### EXO_GANS vs LangGraph: Same Computation Graph, Different State Model

LangGraph models everything as a cyclic directed graph with a shared typed state object.
State reducers accumulate values across node visits: `Annotated[list, add]`.

EXO_GANS models the same computation as an **unrolled DAG** — a cyclic intent
(loop until done, retry on failure) is represented as repeated queue insertions with
`loop_iteration_count`. The `UNIQUE(job_id, current_node)` constraint is the loop guard.

These two models are **computationally equivalent** for all finite loops.
The key difference: LangGraph's state object is in memory and checkpointed externally.
EXO_GANS's state IS the database row — the queue is the state machine.

**This is EXO_GANS's core superpower for time-travel:**
> Every node boundary is a natural, durable checkpoint with zero additional code.
> A "checkpoint" is just `shutil.copy2(swarm_queue.db, checkpoint.db)`.
> LangGraph built ~800 LOC of checkpointer abstractions to achieve the same thing.

---

## PART 3 — Feature-by-Feature: Compatible, Tweak, or Incompatible

### ✅ COMPATIBLE — No Rearchitecting Required

| Feature | What Exists Today | Why it Works |
|---|---|---|
| **Node failure preservation** | `next_node_failure` routes with `payload_path` intact | Payload file = serialized state. Already preserved on every hop. |
| **Re-run from any prior node** | `broker.inject_task(job_id, payload_path, node)` | Any historical ledger file can be injected as a new task payload |
| **Rollback to checkpoint** | `LocalMessageBroker(db_path=fork_path)` | Constructor already accepts custom db path |
| **Database forking** | `shutil.copy2(swarm_queue.db, fork.db)` + above | Trivial. Already architected. |
| **Per-run artifact isolation** | `04_Code_Artifacts/{job_id}/` scoping | Already exists. Extend same pattern to DB snapshots. |
| **Human breakpoint (HITL)** | `MANUAL` node + `interrupt_queue` + hot-mic | Already implemented. Needs Nexus CLI wrapper. |
| **Multi-agent synthesis** | Fan-in via `wait_for` columns + `SYNTHESIZE` node | Already exists for parallel branches. |
| **Topology auto-promotion** | `promote_topology_to_library()` on STOP | Already wired in swarm_worker.py line 556 |

---

### ⚠️ TWEAK — Needs ~30–200 LOC, No New Dependencies

#### Tweak 1: Checkpoint-on-Failure + Rollback (~60 LOC in local_broker.py)

```python
import shutil, time
from maccre_core.utils.path_resolver import get_datacenter_path

def checkpoint_session(self, job_id: str) -> str:
    """Snapshot the queue DB at this instant. Returns checkpoint_id."""
    cid = f"{job_id}_{int(time.time())}"
    dst = get_datacenter_path(f"checkpoints/{cid}.db")
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(self.db_path, dst)
    return cid

def rollback_to(self, checkpoint_id: str, resume_node: str, payload_path: str) -> str:
    """Fork from a prior checkpoint, inject resume_node. Returns new fork job_id."""
    src = get_datacenter_path(f"checkpoints/{checkpoint_id}.db")
    fork_id = f"{checkpoint_id}_fork_{int(time.time())}"
    fork_db = get_datacenter_path(f"checkpoints/{fork_id}.db")
    shutil.copy2(src, fork_db)
    fork_broker = LocalMessageBroker(db_path=str(fork_db))
    fork_broker.inject_task(fork_id, payload_path, resume_node)
    return fork_id
```

**Hook**: `swarm_worker.py` line 568 (except block) — call `checkpoint_session()` BEFORE
routing to `next_node_failure`. Preserves exact queue state at point of failure.

---

#### Tweak 2: Live Topology Node Patch (~40 LOC in topology_engine.py + 30 LOC new tool)

```python
# topology_engine.py
def reload(self) -> None:
    """Hot-reload topology from disk. Call after any live patch."""
    self._nodes = self._parse_topology()

def patch_node(self, node_id: str, field: str, value: str) -> None:
    """Rewrite a single cell in topology.csv and hot-reload."""
    import pandas as pd  # noqa: PLC0415
    df = pd.read_csv(self._topology_path)
    df.loc[df["Node_ID"] == node_id, field] = value
    df.to_csv(self._topology_path, index=False)
    self.reload()
```

```python
# agent_tools.py — new Nexus tool
def rewrite_topology_node(node_id: str, field: str, value: str) -> str:
    """[NEXUS TOOL] Patch a running topology node's config live.
    Example: rewrite_topology_node('REVIEWER', 'Model', 'gemini-2.5-pro')
    """
    from maccre_core.orchestration.topology_engine import TopologyEngine  # noqa
    TopologyEngine().patch_node(node_id, field, value)
    return f"[TOPOLOGY PATCHED] {node_id}.{field} = {value}"
```

**Effect**: Nexus can now change any node's model, temperature, instruction, or next_node
while a job is running. Changes take effect on the NEXT time that node is fetched.

---

#### Tweak 3: Full Datacenter Fork (~40 LOC in admin_tools.py)

```python
def fork_datacenter(source_project: str, fork_label: str) -> str:
    """Clone an entire project's datacenter state into a new isolated fork.
    Forks: swarm_queue.db + all 5-tier file directories + telemetry DBs.
    """
    import shutil
    from maccre_core.utils.path_resolver import get_datacenter_path
    src = get_datacenter_path("", project=source_project)
    dst = get_datacenter_path("", project=f"{source_project}_{fork_label}")
    shutil.copytree(src, dst)
    return f"[FORK CREATED] {source_project} -> {source_project}_{fork_label}"
```

---

#### Tweak 4: Fork Synthesis / Pruning Critic (~200 LOC, new fork_synthesizer.py)

```
fork_synthesizer.py
├── collect_run_ledgers(job_id) -> dict[node_id -> ledger_text]
├── diff_runs(job_a_id, job_b_id) -> RunDiff(common, only_a, only_b, changed_nodes)
├── critic_score_node(node, ledger_a, ledger_b) -> ScoredNode  ← Diamond Loop, temp=0.1
├── prune_dominated_forks(diffs) -> {job_id -> [nodes to keep]}
└── synthesize_to_master(kept_nodes_map) -> merged_ledger_tree
```

This is a pure Diamond Loop application: two ledgers in, Pydantic schema enforced critic
scores each node's output, prunes the dominated fork, synthesizes a canonical master.
Uses `definitions.db` `topology_library` as the institutional memory of which topologies
produced the best outputs over time.

---

#### Tweak 5: History Viewer CLI (~50 LOC in maccre.py)

```
python maccre.py history list <job_id>     # Show all nodes, statuses, timestamps
python maccre.py history rollback <job_id> <node_id>  # Inject rollback task
python maccre.py history fork <job_id> <checkpoint_id>  # Fork from checkpoint
```

---

### ❌ GENUINELY INCOMPATIBLE — Would Require Rearchitecting

| Feature | Why Not Compatible | Notes |
|---|---|---|
| **True cyclic shared mutable state** | `UNIQUE(job_id, current_node)` prevents it by design. The constraint is the correctness proof, not a limitation. LangGraph's `Annotated[list, add]` reducers accumulate across cycles in-memory — EXO_GANS accumulates in ledger files instead. | Functionally equivalent for text pipelines |
| **Token-by-token streaming within a node** | `GeminiClient` is batch. Mid-generation resume requires a live token stream. Without streaming, a "pause" can only happen at the next node boundary. | Requires GeminiClient streaming mode first |
| **Frozen in-memory state replay** | LangGraph replays exact in-memory state objects. EXO_GANS replays ledger files (re-executes from text). For deterministic agents, functionally equivalent. For non-deterministic agents, re-execution produces a different result (which may actually be desirable for iterative refinement). | Design choice, not a defect |

> [!NOTE]
> The "incompatible" features are incompatible with LangGraph's implementation, not with
> EXO_GANS's goals. Re-executing from a ledger file is often BETTER than replaying frozen
> state — it lets the model improve on prior output, not just repeat it.

---

## PART 4 — Local Databasing & Ingestion Comparison

### EXO_GANS Database Stack (7 SQLite databases, zero cloud dependencies)

| DB | Engine | Schema Highlights |
|---|---|---|
| `swarm_queue.db` | SQLite WAL | `task_queue(job_id, current_node, payload_path, lock_status, loop_iteration_count)` — UNIQUE(job_id, current_node) |
| `system_logs.db` | SQLite WAL | FinOps: `(cost, model_id, input_tokens, output_tokens)` per inference call |
| `user_interactions.db` | SQLite WAL | Every Architect input + context tags |
| `terminal_logs.db` | SQLite WAL | venv subprocess command + output |
| `thoughts.db` | SQLite WAL | Raw `<scratchpad>` extracts — RBAC restricted |
| `definitions.db` | SQLite WAL | `topology_library` — proven topologies promoted on STOP |
| `memory.db` | SQLite FTS5 + sqlite-vec | Full-text + semantic vector search, cross-project federation |

### Framework Ingestion Comparison

| Capability | LangGraph | CrewAI | Haystack | Agno | **EXO_GANS** |
|---|---|---|---|---|---|
| Vector store | External | External | Native 8+ stores | Native 5+ stores | ✅ Native sqlite-vec |
| Full-text search | External | External | External (Elasticsearch) | External | ✅ Native FTS5 |
| Hash deduplication | ❌ | ❌ | ❌ | ❌ | ✅ Native |
| Cross-project memory | ❌ | ❌ | ❌ | ❌ | ✅ `query_foreign_memory()` |
| PDF/DOCX loaders | ✅ (50+ via LangChain) | ✅ Basic | ✅ Native 30+ | ✅ Native | ❌ **GAP** |
| FinOps/cost tracking | LangSmith (SaaS) | ❌ | ❌ | ❌ | ✅ Native |
| Thought capture | ❌ | ❌ | ❌ | ❌ | ✅ `thoughts.db` RBAC |
| Offline/sovereign | ❌ | ✅ | ✅ | ✅ | ✅ Fully sovereign |
| Zero-dependency | ❌ | ❌ | ❌ | ❌ | ✅ Pure urllib + SQLite |

> [!TIP]
> The biggest EXO_GANS ingestion gap relative to competitors is **document loaders** —
> no native PDF/DOCX/HTML parsing. Everything else is equal or superior.
> Adding `pypdf` + `python-docx` as optional deps fixes this in ~60 LOC per loader.

---

## PART 5 — The "Sovereign Time-Travel" Wishlist

Ranked by **Impact × Feasibility**. Items 1–7 form a coherent release with no new deps.

| # | Feature | Impact | Feasibility | ~LOC | File Hook |
|---|---|---|---|---|---|
| **1** | Checkpoint-on-failure + rollback | 🔥🔥🔥 | ✅ Trivial | ~60 | `local_broker.py` |
| **2** | Live topology node patch | 🔥🔥🔥 | ✅ Easy | ~40 | `topology_engine.py` |
| **3** | `rewrite_topology_node` Nexus tool | 🔥🔥🔥 | ✅ Easy | ~30 | `agent_tools.py` |
| **4** | Database fork (per-run isolation) | 🔥🔥🔥 | ✅ Trivial | ~30 | `local_broker.py` |
| **5** | Full datacenter fork (5-tier clone) | 🔥🔥🔥 | ✅ Easy | ~40 | `admin_tools.py` |
| **6** | Fork synthesis / pruning critic | 🔥🔥🔥 | ⚠️ Medium | ~200 | new `fork_synthesizer.py` |
| **7** | History CLI (`history list/rollback/fork`) | 🔥🔥 | ✅ Easy | ~50 | `maccre.py` |
| **8** | GeminiClient streaming mode | 🔥🔥🔥 | ⚠️ Medium | ~80 | `gemini_client.py` |
| **9** | Mid-node pause (streaming prerequisite) | 🔥🔥 | ⚠️ Medium | ~100 | `swarm_worker.py` |
| **10** | PDF / DOCX document loaders | 🔥🔥 | ✅ Easy | ~60 ea | `key_ingestor.py` |

### "Sovereign Time-Travel" Release (Items 1–7) — Total: ~450 LOC
### No new dependencies. No new infrastructure. Pure SQLite + filesystem.

---

## PART 6 — The Core Structural Insight

LangGraph uses abstract checkpointer class hierarchies (~800 LOC across
`langgraph-checkpoint-sqlite`, `langgraph-checkpoint-postgres`, `langgraph-checkpoint-redis`)
to achieve what is one line in EXO_GANS:

```python
shutil.copy2(self.db_path, checkpoint_path)
```

The queue-based architecture is NOT a limitation relative to cyclic graph frameworks.
For text-output pipeline use cases (like EXO-GANS publication), it is superior:

- **Every node boundary = automatic durable checkpoint** (no additional code)
- **Forking = copy2** (one line, no abstraction layer)
- **Rollback = inject_task with historical payload_path** (already works)
- **Iterative refinement = re-execution from ledger** (produces better output than frozen replay)
- **Full history** already exists in `03_Agent_Ledgers/{job_id}/` with per-node, per-row files

The only thing LangGraph does that EXO_GANS can't is freeze and replay exact in-memory
Python objects. EXO_GANS replays from serialized text — which for an LLM pipeline
is the correct semantic level to replay from anyway.

---

## Appendix: Framework Architecture Patterns

```
LangGraph   → State machine   (StateGraph → compiled graph → superstep execution)
CrewAI      → Team model      (Crew.kickoff() → role-driven sequential/hierarchical)
AutoGen/AG2 → Actor model     (async message-passing between stateful actor agents)
Haystack    → Pipeline model  (composable typed components, YAML-serializable DAG)
Agno        → OOP model       (Agent class + Workflow → FastAPI runtime + playground UI)
OpenAI SDK  → Handoff model   (agent passes control to next via tool call)
EXO_GANS   → Queue model      (SQLite task queue as state machine, filesystem as ledger)
```

Every framework except EXO_GANS externalises its persistence layer.
EXO_GANS IS the persistence layer — state is the database, not stored IN a database.
