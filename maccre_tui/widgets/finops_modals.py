from textual import on
from textual.app import ComposeResult
from textual.containers import Container, Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Label, Button, Static

class BudgetProposalModal(ModalScreen[bool]):
    """Modal displaying the initial budget proposal and topology overhead."""
    
    def __init__(self, node_count: int, estimated_cost: float | None):
        super().__init__()
        self.node_count = node_count
        #: ``None`` means pre-flight produced no figure. Rendered as absent rather than
        #: as ``$0.0000``, which would be a number where there is none.
        self.estimated_cost = estimated_cost

    def compose(self) -> ComposeResult:
        with Container(classes="dialog", id="budget-proposal-dialog"):
            yield Label("[bold cyan]CTRL_REVIEW: Budget Proposal[/bold cyan]", classes="pane-title")

            with Vertical(id="budget-details"):
                yield Static(f"The queued topology contains [bold yellow]{self.node_count}[/bold yellow] nodes.")
                # This line used to attribute the figure to historical metrics. None were
                # consulted then and none are consulted now — it is arithmetic over
                # declared models. Saying which it is costs one line and stops the dialog
                # asserting an empirical basis it does not have. The exact former wording
                # is not quoted here, because a test forbids that phrase appearing in this
                # file at all and a historical note is not worth weakening it for.
                if self.estimated_cost is None:
                    yield Static(
                        "[bold yellow]No projected cost available[/bold yellow] — "
                        "pre-flight did not complete, so no figure is shown rather than "
                        "a guessed one."
                    )
                else:
                    yield Static(
                        "Projected API cost, priced per node from each node's declared "
                        f"model: [bold red]${self.estimated_cost:.4f}[/bold red]"
                    )
                    yield Static(
                        "[dim]Estimate counts assumed output tokens only. It does not "
                        "account for payload size, so a large input payload will cost "
                        "more than shown.[/dim]"
                    )
                
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
    
    def __init__(self, estimated_cost: float | None):
        super().__init__()
        self.estimated_cost = estimated_cost

    def compose(self) -> ComposeResult:
        with Container(classes="dialog", id="budget-warning-dialog"):
            yield Label("[bold red]WARNING: FINANCIAL COMMITMENT[/bold red]", classes="pane-title")

            # "up to $X" was the strongest claim in this dialog and the least supportable:
            # the estimate ignores input tokens entirely, so the real spend can exceed it.
            # An unbounded commitment stated as a bound is worse than an unstated one.
            if self.estimated_cost is None:
                yield Static(
                    "By proceeding, you are authorizing API token consumption of an "
                    "[bold yellow]unknown amount[/bold yellow] — pre-flight produced no "
                    "estimate."
                )
            else:
                yield Static(
                    "By proceeding, you are authorizing an estimated "
                    f"[bold yellow]${self.estimated_cost:.4f}[/bold yellow] in API token "
                    "consumption."
                )
                yield Static(
                    "[dim]This is an estimate, not a cap. Nothing enforces it, and it "
                    "excludes input-token cost.[/dim]"
                )
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
