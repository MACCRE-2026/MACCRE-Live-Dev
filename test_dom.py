import asyncio
from textual.app import App, ComposeResult
from maccre_tui.widgets.macronode_builder_panel import MacroNodeBuilderPanel

class TestApp(App):
    def compose(self) -> ComposeResult:
        yield MacroNodeBuilderPanel("test_project")
        
    async def on_mount(self):
        panel = self.query_one(MacroNodeBuilderPanel)
        panel.all_agents = ["Agent_A", "Agent_B"]
        from textual.widgets import Select
        sel = panel.query_one("#me-type-select", Select)
        await asyncio.sleep(0.5)
        # We manually call the handler since mocking an event is trickier
        await panel.on_type_select(Select.Changed(sel, "crucible"))
        await asyncio.sleep(0.5)
        
        # Dump the DOM
        with open("dom_dump.txt", "w") as f:
            f.write(str(self.screen.tree))
            
        self.exit()

if __name__ == "__main__":
    app = TestApp()
    app.run()
