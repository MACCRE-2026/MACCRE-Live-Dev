import re

with open('B:\\EXO_GANS\\maccre_tui\\nexus_plex.py', 'r', encoding='utf-8') as f:
    content = f.read()

# 1. Replace FlowExecutionPanel compose
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
                    yield Button("Add MacroNode", variant="primary", id="btn-add-macro", classes="flow-add-btn")
                with Vertical(classes="flow-select-group"):
                    yield Label("Agent")
                    yield Select([], prompt="Select Agent…", id="agent-select")
                    yield Button("Add Agent", variant="success", id="btn-add-agent", classes="flow-add-btn")
                with Vertical(classes="flow-select-group"):
                    yield Label("Special Node")
                    yield Select([], prompt="Select Special Node…", id="special-select")
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


# 2. Add event handlers for the new buttons to NexusPlex
NEW_EVENT_HANDLERS = """
    # ── Inline Flow Editor Handlers ───────────────────────────────────────────
    @on(Button.Pressed, "#btn-add-macro")
    def add_macro_to_flow(self) -> None:
        sel = self.query_one("#macro-select", Select)
        if not sel.value or sel.value == Select.BLANK:
            return
        name = str(sel.value)
        mapping = {}
        # Try to resolve agents if agent_select is populated
        agent_sel = self.query_one("#agent-select", Select)
        if agent_sel.value and agent_sel.value != Select.BLANK:
            selected_agent = str(agent_sel.value)
            try:
                from maccre_core.macronode_registry import get_macronode_store
                store = get_macronode_store()
                macro_def = store.load(name)
                slots = macro_def.get("agent_slots", [])
                for slot in slots:
                    mapping[slot] = selected_agent
            except Exception:
                pass

        from maccre_core.orchestration.flow_engine import FlowStep
        step = FlowStep(macronode_name=name, agent_mapping=mapping)
        self.active_flow_steps.append(step)
        self._refresh_active_flow_sequence()

    @on(Button.Pressed, "#btn-add-agent")
    def add_agent_to_flow(self) -> None:
        sel = self.query_one("#agent-select", Select)
        if not sel.value or sel.value == Select.BLANK:
            return
        name = str(sel.value)
        from maccre_core.orchestration.flow_engine import FlowStep
        step = FlowStep(macronode_name=name)
        self.active_flow_steps.append(step)
        self._refresh_active_flow_sequence()

    @on(Button.Pressed, "#btn-add-special")
    def add_special_to_flow(self) -> None:
        sel = self.query_one("#special-select", Select)
        if not sel.value or sel.value == Select.BLANK:
            return
        name = str(sel.value)
        from maccre_core.orchestration.flow_engine import FlowStep
        step = FlowStep(macronode_name=name)
        self.active_flow_steps.append(step)
        self._refresh_active_flow_sequence()

    @on(Button.Pressed, "#btn-remove-last")
    def remove_last_node(self) -> None:
        if self.active_flow_steps:
            self.active_flow_steps.pop()
            self._refresh_active_flow_sequence()

    @on(Button.Pressed, "#btn-clear-flow")
    def clear_flow_sequence(self) -> None:
        self.active_flow_steps.clear()
        self._refresh_active_flow_sequence()
"""

# Insert these handlers into NexusPlex class. I'll put them right before `def _refresh_active_flow_sequence`
idx = content.find("def _refresh_active_flow_sequence")
if idx != -1:
    content = content[:idx] + NEW_EVENT_HANDLERS + "\n    " + content[idx:]
else:
    print("WARNING: Could not find _refresh_active_flow_sequence")

# 3. Update `_refresh_active_flow_sequence` to use UUIDs
old_btn_create = 'btn = Button(name, id=f"anode-{i}", classes="active-node-btn")'
new_btn_create = 'import uuid\n            btn = Button(name, id=f"anode-{i}-{uuid.uuid4().hex[:8]}", classes="active-node-btn")'
content = content.replace(old_btn_create, new_btn_create)

# 4. Update index extraction
old_idx_extract = 'idx = int(event.button.id.replace("anode-", ""))'
new_idx_extract = 'idx = int(event.button.id.split("-")[1])'
content = content.replace(old_idx_extract, new_idx_extract)

# 5. Populate dropdowns in NexusPlex.on_mount or similar
# We can just hook into `def _populate_initial_state(self)` or `def _refresh_state(self)` which NexusPlex probably has.
# Actually, I'll add a call in `def on_mount` or wherever `roster` is loaded.
# Let's search for where it loads `list_projects`.
populate_code = """
        # Populate inline flow editor selects
        try:
            from maccre_core.macronode_registry import get_macronode_store
            from maccre_core.orchestration.roster_loader import load_agent_names_from_library
            store = get_macronode_store()
            macros = store.list_all()
            macro_sel = self.query_one("#macro-select", Select)
            if macro_sel:
                macro_sel.set_options([(m, m) for m in macros])
            
            agents = load_agent_names_from_library(self.active_project)
            agent_sel = self.query_one("#agent-select", Select)
            if agent_sel:
                agent_sel.set_options([(a, a) for a in agents])
                
            special = ["MANUAL", "DET_ANCHOR", "DET_RECURSION", "DET_PAUSE", "DET_GATE", "DET_CHECKPOINT", "DET_DELAY", "DET_TRANSFORM"]
            special_sel = self.query_one("#special-select", Select)
            if special_sel:
                special_sel.set_options([(s, s) for s in special])
        except Exception:
            pass
"""

# Inject after `roster = load_agent_names_from_library(self.active_project)` in `on_mount`
om_idx = content.find("roster = load_agent_names_from_library")
if om_idx != -1:
    content = content[:om_idx] + populate_code + "\n        " + content[om_idx:]


with open('B:\\EXO_GANS\\maccre_tui\\nexus_plex.py', 'w', encoding='utf-8') as f:
    f.write(content)

print("Migration patched successfully")
