"""Bisect crash — test individual sub-widgets."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from textual.app import App, ComposeResult
from textual.widgets import Footer, Static

# Test individual widgets:
from maccre_tui.widgets.topology_visualizer import TopologyVisualizer
# from maccre_tui.widgets.node_catalog import NodeCatalog


class TestApp(App[None]):
    def compose(self) -> ComposeResult:
        yield Static("Test App")
        yield TopologyVisualizer()
        # yield NodeCatalog()
        yield Footer()


if __name__ == "__main__":
    TestApp().run()
