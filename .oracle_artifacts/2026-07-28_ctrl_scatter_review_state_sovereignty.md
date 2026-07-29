# State & Sovereignty Architectural Audit: CTRL_SCATTER Expansion Plan (v1 -> v2 -> v3)

**Author:** StateAndSovereignty_Oracle  
**Date:** 2026-07-28  
**Domain Scope:** `path_resolver.py`, `access_control.py`, `telemetry_db.py`, `local_broker.py`, `universal_vault.py`, `windows_vault.py`, `omni`

---

## 1. Abstract & Scope of Review

This document provides the definitive State, Security, and Sovereignty assessment of the `CTRL_SCATTER` expansion plan progression (v1, v2, and v3). The review evaluates data persistence, database schema integrity, telemetry matrix evolution, key vault hygiene, file lock safety in 5-tier datacenter silos, and compliance with the Sovereign Edge Omni-Builder Doctrine.

---

## 2. Analysis of Expansion Plan Progression

### 2.1 Plan v1: Linear Synthesis & UI Slotting
- **Core Strategy:** Synthesize MacroNode topology rows on the fly in `flow_engine._get_macronode()` and populate `step.config["scatter_agents"]` in `nexus_plex.py`.
- **Domain Audit:** Functional UI specification. Lacks persistence safety, concurrency analysis, schema migration, or telemetry tracking.

### 2.2 Plan v2: Scope Boundaries & Concurrency Bottlenecks
- **Core Strategy:** Separated NOW (Phase 4.75.7 UI & auto-wrap) from Phase 6 (TUI canvas & DAG visualization). Capped agents at 5 based on SQLite WAL write serialization.
- **Domain Audit:** Correctly identified SQLite single-writer bottleneck under WAL mode. Misjudged API rate limits (assumed free tier 30 RPM limits).

### 2.3 Plan v3: Telemetry Vector Schema & Visionary Roadmap
- **Core Strategy:** Corrected API assumptions (paid tier 1000+ RPM), raised agent limit to 8 (hard cap 12). Introduced **Part A5 (`flow_vector` lineage schema)**, **Phase 6.13 (WAL Sharding by Flow Line)**, and **Phase 7 (Telemetric Memory Simulation: Time-Travel Replay, Agent Perspective Simulation, Counterfactual Branching)**.
- **Domain Audit:** Highly commended for planting the `flow_vector` lineage seed early in `task_queue`. Provides a clear, low-overhead path to high-scale parallelism and analytical replay.

---

## 3. Critical Findings & Schema Safety Risks

### 3.1 `task_queue` UNIQUE Constraint Collision (High Severity)
- **Problem:** `maccre_core/orchestration/local_broker.py` defines `UNIQUE(job_id, current_node)`.
- **Risk:** If a flow contains multiple `CTRL_SCATTER` steps or re-uses an agent name (e.g. `TopperShepherd`), inserting tasks into `task_queue` with identical `current_node` strings in the same `job_id` will trigger a fatal SQLite `IntegrityError`.
- **Remediation:** Synthetic topology node IDs MUST incorporate step tether IDs or instance numbers:  
  `Node_ID = f"{agent_name}_{tether_id}"`.

### 3.2 `flow_vector` Delimiter Collision (Medium Severity)
- **Problem:** Plan v3 proposed colon (`:`) as `flow_vector` delimiter (`CTRL_SCATTER_S0:TopperShepherd_S0`).
- **Risk:** Colon conflicts with Windows drive letters (`C:\`), URI schemes (`http://`), and namespaces.
- **Remediation:** Adopt `>` as the canonical lineage delimiter (`CTRL_SCATTER_S0>TopperShepherd_S0>CTRL_MERGE_S0`).

### 3.3 Data Sovereignty & Telemetry File Contention (Medium Severity)
- **Problem:** Multi-agent parallel execution writing to shared ledger paths in `03_Agent_Ledgers/`.
- **Risk:** Concurrent JSON appends cause partial writes or file locking conflicts.
- **Remediation:** Qualify ledger paths by `job_id` and `tether_id`:  
  `03_Agent_Ledgers/{job_id}_{tether_id}_{agent_name}_telemetry.json`.

### 3.4 Key Vault Hygiene & Memory Zeroing
- **Requirement:** Parallel worker threads dispatching REST calls MUST fetch credentials securely and invoke `ctypes.memset` on key memory buffers immediately post-request.

---

## 4. Database Schema Validation & Migration Plan

### 4.1 Upgraded `task_queue` Schema (`local_broker.py`)

```sql
-- Schema migration for task_queue with flow lineage support
ALTER TABLE task_queue ADD COLUMN flow_line_id TEXT DEFAULT '';
ALTER TABLE task_queue ADD COLUMN tether_id TEXT DEFAULT '';
ALTER TABLE task_queue ADD COLUMN flow_vector TEXT DEFAULT '';

-- Ensure index handles tethered execution cleanly
CREATE UNIQUE INDEX IF NOT EXISTS idx_job_node_tether 
ON task_queue (job_id, current_node, tether_id);
```

### 4.2 Telemetry Correlation Schema (`telemetry_db.py`)

```sql
-- system_logs correlation metadata update
ALTER TABLE system_logs ADD COLUMN flow_vector TEXT DEFAULT '';
ALTER TABLE system_logs ADD COLUMN tether_id TEXT DEFAULT '';
```

---

## 5. Phase 6 & Phase 7 Technical Feasibility

1. **Phase 6.13 WAL Sharding:** Feasible and recommended. Partitioning `swarm_queue.db` into `swarm_queue_fl_{tether_id}.db` eliminates WAL writer lock contention during 8-agent parallel execution.
2. **Phase 7 Replay & Simulation:**
   - **Time-Travel Replay (C1):** Reconstruct branch history by filtering `flow_vector WHERE flow_vector LIKE 'CTRL_SCATTER_S0>%'`.
   - **Agent Perspective Simulation (C2):** Track all occurrences of an agent across vectors.
   - **Counterfactual Simulation (C3):** Re-inject payload states into alternative agent profiles along identical `flow_vector` paths.

---

## 6. Omni CI/CD Gatekeeper Verification Rules

All modified modules must pass the Omni pipeline:
```bash
omni clean .
omni qa maccre_core/orchestration/local_broker.py
omni qa maccre_core/orchestration/flow_engine.py
omni qa maccre_core/orchestration/swarm_worker.py
omni qa maccre_tui/nexus_plex.py
```

---

## 7. Final Oracle Directives

1. Implement `flow_vector` with `>` delimiter in Phase 4.75.7.
2. Tether-qualify node IDs in synthetic topology generator to prevent SQLite UNIQUE index collisions.
3. Enforce isolated ledger files in `03_Agent_Ledgers`.
4. Maintain `ctypes.memset` key zeroing in thread pool REST execution routines.
