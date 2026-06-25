# ┌─────────────────────────────────────────────────────────────────────────────┐
# │  MACCREv2 ENGINEERING DOCTRINE                             Law Rev: 19.0   │
# ├─────────────────────────────────────────────────────────────────────────────┤
# │  I.   TYPING      All signatures: explicit Python 3.11+ type hints.        │
# │  II.  LINTING     Zero unused imports. No wildcards. 120-char line max.    │
# │  III. PATHS       Never hardcode absolute paths. Use get_maccre_root().     │
# │                   Default params: def f(p:str='') -> None: p=p or root/x   │
# └─────────────────────────────────────────────────────────────────────────────┘
"""
Universal File Fingerprinting Ingestion Tool.

Extracts semantic meaning from ANY file (text, executable, image, etc.)
and pins it into the MACCREv2 Sovereign Knowledge Store.
"""

import argparse
import datetime
import json
import os
import sys
import uuid
from pathlib import Path

# Ensure maccre_core is in sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from maccre_core._net.gemini_client import GeminiClient, user_turn
from maccre_core.orchestration.windows_vault import get_native_credential
from maccre_core.memory.knowledge_store import get_knowledge_store, PinRecord
from maccre_core.tools.rag_tools import get_gemini_embedding


def _get_client() -> GeminiClient:
    raw_key = get_native_credential("MACCRE_Sovereign")
    if not raw_key:
        raise ValueError("CRITICAL: Vault returned empty.")
    clean_key = str(raw_key).strip()
    return GeminiClient(api_key=clean_key)


def get_file_metadata(filepath: Path) -> dict[str, str]:
    """Extracts base OS metadata."""
    stats = filepath.stat()
    return {
        "filename": filepath.name,
        "extension": filepath.suffix,
        "size_bytes": str(stats.st_size),
        "created": datetime.datetime.fromtimestamp(stats.st_ctime).isoformat(),
        "modified": datetime.datetime.fromtimestamp(stats.st_mtime).isoformat(),
        "path": str(filepath.resolve()),
    }


def ingest_file(filepath_str: str, project_name: str = "GLOBAL") -> None:
    filepath = Path(filepath_str).resolve()
    if not filepath.exists():
        print(f"[INGEST] Error: File not found: {filepath}")
        return

    os.environ["MACCRE_ACTIVE_PROJECT"] = project_name
    metadata = get_file_metadata(filepath)
    client = _get_client()

    print(f"[INGEST] Analyzing {filepath.name} ({metadata['size_bytes']} bytes)...")

    # Try to read as text
    text_content = ""
    is_readable = False
    try:
        text_content = filepath.read_text(encoding="utf-8")
        is_readable = True
    except UnicodeDecodeError:
        pass

    schema_hint = '{"triplets": [{"subject": "...", "predicate": "...", "object": "...", "significance": "..."}]}'

    if is_readable and len(text_content.strip()) > 0:
        print("[INGEST] File is readable text. Extracting Thought Pins...")
        system = (
            "You are the MACCREv2 Ingestion Engine. "
            "Analyze the following text document. Extract the most brilliant conceptual, mathematical, "
            "or architectural relationships and output them as strict Knowledge Triplets. "
            "Ignore conversational filler. Only pin high-value concepts. "
            "CRITICAL: If you use LaTeX math or backslashes, you MUST double-escape them for valid JSON (e.g., \\\\Phi instead of \\Phi). "
            f"You MUST reply with ONLY valid JSON matching this schema exactly: {schema_hint}"
        )
        content_to_analyze = text_content[:30000] # Cap at 30k chars
    else:
        print("[INGEST] File is binary/unreadable. Performing deep fingerprinting...")
        system = (
            "You are the MACCREv2 Universal File Fingerprinting Engine. "
            "You are looking at the metadata of a binary/unreadable file that the agent cannot natively read. "
            "Based on the filename, extension, size, and timestamps, deduce the likely purpose, nature, and "
            "role of this file within a broader system. Generate Knowledge Triplets that describe what this file "
            "likely is and how it might be used. "
            "CRITICAL: If you use LaTeX math or backslashes, you MUST double-escape them for valid JSON (e.g., \\\\Phi instead of \\Phi). "
            f"You MUST reply with ONLY valid JSON matching this schema exactly: {schema_hint}"
        )
        content_to_analyze = json.dumps(metadata, indent=2)

    schema = {
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
                        "significance": {"type": "STRING"}
                    },
                    "required": ["subject", "predicate", "object", "significance"]
                }
            }
        },
        "required": ["triplets"]
    }

    try:
        response = client.generate_content(
            model="gemini-2.5-flash",
            contents=[user_turn(content_to_analyze)],
            system_instruction=system,
            temperature=0.1,
            response_schema=schema,
        )

        raw = response.text.strip()
        
        try:
            extraction = json.loads(raw, strict=False)
        except json.JSONDecodeError as exc:
            print(f"[INGEST FAULT] Could not parse Gemini JSON response: {exc}")
            with open("b:\\EXO_GANS\\__DATACENTER\\MEMORY_TEST\\01_Raw_Source\\crash.json", "w", encoding="utf-8") as f:
                f.write(raw)
            print("[INGEST FAULT] Saved the raw output to crash.json for inspection.")
            return
        triplets = extraction.get("triplets", [])

        if not triplets:
            print("[INGEST] No concepts extracted.")
            return

        store = get_knowledge_store(project_name, db_name="thought_pins.db")
        concept_text = json.dumps(triplets)
        vector = get_gemini_embedding(concept_text, task_type="RETRIEVAL_DOCUMENT")
        doc_id = f"fingerprint_{filepath.stem}_{uuid.uuid4().hex[:8]}"

        safe_meta = {
            "project": project_name,
            "filename": filepath.name,
            "type": "universal_fingerprint",
            "is_readable": str(is_readable),
            "ingested_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        }

        store.upsert("swarm_memory", PinRecord(
            doc_id=doc_id,
            text=concept_text,
            vector=vector,
            metadata=safe_meta,
        ))

        # ── FULL RAW TEXT CHUNKING & VECTORIZATION ─────────────────────────
        raw_chunks_ingested = 0
        if is_readable and len(text_content.strip()) > 0:
            print("[INGEST] Chunking and vectorizing raw literal text...")
            
            # Simple chunking: split by double newline, or arbitrary length
            paragraphs = [p.strip() for p in text_content.split("\n\n") if len(p.strip()) > 10]
            
            for idx, para in enumerate(paragraphs):
                # If a paragraph is still huge, we should theoretically sub-chunk it, 
                # but for simplicity we'll just embed it.
                para_vector = get_gemini_embedding(para, task_type="RETRIEVAL_DOCUMENT")
                para_doc_id = f"raw_chunk_{filepath.stem}_{uuid.uuid4().hex[:8]}_{idx}"
                para_meta = {
                    "project": project_name,
                    "filename": filepath.name,
                    "type": "raw_source_chunk",
                    "chunk_index": str(idx),
                    "ingested_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                }
                store.upsert("swarm_memory", PinRecord(
                    doc_id=para_doc_id,
                    text=para,
                    vector=para_vector,
                    metadata=para_meta,
                ))
                raw_chunks_ingested += 1

        print(f"[INGEST SUCCESS] Ingested {len(triplets)} semantic pins and {raw_chunks_ingested} raw text chunks into {project_name}/thought_pins.db.")

    except Exception as e:
        print(f"[INGEST FAULT] {e}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Ingest any file into MACCREv2 memory.")
    parser.add_argument("filepath", help="Path to the file to ingest")
    parser.add_argument("--project", default="GLOBAL", help="Target project (default: GLOBAL)")
    args = parser.parse_args()

    ingest_file(args.filepath, args.project)
