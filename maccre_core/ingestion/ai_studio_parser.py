import json
from pathlib import Path
from typing import Dict, Any, List
from maccre_core.ingestion.base_parser import BaseParser

class AIStudioParser(BaseParser):
    """
    Parser for Google AI Studio conversation exports.
    Expects JSON files containing conversation turns.
    """
    
    def parse_file(self, file_path: Path) -> List[Dict[str, Any]]:
        if file_path.suffix.lower() != ".json":
            raise ValueError(f"AI Studio Parser expects JSON files, got {file_path.suffix}")
            
        try:
            data = json.loads(file_path.read_text(encoding="utf-8"))
        except Exception as e:
            raise ValueError(f"Failed to parse JSON from {file_path}: {e}")
            
        documents = []
        # Fallback to simple extraction if structure is unknown
        if isinstance(data, list):
            for i, turn in enumerate(data):
                if isinstance(turn, dict) and "parts" in turn:
                    content = "".join(p.get("text", "") for p in turn.get("parts", []))
                    documents.append({
                        "content": content,
                        "metadata": {
                            "source": file_path.name,
                            "role": turn.get("role", "user"),
                            "turn_index": i
                        }
                    })
        else:
            # Generic catch-all
            documents.append({
                "content": json.dumps(data, indent=2),
                "metadata": {"source": file_path.name, "type": "raw_json"}
            })
            
        return documents
