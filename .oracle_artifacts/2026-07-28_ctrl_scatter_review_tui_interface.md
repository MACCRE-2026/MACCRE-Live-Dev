# Comprehensive Review of CTRL_SCATTER Expansion Plans (v1 - v3) — TUI & Interface Oracle Audit

**Date:** 2026-07-28  
**Specialist Oracle:** TUIAndInterface_Oracle (`maccre_tui/`)  
**Target Files:** `nexus_plex.py`, `nexus_plex.css`, `widgets/topology_visualizer.py`

## 1. Summary of Version Progression

| Plan Version | Scatter Limit | Visualizer Tree Behavior | Core Architectural Focus |
| :--- | :--- | :--- | :--- |
| **v1** | Unbounded | Unchanged (standard collapse) | Raw agent slotting UX proposal; dynamic auto-wrap concept |
| **v2** | 5 agents (max) | Force always-expanded (remove collapse toggle) | Strict scope separation (NOW vs Phase 6); free-tier/WAL write guardrails |
| **v3 (FINAL)** | 8 agents (max 12) | Default expanded + Keep collapse toggle + Condensed summary line | Paid-tier API reality alignment; Telemetry `flow_vector` groundwork |

## 2. Key Findings & Domain Gaps

1. **Roster Data Scope**: `_compose_ctrl_fields` must query `active_project` store rather than hardcoded `"GLOBAL"`.
2. **Dynamic Unmount Lifecycle**: Re-mounting entire child list on removal causes UI flicker; migration to agent-name keyed IDs (`btn-scatter-rm--{name}`) is recommended.
3. **Collapsed Summary Line**: `topology_visualizer.py` requires an explicit suffix formatter for collapsed scatter nodes (`[+] CTRL_SCATTER ⟩ N agents ⟩ CTRL_MERGE`).
4. **CSS Bounds**: `#scatter-agent-list` container needs explicit `max-height: 14` and `overflow-y: scroll` to preserve modal integrity at 8 agents on standard 80x24 displays.

## 3. Phase 6 & Phase 7 UI Roadmap Integration

* **Phase 6.8 Stage Editor & 6.10 Center DAG**: Migration from `Tree` widget to custom multi-column `Static` grid renderable.
* **Phase 6.9 Animated Wires**: Marching-ants unicode wire rendering powered by `set_interval()` timers.
* **Phase 7 Telemetric Memory**: Replay and perspective simulation UI driven by `flow_vector` task lineage breadcrumbs.
