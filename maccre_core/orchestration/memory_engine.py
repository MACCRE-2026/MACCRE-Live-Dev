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

Extracts Knowledge Triplets from every swarm node's output and pins them
to the project-scoped corkboard at
__DATACENTER/<project>/02_Dynamic_Context/memory_pins.

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


# ── Engine ────────────────────────────────────────────────────────────────────

class CognitiveMemoryEngine:
    """Phase 4: The Universal Observer that extracts and pins Swarm memories."""

    def __init__(self, memory_dir: str = "") -> None:
        active_project = os.environ.get("MACCRE_ACTIVE_PROJECT", "GLOBAL")
        self.memory_dir = (
            memory_dir
            or str(get_maccre_root() / "__DATACENTER" / active_project / "02_Dynamic_Context" / "memory_pins")
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

            # Keep the raw json dump as a forensic backup in 02_Dynamic_Context/memory_pins
            out_path = os.path.join(self.memory_dir, f"pin_{source_node}_{file_name}.json")
            with open(out_path, "w", encoding="utf-8") as f:
                json.dump(triplets, f, indent=2)

            logger.info(f"[Memory Engine] Extracted {len(triplets)} thought pins to the Corkboard.")

            # NOTE: Session-level thought_pins.db creation has been removed.
            # Knowledge triplets (thought-pins) are now only vectorized during
            # canonize_session() to save on embedding cost and compute overhead.
            # The raw JSON file in 02_Dynamic_Context/memory_pins/ serves as the forensic backup
            # until the session is promoted to the project-level canon.

        except Exception as e:
            logger.info(f"[Memory Engine] Extraction skipped/failed: {e}")
