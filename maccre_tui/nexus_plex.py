"""
maccre_tui/nexus_plex.py
========================
Nexus_Plex: MACCREv2 Agentic Command Center (TUI).

A persistent Split-Pane Architecture allowing users to collaborate with the
Nexus Copilot while manipulating and tracking MACCREv2 topologies.
"""
from __future__ import annotations

import sys
from pathlib import Path

# Ensure MACCREv2 root is in sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from textual import work, on
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, Container
from textual.screen import ModalScreen
from textual.widgets import (
    Header,
    Footer,
    RichLog,
    Input,
    Static,
    Button,
    Label,
    Select,
    TextArea,
    Switch,
    SelectionList,
    RadioSet,
    RadioButton
)

from maccre_core.orchestration.nexus_agent import NexusAgent
from maccre_core.workbook_data import load_project_names, load_agent_names_from_library, load_model_ids
from maccre_core.utils.path_resolver import get_maccre_root
from maccre_core.agent_library import get_agent_store

# ══════════════════════════════════════════════════════════════════════════════
# MODALS
# ══════════════════════════════════════════════════════════════════════════════

class NewProjectModal(ModalScreen[str]):
    """Modal to create a new project."""
    def compose(self) -> ComposeResult:
        with Container(classes="dialog"):
            yield Label("Create New Project")
            yield Input(placeholder="Project Name (e.g., UAP_Research)", id="new-project-input")
            with Horizontal(classes="dialog-buttons"):
                yield Button("Cancel", variant="error", id="cancel-btn")
                yield Button("Save Project", variant="success", id="save-btn")

    @on(Button.Pressed, "#cancel-btn")
    def cancel(self):
        self.dismiss("")

    @on(Button.Pressed, "#save-btn")
    def save(self):
        val = self.query_one("#new-project-input", Input).value.strip()
        if val:
            proj_dir = get_maccre_root() / "__DATACENTER" / val
            proj_dir.mkdir(parents=True, exist_ok=True)
            self.dismiss(val)


class SelectProjectModal(ModalScreen[str]):
    """Modal to select an existing project."""
    def compose(self) -> ComposeResult:
        with Container(classes="dialog"):
            yield Label("Select Existing Project")
            projects = [(p, p) for p in load_project_names()]
            yield Select(projects, id="project-select")
            with Horizontal(classes="dialog-buttons"):
                yield Button("Cancel", variant="error", id="cancel-btn")
                yield Button("Set Active Project", variant="primary", id="select-btn")

    @on(Button.Pressed, "#cancel-btn")
    def cancel(self):
        self.dismiss("")

    @on(Button.Pressed, "#select-btn")
    def select(self):
        sel = self.query_one("#project-select", Select)
        if sel.value and sel.value != Select.BLANK:
            self.dismiss(str(sel.value))


class SystemInstructionsModal(ModalScreen[str]):
    """Modal for writing System Instructions (replaces old TextArea footprint)."""
    def __init__(self, current_text: str = ""):
        super().__init__()
        self.current_text = current_text

    def compose(self) -> ComposeResult:
        with Container(classes="dialog"):
            yield Label("System Instructions")
            yield TextArea(self.current_text, id="si-textarea")
            with Horizontal(classes="dialog-buttons"):
                yield Button("Paste from Clipboard", variant="default", id="paste-btn")
                yield Button("Cancel", variant="error", id="cancel-btn")
                yield Button("Save Instructions", variant="success", id="save-btn")

    @on(Button.Pressed, "#paste-btn")
    def paste_from_clipboard(self):
        try:
            import pyperclip
            text = pyperclip.paste()
            if text:
                ta = self.query_one("#si-textarea", TextArea)
                # Appending the pasted text
                ta.text = ta.text + "\n" + text if ta.text else text
        except Exception:
            pass

    @on(Button.Pressed, "#cancel-btn")
    def cancel(self):
        self.dismiss(None)

    @on(Button.Pressed, "#save-btn")
    def save(self):
        val = self.query_one("#si-textarea", TextArea).text
        self.dismiss(val)

class EditAgentModal(ModalScreen[str]):
    """Modal to select an agent from the roster to edit."""
    def __init__(self, agents: list[str]):
        super().__init__()
        self.agents = agents

    def compose(self) -> ComposeResult:
        with Container(classes="dialog"):
            yield Label("Select Agent to Edit")
            options = [(a, a) for a in self.agents]
            yield Select(options, id="edit-agent-select")
            with Horizontal(classes="dialog-buttons"):
                yield Button("Cancel", variant="error", id="cancel-btn")
                yield Button("Load Agent", variant="primary", id="load-btn")

    @on(Button.Pressed, "#cancel-btn")
    def cancel(self):
        self.dismiss(None)

    @on(Button.Pressed, "#load-btn")
    def load_agent(self):
        sel = self.query_one("#edit-agent-select", Select)
        if sel.value and sel.value != Select.BLANK:
            self.dismiss(str(sel.value))

class OverwriteConfirmModal(ModalScreen[bool]):
    """Modal to confirm overwriting an existing agent."""
    def compose(self) -> ComposeResult:
        with Container(classes="dialog"):
            yield Label("This action will overwrite the existing agent, do you want to proceed?")
            with Horizontal(classes="dialog-buttons"):
                yield Button("No", variant="error", id="no-btn")
                yield Button("Yes", variant="success", id="yes-btn")

    @on(Button.Pressed, "#no-btn")
    def no_pressed(self):
        self.dismiss(False)

    @on(Button.Pressed, "#yes-btn")
    def yes_pressed(self):
        self.dismiss(True)

class LinearFlowEditorModal(ModalScreen[list]):
    """Modal to define a Flow using MacroNodes and Agents from the Registry."""

    DEFAULT_CSS = """
    LinearFlowEditorModal {
        align: center middle;
    }

    #flow-editor-outer {
        width: 90%;
        height: 85%;
        max-width: 140;
        padding: 1 2;
        background: #0d1117;
        border: thick #30363d;
    }

    #flow-editor-title {
        text-style: bold;
        color: #58a6ff;
        text-align: center;
        margin-bottom: 1;
    }

    /* ── Selection Row ─────────────────────────────── */
    #flow-select-row {
        height: auto;
        layout: horizontal;
        margin-bottom: 1;
    }

    .flow-select-group {
        width: 1fr;
        height: auto;
        padding: 0 1;
    }

    .flow-select-group Label {
        margin-bottom: 0;
        color: #8b949e;
        text-style: bold;
    }

    .flow-select-group Select {
        width: 100%;
        margin-bottom: 0;
    }

    .flow-add-btn {
        margin-top: 1;
        width: 100%;
    }

    /* ── Flow Line Visualization ───────────────────── */
    #flow-line-section {
        height: 7;
        margin: 1 0;
        border: round #30363d;
        padding: 0 1;
        overflow-x: auto;
        overflow-y: hidden;
    }

    #flow-line-section Label {
        color: #484f58;
        text-style: italic;
    }

    #flow-line-content {
        height: 5;
        layout: horizontal;
        align: center middle;
        min-width: 100%;
    }

    .flow-node-box {
        min-width: 22;
        height: 3;
        border: round #58a6ff;
        content-align: center middle;
        padding: 0 1;
        margin: 0 1;
        color: #58a6ff;
    }

    .flow-node-box-agent {
        min-width: 22;
        height: 3;
        border: round #3fb950;
        content-align: center middle;
        padding: 0 1;
        margin: 0 1;
        color: #3fb950;
    }

    .flow-arrow {
        height: 3;
        width: 3;
        content-align: center middle;
        color: #484f58;
    }

    /* ── Info Panels ───────────────────────────────── */
    #flow-info-row {
        height: 1fr;
        layout: horizontal;
        margin-top: 1;
    }

    #flow-macro-info {
        width: 1fr;
        height: 100%;
        border: round #30363d;
        padding: 1;
        overflow-y: auto;
        margin-right: 1;
    }

    #flow-agent-info {
        width: 1fr;
        height: 100%;
        border: round #30363d;
        padding: 1;
        overflow-y: auto;
    }

    .info-panel-title {
        color: #8b949e;
        text-style: bold;
        margin-bottom: 1;
    }

    .info-panel-body {
        color: #c9d1d9;
    }

    /* ── Bottom Buttons ────────────────────────────── */
    #flow-editor-buttons {
        height: auto;
        margin-top: 1;
        layout: horizontal;
        align: right middle;
    }

    #flow-editor-buttons Button {
        margin-left: 1;
    }
    """

    def __init__(self, templates: list[dict], roster: list[str]) -> None:
        super().__init__()
        self.templates = templates
        self.roster = sorted(roster)
        self.flow_steps: list[tuple[str, dict, str]] = []  # (name, mapping, type: "macro"|"agent")

    def compose(self) -> ComposeResult:
        with Container(id="flow-editor-outer"):
            yield Label("━━━ Linear Flow Editor ━━━", id="flow-editor-title")

            # ── Selection Row: MacroNode + Agent side by side ─────────────
            with Horizontal(id="flow-select-row"):
                with Vertical(classes="flow-select-group"):
                    yield Label("MacroNode")
                    yield Select(
                        [(t["name"], t["name"]) for t in self.templates],
                        prompt="Select MacroNode…",
                        id="macro-select",
                    )
                    yield Button(
                        "Add MacroNode to Flow",
                        variant="primary",
                        id="btn-add-macro",
                        classes="flow-add-btn",
                    )

                with Vertical(classes="flow-select-group"):
                    yield Label("Agent")
                    yield Select(
                        [(a, a) for a in self.roster],
                        prompt="Select Agent…",
                        id="agent-select",
                    )
                    yield Button(
                        "Add Agent to Flow",
                        variant="success",
                        id="btn-add-agent",
                        classes="flow-add-btn",
                    )

            # ── Flow Line Visualization ───────────────────────────────────
            with Vertical(id="flow-line-section"):
                yield Horizontal(id="flow-line-content")

            # ── Info Panels ───────────────────────────────────────────────
            with Horizontal(id="flow-info-row"):
                with Vertical(id="flow-macro-info"):
                    yield Label("MacroNode Details", classes="info-panel-title")
                    yield Static(
                        "[dim]Select a MacroNode above to see its description.[/dim]",
                        id="macro-info-body",
                        classes="info-panel-body",
                    )

                with Vertical(id="flow-agent-info"):
                    yield Label("Agent Details", classes="info-panel-title")
                    yield Static(
                        "[dim]Select an Agent above to see its profile.[/dim]",
                        id="agent-info-body",
                        classes="info-panel-body",
                    )

            # ── Bottom Buttons ────────────────────────────────────────────
            with Horizontal(id="flow-editor-buttons"):
                yield Button("Remove Last", variant="warning", id="btn-remove-last")
                yield Button("Clear Flow", variant="error", id="btn-clear-flow")
                yield Button("Done", variant="success", id="btn-done-flow")

    # ── Event Handlers ────────────────────────────────────────────────────────

    @on(Select.Changed, "#macro-select")
    def macro_selection_changed(self, event: Select.Changed) -> None:
        """Show selected MacroNode's description in the info panel."""
        body = self.query_one("#macro-info-body", Static)
        if not event.value or event.value == Select.BLANK:
            body.update("[dim]Select a MacroNode above to see its description.[/dim]")
            return

        name = str(event.value)
        template = next((t for t in self.templates if t["name"] == name), None)
        if not template:
            body.update(f"[red]MacroNode '{name}' not found.[/red]")
            return

        # Build rich info display
        desc = template.get("description", "No description available.")
        tpl_type = template.get("template_type", "custom")
        slots = template.get("agent_slots", [])
        tpl_cfg = template.get("template_config", {})

        info_parts = [
            f"[bold cyan]{name}[/bold cyan]",
            f"[dim]Template:[/dim] {tpl_type or 'freeform'}",
            "",
            "[bold]Description[/bold]",
            str(desc),
        ]

        if slots:
            info_parts.append("")
            info_parts.append(f"[bold]Agents[/bold]: {', '.join(slots)}")

        if tpl_cfg and isinstance(tpl_cfg, dict):
            info_parts.append("")
            info_parts.append("[bold]Configuration[/bold]")
            for k, v in tpl_cfg.items():
                info_parts.append(f"  {k}: {v}")

        # Show topology nodes
        topo_rows = template.get("topology_rows", [])
        if topo_rows:
            info_parts.append("")
            info_parts.append(f"[bold]Topology Nodes[/bold] ({len(topo_rows)})")
            for row in topo_rows:
                node_id = row.get("Node_ID", "?")
                agent = row.get("Agent_Name", "?")
                dp = row.get("Dialogue_Partner")
                dr = row.get("Dialogue_Rounds", 0)
                dp_str = f" ↔ {dp} ({dr} rounds)" if dp else ""
                info_parts.append(f"  • {node_id}: {agent}{dp_str}")

        body.update("\n".join(info_parts))

    @on(Select.Changed, "#agent-select")
    def agent_selection_changed(self, event: Select.Changed) -> None:
        """Show selected Agent's profile in the info panel."""
        body = self.query_one("#agent-info-body", Static)
        if not event.value or event.value == Select.BLANK:
            body.update("[dim]Select an Agent above to see its profile.[/dim]")
            return

        name = str(event.value)
        try:
            from maccre_core.orchestration.roster_loader import load_agent_from_roster  # noqa: PLC0415
            agent = load_agent_from_roster(name)
        except (KeyError, FileNotFoundError):
            body.update(f"[red]Agent '{name}' not found in roster.[/red]")
            return
        except Exception as exc:  # noqa: BLE001
            body.update(f"[red]Error loading agent: {exc}[/red]")
            return

        model = agent.get("model", "unknown")
        tools = agent.get("tools_allowed", "none")
        desc = agent.get("description", "")
        instructions = agent.get("system_prompt", "No instructions available.")

        info_parts = [
            f"[bold green]{name}[/bold green]",
            f"[dim]Model:[/dim] {model}",
            f"[dim]Tools:[/dim] {tools}",
        ]

        if desc:
            info_parts.append(f"[dim]Description:[/dim] {desc}")

        info_parts.append("")
        info_parts.append("[bold]System Instructions[/bold]")

        # Truncate very long instructions for display
        instr_display = str(instructions)
        if len(instr_display) > 2000:
            instr_display = instr_display[:2000] + "\n\n[dim]…truncated (2000 chars shown)…[/dim]"

        info_parts.append(instr_display)
        body.update("\n".join(info_parts))

    @on(Button.Pressed, "#btn-add-macro")
    def add_macro_to_flow(self) -> None:
        """Add the selected MacroNode to the flow line."""
        sel = self.query_one("#macro-select", Select)
        if not sel.value or sel.value == Select.BLANK:
            return

        name = str(sel.value)
        self.flow_steps.append((name, {}, "macro"))
        self._refresh_flow_line()

    @on(Button.Pressed, "#btn-add-agent")
    def add_agent_to_flow(self) -> None:
        """Add the selected Agent as a single-node step to the flow line."""
        sel = self.query_one("#agent-select", Select)
        if not sel.value or sel.value == Select.BLANK:
            return

        name = str(sel.value)
        self.flow_steps.append((name, {}, "agent"))
        self._refresh_flow_line()

    @on(Button.Pressed, "#btn-remove-last")
    def remove_last(self) -> None:
        """Remove the last step from the flow line."""
        if self.flow_steps:
            self.flow_steps.pop()
            self._refresh_flow_line()

    @on(Button.Pressed, "#btn-clear-flow")
    def clear_flow(self) -> None:
        """Clear all steps from the flow line."""
        self.flow_steps.clear()
        self._refresh_flow_line()

    @on(Button.Pressed, "#btn-done-flow")
    def done_flow(self) -> None:
        """Dismiss the modal and return the flow steps."""
        if not self.flow_steps:
            self.dismiss(None)
            return
        # Return as list of [name, mapping] pairs for backward compatibility
        result = [[name, mapping] for name, mapping, _ in self.flow_steps]
        self.dismiss(result)

    # ── Flow Line Visualization ───────────────────────────────────────────────

    def _refresh_flow_line(self) -> None:
        """Redraw the flow line visualization with hollow boxes."""
        container = self.query_one("#flow-line-content", Horizontal)

        # Clear existing widgets
        for w in list(container.children):
            w.remove()

        if not self.flow_steps:
            container.mount(
                Static("[dim italic]  ── empty flow line ──  [/dim italic]")
            )
            return

        for i, (name, _mapping, step_type) in enumerate(self.flow_steps):
            if i > 0:
                container.mount(Static(" → ", classes="flow-arrow"))

            css_class = "flow-node-box" if step_type == "macro" else "flow-node-box-agent"
            container.mount(Static(f" {name} ", classes=css_class))



class ContextInjectModalScreen(ModalScreen[str]):
    def compose(self) -> ComposeResult:
        with Container(classes="dialog", id="context-inject-dialog"):
            yield Label("Inject Context")
            yield TextArea(id="context-text-area")
            with Horizontal(classes="dialog-buttons"):
                yield Button("Cancel", variant="error", id="cancel-btn")
                yield Button("Paste from Clipboard", variant="default", id="paste-btn")
                yield Button("Send", variant="success", id="send-btn")

    @on(Button.Pressed, "#cancel-btn")
    def cancel(self):
        self.dismiss(None)

    @on(Button.Pressed, "#paste-btn")
    def paste_clipboard(self):
        # Cross platform clipboard read in terminal can be tricky. We will leave this stubbed for future GUI/pyperclip use.
        ta = self.query_one("#context-text-area", TextArea)
        ta.text += "\n[Clipboard content here]"

    @on(Button.Pressed, "#send-btn")
    def send(self):
        text = self.query_one("#context-text-area", TextArea).text.strip()
        self.dismiss(text)


class FlowHistoryModalScreen(ModalScreen[str]):
    def compose(self) -> ComposeResult:
        with Container(classes="dialog", id="flow-history-dialog"):
            yield Label("Flow History")
            yield Static("No past flows available yet.") # Placeholder
            with Horizontal(classes="dialog-buttons"):
                yield Button("Close", variant="default", id="close-btn")
                yield Button("Canonize Flow", variant="success", id="btn-canonize-flow")

    @on(Button.Pressed, "#close-btn")
    def close(self):
        self.dismiss(None)
        
    @on(Button.Pressed, "#btn-canonize-flow")
    def canonize(self):
        self.dismiss("canonize")


class FileCabinetModalScreen(ModalScreen[dict]):
    def compose(self) -> ComposeResult:
        with Container(classes="dialog", id="file-cabinet-dialog"):
            yield Label("File Cabinet (Notebook Ingestion)")
            yield Input(placeholder="Notebook Name...", id="fc-notebook-name")
            yield Input(placeholder="Datacenter (Project Name)...", id="fc-datacenter")
            yield Input(placeholder="Files to Ingest (Comma separated paths)...", id="fc-files")
            with Horizontal(classes="dialog-buttons"):
                yield Button("Close", variant="error", id="close-btn")
                yield Button("Create & Ingest", variant="success", id="ingest-btn")

    @on(Button.Pressed, "#close-btn")
    def close(self):
        self.dismiss(None)
        
    @on(Button.Pressed, "#ingest-btn")
    def ingest(self):
        name = self.query_one("#fc-notebook-name", Input).value.strip()
        project = self.query_one("#fc-datacenter", Input).value.strip()
        files = self.query_one("#fc-files", Input).value.strip()
        if name and project:
            self.dismiss({"name": name, "project": project, "files": files.split(",")})
        else:
            self.dismiss(None)


class AgentChatInputModalScreen(ModalScreen[str]):
    def compose(self) -> ComposeResult:
        with Container(classes="dialog", id="agent-chat-input-dialog"):
            yield Label("Agent Chat Input")
            yield TextArea(id="agent-chat-text-area")
            with Horizontal(classes="dialog-buttons"):
                yield Button("Cancel", variant="error", id="cancel-btn")
                yield Button("Paste from Clipboard", variant="default", id="paste-btn")
                yield Button("Send to Chat", variant="success", id="send-btn")

    @on(Button.Pressed, "#cancel-btn")
    def cancel(self):
        self.dismiss(None)

    @on(Button.Pressed, "#paste-btn")
    def paste_clipboard(self):
        try:
            import pyperclip
            text = pyperclip.paste()
            if text:
                ta = self.query_one("#agent-chat-text-area", TextArea)
                ta.text = ta.text + "\n" + text if ta.text else text
        except Exception:
            pass

    @on(Button.Pressed, "#send-btn")
    def send(self):
        text = self.query_one("#agent-chat-text-area", TextArea).text.strip()
        self.dismiss(text)


class AgentChatModalScreen(ModalScreen):
    BINDINGS = [("ctrl+j", "submit_chat", "Send Chat (Ctrl+Enter)")]
    
    def compose(self) -> ComposeResult:
        with Container(classes="dialog agent-chat-dialog"):
            yield Label("Agent Chat Session")
            
            with Horizontal(classes="chat-config-row"):
                with Vertical(classes="agent-selector-pane"):
                    yield Label("Select Agents")
                    yield SelectionList(id="agent-selection-list")
                with Vertical(classes="mode-selector-pane"):
                    yield Label("Session Mode")
                    with RadioSet(id="chat-mode-radio"):
                        yield RadioButton("Sequential", value=True, id="mode-sequential")
                        yield RadioButton("Live with Physics", id="mode-physics")
                    with Horizontal(classes="chat-buttons"):
                        yield Button("Start Session", variant="success", id="btn-start-chat")
                        yield Button("Stop Session", variant="error", id="btn-stop-chat", disabled=True)
                        yield Button("Close", variant="default", id="btn-close-chat")

            yield RichLog(id="agent-chat-log", wrap=True, highlight=True, markup=True)
            
            with Horizontal(id="agent-chat-input-container"):
                with Horizontal(classes="chat-input-row"):
                    yield TextArea(id="agent-chat-input")
                    yield Button("Enter", id="btn-agent-chat-send", variant="primary")
            yield Label(id="typing-indicator", classes="dim")

    def on_mount(self) -> None:
        self.session_task = None
        self.session_task = None
        self.session_manager = None
        self.active_workers = {}
        self.roster = []
        try:
            from maccre_core.workbook_data import load_agent_names_from_library
            roster = load_agent_names_from_library(self.app.active_project)
            if self.app.active_project != "GLOBAL":
                roster.extend(load_agent_names_from_library("GLOBAL"))
            self.roster = list(set(roster))
            self._build_agent_list()
        except Exception:
            pass

    def _build_agent_list(self, tensions: dict[str, float] = None) -> None:
        self._is_rebuilding = True
        if tensions is None:
            tensions = {}
        sel_list = self.query_one("#agent-selection-list", SelectionList)
        selected = list(sel_list.selected)
        
        all_agents = sorted(self.roster)
        ordered_agents = [a for a in all_agents if a in selected] + [a for a in all_agents if a not in selected]
        
        highlighted = getattr(sel_list, "highlighted", None)
        sel_list.clear_options()
        
        from rich.text import Text
        for agent in ordered_agents:
            tension = tensions.get(agent, 0.0)
            bar_len = 10
            filled = int(tension * bar_len)
            empty = bar_len - filled
            
            if tension < 0.2:
                color = "blue"
            elif tension < 0.4:
                color = "cyan"
            elif tension < 0.6:
                color = "yellow"
            elif tension < 0.8:
                color = "orange"
            else:
                color = "bright_red"
                
            bar_text = "█" * filled + "░" * empty
            
            if agent in selected and self.session_task:
                label = Text(f"{agent} ")
                label.append(f"[{bar_text}]", style=color)
            else:
                label = Text(agent)
                
            sel_list.add_option((label, agent, agent in selected))
            
        if highlighted is not None and highlighted < len(ordered_agents):
            try:
                sel_list.highlighted = highlighted
            except Exception:
                pass
        self._is_rebuilding = False

    def on_physics_update(self, payload: dict) -> None:
        def do_update():
            agent_tensions = payload.get("agent_tension", {})
            self._build_agent_list(tensions=agent_tensions)
        self.call_from_thread(do_update)

    @on(Button.Pressed, "#btn-close-chat")
    def close(self):
        self.stop_chat()
        self.dismiss(None)

    def _inject_live_task(self, agent_name: str) -> None:
        import sqlite3
        from pathlib import Path
        from maccre_core.utils.path_resolver import get_datacenter_path
        
        job_id = "live_session"
        payload_path = str(get_datacenter_path(f"02_Dynamic_Context/{job_id}_payload.txt"))
        Path(payload_path).parent.mkdir(parents=True, exist_ok=True)
        Path(payload_path).write_text("[SYSTEM] WAIT_FOR_USER", encoding="utf-8")
            
        active_proj = self.app.active_project
        if active_proj == "GLOBAL":
            db_path = get_datacenter_path("swarm_queue.db")
        else:
            db_path = get_datacenter_path(f"{active_proj}/swarm_queue.db")
            
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        
        with sqlite3.connect(db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS task_queue (
                    id                   INTEGER PRIMARY KEY AUTOINCREMENT,
                    job_id               TEXT NOT NULL,
                    payload_path         TEXT NOT NULL,
                    source_payload_path  TEXT DEFAULT '',
                    current_node         TEXT NOT NULL,
                    lock_status          TEXT DEFAULT 'open',
                    locked_by            TEXT,
                    actual_cost          REAL DEFAULT 0.0,
                    created_at           TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(job_id, current_node)
                )
            """)
            conn.execute("""
                INSERT OR IGNORE INTO task_queue 
                (job_id, payload_path, current_node, lock_status) 
                VALUES (?, ?, ?, 'open')
            """, (job_id, payload_path, agent_name))
            
            conn.execute("""
                UPDATE task_queue SET lock_status = 'open' 
                WHERE job_id = ? AND current_node = ?
            """, (job_id, agent_name))
            conn.commit()

    def _spawn_worker(self, agent_name: str, mode: str) -> None:
        if agent_name in self.active_workers:
            return
            
        self._inject_live_task(agent_name)
        
        import os
        import sys
        import subprocess
        from pathlib import Path
        env = os.environ.copy()
        
        # Ensure the project root is in PYTHONPATH so maccre_core can be imported
        root_dir = str(Path(__file__).parent.parent.resolve())
        env["PYTHONPATH"] = root_dir + (os.pathsep + env.get("PYTHONPATH", "") if "PYTHONPATH" in env else "")
        
        env["MACCRE_ACTIVE_PROJECT"] = self.app.active_project
        if mode == "Live with Physics":
            env["MACCRE_LIVE_OVERRIDE"] = "1"
            
        worker_script = str(Path(__file__).parent.parent / "maccre_core" / "orchestration" / "swarm_worker.py")
        proc = subprocess.Popen(
            [sys.executable, "-u", worker_script, agent_name],
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )
        self.active_workers[agent_name] = proc

    def _kill_worker(self, agent_name: str) -> None:
        proc = self.active_workers.pop(agent_name, None)
        if proc:
            try:
                proc.terminate()
            except Exception:
                pass
        
    @on(Button.Pressed, "#btn-start-chat")
    def start_chat(self):
        log = self.query_one("#agent-chat-log", RichLog)
        sel_list = self.query_one("#agent-selection-list", SelectionList)
        selected_agents = sel_list.selected
        if not selected_agents:
            log.write("[red]System: Please select at least one agent.[/red]")
            return
            
        radio = self.query_one("#chat-mode-radio", RadioSet)
        mode = "Sequential" if radio.pressed_button and radio.pressed_button.id == "mode-sequential" else "Live with Physics"
        
        log.write(f"\n[bold cyan]--- Starting {mode} Session ---[/bold cyan]")
        log.write(f"[bold cyan]Agents:[/bold cyan] {', '.join(selected_agents)}")
        self.query_one("#btn-start-chat", Button).disabled = True
        self.query_one("#btn-stop-chat", Button).disabled = False
        
        if mode == "Live with Physics":
            from maccre_core.orchestration.live_session_manager import LiveSessionManager
            import asyncio
            self.session_manager = LiveSessionManager()
            self.session_manager.register_callback("PHYSICS", self.on_physics_update)
            self.session_manager.register_callback("CHAT", self.on_agent_chat)
            self.session_task = asyncio.create_task(self.session_manager.listen_loop_async())
            
        for agent in selected_agents:
            self._spawn_worker(agent, mode)
            
        self._build_agent_list()
        sel_list.focus()

    @on(Button.Pressed, "#btn-stop-chat")
    def stop_chat(self):
        if self.session_task:
            self.session_task.cancel()
            self.session_task = None
        if getattr(self, "session_manager", None):
            self.session_manager = None
            
        for agent in list(self.active_workers.keys()):
            self._kill_worker(agent)
            
        log = self.query_one("#agent-chat-log", RichLog)
        log.write("\n[bold yellow]--- Session Stopped ---[/bold yellow]")
        self.query_one("#btn-start-chat", Button).disabled = False
        self.query_one("#btn-stop-chat", Button).disabled = True
        
        self._build_agent_list()

    @on(SelectionList.SelectedChanged, "#agent-selection-list")
    def handle_selection_changed(self, event: SelectionList.SelectedChanged) -> None:
        if getattr(self, "session_manager", None):
            new_selection = set(event.selection_list.selected)
            old_selection = self.session_manager.active_agents
            
            if old_selection != new_selection:
                self.session_manager.active_agents = new_selection
                
                added = new_selection - old_selection
                removed = old_selection - new_selection
                
                radio = self.query_one("#chat-mode-radio", RadioSet)
                mode = "Sequential" if radio.pressed_button and radio.pressed_button.id == "mode-sequential" else "Live with Physics"
                
                for a in added:
                    self._spawn_worker(a, mode)
                for r in removed:
                    self._kill_worker(r)
                    
                log = self.query_one("#agent-chat-log", RichLog)
                log.write(f"[dim]Active Swarm Updated: {', '.join(new_selection) or 'None'}[/dim]")

    def action_submit_chat(self) -> None:
        self._send_chat_message()

    @on(Button.Pressed, "#btn-agent-chat-send")
    def handle_btn_send(self) -> None:
        self._send_chat_message()

    def _send_chat_message(self):
        inp = self.query_one("#agent-chat-input", TextArea)
        msg = inp.text.strip()
        if not msg:
            return
            
        log = self.query_one("#agent-chat-log", RichLog)
        log.write(f"\n[bold green]You:[/bold green] {msg}")
        inp.text = ""
        if getattr(self, "session_manager", None):
            self.session_manager.message_bus.publish("MACCRE.CHAT", {
                "agent_name": "User",
                "job_id": "live_session",
                "text": msg
            })
            log.write("[dim]System: Message routed to active agents[/dim]")
        else:
            log.write("[yellow]System: Message routed to active agents (Backend not hooked up)[/yellow]")

    def on_agent_chat(self, payload: dict) -> None:
        try:
            speaker = payload.get("agent_name", "System")
            text = payload.get("text", "")
            is_typing = payload.get("is_typing", False)
            
            typing_lbl = self.query_one("#typing-indicator", Label)
            if is_typing:
                typing_lbl.update(f"[dim i]{speaker} is typing...[/dim i]")
            else:
                typing_lbl.update("")
                if text and speaker != "User":
                    log = self.query_one("#agent-chat-log")
                    if log:
                        log.write(f"[bold blue]{speaker}:[/bold blue] {text}")
        except Exception:  # noqa: BLE001
            pass

    @on(Button.Pressed, "#btn-expand-agent-chat-input")
    def action_expand_agent_chat_input(self) -> None:
        def handle_chat_expanded(msg: str | None):
            if msg:
                log = self.query_one("#agent-chat-log", RichLog)
                log.write(f"\n[bold green]You:[/bold green] {msg}")
                if getattr(self, "session_manager", None):
                    self.session_manager.message_bus.publish("MACCRE.CHAT", {
                        "agent_name": "User",
                        "job_id": "live_session",
                        "text": msg
                    })
                    log.write("[dim]System: Message routed to active agents[/dim]")
                else:
                    log.write("[yellow]System: Message routed to active agents (Backend not hooked up)[/yellow]")
        self.app.push_screen(AgentChatInputModalScreen(), handle_chat_expanded)

class NexusInputModalScreen(ModalScreen[str]):
    def compose(self) -> ComposeResult:
        with Container(classes="dialog", id="nexus-input-dialog"):
            yield Label("Nexus Chat Input")
            yield TextArea(id="nexus-text-area")
            with Horizontal(classes="dialog-buttons"):
                yield Button("Cancel", variant="error", id="cancel-btn")
                yield Button("Paste from Clipboard", variant="default", id="paste-btn")
                yield Button("Send to Nexus", variant="success", id="send-btn")

    @on(Button.Pressed, "#cancel-btn")
    def cancel(self):
        self.dismiss(None)

    @on(Button.Pressed, "#paste-btn")
    def paste_clipboard(self):
        try:
            import pyperclip
            text = pyperclip.paste()
            if text:
                ta = self.query_one("#nexus-text-area", TextArea)
                ta.text = ta.text + "\n" + text if ta.text else text
        except Exception:
            pass

    @on(Button.Pressed, "#send-btn")
    def send(self):
        text = self.query_one("#nexus-text-area", TextArea).text.strip()
        self.dismiss(text)


# ══════════════════════════════════════════════════════════════════════════════
# CUSTOM WIDGETS
# ══════════════════════════════════════════════════════════════════════════════

class NexusChat(Vertical):
    def compose(self) -> ComposeResult:
        yield Label("Nexus Copilot", classes="pane-title")
        yield RichLog(id="nexus-log", wrap=True, highlight=True, markup=True)
        with Horizontal(id="nexus-input-container"):
            yield Button(">", id="btn-expand-nexus-input")
            yield Input(placeholder="Ask Nexus to parse a topology...", id="nexus-input")
            yield Button("Ctrl-Enter", id="btn-nexus-send", variant="primary")

class ProjectControls(Horizontal):
    def compose(self) -> ComposeResult:
        yield Static("Project: [None]", id="active-project-label", classes="ribbon-label")
        yield Button("New Project", variant="success", id="btn-new-project")
        yield Button("Select Project", variant="primary", id="btn-select-project")
        yield Button("File Cabinet", variant="warning", id="btn-file-cabinet")
        yield Button("Agent Chat", variant="default", id="btn-agent-chat")


class AgentBuilderPanel(Vertical):
    """Panel to define and mint new agents into the roster."""
    def compose(self) -> ComposeResult:
        yield Label("Build an Agent", classes="pane-title")
        yield Button("Edit Agent", variant="warning", id="btn-open-edit-agent", classes="top-edit-btn")
        yield Label("Agent Name")
        yield Input(placeholder="e.g., OSINT_Researcher", id="ab-name")
        
        # We will populate models dynamically in on_mount
        yield Label("Model")
        yield Select([], id="ab-model")

        yield Label("System Instructions")
        yield Button("Edit System Instructions", variant="primary", id="btn-edit-instructions")


        yield Label("Temperature")
        yield Input(value="1.0", id="ab-temp")

        # --- AI Studio Options ---
        yield Label("Thinking level", classes="form-group-title")
        yield Select([("None", "none"), ("Low", "low"), ("High", "high")], value="high", id="ab-thinking")

        yield Label("Tools", classes="form-group-title")
        with Horizontal(classes="form-row"):
            yield Label("Structured outputs")
            yield Switch(value=False, id="ab-structured")
        with Horizontal(classes="form-row"):
            yield Label("Code execution")
            yield Switch(value=False, id="ab-code")
        with Horizontal(classes="form-row"):
            yield Label("Function calling")
            yield Switch(value=False, id="ab-function")
        with Horizontal(classes="form-row"):
            yield Label("Grounding with Google Search")
            yield Switch(value=True, id="ab-gsearch")
        with Horizontal(classes="form-row"):
            yield Label("Grounding with Google Maps")
            yield Switch(value=False, id="ab-gmaps")
        with Horizontal(classes="form-row"):
            yield Label("URL context")
            yield Switch(value=False, id="ab-url")

        yield Label("Advanced settings", classes="form-group-title")
        yield Label("Media resolution")
        yield Select([("Default", "default"), ("Low", "low"), ("High", "high")], value="default", id="ab-media")
        
        with Horizontal(classes="form-row"):
            yield Label("Add stop sequence")
            yield Input(placeholder="Add stop...", id="ab-stop")
        with Horizontal(classes="form-row"):
            yield Label("Output length")
            yield Input(value="65536", id="ab-output-len")
        with Horizontal(classes="form-row"):
            yield Label("Top P")
            yield Input(value="0.95", id="ab-top-p")

        yield Button("Save to Roster", variant="success", id="btn-save-agent")


class FlowExecutionPanel(Vertical):
    def compose(self) -> ComposeResult:
        # Flow Execution Top Panel
        with Vertical(classes="panel-section", id="flow-execution-top"):
            yield Label("Flow Execution", classes="pane-title")
            with Horizontal(classes="flow-controls"):
                yield Button("Launch Flow", variant="success", id="btn-launch-flow")
                yield Button("Stop Flow", variant="error", id="btn-stop-flow", disabled=True)
                yield Button("Flow History", variant="default", id="btn-flow-history")
                yield Button("Linear Flow Editor", variant="warning", id="btn-flow-editor")
                
            yield Label("Active Flow Sequence")
            with Horizontal(classes="flow-controls"):
                yield Static("No flow loaded.", id="active-flow-sequence")
                yield Button("Rewind Last Step", variant="warning", id="btn-rewind-flow")

        # Flow Monitor Panel
        with Vertical(classes="panel-section", id="flow-monitor-section"):
            yield Label("Flow Monitor", classes="pane-title")
            yield RichLog(id="flow-execution-log", wrap=True, highlight=True, markup=True)
            with Horizontal(classes="input-row"):
                yield Input(placeholder="Inject context to flow...", id="fe-input")
                yield Button("↗", id="btn-expand-input", variant="primary", classes="btn-icon")



# ══════════════════════════════════════════════════════════════════════════════
# NEXUS_PLEX APP
# ══════════════════════════════════════════════════════════════════════════════

class NexusPlex(App[None]):
    """MACCREv2 Command Center — Nexus_Plex v2."""

    CSS_PATH = "nexus_plex.css"
    TITLE = "Nexus_Plex  ·  MACCREv2 Agentic Command Center"
    
    BINDINGS = [
        Binding("ctrl+q", "quit", "Quit"),
        Binding("ctrl+j", "nexus_send_shortcut", "Send to Nexus", show=False),
        Binding("ctrl+enter", "nexus_send_shortcut", "Send to Nexus", show=False),
    ]

    def __init__(self) -> None:
        super().__init__()
        self.active_project = "GLOBAL"
        self.system_instructions_buffer = ""
        self.active_sessions: dict[str, object] = {}
        self.is_session_active = False
        self.session_mode = "chat"
        self.physics_task = None
        self.is_agent_generating = False
        self.shared_transcript: list[dict[str, str]] = []
        
        self.nexus = NexusAgent(
            print_callback=self.write_nexus_log,
            get_active_project_cb=lambda: self.active_project,
            set_active_project_cb=self.set_active_project
        )

    def set_active_project(self, project_name: str) -> None:
        self.active_project = project_name
        label = self.query_one("#active-project-label", Static)
        
        import threading
        if self._thread_id == threading.get_ident():
            label.update(f"Project: [bold cyan]{project_name}[/bold cyan]")
        else:
            self.call_from_thread(label.update, f"Project: [bold cyan]{project_name}[/bold cyan]")
            
        self.refresh_agent_dropdown()

    def compose(self) -> ComposeResult:
        yield Header()
        with Horizontal(id="main-layout"):
            with Vertical(id="left-pane"):
                yield NexusChat()
            with Vertical(id="right-pane"):
                with Horizontal(id="top-ribbon"):
                    yield ProjectControls(id="project-controls")
                with Horizontal(id="agent-manager"):
                    yield AgentBuilderPanel()
                    yield FlowExecutionPanel()
        yield Footer()

    def on_mount(self) -> None:
        """Initialize the dashboard."""
        self.write_nexus_log("[bold cyan]Nexus:[/bold cyan] Online. What topology shall we parse today?")
        
        # Dynamically load models
        try:
            models = load_model_ids()
            sel_model = self.query_one("#ab-model", Select)
            sel_model.set_options([(m, m) for m in models])
            if models:
                sel_model.value = models[0]
        except Exception as e:
            self.write_nexus_log(f"[red]Error loading models: {e}[/red]")

        self.set_active_project("GLOBAL")

    def on_unmount(self) -> None:
        if hasattr(self, "nexus"):
            self.nexus.close()

    def write_nexus_log(self, text: str) -> None:
        import threading
        log = self.query_one("#nexus-log", RichLog)
        if self._thread_id == threading.get_ident():
            log.write(text)
        else:
            self.call_from_thread(log.write, text)

    def write_agent_log(self, text: str) -> None:
        import threading
        log = self.query_one("#flow-execution-log", RichLog)
        if self._thread_id == threading.get_ident():
            log.write(text)
        else:
            self.call_from_thread(log.write, text)

    # ── Nexus Copilot Handlers ────────────────────────────────────────────────
    @on(Input.Submitted, "#nexus-input")
    def handle_nexus_input(self, event: Input.Submitted) -> None:
        msg = event.value.strip()
        if not msg:
            return
        inp = self.query_one("#nexus-input", Input)
        inp.value = ""
        self.write_nexus_log(f"\n[bold green]You:[/bold green] {msg}")
        self.dispatch_nexus_message(msg)

    @on(Button.Pressed, "#btn-nexus-send")
    def action_nexus_send(self) -> None:
        try:
            inp = self.query_one("#nexus-input", Input)
            msg = inp.value.strip()
            if not msg:
                return
            inp.value = ""
            self.write_nexus_log(f"\n[bold green]You:[/bold green] {msg}")
            self.dispatch_nexus_message(msg)
        except Exception:
            pass

    def action_nexus_send_shortcut(self) -> None:
        try:
            inp = self.query_one("#nexus-input", Input)
            if inp.has_focus:
                self.action_nexus_send()
        except Exception:
            pass

    @on(Button.Pressed, "#btn-expand-nexus-input")
    def action_expand_nexus_input(self) -> None:
        def handle_nexus_expanded(msg: str | None):
            if msg:
                self.write_nexus_log(f"\n[bold green]You:[/bold green] {msg}")
                self.dispatch_nexus_message(msg)
        self.push_screen(NexusInputModalScreen(), handle_nexus_expanded)

    @work(thread=True)
    def dispatch_nexus_message(self, message: str) -> None:
        self.nexus.send_message(message)

    # ── Project Handlers ──────────────────────────────────────────────────────
    @on(Button.Pressed, "#btn-new-project")
    def action_new_project(self) -> None:
        def check_new_project(name: str):
            if name:
                self.set_active_project(name)
                self.write_nexus_log(f"\n[bold green]System:[/bold green] Project '{name}' created and set as active.")
        self.push_screen(NewProjectModal(), check_new_project)

    @on(Button.Pressed, "#btn-select-project")
    def action_select_project(self) -> None:
        def check_select_project(name: str):
            if name:
                self.set_active_project(name)
                self.write_nexus_log(f"\n[bold green]System:[/bold green] Active project switched to '{name}'.")
        self.push_screen(SelectProjectModal(), check_select_project)

    @on(Button.Pressed, "#btn-agent-chat")
    def action_open_agent_chat(self) -> None:
        self.push_screen(AgentChatModalScreen())

    # ── Agent Builder Handlers ────────────────────────────────────────────────
    @on(Button.Pressed, "#btn-open-edit-agent")
    def action_open_edit_agent(self) -> None:
        agents = load_agent_names_from_library(self.active_project)
        def handle_edit_agent(name: str | None):
            if name:
                self._load_agent_into_builder(name)
        self.push_screen(EditAgentModal(agents), handle_edit_agent)

    def _load_agent_into_builder(self, name: str) -> None:
        from maccre_core.agent_library import get_agent_store
        store = get_agent_store(self.active_project)
        all_agents = store.load_all()
        agent = next((a for a in all_agents if a.get("agent_name") == name or a.get("AGENT_NAME") == name), None)
        if not agent:
            store = get_agent_store("GLOBAL")
            all_agents = store.load_all()
            agent = next((a for a in all_agents if a.get("agent_name") == name or a.get("AGENT_NAME") == name), None)
        if not agent:
            from maccre_core.workbook_data import load_agent_roster_csv
            for row in load_agent_roster_csv(self.active_project):
                if row.get("Agent_Name") == name or row.get("agent_name") == name:
                    agent = {
                        "agent_name": row.get("Agent_Name", name),
                        "model": row.get("Model", ""),
                        "system_prompt": row.get("System_Prompt", ""),
                        "tools_allowed": row.get("Tools_Allowed", ""),
                        "ai_studio_options": {}
                    }
                    break
            if not agent:
                for row in load_agent_roster_csv("GLOBAL"):
                    if row.get("Agent_Name") == name or row.get("agent_name") == name:
                        agent = {
                            "agent_name": row.get("Agent_Name", name),
                            "model": row.get("Model", ""),
                            "system_prompt": row.get("System_Prompt", ""),
                            "tools_allowed": row.get("Tools_Allowed", ""),
                            "ai_studio_options": {}
                        }
                        break

        if not agent:
            self.write_nexus_log(f"[red]Could not load agent '{name}'.[/red]")
            return
                
        self.query_one("#ab-name", Input).value = name
        self.query_one("#ab-temp", Input).value = str(agent.get("temperature", 1.0))
        
        # Determine system prompt
        sp = agent.get("system_prompt") or agent.get("PERSONA") or ""
        self.system_instructions_buffer = sp
        btn = self.query_one("#btn-edit-instructions", Button)
        if sp:
            btn.label = "Edit System Instructions (Saved)"
            btn.variant = "success"
        else:
            btn.label = "Edit System Instructions"
            btn.variant = "primary"

        opts = agent.get("ai_studio_options", {})
        
        def set_sel(id_str, val):
            if val:
                sel = self.query_one(id_str, Select)
                if any(o[1] == val for o in sel._options):
                    sel.value = val
                    
        set_sel("#ab-model", agent.get("model"))
        set_sel("#ab-thinking", opts.get("thinking_level"))
        set_sel("#ab-media", opts.get("media_resolution"))

        self.query_one("#ab-structured", Switch).value = bool(opts.get("structured_outputs", False))
        self.query_one("#ab-code", Switch).value = bool(opts.get("code_execution", False))
        self.query_one("#ab-function", Switch).value = bool(opts.get("function_calling", False))
        self.query_one("#ab-gsearch", Switch).value = bool(opts.get("grounding_google_search", False))
        self.query_one("#ab-gmaps", Switch).value = bool(opts.get("grounding_google_maps", False))
        self.query_one("#ab-url", Switch).value = bool(opts.get("url_context", False))

        self.query_one("#ab-stop", Input).value = opts.get("stop_sequence", "")
        self.query_one("#ab-output-len", Input).value = str(opts.get("output_length", 65536))
        self.query_one("#ab-top-p", Input).value = str(opts.get("top_p", 0.95))
        
        self.write_nexus_log(f"[bold cyan]System:[/bold cyan] Loaded agent '{name}' into builder.")

    @on(Button.Pressed, "#btn-edit-instructions")
    def action_edit_instructions(self) -> None:
        def save_instructions(text: str | None):
            if text is not None:
                self.system_instructions_buffer = text
                btn = self.query_one("#btn-edit-instructions", Button)
                btn.label = "Edit System Instructions (Saved)"
                btn.variant = "success"
        self.push_screen(SystemInstructionsModal(self.system_instructions_buffer), save_instructions)

    def refresh_agent_dropdown(self) -> None:
        pass

    @on(Button.Pressed, "#btn-save-agent")
    def action_save_agent(self) -> None:
        name = self.query_one("#ab-name", Input).value.strip()
        model_sel = self.query_one("#ab-model", Select).value
        model = str(model_sel) if model_sel and model_sel != Select.BLANK else ""
        instructions = self.system_instructions_buffer.strip()
        
        if not name or not instructions:
            self.write_nexus_log("[red]System: Agent Name and Instructions are required.[/red]")
            return

        try:
            temp = float(self.query_one("#ab-temp", Input).value.strip())
        except ValueError:
            temp = 1.0

        try:
            top_p = float(self.query_one("#ab-top-p", Input).value.strip())
        except ValueError:
            top_p = 0.95

        try:
            output_len = int(self.query_one("#ab-output-len", Input).value.strip())
        except ValueError:
            output_len = 65536

        thinking_val = self.query_one("#ab-thinking", Select).value
        media_val = self.query_one("#ab-media", Select).value

        # Build ai_studio_options dictionary
        ai_studio_options = {
            "thinking_level": str(thinking_val) if thinking_val != Select.BLANK else "none",
            "structured_outputs": self.query_one("#ab-structured", Switch).value,
            "code_execution": self.query_one("#ab-code", Switch).value,
            "function_calling": self.query_one("#ab-function", Switch).value,
            "grounding_google_search": self.query_one("#ab-gsearch", Switch).value,
            "grounding_google_maps": self.query_one("#ab-gmaps", Switch).value,
            "url_context": self.query_one("#ab-url", Switch).value,
            "media_resolution": str(media_val) if media_val != Select.BLANK else "default",
            "stop_sequence": self.query_one("#ab-stop", Input).value.strip(),
            "output_length": output_len,
            "top_p": top_p
        }

        # The core fields remain at the top level for backward compatibility
        profile = {
            "agent_name": name,
            "model": model,
            "system_prompt": instructions,
            "tools_allowed": "",
            "temperature": temp,
            "ai_studio_options": ai_studio_options
        }

        # Ensure we're hitting the DB
        store = get_agent_store(self.active_project)
        
        def commit_save():
            try:
                store.save(profile)
                self.write_nexus_log(f"[bold green]System:[/bold green] Saved agent '{name}'.")
                
                # Clear inputs
                self.query_one("#ab-name", Input).value = ""
                self.system_instructions_buffer = ""
                btn = self.query_one("#btn-edit-instructions", Button)
                btn.label = "Edit System Instructions"
                btn.variant = "primary"

                self.refresh_agent_dropdown()
            except Exception as e:
                self.write_nexus_log(f"[red]Error saving agent: {e}[/red]")

        existing = load_agent_names_from_library(self.active_project)
        if name in existing:
            def do_save(proceed: bool | None):
                if proceed:
                    commit_save()
                else:
                    self.write_nexus_log(f"[bold yellow]System:[/bold yellow] Save aborted for '{name}'.")
            self.push_screen(OverwriteConfirmModal(), do_save)
        else:
            commit_save()

    # ── Flow Execution Handlers ───────────────────────────────────────────────
    
    @on(Button.Pressed, "#btn-flow-editor")
    def action_flow_editor(self) -> None:
        from maccre_core.macronode_registry import get_macronode_store
        from maccre_core.workbook_data import load_agent_names_from_library
        
        store = get_macronode_store(self.active_project)
        templates = store.list_all()
        # Ensure we have full dictionary with agent_slots
        full_templates = []
        for t in templates:
            try:
                full_templates.append(store.load(t["name"]))
            except Exception:
                pass
                
        roster = load_agent_names_from_library(self.active_project)
        if self.active_project != "GLOBAL":
            roster.extend(load_agent_names_from_library("GLOBAL"))
        roster = list(set(roster))
        
        def handle_add_to_flow(result: list | None) -> None:
            if result:
                if not hasattr(self, "active_flow_steps"):
                    self.active_flow_steps = []

                from maccre_core.orchestration.flow_engine import FlowStep  # noqa: PLC0415
                self.active_flow_steps.clear()
                for step in result:
                    macro_name, mapping = step[0], step[1]
                    self.active_flow_steps.append(FlowStep(macro_name, mapping))

                seq_str = " → ".join([s.macronode_name for s in self.active_flow_steps])
                self.query_one("#active-flow-sequence", Static).update(f"[bold cyan]{seq_str}[/bold cyan]")
                self.write_agent_log(
                    f"[green]Flow Line updated: {len(self.active_flow_steps)} step(s).[/green]"
                )

        self.push_screen(LinearFlowEditorModal(full_templates, roster), handle_add_to_flow)

    @on(Button.Pressed, "#btn-launch-flow")
    def action_launch_flow(self) -> None:
        if not hasattr(self, "active_flow_steps") or not self.active_flow_steps:
            self.write_agent_log("[red]Flow Line is empty. Use Linear Flow Editor to add MacroNodes.[/red]")
            return
            
        self.is_session_active = True
        self.query_one("#btn-launch-flow", Button).disabled = True
        self.query_one("#btn-stop-flow", Button).disabled = False
        self.query_one("#btn-flow-editor", Button).disabled = True
        
        self.write_agent_log("\n[bold cyan]--- Started Linear Flow Execution ---[/bold cyan]")
        self.run_linear_flow_background()

    @work(thread=True)
    def run_linear_flow_background(self) -> None:
        from maccre_core.orchestration.flow_engine import FlowRunner
        runner = FlowRunner(self.active_project)
        
        try:
            final_artifact = runner.execute_flow(self.active_flow_steps, initial_payload_path="none")
            self.write_agent_log(f"\n[green]Flow completed successfully![/green]\nFinal Artifact: {final_artifact}")
        except Exception as e:
            self.write_agent_log(f"\n[red]Flow Error:[/red] {e}")
        finally:
            self.call_from_thread(self._finish_flow)
            
    def _finish_flow(self) -> None:
        self.is_session_active = False
        btn_launch = self.query_one("#btn-launch-flow", Button)
        btn_stop = self.query_one("#btn-stop-flow", Button)
        btn_editor = self.query_one("#btn-flow-editor", Button)
        
        btn_launch.disabled = False
        btn_stop.disabled = True
        btn_editor.disabled = False

    @on(Button.Pressed, "#btn-stop-flow")
    def action_stop_flow(self) -> None:
        self.write_agent_log("\n[bold yellow]--- Flow Stop Requested (Will halt after current node) ---[/bold yellow]")
        self._finish_flow()

    @on(Button.Pressed, "#btn-rewind-flow")
    def action_rewind_flow(self) -> None:
        if not hasattr(self, "active_flow_steps") or not self.active_flow_steps:
            self.write_agent_log("[yellow]Flow Line is empty, nothing to rewind.[/yellow]")
            return
        
        popped = self.active_flow_steps.pop()
        seq_str = " -> ".join([s.macronode_name for s in self.active_flow_steps]) or "No flow loaded."
        self.query_one("#active-flow-sequence", Static).update(f"[bold cyan]{seq_str}[/bold cyan]")
        self.write_agent_log(f"[yellow]Rewound Flow Line: Removed {popped.macronode_name}.[/yellow]")

    @on(Button.Pressed, "#btn-file-cabinet")
    def action_file_cabinet(self) -> None:
        def handle_file_cabinet_result(result: dict | None):
            if result:
                name = result["name"]
                project = result["project"]
                files = result["files"]
                # For now, we will just log it. Backend logic will follow in notebook_registry.py implementation.
                self.write_nexus_log(f"[green]File Cabinet:[/green] Queued {len(files)} files for Notebook '{name}' in {project}.")
                from maccre_core.notebook_registry import ingest_to_notebook
                try:
                    ingest_to_notebook(name, project, files)
                    self.write_nexus_log("[green]File Cabinet:[/green] Ingestion complete.")
                except Exception as e:
                    self.write_nexus_log(f"[red]File Cabinet Error:[/red] {e}")

        self.push_screen(FileCabinetModalScreen(), handle_file_cabinet_result)

    @on(Button.Pressed, "#btn-flow-history")
    def action_flow_history(self) -> None:
        def handle_flow_history_result(result: str | None):
            if result == "canonize":
                self.write_agent_log("[green]Flow Canonized![/green]")
        self.push_screen(FlowHistoryModalScreen(), handle_flow_history_result)

    @on(Button.Pressed, "#btn-expand-input")
    def action_expand_input(self) -> None:
        def handle_inject_result(result: str | None):
            if result:
                self.write_agent_log(f"\n[bold green]You (Context Inject):[/bold green] {result}")
                self.write_agent_log("[dim italic]Note: Mid-flow context injection requires Swarm Worker queue injection (Phase 5).[/dim italic]")
        self.push_screen(ContextInjectModalScreen(), handle_inject_result)

    @on(Input.Submitted, "#fe-input")
    def handle_flow_input(self, event: Input.Submitted) -> None:
        msg = event.value.strip()
        if not msg:
            return
            
        inp = self.query_one("#fe-input", Input)
        inp.value = ""
        self.write_agent_log(f"\n[bold green]You (Context Inject):[/bold green] {msg}")
        self.write_agent_log("[dim italic]Note: Mid-flow context injection requires Swarm Worker queue injection (Phase 5).[/dim italic]")

# ── Entry point ───────────────────────────────────────────────────────────────

def main() -> None:
    NexusPlex().run()

if __name__ == "__main__":
    main()

