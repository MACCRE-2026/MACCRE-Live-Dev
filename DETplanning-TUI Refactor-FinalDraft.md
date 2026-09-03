# NexusPlex v2 — Final Planning Clarifications (Round 3)

**Previous Plan:** [implementation_plan.md (Round 2)](file:///C:/Users/<username>/.gemini/antigravity/brain/aeb9a18e-bdef-4c99-b1d0-9887cd54aea8/implementation_plan.md)
**Git Rollback:** `950996f`

---

## 1. Topology Source: Where Completed Session Data Lives

### The Answer

You were right to question this. **`02_Dynamic_Context` is the canonical source for completed session topology, NOT `swarm_queue.db`.**

`swarm_queue.db` is a **hot runtime queue** — it stores individual task rows (one per node per execution), NOT the structural topology graph. It has:

```sql
CREATE TABLE task_queue (
    id INTEGER PRIMARY KEY,
    job_id TEXT,
    current_node TEXT,         -- individual node being worked
    payload_path TEXT,
    lock_status TEXT,          -- 'open', 'locked', 'completed', 'failed', 'paused'
    loop_iteration_count INT,
    ...
);
```

This is task-level execution state, not topology. And while completed tasks stay in the table (no automatic purge), reconstructing a topology from scattered task rows would be fragile and lossy.

### What `02_Dynamic_Context` Has

For each completed session, the flow engine writes a full snapshot to `02_Dynamic_Context/{job_id}/`:

| File | Contents | Written By |
|------|----------|-----------|
| `as_wrapped_topology.json` | **Complete as-wrapped topology** — every node with its resolved agent name, model, system prompt (with structural augments applied), tools, Wait_For, Next_Node, temperature, all config | `flow_engine.py` after topology hydration |
| `topology_snapshot.csv` | CSV version of the topology graph — Node_ID, Agent_Name, Next_Node, Wait_For, Model_Override, etc. | `flow_engine.py` |
| `flow_config.json` | Flow-level metadata — session name, project, timestamp, flow steps | `flow_engine.py` |

**`as_wrapped_topology.json` is the gold standard** — it captures the *fully resolved* state of the topology at execution time, including all agent overrides, tool assignments, and structural augments.

### Semi-Redundant Systems Assessment

Yes — you built complementary systems on top of the hot queue that are actually better canonical sources:

| System | What It Stores | Canonical For |
|--------|---------------|---------------|
| `swarm_queue.db` (task_queue) | Per-node task rows with execution state | **Runtime execution** (which node is active, what's locked) |
| `02_Dynamic_Context/{job_id}/` | Full topology snapshot + as-wrapped config | **Session reconstruction** (what was the topology, how were agents configured) |
| `03_Agent_Ledgers/{job_id}/` | Per-node output artifacts + ledgers | **Session results** (what each node produced) |
| `flow_registry.db` (deprecated) | Serialized `FlowStep` lists | **Design-time flow recipes** (being removed) |
| `macronode_registry.db` | Template definitions with slot configs | **Reusable topology patterns** (the new canonical for saved topologies) |

### Corrected "Save as MacroNode Template" Rewire

```python
# When user clicks "Save as MacroNode Template" in Session Manager:

def save_session_as_template(job_id: str, project: str, template_name: str) -> None:
    """Convert a completed session's topology into a reusable MacroNode template."""
    
    # 1. Load the canonical topology from 02_Dynamic_Context
    topo_path = get_datacenter_path("02_Dynamic_Context", job_id) / "as_wrapped_topology.json"
    topology = json.loads(topo_path.read_text(encoding="utf-8"))
    
    # 2. Strip agent-specific data — keep only structural blueprint
    #    (node roles, Wait_For graph, Next_Node wiring, node types)
    template_rows = []
    for node in topology["nodes"]:
        template_rows.append({
            "Node_ID": node["Node_ID"],
            "Role": node.get("Role", node["Node_ID"]),  # slot role, not agent name
            "Next_Node": node["Next_Node"],
            "Wait_For": node.get("Wait_For", ""),
            "Node_Type": "control" if node["Node_ID"].startswith(("CTRL_", "DET_")) else "agent",
        })
    
    # 3. Auto-detect template type from topology shape
    template_type = _infer_template_type(template_rows)  # crucible/hologram/chord/cascade/custom
    
    # 4. Save to MacroNode registry — NO agents slotted, just the blueprint
    store = get_macronode_store()
    store.save(
        name=template_name,
        description=f"Template derived from session {job_id}",
        template_type=template_type,
        topology_rows=template_rows,
        agent_mapping={},  # Empty — user slots agents later in MacroNode Workshop
    )
```

> [!IMPORTANT]
> The key insight: `as_wrapped_topology.json` has **more** data than we need for a template (it includes resolved system prompts, model configs, etc.). We intentionally strip that down to the structural skeleton — node roles, wiring, and types. The user then slots fresh agents into this skeleton via the MacroNode Workshop.

---

## 2. Overlay Corrections

### Flow Monitor Overlay (Corrected)

**Previous (wrong):** Covers left Info Panes + right side
**Corrected:** Covers **ONLY the left Info Panes**. Right side (MacroNode Workshop + Topology Visualizer) remains fully visible and interactive.

```
DURING EXECUTION:
┌──────────────────────────────────────────────────────────────┐
│ CustomHeader  [Flow Monitor ◀ collapse tab]                  │
├──────────────┬───────────────────────────────────────────────┤
│ ┌──────────┐ │ RIGHT PANE (fully visible + interactive)      │
│ │ FLOW     │ │                                               │
│ │ MONITOR  │ │  AgentBuilder │ MacroNode Workshop            │
│ │ OVERLAY  │ │               │                               │
│ │          │ │               │ Topology Visualizer            │
│ │ Stage    │ │               │ (live animation —             │
│ │ Readout  │ │               │  active node lit,             │
│ │          │ │               │  flow lines pulsing)          │
│ │ Exec Log │ │               │                               │
│ │          │ │               │ [Stop] [Resume] [Rewind]      │
│ │          │ │               │                               │
│ ├──────────┤ │               │                               │
│ │ Nexus    │ │               │                               │
│ │ Copilot  │ │               │                               │
│ │(visible) │ │               │                               │
│ └──────────┘ │               │                               │
├──────────────┴───────────────────────────────────────────────┤
│ Footer                                                       │
└──────────────────────────────────────────────────────────────┘
```

### NodeConfig Overlay (Covers Agent Builder)

When user clicks a node on the Topology Visualizer:

```
DURING NODE CONFIGURATION:
┌──────────────────────────────────────────────────────────────┐
│ CustomHeader                                                 │
├──────────────┬───────────────────────────────────────────────┤
│ Info Panes   │ ┌──────────┐                                  │
│ (context-    │ │ NODE     │ │ MacroNode Workshop             │
│  sensitive   │ │ CONFIG   │ │                                │
│  collapse)   │ │ OVERLAY  │ │ Topology Visualizer            │
│              │ │          │ │ (selected node highlighted)    │
│ Instruct.  ▼ │ │ Tools    │ │                                │
│ Config     ▼ │ │ Prompt   │ │                                │
│ As-Wrapped ▼ │ │ Payload  │ │                                │
│              │ │ Mode     │ │                                │
│ ─────────── │ │[NodeCfg ◀│ │                                │
│ Nexus        │ │collapse] │ │                                │
│ Copilot      │ └──────────┘ │                                │
├──────────────┴───────────────────────────────────────────────┤
│ Footer                                                       │
└──────────────────────────────────────────────────────────────┘
```

### Collapsible Tab Behavior (Both Overlays)

Each overlay has a **collapse tab** — a small persistent handle on the edge:

| State | Tab Position | Tab Appearance | Action |
|-------|-------------|---------------|--------|
| **Expanded** | Attached to overlay edge | `◀ Collapse` vertical text tab | Click → overlay slides out, tab moves to header/footer |
| **Collapsed** | Nested in Header (Flow Monitor) or Footer (NodeConfig) | Small button: `[📊 Monitor]` or `[⚙ Config]` | Click → overlay slides back in |

```python
# Flow Monitor collapsed state:
# Header gains a button:
#   [📊 Flow Monitor] — click to re-expand the overlay

# NodeConfig collapsed state:  
# Footer gains a button:
#   [⚙ Node Config] — click to re-expand the overlay
```

**CSS animation:** `transition: width 300ms in_out_cubic` for the slide in/out, matching the existing NexusChat expand/collapse pattern.

---

## 3. Topology Visualizer Animation Spec

### Node States

Using Textual's `set_interval` (200ms tick) + Rich Tree custom renderables:

| State | Visual | Text Style | Symbol |
|-------|--------|-----------|--------|
| **Completed** | Greyed out | `dim` / `#5c6370` | `✓` prefix |
| **Active (working)** | Lit / bright | `bold cyan` | `⚡` prefix, cycling `⣾⣽⣻⢿⡿⣟⣯⣷` spinner |
| **Upcoming (next)** | Dimmed but visible | `#8b949e` | `○` prefix |
| **Upcoming (future)** | Dimmed further | `#484f58` | `·` prefix |
| **Failed** | Red | `bold red` | `✗` prefix |
| **Paused** | Orange/amber | `bold yellow` | `⏸` prefix |

### Flow Line Animation

The key animation: **pulsing flow lines** from the active node to its upcoming targets.

```python
class TopologyVisualizer(Tree):
    """Rich Tree with animated flow visualization."""
    
    _animation_frame: reactive[int] = reactive(0)
    
    def on_mount(self) -> None:
        self._animation_timer = self.set_interval(0.2, self._advance_frame)
    
    def _advance_frame(self) -> None:
        self._animation_frame += 1
        self.refresh()  # triggers re-render of custom node renderables
```

**Flow line characters** (cycle through on each frame):

```
Frame 0:  [Active ⚡] ─── → [Next ○]
Frame 1:  [Active ⚡] ──── → [Next ○]
Frame 2:  [Active ⚡] ───── → [Next ○]
Frame 3:  [Active ⚡] ──────→ [Next ○]
Frame 4:  [Active ⚡] ─── → [Next ○]   (cycle restarts)
```

For branches/scatters:
```
                    ╭──── → [Branch A ○]
[Active ⚡] ────╮
                    ╰──── → [Branch B ○]
```

For recursion loops:
```
[Active ⚡] ──── → [Judge ○]
     ↑                    │
     │    ╭── LOOP ──╯    │   (loop arrow pulses with frame)
     ╰────╯               ↓
                    [Exit ○]
```

### Performance: Only Refresh Active Subtree

To avoid redrawing the entire tree on every 200ms tick:
- Track which nodes changed state since last frame
- Only `refresh()` the tree when the active node changes or animation frame advances
- When flow is idle (not executing), disable the animation timer entirely

### What Textual Supports Natively

| Feature | Textual Support | Our Approach |
|---------|----------------|-------------|
| CSS `transition` on widget styles | ✅ Yes (opacity, background, offset) | Use for overlay slide in/out |
| `set_interval` for frame ticks | ✅ Yes | 200ms tick for flow animation |
| Rich custom renderables in Tree nodes | ✅ Yes | Each node is a custom renderable with state-driven styling |
| CSS class toggling | ✅ Yes | `.node-active`, `.node-completed`, `.node-dimmed` classes |
| Tree node expand/collapse | ✅ Built-in | Use for MacroNode sub-trees (expand to see internal topology) |
| Unicode box-drawing characters | ✅ Full support | `─ │ ├ └ ╭ ╰ → ↑ ↓` for flow lines |

---

## 4. Updated Plan Sections

### Phase 3 Confirmation: Rich Tree

Using Textual's built-in `Tree` widget with custom renderables per node. Each `TreeNode.data` holds a `TopologyNodeState` dataclass:

```python
@dataclass
class TopologyNodeState:
    node_id: str
    node_type: str              # "agent", "macronode", "control"
    display_name: str
    status: str                 # "idle", "active", "completed", "failed", "paused"
    next_nodes: list[str]       # for rendering flow lines
    wait_for: list[str]         # for rendering gather connections
    config: dict[str, Any]      # for NodeConfig overlay population
```

### Phase 3 Animation: Within Textual Limits

No wheel reinvention. The combination of:
1. **`set_interval(0.2s)`** — advances animation frame counter
2. **Custom Rich renderables** — each node renders differently based on `status` + `frame`
3. **Unicode flow lines** — `─ → ↑ ╭ ╰` characters that cycle/pulse
4. **CSS class toggling** — `.node-active { color: cyan; text-style: bold; }`

This gives us the pulsing flow lines, lit active nodes, greyed completed nodes, and dimmed upcoming nodes — all within Textual's native capabilities.

---

## 5. Remaining Corrections to Round 2 Plan

### Correction 1: Flow Monitor Overlay Coverage

```diff
- **Coverage:** Covers the left pane Information Panes + right pane (but NOT Nexus Copilot)
+ **Coverage:** Covers ONLY the left pane Information Panes (NOT Nexus Copilot, NOT right pane)
```

### Correction 2: Topology Source for Template Save

```diff
- 1. Load completed session's topology from `swarm_queue.db`
+ 1. Load completed session's topology from `02_Dynamic_Context/{job_id}/as_wrapped_topology.json`
```

### Addition: Both Overlays Get Collapse Tabs

```diff
+ Flow Monitor Overlay: collapse tab → nests into Header as [📊 Flow Monitor] button
+ NodeConfig Overlay: collapse tab → nests into Footer as [⚙ Node Config] button
+ Both use CSS transition: width 300ms in_out_cubic for slide animation
```

---

## 6. Final Phase Plan (Consolidated)

### Phase 0: Foundation
- `controlnode_registry.db` + `ControlNodeStore` + seed 23 nodes
- Dual-prefix (CTRL_ + DET_) in `deterministic_nodes.py`
- `deprecated` column on `macronode_registry`
- Fix save handler bug + 3 audit bugs
- **No UI changes**

### Phase 1: Deprecation & Cleanup
- Delete Flow Registry (15-item checklist)
- Rewire Session Manager → "Save as MacroNode Template" (reads from `02_Dynamic_Context`)
- Delete 3 orphaned surfaces
- **Minimal UI changes**

### Phase 2: Left Pane → Information Panes
- `InfoPane` collapsible widget (CSS class toggle pattern from NexusChat)
- 5-6 panes: MacroNode Details, Agent Details, Control Node Details, Instructions, Configuration, As-Wrapped
- Context-sensitive collapse on NodeConfig overlay trigger
- Replace `MacroNodeBuilderPanel` in compose()

### Phase 3: MacroNode Workshop + Topology Visualizer
- `TopologyVisualizer` — Rich Tree with `TopologyNodeState` renderables
- `NodeCatalog` — unified browser from 3 registries (with `{ComingSoon}` entries)
- `MacroNodeWorkshop` — Catalog + Visualizer + flow control buttons
- NodeConfig Overlay (covers Agent Builder, collapse tab → Footer button)
- Animation: `set_interval(0.2s)` + pulsing flow lines + state-driven node styling
- Replace `FlowExecutionPanel` in compose()

### Phase 4: Flow Monitor + Full Integration
- Flow Monitor Overlay (covers left Info Panes, collapse tab → Header button)
- Triggers on Launch, auto-shows on execution
- Live topology highlighting synced with Flow Monitor
- Full DET_ → CTRL_ rename across 10 files
- DB migration script for saved templates containing DET_ references

### Phase 5: Control Node Evolution
- Implement CTRL_MERGE, CTRL_SCATTER, CTRL_CONDITIONAL_ROUTE
- Refactor Crucible to use CTRL_RECURSION
- Implement CTRL_DIALOG, CTRL_BRANCH
- Media pipeline nodes (CTRL_CONCAT, CTRL_MEDIA_PROBE)
- Nexus Copilot sandbox integration
