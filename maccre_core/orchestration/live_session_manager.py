from __future__ import annotations

import logging
from typing import Callable, Any

_log = logging.getLogger(__name__)

class LiveSessionManager:
    """
    Stream 4 Central Hub.
    Subscribes to all MACCRE.* events from workers via JsonFileQueue.
    Publishes MACCRE.INTERRUPT and MACCRE.ROUTE commands to workers via JsonFileQueue.
    """
    def __init__(self) -> None:
        from maccre_core.orchestration.queues import JsonFileQueue
        self.message_bus = JsonFileQueue("live_session_bus", clear=True)
        
        self.callbacks: dict[str, list[Callable[[dict[str, Any]], None]]] = {}
        
        # Topology C2 State
        self.preset_mode = "entropy"  # Options: entropy, hub, silo, round_robin
        self.active_agents: set[str] = set()
        
        # Physics Engine
        from maccre_core.orchestration.scorekeeper import ScoreKeeper
        self.scorekeeper = ScoreKeeper()

        # HITL (Human-In-The-Loop) turn tracking
        self.global_turns: int = 0
        self.hitl_threshold: int = 5

    def set_preset_mode(self, mode: str) -> None:
        self.preset_mode = mode.lower()
        _log.info(f"[LiveSessionManager] Preset Mode changed to: {self.preset_mode}")

    def register_agent(self, agent_id: str) -> None:
        self.active_agents.add(agent_id)

    def register_callback(self, event_type: str, callback: Callable[[dict[str, Any]], None]) -> None:
        if event_type not in self.callbacks:
            self.callbacks[event_type] = []
        self.callbacks[event_type].append(callback)

    async def _physics_loop_async(self) -> None:
        import asyncio
        while True:
            try:
                self.scorekeeper.tick()
                payload = {
                    "tension": self.scorekeeper.state.tension_level,
                    "agent_tension": self.scorekeeper.state.agent_tension,
                    "silence_ms": self.scorekeeper.state.silence_duration_ms,
                    "last_speaker": self.scorekeeper.state.last_speaker,
                    "speaker_turns": self.scorekeeper.state.speaker_turns
                }
                for cb in self.callbacks.get("PHYSICS", []):
                    cb(payload)
                await asyncio.sleep(0.5)
            except asyncio.CancelledError:
                break
            except Exception as e:
                _log.error("[LiveSessionManager] Physics Loop Error: %s", e)
                await asyncio.sleep(1)

    async def listen_loop_async(self) -> None:
        _log.info("[LiveSessionManager] Listening asynchronously on JsonFileQueue...")
        import asyncio
        
        physics_task = asyncio.create_task(self._physics_loop_async())
        
        while True:
            try:
                messages = self.message_bus.poll(["MACCRE.*"])
                for topic_str, payload in messages:
                    event_type = topic_str.split(".")[-1]
                    
                    if event_type == "CHAT":
                        speaker = payload.get("agent_name")
                        job_id: str = str(payload.get("job_id") or "")
                        is_typing = payload.get("is_typing", False)
                        if speaker:
                            self.register_agent(speaker)
                            if not is_typing:
                                self.scorekeeper.register_speech(speaker, tension_modifier=0.05)
                                await self._route_chat_message(
                                    str(job_id or ""), 
                                    speaker, 
                                    payload.get("text", ""),
                                    payload.get("thought", "")
                                )
                    
                    for cb in self.callbacks.get(event_type, []):
                        cb(payload)
                    for cb in self.callbacks.get("*", []):
                        cb(payload)
                        
                await asyncio.sleep(0.2)  # Prevent tight CPU loop
                    
            except asyncio.CancelledError:
                break
            except Exception as e:
                _log.error("[LiveSessionManager] Decode Error: %s", e)
                
        physics_task.cancel()

    async def _route_chat_message(self, job_id: str, speaker: str, text: str, thought: str = "") -> None:
        from maccre_core.utils.path_resolver import get_datacenter_path

        clean_id = job_id.replace("studio_session_", "", 1) if job_id.startswith("studio_session_") else job_id

        # Write to session-scoped unified chat log
        if job_id.startswith("studio_session_"):
            log_dir = get_datacenter_path("04_Code_Artifacts", f"ChatStudioSessions/{clean_id}-Chat")
            log_path = log_dir / "unified_chat_ledger.md"
        else:
            log_dir = get_datacenter_path("04_Code_Artifacts")
            log_path = log_dir / "agent_chat_ledger.md"
            
        log_dir.mkdir(parents=True, exist_ok=True)
        
        with open(log_path, "a", encoding="utf-8") as f:
            if thought:
                f.write(f"### {speaker} (Internal Reasoning)\n```markdown\n{thought}\n```\n\n")
            f.write(f"**{speaker}**: {text}\n\n---\n\n")

        # Track global turns for HITL pause
        self.global_turns += 1
        
        if self.global_turns >= self.hitl_threshold:
            _log.info("[LiveSessionManager] HITL threshold reached. Pausing swarm.")
            self.global_turns = 0
            # Broadcast the pause to all agents to interrupt them
            payload = {"job_id": job_id, "override_text": "[SYSTEM] Pausing for user input...", "target_agent": "ALL"}
            self.message_bus.publish("MACCRE.INTERRUPT", payload)
            
            with open(log_path, "a", encoding="utf-8") as f:
                f.write("**SYSTEM**: Swarm paused for Human-In-The-Loop review.\n\n---\n\n")
            return

        targets = []
        if self.preset_mode == "entropy":
            best_score = -1.0
            best_agent = None
            
            for agent in self.active_agents:
                if agent == speaker:
                    continue
                turns = self.scorekeeper.state.speaker_turns.get(agent, 0)
                tension = self.scorekeeper.state.agent_tension.get(agent, 0.0)
                
                # Bidding heuristic: prioritize agents with fewer turns and high tension
                bid = (1.0 / (turns + 1)) * 0.5 + tension * 0.5
                if bid > best_score:
                    best_score = bid
                    best_agent = agent
                    
            if best_agent:
                targets = [best_agent]
        elif self.preset_mode == "silo":
            sorted_agents = sorted(list(self.active_agents))
            silo_group = sorted_agents[:2]
            if speaker in silo_group:
                targets = [a for a in silo_group if a != speaker]
        elif self.preset_mode == "hub":
            targets = []
        elif self.preset_mode == "round_robin":
            targets = [a for a in self.active_agents if a != speaker]

        for target in targets:
            route_topic = f"MACCRE.ROUTE.{target}"
            route_payload = {"job_id": job_id, "speaker": speaker, "text": text}
            self.message_bus.publish(route_topic, route_payload)

    async def inject_interrupt_async(self, job_id: str, override_text: str, target_agent: str = "ALL") -> None:
        payload = {"job_id": job_id, "override_text": override_text, "target_agent": target_agent}
        self.message_bus.publish("MACCRE.INTERRUPT", payload)
        _log.info("[LiveSessionManager] Interrupt dispatched for %s (Target: %s)", job_id, target_agent)

    def __del__(self) -> None:
        pass
