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
import logging
import time
from pathlib import Path
from typing import Any, Dict, Optional

from maccre_core.logger import ops_log
from maccre_core.maccre_router import UniversalRouter
from maccre_core.memory import close_all
from maccre_core.orchestration.broker_interface import MessageBroker
from maccre_core.orchestration.local_broker import LocalMessageBroker
from maccre_core.orchestration.memory_engine import CognitiveMemoryEngine
from maccre_core.orchestration.tool_executor import ToolExecutor
from maccre_core.orchestration.topology_interface import TopologyProvider
from maccre_core.orchestration.topology_engine import TopologyEngine
from maccre_core.utils.path_resolver import get_datacenter_path

# Guarantees clean SQLite WAL checkpoint + connection close on any exit path
# (normal exit, SIGTERM, or unhandled exception crash).
atexit.register(close_all)

AGENT_ID = f"universal_node_{os.getpid()}"
logger = logging.getLogger("maccre_core.swarm_worker")


class _FileTee:
    """Lightweight file tee: mirrors writes to orig stream AND a per-job log file.

    fileno() and isatty() stubs prevent crashes when Python's logging,
    subprocess, or Windows console APIs probe the redirected stream.
    """
    def __init__(self, filepath: str, orig_stream: Any) -> None:
        self.orig_stream = orig_stream
        self.log = open(filepath, "w", buffering=1, encoding="utf-8")  # noqa: SIM115

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


class UniversalSwarmWorker:
    def __init__(self) -> None:
        logger.info(f"[{AGENT_ID}] Initializing Universal Swarm Node...")
        self.project_name = os.environ.get("MACCRE_ACTIVE_PROJECT", "GLOBAL")
        self.router = UniversalRouter()
        self.topology: TopologyProvider | None = TopologyEngine()
        self.broker: MessageBroker = LocalMessageBroker()
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
            logger.warning(f"[{AGENT_ID}] WARNING: Missing ROM Cartridge -> {card_str} (using as inline instruction)")
            return str(card_name).strip()

        try:
            persona_data: dict[str, Any] = json.loads(card_path.read_text(encoding="utf-8"))
            return str(persona_data.get("instructions", ""))
        except Exception as e:
            logger.error(f"[{AGENT_ID}] ERROR reading persona {card_str}: {e}")
            return ""

    def _load_memory_pins(self) -> str:
        """Reads the project-scoped corkboard and mounts recent thoughts into the Agent's RAM."""
        mem_dir = get_datacenter_path("02_Dynamic_Context", "memory_pins")
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
            logger.warning(f"[{AGENT_ID}] WARNING: Could not read payload at {payload_path}: {e}")
            return "NO PAYLOAD DATA."

    async def _run_live_session(self, model_id: str, system_prompt: str, current_payload: str, job_id: str, current_node: str) -> str:
        """Stream 4a Alternative: High-speed REST streaming with manual barge-in."""
        # SOVEREIGNTY EXCEPTION: Live API WebSocket protocol has no REST equivalent
        from google import genai
        # SOVEREIGNTY EXCEPTION: Live API WebSocket protocol has no REST equivalent
        from google.genai import types
        from maccre_core.orchestration.windows_vault import get_native_credential
        from maccre_core.orchestration.queues import JsonFileQueue
        import asyncio

        api_key = str(get_native_credential("MACCRE_Sovereign") or "").strip()
        client = genai.Client(api_key=api_key)
        
        message_bus = JsonFileQueue("live_session_bus")
        gathered_text: list[str] = []
        
        # Maintain local history across the session
        history = [
            types.Content(role="user", parts=[types.Part.from_text(text=current_payload)])
        ]
        
        interrupt_event = asyncio.Event()
        override_text = []

        async def queue_listener() -> None:
            while True:
                try:
                    messages = message_bus.poll(["MACCRE.INTERRUPT", f"MACCRE.ROUTE.{current_node}"])
                    for topic_str, payload in messages:
                        if topic_str == "MACCRE.INTERRUPT" and payload.get("job_id") == job_id:
                            logger.info(f"\n[{current_node}] ⚡ LIVE INTERRUPT: Manager triggered barge-in.")
                            override_text.append(f"[User Barge-in]: {payload.get('override_text')}")
                            interrupt_event.set()
                            
                        elif topic_str == f"MACCRE.ROUTE.{current_node}" and payload.get("job_id") == job_id:
                            speaker = payload.get("speaker")
                            text = payload.get("text")
                            override_text.append(f"[{speaker}]: {text}")
                            interrupt_event.set()
                            
                    await asyncio.sleep(0.1)
                except asyncio.CancelledError:
                    break
                except Exception as e:
                    logger.error(f"[Queue Listener Error] {e}")
                    await asyncio.sleep(1)

        listener_task = asyncio.create_task(queue_listener())
        logger.info(f"[{current_node}] Live Session Bound to {model_id} (REST Streaming).")
        
        live_directive = f"\n\n[LIVE SESSION OVERRIDE]: You are in a multi-agent chat. Your specific identity and role is '{current_node}'. You must respond naturally as this entity. Do NOT mistake other agents' messages (e.g. [OtherAgent]: ...) as the user. Treat them as other AI agents working with you. The user is the one assigning tasks, while you collaborate with the swarm. IMPORTANT: Do NOT prefix your own response with your name (e.g. do not output '[{current_node}]:'). The system will automatically add your name prefix to the chat logs. CRITICAL: In this live conversational mode, tool execution is DISABLED. You must rely purely on your conversational knowledge. Do NOT attempt to output tool calls, JSON blocks, or state that you are executing a tool.\n\nFORMAT DIRECTIVE:\nBefore you respond, you MUST output a `<thought>` block containing your internal monologue, evaluating your persona, the topic, and what you should say. After your thought block, you MUST output a `<chat>` block containing the actual message you will send to the group. Example:\n<thought>\nI am the OSINT Analyst. I should provide objective data here.\n</thought>\n<chat>\nHere is the data on that topic...\n</chat>\nDo NOT output any text outside of these blocks."
        
        config = types.GenerateContentConfig(
            system_instruction=system_prompt + live_directive,
            temperature=1.0
        )
        
        is_first_turn = True
        
        try:
            while True:
                interrupt_event.clear()
                
                if override_text:
                    for text in override_text:
                        history.append(types.Content(role="user", parts=[types.Part.from_text(text=text)]))
                    override_text.clear()
                
                if is_first_turn and current_payload == "[SYSTEM] WAIT_FOR_USER":
                    logger.info(f"\n[{current_node}] Initialized in WAIT mode. Awaiting stimulus...")
                    is_first_turn = False
                else:
                    is_first_turn = False
                    try:
                        chat_payload = {
                            "job_id": job_id,
                            "agent_name": current_node,
                            "text": "",
                            "is_typing": True
                        }
                        message_bus.publish("MACCRE.CHAT", chat_payload)
                        
                        stream = await client.aio.models.generate_content_stream(
                            model=model_id,
                            contents=history,
                            config=config
                        )
                        
                        turn_text = []
                        async for chunk in stream:
                            if interrupt_event.is_set():
                                logger.info(f"\n[{current_node}] Stream interrupted by incoming signal.")
                                break
                                
                            if chunk.text:
                                turn_text.append(chunk.text)
                                gathered_text.append(chunk.text)
                                print(chunk.text, end="", flush=True)  # noqa: T201 — live streaming output
                                
                        if turn_text:
                            full_text = "".join(turn_text)
                            import re
                            import time
                            import json
                            from maccre_core.utils.path_resolver import get_datacenter_path
                            
                            thought_match = re.search(r"<thought>(.*?)</thought>", full_text, re.DOTALL)
                            chat_match = re.search(r"<chat>(.*?)</chat>", full_text, re.DOTALL)
                            
                            thought_text = thought_match.group(1).strip() if thought_match else ""
                            chat_text = chat_match.group(1).strip() if chat_match else full_text
                            
                            if thought_text:
                                thought_path = get_datacenter_path("03_Agent_Ledgers", f"{current_node}_thoughts.json")
                                thought_entry = {"time": time.time(), "job_id": job_id, "agent": current_node, "thought": thought_text}
                                with open(thought_path, "a", encoding="utf-8") as f:
                                    f.write(json.dumps(thought_entry) + "\n")

                                # ── Triple DB: Vectorize thought into session-scoped agent_thoughts.db ──
                                try:
                                    from maccre_core.tools.rag_tools import vectorize_thought  # noqa: PLC0415
                                    vectorize_thought(
                                        text=thought_text,
                                        project_name=self.project_name,
                                        session_id=job_id,
                                        agent_id=current_node,
                                    )
                                except Exception as _vec_err:  # noqa: BLE001
                                    logger.warning(f"[{current_node}] [VECTOR_WARN] thought vectorization failed (non-fatal): {_vec_err}")

                            chat_payload = {
                                "job_id": job_id,
                                "agent_name": current_node,
                                "text": chat_text,
                                "is_typing": False
                            }
                            message_bus.publish("MACCRE.CHAT", chat_payload)

                            # ── Triple DB: Vectorize chat response into session-scoped agent_ledgers.db ──
                            if chat_text:
                                try:
                                    from maccre_core.tools.rag_tools import vectorize_ledger  # noqa: PLC0415
                                    vectorize_ledger(
                                        text=chat_text,
                                        project_name=self.project_name,
                                        session_id=job_id,
                                        agent_id=current_node,
                                    )
                                except Exception as _vec_err:  # noqa: BLE001
                                    logger.warning(f"[{current_node}] [VECTOR_WARN] ledger vectorization failed (non-fatal): {_vec_err}")

                            history.append(types.Content(role="model", parts=[types.Part.from_text(text=full_text)]))
                            
                    except Exception as e:
                        logger.error(f"\n[{current_node}] Generation Error: {e}")
                    finally:
                        chat_payload = {
                            "job_id": job_id,
                            "agent_name": current_node,
                            "text": "",
                            "is_typing": False
                        }
                        message_bus.publish("MACCRE.CHAT", chat_payload)

                
                logger.info(f"\n[{current_node}] Turn finished. Awaiting next stimulus...")
                await interrupt_event.wait()

        finally:
            listener_task.cancel()
            
        return "".join(gathered_text)

    # ── Main Loop ─────────────────────────────────────────────────────────────

    def execute_cycle(
        self, 
        pause_event: Optional[Any] = None, 
        stop_event: Optional[Any] = None
    ) -> bool:
        """Executes a single node in the swarm topology.
        
        Args:
            pause_event: A threading.Event (or similar) that, if set, causes the worker to idle.
            stop_event: A threading.Event that, if set, returns False to exit the loop.
            
        Returns:
            False if stopped, True otherwise.
        """
        if stop_event is not None and stop_event.is_set():
            return False
            
        if pause_event is not None and not pause_event.is_set():
            time.sleep(1.0)
            return True

        task: Optional[Dict[str, Any]] = self.broker.fetch_and_lock_task(
            AGENT_ID, self.topology
        )
        if not task:
            if not self._is_sleeping:
                logger.info(f"[{AGENT_ID}] Queue empty or waiting on dependencies. Sleeping.")
                self._is_sleeping = True
            time.sleep(3)
            return True

        self._is_sleeping = False  # Wake up
        row_id: int = int(task["id"])
        job_id: str = str(task["job_id"])
        # Fallback to the worker's bound project_name if the queue doesn't store project_id
        project_id: str = str(task.get("project_id", self.project_name))
        
        # Explicitly scope the environment to this project for all downstream path resolution (e.g. telemetry_db)
        os.environ["MACCRE_ACTIVE_PROJECT"] = project_id
        
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

        orig_stdout = sys.stdout
        orig_stderr = sys.stderr
        dual_out = _FileTee(agent_log_path, orig_stdout)
        dual_err = _FileTee(agent_log_path, orig_stderr)
        sys.stdout = dual_out  # type: ignore[assignment]
        sys.stderr = dual_err  # type: ignore[assignment]

        try:
            logger.info(f"\n[{AGENT_ID}] Lock Acquired: job={job_id} | row={row_id} | Node: [{current_node}]")
            logger.info(f"[{AGENT_ID}] Ledger -> {ledger_path}")

            node_config = {}
            if self.topology is not None:
                try:
                    node_config = self.topology.get_node_config(current_node)
                except Exception:
                    pass

            # ── Deterministic Node Interception ──────────────────────────────────
            from maccre_core.orchestration.deterministic_nodes import (  # noqa: PLC0415
                is_deterministic_node,
                execute_deterministic_node,
            )
            if is_deterministic_node(current_node):
                det_result = execute_deterministic_node(current_node, task, node_config)
                logger.info(f"[{AGENT_ID}] DET Node: {det_result.log_message}")

                # Write a minimal ledger entry
                Path(ledger_path).write_text(
                    f"# {current_node}\n\n{det_result.log_message}\n",
                    encoding="utf-8",
                )

                if det_result.should_pause:
                    # Set task to 'paused' — worker will skip it until manual resume
                    self.broker.pause_task(row_id)
                    sys.stdout = orig_stdout
                    sys.stderr = orig_stderr
                    dual_out.close()
                    dual_err.close()
                    return True

                next_node = det_result.next_node or str(node_config.get("Next_Node", "END"))
                self.broker.route_task(
                    row_id=row_id,
                    job_id=job_id,
                    next_node_str=next_node,
                    new_payload_path=det_result.output_payload_path,
                    source_payload_path=source_payload_path,
                )
                sys.stdout = orig_stdout
                sys.stderr = orig_stderr
                dual_out.close()
                dual_err.close()
                return True
            
            prompt_name = node_config.get("prompt", "none")
            base_prompt = self._load_json_card(prompt_name)
            
            if prompt_name == "none" and not base_prompt.strip():
                pass # Will handle fallback
                
            # If no topology prompt is found, check the agent roster
            if base_prompt == "You are a MACCRE Agent. Analyze the payload and act according to your instructions.":
                try:
                    from maccre_core.agent_library import get_agent_store  # noqa: PLC0415
                    _ag_store = get_agent_store(os.environ.get("MACCRE_ACTIVE_PROJECT", "GLOBAL"))
                    for _ag_row in _ag_store.load_all():
                        _ag_name = str(_ag_row.get("agent_name") or _ag_row.get("AGENT_NAME", ""))
                        if _ag_name.strip() == current_node:
                            base_prompt = str(
                                _ag_row.get("system_prompt") or _ag_row.get("PERSONA", "")
                            ) or base_prompt
                            _ag_model = str(_ag_row.get("model") or _ag_row.get("MODEL", ""))
                            if _ag_model:
                                node_config["model"] = _ag_model
                            _ag_tools = str(_ag_row.get("tools_allowed") or _ag_row.get("TOOLS_ALLOWED", ""))
                            if _ag_tools:
                                node_config["tools_allowed"] = _ag_tools
                            break
                except Exception:
                    pass

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
            
            # Retrieve agent name for potential macro interception
            agent_name = str(node_config.get("agent_name", current_node))
            if agent_name.upper().startswith("MACRO:"):
                from maccre_core.orchestration.macro_factory import expand_macro
                expand_macro(
                    agent_name=agent_name,
                    current_node=current_node,
                    next_node=str(node_config["next_node_success"]),
                    job_id=job_id,
                    payload_path=payload_path,
                    source_payload_path=source_payload_path,
                    broker=self.broker,
                    row_id=row_id
                )
                logger.info(f"[{AGENT_ID}] Macro expansion complete. Yielding worker.")
                if self.topology is not None:
                    self.topology.flush_cache()
                return True

            # ── Dual-Payload Construction ─────────────────────────────────────
            # Each node receives:
            #   [SOURCE DOCUMENT] — the original user input (unchanged through all hops)
            #   [PREVIOUS NODE OUTPUT] — the ledger written by the prior agent
            # For the first node (INGEST), these are the same file; we skip the duplicate block.
            logger.info(f"[{AGENT_ID}] Reading payload: {payload_path}")
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
                        _pred_cfg = self.topology.get_node_config(_pred_node) if self.topology else {}
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
                            logger.info(f"[{AGENT_ID}] Injected artifact from {_pred_node}: {_pred_art_rel}")
                        else:
                            logger.warning(f"[{AGENT_ID}] WARNING: artifact not found for {_pred_node}: {_pred_art_abs}")
                    except Exception as _exc:  # noqa: BLE001
                        logger.warning(f"[{AGENT_ID}] WARNING: could not inject artifact for {_pred_node}: {_exc}")
                if _gathered_blocks:
                    payload_content = (
                        "\n\n".join(_gathered_blocks)
                        + "\n\n"
                        + payload_content
                    )
                    logger.info(f"[{AGENT_ID}] Fan-in: injected {len(_gathered_blocks)} gathered artifact(s) into payload.")

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
                logger.info(f"\n[{AGENT_ID}] 🔥 HOT-MIC INTERCEPT RECEIVED & INJECTED! 🔥")

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
                            logger.info(f"[{AGENT_ID}] Search grounding enabled for '{_agent_name}' via agent_extras.")
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
                # ── DIALOGUE MODE (pair or group) ──────────────────────────────
                # Shared helper: load one agent's config from agent_roster.csv
                # or a {name}.json agent card in 02_Dynamic_Context/.
                # Lookup priority: roster CSV → .json card → defaults.
                # Reads all known persona key variants: PERSONA, persona,
                # system_prompt, instructions (the key used by real agent cards).
                import csv as _csv  # noqa: PLC0415
                import json as _json  # noqa: PLC0415
                from maccre_core.orchestration.dialogue_runner import (  # noqa: PLC0415
                    DialogueRunner,
                    GroupDialogueRunner,
                    ParticipantConfig,
                    ManualInputRequired,
                )

                def _load_agent_cfg(
                    name: str,
                    default_model: str,
                    default_temp: float,
                ) -> tuple[str, str, float, str]:
                    """Return (system_prompt, model_id, temperature, tools_str) for *name*."""
                    if name.strip().upper() == "MANUAL":
                        return "You are the Human user. Provide your input.", "manual", 0.0, "none"

                    _sys = ""
                    _mdl = default_model
                    _tmp = default_temp
                    _tls = "none"
                    _extras = get_datacenter_path("02_Dynamic_Context", "agent_extras.json")
                    if _extras.exists():
                        try:
                            _exd = _json.loads(_extras.read_text(encoding="utf-8"))
                            if _exd.get(name, {}).get("search_grounding"):
                                _tls = "google_search"
                        except Exception:
                            pass
                    from maccre_core.utils.path_resolver import get_maccre_root
                    _roster = get_maccre_root() / "__DATACENTER" / "GLOBAL" / "agent_roster.csv"
                    if _roster.exists():
                        with _roster.open(encoding="utf-8") as _rf:
                            for _row in _csv.DictReader(_rf):
                                # CSV headers: Agent_Name, Model, Tools_Allowed, System_Prompt, Description
                                _agent_name_val = _row.get("Agent_Name", "") or _row.get("AGENT_NAME", "")
                                if _agent_name_val.strip() == name:
                                    _sys = str(
                                        _row.get("System_Prompt", "")
                                        or _row.get("PERSONA", "")
                                        or _row.get("instructions", "")
                                        or ""
                                    )
                                    _mdl = str(_row.get("Model", "") or _row.get("MODEL", "") or _mdl)
                                    _tmp = float(_row.get("Temperature", "") or _row.get("TEMPERATURE", "") or _tmp)
                                    _tls_val = str(_row.get("Tools_Allowed", "") or _row.get("TOOLS_ALLOWED", ""))
                                    if _tls_val:
                                        _tls = _tls_val
                                    break
                    if not _sys:
                        _card = get_datacenter_path("02_Dynamic_Context", f"{name}.json")
                        if _card.exists():
                            _pd = _json.loads(_card.read_text(encoding="utf-8"))
                            # Accept all known persona key variants
                            _sys = str(
                                _pd.get("instructions", "")
                                or _pd.get("persona", "")
                                or _pd.get("system_prompt", "")
                                or ""
                            )
                            _mdl = str(_pd.get("model", _mdl) or _mdl)
                            _tmp = float(_pd.get("temperature", _tmp) or _tmp)
                    return _sys, _mdl, _tmp, _tls

                # ── Detect pair vs group by presence of pipe separator ─────────
                _partner_names = [
                    n.strip() for n in _dialogue_partner.split("|") if n.strip()
                ]
                _host_temp = float(node_config.get("temperature", 1.0))
                _host_label = str(node_config.get("agent", current_node))

                # ── Shared transcript → artifact write block ──────────────────
                def _write_dialogue_artifact(text: str) -> None:
                    _ART_PFX = "04_Code_Artifacts/"
                    _rel = _raw_artifact_path
                    if not _rel:
                        # Auto-persist dialogue artifact if explicit path is omitted
                        _rel = f"{_ART_PFX}{job_id}/dialogue_transcript_{current_node}_{row_id}.md"
                        
                    if _rel.startswith(_ART_PFX) and job_id not in _rel:
                        _rel = f"{_ART_PFX}{job_id}/{_rel[len(_ART_PFX):]}"
                    _abs: Path = get_datacenter_path(*_rel.split("/"))
                    _abs.parent.mkdir(parents=True, exist_ok=True)
                    try:
                        _abs.write_text(text, encoding="utf-8")
                        logger.info(f"[{AGENT_ID}] Dialogue transcript written → {_abs}")
                    except Exception as _we:  # noqa: BLE001
                        logger.warning(f"[{AGENT_ID}] WARNING: Could not write dialogue artifact '{_rel}': {_we}")

                if len(_partner_names) == 1:
                    # ── PAIR DIALOGUE (original DialogueRunner) ───────────────
                    _partner = _partner_names[0]
                    _, _, _, _host_tls = _load_agent_cfg(_host_label, model_id, _host_temp)
                    _p_sys, _p_mdl, _p_tmp, _p_tls = _load_agent_cfg(_partner, model_id, _host_temp)
                    logger.info(
                        f"[{AGENT_ID}] DIALOGUE MODE: {current_node} ↔ {_partner} "
                        f"| rounds={_dialogue_rounds} | partner_model={_p_mdl}"
                    )
                    _pair_runner = DialogueRunner(
                        router=self.router,
                        agent_a_model=model_id,
                        agent_a_system=system_prompt,
                        agent_a_temperature=_host_temp,
                        agent_b_model=_p_mdl,
                        agent_b_system=_p_sys,
                        agent_b_temperature=_p_tmp,
                        num_rounds=_dialogue_rounds,
                        agent_a_label=_host_label,
                        agent_b_label=_partner,
                        agent_a_tools=_host_tls,
                        agent_b_tools=_p_tls,
                    )
                    try:
                        transcript, final_turn, total_cost = _pair_runner.run(current_payload, stop_event=stop_event)
                    except ManualInputRequired as e:
                        _sp = get_datacenter_path("02_Dynamic_Context", f"{job_id}_dialogue_state.json")
                        _sp.write_text(_json.dumps(e.checkpoint), encoding="utf-8")
                        logger.warning(f"[{AGENT_ID}] MANUAL INTERCEPT: {e.participant_label} requires input. Pausing task {row_id}.")
                        self.broker.pause_task(row_id)
                        sys.stdout = orig_stdout
                        sys.stderr = orig_stderr
                        dual_out.close()
                        dual_err.close()
                        return True
                    final_output_text = transcript
                    _write_dialogue_artifact(transcript)

                else:
                    # ── GROUP DIALOGUE (GroupDialogueRunner) ──────────────────
                    # Each name in _partner_names becomes a participant session.
                    # The topology node (this agent) is the host.
                    _participants: list[ParticipantConfig] = []
                    _, _, _, _host_tls = _load_agent_cfg(_host_label, model_id, _host_temp)
                    for _pname in _partner_names:
                        _p_sys, _p_mdl, _p_tmp, _p_tls = _load_agent_cfg(_pname, model_id, _host_temp)
                        _participants.append(
                            ParticipantConfig(
                                label=_pname,
                                model=_p_mdl,
                                system_prompt=_p_sys,
                                temperature=_p_tmp,
                                tools_str=_p_tls,
                            )
                        )
                    p_label_str = ", ".join(_partner_names)
                    logger.info(
                        f"[{AGENT_ID}] GROUP DIALOGUE MODE: host={current_node} "
                        f"| participants=[{p_label_str}] | rounds={_dialogue_rounds}"
                    )
                    _grp_runner = GroupDialogueRunner(
                        router=self.router,
                        host_model=model_id,
                        host_system=system_prompt,
                        host_temperature=_host_temp,
                        host_label=_host_label,
                        participants=_participants,
                        num_rounds=_dialogue_rounds,
                        host_tools=_host_tls,
                    )
                    try:
                        transcript, final_turn, total_cost = _grp_runner.run(current_payload, stop_event=stop_event)
                    except ManualInputRequired as e:
                        _sp = get_datacenter_path("02_Dynamic_Context", f"{job_id}_dialogue_state.json")
                        _sp.write_text(_json.dumps(e.checkpoint), encoding="utf-8")
                        logger.warning(f"[{AGENT_ID}] MANUAL INTERCEPT: {e.participant_label} requires input. Pausing task {row_id}.")
                        self.broker.pause_task(row_id)
                        sys.stdout = orig_stdout
                        sys.stderr = orig_stderr
                        dual_out.close()
                        dual_err.close()
                        return True
                    final_output_text = transcript
                    _write_dialogue_artifact(transcript)

            elif str(node_config.get("live_profile", "")).lower() in ("true", "1", "yes") or os.environ.get("MACCRE_LIVE_OVERRIDE") == "1":

                import asyncio
                logger.info(f"[{AGENT_ID}] Executing via STREAM 4 LIVE SESSION.")
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
                        temperature=float(node_config.get("temperature", 0.7)),
                        expect_multiple_reads=True,
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
                            logger.info(f"[{AGENT_ID}] Tool loop complete: {turn_idx} tool turn(s) → clean output.")
                        break

                    # Capture raw tool call text for forensic audit sidecar.
                    tool_audit_lines.append(f"## TOOL TURN {turn_idx + 1}/{max_tool_turns}\n{output_text}")

                    if is_last:
                        # Graceful close: agent hit the recursion limit mid-sequence.
                        # Give it one final tool-free generation to flush accumulated work.
                        # This applies universally — any agent in any topology recovers here
                        # rather than producing a dangling tool-call as its ledger output.
                        logger.info(f"[{AGENT_ID}] Max tool turns ({max_tool_turns}) reached — graceful close turn.")
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
                            expect_multiple_reads=True,
                        )
                        total_cost += close_cost
                        final_output_text = close_text
                        tool_audit_lines.append(f"## GRACEFUL CLOSE TURN\n{close_text}")
                        logger.info(f"[{AGENT_ID}] Graceful close: {len(close_text)} chars flushed.")
                        break

                    # ── Terminal tool detection ───────────────────────────────────
                    # write_file / execute_render_pipeline are "done" signals: their
                    # side-effect (file written / render queued) already happened.
                    # Feeding "continue" back causes the model to call them again in
                    # a loop. Detect and terminate immediately.
                    _TERMINAL_TOOLS = ("write_file", "execute_render_pipeline", "render_podcast_audio")
                    _fired_terminal = any(
                        f"TOOL CALL REQUESTED: {_t}" in output_text
                        or f"[TOOL_CALL]: {_t}" in output_text
                        for _t in _TERMINAL_TOOLS
                    )
                    if _fired_terminal:
                        t_name, t_args = self.tool_executor._parse(output_text)
                        if t_args and "data" in t_args:
                            final_output_text = str(t_args["data"])
                        elif t_args and "content" in t_args:
                            final_output_text = str(t_args["content"])
                        else:
                            final_output_text = output_text
                            
                        logger.info(f"[{AGENT_ID}] Terminal tool fired — extracting prose payload and closing loop.")
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

            logger.info(f"[{AGENT_ID}] Generation complete. Billed Cost: ${task_cost:.6f}")

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
                logger.info(f"[{AGENT_ID}] Tool audit sidecar: {audit_path}")

            # ── LIVE STREAMING ACOUSTICS ──────────────────────────────────────
            # Trigger real-time conversational streaming for non-director nodes
            if "director" not in AGENT_ID.lower():
                # live_stream_audio(ledger_content_out, AGENT_ID, job_id, current_node)
                pass

            self.memory_engine.extract_and_store(ledger_content_out, current_node, job_id)

            next_node: str = str(node_config.get("next_node_success", node_config.get("Next_Node", "END")))

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
            _ROUTE_TO_PATTERN = _re.compile(r"ROUTE_TO:([A-Za-z][A-Za-z0-9_]*)", _re.IGNORECASE)
            _route_match = _ROUTE_TO_PATTERN.search(raw_model_output or "")
            if _route_match:
                _candidate = _route_match.group(1).strip()

                # ACCEPTED means "all gates passed — proceed to static next_node"
                if _candidate.upper() == "ACCEPTED":
                    logger.info(
                        f"[{AGENT_ID}] CONDITIONAL ROUTE: ROUTE_TO:ACCEPTED — "
                        f"proceeding to static next_node '{next_node}'"
                    )
                elif _candidate.upper() not in {"STOP", "DONE", "TERMINATE", "FAILED"}:
                    # Check main topology first, then ephemeral macros
                    _topology_map = self.topology.get_topology() if self.topology else {}
                    try:
                        from maccre_core.macronode_registry import get_macronode_store  # noqa: PLC0415
                        _ephemeral_map = get_macronode_store().load_ephemeral_graph()
                    except Exception:  # noqa: BLE001
                        _ephemeral_map = {}

                    if _candidate in _topology_map or _candidate in _ephemeral_map:
                        logger.info(
                            f"[{AGENT_ID}] CONDITIONAL ROUTE: '{next_node}' overridden by "
                            f"ROUTE_TO:{_candidate} (model-directed)"
                        )
                        next_node = _candidate
                    else:
                        logger.info(
                            f"[{AGENT_ID}] CONDITIONAL ROUTE: ROUTE_TO:{_candidate} ignored "
                            f"(target not in topology or ephemeral macros)"
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
                    logger.info(f"[{AGENT_ID}] Routing via artifact: {routing_payload_path}")
                else:
                    routing_payload_path = ledger_path
                    logger.info(
                        f"[{AGENT_ID}] WARNING: artifact_path '{_artifact_rel}' not found — "
                        f"falling back to ledger."
                    )
            else:
                routing_payload_path = ledger_path

            # ── Unified Session Ledger Live-Update & Payload Mode Routing ─────────
            try:
                from maccre_core.orchestration.flow_engine import generate_unified_ledger
                _ul_path = generate_unified_ledger(job_id)
                logger.info(f"[{AGENT_ID}] Live-updated unified ledger: {_ul_path}")
                
                payload_mode = "Unified Ledger"
                if self.topology:
                    try:
                        tgt_cfg = self.topology.get_node_config(next_node)
                        payload_mode = str(tgt_cfg.get("payload_mode", "Unified Ledger"))
                    except Exception:
                        pass
                
                if payload_mode == "Unified Ledger" and _ul_path:
                    routing_payload_path = _ul_path
                    logger.info(f"[{AGENT_ID}] Routing via Unified Ledger: {routing_payload_path}")
            except Exception as e:
                logger.warning(f"[{AGENT_ID}] Failed to live-update or route unified session ledger: {e}")

            self.broker.route_task(
                row_id,
                job_id,
                next_node,
                new_payload_path=routing_payload_path,
                actual_cost=task_cost,
                source_payload_path=source_payload_path,
                max_recursion=max_rec,
            )
            
            # Update the session with the live ledger
            self.broker.update_session_ledger(job_id, routing_payload_path)

            # ── Auto-promote topology to library on terminal STOP success ─────
            if next_node.strip().upper() in ("STOP", "DONE", "TERMINATE"):
                try:
                    from maccre_core.tools.admin_tools import promote_topology_to_library  # noqa: PLC0415
                    promo_name = f"job_{job_id}_node_{current_node}"
                    promo_result = promote_topology_to_library(
                        topology_name=promo_name,
                        job_id=job_id,
                    )
                    logger.info(f"[{AGENT_ID}] Topology Promotion: {promo_result}")
                except Exception as promo_err:
                    logger.warning(f"[{AGENT_ID}] WARNING: Topology promotion failed (non-fatal): {promo_err}")

        except Exception as e:
            import traceback
            logger.critical(f"[{AGENT_ID}] CRITICAL FAILURE: {e}.")
            logger.info(traceback.format_exc())
            fail_target = "FAILED"
            try:
                fail_target = str(node_config.get("next_node_failure", "FAILED")).strip()  # type: ignore[possibly-unbound]
            except Exception:
                pass
            logger.info(f"[{AGENT_ID}] Routing task to [{fail_target}]")
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
        
        return True


if __name__ == "__main__":
    worker = UniversalSwarmWorker()
    logger.info(f"=== UNIVERSAL SWARM NODE {AGENT_ID} ONLINE ===")
    while True:
        if not worker.execute_cycle():
            break
        time.sleep(0)  # yield to event loop
