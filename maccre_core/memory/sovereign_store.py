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
"""
maccre_core/memory/sovereign_store.py
=======================================
SovereignPinStore — Zero-dependency SQLite FTS5 KnowledgeStore.

Replaces ChromaDB entirely. Zero PyPI requirements: uses only Python stdlib
sqlite3 (WAL-mode, FTS5) for full-text search + cosine similarity ranking.

Architecture:
  - One WAL-mode SQLite database per project at:
      __DATACENTER/<project>/02_Dynamic_Context/thought_pins.db
  - `pins` table: doc_id, collection, text, vector_blob, metadata_json, ingested_at
  - `pins_fts` FTS5 virtual table: full-text search over text field
  - Vector similarity: cosine distance computed in Python (no onnxruntime, no numpy)
  - Index is ALWAYS reconstructable from source documents — it is a derived artifact.
  - Rebuild: maccre.py reindex <project>

Roadmap: Phase 5 will replace the Python cosine loop with sqlite-vec native ops.
"""
from __future__ import annotations

import json
import sqlite3
import struct
import math
from pathlib import Path
from typing import Any

from maccre_core.memory.knowledge_store import KnowledgeStore, PinRecord


# ── Vector serialization (compact binary, no numpy) ─────────────────────────────

def _vec_to_blob(vector: list[float]) -> bytes:
    """Pack a float list to a compact binary blob (little-endian float32)."""
    return struct.pack(f"<{len(vector)}f", *vector)


def _blob_to_vec(blob: bytes) -> list[float]:
    """Unpack a binary blob back to a float list."""
    n = len(blob) // 4   # 4 bytes per float32
    return list(struct.unpack(f"<{n}f", blob))


def _cosine_distance(a: list[float], b: list[float]) -> float:
    """Compute cosine distance (0 = identical, 2 = opposite)."""
    if len(a) != len(b):
        return 2.0
    dot = sum(x * y for x, y in zip(a, b))
    mag_a = math.sqrt(sum(x * x for x in a))
    mag_b = math.sqrt(sum(y * y for y in b))
    if mag_a == 0.0 or mag_b == 0.0:
        return 2.0
    return 1.0 - (dot / (mag_a * mag_b))


# ── DDL ─────────────────────────────────────────────────────────────────────────

_DDL = """
PRAGMA journal_mode=WAL;
PRAGMA synchronous=NORMAL;

CREATE TABLE IF NOT EXISTS pins (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    doc_id        TEXT    NOT NULL,
    collection    TEXT    NOT NULL,
    text          TEXT    NOT NULL DEFAULT '',
    vector_blob   BLOB,
    metadata_json TEXT    NOT NULL DEFAULT '{}',
    ingested_at   TEXT    NOT NULL,
    UNIQUE(doc_id, collection)
);

CREATE INDEX IF NOT EXISTS idx_pins_collection ON pins(collection);
CREATE INDEX IF NOT EXISTS idx_pins_doc        ON pins(doc_id, collection);

CREATE VIRTUAL TABLE IF NOT EXISTS pins_fts USING fts5(
    doc_id,
    collection,
    text,
    content='pins',
    content_rowid='id'
);

-- Keep FTS in sync with pins table via triggers
CREATE TRIGGER IF NOT EXISTS pins_ai AFTER INSERT ON pins BEGIN
    INSERT INTO pins_fts(rowid, doc_id, collection, text)
    VALUES (new.id, new.doc_id, new.collection, new.text);
END;

CREATE TRIGGER IF NOT EXISTS pins_ad AFTER DELETE ON pins BEGIN
    INSERT INTO pins_fts(pins_fts, rowid, doc_id, collection, text)
    VALUES ('delete', old.id, old.doc_id, old.collection, old.text);
END;

CREATE TRIGGER IF NOT EXISTS pins_au AFTER UPDATE ON pins BEGIN
    INSERT INTO pins_fts(pins_fts, rowid, doc_id, collection, text)
    VALUES ('delete', old.id, old.doc_id, old.collection, old.text);
    INSERT INTO pins_fts(rowid, doc_id, collection, text)
    VALUES (new.id, new.doc_id, new.collection, new.text);
END;
"""


# ── SovereignPinStore ────────────────────────────────────────────────────────────

class SovereignPinStore(KnowledgeStore):
    """
    Sovereign SQLite FTS5 + vector store.

    Drop-in replacement for ChromaDBStore with zero external dependencies.
    Vectors are stored as binary blobs and ranked by cosine distance in Python.
    Full-text search uses SQLite's built-in FTS5 engine.
    """

    def __init__(
        self, 
        project_name: str, 
        db_name: str = "memory_pins.db",
        scope: str = "project",
        session_id: str = ""
    ) -> None:
        from maccre_core.utils.path_resolver import get_maccre_root  # noqa: PLC0415
        
        self._project = project_name
        self._scope = scope
        
        proj_dir = "GLOBAL" if scope == "global" else project_name
        
        db_dir = (
            get_maccre_root()
            / "__DATACENTER"
            / proj_dir
            / "02_Dynamic_Context"
        )
        
        if scope == "session":
            if not session_id:
                raise ValueError("session_id must be provided when scope is 'session'")
            db_dir = db_dir / "sessions" / session_id
        db_dir.mkdir(parents=True, exist_ok=True)
        self._db_path: Path = db_dir / db_name
        self._conn: sqlite3.Connection = sqlite3.connect(
            str(self._db_path),
            check_same_thread=False,
            timeout=30,  # tolerate brief contention from concurrent readers
        )
        self._conn.row_factory = sqlite3.Row
        self._bootstrap()
        # Flush any WAL residue left by the previous process — safe, non-blocking.
        self._conn.execute("PRAGMA wal_checkpoint(PASSIVE)")
        # Register this process so `maccre.py sessions kill` can find stale DB holders.
        self._register_session_pid()
        import atexit as _atexit  # noqa: PLC0415
        _atexit.register(self._deregister_session_pid)
        _atexit.register(self.close)

    def _register_session_pid(self) -> None:
        """Write this process's PID into .session_pids.json at the MACCRE root."""
        import datetime as _dt  # noqa: PLC0415
        import json as _json  # noqa: PLC0415
        import os as _os  # noqa: PLC0415
        from maccre_core.utils.path_resolver import get_maccre_root  # noqa: PLC0415
        registry = get_maccre_root() / ".session_pids.json"
        try:
            entries: list[dict[str, object]] = []
            if registry.exists():
                with open(registry, encoding="utf-8") as f:
                    entries = _json.load(f)
            entries.append({
                "pid": _os.getpid(),
                "project": self._project,
                "db_path": str(self._db_path),
                "started": _dt.datetime.utcnow().isoformat(),
            })
            with open(registry, "w", encoding="utf-8") as f:
                _json.dump(entries, f, indent=2)
        except Exception:  # noqa: BLE001
            pass  # Never block DB open on registry write failure

    def _deregister_session_pid(self) -> None:
        """Remove this process's PID from .session_pids.json on clean exit."""
        import json as _json  # noqa: PLC0415
        import os as _os  # noqa: PLC0415
        from maccre_core.utils.path_resolver import get_maccre_root  # noqa: PLC0415
        registry = get_maccre_root() / ".session_pids.json"
        try:
            if not registry.exists():
                return
            with open(registry, encoding="utf-8") as f:
                entries: list[dict[str, object]] = _json.load(f)
            my_pid = _os.getpid()
            entries = [e for e in entries if e.get("pid") != my_pid]
            with open(registry, "w", encoding="utf-8") as f:
                _json.dump(entries, f, indent=2)
        except Exception:  # noqa: BLE001
            pass

    def close(self) -> None:
        """Checkpoint WAL and close the SQLite connection cleanly."""
        try:
            self._conn.execute("PRAGMA wal_checkpoint(PASSIVE)")
            self._conn.close()
        except Exception:  # noqa: BLE001
            pass

    def _bootstrap(self) -> None:
        """Apply DDL idempotently on first open."""
        self._conn.executescript(_DDL)
        self._conn.commit()

    # ── Write ─────────────────────────────────────────────────────────────

    def upsert(self, collection: str, record: PinRecord) -> None:
        import datetime as _dt  # noqa: PLC0415
        blob = _vec_to_blob(record.vector) if record.vector else None
        meta_json = json.dumps(record.metadata, ensure_ascii=False)
        now = _dt.datetime.utcnow().isoformat()
        self._conn.execute(
            """
            INSERT INTO pins (doc_id, collection, text, vector_blob, metadata_json, ingested_at)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(doc_id, collection) DO UPDATE SET
                text          = excluded.text,
                vector_blob   = excluded.vector_blob,
                metadata_json = excluded.metadata_json,
                ingested_at   = excluded.ingested_at
            """,
            (record.doc_id, collection, record.text, blob, meta_json, now),
        )
        self._conn.commit()

    def delete(self, collection: str, doc_id: str) -> None:
        self._conn.execute(
            "DELETE FROM pins WHERE doc_id = ? AND collection = ?",
            (doc_id, collection),
        )
        self._conn.commit()

    def delete_collection(self, collection: str) -> None:
        self._conn.execute(
            "DELETE FROM pins WHERE collection = ?",
            (collection,),
        )
        self._conn.commit()

    # ── Read ──────────────────────────────────────────────────────────────

    def query(
        self,
        collection: str,
        vector: list[float],
        n: int = 5,
    ) -> list[PinRecord]:
        """
        Vector similarity search via in-Python cosine distance.

        Strategy:
          1. If the collection is small (<= 5000 rows), load all vectors and rank.
          2. Future Phase 5 upgrade: delegate to sqlite-vec native ANN.
        """
        rows = self._conn.execute(
            "SELECT doc_id, text, vector_blob, metadata_json FROM pins WHERE collection = ?",
            (collection,),
        ).fetchall()

        scored: list[tuple[float, PinRecord]] = []
        for row in rows:
            blob: bytes | None = row["vector_blob"]
            if blob is None:
                continue
            row_vec = _blob_to_vec(blob)
            dist = _cosine_distance(vector, row_vec)
            meta: dict[str, Any] = json.loads(row["metadata_json"])
            scored.append((dist, PinRecord(
                doc_id=row["doc_id"],
                text=row["text"],
                vector=row_vec,
                metadata=meta,
                distance=dist,
            )))

        scored.sort(key=lambda t: t[0])
        return [pin for _, pin in scored[:n]]

    def fts_query(self, collection: str, query_text: str, n: int = 5) -> list[PinRecord]:
        """
        Full-text search using SQLite FTS5 BM25 ranking.
        Available as a fast alternative when no embedding vector is needed.
        """
        # Wrap query in quotes to prevent FTS5 from interpreting hyphens as syntax
        safe_query = f'"{query_text.replace("\"", "")}"'
        rows = self._conn.execute(
            """
            SELECT p.doc_id, p.text, p.vector_blob, p.metadata_json,
                   bm25(pins_fts) AS score
            FROM pins_fts
            JOIN pins p ON pins_fts.rowid = p.id
            WHERE pins_fts MATCH ? AND p.collection = ?
            ORDER BY bm25(pins_fts)
            LIMIT ?
            """,
            (safe_query, collection, n),
        ).fetchall()

        pins: list[PinRecord] = []
        for row in rows:
            meta: dict[str, Any] = json.loads(row["metadata_json"])
            blob: bytes | None = row["vector_blob"]
            vec: list[float] | None = _blob_to_vec(blob) if blob else None
            pins.append(PinRecord(
                doc_id=row["doc_id"],
                text=row["text"],
                vector=vec,
                metadata=meta,
                distance=float(row["score"]),
            ))
        return pins

    def get_all(self, collection: str) -> list[PinRecord]:
        rows = self._conn.execute(
            "SELECT doc_id, text, vector_blob, metadata_json FROM pins WHERE collection = ?",
            (collection,),
        ).fetchall()
        pins: list[PinRecord] = []
        for row in rows:
            meta: dict[str, Any] = json.loads(row["metadata_json"])
            blob: bytes | None = row["vector_blob"]
            vec: list[float] | None = _blob_to_vec(blob) if blob else None
            pins.append(PinRecord(
                doc_id=row["doc_id"],
                text=row["text"],
                vector=vec,
                metadata=meta,
            ))
        return pins

    def list_collections(self) -> list[str]:
        rows = self._conn.execute(
            "SELECT DISTINCT collection FROM pins ORDER BY collection"
        ).fetchall()
        return [row["collection"] for row in rows]
