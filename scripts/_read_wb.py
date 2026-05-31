"""Read workbook state - ASCII-safe output."""
import sys
import os

os.environ["PYTHONIOENCODING"] = "utf-8"
sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
sys.path.insert(0, "B:/MACCREv2")

from maccre_core._vendor.openpyxl import load_workbook  # noqa: E402

wb = load_workbook("B:/MACCREv2/MACCRE_Global.xlsx", data_only=True)


def clean(s: str) -> str:
    return "".join(c if ord(c) < 128 else "?" for c in s)


print("=== SWARM_REQUEST (row 3) ===")
ws = wb["SWARM_REQUEST"]
for ci, cell in enumerate(ws[2], start=1):
    h = clean(str(cell.value or "").strip())
    v = clean(str(ws.cell(row=3, column=ci).value or "").strip())
    if h and "REFERENCE" not in h.upper():
        display_v = v[:80] + ("..." if len(v) > 80 else "")
        print(f"  col {ci:2d}: [{h[:35]:<35}] = {display_v}")
    elif not h and v:
        print(f"  col {ci:2d}: [NO HEADER] = {v[:70]}")

print()
print("=== TOPOLOGY (rows 3-8, first 10 cols) ===")
ws = wb["TOPOLOGY"]
headers = []
for cell in ws[2]:
    h = clean(str(cell.value or "").strip())
    headers.append("" if "REFERENCE" in h.upper() else h)

print("  Headers:", headers[:10])
print()
for row in ws.iter_rows(min_row=3, max_row=8, values_only=True):
    if any(row[:10]):
        parts = []
        for i, v in enumerate(row[:10]):
            hdr = headers[i][:10] if i < len(headers) else f"c{i}"
            sv = clean(str(v or ""))[:28] if v else "-"
            parts.append(f"{hdr}={sv}")
        print(" ", parts)
