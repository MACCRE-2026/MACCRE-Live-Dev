"""
scripts/fix_queue_ghost.py
Clears stale/pending queue rows that belong to a different project,
so the SilmLOTR swarm can claim its own slot cleanly.
"""
import sqlite3
import pathlib

SILMLOTR_DIR = pathlib.Path("B:/MACCREv2/__DATACENTER/SilmLOTR")

dbs_to_check = [
    SILMLOTR_DIR / "swarm_queue.db",
    pathlib.Path("B:/MACCREv2/__DATACENTER/swarm_queue.db"),
]

for db_path in dbs_to_check:
    if not db_path.exists():
        print(f"SKIP (not found): {db_path}")
        continue

    con = sqlite3.connect(str(db_path))
    tables = [r[0] for r in con.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    ).fetchall()]
    print(f"\nDB: {db_path}")
    print(f"  Tables: {tables}")

    for t in tables:
        cols = [r[1] for r in con.execute(f"PRAGMA table_info({t})").fetchall()]
        rows = con.execute(f"SELECT rowid, * FROM {t} ORDER BY rowid DESC LIMIT 10").fetchall()
        print(f"  Table '{t}' columns: {cols}")
        for r in rows:
            print(f"    {r}")

    # Cancel any pending rows that are NOT for SilmLOTR
    status_col = None
    project_col = None
    if "queue" in [t.lower() for t in tables]:
        actual_table = next(t for t in tables if t.lower() == "queue")
        cols = [r[1] for r in con.execute(f"PRAGMA table_info({actual_table})").fetchall()]
        status_col = next((c for c in cols if "status" in c.lower()), None)
        project_col = next((c for c in cols if "project" in c.lower()), None)
        if status_col and project_col:
            n = con.execute(
                f"UPDATE {actual_table} SET {status_col}='CANCELLED_GHOST' "
                f"WHERE {status_col} IN ('PENDING','QUEUED') AND {project_col} != 'SilmLOTR'"
            ).rowcount
            con.commit()
            print(f"  Cancelled {n} ghost rows from table '{actual_table}'")

    # Also try 'swarm_queue' as table name  
    for t in tables:
        cols = [r[1] for r in con.execute(f"PRAGMA table_info({t})").fetchall()]
        col_lower = [c.lower() for c in cols]
        if "status" in col_lower and any("project" in c or "node" in c for c in col_lower):
            status_c = cols[col_lower.index("status")]
            node_c = next((cols[i] for i, c in enumerate(col_lower) if "start_node" in c), None)
            proj_c = next((cols[i] for i, c in enumerate(col_lower) if "project" in c), None)
            if proj_c and status_c:
                n = con.execute(
                    f"UPDATE {t} SET {status_c}='CANCELLED_GHOST' "
                    f"WHERE {status_c} IN ('PENDING','QUEUED') AND {proj_c} != 'SilmLOTR'"
                ).rowcount
                con.commit()
                if n:
                    print(f"  Cancelled {n} ghost rows from table '{t}' (project mismatch)")

    con.close()

print("\n[DONE] Queue ghost cleanup complete.")
