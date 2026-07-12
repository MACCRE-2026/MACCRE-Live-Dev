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
import re
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


class ManualInputRequired(Exception):
    """
    Raised when a dialogue round hits a MANUAL participant.
    The swarm worker catches this, saves the checkpoint state, and pauses the task
    until the user provides input via the TUI intercept.
    """
    def __init__(self, participant_label: str, checkpoint: dict[str, Any] | None = None) -> None:
        super().__init__(f"Manual input required for {participant_label}")
        self.participant_label = participant_label
        self.checkpoint = checkpoint


@dataclass
class _AgentSession:
    """Encapsulates one agent's persistent chat state."""

    label: str
    model: str
    system_prompt: str
    temperature: float
    tools_str: str = "none"
    thinking_level: str = "low"
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
        if self.model == "manual":
            raise ManualInputRequired(participant_label=self.label)

        response_text, cost, api_thought = router.generate(
            model_name=self.model,
            payload=message,
            system_prompt=self.system_prompt,
            tools_str=self.tools_str,
            temperature=self.temperature,
            conversation_history=self.history if self.history else None,
            expect_multiple_reads=True,
            thinking_level=self.thinking_level,
        )
        self.total_cost += cost

        # ── Emit thoughts for unified_thoughts_ledger extraction ──────────
        if api_thought:
            logger.info("<api_thought>\n%s\n</api_thought>", api_thought)
        pbr_thoughts = re.findall(r"<thought>(.*?)</thought>", response_text, re.DOTALL)
        for t in pbr_thoughts:
            logger.info("<thought>\n%s\n</thought>", t.strip())
        # Capture native search grounding as a tool call
        if "### Search Grounding Sources:" in response_text:
            _gs_idx = response_text.index("### Search Grounding Sources:")
            _gs_block = response_text[_gs_idx:]
            logger.info("<tool_call>\n[GOOGLE_SEARCH_GROUNDING]\n%s\n</tool_call>", _gs_block)

        # Append this exchange to history so the NEXT call has full context.
        # Format: user turn = what we sent, model turn = what it replied.
        self.history.append({"role": "user",  "text": message})
        self.history.append({"role": "model", "text": response_text})

        logger.info(
            "[DialogueRunner] %s turn complete | history_turns=%d | cost=%.6f",
            self.label, len(self.history) // 2, cost,
        )
        return response_text

    # ── Time Travel API ───────────────────────────────────────────────────────

    def to_checkpoint(self) -> dict[str, Any]:
        """Serialise this session's full state to a JSON-safe dict."""
        return {
            "label": self.label,
            "model": self.model,
            "system_prompt": self.system_prompt,
            "temperature": self.temperature,
            "tools_str": self.tools_str,
            "history": list(self.history),
            "total_cost": self.total_cost,
        }

    @classmethod
    def from_checkpoint(cls, data: dict[str, Any]) -> "_AgentSession":
        """Reconstruct an _AgentSession from a checkpoint dict."""
        session = cls(
            label=str(data["label"]),
            model=str(data["model"]),
            system_prompt=str(data["system_prompt"]),
            temperature=float(data["temperature"]),
            tools_str=str(data.get("tools_str", "none")),
        )
        session.history = list(data.get("history", []))
        session.total_cost = float(data.get("total_cost", 0.0))
        return session


# ─────────────────────────────────────────────────────────────────────────────
# ParticipantConfig — typed spec for GroupDialogueRunner participants
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class ParticipantConfig:
    """
    Configuration for one participant in a GroupDialogueRunner session.

    Fields map 1:1 to what the workbook author specifies in the AGENTS sheet
    and the topology's Dialogue_Partner column.  The swarm_worker loads agent
    cards / roster rows and constructs these before handing off to the runner.
    """

    label: str           # human-readable label used in transcript headers
    model: str           # model ID, e.g. "gemini-2.5-flash"
    system_prompt: str   # persona / instructions string
    temperature: float   # sampling temperature
    tools_str: str = "none"


# ─────────────────────────────────────────────────────────────────────────────
# DialogueRunner — original 2-agent pair runner (unchanged)
# ─────────────────────────────────────────────────────────────────────────────

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

    def run(self, initial_message: str, stop_event: Any = None) -> tuple[str, str, float]:
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
            ``(transcript_str, final_turn, total_cost_usd)``
        """
        transcript_parts: list[str] = []

        logger.info(
            "[DialogueRunner] Starting dialogue: %s ↔ %s | rounds=%d",
            self._agent_a.label, self._agent_b.label, self._num_rounds,
        )

        # Agent A opens — this is round 0, the anchor generation.
        logger.info(
            f"[DialogueRunner] ── Round 0 / {self._num_rounds}: "
            f"{self._agent_a.label} opening ──"
        )
        try:
            a_reply = self._agent_a.send(self._router, initial_message)
        except ManualInputRequired as e:
            e.checkpoint = self.to_checkpoint()
            raise
        transcript_parts.append(
            f"[{self._agent_a.label} — Opening]\n{a_reply}"
        )

        # Alternate for num_rounds full B→A exchanges.
        for round_idx in range(1, self._num_rounds + 1):
            if stop_event is not None and stop_event.is_set():
                logger.info("[DialogueRunner] --- Flow Stop Requested (cancelling between rounds) ---")
                break
                
            logger.info(
                f"[DialogueRunner] ── Round {round_idx} / {self._num_rounds}: "
                f"{self._agent_b.label} responding ──"
            )
            try:
                b_reply = self._agent_b.send(self._router, a_reply)
            except ManualInputRequired as e:
                e.checkpoint = self.to_checkpoint()
                raise
            transcript_parts.append(
                f"[{self._agent_b.label} — Round {round_idx}]\n{b_reply}"
            )

            if round_idx < self._num_rounds:
                logger.info(
                    f"[DialogueRunner] ── Round {round_idx} / {self._num_rounds}: "
                    f"{self._agent_a.label} responding ──"
                )
                try:
                    a_reply = self._agent_a.send(self._router, b_reply)
                except ManualInputRequired as e:
                    e.checkpoint = self.to_checkpoint()
                    raise
                transcript_parts.append(
                    f"[{self._agent_a.label} — Round {round_idx}]\n{a_reply}"
                )
            else:
                # Final A reply — closes the exchange for CounterPartner.
                logger.info(
                    f"[DialogueRunner] ── Round {round_idx} FINAL: "
                    f"{self._agent_a.label} final reply ──"
                )
                try:
                    a_reply = self._agent_a.send(self._router, b_reply)
                except ManualInputRequired as e:
                    e.checkpoint = self.to_checkpoint()
                    raise
                transcript_parts.append(
                    f"[{self._agent_a.label} — Final Reply]\n{a_reply}"
                )

        total_cost = self._agent_a.total_cost + self._agent_b.total_cost
        transcript = "\n\n" + ("\n\n─────────────────────────────────────────\n\n".join(transcript_parts))

        logger.info(
            "[DialogueRunner] Dialogue complete | total_rounds=%d | total_cost=%.6f",
            self._num_rounds, total_cost,
        )
        logger.info(f"[DialogueRunner] ✓ Complete — {self._num_rounds} rounds | cost=${total_cost:.6f}")
        return transcript, a_reply, total_cost

    @property
    def agent_a_history(self) -> list[dict[str, str]]:
        """Full conversation history for Agent A (read-only view)."""
        return list(self._agent_a.history)

    @property
    def agent_b_history(self) -> list[dict[str, str]]:
        """Full conversation history for Agent B (read-only view)."""
        return list(self._agent_b.history)

    # ── Time Travel API ───────────────────────────────────────────────────────

    def to_checkpoint(self) -> dict[str, Any]:
        """Serialise the full pair runner state to a JSON-safe dict."""
        return {
            "runner_type": "pair",
            "num_rounds": self._num_rounds,
            "agent_a": self._agent_a.to_checkpoint(),
            "agent_b": self._agent_b.to_checkpoint(),
        }

    @classmethod
    def from_checkpoint(
        cls,
        router: Any,
        checkpoint: dict[str, Any],
    ) -> "DialogueRunner":
        """Reconstruct a DialogueRunner from a checkpoint dict."""
        runner: DialogueRunner = cls.__new__(cls)
        runner._router = router
        runner._num_rounds = int(checkpoint.get("num_rounds", 3))
        runner._agent_a = _AgentSession.from_checkpoint(checkpoint["agent_a"])
        runner._agent_b = _AgentSession.from_checkpoint(checkpoint["agent_b"])
        return runner

    @property
    def total_cost(self) -> float:
        """Accumulated cost across both agents for the full dialogue."""
        return self._agent_a.total_cost + self._agent_b.total_cost


# ─────────────────────────────────────────────────────────────────────────────
# GroupDialogueRunner — one host + N participants, all persistent sessions
# ─────────────────────────────────────────────────────────────────────────────

class GroupDialogueRunner:
    """
    Persistent group dialogue: one host agent orchestrates N participant agents.

    Every agent — host and all participants — has an independent ``_AgentSession``
    whose conversation history grows on every turn.  This gives each agent the
    same "open AI Studio chat tab" experience as the two-agent ``DialogueRunner``:

    Host's tab sees:
        [user: all initial drafts / payload]
        [model: host reply round 0]
        [user: formatted bundle of all participant replies round 1]
        [model: host reply round 1]
        ...

    Each participant's tab sees:
        [user: host reply round 0]
        [model: participant reply round 1]
        [user: host reply round 1]
        [model: participant reply round 2]
        ...

    Workbook configuration (no new columns required):
        Dialogue_Partner  = "AgentB|AgentC|AgentD"   ← pipe-separated → group mode
        Dialogue_Rounds   = 5                          ← number of full host→all→host cycles

    The node running the topology row IS the host.  Partners in Dialogue_Partner
    are the participants, loaded from agent_roster.csv or {name}.json cards.

    Time Travel:
        checkpoint = runner.to_checkpoint()        # dict — JSON-serialisable
        runner2    = GroupDialogueRunner.from_checkpoint(router, checkpoint)
        runner2.run(next_message)                  # resumes from exact round/history
    """

    # ── Separator used when combining participant replies for the host ─────────
    _SECTION_SEP: str = "\n\n" + "═" * 50 + "\n\n"

    def __init__(
        self,
        router: Any,
        host_model: str,
        host_system: str,
        host_temperature: float,
        host_label: str,
        participants: list[ParticipantConfig],
        num_rounds: int = 3,
        host_tools: str = "none",
    ) -> None:
        if not participants:
            raise ValueError("GroupDialogueRunner requires at least one participant.")

        self._router = router
        self._num_rounds = max(1, num_rounds)

        self._host = _AgentSession(
            label=host_label,
            model=host_model,
            system_prompt=host_system,
            temperature=host_temperature,
            tools_str=host_tools,
        )
        self._participants: list[_AgentSession] = [
            _AgentSession(
                label=p.label,
                model=p.model,
                system_prompt=p.system_prompt,
                temperature=p.temperature,
                tools_str=p.tools_str,
            )
            for p in participants
        ]

    # ── Public API ────────────────────────────────────────────────────────────

    def run(self, initial_message: str, stop_event: Any = None) -> tuple[str, str, float]:
        """
        Execute the full group dialogue and return the merged transcript.

        Flow per run():
            Round 0 — host opens on ``initial_message``:
                host.send(initial_message) → host_reply_0
            Rounds 1..N — for each round:
                for each participant p:
                    p.send(host_reply_prev) → p_reply
                combined = _combine_replies(all p_replies)
                host.send(combined)        → host_reply_round

        The final host reply is the natural synthesis / closing statement,
        suitable for writing to the declared artifact_path downstream.

        Args:
            initial_message: The seed content the host receives first.
                             For Gretchen: the fan-in block of all raw drafts.

        Returns:
            ``(transcript_str, final_turn, total_cost_usd)``
        """
        transcript_parts: list[str] = []
        p_labels = ", ".join(p.label for p in self._participants)

        logger.info(
            "[GroupDialogueRunner] Starting: host=%s | participants=[%s] | rounds=%d",
            self._host.label, p_labels, self._num_rounds,
        )
        logger.info(
            f"[GroupDialogueRunner] HOST={self._host.label} | "
            f"PARTICIPANTS=[{p_labels}] | rounds={self._num_rounds}"
        )

        # ── Round 0: host opens ───────────────────────────────────────────────
        logger.info(f"[GroupDialogueRunner] ── Round 0: {self._host.label} opening ──")
        try:
            host_reply = self._host.send(self._router, initial_message)
        except ManualInputRequired as e:
            e.checkpoint = self.to_checkpoint()
            raise
        transcript_parts.append(f"[{self._host.label} — Opening]\n{host_reply}")

        # ── Rounds 1..N: participants respond, host synthesises ───────────────
        for round_idx in range(1, self._num_rounds + 1):
            if stop_event is not None and stop_event.is_set():
                logger.info("[GroupDialogueRunner] --- Flow Stop Requested (cancelling between rounds) ---")
                break
                
            p_replies: list[tuple[str, str]] = []

            for participant in self._participants:
                logger.info(
                    f"[GroupDialogueRunner] ── Round {round_idx}: "
                    f"{participant.label} responding ──"
                )
                try:
                    p_reply = participant.send(self._router, host_reply)
                except ManualInputRequired as e:
                    e.checkpoint = self.to_checkpoint()
                    raise
                p_replies.append((participant.label, p_reply))
                transcript_parts.append(
                    f"[{participant.label} — Round {round_idx}]\n{p_reply}"
                )

            # Combine all participant replies into one host user-turn
            combined = self._combine_replies(p_replies)

            is_final = round_idx == self._num_rounds
            round_label = "Final Synthesis" if is_final else f"Round {round_idx}"
            logger.info(
                f"[GroupDialogueRunner] ── {round_label}: "
                f"{self._host.label} responding ──"
            )
            try:
                host_reply = self._host.send(self._router, combined)
            except ManualInputRequired as e:
                e.checkpoint = self.to_checkpoint()
                raise
            transcript_parts.append(
                f"[{self._host.label} — {round_label}]\n{host_reply}"
            )

        total_cost = self._host.total_cost + sum(
            p.total_cost for p in self._participants
        )
        transcript = "\n\n" + (
            "\n\n─────────────────────────────────────────\n\n".join(transcript_parts)
        )

        logger.info(
            "[GroupDialogueRunner] Complete | rounds=%d | participants=%d | total_cost=%.6f",
            self._num_rounds, len(self._participants), total_cost,
        )
        logger.info(
            f"[GroupDialogueRunner] ✓ Complete — {self._num_rounds} rounds | "
            f"{len(self._participants)} participants | cost=${total_cost:.6f}"
        )
        return transcript, host_reply, total_cost

    # ── Helpers ───────────────────────────────────────────────────────────────

    @staticmethod
    def _combine_replies(replies: list[tuple[str, str]]) -> str:
        """
        Format N participant replies into one combined message for the host.

        Each section is clearly labelled so the host can address each participant
        individually in its response.  This mirrors manually copy-pasting replies
        from multiple AI Studio tabs into a single message.
        """
        sections: list[str] = []
        for label, text in replies:
            header = f"══ {label} " + "═" * max(0, 46 - len(label))
            sections.append(f"{header}\n\n{text}")
        return GroupDialogueRunner._SECTION_SEP.join(sections)

    # ── Time Travel API ───────────────────────────────────────────────────────

    def to_checkpoint(self) -> dict[str, Any]:
        """
        Serialise the full runner state to a JSON-safe dict.

        Captures every agent's complete conversation history so the session
        can be restored, forked, or replayed at any round.

        Schema::

            {
              "runner_type": "group",
              "num_rounds": 5,
              "host": {_AgentSession checkpoint},
              "participants": [{_AgentSession checkpoint}, ...]
            }
        """
        return {
            "runner_type": "group",
            "num_rounds": self._num_rounds,
            "host": self._host.to_checkpoint(),
            "participants": [p.to_checkpoint() for p in self._participants],
        }

    @classmethod
    def from_checkpoint(
        cls,
        router: Any,
        checkpoint: dict[str, Any],
    ) -> "GroupDialogueRunner":
        """
        Reconstruct a ``GroupDialogueRunner`` from a checkpoint dict.

        The restored runner has every agent's full history intact — calling
        ``.run()`` on it continues the dialogue from exactly where it was
        saved, giving Time Travel the ability to drop agents back into their
        context windows at any prior round.

        Args:
            router:     Live ``UniversalRouter`` instance.
            checkpoint: Dict previously produced by ``to_checkpoint()``.

        Returns:
            Fully restored ``GroupDialogueRunner`` ready to continue.
        """
        runner: GroupDialogueRunner = cls.__new__(cls)
        runner._router = router
        runner._num_rounds = int(checkpoint.get("num_rounds", 3))
        runner._host = _AgentSession.from_checkpoint(checkpoint["host"])
        runner._participants = [
            _AgentSession.from_checkpoint(p) for p in checkpoint["participants"]
        ]
        return runner

    # ── Properties ────────────────────────────────────────────────────────────

    @property
    def host_history(self) -> list[dict[str, str]]:
        """Full conversation history for the host agent (read-only view)."""
        return list(self._host.history)

    @property
    def participant_histories(self) -> dict[str, list[dict[str, str]]]:
        """Full conversation histories for all participants, keyed by label."""
        return {p.label: list(p.history) for p in self._participants}

    @property
    def total_cost(self) -> float:
        """Accumulated cost across all agents for the full session."""
        return self._host.total_cost + sum(p.total_cost for p in self._participants)
