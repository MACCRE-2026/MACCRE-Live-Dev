import sys
import io
import sqlite3
import shutil
import os

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.path.insert(0, '.')
import maccre_core
os.environ['MACCRE_ACTIVE_PROJECT'] = 'EXO_TEST'
from maccre_core.utils.path_resolver import get_maccre_root
from pathlib import Path

dc = get_maccre_root() / '__DATACENTER' / 'EXO_TEST'

# 1. Clear task_queue
qdb = dc / 'swarm_queue.db'
if qdb.exists():
    with sqlite3.connect(str(qdb)) as conn:
        count = conn.execute('SELECT COUNT(*) FROM task_queue').fetchone()[0]
        conn.execute('DELETE FROM task_queue')
        conn.commit()
    print(f'[QUEUE] Cleared {count} rows from task_queue')
else:
    print('[QUEUE] No queue DB found')

# 2. Wipe job subfolder ledgers
ledger_dir = dc / '03_Agent_Ledgers'
for child in ledger_dir.iterdir():
    if child.is_dir() and child.name.startswith('job_'):
        shutil.rmtree(child)
        print(f'[LEDGERS] Removed {child.name}/')
    elif child.is_file():
        child.unlink()
        print(f'[LEDGERS] Removed {child.name}')

# 3. Wipe job subfolder artifacts
art_dir = dc / '04_Code_Artifacts'
for child in art_dir.iterdir():
    if child.is_dir() and child.name.startswith('job_'):
        shutil.rmtree(child)
        print(f'[ARTIFACTS] Removed {child.name}/')
    elif child.is_file():
        child.unlink()
        print(f'[ARTIFACTS] Removed {child.name}')

# 4. Clear memory / telemetry DBs
telem_dir = dc / 'telemetry'
if telem_dir.exists():
    for db_path in telem_dir.glob('*.db'):
        try:
            with sqlite3.connect(str(db_path)) as conn:
                table_q = "SELECT name FROM sqlite_master WHERE type='table'"
                tables = [row[0] for row in conn.execute(table_q).fetchall()]
                for tbl in tables:
                    conn.execute(f'DELETE FROM [{tbl}]')
                conn.commit()
            print(f'[MEMORY] Cleared {db_path.name}')
        except Exception as exc:
            print(f'[MEMORY] Could not clear {db_path.name}: {exc}')

# 5. Wipe ChromaDB
chroma = dc / 'chroma_db'
if chroma.exists():
    shutil.rmtree(chroma)
    chroma.mkdir(parents=True, exist_ok=True)
    print('[CHROMA] ChromaDB wiped and recreated')

# 6. Clear memory pins directory if it exists
for pins_dir in (dc / '06_Memory_Pins',):
    if pins_dir.exists():
        for child in pins_dir.iterdir():
            if child.is_file():
                child.unlink()
                print(f'[PINS] Removed {child.name}')

print()
print('[RESET COMPLETE] EXO_TEST is clean. Ready for fresh launch.')
