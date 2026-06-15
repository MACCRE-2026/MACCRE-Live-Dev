import csv
import sys
from pathlib import Path

# Add project root to path for imports
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from maccre_core.utils.path_resolver import get_maccre_root

def migrate_to_global() -> None:
    dc_path = get_maccre_root() / "__DATACENTER"
    if not dc_path.exists():
        print("Datacenter not found.")
        return

    global_path = dc_path / "GLOBAL"
    global_path.mkdir(parents=True, exist_ok=True)
    global_roster_path = global_path / "agent_roster.csv"

    seen_agents: set[str] = set()
    rows: list[list[str]] = []
    
    # Check if global already exists
    if global_roster_path.exists():
        with open(global_roster_path, "r", encoding="utf-8-sig") as f:
            reader = csv.reader(f)
            next(reader, None)
            for row in reader:
                if row and len(row) > 0:
                    agent_name = row[0].strip()
                    seen_agents.add(agent_name)
                    rows.append(row)

    found_count = 0
    # Sweep all agent_rosters
    for roster in dc_path.rglob("agent_roster.csv"):
        # Skip the global one we are writing to
        if roster.resolve() == global_roster_path.resolve():
            continue
            
        print(f"Reading from: {roster.relative_to(get_maccre_root())}")
        try:
            with open(roster, "r", encoding="utf-8-sig") as f:
                reader = csv.reader(f)
                next(reader, None)
                for row in reader:
                    if row and len(row) > 0:
                        agent_name = row[0].strip()
                        if agent_name not in seen_agents:
                            seen_agents.add(agent_name)
                            rows.append(row)
                            found_count += 1
        except Exception as e:
            print(f"Error reading {roster}: {e}")

    # Write merged
    with open(global_roster_path, "w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["Agent_Name", "Model", "Tools_Allowed", "System_Prompt", "Description"])
        writer.writerows(rows)

    print(f"\nMigration complete. Added {found_count} new unique agents to GLOBAL/agent_roster.csv")
    print(f"Total unique agents in GLOBAL: {len(rows)}")

if __name__ == "__main__":
    migrate_to_global()
