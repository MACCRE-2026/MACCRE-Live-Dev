# ┌─────────────────────────────────────────────────────────────────────────────┐
# │  MACCREv2 ENGINEERING DOCTRINE                             Law Rev: 19.0   │
# ├─────────────────────────────────────────────────────────────────────────────┤
# │  I.   TYPING      All signatures: explicit Python 3.11+ type hints.        │
# │  II.  LINTING     Zero unused imports. No wildcards. 120-char line max.    │
# │  III. PATHS       Never hardcode absolute paths. Use get_maccre_root().     │
# │                   Default params: def f(p:str='') -> None: p=p or root/x   │
# │  IV.  DATACENTER  5-Tier: 01_Raw_Source · 02_Dynamic_Context               │
# │                           03_Agent_Ledgers · 04_Code_Artifacts             │
# │                           05_Rendered_Media                                 │
# │  V.   DIAMOND     Gen: temp=1.0  ·  Critic: temp=0.1 + dataclass schema   │
# │  VI.  ABSTRACTION All I/O behind abc.ABC before any concrete driver.       │
# │  VII. TEARDOWN    try/finally on all handles (omni clean compliance).      │
# │  VIII.TELEMETRY   No bare print(). logger only. JSON → 03_Agent_Ledgers.  │
# └─────────────────────────────────────────────────────────────────────────────┘
"""
maccre_core/orchestration/topology_engine.py
=============================================
Sovereign Local Control Plane: Maps a local CSV file to Swarm Routing.

Replaces the Google Sheets API with a zero-dependency csv module reader.
Uses a TTL-based in-memory cache so the swarm avoids redundant disk reads
while still picking up live edits within 5 seconds.
"""
import os
import csv
from typing import Dict, Any


from maccre_core.utils.path_resolver import get_datacenter_path
from maccre_core.orchestration.topology_interface import TopologyProvider

import logging

logger = logging.getLogger(__name__)


class NodeConfig(dict):  # type: ignore[type-arg]
    """Typed dict shape for a single swarm node configuration."""


class TopologyEngine(TopologyProvider):
    """Sovereign Local Control Plane: Maps local CSV to Swarm Routing."""

    def __init__(self, csv_path: str | None = None) -> None:
        self.csv_path = csv_path or str(get_datacenter_path("02_Dynamic_Context", "topology.csv"))
        self._cached_graph: Dict[str, Any] = {}
        self._last_pull_time: float = 0.0
        self._cache_ttl_seconds: float = 5.0  # Fast refresh for local disk

    def get_topology(self) -> Dict[str, Any]:
        """Returns the Swarm Graph, reloading from disk if the TTL has expired."""
        import time
        current_time = time.time()
        if not self._cached_graph or (current_time - self._last_pull_time) > self._cache_ttl_seconds:
            self._cached_graph = self._pull_from_csv()
            self._last_pull_time = current_time
        return self._cached_graph

    def flush_cache(self) -> None:
        """Forces the graph to be reloaded on the next get_topology() call."""
        self._cached_graph = {}
        self._last_pull_time = 0.0

    def patch_node(self, node_id: str, field: str, value: str) -> None:
        """Rewrite a single cell in topology.csv and hot-reload."""
        import csv
        import tempfile
        import shutil
        import os

        temp_file = tempfile.NamedTemporaryFile(mode='w', delete=False, newline='', encoding='utf-8-sig')
        field_upper = field.upper()
        patched = False

        with open(self.csv_path, mode='r', encoding='utf-8-sig') as infile, temp_file:
            reader = csv.reader(infile)
            writer = csv.writer(temp_file)
            try:
                headers = next(reader)
            except StopIteration:
                os.remove(temp_file.name)
                return
            
            writer.writerow(headers)
            header_map = {h.strip().upper(): i for i, h in enumerate(headers)}
            
            if field_upper not in header_map:
                os.remove(temp_file.name)
                raise KeyError(f"Column '{field}' not found in topology.csv")
                
            col_idx = header_map[field_upper]
            node_id_idx = header_map.get("NODE_ID", -1)
            
            for row in reader:
                if node_id_idx != -1 and len(row) > node_id_idx and row[node_id_idx].strip().upper() == node_id.upper():
                    while len(row) <= col_idx:
                        row.append("")
                    row[col_idx] = value
                    patched = True
                writer.writerow(row)
                
        if patched:
            shutil.move(temp_file.name, self.csv_path)
            self.flush_cache()
        else:
            os.remove(temp_file.name)
            raise ValueError(f"Node '{node_id}' not found in topology.csv")

    def _pull_from_csv(self) -> Dict[str, Any]:
        """Loads and parses the CSV into the engine dictionary."""
        from maccre_core.utils.secret_auth import is_topology_approved
        from maccre_core.utils.path_resolver import get_maccre_root

        if not os.path.exists(self.csv_path):
            # Attempt GLOBAL fallback constraint
            fallback_path = get_maccre_root() / "__DATACENTER" / "GLOBAL" / "02_Dynamic_Context" / "topology.csv"
            if not fallback_path.exists():
                raise FileNotFoundError(f"Topology missing at {self.csv_path} and GLOBAL fallback.")
            self.csv_path = str(fallback_path)

        if not is_topology_approved(self.csv_path):
            raise PermissionError(f"DENIED: Topology {self.csv_path} lacks Hardware Auth Stamp.")

        try:
            # 1. Load the Base Agent Configuration Matrix from the Agent Roster
            agent_roster: Dict[str, Dict[str, str]] = {}
            from maccre_core.agent_library import get_agent_store # noqa: PLC0415
            from pathlib import Path # noqa: PLC0415
            
            # Derive project_id from csv_path (e.g. __DATACENTER/GLOBAL/02_Dynamic_Context/topology.csv -> GLOBAL)
            try:
                project_id = Path(self.csv_path).parent.parent.name
            except Exception:
                project_id = "GLOBAL"
            
            # Load from project library first, then global
            store_project = get_agent_store(project_id)
            for agent in store_project.load_all():
                # Remap keys to match the capitalized legacy keys expected by the engine
                agent_roster[agent["agent_name"]] = {
                    "System_Prompt": agent.get("system_prompt", ""),
                    "Model": agent.get("model", ""),
                    "Tools_Allowed": agent.get("tools_allowed", "")
                }
                
            if project_id.upper() != "GLOBAL":
                store_global = get_agent_store("GLOBAL")
                for agent in store_global.load_all():
                    if agent["agent_name"] not in agent_roster:
                        agent_roster[agent["agent_name"]] = {
                            "System_Prompt": agent.get("system_prompt", ""),
                            "Model": agent.get("model", ""),
                            "Tools_Allowed": agent.get("tools_allowed", "")
                        }
            
            # Fallback for legacy csv if needed (for older installations)
            roster_path = get_maccre_root() / "__DATACENTER" / "GLOBAL" / "agent_roster.csv"
            if roster_path.exists():
                with open(roster_path, "r", encoding="utf-8") as f:
                    reader = csv.DictReader(f)
                    for r in reader:
                        a_name = r.get('Agent_Name', '').strip()
                        if a_name and a_name not in agent_roster:
                            agent_roster[a_name] = dict(r)
                            
            # 2. Parse the Active Swarm Topology and merge overrides
            graph: Dict[str, Any] = {}
            with open(self.csv_path, mode='r', encoding='utf-8-sig') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    # Normalise all CSV column keys to uppercase so the engine
                    # is resilient regardless of what case the workbook template writes.
                    row_upper: dict[str, str] = {k.upper(): v for k, v in row.items()}

                    node_id = str(row_upper.get('NODE_ID', '')).strip()
                    if not node_id:
                        continue

                    try:
                        temp = float(row_upper.get('TEMPERATURE', 0.7))
                    except ValueError:
                        temp = 0.7

                    agent_name = str(row_upper.get('AGENT_NAME', node_id)).strip()
                    roster_profile: Dict[str, str] = agent_roster.get(agent_name, {})

                    # Merge Overrides with Roster Baselines
                    base_prompt: str = roster_profile.get("System_Prompt", roster_profile.get("system_prompt", ""))
                    topo_prompt: str = str(row_upper.get('INSTRUCTION_OVERRIDE', '')).strip()
                    final_prompt: str = topo_prompt if topo_prompt else base_prompt

                    base_model: str = roster_profile.get("Model", roster_profile.get("model", "gemini-2.5-flash"))
                    topo_model: str = str(row_upper.get('MODEL_OVERRIDE', '')).strip()
                    final_model: str = topo_model if topo_model else base_model

                    base_tools: str = roster_profile.get("Tools_Allowed", roster_profile.get("tools_allowed", "none"))
                    topo_tools: str = str(row_upper.get('TOOLS_ALLOWED', '')).strip()
                    final_tools: str = topo_tools if topo_tools else base_tools

                    try:
                        max_rec = int(row_upper.get('MAX_RECURSION', 3))
                    except ValueError:
                        max_rec = 3

                    graph[node_id] = {
                        "prompt": final_prompt,
                        "artifact_path": str(row_upper.get("ARTIFACT_PATH", "")).strip(),
                        "next_node_success": str(row_upper.get('NEXT_NODE', 'DONE')).strip(),
                        "next_node_failure": str(row_upper.get('FAILURE_TARGET', 'FAILED')).strip(),
                        "wait_for": str(row_upper.get('WAIT_FOR', 'none')).strip() or 'none',
                        "temperature": temp,
                        "tools_allowed": final_tools,
                        "model": final_model,
                        "agent_name": agent_name,
                        "max_recursion": max_rec,
                        "live_profile": str(row_upper.get('LIVE_PROFILE', '')).strip(),
                        "payload_mode": str(row_upper.get('PAYLOAD_MODE', 'Unified Ledger')).strip() or 'Unified Ledger',
                        # ── Dialogue Mode ────────────────────────────────────────
                        # When set, swarm_worker fires DialogueRunner instead of
                        # the standard single-shot generate loop.
                        "dialogue_partner": str(row_upper.get('DIALOGUE_PARTNER', '') or '').strip(),
                        "dialogue_rounds":  int(row_upper.get('DIALOGUE_ROUNDS', 0) or 0),
                        # ── Roster passthrough ───────────────────────────────────
                        "agent": agent_name,
                    }
            # 3. Merge ephemeral macro nodes from SQLite registry
            try:
                from maccre_core.macronode_registry import get_macronode_store  # noqa: PLC0415
                store = get_macronode_store()
                ephemeral_data = store.load_ephemeral_graph()
                for k, v in ephemeral_data.items():
                    graph[k] = v
            except Exception as e:  # noqa: BLE001
                logger.info(f"[TopologyEngine] Failed to merge ephemeral macros: {e}")

            return graph

        except Exception as e:
            logger.info(f"[TopologyEngine] Read Collision / Failure: {e}")
            return self._cached_graph  # Fallback to RAM cache

    def get_node_config(self, node_id: str) -> Dict[str, Any]:
        """Retrieve the configuration dict for a single named node.

        Args:
            node_id: The string key identifying the node (e.g. ``"START"``).

        Returns:
            A dict with keys: prompt, next_node_success, next_node_failure,
            temperature, tools_allowed, model.

        Raises:
            ValueError: If the node_id does not exist in the local topology.
        """
        topology = self.get_topology()
        if node_id not in topology:
            raise ValueError(f"CRITICAL: Node '{node_id}' missing from local Control Plane.")
        return topology[node_id]

    def merge_config_overlay(self, node_id: str, overlay: Dict[str, Any]) -> None:
        """Merge a config overlay dict into the cached topology graph for a node.

        This allows FlowStep.config fields (e.g. scatter_targets, tether_id,
        gate predicates) to be injected at runtime without modifying topology.csv.
        The overlay is merged into the cached graph — subsequent ``get_node_config``
        calls will return the merged result.

        Args:
            node_id: The node to overlay.
            overlay: Dict of config fields to merge.
        """
        topology = self.get_topology()
        if node_id in topology:
            topology[node_id].update(overlay)
        else:
            # Node might not exist yet (e.g. CTRL_ nodes added via TUI)
            topology[node_id] = dict(overlay)
        self._cached_graph = topology

    def validate(self) -> "ValidationReport":
        """Pre-flight validation of the loaded topology graph.

        Checks every node for:
          - Missing instruction (no Instruction_Override AND no roster System_Prompt)
          - Empty model (would cause a silent routing failure)
          - Temperature out of valid range [0.0, 2.0]
          - Next_Node references that don't exist in the graph (DAG integrity)

        Returns a ValidationReport. Call report.is_ok before spending any API tokens.

        Set env var MACCRE_SKIP_VALIDATE=1 to bypass (for dynamic/runtime topologies).
        """
        import os as _os
        if _os.environ.get("MACCRE_SKIP_VALIDATE") == "1":
            return ValidationReport(issues=[], skipped=True)

        topology = self.get_topology()
        # Terminal sentinels — valid Next_Node targets that don't need to exist as nodes
        _TERMINALS = {"STOP", "DONE", "TERMINATE", "FAILED", "HUMAN_GATE", "END", ""}

        issues: list[dict[str, str]] = []

        for node_id, cfg in topology.items():
            # 1. Instruction check — must have at least one source of system prompt
            if not str(cfg.get("prompt", "")).strip():
                issues.append({
                    "node": node_id,
                    "field": "prompt/Instruction_Override",
                    "severity": "ERROR",
                    "detail": "No system prompt and no Instruction_Override. Agent has no directive.",
                })

            # 2. Model check
            if not str(cfg.get("model", "")).strip():
                issues.append({
                    "node": node_id,
                    "field": "model",
                    "severity": "ERROR",
                    "detail": "No model specified. Inheriting blank string causes router crash.",
                })

            # 3. Temperature range
            try:
                temp = float(cfg.get("temperature", 0.7))
                if not (0.0 <= temp <= 2.0):
                    issues.append({
                        "node": node_id,
                        "field": "temperature",
                        "severity": "WARN",
                        "detail": f"Temperature {temp} is outside valid range [0.0, 2.0].",
                    })
            except (TypeError, ValueError):
                issues.append({
                    "node": node_id,
                    "field": "temperature",
                    "severity": "WARN",
                    "detail": f"Temperature '{cfg.get('temperature')}' is not a valid float.",
                })

            # 4. DAG integrity — Next_Node must exist or be a known terminal
            for next_key in ("next_node_success", "next_node_failure"):
                raw_next = str(cfg.get(next_key, "")).strip()
                # Fan-out: comma-separated node IDs
                targets = [t.strip() for t in raw_next.split(",") if t.strip()]
                for target in targets:
                    if target.upper() in _TERMINALS:
                        continue
                    if target not in topology:
                        issues.append({
                            "node": node_id,
                            "field": next_key,
                            "severity": "ERROR",
                            "detail": f"Next node '{target}' does not exist in topology.",
                        })


        # 5. Wait_For targets must exist in topology
            _wait_for_raw: str = str(cfg.get("wait_for", "") or "").strip()
            if _wait_for_raw and _wait_for_raw.lower() != "none":
                _wait_targets = [w.strip() for w in _wait_for_raw.replace("|", ",").split(",") if w.strip()]
                for _wt in _wait_targets:
                    if _wt not in topology:
                        issues.append({
                            "node": node_id,
                            "field": "wait_for",
                            "severity": "ERROR",
                            "detail": f"Wait_For target '{_wt}' does not exist in topology.",
                        })

                # 5b. Fan-in size warning — large wait_for lists risk context overflow
                if len(_wait_targets) > 5:
                    issues.append({
                        "node": node_id,
                        "field": "wait_for",
                        "severity": "WARN",
                        "detail": (
                            f"Fan-in has {len(_wait_targets)} gathered artifacts — "
                            "exceeding 5 may saturate the context window."
                        ),
                    })

        # 6. Circular wait_for dependency detection (post-loop, graph-level)
        # Build an adjacency map: node -> set of nodes it must wait for
        _wait_graph: dict[str, set[str]] = {}
        for _nid, _cfg in topology.items():
            _raw = str(_cfg.get("wait_for", "") or "").strip()
            if _raw and _raw.lower() != "none":
                _wait_graph[_nid] = {
                    w.strip() for w in _raw.replace("|", ",").split(",") if w.strip()
                }
            else:
                _wait_graph[_nid] = set()

        # DFS cycle detection on the wait_for graph
        _visited: set[str] = set()
        _in_stack: set[str] = set()

        def _has_cycle(node: str) -> bool:
            _visited.add(node)
            _in_stack.add(node)
            for neighbour in _wait_graph.get(node, set()):
                if neighbour not in topology:
                    continue  # already caught by check 5
                if neighbour not in _visited:
                    if _has_cycle(neighbour):
                        return True
                elif neighbour in _in_stack:
                    return True
            _in_stack.discard(node)
            return False

        for _nid in topology:
            if _nid not in _visited:
                if _has_cycle(_nid):
                    issues.append({
                        "node": _nid,
                        "field": "wait_for",
                        "severity": "ERROR",
                        "detail": "Circular wait_for dependency detected — topology would deadlock.",
                    })

        # 7. dialogue_partner must exist in agent_roster.csv when dialogue_rounds > 0
        import csv as _csv  # noqa: PLC0415
        from maccre_core.utils.path_resolver import get_maccre_root  # noqa: PLC0415
        _roster_path = get_maccre_root() / "__DATACENTER" / "GLOBAL" / "agent_roster.csv"
        _roster_names: set[str] = set()
        if _roster_path.exists():
            with _roster_path.open(encoding="utf-8") as _rf:
                for _rrow in _csv.DictReader(_rf):
                    _rname = str(_rrow.get("AGENT_NAME", "") or "").strip()
                    if _rname:
                        _roster_names.add(_rname)

        for _nid, _cfg in topology.items():
            _dp = str(_cfg.get("dialogue_partner", "") or "").strip()
            _dr_raw = str(_cfg.get("dialogue_rounds", "0") or "0").strip()
            try:
                _dr = int(float(_dr_raw))
            except (TypeError, ValueError):
                _dr = 0
            if _dp and _dr > 0 and _roster_names and _dp not in _roster_names:
                issues.append({
                    "node": _nid,
                    "field": "dialogue_partner",
                    "severity": "ERROR",
                    "detail": f"Dialogue partner '{_dp}' not found in agent_roster.csv.",
                })

        return ValidationReport(issues=issues, skipped=False)



class ValidationReport:
    """Result of TopologyEngine.validate(). Inspect before spending API tokens."""

    def __init__(self, issues: list[dict[str, str]], skipped: bool = False) -> None:
        self.issues = issues
        self.skipped = skipped

    @property
    def is_ok(self) -> bool:
        """True when there are no ERROR-severity issues."""
        return not any(i["severity"] == "ERROR" for i in self.issues)

    def render_table(self) -> str:
        """Human-readable table for terminal output."""
        if self.skipped:
            return "  [VALIDATE] Skipped (MACCRE_SKIP_VALIDATE=1)\n"
        if not self.issues:
            return "  [VALIDATE] ✓ All topology nodes passed pre-flight.\n"
        lines = [
            f"  {'NODE':<20} {'SEVERITY':<8} {'FIELD':<28} DETAIL",
            "  " + "-" * 90,
        ]
        for issue in self.issues:
            lines.append(
                f"  {issue['node']:<20} {issue['severity']:<8} {issue['field']:<28} {issue['detail']}"
            )
        return "\n".join(lines) + "\n"
