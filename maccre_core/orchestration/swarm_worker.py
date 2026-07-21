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
            logger.debug(f"[{AGENT_ID}] Missing ROM Cartridge -> {card_str} (using as inline instruction)")
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

    def _run_interactive_diamond_loop(self, model_id: str, system_prompt: str, current_payload: str, job_id: str, current_node: str, ai_options: dict | None = None, temperature: float = 1.0, tools_str: str = "none") -> str:
        """Synchronous Diamond Loop implementation for Agent Studio Chat"""
        from maccre_core.orchestration.queues import JsonFileQueue
        import threading
        import time
        import asyncio
        import json
        
        message_bus = JsonFileQueue("live_session_bus")
        override_text = []
        
        # Setup session path for thoughts
        clean_id = job_id.replace("studio_session_", "", 1) if job_id.startswith("studio_session_") else job_id
        ledg_dir = get_datacenter_path("03_Agent_Ledgers", f"ChatStudioSessions/{clean_id}-Chat")
        ledg_dir.mkdir(parents=True, exist_ok=True)
        thoughts_log_path = ledg_dir / f"{current_node}_agent.log"
        
        def write_thought(msg: str):
            with open(thoughts_log_path, "a", encoding="utf-8") as tf:
                tf.write(f"\n{msg}\n")
        
        def listener_thread():
            while not self._shutdown_flag:
                try:
                    messages = message_bus.poll([f"MACCRE.ROUTE.{current_node}"])
                    for topic_str, payload in messages:
                        if payload.get("job_id") == job_id:
                            speaker = payload.get("speaker", "User")
                            text = payload.get("text", "")
                            override_text.append(f"**{speaker}**: {text}\n\n---\n\n")
                            
                    time.sleep(0.1)
                except Exception as e:
                    logger.error(f"[Queue Listener Error] {e}")
                    time.sleep(1)
                    
        self._shutdown_flag = False
        t = threading.Thread(target=listener_thread, daemon=True)
        t.start()
        
        logger.info(f"[{current_node}] Studio Session Bound to {model_id} (Diamond Loop).")
        
        # Load local .dict profile if it exists (Agent Studio overrides)
        custom_dict_path = os.environ.get("MACCRE_CUSTOM_DICT", "")
        if custom_dict_path and os.path.exists(custom_dict_path):
            try:
                with open(custom_dict_path, "r", encoding="utf-8") as f:
                    chat_profile = json.load(f)
                    agent_config = chat_profile.get(current_node, {})
                    if agent_config:
                        system_prompt = agent_config.get("system_prompt", system_prompt)
                        model_id = agent_config.get("model", model_id)
                        temperature = float(agent_config.get("temperature", temperature))
                        tools_str = agent_config.get("tools_allowed", tools_str)
                        if ai_options is not None:
                            ai_options.update(agent_config.get("ai_studio_options", {}))
                        else:
                            ai_options = agent_config.get("ai_studio_options", {})
                            
                        # Inject search tools based on UI toggles
                        _t_list = [t.strip() for t in tools_str.replace("|", ",").split(",") if t.strip() and t.strip() != "none"]
                        if ai_options.get("grounding_google_search"):
                            if "google_search" not in _t_list: _t_list.append("google_search")
                        elif "google_search" in _t_list:
                            _t_list.remove("google_search")
                            
                        if ai_options.get("grounding_brave_search"):
                            if "search_web" not in _t_list: _t_list.append("search_web")
                        elif "search_web" in _t_list:
                            _t_list.remove("search_web")
                            
                        tools_str = ",".join(_t_list) if _t_list else "none"
            except Exception as e:
                logger.error(f"Failed to load chat .dict: {e}")
                
        is_first_turn = True
        total_session_cost = 0.0
        agent_turn = False
        
        # Load from unified ledger if it exists to maintain memory across restarts
        art_dir = get_datacenter_path("04_Code_Artifacts", f"ChatStudioSessions/{clean_id}-Chat")
        unified_path = art_dir / "unified_chat_ledger.md"
        if unified_path.exists():
            session_history = unified_path.read_text(encoding="utf-8")
        else:
            session_history = f"[SYSTEM_PAYLOAD]\n{current_payload}\n[/SYSTEM_PAYLOAD]\n\n"
        
        try:
            while True:
                if override_text:
                    for text in override_text:
                        session_history += f"\n{text}\n"
                    override_text.clear()
                    agent_turn = True
                    
                if is_first_turn and "WAIT_FOR_USER" in current_payload:
                    logger.info(f"\n[{current_node}] Initialized in WAIT mode. Awaiting stimulus...")
                    is_first_turn = False
                    time.sleep(0.5)
                    continue
                    
                if is_first_turn:
                    agent_turn = True
                    
                is_first_turn = False
                
                if agent_turn:
                    
                    # RUN DIAMOND LOOP!
                    logger.info(f"[{current_node}] Executing Diamond Loop cycle...")
                    
                    final_response = ""
                    current_loop_cost = 0.0
                    
                    max_tool_turns = 10
                    loop_payload = session_history
                    
                    for turn_idx in range(max_tool_turns + 1):
                        prompt = (
                            f"{system_prompt}\n\n"
                            f"CURRENT SESSION HISTORY:\n{loop_payload}\n\n"
                        )
                        
                        try:
                            # Run synchronous generation
                            # Since this is an async worker originally, we wrap synchronous router 
                            # Or we just call the router since router IS sync!
                            raw_response, loop_cost, api_thought = self.router.generate(
                                model_name=model_id,
                                payload=loop_payload,
                                system_prompt=system_prompt,
                                tools_str=tools_str,
                                temperature=temperature,
                                expect_multiple_reads=True,
                                thinking_level=ai_options.get('thinking_level', 'none'),
                                safety_level=ai_options.get('safety_level', 'BLOCK_NONE')
                            )
                            if api_thought:
                                write_thought(f"<api_thought>\n{api_thought}\n</api_thought>")
                                
                            # Extract Prompt-Based Reasoning thoughts
                            import re
                            pbr_thoughts = re.findall(r'<thought>(.*?)</thought>', raw_response, re.DOTALL)
                            for t in pbr_thoughts:
                                write_thought(f"<thought>\n{t.strip()}\n</thought>")
                                
                            current_loop_cost += loop_cost
                            
                            # Parse tools
                            did_fire, new_payload = self.tool_executor.run(
                                response_text=raw_response,
                                current_prompt=loop_payload,
                                project_id=self.project_name,
                                session_id=job_id,
                                agent_id=current_node
                            )
                            if did_fire:
                                write_thought(f"<tool_call>\n{raw_response}\n</tool_call>")
                                loop_payload = new_payload
                                # Keep iterating
                            else:
                                # Capture native search grounding as a tool call
                                if "### Search Grounding Sources:" in raw_response:
                                    _grounding_start = raw_response.index("### Search Grounding Sources:")
                                    _grounding_block = raw_response[_grounding_start:]
                                    write_thought(f"<tool_call>\n[GOOGLE_SEARCH_GROUNDING]\n{_grounding_block}\n</tool_call>")
                                final_response = raw_response
                                break
                                
                        except Exception as e:
                            logger.error(f"[Diamond Loop Error] {e}")
                            final_response = f"Error during loop execution: {e}"
                            break
                            
                    if not final_response:
                        final_response = "[SYSTEM] Error: Agent exceeded maximum tool iterations or failed to produce an answer."
                        
                    # Finished Loop! Append to history
                    total_session_cost += current_loop_cost
                    session_history += f"**{current_node}**: {final_response}\n\n---\n\n"
                    
                    # Publish final message to TUI
                    chat_payload = {
                        "job_id": job_id,
                        "agent_name": current_node,
                        "content": final_response,
                        "cost": current_loop_cost
                    }
                    message_bus.publish("MACCRE.CHAT", chat_payload)
                    
                    # Write unified ledger directly
                    art_dir = get_datacenter_path("04_Code_Artifacts", f"ChatStudioSessions/{clean_id}-Chat")
                    art_dir.mkdir(parents=True, exist_ok=True)
                    unified_path = art_dir / "unified_chat_ledger.md"
                    with open(unified_path, "w", encoding="utf-8") as f:
                        f.write(session_history)
                    logger.info(f"[{current_node}] Live-updated unified ledger: {unified_path}")
                        
                    agent_turn = False
                    
                time.sleep(0.5)
                
        except KeyboardInterrupt:
            self._shutdown_flag = True
        finally:
            self._shutdown_flag = True
            
        return session_history


    def _apply_triple_index_search(self, current_payload: str, ai_opts: dict, model_id: str, agent_id: str, tools_str: str, system_prompt: str = "") -> tuple[str, float, str]:
        total_cost = 0.0
        try:
            if ai_opts:
                is_exc = ai_opts.get("exclusionary_search", False)
                is_funnel = ai_opts.get("funnel_search", False)
                use_brave = ai_opts.get("grounding_brave_search", False)
                use_local = ai_opts.get("grounding_local_memory", False)
                
                if is_exc or is_funnel or use_brave or use_local:
                    from maccre_core.tools.search_tools import run_search
                    from maccre_core.tools.hybrid_search import _query_local_sovereign
                    from maccre_core.orchestration.universal_vault import get_provider_credential
                    import json
                    import os
                    
                    if "SEARCH_API_KEY" not in os.environ:
                        brave_key = get_provider_credential("BRAVE_SEARCH_API_KEY")
                        if brave_key:
                            os.environ["SEARCH_API_KEY"] = brave_key
                            
                    if is_exc:
                        # EXCLUSIONARY SEARCH PIPELINE (Adversarial)
                        logger.info(f"[{agent_id}] Executing Exclusionary Search pipeline...")
                        import datetime
                        today = datetime.datetime.now().strftime("%Y-%m-%d")
                        prompt = (
                            "Research the following topic using Google Search and extract the 3 most prominent "
                            "domains and 3 most common keywords representing the mainstream consensus. "
                            f"The current date is {today}. "
                            "Return ONLY valid JSON in this exact format: {\"domains\": [\"domain1.com\"], \"keywords\": [\"word1\"]}"
                        )
                        out, cst, _ = self.router.generate(
                            model_name=model_id,
                            payload=current_payload,
                            system_prompt=prompt,
                            tools_str="google_search",
                            temperature=0.1
                        )
                        total_cost += cst
                        
                        try:
                            start = out.find('{')
                            end = out.rfind('}') + 1
                            if start != -1 and end != 0:
                                parsed = json.loads(out[start:end])
                                domains = parsed.get("domains", [])
                                keywords = parsed.get("keywords", [])
                                
                                # Extract a base query
                                q_out, q_cst, _ = self.router.generate(
                                    model_name=model_id, 
                                    payload=current_payload, 
                                    system_prompt=f"{system_prompt}\n\n[TASK] Extract a concise 1-sentence search query for this topic. Return ONLY the query string, no quotes.", 
                                    tools_str="none", 
                                    temperature=0.1
                                )
                                total_cost += q_cst
                                base_query = q_out.strip().replace('"', '')
                                
                                adv_query = base_query
                                for d in domains:
                                    adv_query += f" -site:{d}"
                                for k in keywords:
                                    adv_query += f" -{k}"
                                
                                logger.info(f"[{agent_id}] Exclusionary query generated: {adv_query}")
                                brave_res = run_search(adv_query, count=10)
                                if brave_res.get("results"):
                                    current_payload = f"[EXCLUSIONARY ORTHOGONAL CONTEXT]\n{json.dumps(brave_res, indent=2)}\n\n" + current_payload
                                    # DISABLE NATIVE GOOGLE GROUNDING
                                    if "google_search" in tools_str:
                                        tools_str = tools_str.replace("google_search", "").replace("||", "|").strip("|")
                                        if not tools_str:
                                            tools_str = "none"
                                        logger.info(f"[{agent_id}] Disabled Native Google Grounding to prevent re-contamination.")
                                else:
                                    logger.warning(f"[{agent_id}] Exclusionary search yielded 0 results. Falling back to Additive.")
                        except Exception as e:
                            logger.error(f"[{agent_id}] Exclusionary Search parsing failed: {e}")
                    
                    elif is_funnel:
                        # FUNNEL SEARCH PIPELINE (Iterative Batching)
                        logger.info(f"[{agent_id}] Executing Funnel Search pipeline...")
                        import datetime
                        today = datetime.datetime.now().strftime("%Y-%m-%d")
                        prompt = (
                            f"{system_prompt}\n\n[TASK] Research this topic and extract 5 highly specific, niche entities (e.g., obscure hardware, specific people, subsidiaries) related to it. "
                            f"The current date is {today}. "
                            "Return ONLY valid JSON in this format: {\"entities\": [\"Entity 1\"]}"
                        )
                        out, cst, _ = self.router.generate(
                            model_name=model_id,
                            payload=current_payload,
                            system_prompt=prompt,
                            tools_str="google_search",
                            temperature=0.1
                        )
                        total_cost += cst
                        try:
                            start = out.find('{')
                            end = out.rfind('}') + 1
                            if start != -1 and end != 0:
                                parsed = json.loads(out[start:end])
                                entities = parsed.get("entities", [])
                                funnel_results = []
                                for ent in entities:
                                    res = run_search(f'"{ent}"', count=3)
                                    funnel_results.append({ent: res.get("results", [])})
                                
                                current_payload = f"[FUNNEL BATCH CONTEXT]\n{json.dumps(funnel_results, indent=2)}\n\n" + current_payload
                        except Exception as e:
                            logger.error(f"[{agent_id}] Funnel Search parsing failed: {e}")
                            
                    else:
                        # ADDITIVE MERGING (Parallel pre-injection)
                        if use_brave or use_local:
                            logger.info(f"[{agent_id}] Executing Additive Pre-injection...")
                            import datetime
                            today = datetime.datetime.now().strftime("%Y-%m-%d")
                            q_out, q_cst, _ = self.router.generate(
                                model_name=model_id, 
                                payload=current_payload, 
                                system_prompt=f"{system_prompt}\n\n[TASK] Extract a concise 1-sentence search query to fulfill the user's request based on your persona. The current date is {today}. Return ONLY the query string.", 
                                tools_str="none", 
                                temperature=0.1
                            )
                            total_cost += q_cst
                            base_query = q_out.strip().replace('"', '')
                            
                            if use_brave:
                                try:
                                    brave_res = run_search(base_query, count=5)
                                    current_payload = f"[BRAVE SEARCH CONTEXT]\n{json.dumps(brave_res, indent=2)}\n\n" + current_payload
                                except Exception as e:
                                    logger.error(f"[{agent_id}] Brave injection failed: {e}")
                            if use_local:
                                try:
                                    loc_res = _query_local_sovereign(base_query)
                                    current_payload = f"[LOCAL MEMORY CONTEXT]\n{loc_res}\n\n" + current_payload
                                except Exception as e:
                                    logger.error(f"[{agent_id}] Local Memory injection failed: {e}")
        except Exception as e:
            logger.error(f"[{agent_id}] Triple Index Search pre-injection fault: {e}")
            
        return current_payload, total_cost, tools_str

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

        # Build flow_vector: append current node to existing vector (Phase 4.75.7 A5)
        _existing_vector: str = str(task.get("flow_vector", "") or "")
        flow_vector: str = f"{_existing_vector}:{current_node}" if _existing_vector else current_node

        # ── Project-Scoped Job Directory ─────────────────────────────────────
        custom_ledger = os.environ.get("MACCRE_CUSTOM_LEDGER", "")
        if custom_ledger:
            ledger_path = custom_ledger
            agent_log_path = custom_ledger.replace(".md", "_agent.log")
            job_dir = Path(ledger_path).parent
            job_dir.mkdir(parents=True, exist_ok=True)
        else:
            if job_id.startswith("studio_session_"):
                clean_id = job_id.replace("studio_session_", "", 1)
                job_dir = get_datacenter_path("03_Agent_Ledgers", f"ChatStudioSessions/{clean_id}-Chat")
            else:
                job_dir = get_datacenter_path("03_Agent_Ledgers", job_id)
            job_dir.mkdir(parents=True, exist_ok=True)
            ledger_path = str(job_dir / f"{current_node}_{row_id}.md")
            agent_log_path = str(job_dir / f"{current_node}_{row_id}_agent.log")

        # ── Dual-Stream File Logger ───────────────────────────────────────────
        import sys
        orig_stdout = sys.stdout
        orig_stderr = sys.stderr
        
        is_studio_session = job_id.startswith("studio_session_")
        dual_out = None
        dual_err = None
        
        if not is_studio_session:
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

                # ── Multi-target fan-out (SCATTER / CONDITIONAL_ROUTE) ────────
                if det_result.next_nodes:
                    current_flow_line = str(task.get("flow_line_id", ""))
                    config = node_config or {}
                    tether_id = str(config.get("tether_id", "scatter"))
                    for idx, target_node in enumerate(det_result.next_nodes):
                        flow_line_id = (
                            f"{current_flow_line}.{tether_id}.{idx}"
                            if current_flow_line
                            else f"{tether_id}.{idx}"
                        )
                        self.broker.route_task(
                            row_id=row_id,
                            job_id=job_id,
                            next_node_str=target_node,
                            new_payload_path=det_result.output_payload_path,
                            source_payload_path=source_payload_path,
                            flow_line_id=flow_line_id,
                            flow_vector=flow_vector,
                        )
                    logger.info(
                        "[%s] DET fan-out: %d targets on tether=%s",
                        AGENT_ID, len(det_result.next_nodes), tether_id,
                    )
                elif det_result.next_node:
                    # Single target override (existing behavior)
                    self.broker.route_task(
                        row_id=row_id,
                        job_id=job_id,
                        next_node_str=det_result.next_node,
                        new_payload_path=det_result.output_payload_path,
                        source_payload_path=source_payload_path,
                        flow_line_id=str(task.get("flow_line_id", "")),
                        flow_vector=flow_vector,
                    )
                else:
                    # Default topology routing
                    next_node = str(node_config.get("Next_Node", "END"))
                    self.broker.route_task(
                        row_id=row_id,
                        job_id=job_id,
                        next_node_str=next_node,
                        new_payload_path=det_result.output_payload_path,
                        source_payload_path=source_payload_path,
                        flow_line_id=str(task.get("flow_line_id", "")),
                        flow_vector=flow_vector,
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
                            node_config["temperature"] = float(_ag_row.get("temperature", 1.0))
                            break
                except Exception:
                    pass

            # ── Session-Scoped Artifact Directory ──────────────────────────────
            # ARCHITECTURE NOTE: Routing Paths (Explicit vs Implicit)
            # Currently, MACCREv2 uses Explicit Routing via Sentinels ({SESSION_ID}).
            # This explicitly constructs absolute paths in the instructions, allowing
            # the agent to write files outside of its immediate isolated working
            # directory by passing the resolved path into tools like write_file.
            # 
            # Alternative: Implicit Routing.
            # In an Implicit model, the LLM is only given relative paths (e.g. `04_Code_Artifacts/out.py`).
            # The tool interceptor (`maccre_router.py`) would dynamically map these
            # relative paths to the correct active unified session ledger directory.
            # This would improve security and portability but requires intercepting
            # all I/O bound tools and maintaining active session state inside the router.
            # 
            # We maintain Explicit Routing for now to guarantee tool execution
            # transparency and avoid masking path errors behind router logic.
            
            # Create 04_Code_Artifacts/{job_id}/ once per node execution.
            # {SESSION_ID} tokens in Instruction_Override and Artifact_Path are
            # substituted with the actual job_id at runtime. This guarantees
            # every swarm run writes to its own isolated subdirectory so
            # re-running the same topology never overwrites prior artifacts.
            if job_id.startswith("studio_session_"):
                _clean_id = job_id.replace("studio_session_", "", 1)
                _artifacts_dir = get_datacenter_path("04_Code_Artifacts", f"ChatStudioSessions/{_clean_id}-Chat")
            else:
                _artifacts_dir = get_datacenter_path(f"04_Code_Artifacts/{job_id}")
            _artifacts_dir.mkdir(parents=True, exist_ok=True)

            # Substitute {SESSION_ID} in the instruction text
            base_prompt = base_prompt.replace("{SESSION_ID}", job_id)

            # ── Global Datacenter & Tool Knowledge Injection ──────────────────
            _GLOBAL_ARCHITECTURE = """
[SYSTEM REGISTRY: MACCREv2 DATACENTER ARCHITECTURE]
You are operating within the MACCREv2 5-Tier Datacenter architecture.
All file paths must strictly resolve to these five silos:
  - 01_Raw_Source: External, read-only documents and inputs.
  - 02_Dynamic_Context: Agent registries, project configurations, and metadata.
  - 03_Agent_Ledgers: Your thoughts, debug logs, and intermediate text generation.
  - 04_Code_Artifacts: Final source code, markdown outputs, and structured JSON results.
  - 05_Rendered_Media: Audio/video generated assets.
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
            # ── Targeted Filter Payload Generation ─────────────────────────────
            _payload_mode = str(node_config.get("payload_mode", "Unified Ledger"))
            if _payload_mode == "Targeted Filter":
                try:
                    from maccre_core.orchestration.flow_engine import generate_targeted_ledger  # noqa: PLC0415
                    _judge_node = str(node_config.get("next_node_success", node_config.get("Next_Node", ""))).split(",")[0].strip()
                    _cb_path = generate_targeted_ledger(job_id, current_node, _judge_node)
                    if _cb_path:
                        payload_path = _cb_path
                        logger.info(f"[{AGENT_ID}] Loaded Targeted Filter Ledger: {payload_path}")
                except Exception as e:  # noqa: BLE001
                    logger.warning(f"[{AGENT_ID}] Failed to generate Targeted Filter Ledger: {e}")

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
            #
            # Tether-scoped fan-in (Phase 5): when the current node carries a
            # tether_id, we query the broker for all completed tasks sharing that
            # tether scope and inject their payloads — instead of iterating the
            # static Wait_For list. This ensures parallel flow lines don't
            # contaminate each other's gathered artifacts.
            _tether_id: str = str(node_config.get("tether_id", "") or "")
            _wait_for_str: str = str(node_config.get("wait_for", "") or "")
            _wait_for_nodes: list[str] = [
                n.strip() for n in _wait_for_str.replace("|", ",").split(",") if n.strip() and n.strip().lower() != "none"
            ]

            if _tether_id and _wait_for_nodes and isinstance(self.broker, LocalMessageBroker):
                # ── Tether-scoped fan-in: collect only from matching tether ──
                _gathered_blocks: list[str] = []
                _completed_peers = self.broker.get_completed_by_tether(
                    job_id=job_id,
                    tether_id=_tether_id,
                )
                _peer_nodes: set[str] = {str(r.get("current_node", "")) for r in _completed_peers}
                # Only inject predecessors that are both in our Wait_For list AND completed in our tether
                for _pred_node in _wait_for_nodes:
                    if _pred_node not in _peer_nodes:
                        continue
                    try:
                        _pred_cfg = self.topology.get_node_config(_pred_node) if self.topology else {}
                        _pred_art_rel: str = str(_pred_cfg.get("artifact_path", "") or "")
                        _art_content = None
                        _resolved_path_str = ""

                        if _pred_art_rel:
                            _pred_art_rel = _pred_art_rel.replace("{SESSION_ID}", job_id)
                            _ART_PFX = "04_Code_Artifacts/"
                            if _pred_art_rel.startswith(_ART_PFX) and job_id not in _pred_art_rel:
                                _pred_art_rel = f"{_ART_PFX}{job_id}/{_pred_art_rel[len(_ART_PFX):]}"
                            _pred_art_abs = get_datacenter_path(*_pred_art_rel.split("/"))
                            if _pred_art_abs.exists():
                                _art_content = _pred_art_abs.read_text(encoding="utf-8")
                                _resolved_path_str = _pred_art_rel

                        if _art_content is None:
                            # Fallback: use the payload_path from the completed tether peer row
                            _peer_row = next(
                                (r for r in _completed_peers if r.get("current_node") == _pred_node), None
                            )
                            if _peer_row and _peer_row.get("payload_path"):
                                _peer_payload = str(_peer_row["payload_path"])
                                if Path(_peer_payload).exists():
                                    _art_content = Path(_peer_payload).read_text(encoding="utf-8")
                                    _resolved_path_str = _peer_payload

                        if _art_content is None:
                            import glob  # noqa: PLC0415
                            _ledger_dir = get_datacenter_path("03_Agent_Ledgers", job_id)
                            _ledger_pattern = str(_ledger_dir / f"{_pred_node}_*.md")
                            _matches = glob.glob(_ledger_pattern)
                            if _matches:
                                _art_content = Path(_matches[0]).read_text(encoding="utf-8")
                                _resolved_path_str = f"03_Agent_Ledgers/{job_id}/{Path(_matches[0]).name}"

                        if _art_content is not None:
                            _gathered_blocks.append(
                                f"[GATHERED ARTIFACT: {_pred_node}]\n{_art_content}\n[END ARTIFACT: {_pred_node}]"
                            )
                            logger.info(
                                f"[{AGENT_ID}] Tether-scoped inject from {_pred_node} "
                                f"(tether={_tether_id}): {_resolved_path_str}"
                            )
                        else:
                            logger.warning(
                                f"[{AGENT_ID}] WARNING: tether artifact/ledger not found for {_pred_node}"
                            )
                    except Exception as _exc:  # noqa: BLE001
                        logger.warning(
                            f"[{AGENT_ID}] WARNING: could not inject tether artifact for {_pred_node}: {_exc}"
                        )
                if _gathered_blocks:
                    payload_content = (
                        "\n\n".join(_gathered_blocks)
                        + "\n\n"
                        + payload_content
                    )
                    logger.info(
                        f"[{AGENT_ID}] Tether fan-in: injected {len(_gathered_blocks)} "
                        f"gathered artifact(s) for tether={_tether_id}."
                    )

            elif _wait_for_nodes:
                # ── Standard fan-in: collect from all matching Wait_For predecessors ──
                _gathered_blocks: list[str] = []
                for _pred_node in _wait_for_nodes:
                    try:
                        _pred_cfg = self.topology.get_node_config(_pred_node) if self.topology else {}
                        _pred_art_rel: str = str(_pred_cfg.get("artifact_path", "") or "")
                        _art_content = None
                        _resolved_path_str = ""

                        if _pred_art_rel:
                            # Resolve {SESSION_ID} token in the predecessor's artifact_path
                            _pred_art_rel = _pred_art_rel.replace("{SESSION_ID}", job_id)
                            # Inject job_id subfolder if not already scoped
                            _ART_PFX = "04_Code_Artifacts/"
                            if _pred_art_rel.startswith(_ART_PFX) and job_id not in _pred_art_rel:
                                _pred_art_rel = f"{_ART_PFX}{job_id}/{_pred_art_rel[len(_ART_PFX):]}"
                            _pred_art_abs = get_datacenter_path(*_pred_art_rel.split("/"))
                            if _pred_art_abs.exists():
                                _art_content = _pred_art_abs.read_text(encoding="utf-8")
                                _resolved_path_str = _pred_art_rel

                        if _art_content is None:
                            # Fallback to the predecessor's agent ledger
                            import glob  # noqa: PLC0415
                            _ledger_dir = get_datacenter_path("03_Agent_Ledgers", job_id)
                            _ledger_pattern = str(_ledger_dir / f"{_pred_node}_*.md")
                            _matches = glob.glob(_ledger_pattern)
                            if _matches:
                                _art_content = Path(_matches[0]).read_text(encoding="utf-8")
                                _resolved_path_str = f"03_Agent_Ledgers/{job_id}/{Path(_matches[0]).name}"

                        if _art_content is not None:
                            _gathered_blocks.append(
                                f"[GATHERED ARTIFACT: {_pred_node}]\n{_art_content}\n[END ARTIFACT: {_pred_node}]"
                            )
                            logger.info(f"[{AGENT_ID}] Injected artifact from {_pred_node}: {_resolved_path_str}")
                        else:
                            logger.warning(f"[{AGENT_ID}] WARNING: artifact/ledger not found for {_pred_node}")
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

            ai_options = node_config.get("ai_studio_options", {})
            _is_live_node = str(node_config.get("live_profile", "")).lower() in ("true", "1", "yes") or os.environ.get("MACCRE_LIVE_OVERRIDE") == "1"
            if not _is_dialogue_node:
                try:
                    from maccre_core.agent_library import get_agent_store  # noqa: PLC0415
                    store = get_agent_store("GLOBAL")
                    _agent_profile = next((r for r in store.load_all() if r.get("agent_name") == agent_name), {})
                    if _agent_profile:
                        _ai_opts = _agent_profile.get("ai_studio_options", {})
                        if _ai_opts:
                            ai_options = _ai_opts
                        if ai_options.get("grounding_google_search") and "google_search" not in tools_str:
                            tools_str = f"{tools_str}|google_search" if tools_str.lower() != "none" else "google_search"
                            logger.info(f"[{AGENT_ID}] Search grounding enabled for '{agent_name}' via agent_library.")
                except Exception:  # noqa: BLE001
                    pass  # Non-fatal — grounding simply won't activate

            # ── Flow Dictionary Overrides (host node — highest priority) ──────
            # Same MACCRE_CUSTOM_DICT mechanism used in _load_agent_cfg for
            # dialogue participants.  Applied AFTER topology CSV + agent library
            # DB so dict overrides always win.
            _host_dict_path = os.environ.get("MACCRE_CUSTOM_DICT", "")
            _flow_dict_profile: dict[str, Any] = {}
            if _host_dict_path and os.path.exists(_host_dict_path):
                try:
                    with open(_host_dict_path, "r", encoding="utf-8") as _hdf:
                        _host_full_dict: dict[str, Any] = json.load(_hdf)
                    # Skip _flow_meta key, look for agent-keyed entries
                    _flow_dict_profile = _host_full_dict.get(agent_name, {})
                except Exception as _hde:  # noqa: BLE001
                    logger.error(f"[{AGENT_ID}] Failed to load flow dict for {agent_name}: {_hde}")
            if _flow_dict_profile:
                system_prompt = _flow_dict_profile.get("system_prompt", system_prompt)
                model_id = _flow_dict_profile.get("model", model_id)
                _flow_temp = float(_flow_dict_profile.get("temperature", node_config.get("temperature", 1.0)))
                node_config["temperature"] = _flow_temp
                tools_str = _flow_dict_profile.get("tools_allowed", tools_str)
                _fd_host_ai: dict[str, Any] = _flow_dict_profile.get("ai_studio_options", {})
                if _fd_host_ai:
                    ai_options = _fd_host_ai

                # Inject search tools based on UI toggles (mirrors Chat Studio path)
                _t_list = [
                    t_.strip()
                    for t_ in tools_str.replace("|", ",").split(",")
                    if t_.strip() and t_.strip() != "none"
                ]
                if ai_options.get("grounding_google_search"):
                    if "google_search" not in _t_list:
                        _t_list.append("google_search")
                elif "google_search" in _t_list:
                    _t_list.remove("google_search")
                if ai_options.get("grounding_brave_search"):
                    if "search_web" not in _t_list:
                        _t_list.append("search_web")
                elif "search_web" in _t_list:
                    _t_list.remove("search_web")
                tools_str = ",".join(_t_list) if _t_list else "none"
                logger.info(f"[{AGENT_ID}] Flow dict override applied for host '{agent_name}'")

            if tools_str and tools_str.lower() != "none":
                system_prompt += (
                    "\n\n[TOOL AWARENESS]\n"
                    "You have access to specific functional tools. You do NOT need to ask for permission to use them. "
                    "If your instructions require external data, code execution, or file generation, you MUST use the provided tools."
                )

            # ── Execution Mode Dispatch ─────────────────────────────────────────
            # Three modes, checked in priority order:
            #   1. DIALOGUE — two persistent chat sessions alternating turns
            #   2. LIVE SESSION — streaming async session
            #   3. Standard agentic tool loop (default)
            current_payload: str = payload_content
            total_cost: float = 0.0

            # ── TRIPLE INDEX SEARCH PRE-INJECTION PIPELINES ───────────────────
            if not _is_dialogue_node and not _is_live_node:
                if current_payload.strip() != "[SYSTEM] WAIT_FOR_USER":
                    _ai_opts = locals().get("ai_options", {})
                    current_payload, _ti_cost, tools_str = self._apply_triple_index_search(current_payload, _ai_opts, model_id, AGENT_ID, tools_str, system_prompt=system_prompt)
                    total_cost += _ti_cost
            # ───────────────────────────────────────────────────────────────────────────

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
                    if name.strip().upper() in ("CTRL_REVIEW", "DET_REVIEW"):
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
                    from maccre_core.agent_library import get_agent_store
                    try:
                        _store = get_agent_store("GLOBAL")
                        for _p in _store.load_all():
                            _agent_name_val = str(_p.get("agent_name", "") or _p.get("AGENT_NAME", ""))
                            if _agent_name_val.strip() == name:
                                _sys = str(
                                    _p.get("system_prompt", "")
                                    or _p.get("PERSONA", "")
                                    or _p.get("instructions", "")
                                    or ""
                                )
                                _mdl = str(_p.get("model", "") or _p.get("MODEL", "") or _mdl)
                                _tmp = float(_p.get("temperature", "") or _p.get("TEMPERATURE", "") or _tmp)
                                _tls_val = str(_p.get("tools_allowed", "") or _p.get("TOOLS_ALLOWED", ""))
                                if _tls_val:
                                    _tls = _tls_val
                                
                                # Pull AI Studio toggle for grounding
                                _ai_opts = _p.get("ai_studio_options", {})
                                if _ai_opts.get("grounding_google_search", False):
                                    if "google_search" not in _tls:
                                        _tls = f"{_tls}|google_search" if _tls.lower() != "none" else "google_search"
                                break
                    except Exception as e:
                        logger.warning(f"[{AGENT_ID}] Failed to load agent {name} from DB: {e}")
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

                    # ── Flow Dictionary Overrides (highest priority) ──────────
                    # MACCRE_CUSTOM_DICT is a JSON file keyed by agent name with
                    # full agent profile + ai_studio_options.  Dict wins over
                    # both topology CSV and agent library DB.
                    _custom_dict_path = os.environ.get("MACCRE_CUSTOM_DICT", "")
                    if _custom_dict_path and os.path.exists(_custom_dict_path):
                        try:
                            with open(_custom_dict_path, "r", encoding="utf-8") as _df:
                                _full_dict: dict[str, Any] = _json.load(_df)
                            # Skip _flow_meta key, look for agent-keyed entries
                            _flow_profile: dict[str, Any] = _full_dict.get(name, {})
                            if _flow_profile:
                                _sys = _flow_profile.get("system_prompt", _sys)
                                _mdl = _flow_profile.get("model", _mdl)
                                _tmp = float(_flow_profile.get("temperature", _tmp))
                                _tls = _flow_profile.get("tools_allowed", _tls)
                                _fd_ai_opts: dict[str, Any] = _flow_profile.get("ai_studio_options", {})

                                # Inject search tools based on UI toggles (mirrors Chat Studio path)
                                _t_list = [
                                    _t.strip()
                                    for _t in _tls.replace("|", ",").split(",")
                                    if _t.strip() and _t.strip() != "none"
                                ]
                                if _fd_ai_opts.get("grounding_google_search"):
                                    if "google_search" not in _t_list:
                                        _t_list.append("google_search")
                                elif "google_search" in _t_list:
                                    _t_list.remove("google_search")
                                if _fd_ai_opts.get("grounding_brave_search"):
                                    if "search_web" not in _t_list:
                                        _t_list.append("search_web")
                                elif "search_web" in _t_list:
                                    _t_list.remove("search_web")
                                _tls = ",".join(_t_list) if _t_list else "none"
                                logger.info(f"[{AGENT_ID}] Flow dict override applied for '{name}'")
                        except Exception as _fde:  # noqa: BLE001
                            logger.error(f"[{AGENT_ID}] Failed to load flow dict for {name}: {_fde}")

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

            elif _is_live_node:

                import asyncio
                logger.info(f"[{AGENT_ID}] Executing via STREAM 4 LIVE SESSION.")
                final_output_text = self._run_interactive_diamond_loop(model_id, system_prompt, current_payload, job_id, current_node, locals().get("ai_options", {}), float(node_config.get("temperature", 1.0)), tools_str)
                task_cost = 0.0
                total_cost = 0.0
            else:
                # Multi-turn execution bounded by max_recursion.
                for turn_idx in range(max_tool_turns + 1):
                    is_last: bool = (turn_idx >= max_tool_turns)

                    output_text, turn_cost, api_thought = self.router.generate(
                        model_name=model_id,
                        payload=current_payload,
                        system_prompt=system_prompt,
                        tools_str=tools_str,
                        temperature=float(node_config.get("temperature", 0.7)),
                        expect_multiple_reads=True,
                        thinking_level=ai_options.get('thinking_level', 'low'),
                        safety_level=ai_options.get('safety_level', 'BLOCK_NONE')
                    )

                    # Always emit a forensic generation log for the thoughts ledger
                    _preview = output_text[:300].replace("\n", " ").strip()
                    logger.info(
                        f"<generation_log>\n"
                        f"model={model_id} | turn={turn_idx} | cost=${turn_cost:.6f} | agent={AGENT_ID}\n"
                        f"output_preview: {_preview}{'...' if len(output_text) > 300 else ''}\n"
                        f"</generation_log>"
                    )

                    if api_thought:
                        logger.info(f"<api_thought>\n{api_thought}\n</api_thought>")
                        
                    import re as _re_pbr
                    pbr_thoughts = _re_pbr.findall(r'<thought>(.*?)</thought>', output_text, _re_pbr.DOTALL)
                    for t in pbr_thoughts:
                        logger.info(f"<thought>\n{t.strip()}\n</thought>")

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
                        # Capture native search grounding as a tool call
                        if "### Search Grounding Sources:" in output_text:
                            _gs_start = output_text.index("### Search Grounding Sources:")
                            _gs_block = output_text[_gs_start:]
                            logger.info(f"<tool_call>\n[GOOGLE_SEARCH_GROUNDING]\n{_gs_block}\n</tool_call>")
                        if tool_audit_lines:
                            logger.info(f"[{AGENT_ID}] Tool loop complete: {turn_idx} tool turn(s) → clean output.")
                        break

                    # Capture raw tool call text for forensic audit sidecar.
                    tool_audit_lines.append(f"## TOOL TURN {turn_idx + 1}/{max_tool_turns}\n{output_text}")
                    # Log explicitly into the telemetry stream
                    logger.info(f"<tool_call>\n{output_text}\n</tool_call>")

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
                        close_text, close_cost, _ = self.router.generate(
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
                            final_output_text = f"{output_text}\n\n[FILE CONTENT]:\n{t_args['data']}"
                        elif t_args and "content" in t_args:
                            final_output_text = f"{output_text}\n\n[FILE CONTENT]:\n{t_args['content']}"
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
            
            # ── Prose Purge ──────────────────────────────────────────────────────────
            import re as _re  # noqa: PLC0415
            _scratchpad_pattern = _re.compile(r"<scratchpad[^>]*>(.*?)</scratchpad>", _re.DOTALL)

            # Strip thoughts from the main ledger output so it remains clean prose
            raw_model_output = _scratchpad_pattern.sub("", final_output_text).strip()
            
            # NOTE: We do NOT strip from tool_audit_lines, so the sidecar gets the thoughts inline!

            logger.info(f"[{AGENT_ID}] Generation complete. Billed Cost: ${task_cost:.6f}")

            ledger_content_out = raw_model_output
            with open(ledger_path, "w", encoding="utf-8") as f:
                f.write(ledger_content_out)

            # ── Forensic Thoughts and Tools Sidecar ───────────────────────────────────
            # Written alongside the ledger whenever tools fired during the loop.
            # Captures every tool call + result verbatim for effectiveness auditing.
            if tool_audit_lines:
                from datetime import datetime, timezone  # noqa: PLC0415
                
                if job_id.startswith("studio_session_"):
                    audit_path = Path(ledger_path).parent / f"{job_id}-{AGENT_ID}_thoughts_tool-calls.log"
                    mode = "a"
                else:
                    audit_path = Path(ledger_path).parent / f"thoughts_and_tools_{current_node}_{row_id}.md"
                    mode = "w"
                    
                audit_ts = datetime.now(tz=timezone.utc).isoformat()
                audit_header = f"\n\n# Thoughts and Tools Ledger — {current_node} | {job_id} | {audit_ts}\n\n" if mode == "a" else f"# Thoughts and Tools Ledger — {current_node} | {job_id} | {audit_ts}\n\n"
                audit_body = "\n\n".join(tool_audit_lines) + f"\n\n## FINAL OUTPUT\n{final_output_text}"
                
                with open(audit_path, mode, encoding="utf-8") as af:
                    af.write(audit_header + audit_body)
                logger.info(f"[{AGENT_ID}] Thoughts and tools sidecar: {audit_path}")

            # ── LIVE STREAMING ACOUSTICS ──────────────────────────────────────
            # Trigger real-time conversational streaming for non-director nodes
            if "director" not in AGENT_ID.lower():
                # live_stream_audio(ledger_content_out, AGENT_ID, job_id, current_node)
                pass

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
            _ROUTE_TO_PATTERN = _re.compile(r"ROUTE_TO:\s*([A-Za-z0-9_,\s\[\]{}]+)", _re.IGNORECASE)
            _route_match = _ROUTE_TO_PATTERN.search(raw_model_output or "")
            if _route_match:
                _candidate = _route_match.group(1).replace("[", "").replace("]", "").replace("{", "").replace("}", "").strip()
                
                # ACCEPTED means "all gates passed — proceed to static next_node"
                if _candidate.upper() == "ACCEPTED":
                    logger.info(
                        f"[{AGENT_ID}] CONDITIONAL ROUTE: ROUTE_TO:ACCEPTED — "
                        f"proceeding to static next_node '{next_node}'"
                    )
                elif _candidate and _candidate.upper() not in {"STOP", "DONE", "TERMINATE", "FAILED"}:
                    # Handle comma-separated routes by resolving each individually against Node IDs or Agent Names
                    _topology_map = self.topology.get_topology() if self.topology else {}
                    try:
                        from maccre_core.macronode_registry import get_macronode_store  # noqa: PLC0415
                        _ephemeral_map = get_macronode_store().load_ephemeral_graph()
                    except Exception:  # noqa: BLE001
                        _ephemeral_map = {}

                    combined_map = {**_topology_map, **_ephemeral_map}
                    
                    resolved_targets = []
                    for cand_part in _candidate.split(","):
                        cand_part = cand_part.strip()
                        if not cand_part:
                            continue
                            
                        # Find exact Node ID match OR Agent Name match
                        matched_node_id = None
                        if cand_part in combined_map:
                            matched_node_id = cand_part
                        else:
                            for t_node, t_cfg in combined_map.items():
                                if str(t_cfg.get("agent_name", "")).strip().lower() == cand_part.lower():
                                    matched_node_id = t_node
                                    break
                                    
                        if matched_node_id:
                            resolved_targets.append(matched_node_id)
                            
                    if resolved_targets:
                        next_node = ",".join(resolved_targets)
                        logger.info(
                            f"[{AGENT_ID}] CONDITIONAL ROUTE: overridden by "
                            f"ROUTE_TO:{next_node} (model-directed)"
                        )
                    else:
                        logger.info(
                            f"[{AGENT_ID}] CONDITIONAL ROUTE: ROUTE_TO:{_candidate} ignored "
                            f"(targets not found in topology or ephemeral macros)"
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
                        tgt_cfg = self.topology.get_node_config(next_node.split(",")[0].strip())
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
                flow_line_id=str(task.get("flow_line_id", "")),
                flow_vector=flow_vector,
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
                status="failed",
                flow_line_id=str(task.get("flow_line_id", "")),
                flow_vector=flow_vector,
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
