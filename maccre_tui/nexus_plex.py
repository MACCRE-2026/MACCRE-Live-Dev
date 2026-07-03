"""
maccre_tui/nexus_plex.py
========================
Nexus_Plex: MACCREv2 Agentic Command Center (TUI).

A persistent Split-Pane Architecture allowing users to collaborate with the
Nexus Copilot while manipulating and tracking MACCREv2 topologies.
"""
from __future__ import annotations

import sys
import threading
from pathlib import Path

# Ensure MACCREv2 root is in sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from maccre_tui.macro_editor_modal import MacroNodeEditorModal
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
    RadioButton,
    DataTable,
)

from maccre_tui.widgets.session_manager_modal import SessionManagerModal
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
            for tier in ["01_Raw_Source", "02_Dynamic_Context", "03_Agent_Ledgers", "04_Code_Artifacts", "05_Rendered_Media"]:
                (proj_dir / tier).mkdir(exist_ok=True)
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


class ContextInjectModalScreen(ModalScreen[str]):
    def __init__(self, current_payload: str = "", **kwargs):
        super().__init__(**kwargs)
        self.current_payload = current_payload

    def compose(self) -> ComposeResult:
        with Container(classes="dialog", id="context-inject-dialog"):
            with Horizontal(id="hitl-header-row"):
                yield Label("Unified Ledger Context (Up to this point):", id="hitl-ledger-title")
                yield Button("Copy Ledger", id="btn-copy-hitl-ledger", variant="default", classes="copy-btn-small")
            
            yield RichLog(id="hitl-ledger-content", wrap=True, highlight=True, markup=True)
            yield Label("Inject Context")
            yield TextArea(id="context-text-area")
            with Horizontal(classes="dialog-buttons"):
                yield Button("Cancel", variant="error", id="cancel-btn")
                yield Button("Paste from Clipboard", variant="default", id="paste-btn")
                yield Button("Send", variant="success", id="send-btn")

    def on_mount(self) -> None:
        log_widget = self.query_one("#hitl-ledger-content", RichLog)
        payload_content = self.current_payload
        try:
            import os
            if os.path.exists(self.current_payload) and os.path.isfile(self.current_payload):
                with open(self.current_payload, "r", encoding="utf-8") as f:
                    payload_content = f.read()
        except Exception:
            pass
        log_widget.write(payload_content)

    @on(Button.Pressed, "#btn-copy-hitl-ledger")
    def copy_hitl_ledger(self):
        try:
            import pyperclip
            log_widget = self.query_one("#hitl-ledger-content", RichLog)
            text_lines = [line.plain for line in log_widget.lines]
            pyperclip.copy("\n".join(text_lines))
            self.notify("Copied Ledger to clipboard!")
        except Exception as e:
            self.notify(f"Failed to copy to clipboard: {e}", severity="error")

    @on(Button.Pressed, "#cancel-btn")
    def cancel(self):
        self.dismiss(None)

    @on(Button.Pressed, "#paste-btn")
    def paste_clipboard(self):
        try:
            import pyperclip  # noqa: PLC0415
            text = pyperclip.paste()
            if text:
                ta = self.query_one("#context-text-area", TextArea)
                ta.text = ta.text + "\n" + text if ta.text else text
        except Exception:
            pass

    @on(Button.Pressed, "#send-btn")
    def send(self):
        text = self.query_one("#context-text-area", TextArea).text.strip()
        self.dismiss(text)


class NodeLiveChatModal(ModalScreen[dict[str, str] | None]):
    """Live Chat with a specific flow node's agent. Staged payload + preparatory chat."""

    BINDINGS = [("escape", "close_chat", "Close")]

    def __init__(
        self,
        agent_name: str,
        node_name: str,
        staged_payload: str,
        system_prompt: str = "",
    ) -> None:
        super().__init__()
        self._agent_name = agent_name
        self._node_name = node_name
        self._staged_payload = staged_payload
        self._system_prompt = system_prompt
        self._conversation: list[dict[str, str]] = []
        self._payload_delivered = False

    def compose(self) -> ComposeResult:
        with Container(classes="dialog", id="live-chat-modal"):
            yield Label(
                f"💬 Live Chat: {self._agent_name} (Node: {self._node_name})",
                classes="pane-title",
            )

            # Staged payload display (read-only)
            yield Label("Staged Payload [dim](will be delivered on Continue Flow)[/dim]")
            yield Static(
                f"[dim]{self._staged_payload[:500]}{'...' if len(self._staged_payload) > 500 else ''}[/dim]",
                id="staged-payload-display",
            )

            # Conversation log
            yield Label("Conversation")
            yield RichLog(id="live-chat-log", wrap=True, highlight=True, markup=True)

            # Chat input
            with Horizontal(classes="chat-input-row"):
                yield TextArea(id="live-chat-input")
                yield Button("Send", id="btn-live-chat-send", variant="primary")

            # Action buttons
            with Horizontal(id="live-chat-buttons"):
                yield Button("Continue Flow", id="btn-continue-flow", variant="success")
                yield Button("Re-Run Node", id="btn-rerun-node", variant="warning")
                yield Button("Close", id="btn-close-live-chat", variant="error")

    @on(Button.Pressed, "#btn-live-chat-send")
    def send_message(self) -> None:
        inp = self.query_one("#live-chat-input", TextArea)
        msg = inp.text.strip()
        if not msg:
            return
        inp.text = ""
        log = self.query_one("#live-chat-log", RichLog)
        log.write(f"\n[bold green]You:[/bold green] {msg}")
        self._conversation.append({"role": "user", "text": msg})

        # Generate agent response in background
        self._generate_response(msg, log)

    @work(thread=True)
    def _generate_response(self, user_msg: str, log: RichLog) -> None:
        """Generate agent response via UniversalRouter."""
        try:
            from maccre_core.maccre_router import UniversalRouter  # noqa: PLC0415
            router = UniversalRouter()

            # Build context: system prompt + conversation history
            context_parts: list[str] = []
            if self._system_prompt:
                context_parts.append(f"System: {self._system_prompt}")
            for turn in self._conversation[:-1]:  # All except last (which is current)
                role = "User" if turn["role"] == "user" else self._agent_name
                context_parts.append(f"{role}: {turn['text']}")

            full_prompt = "\n\n".join(context_parts) + f"\n\nUser: {user_msg}"

            response = router.generate(full_prompt, temperature=0.7)
            response_text = response.text if hasattr(response, "text") else str(response)

            self._conversation.append({"role": "agent", "text": response_text})
            self.call_from_thread(
                log.write,
                f"\n[bold blue]{self._agent_name}:[/bold blue] {response_text}",
            )
        except Exception as e:  # noqa: BLE001
            self.call_from_thread(
                log.write,
                f"\n[red]Error generating response: {e}[/red]",
            )

    @on(Button.Pressed, "#btn-continue-flow")
    def continue_flow(self) -> None:
        """Deliver staged payload + conversation context, then dismiss."""
        log = self.query_one("#live-chat-log", RichLog)
        log.write("\n[bold cyan]Delivering staged payload to agent...[/bold cyan]")

        # Build combined context: staged payload + conversation
        combined_parts = [self._staged_payload]
        for turn in self._conversation:
            role = "User" if turn["role"] == "user" else self._agent_name
            combined_parts.append(f"{role}: {turn['text']}")

        combined = "\n\n".join(combined_parts)
        self._payload_delivered = True
        self.dismiss({"action": "continue", "payload": combined})

    @on(Button.Pressed, "#btn-rerun-node")
    def rerun_node(self) -> None:
        """Clear conversation and restart."""
        self._conversation.clear()
        self._payload_delivered = False
        log = self.query_one("#live-chat-log", RichLog)
        log.clear()
        log.write("[yellow]Node reset. Start a new preparatory conversation.[/yellow]")

    @on(Button.Pressed, "#btn-close-live-chat")
    def action_close_chat(self) -> None:
        """Close without delivering - flow stays paused."""
        self.dismiss(None)


class FlowHistoryModalScreen(ModalScreen[dict | None]):
    """Browse completed flow sessions by project and load them as templates."""

    def compose(self) -> ComposeResult:
        with Container(classes="dialog", id="flow-history-dialog"):
            yield Label("Flow History", id="flow-history-title")
            yield Static("Project:", classes="flow-history-label")
            yield Select(
                options=[("All Projects", "")],
                value="",
                id="fh-project-select",
                allow_blank=False,
            )
            yield DataTable(id="fh-session-table", cursor_type="row")
            with Horizontal(classes="dialog-buttons"):
                yield Button("Close", variant="default", id="fh-close-btn")
                yield Button("Load Flow", variant="success", id="fh-load-btn")
                yield Button("Canonize", variant="warning", id="fh-canonize-btn")

    def on_mount(self) -> None:
        # Populate project selector
        try:
            from maccre_core.utils.session_manager import list_projects  # noqa: PLC0415
            projects = list_projects()
            options: list[tuple[str, str]] = [("All Projects", "")]
            for p in projects:
                name = p.get("project_name", "")
                if name:
                    options.append((name, name))
            select = self.query_one("#fh-project-select", Select)
            select.set_options(options)
        except Exception:  # noqa: BLE001
            pass

        # Set up DataTable columns
        table = self.query_one("#fh-session-table", DataTable)
        table.add_columns("Job ID", "Flow", "Cost", "Date", "Artifact")
        self._refresh_table("")

    def _refresh_table(self, project: str) -> None:
        """Re-query flow_history and populate the DataTable."""
        table = self.query_one("#fh-session-table", DataTable)
        table.clear()
        self._flow_records: list[dict] = []
        try:
            from maccre_core.utils.session_manager import list_completed_flows  # noqa: PLC0415
            import json  # noqa: PLC0415
            flows = list_completed_flows(project_name=project)
            for flow in flows:
                job_id = str(flow.get("job_id", "?"))
                # Parse flow steps for display
                try:
                    steps = json.loads(flow.get("flow_steps_json", "[]"))
                    flow_names = " → ".join(s.get("macronode_name", "?") for s in steps)
                except Exception:  # noqa: BLE001
                    flow_names = "?"
                cost = f"${flow.get('total_cost', 0.0):.4f}"
                date = str(flow.get("completed_at", "?"))[:16]
                artifact = str(flow.get("final_artifact", ""))
                has_artifact = "✓" if artifact and artifact != "none" else "-"
                table.add_row(job_id, flow_names, cost, date, has_artifact)
                self._flow_records.append(flow)
        except Exception:  # noqa: BLE001
            pass

    @on(Select.Changed, "#fh-project-select")
    def on_project_change(self, event: Select.Changed) -> None:
        project = str(event.value) if event.value is not None else ""
        self._refresh_table(project)

    @on(Button.Pressed, "#fh-close-btn")
    def close(self) -> None:
        self.dismiss(None)

    @on(Button.Pressed, "#fh-load-btn")
    def load_flow(self) -> None:
        table = self.query_one("#fh-session-table", DataTable)
        cursor = table.cursor_row
        if cursor is not None and 0 <= cursor < len(self._flow_records):
            record = self._flow_records[cursor]
            self.dismiss({"action": "load", "record": record})
        else:
            self.dismiss(None)

    @on(Button.Pressed, "#fh-canonize-btn")
    def canonize(self) -> None:
        table = self.query_one("#fh-session-table", DataTable)
        cursor = table.cursor_row
        if cursor is not None and 0 <= cursor < len(self._flow_records):
            record = self._flow_records[cursor]
            self.dismiss({"action": "canonize", "record": record})
        else:
            self.dismiss(None)

class FileCabinetModalScreen(ModalScreen[dict]):
    def compose(self) -> ComposeResult:
        with Container(classes="dialog", id="file-cabinet-dialog"):
            yield Label("File Cabinet (Knowledge Collection)")
            yield Input(placeholder="Collection Name...", id="fc-collection-name")
            yield Input(placeholder="Datacenter (Project Name)...", id="fc-datacenter")
            yield Input(placeholder="Files to Ingest (Comma separated paths)...", id="fc-files")
            with Horizontal(classes="dialog-buttons"):
                yield Button("Close", variant="error", id="close-btn")
                yield Button("Create & Ingest", variant="success", id="ingest-btn")
                yield Button("Project Canon & Memory", variant="warning", id="btn-project-canon")

    @on(Button.Pressed, "#btn-project-canon")
    def open_canon(self):
        self.dismiss({"action": "project_canon"})

    @on(Button.Pressed, "#close-btn")
    def close(self):
        self.dismiss(None)
        
    @on(Button.Pressed, "#ingest-btn")
    def ingest(self):
        name = self.query_one("#fc-collection-name", Input).value.strip()
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


class ChatDashboardPane(Vertical):
    def compose(self) -> ComposeResult:
        yield Label("Chat Dashboard", classes="pane-title")
        yield Label("Select a Previous Chat")
        yield SelectionList(id="studio-history-list")
        yield Button("Load Chat", variant="primary", id="btn-load-studio-chat")

class ChatBuilderPane(Vertical):
    def compose(self) -> ComposeResult:
        yield Label("Chat Builder", classes="pane-title")
        yield Label("Select Agents for Chat")
        yield SelectionList(id="studio-select-agents")
        yield Label("Configure Agent")
        yield SelectionList(id="studio-configure-agent")
        
        # Copied from AgentBuilderPanel logic
        yield Label("Agent Profile Overrides", classes="pane-title")
        yield Label("Model")
        yield Select([], id="studio-model")
        yield Label("System Instructions")
        yield Button("Edit System Instructions (Saved)", variant="primary", id="btn-studio-edit-instructions")
        
        yield Label("Temperature")
        yield Input(value="1.0", id="studio-temp")
        
        yield Label("Thinking level", classes="form-group-title")
        yield Select([("None", "none"), ("Low", "low"), ("High", "high")], value="high", id="studio-thinking")
        
        yield Label("Tools", classes="form-group-title")
        with Horizontal(classes="form-row"):
            yield Label("Structured outputs")
            yield Switch(value=False, id="studio-structured")
        with Horizontal(classes="form-row"):
            yield Label("Code execution")
            yield Switch(value=False, id="studio-code")
        with Horizontal(classes="form-row"):
            yield Label("Function calling")
            yield Switch(value=False, id="studio-function")
        with Vertical(id="studio-triple-index-box", classes="form-group-box"):
            yield Label("Triple Index Search", classes="form-group-title")
            with Horizontal(classes="form-row"):
                yield Label("Grounding with Google Search")
                yield Switch(value=True, id="studio-gsearch")
            with Horizontal(classes="form-row"):
                yield Label("Grounding with Brave Search")
                yield Switch(value=False, id="studio-bsearch")
            with Horizontal(classes="form-row"):
                yield Label("Grounding with Local Memory")
                yield Switch(value=False, id="studio-msearch")
            with Horizontal(classes="form-row"):
                yield Label("Exclusionary Search")
                yield Switch(value=False, id="studio-exclusionary", disabled=True)
            with Horizontal(classes="form-row"):
                yield Label("Funnel Search")
                yield Switch(value=False, id="studio-funnel", disabled=True)
            yield Label("Information")
            yield RichLog(id="studio-search-info-panel", wrap=True, highlight=True, markup=True)
            
        with Horizontal(classes="form-row"):
            yield Label("Grounding with Google Maps")
            yield Switch(value=False, id="studio-gmaps")
        with Horizontal(classes="form-row"):
            yield Label("URL context")
            yield Switch(value=False, id="studio-url")

        yield Label("Advanced settings", classes="form-group-title")
        yield Label("Media resolution")
        yield Select([("Default", "default"), ("Low", "low"), ("High", "high")], value="default", id="studio-media")
        
        with Horizontal(classes="form-row"):
            yield Label("Add stop sequence")
            yield Input(placeholder="Add stop...", id="studio-stop")
        with Horizontal(classes="form-row"):
            yield Label("Output length")
            yield Input(value="65536", id="studio-output-len")
        with Horizontal(classes="form-row"):
            yield Label("Top P")
            yield Input(value="0.95", id="studio-top-p")
        
        yield Button("Start Chat", variant="success", id="btn-start-studio-chat", classes="top-edit-btn")

class ChatArenaPane(Vertical):
    def compose(self) -> ComposeResult:
        with Horizontal(id="chat-arena-header"):
            yield Input(placeholder="Name Chat (Optional)", id="chat-rename-input")
            yield Label("Tokens: 0 | Cost: $0.000", id="chat-finops-readout")
            yield Button("Close Chat", variant="error", id="btn-close-studio-chat")
            
        yield RichLog(id="chat-arena-log", wrap=True, highlight=True, markup=True)
        
        with Vertical(id="chat-arena-footer"):
            yield Label("", id="chat-typing-indicator", classes="dim")
            yield TextArea(id="chat-arena-input")
            with Horizontal(classes="chat-arena-controls"):
                yield Button("Expand", variant="primary", id="btn-expand-input")
                yield Button("Paste from Clipboard", variant="default", id="btn-paste-clipboard")
                yield Button("Send (Ctrl+Enter)", variant="success", id="btn-send-studio")
            yield Label("Select Notebook (KnowledgeStore Grounding)")
            yield SelectionList(id="chat-notebook-list")

class AgentStudioChatScreen(ModalScreen):
    BINDINGS = [("ctrl+j", "submit_chat", "Send Chat (Ctrl+Enter)")]
    
    def compose(self) -> ComposeResult:
        with Horizontal(id="studio-chat-layout"):
            yield ChatDashboardPane()
            yield ChatArenaPane()
            yield ChatBuilderPane()
        
    def on_mount(self) -> None:
        self.active_chat_name = "New_Session"
        self.local_profiles = {}
        self.session_task = None
        self.roster = []
        
        # Initialize dictionary immediately
        self._save_dict_profile()
        
        try:
            from maccre_core.workbook_data import load_agent_names_from_library, load_model_ids
            
            # Populate Models
            sel_model = self.query_one("#studio-model", Select)
            models = load_model_ids()
            sel_model.set_options([(m, m) for m in models])
            
            roster = load_agent_names_from_library(self.app.active_project)
            if self.app.active_project != "GLOBAL":
                roster.extend(load_agent_names_from_library("GLOBAL"))
            self.roster = list(set(roster))
            
            sel_agents = self.query_one("#studio-select-agents", SelectionList)
            for agent in sorted(self.roster):
                sel_agents.add_option((agent, agent))
                
            self._refresh_history_list()
        except Exception:
            pass
            
        self._poll_timer = self.set_interval(0.5, self._poll_chat_bus)
        
    def _poll_chat_bus(self):
        if not getattr(self, "active_job_id", None) or not getattr(self, "message_bus", None):
            return
            
        try:
            messages = self.message_bus.poll(["MACCRE.CHAT"])
            if messages:
                for topic, payload in messages:
                    if payload.get("job_id") == self.active_job_id:
                        agent_name = payload.get("agent_name", "Agent")
                        content = payload.get("content", "")
                        
                        log = self.query_one("#chat-arena-log", RichLog)
                        log.write(f"\n[bold blue]{agent_name}:[/bold blue] {content}")
                        
                        indicator = self.query_one("#chat-typing-indicator", Label)
                        indicator.update("")
        except Exception:
            pass

    def _refresh_history_list(self) -> None:
        try:
            import os
            from maccre_core.utils.path_resolver import get_datacenter_path
            ledgers_dir = get_datacenter_path("03_Agent_Ledgers", "live_sessions")
            if not ledgers_dir.exists():
                return
                
            sel_hist = self.query_one("#studio-history-list", SelectionList)
            sel_hist.clear_options()
            
            for file in ledgers_dir.glob("*.md"):
                sel_hist.add_option((file.stem, str(file)))
        except Exception:
            pass
            
    @on(SelectionList.SelectedChanged, "#studio-select-agents")
    def on_agents_selected(self, event: SelectionList.SelectedChanged) -> None:
        sel_config = self.query_one("#studio-configure-agent", SelectionList)
        sel_config.clear_options()
        
        from maccre_core.agent_library import get_agent_store
        
        for agent in event.selection_list.selected:
            sel_config.add_option((agent, agent))
            if agent not in self.local_profiles:
                # Load from DB initially
                store = get_agent_store(self.app.active_project)
                all_agents = store.load_all()
                profile = next((a for a in all_agents if a.get("agent_name") == agent or a.get("AGENT_NAME") == agent), None)
                if not profile:
                    store = get_agent_store("GLOBAL")
                    all_agents = store.load_all()
                    profile = next((a for a in all_agents if a.get("agent_name") == agent or a.get("AGENT_NAME") == agent), None)
                self.local_profiles[agent] = profile or {}
                
        self._save_dict_profile()
                
    @on(SelectionList.SelectedChanged, "#studio-configure-agent")
    def on_configure_agent_selected(self, event: SelectionList.SelectedChanged) -> None:
        if not event.selection_list.selected:
            return
            
        agent = event.selection_list.selected[-1] # Enforce single select
        sel_config = self.query_one("#studio-configure-agent", SelectionList)
        
        # Stop event loop recursion
        if len(sel_config.selected) != 1 or sel_config.selected[0] != agent:
            with sel_config.prevent(SelectionList.SelectedChanged):
                sel_config.deselect_all()
                sel_config.select(agent)
        
        profile = self.local_profiles.get(agent, {})
        if profile:
            # Prevent handlers from triggering save while loading
            with self.prevent(Select.Changed, Input.Changed, Switch.Changed):
                self.query_one("#studio-temp", Input).value = str(profile.get("temperature", 1.0))
                model_val = profile.get("model")
                if model_val:
                    try:
                        self.query_one("#studio-model", Select).value = model_val
                    except Exception:
                        pass
                
                ai_options = profile.get("ai_studio_options", {})
                
                thinking_val = ai_options.get("thinking_level", "high")
                try:
                    self.query_one("#studio-thinking", Select).value = thinking_val
                except Exception:
                    pass
                    
                media_val = ai_options.get("media_resolution", "default")
                try:
                    self.query_one("#studio-media", Select).value = media_val
                except Exception:
                    pass
                    
                self.query_one("#studio-structured", Switch).value = ai_options.get("structured_outputs", False)
                self.query_one("#studio-code", Switch).value = ai_options.get("code_execution", False)
                self.query_one("#studio-function", Switch).value = ai_options.get("function_calling", False)
                
                self.query_one("#studio-gsearch", Switch).value = ai_options.get("triple_google", True)
                self.query_one("#studio-bsearch", Switch).value = ai_options.get("triple_brave", False)
                self.query_one("#studio-msearch", Switch).value = ai_options.get("triple_local", False)
                self.query_one("#studio-exclusionary", Switch).value = ai_options.get("exclusionary", False)
                self.query_one("#studio-funnel", Switch).value = ai_options.get("funnel", False)
                self.query_one("#studio-gmaps", Switch).value = ai_options.get("google_maps", False)
                self.query_one("#studio-url", Switch).value = ai_options.get("url_context", False)
                
                self.query_one("#studio-stop", Input).value = ai_options.get("stop_sequence", "")
                self.query_one("#studio-output-len", Input).value = str(ai_options.get("output_length", "65536"))
                self.query_one("#studio-top-p", Input).value = str(ai_options.get("top_p", "0.95"))
            
    @on(Select.Changed, "#studio-model")
    def on_model_changed(self, event: Select.Changed) -> None:
        if event.value != Select.BLANK:
            self._update_local_profile("model", event.value)
            
    @on(Select.Changed, "#studio-thinking")
    def on_thinking_changed(self, event: Select.Changed) -> None:
        if event.value != Select.BLANK:
            sel_config = self.query_one("#studio-configure-agent", SelectionList)
            if sel_config.selected:
                agent = sel_config.selected[0]
                if agent in self.local_profiles:
                    if "ai_studio_options" not in self.local_profiles[agent]:
                        self.local_profiles[agent]["ai_studio_options"] = {}
                    self.local_profiles[agent]["ai_studio_options"]["thinking_level"] = event.value
                    self._save_dict_profile()
                    
    @on(Switch.Changed, "#studio-gsearch")
    @on(Switch.Changed, "#studio-bsearch")
    @on(Switch.Changed, "#studio-msearch")
    @on(Switch.Changed, "#studio-exclusionary")
    @on(Switch.Changed, "#studio-funnel")
    @on(Switch.Changed, "#studio-gmaps")
    @on(Switch.Changed, "#studio-url")
    @on(Switch.Changed, "#studio-structured")
    @on(Switch.Changed, "#studio-code")
    @on(Switch.Changed, "#studio-function")
    def on_studio_switch_changed(self, event: Switch.Changed) -> None:
        sel_config = self.query_one("#studio-configure-agent", SelectionList)
        if sel_config.selected:
            agent = sel_config.selected[0]
            if agent in self.local_profiles:
                if "ai_studio_options" not in self.local_profiles[agent]:
                    self.local_profiles[agent]["ai_studio_options"] = {}
                    
                s_id = event.switch.id
                key_map = {
                    "studio-structured": "structured_outputs",
                    "studio-code": "code_execution",
                    "studio-function": "function_calling",
                    "studio-gsearch": "triple_google",
                    "studio-bsearch": "triple_brave",
                    "studio-msearch": "triple_local",
                    "studio-exclusionary": "exclusionary",
                    "studio-funnel": "funnel",
                    "studio-gmaps": "google_maps",
                    "studio-url": "url_context"
                }
                if s_id in key_map:
                    self.local_profiles[agent]["ai_studio_options"][key_map[s_id]] = event.value
                self._save_dict_profile()

    @on(Input.Changed, "#studio-stop")
    @on(Input.Changed, "#studio-output-len")
    @on(Input.Changed, "#studio-top-p")
    def on_studio_adv_changed(self, event: Input.Changed) -> None:
        sel_config = self.query_one("#studio-configure-agent", SelectionList)
        if sel_config.selected:
            agent = sel_config.selected[0]
            if agent in self.local_profiles:
                if "ai_studio_options" not in self.local_profiles[agent]:
                    self.local_profiles[agent]["ai_studio_options"] = {}
                
                i_id = event.input.id
                key_map = {
                    "studio-stop": "stop_sequence",
                    "studio-output-len": "output_length",
                    "studio-top-p": "top_p"
                }
                if i_id in key_map:
                    val = event.value
                    if i_id == "studio-output-len":
                        try:
                            val = int(val)
                        except: pass
                    elif i_id == "studio-top-p":
                        try:
                            val = float(val)
                        except: pass
                    self.local_profiles[agent]["ai_studio_options"][key_map[i_id]] = val
                self._save_dict_profile()
                
    @on(Select.Changed, "#studio-media")
    def on_studio_media_changed(self, event: Select.Changed) -> None:
        if event.value != Select.BLANK:
            sel_config = self.query_one("#studio-configure-agent", SelectionList)
            if sel_config.selected:
                agent = sel_config.selected[0]
                if agent in self.local_profiles:
                    if "ai_studio_options" not in self.local_profiles[agent]:
                        self.local_profiles[agent]["ai_studio_options"] = {}
                    self.local_profiles[agent]["ai_studio_options"]["media_resolution"] = event.value
                    self._save_dict_profile()
            
    @on(Input.Changed, "#studio-temp")
    def on_temp_changed(self, event: Input.Changed) -> None:
        self._update_local_profile("temperature", event.value)
        
    def _update_local_profile(self, key: str, value: str):
        sel_config = self.query_one("#studio-configure-agent", SelectionList)
        if sel_config.selected:
            agent = sel_config.selected[0]
            if agent in self.local_profiles:
                if key == "temperature":
                    try:
                        self.local_profiles[agent][key] = float(value)
                    except ValueError:
                        pass
                else:
                    self.local_profiles[agent][key] = value
                self._save_dict_profile()

    @on(Button.Pressed, "#btn-studio-edit-instructions")
    def action_studio_edit_instructions(self) -> None:
        sel_config = self.query_one("#studio-configure-agent", SelectionList)
        if not sel_config.selected:
            return
        agent = sel_config.selected[0]
        if agent not in self.local_profiles:
            return
            
        current_text = self.local_profiles[agent].get("system_prompt", "")
        def save_instructions(text: str | None):
            if text is not None:
                self.local_profiles[agent]["system_prompt"] = text
                btn = self.query_one("#btn-studio-edit-instructions", Button)
                btn.label = "Edit System Instructions (Saved)"
                btn.variant = "success"
                self._save_dict_profile()
                
        # Import SystemInstructionsModal from wherever it is defined
        from maccre_tui.nexus_plex import SystemInstructionsModal
        self.app.push_screen(SystemInstructionsModal(current_text), save_instructions)
        
    @on(Input.Submitted, "#chat-rename-input")
    def on_chat_renamed(self, event: Input.Submitted) -> None:
        new_name = event.value.strip()
        if new_name:
            self.active_chat_name = new_name
            self.notify(f"Chat renamed to: {self.active_chat_name}")
            self._save_dict_profile()
            
    def _save_dict_profile(self) -> str:
        import json
        from maccre_core.utils.path_resolver import get_datacenter_path
        ledgers_dir = get_datacenter_path("03_Agent_Ledgers", f"studio_session_{self.active_chat_name}")
        ledgers_dir.mkdir(parents=True, exist_ok=True)
        
        dict_path = ledgers_dir / f"{self.active_chat_name}-dictionary.dict"
        try:
            with open(dict_path, "w", encoding="utf-8") as f:
                json.dump(self.local_profiles, f, indent=4)
            return str(dict_path)
        except Exception as e:
            self.notify(f"Failed to save dictionary: {e}", severity="error")
            return ""

    @on(Button.Pressed, "#btn-start-studio-chat")
    def action_start_chat(self, event: Button.Pressed) -> None:
        sel_agents = self.query_one("#studio-select-agents", SelectionList).selected
        if not sel_agents:
            self.notify("Select at least one agent to start chat.", severity="warning")
            return
            
        dict_path = self._save_dict_profile()
        agent_name = sel_agents[0]
        
        import sqlite3
        import os
        import sys
        import subprocess
        from pathlib import Path
        from maccre_core.utils.path_resolver import get_datacenter_path
        
        job_id = f"studio_session_{self.active_chat_name}"
        self.active_job_id = job_id
        payload_path = str(get_datacenter_path(f"02_Dynamic_Context/{job_id}_payload.txt"))
        Path(payload_path).parent.mkdir(parents=True, exist_ok=True)
        Path(payload_path).write_text("[SYSTEM] WAIT_FOR_USER", encoding="utf-8")
        
        os.environ["MACCRE_ACTIVE_PROJECT"] = self.app.active_project
        db_path = get_datacenter_path("swarm_queue.db")
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        
        with sqlite3.connect(db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS task_queue (
                    id INTEGER PRIMARY KEY,
                    job_id TEXT,
                    payload_path TEXT,
                    source_payload_path TEXT DEFAULT '',
                    current_node TEXT,
                    lock_status TEXT DEFAULT 'open',
                    locked_by TEXT,
                    actual_cost REAL DEFAULT 0.0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    loop_iteration_count INTEGER DEFAULT 0,
                    completed_at TIMESTAMP
                )
            """)
            conn.execute(
                "INSERT OR REPLACE INTO task_queue (job_id, current_node, payload_path, lock_status) VALUES (?, ?, ?, ?)",
                (job_id, agent_name, payload_path, "open")
            )
            conn.commit()

        env = os.environ.copy()
        
        root_dir = str(Path(__file__).parent.parent.resolve())
        env["PYTHONPATH"] = root_dir + (os.pathsep + env.get("PYTHONPATH", "") if "PYTHONPATH" in env else "")
        env["MACCRE_ACTIVE_PROJECT"] = self.app.active_project
        env["MACCRE_LIVE_OVERRIDE"] = "1"
        env["MACCRE_CUSTOM_DICT"] = dict_path
            
        worker_script = str(Path(__file__).parent.parent / "maccre_core" / "orchestration" / "swarm_worker.py")
        proc = subprocess.Popen(
            [sys.executable, "-u", worker_script, agent_name],
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )
        self.session_task = proc
        
        # Initialize persistent message bus for polling
        from maccre_core.orchestration.queues import JsonFileQueue
        self.message_bus = JsonFileQueue("live_session_bus")
        # Fast forward cursor to end of file so we don't read old messages from previous sessions
        try:
            with open(self.message_bus.filepath, "r", encoding="utf-8") as f:
                f.seek(0, 2)
                self.message_bus.cursor = f.tell()
        except FileNotFoundError:
            pass
            
        self.notify("Started Studio Chat!")
        
        log = self.query_one("#chat-arena-log", RichLog)
        log.clear()
        log.write(f"\n[italic dim]System: {agent_name} has entered the chat.[/italic dim]")
        
    def action_submit_chat(self) -> None:
        self._send_chat_message()

    @on(Button.Pressed, "#btn-send-studio")
    def handle_btn_send_studio(self, event: Button.Pressed) -> None:
        self._send_chat_message()

    def _send_chat_message(self):
        inp = self.query_one("#chat-arena-input", TextArea)
        msg = inp.text.strip()
        if not msg:
            return
            
        log = self.query_one("#chat-arena-log", RichLog)
        log.write(f"\n[bold green]You:[/bold green] {msg}")
        inp.text = ""
        
        sel_agents = self.query_one("#studio-select-agents", SelectionList).selected
        if not sel_agents:
            return
            
        agent_name = sel_agents[0]
        
        indicator = self.query_one("#chat-typing-indicator", Label)
        indicator.update(f"{agent_name} is typing...")
        
        from maccre_core.orchestration.queues import JsonFileQueue
        import time
        
        message_bus = JsonFileQueue("live_session_bus")
        payload = {
            "job_id": getattr(self, "active_job_id", ""),
            "speaker": "User",
            "text": msg
        }
        message_bus.publish(f"MACCRE.ROUTE.{agent_name}", payload)
        
    @on(Button.Pressed, "#btn-close-studio-chat")
    def action_close(self, event: Button.Pressed) -> None:
        self.dismiss(None)
        
    @on(Button.Pressed, "#btn-expand-input")
    def toggle_expand(self, event: Button.Pressed) -> None:
        inp = self.query_one("#chat-arena-input", TextArea)
        if inp.has_class("-expanded"):
            inp.remove_class("-expanded")
            event.button.label = "Expand"
        else:
            inp.add_class("-expanded")
            event.button.label = "Collapse"

class NexusChat(Vertical):
    def compose(self) -> ComposeResult:
        with Horizontal(id="nexus-header-row"):
            yield Label("Nexus Copilot", classes="pane-title")
            yield Button("Copy", id="btn-copy-nexus")
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
        yield Label("Agent Builder", classes="pane-title")
        yield Button("Edit Agent", variant="warning", id="btn-open-edit-agent", classes="top-edit-btn")
        yield Button("Edit MacroNode", variant="warning", id="btn-open-edit-macro", classes="top-edit-btn")
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
        with Vertical(id="triple-index-box", classes="form-group-box"):
            yield Label("Triple Index Search", classes="form-group-title")
            with Horizontal(classes="form-row"):
                yield Label("Grounding with Google Search")
                yield Switch(value=True, id="ab-gsearch")
            with Horizontal(classes="form-row"):
                yield Label("Grounding with Brave Search")
                yield Switch(value=False, id="ab-bsearch")
            with Horizontal(classes="form-row"):
                yield Label("Grounding with Local Memory")
                yield Switch(value=False, id="ab-msearch")
            with Horizontal(classes="form-row"):
                yield Label("Exclusionary Search")
                yield Switch(value=False, id="ab-exclusionary", disabled=True)
            with Horizontal(classes="form-row"):
                yield Label("Funnel Search")
                yield Switch(value=False, id="ab-funnel", disabled=True)
            yield Label("Information")
            yield RichLog(id="search-info-panel", wrap=True, highlight=True, markup=True)

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

    @on(Switch.Changed, "#ab-gsearch")
    @on(Switch.Changed, "#ab-bsearch")
    @on(Switch.Changed, "#ab-msearch")
    @on(Switch.Changed, "#ab-exclusionary")
    @on(Switch.Changed, "#ab-funnel")
    def on_search_toggle_changed(self, event: Switch.Changed) -> None:
        gsearch = self.query_one("#ab-gsearch", Switch).value
        bsearch = self.query_one("#ab-bsearch", Switch).value
        msearch = self.query_one("#ab-msearch", Switch).value
        exc = self.query_one("#ab-exclusionary", Switch)
        fun = self.query_one("#ab-funnel", Switch)
        info = self.query_one("#search-info-panel", RichLog)

        # Count active groundings
        count = sum([gsearch, bsearch, msearch])

        # Enable/Disable advanced mode based on count
        if count < 2:
            exc.disabled = True
            exc.value = False
            fun.disabled = True
            fun.value = False
        else:
            exc.disabled = False
            fun.disabled = False

        # Mutually exclusive logic
        if event.control.id == "ab-exclusionary" and event.value:
            fun.value = False
        elif event.control.id == "ab-funnel" and event.value:
            exc.value = False

        # Update Info Panel
        info.clear()
        if exc.value:
            info.write("[bold red]Adversarial Topology Active (Exclusionary Search)[/bold red]")
            info.write("Logic: Google establishes consensus. Brave finds non-overlapping, buried intelligence.")
            info.write("FinOps: [bold yellow]High Cost[/bold yellow] (Multi-step sequential token burn).")
            info.write("Fallback: If exclusion yields 0 results, safely falls back to Additive Merging.")
        elif fun.value:
            info.write("[bold cyan]Funnel Topology Active (Iterative Source Batching)[/bold cyan]")
            info.write("Logic: Google finds broad sources. Entities are extracted and passed to Brave for deep-dives.")
            info.write("FinOps: [bold yellow]High Cost[/bold yellow] (Entity extraction intermediate step).")
        elif count >= 2:
            info.write("[bold green]Additive Merging Active[/bold green]")
            info.write("Logic: Parallel API calls are executed and merged into a single deduplicated context window.")
            info.write("FinOps: Medium-High Cost (Parallel API fees and wider context window).")
        elif count == 1:
            info.write("Standard Single Index Grounding active.")
            info.write("FinOps: Low Cost.")
        else:
            info.write("No Search Grounding selected.")


class CreatePayloadModal(ModalScreen[dict]):
    """Modal for creating a payload (text + files) before launching a flow."""

    def __init__(self, existing_text: str = "", existing_files: str = "", **kwargs) -> None:
        super().__init__(**kwargs)
        self.existing_text = existing_text
        self.existing_files = existing_files

    def compose(self) -> ComposeResult:
        with Container(id="payload-modal-outer"):
            yield Label("━━━ Create Payload ━━━", id="payload-modal-title")

            # Text Payload Section
            with Horizontal(classes="payload-toggle-row"):
                yield Switch(value=True, id="sw-text-payload")
                yield Label("Text Payload", classes="payload-toggle-label")
            yield TextArea(self.existing_text, id="payload-text-area", language=None)
            with Horizontal(classes="payload-btn-row"):
                yield Button("Paste from Clipboard", variant="default", id="btn-paste-text")

            # File Payload Section
            with Horizontal(classes="payload-toggle-row"):
                yield Switch(value=False, id="sw-file-payload")
                yield Label("File Payload (comma-separated paths)", classes="payload-toggle-label")
            yield Input(value=self.existing_files, placeholder="path/to/file1.md, path/to/file2.txt", id="payload-file-input")
            with Horizontal(classes="payload-btn-row"):
                yield Button("Paste from Clipboard", variant="default", id="btn-paste-files")

            # Bottom Buttons
            with Horizontal(id="payload-modal-buttons"):
                yield Button("Cancel", variant="error", id="btn-payload-cancel")
                yield Button("Set Payload", variant="success", id="btn-payload-set")

    @on(Button.Pressed, "#btn-paste-text")
    def paste_text(self) -> None:
        try:
            import pyperclip  # noqa: PLC0415
            text = pyperclip.paste()
            if text:
                ta = self.query_one("#payload-text-area", TextArea)
                ta.text = ta.text + "\n" + text if ta.text else text
        except Exception:
            pass

    @on(Button.Pressed, "#btn-paste-files")
    def paste_files(self) -> None:
        try:
            import pyperclip  # noqa: PLC0415
            text = pyperclip.paste()
            if text:
                inp = self.query_one("#payload-file-input", Input)
                inp.value = inp.value + ", " + text if inp.value else text
        except Exception:
            pass

    @on(Button.Pressed, "#btn-payload-cancel")
    def cancel(self) -> None:
        self.dismiss(None)

    @on(Button.Pressed, "#btn-payload-set")
    def set_payload(self) -> None:
        text_enabled = self.query_one("#sw-text-payload", Switch).value
        file_enabled = self.query_one("#sw-file-payload", Switch).value
        text_content = self.query_one("#payload-text-area", TextArea).text.strip() if text_enabled else ""
        file_paths = self.query_one("#payload-file-input", Input).value.strip() if file_enabled else ""

        result = {
            "text_enabled": text_enabled,
            "file_enabled": file_enabled,
            "text": text_content,
            "files": file_paths,
        }
        self.dismiss(result)



class FlowRegistryModalScreen(ModalScreen[dict | None]):
    """Modal to save/load complete flow layouts from flow_registry.db"""
    
    CSS = """
    FlowRegistryModalScreen {
        align: center middle;
    }
    #reg-dialog {
        width: 80;
        height: auto;
        max-height: 90vh;
        background: $panel;
        border: solid $primary;
        padding: 1 2;
    }
    .reg-section {
        border: solid $secondary;
        padding: 1;
        margin-bottom: 1;
    }
    #reg-save-desc {
        height: 5;
    }
    """
    
    def __init__(self, flows: list[dict], **kwargs):
        super().__init__(**kwargs)
        self.flows = flows
        
    def compose(self) -> ComposeResult:
        with Vertical(id="reg-dialog"):
            yield Label("Flow Registry", classes="pane-title")
            
            with Vertical(classes="reg-section"):
                yield Label("Save Current Flow", classes="node-cfg-title")
                yield Input(placeholder="Flow Name", id="reg-save-name")
                yield TextArea(id="reg-save-desc")
                yield Button("Save Flow", variant="success", id="btn-reg-save")
                
            with Vertical(classes="reg-section"):
                yield Label("Load Flow", classes="node-cfg-title")
                opts = [(f["name"], f["name"]) for f in self.flows]
                yield Select(opts, prompt="Select Flow...", id="reg-load-select")
                yield Static("", id="reg-load-desc", classes="info-panel-body")
                yield Button("Load Flow", variant="primary", id="btn-reg-load")
                
            with Horizontal():
                yield Button("Cancel", variant="error", id="btn-reg-cancel")

    @on(Select.Changed, "#reg-load-select")
    def on_select(self, event: Select.Changed):
        desc = self.query_one("#reg-load-desc", Static)
        if not event.value or event.value == Select.BLANK:
            desc.update("")
            return
        for f in self.flows:
            if f["name"] == str(event.value):
                desc.update(f"[b]Description:[/b]\n{f['description']}")
                break

    @on(Button.Pressed, "#btn-reg-save")
    def action_save(self):
        name = self.query_one("#reg-save-name", Input).value.strip()
        desc = self.query_one("#reg-save-desc", TextArea).text.strip()
        if name:
            self.dismiss({"action": "save", "name": name, "description": desc})

    @on(Button.Pressed, "#btn-reg-load")
    def action_load(self):
        sel = self.query_one("#reg-load-select", Select)
        if sel.value and sel.value != Select.BLANK:
            self.dismiss({"action": "load", "name": str(sel.value)})

    @on(Button.Pressed, "#btn-reg-cancel")
    def action_cancel(self):
        self.dismiss(None)


class NodeConfigModal(ModalScreen[dict | None]):
    """Modal to configure payload, routing, tools, and prompts for a specific instance of a MacroNode."""
    
    CSS = """
    NodeConfigModal {
        align: center middle;
        background: $background 80%;
    }
    #node-config-container {
        width: 95%;
        max-width: 160;
        height: auto;
        max-height: 95vh;
        background: $surface;
        border: solid $primary;
        padding: 1 2;
    }
    .node-cfg-title {
        text-align: center;
        text-style: bold;
        color: $accent;
        margin-bottom: 1;
    }
    .node-cfg-row {
        height: auto;
        margin-top: 1;
        margin-bottom: 1;
    }
    .category-title {
        text-style: bold;
        color: #e6edf3;
        margin-top: 1;
        margin-bottom: 1;
    }
    #cfg-custom-instructions {
        height: 6;
        border: solid $panel;
    }
    #cfg-payload-injection {
        height: 6;
        border: solid $panel;
    }
    #cfg-agent-tools-container {
        height: 12;
        margin-bottom: 1;
    }
    .tool-button-group {
        height: 3;
        margin-top: 1;
    }
    .tool-button-group Button {
        min-width: 12;
    }
    #cfg-agent-row {
        height: 3;
        margin-bottom: 1;
    }
    #node-tools-input {
        width: 1fr;
    }
    """
    
    def __init__(self, node_name: str, current_payload_mode: str = "Unified Ledger", current_instructions: str = "", active_project: str = "", agents_in_node: list[str] = None, baked_tools: dict = None, current_agent_tools_overrides: dict = None, **kwargs):
        super().__init__(**kwargs)
        self.node_name = node_name
        self.current_payload_mode = current_payload_mode
        self.current_instructions = current_instructions
        self.active_project = active_project
        self.agents_in_node = agents_in_node or []
        self.baked_tools = baked_tools or {}
        self.current_agent_tools_overrides = current_agent_tools_overrides or {}
        self.agent_profiles = {}
        
        if self.agents_in_node and self.active_project:
            try:
                from maccre_core.agent_library import get_agent_store
                store = get_agent_store(self.active_project)
                for p in store.load_all():
                    aname = (p.get("agent_name") or p.get("AGENT_NAME", "")).strip()
                    if aname in self.agents_in_node:
                        self.agent_profiles[aname] = p
            except Exception:
                pass
        
    def compose(self) -> ComposeResult:
        with Vertical(id="node-config-container"):
            yield Label(f"Configure Node: {self.node_name}", classes="node-cfg-title")
            with Horizontal(classes="node-cfg-row"):
                yield Label("Custom Node Name: ")
                yield Input(value=self.node_name, id="cfg-node-name")
                
            with Horizontal(classes="node-cfg-row"):
                yield Label("Ledger Routing Mode: ")
                yield Select(
                    [("Unified Ledger", "Unified Ledger"), ("Preceding Node Only", "Preceding Node Only")],
                    value=self.current_payload_mode,
                    id="cfg-payload-mode"
                )

            if self.agents_in_node:
                yield Label("Agent Tool Configuration", classes="category-title")
                with Horizontal(id="cfg-agent-row"):
                    yield Select(
                        [(a, a) for a in self.agents_in_node],
                        prompt="Select Agent to configure...",
                        id="cfg-agent-select"
                    )
                    yield Input(value="", id="node-tools-input", disabled=True)
                    
                with Horizontal(id="cfg-agent-tools-container"):
                    with Vertical(classes="flow-select-group"):
                        yield Label("[dim]Available Tools[/dim]")
                        common_tools = ["read_file", "write_file", "list_dir", "web_search", "hybrid_search", "execute_sql", "execute_terminal"]
                        yield Select(
                            [(t, t) for t in common_tools],
                            prompt="Select a tool to add...",
                            id="tool-select",
                            disabled=True
                        )
                        with Horizontal(classes="tool-button-group"):
                            yield Button("Add Tool", id="btn-add-tool", variant="primary", disabled=True, classes="flow-add-btn")
                            yield Button("Clear", id="btn-clear-tools", variant="error", disabled=True, classes="flow-add-btn")
                    
                    with Vertical(id="tool-info-panel", classes="info-panel-container"):
                        yield Label("Tool Details", classes="info-panel-title")
                        yield Static("[dim]Select a tool to view details.[/dim]", id="tool-info-body", classes="info-panel-body")

            yield Label("Node-Specific Custom Instructions (Appended to System Prompt):", classes="node-cfg-row")
            yield TextArea(text=self.current_instructions, id="cfg-custom-instructions")
            
            yield Label("Node-Specific Payload Injection (Overrides Flow Payload):", classes="node-cfg-row")
            yield TextArea(text="", id="cfg-payload-injection") # TODO: load from FlowStep if we add it

            
            with Horizontal(id="payload-modal-buttons"):
                yield Button("Cancel", variant="error", id="btn-cfg-cancel")
                yield Button("Save", variant="success", id="btn-cfg-save")
                
    @on(Select.Changed, "#cfg-agent-select")
    def on_agent_selected(self, event: Select.Changed) -> None:
        agent_name = str(event.value) if event.value and event.value != Select.BLANK else ""
        tool_select = self.query_one("#tool-select", Select)
        btn_add = self.query_one("#btn-add-tool", Button)
        btn_clear = self.query_one("#btn-clear-tools", Button)
        tools_input = self.query_one("#node-tools-input", Input)
        
        if not agent_name:
            tool_select.disabled = True
            btn_add.disabled = True
            btn_clear.disabled = True
            tools_input.disabled = True
            tools_input.value = ""
            return
            
        tool_select.disabled = False
        btn_add.disabled = False
        btn_clear.disabled = False
        tools_input.disabled = False
        
        prof = self.agent_profiles.get(agent_name, {})
        # Precedence: Overrides -> Baked Tools -> Base Agent Profile
        if agent_name in self.current_agent_tools_overrides:
            tools = self.current_agent_tools_overrides[agent_name]
        elif agent_name in self.baked_tools:
            tools = self.baked_tools[agent_name]
        else:
            tools = prof.get("tools_allowed", "")
            
        assigned = [t.strip() for t in tools.split(",")] if tools and tools != "none" else []
        tools_input.value = ",".join(assigned) if assigned else "none"

    @on(Input.Changed, "#node-tools-input")
    def on_tools_input_changed(self, event: Input.Changed) -> None:
        agent_select = self.query_one("#cfg-agent-select", Select)
        if agent_select and agent_select.value and agent_select.value != Select.BLANK:
            self.current_agent_tools_overrides[str(agent_select.value)] = event.input.value.strip() or "none"

    @on(Button.Pressed, "#btn-add-tool")
    def add_tool(self):
        sel = self.query_one("#tool-select", Select)
        inp = self.query_one("#node-tools-input", Input)
        if sel.value and sel.value != Select.BLANK and not inp.disabled:
            current = [t.strip() for t in inp.value.split(",") if t.strip() and t.strip() != "none"]
            if str(sel.value) not in current:
                current.append(str(sel.value))
                inp.value = ",".join(current)
                
    @on(Button.Pressed, "#btn-clear-tools")
    def clear_tools(self):
        inp = self.query_one("#node-tools-input", Input)
        if not inp.disabled:
            inp.value = "none"
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
            "web_search": "Searches the live web for current information.\n\n[bold warning]Note:[/bold warning] Standard Google Search Grounding is configured globally in the Agent Builder. This tool is primarily for local agent Brave searches or combined Brave/Google dual-search.",
            "hybrid_search": "Semantic vector search against the local Sovereign Memory Chroma DB, combined with lexical BM25.\n\n[bold warning]Note:[/bold warning] Standard Google Search Grounding is configured globally in the Agent Builder. This tool is primarily for local agent Brave searches or combined Brave/Google dual-search.",
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
        body.update("\n".join(info))

    @on(Button.Pressed, "#btn-cfg-cancel")
    def cancel(self):
        self.dismiss(None)
        
    @on(Button.Pressed, "#btn-cfg-save")
    def save(self):
        new_name = self.query_one("#cfg-node-name", Input).value.strip()
        new_mode = self.query_one("#cfg-payload-mode", Select).value
        new_instr = self.query_one("#cfg-custom-instructions", TextArea).text.strip()
        
        # Ensure the final edit is captured if the user didn't blur the input
        try:
            agent_select = self.query_one("#cfg-agent-select", Select)
            if agent_select and agent_select.value and agent_select.value != Select.BLANK:
                tools_val = self.query_one("#node-tools-input", Input).value.strip() or "none"
                agent_name = str(agent_select.value)
                self.current_agent_tools_overrides[agent_name] = tools_val
        except Exception:
            pass
            
        self.dismiss({"name": new_name, "payload_mode": new_mode, "custom_instructions": new_instr, "agent_tools_overrides": self.current_agent_tools_overrides})



class FlowExecutionPanel(Vertical):
    def compose(self) -> ComposeResult:
        # Flow Execution Top Panel
        with Vertical(classes="panel-section", id="flow-execution-top"):
            yield Label("Flow Execution", classes="pane-title")
            with Horizontal(id="main-flow-load-row", classes="flow-controls"):
                yield Select([], prompt="Load Flow from Registry...", id="main-flow-load-select")
            with Horizontal(id="flow-select-row"):
                with Vertical(classes="flow-select-group"):
                    yield Label("MacroNode")
                    yield Select([], prompt="Select MacroNode…", id="macro-select")
                    with Vertical(id="flow-macro-info", classes="info-panel-container"):
                        yield Label("MacroNode Details", classes="info-panel-title")
                        yield RichLog(id="macro-info-body", classes="info-panel-body", wrap=True, markup=True)
                    yield Button("Add MacroNode", variant="primary", id="btn-add-macro", classes="flow-add-btn")
                with Vertical(classes="flow-select-group"):
                    yield Label("Agent")
                    yield Select([], prompt="Select Agent…", id="agent-select")
                    with Vertical(id="flow-agent-info", classes="info-panel-container"):
                        yield Label("Agent Details", classes="info-panel-title")
                        yield RichLog(id="agent-info-body", classes="info-panel-body", wrap=True, markup=True)
                    yield Button("Add Agent", variant="success", id="btn-add-agent", classes="flow-add-btn")
                with Vertical(classes="flow-select-group"):
                    yield Label("Special Node")
                    yield Select([], prompt="Select Special Node…", id="special-select")
                    with Vertical(id="flow-special-info", classes="info-panel-container"):
                        yield Label("Special Details", classes="info-panel-title")
                        yield Static("[dim]Select a Special Node above to see its description.[/dim]", id="special-info-body", classes="info-panel-body")
                    yield Button("Add Special", variant="warning", id="btn-add-special", classes="flow-add-btn")

            with Horizontal(classes="flow-controls"):
                yield Button("Launch Flow", variant="success", id="btn-launch-flow")
                yield Button("Stop Flow", variant="error", id="btn-stop-flow", disabled=True)
                yield Button("Resume Flow", variant="success", id="btn-resume-flow", disabled=True)
                yield Button("Rewind Flow", variant="warning", id="btn-rewind-flow", disabled=False)
                yield Button("Create Payload", variant="primary", id="btn-create-payload")
                yield Button("Session Manager", variant="primary", id="btn-session-manager")

            yield Label("Active Flow Sequence", id="active-flow-sequence-label")
            with Horizontal(id="active-flow-sequence", classes="flow-controls"):
                yield Static("No flow loaded.", classes="flow-seq-text")
                
            with Horizontal(classes="flow-controls", id="flow-line-actions"):
                yield Button("Remove Last Node", variant="warning", id="btn-remove-last")
                yield Button("Clear Flow", variant="error", id="btn-clear-flow")
                yield Input(placeholder="Name Session...", id="main-name-session-input", disabled=True)

        # Flow Monitor Panel
        with Vertical(classes="panel-section", id="flow-monitor-section"):
            with Horizontal(id="flow-monitor-header-row"):
                yield Label("Flow Monitor", classes="pane-title")
                yield Button("Copy", id="btn-copy-monitor")
            yield Label("Stage: [dim]Idle[/dim]", id="flow-stage-readout", classes="flow-stage-readout")
            yield RichLog(id="flow-execution-log", wrap=True, highlight=True, markup=True)

            # VCR Transport + Instruction Panel
            with Horizontal(id="vcr-transport-row"):
                yield Button("⏸", id="btn-vcr", classes="vcr-btn vcr-btn--idle", disabled=True)
                yield Static(
                    "[dim]While paused: click a node → ○ radios appear → "
                    "left = inject before (+ Live Chat) · right = inject after (fork) → "
                    "orange arrow = open injection modal → ▶ to resume[/dim]",
                    id="vcr-instructions",
                    classes="vcr-instructions",
                )

            # Pre-flight override (hidden by default, shown on validation failure)
            yield Button(
                "⚠ Proceed Anyway", id="btn-proceed-anyway",
                variant="warning", classes="btn-proceed-anyway hidden",
            )

            with Horizontal(classes="input-row"):
                yield Input(placeholder="Inject context to flow...", id="fe-input")
                yield Button("↗", id="btn-expand-input", variant="primary", classes="btn-icon")



# ══════════════════════════════════════════════════════════════════════════════
# NEXUS_PLEX APP
# ══════════════════════════════════════════════════════════════════════════════

class NexusPlex(App[None]):
    """MACCREv2 Command Center - Nexus_Plex v2."""

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
        self.active_flow_steps: list = []
        self._flow_cancel_event: threading.Event | None = None
        self._flow_pause_event: threading.Event | None = None
        self._pending_payload_path: str = "none"
        # VCR state: "idle" | "running" | "paused"
        self._vcr_state: str = "idle"
        # Time-travel state
        self._paused_selected_node: int | None = None
        self._paused_radio_side: str = ""  # "left" | "right" | ""
        self._node_payloads: list[str] = []  # captured output path per completed step
        self._injected_context: str = ""  # text from context injection modal
        self._hitl_job_id: str = ""  # job_id for HITL pause resume
        # Flow history tracking (duplicate-run guard)
        self._flow_loaded_from_history: bool = False
        self._flow_history_job_id: str = ""
        self._flow_history_hash: str = ""
        
        self.nexus = NexusAgent(
            print_callback=self.write_nexus_log,
            get_active_project_cb=lambda: self.active_project,
            set_active_project_cb=self.set_active_project
        )

    def set_active_project(self, project_name: str) -> None:
        self.active_project = project_name
        import os
        os.environ["MACCRE_ACTIVE_PROJECT"] = project_name
        label = self.query_one("#active-project-label", Static)
        
        display_name = project_name if project_name else "SET ACTIVE PROJECT"
        
        import threading
        if self._thread_id == threading.get_ident():
            label.update(f"Project: [bold cyan]{display_name}[/bold cyan]")
        else:
            self.call_from_thread(label.update, f"Project: [bold cyan]{display_name}[/bold cyan]")
            
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

        self.set_active_project("")

        # Populate inline flow editor selects
        try:
            from maccre_core.macronode_registry import get_macronode_store
            from maccre_core.agent_library import get_agent_store
            store = get_macronode_store()
            macros = store.list_all()
            macro_sel = self.query_one("#macro-select", Select)
            if macro_sel:
                macro_sel.set_options([(m.get("name", "Unknown"), m.get("name", "Unknown")) for m in macros])
            
            agents = get_agent_store("GLOBAL").get_names()
            agent_sel = self.query_one("#agent-select", Select)
            if agent_sel:
                agent_sel.set_options([(a, a) for a in agents])
                
            special = ["MANUAL", "DET_ANCHOR", "DET_RECURSION", "DET_PAUSE", "DET_GATE", "DET_CHECKPOINT", "DET_DELAY", "DET_TRANSFORM"]
            special_sel = self.query_one("#special-select", Select)
            if special_sel:
                special_sel.set_options([(s, s) for s in special])
            self._populate_flow_registry_dropdown()
        except Exception as e:
            self.write_nexus_log(f"[red]Error populating selects: {e}[/red]")
            
        self._load_autosave_flow()


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
        self.push_screen(AgentStudioChatScreen())

    # ── Agent Builder Handlers ────────────────────────────────────────────────
    @on(Button.Pressed, "#btn-open-edit-agent")
    def action_open_edit_agent(self) -> None:
        agents = load_agent_names_from_library(self.active_project)
        def handle_edit_agent(name: str | None):
            if name:
                self._load_agent_into_builder(name)
        self.push_screen(EditAgentModal(agents), handle_edit_agent)

    @on(Button.Pressed, "#btn-open-edit-macro")
    def action_open_edit_macro(self) -> None:
        from maccre_core.macronode_registry import SQLiteMacroNodeStore, _db_path
        store = SQLiteMacroNodeStore(_db_path(self.active_project))
        templates = store.list_all()
        full_templates = []
        for t in templates:
            try:
                full_templates.append(store.load(t["name"]))
            except Exception:
                pass

        agents = load_agent_names_from_library(self.active_project)
        
        special_nodes = [
            ("MANUAL", "Live swarm intercept - pauses the task in awaiting_orders for manual resume."),
            ("DET_ANCHOR", "Entry marker - passes payload through unchanged."),
            ("DET_RECURSION", "Loop-back control with counter tracking."),
            ("DET_PAUSE", "Halts execution, sets task to paused for manual resume."),
            ("DET_GATE", "Conditional gate - blocks unless prerequisite nodes complete."),
            ("DET_CHECKPOINT", "Snapshots current payload to a checkpoint file."),
            ("DET_DELAY", "Sleeps for a configurable number of seconds."),
            ("DET_TRANSFORM", "Applies a static text wrapper/template to the payload."),
        ]

        def handle_edit_macro(result: dict | None):
            if not result:
                return
            
            name = result["name"]
            desc = result["description"]
            tpl_type = result["template_type"]
            agent_mapping = result["agent_mapping"]
            config = result["config"]
            
            existing = next((t for t in templates if t["name"] == name), None)
            
            def do_save():
                from maccre_core.orchestration.macro_factory import build_from_template
                from maccre_core.workbook_data import load_agent_roster_csv
                roster_rows = load_agent_roster_csv(self.active_project)
                global_rows = load_agent_roster_csv("GLOBAL")
                roster_dict = {}
                for r in global_rows:
                    roster_dict[str(r.get("Agent_Name", r.get("agent_name")))] = dict(r)
                for r in roster_rows:
                    roster_dict[str(r.get("Agent_Name", r.get("agent_name")))] = dict(r)
                    
                for sn in special_nodes:
                    roster_dict[sn[0]] = {"agent_name": sn[0], "system_prompt": "", "tools_allowed": "none"}
                
                try:
                    topology_rows = build_from_template(tpl_type, agent_mapping, config, roster_dict)
                except Exception as e:
                    self.app.notify(f"Error building topology: {e}", severity="error")
                    return
                
                slots = []
                for v in agent_mapping.values():
                    slots.extend(v)
                    
                store.save(
                    name=name,
                    topology_rows=topology_rows,
                    roster_rows=[],
                    description=desc,
                    is_template=True,
                    agent_slots=slots,
                    template_type=tpl_type,
                    template_config=config,
                )
                self.write_nexus_log(f"[bold green]System:[/bold green] MacroNode '{name}' saved successfully.")

            if existing:
                def handle_overwrite(confirm: bool):
                    if confirm:
                        do_save()
                self.push_screen(OverwriteConfirmModal(), handle_overwrite)
            else:
                do_save()

        self.push_screen(MacroNodeEditorModal(full_templates, agents, special_nodes), handle_edit_macro)

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
        self.query_one("#ab-bsearch", Switch).value = bool(opts.get("grounding_brave_search", False))
        self.query_one("#ab-msearch", Switch).value = bool(opts.get("grounding_local_memory", False))
        self.query_one("#ab-exclusionary", Switch).value = bool(opts.get("exclusionary_search", False))
        self.query_one("#ab-funnel", Switch).value = bool(opts.get("funnel_search", False))
        
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
        try:
            from maccre_core.agent_library import get_agent_store
            agents = get_agent_store("GLOBAL").get_names()
            
            try:
                agent_sel = self.query_one("#agent-select", Select)
                if agent_sel:
                    # Save current value if it exists
                    current_val = agent_sel.value
                    agent_sel.set_options([(a, a) for a in agents])
                    if current_val in agents:
                        agent_sel.value = current_val
            except Exception:
                pass

            try:
                edit_agent_sel = self.query_one("#edit-agent-select", Select)
                if edit_agent_sel:
                    current_edit_val = edit_agent_sel.value
                    edit_agent_sel.set_options([(a, a) for a in agents])
                    if current_edit_val in agents:
                        edit_agent_sel.value = current_edit_val
            except Exception:
                pass
                
        except Exception as e:
            self.write_nexus_log(f"[red]Error refreshing agent dropdowns: {e}[/red]")

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
            "grounding_brave_search": self.query_one("#ab-bsearch", Switch).value,
            "grounding_local_memory": self.query_one("#ab-msearch", Switch).value,
            "exclusionary_search": self.query_one("#ab-exclusionary", Switch).value,
            "funnel_search": self.query_one("#ab-funnel", Switch).value,
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
        store = get_agent_store("GLOBAL")
        
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

        existing = get_agent_store("GLOBAL").get_names()
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
    


    @on(Button.Pressed, "#btn-create-payload")
    def action_create_payload(self) -> None:
        """Open the Create Payload modal to set text/file input for the next flow run."""
        def handle_payload(result: dict | None) -> None:
            if result is None:
                return

            text = result.get("text", "")
            files = result.get("files", "")

            if not text and not files:
                self.write_agent_log("[yellow]Payload is empty - no text or files provided.[/yellow]")
                self._pending_payload_path = "none"
                return

            # Write the payload to a file in 04_Code_Artifacts
            from maccre_core.utils.path_resolver import get_datacenter_path  # noqa: PLC0415
            import uuid  # noqa: PLC0415
            payload_dir = get_datacenter_path("04_Code_Artifacts", self.active_project)
            payload_dir.mkdir(parents=True, exist_ok=True)
            payload_file = payload_dir / f"payload_{uuid.uuid4().hex[:8]}.md"

            content_parts: list[str] = []
            if text:
                content_parts.append(text)
            if files:
                content_parts.append(f"\n## Attached Files\n{files}")

            payload_file.write_text("\n".join(content_parts), encoding="utf-8")
            self._pending_payload_path = str(payload_file)
            self.write_agent_log(
                f"[green]Payload set:[/green] {payload_file.name}\n"
                f"  Text: {'✓' if text else '✗'} | Files: {'✓' if files else '✗'}"
            )

        ex_text = ""
        ex_files = ""
        if getattr(self, "_pending_payload_path", "none") != "none":
            try:
                from pathlib import Path
                p = Path(self._pending_payload_path)
                if p.exists():
                    content = p.read_text(encoding="utf-8")
                    if "\n## Attached Files\n" in content:
                        parts = content.split("\n## Attached Files\n", 1)
                        ex_text = parts[0].strip()
                        ex_files = parts[1].strip()
                    else:
                        ex_text = content.strip()
            except Exception:
                pass

        self.push_screen(CreatePayloadModal(existing_text=ex_text, existing_files=ex_files), handle_payload)

    @on(Button.Pressed, "#btn-vcr")
    def action_vcr_toggle(self) -> None:
        """Toggle pause/play - the VCR transport button."""
        if self._vcr_state == "running":
            # PAUSE the flow
            self._vcr_state = "paused"
            if self._flow_pause_event:
                self._flow_pause_event.clear()  # Block the flow worker
            vcr_btn = self.query_one("#btn-vcr", Button)
            vcr_btn.label = "▶"
            vcr_btn.remove_class("vcr-btn--running")
            vcr_btn.add_class("vcr-btn--paused")
            self.write_agent_log("[bold yellow]⏸ Flow paused.[/bold yellow]")
            self._enter_paused_state()

        elif self._vcr_state == "paused":
            # RESUME the flow
            self._vcr_state = "running"
            if self._flow_pause_event:
                self._flow_pause_event.set()  # Unblock the flow worker
            vcr_btn = self.query_one("#btn-vcr", Button)
            vcr_btn.label = "⏸"
            vcr_btn.remove_class("vcr-btn--paused")
            vcr_btn.add_class("vcr-btn--running")
            self.write_agent_log("[bold cyan]▶ Flow resumed.[/bold cyan]")
            self._exit_paused_state()

    def _set_vcr_state(self, state: str) -> None:
        """Set VCR button visual state: 'idle' | 'running' | 'paused'."""
        self._vcr_state = state
        vcr_btn = self.query_one("#btn-vcr", Button)
        vcr_btn.remove_class("vcr-btn--idle", "vcr-btn--running", "vcr-btn--paused")
        if state == "idle":
            vcr_btn.label = "⏸"
            vcr_btn.add_class("vcr-btn--idle")
            vcr_btn.disabled = True
        elif state == "running":
            vcr_btn.label = "⏸"
            vcr_btn.add_class("vcr-btn--running")
            vcr_btn.disabled = False
        elif state == "paused":
            vcr_btn.label = "▶"
            vcr_btn.add_class("vcr-btn--paused")
            vcr_btn.disabled = False

    def _enter_paused_state(self) -> None:
        """Transform the flow line into interactive paused-state controls."""
        self._paused_selected_node = None
        self._paused_radio_side = ""
        self._injected_context = ""
        try:
            self.query_one("#btn-resume-flow", Button).disabled = False
        except Exception:
            pass
        # Rebuild flow line with clickable nodes (Phase C will add radio dots + orange arrows)
        self._refresh_paused_flow_line()

    def _exit_paused_state(self) -> None:
        """Restore flow line to normal non-interactive state and process injections."""
        try:
            self.query_one("#btn-resume-flow", Button).disabled = True
        except Exception:
            pass
            
        if self._injected_context and self._paused_selected_node is not None:
            # Determine which payload file to append to
            idx = self._paused_selected_node
            
            if self._paused_radio_side == "left":
                target_idx = idx - 1
            else:
                target_idx = idx
                
            payload_to_modify = None
            job_id = getattr(self, "_current_job_id", None)
            
            if target_idx == -1:
                payload_to_modify = self._pending_payload_path
            elif job_id:
                try:
                    import sqlite3
                    from maccre_core.utils.path_resolver import get_datacenter_path
                    db_path = str(get_datacenter_path("swarm_queue.db"))
                    with sqlite3.connect(db_path) as conn:
                        conn.row_factory = sqlite3.Row
                        rows = conn.execute(
                            "SELECT payload_path FROM task_queue WHERE job_id = ? ORDER BY id",
                            (job_id,)
                        ).fetchall()
                        if target_idx >= 0 and target_idx < len(rows):
                            payload_to_modify = str(rows[target_idx]["payload_path"])
                except Exception:
                    pass
            elif target_idx >= 0 and target_idx < len(self._node_payloads):
                payload_to_modify = self._node_payloads[target_idx]

            if payload_to_modify and Path(payload_to_modify).exists():
                try:
                    with open(payload_to_modify, "a", encoding="utf-8") as f:
                        f.write(f"\n\n--- INJECTED CONTEXT ---\n{self._injected_context}\n")
                    self.write_agent_log(f"[bold green]✓ Injected context appended to:[/bold green] {payload_to_modify}")
                except Exception as e:
                    self.write_agent_log(f"[red]Failed to inject context:[/red] {e}")

        self._paused_selected_node = None
        self._paused_radio_side = ""
        self._injected_context = ""
        self._refresh_active_flow_sequence()

    def _refresh_paused_flow_line(self) -> None:
        """Rebuild flow line for paused state - nodes are clickable, arrows can turn orange."""
        container = self.query_one("#active-flow-sequence", Horizontal)
        # Clear everything except the static fallback
        for w in list(container.children):
            w.remove()

        if not self.active_flow_steps:
            container.mount(Static("[dim italic]  ── empty flow line ──  [/dim italic]"))
            return

        display_names = []
        job_id = getattr(self, "_current_job_id", None)
        if job_id:
            try:
                import sqlite3
                from maccre_core.utils.path_resolver import get_datacenter_path
                db_path = str(get_datacenter_path("swarm_queue.db"))
                with sqlite3.connect(db_path) as conn:
                    conn.row_factory = sqlite3.Row
                    rows = conn.execute(
                        "SELECT current_node FROM task_queue WHERE job_id = ? ORDER BY id",
                        (job_id,)
                    ).fetchall()
                    for r in rows:
                        display_names.append(r["current_node"])
            except Exception:
                pass

        if not display_names:
            from maccre_core.orchestration.flow_engine import FlowStep  # noqa: PLC0415
            display_names = [step.macronode_name if isinstance(step, FlowStep) else str(step) for step in self.active_flow_steps]

        container.mount(Static("[yellow]⏸ PAUSED[/yellow] ", classes="flow-arrow-dim"))

        for i, name in enumerate(display_names):

            if i > 0:
                # Arrow between nodes - dim by default, illuminates orange when a radio selects it
                arrow_cls = "flow-arrow-dim"
                if self._paused_selected_node is not None:
                    if self._paused_radio_side == "right" and i == self._paused_selected_node + 1:
                        arrow_cls = "flow-arrow-paused"
                    elif self._paused_radio_side == "left" and i == self._paused_selected_node:
                        arrow_cls = "flow-arrow-paused"
                container.mount(
                    Button("→", id=f"paused-arrow-{i}", classes=arrow_cls,
                           disabled=(arrow_cls == "flow-arrow-dim"))
                )

            # Node button
            node_cls = "flow-node-clickable"
            if self._paused_selected_node == i:
                node_cls = "flow-node-clickable flow-node-selected"

            node_wrapper = Horizontal(classes="flow-node-wrapper")
            container.mount(node_wrapper)

            # Left radio dot (visible only when this node is selected)
            if self._paused_selected_node == i:
                left_cls = "radio-dot" + (" radio-dot-active" if self._paused_radio_side == "left" else "")
                node_wrapper.mount(Button("○", id=f"radio-left-{i}", classes=left_cls))

            node_wrapper.mount(Button(f" {name} ", id=f"paused-node-{i}", classes=node_cls))

            # Right radio dot
            if self._paused_selected_node == i:
                right_cls = "radio-dot" + (" radio-dot-active" if self._paused_radio_side == "right" else "")
                node_wrapper.mount(Button("○", id=f"radio-right-{i}", classes=right_cls))

        # If left radio is selected, show Live Chat button
        if self._paused_selected_node is not None and self._paused_radio_side == "left":
            container.mount(
                Button("💬 Live Chat", id="btn-open-live-chat",
                       variant="primary", classes="btn-live-chat")
            )

        container.mount(Static(" [dim](click a node)[/dim]", classes="flow-arrow-dim"))

    
    # ── Inline Flow Editor Handlers ───────────────────────────────────────────
    @on(Button.Pressed, "#btn-add-macro")
    def add_macro_to_flow(self) -> None:
        sel = self.query_one("#macro-select", Select)
        if not sel.value or sel.value == Select.BLANK or str(sel.value) == "Select.NULL":
            return
        name = str(sel.value)
        mapping = {}
        # We no longer aggressively overwrite all template slots with the single agent
        # selected in the #agent-select dropdown. The default agent names defined 
        # in the template will be preserved.

        from maccre_core.orchestration.flow_engine import FlowStep
        step = FlowStep(macronode_name=name, agent_mapping=mapping)
        self.active_flow_steps.append(step)
        self.write_nexus_log(f"[dim]System:[/dim] Added MacroNode '{name}' to flow.")
        self.write_agent_log(f"[dim]System:[/dim] Added MacroNode '{name}' to flow.")
        self._refresh_active_flow_sequence()

    @on(Button.Pressed, "#btn-add-agent")
    def add_agent_to_flow(self) -> None:
        sel = self.query_one("#agent-select", Select)
        if not sel.value or sel.value == Select.BLANK or str(sel.value) == "Select.NULL":
            return
        name = str(sel.value)
        from maccre_core.orchestration.flow_engine import FlowStep
        step = FlowStep(macronode_name=name)
        self.active_flow_steps.append(step)
        self.write_nexus_log(f"[dim]System:[/dim] Added Agent '{name}' to flow.")
        self.write_agent_log(f"[dim]System:[/dim] Added Agent '{name}' to flow.")
        self._refresh_active_flow_sequence()

    @on(Button.Pressed, "#btn-add-special")
    def add_special_to_flow(self) -> None:
        sel = self.query_one("#special-select", Select)
        if not sel.value or sel.value == Select.BLANK or str(sel.value) == "Select.NULL":
            return
        name = str(sel.value)
        from maccre_core.orchestration.flow_engine import FlowStep
        step = FlowStep(macronode_name=name)
        self.active_flow_steps.append(step)
        self.write_nexus_log(f"[dim]System:[/dim] Added Special Node '{name}' to flow.")
        self.write_agent_log(f"[dim]System:[/dim] Added Special Node '{name}' to flow.")
        self._refresh_active_flow_sequence()

    @on(Select.Changed, "#macro-select")
    def on_macro_selected(self, event: Select.Changed) -> None:
        if not event.value or event.value == Select.BLANK:
            return
        from maccre_core.macronode_registry import get_macronode_store
        from maccre_core.agent_library import get_agent_store
        store = get_macronode_store()
        agent_store = get_agent_store("GLOBAL")
        try:
            m = store.load(str(event.value))
            desc = m.get("description", "No description available.")
            
            output = f"[bold cyan]MacroNode Structure:[/bold cyan]\n{desc}\n\n[bold cyan]Agent Breakdown:[/bold cyan]\n"
            
            tpl_cfg = m.get("template_config", {})
            agent_mapping = tpl_cfg.get("_agent_mapping", {})
            slot_tools = tpl_cfg.get("slot_tools", {})
            struct_augment = tpl_cfg.get("structural_augment", "")
            
            for slot, agents in agent_mapping.items():
                for a_name in agents:
                    tools_for_slot = slot_tools.get(f"{slot}_{a_name}", slot_tools.get(slot, "none"))
                    p = agent_store.get(a_name)
                    if p:
                        sys_prompt = p.get('system_prompt', '')
                        if struct_augment and slot in ("judge", "anchor"):
                            sys_prompt += f"\n\n[STRUCTURAL AUGMENT]\n{struct_augment}"
                            
                        output += (
                            f"\n[bold green]► {a_name}[/bold green] (Slot: {slot})\n"
                            f"  [dim]Model:[/dim] {p.get('model', 'Unknown')}\n"
                            f"  [dim]Tools Baked:[/dim] {tools_for_slot}\n"
                            f"  [dim]System Prompt:[/dim]\n  {sys_prompt.replace(chr(10), chr(10)+'  ')}\n"
                        )
                    else:
                        output += f"\n[bold red]► {a_name}[/bold red] (Profile not found in GLOBAL)\n"
            
            log_widget = self.query_one("#macro-info-body", RichLog)
            log_widget.clear()
            log_widget.write(output)
        except Exception as e:
            log_widget = self.query_one("#macro-info-body", RichLog)
            log_widget.clear()
            log_widget.write(f"[red]Error: {e}[/red]")

    @on(Select.Changed, "#agent-select")
    def on_main_agent_selected(self, event: Select.Changed) -> None:
        if not event.value or event.value == Select.BLANK:
            return
        from maccre_core.agent_library import get_agent_store
        store = get_agent_store("GLOBAL")
        try:
            p = store.get(str(event.value))
            desc = (
                f"[bold cyan]Agent Breakdown:[/bold cyan]\n"
                f"[bold green]► {p.get('agent_name', 'Unknown')}[/bold green]\n"
                f"  [dim]Model:[/dim] {p.get('model', 'Unknown')}\n"
                f"  [dim]Tools:[/dim] None (Ephemeral until configured)\n"
                f"  [dim]Temperature:[/dim] {p.get('temperature', '0.7')}\n"
                f"  [dim]System Prompt:[/dim]\n  {str(p.get('system_prompt', '')).replace(chr(10), chr(10)+'  ')}"
            )
            log_widget = self.query_one("#agent-info-body", RichLog)
            log_widget.clear()
            log_widget.write(desc)
        except Exception as e:
            log_widget = self.query_one("#agent-info-body", RichLog)
            log_widget.clear()
            log_widget.write(f"[red]Error: {e}[/red]")

    @on(Select.Changed, "#special-select")
    def on_special_selected(self, event: Select.Changed) -> None:
        if not event.value or event.value == Select.BLANK:
            return
        desc_map = {
            "MANUAL": "Pauses execution for manual user input. Acts as a strict human-in-the-loop gate.",
            "DET_ANCHOR": "Anchors execution state, creating a reliable fallback point if downstream nodes fail.",
            "DET_RECURSION": "Triggers a recursive loop, rerunning the previous node sequence until conditions are met.",
            "DET_PAUSE": "Temporarily pauses execution for a predefined amount of time or until externally unpaused.",
            "DET_GATE": "Evaluates conditions and gates execution flow based on logical rules.",
            "DET_CHECKPOINT": "Saves state and artifacts mid-flow, ensuring work is not lost during long executions.",
            "DET_DELAY": "Injects an explicit delay into the execution flow.",
            "DET_TRANSFORM": "Transforms payload data format (e.g., Markdown to JSON) before passing to next node."
        }
        val = str(event.value)
        self.query_one("#special-info-body", Static).update(desc_map.get(val, "Special node for logic control."))

    @on(Button.Pressed, "#btn-remove-last")
    def remove_last_node(self) -> None:
        if self.active_flow_steps:
            self.active_flow_steps.pop()
            self._refresh_active_flow_sequence()

    def _populate_flow_registry_dropdown(self) -> None:
        try:
            from maccre_core.flow_registry import FlowRegistryStore
            store = FlowRegistryStore()
            names = store.list_flow_names()
            opts = [(n, n) for n in names]
            sel = self.query_one("#main-flow-load-select", Select)
            if sel:
                sel.set_options(opts)
        except Exception as e:
            self.write_agent_log(f"[red]Error loading Flow Registry dropdown: {e}[/red]")

    @on(Select.Changed, "#main-flow-load-select")
    def on_main_flow_load(self, event: Select.Changed) -> None:
        val = event.value
        if not val or val == Select.BLANK:
            return
        try:
            import json
            from maccre_core.flow_registry import FlowRegistryStore
            from maccre_core.orchestration.flow_engine import FlowStep
            store = FlowRegistryStore()
            flow = store.load_flow(str(val))
            raw_steps = json.loads(flow["steps_json"])
            
            self.active_flow_steps = []
            for s in raw_steps:
                if isinstance(s, dict):
                    self.active_flow_steps.append(FlowStep.from_dict(s))
                elif isinstance(s, str):
                    import ast
                    try:
                        d = ast.literal_eval(s)
                        if isinstance(d, dict):
                            self.active_flow_steps.append(FlowStep.from_dict(d))
                        else:
                            self.active_flow_steps.append(s)
                    except Exception:
                        self.active_flow_steps.append(s)
                else:
                    self.active_flow_steps.append(s)
                    
            self._refresh_active_flow_sequence()
            self.notify(f"Loaded Flow: {flow['name']}")
            self._current_job_id = None
            self.query_one("#active-flow-sequence-label", Label).update("Active Flow Sequence [Unsaved]")
        except Exception as e:
            self.notify(f"Load failed: {e}", severity="error")

    @on(Button.Pressed, "#btn-clear-flow")
    def clear_flow_sequence(self) -> None:
        self.active_flow_steps.clear()
        self._refresh_active_flow_sequence()
        # Disable main session naming since no flow is active
        name_input = self.query_one("#main-name-session-input", Input)
        name_input.disabled = True
        name_input.value = ""

    @on(Input.Submitted, "#main-name-session-input")
    def handle_main_session_name(self, event: Input.Submitted) -> None:
        job_id = getattr(self, "_current_job_id", None)
        new_name = event.value.strip()
        if job_id and new_name and job_id != new_name:
            from maccre_core.orchestration.local_broker import LocalMessageBroker
            try:
                LocalMessageBroker().rename_session(job_id, new_name)
                self._current_job_id = new_name
                self.notify(f"Session renamed to {new_name}")
            except Exception as e:
                self.notify(f"Rename failed: {e}", severity="error")

    @on(Button.Pressed, "#btn-session-manager")
    def handle_session_manager(self, event: Button.Pressed) -> None:
        def handle_sm_result(result: dict | None) -> None:
            if not result:
                return
            action = result.get("action")
            job_id = result.get("job_id")
            if not action or not job_id:
                return

            if action == "resume":
                self.notify(f"Resuming flow for {job_id}...")
                self.is_session_active = True
                self.query_one("#btn-launch-flow", Button).disabled = True
                self.query_one("#btn-stop-flow", Button).disabled = False
                self.query_one("#btn-create-payload", Button).disabled = True
                
                self._flow_cancel_event = threading.Event()
                self._flow_pause_event = threading.Event()
                self._flow_pause_event.set()
                self._node_payloads = []
                self._set_vcr_state("running")
                self._readout_timer = self.set_interval(1.0, self._update_flow_stage_readout)
                
                self.resume_linear_flow_background(job_id)

            elif action == "canonize":
                try:
                    from maccre_core.orchestration.local_broker import LocalMessageBroker
                    from maccre_core.utils.path_resolver import get_datacenter_path
                    import sqlite3

                    broker = LocalMessageBroker()
                    broker.mark_canonized(job_id)

                    conn = broker._get_conn()
                    conn.row_factory = sqlite3.Row
                    row = conn.execute("SELECT topology_csv FROM job_sessions WHERE job_id = ?", (job_id,)).fetchone()
                    if row and row["topology_csv"]:
                        from maccre_core.flow_registry import FlowRegistryStore
                        store = FlowRegistryStore()
                        store.save_flow(f"{job_id}-CanonFlow", "Canonized Flow", row["topology_csv"])
                        self._populate_flow_registry_dropdown()

                    # Fix canonize arguments
                    ledger_path = str(get_datacenter_path("03_Agent_Ledgers", job_id, "unified_session_ledger.md"))
                    self.notify(f"Extracting memory pins for {job_id}...")
                    self.run_worker(self._async_canonize(ledger_path, job_id), thread=True)
                except Exception as e:
                    self.notify(f"Canonize failed: {e}", severity="error")

            elif action == "save_registry":
                try:
                    from maccre_core.orchestration.local_broker import LocalMessageBroker
                    import sqlite3
                    conn = LocalMessageBroker()._get_conn()
                    conn.row_factory = sqlite3.Row
                    row = conn.execute("SELECT topology_csv FROM job_sessions WHERE job_id = ?", (job_id,)).fetchone()
                    if row and row["topology_csv"]:
                        from maccre_core.flow_registry import FlowRegistryStore
                        store = FlowRegistryStore()
                        store.save_flow(job_id, "Saved from Session Manager", row["topology_csv"])
                        self.notify(f"Flow {job_id} saved to registry.")
                        self._populate_flow_registry_dropdown()
                except Exception as e:
                    self.notify(f"Save failed: {e}", severity="error")

            elif action == "nexus_deadflow":
                self.focus_nexus()
                chat_input = self.query_one("#fe-input", Input)
                chat_input.value = f"Nexus, please inspect the DeadFlow for session '{job_id}' and propose a fix."
                chat_input.focus()

        self.app.push_screen(SessionManagerModal(), handle_sm_result)

    async def _async_canonize(self, ledger_path: str, job_id: str) -> None:
        try:
            from maccre_core.orchestration.memory_engine import CognitiveMemoryEngine
            mem = CognitiveMemoryEngine()
            mem.extract_from_canonized_ledger(ledger_path, job_id)
            self.call_from_thread(self.notify, f"Session {job_id} canonized successfully!")
        except Exception as e:
            self.call_from_thread(self.notify, f"Canonize failed: {e}", severity="error")

    @on(Button.Pressed, "#btn-flow-registry")
    def action_flow_registry(self) -> None:
        if self._vcr_state != "idle":
            return
            
        try:
            from maccre_core.flow_registry import FlowRegistryStore
            store = FlowRegistryStore()
            flows = store.load_all_flows()
        except Exception as e:
            self.write_agent_log(f"[red]Error loading Flow Registry: {e}[/red]")
            return
            
        def handle_registry(result: dict | None):
            if result:
                action = result.get("action")
                if action == "save":
                    try:
                        import json
                        store = FlowRegistryStore()
                        steps_json = json.dumps([s.to_dict() for s in self.active_flow_steps])
                        store.save_flow(result["name"], result["description"], steps_json)
                        self.write_agent_log(f"[green]Flow '{result['name']}' saved to registry.[/green]")
                    except Exception as e:
                        self.write_agent_log(f"[red]Failed to save flow: {e}[/red]")
                elif action == "load":
                    try:
                        import json
                        store = FlowRegistryStore()
                        flow = store.load_flow(result["name"])
                        steps_data = json.loads(flow["steps_json"])
                        from maccre_core.orchestration.flow_engine import FlowStep
                        self.active_flow_steps = [FlowStep.from_dict(s) for s in steps_data]
                        self._refresh_active_flow_sequence()
                        self.write_agent_log(f"[green]Flow '{result['name']}' loaded from registry.[/green]")
                    except Exception as e:
                        self.write_agent_log(f"[red]Failed to load flow: {e}[/red]")
                        
        self.app.push_screen(FlowRegistryModalScreen(flows), handle_registry)

    def _refresh_active_flow_sequence(self) -> None:
        """Refresh the active flow sequence display with clickable nodes."""
        container = self.query_one("#active-flow-sequence", Horizontal)
        
        # Safely mark all existing children for removal
        container.query("*").remove()
        
        if not self.active_flow_steps:
            container.mount(Static("No flow loaded.", classes="flow-seq-text"))
            return
            
        widgets_to_mount = []
        for i, step in enumerate(self.active_flow_steps):
            if i > 0:
                widgets_to_mount.append(Static(" → ", classes="flow-arrow-dim"))
            name = step.macronode_name if hasattr(step, "macronode_name") else str(step)
            import uuid
            btn = Button(name, variant="default", id=f"anode-{i}-{uuid.uuid4().hex[:8]}", classes="active-node-btn")
            widgets_to_mount.append(btn)
            
        # Batch mount the new widgets
        container.mount(*widgets_to_mount)
        self._save_autosave_flow()

    @on(Button.Pressed, ".active-node-btn")
    def action_configure_node(self, event: Button.Pressed) -> None:
        if self._vcr_state != "idle":
            return
            
        try:
            idx = int(event.button.id.split("-")[1])
            node = self.active_flow_steps[idx]
        except (ValueError, AttributeError):
            return
            
        def handle_config(result: dict | None):
            if result:
                if result.get("name"):
                    node.macronode_name = result["name"]
                if result.get("payload_mode"):
                    node.payload_mode = str(result["payload_mode"])
                if "custom_instructions" in result:
                    node.custom_instructions = result["custom_instructions"]
                if "agent_tools_overrides" in result:
                    node.agent_tools_overrides.update(result["agent_tools_overrides"])
                self.write_agent_log(f"[green]Node {idx} updated.[/green]")
                self._refresh_active_flow_sequence()
                
        # Resolve agents in the MacroNode
        agents_in_node = set()
        try:
            from maccre_core.macronode_registry import get_macronode_store
            store = get_macronode_store()
            macro_def = store.load(node.macronode_name)
            
            # Extract from topology rows
            for row in macro_def.get("topology_rows", []):
                aname = str(row.get("Agent_Name", ""))
                for slot_key, slot_val in getattr(node, "agent_mapping", {}).items():
                    if aname == f"{{{slot_key}}}" or aname == slot_key:
                        aname = slot_val
                if aname and not aname.startswith("{") and aname.upper() != "NONE" and aname != "Select.NULL":
                    agents_in_node.add(aname)
                    
            # Extract from agent slots (covers template macros where secondary agents aren't explicit rows)
            for slot in macro_def.get("agent_slots", []):
                aname = slot
                for slot_key, slot_val in getattr(node, "agent_mapping", {}).items():
                    if aname == slot_key:
                        aname = slot_val
                if aname and not aname.startswith("{") and aname.upper() != "NONE" and aname != "Select.NULL":
                    agents_in_node.add(aname)
        except Exception:
            try:
                from maccre_core.agent_library import get_agent_store
                if get_agent_store("GLOBAL").get(node.macronode_name):
                    agents_in_node.add(node.macronode_name)
            except Exception:
                pass

        # Extract baked tools from MacroNode to prepopulate NodeConfigModal
        baked_tools = {}
        try:
            tpl_cfg = macro_def.get("template_config", {})
            slot_tools = tpl_cfg.get("slot_tools", {})
            agent_mapping = getattr(node, "agent_mapping", None) or tpl_cfg.get("_agent_mapping", {})
            
            for slot, agents in agent_mapping.items():
                for a in agents:
                    tools = slot_tools.get(f"{slot}_{a}", slot_tools.get(slot, "none"))
                    if tools and tools != "none":
                        baked_tools[a] = tools
        except Exception as e:
            self.write_agent_log(f"[red]Error extracting baked tools: {e}[/red]")
            pass
            
        self.write_agent_log(f"[dim]Debug:[/dim] Passing baked_tools to NodeConfigModal: {baked_tools}")
        
        self.push_screen(NodeConfigModal(
            node_name=node.macronode_name,
            current_payload_mode=getattr(node, "payload_mode", "Unified Ledger"),
            current_instructions=getattr(node, "custom_instructions", ""),
            active_project=self.active_project,
            agents_in_node=list(agents_in_node),
            baked_tools=baked_tools,
            current_agent_tools_overrides=getattr(node, "agent_tools_overrides", {})
        ), handle_config)

    @on(Button.Pressed)
    def _handle_paused_flow_clicks(self, event: Button.Pressed) -> None:
        """Route clicks on paused-state flow line elements."""
        btn_id = str(event.button.id or "")

        # ── Node clicked - select it, show radio dots ──
        if btn_id.startswith("paused-node-"):
            if self._vcr_state != "paused":
                return
            try:
                idx = int(btn_id.replace("paused-node-", ""))
            except ValueError:
                return
            self._paused_selected_node = idx
            self._paused_radio_side = ""
            self._refresh_paused_flow_line()
            name = self.active_flow_steps[idx].macronode_name
            self.write_agent_log(
                f"[cyan]Selected node: {name}[/cyan] - click ○ left (inject before) or ○ right (inject after/fork)"
            )

        # ── Radio dot clicked - set side, illuminate arrow ──
        elif btn_id.startswith("radio-left-"):
            try:
                idx = int(btn_id.replace("radio-left-", ""))
            except ValueError:
                return
            self._paused_radio_side = "left"
            self._refresh_paused_flow_line()
            self.write_agent_log(
                "[yellow]◀ Left radio:[/yellow] inject context BEFORE this node. "
                "Click the orange arrow to inject, or 💬 Live Chat for interactive prep."
            )

        elif btn_id.startswith("radio-right-"):
            try:
                idx = int(btn_id.replace("radio-right-", ""))
            except ValueError:
                return
            self._paused_radio_side = "right"
            self._refresh_paused_flow_line()
            self.write_agent_log(
                "[yellow]▶ Right radio:[/yellow] inject context AFTER this node's output (fork). "
                "Click the orange arrow to inject."
            )

        # ── Orange arrow clicked - open context injection modal ──
        elif btn_id.startswith("paused-arrow-"):
            if self._paused_selected_node is None or not self._paused_radio_side:
                return
            self._open_paused_injection_modal()

    def _open_paused_injection_modal(self) -> None:
        """Open context injection for the selected arrow in paused state."""
        def handle_injection(text: str | None) -> None:
            if text:
                self._injected_context = text
                side = self._paused_radio_side
                node_idx = self._paused_selected_node
                if node_idx is not None:
                    name = self.active_flow_steps[node_idx].macronode_name
                    self.write_agent_log(
                        f"[green]Context injected ({len(text)} chars) "
                        f"{'before' if side == 'left' else 'after'} '{name}'.[/green]\n"
                        f"Click ▶ to resume flow from this point."
                    )
        self.push_screen(ContextInjectModalScreen(), handle_injection)

    @on(Button.Pressed, "#btn-open-live-chat")
    def _open_live_chat(self) -> None:
        """Open Live Chat modal for the selected node."""
        if self._paused_selected_node is None:
            return
        node_idx = self._paused_selected_node
        step = self.active_flow_steps[node_idx]

        # Determine the staged payload for this node
        if node_idx == 0:
            staged = self._pending_payload_path
        elif node_idx - 1 < len(self._node_payloads):
            staged = self._node_payloads[node_idx - 1]
        else:
            staged = "(no captured payload for this step)"

        # Try to read staged payload content
        staged_content = staged
        try:
            from pathlib import Path  # noqa: PLC0415
            p = Path(staged)
            if p.exists():
                staged_content = p.read_text(encoding="utf-8")[:2000]
        except Exception:  # noqa: BLE001
            pass

        # Get agent name and system prompt from topology
        agent_name = "Agent"
        system_prompt = ""
        try:
            from maccre_core.orchestration.roster_loader import load_agent_roster  # noqa: PLC0415
            roster = load_agent_roster()
            # First mapped agent name, or node name as fallback
            if step.agent_mapping:
                agent_name = next(iter(step.agent_mapping.values()), step.macronode_name)
            else:
                agent_name = step.macronode_name
            profile = roster.get(agent_name, {})
            system_prompt = profile.get("System_Prompt", "")
        except Exception:  # noqa: BLE001
            pass

        def handle_live_chat_result(result: dict[str, str] | None) -> None:
            if result and result.get("action") == "continue":
                payload = result.get("payload", "")
                self.write_agent_log(
                    f"[green]Live Chat complete - {len(payload)} chars payload ready.[/green]\n"
                    f"Click ▶ to resume flow from node '{step.macronode_name}'."
                )
                self._injected_context = payload
            else:
                self.write_agent_log("[dim]Live Chat closed. Flow remains paused.[/dim]")

        self.push_screen(
            NodeLiveChatModal(
                agent_name=agent_name,
                node_name=step.macronode_name,
                staged_payload=staged_content,
                system_prompt=system_prompt,
            ),
            handle_live_chat_result,
        )

    @on(Button.Pressed, "#btn-launch-flow")
    def action_launch_flow(self) -> None:
        if not self.active_flow_steps:
            self.write_agent_log("[red]Flow Line is empty. Use Linear Flow Editor to add MacroNodes.[/red]")
            return

        if self._pending_payload_path == "none":
            self.write_agent_log(
                "[yellow]No payload set. Use 'Create Payload' to set input data, "
                "or launching with empty payload.[/yellow]"
            )

        if not self.active_project or self.active_project == "SET ACTIVE PROJECT":
            self.write_agent_log("[red]Please select or create an active project before launching.[/red]")
            return
            
        # Check pre-flight conditions Gate ────────────────────────────────────────
        self.write_agent_log("\n[bold cyan]Running pre-flight checks...[/bold cyan]")
        try:
            from maccre_core.orchestration.flow_engine import FlowRunner  # noqa: PLC0415
            runner = FlowRunner(self.active_project)
            report = runner.preflight_check(self.active_flow_steps)
            self.write_agent_log(report.render())

            if not report.is_ok:
                # Hard-block - show Proceed Anyway button
                self.write_agent_log(
                    "\n[bold red]Pre-flight validation failed. "
                    "Review errors above, then click [Proceed Anyway] to override.[/bold red]"
                )
                self._preflight_override_pending = True
                self.query_one("#btn-proceed-anyway", Button).remove_class("hidden")
                return
        except Exception as e:  # noqa: BLE001
            self.write_agent_log(f"[yellow]Pre-flight check skipped: {e}[/yellow]")

        # ── Duplicate-Run Guard ───────────────────────────────────────────────
        if self._flow_loaded_from_history:
            current_hash = self._hash_flow_config(self.active_flow_steps, self._pending_payload_path)
            if current_hash == self._flow_history_hash:
                self.write_agent_log(
                    f"\n[bold yellow]⚠ DUPLICATE RUN DETECTED[/bold yellow]\n"
                    f"[dim]This is an unmodified replay of job {self._flow_history_job_id}.[/dim]\n"
                    f"[dim]Modify the flow or payload, or click [Proceed Anyway] to launch as-is.[/dim]"
                )
                self._preflight_override_pending = True
                self.query_one("#btn-proceed-anyway", Button).remove_class("hidden")
                return
            else:
                self.write_agent_log("[green]✓ Flow modified from history template - proceeding.[/green]")

        # Reset history tracking on launch
        self._flow_loaded_from_history = False
        self._do_launch_flow()

    @on(Button.Pressed, "#btn-proceed-anyway")
    def action_proceed_anyway(self) -> None:
        """Override pre-flight hard-block and launch anyway."""
        if getattr(self, "_preflight_override_pending", False):
            self._preflight_override_pending = False
            self.query_one("#btn-proceed-anyway", Button).add_class("hidden")
            self.write_agent_log("[yellow]⚠ Proceeding despite pre-flight errors.[/yellow]")
            self._do_launch_flow()

    def _update_flow_stage_readout(self) -> None:
        """Poll the SQLite task_queue to update the real-time stage readout label."""
        if not getattr(self, "is_session_active", False) or self._vcr_state != "running":
            return
            
        job_id = getattr(self, "_current_job_id", None)
        if not job_id:
            return
            
        try:
            import sqlite3
            from maccre_core.utils.path_resolver import get_datacenter_path
            db_path = str(get_datacenter_path("swarm_queue.db"))
            with sqlite3.connect(db_path) as conn:
                conn.row_factory = sqlite3.Row
                # Get total tasks and completed tasks
                total = conn.execute("SELECT COUNT(*) FROM task_queue WHERE job_id = ?", (job_id,)).fetchone()[0]
                completed = conn.execute("SELECT COUNT(*) FROM task_queue WHERE job_id = ? AND lock_status = 'completed'", (job_id,)).fetchone()[0]
                
                # Get currently active task (locked or open)
                active = conn.execute("SELECT current_node, agent_name FROM task_queue WHERE job_id = ? AND lock_status IN ('locked', 'open') ORDER BY id LIMIT 1", (job_id,)).fetchone()
                
                if active:
                    node_name = active["current_node"]
                    agent_name = active["agent_name"]
                    label_text = f"Stage: [bold cyan]{node_name}[/bold cyan] ([green]{agent_name}[/green]) | Flow Progress: {completed}/{total}"
                else:
                    label_text = f"Stage: [dim]Processing...[/dim] | Flow Progress: {completed}/{total}"
                
                self.query_one("#flow-stage-readout", Label).update(label_text)
        except Exception:
            pass

    def _do_launch_flow(self) -> None:
        """Internal launch - called after pre-flight passes or is overridden."""
        self.is_session_active = True
        self.query_one("#btn-launch-flow", Button).disabled = True
        self.query_one("#btn-stop-flow", Button).disabled = False
        self.query_one("#btn-create-payload", Button).disabled = True
        
        self.write_agent_log(
            f"\n[bold cyan]--- Started Linear Flow Execution ---[/bold cyan]\n"
            f"Payload: {self._pending_payload_path}"
        )
        self._flow_cancel_event = threading.Event()
        self._flow_pause_event = threading.Event()
        self._flow_pause_event.set()  # Start unblocked
        self._node_payloads = []
        self._set_vcr_state("running")
        
        # Start readout poller
        self._readout_timer = self.set_interval(1.0, self._update_flow_stage_readout)
        
        self.run_linear_flow_background()

    @work(thread=True)
    def run_linear_flow_background(self) -> None:
        import logging
        
        class RichLogHandler(logging.Handler):
            def __init__(self, tui_app):
                super().__init__()
                self.tui_app = tui_app

            def emit(self, record):
                try:
                    msg = record.getMessage()
                    self.tui_app.write_agent_log(msg)
                except Exception:
                    pass

        tui_handler = RichLogHandler(self)
        root_logger = logging.getLogger()
        
        # Save original level to restore later
        original_level = root_logger.level
        root_logger.setLevel(logging.INFO)
        root_logger.addHandler(tui_handler)
        
        from maccre_core.orchestration.flow_engine import FlowRunner  # noqa: PLC0415
        runner = FlowRunner(self.active_project)
        
        def _on_step_complete(step_index: int, output_path: str) -> None:
            """Capture per-step output for time travel."""
            while len(self._node_payloads) <= step_index:
                self._node_payloads.append("")
            self._node_payloads[step_index] = output_path

        def _on_hitl_pause(step_index: int, job_id: str, payload: str) -> None:
            """Called from flow engine thread when DET_PAUSE fires."""
            self._hitl_job_id = job_id
            self.call_from_thread(self._surface_hitl_pause, step_index, job_id, payload)

        def _on_job_started(job_id: str) -> None:
            """Capture the active job ID for SQLite unrolling queries."""
            self._current_job_id = job_id

        try:
            final_artifact = runner.execute_flow(
                self.active_flow_steps,
                initial_payload_path=self._pending_payload_path,
                cancel_event=self._flow_cancel_event,
                pause_event=self._flow_pause_event,
                step_callback=_on_step_complete,
                hitl_callback=_on_hitl_pause,
                job_started_callback=_on_job_started,
            )
            if self._flow_cancel_event and self._flow_cancel_event.is_set():
                self.write_agent_log("\n[yellow]Flow was cancelled by user.[/yellow]")
            else:
                self.write_agent_log(f"\n[green]Flow completed successfully![/green]\nFinal Artifact: {final_artifact}")
        except Exception as e:
            self.write_agent_log(f"\n[red]Flow Error:[/red] {e}")
        finally:
            root_logger.removeHandler(tui_handler)
            root_logger.setLevel(original_level)
            self.call_from_thread(self._finish_flow)

    @work(thread=True)
    def resume_linear_flow_background(self, job_id: str) -> None:
        import logging
        class RichLogHandler(logging.Handler):
            def __init__(self, tui_app):
                super().__init__()
                self.tui_app = tui_app
            def emit(self, record):
                try:
                    self.tui_app.write_agent_log(record.getMessage())
                except Exception:
                    pass

        tui_handler = RichLogHandler(self)
        root_logger = logging.getLogger()
        original_level = root_logger.level
        root_logger.setLevel(logging.INFO)
        root_logger.addHandler(tui_handler)
        
        from maccre_core.orchestration.flow_engine import FlowRunner
        runner = FlowRunner(self.active_project)
        
        def _on_step_complete(step_index: int, output_path: str) -> None:
            while len(self._node_payloads) <= step_index:
                self._node_payloads.append("")
            self._node_payloads[step_index] = output_path

        def _on_hitl_pause(step_index: int, hitl_job_id: str, payload: str) -> None:
            self._hitl_job_id = hitl_job_id
            self.call_from_thread(self._surface_hitl_pause, step_index, hitl_job_id, payload)

        def _on_job_started(started_job_id: str) -> None:
            self._current_job_id = started_job_id

        try:
            self.write_agent_log(f"\n[bold cyan]--- Resuming Linear Flow Execution ({job_id}) ---[/bold cyan]")
            result_path = runner.resume_flow(
                job_id,
                cancel_event=self._flow_cancel_event,
                pause_event=self._flow_pause_event,
                step_callback=_on_step_complete,
                hitl_callback=_on_hitl_pause,
                job_started_callback=_on_job_started
            )
            if self._flow_cancel_event.is_set():
                self.write_agent_log("[yellow]Flow execution was cancelled by user.[/yellow]")
            else:
                self.write_agent_log(f"\n[bold green]✓ Flow Resume Complete![/bold green]\nFinal Output: {result_path}")
        except Exception as e:
            self.write_agent_log(f"\n[bold red]Flow Resume Failed:[/bold red] {e}")
            import traceback
            self.write_agent_log(f"[dim]{traceback.format_exc()}[/dim]")
        finally:
            self.is_session_active = False
            self.call_from_thread(self._finish_flow_execution)
            root_logger.removeHandler(tui_handler)
            root_logger.setLevel(original_level)


    def _finish_flow(self) -> None:
        self.is_session_active = False
        
        if getattr(self, "_readout_timer", None):
            self._readout_timer.stop()
            self.query_one("#flow-stage-readout", Label).update("Stage: [dim]Idle[/dim]")
            
        self.query_one("#btn-launch-flow", Button).disabled = False
        self.query_one("#btn-stop-flow", Button).disabled = True
        self.query_one("#btn-create-payload", Button).disabled = False
        self._set_vcr_state("idle")
        self._exit_paused_state()

    def _surface_hitl_pause(self, step_index: int, job_id: str, payload: str) -> None:
        """Surface HITL pause to the TUI - show injection modal."""
        step_name = "unknown"
        if 0 <= step_index < len(self.active_flow_steps):
            step_name = self.active_flow_steps[step_index].macronode_name

        self._set_vcr_state("paused")
        self._enter_paused_state()
        self.write_agent_log(
            f"\n[bold yellow]⏸ HITL PAUSE at node '{step_name}'[/bold yellow]\n"
            f"[dim]The flow has paused for human input. Inject context to continue.[/dim]"
        )

        def _on_hitl_inject(text: str | None) -> None:
            if text:
                self._hitl_resume_with_context(job_id, text)
            else:
                self.write_agent_log("[dim]HITL modal dismissed - flow remains paused. Use ▶ to resume.[/dim]")

        self.push_screen(ContextInjectModalScreen(current_payload=payload), _on_hitl_inject)

    def _hitl_resume_with_context(self, job_id: str, context: str) -> None:
        """Write injected context to a payload file and resume the paused broker task."""
        from maccre_core.utils.path_resolver import get_datacenter_path  # noqa: PLC0415

        # Write context to a payload file
        payload_dir = get_datacenter_path("03_Agent_Ledgers", job_id)
        payload_dir.mkdir(parents=True, exist_ok=True)
        hitl_payload_path = payload_dir / "HITL_injection.md"
        hitl_payload_path.write_text(context, encoding="utf-8")

        # Resume the paused task with the new payload
        from maccre_core.orchestration.local_broker import LocalMessageBroker  # noqa: PLC0415
        broker = LocalMessageBroker()
        resumed = broker.resume_paused_task(job_id, str(hitl_payload_path))

        if resumed:
            self.write_agent_log(
                f"[green]HITL context injected ({len(context)} chars) → paused task resumed.[/green]"
            )
            # Unblock the flow engine
            if self._flow_pause_event is not None:
                self._flow_pause_event.set()
            self._set_vcr_state("running")
            self._exit_paused_state()
        else:
            self.write_agent_log("[red]No paused task found to resume.[/red]")

    @on(Button.Pressed, "#btn-stop-flow")
    def action_stop_flow(self) -> None:
        self.write_agent_log("\n[bold yellow]--- Flow Stop Requested (cancelling after current node) ---[/bold yellow]")
        if self._flow_cancel_event:
            self._flow_cancel_event.set()
        self._finish_flow()

    @on(Button.Pressed, "#btn-resume-flow")
    def action_resume_flow(self) -> None:
        """Resume a paused flow (DET_PAUSE)."""
        if self._flow_pause_event:
            self._flow_pause_event.set()
            try:
                self.query_one("#btn-resume-flow", Button).disabled = True
            except Exception:
                pass
            self.write_agent_log("[bold cyan]▶ Flow resumed.[/bold cyan]")
            self._set_vcr_state("running")
            self._exit_paused_state()
        else:
            self.write_agent_log("[yellow]No paused flow to resume.[/yellow]")

    @on(Button.Pressed, "#btn-rewind-flow")
    def action_rewind_flow(self) -> None:
        if not self.active_flow_steps:
            self.write_agent_log("[yellow]Flow Line is empty, nothing to rewind.[/yellow]")
            return
        
        popped = self.active_flow_steps.pop()
        seq_str = " -> ".join([s.macronode_name for s in self.active_flow_steps]) or "No flow loaded."
        for w in self.query(".flow-seq-text"):
            w.update(f"[bold cyan]{seq_str}[/bold cyan]")
        self.write_agent_log(f"[yellow]Rewound Flow Line: Removed {popped.macronode_name}.[/yellow]")

    @on(Button.Pressed, "#btn-copy-nexus")
    def copy_nexus_log(self) -> None:
        self._copy_richlog_to_clipboard("#nexus-log")

    @on(Button.Pressed, "#btn-copy-monitor")
    def copy_flow_log(self) -> None:
        self._copy_richlog_to_clipboard("#flow-execution-log")

    def _copy_richlog_to_clipboard(self, log_id: str) -> None:
        try:
            import pyperclip  # noqa: PLC0415
            log_widget = self.query_one(log_id, RichLog)
            text_lines = [line.text for line in log_widget.lines]
            pyperclip.copy("\n".join(text_lines))
            self.notify(f"Copied {log_id.strip('#')} to clipboard!")
        except Exception as e:
            self.notify(f"Failed to copy to clipboard: {e}", severity="error")

    @on(Button.Pressed, "#btn-file-cabinet")
    def action_file_cabinet(self) -> None:
        def handle_file_cabinet_result(result: dict | None):
            if result:
                action = result.get("action")
                if action == "project_canon":
                    from maccre_tui.widgets.project_canon_modal import ProjectCanonModal
                    self.push_screen(ProjectCanonModal())
                    return
                
                name = result.get("name")
                project = result.get("project")
                files = result.get("files", [])
                if name and project:
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
        def handle_flow_history_result(result: dict | None) -> None:
            if result is None:
                return
            action = result.get("action", "")
            record = result.get("record", {})

            if action == "load":
                self._load_flow_from_history(record)
            elif action == "canonize":
                self._canonize_from_history(record)

        self.push_screen(FlowHistoryModalScreen(), handle_flow_history_result)

    def _load_flow_from_history(self, record: dict) -> None:
        """Deserialize a flow_history record into the active flow sequence."""
        import json  # noqa: PLC0415
        from maccre_core.orchestration.flow_engine import FlowStep  # noqa: PLC0415

        job_id = record.get("job_id", "?")
        steps_json = record.get("flow_steps_json", "[]")
        initial_payload = record.get("initial_payload", "none")

        try:
            step_dicts = json.loads(steps_json)
            loaded_steps = [FlowStep.from_dict(d) for d in step_dicts]
        except Exception as e:  # noqa: BLE001
            self.write_agent_log(f"[red]Failed to parse flow steps from history:[/red] {e}")
            return

        if not loaded_steps:
            self.write_agent_log("[yellow]Flow history record contains no steps.[/yellow]")
            return

        # Populate active flow sequence
        self.active_flow_steps = loaded_steps
        self._refresh_flow_line()

        # Populate payload
        self._pending_payload_path = initial_payload

        # Track history source for duplicate-run guard
        self._flow_loaded_from_history = True
        self._flow_history_job_id = job_id
        self._flow_history_hash = self._hash_flow_config(loaded_steps, initial_payload)

        flow_names = " → ".join(s.macronode_name for s in loaded_steps)
        self.write_agent_log(
            f"\n[bold green]Flow loaded from history:[/bold green] {job_id}\n"
            f"[dim]Steps: {flow_names}[/dim]\n"
            f"[dim]Payload: {initial_payload}[/dim]\n"
            f"[dim]Edit the flow or payload before launching, or launch as-is.[/dim]"
        )

    def _canonize_from_history(self, record: dict) -> None:
        """Trigger canonization for a flow history session."""
        job_id = record.get("job_id", "?")
        project = record.get("project_name", self.active_project)
        self.write_agent_log(
            f"[bold yellow]Canonizing session {job_id} for project {project}...[/bold yellow]"
        )
        try:
            from maccre_core.tools.rag_tools import canonize_session  # noqa: PLC0415
            result = canonize_session(project, job_id)
            self.write_agent_log(f"[green]Canonization complete:[/green] {result}")
        except Exception as e:  # noqa: BLE001
            self.write_agent_log(f"[red]Canonization failed:[/red] {e}")

    @staticmethod
    def _hash_flow_config(steps: list, payload: str) -> str:
        """Generate a hash of the flow config for duplicate detection."""
        import hashlib  # noqa: PLC0415
        import json  # noqa: PLC0415
        content = json.dumps([
            {"name": s.macronode_name, "mapping": s.agent_mapping}
            for s in steps
        ], sort_keys=True) + "|" + payload
        return hashlib.sha256(content.encode()).hexdigest()[:16]

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

    def _save_autosave_flow(self) -> None:
        """Saves the current flow sequence to a quick-recovery autosave file."""
        import json
        from maccre_core.utils.path_resolver import get_datacenter_path
        autosave_path = get_datacenter_path("autosave_flow.json")
        try:
            steps_data = [s.to_dict() for s in self.active_flow_steps]
            autosave_path.parent.mkdir(parents=True, exist_ok=True)
            autosave_path.write_text(json.dumps(steps_data, indent=2), encoding="utf-8")
        except Exception:
            pass

    def _load_autosave_flow(self) -> None:
        """Loads the flow sequence from the quick-recovery autosave file."""
        import json
        from maccre_core.orchestration.flow_engine import FlowStep
        from maccre_core.utils.path_resolver import get_datacenter_path
        autosave_path = get_datacenter_path("autosave_flow.json")
        if not autosave_path.exists():
            return
        try:
            steps_data = json.loads(autosave_path.read_text(encoding="utf-8"))
            self.active_flow_steps = [FlowStep.from_dict(d) for d in steps_data]
            self._refresh_active_flow_sequence()
            self.write_nexus_log("[dim]Autosaved flow sequence recovered.[/dim]")
        except Exception:
            pass

# ── Entry point ───────────────────────────────────────────────────────────────

def main() -> None:
    NexusPlex().run()

if __name__ == "__main__":
    main()

