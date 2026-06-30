import re

content = open('B:\EXO_GANS\maccre_tui\nexus_plex.py', 'r', encoding='utf-8').read()

MODALS = '''
class NodeConfigModal(ModalScreen[tuple]):
    """Modal for configuring an Agent or Macro node."""
    
    DEFAULT_CSS = """
    NodeConfigModal {
        align: center middle;
    }
    #node-config-dialog {
        padding: 1 2;
        width: 60;
        height: auto;
        border: thick $background 80%;
        background: $surface;
    }
    .config-title {
        text-style: bold;
        color: #58a6ff;
        margin-bottom: 1;
    }
    .category-title {
        text-style: bold;
        color: #e6edf3;
        margin-top: 1;
        margin-bottom: 1;
    }
    """

    def __init__(self, step_data: tuple, active_project: str) -> None:
        super().__init__()
        self.step_data = step_data
        self.name = step_data[0]
        self.step_type = step_data[2]
        self.payload_mode = step_data[3] if len(step_data) > 3 else "Unified Ledger"
        self.active_project = active_project
        self.agent_profile = {}
        if self.step_type == "agent":
            from maccre_core.agent_library import get_agent_store
            store = get_agent_store(self.active_project)
            for p in store.load_all():
                if (p.get("agent_name") or p.get("AGENT_NAME", "")).strip() == self.name:
                    self.agent_profile = p
                    break

    def compose(self) -> ComposeResult:
        with Container(id="node-config-dialog"):
            yield Label(f"Configure Node: {self.name}", classes="config-title")
            
            yield Label("Payload Context Mode", classes="category-title")
            yield Select(
                [("Unified Ledger", "Unified Ledger"), ("Preceding Node Only", "Preceding Node Only")],
                value=self.payload_mode,
                id="node-payload-mode"
            )
            
            if self.step_type == "agent":
                yield Label("Assigned Tools", classes="category-title")
                yield Label("Tools exposed to this agent. Comma separated list.")
                tools = self.agent_profile.get("tools_allowed", "") if self.agent_profile else ""
                
                # Checkboxes for common tools
                common_tools = ["read_file", "write_file", "list_dir", "google_search", "hybrid_search", "execute_sql", "execute_terminal"]
                assigned = [t.strip() for t in tools.split(",")] if tools and tools != "none" else []
                
                with Horizontal():
                    with Vertical():
                        yield Label("[dim]Available Tools[/dim]")
                        yield Select(
                            [(t, t) for t in common_tools],
                            prompt="Select a tool to add...",
                            id="tool-select"
                        )
                        yield Button("Add Tool", id="btn-add-tool", variant="primary")
                
                yield Input(value=",".join(assigned) if assigned else "none", id="node-tools-input")
            
            with Horizontal(classes="dialog-buttons"):
                yield Button("Cancel", variant="error", id="btn-cancel")
                yield Button("Save Configuration", variant="success", id="btn-save")

    @on(Button.Pressed, "#btn-add-tool")
    def add_tool(self):
        sel = self.query_one("#tool-select", Select)
        inp = self.query_one("#node-tools-input", Input)
        if sel.value and sel.value != Select.BLANK:
            current = [t.strip() for t in inp.value.split(",") if t.strip() and t.strip() != "none"]
            if sel.value not in current:
                current.append(sel.value)
                inp.value = ",".join(current)

    @on(Button.Pressed, "#btn-cancel")
    def cancel(self):
        self.dismiss(None)

    @on(Button.Pressed, "#btn-save")
    def save(self):
        new_payload = self.query_one("#node-payload-mode", Select).value
        
        if self.step_type == "agent":
            inp = self.query_one("#node-tools-input", Input)
            tools_val = inp.value.strip() or "none"
            if self.agent_profile:
                # Update SQLite DB
                from maccre_core.agent_library import get_agent_store
                store = get_agent_store(self.active_project)
                self.agent_profile["tools_allowed"] = tools_val
                store.save_profile(self.agent_profile)

        # return the updated tuple
        new_tuple = list(self.step_data)
        if len(new_tuple) > 3:
            new_tuple[3] = str(new_payload)
        else:
            new_tuple.append(str(new_payload))
        self.dismiss(tuple(new_tuple))

class SpecialNodeConfigModal(ModalScreen[tuple]):
    def __init__(self, step_data: tuple) -> None:
        super().__init__()
        self.step_data = step_data
        self.name = step_data[0]
        self.payload_mode = step_data[3] if len(step_data) > 3 else "Unified Ledger"

    def compose(self) -> ComposeResult:
        with Container(id="node-config-dialog"):
            yield Label(f"Configure Special Node: {self.name}", classes="config-title")
            yield Label("[dim]Configuration currently unsupported in UI for Special Nodes.[/dim]")
            
            yield Label("Payload Context Mode", classes="category-title")
            yield Select(
                [("Unified Ledger", "Unified Ledger"), ("Preceding Node Only", "Preceding Node Only")],
                value=self.payload_mode,
                id="special-payload-mode"
            )
            with Horizontal(classes="dialog-buttons"):
                yield Button("Cancel", variant="error", id="btn-cancel")
                yield Button("Save Configuration", variant="success", id="btn-save")

    @on(Button.Pressed, "#btn-cancel")
    def cancel(self):
        self.dismiss(None)

    @on(Button.Pressed, "#btn-save")
    def save(self):
        new_payload = self.query_one("#special-payload-mode", Select).value
        new_tuple = list(self.step_data)
        if len(new_tuple) > 3:
            new_tuple[3] = str(new_payload)
        else:
            new_tuple.append(str(new_payload))
        self.dismiss(tuple(new_tuple))
'''

content = content.replace('class LinearFlowEditorModal(ModalScreen[list]):', MODALS + '
class LinearFlowEditorModal(ModalScreen[list]):')
open('B:\EXO_GANS\maccre_tui\nexus_plex.py', 'w', encoding='utf-8').write(content)
