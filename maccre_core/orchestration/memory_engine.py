# ┌─────────────────────────────────────────────────────────────────────────────┐
# │  MACCREv2 ENGINEERING DOCTRINE                             Law Rev: 19.0   │
# ├─────────────────────────────────────────────────────────────────────────────┤
# │  I.   TYPING      All signatures: explicit Python 3.11+ type hints.        │
# │  II.  LINTING     Zero unused imports. No wildcards. 120-char line max.    │
# │  III. PATHS       Never hardcode absolute paths. Use get_maccre_root().     │
# │                   Default params: def f(p:str='') -> None: p=p or root/x   │
# │  IV.  DATACENTER  6-Tier: 01_Raw_Source · 02_Dynamic_Context               │
# │                           03_Agent_Ledgers · 04_Code_Artifacts             │
# │                           05_Rendered_Media · 06_Memory_Pins               │
# │  V.   DIAMOND     Gen: temp=1.0  ·  Critic: temp=0.1 + dataclass schema   │
# │  VI.  ABSTRACTION All I/O behind abc.ABC before any concrete driver.       │
# │  VII. TEARDOWN    try/finally on all handles (omni clean compliance).      │
# │  VIII.TELEMETRY   No bare print(). logger only. JSON → 03_Agent_Ledgers.  │
# └─────────────────────────────────────────────────────────────────────────────┘
"""
maccre_core/orchestration/memory_engine.py
============================================
Phase 4: The Universal Observer.

Extracts Knowledge Triplets from every swarm node's output and pins them
to the project-scoped corkboard at
__DATACENTER/<project>/06_Memory_Pins (the official 6th data tier).

Project-scoping ensures thought pins from Project A never leak into
Project B's semantic context, and allows cross-pollination to be
explicitly managed via the Synaptic Bridge when desired.
"""
import os
import json
from typing import TypedDict, List, cast

from maccre_core._net.gemini_client import GeminiClient, user_turn
from maccre_core.orchestration.windows_vault import get_native_credential
from maccre_core.utils.path_resolver import get_maccre_root


# ── Strict Schema for a "Thought Pin" ─────────────────────────────────────────

class KnowledgeTriplet(TypedDict):
    subject: str
    predicate: str       # e.g. "is mathematically similar to", "depends on"
    object: str
    significance: str    # One sentence explaining WHY this connection matters


class MemoryExtraction(TypedDict):
    triplets: List[KnowledgeTriplet]


# ── Engine ────────────────────────────────────────────────────────────────────

class CognitiveMemoryEngine:
    """Phase 4: The Universal Observer that extracts and pins Swarm memories."""

    def __init__(self, memory_dir: str = "") -> None:
        active_project = os.environ.get("MACCRE_ACTIVE_PROJECT", "GLOBAL")
        self.memory_dir = (
            memory_dir
            or str(get_maccre_root() / "__DATACENTER" / active_project / "06_Memory_Pins")
        )
        os.makedirs(self.memory_dir, exist_ok=True)

        raw_key = get_native_credential("MACCRE_Sovereign")
        if not raw_key or not str(raw_key).strip().startswith("AIza"):
            raise ValueError(
                "CRITICAL: Vault returned empty or invalid key for Memory Engine. "
                f"Got: '{raw_key}'"
            )

        self.client = GeminiClient(api_key=str(raw_key).strip())
        self.extractor_model = "gemini-2.5-flash"

    def extract_and_store(self, agent_payload: str, source_node: str, file_name: str) -> None:
        """Silently extracts thought pins from the payload and saves them to the corkboard."""
        if not agent_payload or len(agent_payload) < 100:
            return

        schema_hint = (
            '{"triplets": [{"subject": "...", "predicate": "...", "object": "...", "significance": "..."}]}'
        )
        system = (
            "You are the MACCREv2 Cognitive Memory Engine. "
            "Analyze the following agent output. Extract the most brilliant conceptual, mathematical, "
            "or architectural relationships and output them as strict Knowledge Triplets. "
            "Ignore conversational filler. Only pin high-value concepts. "
            f"You MUST reply with ONLY valid JSON matching this schema exactly: {schema_hint}"
        )

        try:
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

            # Keep the raw json dump as a forensic backup in 06_Memory_Pins
            out_path = os.path.join(self.memory_dir, f"pin_{source_node}_{file_name}.json")
            with open(out_path, "w", encoding="utf-8") as f:
                json.dump(triplets, f, indent=2)

            print(f"[Memory Engine] Extracted {len(triplets)} thought pins to the Corkboard.")

            # Embed and upsert into the ephemeral session database
            session_id = file_name
            project_name = os.environ.get("MACCRE_ACTIVE_PROJECT", "GLOBAL")
            
            try:
                from maccre_core.tools.rag_tools import get_gemini_embedding
                from maccre_core.memory.knowledge_store import get_knowledge_store, PinRecord
                import uuid
                import datetime
                
                db_name = f"session_{session_id}_thought_pins.db"
                store = get_knowledge_store(project_name, db_name=db_name)
                
                # We embed the entire array of triplets as one semantic concept for this node
                concept_text = json.dumps(triplets)
                vector = get_gemini_embedding(concept_text, task_type="RETRIEVAL_DOCUMENT")
                doc_id = f"pin_{source_node}_{uuid.uuid4().hex[:8]}"
                
                safe_meta = {
                    "project": project_name,
                    "session_id": session_id,
                    "agent_id": source_node,
                    "type": "thought_pin",
                    "ingested_at": datetime.datetime.utcnow().isoformat(),
                }
                
                store.upsert("swarm_memory", PinRecord(
                    doc_id=doc_id,
                    text=concept_text,
                    vector=vector,
                    metadata=safe_meta,
                ))
                print(f"[Memory Engine] Ephemeral Vector Success: Upserted {len(triplets)} pins to {db_name}")
            except Exception as vec_err:
                print(f"[Memory Engine] Ephemeral Vector Failed: {vec_err}")

        except Exception as e:
            print(f"[Memory Engine] Extraction skipped/failed: {e}")