import json
import uuid
from typing import Any

from textual.screen import ModalScreen
from textual.app import ComposeResult
from textual.containers import Vertical, Horizontal
from textual.widgets import Label, Select, Input, Button, RichLog, Static, TextArea
from textual import on

from maccre_core.orchestration.local_broker import LocalMessageBroker


# ── MacroNode Name Modal ─────────────────────────────────────────────────────

class MacroNodeNameModal(ModalScreen[dict | None]):
    """Small popup to name and describe a MacroNode before saving."""

    DEFAULT_CSS = """
    MacroNodeNameModal {
        align: center middle;
        background: $background 80%;
    }
    #macronode-name-dialog {
        width: 64;
        height: auto;
        max-height: 22;
        background: $surface;
        border: thick $primary;
        padding: 1 2;
    }
    .mn-title {
        text-align: center;
        background: $primary-darken-2;
        color: white;
        padding: 1;
        margin-bottom: 1;
    }
    .mn-field-label {
        margin-top: 1;
    }
    .mn-info {
        margin-top: 1;
        color: $text-muted;
    }
    #mn-desc-area {
        height: 4;
    }
    .mn-buttons {
        margin-top: 1;
        align: center middle;
    }
    """

    def __init__(self, save_mode: str = "configured", source_info: str = "", **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._save_mode = save_mode
        self._source_info = source_info

    def compose(self) -> ComposeResult:
        mode_label = "Configured MacroNode" if self._save_mode == "configured" else "Template MacroNode"
        yield Vertical(
            Label("━━━ Name Your MacroNode ━━━", classes="mn-title"),
            Label("Name:", classes="mn-field-label"),
            Input(placeholder="MacroNode name (required)", id="mn-name-input"),
            Label("Description:", classes="mn-field-label"),
            TextArea(id="mn-desc-area"),
            Label(f"Save Mode:  {mode_label}", classes="mn-info"),
            Label(f"Source: {self._source_info}" if self._source_info else "Source: —", classes="mn-info"),
            Horizontal(
                Button("Cancel", id="mn-cancel", variant="error"),
                Button("Save", id="mn-save", variant="success"),
                classes="mn-buttons",
            ),
            id="macronode-name-dialog",
        )

    @on(Button.Pressed, "#mn-cancel")
    def _cancel(self, event: Button.Pressed) -> None:
        self.dismiss(None)

    @on(Button.Pressed, "#mn-save")
    def _save(self, event: Button.Pressed) -> None:
        name_val = self.query_one("#mn-name-input", Input).value.strip()
        if not name_val:
            self.notify("Name is required.", severity="error")
            return
        desc_val = self.query_one("#mn-desc-area", TextArea).text.strip()
        self.dismiss({
            "name": name_val,
            "description": desc_val,
            "save_mode": self._save_mode,
        })

class SessionManagerModal(ModalScreen[dict | None]):
    """Modal for managing FlowStasis (Paused), Completed sessions, and DeadFlows."""
    
    DEFAULT_CSS = """
    SessionManagerModal {
        align: center middle;
        background: $background 80%;
    }
    #session-manager-dialog {
        width: 90%;
        height: 90%;
        background: $surface;
        border: thick $primary;
        padding: 1 2;
    }
    .panel-title {
        text-align: center;
        background: $primary-darken-2;
        color: white;
        padding: 1;
        margin-bottom: 1;
    }
    #sm-columns {
        height: 1fr;
    }
    .sm-column {
        width: 33%;
        padding: 0 1;
        border-right: solid $primary;
    }
    #deadflow-panel {
        border-right: none;
    }
    #sm-flow-preview-line {
        height: 3;
        margin-top: 1;
        overflow-x: auto;
    }
    .sm-flow-node-btn {
        min-width: 10;
        margin-right: 1;
    }
    #sm-node-config-view {
        height: 1fr;
        border: solid $secondary;
        margin-top: 1;
    }
    .mt-1 { margin-top: 1; }
    """
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.broker = LocalMessageBroker()
        self.sessions = []
        
        self.selected_stasis = None
        self.selected_completed = None
        self.selected_deadflow = None

    def compose(self) -> ComposeResult:
        yield Vertical(
            Label("━━━ Session Manager ━━━", classes="panel-title"),
            Horizontal(
                # Name Session input sits globally across the top
                Input(placeholder="Name Session (Select a FlowStasis or Completed session)...", id="session-name-input", disabled=True),
                Button("Rename Session", id="btn-rename-session", disabled=True, variant="primary"),
                id="name-session-row"
            ),
            Horizontal(
                # LEFT COLUMN: FlowStasis (Paused/Active)
                Vertical(
                    Label("FlowStasis (Active/Paused)", classes="panel-title"),
                    Select([], prompt="Select FlowStasis...", id="stasis-select"),
                    Button("Resume Flow", id="btn-resume-session", variant="success", disabled=True, classes="mt-1"),
                    classes="sm-column", id="stasis-panel"
                ),
                # MIDDLE COLUMN: Completed Sessions
                Vertical(
                    Label("Completed Sessions", classes="panel-title"),
                    Select([], prompt="Select Completed...", id="completed-select"),
                    Horizontal(
                        Button("Canonize", id="btn-canonize-session", variant="warning", disabled=True),
                        Button("Save as MacroNode", id="btn-save-macronode", variant="primary"),
                        Button("Save as Template", id="btn-save-template", variant="primary"),
                        classes="mt-1"
                    ),
                    Static(
                        "[dim]ℹ No completed session selected — buttons will use the current "
                        "Topology Visualizer.[/dim]",
                        id="save-source-hint",
                        classes="save-source-hint",
                    ),
                    classes="sm-column", id="completed-panel"
                ),
                # RIGHT COLUMN: DeadFlows
                Vertical(
                    Label("DeadFlow Registry (Failed)", classes="panel-title"),
                    Select([], prompt="Select a DeadFlow...", id="deadflow-select"),
                    Button("Send to Nexus", id="btn-send-nexus", variant="error", disabled=True, classes="mt-1"),
                    classes="sm-column", id="deadflow-panel"
                ),
                id="sm-columns"
            ),
            Vertical(
                Label("Flow Line Preview (Select any session):", classes="mt-1"),
                Horizontal(id="sm-flow-preview-line"),
                RichLog(id="sm-node-config-view", wrap=True, markup=True),
            ),
            Button("Close", id="btn-close-session-manager", variant="primary", classes="mt-1"),
            id="session-manager-dialog"
        )

    def on_mount(self) -> None:
        self._load_sessions()

    def _load_sessions(self) -> None:
        try:
            self.sessions = self.broker.get_resumable_sessions()
            
            stasis_opts = [(f"{s['job_id']} [{s['status']}]", s['job_id']) for s in self.sessions if s['status'] in ('active', 'paused')]
            comp_opts = [(f"{s['job_id']} [{s['status']}]", s['job_id']) for s in self.sessions if s['status'] in ('completed', 'canonized')]
            dead_opts = [(f"{s['job_id']} [{s['status']}]", s['job_id']) for s in self.sessions if s['status'] in ('failed', 'cancelled')]
            
            self.query_one("#stasis-select", Select).set_options(stasis_opts)
            self.query_one("#completed-select", Select).set_options(comp_opts)
            self.query_one("#deadflow-select", Select).set_options(dead_opts)
        except Exception as e:
            self.query_one("#sm-node-config-view", RichLog).write(f"[red]Error loading sessions: {e}[/red]")

    def _draw_preview(self, job_id: str) -> None:
        if not job_id:
            return
        session = next((s for s in self.sessions if s['job_id'] == job_id), None)
        if not session:
            return
            
        preview_container = self.query_one("#sm-flow-preview-line", Horizontal)
        # Using UUIDs or None as id prevents the duplicate ID bug
        for child in list(preview_container.children):
            child.remove()
            
        try:
            topo_data = json.loads(session.get("topology_csv", "[]"))
            for idx, step in enumerate(topo_data):
                node_name = step.get("macronode", f"Step_{idx}")
                btn = Button(node_name, id=f"preview-node-{uuid.uuid4()}", classes="sm-flow-node-btn")
                btn._step_data = step
                preview_container.mount(btn)
                
            if session.get("status") in ("completed", "canonized"):
                ledger_path = session.get("current_ledger_path")
                if ledger_path:
                    from pathlib import Path
                    if Path(ledger_path).exists():
                        with open(ledger_path, "r", encoding="utf-8") as f:
                            content = f.read()
                        log_view = self.query_one("#sm-node-config-view", RichLog)
                        log_view.clear()
                        log_view.write(f"[bold cyan]Unified Session Ledger ({job_id}):[/bold cyan]\n")
                        log_view.write(content)
        except Exception as e:
            self.query_one("#sm-node-config-view", RichLog).write(f"[red]Error parsing topology for preview: {e}[/red]")

    def _update_naming_state(self, job_id: str | None) -> None:
        name_inp = self.query_one("#session-name-input", Input)
        name_btn = self.query_one("#btn-rename-session", Button)
        if job_id and job_id != Select.BLANK:
            name_inp.disabled = False
            job_str = str(job_id)
            name_inp.value = job_str if not job_str.startswith("job_") else ""
            name_btn.disabled = False
        else:
            name_inp.disabled = True
            name_btn.disabled = True

    @on(Select.Changed, "#stasis-select")
    def on_stasis_selected(self, event: Select.Changed) -> None:
        self.selected_stasis = event.value if event.value != Select.BLANK else None
        self.query_one("#btn-resume-session", Button).disabled = not bool(self.selected_stasis)
        if self.selected_stasis:
            self.query_one("#completed-select", Select).clear()
            self.query_one("#deadflow-select", Select).clear()
            self._update_naming_state(self.selected_stasis)
            self._draw_preview(self.selected_stasis)

    @on(Select.Changed, "#completed-select")
    def on_completed_selected(self, event: Select.Changed) -> None:
        val = event.value if event.value != Select.BLANK else None
        self.selected_completed = val
        is_named = bool(val) and not str(val).startswith("job_")
        self.query_one("#btn-canonize-session", Button).disabled = not is_named

        # Update the save-source hint
        hint = self.query_one("#save-source-hint", Static)
        if val:
            hint.update(f"[dim]ℹ Source: completed session '{val}'[/dim]")
        else:
            hint.update(
                "[dim]ℹ No completed session selected — buttons will use the current "
                "Topology Visualizer.[/dim]"
            )

        if val:
            self.query_one("#stasis-select", Select).clear()
            self.query_one("#deadflow-select", Select).clear()
            self._update_naming_state(val)
            self._draw_preview(val)

    @on(Select.Changed, "#deadflow-select")
    def on_deadflow_selected(self, event: Select.Changed) -> None:
        self.selected_deadflow = event.value if event.value != Select.BLANK else None
        self.query_one("#btn-send-nexus", Button).disabled = not bool(self.selected_deadflow)
        if self.selected_deadflow:
            self.query_one("#stasis-select", Select).clear()
            self.query_one("#completed-select", Select).clear()
            self._update_naming_state(None) # Disable naming for DeadFlows
            self._draw_preview(self.selected_deadflow)

    @on(Button.Pressed, ".sm-flow-node-btn")
    def on_preview_node_clicked(self, event: Button.Pressed) -> None:
        log = self.query_one("#sm-node-config-view", RichLog)
        log.clear()
        step_data = getattr(event.button, "_step_data", {})
        log.write(f"[b]Node Configuration:[/b]\n{json.dumps(step_data, indent=2)}")

    @on(Input.Changed, "#session-name-input")
    def on_name_changed(self, event: Input.Changed) -> None:
        val = event.value.strip()
        is_named = val and not val.startswith("job_")
        if self.selected_completed:
            self.query_one("#btn-canonize-session", Button).disabled = not is_named

    @on(Button.Pressed, "#btn-rename-session")
    def on_rename_session(self, event: Button.Pressed) -> None:
        active_id = self.selected_stasis or self.selected_completed
        if not active_id:
            return
        new_name = self.query_one("#session-name-input", Input).value.strip()
        if not new_name or new_name == active_id:
            return
        try:
            self.broker.rename_session(active_id, new_name)
            self.notify(f"Session renamed to {new_name}")
            self._load_sessions()
            
            # Select the newly named session in the correct dropdown
            session = next((s for s in self.sessions if s['job_id'] == new_name), None)
            if session:
                if session['status'] in ('active', 'paused'):
                    self.query_one("#stasis-select", Select).value = new_name
                elif session['status'] in ('completed', 'canonized'):
                    self.query_one("#completed-select", Select).value = new_name
        except Exception as e:
            self.notify(f"Rename failed: {e}", severity="error")

    @on(Button.Pressed, "#btn-send-nexus")
    def on_send_nexus(self, event: Button.Pressed) -> None:
        if self.selected_deadflow:
            self.dismiss({"action": "nexus_deadflow", "job_id": self.selected_deadflow})

    @on(Button.Pressed, "#btn-resume-session")
    def on_resume(self, event: Button.Pressed) -> None:
        if self.selected_stasis:
            self.dismiss({"action": "resume", "job_id": self.selected_stasis})

    @on(Button.Pressed, "#btn-canonize-session")
    def on_canonize(self, event: Button.Pressed) -> None:
        if self.selected_completed:
            new_name = self.query_one("#session-name-input", Input).value.strip()
            job_to_canonize = self.selected_completed
            if new_name and new_name != self.selected_completed and not new_name.startswith("job_"):
                try:
                    self.broker.rename_session(self.selected_completed, new_name)
                    job_to_canonize = new_name
                except Exception as e:
                    self.notify(f"Rename failed before canonizing: {e}", severity="error")
                    return
            self.dismiss({"action": "canonize", "job_id": job_to_canonize})

    @on(Button.Pressed, "#btn-save-macronode")
    def on_save_macronode(self, event: Button.Pressed) -> None:
        """Save topology as a fully configured MacroNode."""
        self._save_as_macro(save_mode="configured")

    @on(Button.Pressed, "#btn-save-template")
    def on_save_template(self, event: Button.Pressed) -> None:
        """Save topology as a MacroNode template with empty slots."""
        self._save_as_macro(save_mode="template")

    def _save_as_macro(self, save_mode: str) -> None:
        """Common handler for both save buttons — pushes MacroNodeNameModal."""
        source_info = ""
        if self.selected_completed:
            source_info = f"Completed session: {self.selected_completed}"
        else:
            source_info = "Current Topology Visualizer"

        def handle_name_result(result: dict | None) -> None:
            if result is None:
                return
            job_id = self.selected_completed or "__topology_visualizer__"
            self.dismiss({
                "action": "save_as_macronode",
                "job_id": job_id,
                "template_name": result["name"],
                "template_description": result.get("description", ""),
                "save_mode": result["save_mode"],
            })

        self.app.push_screen(
            MacroNodeNameModal(save_mode=save_mode, source_info=source_info),
            handle_name_result,
        )

    @on(Button.Pressed, "#btn-close-session-manager")
    def on_close(self, event: Button.Pressed) -> None:
        self.dismiss(None)
