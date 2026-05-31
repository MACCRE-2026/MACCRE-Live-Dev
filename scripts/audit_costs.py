"""
scripts/audit_costs.py
Audit all telemetry DB and ledger logs for cost data from the last 7 days.
Compare against the $19.00 figure in the billing chart (Apr 18-24, 2026).
"""
import sqlite3
import pathlib
from datetime import datetime

cutoff = datetime(2026, 4, 17)  # 7 days back from Apr 24

DATACENTER = pathlib.Path("B:/MACCREv2/__DATACENTER")

# ── 1. Scan all system_logs.db files across ALL project silos ─────────────────
total_actual_cost = 0.0
total_log_cost    = 0.0
per_day: dict[str, float] = {}
per_model: dict[str, float] = {}
sessions_seen: set[str] = set()
db_files: list[pathlib.Path] = []

for db in DATACENTER.rglob("system_logs.db"):
    db_files.append(db)
    try:
        con = sqlite3.connect(str(db))
        con.row_factory = sqlite3.Row
        rows = con.execute(
            "SELECT timestamp, cost, model_id, session_id, action_type, payload "
            "FROM system_logs WHERE timestamp >= ? ORDER BY timestamp",
            (cutoff.isoformat(),),
        ).fetchall()
        for row in rows:
            cost = float(row["cost"] or 0.0)
            total_log_cost += cost
            day = str(row["timestamp"])[:10]
            per_day[day] = per_day.get(day, 0.0) + cost
            model = (row["model_id"] or "unknown").strip()
            per_model[model] = per_model.get(model, 0.0) + cost
            if row["session_id"]:
                sessions_seen.add(row["session_id"])
        con.close()
    except Exception as e:
        print(f"  [WARN] {db}: {e}")

# ── 2. Scan swarm_queue.db for actual_cost column ─────────────────────────────
queue_cost = 0.0
for db in DATACENTER.rglob("swarm_queue.db"):
    try:
        con = sqlite3.connect(str(db))
        rows = con.execute(
            "SELECT actual_cost, created_at, current_node, job_id "
            "FROM task_queue "
            "ORDER BY created_at DESC LIMIT 200"
        ).fetchall()
        for row in rows:
            c = float(row[0] or 0.0)
            queue_cost += c
        con.close()
    except Exception as e:
        print(f"  [WARN queue] {db}: {e}")

# ── 3. Scan Agent Ledger markdown files for "Billed Cost" lines ──────────────
ledger_cost = 0.0
ledger_lines: list[tuple[str, float]] = []
for f in DATACENTER.rglob("*.md"):
    try:
        mtime = datetime.fromtimestamp(f.stat().st_mtime)
        if mtime < cutoff:
            continue
        for line in f.read_text(encoding="utf-8", errors="ignore").splitlines():
            if "Billed Cost" in line or "billed_cost" in line.lower():
                import re
                m = re.search(r"\$?([\d]+\.[\d]+)", line)
                if m:
                    c = float(m.group(1))
                    ledger_cost += c
                    ledger_lines.append((f.name, c))
    except Exception:
        pass

# ── Report ───────────────────────────────────────────────────────────────────

print(f"DB files scanned: {len(db_files)}")
print(f"Sessions in DB:   {len(sessions_seen)}")
print("\n=== COST SUMMARY (Apr 18-24, 2026) ===")
print(f"  system_logs.db total:  ${total_log_cost:.6f}")
print(f"  swarm_queue actual:    ${queue_cost:.6f}")
print(f"  Ledger Billed Cost:    ${ledger_cost:.6f}")
print("  -------------------------")
print("  Google billing chart:  $19.00")
print(f"  Our tracked total:     ${total_log_cost + ledger_cost:.4f}")
print(f"  DELTA (untracked):     ${19.00 - (total_log_cost + ledger_cost):.4f}")

print("\n=== COST BY DAY ===")
for day in sorted(per_day):
    print(f"  {day}:  ${per_day[day]:.4f}")

print("\n=== COST BY MODEL (top 15) ===")
for model, cost in sorted(per_model.items(), key=lambda x: -x[1])[:15]:
    print(f"  {model:50} ${cost:.6f}")

print("\n=== LEDGER BILLED COST (last 20 entries) ===")
for fname, cost in ledger_lines[-20:]:
    print(f"  {fname:40} ${cost:.6f}")
