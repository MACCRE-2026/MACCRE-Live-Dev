# MACCREv2 Master Architectural Roadmap

## Phase 1: Swarm Session State Architecture
Our current swarm queue is stateless. If a crash occurs, tasks become permanently orphaned ghosts. We will introduce a crosslinked metadata system to serve as a live anchor for fixing and resuming failed swarms.

### 1.1 Swarm Session State Architecture
- **Job Sessions Table:** Introduce `job_sessions` in `swarm_queue.db` (`job_id`, `status`, `current_ledger_path`, `topology_csv`).
- **Live Telemetry:** Update `LocalMessageBroker` and `flow_engine.py` to live-write execution state and update the `current_ledger_path` after every completed node.
- **The Dead Letter Queue & Orphaned Job Mall:** 
  - Sessions that crash or are cancelled are moved to a dead letter status.
  - *Future Expansion:* An automated agent will eventually categorize these as "Junk" or "Resume Candidates" based on chronological followup and contextual usefulness.
  - *Immediate Action:* Provide a TUI UI to review failed sessions, allowing the user to clear the junk and select "Resume" for valid candidates.

### 1.2 HITL Injection & Collaborative Nexus Fixing
- **Contextual Injection:** When a flow hits a `MANUAL` pause, or resumes from failure, the HITL modal will display the *unified history* of the ledger alongside the injection text area.
- **Nexus Copilot Integration:** Build a pathway to send a snapshot of the topology and ledgers directly to Nexus. Nexus will be equipped with specialized schema-reading tools allowing it to recursively inspect the specific SQLite databases and ledger files to deeply understand what went wrong and help you fix the codebase before resuming the swarm.

### 1.3 Linear Flow Editor Persistence
- Flow topologies that are currently being edited but have *not* been launched should persist if the app is closed or the modal is dismissed. 
- Once a flow is fully validated and launched, the topology is permanently saved/committed to the session state.

---

## Phase 2 Addendum: The Sovereign File Cabinet & Universal Auth Layer

**Objective:** Completely overhaul the ingestion pipeline into a centralized "File Cabinet" that manages data state, telemetry, and encrypted, provider-agnostic credentials. This replaces the legacy "Notebook" nomenclature with streamlined Knowledge Collections.

* **State-Aware Ingestion Pipeline:** When files are ingested, the File Cabinet extracts all readable text and metadata, converts them into thought-pins within the project's SQLite memory, and copies the raw file to `02_Dynamic_Context\KnowledgeStore\[CollectionName]`.
* **Cryptographic Fingerprinting:** Every ingested file is hashed (e.g., SHA-256) and tracked in a global JSON fingerprint index. This tracks the state of the data, prevents duplication, and intelligently manages updates to modified files.
* **Universal Auth Vault:** The File Cabinet serves as the ingestion point for all cloud provider credentials (Google, OpenAI, Anthropic, xAI). Credentials are managed by a federated system prioritizing the OS Vault (`keyring`) with a gracefully degrading AES-encrypted `.bin` fallback.
* **Agnostic Probing & Routing:** Upon key ingestion, the system silently probes the provider to log available models and capabilities. The `UniversalSwarmWorker` will be expanded to natively route payloads and tool calls to any of these providers dynamically based on the Agent's profile.

---

## Phase 4: The FinOps Onion & High-Cost Authorizations

**Objective:** Transform expensive media rendering and massive ingestion operations into "Specialized Tool Calls" that mandate a Human-in-the-Loop (HITL) pause for cost approval.

* **Pre-Execution Pause Hooks:** Modify rendering tools so that *before* calling Cloud APIs, they emit a `ManualInputRequired` pause event.
* **TUI Authorization Modal:** When paused on a FinOps gate, display the requested action, estimated token cost, and USD burn. Allow the user to Approve, Adjust, or Consult the Swarm.
* **Ledger Reconciliation:** Build a continuous ledger comparing *Estimated Cost* vs *Actual Execution Cost*. 

---

## Phase 4.5: Tool Compliance & Refactoring

**Objective:** Audit and modernize the complete agent-facing tool registry to ensure compliance with the SovereignPinStore vector database, dynamic project-aware pathing, and hybrid search grounding requirements.

* **Tool Registry Audit:** Evaluate all active tools to verify they adhere to the Strangler Fig pattern and Project-Aware adapters (especially `query_local_memory` and telemetry reading tools).
* **Multi-Tier Search Logic:** Implement the Hybrid Exclusionary Search logic (coordinating Google Search Grounding with Brave LLM indexing) and Tri-Grounding system prompt injection rules.
* **Phase 5 Preparation:** Identify and develop the required new tooling endpoints (such as granular vision tools or extended extraction capabilities) necessary to support the upcoming Multimodal Ingestion overhaul in Phase 5.

---

## Phase 5: Multimodal Ingestion (The Horizon Goal)

**Objective:** Execute the Alphabet Oracle's design for semantic visual ingestion.

* **Visionary Scout Agent:** Implement an agent role dedicated to processing images (e.g., graphic novel panels) during File Cabinet ingestion.
* **Synthetic Metadata Generation:** Have the Scout output spatial bounding boxes, distinct dialogue tags, and synthetic text descriptions of the art. 
* **Triune Memory Linking:** Store the synthetic text in the sovereign SQLite database (for fast semantic RAG) but retain a hard URI pointer to the raw `.jpg`/`.png` in the `01_Raw_Source` tier. This allows downstream agents to search text, but fetch the original pixels when passing context to a render pipeline.
