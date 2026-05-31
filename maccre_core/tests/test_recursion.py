# ┌─────────────────────────────────────────────────────────────────────────────┐
# │  MACCREv2 ENGINEERING DOCTRINE                             Law Rev: 19.0   │
# ├─────────────────────────────────────────────────────────────────────────────┤
# │  I.   TYPING      All signatures: explicit Python 3.11+ type hints.        │
# │  II.  LINTING     Zero unused imports. No wildcards. 120-char line max.    │
# │  III. PATHS       Never hardcode absolute paths. Use get_maccre_root().     │
# │                   Default params: def f(p:str='') -> None: p=p or root/x   │
# │  IV.  DATACENTER  5-Tier: 01_Raw_Source · 02_Dynamic_Context               │
# │                           03_Agent_Ledgers · 04_Code_Artifacts             │
# │                           05_Rendered_Media                                 │
# │  V.   DIAMOND     Gen: temp=1.0  ·  Critic: temp=0.1 + dataclass schema   │
# │  VI.  ABSTRACTION All I/O behind abc.ABC before any concrete driver.       │
# │  VII. TEARDOWN    try/finally on all handles (omni clean compliance).      │
# │  VIII.TELEMETRY   No bare print(). logger only. JSON → 03_Agent_Ledgers.  │
# └─────────────────────────────────────────────────────────────────────────────┘
import os
import sqlite3
from pathlib import Path
from maccre_core.orchestration.local_broker import LocalMessageBroker

def test_recursion_limit():
    db_path = str(Path("test_recursion_queue.db").absolute())
    if os.path.exists(db_path):
        os.remove(db_path)
        
    broker = LocalMessageBroker(db_path)
    job_id = "test_job_1"
    
    print("\n--- Phase 1: Epistemic Validation Test ---")
    broker.inject_task(job_id, "payload.md", starting_node="NODE_A")
    
    for i in range(1, 6):
        print(f"\n[Iteration {i}] Attempting Epistemic Bounce from B -> A...")
        
        # We simulate the worker resolving tasks and natively asking the broker to route
        # First we must grab the row_id of the current target
        with sqlite3.connect(db_path) as conn:
            cursor = conn.execute("SELECT id, current_node FROM task_queue WHERE lock_status='open'")
            row = cursor.fetchone()
            if not row:
                break
            
            row_id, node = row
            
        print(f"   > Discovered locked node: {node} (ID: {row_id})")
        # Route it to B, then B routes back to A (simulating a recursion fail)
        broker.route_task(row_id, job_id, "NODE_A", "payload.md")

    print("\n--- SQLite Boundary Dump Tracker ---")
    with sqlite3.connect(db_path) as conn:
        for row in conn.execute("SELECT current_node, loop_iteration_count, lock_status FROM task_queue"):
            print(f"Node: {str(row[0]).ljust(10)} | Iterations: {row[1]} | Status: {row[2]}")

if __name__ == "__main__":
    test_recursion_limit()
