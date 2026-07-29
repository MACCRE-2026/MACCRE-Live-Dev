# MACCREv2 Evolution Roadmap
## From Sovereign Exo-Cortex to Distributed Cognition Engine

> Status: PLANNING — No work begins until Phase 0 is proven complete.
> Sequence is strict. Each phase is a prerequisite for the next.

---

## Phase 0 — Prove What We Have (NOW)
**Goal:** Demonstrate the workbook-sovereign pipeline executes real work, end-to-end, before any further structural changes.

**Definition of "working":**
- `MACCRE_Global.xlsx` filled with a real project definition, one real agent, one real topology node
- `maccre.py global` reads the workbook, passes completeness gate, prints EXECUTION_PLAN, runs the swarm
- The swarm produces a real output artifact in `04_Code_Artifacts`
- Session is registered in `project_registry.db` with correct timestamps
- `maccre.py ingest <project>` successfully ingests at least one source document into ChromaDB (SHA-256 gated)
- `maccre.py canonize` writes the session summary to `03_Agent_Ledgers`
- `omni qa` stays green throughout

**What we are NOT doing in Phase 0:**
- No new features
- No architecture changes
- No dependency modifications after the venv repair

---

## Phase 1 — Sovereignty Foundation
**Trigger:** Phase 0 proven complete.
**Goal:** Clean the dependency surface. Establish the vendor layer.

### 1A — Requirements Triage
- Audit `requirements.txt` against the actual 12 imports the codebase uses
- Create `requirements-sovereign.txt`: only the 12 packages actually imported (pinned, exact versions)
- Create `requirements-optional.txt`: anthropic, openai, groq — installed separately, never auto-required
- Remove all dead packages: flet, flet-desktop, streamlit, textual, altair, pydeck, narwhals, pandas, and all their cascades (~40 packages, ~300MB venv reduction)
- Update `requirements.txt` to reference the sovereign + optional split

### 1B — Vendor Layer Scaffold
- Create `maccre_core/_vendor/` directory with its own `__init__.py` and `README.md` explaining the sovereignty strategy
- Create `maccre_core/_net/` — future home for all native HTTP clients, currently empty with ABC interfaces defined

### 1C — Vendor openpyxl
- Copy `openpyxl` source into `maccre_core/_vendor/openpyxl/`
- Import shim: `maccre_core/_vendor/__init__.py` re-exports it so all existing `import openpyxl` calls work unmodified
- Remove openpyxl from `requirements-sovereign.txt` — it now comes from source
- All workbook r/w is now zero-dependency at the PyPI level

### 1D — Native OOXML Writer (Replaces openpyxl long-term)
- Design a write-only `maccre_core/_net/ooxml.py` — sovereign xlsx generation without openpyxl
- xlsx is a ZIP archive containing XML files. A write-only implementation is ~800 lines of stdlib `zipfile` + `xml.etree`
- `generate_global_template.py` migrates to native writer first (lowest risk)
- Read path stays on vendored openpyxl until read-only OOXML parsing is validated

### 1E — Project Root Anchoring *(Law VIII — COMPLETE as of Phase 19)*
- All module-level path constants and default parameter values must derive from `get_maccre_root()` in `maccre_core/utils/path_resolver.py`
- `get_maccre_root()` implements a two-tier priority cascade: `MACCRE_ROOT` env var (highest) → `Path(__file__).resolve().parent` traversal (fallback)
- Default parameter idiom for pyright compliance: `def __init__(self, path: str = "") -> None: self.path = path or str(get_maccre_root() / "subdir")`
- Hardcoded absolute paths (e.g. `"B:/MACCREv2/..."`) are treated as a **build violation** — equivalent to a hardcoded IP address
- `setup_mcp.py` at project root: one-run portable setup for new installations on any machine or drive letter

---

## Phase 2 — Thought Pin Memory System
**Trigger:** Phase 1 complete, venv stable.
**Goal:** Replace ChromaDB with a sovereign SQLite FTS5 + agent-curated semantic index.

### 2A — Archive the ChromaDB Layer
- Move `ingest_document()`, `query_local_memory()`, and ChromaDB-specific code in `rag_tools.py` behind a `KnowledgeStore` ABC interface
- `ChromaDBStore` becomes one concrete implementation — still default, not removed
- `SovereignPinStore` is the new concrete implementation being built
- At no point does ChromaDB break while the replacement is in progress

### 2B — Sidecar Format Specification
- Define `.pins.json` schema (finalized from planning session):
  - `source_sha256`: links pin set to exact file version
  - `source_path`: relative from `01_Raw_Source`
  - `pinned_at`: ISO timestamp
  - `agent`: agent persona name from the workbook
  - `project_context`: which project's lens this pin set was created under (empty = generic)
  - `pins[]`: array of `{id, statement, context, weight, tags[]}`
- Schema is versioned. Future evolution of the format is non-breaking.

### 2C — thought_pins.db (SQLite FTS5)
- Single WAL-mode SQLite database per project at `02_Dynamic_Context/thought_pins.db`
- FTS5 virtual table indexing: `pin_id`, `source_sha256`, `source_path`, `statement`, `context`, `tags`, `project_context`
- Standard metadata table: `pins_meta` with rowid foreign key, timestamps, weight
- Index is **always reconstructable** from the `.pins.json` sidecars — it is a derived artifact, not the source of truth
- Rebuild command: `maccre.py reindex <project>` — scans all `.pins.json` files and re-populates `thought_pins.db`

### 2D — Archivist Persona
- New agent persona: `ArchivistAgent` — defined in the workbook's AGENTS sheet like any other agent
- Archivist is invoked by `maccre.py ingest` when the project is using `SovereignPinStore`
- Archivist reads the source document + the project's `DESCRIPTION` from `PROJECT_DEFINITION`
- Produces a `.pins.json` sidecar alongside the source file
- SHA-256 gating: if sidecar already exists and hash matches, archivist is skipped (uses existing manifest logic)
- Archivist tier is configurable: `archival_tier: cloud` (Gemini Flash) or `archival_tier: local` (Ollama, for S25)

### 2E — Cross-Project Re-Contextualization
- When `LINKED_PROJECTS` is populated in the workbook, the ingest command re-runs the archivist for each linked document
- Re-contextualization produces a new sidecar: `source.PROJECT_NAME.pins.json` — does not overwrite the generic pins
- The archivist's prompt for re-contextualization receives: the original document + the linked project's DESCRIPTION + the linked project's README
- The FTS5 index includes `project_context` as a searchable field — queries can be scoped or federated

### 2F — Migration and Retirement
- `SovereignPinStore` is tested in parallel with ChromaDB until query quality is validated on real project data
- When validated: ChromaDB is removed from `requirements-sovereign.txt`
- `chromadb`, `onnxruntime`, `numpy`, `kubernetes`, `grpcio`, `opentelemetry` full stack, `tokenizers`, `uvicorn`, `orjson`, `mmh3`, `pybase64` — all evaporate as transitive deps
- Estimated reduction: ~120 packages from the venv

---

## Phase 3 — S25 Integration
**Trigger:** Phase 2 complete, archivist locally validated.
**Goal:** S25 Ultra as an autonomous overnight archivism daemon.

### 3A — Ollama Archivist Tier Validation
- Test archivist pipeline with `archival_tier: local` against the laptop's Ollama instance first
- Validate that Gemma 3 4B produces pin quality acceptable for production use
- Tune the archivist's persona and instruction set for local model behavior (local models benefit from more explicit output format guidance)

### 3B — Phone-Side MACCRE Minimal Node
- Termux on S25 Ultra running Ollama with Gemma 3 (NPU-accelerated via Samsung AI stack)
- Minimal MACCRE install: `maccre.py`, `maccre_core/`, sovereign venv — no GUI, no cloud deps
- `maccre.py ingest` is the only command the phone needs to run autonomously
- Drive sync provides `01_Raw_Source` files; phone writes `.pins.json` sidecars back

### 3C — Drive-Mediated Trigger
- Workbook EXECUTION_PLAN `INGEST` checkbox triggers the archivist when `maccre.py global` is run on the phone
- Phone monitors its Drive-synced project folder for new source files
- Results propagate back to laptop via Drive sync
- Laptop runs `maccre.py reindex <project>` to rebuild `thought_pins.db` from updated sidecars

---

## Phase 4 — Native Client Replacement
**Trigger:** Phase 3 stable.
**Goal:** Eliminate `google-genai` and Google auth client dependencies.

### 4A — Sovereign Gemini HTTP Client
- `maccre_core/_net/gemini_client.py` — direct `urllib` REST calls to Gemini API
- Same interface as the existing `UniversalRouter.generate()` — drop-in replacement
- Eliminates: `google-genai`, `google-auth`, `google-auth-oauthlib`, `google-api-core`, `httpx`, `anyio`, `sniffio`, `protobuf`, `googleapis-common-protos`, `proto-plus` — approximately 15 packages
- Tested behind the existing router interface; no callers change

### 4B — Sovereign Drive HTTP Client
- `maccre_core/_net/drive_client.py` — direct OAuth2 PKCE + Drive REST API via `urllib`
- PKCE flow: redirect to localhost, capture token, store in Windows Vault (already have vault)
- Replaces `google-auth-oauthlib`, `google-api-python-client`, `httplib2`, `uritemplate`

### 4C — Sovereign Schema Validation
- `maccre_core/schemas/sovereign_schema.py` — `dataclasses` + `__post_init__` validation replacing Pydantic's role in the router
- `AgentResponse` is the only Pydantic-enforced schema in the active code path
- A `SovereignSchema` base class with field typing, required field checking, and JSON round-trip is ~150 lines
- Pydantic is retained in `requirements-optional.txt` for anthropic/openai SDK compatibility but removed from sovereign path

---

## Phase 5 — Neuronal Node Architecture
**Trigger:** Phase 4 stable. System is fully sovereign.
**Goal:** Define the minimal node interface and the P2P query protocol.

### 5A — The Minimal Node Contract
A MACCRE node at minimum must be able to:
- Maintain a local `thought_pins.db` with FTS5 query capability
- Run one archivist agent (cloud or local tier)
- Accept a query over a defined P2P protocol and return matching pin statements
- Declare its node identity, topic signature (aggregate of its tags), and last-active timestamp
- Operate fully offline; P2P is opportunistic, not required

### 5B — P2P Query Protocol
- Node-to-node queries: `{query_text, requester_id, scope, depth}` over local network or internet (WebSocket or simple HTTP)
- Response: `{pins[], source_hashes[], node_id, confidence}` — never raw documents, only pins (privacy boundary)
- Depth controls fan-out: a node can forward a query to its known peers, who can forward to theirs
- No central directory. Node discovery via mDNS on LAN, optionally via a shared Drive file for trusted peer registration

### 5C — Pin Propagation
- A pin that arrives from an external node via query is **not automatically stored** — the local archivist evaluates it
- If the local archivist judges the incoming pin relevant to the local project context, it is pinned with `source: external, origin_node: <id>`
- This is the analog of synaptic strengthening: knowledge that is repeatedly queried and validated by multiple nodes gains weight
- Pins with high cross-node confirmation weight get elevated in local FTS5 `weight` field

### 5D — Network Topology
- Mesh, not hierarchy. No master node.
- Each node maintains a peer list of 8-32 trusted nodes (like BitTorrent's DHT)
- Gossip protocol for node health: nodes periodically exchange topic signatures so the mesh can route queries efficiently
- The network has no center. This is architecturally essential to the emergence thesis.

---

## Phase 6 — Distributed Deployment
**Trigger:** Phase 5 architecture validated on laptop + S25 two-node test.
**Goal:** Multi-device mesh, privacy-preserving, user-controlled.

### 6A — Privacy Boundary Definition
- Every pin is tagged `visibility: private | trusted | open`
- `private`: never leaves the node (default)
- `trusted`: shared only with named peers in the peer list
- `open`: available to any querying node
- The user controls visibility in the workbook (`SESSION_CONFIG` or global `VAULT_KEYS`)

### 6B — Node Identity and Trust
- Each node has a keypair (Windows CNG via ctypes — already sovereign)
- Queries are signed. Responses are signed. No anonymous queries in the trusted tier.
- Trust is established out-of-band (you add a friend's node ID and public key)

### 6C — First External Deployment
- S25 Ultra as Node 2 in the user's personal mesh
- Validates the full loop: laptop archives → Drive → phone indexes → phone queries laptop → laptop queries phone

---

## Dependency Elimination Scorecard (Projected)

| Phase | Packages Removed | Venv Reduction |
|---|---|---|
| Phase 1 (dead GUI deps) | ~40 | ~300 MB |
| Phase 2 (chromadb + cascade) | ~120 | ~200 MB |
| Phase 4 (google-genai + auth cascade) | ~30 | ~150 MB |
| **Total projected** | **~190/189** | **~961 MB → ~50 MB** |

The endgame venv contains approximately:
`sqlite3` (stdlib) + `pywin32` (ctypes Windows vault) + `requests` (or native urllib) + `openpyxl` (vendored) + Ollama HTTP (one function) = **sovereign core**.
