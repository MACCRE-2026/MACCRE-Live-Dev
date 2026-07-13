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
``CTRL_ANCHOR``      Entry marker — passes payload through unchanged.
``CTRL_RECURSION``   Loop-back control with counter tracking.
``CTRL_PAUSE``       Halts execution, sets task to ``paused`` for manual resume.
``CTRL_GATE``        Conditional gate — blocks unless prerequisite nodes complete.
``CTRL_CHECKPOINT``  Snapshots current payload to a checkpoint file.
``CTRL_DELAY``       Sleeps for a configurable number of seconds.
``CTRL_TRANSFORM``   Applies a static text wrapper/template to the payload.
``CTRL_SCATTER``     Fan-out — distributes payload to multiple downstream nodes.
``CTRL_MERGE``       Merges multiple upstream payloads into a single document.
``CTRL_CONCAT``      Flat concatenation of predecessor payloads.
``CTRL_BRANCH``      Keyword-based conditional routing to downstream nodes.
``CTRL_FILTER``      Applies filter rules (strip sections, truncate, regex) to payload.
``CTRL_CLEANUP``     Deletes temporary files matching glob patterns.
``CTRL_CONDITIONAL_ROUTE``  4-vector fallback routing: structured → keyword → score → fuzzy.
"""
from __future__ import annotations

import glob
import json
import logging
import re
import shutil
import time
from enum import Enum
from pathlib import Path
from typing import Any, Callable

from maccre_core.utils.path_resolver import get_datacenter_path

logger = logging.getLogger(__name__)

CTRL_PREFIX = "CTRL_"
DET_PREFIX = "DET_"  # Legacy alias — kept for backward compat in saved topologies


class DeterministicNodeType(Enum):
    """Enum of all supported deterministic node types."""
    ANCHOR = "CTRL_ANCHOR"
    RECURSION = "CTRL_RECURSION"
    PAUSE = "CTRL_PAUSE"
    GATE = "CTRL_GATE"
    CHECKPOINT = "CTRL_CHECKPOINT"
    DELAY = "CTRL_DELAY"
    TRANSFORM = "CTRL_TRANSFORM"
    SCATTER = "CTRL_SCATTER"
    MERGE = "CTRL_MERGE"
    CONCAT = "CTRL_CONCAT"
    BRANCH = "CTRL_BRANCH"
    FILTER = "CTRL_FILTER"
    CLEANUP = "CTRL_CLEANUP"
    CONDITIONAL_ROUTE = "CTRL_CONDITIONAL_ROUTE"


def is_deterministic_node(node_id: str) -> bool:
    """Return True if a node_id uses the CTRL_ or legacy DET_ prefix convention."""
    upper = node_id.strip().upper()
    return upper.startswith(CTRL_PREFIX) or upper.startswith(DET_PREFIX)


def _resolve_node_type(node_id: str) -> DeterministicNodeType | None:
    """Map a node_id string to its DeterministicNodeType enum, if valid.

    Supports both CTRL_ and legacy DET_ prefixes.
    """
    upper = node_id.strip().upper()
    # Normalize legacy DET_ prefix to CTRL_ for enum matching
    if upper.startswith(DET_PREFIX):
        upper = CTRL_PREFIX + upper[len(DET_PREFIX):]
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
        next_nodes: list[str] | None = None,
        should_pause: bool = False,
        log_message: str = "",
        payload_artifact: str = "",
    ) -> None:
        self.output_payload_path = output_payload_path
        self.next_node = next_node  # Override topology next_node if set
        self.next_nodes = next_nodes  # Multi-target fan-out (SCATTER)
        self.should_pause = should_pause
        self.log_message = log_message
        self.payload_artifact = payload_artifact  # JSON metadata for scatter/merge ops


def execute_deterministic_node(
    node_id: str,
    task: dict[str, Any],
    topology_config: dict[str, Any] | None = None,
    predecessor_payloads: list[str] | None = None,
) -> DeterministicNodeResult:
    """Execute a deterministic node and return the result.

    Args:
        node_id: The full Node_ID string (e.g., ``CTRL_CHECKPOINT_1``).
        task: The task dict from the broker (contains payload_path, job_id, etc.).
        topology_config: Optional node config from topology.csv row dict.
        predecessor_payloads: Optional list of payload file paths from upstream
            nodes. Used by MERGE / CONCAT handlers.

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
    return handler(node_id, payload_path, job_id, config, predecessor_payloads or [])


# ── Individual Node Handlers ─────────────────────────────────────────────────


def _handle_anchor(
    node_id: str,
    payload_path: str,
    job_id: str,
    config: dict[str, Any],
    predecessor_payloads: list[str],
) -> DeterministicNodeResult:
    """CTRL_ANCHOR — Pass-through entry marker. No transformation."""
    logger.info(f"[CTRL_ANCHOR] {node_id}: Pass-through. Payload unchanged.")
    return DeterministicNodeResult(
        output_payload_path=payload_path,
        log_message=f"ANCHOR node {node_id}: payload forwarded unchanged.",
    )


def _handle_recursion(
    node_id: str,
    payload_path: str,
    job_id: str,
    config: dict[str, Any],
    predecessor_payloads: list[str],
) -> DeterministicNodeResult:
    """CTRL_RECURSION — Loop-back control with iteration counter.

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
            f"[CTRL_RECURSION] {node_id}: Iteration {iteration + 1}/{max_recursion} "
            f"— looping back to {loop_target}"
        )
        return DeterministicNodeResult(
            output_payload_path=payload_path,
            next_node=loop_target,
            log_message=f"RECURSION {iteration + 1}/{max_recursion}: looping to {loop_target}",
        )
    else:
        logger.info(f"[CTRL_RECURSION] {node_id}: Max recursion ({max_recursion}) reached — proceeding.")
        return DeterministicNodeResult(
            output_payload_path=payload_path,
            log_message=f"RECURSION complete after {max_recursion} iterations.",
        )


def _handle_pause(
    node_id: str,
    payload_path: str,
    job_id: str,
    config: dict[str, Any],
    predecessor_payloads: list[str],
) -> DeterministicNodeResult:
    """CTRL_PAUSE — Halt execution. Task set to 'paused' for manual resume."""
    logger.info(f"[CTRL_PAUSE] {node_id}: Flow paused. Awaiting manual resume.")
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
    predecessor_payloads: list[str],
) -> DeterministicNodeResult:
    """CTRL_GATE — Conditional gate.

    The gate checks if the payload file exists and has content.
    If empty or missing, it blocks (returns the same node as next_node
    so the broker re-queues it). Otherwise, passes through.
    """
    if not payload_path or payload_path == "none":
        logger.info(f"[CTRL_GATE] {node_id}: No payload — gate BLOCKED.")
        return DeterministicNodeResult(
            output_payload_path=payload_path,
            next_node=node_id,  # Re-queue self
            log_message=f"GATE {node_id}: blocked — no payload.",
        )

    path = Path(payload_path)
    if not path.exists() or path.stat().st_size == 0:
        logger.info(f"[CTRL_GATE] {node_id}: Payload empty or missing — gate BLOCKED.")
        return DeterministicNodeResult(
            output_payload_path=payload_path,
            next_node=node_id,
            log_message=f"GATE {node_id}: blocked — empty payload.",
        )

    logger.info(f"[CTRL_GATE] {node_id}: Gate PASSED.")
    return DeterministicNodeResult(
        output_payload_path=payload_path,
        log_message=f"GATE {node_id}: passed.",
    )


def _handle_checkpoint(
    node_id: str,
    payload_path: str,
    job_id: str,
    config: dict[str, Any],
    predecessor_payloads: list[str],
) -> DeterministicNodeResult:
    """CTRL_CHECKPOINT — Snapshot current payload to a checkpoint file."""
    checkpoint_dir = get_datacenter_path("03_Agent_Ledgers", job_id)
    checkpoint_dir.mkdir(parents=True, exist_ok=True)
    checkpoint_file = checkpoint_dir / f"{node_id}_checkpoint.md"

    if payload_path and payload_path != "none" and Path(payload_path).exists():
        shutil.copy2(payload_path, checkpoint_file)
        logger.info(f"[CTRL_CHECKPOINT] {node_id}: Snapshot saved → {checkpoint_file}")
    else:
        checkpoint_file.write_text(
            f"# Checkpoint: {node_id}\n\nNo payload at checkpoint time.\n",
            encoding="utf-8",
        )
        logger.info(f"[CTRL_CHECKPOINT] {node_id}: Empty checkpoint created → {checkpoint_file}")

    return DeterministicNodeResult(
        output_payload_path=payload_path,
        log_message=f"CHECKPOINT {node_id}: saved to {checkpoint_file.name}",
    )


def _handle_delay(
    node_id: str,
    payload_path: str,
    job_id: str,
    config: dict[str, Any],
    predecessor_payloads: list[str],
) -> DeterministicNodeResult:
    """CTRL_DELAY — Sleep for configured seconds.

    Delay duration is read from ``Instruction_Override`` field (e.g., "30"
    for 30 seconds). Defaults to 5 seconds if not specified.
    """
    delay_str = str(config.get("Instruction_Override", "5")).strip()
    try:
        delay_seconds = max(0.0, min(float(delay_str), 3600.0))  # Cap at 1 hour
    except ValueError:
        delay_seconds = 5.0

    logger.info(f"[CTRL_DELAY] {node_id}: Sleeping for {delay_seconds}s...")
    time.sleep(delay_seconds)
    logger.info(f"[CTRL_DELAY] {node_id}: Woke up after {delay_seconds}s.")

    return DeterministicNodeResult(
        output_payload_path=payload_path,
        log_message=f"DELAY {node_id}: slept {delay_seconds}s.",
    )


def _handle_transform(
    node_id: str,
    payload_path: str,
    job_id: str,
    config: dict[str, Any],
    predecessor_payloads: list[str],
) -> DeterministicNodeResult:
    """CTRL_TRANSFORM — Apply a static text template to the payload.

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

    logger.info(f"[CTRL_TRANSFORM] {node_id}: Template applied → {output_file}")
    return DeterministicNodeResult(
        output_payload_path=str(output_file),
        log_message=f"TRANSFORM {node_id}: output → {output_file.name}",
    )


# ── New Wave 3 Handlers ──────────────────────────────────────────────────────


def _read_payload(payload_path: str) -> str:
    """Safely read payload content from a file path."""
    if payload_path and payload_path != "none" and Path(payload_path).exists():
        return Path(payload_path).read_text(encoding="utf-8")
    return ""


def _handle_scatter(
    node_id: str,
    payload_path: str,
    job_id: str,
    config: dict[str, Any],
    predecessor_payloads: list[str],
) -> DeterministicNodeResult:
    """CTRL_SCATTER — Fan-out payload to multiple downstream nodes.

    Reads ``scatter_targets`` (list of node IDs) and ``scatter_mode`` from
    topology_config.  Modes:
      - ``full_copy``   (default): pass the full payload to every target.
      - ``chunk_split``: split payload by ``## `` headers and distribute
        one chunk per target (extra targets get empty payload).
    """
    scatter_targets: list[str] = config.get("scatter_targets", [])
    scatter_mode: str = str(config.get("scatter_mode", "full_copy")).strip().lower()

    if not scatter_targets:
        logger.warning(f"[CTRL_SCATTER] {node_id}: No scatter_targets configured — pass-through.")
        return DeterministicNodeResult(
            output_payload_path=payload_path,
            log_message=f"SCATTER {node_id}: no targets — pass-through.",
        )

    payload_content = _read_payload(payload_path)
    job_dir = get_datacenter_path("03_Agent_Ledgers", job_id)
    job_dir.mkdir(parents=True, exist_ok=True)

    scatter_meta: dict[str, Any] = {
        "source_node": node_id,
        "mode": scatter_mode,
        "targets": scatter_targets,
        "chunks": {},
    }

    if scatter_mode == "chunk_split":
        # Split on markdown ## headers
        chunks: list[str] = re.split(r"(?=^## )", payload_content, flags=re.MULTILINE)
        chunks = [c for c in chunks if c.strip()]  # Drop empty leading split
        for idx, target in enumerate(scatter_targets):
            chunk_content = chunks[idx] if idx < len(chunks) else ""
            chunk_file = job_dir / f"{node_id}_chunk_{idx}.md"
            chunk_file.write_text(chunk_content, encoding="utf-8")
            scatter_meta["chunks"][target] = str(chunk_file)
    else:
        # full_copy — every target receives the same payload
        for target in scatter_targets:
            scatter_meta["chunks"][target] = payload_path

    meta_json = json.dumps(scatter_meta, indent=2)
    logger.info(
        f"[CTRL_SCATTER] {node_id}: mode={scatter_mode}, "
        f"targets={scatter_targets} ({len(scatter_targets)} nodes)"
    )
    return DeterministicNodeResult(
        output_payload_path=payload_path,
        next_nodes=scatter_targets,
        log_message=f"SCATTER {node_id}: fan-out to {len(scatter_targets)} targets.",
        payload_artifact=meta_json,
    )


def _handle_merge(
    node_id: str,
    payload_path: str,
    job_id: str,
    config: dict[str, Any],
    predecessor_payloads: list[str],
) -> DeterministicNodeResult:
    """CTRL_MERGE — Merge multiple upstream payloads into one document.

    Reads ``merge_mode`` from topology_config:
      - ``structured`` (default): build output with ``## Source: <filename>`` sections.
      - ``concat``: join with ``merge_delimiter`` (default ``\\n---\\n``).
    """
    merge_mode: str = str(config.get("merge_mode", "structured")).strip().lower()
    delimiter: str = str(config.get("merge_delimiter", "\n---\n"))

    job_dir = get_datacenter_path("03_Agent_Ledgers", job_id)
    job_dir.mkdir(parents=True, exist_ok=True)
    output_file = job_dir / f"{node_id}_merged.md"

    sections: list[str] = []
    for pp in predecessor_payloads:
        content = _read_payload(pp)
        if merge_mode == "structured":
            source_name = Path(pp).stem if pp else "unknown"
            sections.append(f"## Source: {source_name}\n\n{content}")
        else:
            sections.append(content)

    # Also include the primary payload if not already in predecessors
    if payload_path and payload_path not in predecessor_payloads:
        primary = _read_payload(payload_path)
        if primary:
            if merge_mode == "structured":
                sections.insert(0, f"## Source: {Path(payload_path).stem}\n\n{primary}")
            else:
                sections.insert(0, primary)

    merged = delimiter.join(sections) if merge_mode == "concat" else "\n\n".join(sections)
    output_file.write_text(merged, encoding="utf-8")

    logger.info(f"[CTRL_MERGE] {node_id}: Merged {len(sections)} sources → {output_file}")
    return DeterministicNodeResult(
        output_payload_path=str(output_file),
        log_message=f"MERGE {node_id}: {len(sections)} sources merged.",
    )


def _handle_concat(
    node_id: str,
    payload_path: str,
    job_id: str,
    config: dict[str, Any],
    predecessor_payloads: list[str],
) -> DeterministicNodeResult:
    """CTRL_CONCAT — Flat concatenation of predecessor payloads.

    Reads ``concat_delimiter`` from topology_config (default ``\\n``).
    """
    delimiter: str = str(config.get("concat_delimiter", "\n"))

    job_dir = get_datacenter_path("03_Agent_Ledgers", job_id)
    job_dir.mkdir(parents=True, exist_ok=True)
    output_file = job_dir / f"{node_id}_concatenated.md"

    parts: list[str] = []
    # Include primary payload first
    primary = _read_payload(payload_path)
    if primary:
        parts.append(primary)
    # Append predecessors
    for pp in predecessor_payloads:
        content = _read_payload(pp)
        if content:
            parts.append(content)

    concatenated = delimiter.join(parts)
    output_file.write_text(concatenated, encoding="utf-8")

    logger.info(f"[CTRL_CONCAT] {node_id}: Concatenated {len(parts)} payloads → {output_file}")
    return DeterministicNodeResult(
        output_payload_path=str(output_file),
        log_message=f"CONCAT {node_id}: {len(parts)} payloads joined.",
    )


def _handle_branch(
    node_id: str,
    payload_path: str,
    job_id: str,
    config: dict[str, Any],
    predecessor_payloads: list[str],
) -> DeterministicNodeResult:
    """CTRL_BRANCH — Keyword-based conditional routing.

    Reads ``keyword_map`` (dict[str, str]) from topology_config, where keys
    are keywords and values are target node IDs. Scans the payload content
    for keywords (case-insensitive). Routes to the first match.
    Falls back to ``default_target`` or ``END``.
    """
    keyword_map: dict[str, str] = config.get("keyword_map", {})
    default_target: str = str(config.get("default_target", "END")).strip()

    payload_content = _read_payload(payload_path).lower()
    chosen_target = default_target

    for keyword, target_node in keyword_map.items():
        if keyword.lower() in payload_content:
            chosen_target = target_node
            logger.info(
                f"[CTRL_BRANCH] {node_id}: Keyword '{keyword}' matched → routing to {target_node}"
            )
            break

    if chosen_target == default_target:
        logger.info(f"[CTRL_BRANCH] {node_id}: No keyword match → default target {default_target}")

    return DeterministicNodeResult(
        output_payload_path=payload_path,
        next_node=chosen_target,
        log_message=f"BRANCH {node_id}: routed to {chosen_target}.",
    )


def _handle_filter(
    node_id: str,
    payload_path: str,
    job_id: str,
    config: dict[str, Any],
    predecessor_payloads: list[str],
) -> DeterministicNodeResult:
    """CTRL_FILTER — Apply filter rules to payload content.

    Reads ``filter_rules`` dict from topology_config with optional keys:
      - ``strip_sections``: list of markdown header strings to remove (with their content).
      - ``max_chars``: int — truncate payload to this length.
      - ``regex_remove``: str — regex pattern whose matches are removed.
    Rules are applied in the order: strip_sections → regex_remove → max_chars.
    """
    filter_rules: dict[str, Any] = config.get("filter_rules", {})

    job_dir = get_datacenter_path("03_Agent_Ledgers", job_id)
    job_dir.mkdir(parents=True, exist_ok=True)
    output_file = job_dir / f"{node_id}_filtered.md"

    content = _read_payload(payload_path)
    applied: list[str] = []

    # 1. Strip sections by header
    strip_sections: list[str] = filter_rules.get("strip_sections", [])
    for header in strip_sections:
        # Remove from the header line up to the next same-level or higher header
        escaped = re.escape(header)
        pattern = rf"^(#{{{1,6}}}\s*{escaped}).*?(?=^#{{1,6}}\s|\Z)"
        content = re.sub(pattern, "", content, flags=re.MULTILINE | re.DOTALL)
        applied.append(f"strip:{header}")

    # 2. Regex removal
    regex_remove: str = str(filter_rules.get("regex_remove", "")).strip()
    if regex_remove:
        try:
            content = re.sub(regex_remove, "", content)
            applied.append(f"regex:{regex_remove}")
        except re.error as exc:
            logger.warning(f"[CTRL_FILTER] {node_id}: Invalid regex '{regex_remove}': {exc}")

    # 3. Truncate
    max_chars: int = int(filter_rules.get("max_chars", 0))
    if max_chars > 0 and len(content) > max_chars:
        content = content[:max_chars]
        applied.append(f"truncated:{max_chars}")

    output_file.write_text(content, encoding="utf-8")
    logger.info(f"[CTRL_FILTER] {node_id}: Applied [{', '.join(applied)}] → {output_file}")
    return DeterministicNodeResult(
        output_payload_path=str(output_file),
        log_message=f"FILTER {node_id}: rules applied [{', '.join(applied)}].",
    )


def _handle_cleanup(
    node_id: str,
    payload_path: str,
    job_id: str,
    config: dict[str, Any],
    predecessor_payloads: list[str],
) -> DeterministicNodeResult:
    """CTRL_CLEANUP — Delete temporary files matching glob patterns.

    Reads from topology_config:
      - ``glob_patterns``: list of glob strings (e.g., ``["*.tmp", "*_chunk_*.md"]``).
      - ``cleanup_dir``: subdirectory under ``03_Agent_Ledgers/<job_id>`` to clean.
        Defaults to the job ledger directory itself.
    Returns a summary of deleted files.
    """
    glob_patterns: list[str] = config.get("glob_patterns", ["*.tmp"])
    cleanup_subdir: str = str(config.get("cleanup_dir", "")).strip()

    base_dir = get_datacenter_path("03_Agent_Ledgers", job_id)
    if cleanup_subdir:
        target_dir = base_dir / cleanup_subdir
    else:
        target_dir = base_dir

    deleted: list[str] = []
    if target_dir.exists():
        for pattern in glob_patterns:
            for match_path in glob.glob(str(target_dir / pattern)):
                mp = Path(match_path)
                if mp.is_file():
                    try:
                        mp.unlink()
                        deleted.append(mp.name)
                    except OSError as exc:
                        logger.warning(f"[CTRL_CLEANUP] {node_id}: Failed to delete {mp}: {exc}")

    summary = f"Deleted {len(deleted)} files: {', '.join(deleted[:20])}"
    if len(deleted) > 20:
        summary += f" ... and {len(deleted) - 20} more"

    logger.info(f"[CTRL_CLEANUP] {node_id}: {summary}")
    return DeterministicNodeResult(
        output_payload_path=payload_path,
        log_message=f"CLEANUP {node_id}: {summary}",
    )


# ── Wave 4: Conditional Route — 4-Vector Fallback Chain ──────────────────────


def _levenshtein(s1: str, s2: str) -> int:
    """Compute Levenshtein edit distance between two strings (pure Python)."""
    if len(s1) < len(s2):
        return _levenshtein(s2, s1)
    if len(s2) == 0:
        return len(s1)
    prev_row: list[int] = list(range(len(s2) + 1))
    for i, c1 in enumerate(s1):
        curr_row: list[int] = [i + 1]
        for j, c2 in enumerate(s2):
            insert = prev_row[j + 1] + 1
            delete = curr_row[j] + 1
            substitute = prev_row[j] + (0 if c1 == c2 else 1)
            curr_row.append(min(insert, delete, substitute))
        prev_row = curr_row
    return prev_row[-1]


def _try_structured_route(payload: str) -> str | None:
    """Vector 1 — Parse ``[ROUTE_TO: X]`` tag from payload."""
    match = re.search(r'\[ROUTE_TO:\s*(.+?)\]', payload)
    return match.group(1).strip() if match else None


def _try_keyword_route(payload: str, keyword_map: dict[str, str]) -> str | None:
    """Vector 2 — Case-insensitive keyword substring match."""
    payload_lower = payload.lower()
    for keyword, target in keyword_map.items():
        if keyword.lower() in payload_lower:
            return target
    return None


def _try_score_route(payload: str, score_threshold: float, config: dict[str, Any]) -> str | None:
    """Vector 3 — Parse ``[SCORE: X.XX]`` tag and route by threshold."""
    match = re.search(r'\[SCORE:\s*([\d.]+)\]', payload)
    if not match:
        return None
    try:
        score = float(match.group(1))
    except ValueError:
        return None
    default_fallback: str = config.get("default_target", "END")
    if score >= score_threshold:
        return config.get("high_target", default_fallback)
    return config.get("low_target", default_fallback)


def _try_fuzzy_route(payload: str, available_targets: list[str], max_distance: int = 3) -> str | None:
    """Vector 4 — Fuzzy-match a ``[ROUTE_TO: X]`` tag against available targets via Levenshtein."""
    match = re.search(r'\[ROUTE_TO:\s*(.+?)\]', payload)
    if not match:
        return None
    raw_target: str = match.group(1).strip()
    # Only engage fuzzy if it's NOT an exact match (Vector 1 would have caught it)
    if raw_target in available_targets:
        return None
    best_target: str | None = None
    best_dist: int = max_distance + 1
    for candidate in available_targets:
        dist = _levenshtein(raw_target, candidate)
        if dist < best_dist:
            best_dist = dist
            best_target = candidate
    if best_dist <= max_distance:
        return best_target
    return None


def _handle_conditional_route(
    node_id: str,
    payload_path: str,
    job_id: str,
    config: dict[str, Any],
    predecessor_payloads: list[str],
) -> DeterministicNodeResult:
    """CTRL_CONDITIONAL_ROUTE — 4-vector fallback routing chain.

    Tries routing vectors in priority order:
      1. Structured ``[ROUTE_TO: X]`` tag (exact match).
      2. Keyword gate — case-insensitive substring scan.
      3. Score threshold — ``[SCORE: X.XX]`` tag vs. threshold.
      4. Fuzzy — Levenshtein distance against available targets.
    Returns on first successful match; falls back to ``default_target``.
    """
    # ── Read configuration ────────────────────────────────────────────────
    all_vectors: list[str] = ["structured", "keyword", "score", "fuzzy"]
    route_vectors: list[str] = config.get("route_vectors", all_vectors)
    keyword_map: dict[str, str] = config.get("keyword_map", {})
    score_threshold: float = float(config.get("score_threshold", 0.7))
    default_target: str = str(config.get("default_target", "END")).strip()
    available_targets: list[str] = config.get("available_targets", [])
    max_distance: int = int(config.get("fuzzy_max_distance", 3))

    payload = _read_payload(payload_path)
    matched_target: str | None = None
    matched_vector: str = "default"

    # ── Execute vectors in priority order ─────────────────────────────────
    for vector in route_vectors:
        vec = vector.strip().lower()
        if vec == "structured":
            result = _try_structured_route(payload)
            if result is not None:
                # Confirm exact match exists in available_targets (if provided)
                if not available_targets or result in available_targets:
                    matched_target = result
                    matched_vector = "structured"
                    break
        elif vec == "keyword":
            result = _try_keyword_route(payload, keyword_map)
            if result is not None:
                matched_target = result
                matched_vector = "keyword"
                break
        elif vec == "score":
            result = _try_score_route(payload, score_threshold, config)
            if result is not None:
                matched_target = result
                matched_vector = "score"
                break
        elif vec == "fuzzy":
            result = _try_fuzzy_route(payload, available_targets, max_distance)
            if result is not None:
                matched_target = result
                matched_vector = "fuzzy"
                break

    final_target = matched_target or default_target
    logger.info(
        f"[CTRL_CONDITIONAL_ROUTE] {node_id}: vector={matched_vector} → {final_target}"
    )
    return DeterministicNodeResult(
        output_payload_path=payload_path,
        next_nodes=[final_target],
        log_message=f"CONDITIONAL_ROUTE {node_id}: vector={matched_vector} → {final_target}.",
    )


# ── Handler Registry ─────────────────────────────────────────────────────────

# Type alias for handler functions
_HandlerFn = Callable[[str, str, str, dict[str, Any], list[str]], DeterministicNodeResult]

_NODE_HANDLERS: dict[DeterministicNodeType, _HandlerFn] = {
    DeterministicNodeType.ANCHOR: _handle_anchor,
    DeterministicNodeType.RECURSION: _handle_recursion,
    DeterministicNodeType.PAUSE: _handle_pause,
    DeterministicNodeType.GATE: _handle_gate,
    DeterministicNodeType.CHECKPOINT: _handle_checkpoint,
    DeterministicNodeType.DELAY: _handle_delay,
    DeterministicNodeType.TRANSFORM: _handle_transform,
    DeterministicNodeType.SCATTER: _handle_scatter,
    DeterministicNodeType.MERGE: _handle_merge,
    DeterministicNodeType.CONCAT: _handle_concat,
    DeterministicNodeType.BRANCH: _handle_branch,
    DeterministicNodeType.FILTER: _handle_filter,
    DeterministicNodeType.CLEANUP: _handle_cleanup,
    DeterministicNodeType.CONDITIONAL_ROUTE: _handle_conditional_route,
}
