import sys, io, sqlite3, pathlib, os
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.path.insert(0, '.')
import maccre_core
os.environ['MACCRE_ACTIVE_PROJECT'] = 'EXO_TEST'
from maccre_core.utils.path_resolver import get_maccre_root

root = get_maccre_root()

# Locate queue DB
db = root / '__DATACENTER' / 'EXO_TEST' / 'swarm_queue.db'
if not db.exists():
    for f in root.rglob('swarm_queue.db'):
        db = f
        break

print(f'Queue DB: {db}')
print()

with sqlite3.connect(str(db)) as conn:
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        'SELECT job_id, current_node, lock_status, locked_by, payload_path, '
        'actual_cost, loop_iteration_count, created_at '
        'FROM task_queue ORDER BY id DESC LIMIT 30'
    ).fetchall()
    print(f'{"LOCK":10s}  {"NODE":25s}  {"LOCKED_BY":30s}  {"COST":>10s}  CREATED')
    print('-' * 110)
    for r in rows:
        lk  = str(r['lock_status'])
        nd  = str(r['current_node'])
        lb  = str(r['locked_by'] or '-')[:28]
        cst = f"${r['actual_cost']:.5f}"
        cr  = str(r['created_at'])
        print(f'{lk:10s}  {nd:25s}  {lb:30s}  {cst:>10s}  {cr}')

# Ledger check
print()
ledger_dir = root / '__DATACENTER' / 'EXO_TEST' / '03_Agent_Ledgers'
if ledger_dir.exists():
    files = sorted(ledger_dir.rglob('*.json'), key=lambda x: x.stat().st_mtime, reverse=True)
    print(f'Ledger files ({len(files)} total):')
    for f in files[:8]:
        print(f'  {f.name:50s}  {f.stat().st_size:>8d} bytes')
else:
    print('No ledger directory found yet.')

# Artifacts check
art_dir = root / '__DATACENTER' / 'EXO_TEST' / '04_Code_Artifacts'
if art_dir.exists():
    arts = sorted(art_dir.rglob('*'), key=lambda x: x.stat().st_mtime if x.is_file() else 0, reverse=True)
    arts = [a for a in arts if a.is_file()]
    if arts:
        print()
        print(f'04_Code_Artifacts ({len(arts)} files):')
        for f in arts[:10]:
            print(f'  {f.name:45s}  {f.stat().st_size:>8d} bytes')
