from textual.screen import ModalScreen
from textual.app import ComposeResult
from textual.containers import Vertical, Horizontal
from textual.widgets import Label, Select, Input, Button, RichLog, OptionList
from textual.widgets.option_list import Option
from textual import on
from typing import List, Dict, Any

from maccre_core.orchestration.memory_engine import CognitiveMemoryEngine
from maccre_core.utils.path_resolver import get_datacenter_path

class ProjectCanonModal(ModalScreen[None]):
    """Modal for managing Project Canon & Memory (Sovereign Pin Store)."""
    
    DEFAULT_CSS = """
    ProjectCanonModal {
        align: center middle;
        background: $background 80%;
    }
    #canon-dialog {
        width: 90%;
        height: 90%;
        background: $surface;
        border: thick $primary;
        padding: 1;
    }
    .panel-title {
        text-align: center;
        background: $primary-darken-2;
        color: white;
        padding: 1;
        margin-bottom: 1;
    }
    #canon-columns {
        height: 1fr;
    }
    #canon-left-pane {
        width: 40%;
        border-right: solid $primary;
        padding-right: 1;
    }
    #canon-right-pane {
        width: 60%;
        padding-left: 1;
    }
    #pin-list {
        height: 1fr;
        border: solid $secondary;
        margin-top: 1;
    }
    #ledger-view {
        height: 1fr;
        border: solid $secondary;
    }
    .mt-1 { margin-top: 1; }
    """
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.mem_engine = CognitiveMemoryEngine()
        self.jobs = []
        self.active_job_id = None
        self.active_pins = []

    def compose(self) -> ComposeResult:
        yield Vertical(
            Label("━━━ Project Canon & Memory ━━━", classes="panel-title"),
            Horizontal(
                Vertical(
                    Label("Session Memories"),
                    Select([], prompt="Select Session...", id="canon-session-select"),
                    Label("Memory Pins:", classes="mt-1"),
                    OptionList(id="pin-list"),
                    Horizontal(
                        Button("Add Pin", id="btn-add-pin", variant="success", disabled=True),
                        Button("Delete Pin", id="btn-delete-pin", variant="error", disabled=True),
                        classes="mt-1"
                    ),
                    id="canon-left-pane"
                ),
                Vertical(
                    Label("Unified Session Ledger"),
                    RichLog(id="ledger-view", markup=True, highlight=True, wrap=True),
                    id="canon-right-pane"
                ),
                id="canon-columns"
            ),
            Button("Close", id="btn-close-canon", variant="primary", classes="mt-1"),
            id="canon-dialog"
        )

    def on_mount(self) -> None:
        self._load_jobs()

    def _load_jobs(self) -> None:
        try:
            self.jobs = self.mem_engine.store.get_all_jobs()
            opts = [(j, j) for j in self.jobs]
            self.query_one("#canon-session-select", Select).set_options(opts)
        except Exception as e:
            self.query_one("#ledger-view", RichLog).write(f"[red]Error loading memory store: {e}[/red]")

    @on(Select.Changed, "#canon-session-select")
    def on_session_selected(self, event: Select.Changed) -> None:
        job_id = event.value
        self.active_job_id = job_id
        
        pin_list = self.query_one("#pin-list", OptionList)
        pin_list.clear_options()
        self.query_one("#btn-add-pin", Button).disabled = not bool(job_id)
        
        ledger_view = self.query_one("#ledger-view", RichLog)
        ledger_view.clear()
        
        if not job_id:
            return
            
        try:
            self.active_pins = self.mem_engine.store.get_pins_by_job(job_id)
            for idx, p in enumerate(self.active_pins):
                pin_list.add_option(Option(f"{p['subject']} -> {p['predicate']} -> {p['object']}", id=str(idx)))
            
            # Load the unified ledger text
            ledger_path = get_datacenter_path("04_Code_Artifacts", job_id, "unified_session_ledger.md")
            if ledger_path.exists():
                text = ledger_path.read_text(encoding="utf-8")
                ledger_view.write(text)
            else:
                ledger_view.write(f"[dim]No unified ledger found at {ledger_path}[/dim]")
        except Exception as e:
            ledger_view.write(f"[red]Error loading data: {e}[/red]")

    @on(OptionList.OptionSelected, "#pin-list")
    def on_pin_selected(self, event: OptionList.OptionSelected) -> None:
        self.query_one("#btn-delete-pin", Button).disabled = False

    @on(Button.Pressed, "#btn-delete-pin")
    def delete_pin(self, event: Button.Pressed) -> None:
        pin_list = self.query_one("#pin-list", OptionList)
        idx = pin_list.highlighted
        if idx is not None and 0 <= idx < len(self.active_pins):
            pin_id = self.active_pins[idx]['id']
            try:
                self.mem_engine.store.delete_pin(pin_id)
                self.notify("Pin deleted.")
                # Refresh pins
                self.on_session_selected(Select.Changed(self.query_one("#canon-session-select", Select), self.active_job_id))
            except Exception as e:
                self.notify(f"Delete failed: {e}", severity="error")

    @on(Button.Pressed, "#btn-add-pin")
    def add_pin(self, event: Button.Pressed) -> None:
        if self.active_job_id:
            # For simplicity, we just inject a template pin into the DB. 
            # In a full UI we'd pop another form modal, but appending a default is quick.
            ledger_path = str(get_datacenter_path("04_Code_Artifacts", self.active_job_id, "unified_session_ledger.md"))
            try:
                self.mem_engine.store.add_pin(
                    job_id=self.active_job_id,
                    ledger_path=ledger_path,
                    subject="New Subject",
                    predicate="connects to",
                    obj="New Object",
                    significance="Added manually via UI."
                )
                self.notify("New pin added (edit manually in DB or via UI).")
                self.on_session_selected(Select.Changed(self.query_one("#canon-session-select", Select), self.active_job_id))
            except Exception as e:
                self.notify(f"Add failed: {e}", severity="error")

    @on(Button.Pressed, "#btn-close-canon")
    def on_close(self, event: Button.Pressed) -> None:
        self.dismiss(None)
