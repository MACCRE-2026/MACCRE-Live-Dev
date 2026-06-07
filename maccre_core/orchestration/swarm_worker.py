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
maccre_core/orchestration/swarm_worker.py
==========================================
Universal Swarm Worker — Phase 10 Sovereign Local State Machine.

All inference logic is delegated to UniversalRouter.
State machine is powered by LocalMessageBroker (SQLite).
All I/O paths are fully project-scoped via get_datacenter_path().
"""
import atexit
import json
import os
import time
from pathlib import Path
from typing import Any, Dict, Optional

from maccre_core.logger import ops_log
from maccre_core.maccre_router import UniversalRouter
from maccre_core.memory import close_all
from maccre_core.orchestration.local_broker import LocalMessageBroker
from maccre_core.orchestration.memory_engine import CognitiveMemoryEngine
from maccre_core.orchestration.tool_executor import ToolExecutor
from maccre_core.orchestration.topology_engine import TopologyEngine
from maccre_core.utils.path_resolver import get_datacenter_path

# Guarantees clean SQLite WAL checkpoint + connection close on any exit path
# (normal exit, SIGTERM, or unhandled exception crash).
atexit.register(close_all)

AGENT_ID = f"universal_node_{os.getpid()}"


class UniversalSwarmWorker:
    def __init__(self) -> None:
        print(f"[{AGENT_ID}] Initializing Universal Swarm Node...")
        self.project_name = os.environ.get("MACCRE_ACTIVE_PROJECT", "GLOBAL")
        self.router = UniversalRouter()
        self.topology: Optional[TopologyEngine] = TopologyEngine()
        self.broker = LocalMessageBroker()
        self.memory_engine = CognitiveMemoryEngine()
        self.tool_executor = ToolExecutor()
        self._is_sleeping = False  # Tracks rest state to prevent log spam

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _load_json_card(self, card_name: str) -> str:
        """Load a ROM cartridge persona card from 02_Dynamic_Context (project-scoped).

        If card_name is longer than 80 characters it is treated as an inline instruction
        rather than a card filename — no file lookup is attempted and no warning is emitted.
        This is the normal path for topology nodes that use Instruction_Override.
        """
        card_str = str(card_name).strip()
        if card_str.lower() == "none" or not card_str:
            return ""

        # Long strings are clearly inline instructions, not card names — fast-path return.
        if len(card_str) > 80:
            return card_str

        # Auto-append .json so it maps topology IDs to the physical files
        if not card_str.lower().endswith(".json"):
            card_str += ".json"

        # Project-scoped path: __DATACENTER/<ACTIVE_PROJECT>/02_Dynamic_Context/<card>.json
        card_path = get_datacenter_path("02_Dynamic_Context", card_str)
        if not card_path.exists():
            # Short text that isn't a valid card name — warn and return as-is
            print(f"[{AGENT_ID}] WARNING: Missing ROM Cartridge -> {card_str} (using as inline instruction)")
            return str(card_name).strip()

        try:
            persona_data: dict[str, Any] = json.loads(card_path.read_text(encoding="utf-8"))
            return str(persona_data.get("instructions", ""))
        except Exception as e:
            print(f"[{AGENT_ID}] ERROR reading persona {card_str}: {e}")
            return ""

    def _load_memory_pins(self) -> str:
        """Reads the project-scoped corkboard and mounts recent thoughts into the Agent's RAM."""
        mem_dir = get_datacenter_path("06_Memory_Pins")
        if not mem_dir.exists():
            return ""
        files = sorted(mem_dir.glob("*.json"), key=lambda f: f.stat().st_mtime, reverse=True)
        pins: list[str] = []
        for f in files[:10]:
            try:
                pins.append(f.read_text(encoding="utf-8"))
            except Exception:
                pass
        if not pins:
            return ""
        return "\n\n--- RECOVERED SWARM MEMORIES (CORKBOARD) ---\n" + "\n".join(pins) + "\n----------------------------------------------\n"

    def _read_local_payload(self, payload_path: str) -> str:
        """Reads the task payload directly from the local filesystem."""
        try:
            with open(payload_path, "r", encoding="utf-8") as f:
                return f.read()
        except Exception as e:
            print(f"[{AGENT_ID}] WARNING: Could not read payload at {payload_path}: {e}")
            return "NO PAYLOAD DATA."

    async def _run_live_session(self, model_id: str, system_prompt: str, current_payload: str, job_id: str, current_node: str) -> str:
        """Stream 4: Establish Live WebSocket session and listen for ScoreKeeper interrupts."""
        import asyncio
        import zmq
        import zmq.asyncio
        from maccre_core._net.live_client import GeminiLiveClient

        from maccre_core.orchestration.windows_vault import get_native_credential
        api_key = str(get_native_credential("MACCRE_Sovereign") or "").strip()
        client = GeminiLiveClient(api_key=api_key, model=model_id)
        
        ctx = zmq.asyncio.Context.instance()
        sub_socket = ctx.socket(zmq.SUB)
        sub_socket.connect("tcp://127.0.0.1:5557")
        # Listen for global interrupts and specifically routed messages for THIS agent
        sub_socket.setsockopt_string(zmq.SUBSCRIBE, "MACCRE.INTERRUPT")
        sub_socket.setsockopt_string(zmq.SUBSCRIBE, f"MACCRE.ROUTE.{AGENT_ID}")
        
        pub_socket = ctx.socket(zmq.PUB)
        pub_socket.connect("tcp://127.0.0.1:5556")
        
        gathered_text: list[str] = []
        
        async def session_runner(session: Any) -> None:
            async def zmq_listener() -> None:
                while True:
                    try:
                        topic, msg = await sub_socket.recv_multipart()
                        topic_str = topic.decode("utf-8")
                        payload = json.loads(msg.decode("utf-8"))
                        
                        if topic_str == "MACCRE.INTERRUPT" and payload.get("job_id") == job_id:
                            print(f"\n[{AGENT_ID}] ⚡ LIVE INTERRUPT: Manager triggered barge-in.")
                            await session.send(input=f"[USER OVERRIDE]: {payload.get('override_text')}", end_of_turn=True)
                            
                        elif topic_str == f"MACCRE.ROUTE.{AGENT_ID}" and payload.get("job_id") == job_id:
                            speaker = payload.get("speaker")
                            text = payload.get("text")
                            await session.send(input=f"[{speaker}]: {text}", end_of_turn=True)
                            
                    except asyncio.CancelledError:
                        break
                    except Exception as e:
                        print(f"[ZMQ Listener Error] {e}")
                        
            listener_task = asyncio.create_task(zmq_listener())
            
            print(f"[{AGENT_ID}] Live Session Bound to {model_id}. Streaming context...")
            await session.send(input=current_payload, end_of_turn=True)
            
            try:
                async for response in session.receive():
                    server_content = response.server_content
                    if server_content is None:
                        continue
                    
                    if getattr(server_content, "interrupted", False):
                        print(f"\n[{AGENT_ID}] Model acknowledges barge-in.")
                        
                    model_turn = server_content.model_turn
                    if model_turn:
                        for part in model_turn.parts:
                            if part.text:
                                gathered_text.append(part.text)
                                print(part.text, end="", flush=True)
                                # Publish speech to Manager for Routing & TUI Display
                                chat_payload = {
                                    "job_id": job_id,
                                    "agent_name": AGENT_ID,
                                    "text": part.text
                                }
                                pub_socket.send_multipart([b"MACCRE.CHAT", json.dumps(chat_payload).encode("utf-8")])
                                
            finally:
                listener_task.cancel()

        try:
            await client.run_session(system_instruction=system_prompt, run_loop_cb=session_runner)
        finally:
            sub_socket.close()
            pub_socket.close()
            
        return "".join(gathered_text)

    # ── Main Loop ─────────────────────────────────────────────────────────────

    def execute_cycle(self) -> None:
        task: Optional[Dict[str, Any]] = self.broker.fetch_and_lock_task(
            AGENT_ID, self.topology
        )
        if not task:
            if not self._is_sleeping:
                print(f"[{AGENT_ID}] Queue empty or waiting on dependencies. Sleeping.")
                self._is_sleeping = True
            time.sleep(3)
            return

        self._is_sleeping = False  # Wake up
        row_id: int = int(task["id"])
        job_id: str = str(task["job_id"])
        project_id: str = str(task.get("project_id", "UNNAMED"))
        payload_path: str = str(task["payload_path"])
        current_node: str = str(task.get("current_node", "START"))

        # Boot dual-tier telemetry
        # job_id IS the session ID — unified format: job_{YYYYMMDD-HHMMSS-{4rand}}
        from maccre_core.logger import setup_session_loggers
        setup_session_loggers(project_id, job_id)
        # source_payload_path: the ORIGINAL user document — never mutated by routing
        source_payload_path: str = str(task.get("source_payload_path") or payload_path)

        # ── Project-Scoped Job Directory ─────────────────────────────────────
        job_dir = get_datacenter_path("03_Agent_Ledgers", job_id)
        job_dir.mkdir(parents=True, exist_ok=True)
        ledger_path = str(job_dir / f"{current_node}_{row_id}.md")
        agent_log_path = str(job_dir / f"{current_node}_{row_id}_agent.log")

        # ── Dual-Stream File Logger ───────────────────────────────────────────
        import sys

        class _FileTee:
            """Lightweight file tee: mirrors writes to orig stream AND a per-job log file.

            fileno() and isatty() stubs prevent crashes when Python's logging,
            subprocess, or Windows console APIs probe the redirected stream.
            """
            def __init__(self, filepath: str, orig_stream: Any) -> None:
                self.orig_stream = orig_stream
                self.log = open(filepath, "w", encoding="utf-8")  # noqa: SIM115

            def write(self, msg: str) -> None:
                self.orig_stream.write(msg)
                self.log.write(msg)

            def flush(self) -> None:
                self.orig_stream.flush()
                self.log.flush()

            def close(self) -> None:
                self.log.close()

            def fileno(self) -> int:  # Windows console API compatibility
                return self.orig_stream.fileno()

            def isatty(self) -> bool:
                return False

        orig_stdout = sys.stdout
        orig_stderr = sys.stderr
        dual_out = _FileTee(agent_log_path, orig_stdout)
        dual_err = _FileTee(agent_log_path, orig_stderr)
        sys.stdout = dual_out  # type: ignore[assignment]
        sys.stderr = dual_err  # type: ignore[assignment]

        try:
            print(f"\n[{AGENT_ID}] Lock Acquired: job={job_id} | row={row_id} | Node: [{current_node}]")
            print(f"[{AGENT_ID}] Ledger -> {ledger_path}")

            assert self.topology is not None, "TopologyEngine must be initialized before swarm execution"
            node_config = self.topology.get_node_config(current_node)
            base_prompt = self._load_json_card(node_config.get("prompt", "none"))

            # ── Session-Scoped Artifact Directory ──────────────────────────────
            # Create 04_Code_Artifacts/{job_id}/ once per node execution.
            # {SESSION_ID} tokens in Instruction_Override and Artifact_Path are
            # substituted with the actual job_id at runtime. This guarantees
            # every swarm run writes to its own isolated subdirectory so
            # re-running the same topology never overwrites prior artifacts.
            _artifacts_dir = get_datacenter_path(f"04_Code_Artifacts/{job_id}")
            _artifacts_dir.mkdir(parents=True, exist_ok=True)

            # Substitute {SESSION_ID} in the instruction text
            base_prompt = base_prompt.replace("{SESSION_ID}", job_id)

            # ── Global Datacenter & Tool Knowledge Injection ──────────────────
            _GLOBAL_ARCHITECTURE = """
[SYSTEM REGISTRY: MACCREv2 DATACENTER ARCHITECTURE & TOOL AWARENESS]
You are operating within the MACCREv2 5-Tier Datacenter architecture.
All file paths must strictly resolve to these five silos:
  - 01_Raw_Source: External, read-only documents and inputs.
  - 02_Dynamic_Context: Agent registries, project configurations, and metadata.
  - 03_Agent_Ledgers: Your thoughts, debug logs, and intermediate text generation.
  - 04_Code_Artifacts: Final source code, markdown outputs, and structured JSON results.
  - 05_Rendered_Media: Audio/video generated assets.
  
You have access to specific functional tools (if declared in your active configuration).
You do NOT need to ask for permission to use them. If your instructions require external data, code execution, or file generation, you MUST use the provided tools.
"""
            swarm_memories = self._load_memory_pins()
            system_prompt = base_prompt + _GLOBAL_ARCHITECTURE + swarm_memories

            # ── Dual-Payload Construction ─────────────────────────────────────
            # Each node receives:
            #   [SOURCE DOCUMENT] — the original user input (unchanged through all hops)
            #   [PREVIOUS NODE OUTPUT] — the ledger written by the prior agent
            # For the first node (INGEST), these are the same file; we skip the duplicate block.
            print(f"[{AGENT_ID}] Reading payload: {payload_path}")
            ledger_content = self._read_local_payload(payload_path)
            source_content = self._read_local_payload(source_payload_path)

            if source_payload_path != payload_path and source_content not in ("NO PAYLOAD DATA.", ledger_content):
                payload_content = (
                    f"[SOURCE DOCUMENT — original user input]\n{source_content}\n\n"
                    f"[PREVIOUS NODE OUTPUT — {current_node} predecessor]\n{ledger_content}"
                )
            else:
                payload_content = ledger_content

            # ── Fan-In Artifact Injection (WAIT_FOR nodes) ────────────────
            # When this node declares wait_for predecessors that each wrote an
            # artifact_path, pre-load all those artifacts directly into the payload
            # as [GATHERED ARTIFACT: NODE_ID] blocks.  This eliminates the need for
            # fan-in nodes (e.g. GRETCHEN_ED1) to call read_file in a sequential
            # tool-call loop — a pattern that causes 2.5 Pro to repeat the first call
            # indefinitely.  All source material arrives pre-loaded in context.
            _wait_for_str: str = str(node_config.get("wait_for", "") or "")
            _wait_for_nodes: list[str] = [
                n.strip() for n in _wait_for_str.replace("|", ",").split(",") if n.strip() and n.strip().lower() != "none"
            ]
            if _wait_for_nodes:
                _gathered_blocks: list[str] = []
                for _pred_node in _wait_for_nodes:
                    try:
                        _pred_cfg = self.topology.get_node_config(_pred_node)
                        _pred_art_rel: str = str(_pred_cfg.get("artifact_path", "") or "")
                        if not _pred_art_rel:
                            continue
                        # Resolve {SESSION_ID} token in the predecessor's artifact_path
                        _pred_art_rel = _pred_art_rel.replace("{SESSION_ID}", job_id)
                        # Inject job_id subfolder if not already scoped
                        _ART_PFX = "04_Code_Artifacts/"
                        if _pred_art_rel.startswith(_ART_PFX) and job_id not in _pred_art_rel:
                            _pred_art_rel = f"{_ART_PFX}{job_id}/{_pred_art_rel[len(_ART_PFX):]}"
                        _pred_art_abs = get_datacenter_path(*_pred_art_rel.split("/"))
                        if _pred_art_abs.exists():
                            _art_content = _pred_art_abs.read_text(encoding="utf-8")
                            _gathered_blocks.append(
                                f"[GATHERED ARTIFACT: {_pred_node}]\n{_art_content}\n[END ARTIFACT: {_pred_node}]"
                            )
                            print(f"[{AGENT_ID}] Injected artifact from {_pred_node}: {_pred_art_rel}")
                        else:
                            print(f"[{AGENT_ID}] WARNING: artifact not found for {_pred_node}: {_pred_art_abs}")
                    except Exception as _exc:  # noqa: BLE001
                        print(f"[{AGENT_ID}] WARNING: could not inject artifact for {_pred_node}: {_exc}")
                if _gathered_blocks:
                    payload_content = (
                        "\n\n".join(_gathered_blocks)
                        + "\n\n"
                        + payload_content
                    )
                    print(f"[{AGENT_ID}] Fan-in: injected {len(_gathered_blocks)} gathered artifact(s) into payload.")

            # ── HOT-MIC PRIORITY INGESTION ────────────────────────────────────
            # Polled gracefully just before inference. Asynchronous intercept vector!
            interrupts = self.broker.consume_pending_interrupts(job_id)
            if interrupts:
                all_intercepts = "\n\n".join(interrupts)
                sys_intercept = (
                    f"\n\n[CRITICAL HOT-MIC SYSTEM OVERRIDE! THE USER AT THE TERMINAL JUST INTERRUPTED YOU WITH:\n"
                    f"> {all_intercepts}\n\n"
                    f"YOU MUST PIVOT TO ADDRESS THIS IMMEDIATELY BEFORE PROCEEDING WITH YOUR NORMAL INSTRUCTIONS!]"
                )
                system_prompt += sys_intercept
                print(f"\n[{AGENT_ID}] 🔥 HOT-MIC INTERCEPT RECEIVED & INJECTED! 🔥")

            model_id: str = str(node_config.get("model", "gemini-2.5-flash"))
            tools_str: str = str(node_config.get("tools_allowed", "none"))
            max_tool_turns: int = int(node_config.get("max_recursion", 3))

            # ── SEARCH_GROUNDING: inject google_search if flagged in agent_extras.json ──
            # agent_extras.json is written by the sheet_parser materialiser and
            # lives in 02_Dynamic_Context. If the agent has search_grounding=True
            # we append |google_search so the router enables live grounding.
            # GUARD: skip for dialogue nodes — the model uses native grounding
            # transparently inside DialogueRunner without needing tool injection,
            # and injecting google_search alongside function tools causes a 400.
            _dialogue_partner_peek: str = str(node_config.get("dialogue_partner", "") or "")
            _dialogue_rounds_peek: int = int(node_config.get("dialogue_rounds", 0) or 0)
            _is_dialogue_node: bool = bool(_dialogue_partner_peek and _dialogue_rounds_peek > 0)

            if not _is_dialogue_node:
                try:
                    _extras_path = get_datacenter_path("02_Dynamic_Context", "agent_extras.json")
                    if _extras_path.exists():
                        _extras: dict[str, Any] = json.loads(_extras_path.read_text(encoding="utf-8"))
                        _agent_name = str(node_config.get("agent", ""))
                        _agent_extra = _extras.get(_agent_name, {})
                        if _agent_extra.get("search_grounding") and "google_search" not in tools_str:
                            tools_str = f"{tools_str}|google_search" if tools_str.lower() != "none" else "google_search"
                            print(f"[{AGENT_ID}] Search grounding enabled for '{_agent_name}' via agent_extras.")
                except Exception:  # noqa: BLE001
                    pass  # Non-fatal — grounding simply won't activate

            # ── Execution Mode Dispatch ─────────────────────────────────────────
            # Three modes, checked in priority order:
            #   1. DIALOGUE — two persistent chat sessions alternating turns
            #   2. LIVE SESSION — streaming async session
            #   3. Standard agentic tool loop (default)
            current_payload: str = payload_content
            total_cost: float = 0.0
            final_output_text: str = ""
            tool_audit_lines: list[str] = []

            # ── {SESSION_ID} TOKEN RESOLUTION ──────────────────────────────────
            # Replace the {SESSION_ID} template token with the live job_id so
            # models write artifacts to the correct session-scoped paths.
            # Applied to: artifact_path (routing), system_prompt (write_file
            # instructions), and the initial payload (any cross-references).
            _session_token = "{SESSION_ID}"
            if _session_token in system_prompt:
                system_prompt = system_prompt.replace(_session_token, job_id)
            if _session_token in current_payload:
                current_payload = current_payload.replace(_session_token, job_id)
            _raw_artifact_path: str = str(node_config.get("artifact_path", "") or "")
            if _session_token in _raw_artifact_path:
                _raw_artifact_path = _raw_artifact_path.replace(_session_token, job_id)

            _dialogue_partner: str = _dialogue_partner_peek
            _dialogue_rounds: int = _dialogue_rounds_peek

            if _dialogue_partner and _dialogue_rounds > 0:
                # ── DIALOGUE MODE ──────────────────────────────────────────────
                # Load partner agent config from agent_roster.csv so we can
                # pull their model, temperature, and persona independently.
                from maccre_core.orchestration.dialogue_runner import DialogueRunner  # noqa: PLC0415

                _roster_path = get_datacenter_path("02_Dynamic_Context", "agent_roster.csv")
                _partner_system = ""
                _partner_model = model_id
                _partner_temp = float(node_config.get("temperature", 1.0))

                if _roster_path.exists():
                    import csv  # noqa: PLC0415
                    with _roster_path.open(encoding="utf-8") as _rf:
                        for _row in csv.DictReader(_rf):
                            if _row.get("AGENT_NAME", "").strip() == _dialogue_partner:
                                _partner_system = str(_row.get("PERSONA", "") or "")
                                _partner_model  = str(_row.get("MODEL", model_id) or model_id)
                                _partner_temp   = float(_row.get("TEMPERATURE", _partner_temp) or _partner_temp)
                                break

                if not _partner_system:
                    _partner_card = get_datacenter_path("02_Dynamic_Context", f"{_dialogue_partner}.json")
                    if _partner_card.exists():
                        import json as _json  # noqa: PLC0415
                        _pdata = _json.loads(_partner_card.read_text(encoding="utf-8"))
                        _partner_system = str(_pdata.get("persona", "") or _pdata.get("system_prompt", ""))
                        _partner_model  = str(_pdata.get("model", _partner_model) or _partner_model)
                        _partner_temp   = float(_pdata.get("temperature", _partner_temp) or _partner_temp)

                print(
                    f"[{AGENT_ID}] DIALOGUE MODE: {current_node} ↔ {_dialogue_partner} "
                    f"| rounds={_dialogue_rounds} | partner_model={_partner_model}"
                )

                _dialogue_runner = DialogueRunner(
                    router=self.router,
                    agent_a_model=model_id,
                    agent_a_system=system_prompt,
                    agent_a_temperature=float(node_config.get("temperature", 1.0)),
                    agent_b_model=_partner_model,
                    agent_b_system=_partner_system,
                    agent_b_temperature=_partner_temp,
                    num_rounds=_dialogue_rounds,
                    agent_a_label=str(node_config.get("agent", current_node)),
                    agent_b_label=_dialogue_partner,
                )
                final_output_text, total_cost = _dialogue_runner.run(current_payload)

                # ── Dialogue transcript → artifact_path ───────────────────────────────
                # When a dialogue node declares an artifact_path, write the full
                # transcript there immediately after the run completes.  Without this
                # step the artifact-coherent routing block below cannot find the file
                # and emits WARNING: artifact_path not found — falling back to ledger.
                if _raw_artifact_path:
                    # Mirror the routing block's auto-scope: if the path starts with
                    # 04_Code_Artifacts/ and the job_id isn't already injected, insert it
                    # so the transcript lands at the same location the routing block
                    # will look for (e.g. 04_Code_Artifacts/job_xxx/project/file.md).
                    _ART_PFX = "04_Code_Artifacts/"
                    _dlg_art_rel = _raw_artifact_path
                    if _dlg_art_rel.startswith(_ART_PFX) and job_id not in _dlg_art_rel:
                        _dlg_art_rel = f"{_ART_PFX}{job_id}/{_dlg_art_rel[len(_ART_PFX):]}"
                    _dlg_art_abs: Path = get_datacenter_path(*_dlg_art_rel.split("/"))
                    _dlg_art_abs.parent.mkdir(parents=True, exist_ok=True)
                    try:
                        _dlg_art_abs.write_text(final_output_text, encoding="utf-8")
                        print(
                            f"[{AGENT_ID}] DialogueRunner transcript written → "
                            f"{_dlg_art_abs}"
                        )
                    except Exception as _dlg_write_err:  # noqa: BLE001
                        print(
                            f"[{AGENT_ID}] WARNING: Could not write dialogue artifact "
                            f"'{_dlg_art_rel}': {_dlg_write_err}"
                        )

            elif str(node_config.get("live_profile", "")).lower() in ("true", "1", "yes"):

                import asyncio
                print(f"[{AGENT_ID}] Executing via STREAM 4 LIVE SESSION.")
                final_output_text = asyncio.run(self._run_live_session(model_id, system_prompt, current_payload, job_id, current_node))
                task_cost = 0.0
                total_cost = 0.0
            else:
                # Multi-turn execution bounded by max_recursion.
                for turn_idx in range(max_tool_turns + 1):
                    is_last: bool = (turn_idx >= max_tool_turns)

                    output_text, turn_cost = self.router.generate(
                        model_name=model_id,
                        payload=current_payload,
                        system_prompt=system_prompt,
                        tools_str=tools_str,
                        temperature=float(node_config["temperature"]),
                    )
                    total_cost += turn_cost

                    did_fire, updated_prompt = self.tool_executor.run(
                        output_text,
                        current_payload,
                        project_id=self.project_name,
                        session_id=job_id,
                        agent_id=AGENT_ID,
                        is_final_turn=is_last,
                    )

                    if not did_fire:
                        # Clean prose output — loop terminates naturally.
                        final_output_text = output_text
                        if tool_audit_lines:
                            print(f"[{AGENT_ID}] Tool loop complete: {turn_idx} tool turn(s) → clean output.")
                        break

                    # Capture raw tool call text for forensic audit sidecar.
                    tool_audit_lines.append(f"## TOOL TURN {turn_idx + 1}/{max_tool_turns}\n{output_text}")

                    if is_last:
                        # Graceful close: agent hit the recursion limit mid-sequence.
                        # Give it one final tool-free generation to flush accumulated work.
                        # This applies universally — any agent in any topology recovers here
                        # rather than producing a dangling tool-call as its ledger output.
                        print(f"[{AGENT_ID}] Max tool turns ({max_tool_turns}) reached — graceful close turn.")
                        close_prompt = (
                            f"{updated_prompt}\n\n"
                            "[SYSTEM: Your tool budget is exhausted. Do not request any more tool calls. "
                            "You must now produce your complete final output as prose immediately. "
                            "Consolidate all findings from this session and write your structured output now.]"
                        )
                        close_text, close_cost = self.router.generate(
                            model_name=model_id,
                            payload=close_prompt,
                            system_prompt=system_prompt,
                            tools_str="none",
                            temperature=float(node_config["temperature"]),
                        )
                        total_cost += close_cost
                        final_output_text = close_text
                        tool_audit_lines.append(f"## GRACEFUL CLOSE TURN\n{close_text}")
                        print(f"[{AGENT_ID}] Graceful close: {len(close_text)} chars flushed.")
                        break

                    # ── Terminal tool detection ───────────────────────────────────
                    # write_file / execute_render_pipeline are "done" signals: their
                    # side-effect (file written / render queued) already happened.
                    # Feeding "continue" back causes the model to call them again in
                    # a loop. Detect and terminate immediately.
                    _TERMINAL_TOOLS = ("write_file", "execute_render_pipeline", "render_podcast_audio")
                    _fired_terminal = any(
                        f"[TOOL CALL REQUESTED: {_t}" in output_text
                        or f"[TOOL_CALL]: {_t}" in output_text
                        for _t in _TERMINAL_TOOLS
                    )
                    if _fired_terminal:
                        final_output_text = output_text
                        print(f"[{AGENT_ID}] Terminal tool fired — closing loop after turn {turn_idx + 1}.")
                        break
                    # ─────────────────────────────────────────────────────────────

                    # Extract the tool result block, stripping the [SYSTEM] tail
                    # so intermediate turns get "continue" not "stop" messaging.
                    cb_start = updated_prompt.find("[SYSTEM_TOOL_CALLBACK", len(current_payload))
                    sys_pos = updated_prompt.find("\n\n[SYSTEM]:", cb_start if cb_start > -1 else 0)
                    if cb_start > -1 and sys_pos > -1:
                        tool_result_block = updated_prompt[cb_start:sys_pos].strip()
                    elif cb_start > -1:
                        tool_result_block = updated_prompt[cb_start:].strip()
                    else:
                        tool_result_block = "[TOOL_RESULT]: Tool executed (result not captured in prompt)."

                    remaining = max_tool_turns - turn_idx - 1
                    current_payload = (
                        f"{current_payload}\n\n{tool_result_block}\n\n"
                        f"[SYSTEM]: Tool result received. {remaining} tool turn(s) remaining. "
                        "Continue — call your next tool or produce your final output directly."
                    )
                    final_output_text = output_text  # fallback if loop exits unexpectedly

            task_cost = total_cost
            raw_model_output = final_output_text

            print(f"[{AGENT_ID}] Generation complete. Billed Cost: ${task_cost:.6f}")

            ledger_content_out = raw_model_output
            with open(ledger_path, "w", encoding="utf-8") as f:
                f.write(ledger_content_out)

            # ── Forensic Tool Audit Sidecar ───────────────────────────────────
            # Written alongside the ledger whenever tools fired during the loop.
            # Captures every tool call + result verbatim for effectiveness auditing.
            if tool_audit_lines:
                from datetime import datetime, timezone  # noqa: PLC0415
                audit_path = Path(ledger_path).parent / f"tool_audit_{current_node}_{row_id}.md"
                audit_ts = datetime.now(tz=timezone.utc).isoformat()
                audit_header = f"# Tool Audit — {current_node} | {job_id} | {audit_ts}\n\n"
                audit_body = "\n\n".join(tool_audit_lines) + f"\n\n## FINAL OUTPUT\n{final_output_text}"
                with open(audit_path, "w", encoding="utf-8") as af:
                    af.write(audit_header + audit_body)
                print(f"[{AGENT_ID}] Tool audit sidecar: {audit_path}")

            # ── LIVE STREAMING ACOUSTICS ──────────────────────────────────────
            # Trigger real-time conversational streaming for non-director nodes
            if "director" not in AGENT_ID.lower():
                # live_stream_audio(ledger_content_out, AGENT_ID, job_id, current_node)
                pass

            self.memory_engine.extract_and_store(ledger_content_out, current_node, job_id)

            next_node: str = str(node_config["next_node_success"])

            # ── Phase 4: Conditional Routing ─────────────────────────────────────────
            # If the node's output contains ROUTE_TO:<NODE_ID>, override the static
            # next_node with the model-specified target.  This enables backward routing
            # (e.g. JUDGE re-queuing REFINER) without hardcoding the loop in the CSV.
            #
            # Safety constraints:
            #  1. Target must exist in the topology (no phantom routing)
            #  2. Target must be a valid string (not a terminal sentinel)
            #  3. The current node's max_recursion already bounds total re-queues
            import re as _re  # noqa: PLC0415
            _ROUTE_TO_PATTERN = _re.compile(r"ROUTE_TO:([A-Z][A-Z0-9_]*)", _re.IGNORECASE)
            _route_match = _ROUTE_TO_PATTERN.search(raw_model_output or "")
            if _route_match:
                _candidate = _route_match.group(1).strip().upper()
                _topology_map = self.topology.get_topology() if self.topology else {}
                if _candidate and _candidate not in {"STOP", "DONE", "TERMINATE", "FAILED"} and _candidate in _topology_map:
                    print(
                        f"[{AGENT_ID}] CONDITIONAL ROUTE: '{next_node}' overridden by "
                        f"ROUTE_TO:{_candidate} (model-directed)"
                    )
                    next_node = _candidate
                elif _candidate:
                    print(
                        f"[{AGENT_ID}] CONDITIONAL ROUTE: ROUTE_TO:{_candidate} ignored "
                        f"(target not in topology or is terminal sentinel)"
                    )

            ops_log.node_routed(
                agent_name=str(node_config.get("agent_name", current_node)),
                next_node=next_node,
                job_id=job_id,
                agent_id=AGENT_ID,
                source_node=current_node,
            )
            # Read max_recursion config targeting exactly the NEXT node limit
            max_rec = 3
            try:
                if self.topology:
                    tgt_cfg = self.topology.get_node_config(next_node)
                    max_rec = int(tgt_cfg.get("max_recursion", 3))
            except Exception:
                pass

            # ── Artifact-Coherent Routing ─────────────────────────────────────────────
            # If the topology node declares an Artifact_Path, route the next node to
            # the canonical output file rather than the raw generation ledger.
            # Falls back to ledger silently if the artifact isn't present (e.g. agent
            # skipped the write_file call).
            _artifact_rel = (
                str(node_config.get("artifact_path", ""))
                .strip()
                .replace("{SESSION_ID}", job_id)  # resolve explicit token
            )
            # Mirror the write_file auto-scoping: if the artifact lives in
            # 04_Code_Artifacts/ but isn't already session-scoped, inject job_id
            # so the routing lookup matches where write_file actually wrote the file.
            _ART_PREFIX = "04_Code_Artifacts/"
            if _artifact_rel.startswith(_ART_PREFIX) and job_id not in _artifact_rel:
                _art_rel_part = _artifact_rel[len(_ART_PREFIX):]
                _artifact_rel = f"{_ART_PREFIX}{job_id}/{_art_rel_part}"

            if _artifact_rel:
                _artifact_abs: Path = get_datacenter_path(_artifact_rel)
                if _artifact_abs.exists():
                    routing_payload_path = str(_artifact_abs)
                    print(f"[{AGENT_ID}] Routing via artifact: {routing_payload_path}")
                else:
                    routing_payload_path = ledger_path
                    print(
                        f"[{AGENT_ID}] WARNING: artifact_path '{_artifact_rel}' not found — "
                        f"falling back to ledger."
                    )
            else:
                routing_payload_path = ledger_path

            self.broker.route_task(
                row_id,
                job_id,
                next_node,
                new_payload_path=routing_payload_path,
                actual_cost=task_cost,
                source_payload_path=source_payload_path,
                max_recursion=max_rec,
            )

            # ── Auto-promote topology to library on terminal STOP success ─────
            if next_node.strip().upper() in ("STOP", "DONE", "TERMINATE"):
                try:
                    from maccre_core.tools.admin_tools import promote_topology_to_library  # noqa: PLC0415
                    promo_name = f"job_{job_id}_node_{current_node}"
                    promo_result = promote_topology_to_library(
                        topology_name=promo_name,
                        job_id=job_id,
                    )
                    print(f"[{AGENT_ID}] Topology Promotion: {promo_result}")
                except Exception as promo_err:
                    print(f"[{AGENT_ID}] WARNING: Topology promotion failed (non-fatal): {promo_err}")

        except Exception as e:
            import traceback
            print(f"[{AGENT_ID}] CRITICAL FAILURE: {e}.")
            print(traceback.format_exc())
            fail_target = "FAILED"
            try:
                fail_target = str(node_config.get("next_node_failure", "FAILED")).strip()  # type: ignore[possibly-unbound]
            except Exception:
                pass
            print(f"[{AGENT_ID}] Routing task to [{fail_target}]")
            self.broker.route_task(  # type: ignore[possibly-unbound]
                row_id,
                job_id,
                fail_target,
                new_payload_path=payload_path,
                actual_cost=0.0,
                source_payload_path=source_payload_path,
            )
        finally:
            sys.stdout = orig_stdout
            sys.stderr = orig_stderr
            dual_out.close()
            dual_err.close()


if __name__ == "__main__":
    worker = UniversalSwarmWorker()
    print(f"=== UNIVERSAL SWARM NODE {AGENT_ID} ONLINE ===")
    while True:
        worker.execute_cycle()
        time.sleep(0)  # yield to event loop
