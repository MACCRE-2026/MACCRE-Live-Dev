import re
content = open('B:\\EXO_GANS\\maccre_tui\\nexus_plex.py', 'r', encoding='utf-8').read()

MODAL_CODE = """class NodeConfigModal(ModalScreen[dict | None]):
    \"\"\"Modal to edit a MacroNode's name or override parameters.\"\"\"
    CSS = \"\"\"
    NodeConfigModal {
        align: center middle;
        background: $background 80%;
    }
    #node-config-container {
        width: 70%;
        height: 80%;
        border: solid $accent;
        background: $surface;
        padding: 1 2;
    }
    .node-cfg-title {
        text-align: center;
        text-style: bold;
        color: $accent;
        margin-bottom: 1;
    }
    .node-cfg-row {
        height: auto;
        align: left middle;
        margin-bottom: 1;
    }
    .category-title {
        text-style: bold;
        color: #e6edf3;
        margin-top: 1;
        margin-bottom: 1;
    }
    #cfg-custom-instructions {
        height: 1fr;
        border: solid $panel;
    }
    \"\"\"
    
    def __init__(self, node_name: str, current_payload_mode: str = "Unified Ledger", current_instructions: str = "", active_project: str = "", agents_in_node: list[str] = None, **kwargs):
        super().__init__(**kwargs)
        self.node_name = node_name
        self.current_payload_mode = current_payload_mode
        self.current_instructions = current_instructions
        self.active_project = active_project
        self.agents_in_node = agents_in_node or []
        self.agent_profiles = {}
        
        if self.agents_in_node and self.active_project:
            try:
                from maccre_core.agent_library import get_agent_store
                store = get_agent_store(self.active_project)
                for p in store.load_all():
                    aname = (p.get("agent_name") or p.get("AGENT_NAME", "")).strip()
                    if aname in self.agents_in_node:
                        self.agent_profiles[aname] = p
            except Exception:
                pass
        
    def compose(self) -> ComposeResult:
        with Vertical(id="node-config-container"):
            yield Label(f"Configure Node: {self.node_name}", classes="node-cfg-title")
            with Horizontal(classes="node-cfg-row"):
                yield Label("Custom Node Name: ")
                yield Input(value=self.node_name, id="cfg-node-name")
                
            with Horizontal(classes="node-cfg-row"):
                yield Label("Ledger Routing Mode: ")
                yield Select(
                    [("Unified Ledger", "Unified Ledger"), ("Preceding Node Only", "Preceding Node Only")],
                    value=self.current_payload_mode,
                    id="cfg-payload-mode"
                )

            if self.agents_in_node:
                yield Label("Agent Tool Configuration", classes="category-title")
                yield Select(
                    [(a, a) for a in self.agents_in_node],
                    prompt="Select Agent to configure...",
                    id="cfg-agent-select"
                )
                with Horizontal(id="cfg-agent-tools-container"):
                    with Vertical():
                        yield Label("[dim]Available Tools[/dim]")
                        common_tools = ["read_file", "write_file", "list_dir", "google_search", "hybrid_search", "execute_sql", "execute_terminal"]
                        yield Select(
                            [(t, t) for t in common_tools],
                            prompt="Select a tool to add...",
                            id="tool-select",
                            disabled=True
                        )
                        yield Button("Add Tool", id="btn-add-tool", variant="primary", disabled=True)
                
                yield Input(value="", id="node-tools-input", disabled=True)

            yield Label("Node-Specific Custom Instructions (Appended to System Prompt):", classes="node-cfg-row")
            yield TextArea(text=self.current_instructions, id="cfg-custom-instructions")
            
            with Horizontal(id="payload-modal-buttons"):
                yield Button("Cancel", variant="error", id="btn-cfg-cancel")
                yield Button("Save", variant="success", id="btn-cfg-save")
                
    @on(Select.Changed, "#cfg-agent-select")
    def on_agent_selected(self, event: Select.Changed) -> None:
        agent_name = str(event.value) if event.value and event.value != Select.BLANK else ""
        tool_select = self.query_one("#tool-select", Select)
        btn_add = self.query_one("#btn-add-tool", Button)
        tools_input = self.query_one("#node-tools-input", Input)
        
        if not agent_name:
            tool_select.disabled = True
            btn_add.disabled = True
            tools_input.disabled = True
            tools_input.value = ""
            return
            
        tool_select.disabled = False
        btn_add.disabled = False
        tools_input.disabled = False
        
        prof = self.agent_profiles.get(agent_name, {})
        tools = prof.get("tools_allowed", "")
        assigned = [t.strip() for t in tools.split(",")] if tools and tools != "none" else []
        tools_input.value = ",".join(assigned) if assigned else "none"

    @on(Button.Pressed, "#btn-add-tool")
    def add_tool(self):
        sel = self.query_one("#tool-select", Select)
        inp = self.query_one("#node-tools-input", Input)
        if sel.value and sel.value != Select.BLANK and not inp.disabled:
            current = [t.strip() for t in inp.value.split(",") if t.strip() and t.strip() != "none"]
            if str(sel.value) not in current:
                current.append(str(sel.value))
                inp.value = ",".join(current)
                
    @on(Button.Pressed, "#btn-cfg-cancel")
    def cancel(self):
        self.dismiss(None)
        
    @on(Button.Pressed, "#btn-cfg-save")
    def save(self):
        new_name = self.query_one("#cfg-node-name", Input).value.strip()
        new_mode = self.query_one("#cfg-payload-mode", Select).value
        new_instr = self.query_one("#cfg-custom-instructions", TextArea).text.strip()
        
        # Save Agent tool config to AgentStore
        try:
            agent_select = self.query_one("#cfg-agent-select", Select)
            if agent_select and agent_select.value and agent_select.value != Select.BLANK:
                tools_val = self.query_one("#node-tools-input", Input).value.strip() or "none"
                agent_name = str(agent_select.value)
                if agent_name in self.agent_profiles:
                    self.agent_profiles[agent_name]["tools_allowed"] = tools_val
                    from maccre_core.agent_library import get_agent_store
                    store = get_agent_store(self.active_project)
                    store.save(self.agent_profiles[agent_name])
        except Exception:
            pass
            
        self.dismiss({"name": new_name, "payload_mode": new_mode, "custom_instructions": new_instr})
"""

CALLER_OLD = """        def handle_config(result: dict | None):
            if result:
                if result.get("name"):
                    node.macronode_name = result["name"]
                if result.get("payload_mode"):
                    node.payload_mode = str(result["payload_mode"])
                if "custom_instructions" in result:
                    node.custom_instructions = result["custom_instructions"]
                self.write_agent_log(f"[green]Node {idx} updated.[/green]")
                self._refresh_active_flow_sequence()
                
        self.push_screen(NodeConfigModal(
            node_name=node.macronode_name,
            current_payload_mode=getattr(node, "payload_mode", "Unified Ledger"),
            current_instructions=getattr(node, "custom_instructions", "")
        ), handle_config)"""

CALLER_NEW = """        def handle_config(result: dict | None):
            if result:
                if result.get("name"):
                    node.macronode_name = result["name"]
                if result.get("payload_mode"):
                    node.payload_mode = str(result["payload_mode"])
                if "custom_instructions" in result:
                    node.custom_instructions = result["custom_instructions"]
                self.write_agent_log(f"[green]Node {idx} updated.[/green]")
                self._refresh_active_flow_sequence()
                
        # Resolve agents in the MacroNode
        agents_in_node = set()
        try:
            from maccre_core.macronode_registry import get_macronode_store
            store = get_macronode_store()
            macro_def = store.load(node.macronode_name)
            for row in macro_def.get("topology_rows", []):
                aname = str(row.get("Agent_Name", ""))
                for slot_key, slot_val in getattr(node, "agent_mapping", {}).items():
                    if aname == f"{{{slot_key}}}" or aname == slot_key:
                        aname = slot_val
                if aname and not aname.startswith("{") and aname.upper() != "NONE":
                    agents_in_node.add(aname)
        except Exception:
            pass

        self.push_screen(NodeConfigModal(
            node_name=node.macronode_name,
            current_payload_mode=getattr(node, "payload_mode", "Unified Ledger"),
            current_instructions=getattr(node, "custom_instructions", ""),
            active_project=self.active_project,
            agents_in_node=list(agents_in_node)
        ), handle_config)"""

# Extract the old NodeConfigModal to replace
start_idx = content.find("class NodeConfigModal(ModalScreen[dict | None]):")
end_idx = content.find("class FlowExecutionPanel(Vertical):")

if start_idx != -1 and end_idx != -1:
    content = content[:start_idx] + MODAL_CODE + "\n\n\n" + content[end_idx:]

if CALLER_OLD in content:
    content = content.replace(CALLER_OLD, CALLER_NEW)
else:
    print("CALLER_OLD not found in content!")

with open('B:\\EXO_GANS\\maccre_tui\\nexus_plex.py', 'w', encoding='utf-8') as f:
    f.write(content)
print("Updated successfully")
