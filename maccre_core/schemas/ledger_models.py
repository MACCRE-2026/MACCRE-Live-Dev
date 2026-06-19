from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Any, List, Optional

@dataclass
class FlowChatEntry:
    """A clean, conversational entry in the FlowChat Ledger."""
    job_id: str
    role: str  # "user" or "model" or "system"
    agent_name: str
    content: str
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_json(self) -> str:
        return json.dumps(asdict(self))

@dataclass
class FlowSystemEntry:
    """The raw compute exhaust and inner monologue for a specific job."""
    job_id: str
    agent_name: str
    model_id: str
    system_prompt: str
    scratchpad_thought: str
    tool_calls: List[dict[str, Any]] = field(default_factory=list)
    tool_results: List[dict[str, Any]] = field(default_factory=list)
    input_tokens: int = 0
    output_tokens: int = 0
    duration_ms: int = 0
    cost: float = 0.0
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_json(self) -> str:
        return json.dumps(asdict(self))

@dataclass
class FlowSessionLog:
    """The master wrapper for a flow execution session."""
    session_id: str
    project_id: str
    flow_name: str
    start_time: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    end_time: Optional[str] = None
    chat_ledger: List[FlowChatEntry] = field(default_factory=list)
    system_ledger: List[FlowSystemEntry] = field(default_factory=list)

    def export_chat_json(self) -> str:
        return json.dumps([asdict(c) for c in self.chat_ledger], indent=2)

    def export_system_json(self) -> str:
        return json.dumps([asdict(s) for s in self.system_ledger], indent=2)
