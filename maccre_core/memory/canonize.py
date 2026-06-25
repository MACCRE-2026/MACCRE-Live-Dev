# ┌─────────────────────────────────────────────────────────────────────────────┐
# │  MACCREv2 ENGINEERING DOCTRINE                             Law Rev: 19.0   │
# ├─────────────────────────────────────────────────────────────────────────────┤
# │  I.   TYPING      All signatures: explicit Python 3.11+ type hints.        │
# │  II.  LINTING     Zero unused imports. No wildcards. 120-char line max.    │
# │  III. PATHS       Never hardcode absolute paths. Use get_maccre_root().     │
# │  IV.  DATACENTER  5-Tier Data Sovereignty.                                 │
# │  V.   DIAMOND     Separation of generation vs critique.                    │
# │  VI.  ABSTRACTION All I/O behind abc.ABC.                                  │
# │  VII. TEARDOWN    omni clean compliance.                                   │
# │  VIII.TELEMETRY   Strict JSON structured logging.                          │
# └─────────────────────────────────────────────────────────────────────────────┘
"""
maccre_core/memory/canonize.py
==============================
Sovereign Vector DB Triad Canonization logic.

Reads the unified_session_ledger.md for a given session, extracts High-Density 
Thought-Pins using the LLM, and inserts them into the Project-Level thought_pins.db.
"""
from __future__ import annotations

import json
import logging
import uuid
import datetime
from typing import Any

from maccre_core._net.gemini_client import GeminiClient, get_gemini_embedding
from maccre_core.memory.knowledge_store import get_knowledge_store, PinRecord
from maccre_core.utils.path_resolver import get_datacenter_path

logger = logging.getLogger(__name__)

def canonize_job(
    project_name: str, 
    job_id: str,
) -> int:
    """
    Parse a siloed Session (unified_session_ledger.md) and insert High-Density 
    Thought-Pins into the Project-Level thought_pins.db.
    
    Args:
        project_name: The active project name.
        job_id: The specific job to canonize (e.g., "job_123").
        
    Returns:
        The number of vectors successfully canonized.
    """
    ledger_path = get_datacenter_path("04_Code_Artifacts", job_id) / "unified_session_ledger.md"
    if not ledger_path.exists():
        logger.error(f"[CANONIZE] Unified session ledger not found for job {job_id}.")
        return 0
        
    ledger_content = ledger_path.read_text(encoding="utf-8")
    
    system_prompt = (
        "You are the Canonization Subagent. Your task is to extract high-density "
        "Thought-Pins from the provided unified session ledger. Focus only on critical "
        "architectural decisions, codebase mutations, and systemic learnings. "
        "Respond strictly in JSON format matching the schema: "
        "{'triplets': [{'subject': '', 'predicate': '', 'object': '', 'context': ''}]}"
    )
    
    client = GeminiClient()
    try:
        response = client.generate_content(
            model="gemini-3.1-pro-preview",
            contents=[ledger_content[:50000]], # Cap extraction context
            system_instruction=system_prompt,
            temperature=0.1,
            response_schema={
                "type": "OBJECT",
                "properties": {
                    "triplets": {
                        "type": "ARRAY",
                        "items": {
                            "type": "OBJECT",
                            "properties": {
                                "subject": {"type": "STRING"},
                                "predicate": {"type": "STRING"},
                                "object": {"type": "STRING"},
                                "context": {"type": "STRING"}
                            },
                            "required": ["subject", "predicate", "object"]
                        }
                    }
                },
                "required": ["triplets"]
            }
        )
        
        raw = response.text.strip()
        data = json.loads(raw)
        triplets = data.get("triplets", [])
    except Exception as e:
        logger.error(f"[CANONIZE] Extraction fault: {e}")
        return 0

    if not triplets:
        logger.info(f"[CANONIZE] No high-density pins extracted for {job_id}.")
        return 0
        
    target_store = get_knowledge_store(project_name, db_name="thought_pins.db")
    count = 0
    
    for triplet in triplets:
        try:
            concept_text = json.dumps(triplet)
            vector = get_gemini_embedding(concept_text, task_type="RETRIEVAL_DOCUMENT")
            doc_id = f"pin_{job_id}_{uuid.uuid4().hex[:8]}"
            safe_meta = {
                "project": project_name,
                "job_id": job_id,
                "type": "canonized_thought_pin",
                "ingested_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            }
            target_store.upsert("swarm_memory", PinRecord(
                doc_id=doc_id,
                text=concept_text,
                vector=vector,
                metadata=safe_meta,
            ))
            count += 1
        except Exception as pin_err:
            logger.warning(f"[CANONIZE] Failed to vectorize triplet: {pin_err}")
            
    logger.info(f"[CANONIZE] Promoted {count} high-density vectors from job {job_id} to Project DB.")
    
    # Track canonization event to project_registry.db or active_flow_topology
    try:
        import sqlite3
        registry_path = str(get_datacenter_path("..", "project_registry.db").resolve())
        # The path resolver usually anchors at the project. 
        # Actually, get_datacenter_path is relative to the ACTIVE project. 
        # The registry is at MACCRE_ROOT.
        from maccre_core.utils.path_resolver import get_maccre_root
        reg_db = get_maccre_root() / "project_registry.db"
        with sqlite3.connect(str(reg_db)) as conn:
            # We add a column to sessions table if not exists or a separate table
            conn.execute(
                "CREATE TABLE IF NOT EXISTS canonizations (job_id TEXT, project_name TEXT, pins_count INTEGER, canonized_at DATETIME DEFAULT CURRENT_TIMESTAMP)"
            )
            conn.execute(
                "INSERT INTO canonizations (job_id, project_name, pins_count) VALUES (?, ?, ?)",
                (job_id, project_name, count)
            )
    except Exception as e:
        logger.warning(f"[CANONIZE] Could not track canonization in registry: {e}")

    return count
