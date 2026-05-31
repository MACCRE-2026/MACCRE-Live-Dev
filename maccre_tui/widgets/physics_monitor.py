from textual.app import ComposeResult
from textual.containers import Vertical
from textual.widgets import ProgressBar, Static, Label

class PhysicsMonitor(Static):
    """Displays real-time conversational physics metrics."""
    
    def compose(self) -> ComposeResult:
        with Vertical(id="physics-container"):
            yield Label("⚙️  ScoreKeeper Physics Engine", id="physics-title", classes="panel-title")
            
            yield Label("Tension Level")
            self.pb_tension = ProgressBar(total=1.0, show_eta=False, id="pb-tension")
            yield self.pb_tension
            
            yield Label("Silence (ms)")
            # Cap the visual silence bar at 10 seconds (10000 ms)
            self.pb_silence = ProgressBar(total=10000.0, show_eta=False, id="pb-silence")
            yield self.pb_silence
            
    def update_physics(self, tension: float, silence_ms: int) -> None:
        self.pb_tension.update(progress=tension)
        self.pb_silence.update(progress=min(10000.0, float(silence_ms)))
