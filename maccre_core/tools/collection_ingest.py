import os
import json
import datetime
import logging
import time

from maccre_core.utils.path_resolver import get_datacenter_path
from maccre_core.tools.rag_tools import _get_rag_client, get_gemini_embedding
from maccre_core.memory.knowledge_store import get_knowledge_store, PinRecord
from maccre_core._net.gemini_client import user_turn

_log = logging.getLogger(__name__)

OFF_SAFETY_SETTINGS = [
    {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_NONE"},
    {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_NONE"},
    {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_NONE"},
    {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_NONE"},
]

# ── Internal AI Operations ───────────────────────────────────────────────────

def _scout_theme(text: str) -> str:
    """Reads the first 10k chars and extracts a 3-5 word core theme."""
    client = _get_rag_client()
    system = "You are a fast semantic scout. Read this text and return a 3 to 5 word description of its core theme/topic. Return ONLY the theme string."
    
    # Cap text length to ensure extremely fast inference
    capped_text = text[:10000]
    
    try:
        response = client.generate_content(
            model="gemini-2.5-flash",
            contents=[user_turn(capped_text)],
            system_instruction=system,
            temperature=0.1,
            safety_settings=OFF_SAFETY_SETTINGS,
        )
        return response.text.strip()
    except Exception as e:
        _log.warning(f"[_scout_theme] Fault: {e}")
        return "Uncategorized Error"


def _cluster_themes(themes_dict: dict[str, str], num_categories: int) -> list[str]:
    """Uses Gemini Pro to cluster the raw themes into exactly N categories."""
    client = _get_rag_client()
    system = (
        f"You are the Master Archivist. You have been given a JSON mapping of files to their raw semantic themes.\n"
        f"Your task is to analyze these themes and cluster them into EXACTLY {num_categories} overarching Concept Categories "
        f"that best encapsulate this entire dataset.\n"
        f"Return ONLY a strict JSON array of {num_categories} string values."
    )
    
    payload = json.dumps(themes_dict, indent=2)
    
    try:
        response = client.generate_content(
            model="gemini-3.1-pro-preview",
            contents=[user_turn(payload)],
            system_instruction=system,
            temperature=0.2,
            safety_settings=OFF_SAFETY_SETTINGS,
        )
        raw = response.text.strip()
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        
        categories = json.loads(raw)
        if not isinstance(categories, list) or len(categories) != num_categories:
            _log.warning(f"[_cluster_themes] Model failed to return exactly {num_categories} categories. Attempting to parse anyway.")
            
        return [str(c).replace(" ", "_").lower() for c in categories]
    except Exception as e:
        _log.error(f"[_cluster_themes] Fault: {e}")
        return ["general_concept"] * num_categories


def _extract_and_categorize(text: str, categories: list[str]) -> dict:
    """Categorizes the text into one of the provided categories and extracts triplets."""
    client = _get_rag_client()
    schema_hint = '{"category": "...", "triplets": [{"subject": "...", "predicate": "...", "object": "...", "significance": "..."}]}'
    
    system = (
        "You are the Ingestion Agent for the GLOBAL Archive.\n"
        f"Here are the official concept categories for this archive: {json.dumps(categories)}\n\n"
        "1. You MUST categorize this file into exactly ONE of those categories.\n"
        "2. You MUST extract the most brilliant conceptual or architectural relationships and output them as strict Knowledge Triplets.\n"
        "Ignore conversational filler. Only pin high-value concepts.\n"
        f"You MUST reply with ONLY valid JSON matching this schema exactly: {schema_hint}"
    )
    
    try:
        response = client.generate_content(
            model="gemini-3.1-pro-preview",
            contents=[user_turn(text[:30000])], # Cap extraction context
            system_instruction=system,
            temperature=0.1,
            safety_settings=OFF_SAFETY_SETTINGS,
        )
        
        raw = response.text.strip()
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
                
        data = json.loads(raw)
        
        cat = str(data.get("category", "general_concept")).replace(" ", "_").lower()
        if cat not in categories:
            # Fallback if hallucinated
            cat = categories[0] if categories else "general_concept"
            
        return {
            "category": cat,
            "triplets": data.get("triplets", [])
        }
    except Exception as e:
        _log.error(f"[_extract_and_categorize] Fault: {e}")
        return {"category": categories[0] if categories else "general_concept", "triplets": []}


# ── Agent-Facing Tools ───────────────────────────────────────────────────────

def scout_archive_themes(ingestion_project_name: str) -> str:
    """
    Scans the 01_Raw_Source directory of a GLOBAL ingestion project and returns a JSON map of file themes.
    Agent should use this to get the 'lay of the land' before clustering categories.
    """
    os.environ["MACCRE_ACTIVE_PROJECT"] = f"GLOBAL/{ingestion_project_name}"
    source_dir = get_datacenter_path("01_Raw_Source")
    
    if not source_dir.exists():
        return f"[SCOUT_FAULT] Directory not found: {source_dir}"
        
    themes_dict = {}
    files = list(source_dir.glob("*.md")) + list(source_dir.glob("*.txt"))
    
    if not files:
        return "[SCOUT_FAULT] No .md or .txt files found in 01_Raw_Source."
        
    for i, file_path in enumerate(files, 1):
        text = file_path.read_text(encoding="utf-8", errors="replace")
        if text.strip():
            _log.info(f"[{i}/{len(files)}] Scouting theme for: {file_path.name}")
            themes_dict[file_path.name] = _scout_theme(text)
            time.sleep(4)  # 15 RPM FinOps throttle
            
    return json.dumps(themes_dict, indent=2)


def execute_archive_ingestion(ingestion_project_name: str, categories: list[str]) -> str:
    """
    Executes the heavy Triune ingestion pipeline. Takes a list of categories decided by the Agent.
    Categorizes each file, extracts triplets, and routes them into the corresponding concept_[cat].db and memory_pins_[cat].db.
    """
    if not categories:
        return "[INGESTION_FAULT] You must provide a valid list of categories."
        
    clean_categories = [str(c).replace(" ", "_").lower() for c in categories]
    os.environ["MACCRE_ACTIVE_PROJECT"] = f"GLOBAL/{ingestion_project_name}"
    
    source_dir = get_datacenter_path("01_Raw_Source")
    pins_dir = get_datacenter_path("02_Dynamic_Context", "memory_pins")
    pins_dir.mkdir(parents=True, exist_ok=True)
    
    files = list(source_dir.glob("*.md")) + list(source_dir.glob("*.txt"))
    if not files:
        return "[INGESTION_FAULT] No files found."
        
    results = []
    
    for i, file_path in enumerate(files, 1):
        try:
            text = file_path.read_text(encoding="utf-8", errors="replace")
            if not text.strip():
                continue
                
            _log.info(f"[{i}/{len(files)}] Ingesting & Categorizing: {file_path.name}")
            extraction = _extract_and_categorize(text, clean_categories)
            cat = extraction["category"]
            triplets = extraction["triplets"]
            
            doc_id = file_path.stem.replace(".", "_")
            
            # 1. Save triplets to JSON
            out_path = pins_dir / f"global_pin_{doc_id}.json"
            with open(out_path, "w", encoding="utf-8") as f:
                json.dump(triplets, f, indent=2)
                
            # 2. Embed and Store Raw Text in concept_{cat}.db
            safe_meta = {
                "project": f"GLOBAL/{ingestion_project_name}",
                "filename": file_path.name,
                "category": cat,
                "tier": "global_collection",
                "ingested_at": datetime.datetime.utcnow().isoformat(),
            }
            
            concept_vector = get_gemini_embedding(text, task_type="RETRIEVAL_DOCUMENT")
            concept_store = get_knowledge_store(f"GLOBAL/{ingestion_project_name}", db_name=f"concept_{cat}.db")
            concept_store.upsert("swarm_memory", PinRecord(
                doc_id=doc_id,
                text=text,
                vector=concept_vector,
                metadata=safe_meta,
            ))
            
            # 3. Embed and Store Triplets in memory_pins_{cat}.db
            if triplets:
                pin_text = json.dumps(triplets)
                pin_vector = get_gemini_embedding(pin_text, task_type="RETRIEVAL_DOCUMENT")
                pin_store = get_knowledge_store(f"GLOBAL/{ingestion_project_name}", db_name=f"memory_pins_{cat}.db")
                pin_store.upsert("swarm_memory", PinRecord(
                    doc_id=f"pin_{doc_id}",
                    text=pin_text,
                    vector=pin_vector,
                    metadata=safe_meta,
                ))
            
            results.append(f"Ingested '{file_path.name}' -> [{cat}] ({len(triplets)} pins)")
            time.sleep(4)  # 15 RPM FinOps throttle
        except Exception as e:
            results.append(f"Failed '{file_path.name}': {e!s}")
            
    return "\n".join(results)


# ── Deterministic Python Pipeline ────────────────────────────────────────────

def run_global_ingestion(ingestion_project_name: str, num_categories: int = 10) -> str:
    """
    Executes the entire MapReduce sequence automatically without Agent oversight.
    1. Scouts themes.
    2. Clusters into N categories using Gemini Pro.
    3. Executes the archive ingestion.
    """
    _log.info(f"Starting deterministic global ingestion for {ingestion_project_name}...")
    
    # Pass 1: Scout
    _log.info("[Pass 1] Scouting themes...")
    raw_themes = scout_archive_themes(ingestion_project_name)
    if raw_themes.startswith("[SCOUT_FAULT]"):
        return raw_themes
        
    try:
        themes_dict = json.loads(raw_themes)
    except Exception:
        return f"[INGESTION_FAULT] Failed to parse scouted themes: {raw_themes}"
        
    # Council: Cluster
    _log.info(f"[Council] Clustering {len(themes_dict)} themes into {num_categories} categories...")
    categories = _cluster_themes(themes_dict, num_categories)
    _log.info(f"Defined categories: {categories}")
    
    # Pass 2: Ingest
    _log.info("[Pass 2] Executing heavy ingestion routing...")
    return execute_archive_ingestion(ingestion_project_name, categories)
