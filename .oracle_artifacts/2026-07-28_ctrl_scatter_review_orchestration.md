# Orchestration & Swarm Engine Review: CTRL_SCATTER Expansion Plan (v1 → v2 → v3)

**Author:** OrchestrationAndEngine_Oracle  
**Date:** 2026-07-28  
**Status:** Approved with 5 Engine Corrections  
**Target Core Files:** `maccre_core/orchestration/flow_engine.py`, `swarm_worker.py`, `local_broker.py`, `topology_engine.py`, `deterministic_nodes.py`

---

## 1. Executive Summary

This report provides the Specialist Orchestration & Engine audit of the **CTRL_SCATTER Expansion Plan** across its three design iterations (v1, v2, and v3 FINAL). The initiative transitions `CTRL_SCATTER` from a static node reference into a dynamic container for agent slotting, synthetic topology expansion, telemetric lineage tracking, and high-concurrency WAL-sharded scatter-gather execution.

The architectural direction of **v3 (FINAL)** is endorsed. Crucially, v3 introduces the `flow_vector` lineage column in Phase 4.75.7, establishing the foundational schema for Phase 6 WAL Sharding (§6.13) and Phase 7 Time-Travel Replay (§7.X).

However, code-level analysis revealed 5 critical engine and hydration bugs in the proposed implementations that must be resolved prior to deployment.

---

## 2. Progression Analysis (v1 → v2 → v3)

### v1: Dynamic MacroNode Constructor
- Introduced `CTRL_` auto-wrap concept in `_get_macronode()`.
- Synthesized `CTRL_SCATTER -> Slotted Agents -> CTRL_MERGE` DAG at runtime.
- Added TUI agent slotting UI fields.
- **Limitation:** Did not address visualizer rendering, rate-limit economics, or telemetry lineage.

### v2: Agent Slotting & Visualizer Mechanics
- Formalized scope into **NOW (Phase 4.75.7)** vs **Phase 6 Roadmap**.
- Proposed always-expanded topology tree (stripping collapse toggles).
- Introduced `MAX_SCATTER_AGENTS = 5` constraint based on assumed free-tier API rate limits.
- **Limitation:** Inaccurately assumed free-tier API bottlenecks; topology collapse toggle removal caused UI pane clutter.

### v3 (FINAL): Telemetry Lineage & Scale Architecture
- **Corrected Rate Limits:** Adjusted `MAX_SCATTER_AGENTS` to 8 (hard cap 12) for paid Gemini API tier.
- **Refined Visualizer:** Defaulted tree to expanded (`True`) while keeping collapse toggle `[+]/[-]` with condensed summary mode (`[+] CTRL_SCATTER ⟩ 3 agents ⟩ CTRL_MERGE`).
- **Planted `flow_vector` Groundwork:** Added `flow_vector TEXT DEFAULT ''` to `task_queue` in `local_broker.py` (Phase 4.75.7).
- **Phase 6 WAL Sharding (§6.13):** Scaled DB write throughput by sharding parallel scatter lines into separate WAL files (`swarm_queue_fl_scatter_A.db`) using `flow_vector` as partition key.
- **Phase 7 Telemetric Memory Simulation:** Defined Time-Travel Replay, Agent Perspective Simulation, and Counterfactual Path Simulation.

---

## 3. Orchestration Engine Technical Audit & Required Fixes

### 3.1 Bug Fix #1: `step_config` Passthrough in `execute_flow` (L545)
In `flow_engine.py`, `_get_macronode()` signature is updated to accept `step_config`. However, inside `execute_flow()` at line 545, `_get_macronode` is invoked without `step_config`:
```python
# BEFORE (Bug):
macro_def = self._get_macronode(step.macronode_name)

# AFTER (Fixed):
macro_def = self._get_macronode(step.macronode_name, step_config=getattr(step, "config", {}))
```

### 3.2 Bug Fix #2: Comma-Separated `Next_Node` Hydration in `_hydrate_topology()`
`CTRL_SCATTER` produces `"Next_Node": "Agent_A,Agent_B"`. `_hydrate_topology()` in `flow_engine.py` (L400-401) previously appended `_S{step_index}` to the raw string, producing `"Agent_A,Agent_B_S0"`.
```python
# BEFORE (Bug):
if next_node and next_node.upper() not in ("END", "FAILED"):
    next_node = f"{next_node}_S{step_index}"

# AFTER (Fixed):
if next_node and next_node.upper() not in ("END", "FAILED"):
    parts = [p.strip() for p in next_node.split(",") if p.strip()]
    hydrated_parts = [
        f"{p}_S{step_index}" if p.upper() not in ("END", "FAILED") else p 
        for p in parts
    ]
    next_node = ",".join(hydrated_parts)
```

### 3.3 Bug Fix #3: `Tether_ID` Isolation in Synthesized Topology Rows
To prevent cross-contamination between parallel flow lines in `swarm_worker.py` (L824-830), `_get_macronode()` must explicitly attach `"Tether_ID"` to all synthesized rows:
```python
tether_id = cfg.get("tether_id", f"scatter_{id(scatter_agents) % 9999:04d}")
# Include "Tether_ID": tether_id in topo_rows for CTRL_SCATTER, slotted agents, and CTRL_MERGE
```

### 3.4 Bug Fix #4: Preflight Validation of Slotted Scatter Agents
Instead of bypassing preflight completely with `if macro_name.startswith("CTRL_"): continue`, `preflight_check()` should fetch the synthetic MacroNode definition:
```python
if macro_name.strip().upper().startswith("CTRL_"):
    macro_def = self._get_macronode(macro_name, step_config=getattr(step, "config", {}))
```
This ensures slotted agents are checked against `agent_library.db` and estimated API costs are accumulated.

### 3.5 Bug Fix #5: Hardware Probing for Local Scatter Models
Per Omni-Builder Rule V, if any agent in `scatter_agents` resolves to a local Ollama model (e.g. `gemma3:9b`), preflight must probe host RAM/VRAM via `environment_probe.py` and cap local scatter concurrency to 2 to prevent host lockup.

---

## 4. Telemetry Lineage Mechanics (`flow_vector`)

In `local_broker.py`, `task_queue` schema is updated:
```sql
ALTER TABLE task_queue ADD COLUMN flow_vector TEXT DEFAULT '';
```
When `swarm_worker.py` dispatches a task to its `next_node`, it updates `flow_vector`:
```python
parent_vector = task.get("flow_vector", "")
new_vector = f"{parent_vector}:{current_node}" if parent_vector else current_node
```
For a scatter step, each fan-out agent task receives its unique branch vector:
- `CTRL_SCATTER_S0:TopperShepherd_S0`
- `CTRL_SCATTER_S0:TopperAngry_S0`

This colon-delimited path enables:
1. **Phase 6 WAL Sharding:** Partitioning tasks into `swarm_queue_fl_<branch>.db`.
2. **Phase 7 Replay Engine:** Reconstructing exact branch execution paths and payload evolution.

---

## 5. Verification Plan

### Automated Gatekeeper QA
```bash
omni qa maccre_core/orchestration/flow_engine.py
omni qa maccre_core/orchestration/local_broker.py
omni qa maccre_core/orchestration/swarm_worker.py
omni qa maccre_tui/nexus_plex.py
```

### Manual DAG Verification
1. Add `CTRL_SCATTER` to flow step in TUI.
2. Slot 3 agents with custom prompt overrides in `NodeConfigModal`.
3. Verify topology visualizer displays `CTRL_SCATTER ⟩ Agent_A, Agent_B, Agent_C ⟩ CTRL_MERGE`.
4. Execute flow; verify parallel dispatch, tethered fan-in, and correct `flow_vector` lineage in `task_queue`.
