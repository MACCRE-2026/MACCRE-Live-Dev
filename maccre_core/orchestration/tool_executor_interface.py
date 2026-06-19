# ┌─────────────────────────────────────────────────────────────────────────────┐
# │  MACCREv2 ENGINEERING DOCTRINE                             Law Rev: 19.0   │
# ├─────────────────────────────────────────────────────────────────────────────┤
# │  VI.  ABSTRACTION All I/O behind abc.ABC before any concrete driver.       │
# └─────────────────────────────────────────────────────────────────────────────┘
"""
maccre_core/orchestration/tool_executor_interface.py
====================================================
Phase 0D — Strangler Fig ABC for the Tool Executor.

Defines the ``ToolDispatcher`` interface contract that ``ToolExecutor``
(TOOL_DISPATCHER dict-based) implements today.
"""
from __future__ import annotations

import abc


class ToolDispatcher(abc.ABC):
    """Abstract interface for tool call parsing and dispatch.

    The swarm worker and TUI interactive shell both consume this interface
    to parse model responses and execute tool calls.
    """

    @abc.abstractmethod
    def run(
        self,
        response_text: str,
        current_prompt: str,
        session_id: str = "",
        project_id: str = "",
        agent_id: str = "",
        is_final_turn: bool = True,
    ) -> tuple[bool, str]:
        """Parse a model response for a tool call and dispatch it if found.

        Args:
            response_text: Raw text returned by the model.
            current_prompt: The current rolling prompt ledger.
            session_id: Active session identifier.
            project_id: Active project identifier.
            agent_id: Calling agent identifier.
            is_final_turn: Whether this is the last tool turn.

        Returns:
            (did_fire, updated_prompt): True if a tool was found and executed,
            plus the updated prompt ledger.
        """
