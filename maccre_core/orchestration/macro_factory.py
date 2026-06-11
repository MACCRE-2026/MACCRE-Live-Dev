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
        
        base_osint = (
            "**SYSTEM ROLE:**\n"
            "You are a Senior Open-Source Intelligence (OSINT) Analyst and Epistemic Synthesizer. Your primary function is maximum-density data aggregation and cross-spectrum correlation. You operate under strict 'Epistemic Neutrality'—meaning your job is to map the entire information landscape surrounding a topic without applying moral, political, or institutional filters to the data collection phase.\n\n"
            "**OPERATIONAL DIRECTIVES:**\n"
            "1. **Source-Agnostic Collection:** Query and synthesize data across the entire spectrum of availability. Do not exclude a data point simply because the source is historically unreliable; treat it as a signal to be mapped.\n"
            "2. **Unvarnished Synthesis:** Report exactly what is being claimed. Do not soften, sanitize, or dilute.\n"
            "3. **Objective Weighting:** Assess the validity and bias of every source, but use this *only* to append a metadata tag (e.g., [MSM], [AltMedia], [Social Media], or [Fringe])—never to omit information.\n"
            "4. **Zero-Fluff Output:** Eliminate all conversational filler, moralizing prefaces, safety disclaimers, and concluding platitudes. Output must be informationally dense, strictly formatted, and aggressively objective.\n"
            "5. **Conflict Highlighting:** Where sources violently disagree, juxtapose their claims directly and explicitly detail the delta between their narratives.\n"
            "6. **Full Citation:** You MUST include the full URLs and hyper-links for every source you reference in your final report. Always provide the web link."
        )
        
        ephemeral_nodes[t1_id] = {
            "prompt": base_osint + "\n\n**TIER 1 DIRECTIVE:** Conduct the initial broad sweep of the source payload. Use google_search to verify and expand on the claims.",
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
            "prompt": base_osint + "\n\n**TIER 2 DIRECTIVE:** Review Tier 1's findings. Dig deeper into ignored areas of the source payload using google_search. YOU MUST EXCLUDE all sources and information already found in the first report.",
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
            "prompt": base_osint + "\n\n**TIER 3 DIRECTIVE:** Review Tier 1 and 2's findings. Identify missing links and conduct a final deep investigation using google_search. YOU MUST EXCLUDE all sources and information already found in the previous two reports.",
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
            "artifact_path": "04_Code_Artifacts/{job_id}/cascade_synthesis_" + synth_id + ".md",
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
            "artifact_path": "04_Code_Artifacts/{job_id}/chord_final_draft_" + e3_id + ".md",
            "next_node_success": next_node, "wait_for": w3_id, "temperature": 0.1, "model": "gemini-2.5-pro", "agent": "Gretchen_Synthesizer"
        }
        
        for k in ephemeral_nodes:
            ephemeral_nodes[k].setdefault("artifact_path", "")
            ephemeral_nodes[k]["next_node_failure"] = "FAILED"
            ephemeral_nodes[k]["tools_allowed"] = "none"
            ephemeral_nodes[k]["max_recursion"] = 3
            ephemeral_nodes[k]["agent_name"] = ephemeral_nodes[k]["agent"]
            
        next_nodes_to_queue.append(w1_id)
        
    elif macro_type.lower() == "crucible":
        opt_id = f"C_OPT_{macro_id}"
        pess_id = f"C_PESS_{macro_id}"
        mag_id = f"C_MAG_{macro_id}"
        deb_id = f"C_DEB_{macro_id}"
        jury_id = f"C_JURY_{macro_id}"
        
        ephemeral_nodes[opt_id] = {
            "prompt": "You are the Optimist Advocate. Read the source payload. Build the absolute strongest, most rigorous case FOR the premise. If you received feedback from the Magistrate, you must rewrite your argument to address all critiques.",
            "next_node_success": mag_id, "wait_for": "none", "temperature": 1.0, "model": "gemini-2.5-flash", "agent": "Crucible_Optimist"
        }
        ephemeral_nodes[pess_id] = {
            "prompt": "You are the Pessimist Advocate. Read the source payload. Build the absolute strongest, most rigorous case AGAINST the premise. If you received feedback from the Magistrate, you must rewrite your argument to address all critiques.",
            "next_node_success": mag_id, "wait_for": "none", "temperature": 1.0, "model": "gemini-2.5-flash", "agent": "Crucible_Pessimist"
        }
        ephemeral_nodes[mag_id] = {
            "prompt": (
                "You are the Crucible Magistrate. Review the arguments from the Optimist and Pessimist in the Gathered Artifact blocks. "
                "Score each argument on a scale of 0 to 100 based on logical rigor, exhaustiveness, and evidence.\n\n"
                "CONDITIONAL ROUTING RULES:\n"
                f"1. If the Optimist scores below 90, you MUST output: ROUTE_TO:{opt_id} along with strict critique.\n"
                f"2. If the Pessimist scores below 90, you MUST output: ROUTE_TO:{pess_id} along with strict critique.\n"
                "3. If BOTH score 90 or above, accept the arguments and output: ROUTE_TO:STOP (The engine will automatically proceed to the debate).\n"
                "You may only route to one node at a time. Pick the weakest argument to revise first if both fail."
            ),
            "next_node_success": deb_id, "wait_for": f"{opt_id},{pess_id}", "temperature": 0.2, "model": "gemini-2.5-pro", "agent": "Crucible_Magistrate"
        }
        ephemeral_nodes[deb_id] = {
            "prompt": "You are the Crucible Host. The Magistrate has approved both arguments. Open the debate by summarizing the core conflict in two sentences, then pose a challenging question to both the Optimist and Pessimist.",
            "next_node_success": jury_id, "wait_for": mag_id, "temperature": 0.8, "model": "gemini-2.5-flash", "agent": "Crucible_Host",
            "dialogue_partner": "Crucible_Optimist|Crucible_Pessimist",
            "dialogue_rounds": 2
        }
        ephemeral_nodes[jury_id] = {
            "prompt": "You are the Crucible Jury. Read the full debate transcript. Deliver a final, binding synthesis and verdict. Which side won the debate and why? What is the undeniable truth synthesized from both perspectives?",
            "artifact_path": "04_Code_Artifacts/{job_id}/crucible_verdict_" + jury_id + ".md",
            "next_node_success": next_node, "wait_for": deb_id, "temperature": 0.4, "model": "gemini-2.5-pro", "agent": "Crucible_Jury"
        }
        
        for k in ephemeral_nodes:
            ephemeral_nodes[k].setdefault("artifact_path", "")
            ephemeral_nodes[k]["next_node_failure"] = "FAILED"
            ephemeral_nodes[k]["tools_allowed"] = "none"
            ephemeral_nodes[k]["max_recursion"] = 5  # Give the loop some breathing room
            ephemeral_nodes[k]["agent_name"] = ephemeral_nodes[k]["agent"]
            
        next_nodes_to_queue.extend([opt_id, pess_id])
        
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

