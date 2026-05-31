from __future__ import annotations
import sys
import os
sys.path.insert(0, "B:/MACCREv2")
os.environ["MACCRE_ROOT"] = "B:/MACCREv2"
os.environ["MACCRE_ACTIVE_PROJECT"] = "PATTERN_shift_register_4d3ce656"

JOB_ID = "pat_shift_register_4d3ce656"
SILO   = "PATTERN_shift_register_4d3ce656"

from maccre_core.tools.admin_tools import run_swarm
from maccre_core.patterns.pattern_executor import PatternExecutor

print(f"Running shift_register swarm v3 (17 nodes, S3 chain accumulation, silo={SILO})")
result = run_swarm(project_name=SILO, max_cycles=500, timeout_seconds=3600)
print(result)

print("\n=== Polling HUMAN_GATE ===")
executor = PatternExecutor()
packet = executor.poll_gate(JOB_ID, SILO)
print(packet)
