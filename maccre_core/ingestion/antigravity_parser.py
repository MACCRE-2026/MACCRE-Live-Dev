import datetime
from pathlib import Path
from typing import Dict, Any, List
from maccre_core.ingestion.base_parser import BaseParser

class AntigravityParser(BaseParser):
    """
    Parser for raw Antigravity/MACCREv2 log files and artifacts.
    Also handles universal file fingerprinting for unreadable binaries.
    """
    
    def get_file_metadata(self, filepath: Path) -> dict[str, str]:
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

    def parse_file(self, file_path: Path) -> List[Dict[str, Any]]:
        metadata = self.get_file_metadata(file_path)
        documents = []
        
        # Try to read as text
        is_readable = False
        try:
            text_content = file_path.read_text(encoding="utf-8")
            is_readable = True
        except UnicodeDecodeError:
            pass

        if is_readable and text_content.strip():
            # Cap at reasonable length for memory ingestion
            metadata["type"] = "text_artifact"
            documents.append({
                "content": text_content[:30000],
                "metadata": metadata
            })
        else:
            # Binary fallback fingerprinting
            import json
            metadata["type"] = "binary_fingerprint"
            documents.append({
                "content": f"Unreadable binary file fingerprint: {json.dumps(metadata)}",
                "metadata": metadata
            })
            
        return documents
