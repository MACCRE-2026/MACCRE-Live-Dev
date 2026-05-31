"""
Gemma1 via the MACCREv2 Swarm Engine.

Uses admin_tools.ignite_swarm (queue the job) + admin_tools.run_swarm
(UniversalSwarmWorker execution loop) — the same code path the MCP tools call.
Agents and topology are already written to the Gemma1 silo.
"""
from __future__ import annotations
import os
import sys
sys.path.insert(0, "B:/MACCREv2")
os.environ.setdefault("MACCRE_ROOT", "B:/MACCREv2")
os.environ["MACCRE_ACTIVE_PROJECT"] = "Gemma1"

from maccre_core.tools.admin_tools import mint_agent, build_topology, ignite_swarm, run_swarm
from maccre_core.utils.path_resolver import get_datacenter_path

# ── 1. Mint both agents ───────────────────────────────────────────────────────
multiplier_prompt = (
    "You are a math worker node in a Gemma4-31B compute swarm.\n"
    "Read the context you receive (a growing log of NODE_RESULT lines from previous nodes).\n"
    "Count existing NODE_RESULT lines — your node number N = count + 1.\n"
    "Steps:\n"
    "  1. Choose A = (N * 7919) % 8999 + 1000 and B = (N * 6271) % 8999 + 1000.\n"
    "  2. Multiply A * B step by step showing partial products.\n"
    "  3. Append this line verbatim: NODE_RESULT: node{N} | {A}x{B} | {product}\n"
    "  4. Output the ENTIRE log: all previous NODE_RESULT lines plus your new one."
)

aggregator_prompt = (
    "You are the aggregator node (Node 11) in a Gemma4-31B compute swarm.\n"
    "You receive a log with exactly 10 NODE_RESULT lines in format:\n"
    "  NODE_RESULT: nodeN | AxB | product\n"
    "Your tasks:\n"
    "  1. List each node, its multiplication problem (AxB), and the reported product.\n"
    "  2. Add all 10 products and divide by 10 to compute the mean.\n"
    "  3. Show your arithmetic step by step.\n"
    "  4. End your reply with exactly: SWARM_AVERAGE: <integer_mean>"
)

print(mint_agent("GemmaMultiplier", "gemma-4-31b-it", multiplier_prompt, tools_string="none"))
print(mint_agent("GemmaAggregator", "gemma-4-31b-it", aggregator_prompt, tools_string="none"))

# ── 2. Build 11-node sequential topology ──────────────────────────────────────
#  7-col format: Node_ID, Agent_Name, Model_Override, Wait_For,
#                Next_Node, Temperature, Instruction_Override
nodes: list[list[str]] = []
for i in range(1, 11):
    nxt = f"MULTIPLY_{i+1}" if i < 10 else "AGGREGATE"
    nodes.append([
        f"MULTIPLY_{i}", "GemmaMultiplier", "gemma-4-31b-it", "",
        nxt, "1.0",
        f"You are worker node {i}. Compute N={i}: A=(N*7919)%8999+1000, B=(N*6271)%8999+1000. "
        f"Append NODE_RESULT: node{i} | {{A}}x{{B}} | {{product}} to the log.",
    ])
nodes.append([
    "AGGREGATE", "GemmaAggregator", "gemma-4-31b-it", "",
    "STOP", "0.1",
    "Average all 10 NODE_RESULT products. End with SWARM_AVERAGE: <value>",
])
print(build_topology(nodes))

# ── 3. Write payload to 01_Raw_Source and ignite ──────────────────────────────
payload_file = "gemma1_payload.md"
payload_path = get_datacenter_path("01_Raw_Source", payload_file)
payload_path.write_text(
    "# Gemma1 Multiplication Swarm\n\n"
    "BEGIN SWARM. No NODE_RESULT lines yet. Log is empty.\n"
    "Node 1: you are first. Start the log.\n",
    encoding="utf-8",
)
print(f"Payload written -> {payload_path}")
print(ignite_swarm(payload_file, starting_node="MULTIPLY_1"))

# ── 4. Execute via UniversalSwarmWorker (same as MCP run_swarm) ───────────────
print("\nRunning swarm... (11 nodes x gemma-4-31b-it, may take several minutes)\n")
result = run_swarm(project_name="Gemma1", max_cycles=200, timeout_seconds=1800)
print(result)
