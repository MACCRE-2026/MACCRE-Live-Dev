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
maccre_core/memory/chroma_store.py
====================================
ChromaDB concrete implementation of KnowledgeStore.

Status: LEGACY — Phase 2 default until SovereignPinStore is validated.
        Set MACCRE_MEMORY_BACKEND=sovereign to switch.
        ChromaDB will be removed from requirements-sovereign.txt once
        SovereignPinStore query quality is validated on live project data.
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Any

from maccre_core.memory.knowledge_store import KnowledgeStore, PinRecord

if TYPE_CHECKING:
    import chromadb  # type: ignore
    import chromadb.api  # type: ignore


class ChromaDBStore(KnowledgeStore):
    """
    Thin wrapper over ChromaDB PersistentClient.

    Adapts the raw ChromaDB API surface to the KnowledgeStore contract
    so that all callers are isolated from chromadb-specific types.
    """

    def __init__(self, project_name: str) -> None:
        import chromadb as _chroma  # type: ignore  # noqa: PLC0415
        from maccre_core.utils.path_resolver import get_datacenter_path  # noqa: PLC0415
        self._project = project_name
        db_path = str(get_datacenter_path("chroma_db"))
        self._client: chromadb.api.ClientAPI = _chroma.PersistentClient(path=db_path)  # type: ignore[attr-defined]

    # ── Write ─────────────────────────────────────────────────────────────

    def upsert(self, collection: str, record: PinRecord) -> None:
        col = self._client.get_or_create_collection(name=collection)
        kwargs: dict[str, Any] = {
            "ids": [record.doc_id],
            "documents": [record.text],
            "metadatas": [record.metadata],
        }
        if record.vector is not None:
            kwargs["embeddings"] = [record.vector]
        col.upsert(**kwargs)  # type: ignore[arg-type]

    def delete(self, collection: str, doc_id: str) -> None:
        col = self._client.get_collection(name=collection)
        col.delete(ids=[doc_id])

    def delete_collection(self, collection: str) -> None:
        self._client.delete_collection(name=collection)

    # ── Read ──────────────────────────────────────────────────────────────

    def query(
        self,
        collection: str,
        vector: list[float],
        n: int = 5,
    ) -> list[PinRecord]:
        try:
            col = self._client.get_collection(name=collection)
        except Exception:  # noqa: BLE001
            return []
        results = col.query(query_embeddings=[vector], n_results=n)
        raw_docs = results.get("documents")
        raw_dists = results.get("distances")
        raw_ids = results.get("ids")
        raw_meta = results.get("metadatas")
        if not raw_docs or not raw_docs[0]:
            return []
        pins: list[PinRecord] = []
        for i, text in enumerate(raw_docs[0]):
            dist = float(raw_dists[0][i]) if raw_dists and raw_dists[0] else 0.0  # type: ignore[index]
            doc_id = raw_ids[0][i] if raw_ids and raw_ids[0] else f"doc_{i}"  # type: ignore[index]
            meta: dict[str, Any] = dict(raw_meta[0][i]) if (raw_meta and raw_meta[0]) else {}  # type: ignore[index]
            pins.append(PinRecord(doc_id=doc_id, text=text, distance=dist, metadata=meta))
        return pins

    def get_all(self, collection: str) -> list[PinRecord]:
        try:
            col = self._client.get_collection(name=collection)
        except Exception:  # noqa: BLE001
            return []
        data = col.get(include=["embeddings", "documents", "metadatas"])
        pins: list[PinRecord] = []
        for i, doc_id in enumerate(data["ids"]):
            text = data["documents"][i] if data.get("documents") else ""  # type: ignore[index]
            embs = data.get("embeddings")
            vec: list[float] | None = list(embs[i]) if embs else None  # type: ignore[index]
            meta_raw = data.get("metadatas")
            meta: dict[str, Any] = dict(meta_raw[i]) if meta_raw else {}  # type: ignore[index]
            pins.append(PinRecord(doc_id=doc_id, text=text, vector=vec, metadata=meta))
        return pins

    def list_collections(self) -> list[str]:
        return [c.name for c in self._client.list_collections()]

    # ── Lifecycle ─────────────────────────────────────────────────────────

    def close(self) -> None:
        pass  # ChromaDB PersistentClient manages its own connection lifecycle
