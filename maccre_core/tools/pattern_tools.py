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
maccre_core/tools/pattern_tools.py
====================================
Pattern Library MCP Tools — 5 tools that expose the pattern library to
Antigravity as direct MCP tool calls.

These tools shift Antigravity from operator to orchestrator: instead of
running one command at a time and waiting for approval, Antigravity can
dispatch a swarm pattern and receive a synthesized BriefPacket when the
work is done.

Tools:
    submit_pattern(pattern_name, payload, project_id, cost_limit_usd) → job_id
    poll_human_gate(job_id, silo_project) → BriefPacket JSON | status string
    resolve_gate(job_id, decision, silo_project) → "acknowledged" | error
    list_patterns() → JSON list of pattern metadata
    get_session_brief(project_id) → BriefPacket JSON (synchronous fast path)
"""
from __future__ import annotations

import json
import os
from typing import Any


def submit_pattern(
    pattern_name: str,
    payload: str,
    project_id: str = "",
    cost_limit_usd: float = 5.0,
) -> str:
    """Materialize a named pattern and inject it into an isolated swarm silo.

    The pattern runs asynchronously. Use poll_human_gate(job_id) to check
    for completion and retrieve the BriefPacket.

    Args:
        pattern_name: One of the registered pattern names (see list_patterns()).
        payload: The input payload for the pattern (markdown text).
        project_id: Active project silo name. Defaults to MACCRE_ACTIVE_PROJECT env var.
        cost_limit_usd: Abort if estimated cost exceeds this limit.

    Returns:
        JSON string with job_id and metadata, or error description.
    """
    from maccre_core.patterns.pattern_executor import get_executor  # noqa: PLC0415
    pid = project_id or os.environ.get("MACCRE_ACTIVE_PROJECT", "GLOBAL")
    executor = get_executor(pid)
    result = executor.submit(pattern_name, payload, cost_limit_usd)
    return json.dumps(result, indent=2, ensure_ascii=False)


def poll_human_gate(job_id: str, silo_project: str = "") -> str:
    """Check whether the HUMAN_GATE has fired for a pattern job.

    Args:
        job_id: The job_id returned by submit_pattern().
        silo_project: Silo project name (from submit_pattern result). Optional — 
                      executor will scan DATACENTER silos if not provided.

    Returns:
        One of:
          "still_running" — job is active, gate not yet reached
          "not_found"     — job_id doesn't exist in any silo
          BriefPacket JSON string — gate fired, decision surface ready for review
    """
    from maccre_core.patterns.pattern_executor import get_executor  # noqa: PLC0415
    executor = get_executor()
    result = executor.poll_gate(job_id, silo_project)
    if isinstance(result, str):
        return result
    # BriefPacket — return formatted markdown + raw JSON
    return result.format_for_display() + "\n\n---\n\n```json\n" + result.to_json() + "\n```"


def resolve_gate(job_id: str, decision: str, silo_project: str = "") -> str:
    """Inject a decision into a HUMAN_GATE to continue the swarm.

    Args:
        job_id: The paused job ID.
        decision: Decision string — should match one of BriefPacket.decision_surface.next_action_options.
        silo_project: Silo project name (optional).

    Returns:
        "acknowledged" on success, or error description.
    """
    from maccre_core.patterns.pattern_executor import get_executor  # noqa: PLC0415
    executor = get_executor()
    return executor.resolve_gate(job_id, decision, silo_project)


def list_patterns() -> str:
    """List all registered topology patterns with metadata.

    Returns:
        JSON array of pattern metadata dicts.
    """
    from maccre_core.patterns import list_patterns as _list  # noqa: PLC0415
    patterns = _list()
    return json.dumps(patterns, indent=2, ensure_ascii=False)


def get_session_brief(project_id: str = "") -> str:
    """Build a session brief synchronously without queuing a swarm.

    Fast path for conversation startup re-contextualization.
    Reads git log, cost data, and sentinel health directly from local state.
    Costs effectively $0 (no model calls).

    Args:
        project_id: Active project silo name.

    Returns:
        Formatted markdown session brief + raw BriefPacket JSON.
    """
    from maccre_core.patterns.pattern_executor import get_executor  # noqa: PLC0415
    pid = project_id or os.environ.get("MACCRE_ACTIVE_PROJECT", "GLOBAL")
    executor = get_executor(pid)
    brief = executor.get_session_brief()
    return brief.format_for_display() + "\n\n---\n\n```json\n" + brief.to_json() + "\n```"


# ── Tool Registry Integration ─────────────────────────────────────────────────
# These tools are registered in tool_registry.py under the PATTERN_TOOLS group.
# MCP exposure happens via maccre_mcp.py.

PATTERN_TOOL_DEFINITIONS: list[dict[str, Any]] = [
    {
        "name": "submit_pattern",
        "description": (
            "Materialize and fire a named swarm pattern into an isolated silo. "
            "Returns job_id. Use poll_human_gate(job_id) to retrieve the BriefPacket. "
            "Available patterns: simulation_swarm, research_sweep, session_brief, "
            "checkpoint_sweep, fault_investigation, monitor_watch, code_review."
        ),
        "function": submit_pattern,
        "parameters": {
            "type": "object",
            "properties": {
                "pattern_name": {"type": "string", "description": "Pattern name from list_patterns()"},
                "payload": {"type": "string", "description": "Input payload as markdown text"},
                "project_id": {"type": "string", "description": "Active project silo (optional)"},
                "cost_limit_usd": {"type": "number", "description": "Abort if estimated cost exceeds this"},
            },
            "required": ["pattern_name", "payload"],
        },
    },
    {
        "name": "poll_human_gate",
        "description": (
            "Check if a HUMAN_GATE has fired for a pattern job. "
            "Returns 'still_running', 'not_found', or a formatted BriefPacket."
        ),
        "function": poll_human_gate,
        "parameters": {
            "type": "object",
            "properties": {
                "job_id": {"type": "string", "description": "job_id from submit_pattern()"},
                "silo_project": {"type": "string", "description": "Silo project name (optional)"},
            },
            "required": ["job_id"],
        },
    },
    {
        "name": "resolve_gate",
        "description": (
            "Inject a decision into a paused HUMAN_GATE to continue the swarm. "
            "Decision should match one of the next_action_options in the BriefPacket."
        ),
        "function": resolve_gate,
        "parameters": {
            "type": "object",
            "properties": {
                "job_id": {"type": "string"},
                "decision": {"type": "string", "description": "e.g. 'approve_path_A'"},
                "silo_project": {"type": "string", "description": "optional"},
            },
            "required": ["job_id", "decision"],
        },
    },
    {
        "name": "list_patterns",
        "description": "List all registered swarm topology patterns with metadata and cost estimates.",
        "function": list_patterns,
        "parameters": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "get_session_brief",
        "description": (
            "Synchronously build a session brief (git log + cost + sentinel health). "
            "Zero cost fast path. Use at the start of each session to re-contextualize."
        ),
        "function": get_session_brief,
        "parameters": {
            "type": "object",
            "properties": {
                "project_id": {"type": "string", "description": "Active project silo (optional)"}
            },
            "required": [],
        },
    },
]

__all__ = [
    "submit_pattern",
    "poll_human_gate",
    "resolve_gate",
    "list_patterns",
    "get_session_brief",
    "PATTERN_TOOL_DEFINITIONS",
]
