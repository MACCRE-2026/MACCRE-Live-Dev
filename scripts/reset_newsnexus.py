"""scripts/reset_newsnexus.py — Reset NewsNexus project memory to clean state.

Clears:
  - chroma_db/            (contaminated vector store)
  - thought_pins.db       (fabricated OSINT thought pins)
  - swarm_queue.db        (stale job queue)
  - 04_Code_Artifacts/    (stale briefs, tier artifacts, editorial)

Preserves:
  - 03_Agent_Ledgers/     (forensic run history)
  - 05_Rendered_Media/    (produced broadcasts)
  - telemetry/            (cost and system logs)
  - topology.csv          (pipeline config)
  - agent_roster.csv      (agent config)
"""
import shutil
import sqlite3
from pathlib import Path

from maccre_core.utils.path_resolver import get_maccre_root

root = get_maccre_root() / "__DATACENTER" / "NewsNexus"


def _clear_table(db_path: Path) -> list[str]:
    """Truncate all tables in a SQLite DB, return list of table names."""
    with sqlite3.connect(db_path) as conn:
        tables: list[str] = [
            r[0] for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        ]
        for t in tables:
            conn.execute(f"DELETE FROM {t}")  # noqa: S608
        conn.commit()
    return tables


# ── 1. Chroma vector store ─────────────────────────────────────────────────
chroma = root / "chroma_db"
if chroma.exists():
    shutil.rmtree(chroma)
    print("[RESET] chroma_db/ deleted (contaminated vector store)")
else:
    print("[RESET] chroma_db/ not present — skipping")

# ── 2. Thought pins ────────────────────────────────────────────────────────
pins_db = root / "02_Dynamic_Context" / "thought_pins.db"
if pins_db.exists():
    pins_db.unlink()
    print("[RESET] thought_pins.db deleted (will recreate fresh on next run)")
else:
    print("[RESET] thought_pins.db not present — skipping")

# ── 3. Swarm queue ─────────────────────────────────────────────────────────
queue_db = root / "swarm_queue.db"
if queue_db.exists():
    tables = _clear_table(queue_db)
    print(f"[RESET] swarm_queue.db cleared   (tables: {tables})")
else:
    print("[RESET] swarm_queue.db not present — skipping")

# ── 4. Code artifacts ──────────────────────────────────────────────────────
artifacts = root / "04_Code_Artifacts"
cleared: list[str] = []
for f in artifacts.glob("*.md"):
    f.unlink()
    cleared.append(f.name)
if cleared:
    print(f"[RESET] 04_Code_Artifacts: removed {len(cleared)} stale files:")
    for name in cleared:
        print(f"         - {name}")
else:
    print("[RESET] 04_Code_Artifacts: already empty")

print()
print("[RESET COMPLETE] NewsNexus memory is clean.")
print("  Ledgers, media, telemetry, topology, and roster preserved.")
