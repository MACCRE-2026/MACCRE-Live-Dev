# Functional Ledger Report: MACCREv2 Memory, Schemas, Ingestion, Patterns, and Utils

**Target Output File:** `B:\EXO_GANS\Analysis\Wave1\05_memory_schemas_utils_ledger.md`  
**Analysis Date:** 2026-07-24  
**Scope:** Granular line-by-line functional analysis of core foundational packages in `maccre_core`.

---

## 1. Executive Abstract & Doctrine Compliance

This functional ledger details the internal architecture, data structures, and operational semantics of five foundational subsystems within `maccre_core`:
1. **Memory (`maccre_core/memory/*`)**: `sovereign_store.py`, `chroma_store.py`, `knowledge_store.py`
2. **Schemas (`maccre_core/schemas/*`)**: `sovereign_schema.py`, `topology_schemas.py`, `ledger_models.py`
3. **Ingestion (`maccre_core/ingestion/*`)**: `base_parser.py`, `gemini_parser.py`, `ai_studio_parser.py`, `antigravity_parser.py`, `fingerprint_index.py`
4. **Patterns (`maccre_core/patterns/*`)**: `pattern_executor.py`, `brief_packet.py`, `__init__.py`
5. **Utils (`maccre_core/utils/*`)**: `path_resolver.py`, `session_manager.py`, `secret_auth.py`, `session_utils.py`

---

## 2. Memory Subsystem (`maccre_core/memory/*`)
- **`PinRecord`**: Stored knowledge primitive using `__slots__ = ("doc_id", "text", "vector", "metadata", "distance")`.
- **`KnowledgeStore(abc.ABC)`**: Abstract interface defining mandatory operations.
- **`SovereignPinStore`**: Zero-dependency SQLite FTS5 store using standard library `sqlite3` in WAL mode with binary vector serialization (`_vec_to_blob`, `_blob_to_vec`, `_cosine_distance`).

---

## 3. Schemas & Type Enforcement (`maccre_core/schemas/*`)
- **`sovereign_schema.py`**: Custom zero-dependency validator replacing Pydantic with standard library reflection (`dict_to_dataclass`, `_resolve_type`).
- **`topology_schemas.py`**: `AgentRecordSchema`, `TopologyNode`, `ForgeProposal`.
- **`ledger_models.py`**: `FlowChatEntry`, `FlowSystemEntry`, `FlowSessionLog`.

---

## 4. Ingestion Pipeline & File Cabinet (`maccre_core/ingestion/*`)
- **`BaseParser(ABC)`**: Abstract parser interface.
- **Specialized Parsers**: `GeminiParser`, `AIStudioParser`, `AntigravityParser`.
- **`FingerprintManager`**: Cryptographic SHA-256 hash tracking for file ingestion deduplication.

---

## 5. Swarm Patterns & Execution Engine (`maccre_core/patterns/*`)
- **`PatternDefinition`**: Dataclass holding pattern metadata and compiling topology/roster CSVs.
- **`PatternExecutor`**: Materializes pattern templates into ephemeral project silos at `__DATACENTER/PATTERN_<name>_<job_id>/`.
- **`BriefPacket`**: Context packet delivered at `HUMAN_GATE` nodes.

---

## 6. Utility Layer & Core Infrastructure (`maccre_core/utils/*`)
- **`path_resolver.py`**: Runtime root anchoring via `get_maccre_root()` and `get_datacenter_path()`.
- **`session_manager.py`**: SQLite `project_registry.db` tracking unique project silos, sessions, and flow history.
- **`secret_auth.py`**: Steganographic auth using NTFS Alternate Data Stream `csv_path:maccre_auth`.
