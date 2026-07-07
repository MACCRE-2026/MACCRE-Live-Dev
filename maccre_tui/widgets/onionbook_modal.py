from textual import on
from textual.app import ComposeResult
from textual.containers import Container, Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Label, Button, DataTable, Static

from maccre_core.finops._finop_daemon_ import get_finop_daemon

class FinOpsBuddy(Static):
    """Micro-reporting widget tracking total costs."""
    
    def on_mount(self) -> None:
        self.set_interval(10.0, self.update_cost)
        self.update_cost()

    def update_cost(self) -> None:
        try:
            daemon = get_finop_daemon()
            project_name = getattr(self.app, "active_project", None)
            
            if project_name and project_name != "GLOBAL":
                total = daemon.ledger.get_aggregated_costs(project_name=project_name)
                self.update(f"[bold green]FinOpsBuddy:[/bold green] Project Cost: ${total:.4f}")
            else:
                self.update("[bold green]FinOpsBuddy:[/bold green] Waiting for project...")
        except Exception:
            self.update("[bold red]FinOpsBuddy:[/bold red] Error fetching costs")


class OnionBookModal(ModalScreen[None]):
    """Checkbook UI tracking project expenditures and health ratios."""
    
    def __init__(self, project_name: str):
        super().__init__()
        self.project_name = project_name
        self.daemon = get_finop_daemon()

    def compose(self) -> ComposeResult:
        with Container(classes="dialog onionbook-dialog", id="onionbook-modal"):
            yield Label(f"[bold cyan]OnionBook - {self.project_name}[/bold cyan]", classes="pane-title")
            
            # Health Metrics Bar
            with Horizontal(id="health-metrics-bar"):
                yield Static("Loading metrics...", id="health-metrics-text")
                yield Button("Refresh", id="btn-refresh-onionbook", variant="primary")
            
            # Ledger Data Grid
            yield DataTable(id="ledger-table")
            
            # Footer Totals
            yield Static("Total Cost: $0.00", id="ledger-total")
            
            with Horizontal(classes="dialog-buttons"):
                yield Button("Close", variant="error", id="btn-close-onionbook")

    def on_mount(self) -> None:
        self.refresh_data()

    def refresh_data(self) -> None:
        # Update metrics
        metrics = self.daemon.ledger.get_health_metrics(self.project_name)
        if metrics:
            fail_rate = metrics.get('fail_rate', 0.0) * 100
            canon_ratio = metrics.get('canonization_ratio', 0.0) * 100
            size_ratio = metrics.get('size_ratio_04_05', 0.0)
            
            text = f"Fail Rate: {fail_rate:.1f}% | Canonized: {canon_ratio:.1f}% | Storage Ratio (04/05): {size_ratio:.2f}"
            self.query_one("#health-metrics-text", Static).update(text)
        
        # Populate Data Table
        table = self.query_one("#ledger-table", DataTable)
        table.clear(columns=True)
        table.add_columns("Timestamp", "Session ID", "Node Type", "Agent", "Tool", "Cost ($)", "Status")
        
        entries = self.daemon.ledger.get_ledger_entries({"project_name": self.project_name})
        
        total_cost = 0.0
        for e in entries:
            table.add_row(
                e["timestamp"],
                e["session_id"],
                e["node_type"],
                e.get("agent_name", "N/A"),
                e.get("tool_name", "N/A"),
                f"${e['cost_usd']:.4f}",
                e.get("canonization_status", "uncanonized")
            )
            total_cost += e["cost_usd"]
            
        self.query_one("#ledger-total", Static).update(f"[bold]Total Cost for Filtered Subset:[/bold] ${total_cost:.4f}")

    @on(Button.Pressed, "#btn-refresh-onionbook")
    def on_refresh(self):
        # AUA Interrupt trigger
        self.daemon.refresh_project_health_metrics(self.project_name)
        self.refresh_data()

    @on(Button.Pressed, "#btn-close-onionbook")
    def on_close(self):
        self.dismiss(None)
