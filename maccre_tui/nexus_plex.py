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
    Switch
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


# ══════════════════════════════════════════════════════════════════════════════
# CUSTOM WIDGETS
# ══════════════════════════════════════════════════════════════════════════════

class NexusChat(Vertical):
    def compose(self) -> ComposeResult:
        yield Label("Nexus Copilot", classes="pane-title")
        yield RichLog(id="nexus-log", wrap=True, highlight=True, markup=True)
        yield Input(placeholder="Ask Nexus to parse a topology...", id="nexus-input")

class ProjectControls(Horizontal):
    def compose(self) -> ComposeResult:
        yield Static("Project: [None]", id="active-project-label", classes="ribbon-label")
        yield Button("New Project", variant="success", id="btn-new-project")
        yield Button("Select Project", variant="primary", id="btn-select-project")

class TopologyTracker(Horizontal):
    def compose(self) -> ComposeResult:
        yield Static("Topology: [Not Loaded]", id="topo-status")


class AgentBuilderPanel(Vertical):
    """Panel to define and mint new agents into the roster."""
    def compose(self) -> ComposeResult:
        yield Label("Build an Agent", classes="pane-title")
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


class AgentChatPanel(Vertical):
    def compose(self) -> ComposeResult:
        yield Label("Agent Chat", classes="pane-title")
        with Horizontal(classes="agent-chat-controls"):
            yield Select([], prompt="Select Agent to Add", id="ac-select-agent")
            yield Button("Add Agent", variant="success", id="btn-add-agent")
            yield Button("Remove Agent", variant="error", id="btn-remove-agent")
            
        yield Label("Active Roster")
        yield Horizontal(id="active-agent-roster")
            
        with Horizontal(classes="agent-chat-controls"):
            yield Select([("Chat Mode (Sequential)", "chat"), ("Live Mode (Physics)", "live")], value="chat", id="ac-select-mode")
            yield Button("Start Session", variant="primary", id="btn-start-session")
            yield Button("Stop Session", variant="error", id="btn-stop-session", disabled=True)
            yield Button("Chat History", variant="default", id="btn-chat-history")
        
        yield RichLog(id="agent-chat-log", wrap=True, highlight=True, markup=True)
        with Horizontal(classes="agent-chat-controls"):
            yield Button("Canonize Chat", variant="success", id="btn-canonize")
            yield Button("Rename Chat", variant="warning", id="btn-rename")
        yield Input(placeholder="Send message to session...", id="ac-input")


# ══════════════════════════════════════════════════════════════════════════════
# NEXUS_PLEX APP
# ══════════════════════════════════════════════════════════════════════════════

class NexusPlex(App[None]):
    """MACCREv2 Command Center — Nexus_Plex v2."""

    CSS_PATH = "nexus_plex.css"
    TITLE = "Nexus_Plex  ·  MACCREv2 Agentic Command Center"
    
    BINDINGS = [
        Binding("ctrl+q", "quit", "Quit"),
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
                    yield TopologyTracker(id="topo-tracker")
                with Horizontal(id="agent-manager"):
                    yield AgentBuilderPanel()
                    yield AgentChatPanel()
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
        log = self.query_one("#agent-chat-log", RichLog)
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

    # ── Agent Builder Handlers ────────────────────────────────────────────────
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
            agents = load_agent_names_from_library(self.active_project)
            sel = self.query_one("#ac-select-agent", Select)
            import threading
            if self._thread_id == threading.get_ident():
                sel.set_options([(a, a) for a in agents])
            else:
                self.call_from_thread(sel.set_options, [(a, a) for a in agents])
        except Exception as e:
            self.write_nexus_log(f"[red]Error refreshing agent list: {e}[/red]")

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
        try:
            store.save(profile)
            self.write_nexus_log(f"[bold green]System:[/bold green] Saved agent '{name}' to GLOBAL roster.")
            
            # Clear inputs
            self.query_one("#ab-name", Input).value = ""
            self.system_instructions_buffer = ""
            btn = self.query_one("#btn-edit-instructions", Button)
            btn.label = "Edit System Instructions"
            btn.variant = "primary"

            self.refresh_agent_dropdown()
        except Exception as e:
            self.write_nexus_log(f"[red]Error saving agent: {e}[/red]")

    # ── Agent Chat Handlers ───────────────────────────────────────────────────
    @on(Button.Pressed, "#btn-add-agent")
    def action_add_agent(self) -> None:
        if self.is_session_active:
            self.write_agent_log("[red]Cannot add agents while session is active. Stop it first.[/red]")
            return
            
        sel = self.query_one("#ac-select-agent", Select)
        if not sel.value or sel.value == Select.BLANK:
            self.write_agent_log("[red]Please select an agent to add.[/red]")
            return
            
        agent_name = str(sel.value)
        if agent_name in self.active_sessions:
            return # Already added
            
        from maccre_core.agent_library import get_agent_store
        from maccre_core.workbook_data import load_agent_roster_csv
        
        profile = None
        for row in get_agent_store(self.active_project).load_all():
            if row.get("agent_name") == agent_name:
                profile = row
                break
        
        if not profile and self.active_project != "GLOBAL":
            for row in get_agent_store("GLOBAL").load_all():
                if row.get("agent_name") == agent_name:
                    profile = row
                    break
                    
        if not profile:
            for row in load_agent_roster_csv(self.active_project):
                n = str(row.get("Agent_Name") or row.get("AGENT_NAME") or "").strip()
                if n == agent_name:
                    profile = {
                        "agent_name": agent_name,
                        "model": row.get("Model", "gemini-2.5-flash"),
                        "system_prompt": row.get("System_Prompt", ""),
                        "temperature": float(row.get("Temperature", 1.0) or 1.0)
                    }
                    break
                    
        if not profile:
            self.write_agent_log(f"[red]Error: Could not locate profile for '{agent_name}'.[/red]")
            return

        from maccre_core.orchestration.dialogue_runner import _AgentSession
        self.active_sessions[agent_name] = _AgentSession(
            label=profile.get("agent_name", agent_name),
            model=profile.get("model", "gemini-2.5-flash"),
            system_prompt=profile.get("system_prompt", ""),
            temperature=float(profile.get("temperature", 1.0))
        )
        
        roster = self.query_one("#active-agent-roster", Horizontal)
        roster.mount(Static(f"{agent_name}", classes="agent-pill", id=f"pill-{agent_name}"))
        self.write_agent_log(f"[green]Added {agent_name} to session roster.[/green]")

    @on(Button.Pressed, "#btn-remove-agent")
    def action_remove_agent(self) -> None:
        if self.is_session_active:
            self.write_agent_log("[red]Cannot remove agents while session is active. Stop it first.[/red]")
            return
            
        sel = self.query_one("#ac-select-agent", Select)
        if not sel.value or sel.value == Select.BLANK:
            return
            
        agent_name = str(sel.value)
        if agent_name in self.active_sessions:
            del self.active_sessions[agent_name]
            pill = self.query_one(f"#pill-{agent_name}", Static)
            pill.remove()
            self.write_agent_log(f"[yellow]Removed {agent_name} from session roster.[/yellow]")

    @on(Button.Pressed, "#btn-start-session")
    def action_start_session(self) -> None:
        if not self.active_sessions:
            self.write_agent_log("[red]Add at least one agent to the roster to start a session.[/red]")
            return
            
        self.is_session_active = True
        self.session_mode = str(self.query_one("#ac-select-mode", Select).value)
        self.shared_transcript.clear()
        
        self.query_one("#btn-start-session", Button).disabled = True
        self.query_one("#btn-stop-session", Button).disabled = False
        self.query_one("#btn-add-agent", Button).disabled = True
        self.query_one("#btn-remove-agent", Button).disabled = True
        self.query_one("#ac-select-mode", Select).disabled = True
        
        start_msg = f"\n[bold cyan]--- Started Group Session ({self.session_mode.upper()} MODE) ---[/bold cyan]"
        self.write_agent_log(start_msg)
        self.shared_transcript.append({"role": "system", "text": f"--- Started Group Session ({self.session_mode.upper()} MODE) ---"})
        
        if self.session_mode == "live":
            from maccre_core.maccre_router import UniversalRouter
            if not hasattr(self, "universal_router"):
                self.universal_router = UniversalRouter()
            import asyncio
            self.physics_task = asyncio.create_task(self._live_mode_physics_loop())

    @on(Button.Pressed, "#btn-stop-session")
    def action_stop_session(self) -> None:
        self.is_session_active = False
        self.query_one("#btn-start-session", Button).disabled = False
        self.query_one("#btn-stop-session", Button).disabled = True
        self.query_one("#btn-add-agent", Button).disabled = False
        self.query_one("#btn-remove-agent", Button).disabled = False
        self.query_one("#ac-select-mode", Select).disabled = False
        
        if self.physics_task:
            self.physics_task.cancel()
            self.physics_task = None
            
        self.write_agent_log("\n[bold yellow]--- Session Stopped ---[/bold yellow]")
        self.shared_transcript.append({"role": "system", "text": "--- Session Stopped ---"})

    @on(Button.Pressed, "#btn-canonize")
    def action_canonize_chat(self) -> None:
        if not self.shared_transcript:
            self.write_agent_log("[yellow]Nothing to canonize. The transcript is empty.[/yellow]")
            return
            
        import json
        import datetime
        from maccre_core.utils.path_resolver import get_maccre_root
        
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        out_dir = get_maccre_root() / "__DATACENTER" / self.active_project / "03_Agent_Ledgers" / "chat_sessions"
        out_dir.mkdir(parents=True, exist_ok=True)
        
        out_file = out_dir / f"session_{timestamp}.json"
        
        payload = {
            "project": self.active_project,
            "mode": self.session_mode,
            "agents": list(self.active_sessions.keys()),
            "transcript": self.shared_transcript
        }
        
        with open(out_file, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2)
            
        self.write_agent_log(f"[green]Chat Ledger Saved to: 03_Agent_Ledgers/chat_sessions/session_{timestamp}.json[/green]")

    @on(Input.Submitted, "#ac-input")
    def handle_agent_input(self, event: Input.Submitted) -> None:
        msg = event.value.strip()
        if not msg:
            return
        if not self.is_session_active:
            self.write_agent_log("[red]Please Start Session first.[/red]")
            return
            
        inp = self.query_one("#ac-input", Input)
        inp.value = ""
        self.write_agent_log(f"\n[bold green]You:[/bold green] {msg}")
        self.shared_transcript.append({"role": "user", "text": msg})
        
        if self.session_mode == "chat":
            self.dispatch_chat_mode(msg)
        else:
            self.dispatch_live_mode_input(msg)

    @work(thread=True)
    def dispatch_chat_mode(self, message: str) -> None:
        try:
            from maccre_core.maccre_router import UniversalRouter
            if not hasattr(self, "universal_router"):
                self.universal_router = UniversalRouter()
                
            rolling_context = f"[User]: {message}"
            round_replies = {}
            
            for agent_name, session in list(self.active_sessions.items()):
                if not self.is_session_active:
                    break
                self.write_agent_log(f"[dim italic]... {agent_name} is typing ...[/dim italic]")
                reply = session.send(self.universal_router, rolling_context)
                self.write_agent_log(f"\n[bold cyan]{agent_name}:[/bold cyan] {reply}")
                self.shared_transcript.append({"role": agent_name, "text": reply})
                
                round_replies[agent_name] = reply
                rolling_context += f"\n\n[{agent_name}]: {reply}"
                
            # Inject missed context so everyone has identical histories for the next turn
            agent_names = list(self.active_sessions.keys())
            for i, name in enumerate(agent_names):
                missed_text = ""
                for j in range(i + 1, len(agent_names)):
                    other_name = agent_names[j]
                    missed_text += f"\n\n[{other_name}]: {round_replies[other_name]}"
                
                if missed_text:
                    self.active_sessions[name].history.append({"role": "user", "text": f"Observation of peers:{missed_text}"})
                    self.active_sessions[name].history.append({"role": "model", "text": "Acknowledged."})

        except Exception as e:
            self.write_agent_log(f"\n[red]Agent Error:[/red] {e}")

    def dispatch_live_mode_input(self, message: str) -> None:
        """User input in Live mode injects tension and forces agents to see it."""
        if hasattr(self, "scorekeeper"):
            self.scorekeeper.register_speech("User", tension_modifier=0.3)
            
        for name, session in self.active_sessions.items():
            session.history.append({"role": "user", "text": f"[User]: {message}"})
            session.history.append({"role": "model", "text": "Acknowledged."})

    async def _live_mode_physics_loop(self) -> None:
        """Background asyncio loop for Conversational Physics"""
        from maccre_core.orchestration.scorekeeper import ScoreKeeper
        import asyncio
        self.scorekeeper = ScoreKeeper()
        
        while self.is_session_active:
            try:
                # Only tick silence if no one is currently speaking
                if not self.is_agent_generating:
                    self.scorekeeper.tick()
                    
                    if self.scorekeeper.state.silence_duration_ms > 4000: # 4 sec silence
                        best_agent = None
                        best_score = 0.0
                        
                        for name in self.active_sessions.keys():
                            if name == self.scorekeeper.state.last_speaker:
                                continue
                                
                            turns = self.scorekeeper.state.speaker_turns.get(name, 0)
                            dominance = 1.0 / (1.0 + turns)
                            # Higher tension requires higher dominance to break silence
                            score = (0.5 * 0.4) + (self.scorekeeper.state.tension_level * 0.3) + (dominance * 0.3)
                            
                            if score > 0.2 and score > best_score:
                                best_score = score
                                best_agent = name
                                
                        if best_agent:
                            self.scorekeeper.register_speech(best_agent, tension_modifier=-0.1)
                            self.dispatch_live_mode_agent_generation(best_agent)
                        
                await asyncio.sleep(1.0)
            except asyncio.CancelledError:
                break
            except Exception as e:
                self.write_agent_log(f"[red]Physics Loop Error:[/red] {e}")
                await asyncio.sleep(1.0)

    @work(thread=True)
    def dispatch_live_mode_agent_generation(self, agent_name: str) -> None:
        try:
            self.is_agent_generating = True
            self.write_agent_log(f"[dim italic]... {agent_name} takes the floor ...[/dim italic]")
            session = self.active_sessions[agent_name]
            reply = session.send(self.universal_router, "[System]: Continue the conversation organically. You are speaking to the group.")
            self.write_agent_log(f"\n[bold cyan]{agent_name}:[/bold cyan] {reply}")
            self.shared_transcript.append({"role": agent_name, "text": reply})
            
            # Inject context
            for other_name, other_session in self.active_sessions.items():
                if other_name != agent_name:
                    other_session.history.append({"role": "user", "text": f"[{agent_name}]: {reply}"})
                    other_session.history.append({"role": "model", "text": "Acknowledged."})
        except Exception as e:
            self.write_agent_log(f"[red]Agent Error:[/red] {e}")
        finally:
            self.is_agent_generating = False
            # Reset silence so they don't immediately rapid-fire trigger again
            if hasattr(self, "scorekeeper"):
                self.scorekeeper.state.silence_duration_ms = 0

# ── Entry point ───────────────────────────────────────────────────────────────

def main() -> None:
    NexusPlex().run()

if __name__ == "__main__":
    main()

