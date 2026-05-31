"""One-shot: extract the write_file payload from FinalDirector's ledger and write it."""
import re
import pathlib

ledger_path = pathlib.Path(
    r"B:\MACCREv2\__DATACENTER\WeatherDebate\03_Agent_Ledgers\job_52441ad8\FinalDirector_76.md"
)
out_path = pathlib.Path(
    r"B:\MACCREv2\__DATACENTER\WeatherDebate\05_Rendered_Media\weather_expert_report.md"
)

raw = ledger_path.read_text(encoding="utf-8")

# The tool call format is: [TOOL CALL REQUESTED: write_file - {'path': '...', 'data': '...'}]
# Pull everything after "'data': '" up to the closing '}]'
m = re.search(r"'data':\s*'(.*?)'\}\]$", raw, re.DOTALL)
if not m:
    print("[FAIL] Could not locate 'data' key in ledger. Dumping raw:")
    print(raw[:500])
else:
    content = m.group(1)
    # Unescape the escaped sequences the model embedded
    content = content.replace("\\n", "\n").replace("\\'", "'").replace('\\"', '"')
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(content, encoding="utf-8")
    print(f"[OK] Expert report written → {out_path}")
    print(f"     Size: {out_path.stat().st_size:,} bytes")
    print("\n--- PREVIEW (first 300 chars) ---")
    print(content[:300])
