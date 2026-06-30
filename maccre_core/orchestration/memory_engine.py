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
maccre_core/orchestration/memory_engine.py
============================================
Phase 4: The Universal Observer.

Extracts Knowledge Triplets from canonized unified session ledgers
and pins them to the project-scoped SovereignPinStore (SQLite3) at
__DATACENTER/<project>/02_Dynamic_Context/memory_pins.db.
"""
import os
import json
import sqlite3
from typing import TypedDict, List, cast

from maccre_core._net.gemini_client import GeminiClient, user_turn
from maccre_core.orchestration.universal_vault import get_provider_credential
from maccre_core.utils.path_resolver import get_maccre_root

import logging

logger = logging.getLogger(__name__)


# ── Strict Schema for a "Thought Pin" ─────────────────────────────────────────

class KnowledgeTriplet(TypedDict):
    subject: str
    predicate: str       # e.g. "is mathematically similar to", "depends on"
    object: str
    significance: str    # One sentence explaining WHY this connection matters


class MemoryExtraction(TypedDict):
    triplets: List[KnowledgeTriplet]


# ── SQLite SovereignPinStore ──────────────────────────────────────────────────

class SovereignPinStore:
    """Project-level database for tracking semantic pins from canonized sessions."""
    def __init__(self, db_path: str) -> None:
        self.db_path = db_path
        self._init_db()
        
    def _init_db(self) -> None:
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS memory_pins (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    job_id TEXT NOT NULL,
                    ledger_path TEXT NOT NULL,
                    subject TEXT,
                    predicate TEXT,
                    object TEXT,
                    significance TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
    def store_triplets(self, job_id: str, ledger_path: str, triplets: List[dict]) -> None:
        with sqlite3.connect(self.db_path) as conn:
            for t in triplets:
                conn.execute(
                    "INSERT INTO memory_pins (job_id, ledger_path, subject, predicate, object, significance) VALUES (?, ?, ?, ?, ?, ?)",
                    (job_id, ledger_path, t.get("subject"), t.get("predicate"), t.get("object"), t.get("significance"))
                )


# ── Engine ────────────────────────────────────────────────────────────────────

class CognitiveMemoryEngine:
    """Phase 4: The Universal Observer that extracts and pins Swarm memories."""

    def __init__(self, db_path: str = "") -> None:
        active_project = os.environ.get("MACCRE_ACTIVE_PROJECT", "GLOBAL")
        self.db_path = (
            db_path
            or str(get_maccre_root() / "__DATACENTER" / active_project / "02_Dynamic_Context" / "memory_pins.db")
        )
        self.store = SovereignPinStore(self.db_path)

        raw_key = get_provider_credential("MACCRE_Sovereign")
        if not raw_key or not str(raw_key).strip().startswith("AIza"):
            raise ValueError(
                "CRITICAL: Vault returned empty or invalid key for Memory Engine. "
                f"Got: '{raw_key}'"
            )

        self.client = GeminiClient(key_provider=lambda: get_provider_credential("MACCRE_Sovereign"))
        self.extractor_model = "gemini-2.5-flash"

    def extract_from_canonized_ledger(self, ledger_path: str, job_id: str) -> None:
        """Silently extracts thought pins from a unified ledger and saves them to SQLite."""
        try:
            with open(ledger_path, "r", encoding="utf-8") as f:
                agent_payload = f.read()
                
            if not agent_payload or len(agent_payload) < 100:
                return

            schema_hint = (
                '{"triplets": [{"subject": "...", "predicate": "...", "object": "...", "significance": "..."}]}'
            )
            system = (
                "You are the MACCREv2 Cognitive Memory Engine. "
                "Analyze the following session ledger output. Extract the most brilliant conceptual, mathematical, "
                "or architectural relationships and output them as strict Knowledge Triplets. "
                "Ignore conversational filler. Only pin high-value concepts. "
                f"You MUST reply with ONLY valid JSON matching this schema exactly: {schema_hint}"
            )

            response = self.client.generate_content(
                model=self.extractor_model,
                contents=[user_turn(agent_payload)],
                system_instruction=system,
                temperature=0.1,
            )

            raw = response.text.strip()
            # Strip markdown fences if the model added them
            if raw.startswith("```"):
                raw = raw.split("```")[1]
                if raw.startswith("json"):
                    raw = raw[4:]

            extraction: dict[str, object] = json.loads(raw)
            triplets = cast(List[object], extraction.get("triplets", []))

            if not triplets:
                return

            self.store.store_triplets(job_id, ledger_path, triplets)
            logger.info(f"[Memory Engine] Extracted {len(triplets)} thought pins to SovereignPinStore.")

        except Exception as e:
            logger.info(f"[Memory Engine] Extraction skipped/failed: {e}")
