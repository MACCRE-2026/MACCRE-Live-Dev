import re

with open('B:\\EXO_GANS\\maccre_tui\\nexus_plex.py', 'r', encoding='utf-8') as f:
    content = f.read()

NEW_EXEC_PANEL_TOP = """class FlowExecutionPanel(Vertical):
    def compose(self) -> ComposeResult:
        # Flow Execution Top Panel
        with Vertical(classes="panel-section", id="flow-execution-top"):
            yield Label("Flow Execution", classes="pane-title")
            with Horizontal(classes="flow-controls"):
                yield Button("Launch Flow", variant="success", id="btn-launch-flow")
                yield Button("Stop Flow", variant="error", id="btn-stop-flow", disabled=True)
                yield Button("Resume Flow", variant="success", id="btn-resume-flow", disabled=True)
                yield Button("Rewind Flow", variant="warning", id="btn-rewind-flow", disabled=False)
                yield Button("Create Payload", variant="primary", id="btn-create-payload")

            with Horizontal(id="flow-select-row"):
                with Vertical(classes="flow-select-group"):
                    yield Label("MacroNode")
                    yield Select([], prompt="Select MacroNode…", id="macro-select")
                    with Vertical(id="flow-macro-info", classes="info-panel-container"):
                        yield Label("MacroNode Details", classes="info-panel-title")
                        yield Static("[dim]Select a MacroNode above to see its description.[/dim]", id="macro-info-body", classes="info-panel-body")
                    yield Button("Add MacroNode", variant="primary", id="btn-add-macro", classes="flow-add-btn")
                with Vertical(classes="flow-select-group"):
                    yield Label("Agent")
                    yield Select([], prompt="Select Agent…", id="agent-select")
                    with Vertical(id="flow-agent-info", classes="info-panel-container"):
                        yield Label("Agent Details", classes="info-panel-title")
                        yield Static("[dim]Select an Agent above to see its profile.[/dim]", id="agent-info-body", classes="info-panel-body")
                    yield Button("Add Agent", variant="success", id="btn-add-agent", classes="flow-add-btn")
                with Vertical(classes="flow-select-group"):
                    yield Label("Special Node")
                    yield Select([], prompt="Select Special Node…", id="special-select")
                    with Vertical(id="flow-special-info", classes="info-panel-container"):
                        yield Label("Special Details", classes="info-panel-title")
                        yield Static("[dim]Select a Special Node above to see its description.[/dim]", id="special-info-body", classes="info-panel-body")
                    yield Button("Add Special", variant="warning", id="btn-add-special", classes="flow-add-btn")

            yield Label("Active Flow Sequence")
            with Horizontal(id="active-flow-sequence", classes="flow-controls"):
                yield Static("No flow loaded.", classes="flow-seq-text")
                
            with Horizontal(classes="flow-controls", id="flow-line-actions"):
                yield Button("Remove Last Node", variant="warning", id="btn-remove-last")
                yield Button("Clear Flow", variant="error", id="btn-clear-flow")

        # Flow Monitor Panel"""

old_exec_panel_top_re = re.compile(
    r'class FlowExecutionPanel\(Vertical\):\s*def compose\(self\) -> ComposeResult:\s*# Flow Execution Top Panel.*?# Flow Monitor Panel',
    re.DOTALL
)

if old_exec_panel_top_re.search(content):
    content = old_exec_panel_top_re.sub(NEW_EXEC_PANEL_TOP, content)
else:
    print("WARNING: Could not find FlowExecutionPanel top to replace.")


EVENT_HANDLERS = """
    @on(Select.Changed, "#macro-select")
    def macro_selection_changed(self, event: Select.Changed) -> None:
        body = self.query_one("#macro-info-body", Static)
        if not event.value or event.value == Select.BLANK:
            body.update("[dim]Select a MacroNode above to see its description.[/dim]")
            return
        name = str(event.value)
        try:
            from maccre_core.macronode_registry import get_macronode_store
            store = get_macronode_store()
            template = store.load(name)
            desc = template.get("description", "No description available.")
            slots = template.get("agent_slots", [])
            topo_rows = template.get("topology_rows", [])
            
            info_parts = [
                f"[bold cyan]{name}[/bold cyan]",
                "",
                "[bold]Description[/bold]",
                str(desc)
            ]
            if slots:
                info_parts.append("")
                info_parts.append(f"[bold]Agents[/bold]: {', '.join(slots)}")
            if topo_rows:
                info_parts.append("")
                info_parts.append(f"[bold]Topology Nodes[/bold] ({len(topo_rows)})")
                for row in topo_rows:
                    info_parts.append(f"  • {row.get('Node_ID', '?')}: {row.get('Agent_Name', '?')}")
            body.update("\\n".join(info_parts))
        except Exception as e:
            body.update(f"[red]Error loading MacroNode: {e}[/red]")

    @on(Select.Changed, "#agent-select")
    def agent_selection_changed(self, event: Select.Changed) -> None:
        body = self.query_one("#agent-info-body", Static)
        if not event.value or event.value == Select.BLANK:
            body.update("[dim]Select an Agent above to see its profile.[/dim]")
            return
        name = str(event.value)
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
                f"[dim]Tools:[/dim] {tools}"
            ]
            if desc:
                info_parts.append(f"[dim]Description:[/dim] {desc}")
            info_parts.append("")
            info_parts.append("[bold]System Instructions[/bold]")
            instr_display = str(instructions)
            if len(instr_display) > 1000:
                instr_display = instr_display[:1000] + "\\n\\n[dim]…truncated…[/dim]"
            info_parts.append(instr_display)
            body.update("\\n".join(info_parts))
        except Exception as e:
            body.update(f"[red]Error loading agent: {e}[/red]")

    @on(Select.Changed, "#special-select")
    def special_selection_changed(self, event: Select.Changed) -> None:
        body = self.query_one("#special-info-body", Static)
        if not event.value or event.value == Select.BLANK:
            body.update("[dim]Select a Special Node above to see its description.[/dim]")
            return
        name = str(event.value)
        
        special_nodes = {
            "MANUAL": "Live swarm intercept — pauses the task in awaiting_orders for manual resume.",
            "DET_ANCHOR": "Entry marker — passes payload through unchanged.",
            "DET_RECURSION": "Loop-back control with counter tracking.",
            "DET_PAUSE": "Halts execution, sets task to paused for manual resume.",
            "DET_GATE": "Conditional gate — blocks unless prerequisite nodes complete.",
            "DET_CHECKPOINT": "Snapshots current payload to a checkpoint file.",
            "DET_DELAY": "Sleeps for a configurable number of seconds.",
            "DET_TRANSFORM": "Applies a static text wrapper/template to the payload."
        }
        
        desc = special_nodes.get(name, "No description available.")
        info = [
            f"[bold warning]{name}[/bold warning]",
            "",
            "[bold]Description[/bold]",
            str(desc)
        ]
        body.update("\\n".join(info))
"""

idx = content.find("def add_macro_to_flow(self) -> None:")
if idx != -1:
    idx2 = content.rfind("@on", 0, idx)
    content = content[:idx2] + EVENT_HANDLERS + "\n    " + content[idx2:]
else:
    print("WARNING: Could not find add_macro_to_flow")

with open('B:\\EXO_GANS\\maccre_tui\\nexus_plex.py', 'w', encoding='utf-8') as f:
    f.write(content)

print("Patch part 2 done.")
