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
import sqlite3
import struct
import json
from contextlib import contextmanager
from typing import Any, Dict, Generator, List
from maccre_core.utils.path_resolver import get_maccre_root

try:
    import sqlite_vec as _sqlite_vec
    _SQLITE_VEC_AVAILABLE = True
except ImportError:
    _sqlite_vec = None  # type: ignore[assignment]
    _SQLITE_VEC_AVAILABLE = False


def pack_vec(*floats: float) -> bytes:
    """Packs floats into the binary format required by sqlite_vec."""
    return struct.pack('%sf' % len(floats), *floats)

def unpack_vec(blob: bytes) -> List[float]:
    """Unpacks binary sqlite_vec format back into python floats."""
    return list(struct.unpack('%sf' % (len(blob) // 4), blob))

@contextmanager
def get_pin_db(project_name: str) -> Generator[sqlite3.Connection, None, None]:
    """
    Yields an active sqlite3 connection hooked to the active project's thought_pins.db
    with sqlite-vec fully enabled. Ensures schemas are verified.
    """
    ctx_dir = get_maccre_root() / "__DATACENTER" / project_name / "02_Dynamic_Context"
    ctx_dir.mkdir(parents=True, exist_ok=True)
    db_path = ctx_dir / "thought_pins.db"

    conn = sqlite3.connect(str(db_path))
    if _SQLITE_VEC_AVAILABLE and _sqlite_vec is not None:
        conn.enable_load_extension(True)
        _sqlite_vec.load(conn)  # type: ignore[union-attr]
        conn.enable_load_extension(False)

    _init_schema(conn)
    try:
        yield conn
    finally:
        conn.close()

def _init_schema(conn: sqlite3.Connection) -> None:
    """Initializes the VEC and FTS5 tables if they don't exist."""
    c = conn.cursor()
    # Metatadata layer anchoring the system
    c.execute('''
        CREATE TABLE IF NOT EXISTS pin_meta (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            doc_id TEXT UNIQUE,
            collection_name TEXT,
            ingested_at TEXT,
            metadata_json TEXT
        )
    ''')
    # Semantic layer (256-dim for gemini-embedding-001)
    c.execute('''
        CREATE VIRTUAL TABLE IF NOT EXISTS pin_vec USING vec0(
            id INTEGER PRIMARY KEY,
            embedding float[256]
        )
    ''')
    # Lexical layer
    c.execute('''
        CREATE VIRTUAL TABLE IF NOT EXISTS pin_fts USING fts5(
            doc_id UNINDEXED,
            text,
            tags
        )
    ''')
    conn.commit()

def upsert_pin(project_name: str, doc_id: str, collection_name: str, text: str, 
               tags: str, vector: List[float], metadata: Dict[str, Any], ingested_at: str) -> None:
    """Atomically upserts a vector into the hybrid DB."""
    with get_pin_db(project_name) as conn:
        c = conn.cursor()
        
        # Check if exists
        c.execute('SELECT id FROM pin_meta WHERE doc_id = ?', (doc_id,))
        row = c.fetchone()
        
        meta_json = json.dumps(metadata)
        vec_bytes = pack_vec(*vector)
        
        if row:
            internal_id = row[0]
            c.execute('UPDATE pin_meta SET collection_name=?, ingested_at=?, metadata_json=? WHERE id=?', 
                      (collection_name, ingested_at, meta_json, internal_id))
            c.execute('UPDATE pin_fts SET text=?, tags=? WHERE rowid=?', (text, tags, internal_id))
            c.execute('UPDATE pin_vec SET embedding=? WHERE id=?', (vec_bytes, internal_id))
        else:
            c.execute('INSERT INTO pin_meta (doc_id, collection_name, ingested_at, metadata_json) VALUES (?, ?, ?, ?)',
                      (doc_id, collection_name, ingested_at, meta_json))
            internal_id = c.lastrowid
            # Standard rowid maps across all tables
            c.execute('INSERT INTO pin_fts (rowid, doc_id, text, tags) VALUES (?, ?, ?, ?)', 
                      (internal_id, doc_id, text, tags))
            c.execute('INSERT INTO pin_vec (id, embedding) VALUES (?, ?)', 
                      (internal_id, vec_bytes))
        conn.commit()

def query_hybrid(project_name: str, collection_name: str, query_vector: List[float], n_results: int = 5) -> List[Dict[str, Any]]:
    """Runs a Semantic KNN search against the SQLite Vec0 engine."""
    with get_pin_db(project_name) as conn:
        c = conn.cursor()
        vec_bytes = pack_vec(*query_vector)
        
        # We query VEC0 for mathematical cosine similarity, then JOIN meta and fts for readable output
        c.execute('''
            SELECT 
                m.doc_id,
                vec_distance_cosine(v.embedding, ?) as distance,
                f.text,
                m.metadata_json
            FROM pin_vec v
            JOIN pin_meta m ON v.id = m.id
            JOIN pin_fts f ON v.id = f.rowid
            WHERE m.collection_name = ?
            ORDER BY distance ASC
            LIMIT ?
        ''', (vec_bytes, collection_name, n_results))
        
        results: list[dict[str, Any]] = []
        for row in c.fetchall():
            results.append({
                "doc_id": row[0],
                "distance": row[1],
                "text": row[2],
                "metadata": json.loads(row[3]) if row[3] else {},
            })
        return results

def delete_pin(project_name: str, doc_id: str) -> bool:
    """Removes a pin atomically from all 3 tables."""
    with get_pin_db(project_name) as conn:
        c = conn.cursor()
        c.execute('SELECT id FROM pin_meta WHERE doc_id = ?', (doc_id,))
        row = c.fetchone()
        if not row:
            return False
        internal_id = row[0]
        c.execute('DELETE FROM pin_fts WHERE rowid = ?', (internal_id,))
        c.execute('DELETE FROM pin_vec WHERE id = ?', (internal_id,))
        c.execute('DELETE FROM pin_meta WHERE id = ?', (internal_id,))
        conn.commit()
        return True
