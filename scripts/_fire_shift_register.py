"""
Live smoke-fire of the shift_register pattern via pattern_executor.
Uses a lightweight coding problem so results are meaningful but fast.
"""
from __future__ import annotations
import sys
import os
sys.path.insert(0, "B:/MACCREv2")
os.environ["MACCRE_ROOT"] = "B:/MACCREv2"
os.environ["MACCRE_ACTIVE_PROJECT"] = "GLOBAL"

from maccre_core.patterns.pattern_executor import PatternExecutor

PAYLOAD = """## Shift Register Input

**Problem Statement:**
Design a lightweight job-queue system for MACCREv2 that replaces the current
SQLite swarm_queue.db approach. The queue must handle concurrent workers,
support job prioritization, survive process restarts, and provide real-time
status visibility without adding external infrastructure dependencies.

**Relevant Context / Constraints:**
- MACCREv2 runs on Windows, must be cross-platform compatible
- No Redis, RabbitMQ, or other external brokers allowed
- Current SQLite queue works but has WAL contention under concurrent writers
- Must integrate with existing UniversalSwarmWorker and LocalMessageBroker ABCs

**Non-Negotiables:**
- Zero new pip dependencies that aren't already in the venv
- Must survive a Python process crash without data loss
- Must be inspectable/debuggable without a special GUI

**What Antigravity wants from the swarm:**
Three genuinely different architectural approaches. I want to see what disagrees
between them — the cross-pollination is the point.
"""

print("=== Firing shift_register pattern ===")
executor = PatternExecutor()
result = executor.submit("shift_register", PAYLOAD, cost_limit_usd=2.0)
print(f"Job ID   : {result['job_id']}")
print(f"Silo     : {result['silo_project']}")
print(f"Est. cost: ${result['estimated_cost_usd']:.3f}")
print(f"Topology : {result['topology_path']}")
print()
print("Swarm running... poll with:")
print(f"  executor.poll_gate('{result['job_id']}', '{result['silo_project']}')")
