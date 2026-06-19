from __future__ import annotations

import time
import logging
from dataclasses import dataclass, field

_log = logging.getLogger(__name__)

@dataclass
class ConversationState:
    """The central nervous system of a Live Swarm session."""
    speaker_turns: dict[str, int] = field(default_factory=dict)
    topic_momentum: dict[str, float] = field(default_factory=dict)
    tension_level: float = 0.0
    agent_tension: dict[str, float] = field(default_factory=dict)
    silence_duration_ms: int = 0
    last_speaker: str = "System"
    pending_interrupts: list[str] = field(default_factory=list)
    last_tick_time: float = field(default_factory=time.time)

class ScoreKeeper:
    """
    Stream 4b: Conversational Physics Engine.
    Evaluates real-time tension, topic affinity, and dominance to orchestrate
    agent interruptions without predefined turn orders.
    """
    def __init__(self) -> None:
        self.state = ConversationState()
        
    def tick(self) -> None:
        """Called every N milliseconds by the LiveSessionManager."""
        now = time.time()
        delta_ms = int((now - self.state.last_tick_time) * 1000)
        self.state.silence_duration_ms += delta_ms
        self.state.last_tick_time = now
        
        # Natural decay of tension during silence
        if self.state.tension_level > 0:
            self.state.tension_level = max(0.0, self.state.tension_level - 0.01)
            
        # Decay individual agent tensions
        for agent in list(self.state.agent_tension.keys()):
            if self.state.agent_tension[agent] > 0:
                self.state.agent_tension[agent] = max(0.0, self.state.agent_tension[agent] - 0.02)

    def evaluate_interruption(self, agent_name: str, dominance: float, interrupt_threshold: float, topic_affinity_match: float) -> bool:
        """
        Physics Math:
        score = (topic_affinity * 0.4) + (tension * 0.3) + (dominance * 0.3)
        """
        score = (topic_affinity_match * 0.4) + (self.state.tension_level * 0.3) + (dominance * 0.3)
        
        # Agents with high verbosity and dominance who cross the threshold will barge in.
        if score > interrupt_threshold:
            _log.info(f"[ScoreKeeper] {agent_name} generated an interruption impulse (Score: {score:.2f} > {interrupt_threshold})")
            return True
            
        return False
        
    def register_speech(self, speaker: str, tension_modifier: float = 0.0) -> None:
        """Fired when an agent successfully speaks."""
        self.state.silence_duration_ms = 0
        self.state.last_speaker = speaker
        self.state.speaker_turns[speaker] = self.state.speaker_turns.get(speaker, 0) + 1
        
        # Bump or lower tension based on the content of the speech
        self.state.tension_level = min(1.0, max(0.0, self.state.tension_level + tension_modifier))
        self.state.agent_tension[speaker] = min(1.0, self.state.agent_tension.get(speaker, 0.0) + 0.3 + tension_modifier)
