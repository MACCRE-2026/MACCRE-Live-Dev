# ┌─────────────────────────────────────────────────────────────────────────────┐
# │  MACCREv2 ENGINEERING DOCTRINE                             Law Rev: 19.0   │
# ├─────────────────────────────────────────────────────────────────────────────┤
# │  I.   TYPING      All signatures: explicit Python 3.11+ type hints.        │
# │  II.  LINTING     Zero unused imports. No wildcards. 120-char line max.    │
# │  III. PATHS       Never hardcode absolute paths. Use get_maccre_root().     │
# │  IV.  DATACENTER  5-Tier Data Sovereignty.                                 │
# │  VI.  ABSTRACTION All I/O behind abc.ABC before any concrete driver.       │
# │  VII. TEARDOWN    try/finally on all handles (omni clean compliance).      │
# └─────────────────────────────────────────────────────────────────────────────┘
"""
maccre_core/flow_dict.py
========================
Flow Dictionary — session-specific agent configuration for Flow sessions.

Extends the Chat Studio `.dict` pattern to Flow sessions with additional
metadata for tethering, flow lines, and node configs.

Format:
  {
    "_flow_meta": {
      "session_name": "...",
      "created_at": "...",
      "tethers": { ... },
      "flow_lines": { ... },
      "node_configs": { ... }
    },
    "AgentName1": { agent_profile },
    "AgentName2": { agent_profile }
  }
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# ── Default agent profile template ───────────────────────────────────────────

_DEFAULT_AI_OPTIONS: dict[str, Any] = {
    "thinking_level": "high",
    "grounding_google_search": False,
    "grounding_brave_search": False,
    "grounding_local_memory": False,
    "finops_ledger": False,
    "grounding_google_maps": False,
    "url_context": False,
    "exclusionary_search": False,
    "funnel_search": False,
    "code_execution": False,
    "structured_outputs": False,
    "function_calling": False,
    "media_resolution": "default",
    "stop_sequence": "",
    "output_length": 65536,
    "top_p": 0.95,
}


def make_default_agent_profile(agent_name: str) -> dict[str, Any]:
    """Create a default agent profile entry for the flow dict."""
    return {
        "agent_name": agent_name,
        "model": "",
        "system_prompt": "",
        "temperature": 1.0,
        "tools_allowed": "",
        "ai_studio_options": dict(_DEFAULT_AI_OPTIONS),
    }


# ── Flow Dict Buffer ─────────────────────────────────────────────────────────

class FlowDictBuffer:
    """In-memory buffer for building a Flow session dictionary.

    Mirrors Chat Studio's ``local_profiles`` pattern but adds ``_flow_meta``
    for tethering, flow lines, and node configs.
    """

    def __init__(self, session_name: str = "") -> None:
        self._session_name = session_name
        self._agents: dict[str, dict[str, Any]] = {}
        self._tethers: dict[str, dict[str, Any]] = {}
        self._flow_lines: dict[str, dict[str, Any]] = {}
        self._node_configs: dict[str, dict[str, Any]] = {}

    # ── Agent Profiles ────────────────────────────────────────────────────

    def set_agent_profile(self, agent_name: str, profile: dict[str, Any]) -> None:
        """Set or update an agent's override profile."""
        self._agents[agent_name] = profile

    def get_agent_profile(self, agent_name: str) -> dict[str, Any] | None:
        """Get an agent's override profile, or None if not set."""
        return self._agents.get(agent_name)

    def ensure_agent(self, agent_name: str) -> dict[str, Any]:
        """Ensure an agent entry exists, creating a default if needed."""
        if agent_name not in self._agents:
            self._agents[agent_name] = make_default_agent_profile(agent_name)
        return self._agents[agent_name]

    def remove_agent(self, agent_name: str) -> None:
        """Remove an agent profile from the buffer."""
        self._agents.pop(agent_name, None)

    # ── Tethers ──────────────────────────────────────────────────────────

    def set_tether(
        self,
        tether_id: str,
        source: str,
        sink: str,
        targets: list[str] | None = None,
        parent_tether: str = "",
    ) -> None:
        """Register a tether pair (SCATTER↔sink binding)."""
        self._tethers[tether_id] = {
            "source": source,
            "sink": sink,
            "targets": targets or [],
            "parent_tether": parent_tether,
        }

    def get_tether(self, tether_id: str) -> dict[str, Any] | None:
        """Get tether config by ID."""
        return self._tethers.get(tether_id)

    # ── Flow Lines ───────────────────────────────────────────────────────

    def set_flow_line(
        self,
        flow_line_id: str,
        agent: str,
        parent: str,
    ) -> None:
        """Register a flow line created by CTRL_SCATTER."""
        self._flow_lines[flow_line_id] = {
            "agent": agent,
            "parent": parent,
        }

    # ── Node Configs ─────────────────────────────────────────────────────

    def set_node_config(self, node_id: str, config: dict[str, Any]) -> None:
        """Set node-specific configuration (scatter_mode, merge_mode, etc.)."""
        self._node_configs[node_id] = config

    def get_node_config(self, node_id: str) -> dict[str, Any] | None:
        """Get node-specific configuration."""
        return self._node_configs.get(node_id)

    # ── Serialization ────────────────────────────────────────────────────

    def to_dict(self) -> dict[str, Any]:
        """Serialize the entire flow dict buffer to a JSON-compatible dict."""
        result: dict[str, Any] = {
            "_flow_meta": {
                "session_name": self._session_name,
                "created_at": datetime.now(tz=timezone.utc).isoformat(),
                "tethers": dict(self._tethers),
                "flow_lines": dict(self._flow_lines),
                "node_configs": dict(self._node_configs),
            },
        }
        # Agent profiles are top-level keys (same as Chat Studio format)
        for agent_name, profile in self._agents.items():
            result[agent_name] = profile
        return result

    def to_json(self, indent: int = 4) -> str:
        """Serialize to a JSON string."""
        return json.dumps(self.to_dict(), indent=indent, ensure_ascii=False)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> FlowDictBuffer:
        """Deserialize from a dict (e.g., loaded from a .dict file)."""
        meta = data.get("_flow_meta", {})
        buf = cls(session_name=meta.get("session_name", ""))
        buf._tethers = dict(meta.get("tethers", {}))
        buf._flow_lines = dict(meta.get("flow_lines", {}))
        buf._node_configs = dict(meta.get("node_configs", {}))

        # All non-meta keys are agent profiles
        for key, value in data.items():
            if key != "_flow_meta" and isinstance(value, dict):
                buf._agents[key] = value
        return buf

    @classmethod
    def from_file(cls, path: str | Path) -> FlowDictBuffer:
        """Load a FlowDictBuffer from a .dict file."""
        p = Path(path)
        if not p.exists():
            logger.warning("Flow dict file not found: %s", p)
            return cls()
        try:
            with open(p, "r", encoding="utf-8") as f:
                data = json.load(f)
            return cls.from_dict(data)
        except Exception:
            logger.exception("Failed to load flow dict from %s", p)
            return cls()

    def write_to_file(self, path: str | Path) -> None:
        """Write the flow dict to a .dict file."""
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        with open(p, "w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, indent=4, ensure_ascii=False)
        logger.info("Flow dict written to %s (%d agents)", p, len(self._agents))

    # ── Properties ───────────────────────────────────────────────────────

    @property
    def session_name(self) -> str:
        """Return the session name."""
        return self._session_name

    @session_name.setter
    def session_name(self, name: str) -> None:
        """Set the session name."""
        self._session_name = name

    @property
    def agent_names(self) -> list[str]:
        """Return all agent names in the buffer."""
        return list(self._agents.keys())

    @property
    def is_empty(self) -> bool:
        """True if no agents or node configs have been added."""
        return not self._agents and not self._node_configs
