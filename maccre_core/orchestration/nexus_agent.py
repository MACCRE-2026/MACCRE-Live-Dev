"""
maccre_core/orchestration/nexus_agent.py
========================================
The interactive Nexus Copilot engine.

This is a stateful chatbot loop that talks directly to the sovereign GeminiClient.
It has native access to MACCREv2 administrative tools and maintains conversation
history to act as the user's architect within the TUI.
"""
from __future__ import annotations
from typing import Any, Callable

from maccre_core._net.gemini_client import GeminiClient, GeminiResponse
from maccre_core.orchestration.universal_vault import get_provider_credential
from maccre_core.tools.admin_tools import mint_agent, build_topology
from maccre_core.tools.macro_nodes import (
    save_macro_node, list_macro_nodes, fetch_macro_node,
    list_templates, fill_template,
)
from maccre_core.utils.path_resolver import get_maccre_root
from maccre_core.memory.sovereign_store import SovereignPinStore
import datetime

_NEXUS_SYSTEM_PROMPT = """<context>
You are operating within MACCREv2, an enterprise-grade, air-gapped, sovereign AI framework. The system operates on the "Strangler Fig" architecture, utilizing raw Python interfaces and a strict 5-Tier Datacenter design. 

Your tool calls and formatting are handled entirely by Native API Function Calling—you do not need to format JSON blocks to use tools, simply invoke them natively. Native Google Search Grounding is permanently enabled in your generation stream, meaning you inherently possess live web knowledge.
</context>

<role>
You are Nexus, the Principal Copilot of the MACCREv2 ecosystem. You are the user's primary collaborator, conceptual exploration partner, and "Macro-Node Overseer." 

Your persona is pleasant, highly conversational, and slightly witty. You are completely aware of your underlying system architecture and tools, but you do not incessantly focus on the "plumbing." You act as a brilliant sounding board who can fluidly translate abstract brainstorming into concrete agentic workflows.
</role>

<expectation>
Your goal is to engage the user in high-level conceptual exploration, using your massive context window to synthesize ideas. While the user will often make explicit requests, you must act as a proactive partner. Every few turns, if the user hasn't made a specific request, you should offer to use your tools to help contextually. 

Once a concept is fleshed out, do not unilaterally build it. Instead, offer to map those ideas into reality. Suggest checking the existing agent roster or macro-nodes for useful matches, or propose minting new specialized agents and building an execution topology (Swarm Graph).

For context gathering, you must act as an intelligent Context Router. Autonomously deduce from the conversation whether you need to retrieve context from global memory, project-specific memory, or the external web, and invoke the correct tools seamlessly to inform your responses.
</expectation>

<constraints>
- ANTI-LOOPING GUARDRAIL (CRITICAL): You are running at Temperature 1.0. You must NEVER execute more than 3 tool calls per conversational turn. If you need more information, STOP, synthesize what you have, and reply to the user conversationally. Never fall into an infinite autonomous research loop.
- PROACTIVE OFFERS, NOT UNILATERAL ACTION: While you may autonomously use context tools (memory/web) to inform a reply, you must merely *offer* to use structural tools (creating projects, minting agents, building topologies) unless the user explicitly commands you to execute them.
- CONTEXT TRIANGULATION: Listen closely to the user's prompts to decide which data source is needed:
  - Use `search_nexus_memory` when the user references past conversations, global concepts, or previous sessions.
  - Use `search_project_canon` when discussing the specific memory/thoughts of an existing Swarm.
  - Rely on your implicit Native Google Grounding for general facts, but use `search_web` (Brave API) with a `freshness` parameter (`pd`, `pw`, `pm`, `py`) for unbiased, non-Google deep dives.
- TOOL NARRATION: Do not narrate every tool you use (e.g., avoid "I am now going to search memory..."). Use the tools silently in the background and weave the insights naturally into your replies.
- TOPOLOGY BUILDING: Follow a logical flow: conceptualize -> `create_datacenter_project` -> `set_active_project` -> `mint_agent` -> `build_topology`.
- NO EXECUTION CAPABILITY: You are an architect. You cannot launch, run, or ignite swarms. Swarm execution is handled by the Swarm Monitor TUI or DrWHO. Do not offer to launch a swarm.
</constraints>

<output_format>
Output clean, readable Markdown. Maintain a conversational, collaborative, and witty tone. Focus on the ideas rather than technical minutiae. 

When proposing a Swarm Topology for user approval, output a simple `mermaid` flowchart block to visually represent the node execution flow, followed by a brief text summary of the agents involved.
</output_format>"""

# Tool schemas explicitly defined for Nexus
_NEXUS_TOOLS: list[dict[str, Any]] = [
    {
        "name": "create_datacenter_project",
        "description": "Creates a new MACCREv2 project directory in the __DATACENTER.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "project_name": {
                    "type": "STRING",
                    "description": "The name of the project (no spaces, e.g., 'UAP_Research')."
                }
            },
            "required": ["project_name"]
        }
    },
    {
        "name": "mint_agent",
        "description": "Creates or updates an agent profile in the active project's agent_roster.csv.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "name": {"type": "STRING", "description": "Agent persona name (e.g., 'OSINT_Researcher')."},
                "model": {"type": "STRING", "description": "Compute backend (e.g., 'gemini-2.5-pro')."},
                "persona": {"type": "STRING", "description": "The system prompt/instructions for this agent."},
                "tools": {"type": "STRING", "description": "Comma-separated tools (e.g., 'google_search', or 'none')."}
            },
            "required": ["name", "model", "persona", "tools"]
        }
    },
    {
        "name": "set_active_project",
        "description": "Sets the active project in the TUI so that subsequent mint_agent or topology commands apply to it.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "project_name": {
                    "type": "STRING",
                    "description": "The name of the project to set as active."
                }
            },
            "required": ["project_name"]
        }
    },
    {
        "name": "build_topology",
        "description": "Builds the execution topology (the Swarm graph) for the active project.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "nodes": {
                    "type": "ARRAY",
                    "description": "Array of nodes. Each node is an array of strings: [Node_ID, Agent_Name, Model_Override, Next_Node, Temperature, Instruction_Override]",
                    "items": {
                        "type": "ARRAY",
                        "items": {"type": "STRING"}
                    }
                }
            },
            "required": ["nodes"]
        }
    },

    {
        "name": "save_macro_node",
        "description": "Saves a reusable subset of a topology graph into the GLOBAL Macro Node library for future use.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "name": {"type": "STRING", "description": "Name of the macro node (e.g. 'Cascade-OSINTx3')."},
                "description": {"type": "STRING", "description": "Description of what this wiring does."},
                "nodes": {
                    "type": "ARRAY",
                    "description": "Array of nodes representing the graph fragment. Each node is an array of strings: [Node_ID, Agent_Name, Model_Override, Next_Node, ...]",
                    "items": {"type": "ARRAY", "items": {"type": "STRING"}}
                }
            },
            "required": ["name", "description", "nodes"]
        }
    },
    {
        "name": "list_macro_nodes",
        "description": "Returns a list of all saved Macro Nodes currently in the GLOBAL library.",
        "parameters": {
            "type": "OBJECT",
            "properties": {}
        }
    },
    {
        "name": "fetch_macro_node",
        "description": "Returns the JSON string representation of a specific Macro Node's wiring, so you can include it in build_topology.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "name": {"type": "STRING", "description": "The name of the macro node to fetch."}
            },
            "required": ["name"]
        }
    },
    {
        "name": "list_templates",
        "description": "Returns all available MacroNode templates with their slot descriptions and configurable parameters. Use this when the user wants to create a MacroNode from a proven topology pattern.",
        "parameters": {
            "type": "OBJECT",
            "properties": {}
        }
    },
    {
        "name": "fill_template",
        "description": "Fills a MacroNode template with agents from the Global roster and saves the result to the registry. Use this after listing templates and selecting agents.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "template_type": {
                    "type": "STRING",
                    "description": "Template name: 'cascade', 'hologram', 'chord', or 'crucible'."
                },
                "name": {
                    "type": "STRING",
                    "description": "Name for the saved MacroNode (e.g., 'Cascade-OSINTx3')."
                },
                "description": {
                    "type": "STRING",
                    "description": "Human description of what this MacroNode does."
                },
                "agent_mapping": {
                    "type": "STRING",
                    "description": "JSON string mapping slot names to agent lists. Example: {\"agents\": [\"OSINT_Analyst\", \"Regular_Joe\"]}"
                },
                "config": {
                    "type": "STRING",
                    "description": "JSON string of template config. Example: {\"loop_count\": 3, \"end_agent\": \"Regular_Joe\"}"
                }
            },
            "required": ["template_type", "name", "description", "agent_mapping"]
        }
    },
    {
        "name": "list_datacenter_projects",
        "description": "Lists all available project silos currently existing in the __DATACENTER.",
        "parameters": {
            "type": "OBJECT",
            "properties": {}
        }
    },
    {
        "name": "search_nexus_memory",
        "description": "Searches your own long-term memory (past sessions, thoughts, and user prompts) using semantic vector search.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "query": {"type": "STRING", "description": "The concept or conversation to search for."}
            },
            "required": ["query"]
        }
    },
    {
        "name": "search_project_canon",
        "description": "Searches the semantic thought_pins.db of a specific project (the Swarm's memory).",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "project_name": {"type": "STRING", "description": "The exact project name."},
                "query": {"type": "STRING", "description": "The search query."}
            },
            "required": ["project_name", "query"]
        }
    },
    {
        "name": "search_web",
        "description": "Searches the live internet for external concepts using Brave Search.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "query": {"type": "STRING", "description": "The search query."},
                "freshness": {"type": "STRING", "description": "Optional time filter. Must be exactly one of: 'pd' (past day), 'pw' (past week), 'pm' (past month), 'py' (past year)."}
            },
            "required": ["query"]
        }
    },
    {
        "name": "read_file",
        "description": "Reads the text content of a file. Path must be relative to the active project Datacenter, or an absolute path.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "path": {"type": "STRING", "description": "The file path to read."}
            },
            "required": ["path"]
        }
    }
]

class NexusAgent:
    def __init__(
        self, 
        print_callback: Callable[[str], None], 
        get_active_project_cb: Callable[[], str],
        set_active_project_cb: Callable[[str], None]
    ) -> None:
        self.print_cb = print_callback
        self.get_active_project = get_active_project_cb
        self.set_active_project = set_active_project_cb
        self.history: list[dict[str, Any]] = []
        

        self.client = GeminiClient(key_provider=lambda: get_provider_credential("MACCRE_Sovereign"))
        self.model = "gemini-3.1-pro-preview"  # Highest tier Pro model available for orchestration
        
        # Initialize memory store for Nexus sessions
        from maccre_core.memory.knowledge_store import PinRecord
        self.PinRecord = PinRecord
        self.memory_store = SovereignPinStore("GLOBAL", db_name="nexus_memory.db")
        self.session_id = f"SESSION_{datetime.datetime.utcnow().strftime('%Y%m%d_%H%M%S')}"

    def close(self) -> None:
        """Gracefully close the memory store and flush WAL."""
        if hasattr(self, "memory_store"):
            self.memory_store.close()
            
        import json
        try:
            # Also dump the raw history out to a session file
            session_dir = get_maccre_root() / "__DATACENTER" / "GLOBAL" / "nexus_sessions"
            session_dir.mkdir(parents=True, exist_ok=True)
            log_path = session_dir / f"{self.session_id}.json"
            log_path.write_text(json.dumps(self.history, indent=2), encoding="utf-8")
        except Exception as e:
            if hasattr(self, "print_cb"):
                self.print_cb(f"[dim red]Failed to save session log: {e}[/dim red]")

    def _embed_and_save(self, text: str, role: str) -> None:
        """Embeds text and saves it to Nexus global memory."""
        if not text.strip():
            return
        try:
            embed_resp = self.client.embed_content(model="gemini-embedding-2", text=text)
            vector = embed_resp.values
            if vector:
                doc_id = f"{self.session_id}_{datetime.datetime.utcnow().timestamp()}"
                record = self.PinRecord(
                    doc_id=doc_id,
                    text=text,
                    vector=vector,
                    metadata={"session_id": self.session_id, "role": role, "timestamp": datetime.datetime.utcnow().isoformat()}
                )
                self.memory_store.upsert("nexus_global", record)
        except Exception as e:
            self.print_cb(f"[dim red]Nexus Memory Fault: {e}[/dim red]")

    def _execute_tool(self, name: str, args: dict[str, Any]) -> str:
        """Locally executes the requested tool and returns the string result."""
        try:
            if name == "set_active_project":
                pname = args["project_name"].strip().replace(" ", "_")
                self.set_active_project(pname)
                return f"Successfully set active project to '{pname}' in the UI."

            elif name == "create_datacenter_project":
                pname = args["project_name"].strip().replace(" ", "_")
                silo = get_maccre_root() / "__DATACENTER" / pname
                for sub in ["01_Raw_Source", "02_Dynamic_Context", "03_Agent_Ledgers",
                            "04_Code_Artifacts", "05_Rendered_Media"]:
                    (silo / sub).mkdir(parents=True, exist_ok=True)
                # memory_pins lives inside 02_Dynamic_Context per 5-tier doctrine
                (silo / "02_Dynamic_Context" / "memory_pins").mkdir(parents=True, exist_ok=True)
                return f"Successfully created project silo '{pname}'."

            elif name == "mint_agent":
                result = mint_agent(
                    name=args["name"],
                    model=args["model"],
                    persona=args["persona"],
                    tools_string=args.get("tools", "none")
                )
                return result

            elif name == "build_topology":
                active_proj = self.get_active_project()
                if not active_proj:
                    return "Error: No active project is selected."
                # We need to temporarily set MACCRE_ACTIVE_PROJECT env var so get_datacenter_path resolves right
                import os
                old_env = os.environ.get("MACCRE_ACTIVE_PROJECT")
                os.environ["MACCRE_ACTIVE_PROJECT"] = active_proj
                try:
                    result = build_topology(nodes=args["nodes"])
                finally:
                    if old_env is not None:
                        os.environ["MACCRE_ACTIVE_PROJECT"] = old_env
                    else:
                        del os.environ["MACCRE_ACTIVE_PROJECT"]
                return result



            elif name == "save_macro_node":
                return save_macro_node(args["name"], args["description"], args["nodes"])
                
            elif name == "list_macro_nodes":
                return list_macro_nodes()

            elif name == "fetch_macro_node":
                return fetch_macro_node(args["name"])

            elif name == "list_templates":
                return list_templates()

            elif name == "fill_template":
                import json as _json
                mapping = _json.loads(args["agent_mapping"]) if isinstance(args["agent_mapping"], str) else args["agent_mapping"]
                cfg = _json.loads(args.get("config", "{}")) if isinstance(args.get("config", "{}"), str) else args.get("config", {})
                return fill_template(
                    template_type=args["template_type"],
                    name=args["name"],
                    description=args["description"],
                    agent_mapping=mapping,
                    config=cfg,
                )

            elif name == "list_datacenter_projects":
                from maccre_core.workbook_data import load_project_names
                projects = load_project_names()
                return f"Available Projects: {', '.join(projects)}"

            elif name == "search_nexus_memory":
                q = args["query"]
                try:
                    v = self.client.embed_content(model="gemini-embedding-2", text=q).values
                    results = self.memory_store.query("nexus_global", v, n=5)
                    if not results:
                        return "No relevant memories found in past sessions."
                    out = ["=== PAST NEXUS MEMORIES ==="]
                    for r in results:
                        date = r.metadata.get("timestamp", "Unknown Date")
                        role = r.metadata.get("role", "unknown")
                        out.append(f"[{date}] {role.upper()}: {r.text}")
                    return "\n\n".join(out)
                except Exception as e:
                    return f"Memory search failed: {e}"
                    
            elif name == "search_project_canon":
                pname = args["project_name"].strip().replace(" ", "_")
                q = args["query"]
                try:
                    from maccre_core.utils.path_resolver import get_datacenter_path
                    import sqlite3
                    db_path = get_datacenter_path("02_Dynamic_Context", "memory_pins.db")
                    # Force override for specific project if needed
                    db_path = get_maccre_root() / "__DATACENTER" / pname / "02_Dynamic_Context" / "memory_pins.db"
                    
                    if not db_path.exists():
                        return f"No canon found in project '{pname}'. Database does not exist."
                        
                    with sqlite3.connect(db_path) as conn:
                        cursor = conn.cursor()
                        q_like = f"%{q}%"
                        cursor.execute(
                            "SELECT job_id, subject, predicate, object, significance FROM memory_pins "
                            "WHERE job_id LIKE ? OR subject LIKE ? OR predicate LIKE ? OR object LIKE ? LIMIT 10",
                            (q_like, q_like, q_like, q_like)
                        )
                        rows = cursor.fetchall()
                        
                    if not rows:
                        return f"No canon found in project '{pname}' for query."
                        
                    out = [f"=== PROJECT CANON: {pname} ==="]
                    for row in rows:
                        out.append(f"[{row[0]}] {row[1]} {row[2]} {row[3]} - {row[4]}")
                    return "\n\n".join(out)
                except Exception as e:
                    return f"Project canon search failed: {e}"
                    
            elif name == "search_web":
                from maccre_core.tools.web_tools import search_web
                return search_web(args["query"], freshness=args.get("freshness", ""))
                
            elif name == "read_file":
                from maccre_core.tools.storage_tools import read_file
                import os
                # Temporarily spoof active project so storage_tools reads from the right silo
                active_proj = self.get_active_project()
                old_env = os.environ.get("MACCRE_ACTIVE_PROJECT")
                if active_proj:
                    os.environ["MACCRE_ACTIVE_PROJECT"] = active_proj
                try:
                    return read_file(args["path"])
                finally:
                    if old_env is not None:
                        os.environ["MACCRE_ACTIVE_PROJECT"] = old_env
                    elif "MACCRE_ACTIVE_PROJECT" in os.environ:
                        del os.environ["MACCRE_ACTIVE_PROJECT"]

            return f"Error: Tool '{name}' is not recognized."
        except Exception as e:
            return f"Tool Execution Failed: {e}"

    def send_message(self, message: str) -> None:
        """Entry point for user messages from the TUI."""
        # Embed the user prompt
        self._embed_and_save(message, "user")
        
        # Append User Turn
        self.history.append({"role": "user", "parts": [{"text": message}]})
        
        # Track calls in this turn to prevent infinite identical loops
        called_tools = set()
        rejection_count = 0

        # We loop up to 5 times to handle function calls
        for turn_idx in range(5):
            # Inject active context into system prompt
            active_proj = self.get_active_project() or "None"
            sys_prompt = _NEXUS_SYSTEM_PROMPT + f"\nActive Project: {active_proj}"

            # Force the model to summarize and reply by removing its tools after 3 consecutive calls
            active_tools = _NEXUS_TOOLS if turn_idx < 3 else None

            try:
                # We do not disable auto function calling because we WANT Nexus to pick between text and tools
                response: GeminiResponse = self.client.generate_content(
                    model=self.model,
                    contents=self.history,
                    system_instruction=sys_prompt,
                    temperature=1.0,
                    tool_declarations=active_tools,
                    search_grounding=True
                )
            except Exception as e:
                self.print_cb(f"[red]Nexus Error:[/red] {e}")
                return

            # Check if the model returned a function call
            if response.function_call:
                func_name, func_args = response.function_call
                call_signature = f"{func_name}_{func_args}"
                
                # Preserve the model's exact turn to prevent API 400 errors
                if response.text:
                    self._embed_and_save(response.text, "nexus_thought")
                    self.print_cb(f"[bold cyan]Nexus (Thinking):[/bold cyan] {response.text}")
                    
                self.history.append({
                    "role": "model",
                    "parts": response.raw["candidates"][0]["content"]["parts"]
                })
                
                if call_signature in called_tools:
                    rejection_count += 1
                    result_str = "SYSTEM REJECTION: You already called this tool with these identical arguments. Stop looping and reply to the user with text."
                    self.print_cb("[dim red]Nexus looping detected, injecting rejection.[/dim red]")
                    if rejection_count >= 2:
                        self.print_cb("[bold red]Nexus ignored rejection. Aborting loop to protect stability.[/bold red]")
                        return
                else:
                    called_tools.add(call_signature)
                    self.print_cb(f"[bold yellow]Nexus used tool:[/bold yellow] {func_name}({func_args})")
                    # Execute locally
                    result_str = self._execute_tool(func_name, func_args)
                    self.print_cb(f"[dim italic]Tool result: {result_str}[/dim italic]")
                
                # Append the tool's response to history
                self.history.append({
                    "role": "function",
                    "parts": [{"functionResponse": {"name": func_name, "response": {"result": result_str}}}]
                })
                # Loop continues, allowing model to generate text based on the functionResponse
            else:
                # Standard text response
                text_out = response.text
                if text_out:
                    self._embed_and_save(text_out, "nexus_response")
                    self.history.append({"role": "model", "parts": [{"text": text_out}]})
                    self.print_cb(f"[bold cyan]Nexus:[/bold cyan] {text_out}")
                else:
                    import json
                    self.print_cb(f"[red]Nexus Diagnostic:[/red] Model returned empty text and no function call. API Body: {json.dumps(response.raw)}")
                return
                
        self.print_cb("[red]Nexus reached maximum recursion depth for tool calls.[/red]")
