import json
import pathlib

data = json.loads(pathlib.Path("B:/MACCREv2/scripts/model_capability_map.json").read_text(encoding="utf-8"))
for m in data:
    live = m["liveness"]
    live_str = "YES" if live.get("live") is True else ("N/A" if live.get("live") == "N/A" else "NO")
    methods = ",".join(m["supportedMethods"])[:50]
    name = m["name"]
    ctx = str(m["inputTokenLimit"])
    out = str(m["outputTokenLimit"])
    print(f"{name:55} ctx={ctx:>8} out={out:>6} live={live_str}  [{methods}]")
