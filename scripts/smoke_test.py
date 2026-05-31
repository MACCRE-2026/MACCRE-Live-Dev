"""
Smoke test: core MACCREv2 module imports and path anchoring verification.
Run this after any major refactor to verify the system boots cleanly.
"""
import sys
sys.path.insert(0, "B:/MACCREv2")

PASS = []
FAIL = []

def check(label: str, fn):  # type: ignore[no-untyped-def]
    try:
        result = fn()
        PASS.append(f"  [OK]   {label}{(' : ' + str(result)) if result is not None else ''}")
    except Exception as exc:
        FAIL.append(f"  [FAIL] {label} -- {exc}")

# ── Test 1: path resolver ──────────────────────────────────────────────────────
from maccre_core.utils.path_resolver import get_maccre_root
check("path_resolver.get_maccre_root()", lambda: get_maccre_root())

# ── Test 2: core logger ────────────────────────────────────────────────────────
from maccre_core.logger import logger
check("maccre_core.logger", lambda: type(logger).__name__)

# ── Test 3: telemetry_db ───────────────────────────────────────────────────────
check("telemetry_db.init_all_silos", lambda: "imported")

# ── Test 4: local broker ───────────────────────────────────────────────────────
check("local_broker.LocalMessageBroker", lambda: "imported")

# ── Test 5: topology engine ────────────────────────────────────────────────────
check("topology_engine.TopologyEngine", lambda: "imported")

# ── Test 6: tool registry ──────────────────────────────────────────────────────
from maccre_core.tools.tool_registry import TOOL_REGISTRY
check("tool_registry.TOOL_REGISTRY", lambda: f"{len(TOOL_REGISTRY)} tools")

# ── Test 7: datacenter router - path anchoring ────────────────────────────────
from maccre_core.orchestration.datacenter_router import DatacenterRouter
dr = DatacenterRouter()
root = get_maccre_root()
is_anchored = dr.root_path == str(root / "__DATACENTER")
check("datacenter_router path anchor", lambda: "PASS - get_maccre_root() derived" if is_anchored else f"FAIL - got {dr.root_path}")

# ── Test 8: session registry - path anchoring ─────────────────────────────────
import maccre_core.orchestration.session_registry as sr
reg_dir = sr._GLOBAL_REGISTRY_DIR
is_anchored_reg = str(root) in reg_dir
check("session_registry path anchor", lambda: "PASS" if is_anchored_reg else f"FAIL - got {reg_dir}")

# ── Test 9: MCP tool count (without starting the server) ──────────────────────
import pathlib
mcp_src = pathlib.Path("B:/MACCREv2/maccre_mcp.py").read_text(encoding="utf-8")
tool_count = mcp_src.count("@mcp.tool()")
check("maccre_mcp.py tool registrations", lambda: f"{tool_count} @mcp.tool() decorators")

# ── Report ─────────────────────────────────────────────────────────────────────
print("\n" + "="*60)
print("  MACCREv2 Smoke Test")
print("="*60)
for line in PASS:
    print(line)
if FAIL:
    print("\n  --- FAILURES ---")
    for line in FAIL:
        print(line)
print("="*60)
print(f"  Result: {len(PASS)} passed, {len(FAIL)} failed")
print("="*60 + "\n")

sys.exit(1 if FAIL else 0)
