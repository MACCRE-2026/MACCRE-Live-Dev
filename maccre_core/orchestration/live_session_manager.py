# B:/MACCREv2/maccre_core/orchestration/live_session_manager.py
from __future__ import annotations

import json
import logging
from typing import Callable, Any

_log = logging.getLogger(__name__)

class LiveSessionManager:
    """
    Stream 4 Central Hub.
    Subscribes to all MACCRE.* events from workers via tcp://127.0.0.1:5556.
    Publishes MACCRE.INTERRUPT and MACCRE.ROUTE commands to workers via tcp://127.0.0.1:5557.
    """
    def __init__(self) -> None:
        import zmq  # type: ignore
        import zmq.asyncio  # type: ignore
        self.zmq_ctx = zmq.asyncio.Context.instance()
        
        # SUB socket: listen to Swarm telemetry (Workers CONNECT, Manager BINDs)
        self.sub_socket = self.zmq_ctx.socket(zmq.SUB)
        self.sub_socket.bind("tcp://127.0.0.1:5556")
        self.sub_socket.setsockopt_string(zmq.SUBSCRIBE, "MACCRE.")
        
        # PUB socket: push interrupts & routed messages to Swarm workers
        self.pub_socket = self.zmq_ctx.socket(zmq.PUB)
        self.pub_socket.bind("tcp://127.0.0.1:5557")
        
        self.callbacks: dict[str, list[Callable[[dict[str, Any]], None]]] = {}
        
        # Topology C2 State
        self.preset_mode = "entropy"  # Options: entropy, hub, silo, round_robin
        self.active_agents: set[str] = set()
        
        # Physics Engine
        from maccre_core.orchestration.scorekeeper import ScoreKeeper
        self.scorekeeper = ScoreKeeper()

    def set_preset_mode(self, mode: str) -> None:
        self.preset_mode = mode.lower()
        _log.info(f"[LiveSessionManager] Preset Mode changed to: {self.preset_mode}")

    def register_agent(self, agent_id: str) -> None:
        self.active_agents.add(agent_id)

    def register_callback(self, event_type: str, callback: Callable[[dict[str, Any]], None]) -> None:
        """Register a function to fire when a specific event (e.g., 'CHAT') is received."""
        if event_type not in self.callbacks:
            self.callbacks[event_type] = []
        self.callbacks[event_type].append(callback)

    async def _physics_loop_async(self) -> None:
        """Broadcasts conversational physics updates to the TUI."""
        import asyncio
        while True:
            try:
                self.scorekeeper.tick()
                # Broadcast state
                payload = {
                    "tension": self.scorekeeper.state.tension_level,
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
        """Asynchronous loop for Textual TUI integration."""
        _log.info("[LiveSessionManager] Listening asynchronously on ZMQ 5556...")
        import asyncio
        
        # Start the physics loop
        physics_task = asyncio.create_task(self._physics_loop_async())
        
        while True:
            try:
                topic, msg = await self.sub_socket.recv_multipart()
                topic_str = topic.decode("utf-8")
                payload = json.loads(msg.decode("utf-8"))
                
                event_type = topic_str.split(".")[-1]
                
                if event_type == "CHAT":
                    speaker = payload.get("agent_name")
                    job_id = payload.get("job_id")
                    if speaker:
                        self.register_agent(speaker)
                        # Register speech in physics engine
                        self.scorekeeper.register_speech(speaker, tension_modifier=0.05)
                        await self._route_chat_message(job_id, speaker, payload.get("text", ""))
                
                # Dispatch to local TUI UI listeners
                for cb in self.callbacks.get(event_type, []):
                    cb(payload)
                for cb in self.callbacks.get("*", []):
                    cb(payload)
                    
            except asyncio.CancelledError:
                break
            except Exception as e:
                _log.error("[LiveSessionManager] Decode Error: %s", e)
                
        physics_task.cancel()

    async def _route_chat_message(self, job_id: str, speaker: str, text: str) -> None:
        """Dynamic isolation logic based on current preset mode."""
        targets = []
        if self.preset_mode == "entropy":
            # Everyone hears everyone
            targets = [a for a in self.active_agents if a != speaker]
        elif self.preset_mode == "silo":
            # Just as an example, silo prevents agents from hearing each other, they only hear User?
            # User wants: "Two agents talk only to each other. User provides nudges but agents don't talk to the user."
            # For dynamic isolation, we might just block all agent-to-agent chatter for now unless configured.
            # Real implementation of silo would look up a dedicated subgroup.
            # Let's say "silo" limits to the first 2 agents seen.
            sorted_agents = sorted(list(self.active_agents))
            silo_group = sorted_agents[:2]
            if speaker in silo_group:
                targets = [a for a in silo_group if a != speaker]
        elif self.preset_mode == "hub":
            # Agents only focus on user, do not talk to each other
            targets = []
        elif self.preset_mode == "round_robin":
            # Enforce strict turn taking
            targets = [a for a in self.active_agents if a != speaker]

        for target in targets:
            route_topic = f"MACCRE.ROUTE.{target}".encode("utf-8")
            route_payload = json.dumps({"job_id": job_id, "speaker": speaker, "text": text}).encode("utf-8")
            await self.pub_socket.send_multipart([route_topic, route_payload])

    async def inject_interrupt_async(self, job_id: str, override_text: str, target_agent: str = "ALL") -> None:
        """Pushes an instantaneous override payload to the active worker(s)."""
        payload = {"job_id": job_id, "override_text": override_text, "target_agent": target_agent}
        await self.pub_socket.send_multipart([b"MACCRE.INTERRUPT", json.dumps(payload).encode("utf-8")])
        _log.info("[LiveSessionManager] Interrupt dispatched for %s (Target: %s)", job_id, target_agent)

    def __del__(self) -> None:
        """OmniBuilder Compliance: Teardown ZMQ sockets."""
        try:
            self.sub_socket.close()
            self.pub_socket.close()
        except Exception:
            pass
