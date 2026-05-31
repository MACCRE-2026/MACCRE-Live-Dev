# Era 3: Project Nexus (Memory & Cryptography)

## Chronological & Conceptual Evolution
The `Sample` folder contained the core logic for Project Nexus, integrating advanced concepts like vector storage (`ChromaDB`), credential encryption (`key_vault.py`), and Model Context Protocol integrations (`mcp_server_v5.py`). This codebase attempted to elevate the system from a stateless pipeline into a Long-Term Memory (LTM) cognitive agent with multi-modal embeddings.

## Core Breakthroughs
- **Secure Vault Architecture**: Successful implementation of PBKDF2HMAC key derivation and AES-based `Fernet` encryption, protecting API keys via standard passphrase unlocks.
- **Delta Sync / Lazy Indexing**: The `index_system_metadata` logic mathematically skipped unchanged files by checking OS `mtime`, pushing ingestion latency to O(1).
- **Strangler Fig Design Patterns**: The earliest hints of abstracting LLM providers via `LLMProvider(ABC)`.

## Dead Ends & Spaghetti
- **Monolithic God Objects**: The `MemoryVault` class handled everything from config and relative path calculation to database connection, semantic chunking, flat-file logging, and document parsing.
- **Hardcoded Relative Pathing**: Relied on fragile `os.path.dirname(os.path.dirname(__file__))` constructions, causing execution failures when imported from external modules like `maccre_router.py`.
- **Spaghetti Warning**: **Never merge I/O processing (chunking text) with I/O destination (ChromaDB API).** Text processing primitives MUST remain in `text_tools`, while storage interfaces must strictly reside in `storage_tools`.
