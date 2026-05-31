import csv, io
from pathlib import Path

roster_path = Path("B:/MACCREv2/__DATACENTER/NewsNexus/agent_roster.csv")
text = roster_path.read_text(encoding="utf-8")

replacements = {
    "gemini-2.5-flash-preview-04-17": "gemini-2.5-flash",
    "gemini-2.5-pro-preview-05-06": "gemini-3.1-pro-preview",
}

for old, new in replacements.items():
    text = text.replace(old, new)

roster_path.write_text(text, encoding="utf-8")

reader = csv.DictReader(io.StringIO(text))
for row in reader:
    if row.get("Agent_Name"):
        print(f"{row['Agent_Name']}: {row['Model']}")
print("Done.")
