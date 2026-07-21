# CTRL_SCATTER Agent Slotting & Topology Visualization — Implementation Plan v2

## Scope Separation

| Scope | What | Why Now / Why Later |
|-------|------|---------------------|
| **NOW (Phase 4.75.7)** | CTRL_SCATTER agent slotting modal + flow engine auto-wrap + always-expanded topology | Core functionality — scatter can't work without agent slotting |
| **Phase 6** | Flow Stage editor, animated wires, parallel execution, center-justified tree, node swap/replace | Major widget rewrite + concurrency infrastructure |

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
│ ── Scatter Agent Slots ──────────────────────────────────    │
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

**Add Agent button** — appends selected agent to `_scatter_agents`, dynamically mounts a new `Horizontal` row with the agent name + Overrides + Remove buttons. Max agent count governed by config constant (`MAX_SCATTER_AGENTS = 5`, see concurrency analysis below).

**⚙ Overrides button** — opens `AgentProfileOverridesModal` (existing class at L1679), stores result in `_scatter_agent_overrides[agent_name]`. Identical UX to the existing MacroNode agent overrides.

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

### A3. Always-Expanded Topology Visualizer

#### [MODIFY] [topology_visualizer.py](file:///B:/EXO_GANS/maccre_tui/widgets/topology_visualizer.py)

Currently the tree has collapsible MacroNode nodes (`[+]/[-]` toggle, Task 37). Change to always show expanded state:

1. In `_rebuild_tree()` (L364): After building the tree, call `tree.root.expand_all()` (already done at L386 ✅)
2. In `_add_subtree()` (L388): Always render inner MacroNode topology (remove the `self._expand_states.get(node_id, False)` guard at L406)
3. Remove the `toggle_expansion` shortcut handling — nodes always show their full subtree

> [!NOTE]
> This is a minor change — the tree already auto-expands. We just remove the collapse toggle to enforce "always expanded."

---

### A4. Scatter Topology Visualization

#### [MODIFY] [nexus_plex.py](file:///B:/EXO_GANS/maccre_tui/nexus_plex.py)

When the flow starts with a CTRL_SCATTER step, the topology data fed to `TopologyVisualizer.load_topology()` must include the synthesized scatter→agents→merge structure (not just a single `CTRL_SCATTER` node). This happens naturally because `_get_macronode` now returns the full topology_rows.

**Update the topology loading section** (~L4620-4624) to pass inner topology rows for scatter steps:

```python
for i, step in enumerate(self.active_flow_steps):
    step_config = getattr(step, "config", {})
    if step.macronode_name.startswith("CTRL_SCATTER") and step_config.get("scatter_agents"):
        # Emit scatter tree structure for visualizer
        agents = step_config["scatter_agents"]
        topo_steps.append({"Node_ID": step.macronode_name, "Next_Node": ",".join(agents)})
        for agent in agents:
            topo_steps.append({"Node_ID": agent, "Next_Node": "CTRL_MERGE"})
        topo_steps.append({"Node_ID": "CTRL_MERGE", "Next_Node": next_name, "Wait_For": ",".join(agents)})
    else:
        topo_steps.append({"Node_ID": step.macronode_name, "Next_Node": next_name})
```

---

## Part B — Phase 6 Deferrals

### B1. Flow Stage Editor (§6.8)

The concept of **Flow Stages** — horizontal lines where nodes on the same stage execute in parallel and the flow waits for all to complete before advancing.

- **Data model:** Each stage is an ordered list of up to `MAX_PARALLEL` nodes. The topology is an ordered list of stages.
- **UI:** Selecting a Flow Stage highlights it. Add/remove/swap nodes within a stage. Visual reordering on add.
- **Execution:** The swarm worker processes all nodes in a stage before advancing (already works via `Wait_For` — each next-stage node waits for all current-stage nodes).

### B2. Animated Flow Wires (§6.9)

Replace Textual Tree connectors with custom-drawn wire segments:

- **Wire types:** Dashed lines for inactive flow, solid for active, color-coded by flow type (scatter=orange, normal=cyan, gate=yellow)
- **Animation:** 4-segment dashed pattern that progresses along the wire path like a progress bar — "marching ants" effect
- **Implementation:** Custom Rich `Renderable` that draws Unicode box-drawing characters with state-driven styling. Replace `Tree` widget with a custom `Canvas`-style widget that renders the DAG as a center-justified flow tree.

### B3. Center-Justified Flow Tree (§6.10)

Replace the current vertical `Tree` widget (left-aligned, indented) with a center-justified flow tree:

```
              CTRL_SCATTER
            /      |       \
    Agent_A    Agent_B    Agent_C
            \      |       /
              CTRL_MERGE
                  |
              Writer_Final
```

- Requires a custom widget (not Textual Tree) — a `Static` or `Canvas` that renders Rich Text blocks with calculated positions
- Center-justification based on the widest stage in the topology
- Responsive to pane width changes

### B4. Node Swap/Replace (§6.11)

- Select a node in the topology → highlight it
- Add another node → swap into the selected node's position
- Remove button (red ✕) on selected nodes
- Undo/redo via topology version stack

### B5. Parallel Execution Threading (§6.12)

Currently the swarm worker processes tasks **sequentially** — one `execute_cycle()` call per loop iteration (L714). For true parallel execution:

- ThreadPoolExecutor with `max_workers=MAX_SCATTER_AGENTS`
- Each scatter target runs in its own thread
- SQLite WAL mode handles concurrent reads; writes serialize via WAL journal
- Merge node polls completion via `Wait_For` check (already works)

---

## Concurrency Analysis: MAX_SCATTER_AGENTS

### Bottlenecks

| Layer | Constraint | Impact |
|-------|-----------|--------|
| **Gemini API** | ~30 RPM (free), ~1000 RPM (paid) per model | Each agent makes 1+ API call per task |
| **SQLite WAL** | Unlimited concurrent readers, **1 writer at a time** | Write serialization is the true bottleneck — each task completion writes to `task_queue`, `thoughts_telemetry`, `session_telemetry` |
| **Python GIL** | CPU-bound work serializes | API calls are I/O-bound (no GIL issue), but JSON parsing and file writes are CPU-bound |
| **Memory** | Each agent context: ~2-5 MB (prompt + payload + response) | 10 agents = ~50 MB overhead (negligible) |
| **File I/O** | Each agent writes ledger files to `03_Agent_Ledgers/` | Concurrent writes to different files = no contention |

### Recommendation

> [!IMPORTANT]
> **MAX_SCATTER_AGENTS = 5** (configurable constant)
>
> - **5 is safe** for both free and paid API tiers — even at 1 RPM per agent, 5 agents stay well within 30 RPM free-tier limits
> - **SQLite serialization** means >5 concurrent writers start queueing significantly, but since execution is currently sequential anyway, this only matters when we add threading in Phase 6
> - **For Phase 4.75.7 (now):** The limit is purely a UX guard. The worker processes tasks sequentially, so 5 vs 10 has no concurrency difference. The limit prevents the user from creating unmanageably wide topologies.
> - **For Phase 6 (threaded):** 5 threads × ~3 SQLite writes each = 15 serialized writes, completing in <1s total. Acceptable.
> - Users who need more can set `MAX_SCATTER_AGENTS` in project config. Hard cap at 10 to prevent rate limit storms.

---

## Files Changed Summary

### NOW (Phase 4.75.7)

| File | Change |
|------|--------|
| [nexus_plex.py](file:///B:/EXO_GANS/maccre_tui/nexus_plex.py) | CTRL_SCATTER agent slotting UI in `_compose_ctrl_fields` + `_collect_ctrl_config`, scatter topology in visualizer load |
| [flow_engine.py](file:///B:/EXO_GANS/maccre_core/orchestration/flow_engine.py) | CTRL_ auto-wrap in `_get_macronode`, preflight bypass, `step_config` passthrough |
| [topology_visualizer.py](file:///B:/EXO_GANS/maccre_tui/widgets/topology_visualizer.py) | Remove collapse toggle, always-expanded |

### Phase 6 (Deferred to Era2 Roadmap)

| Section | Feature |
|---------|---------|
| §6.8 | Flow Stage Editor — horizontal stages with parallel node management |
| §6.9 | Animated Flow Wires — marching-ants dashed lines with color coding |
| §6.10 | Center-Justified Flow Tree — custom widget replacing Textual Tree |
| §6.11 | Node Swap/Replace — select-and-swap with undo/redo |
| §6.12 | Parallel Execution Threading — ThreadPoolExecutor in swarm worker |

---

## Verification Plan

### Manual Verification
1. Add CTRL_SCATTER to flow → open modal → verify agent roster dropdown appears
2. Add 3 agents → verify rows with Overrides + Remove buttons
3. ⚙ Overrides → verify AgentProfileOverridesModal opens with correct profile
4. Save → reopen → verify persistence
5. Run flow → verify scatter topology synthesizes, agents execute, merge collects
6. Check Topology Visualizer shows expanded scatter→agents→merge tree

### Automated
- `omni qa maccre_core/orchestration/flow_engine.py`
- `omni qa maccre_tui/nexus_plex.py`
- `omni qa maccre_tui/widgets/topology_visualizer.py`
