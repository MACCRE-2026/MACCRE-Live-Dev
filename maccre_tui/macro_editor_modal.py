from textual import on
from textual.app import ComposeResult
from textual.containers import Container, Horizontal
from textual.screen import ModalScreen
from textual.widgets import Button, Input, Label, Select
from maccre_core.orchestration.macro_factory import TEMPLATE_CATALOG

class MacroNodeEditorModal(ModalScreen[dict | None]):
    """Modal to create or edit a Template MacroNode."""
    
    CSS = """
    #macro-editor-dialog {
        width: 90%;
        max-width: 90%;
        height: 90%;
        border: round $primary;
        background: $surface;
        padding: 1 2;
        layout: horizontal;
    }
    #me-left-form {
        width: 3fr;
        height: 100%;
        overflow-y: auto;
        padding-right: 2;
        border-right: solid $primary;
    }
    #me-right-info {
        width: 2fr;
        height: 100%;
        padding-left: 2;
        overflow-y: auto;
    }
    .me-slot-row {
        layout: horizontal;
        height: auto;
        margin-bottom: 1;
    }
    #me-buttons {
        margin-top: 1;
        margin-bottom: 1;
        padding-bottom: 1;
    }
    .me-slot-label {
        width: auto;
        min-width: 20;
        content-align-vertical: middle;
        margin-right: 1;
    }
    .me-slot-input {
        width: 1fr;
    }
    #me-dynamic-container {
        height: auto;
        margin-top: 1;
        border-top: solid $primary;
        padding-top: 1;
    }
    .info-panel-title {
        color: #8b949e;
        text-style: bold;
        margin-bottom: 1;
    }
    .info-panel-body {
        color: #c9d1d9;
    }
    """

    def __init__(self, templates: list[dict], roster: list[str], special_nodes: list[tuple[str, str]]):
        super().__init__()
        self.templates = templates
        self.roster = sorted(roster)
        self.special_nodes = special_nodes
        self.all_agents = sorted(self.roster + [sn[0] for sn in self.special_nodes])
        self.current_slots: list[str] = []
        self.current_configs: list[str] = []

    def compose(self) -> ComposeResult:
        from textual.widgets import Static
        from textual.containers import Vertical
        with Container(classes="dialog", id="macro-editor-dialog"):
            with Vertical(id="me-left-form"):
                yield Label("Edit / Create MacroNode", classes="pane-title", id="me-title")
                
                with Horizontal(classes="me-slot-row"):
                    yield Label("Select MacroNode:", classes="me-slot-label")
                    options = [("*** Create New... ***", "__NEW__")] + [(t["name"], t["name"]) for t in self.templates]
                    yield Select(options, value="__NEW__", id="me-macro-select")
                    
                yield Label("Macro Name")
                yield Input(id="me-name")
                
                yield Label("Description")
                yield Input(id="me-desc")
                
                yield Label("Template Type")
                type_opts = [(k, k) for k in TEMPLATE_CATALOG.keys()]
                yield Select(type_opts, prompt="Select Template...", id="me-type-select")
                
                yield Container(id="me-dynamic-container")
                
                with Horizontal(classes="dialog-buttons", id="me-buttons"):
                    yield Button("Cancel", variant="error", id="cancel-btn")
                    yield Button("Save", variant="success", id="save-btn")

            with Vertical(id="me-right-info"):
                yield Label("Node / Agent Details", classes="info-panel-title")
                yield Static(
                    "[dim]Select an agent or special node in the slots to see its description here.[/dim]",
                    id="me-info-body",
                    classes="info-panel-body"
                )

    @on(Select.Changed, "#me-macro-select")
    def on_macro_select(self, event: Select.Changed) -> None:
        val = str(event.value)
        name_inp = self.query_one("#me-name", Input)
        desc_inp = self.query_one("#me-desc", Input)
        type_sel = self.query_one("#me-type-select", Select)
        
        if val == "__NEW__":
            self.query_one("#me-title", Label).update("Create MacroNode")
            name_inp.value = ""
            desc_inp.value = ""
            type_sel.disabled = False
            type_sel.clear()
            self.query_one("#me-dynamic-container").remove_children()
            self.current_slots.clear()
            self.current_configs.clear()
            return
            
        self.query_one("#me-title", Label).update(f"Edit MacroNode: {val}")
        template = next((t for t in self.templates if t["name"] == val), None)
        if not template:
            return
            
        name_inp.value = template["name"]
        desc_inp.value = template.get("description", "")
        
        tpl_type = template.get("template_type", "")
        if tpl_type:
            type_sel.value = tpl_type
            type_sel.disabled = True
        else:
            type_sel.clear()
            type_sel.disabled = False
        
        self.set_timer(0.1, lambda: self._populate_existing(template))

    @on(Select.Changed, "#me-type-select")
    def on_type_select(self, event: Select.Changed) -> None:
        val = event.value
        container = self.query_one("#me-dynamic-container")
        container.remove_children()
        self.current_slots.clear()
        self.current_configs.clear()
        
        if not val or val == Select.BLANK:
            return
            
        tpl_def = TEMPLATE_CATALOG.get(str(val))
        if not tpl_def:
            return
            
        container.mount(Label(f"Agent Slots for {val}", classes="pane-title"))
        for slot in tpl_def.slots:
            slot_id = f"slot_{slot.name}"
            self.current_slots.append(slot.name)
            lbl = Label(f"{slot.name} ({slot.min_agents}-{slot.max_agents})", classes="me-slot-label")
            if slot.max_agents == 1:
                opts = [(a, a) for a in self.all_agents]
                inp = Select(opts, prompt="Select Agent...", id=slot_id, classes="me-slot-input")
            else:
                inp = Input(placeholder="Comma-separated Agents (e.g. OSINT, MANUAL)", id=slot_id, classes="me-slot-input")
            container.mount(Horizontal(lbl, inp, classes="me-slot-row"))
                
        if tpl_def.config:
            container.mount(Label(f"Configuration for {val}", classes="pane-title"))
            for cfg in tpl_def.config:
                cfg_id = f"cfg_{cfg.name}"
                self.current_configs.append(cfg.name)
                lbl = Label(cfg.name, classes="me-slot-label")
                if cfg.choices:
                    opts = [(c, c) for c in cfg.choices]
                    inp = Select(opts, value=cfg.default, id=cfg_id, classes="me-slot-input")
                else:
                    inp = Input(value=str(cfg.default), id=cfg_id, classes="me-slot-input")
                container.mount(Horizontal(lbl, inp, classes="me-slot-row"))

    def _populate_existing(self, template: dict) -> None:
        tpl_cfg = template.get("template_config") or {}
        agent_mapping = tpl_cfg.get("_agent_mapping") or {}
        
        for s_name in self.current_slots:
            try:
                inp = self.query_one(f"#slot_{s_name}")
                val = agent_mapping.get(s_name, [])
                if isinstance(inp, Select):
                    if val:
                        inp.value = val[0]
                    else:
                        inp.clear()
                elif isinstance(inp, Input):
                    inp.value = ", ".join(val)
            except Exception:
                pass
                
        for c_name in self.current_configs:
            try:
                inp = self.query_one(f"#cfg_{c_name}")
                val = tpl_cfg.get(c_name)
                if val is not None:
                    if isinstance(inp, Select):
                        inp.value = str(val)
                    elif isinstance(inp, Input):
                        inp.value = str(val)
            except Exception:
                pass

    @on(Button.Pressed, "#cancel-btn")
    def cancel(self):
        self.dismiss(None)

    @on(Button.Pressed, "#save-btn")
    def save(self):
        name = self.query_one("#me-name", Input).value.strip()
        desc = self.query_one("#me-desc", Input).value.strip()
        tpl_type = self.query_one("#me-type-select", Select).value
        
        if not name or not tpl_type or tpl_type == Select.BLANK:
            self.app.notify("Name and Template Type are required.", severity="error")
            return
            
        agent_mapping = {}
        for s_name in self.current_slots:
            inp = self.query_one(f"#slot_{s_name}")
            if isinstance(inp, Select):
                val = inp.value
                if val and val != Select.BLANK:
                    agent_mapping[s_name] = [str(val)]
                else:
                    agent_mapping[s_name] = []
            elif isinstance(inp, Input):
                parts = [p.strip() for p in inp.value.split(",") if p.strip()]
                agent_mapping[s_name] = parts
                
        config = {}
        for c_name in self.current_configs:
            inp = self.query_one(f"#cfg_{c_name}")
            if isinstance(inp, Select):
                config[c_name] = str(inp.value)
            elif isinstance(inp, Input):
                config[c_name] = inp.value.strip()
                
        config["_agent_mapping"] = agent_mapping
        
        result = {
            "name": name,
            "description": desc,
            "template_type": str(tpl_type),
            "agent_mapping": agent_mapping,
            "config": config
        }
        self.dismiss(result)

    @on(Select.Changed, ".me-slot-input")
    def on_slot_selection_changed(self, event: Select.Changed) -> None:
        """Show selected Agent's or Special Node's profile in the info panel."""
        from textual.widgets import Static
        body = self.query_one("#me-info-body", Static)
        if not event.value or event.value == Select.BLANK:
            return

        name = str(event.value)
        
        # Check if it's a special node
        special_node = next((sn for sn in self.special_nodes if sn[0] == name), None)
        if special_node:
            info = [
                f"[bold warning]{name}[/bold warning]",
                "",
                "[bold]Description[/bold]",
                str(special_node[1]),
            ]
            body.update("\n".join(info))
            return

        # Otherwise it's an agent
        try:
            from maccre_core.orchestration.roster_loader import load_agent_from_roster
            agent = load_agent_from_roster(name)
            model = agent.get("model", "unknown")
            tools = agent.get("tools_allowed", "none")
            desc = agent.get("description", "")
            instructions = agent.get("system_prompt", "No instructions available.")
            
            info_parts = [
                f"[bold green]{name}[/bold green]",
                f"[dim]Model:[/dim] {model}",
                f"[dim]Tools:[/dim] {tools}",
            ]
            if desc:
                info_parts.append(f"[dim]Description:[/dim] {desc}")
                
            info_parts.append("")
            info_parts.append("[bold]System Instructions[/bold]")
            
            instr_display = str(instructions)
            if len(instr_display) > 1000:
                instr_display = instr_display[:1000] + "\n\n[dim]…truncated…[/dim]"
                
            info_parts.append(instr_display)
            body.update("\n".join(info_parts))
        except Exception as exc:
            body.update(f"[red]Error loading '{name}': {exc}[/red]")

