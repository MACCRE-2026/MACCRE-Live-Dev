# CTRL_SCATTER Agent Slotting & Topology Visualization — Implementation Plan v3 (FINAL)

## Scope Separation

| Scope | What | Why Now / Why Later |
|-------|------|---------------------|
| **NOW (Phase 4.75.7)** | CTRL_SCATTER agent slotting modal + flow engine auto-wrap + default-expanded topology + telemetry vector schema groundwork | Core functionality — scatter can't work without agent slotting |
| **Phase 6** | Flow Stage editor, animated wires, center-justified tree, node swap/replace, ThreadPoolExecutor parallelism, WAL sharding at scale |
| **Phase 7** | Telemetric Memory Simulation, time-travel replay, agent perspective simulation, branch isolation analysis |

---

## Part A — NOW: Phase 4.75.7

### A1. CTRL_SCATTER Agent Slotting Modal

#### [MODIFY] [nexus_plex.py](file:///B:/EXO_GANS/maccre_tui/nexus_plex.py)

**Replace** the CTRL_SCATTER section in `_compose_ctrl_fields` (L2176-2189) with a full agent slotting interface.

**New layout:**

```
┌─ Control Node Config: CTRL_SCATTER ─────────────────────────┐
│ Tether ID: [____________]                                    │
│ Scatter Mode: [Full Copy ▼]                                  │
│                                                              │
│ ── Scatter Agent Slots (0/8) ────────────────────────────    │
│ [Select Agent to add... ▼]  [+ Add Agent]                    │
│                                                              │
│ 1. TopperShepherd  [⚙ Overrides] [✕ Remove]                 │
│ 2. TopperAngry     [⚙ Overrides] [✕ Remove]                 │
│ 3. TopperChill     [⚙ Overrides] [✕ Remove]                 │
└──────────────────────────────────────────────────────────────┘
```

**New class-level state in NodeConfigModal:**

```python
self._scatter_agents: list[str] = list(node_config.get("scatter_agents", []))
self._scatter_agent_overrides: dict[str, dict] = dict(node_config.get("scatter_agent_overrides", {}))
```

**Agent selector** — dropdown populated from full project roster (all agents in `agent_library.db`), same data source as `#agent-select` in FlowExecutionPanel.

**Add Agent button** — appends selected agent to `_scatter_agents`, dynamically mounts a new `Horizontal` row with the agent name + Overrides + Remove buttons. Max agent count governed by `MAX_SCATTER_AGENTS = 8` (see concurrency analysis below).

**⚙ Overrides button** — opens `AgentProfileOverridesModal` (existing class at L1679), stores result in `_scatter_agent_overrides[agent_name]`. Identical UX to the existing MacroNode agent overrides in the user's first screenshot.

**✕ Remove button** — removes agent from `_scatter_agents` and unmounts its row widget.

**Save handler** (`_collect_ctrl_config` CTRL_SCATTER branch):

```python
cfg["scatter_agents"] = list(self._scatter_agents)
cfg["scatter_agent_overrides"] = dict(self._scatter_agent_overrides)
cfg["scatter_targets"] = list(self._scatter_agents)  # backwards compat
```

---

### A2. Flow Engine — CTRL_ Auto-Wrap

#### [MODIFY] [flow_engine.py](file:///B:/EXO_GANS/maccre_core/orchestration/flow_engine.py)

**Problem:** `_get_macronode("CTRL_SCATTER")` fails with `KeyError` — CTRL_ nodes aren't registered as MacroNodes, so they can't execute in the linear flow at all.

**Fix:** Add a CTRL_ auto-wrap branch to `_get_macronode()` between the agent roster fallback (L165) and the `raise KeyError` (L168).

**Two paths:**

**Path 1 — CTRL_SCATTER with slotted agents** (`step_config.get("scatter_agents")`):
Synthesizes a complete scatter→agents→merge topology:

```python
# Topology structure:
# CTRL_SCATTER → Agent_A, Agent_B, Agent_C (parallel tasks in queue)
#                    ↓          ↓         ↓
#                        CTRL_MERGE (Wait_For: all agents)

topo_rows = [
    # Scatter node — next_node = comma-separated agent list
    {"Node_ID": "CTRL_SCATTER", "Agent_Name": "SYSTEM", "Next_Node": "Agent_A,Agent_B,Agent_C", ...},
    # Per-agent rows with profile overrides applied
    {"Node_ID": "Agent_A", "Agent_Name": "Agent_A", "Next_Node": "CTRL_MERGE", ...},
    {"Node_ID": "Agent_B", "Agent_Name": "Agent_B", "Next_Node": "CTRL_MERGE", ...},
    {"Node_ID": "Agent_C", "Agent_Name": "Agent_C", "Next_Node": "CTRL_MERGE", ...},
    # Merge node — waits for all agents
    {"Node_ID": "CTRL_MERGE", "Agent_Name": "SYSTEM", "Next_Node": "END", "Wait_For": "Agent_A|Agent_B|Agent_C"},
]
```

**Path 2 — Generic CTRL_ node** (no agents):
Single-node passthrough topology (CTRL_PAUSE, CTRL_GATE, etc.):

```python
{"Node_ID": name, "Agent_Name": "SYSTEM", "Next_Node": "END", ...}
```

**Signature change:** `_get_macronode(self, name, step_config=None)` — pass `step.config` from the call site at L661.

**Preflight bypass:** Update `preflight_check()` to skip macronode existence check for `CTRL_*` names.

---

### A3. Topology Visualizer — Default Expanded with Collapse Toggle

#### [MODIFY] [topology_visualizer.py](file:///B:/EXO_GANS/maccre_tui/widgets/topology_visualizer.py)

**Default to expanded, collapsible on click:**

1. In `_rebuild_tree()` (L364): After building the tree, `expand_all()` is already called (L386 ✅). No change needed.
2. In `_add_subtree()` (L388): Change the MacroNode inner expansion guard (L406) from `self._expand_states.get(node_id, False)` to `self._expand_states.get(node_id, True)` — **default True** instead of False.
3. **Keep** the `toggle_expansion()` method and the `[+]/[-]` indicator — but `[-]` is now the default state (expanded).
4. When collapsed, show a condensed single-line summary: `[+] CTRL_SCATTER ⟩ 3 agents ⟩ CTRL_MERGE` — acting as a compact root that, when clicked, re-expands to full tree.

---

### A4. Scatter Topology Visualization

#### [MODIFY] [nexus_plex.py](file:///B:/EXO_GANS/maccre_tui/nexus_plex.py)

When the flow includes a CTRL_SCATTER step, the topology data fed to `TopologyVisualizer.load_topology()` must include the synthesized scatter→agents→merge structure. Update the topology loading section to emit scatter tree structure:

```python
for i, step in enumerate(self.active_flow_steps):
    step_config = getattr(step, "config", {})
    if step.macronode_name.startswith("CTRL_SCATTER") and step_config.get("scatter_agents"):
        agents = step_config["scatter_agents"]
        topo_steps.append({"Node_ID": step.macronode_name, "Next_Node": ",".join(agents), "type": "macronode"})
        for agent in agents:
            topo_steps.append({"Node_ID": agent, "Next_Node": "CTRL_MERGE"})
        topo_steps.append({"Node_ID": "CTRL_MERGE", "Next_Node": next_name, "Wait_For": ",".join(agents)})
    else:
        topo_steps.append({"Node_ID": step.macronode_name, "Next_Node": next_name})
```

---

### A5. Telemetry Vector Schema Groundwork

#### [MODIFY] [local_broker.py](file:///B:/EXO_GANS/maccre_core/orchestration/local_broker.py)

Add a `flow_vector` column to `task_queue` table to track the full execution path ancestry for each task. This is the minimal schema change that enables all future Phase 6/7 capabilities:

```sql
ALTER TABLE task_queue ADD COLUMN flow_vector TEXT DEFAULT '';
-- Format: "SCATTER_A>Agent_B>MERGE_A" — breadcrumb trail of node traversal
```

**`flow_vector` is a colon-delimited path string** recording the complete lineage of how a task reached its current node. Each time a task is routed to a next_node, the current node is appended:

```
"CTRL_SCATTER_S0:TopperShepherd_S0"  ← this task was scattered from CTRL_SCATTER to TopperShepherd
"CTRL_SCATTER_S0:TopperAngry_S0"     ← this task was scattered to TopperAngry
```

> [!NOTE]
> This column is write-only in Phase 4.75.7 — we populate it during routing but don't read it yet. It becomes the foundational index for:
> - Phase 6: WAL sharding (group writes by flow_vector prefix)
> - Phase 7: Time-travel replay (reconstruct any execution branch from vectors)
> - Phase 7: Agent perspective simulation (filter vectors containing a specific agent)

**Swarm worker update** — when routing a task to its next_node, append the current node to `flow_vector`:

```python
new_vector = f"{existing_vector}:{current_node}" if existing_vector else current_node
```

---

## Part B — Phase 6 Deferrals

### B1. Flow Stage Editor (§6.8)

The concept of **Flow Stages** — horizontal lines where nodes on the same stage execute in parallel and the flow waits for all to complete before advancing.

### B2. Animated Flow Wires (§6.9)

Marching-ants dashed lines with color coding by flow type. Custom Rich Renderable replacing Tree connectors.

### B3. Center-Justified Flow Tree (§6.10)

Custom canvas widget replacing Textual Tree with center-justified DAG layout.

### B4. Node Swap/Replace (§6.11)

Select-and-swap with undo/redo topology version stack.

### B5. Parallel Execution Threading (§6.12)

ThreadPoolExecutor in swarm_worker with `max_workers=MAX_SCATTER_AGENTS`.

### B6. WAL Sharding by Flow Line (§6.13 — NEW)

Scale SQLite write throughput by sharding the `task_queue` and telemetry tables across per-flow-line database files:

```
swarm_queue.db                 ← main orchestration DB (job_sessions, interrupt_queue)
swarm_queue_fl_scatter_A.db    ← flow line shard for scatter branch A
swarm_queue_fl_scatter_B.db    ← flow line shard for scatter branch B
```

- Each shard is its own WAL-mode SQLite file — **eliminating write contention** between parallel flow lines
- The broker routes reads/writes by `flow_line_id` → shard DB path
- A `shard_manifest` table in the main DB tracks active shards and their flow_line_id mapping
- Shards are merged back into the main DB on flow completion (or left isolated for branch analysis)
- `flow_vector` column (planted in A5) becomes the partition key for shard assignment

**Telemetry scaling metadata:**

```json
{
  "shard_id": "fl_scatter_A",
  "flow_vector_prefix": "CTRL_SCATTER_S0:TopperShepherd_S0",
  "created_at": "2026-07-20T20:00:00Z",
  "task_count": 3,
  "write_ops": 15,
  "merge_status": "pending"
}
```

---

## Part C — Phase 7: Telemetric Memory Simulation (NEW)

> [!IMPORTANT]
> This is visionary-tier architecture. The `flow_vector` schema planted in A5 is the seed.

### C1. Time-Travel Replay (§7.X)

Given a completed session's `flow_vector` data + ledger artifacts, reconstruct the exact execution timeline of any branch:

- **Branch isolation:** Filter `flow_vector` by prefix to extract a single scatter branch's complete execution history
- **Timeline reconstruction:** Order by `created_at` timestamps to replay the exact sequence of events
- **State snapshots:** Each task row captures `payload_path` at entry and exit — providing payload state at every node boundary

### C2. Agent Perspective Simulation (§7.X)

Follow a specific agent across all branches it appeared in:

- **Agent trace:** Filter `flow_vector` entries containing agent name → get every node that agent touched, in order
- **Cross-branch correlation:** If the same agent appears in multiple scatter branches, correlate its inputs/outputs across branches
- **"Fly on the wall" mode:** Feed an observer agent the complete telemetry trace of a target agent's journey — the observer absorbs the decision context, payload evolution, and outcome without having been present

### C3. Counterfactual Simulation (§7.X)

Send a **different** agent through a completed agent's exact path:

- Replay the exact same payload sequence and node routing that Agent_A experienced
- But route it through Agent_B (different model, different system prompt, different tools)
- Compare outputs at each node to study how different agent configurations would have handled the same flow
- Uses `flow_vector` to reconstruct the exact routing path, and ledger artifacts to replay exact payloads

> [!NOTE]
> All three C-tier capabilities require zero new schema beyond the `flow_vector` column planted in A5 + the existing ledger file artifacts. The data is already being generated — we just need the replay engine (Phase 7).

---

## Concurrency Analysis: MAX_SCATTER_AGENTS (Corrected)

### API Reality Check

Per [ReFactor_Redux-1a933d9.txt](file:///B:/EXO_GANS/ReFactor_Redux-1a933d9.txt): There is **no free tier**. The Sovereign Edge system runs on paid Gemini API credentials with current-generation models (`gemini-3.1-pro-preview`, `gemini-3.5-flash`, `gemini-omni-flash-preview`).

Paid-tier rate limits for Gemini 3.x:
- **RPM:** ~1000-2000 RPM per model (varies by plan)
- **TPM:** ~4M tokens/min for Flash, ~2M for Pro
- **Concurrent requests:** No hard limit — rate-limited by RPM/TPM

### Bottleneck Analysis (Corrected)

| Layer | Constraint | Reality |
|-------|-----------|---------|
| **Gemini API** | ~1000-2000 RPM paid tier | 8 agents × ~3 calls each = 24 RPM — **well within limits** |
| **SQLite WAL** | 1 writer at a time, `busy_timeout=5000ms` | Current sequential execution means no contention. Phase 6 threading introduces contention → WAL sharding (§6.13) scales this |
| **Python GIL** | CPU-bound work serializes | API calls are I/O-bound (urllib). JSON parsing is fast. Not a practical bottleneck |
| **Memory** | ~2-5 MB per agent context | 8 agents = ~40 MB overhead (negligible on modern hardware) |
| **Topology width** | Visual manageability in TUI | 8 nodes side-by-side in a center-justified tree (Phase 6) fits in ~120 columns |

### Recommendation (Revised)

> [!IMPORTANT]
> **MAX_SCATTER_AGENTS = 8** (configurable, hard cap 12)
>
> - **8 is comfortable** for paid-tier API (24 RPM out of 1000+ available)
> - **8 is visually manageable** in the topology visualizer (even the current Tree widget handles 8 children cleanly)
> - **12 hard cap** provides headroom for power users running high-RPM plans
> - **Phase 6 WAL sharding** eliminates the SQLite bottleneck for >5 concurrent writers
> - Defined as `MAX_SCATTER_AGENTS` constant in a shared config module (not hardcoded)

---

## Files Changed Summary

### NOW (Phase 4.75.7)

| File | Change |
|------|--------|
| [nexus_plex.py](file:///B:/EXO_GANS/maccre_tui/nexus_plex.py) | CTRL_SCATTER agent slotting UI in `_compose_ctrl_fields` + `_collect_ctrl_config`, scatter topology in visualizer load |
| [flow_engine.py](file:///B:/EXO_GANS/maccre_core/orchestration/flow_engine.py) | CTRL_ auto-wrap in `_get_macronode`, preflight bypass, `step_config` passthrough |
| [topology_visualizer.py](file:///B:/EXO_GANS/maccre_tui/widgets/topology_visualizer.py) | Default expanded (True), keep collapse toggle, condensed collapsed view |
| [local_broker.py](file:///B:/EXO_GANS/maccre_core/orchestration/local_broker.py) | Add `flow_vector` column to `task_queue` |
| [swarm_worker.py](file:///B:/EXO_GANS/maccre_core/orchestration/swarm_worker.py) | Populate `flow_vector` on task routing |

### Phase 6 (Deferred to Era2 Roadmap)

| Section | Feature |
|---------|---------|
| §6.8 | Flow Stage Editor |
| §6.9 | Animated Flow Wires |
| §6.10 | Center-Justified Flow Tree |
| §6.11 | Node Swap/Replace |
| §6.12 | Parallel Execution Threading |
| §6.13 | WAL Sharding by Flow Line |

### Phase 7 (Deferred to Era2 Roadmap)

| Section | Feature |
|---------|---------|
| §7.X | Time-Travel Replay — branch isolation from flow_vector |
| §7.X | Agent Perspective Simulation — cross-branch agent tracing |
| §7.X | Counterfactual Simulation — replay paths with different agents |

---

## Verification Plan

### Manual Verification
1. Add CTRL_SCATTER to flow → open modal → verify agent roster dropdown appears
2. Add 3 agents (up to 8 max) → verify rows with Overrides + Remove buttons
3. ⚙ Overrides → verify AgentProfileOverridesModal opens with correct profile
4. Save → reopen → verify persistence
5. Run flow → verify scatter topology synthesizes, agents execute, merge collects
6. Check Topology Visualizer shows expanded scatter→agents→merge tree (default expanded)
7. Click collapse toggle → verify condensed single-line view
8. Inspect `task_queue` after run → verify `flow_vector` column populated

### Automated
- `omni qa maccre_core/orchestration/flow_engine.py`
- `omni qa maccre_core/orchestration/local_broker.py`
- `omni qa maccre_core/orchestration/swarm_worker.py`
- `omni qa maccre_tui/nexus_plex.py`
- `omni qa maccre_tui/widgets/topology_visualizer.py`
