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
maccre_core/tests/test_mega_pipeline.py
=======================================
The MACCREv2 Mega-Test (Database-Aware).
Strict, synchronous execution of the DAG.
Proves local ChromaDB ingestion and RAG retrieval by the Nexus agent.
"""
from __future__ import annotations

import json
import os
import traceback
from typing import Any

from google.genai import types

from maccre_core.logger import setup_maccre_logger
from maccre_core.maccre_router import UniversalRouter
from maccre_core.tools.tool_registry import TOOL_DISPATCHER
from maccre_core.tools.rag_tools import ingest_document

# ── Configuration ─────────────────────────────────────────────────────────────
DATACENTER = "B:/MACCREv2/__DATACENTER"
RAW_SOURCE_DIR = f"{DATACENTER}/01_Raw_Source"
CONTEXT_DIR = f"{DATACENTER}/02_Dynamic_Context"
TARGET_FILE = f"{RAW_SOURCE_DIR}/conversation.md"
TEST_COLLECTION = "mega_test_memory"

logger = setup_maccre_logger("MEGA_TEST")


def load_persona(persona_id: str) -> str:
    path = f"{CONTEXT_DIR}/{persona_id.lower()}.json"
    if not os.path.exists(path):
        raise FileNotFoundError(f"CRITICAL: Persona {persona_id} not found at {path}")
    with open(path, "r", encoding="utf-8") as f:
        data: dict[str, Any] = json.load(f)
        return data.get("instructions", "")


def setup_dummy_file() -> None:
    os.makedirs(RAW_SOURCE_DIR, exist_ok=True)
    if not os.path.exists(TARGET_FILE):
        with open(TARGET_FILE, "w", encoding="utf-8") as f:
            f.write(
                "USER A: I think the integration of local SQLite WAL mode with cloud LLMs "
                "is the only way to maintain data sovereignty.\n"
            )
            f.write(
                "USER B: Agreed, but the latency of the cloud TTS models is a bottleneck "
                "for real-time media generation. We need a local fallback.\n"
            )
            f.write(
                "USER A: If we use Kokoro locally, we drop the cost to zero, but we lose "
                "the emotive prosody of Gemini 2.5 Pro Audio.\n"
            )
        logger.info(f"Created dummy source file at {TARGET_FILE}")


def write_ledger(node_name: str, content: str) -> None:
    """Mimics the swarm_worker.py ledger persistence."""
    ledger_dir = f"{DATACENTER}/03_Agent_Ledgers"
    os.makedirs(ledger_dir, exist_ok=True)
    path = f"{ledger_dir}/MEGA_TEST_{node_name}.md"
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    logger.info(f"Ledger written to {path}")


def execute_nexus_with_rag(
    router: UniversalRouter, payload: str, system_prompt: str
) -> tuple[str, float]:
    """Forces Nexus to use query_local_memory to interrogate ChromaDB."""
    logger.info("Executing Nexus Agent with RAG Tool-Call Loop...")
    client = router.gemini_client
    if not client:
        raise RuntimeError("Gemini client not initialized in UniversalRouter.")

    query_tool = TOOL_DISPATCHER["query_local_memory"]

    config = types.GenerateContentConfig(
        system_instruction=system_prompt,
        temperature=0.1,
        tools=[query_tool],
        automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=False),
    )

    response = client.models.generate_content(
        model="gemini-2.5-pro",
        contents=payload,
        config=config,
    )

    cost = 0.0
    if response.usage_metadata:
        from maccre_core.tools.finops_tools import calculate_actual_cost  # noqa: PLC0415

        cost = calculate_actual_cost(
            "gemini-2.5-pro",
            int(response.usage_metadata.prompt_token_count or 0),
            int(response.usage_metadata.candidates_token_count or 0),
        )

    return response.text or "", cost


async def run_mega_test() -> None:
    print("=" * 60)
    print("MACCREv2 MEGA-TEST INITIATED (RAG ENABLED)")
    print("=" * 60)

    total_cost = 0.0
    router = UniversalRouter()

    try:
        # 0. Setup & Database Ingestion
        setup_dummy_file()
        with open(TARGET_FILE, "r", encoding="utf-8") as f:
            raw_source = f.read()

        print("\n[0/6] Ingesting Raw Source into Sovereign ChromaDB...")
        ingest_result = ingest_document(
            text=raw_source,
            doc_id="mega_test_source_001",
            collection_name=TEST_COLLECTION,
            metadata={"source": "conversation.md", "type": "raw_audio_transcript"},
        )
        print(f"      {ingest_result}")
        logger.info(
            "Phase 0: Ingestion Complete",
            extra={"extra_data": {"ingest_result": ingest_result}},
        )

        # 1. Epistemic OSINT
        print("\n[1/6] Executing EPISTEMIC_OSINT...")
        osint_sys = load_persona("EPISTEMIC_OSINT")
        osint_out, cost, _ = router.generate("gemini-2.5-flash", raw_source, osint_sys, "none", 0.3)
        total_cost += cost
        write_ledger("01_EPISTEMIC_OSINT", osint_out)
        logger.info("OSINT Complete", extra={"extra_data": {"cost": cost}})

        # 2. Strategic Forecaster
        print("\n[2/6] Executing STRATEGIC_FORECASTER...")
        forecast_sys = load_persona("STRATEGIC_FORECASTER")
        forecast_out, cost, _ = router.generate(
            "gemini-2.5-pro", raw_source, forecast_sys, "none", 0.7
        )
        total_cost += cost
        write_ledger("02_STRATEGIC_FORECASTER", forecast_out)
        logger.info("Forecaster Complete", extra={"extra_data": {"cost": cost}})

        # 3. Diamond Synthesizer (Initial)
        print("\n[3/6] Executing DIAMOND_SYNTHESIZER (Phase 1)...")
        synth_sys = load_persona("THE_DIAMOND_SYNTHESIZER")
        synth_payload = (
            f"RAW SOURCE:\n{raw_source}\n\nOSINT:\n{osint_out}\n\nFORECAST:\n{forecast_out}"
        )
        synth1_out, cost, _ = router.generate(
            "gemini-2.5-flash", synth_payload, synth_sys, "none", 0.1
        )
        total_cost += cost
        write_ledger("03_DIAMOND_SYNTHESIZER_1", synth1_out)
        logger.info("Synthesis 1 Complete", extra={"extra_data": {"cost": cost}})

        # 4. Nexus Agent (RAG Verification)
        print("\n[4/6] Executing NEXUS (Verification via ChromaDB RAG)...")
        nexus_sys = load_persona("THE_NEXUS")
        nexus_sys += (
            f"\n\nCRITICAL DIRECTIVE: You have been handed a synthesis. You MUST use the "
            f"`query_local_memory` tool to search the '{TEST_COLLECTION}' collection for the "
            "original conversation. Compare the retrieved vector memory to the synthesis. "
            "Output a strict analysis of any deviations or lost context."
        )
        nexus_out, cost = execute_nexus_with_rag(
            router, f"SYNTHESIS PAYLOAD:\n{synth1_out}", nexus_sys
        )
        total_cost += cost
        write_ledger("04_NEXUS_VERIFICATION", nexus_out)
        logger.info("Nexus Verification Complete", extra={"extra_data": {"cost": cost}})

        # 5. Media Manifest Generation (Direct Structured Output — bypasses Synthesizer compression)
        print("\n[5/6] Generating MEDIA MANIFEST (Structured JSON via Director call)...")
        client = router.gemini_client
        if not client:
            raise RuntimeError("Gemini client not initialized in UniversalRouter.")

        _manifest_system = (
            "You are a sovereign media director. Your ONLY output is a strict JSON array. "
            "No prose, no markdown fences, no XML tags — raw JSON only. "
            "Convert the provided analysis into a 2-person podcast dialogue of approximately 5 minutes. "
            'Schema: [{"speaker": "Host"|"Guest"|"Narrator", "text": "...", "video_prompt": "..."}]. '
            "Each scene must have a video_prompt describing a cinematic visual for that segment."
        )
        _manifest_config = types.GenerateContentConfig(
            system_instruction=_manifest_system,
            temperature=0.4,
            response_mime_type="application/json",
        )
        _manifest_response = client.models.generate_content(
            model="gemini-2.5-pro",
            contents=f"SOURCE ANALYSIS:\n{nexus_out}",
            config=_manifest_config,
        )
        manifest_out = _manifest_response.text or ""
        cost = 0.0
        if _manifest_response.usage_metadata:
            from maccre_core.tools.finops_tools import calculate_actual_cost  # noqa: PLC0415
            cost = calculate_actual_cost(
                "gemini-2.5-pro",
                int(_manifest_response.usage_metadata.prompt_token_count or 0),
                int(_manifest_response.usage_metadata.candidates_token_count or 0),
            )
        total_cost += cost

        from maccre_core.tools.text_tools import parse_json_response  # noqa: PLC0415
        import re as _re  # noqa: PLC0415

        # ── Hardened Manifest Extractor ───────────────────────────────────────
        # Tier 1: strip markdown code fences if present, then attempt direct parse
        _stripped = _re.sub(r"```(?:json)?\s*|\s*```", "", manifest_out).strip()
        manifest_json = ""
        for _candidate in (_stripped, manifest_out):
            _candidate = _candidate.strip()
            if not _candidate:
                continue
            try:
                _parsed = json.loads(_candidate)
                if isinstance(_parsed, list) and len(_parsed) > 0:
                    manifest_json = json.dumps(_parsed)
                    break
            except (json.JSONDecodeError, ValueError):
                pass

        # Tier 2: try parse_json_response helper
        if not manifest_json:
            try:
                _parsed = parse_json_response(manifest_out)
                if isinstance(_parsed, list) and len(_parsed) > 0:
                    manifest_json = json.dumps(_parsed)
            except (ValueError, Exception):
                pass

        if not manifest_json:
            # Diagnostic dump before hard fail
            logger.error(
                "MANIFEST PARSE FAILURE: model did not emit a valid JSON array.",
                extra={"extra_data": {"raw_output_preview": manifest_out[:500]}},
            )
            raise ValueError(
                f"MANIFEST PARSE FAILURE: model output could not be parsed as a JSON array.\n"
                f"Raw preview: {manifest_out[:300]}"
            )
        # ─────────────────────────────────────────────────────────────────────

        write_ledger("05_MEDIA_MANIFEST", manifest_json)
        logger.info("Media Manifest Generated", extra={"extra_data": {"cost": cost}})

        # 6. Render Pipeline
        print("\n[6/6] Executing RENDER_PIPELINE (Cloud TTS + Imagen 3 + Edge FFmpeg)...")
        # Await the async inner function directly — we are already inside an
        # asyncio event loop (run_mega_test is a coroutine), so asyncio.run()
        # cannot be nested here.
        from maccre_core.tools.render_executor import _async_execute_render_pipeline  # noqa: PLC0415
        render_result = await _async_execute_render_pipeline(manifest_json)
        logger.info(
            "Render Pipeline Complete", extra={"extra_data": {"result": render_result}}
        )

        print("\n" + "=" * 60)
        print(f"MEGA-TEST SUCCESSFUL. Total Inference Cost: ${total_cost:.6f}")
        print(f"Final Output: {render_result}")
        print("=" * 60)

    except Exception:
        logger.error(
            "MEGA-TEST FAILED",
            extra={"extra_data": {"traceback": traceback.format_exc()}},
        )
        print("\n[!] CRITICAL FAILURE. Check maccre_system.log for exact traceback.")
        print(traceback.format_exc())


if __name__ == "__main__":
    import asyncio

    asyncio.run(run_mega_test())
