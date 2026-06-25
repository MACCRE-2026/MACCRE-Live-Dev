from abc import ABC, abstractmethod
from typing import Dict, Any, List
from pathlib import Path

class BaseParser(ABC):
    """
    Abstract Base Class for Sovereign Data Ingestion Parsers.
    All parsers must convert their specific source formats into a standardized
    format for Sovereign SQLite memory insertion.
    """
    
    def __init__(self, project_id: str):
        """
        Initialize the parser with a target project context.
        """
        self.project_id = project_id

    @abstractmethod
    def parse_file(self, file_path: Path) -> List[Dict[str, Any]]:
        """
        Parse a source file and return a list of standardized documents.
        Each document should be a dictionary containing at least:
        - 'content': The text content to embed.
        - 'metadata': A dictionary of metadata (e.g., source, timestamp, author).
        """
        pass
