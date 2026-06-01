"""
maccre_tui/nexus_plex.py
========================
Nexus_Plex: MACCREv2 Topology Builder TUI.

A multi-tab Textual application that lets Nexus (or any operator) create,
inspect, edit, and launch swarm topologies without writing any code.

Tabs:
  [1] Projects     — browse / create project silos in __DATACENTER
  [2] Topology     — add / edit / delete topology nodes (DataTable + modal)
  [3] Agents       — view agent_roster.csv for the active project
  [4] Launch       — run the active project and stream live logs

Usage:
    python -m maccre_tui.nexus_plex
    # or via omni run:
    omni run maccre_tui/nexus_plex.py

MACCREv2 Law Rev 19.0 compliant.
"""
from __future__ import annotations

import csv
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from textual import on, work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Container, Horizontal, ScrollableContainer
from textual.screen import ModalScreen
from textual.widgets import (
    Button,
    DataTable,
    Footer,
    Header,
    Input,
    Label,
    RichLog,
    Static,
    TabbedContent,
    TabPane,
)

from maccre_core.utils.path_resolver import get_datacenter_path, get_maccre_root

# ── Topology column definition ────────────────────────────────────────────────
_TOPO_COLS: list[str] = [
    "NODE_ID", "AGENT_NAME", "NEXT_NODE", "MODEL_OVERRIDE",
    "TEMPERATURE", "MAX_RECURSION", "WAIT_FOR", "FAILURE_TARGET",
    "ARTIFACT_PATH", "DIALOGUE_PARTNER", "DIALOGUE_ROUNDS",
]
_TOPO_DISPLAY: list[str] = [
    "NODE_ID", "AGENT", "NEXT_NODE", "WAIT_FOR", "DLG_PARTNER", "DLG_RND",
]

# ── Sentinel placeholder ───────────────────────────────────────────────────────
_EMPTY_NODE: dict[str, str] = {c: "" for c in _TOPO_COLS}


# ══════════════════════════════════════════════════════════════════════════════
# NODE EDITOR MODAL
# ══════════════════════════════════════════════════════════════════════════════

class NodeEditorModal(ModalScreen[dict[str, str] | None]):
    """Full-node edit form displayed as a modal overlay."""

    CSS = """
    NodeEditorModal {
        align: center middle;
    }
    #modal-container {
        width: 80;
        height: auto;
        background: $surface;
        border: thick $primary;
        padding: 1 2;
    }
    #modal-title {
        text-align: center;
        color: $accent;
        text-style: bold;
        margin-bottom: 1;
    }
    .field-label {
        color: $text-muted;
        margin-top: 1;
    }
    #modal-buttons {
        margin-top: 2;
        height: 3;
    }
    #btn-save   { dock: right; margin-left: 1; }
    #btn-cancel { dock: right; }
    """

    def __init__(self, node_data: dict[str, str], title: str = "Edit Node") -> None:
        super().__init__()
        self._node_data = dict(node_data)
        self._modal_title = title

    def compose(self) -> ComposeResult:
        with Container(id="modal-container"):
            yield Label(self._modal_title, id="modal-title")
            for col in _TOPO_COLS:
                yield Label(col, classes="field-label")
                yield Input(
                    value=self._node_data.get(col, ""),
                    placeholder=col.lower().replace("_", " "),
                    id=f"field-{col}",
                )
            with Horizontal(id="modal-buttons"):
                yield Button("Cancel", variant="default", id="btn-cancel")
                yield Button("Save", variant="primary", id="btn-save")

    @on(Button.Pressed, "#btn-save")
    def _save(self) -> None:
        result: dict[str, str] = {}
        for col in _TOPO_COLS:
            widget = self.query_one(f"#field-{col}", Input)
            result[col] = widget.value.strip()
        self.dismiss(result)

    @on(Button.Pressed, "#btn-cancel")
    def _cancel(self) -> None:
        self.dismiss(None)


# ══════════════════════════════════════════════════════════════════════════════
# NEXUS_PLEX APP
# ══════════════════════════════════════════════════════════════════════════════

class NexusPlex(App[None]):
    """MACCREv2 Topology Builder — Nexus_Plex v1."""

    CSS_PATH = "nexus_plex.css"
    TITLE = "Nexus_Plex  ·  MACCREv2 Topology Builder"
    BINDINGS = [
        Binding("ctrl+q", "quit", "Quit"),
        Binding("ctrl+s", "save_topology", "Save Topology"),
        Binding("ctrl+n", "add_node", "Add Node"),
        Binding("ctrl+d", "delete_node", "Delete Node"),
        Binding("ctrl+l", "launch_project", "Launch"),
        Binding("f1", "switch_tab('projects')", "Projects"),
        Binding("f2", "switch_tab('topology')", "Topology"),
        Binding("f3", "switch_tab('agents')", "Agents"),
        Binding("f4", "switch_tab('launch')", "Launch Monitor"),
    ]

    def __init__(self) -> None:
        super().__init__()
        self._active_project: str = ""
        self._topology_rows: list[dict[str, str]] = []
        self._projects: list[str] = []
        self._agents: list[dict[str, str]] = []
        self._launch_proc: subprocess.Popen[str] | None = None

    # ── Composition ───────────────────────────────────────────────────────────

    def compose(self) -> ComposeResult:
        yield Header()
        with TabbedContent(id="tabs"):
            # Tab 1: Projects
            with TabPane("📂 Projects  [F1]", id="projects"):
                yield Label("Select or create a project silo:", id="proj-label")
                with Horizontal(id="proj-toolbar"):
                    yield Input(placeholder="New project name…", id="new-proj-input")
                    yield Button("＋ Create", variant="success", id="btn-create-proj")
                    yield Button("⟳ Refresh", variant="default", id="btn-refresh-proj")
                yield DataTable(id="proj-table", show_cursor=True, zebra_stripes=True)

            # Tab 2: Topology Builder
            with TabPane("🕸  Topology  [F2]", id="topology"):
                with Horizontal(id="topo-toolbar"):
                    yield Static(id="active-proj-label", classes="status-label")
                    yield Button("＋ Add Node", variant="success", id="btn-add-node")
                    yield Button("✎ Edit", variant="primary", id="btn-edit-node")
                    yield Button("✖ Delete", variant="error", id="btn-del-node")
                    yield Button("💾 Save CSV", variant="default", id="btn-save-csv")
                yield DataTable(
                    id="topo-table",
                    show_cursor=True,
                    zebra_stripes=True,
                    cursor_type="row",
                )

            # Tab 3: Agent Roster
            with TabPane("🤖 Agents   [F3]", id="agents"):
                yield Label("Agent roster for active project:", id="agents-label")
                yield DataTable(
                    id="agents-table",
                    show_cursor=True,
                    zebra_stripes=True,
                )

            # Tab 4: Launch Monitor
            with TabPane("🚀 Launch   [F4]", id="launch"):
                with Horizontal(id="launch-toolbar"):
                    yield Static(id="launch-status", classes="status-label")
                    yield Button("▶  Launch", variant="success", id="btn-launch")
                    yield Button("⏹  Kill", variant="error", id="btn-kill")
                    yield Button("🗑  Clear Log", variant="default", id="btn-clear-log")
                yield ScrollableContainer(
                    RichLog(id="launch-log", highlight=True, markup=True, wrap=True),
                    id="log-scroll",
                )
        yield Footer()

    # ── Mount ─────────────────────────────────────────────────────────────────

    def on_mount(self) -> None:
        self._setup_proj_table()
        self._setup_topo_table()
        self._setup_agents_table()
        self._refresh_projects()

    def _setup_proj_table(self) -> None:
        tbl = self.query_one("#proj-table", DataTable)
        tbl.add_columns("Project", "Topology Nodes", "Last Modified")

    def _setup_topo_table(self) -> None:
        tbl = self.query_one("#topo-table", DataTable)
        tbl.add_columns(*_TOPO_DISPLAY)

    def _setup_agents_table(self) -> None:
        tbl = self.query_one("#agents-table", DataTable)
        tbl.add_columns("AGENT_NAME", "MODEL", "TEMPERATURE", "TOOLS", "PERSONA[:80]")

    # ── Project management ────────────────────────────────────────────────────

    def _refresh_projects(self) -> None:
        dc = get_maccre_root() / "__DATACENTER"
        tbl = self.query_one("#proj-table", DataTable)
        tbl.clear()
        self._projects = []
        if not dc.exists():
            return
        for p in sorted(dc.iterdir()):
            if not p.is_dir() or p.name.startswith("."):
                continue
            topo_csv = p / "02_Dynamic_Context" / "topology.csv"
            node_count = "—"
            if topo_csv.exists():
                try:
                    with topo_csv.open(encoding="utf-8") as f:
                        node_count = str(sum(1 for _ in csv.DictReader(f)))
                except Exception:  # noqa: BLE001
                    node_count = "?"
            mtime = ""
            wb = p / "MACCRE_Swarm_Request.xlsx"
            if wb.exists():
                import datetime  # noqa: PLC0415
                mtime = datetime.datetime.fromtimestamp(wb.stat().st_mtime).strftime("%Y-%m-%d %H:%M")
            self._projects.append(p.name)
            tbl.add_row(p.name, node_count, mtime, key=p.name)

    def _load_project(self, project_name: str) -> None:
        self._active_project = project_name
        label = self.query_one("#active-proj-label", Static)
        label.update(f"Active: [bold cyan]{project_name}[/bold cyan]")
        launch_lbl = self.query_one("#launch-status", Static)
        launch_lbl.update(f"Project: [bold]{project_name}[/bold]  |  Status: idle")
        self._load_topology()
        self._load_agents()

    def _load_topology(self) -> None:
        tbl = self.query_one("#topo-table", DataTable)
        tbl.clear()
        self._topology_rows = []
        if not self._active_project:
            return
        topo_csv = get_datacenter_path("02_Dynamic_Context", "topology.csv")
        if not topo_csv.exists():
            return
        try:
            with topo_csv.open(encoding="utf-8") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    norm: dict[str, str] = {c: str(row.get(c, "") or "") for c in _TOPO_COLS}
                    self._topology_rows.append(norm)
                    tbl.add_row(
                        norm["NODE_ID"],
                        norm["AGENT_NAME"],
                        norm["NEXT_NODE"],
                        norm["WAIT_FOR"],
                        norm["DIALOGUE_PARTNER"],
                        norm["DIALOGUE_ROUNDS"],
                        key=norm["NODE_ID"],
                    )
        except Exception as exc:  # noqa: BLE001
            self._log(f"[red]Error loading topology.csv: {exc}[/red]")

    def _load_agents(self) -> None:
        tbl = self.query_one("#agents-table", DataTable)
        tbl.clear()
        self._agents = []
        if not self._active_project:
            return
        roster = get_datacenter_path("02_Dynamic_Context", "agent_roster.csv")
        if not roster.exists():
            roster = get_maccre_root() / "__DATACENTER" / self._active_project / "agent_roster.csv"
        if not roster.exists():
            return
        try:
            with roster.open(encoding="utf-8") as f:
                for row in csv.DictReader(f):
                    self._agents.append(dict(row))
                    persona = str(row.get("PERSONA", "") or "")[:80]
                    tbl.add_row(
                        str(row.get("AGENT_NAME", "")),
                        str(row.get("MODEL", "")),
                        str(row.get("TEMPERATURE", "")),
                        str(row.get("TOOLS", "")),
                        persona,
                    )
        except Exception as exc:  # noqa: BLE001
            self._log(f"[red]Error loading roster: {exc}[/red]")

    # ── Topology editing ──────────────────────────────────────────────────────

    def _save_topology_csv(self) -> None:
        if not self._active_project:
            self._log("[yellow]No active project — select one first.[/yellow]")
            return
        topo_dir = get_maccre_root() / "__DATACENTER" / self._active_project / "02_Dynamic_Context"
        topo_dir.mkdir(parents=True, exist_ok=True)
        topo_csv = topo_dir / "topology.csv"
        try:
            with topo_csv.open("w", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=_TOPO_COLS)
                writer.writeheader()
                writer.writerows(self._topology_rows)
            self._log(f"[green]✓ topology.csv saved → {topo_csv}[/green]")
        except Exception as exc:  # noqa: BLE001
            self._log(f"[red]Error saving topology.csv: {exc}[/red]")

    def _refresh_topo_table(self) -> None:
        tbl = self.query_one("#topo-table", DataTable)
        tbl.clear()
        for row in self._topology_rows:
            tbl.add_row(
                row["NODE_ID"], row["AGENT_NAME"], row["NEXT_NODE"],
                row["WAIT_FOR"], row["DIALOGUE_PARTNER"], row["DIALOGUE_ROUNDS"],
                key=row["NODE_ID"],
            )

    # ── Launch monitor ────────────────────────────────────────────────────────

    def _log(self, text: str) -> None:
        try:
            log = self.query_one("#launch-log", RichLog)
            log.write(text)
        except Exception:  # noqa: BLE001
            pass

    @work(thread=True)
    def _stream_launch(self, project: str) -> None:
        root = str(get_maccre_root())
        python = str(get_maccre_root() / ".venv" / "Scripts" / "python.exe")
        maccre = str(get_maccre_root() / "maccre.py")
        self._launch_proc = subprocess.Popen(
            [python, maccre, "launch", project, "--yes"],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            cwd=root,
            bufsize=1,
        )
        assert self._launch_proc.stdout is not None
        for line in self._launch_proc.stdout:
            stripped = line.rstrip()
            if stripped:
                colour = (
                    "[green]" if "SWARM_COMPLETE" in stripped or "✓" in stripped
                    else "[red]" if "ERROR" in stripped or "FAULT" in stripped or "FAILED" in stripped
                    else "[yellow]" if "WARNING" in stripped or "WARN" in stripped
                    else "[cyan]" if "Lock Acquired" in stripped or "NODE_ROUTED" in stripped
                    else ""
                )
                end = "[/]" if colour else ""
                self.call_from_thread(self._log, f"{colour}{stripped}{end}")
        rc = self._launch_proc.wait()
        status = "[green]✓ Complete[/green]" if rc == 0 else f"[red]✗ Exit code {rc}[/red]"
        self.call_from_thread(self._log, f"\n{status}")
        lbl = self.query_one("#launch-status", Static)
        self.call_from_thread(lbl.update, f"Project: [bold]{project}[/bold]  |  {status}")

    # ── Button handlers ───────────────────────────────────────────────────────

    @on(Button.Pressed, "#btn-refresh-proj")
    def _on_refresh(self) -> None:
        self._refresh_projects()

    @on(Button.Pressed, "#btn-create-proj")
    def _on_create_proj(self) -> None:
        inp = self.query_one("#new-proj-input", Input)
        name = inp.value.strip().upper().replace(" ", "_")
        if not name:
            return
        silo = get_maccre_root() / "__DATACENTER" / name
        for sub in ["01_Raw_Source", "02_Dynamic_Context", "03_Agent_Ledgers",
                    "04_Code_Artifacts", "05_Rendered_Media", "06_Memory_Pins"]:
            (silo / sub).mkdir(parents=True, exist_ok=True)
        inp.value = ""
        self._refresh_projects()
        self._log(f"[green]Created project silo: {name}[/green]")

    @on(DataTable.RowSelected, "#proj-table")
    def _on_proj_selected(self, event: DataTable.RowSelected) -> None:
        if event.row_key and event.row_key.value:
            self._load_project(str(event.row_key.value))

    @on(Button.Pressed, "#btn-add-node")
    def _on_add_node(self) -> None:
        self.app.push_screen(
            NodeEditorModal(dict(_EMPTY_NODE), title="Add New Node"),
            self._on_node_saved,
        )

    @on(Button.Pressed, "#btn-edit-node")
    def _on_edit_node(self) -> None:
        tbl = self.query_one("#topo-table", DataTable)
        if tbl.cursor_row < 0 or tbl.cursor_row >= len(self._topology_rows):
            return
        node = self._topology_rows[tbl.cursor_row]
        self.app.push_screen(
            NodeEditorModal(node, title=f"Edit Node: {node['NODE_ID']}"),
            self._on_node_saved,
        )

    def _on_node_saved(self, result: dict[str, str] | None) -> None:
        if result is None:
            return
        # Update existing or insert new
        for i, row in enumerate(self._topology_rows):
            if row["NODE_ID"] == result["NODE_ID"]:
                self._topology_rows[i] = result
                self._refresh_topo_table()
                return
        self._topology_rows.append(result)
        self._refresh_topo_table()

    @on(Button.Pressed, "#btn-del-node")
    def _on_del_node(self) -> None:
        tbl = self.query_one("#topo-table", DataTable)
        if tbl.cursor_row < 0 or tbl.cursor_row >= len(self._topology_rows):
            return
        removed = self._topology_rows.pop(tbl.cursor_row)
        self._refresh_topo_table()
        self._log(f"[yellow]Deleted node: {removed['NODE_ID']}[/yellow]")

    @on(Button.Pressed, "#btn-save-csv")
    def _on_save_csv(self) -> None:
        self._save_topology_csv()

    @on(Button.Pressed, "#btn-launch")
    def _on_launch(self) -> None:
        if not self._active_project:
            self._log("[yellow]Select a project first.[/yellow]")
            return
        log = self.query_one("#launch-log", RichLog)
        log.clear()
        self._log(f"[bold cyan]▶ Launching {self._active_project}…[/bold cyan]\n")
        self._stream_launch(self._active_project)

    @on(Button.Pressed, "#btn-kill")
    def _on_kill(self) -> None:
        if self._launch_proc and self._launch_proc.poll() is None:
            self._launch_proc.terminate()
            self._log("[red]⏹ Launch process terminated.[/red]")

    @on(Button.Pressed, "#btn-clear-log")
    def _on_clear_log(self) -> None:
        self.query_one("#launch-log", RichLog).clear()

    # ── Action bindings ───────────────────────────────────────────────────────

    def action_save_topology(self) -> None:
        self._save_topology_csv()

    def action_add_node(self) -> None:
        self._on_add_node()

    def action_delete_node(self) -> None:
        self._on_del_node()

    def action_launch_project(self) -> None:
        self._on_launch()

    def action_switch_tab(self, tab_id: str) -> None:
        tabs = self.query_one("#tabs", TabbedContent)
        tabs.active = tab_id


# ── Entry point ───────────────────────────────────────────────────────────────

def main() -> None:
    NexusPlex().run()


if __name__ == "__main__":
    main()
