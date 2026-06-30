import re

with open('B:\\EXO_GANS\\maccre_tui\\nexus_plex.py', 'r', encoding='utf-8') as f:
    content = f.read()

TOOL_EVENT_HANDLER = """
    @on(Select.Changed, "#tool-select")
    def tool_selection_changed(self, event: Select.Changed) -> None:
        body = self.query_one("#tool-info-body", Static)
        if not event.value or event.value == Select.BLANK:
            body.update("[dim]Select a tool to view details.[/dim]")
            return
        name = str(event.value)
        
        tool_desc = {
            "read_file": "Reads the contents of a specified file. Used for extracting exact file data.",
            "write_file": "Overwrites or creates a new file. Used for saving generated code.",
            "list_dir": "Lists the contents of a directory. Useful for exploring the workspace.",
            "web_search": "Searches the live web for current information.\\n\\n[bold warning]Note:[/bold warning] Standard Google Search Grounding is configured globally in the Agent Builder. This tool is primarily for local agent Brave searches or combined Brave/Google dual-search.",
            "hybrid_search": "Semantic vector search against the local Sovereign Memory Chroma DB, combined with lexical BM25.\\n\\n[bold warning]Note:[/bold warning] Standard Google Search Grounding is configured globally in the Agent Builder. This tool is primarily for local agent Brave searches or combined Brave/Google dual-search.",
            "execute_sql": "Executes a raw SQL query against a specified database.",
            "execute_terminal": "Runs an arbitrary shell command (e.g. git, npm, python). Use with caution."
        }
        
        desc = tool_desc.get(name, "No description available.")
        info = [
            f"[bold cyan]{name}[/bold cyan]",
            "",
            "[bold]Description[/bold]",
            str(desc)
        ]
        body.update("\\n".join(info))
"""

idx = content.find("class NodeConfigModal(ModalScreen")
if idx != -1:
    idx2 = content.find("@on(Button.Pressed, \"#btn-cfg-cancel\")", idx)
    content = content[:idx2] + TOOL_EVENT_HANDLER + "\n    " + content[idx2:]
else:
    print("WARNING: Could not find NodeConfigModal class to insert tool handler")

with open('B:\\EXO_GANS\\maccre_tui\\nexus_plex.py', 'w', encoding='utf-8') as f:
    f.write(content)

print("Patch part 3 fix done.")
