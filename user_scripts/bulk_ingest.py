import sys
import io

if sys.stdout.encoding and sys.stdout.encoding.lower() != 'utf-8':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

from maccre_core.utils.path_resolver import get_maccre_root
from maccre_core.tools.rag_tools import ingest_project

def run_bulk_ingest():
    dc = get_maccre_root() / "__DATACENTER"
    print("Starting Bulk Ingestion...")
    projects = [p.name for p in dc.iterdir() if p.is_dir() and not p.name.startswith("_")]
    
    for proj in projects:
        print(f"Ingesting {proj}...")
        res = ingest_project(proj)
        print(f"  Result: {res}")
        
if __name__ == "__main__":
    run_bulk_ingest()
