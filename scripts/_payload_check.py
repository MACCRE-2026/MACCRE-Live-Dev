"""Check actual payload size in workbook cell (no data_only, full string)."""
import sys
import os

os.environ["PYTHONIOENCODING"] = "utf-8"
sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
sys.path.insert(0, "B:/MACCREv2")

from maccre_core._vendor.openpyxl import load_workbook  # noqa: E402

wb = load_workbook("B:/MACCREv2/MACCRE_Global.xlsx", data_only=False)
ws = wb["SWARM_REQUEST"]

print("=== SWARM_REQUEST raw cell scan ===")
for ci, cell in enumerate(ws[2], start=1):
    h = str(cell.value or "").strip()
    val = ws.cell(row=3, column=ci).value
    sv = str(val or "")
    byte_len = len(sv.encode("utf-8"))
    if "PAYLOAD" in h.upper() or "PROJECT" in h.upper() or "START" in h.upper():
        print(f"  Col {ci} [{h}]: {len(sv):,} chars / {byte_len:,} bytes")
        if sv:
            print(f"    START: {sv[:200]}")
            if len(sv) > 200:
                print(f"    END:   ...{sv[-100:]}")
    elif val:
        clean = "".join(c if ord(c) < 128 else "?" for c in sv)
        print(f"  Col {ci} [{h}]: {clean[:80]}")

print()
print("=== PROJECT_DEFINITION check ===")
ws2 = wb["PROJECT_DEFINITION"]
for row in ws2.iter_rows(min_row=3, max_row=8, values_only=True):
    if row[0]:
        print(f"  {row[0]}: {row[1]}")
