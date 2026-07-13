# Phase 5: Control Node Evolution + Workshop Completion

## Overview

Phase 5 has three interleaved tracks:

1. **Control Node Implementation** — 7 new CTRL_ nodes + template modernization
2. **Template System Evolution** — Save-from-session naming modal + modernized guide templates
3. **Workshop Completion** — Flow Monitor collapse, Topology Visualizer expansion, NodeConfig overlay

---

## Track A: Control Node Implementations

### A1. The 7 Priority Nodes

All handlers go in [deterministic_nodes.py](file:///B:/EXO_GANS/maccre_core/orchestration/deterministic_nodes.py), registered in [controlnode_registry.py](file:///B:/EXO_GANS/maccre_core/controlnode_registry.py).

| Node | Behavior | Config via `Instruction_Override` |
|------|----------|-----------------------------------|
| **CTRL_MERGE** | Reads all Wait_For predecessor outputs from `03_Agent_Ledgers/{job_id}/`, assembles structured doc with `## Source: {node_id}` headers. Config option `"concat"` → flat mode. | `"concat"` or `"structured"` (default) |
| **CTRL_SCATTER** | Semantic pass-through — payload forwarded unchanged. The topology's pipe-delimited `Next_Node` already handles fan-out. This node exists for visual clarity in the Topology Visualizer. | N/A |
| **CTRL_CONCAT** | Like MERGE but flat concatenation with configurable delimiter. | Delimiter string (default `"\n\n---\n\n"`) |
| **CTRL_BRANCH** | Deterministic keyword router. Reads JSON mapping from config: `{"keyword1": "NODE_A", "default": "NODE_B"}`. Scans payload for first keyword match → overrides `next_node`. | JSON keyword→target map |
| **CTRL_CONDITIONAL_ROUTE** | Probabilistic router. Extracts `[ROUTE_TO: TARGET]` from *incoming payload* (which is the previous node's output). Overrides `next_node`. Fallback to topology's `Next_Node`. | N/A (driven by upstream agent output) |
| **CTRL_FILTER** | Strips payload sections. Reads JSON predicate config: `{"strip_sections": ["## Debug"], "max_chars": 50000}`. Writes filtered output. | JSON filter rules |
| **CTRL_CLEANUP** | Deletes temp files matching glob patterns from `Instruction_Override` (e.g. `"*.tmp,checkpoint_*.md"`). Scans job ledger directory. | Comma-separated glob patterns |

> [!NOTE]
> `CTRL_MERGE` and `CTRL_CONCAT` require reading predecessor outputs. The existing fan-in artifact injection at [swarm_worker.py:762-819](file:///B:/EXO_GANS/maccre_core/orchestration/swarm_worker.py#L762-L819) already collects Wait_For predecessor payloads — but only for AI agent nodes. For CTRL_ nodes, the handler itself needs to do the collection since it bypasses the AI pipeline. This means `execute_deterministic_node()` needs access to the broker's task data to query predecessor output paths.

### A2. Architecture Change for MERGE/CONCAT

Currently `execute_deterministic_node()` receives:
```python
def execute_deterministic_node(node_id, task, topology_config) -> DeterministicNodeResult
```

The `task` dict has `job_id`, `payload_path`, and `loop_iteration_count`. But MERGE/CONCAT need predecessor output paths. Two options:

**(A) Pass broker reference** — handlers query `task_queue` for completed predecessor tasks  
**(B) Pre-collect in swarm_worker** — before calling `execute_deterministic_node()`, worker gathers Wait_For artifacts and writes a combined temp file as `payload_path`

> [!IMPORTANT]
> **Recommendation: Option B.** The swarm_worker already has the fan-in artifact collection logic at L762-819. We extend it to run for CTRL_ nodes too (currently it only runs for AI agent nodes). The handler then reads the single combined payload file. This keeps handlers pure (no broker dependency) and reuses existing collection code.

### A3. CTRL_MERGE Config in NodeConfig Overlay

Per your direction, the structured-vs-concat choice for CTRL_MERGE should be a **config option in the NodeConfiguration Overlay**, not just `Instruction_Override`. This connects to Track C (NodeConfig Overlay).

The NodeConfig overlay already has "Ledger Routing Mode" and "Custom Node Instructions". We add a new section for **CTRL_ Node Config** that appears when the selected node is a control node:

```
┌─ Configure Node: CTRL_MERGE_1 ──────────────┐
│                                               │
│  Custom Node Name: [CTRL_MERGE_1          ]   │
│                                               │
│  ── Control Node Settings ──────────────────  │
│  Merge Mode:  [Structured ▼]                  │
│               (Structured / Concatenate)       │
│                                               │
│  Custom Delimiter: [---                   ]   │
│  (only shown when Concatenate selected)        │
│                                               │
│  ── Custom Instructions ────────────────────  │
│  [                                         ]  │
│  [                                         ]  │
│                                               │
│  [Cancel]                [Save]               │
└───────────────────────────────────────────────┘
```

---

## Track B: Template System Evolution

### B1. How CTRL_ Nodes Change Templates

**Critical architectural insight**: Cascade and Chord collapse their entire multi-turn loop into a **single GroupDialogRunner node**. There are no discrete inter-round nodes, so CTRL_ nodes **cannot be injected mid-loop**. This is by design — GroupDialogRunner manages conversation state internally.

This means CTRL_ nodes don't change the existing 4 templates directly. Instead:

```
┌─────────────────────────────────────────────────────────────────┐
│ TEMPLATE LAYER                 vs.    TOPOLOGY LAYER            │
│ (macro_factory.py)                    (topology.csv)            │
│                                                                 │
│ Templates generate topology          Topologies CAN contain     │
│ rows. Some use GroupDialog           CTRL_ nodes as explicit    │
│ (single-node, internal loop).        topology participants.     │
│                                                                 │
│ CTRL_ nodes won't change the         CTRL_ nodes WILL appear   │
│ existing 4 template builders.        in USER-BUILT topologies   │
│                                      and session-derived        │
│                                      templates.                 │
└─────────────────────────────────────────────────────────────────┘
```

**The templates become "guide patterns"** — users can:
1. Start with a template (Hologram, Crucible, etc.)
2. In the Topology Visualizer, see the expanded nodes
3. Click nodes → NodeConfig overlay → customize
4. **Add CTRL_ nodes** between existing nodes (insert CTRL_CHECKPOINT, CTRL_PAUSE, CTRL_FILTER, etc.)
5. Save the modified topology as a new custom template

### B2. Template Modernization — What Changes

The 4 existing templates should get **topology previews** in the Topology Visualizer when selected from the Node Catalog. Currently, selecting a MacroNode template from the catalog shows a description in the InfoPane but doesn't preview the topology shape.

**Proposed enhancement:**
- When user selects a template from the MacroNode tab in NodeCatalog:
  - InfoPane shows description + slot requirements (already works)
  - TopologyVisualizer shows a **preview skeleton** of the template's node pattern (new)
  - Preview nodes are rendered in `IDLE` state with role labels instead of agent names
  - Example: Hologram preview → `○ FACET_1 → ○ FACET_2 → ○ SYNTHESIZER (Wait_For: FACET_1, FACET_2)`

### B3. Save-from-Session Template Naming Modal

Currently, "Save as Template" in the Session Manager (at [session_manager_modal.py:275-288](file:///B:/EXO_GANS/maccre_tui/widgets/session_manager_modal.py#L275-L288)) saves the template with `name=job_id`. The user can rename the session first (L281-287), but this also renames the session itself.

**The fix: A small popup modal** that appears after clicking "Save as Template":

```
┌─ Save as MacroNode Template ─────────────────┐
│                                               │
│  Template Name: [                          ]  │
│  Description:   [                          ]  │
│                                               │
│  Source Session: job_20260712-070622-vlet      │
│  Nodes: 4 agent + 1 control                   │
│                                               │
│  [Cancel]                       [Save]        │
└───────────────────────────────────────────────┘
```

#### [NEW] `TemplateNameModal(ModalScreen[dict | None])`

Location: [session_manager_modal.py](file:///B:/EXO_GANS/maccre_tui/widgets/session_manager_modal.py) (add to same file)

- Fields: template name (required), description (optional)
- Shows source session info (read-only)
- Returns `{"name": "...", "description": "..."}` or None on cancel
- The Session Manager's `on_save_registry` handler pushes this modal first, then uses the returned name for the `store.save()` call instead of `job_id`

**Flow change:**
```
Before:  [Save as Template] → dismiss(save_as_template, job_id) → NexusPlex saves with name=job_id
After:   [Save as Template] → push TemplateNameModal → user enters name → dismiss(save_as_template, job_id, template_name) → NexusPlex saves with name=template_name
```

---

## Track C: Workshop Completion

### C1. Flow Monitor Collapse Button — Already Done ✓

The `📊 Monitor` button **already exists** at [nexus_plex.py:1404](file:///B:/EXO_GANS/maccre_tui/nexus_plex.py#L1404) in the CustomHeader:

```python
yield Button("📊 Monitor", variant="primary", id="btn-expand-monitor", classes="hidden")
```

And the collapse/expand handlers are wired at [L2154-2172](file:///B:/EXO_GANS/maccre_tui/nexus_plex.py#L2154-L2172):
- `FlowMonitorCollapsed` → hide overlay, show InformationPanel, show header button
- `#btn-expand-monitor` pressed → hide button, hide InformationPanel, show overlay

> [!NOTE]
> **Verify this works during a live flow.** You mentioned the collapsed button didn't appear — it should show when you click the "Collapse" button on the overlay itself. If it's not appearing, the issue is likely in the CSS cascade or the hidden class not being toggled correctly. I'll verify this during implementation.

### C2. Remove Flow Monitor from MacroNode Workshop

The [MacroNodeWorkshop](file:///B:/EXO_GANS/maccre_tui/widgets/macronode_workshop.py#L208-L243) currently has a **duplicate Flow Monitor section** (L208-243) that should be removed. The canonical Flow Monitor is now the overlay at [flow_monitor_overlay.py](file:///B:/EXO_GANS/maccre_tui/widgets/flow_monitor_overlay.py).

**What to remove from MacroNodeWorkshop.compose():**
- The `flow-monitor-section` Vertical (L209-243): stage readout, RichLog, VCR instructions, Proceed Anyway button, context injection Input
- The `write_monitor_log()` and `set_stage_readout()` methods (L299-311) — these should delegate to FlowMonitorOverlay

**What to keep:**
- NodeCatalog (L174)
- TopologyVisualizer (L177)
- Topo Actions row (L180-188)
- Active Flow Sequence row (L191-195)
- Flow Control buttons (L198-206) — Launch, Stop, Resume, Rewind, Create Payload, Session Manager, Chat Studio, File Cabinet

**Impact:** After removal, the Workshop becomes purely a **topology builder + flow launcher**. All execution monitoring happens in the overlay. This frees up vertical space for a taller TopologyVisualizer.

### C3. Topology Visualizer — Show All Individual Nodes + Recursion

Currently the [TopologyVisualizer](file:///B:/EXO_GANS/maccre_tui/widgets/topology_visualizer.py) renders the flow as a Tree but with limitations:

**Current state:**
- ✅ Loads topology from step dicts with Node_ID, Next_Node, Wait_For
- ✅ Renders nodes with state-driven symbols (idle/active/completed/failed/paused)
- ✅ Pulsing animation for active nodes
- ✅ Click-to-select posts `TopologyNodeSelected` message
- ✅ Back-reference detection for loops (`↩ node_id (loop)`)
- ❌ Only shows the **MacroNode-level** flow steps — doesn't expand to show individual inner nodes
- ❌ No double-click → NodeConfig overlay wiring
- ❌ Recursion loops shown as simple back-references, not mapped with iteration tracking

**Needed changes:**

#### C3a. Expand MacroNodes to Show Inner Topology

When a MacroNode step is in the flow, the Topology Visualizer should expand it to show its inner topology rows (from the macronode registry or `as_wrapped_topology.json`).

```
Flow (top-level):
├── ○ Step 1: HOLO_Research_Cluster
│   ├── ○ HOLO_OSINT_b3f2  → HOLO_SYNTH_b3f2
│   ├── ○ HOLO_ANALYST_b3f2  → HOLO_SYNTH_b3f2
│   └── ✓ HOLO_SYNTH_b3f2 (Wait_For: OSINT, ANALYST)
├── ● Step 2: Crucible_Refinement   ← currently active
│   ├── ● C_ADV_WRITER_a1c9
│   ├── ○ C_ADV_EDITOR_a1c9
│   ├── ○ C_JUDGE_a1c9 (Wait_For: WRITER, EDITOR)
│   └── ↩ C_ADV_WRITER_a1c9 (recursion loop)
└── ○ Step 3: CTRL_CHECKPOINT_1
```

**How**: `load_topology()` already accepts step dicts. The `MacroNodeWorkshop._handle_node_add()` currently creates simple single-node entries. When adding a MacroNode, expand it: load the macronode's `topology_rows` from the registry and add them as children.

#### C3b. Clickable Nodes → NodeConfig Overlay

When a node is clicked in the Topology Visualizer:
- Single click: show node details in InformationPanel (already works via `TopologyNodeSelected`)
- Double click: open the **NodeConfig Overlay** (not a modal — an overlay that covers the AgentBuilder panel)

The `TopologyNodeDoubleClicked` message already exists (L96-101) but isn't handled. Wire it to open the NodeConfig panel.

> [!IMPORTANT]
> **NodeConfig Overlay vs Modal:** The current `NodeConfigModal` (L1667-1907) is a **modal screen**. The plan calls for it to become an **overlay** that covers the AgentBuilder area. This is a significant UI refactor — the modal's fields need to be relocated into a `NodeConfigOverlay(Vertical)` widget that mounts inside the right pane, covering `AgentBuilderPanel` while leaving `MacroNodeWorkshop` visible.
>
> For this phase, we should **keep the modal** but add the CTRL_ config section to it. The overlay conversion can be Phase 6.

#### C3c. Recursion Mapping

When a topology has recursion loops (CTRL_RECURSION or ROUTE_TO-based), the Topology Visualizer should show:

```
├── ● C_ADV_WRITER_a1c9
├── ● C_ADV_EDITOR_a1c9
├── ● C_JUDGE_a1c9 (Wait_For: WRITER, EDITOR)
│   ├── ↩ C_ADV_WRITER_a1c9 (loop 1/3)
│   └── ↩ C_ADV_EDITOR_a1c9 (loop 1/3)
└── ○ POST_ACCEPTANCE → END
```

The loop iteration counter comes from `task_queue.loop_iteration_count`. During live execution, the visualizer should update to show current iteration.

---

## Prioritized Work Breakdown

### Wave 1: Cleanup + Foundation (lowest risk)
1. Remove Flow Monitor section from MacroNodeWorkshop
2. Verify Flow Monitor collapse/expand button works in header
3. Create `TemplateNameModal` for save-from-session naming

### Wave 2: Control Node Handlers
4. Implement 7 handlers in `deterministic_nodes.py`
5. Extend fan-in artifact collection in `swarm_worker.py` to run for CTRL_ nodes (for MERGE/CONCAT)
6. Update `controlnode_registry.py` seeds — status → active, add handler refs + config_schema
7. Add CTRL_ config section to `NodeConfigModal`

### Wave 3: Topology Visualizer Expansion
8. MacroNode inner topology expansion in `load_topology()`
9. Wire `TopologyNodeDoubleClicked` → open NodeConfigModal
10. Recursion iteration display in tree labels
11. Template skeleton preview when template selected from catalog

---

## Open Questions

> [!IMPORTANT]
> **NodeConfig Overlay vs Modal timing:** Should we convert NodeConfigModal to an overlay this phase, or keep it as a modal and convert later? Converting to overlay requires significant CSS/layout work in `NexusPlex.compose()`. I recommend keeping the modal for now and targeting overlay conversion for Phase 6.

> [!IMPORTANT]
> **Crucible refactor:** Should we refactor Crucible to use `CTRL_CONDITIONAL_ROUTE` instead of the text-scraping `ROUTE_TO:` pattern, or leave Crucible working as-is? The `ROUTE_TO:` pattern is deeply integrated into [swarm_worker.py:1279-1340](file:///B:/EXO_GANS/maccre_core/orchestration/swarm_worker.py). My recommendation: **leave Crucible as-is** — `CTRL_CONDITIONAL_ROUTE` is a new node that handles the same pattern formally, but existing templates don't need to be migrated.

