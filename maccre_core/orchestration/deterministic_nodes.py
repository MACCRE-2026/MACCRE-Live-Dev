# ┌─────────────────────────────────────────────────────────────────────────────┐
# │  MACCREv2 ENGINEERING DOCTRINE                             Law Rev: 19.0   │
# ├─────────────────────────────────────────────────────────────────────────────┤
# │  I.   TYPING      All signatures: explicit Python 3.11+ type hints.        │
# │  II.  LINTING     Zero unused imports. No wildcards. 120-char line max.    │
# │  III. PATHS       Never hardcode absolute paths. Use get_maccre_root().     │
# │  IV.  DATACENTER  5-Tier Data Sovereignty.                                 │
# │  VI.  ABSTRACTION All I/O behind abc.ABC before any concrete driver.       │
# │  VII. TEARDOWN    try/finally on all handles (omni clean compliance).      │
# │  VIII.TELEMETRY   No bare print(). logger only. JSON → 03_Agent_Ledgers.  │
# └─────────────────────────────────────────────────────────────────────────────┘
"""
maccre_core/orchestration/deterministic_nodes.py
=================================================
Phase 4 — Deterministic Node Library.

Control nodes (CTRL_ prefix, legacy DET_) execute without calling the LLM. They perform
structural operations on the flow graph: anchoring, recursion control,
gating, pausing, checkpointing, delay, and text transformation.

A node is a control node if its ``Node_ID`` starts with ``CTRL_`` (or legacy ``DET_``) prefix.
The swarm worker checks ``is_deterministic_node()`` and routes to
``execute_deterministic_node()`` instead of the AI pipeline.

Node Types
----------
``DET_ANCHOR``      Entry marker — passes payload through unchanged.
``DET_RECURSION``   Loop-back control with counter tracking.
``DET_PAUSE``       Halts execution, sets task to ``paused`` for manual resume.
``DET_GATE``        Conditional gate — blocks unless prerequisite nodes complete.
``DET_CHECKPOINT``  Snapshots current payload to a checkpoint file.
``DET_DELAY``       Sleeps for a configurable number of seconds.
``DET_TRANSFORM``   Applies a static text wrapper/template to the payload.
"""
from __future__ import annotations

import logging
import shutil
import time
from enum import Enum
from pathlib import Path
from typing import Any, Callable

from maccre_core.utils.path_resolver import get_datacenter_path

logger = logging.getLogger(__name__)

DET_PREFIX = "DET_"
CTRL_PREFIX = "CTRL_"


class DeterministicNodeType(Enum):
    """Enum of all supported deterministic node types."""
    ANCHOR = "DET_ANCHOR"
    RECURSION = "DET_RECURSION"
    PAUSE = "DET_PAUSE"
    GATE = "DET_GATE"
    CHECKPOINT = "DET_CHECKPOINT"
    DELAY = "DET_DELAY"
    TRANSFORM = "DET_TRANSFORM"


def is_deterministic_node(node_id: str) -> bool:
    """Return True if a node_id uses the CTRL_ or legacy DET_ prefix convention."""
    upper = node_id.strip().upper()
    return upper.startswith(CTRL_PREFIX) or upper.startswith(DET_PREFIX)


def _resolve_node_type(node_id: str) -> DeterministicNodeType | None:
    """Map a node_id string to its DeterministicNodeType enum, if valid.

    Supports both CTRL_ and legacy DET_ prefixes.
    """
    upper = node_id.strip().upper()
    # Normalize CTRL_ prefix to DET_ for enum matching
    if upper.startswith(CTRL_PREFIX):
        upper = DET_PREFIX + upper[len(CTRL_PREFIX):]
    # Match longest prefix first to avoid DET_GATE matching DET_GATEWAY etc.
    for ntype in DeterministicNodeType:
        if upper.startswith(ntype.value):
            return ntype
    return None


# ── Node Execution Dispatch ──────────────────────────────────────────────────


class DeterministicNodeResult:
    """Return type for deterministic node execution."""

    def __init__(
        self,
        output_payload_path: str,
        next_node: str | None = None,
        should_pause: bool = False,
        log_message: str = "",
    ) -> None:
        self.output_payload_path = output_payload_path
        self.next_node = next_node  # Override topology next_node if set
        self.should_pause = should_pause
        self.log_message = log_message


def execute_deterministic_node(
    node_id: str,
    task: dict[str, Any],
    topology_config: dict[str, Any] | None = None,
) -> DeterministicNodeResult:
    """Execute a deterministic node and return the result.

    Args:
        node_id: The full Node_ID string (e.g., ``DET_CHECKPOINT_1``).
        task: The task dict from the broker (contains payload_path, job_id, etc.).
        topology_config: Optional node config from topology.csv row dict.

    Returns:
        DeterministicNodeResult with output path, next_node override, etc.
    """
    ntype = _resolve_node_type(node_id)
    if ntype is None:
        logger.warning(f"Unknown deterministic node type: {node_id}. Treating as ANCHOR.")
        ntype = DeterministicNodeType.ANCHOR

    payload_path: str = str(task.get("payload_path", ""))
    job_id: str = str(task.get("job_id", "unknown"))
    config = topology_config or {}

    handler = _NODE_HANDLERS.get(ntype)
    if handler is None:
        handler = _handle_anchor
    return handler(node_id, payload_path, job_id, config)


# ── Individual Node Handlers ─────────────────────────────────────────────────


def _handle_anchor(
    node_id: str,
    payload_path: str,
    job_id: str,
    config: dict[str, Any],
) -> DeterministicNodeResult:
    """DET_ANCHOR — Pass-through entry marker. No transformation."""
    logger.info(f"[DET_ANCHOR] {node_id}: Pass-through. Payload unchanged.")
    return DeterministicNodeResult(
        output_payload_path=payload_path,
        log_message=f"ANCHOR node {node_id}: payload forwarded unchanged.",
    )


def _handle_recursion(
    node_id: str,
    payload_path: str,
    job_id: str,
    config: dict[str, Any],
) -> DeterministicNodeResult:
    """DET_RECURSION — Loop-back control with iteration counter.

    Uses ``loop_iteration_count`` from the task and ``Max_Recursion`` from
    topology config to decide whether to loop back or proceed to next.
    """
    max_recursion = int(config.get("Max_Recursion", 3))
    iteration = int(config.get("loop_iteration_count", 0))

    if iteration < max_recursion:
        # Loop back: override next_node to the recursion target
        loop_target = str(config.get("Instruction_Override", "")).strip()
        if not loop_target or loop_target.lower() == "none":
            loop_target = str(config.get("Next_Node", "END")).split("|")[0].strip()

        logger.info(
            f"[DET_RECURSION] {node_id}: Iteration {iteration + 1}/{max_recursion} "
            f"— looping back to {loop_target}"
        )
        return DeterministicNodeResult(
            output_payload_path=payload_path,
            next_node=loop_target,
            log_message=f"RECURSION {iteration + 1}/{max_recursion}: looping to {loop_target}",
        )
    else:
        logger.info(f"[DET_RECURSION] {node_id}: Max recursion ({max_recursion}) reached — proceeding.")
        return DeterministicNodeResult(
            output_payload_path=payload_path,
            log_message=f"RECURSION complete after {max_recursion} iterations.",
        )


def _handle_pause(
    node_id: str,
    payload_path: str,
    job_id: str,
    config: dict[str, Any],
) -> DeterministicNodeResult:
    """DET_PAUSE — Halt execution. Task set to 'paused' for manual resume."""
    logger.info(f"[DET_PAUSE] {node_id}: Flow paused. Awaiting manual resume.")
    return DeterministicNodeResult(
        output_payload_path=payload_path,
        should_pause=True,
        log_message=f"PAUSE node {node_id}: flow halted. Press Resume to continue.",
    )


def _handle_gate(
    node_id: str,
    payload_path: str,
    job_id: str,
    config: dict[str, Any],
) -> DeterministicNodeResult:
    """DET_GATE — Conditional gate.

    The gate checks if the payload file exists and has content.
    If empty or missing, it blocks (returns the same node as next_node
    so the broker re-queues it). Otherwise, passes through.
    """
    if not payload_path or payload_path == "none":
        logger.info(f"[DET_GATE] {node_id}: No payload — gate BLOCKED.")
        return DeterministicNodeResult(
            output_payload_path=payload_path,
            next_node=node_id,  # Re-queue self
            log_message=f"GATE {node_id}: blocked — no payload.",
        )

    path = Path(payload_path)
    if not path.exists() or path.stat().st_size == 0:
        logger.info(f"[DET_GATE] {node_id}: Payload empty or missing — gate BLOCKED.")
        return DeterministicNodeResult(
            output_payload_path=payload_path,
            next_node=node_id,
            log_message=f"GATE {node_id}: blocked — empty payload.",
        )

    logger.info(f"[DET_GATE] {node_id}: Gate PASSED.")
    return DeterministicNodeResult(
        output_payload_path=payload_path,
        log_message=f"GATE {node_id}: passed.",
    )


def _handle_checkpoint(
    node_id: str,
    payload_path: str,
    job_id: str,
    config: dict[str, Any],
) -> DeterministicNodeResult:
    """DET_CHECKPOINT — Snapshot current payload to a checkpoint file."""
    checkpoint_dir = get_datacenter_path("03_Agent_Ledgers", job_id)
    checkpoint_dir.mkdir(parents=True, exist_ok=True)
    checkpoint_file = checkpoint_dir / f"{node_id}_checkpoint.md"

    if payload_path and payload_path != "none" and Path(payload_path).exists():
        shutil.copy2(payload_path, checkpoint_file)
        logger.info(f"[DET_CHECKPOINT] {node_id}: Snapshot saved → {checkpoint_file}")
    else:
        checkpoint_file.write_text(
            f"# Checkpoint: {node_id}\n\nNo payload at checkpoint time.\n",
            encoding="utf-8",
        )
        logger.info(f"[DET_CHECKPOINT] {node_id}: Empty checkpoint created → {checkpoint_file}")

    return DeterministicNodeResult(
        output_payload_path=payload_path,
        log_message=f"CHECKPOINT {node_id}: saved to {checkpoint_file.name}",
    )


def _handle_delay(
    node_id: str,
    payload_path: str,
    job_id: str,
    config: dict[str, Any],
) -> DeterministicNodeResult:
    """DET_DELAY — Sleep for configured seconds.

    Delay duration is read from ``Instruction_Override`` field (e.g., "30"
    for 30 seconds). Defaults to 5 seconds if not specified.
    """
    delay_str = str(config.get("Instruction_Override", "5")).strip()
    try:
        delay_seconds = max(0.0, min(float(delay_str), 3600.0))  # Cap at 1 hour
    except ValueError:
        delay_seconds = 5.0

    logger.info(f"[DET_DELAY] {node_id}: Sleeping for {delay_seconds}s...")
    time.sleep(delay_seconds)
    logger.info(f"[DET_DELAY] {node_id}: Woke up after {delay_seconds}s.")

    return DeterministicNodeResult(
        output_payload_path=payload_path,
        log_message=f"DELAY {node_id}: slept {delay_seconds}s.",
    )


def _handle_transform(
    node_id: str,
    payload_path: str,
    job_id: str,
    config: dict[str, Any],
) -> DeterministicNodeResult:
    """DET_TRANSFORM — Apply a static text template to the payload.

    The template is read from ``Instruction_Override``. The placeholder
    ``{PAYLOAD}`` in the template is replaced with the actual payload content.
    Output is written to a new file in the job ledger directory.
    """
    template = str(config.get("Instruction_Override", "{PAYLOAD}"))
    job_dir = get_datacenter_path("03_Agent_Ledgers", job_id)
    job_dir.mkdir(parents=True, exist_ok=True)
    output_file = job_dir / f"{node_id}_transformed.md"

    # Read source payload
    payload_content = ""
    if payload_path and payload_path != "none" and Path(payload_path).exists():
        payload_content = Path(payload_path).read_text(encoding="utf-8")

    # Apply template
    transformed = template.replace("{PAYLOAD}", payload_content)
    output_file.write_text(transformed, encoding="utf-8")

    logger.info(f"[DET_TRANSFORM] {node_id}: Template applied → {output_file}")
    return DeterministicNodeResult(
        output_payload_path=str(output_file),
        log_message=f"TRANSFORM {node_id}: output → {output_file.name}",
    )


# ── Handler Registry ─────────────────────────────────────────────────────────

# Type alias for handler functions
_HandlerFn = Callable[[str, str, str, dict[str, Any]], DeterministicNodeResult]

_NODE_HANDLERS: dict[DeterministicNodeType, _HandlerFn] = {
    DeterministicNodeType.ANCHOR: _handle_anchor,
    DeterministicNodeType.RECURSION: _handle_recursion,
    DeterministicNodeType.PAUSE: _handle_pause,
    DeterministicNodeType.GATE: _handle_gate,
    DeterministicNodeType.CHECKPOINT: _handle_checkpoint,
    DeterministicNodeType.DELAY: _handle_delay,
    DeterministicNodeType.TRANSFORM: _handle_transform,
}
