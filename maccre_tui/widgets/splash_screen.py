from textual import work, on
from textual.app import ComposeResult
from textual.containers import Container, Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Label, Button, ProgressBar, Static, Input, Select
import asyncio
import itertools

from maccre_core.utils.path_resolver import get_maccre_root
from maccre_core.finops._finop_daemon_ import get_finop_daemon

LOADING_QUOTES = [
    "Hiring HR Agents...",
    "Ordering Office Furniture...",
    "Talking Gretchen Harwell down from the roof....",
    "Writing dissertation on probabalistic determinism...",
    "Preparing Exo-Cortex for implantation...",
    "Preparing Exo_Cortex for implementation....",
    "Polling the past into todays truth...",
    "Fabricating Context Window Frames...",
    "Diverting Flow...",
    "Condensing Probability Clouds...",
    "Have you heard the hit George Strait song, 'All my Ex'es live in Context Caches'...?"
]

class BootSplashModal(ModalScreen[str]):
    """Splash screen forcing the user to create or select a project."""
    
    def compose(self) -> ComposeResult:
        with Container(classes="dialog", id="boot-splash-dialog"):
            yield Label("[bold cyan]Welcome to MACCREv2[/bold cyan]", id="boot-title")
            yield Label("Please select or create a project to begin:", id="boot-subtitle")
            
            # Select existing project
            from pathlib import Path
            root_dir = Path(__file__).parent.parent.parent.resolve()
            datacenter = root_dir / "__DATACENTER"
            projects = []
            if datacenter.exists() and datacenter.is_dir():
                for folder in datacenter.iterdir():
                    if folder.is_dir():
                        tiers = [
                            "01_Raw_Source", "02_Dynamic_Context", "03_Agent_Ledgers",
                            "04_Code_Artifacts", "05_Rendered_Media"
                        ]
                        if all((folder / tier).exists() for tier in tiers):
                            projects.append((folder.name, folder.name))
                            
            with Vertical(classes="boot-section"):
                yield Label("Existing Projects:")
                yield Select(projects, id="boot-project-select")
                yield Button("Load Selected Project", variant="primary", id="boot-load-btn")
            
            with Vertical(classes="boot-section"):
                yield Label("Or Create New Project:")
                yield Input(placeholder="New Project Name", id="boot-new-project-input")
                yield Button("Create Project", variant="success", id="boot-create-btn")

    @on(Button.Pressed, "#boot-load-btn")
    def load_project(self):
        sel = self.query_one("#boot-project-select", Select)
        if sel.value and sel.value != Select.BLANK:
            self.dismiss(str(sel.value))

    @on(Button.Pressed, "#boot-create-btn")
    def create_project(self):
        val = self.query_one("#boot-new-project-input", Input).value.strip()
        if val:
            proj_dir = get_maccre_root() / "__DATACENTER" / val
            proj_dir.mkdir(parents=True, exist_ok=True)
            for tier in ["01_Raw_Source", "02_Dynamic_Context", "03_Agent_Ledgers", "04_Code_Artifacts", "05_Rendered_Media"]:
                (proj_dir / tier).mkdir(exist_ok=True)
            self.dismiss(val)

class LoadingSplashModal(ModalScreen[None]):
    """Animated loading screen that runs AUA Interrupts."""
    
    def __init__(self, project_name: str):
        super().__init__()
        self.project_name = project_name
        import random
        shuffled_quotes = list(LOADING_QUOTES)
        random.shuffle(shuffled_quotes)
        self._quotes_iter = itertools.cycle(shuffled_quotes)
    def compose(self) -> ComposeResult:
        with Container(classes="dialog", id="loading-splash-dialog"):
            yield Label(f"[bold cyan]Initializing Project: {self.project_name}[/bold cyan]")
            yield Static(next(self._quotes_iter), id="loading-quote")
            yield ProgressBar(total=100, show_eta=False, id="loading-progress")

    def on_mount(self) -> None:
        self.run_startup_tasks()

    @work(exclusive=True, thread=True)
    def run_startup_tasks(self) -> None:
        import time
        # Start progress bar updater in textual event loop
        self.app.call_from_thread(self._start_progress_updates)
        
        # 1. Run FinOps AUA polling
        daemon = get_finop_daemon()
        daemon.refresh_project_health_metrics(self.project_name)
        
        # Artificial delay to let the user enjoy the splash screen quotes
        time.sleep(5.0)
        
        # Finish progress
        self.app.call_from_thread(self._finish_loading)

    def _start_progress_updates(self):
        self.set_interval(0.5, self._tick_progress)
        self.set_interval(3.0, self._tick_quote)

    def _tick_progress(self):
        pb = self.query_one("#loading-progress", ProgressBar)
        if pb.progress < 95:
            pb.advance(5)

    def _tick_quote(self):
        q = self.query_one("#loading-quote", Static)
        q.update(next(self._quotes_iter))

    def _finish_loading(self):
        pb = self.query_one("#loading-progress", ProgressBar)
        pb.progress = 100
        self.dismiss(None)
