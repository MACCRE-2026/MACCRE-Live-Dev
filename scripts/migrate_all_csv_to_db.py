import os
import sys

# Ensure maccre_core can be imported
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from maccre_core.agent_library import get_agent_store
from maccre_core.workbook_data import load_agent_roster_csv

def main():
    print("Migrating GLOBAL agent_roster.csv to SovereignPinStore...")
    global_csv_agents = load_agent_roster_csv("GLOBAL")
    
    store = get_agent_store("GLOBAL")
    existing = {a.get("agent_name") or a.get("AGENT_NAME") for a in store.load_all()}
    
    migrated_count = 0
    for row in global_csv_agents:
        name = row.get("Agent_Name") or row.get("agent_name")
        if not name:
            continue
            
        if name not in existing:
            # Upgrade to new schema with default AI Studio settings
            profile = {
                "agent_name": name,
                "model": row.get("Model", "gemini-2.5-flash"),
                "system_prompt": row.get("System_Prompt", ""),
                "tools_allowed": row.get("Tools_Allowed", "none"),
                "temperature": 1.0,
                "ai_studio_options": {
                    "thinking_level": "none",
                    "structured_outputs": False,
                    "code_execution": False,
                    "function_calling": True,  # Defaulting to True for future-proofing
                    "grounding_google_search": False,
                    "grounding_google_maps": False,
                    "url_context": False,
                    "media_resolution": "default",
                    "stop_sequence": "",
                    "output_length": 65536,
                    "top_p": 0.95
                }
            }
            store.save(profile)
            migrated_count += 1
            print(f"Migrated: {name}")
            
    print(f"\nSuccessfully migrated {migrated_count} agents to the new schema.")

if __name__ == "__main__":
    main()
