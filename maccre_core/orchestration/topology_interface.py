# ┌─────────────────────────────────────────────────────────────────────────────┐
# │  MACCREv2 ENGINEERING DOCTRINE                             Law Rev: 19.0   │
# ├─────────────────────────────────────────────────────────────────────────────┤
# │  VI.  ABSTRACTION All I/O behind abc.ABC before any concrete driver.       │
# └─────────────────────────────────────────────────────────────────────────────┘
"""
maccre_core/orchestration/topology_interface.py
===============================================
Phase 0C — Strangler Fig ABC for the Topology Provider.

Defines the ``TopologyProvider`` interface contract that ``TopologyEngine``
(CSV-based) implements today.  Future drivers could read from SQLite,
YAML, or a live API without touching consumer code.
"""
from __future__ import annotations

import abc
from typing import Any


class TopologyProvider(abc.ABC):
    """Abstract interface for topology data access.

    All orchestration components (SwarmWorker, LocalMessageBroker, FlowRunner)
    MUST type-hint against this ABC, never against a concrete parser.
    """

    @abc.abstractmethod
    def get_topology(self) -> dict[str, Any]:
        """Return the full topology as a dict of ``{node_id: node_config}``.

        The returned dict maps each ``Node_ID`` string to a config dict with keys:
        ``agent_name``, ``system_instruction``, ``next_node``, ``temperature``,
        ``output_format``, ``wait_for``, ``fallback_node``, ``max_retries``,
        ``payload_path``, ``is_end_node``, ``timeout_sec``, ``dialogue_partner``,
        ``dialogue_rounds``, ``model_override``, ``tools_allowed``.
        """

    @abc.abstractmethod
    def get_node_config(self, node_id: str) -> dict[str, Any]:
        """Return the configuration dict for a single topology node.

        Args:
            node_id: The ``Node_ID`` to look up.

        Returns:
            Config dict for the node, or a default dict with ``next_node='END'``
            if the node is not found.
        """

    @abc.abstractmethod
    def flush_cache(self) -> None:
        """Invalidate any cached topology data, forcing a re-read on next access."""

    @abc.abstractmethod
    def merge_config_overlay(self, node_id: str, overlay: dict[str, Any]) -> None:
        """Merge a runtime config overlay into the cached topology for a node.

        Args:
            node_id: The ``Node_ID`` to overlay.
            overlay: Dict of config fields to merge into the node's config.
        """

    @abc.abstractmethod
    def validate(self) -> Any:
        """Validate the topology for structural errors.

        Returns:
            A ValidationReport (or equivalent) with ``is_ok()`` and ``render_table()``.
        """
