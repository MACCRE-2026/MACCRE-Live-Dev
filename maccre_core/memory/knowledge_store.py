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
maccre_core/memory/knowledge_store.py
======================================
Strangler Fig ABC — KnowledgeStore Interface.

Every concrete memory backend (ChromaDB, SovereignPin, future P2P mesh) MUST
implement this interface.  No caller in MACCREv2 may touch a backend directly;
all access goes through a KnowledgeStore instance.

Concrete implementations:
  - ChromaDBStore   → maccre_core/memory/chroma_store.py  (legacy, Phase 2A)
  - SovereignPinStore → maccre_core/memory/sovereign_store.py  (Phase 2B target)

Switching backends is a one-line change in get_knowledge_store().
"""
from __future__ import annotations

import abc
from typing import Any


# ── Data Types ──────────────────────────────────────────────────────────────────

class PinRecord:
    """A single stored document / knowledge pin."""
    __slots__ = ("doc_id", "text", "vector", "metadata", "distance")

    def __init__(
        self,
        doc_id: str,
        text: str,
        vector: list[float] | None = None,
        metadata: dict[str, Any] | None = None,
        distance: float = 0.0,
    ) -> None:
        self.doc_id: str = doc_id
        self.text: str = text
        self.vector: list[float] | None = vector
        self.metadata: dict[str, Any] = metadata or {}
        self.distance: float = distance


# ── Abstract Interface ──────────────────────────────────────────────────────────

class KnowledgeStore(abc.ABC):
    """
    Abstract interface for all MACCREv2 memory backends.

    Lifecycle:
        store = get_knowledge_store(project_name)
        store.upsert(collection, PinRecord(...))
        results = store.query(collection, vector, n=5)
        store.close()
    """

    # ── Write ────────────────────────────────────────────────────────────────

    @abc.abstractmethod
    def upsert(self, collection: str, record: PinRecord) -> None:
        """Insert or update a document in the given collection."""

    @abc.abstractmethod
    def delete(self, collection: str, doc_id: str) -> None:
        """Remove a single document by ID from the given collection."""

    @abc.abstractmethod
    def delete_collection(self, collection: str) -> None:
        """Drop an entire collection."""

    # ── Read ─────────────────────────────────────────────────────────────────

    @abc.abstractmethod
    def query(
        self,
        collection: str,
        vector: list[float],
        n: int = 5,
    ) -> list[PinRecord]:
        """
        Return up to n records whose vectors are nearest to the query vector.
        Results MUST be sorted ascending by distance (closest first).
        """

    @abc.abstractmethod
    def get_all(self, collection: str) -> list[PinRecord]:
        """Return every record in the collection (used for bulk merge/export)."""

    @abc.abstractmethod
    def list_collections(self) -> list[str]:
        """Return a list of all collection names in this store."""

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    @abc.abstractmethod
    def close(self) -> None:
        """Release any held resources (file handles, connections, etc.)."""

    # ── Optional / Backend-Specific Extensions ────────────────────────────────

    def fts_query(self, collection: str, query_text: str, n: int = 5) -> list[PinRecord]:
        """
        Full-text keyword search (BM25 / FTS5).

        Backends that support native FTS should override this method.
        The default fallback performs a case-insensitive substring scan over
        ``get_all()`` results so that callers always get a valid response
        regardless of backend.
        """
        query_lower = query_text.lower()
        candidates = [
            p for p in self.get_all(collection)
            if query_lower in p.text.lower()
        ]
        return candidates[:n]


# ── Factory ─────────────────────────────────────────────────────────────────────

_BACKEND: str = "sovereign"   # "chroma" | "sovereign"
_instances: dict[str, KnowledgeStore] = {}


def get_knowledge_store(
    project_name: str, 
    db_name: str = "memory_pins.db",
    scope: str = "project",
    session_id: str = ""
) -> KnowledgeStore:
    """
    Return the singleton KnowledgeStore for project_name and db_name with specific scoping.

    Switch backend globally by changing _BACKEND above (or via env var
    MACCRE_MEMORY_BACKEND).  No callers need to change.
    """
    import os
    backend = os.environ.get("MACCRE_MEMORY_BACKEND", _BACKEND)
    cache_key = f"{project_name}:{db_name}:{scope}:{session_id}"

    if cache_key not in _instances:
        if backend == "chroma":
            from maccre_core.memory.chroma_store import ChromaDBStore  # noqa: PLC0415
            _instances[cache_key] = ChromaDBStore(project_name)
        else:
            from maccre_core.memory.sovereign_store import SovereignPinStore  # noqa: PLC0415
            _instances[cache_key] = SovereignPinStore(
                project_name=project_name, 
                db_name=db_name,
                scope=scope,
                session_id=session_id
            )

    return _instances[cache_key]


def close_all() -> None:
    """Teardown all open store singletons. Call on process exit."""
    for store in _instances.values():
        try:
            store.close()
        except Exception:  # noqa: BLE001
            pass
    _instances.clear()
