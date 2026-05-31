import sys
import os
sys.path.insert(0, "B:/MACCREv2")
os.environ["MACCRE_ROOT"] = "B:/MACCREv2"
os.environ["MACCRE_ACTIVE_PROJECT"] = "GLOBAL"

from maccre_core.patterns import list_patterns, get_pattern

patterns = list_patterns()
print("=== REGISTERED PATTERNS ===")
for p in patterns:
    print(f"  {p['name']:25} | nodes={p['node_count']:3} | cost=${p['estimated_cost_usd']:.3f}")

print()
sr = get_pattern("shift_register")
print(f"=== shift_register TOPOLOGY ({len(sr.nodes)} nodes) ===")
for n in sr.nodes:
    print(f"  {n.node_id:15} -> {n.next_node:20} | agent={n.agent_name:15} | temp={n.temperature}")

print()
print("Roster agents:", [e["Agent_Name"] for e in sr.agent_roster_entries])
