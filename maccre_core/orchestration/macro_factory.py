import json
import uuid
from typing import Any
from maccre_core.utils.path_resolver import get_datacenter_path
from maccre_core.orchestration.local_broker import LocalMessageBroker

def _register_ephemeral_nodes(nodes: dict[str, dict[str, Any]]) -> None:
    """Writes the generated macro nodes to 02_Dynamic_Context/ephemeral_macros.json."""
    ephemeral_path = get_datacenter_path("02_Dynamic_Context", "ephemeral_macros.json")
    try:
        if ephemeral_path.exists():
            with open(ephemeral_path, "r", encoding="utf-8") as f:
                data = json.load(f)
        else:
            data = {}
    except Exception:
        data = {}
    
    data.update(nodes)
    
    with open(ephemeral_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)

def expand_macro(
    agent_name: str,
    current_node: str,
    next_node: str,
    job_id: str,
    payload_path: str,
    source_payload_path: str,
    broker: LocalMessageBroker,
    row_id: int
) -> None:
    """
    Expands a MACRO: agent into a cluster of ephemeral tasks in the SQLite queue.
    """
    macro_type = agent_name.split(":", 1)[1].strip()
    
    # Generate a unique ID for this macro instance to prevent collisions
    # between multiple macro executions of the same type.
    macro_id = str(uuid.uuid4())[:8]
    ephemeral_nodes = {}
    next_nodes_to_queue = []
    
    print(f"[MACRO_FACTORY] Intercepted MACRO request: '{macro_type}'. Expanding...")
    
    if macro_type.lower() == "hologram-academic":
        variants = ["Historian", "Sociologist", "Economist", "Scientist", "Engineer"]
        variant_node_ids = []
        
        for variant in variants:
            v_id = f"HOLO_{variant.upper()}_{macro_id}"
            variant_node_ids.append(v_id)
            ephemeral_nodes[v_id] = {
                "prompt": f"You are a {variant}. Analyze the source document strictly from the perspective of your discipline.",
                "artifact_path": "",
                "next_node_success": f"HOLO_SYNTH_{macro_id}",
                "next_node_failure": "FAILED",
                "wait_for": "none",
                "temperature": 0.7,
                "tools_allowed": "none",
                "model": "gemini-2.5-flash",
                "agent_name": f"Holo_{variant}",
                "max_recursion": 3,
                "agent": f"Holo_{variant}",
            }
            next_nodes_to_queue.append(v_id)
            
        synth_id = f"HOLO_SYNTH_{macro_id}"
        wait_for_str = ",".join(variant_node_ids)
        ephemeral_nodes[synth_id] = {
            "prompt": "You are the Hologram Synthesizer. Review the perspectives of the Academic variants and synthesize a unified final report.",
            "artifact_path": "",
            "next_node_success": next_node,
            "next_node_failure": "FAILED",
            "wait_for": wait_for_str,
            "temperature": 0.5,
            "tools_allowed": "none",
            "model": "gemini-2.5-pro",
            "agent_name": "Holo_Synthesizer",
            "max_recursion": 3,
            "agent": "Holo_Synthesizer",
        }
        
    elif macro_type.lower() == "cascade-osint3x":
        t1_id = f"CASC_T1_{macro_id}"
        t2_id = f"CASC_T2_{macro_id}"
        t3_id = f"CASC_T3_{macro_id}"
        synth_id = f"CASC_SYNTH_{macro_id}"
        
        ephemeral_nodes[t1_id] = {
            "prompt": "You are OSINT Tier 1. Conduct an initial broad analysis.",
            "artifact_path": "",
            "next_node_success": t2_id,
            "next_node_failure": "FAILED",
            "wait_for": "none",
            "temperature": 1.0,
            "tools_allowed": "google_search",
            "model": "gemini-2.5-flash",
            "agent_name": "OSINT_Tier1",
            "max_recursion": 3,
            "agent": "OSINT_Tier1",
        }
        
        ephemeral_nodes[t2_id] = {
            "prompt": "You are OSINT Tier 2. Review Tier 1's findings and dig deeper into ignored areas. DO NOT repeat Tier 1's findings.",
            "artifact_path": "",
            "next_node_success": t3_id,
            "next_node_failure": "FAILED",
            "wait_for": t1_id,
            "temperature": 1.5,
            "tools_allowed": "google_search",
            "model": "gemini-2.5-flash",
            "agent_name": "OSINT_Tier2",
            "max_recursion": 3,
            "agent": "OSINT_Tier2",
        }
        
        ephemeral_nodes[t3_id] = {
            "prompt": "You are OSINT Tier 3. Review Tier 1 and 2's findings. Identify missing links and conduct a final deep investigation.",
            "artifact_path": "",
            "next_node_success": synth_id,
            "next_node_failure": "FAILED",
            "wait_for": t2_id,
            "temperature": 2.0,
            "tools_allowed": "google_search",
            "model": "gemini-2.5-flash",
            "agent_name": "OSINT_Tier3",
            "max_recursion": 3,
            "agent": "OSINT_Tier3",
        }
        
        ephemeral_nodes[synth_id] = {
            "prompt": "You are the Cascade Synthesizer. Review all three tiers of OSINT findings and compile a comprehensive final intelligence report.",
            "artifact_path": "",
            "next_node_success": next_node,
            "next_node_failure": "FAILED",
            "wait_for": t3_id,
            "temperature": 0.3,
            "tools_allowed": "none",
            "model": "gemini-2.5-pro",
            "agent_name": "OSINT_Synthesizer",
            "max_recursion": 3,
            "agent": "OSINT_Synthesizer",
        }
        next_nodes_to_queue.append(t1_id)
        
    elif macro_type.lower() == "chord-topperwriter-gretchen3x":
        w1_id = f"CHORD_W1_{macro_id}"
        e1_id = f"CHORD_E1_{macro_id}"
        w2_id = f"CHORD_W2_{macro_id}"
        e2_id = f"CHORD_E2_{macro_id}"
        w3_id = f"CHORD_W3_{macro_id}"
        e3_id = f"CHORD_E3_{macro_id}"
        
        # Loop unrolled to guarantee the 3x Draft -> Editor -> Draft cycle.
        ephemeral_nodes[w1_id] = {
            "prompt": "You are TopperWriter. Draft the initial content based on the source document.",
            "next_node_success": e1_id, "wait_for": "none", "temperature": 1.0, "model": "gemini-2.5-flash", "agent": "TopperWriter"
        }
        ephemeral_nodes[e1_id] = {
            "prompt": "You are Gretchen (Editor). Review the draft. Provide strict, actionable feedback.",
            "next_node_success": w2_id, "wait_for": w1_id, "temperature": 0.3, "model": "gemini-2.5-flash", "agent": "Gretchen"
        }
        ephemeral_nodes[w2_id] = {
            "prompt": "You are TopperWriter. Revise your draft based strictly on Gretchen's feedback.",
            "next_node_success": e2_id, "wait_for": e1_id, "temperature": 0.8, "model": "gemini-2.5-flash", "agent": "TopperWriter"
        }
        ephemeral_nodes[e2_id] = {
            "prompt": "You are Gretchen (Editor). Review the 2nd draft. Provide strict, actionable feedback.",
            "next_node_success": w3_id, "wait_for": w2_id, "temperature": 0.3, "model": "gemini-2.5-flash", "agent": "Gretchen"
        }
        ephemeral_nodes[w3_id] = {
            "prompt": "You are TopperWriter. Apply the final round of edits based on Gretchen's latest feedback.",
            "next_node_success": e3_id, "wait_for": e2_id, "temperature": 0.8, "model": "gemini-2.5-flash", "agent": "TopperWriter"
        }
        ephemeral_nodes[e3_id] = {
            "prompt": "You are Gretchen (Synthesizer). This is the final pass. Produce the perfect, polished final draft.",
            "next_node_success": next_node, "wait_for": w3_id, "temperature": 0.1, "model": "gemini-2.5-pro", "agent": "Gretchen_Synthesizer"
        }
        
        for k in ephemeral_nodes:
            ephemeral_nodes[k]["artifact_path"] = ""
            ephemeral_nodes[k]["next_node_failure"] = "FAILED"
            ephemeral_nodes[k]["tools_allowed"] = "none"
            ephemeral_nodes[k]["max_recursion"] = 3
            ephemeral_nodes[k]["agent_name"] = ephemeral_nodes[k]["agent"]
            
        next_nodes_to_queue.append(w1_id)
        
    else:
        print(f"[MACRO_FACTORY] Unknown macro type: {macro_type}")
        broker.route_task(row_id, job_id, "FAILED", payload_path, source_payload_path=source_payload_path)
        return

    # 1. Register ephemeral configs to JSON
    _register_ephemeral_nodes(ephemeral_nodes)
    
    # 2. Complete the intercept node and inject the first node(s) of the macro
    next_node_str = ",".join(next_nodes_to_queue)
    print(f"[MACRO_FACTORY] Spawned {len(ephemeral_nodes)} ephemeral nodes. Queueing: {next_node_str}")
    broker.route_task(row_id, job_id, next_node_str, payload_path, actual_cost=0.0, source_payload_path=source_payload_path)

