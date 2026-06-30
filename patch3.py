import re

with open('B:\\EXO_GANS\\maccre_tui\\nexus_plex.py', 'r', encoding='utf-8') as f:
    content = f.read()

# 1. Update NodeConfigModal UI
NEW_NODE_CFG_MODAL = """            if self.agents_in_node:
                yield Label("Agent Tool Configuration", classes="category-title")
                yield Select(
                    [(a, a) for a in self.agents_in_node],
                    prompt="Select Agent to configure...",
                    id="cfg-agent-select"
                )
                with Horizontal(id="cfg-agent-tools-container"):
                    with Vertical(classes="flow-select-group"):
                        yield Label("[dim]Available Tools[/dim]")
                        common_tools = ["read_file", "write_file", "list_dir", "web_search", "hybrid_search", "execute_sql", "execute_terminal"]
                        yield Select(
                            [(t, t) for t in common_tools],
                            prompt="Select a tool to add...",
                            id="tool-select",
                            disabled=True
                        )
                        yield Button("Add Tool", id="btn-add-tool", variant="primary", disabled=True, classes="flow-add-btn")
                    
                    with Vertical(id="tool-info-panel", classes="info-panel-container"):
                        yield Label("Tool Details", classes="info-panel-title")
                        yield Static("[dim]Select a tool to view details.[/dim]", id="tool-info-body", classes="info-panel-body")
                
                yield Input(value="", id="node-tools-input", disabled=True)

            yield Label("Node-Specific Custom Instructions (Appended to System Prompt):", classes="node-cfg-row")
            yield TextArea(text=self.current_instructions, id="cfg-custom-instructions")
            
            yield Label("Node-Specific Payload Injection (Overrides Flow Payload):", classes="node-cfg-row")
            yield TextArea(text="", id="cfg-payload-injection") # TODO: load from FlowStep if we add it
"""

cfg_modal_re = re.compile(r'            if self.agents_in_node:.*?(?=\s*with Horizontal\(id="payload-modal-buttons"\):)', re.DOTALL)
if cfg_modal_re.search(content):
    content = cfg_modal_re.sub(NEW_NODE_CFG_MODAL, content)
else:
    print("WARNING: Could not find NodeConfigModal container to replace")

# 2. Add Tool Select event handler
TOOL_EVENT_HANDLER = """
    @on(Select.Changed, "#tool-select")
    def tool_selection_changed(self, event: Select.Changed) -> None:
        body = self.query_one("#tool-info-body", Static)
        if not event.value or event.value == Select.BLANK:
            body.update("[dim]Select a tool to view details.[/dim]")
            return
        name = str(event.value)
        
        tool_desc = {
            "read_file": "Reads the contents of a specified file. Used for extracting exact file data.",
            "write_file": "Overwrites or creates a new file. Used for saving generated code.",
            "list_dir": "Lists the contents of a directory. Useful for exploring the workspace.",
            "web_search": "Searches the live web for current information.\\n\\n[bold warning]Note:[/bold warning] Standard Google Search Grounding is configured globally in the Agent Builder. This tool is primarily for local agent Brave searches or combined Brave/Google dual-search.",
            "hybrid_search": "Semantic vector search against the local Sovereign Memory Chroma DB, combined with lexical BM25.\\n\\n[bold warning]Note:[/bold warning] Standard Google Search Grounding is configured globally in the Agent Builder. This tool is primarily for local agent Brave searches or combined Brave/Google dual-search.",
            "execute_sql": "Executes a raw SQL query against a specified database.",
            "execute_terminal": "Runs an arbitrary shell command (e.g. git, npm, python). Use with caution."
        }
        
        desc = tool_desc.get(name, "No description available.")
        info = [
            f"[bold cyan]{name}[/bold cyan]",
            "",
            "[bold]Description[/bold]",
            str(desc)
        ]
        body.update("\\n".join(info))
"""

idx = content.find("class NodeConfigModal(ModalScreen[dict]):")
if idx != -1:
    idx2 = content.find("@on(Button.Pressed, \"#btn-cfg-cancel\")", idx)
    content = content[:idx2] + TOOL_EVENT_HANDLER + "\n    " + content[idx2:]
else:
    print("WARNING: Could not find NodeConfigModal class to insert tool handler")

with open('B:\\EXO_GANS\\maccre_tui\\nexus_plex.py', 'w', encoding='utf-8') as f:
    f.write(content)

print("Patch part 3 done.")
