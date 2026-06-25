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
maccre_core/ingestion/fingerprint_index.py
=========================================
State tracking for the Sovereign File Cabinet. 
Generates and tracks cryptographic hashes of ingested files to prevent duplicate
thought-pin extraction and handle delta updates gracefully.
"""

import hashlib
import json
import os
from typing import Dict

from maccre_core.utils.path_resolver import get_datacenter_path

class FingerprintManager:
    """Manages state tracking for ingested files via SHA-256 hashing."""

    def __init__(self, project_id: str = "GLOBAL") -> None:
        self.project_id = project_id
        # We store the fingerprint index inside the project's Dynamic_Context tier
        self.index_path = get_datacenter_path(
            "02_Dynamic_Context", 
            "KnowledgeStore", 
            "ingestion_fingerprints.json", 
            project_id=self.project_id
        )
        self._cache: Dict[str, str] = self._load_index()

    def _load_index(self) -> Dict[str, str]:
        if self.index_path.exists():
            try:
                with open(self.index_path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except json.JSONDecodeError:
                return {}
        return {}

    def _save_index(self) -> None:
        self.index_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.index_path, "w", encoding="utf-8") as f:
            json.dump(self._cache, f, indent=4)

    def generate_hash(self, file_path: str) -> str:
        """Generate a SHA-256 hash for the given file."""
        sha256 = hashlib.sha256()
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(65536), b""):
                sha256.update(chunk)
        return sha256.hexdigest()

    def is_modified(self, file_path: str, collection_name: str) -> bool:
        """Check if the file is new or modified compared to the index.
        
        Args:
            file_path: The path of the file being ingested.
            collection_name: The name of the collection it's being ingested to.
        """
        # We key the index by a combination of the collection name and the basename
        # to ensure that if a file with the same name is ingested into two different
        # collections, they are tracked independently.
        basename = os.path.basename(file_path)
        index_key = f"{collection_name}::{basename}"
        
        current_hash = self.generate_hash(file_path)
        
        if index_key not in self._cache or self._cache[index_key] != current_hash:
            return True
        return False

    def mark_ingested(self, file_path: str, collection_name: str) -> None:
        """Record the file's hash as successfully ingested."""
        basename = os.path.basename(file_path)
        index_key = f"{collection_name}::{basename}"
        
        self._cache[index_key] = self.generate_hash(file_path)
        self._save_index()
