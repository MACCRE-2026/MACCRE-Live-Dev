"""
maccre_core/orchestration/dialogue_runner.py
============================================
Persistent two-agent dialogue sessions with full context retention.

Each agent maintains an independent conversation history that grows with
every exchange turn, giving both agents a genuine "open chat window" — the
model sees its own complete prior output AND its partner's replies in their
correct conversational positions.

MACCREv2 Law Rev 19.0 compliant.

Usage (swarm_worker.py):
    from maccre_core.orchestration.dialogue_runner import DialogueRunner

    runner = DialogueRunner(
        router=self.router,
        agent_a_model="gemini-2.5-flash",
        agent_a_system=osint_system_prompt,
        agent_a_temperature=1.0,
        agent_b_model="gemini-2.5-flash",
        agent_b_system=joe_system_prompt,
        agent_b_temperature=0.9,
        num_rounds=3,
        agent_a_label="OSINT_Analyst",
        agent_b_label="Regular_Joe",
    )
    transcript, total_cost = runner.run(initial_message=payload)
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class _AgentSession:
    """Encapsulates one agent's persistent chat state."""

    label: str
    model: str
    system_prompt: str
    temperature: float
    tools_str: str = "none"
    # Conversation history — grows after every exchange turn.
    # Format mirrors router.generate(conversation_history=…):
    #   [{"role": "user", "text": "<what the model received>"},
    #    {"role": "model", "text": "<what the model replied>"},
    #    ...]
    history: list[dict[str, str]] = field(default_factory=list)
    total_cost: float = 0.0

    def send(self, router: Any, message: str) -> str:
        """
        Send ``message`` to this agent and return the raw response text.

        The full conversation history is passed to the router on every call
        so the model has genuine multi-turn context — it remembers everything
        it has said and received in this session.

        Args:
            router: ``UniversalRouter`` instance from ``maccre_router.py``.
            message: The incoming user turn content.

        Returns:
            The model's raw reply text.
        """
        response_text, cost = router.generate(
            model_name=self.model,
            payload=message,
            system_prompt=self.system_prompt,
            tools_str=self.tools_str,
            temperature=self.temperature,
            conversation_history=self.history if self.history else None,
        )
        self.total_cost += cost

        # Append this exchange to history so the NEXT call has full context.
        # Format: user turn = what we sent, model turn = what it replied.
        self.history.append({"role": "user",  "text": message})
        self.history.append({"role": "model", "text": response_text})

        logger.info(
            "[DialogueRunner] %s turn complete | history_turns=%d | cost=%.6f",
            self.label, len(self.history) // 2, cost,
        )
        return response_text


class DialogueRunner:
    """
    Runs a structured multi-turn dialogue between two persistent agent sessions.

    Both agents retain their full conversation history across all rounds.
    Agent A speaks first (receives the initial payload). Agent B responds.
    They alternate for ``num_rounds`` full exchanges.

    The returned transcript is a clean chronological log of every turn,
    labelled by agent, suitable for passing directly to a downstream node
    (e.g. CounterPartner) as a self-contained document.

    Args:
        router:              ``UniversalRouter`` instance.
        agent_a_model:       Model ID for Agent A.
        agent_a_system:      System prompt / persona for Agent A.
        agent_a_temperature: Sampling temperature for Agent A.
        agent_b_model:       Model ID for Agent B.
        agent_b_system:      System prompt / persona for Agent B.
        agent_b_temperature: Sampling temperature for Agent B.
        num_rounds:          Number of complete A→B exchanges to run.
        agent_a_label:       Human-readable label for transcript headers.
        agent_b_label:       Human-readable label for transcript headers.
        agent_a_tools:       Pipe-separated tool names for Agent A (default "none").
        agent_b_tools:       Pipe-separated tool names for Agent B (default "none").
    """

    def __init__(
        self,
        router: Any,
        agent_a_model: str,
        agent_a_system: str,
        agent_a_temperature: float,
        agent_b_model: str,
        agent_b_system: str,
        agent_b_temperature: float,
        num_rounds: int = 3,
        agent_a_label: str = "Agent_A",
        agent_b_label: str = "Agent_B",
        agent_a_tools: str = "none",
        agent_b_tools: str = "none",
    ) -> None:
        self._router = router
        self._num_rounds = max(1, num_rounds)

        self._agent_a = _AgentSession(
            label=agent_a_label,
            model=agent_a_model,
            system_prompt=agent_a_system,
            temperature=agent_a_temperature,
            tools_str=agent_a_tools,
        )
        self._agent_b = _AgentSession(
            label=agent_b_label,
            model=agent_b_model,
            system_prompt=agent_b_system,
            temperature=agent_b_temperature,
            tools_str=agent_b_tools,
        )

    # ── Public API ────────────────────────────────────────────────────────────

    def run(self, initial_message: str) -> tuple[str, float]:
        """
        Execute the full dialogue and return the merged transcript.

        Flow:
            1. Agent A receives ``initial_message`` — generates opening turn.
            2. Agent B receives Agent A's output — generates first reply.
            3. Repeat (A→B) for ``num_rounds`` total full exchanges.

        Both agents see their own full prior output in every subsequent turn
        via the persistent history passed to ``router.generate()``.

        Args:
            initial_message: The seed content Agent A receives first.
                             Typically the user's research payload.

        Returns:
            ``(transcript_str, total_cost_usd)``
        """
        transcript_parts: list[str] = []

        logger.info(
            "[DialogueRunner] Starting dialogue: %s ↔ %s | rounds=%d",
            self._agent_a.label, self._agent_b.label, self._num_rounds,
        )

        # Agent A opens — this is round 0, the anchor generation.
        print(
            f"[DialogueRunner] ── Round 0 / {self._num_rounds}: "
            f"{self._agent_a.label} opening ──"
        )
        a_reply = self._agent_a.send(self._router, initial_message)
        transcript_parts.append(
            f"[{self._agent_a.label} — Opening]\n{a_reply}"
        )

        # Alternate for num_rounds full B→A exchanges.
        for round_idx in range(1, self._num_rounds + 1):
            print(
                f"[DialogueRunner] ── Round {round_idx} / {self._num_rounds}: "
                f"{self._agent_b.label} responding ──"
            )
            b_reply = self._agent_b.send(self._router, a_reply)
            transcript_parts.append(
                f"[{self._agent_b.label} — Round {round_idx}]\n{b_reply}"
            )

            if round_idx < self._num_rounds:
                print(
                    f"[DialogueRunner] ── Round {round_idx} / {self._num_rounds}: "
                    f"{self._agent_a.label} responding ──"
                )
                a_reply = self._agent_a.send(self._router, b_reply)
                transcript_parts.append(
                    f"[{self._agent_a.label} — Round {round_idx}]\n{a_reply}"
                )
            else:
                # Final A reply — closes the exchange for CounterPartner.
                print(
                    f"[DialogueRunner] ── Round {round_idx} FINAL: "
                    f"{self._agent_a.label} final reply ──"
                )
                a_reply = self._agent_a.send(self._router, b_reply)
                transcript_parts.append(
                    f"[{self._agent_a.label} — Final Reply]\n{a_reply}"
                )

        total_cost = self._agent_a.total_cost + self._agent_b.total_cost
        transcript = "\n\n" + ("\n\n─────────────────────────────────────────\n\n".join(transcript_parts))

        logger.info(
            "[DialogueRunner] Dialogue complete | total_rounds=%d | total_cost=%.6f",
            self._num_rounds, total_cost,
        )
        print(f"[DialogueRunner] ✓ Complete — {self._num_rounds} rounds | cost=${total_cost:.6f}")
        return transcript, total_cost

    @property
    def agent_a_history(self) -> list[dict[str, str]]:
        """Full conversation history for Agent A (read-only view)."""
        return list(self._agent_a.history)

    @property
    def agent_b_history(self) -> list[dict[str, str]]:
        """Full conversation history for Agent B (read-only view)."""
        return list(self._agent_b.history)

    @property
    def total_cost(self) -> float:
        """Accumulated cost across both agents for the full dialogue."""
        return self._agent_a.total_cost + self._agent_b.total_cost
