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
# B:/MACCREv2/maccre_core/tools/rag_tools.py
"""
Sovereign RAG Engine — OS Vault-Authenticated Embeddings.

All vector storage goes through the KnowledgeStore ABC (maccre_core/memory/).
The active backend (ChromaDB legacy | SovereignPinStore) is selected by the
MACCRE_MEMORY_BACKEND environment variable. Default: sovereign.

Public API is 100% backward-compatible — callers do not change.
"""
from __future__ import annotations

import datetime
import logging
import os
from typing import Any

from maccre_core._net.gemini_client import GeminiClient

from maccre_core.memory import PinRecord, get_knowledge_store
from maccre_core.orchestration.universal_vault import get_provider_credential
from maccre_core.utils.path_resolver import get_datacenter_path

_log = logging.getLogger(__name__)

_rag_client: GeminiClient | None = None


# ── Embedding ───────────────────────────────────────────────────────────────────

def _get_rag_client() -> GeminiClient:
    global _rag_client
    if not _rag_client:
        raw_key = get_provider_credential("MACCRE_Sovereign")
        if not raw_key:
            raise ValueError("CRITICAL: Vault returned empty.")
        clean_key = str(raw_key).strip()
        if not clean_key.startswith("AIza"):
            raise ValueError("CRITICAL: Invalid Key.")
        _rag_client = GeminiClient(key_provider=lambda: get_provider_credential("MACCRE_Sovereign"))
    return _rag_client


def get_gemini_embedding(text: str, task_type: str = "RETRIEVAL_DOCUMENT") -> list[float]:
    """Generates a 256-dim embedding vector via OS Vault client.

    Args:
        text: Text to embed.
        task_type: ``"RETRIEVAL_DOCUMENT"`` for ingestion, ``"RETRIEVAL_QUERY"`` for search.

    Returns:
        List of 256 floats.
    """
    client = _get_rag_client()
    response = client.embed_content(
        model="gemini-embedding-001",
        text=text,
        task_type=task_type,
    )
    if not response.values:
        raise ValueError("Embedding response returned no values.")
    return response.values


# ── Core Ingest ─────────────────────────────────────────────────────────────────

def ingest_document(
    text: str = "",
    doc_id: str = "",
    collection_name: str = "swarm_memory",
    metadata: dict[str, Any] | None = None,
    *,
    file_path: str = "",
) -> str:
    """Embeds and upserts a document into the sovereign knowledge store.

    Can be called with raw ``text`` + ``doc_id``, or with a ``file_path`` that
    is resolved through the active datacenter jail (``get_datacenter_path``).

    Args:
        text: Raw text to embed and store.  Ignored if ``file_path`` is given.
        doc_id: Unique upsert key. Same ID overwrites rather than duplicates.
            Auto-derived from the filename stem when ``file_path`` is given.
        collection_name: Target collection. Default: ``"swarm_memory"``.
        metadata: Optional metadata dict stored alongside the document.
        file_path: Relative path inside the active datacenter project
            (e.g. ``"01_Raw_Source/payload.md"``).  When provided, the file is
            read and its content is used as ``text``.

    Returns:
        Confirmation string or error message.
    """
    import pathlib as _pl  # noqa: PLC0415
    try:
        if file_path:
            parts = _pl.PurePosixPath(file_path).parts
            full = get_datacenter_path(*parts)
            if not full.exists():
                return f"[RAG_FAULT] File not found: {full}"
            text = full.read_text(encoding="utf-8")
            if not doc_id:
                doc_id = full.stem

        if not text:
            return "[RAG_FAULT] ingest_document requires either 'text' or 'file_path'."
        if not doc_id:
            return "[RAG_FAULT] ingest_document requires 'doc_id' when called with raw 'text'."

        safe_meta: dict[str, Any] = metadata if metadata else {}
        safe_meta.setdefault("type", "uncategorized")
        safe_meta["ingested_at"] = datetime.datetime.utcnow().isoformat()

        vector = get_gemini_embedding(text, task_type="RETRIEVAL_DOCUMENT")
        project = safe_meta.get("project", os.environ.get("MACCRE_ACTIVE_PROJECT", "GLOBAL"))
        store = get_knowledge_store(str(project))
        store.upsert(collection_name, PinRecord(
            doc_id=doc_id,
            text=text,
            vector=vector,
            metadata=safe_meta,
        ))

        # Dual-write to memory_pins legacy table (non-fatal)
        try:
            from maccre_core.orchestration.thought_pins import upsert_pin  # noqa: PLC0415
            import uuid
            tp_id = f"tp_{uuid.uuid4().hex[:8]}"
            upsert_pin(str(project), tp_id, text, vector)
        except Exception as vec_e:  # noqa: BLE001
            _log.warning("[DUAL-WRITE FAULT] memory_pins upsert: %s", vec_e)

        return f"[RAG] Ingested '{doc_id}' into '{collection_name}'."
    except Exception as e:  # noqa: BLE001
        return f"[Memory Engine] Ingest failed: {e!s}"


# ── Core Query ──────────────────────────────────────────────────────────────────

def query_local_memory(
    query: str,
    active_project: str = "swarm_memory",
    linked_projects: list[str] | None = None,
    global_context: bool = False,
    *,
    collection_name: str = "",
    n_results: int = 5,
) -> str:
    """Queries the sovereign knowledge store across dynamic project scopes.

    Aggregates results from the active project, any explicitly linked projects,
    or every collection when ``global_context=True``. Results are re-ranked by
    distance and the top ``n_results`` are returned.

    Args:
        query: Search term or question.
        active_project: Primary collection to query. Default: ``"swarm_memory"``.
        linked_projects: Additional collection names to include.
        global_context: If ``True``, search ALL collections in the store.
        collection_name: Alias for ``active_project``.
        n_results: Maximum results to return per collection. Default 5.

    Returns:
        Formatted string of federated memory chunks, or a not-found message.
    """
    resolved_collection = collection_name or active_project
    env_project = os.environ.get("MACCRE_ACTIVE_PROJECT", "GLOBAL")
    store = get_knowledge_store(env_project)

    try:
        vector = get_gemini_embedding(query, task_type="RETRIEVAL_QUERY")

        if global_context:
            target_collections = store.list_collections()
        else:
            target_collections = [resolved_collection]
            if linked_projects:
                target_collections.extend(linked_projects)

        aggregated: list[PinRecord] = []
        for col in target_collections:
            try:
                results = store.query(col, vector, n=n_results)
                aggregated.extend(results)
            except Exception:  # noqa: BLE001
                continue

        aggregated.sort(key=lambda p: p.distance)

        if not aggregated:
            return f"No relevant memories found in active scope(s): {target_collections}"

        output = "--- RECOVERED FEDERATED MEMORIES ---\n"
        for pin in aggregated[:n_results]:
            output += (
                f"[Source: {pin.metadata.get('project', env_project)} | "
                f"Distance: {pin.distance:.4f}]\n"
                f"{pin.text}\n\n"
            )
        return output
    except Exception as e:  # noqa: BLE001
        return f"[Memory Engine] Query failed: {e!s}"


def fts_search_memory(
    query: str,
    collection_name: str = "swarm_memory",
    n_results: int = 5,
) -> str:
    """Full-text keyword search across ALL ingested documents using SQLite FTS5 BM25.

    USE THIS INSTEAD OF query_local_memory when:
    - Searching for specific terms like 'alien', 'EBO', 'diving suit', 'dark matter'
    - The content you need may be buried deep in large source files
    - query_local_memory returned no results or weak results

    Unlike query_local_memory (which uses the embedding of the first ~2000 tokens),
    fts_search_memory searches the COMPLETE stored text of every document regardless
    of document length. All 27 raw source files are fully indexed including the
    deepest content in OriginalTIGR.txt (9000+ lines).

    Args:
        query: Keywords or phrase to search for. Supports FTS5 operators:
               AND, OR, NOT, "exact phrase", prefix*, NEAR(term1 term2, distance).
               Examples: 'alien diving suit', 'dark matter filament', 'Square Edge'.
        collection_name: Collection to search. Default: ``"swarm_memory"``.
        n_results: Maximum results to return. Default 5.

    Returns:
        Formatted string of matching document excerpts with source labels.
    """
    env_project = os.environ.get("MACCRE_ACTIVE_PROJECT", "GLOBAL")
    store = get_knowledge_store(env_project)
    try:
        results = store.fts_query(collection_name, query, n=n_results)
        if not results:
            return f"[FTS] No matches for '{query}' in collection '{collection_name}'."
        output = f"--- FTS RESULTS for '{query}' ({len(results)} hit(s)) ---\n"
        for pin in results:
            src = pin.metadata.get("filename", pin.doc_id)
            tier = pin.metadata.get("type", "source")
            output += f"[{tier} | {src} | BM25={pin.distance:.3f}]\n{pin.text[:1200]}...\n\n"
        return output
    except Exception as e:  # noqa: BLE001
        return f"[FTS] Search failed: {e!s}"


def iterative_scoped_search(
    query: str,
    excluded_ids: list[str] | None = None,
    collection_name: str = "swarm_memory",
    n_results: int = 5,
) -> str:
    """Dynamically Scoped Infosphere Search (Two-Stage).
    
    Step 1: Uses FTS on memory_pins.db to establish the semantic scope of the project.
    Step 2: Uses Vector Similarity on the active project store (which includes canonized
            agent_ledgers and agent_thoughts) to find exact content.
    Step 3: Excludes any doc_id in excluded_ids to allow iterating deep into the DB.
    
    Args:
        query: The semantic search string.
        excluded_ids: List of doc_ids to exclude from the results (from previous searches).
        collection_name: Target collection. Default: "swarm_memory".
        n_results: Max chunks to return. Default 5.
    """
    env_project = os.environ.get("MACCRE_ACTIVE_PROJECT", "GLOBAL")
    env_session = os.environ.get("MACCRE_ACTIVE_SESSION", "")
    
    try:
        # Query L2 Project DB for semantic scope
        tp_store = get_knowledge_store(env_project, db_name="thought_pins.db")
        pin_results = tp_store.fts_query(collection_name, query, n=3)
        
        # Also query L1 Ephemeral Session DBs for semantic scope (if active)
        # NOTE: Session-level thought_pins.db no longer exists — thought-pins are
        # only vectorized during canonize_session(). We query session agent_thoughts
        # instead for ephemeral scope enrichment.
        if env_session:
            try:
                sess_thoughts = get_knowledge_store(env_project, db_name=f"session_{env_session}_agent_thoughts.db")
                pin_results.extend(sess_thoughts.fts_query(collection_name, query, n=3))
            except Exception:  # noqa: BLE001
                pass  # Ephemeral DB may not exist yet

        scope_context = ""
        if pin_results:
            scope_context = " ".join([p.text for p in pin_results])
            
        # Enrich the query with the thought pin context for the deep vector search
        enriched_query = f"{query}\n[Context Pins]: {scope_context}" if scope_context else query
        vector = get_gemini_embedding(enriched_query, task_type="RETRIEVAL_QUERY")
        
        # Query L2 Project DB for final vector match
        candidates = tp_store.query(collection_name, vector, n=n_results + (len(excluded_ids) if excluded_ids else 0))
        
        # Query L1 Ephemeral Session DB for final vector match
        if env_session:
            try:
                candidates.extend(sess_thoughts.query(collection_name, vector, n=n_results + (len(excluded_ids) if excluded_ids else 0)))
            except Exception:  # noqa: BLE001
                pass  # Ephemeral DB may not exist yet
        # Sort combined candidates by distance
        candidates = sorted(candidates, key=lambda x: x.distance)
        
        # Step 3: Apply exclusions
        excludes = set(excluded_ids or [])
        filtered = [c for c in candidates if c.doc_id not in excludes][:n_results]
        
        if not filtered:
            return f"[SCOPED_SEARCH] No new relevant memories found for '{query}'."
            
        output = f"--- DYNAMICALLY SCOPED SEARCH RESULTS (n={len(filtered)}) ---\n"
        output += f"Exclusions Applied: {len(excludes)}\n\n"
        for pin in filtered:
            src = pin.metadata.get("filename", pin.doc_id)
            tier = pin.metadata.get("type", "unknown_tier")
            output += (
                f"[DocID: {pin.doc_id} | Tier: {tier} | Source: {src} | Distance: {pin.distance:.4f}]\n"
                f"{pin.text}\n\n"
            )
        return output
    except Exception as e:
        return f"[SCOPED_SEARCH_FAULT] {e!s}"


# ── Global Ingest & Query ────────────────────────────────────────────────────────

def ingest_global_archive(file_path: str) -> str:
    """Ingests a file into the GLOBAL archive by extracting conceptual thought pins.
    
    Reads a file from GLOBAL/01_Raw_Source, prompts Gemini to extract Knowledge Triplets,
    saves the triplets to GLOBAL/02_Dynamic_Context/memory_pins, and embeds the concept into the
    GLOBAL SovereignPinStore with the source file path linked in metadata.
    """
    import json
    import pathlib as _pl
    from maccre_core._net.gemini_client import user_turn
    from maccre_core.utils.path_resolver import get_datacenter_path
    
    try:
        # Force project to GLOBAL for resolving paths
        os.environ["MACCRE_ACTIVE_PROJECT"] = "GLOBAL"
        
        parts = _pl.PurePosixPath(file_path).parts
        full = get_datacenter_path(*parts)
        if not full.exists():
            return f"[GLOBAL_INGEST_FAULT] File not found: {full}"
            
        text = full.read_text(encoding="utf-8", errors="replace")
        if not text:
            return f"[GLOBAL_INGEST_FAULT] File is empty: {full}"
            
        # Extract Concepts
        client = _get_rag_client()
        schema_hint = '{"triplets": [{"subject": "...", "predicate": "...", "object": "...", "significance": "..."}]}'
        system = (
            "You are the MACCREv2 Global Archive Ingestion Engine. "
            "Analyze the following raw source document. Extract the most brilliant conceptual, mathematical, "
            "or architectural relationships and output them as strict Knowledge Triplets. "
            "Ignore conversational filler. Only pin high-value concepts. "
            f"You MUST reply with ONLY valid JSON matching this schema exactly: {schema_hint}"
        )
        
        response = client.generate_content(
            model="gemini-3.1-pro-preview",
            contents=[user_turn(text[:30000])], # Cap at 30k chars to prevent token bloat during extraction
            system_instruction=system,
            temperature=0.1,
        )
        
        raw = response.text.strip()
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
                
        extraction = json.loads(raw)
        triplets = extraction.get("triplets", [])
        
        if not triplets:
            return "[GLOBAL_INGEST_FAULT] No concepts extracted."
            
        # Save to 02_Dynamic_Context/memory_pins
        memory_dir = get_datacenter_path("02_Dynamic_Context", "memory_pins")
        memory_dir.mkdir(parents=True, exist_ok=True)
        doc_id = full.stem.replace(".", "_")
        out_path = memory_dir / f"global_pin_{doc_id}.json"
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(triplets, f, indent=2)
            
        # Embed and Store in Vector DB
        concept_text = json.dumps(triplets)
        vector = get_gemini_embedding(concept_text, task_type="RETRIEVAL_DOCUMENT")
        
        safe_meta = {
            "project": "GLOBAL",
            "filename": full.name,
            "source_file": str(full.relative_to(full.parent.parent.parent)), # Gives e.g. GLOBAL/01_Raw_Source/file.txt
            "tier": "global_concept",
            "type": "global_concept",
            "ingested_at": datetime.datetime.utcnow().isoformat(),
        }
        
        store = get_knowledge_store("GLOBAL")
        store.upsert("swarm_memory", PinRecord(
            doc_id=doc_id,
            text=concept_text,
            vector=vector,
            metadata=safe_meta,
        ))
        
        return f"[GLOBAL_INGEST] Extracted and vectorized {len(triplets)} concepts from '{doc_id}' into GLOBAL index."
        
    except Exception as e:
        return f"[GLOBAL_INGEST_FAULT] {e!s}"


def query_global_archive(concept_query: str, n_results: int = 5) -> str:
    """Semantic search explicitly targeting the GLOBAL concept archive.
    
    Can be called by an agent in ANY project to retrieve global Thought Pins and
    the exact physical paths to the source documents.
    """
    try:
        vector = get_gemini_embedding(concept_query, task_type="RETRIEVAL_QUERY")
        store = get_knowledge_store("GLOBAL")
        
        results = store.query("swarm_memory", vector, n=n_results)
        
        if not results:
            return "No relevant global concepts found."
            
        output = "--- RECOVERED GLOBAL KNOWLEDGE CONCEPTS ---\n"
        for pin in results:
            source_file = pin.metadata.get("source_file", "Unknown")
            output += (
                f"[Source Document: {source_file} | Distance: {pin.distance:.4f}]\n"
                f"Concepts:\n{pin.text}\n"
                f"*(To read the full document, use the read_file tool with this source path)*\n\n"
            )
        return output
    except Exception as e:
        return f"[GLOBAL_QUERY_FAULT] {e!s}"


# ── Synaptic Bridge ─────────────────────────────────────────────────────────────

def _get_active_project() -> str:
    return os.environ.get("MACCRE_ACTIVE_PROJECT", "GLOBAL")


def _verify_synaptic_bridge(target_project: str) -> bool:
    """Checks the local project_schema.json to see if target_project is linked."""
    import json  # noqa: PLC0415
    active_project = _get_active_project()
    if active_project == target_project:
        return True

    schema_path = get_datacenter_path("project_schema.json")
    if not schema_path.exists():
        return False

    try:
        with schema_path.open(encoding="utf-8") as f:
            schema = json.load(f)
            linked = schema.get("linked_projects", [])
            return target_project in linked
    except Exception:  # noqa: BLE001
        return False


def query_foreign_memory(target_project: str, query: str, n_results: int = 3) -> str:
    """Read-only query of a linked foreign project's knowledge store.

    Args:
        target_project: The exact string name of the foreign project.
        query: The semantic search string.
        n_results: Max chunks to return. Default 3.
    """
    if not _verify_synaptic_bridge(target_project):
        return (
            f"[SECURITY_FAULT] The active project ({_get_active_project()}) is NOT "
            f"linked to '{target_project}'. Request denied by project_schema.json."
        )

    try:
        vector = get_gemini_embedding(query, task_type="RETRIEVAL_QUERY")
        foreign_store = get_knowledge_store(target_project)

        results_merged: list[PinRecord] = []
        for col in foreign_store.list_collections():
            results_merged.extend(foreign_store.query(col, vector, n=n_results))

        results_merged.sort(key=lambda p: p.distance)
        if not results_merged:
            return f"No relevant memories found in foreign project '{target_project}'."

        output = f"--- FOREIGN OVERRIDE: {target_project} ---\n"
        for pin in results_merged[:n_results]:
            output += (
                f"[Collection: {pin.metadata.get('collection', target_project)} "
                f"| Distance: {pin.distance:.4f}]\n"
                f"{pin.text}\n\n"
            )
        return output
    except Exception as e:  # noqa: BLE001
        return f"[Memory Engine] Foreign Query failed: {e!s}"


def import_foreign_vectors(
    target_project: str,
    query: str,
    relevance_threshold: float = 1.0,
) -> str:
    """Selectively imports highly relevant semantic memory from a foreign store.

    Args:
        target_project: The exact string name of the foreign project.
        query: The semantic concept to search for.
        relevance_threshold: Max cosine distance. Lower is stricter.
            Default 1.0 blocks almost all ingestion — lower it to permit import.
    """
    if relevance_threshold == 1.0:
        return (
            "[BRIDGE_FAULT] relevance_threshold set to 1.0. Osmosis blocked. "
            "You must manually lower the threshold (e.g. 0.4) to permit physical DB mutation."
        )

    if not _verify_synaptic_bridge(target_project):
        return f"[SECURITY_FAULT] Active project is NOT linked to '{target_project}'."

    try:
        vector = get_gemini_embedding(query, task_type="RETRIEVAL_QUERY")
        foreign_store = get_knowledge_store(target_project)
        active_store = get_knowledge_store(_get_active_project())

        imported_count = 0
        for col in foreign_store.list_collections():
            candidates = foreign_store.query(col, vector, n=5)
            for pin in candidates:
                if pin.distance <= relevance_threshold:
                    bridge_pin = PinRecord(
                        doc_id=f"foreign_{target_project}_{col}_{pin.doc_id}",
                        text=pin.text,
                        vector=pin.vector,
                        metadata={**pin.metadata, "origin_project": target_project},
                    )
                    active_store.upsert("synaptic_bridge", bridge_pin)
                    imported_count += 1

        return (
            f"[OSMOSIS_SUCCESS] Migrated {imported_count} vectors from '{target_project}' "
            f"below {relevance_threshold} threshold into active DB."
        )
    except Exception as e:  # noqa: BLE001
        return f"[Memory Engine] Import failed: {e!s}"


def merge_session_to_project(session_name: str, project_name: str) -> str:
    """Zero-compute vector merge — promotes L1 Session agent_thoughts to L2 Project memory.

    NOTE: For full session canonization (agent_thoughts + agent_ledgers + thought_pins),
    use ``canonize_session()`` instead.  This function is a lightweight single-DB merge.

    Args:
        session_name: The session identifier (collection ``session_<session_name>``).
        project_name: The project identifier (collection ``project_<project_name>``).

    Returns:
        A status string prefixed with MERGE_SUCCESS, MERGE_SKIPPED, or MERGE_FAILED.
    """
    sess_col = "swarm_memory"
    proj_col = "swarm_memory"

    # Store for L2 Project Database
    canon_store = get_knowledge_store(project_name, db_name="agent_thoughts.db")

    # Store for L1 Session Database
    sess_db_name = f"session_{session_name}_agent_thoughts.db"
    sess_store = get_knowledge_store(project_name, db_name=sess_db_name)

    try:
        all_pins = sess_store.get_all(sess_col)
        if not all_pins:
            return f"MERGE_SKIPPED: {sess_db_name} is empty."

        for pin in all_pins:
            canon_store.upsert(proj_col, pin)

        # Clear out the session DB or delete it
        sess_store.delete_collection(sess_col)
        return (
            f"MERGE_SUCCESS: Promoted {len(all_pins)} vectors "
            f"from {sess_db_name} to agent_thoughts.db."
        )
    except Exception as exc:  # noqa: BLE001
        return f"MERGE_FAILED: {exc}"


def canonize_project_to_global(project_name: str) -> str:
    """Zero-compute vector merge — promotes L2 Project memory to L3 Global memory.

    Args:
        project_name: The project identifier (collection ``project_<project_name>``).

    Returns:
        A status string prefixed with MERGE_SUCCESS, MERGE_SKIPPED, or MERGE_FAILED.
    """
    proj_col = f"project_{project_name}"
    glob_col = "global_memory"

    project_store = get_knowledge_store(project_name)
    global_store = get_knowledge_store("GLOBAL")

    try:
        if proj_col not in project_store.list_collections():
            return f"MERGE_SKIPPED: No project memory found for {proj_col}."

        all_pins = project_store.get_all(proj_col)
        if not all_pins:
            return f"MERGE_SKIPPED: {proj_col} is empty."

        for pin in all_pins:
            safe_meta = dict(pin.metadata) if pin.metadata else {}
            safe_meta["origin_project"] = project_name
            pin.metadata = safe_meta
            global_store.upsert(glob_col, pin)

        return (
            f"MERGE_SUCCESS: Promoted {len(all_pins)} vectors "
            f"from {proj_col} to {glob_col} in GLOBAL memory."
        )
    except Exception as exc:  # noqa: BLE001
        return f"MERGE_FAILED: {exc}"


def vectorize_ledger(text: str, project_name: str, session_id: str, agent_id: str = "") -> str:
    """Embeds an agent's final response and stores it in the session's ephemeral agent_ledgers.db."""
    try:
        from maccre_core.memory.knowledge_store import get_knowledge_store, PinRecord
        import uuid
        
        db_name = f"session_{session_id}_agent_ledgers.db"
        store = get_knowledge_store(project_name, db_name=db_name)
        
        vector = get_gemini_embedding(text, task_type="RETRIEVAL_DOCUMENT")
        doc_id = f"ledger_{uuid.uuid4().hex[:8]}"
        
        safe_meta = {
            "project": project_name,
            "session_id": session_id,
            "agent_id": agent_id,
            "type": "agent_ledger",
            "ingested_at": datetime.datetime.utcnow().isoformat(),
        }
        
        store.upsert("swarm_memory", PinRecord(
            doc_id=doc_id,
            text=text,
            vector=vector,
            metadata=safe_meta,
        ))
        return f"[VECTOR_SUCCESS] Ledger logged to ephemeral {db_name}"
    except Exception as e:
        return f"[VECTOR_FAULT] {e!s}"

def canonize_session(session_id: str, project_name: str) -> str:
    """
    Manually canonizes a successful swarm session.

    Two-phase promotion:
      1. Merges the session-scoped agent_thoughts and agent_ledgers vectors
         into their project-level canon databases, then deletes the ephemerals.
      2. Reads the raw knowledge-triplet JSON files from 02_Dynamic_Context/memory_pins/ for
         this session, vectorizes them, and upserts into the project canon
         memory_pins.db.  This is the ONLY place thought-pins are vectorized,
         keeping per-session cost to zero.
    """
    import os
    from maccre_core.utils.path_resolver import get_datacenter_path

    # ── Phase 1: Merge session ephemeral vectors into canon ──────────────────
    databases = [
        ("agent_ledgers", f"session_{session_id}_agent_ledgers.db", "agent_ledgers.db"),
    ]

    results: list[str] = []
    dynamic_dir = get_datacenter_path("02_Dynamic_Context")
    os.environ["MACCRE_ACTIVE_PROJECT"] = project_name

    for db_type, ephemeral_name, canon_name in databases:
        try:
            ephemeral_path = dynamic_dir / ephemeral_name
            if not ephemeral_path.exists():
                results.append(f"[{db_type}] No ephemeral DB found.")
                continue

            e_store = get_knowledge_store(project_name, db_name=ephemeral_name)
            c_store = get_knowledge_store(project_name, db_name=canon_name)

            # Transfer all pins
            all_pins = e_store.get_all("swarm_memory")
            count = 0
            for pin in all_pins:
                c_store.upsert("swarm_memory", pin)
                count += 1

            # Close the ephemeral connection so we can delete the file
            e_store.close()

            # Physically delete the DB files (main, shm, wal)
            try:
                if ephemeral_path.exists():
                    os.remove(ephemeral_path)
                wal_path = ephemeral_path.with_name(ephemeral_name + "-wal")
                shm_path = ephemeral_path.with_name(ephemeral_name + "-shm")
                if wal_path.exists():
                    os.remove(wal_path)
                if shm_path.exists():
                    os.remove(shm_path)
            except Exception as f_err:
                results.append(f"[{db_type}] Merged {count} vectors, but failed to delete file: {f_err}")
                continue

            results.append(f"[{db_type}] Successfully canonized {count} vectors.")
        except Exception as e:
            results.append(f"[{db_type}] Error: {e!s}")

    # ── Phase 2: Vectorize knowledge triplets into SovereignPinStore (SQLite) ─────
    try:
        from maccre_core.orchestration.memory_engine import CognitiveMemoryEngine
        
        unified_ledger_path = get_datacenter_path("04_Code_Artifacts", session_id, "unified_session_ledger.md")
        if unified_ledger_path.exists():
            engine = CognitiveMemoryEngine()
            engine.extract_from_canonized_ledger(str(unified_ledger_path), session_id)
            results.append("[memory_pins] Extracted pins from unified ledger into SovereignPinStore.")
        else:
            results.append("[memory_pins] unified_session_ledger.md not found, skipping extraction.")
            
    except Exception as tp_err:
        results.append(f"[memory_pins] Extraction error: {tp_err!s}")
        
    # ── Phase 3: Insert Unified Thoughts Ledger into thoughts.db ──────────────────
    try:
        thoughts_ledger_path = get_datacenter_path("04_Code_Artifacts", session_id, "unified_thoughts_ledger.md")
        if thoughts_ledger_path.exists():
            import sqlite3
            import re
            
            telemetry_dir = get_datacenter_path("telemetry")
            telemetry_dir.mkdir(parents=True, exist_ok=True)
            thoughts_db_path = telemetry_dir / "thoughts.db"
            
            with sqlite3.connect(thoughts_db_path) as conn:
                conn.execute('''
                    CREATE TABLE IF NOT EXISTS agent_thoughts (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        job_id TEXT,
                        agent TEXT,
                        timestamp TEXT,
                        entry_type TEXT,
                        content TEXT
                    )
                ''')
                
                content = thoughts_ledger_path.read_text(encoding="utf-8")
                
                # Split by agent turns
                turns = content.split("### ")
                inserted = 0
                for turn in turns[1:]:
                    lines = turn.split("\n")
                    agent_name = lines[0].strip()
                    ts = ""
                    ts_match = re.search(r"\*Written: (.*?)\*", turn)
                    if ts_match:
                        ts = ts_match.group(1).split(" |")[0].strip()
                        
                    blocks = turn.split("#### ")
                    for block in blocks[1:]:
                        entry_type = "Thought" if "🤔 Thought" in block else "Tool Call"
                        code_match = re.search(r"```(.*?)```", block, re.DOTALL)
                        if code_match:
                            entry_content = code_match.group(1).strip()
                            conn.execute(
                                "INSERT INTO agent_thoughts (job_id, agent, timestamp, entry_type, content) VALUES (?, ?, ?, ?, ?)",
                                (session_id, agent_name, ts, entry_type, entry_content)
                            )
                            inserted += 1
                
                results.append(f"[thoughts_db] Canonized {inserted} thought/tool records into telemetry/thoughts.db")
        else:
            results.append("[thoughts_db] unified_thoughts_ledger.md not found, skipping thoughts telemetry.")
    except Exception as t_err:
        results.append(f"[thoughts_db] Error canonizing thoughts: {t_err!s}")
        
    return "\n".join(results)


def query_session_memory(session_id: str, db_type: str, query: str, n_results: int = 5) -> str:
    """
    Forensic tool: Queries an ephemeral session database (usually for a failed swarm) to salvage or analyze vectors.
    db_type must be one of: 'agent_thoughts', 'agent_ledgers'.
    """
    valid_types = ['agent_ledgers', 'agent_thoughts']
    if db_type not in valid_types:
        return f"Invalid db_type. Must be one of: {valid_types}"
        
    try:
        project_name = os.environ.get("MACCRE_ACTIVE_PROJECT", "GLOBAL")
        db_name = f"session_{session_id}_{db_type}.db"
        store = get_knowledge_store(project_name, db_name=db_name)
        
        vector = get_gemini_embedding(query, task_type="RETRIEVAL_QUERY")
        results = store.query("swarm_memory", vector, n=n_results)
        
        if not results:
            return f"No records found in {db_name}."
            
        output = f"--- FORENSIC QUERY: {db_name} ---\n"
        for pin in results:
            output += (
                f"[Agent: {pin.metadata.get('agent_id', 'Unknown')} | Distance: {pin.distance:.4f}]\n"
                f"{pin.text}\n\n"
            )
        return output
    except Exception as e:
        return f"[FORENSIC_FAULT] {e!s}"


def prune_semantic_memory(
    collection_name: str,
    document_id: str = "",
    days_old: int = 0,
) -> str:
    """Removes vectors from a MACCREv2 knowledge store collection.

    Mode A — by document ID (exact deletion)::
        prune_semantic_memory(collection_name="spectrum_knowledge", document_id="foo")

    Mode B — by age (sweep all vectors older than N days)::
        prune_semantic_memory(collection_name="spectrum_knowledge", days_old=7)

    Args:
        collection_name: The collection to clean.
        document_id: Specific vector ID to delete.
        days_old: Delete every vector whose ``ingested_at`` is older than N days.

    Returns:
        A string beginning with ``[PRUNE_SUCCESS]`` or ``[PRUNE_FAULT]``.
    """
    env_project = os.environ.get("MACCRE_ACTIVE_PROJECT", "GLOBAL")
    store = get_knowledge_store(env_project)

    try:
        # ── Mode A: exact document deletion ────────────────────────────────────
        if document_id:
            store.delete(collection_name, document_id)
            return f"[PRUNE_SUCCESS] Vector '{document_id}' removed from '{collection_name}'."

        # ── Mode B: age-based sweep ────────────────────────────────────────────
        if days_old > 0:
            cutoff = (
                datetime.datetime.utcnow() - datetime.timedelta(days=days_old)
            ).isoformat()
            all_pins = store.get_all(collection_name)
            to_delete = [
                pin for pin in all_pins
                if str(pin.metadata.get("ingested_at", "9999")) < cutoff
            ]
            for pin in to_delete:
                store.delete(collection_name, pin.doc_id)
            if to_delete:
                return (
                    f"[PRUNE_SUCCESS] Removed {len(to_delete)} vector(s) "
                    f"older than {days_old} days from '{collection_name}'."
                )
            return (
                f"[PRUNE_SUCCESS] No vectors older than {days_old} days found "
                f"in '{collection_name}'. Collection is current."
            )

        return "[PRUNE_FAULT] Provide either document_id or days_old > 0."

    except Exception as e:  # noqa: BLE001
        return f"[PRUNE_FAULT] {e}"


# ── Phase 4: Bulk Hash-Aware Project Ingest ─────────────────────────────────────

def ingest_project(project_name: str, session_id: str = "") -> str:
    """Bulk-ingest 01_Raw_Source and 04_Code_Artifacts for a project, honoring SHA-256 manifest.

    Compares each file against ``02_Dynamic_Context/ingest_manifest.json``.
    - **NEW** files → embed + upsert into 'swarm_memory' store
    - **CHANGED** files (hash mismatch) → re-embed, update vector, update manifest
    - **UNCHANGED** files → skip entirely (zero API calls)

    Scans two datacenter tiers:
    - ``01_Raw_Source``   → ``type: "raw_source"``     (user-supplied input documents)
    - ``04_Code_Artifacts`` → ``type: "derived_artifact"``  (swarm-produced outputs)

    Args:
        project_name: Target project silo name.  Sets MACCRE_ACTIVE_PROJECT.
        session_id:   Optional session stamp for metadata.

    Returns:
        Summary string: totals by category + any ingestion errors.
    """
    import hashlib  # noqa: PLC0415
    import json as _json  # noqa: PLC0415
    from maccre_core.utils.path_resolver import get_maccre_root  # noqa: PLC0415

    os.environ["MACCRE_ACTIVE_PROJECT"] = project_name

    base_dir  = get_maccre_root() / "__DATACENTER" / project_name
    raw_dir   = base_dir / "01_Raw_Source"
    art_dir   = base_dir / "04_Code_Artifacts"
    ledg_dir  = base_dir / "03_Agent_Ledgers"
    ctx_dir   = base_dir / "02_Dynamic_Context"
    manifest_path = ctx_dir / "ingest_manifest.json"

    if not raw_dir.exists():
        return (
            f"[INGEST_FAULT] 01_Raw_Source not found for project '{project_name}'. "
            "Run 'maccre.py global' first."
        )

    ctx_dir.mkdir(parents=True, exist_ok=True)

    manifest: dict[str, dict[str, str]] = {}
    if manifest_path.exists():
        try:
            manifest = _json.loads(manifest_path.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            manifest = {}

    TEXT_EXTS = {".md", ".txt", ".json", ".yaml", ".yml", ".csv", ".py", ".rst", ".html"}

    # ── Collect files from both tiers ──────────────────────────────────────────
    scan_targets: list[tuple[str, str]] = []   # (abs_path, type_label)
    for fpath in sorted(raw_dir.rglob("*")):
        if fpath.is_file() and fpath.suffix.lower() in TEXT_EXTS:
            scan_targets.append((str(fpath), "raw_source"))
    if art_dir.exists():
        for fpath in sorted(art_dir.rglob("*")):
            if fpath.is_file() and fpath.suffix.lower() in TEXT_EXTS:
                scan_targets.append((str(fpath), "derived_artifact"))
    if ledg_dir.exists():
        for fpath in sorted(ledg_dir.rglob("*")):
            if fpath.is_file() and fpath.suffix.lower() in TEXT_EXTS:
                scan_targets.append((str(fpath), "agent_ledger"))

    results: list[tuple[str, str, str]] = []
    new_count = changed_count = skipped_count = error_count = 0

    for fpath_str, type_label in scan_targets:
        import pathlib as _pl  # noqa: PLC0415
        fpath = _pl.Path(fpath_str)
        rel = f"{type_label}/{fpath.name}"
        try:
            raw_bytes = fpath.read_bytes()
            sha256 = hashlib.sha256(raw_bytes).hexdigest()
            existing = manifest.get(rel, {})

            if existing.get("sha256") == sha256:
                skipped_count += 1
                results.append((rel, "SKIPPED", "unchanged"))
                continue

            status_label = "NEW" if rel not in manifest else "UPDATED"
            text = fpath.read_text(encoding="utf-8", errors="replace")
            doc_id = f"{project_name}__{type_label}__{fpath.stem.replace('.', '_')}"

            now = datetime.datetime.utcnow().isoformat()
            result = ingest_document(
                text=text,
                doc_id=doc_id,
                collection_name="swarm_memory",
                metadata={
                    "project":    project_name,
                    "filename":   fpath.name,
                    "tier":       type_label,
                    "session_id": session_id,
                    "type":       type_label,
                    "ingested_at": now,
                },
            )

            if "[RAG_FAULT]" in result or "Ingest failed" in result:
                error_count += 1
                results.append((rel, "ERROR", result[:80]))
            else:
                manifest[rel] = {
                    "sha256":      sha256,
                    "doc_id":      doc_id,
                    "ingested_at": datetime.datetime.utcnow().isoformat(),
                }
                if status_label == "NEW":
                    new_count += 1
                else:
                    changed_count += 1
                results.append((rel, status_label, "✓"))

        except Exception as exc:  # noqa: BLE001
            error_count += 1
            results.append((rel, "ERROR", str(exc)[:80]))

    try:
        manifest_path.write_text(
            _json.dumps(manifest, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
    except Exception:  # noqa: BLE001
        pass

    col_w = max((len(r[0]) for r in results), default=10)
    header = f"{'FILE':<{col_w}}  {'STATUS':<8}  NOTE"
    sep    = "-" * (col_w + 24)
    lines  = [f"\n[INGEST] Project: {project_name}", sep, header, sep]
    for fname, status, note in results:
        lines.append(f"{fname:<{col_w}}  {status:<8}  {note}")
    lines.append(sep)
    lines.append(
        f"Total: {len(results)} files — "
        f"NEW={new_count}  UPDATED={changed_count}  "
        f"SKIPPED={skipped_count}  ERROR={error_count}"
    )
    report = "\n".join(lines)
    _log.info(report)
    return report

