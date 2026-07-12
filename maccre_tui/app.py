import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from textual.app import App, ComposeResult
from textual.containers import Grid, Horizontal, Vertical
from textual.widgets import Header, Footer, RichLog, Input, RadioSet, RadioButton, Label
from textual.widgets import Static


class PhysicsMonitor(Static):
    """Stub — original module deleted. Legacy LiveSwarmTUI only."""

    def update_physics(self, tension: float = 0.0, silence_ms: int = 0) -> None:
        self.update(f"T:{tension:.1f} S:{silence_ms}ms")
from maccre_core.orchestration.live_session_manager import LiveSessionManager

class AgentPane(Vertical):
    def __init__(self, agent_name: str):
        super().__init__()
        self.agent_name = agent_name

    def compose(self) -> ComposeResult:
        self.border_title = self.agent_name
        self.log_widget = RichLog(highlight=True, markup=True, id=f"log-{self.agent_name}")
        yield self.log_widget
        
    def write(self, text: str) -> None:
        self.log_widget.write(text)

class LiveSwarmTUI(App):
    CSS_PATH = "tui.css"
    TITLE = "MACCREv2 Live C2 Console"
    
    def __init__(self) -> None:
        super().__init__()
        self.manager = LiveSessionManager()
        self.agent_panes = {}
        # In a real dynamic system we would learn job_id from ZMQ. Hardcoded for the workbook.
        self.current_job_id = "LiveSession" 
        
    def compose(self) -> ComposeResult:
        yield Header()
        
        self.grid = Grid(id="agent-grid")
        with self.grid:
            for agent in ["Agent_Alpha", "Agent_Beta", "Agent_Gamma"]:
                pane = AgentPane(agent)
                self.agent_panes[agent] = pane
                yield pane
                
        with Horizontal(id="control-panel"):
            with Vertical(id="routing-controls"):
                yield Label("Topology Routing Preset")
                self.radio_set = RadioSet(
                    RadioButton("Entropy (Free-for-all)", id="mode-entropy", value=True),
                    RadioButton("Hub (User Focus)", id="mode-hub"),
                    RadioButton("Round Robin", id="mode-round_robin"),
                    RadioButton("Silo (Agent isolation)", id="mode-silo")
                )
                yield self.radio_set
            
            self.physics_monitor = PhysicsMonitor()
            yield self.physics_monitor
            
        self.user_input = Input(placeholder="Type a nudge and press Enter to interrupt...", id="user-input")
        yield self.user_input
        yield Footer()

    def on_mount(self) -> None:
        # Start the LiveSessionManager loop in Textual's async worker thread
        self.manager.register_callback("CHAT", self.on_chat_event)
        self.manager.register_callback("PHYSICS", self.on_physics_event)
        self.run_worker(self.manager.listen_loop_async(), exclusive=True, thread=False)

    def on_radio_set_changed(self, event: RadioSet.Changed) -> None:
        if event.pressed and event.pressed.id:
            mode = str(event.pressed.id).replace("mode-", "")
            self.manager.set_preset_mode(mode)
        
    async def on_input_submitted(self, event: Input.Submitted) -> None:
        text = event.value
        self.user_input.value = ""
        if text.strip():
            await self.manager.inject_interrupt_async(self.current_job_id, text, "ALL")
            # Echo to all logs
            for pane in self.agent_panes.values():
                pane.write(f"[bold cyan]User Nudge:[/bold cyan] {text}")

    def on_chat_event(self, payload: dict) -> None:
        agent = payload.get("agent_name")
        text = payload.get("text")
        if agent in self.agent_panes:
            self.call_from_thread(self.agent_panes[agent].write, f"[bold green]{agent}:[/bold green] {text}")
            
    def on_physics_event(self, payload: dict) -> None:
        self.call_from_thread(
            self.physics_monitor.update_physics,
            payload.get("tension", 0.0),
            payload.get("silence_ms", 0)
        )

if __name__ == "__main__":
    app = LiveSwarmTUI()
    app.run()
