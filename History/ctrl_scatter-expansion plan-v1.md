# CTRL_SCATTER Agent Slotting — Dynamic MacroNode Constructor

## Problem

CTRL_SCATTER currently treats `scatter_targets` as pre-existing **node IDs** in a topology. But the user's mental model is that CTRL_SCATTER should act as a **container** for agents — you slot agents into it, configure their overrides, and it spawns them all in parallel at execution time.

Additionally, CTRL_ nodes can't even execute in the linear flow right now — `_get_macronode("CTRL_SCATTER")` fails with `KeyError` because there's no macronode registered with that name.

## Proposed Changes

### Component 1: Flow Engine — CTRL_ Auto-Wrap

#### [MODIFY] [flow_engine.py](file:///B:/EXO_GANS/maccre_core/orchestration/flow_engine.py)

Add a CTRL_ auto-wrap branch to `_get_macronode()` (between the agent roster fallback and the `raise KeyError`). When the step name starts with `CTRL_`, synthesize a single-node topology on the fly:

```python
# ── CTRL_ Node Auto-Wrap ──
if name.startswith("CTRL_"):
    return {
        "name": name,
        "description": f"Auto-wrapped control node: {name}",
        "is_template": False,
        "agent_slots": [],
        "topology_rows": [{
            "Node_ID": name,
            "Agent_Name": "SYSTEM",
            "Model_Override": "none",
            "Next_Node": "END",
            "Temperature": "0",
            "Instruction_Override": "",
            "Wait_For": "none",
        }],
        "roster_rows": [],
        "template_type": "",
        "template_config": None,
    }
```

**For CTRL_SCATTER with slotted agents**, the auto-wrap becomes richer — it generates a scatter topology from `step.config["scatter_agents"]`:

```
CTRL_SCATTER → Agent_A (parallel)
             → Agent_B (parallel)
             → Agent_C (parallel)
             → CTRL_MERGE (fan-in, auto-appended)
```

This is a complete synthetic MacroNode definition generated at runtime from the FlowStep config.

> [!IMPORTANT]
> The auto-wrap for CTRL_SCATTER must read `step.config` to build the topology. This means `_get_macronode` needs access to the step config. We'll add an optional `step_config` parameter.

---

### Component 2: NodeConfigModal — Agent Slotting UI for CTRL_SCATTER

#### [MODIFY] [nexus_plex.py](file:///B:/EXO_GANS/maccre_tui/nexus_plex.py)

Replace the current CTRL_SCATTER section in `_compose_ctrl_fields` (L2176-2189) with a full agent slotting interface:

**New CTRL_SCATTER config section layout:**

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

**Implementation details:**

1. **Agent selector dropdown** — populated from the project's agent roster (same source as the existing `#agent-select` dropdown in FlowExecutionPanel)
2. **Add Agent button** — appends the selected agent to `self._scatter_agents: list[str]` and re-renders the agent list
3. **Per-agent row** — shows agent name, ⚙ Overrides button (opens `AgentProfileOverridesModal`), ✕ Remove button
4. **Overrides** — uses the existing `AgentProfileOverridesModal` class (same as MacroNode modal), stored in `self._scatter_agent_overrides: dict[str, dict]`
5. **Remove** — removes the agent from the list

The `_collect_ctrl_config` save handler merges the agent list and overrides into the config dict:

```python
cfg["scatter_agents"] = self._scatter_agents  # ["TopperShepherd", "TopperAngry", ...]
cfg["scatter_agent_overrides"] = self._scatter_agent_overrides  # per-agent profile dicts
cfg["scatter_targets"] = self._scatter_agents  # backwards compat — targets = agent names
```

---

### Component 3: Flow Engine — Scatter Topology Synthesis

#### [MODIFY] [flow_engine.py](file:///B:/EXO_GANS/maccre_core/orchestration/flow_engine.py)

In `_get_macronode`, when `name == "CTRL_SCATTER"` and `step_config` contains `scatter_agents`, synthesize a full scatter→agents→merge topology:

```python
if name.startswith("CTRL_SCATTER") and step_config.get("scatter_agents"):
    agents = step_config["scatter_agents"]
    agent_overrides = step_config.get("scatter_agent_overrides", {})
    scatter_mode = step_config.get("scatter_mode", "full_copy")
    tether_id = step_config.get("tether_id", f"scatter_{id(agents) % 9999:04d}")
    
    topo_rows = []
    # 1. CTRL_SCATTER node → fans out to all agents
    topo_rows.append({
        "Node_ID": "CTRL_SCATTER",
        "Agent_Name": "SYSTEM",
        "Model_Override": "none",
        "Next_Node": ",".join(agents),  # multi-target
        "Temperature": "0",
        "Instruction_Override": "",
    })
    # 2. One row per slotted agent
    for agent_name in agents:
        overrides = agent_overrides.get(agent_name, {})
        topo_rows.append({
            "Node_ID": agent_name,
            "Agent_Name": agent_name,
            "Model_Override": overrides.get("model", ""),
            "Next_Node": "CTRL_MERGE",
            "Temperature": str(overrides.get("temperature", "1.0")),
            "Instruction_Override": overrides.get("system_prompt_override", ""),
            "Tools_Allowed": overrides.get("tools_allowed", ""),
        })
    # 3. CTRL_MERGE fan-in
    topo_rows.append({
        "Node_ID": "CTRL_MERGE",
        "Agent_Name": "SYSTEM",
        "Model_Override": "none",
        "Next_Node": "END",
        "Temperature": "0",
        "Wait_For": "|".join(agents),
    })
    
    return {
        "name": name,
        "description": f"Dynamic scatter: {len(agents)} agents",
        "topology_rows": topo_rows,
        "agent_slots": agents,
        ...
    }
```

> [!IMPORTANT]
> The merge node is auto-appended because a scatter without a merge would leave dangling flow lines. The tether_id links them.

---

### Component 4: FlowStep.config Passthrough

#### [MODIFY] [flow_engine.py](file:///B:/EXO_GANS/maccre_core/orchestration/flow_engine.py)

Update `_get_macronode` signature to accept optional `step_config`:

```python
def _get_macronode(self, name: str, step_config: dict[str, Any] | None = None) -> dict[str, Any]:
```

Update the call site at L661:

```python
macro_def = self._get_macronode(step.macronode_name, step_config=getattr(step, "config", {}))
```

Also update `preflight_check` L197-200 to handle CTRL_ nodes:

```python
if macro_name.startswith("CTRL_"):
    continue  # CTRL_ nodes are auto-wrapped, skip macronode existence check
```

---

### Component 5: Agent Profile Loading in NodeConfigModal

#### [MODIFY] [nexus_plex.py](file:///B:/EXO_GANS/maccre_tui/nexus_plex.py)

When the NodeConfigModal opens for CTRL_SCATTER, load the **full roster** (not just `agents_in_node`) into the agent selector so the user can pick from all available agents:

```python
# In _compose_ctrl_fields, CTRL_SCATTER branch:
# Load all roster agents for the dropdown
from maccre_core.agent_library import get_agent_store
store = get_agent_store(self.active_project)
all_agents = [p.get("agent_name", "") for p in store.load_all()]
```

---

## Data Flow Summary

```
User opens CTRL_SCATTER modal
  ↓ picks agents, configures overrides
  ↓ saves → FlowStep.config = {"scatter_agents": [...], "scatter_agent_overrides": {...}}
  
User clicks ▶ Run
  ↓ flow_engine.execute_flow() iterates steps
  ↓ _get_macronode("CTRL_SCATTER", step_config=step.config)
  ↓ detects scatter_agents in step_config
  ↓ synthesizes topology: SCATTER → Agent_A | Agent_B | Agent_C → MERGE
  ↓ _hydrate_topology() writes to topology.csv
  ↓ swarm_worker reads topology, executes CTRL_SCATTER
  ↓ _handle_scatter returns next_nodes=[Agent_A, Agent_B, Agent_C]
  ↓ agents execute in parallel, results merge at CTRL_MERGE
```

## Verification Plan

### Manual Verification
1. Add CTRL_SCATTER to flow → open Configure Node Modal → verify agent selector dropdown appears with roster agents
2. Add 3 agents → verify all 3 appear in the agent list with Overrides buttons
3. Click ⚙ Overrides on one agent → verify AgentProfileOverridesModal opens with correct profile
4. Save → reopen modal → verify all 3 agents + overrides persist
5. Run flow → verify scatter topology synthesizes correctly and agents execute in parallel

### Automated (omni qa)
- `omni qa maccre_core/orchestration/flow_engine.py`
- `omni qa maccre_tui/nexus_plex.py`

## Items Deferred to Phase 6

- **Downstream scatter with mixed targets** — targeting both existing topology nodes AND newly-slotted agents in the same CTRL_SCATTER
- **CTRL_BRANCH / CTRL_CONDITIONAL_ROUTE agent slotting** — same pattern but for routing nodes
- **Drag-and-drop reordering** of slotted agents within the scatter UI
