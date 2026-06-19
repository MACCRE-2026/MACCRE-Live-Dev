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

Moves vectors generated during a specific Session up to the Project-level
or Global-level Sovereign DB.
"""
from __future__ import annotations

import logging

from maccre_core.memory.knowledge_store import get_knowledge_store

logger = logging.getLogger(__name__)

def canonize_job(
    project_name: str, 
    job_id: str, 
    session_id: str, 
    target_scope: str = "project"
) -> int:
    """
    Promote all vectors associated with a specific job_id from the Session DB
    into either the Project DB or the Global DB.
    
    Args:
        project_name: The active project name.
        job_id: The specific job to canonize (e.g., "job_123").
        session_id: The session in which the job occurred.
        target_scope: "project" or "global".
        
    Returns:
        The number of vectors successfully canonized.
    """
    if target_scope not in ("project", "global"):
        raise ValueError(f"Invalid target_scope '{target_scope}'. Must be 'project' or 'global'.")
        
    source_store = get_knowledge_store(project_name, scope="session", session_id=session_id)
    target_store = get_knowledge_store(project_name, scope=target_scope)
    
    count = 0
    for collection in source_store.list_collections():
        all_pins = source_store.get_all(collection)
        for pin in all_pins:
            if pin.metadata.get("job_id") == job_id:
                # Merge target metadata to ensure scope traceability
                new_meta = dict(pin.metadata)
                new_meta["canonized_from_session"] = session_id
                
                pin.metadata = new_meta
                target_store.upsert(collection, pin)
                count += 1
                
    logger.info(f"[CANONIZE] Promoted {count} vectors from session {session_id} (job {job_id}) to {target_scope} DB.")
    return count
