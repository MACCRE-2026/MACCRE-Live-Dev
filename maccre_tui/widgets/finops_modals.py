from textual import on
from textual.app import ComposeResult
from textual.containers import Container, Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Label, Button, Static

class BudgetProposalModal(ModalScreen[bool]):
    """Modal displaying the initial budget proposal and topology overhead."""
    
    def __init__(self, node_count: int, estimated_cost: float):
        super().__init__()
        self.node_count = node_count
        self.estimated_cost = estimated_cost

    def compose(self) -> ComposeResult:
        with Container(classes="dialog", id="budget-proposal-dialog"):
            yield Label("[bold cyan]CTRL_REVIEW: Budget Proposal[/bold cyan]", classes="pane-title")
            
            with Vertical(id="budget-details"):
                yield Static(f"The queued topology contains [bold yellow]{self.node_count}[/bold yellow] nodes.")
                yield Static(f"Based on historical metrics, the projected API cost is: [bold red]${self.estimated_cost:.4f}[/bold red]")
                
            yield Label("Do you approve this budget proposal?")
            
            with Horizontal(classes="dialog-buttons"):
                yield Button("Reject", variant="error", id="btn-reject")
                yield Button("Approve", variant="success", id="btn-approve")

    @on(Button.Pressed, "#btn-reject")
    def on_reject(self):
        self.dismiss(False)

    @on(Button.Pressed, "#btn-approve")
    def on_approve(self):
        self.dismiss(True)


class BudgetWarningModal(ModalScreen[bool]):
    """Secondary warning modal for final confirmation."""
    
    def __init__(self, estimated_cost: float):
        super().__init__()
        self.estimated_cost = estimated_cost

    def compose(self) -> ComposeResult:
        with Container(classes="dialog", id="budget-warning-dialog"):
            yield Label("[bold red]WARNING: FINANCIAL COMMITMENT[/bold red]", classes="pane-title")
            
            yield Static(f"By proceeding, you are authorizing up to [bold yellow]${self.estimated_cost:.4f}[/bold yellow] in API token consumption.")
            yield Static("This action will commit funds against your configured provider budgets.")
            
            yield Label("Are you absolutely certain you wish to proceed?")
            
            with Horizontal(classes="dialog-buttons"):
                yield Button("Cancel Execution", variant="primary", id="btn-cancel")
                yield Button("CONFIRM & EXECUTE", variant="error", id="btn-confirm")

    @on(Button.Pressed, "#btn-cancel")
    def on_cancel(self):
        self.dismiss(False)

    @on(Button.Pressed, "#btn-confirm")
    def on_confirm(self):
        self.dismiss(True)
