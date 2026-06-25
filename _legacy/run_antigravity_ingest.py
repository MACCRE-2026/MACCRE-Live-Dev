import sys
import logging
from maccre_core.tools.antigravity_ingest import run_antigravity_ingestion

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python run_antigravity_ingest.py <ingestion_project_name> [num_epochs]")
        print("Example: python run_antigravity_ingest.py AntigravityExport 5")
        sys.exit(1)
        
    project_name = sys.argv[1]
    num_cats = int(sys.argv[2]) if len(sys.argv) > 2 else 5
    
    print("==================================================")
    print(" MACCREv2 Historical Epoch MapReduce Ingestion")
    print(f" Target: GLOBAL/{project_name}")
    print(f" Target Epochs: {num_cats}")
    print("==================================================\n")
    
    result = run_antigravity_ingestion(project_name, num_cats)
    
    print("\n==================================================")
    print(" INGESTION COMPLETE")
    print("==================================================")
    print(result)
