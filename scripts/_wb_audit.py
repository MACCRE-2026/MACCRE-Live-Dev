"""Full workbook audit — reads all key fields and traces payload flow."""
import sys
import os

os.environ["PYTHONIOENCODING"] = "utf-8"
sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
sys.path.insert(0, "B:/MACCREv2")

from maccre_core._vendor.openpyxl import load_workbook  # noqa: E402


def clean(s: str) -> str:
    return "".join(c if ord(c) < 128 else "?" for c in s)


wb = load_workbook("B:/MACCREv2/MACCRE_Global.xlsx", data_only=True)


def _hmap(ws):  # type: ignore[no-untyped-def]
    result: dict[str, int] = {}
    for ci, cell in enumerate(ws[2], start=1):
        h = clean(str(cell.value or "")).strip().upper().replace(" ", "_").strip("_?* ")
        if h:
            result[h] = ci
    return result


# ── PROJECT_DEFINITION ────────────────────────────────────────────────────────
print("=== PROJECT_DEFINITION ===")
ws = wb["PROJECT_DEFINITION"]
for row in ws.iter_rows(min_row=3, max_row=12, values_only=True):
    if row[0]:
        k = clean(str(row[0])).strip()
        v = clean(str(row[1] or "")).strip()
        print(f"  {k}: {v}")

# ── SWARM_REQUEST ─────────────────────────────────────────────────────────────
print()
print("=== SWARM_REQUEST ===")
ws = wb["SWARM_REQUEST"]
hm = _hmap(ws)
row3 = list(ws.iter_rows(min_row=3, max_row=3, values_only=True))[0]

for name, ci in sorted(hm.items(), key=lambda x: x[1]):
    if "REFERENCE" in name:
        continue
    if ci <= len(row3):
        val = row3[ci - 1]
        if val is not None:
            sv = clean(str(val))
            if "PAYLOAD_TEXT" in name:
                byte_len = len(sv.encode("utf-8"))
                print(f"  {name}: [{byte_len:,} bytes / {len(sv):,} chars]")
                print(f"    First 150 chars: {sv[:150]}")
            else:
                print(f"  {name}: {sv[:100]}")

# ── AGENTS ────────────────────────────────────────────────────────────────────
print()
print("=== AGENTS ===")
ws = wb["AGENTS"]
hm = _hmap(ws)
for row in ws.iter_rows(min_row=3, max_row=15, values_only=True):
    name_ci = hm.get("AGENT_NAME", 1)
    if not row or len(row) < name_ci or not row[name_ci - 1]:
        continue
    name  = clean(str(row[name_ci - 1]))
    model = clean(str(row[hm["MODEL"] - 1] or "")) if "MODEL" in hm else ""
    tools = clean(str(row[hm["TOOLS"] - 1] or "")) if "TOOLS" in hm else ""
    temp  = row[hm["TEMPERATURE"] - 1] if "TEMPERATURE" in hm else ""
    print(f"  {name} | model={model} | temp={temp} | tools={tools[:70]}")

# ── TOPOLOGY ──────────────────────────────────────────────────────────────────
print()
print("=== TOPOLOGY ===")
ws = wb["TOPOLOGY"]
hm = _hmap(ws)
for row in ws.iter_rows(min_row=3, max_row=12, values_only=True):
    nid_ci = hm.get("NODE_ID", 1)
    if not row or len(row) < nid_ci or not row[nid_ci - 1]:
        continue
    node_id  = clean(str(row[nid_ci - 1]))
    agent    = clean(str(row[hm["AGENT_NAME"] - 1] or "")) if "AGENT_NAME" in hm else "?"
    nxt      = clean(str(row[hm["NEXT_NODE"] - 1]  or "")) if "NEXT_NODE"  in hm else "?"
    temp     = row[hm["TEMPERATURE"] - 1]    if "TEMPERATURE"   in hm else ""
    max_rec  = row[hm["MAX_RECURSION"] - 1]  if "MAX_RECURSION" in hm else "?"
    wait_for = clean(str(row[hm["WAIT_FOR"] - 1] or "")) if "WAIT_FOR" in hm else ""
    print(f"  {node_id} -> {nxt} | agent={agent} | temp={temp} | max_rec={max_rec} | wait={wait_for}")
