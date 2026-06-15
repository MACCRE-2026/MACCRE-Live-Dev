"""
maccre_core/tools/macro_nodes.py
=================================
Manages reusable topology graph fragments (Macro Nodes) in the GLOBAL namespace.
These functions allow Nexus to save and retrieve complex agent wirings.
"""
import json
from maccre_core.utils.path_resolver import get_maccre_root

def _get_registry_path():
    path = get_maccre_root() / "__DATACENTER" / "GLOBAL" / "macro_nodes.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    return path

def save_macro_node(name: str, description: str, nodes: list[list[str]]) -> str:
    """Saves a reusable subset of a topology graph into the GLOBAL library."""
    try:
        path = _get_registry_path()
        registry = {}
        if path.exists():
            with open(path, "r", encoding="utf-8") as f:
                registry = json.load(f)
                
        registry[name] = {
            "description": description,
            "nodes": nodes
        }
        
        with open(path, "w", encoding="utf-8") as f:
            json.dump(registry, f, indent=4)
            
        return f"[ADMIN_SUCCESS] Successfully saved Macro Node '{name}' with {len(nodes)} nodes."
    except Exception as e:
        return f"[ADMIN_FAULT] Failed to save Macro Node: {e}"

def list_macro_nodes() -> str:
    """Returns a list of all saved Macro Nodes in the GLOBAL library."""
    try:
        path = _get_registry_path()
        if not path.exists():
            return "No Macro Nodes currently saved."
            
        with open(path, "r", encoding="utf-8") as f:
            registry = json.load(f)
            
        if not registry:
            return "No Macro Nodes currently saved."
            
        output = "Available Macro Nodes:\n"
        for name, data in registry.items():
            output += f"- {name}: {data.get('description', '')}\n"
        return output
    except Exception as e:
        return f"[ADMIN_FAULT] Failed to list Macro Nodes: {e}"

def fetch_macro_node(name: str) -> str:
    """Returns the JSON string representation of a specific Macro Node's wiring."""
    try:
        path = _get_registry_path()
        if not path.exists():
            return f"[ADMIN_FAULT] Macro Node '{name}' not found."
            
        with open(path, "r", encoding="utf-8") as f:
            registry = json.load(f)
            
        if name not in registry:
            return f"[ADMIN_FAULT] Macro Node '{name}' not found."
            
        return json.dumps(registry[name]["nodes"])
    except Exception as e:
        return f"[ADMIN_FAULT] Failed to fetch Macro Node: {e}"
