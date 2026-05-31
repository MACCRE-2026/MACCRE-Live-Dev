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
maccre_core/tools/text_tools.py
================================
Atomic, GUI-agnostic text-processing helpers for the MACCRE Tool Registry.

All functions carry explicit type hints and Google-style docstrings so the
`google-generativeai` SDK can compile correct Function Calling schemas from
them automatically.

Gemini Function Calling schema contract (enforced by .agrules):
  - Type hints: use `typing` module primitives.
  - Docstrings: Google style only (Args / Returns / Raises).
  - No business logic. Pure transformations.
"""

import json
import re
from typing import Any


def parse_json_response(raw: str) -> dict[str, Any]:
    """Strip optional Markdown fences from an LLM response and parse it as JSON.

    Args:
        raw: The raw string returned by a Gemini generate_content call. May be
            wrapped in triple-backtick code fences with an optional language tag
            (e.g. ```json ... ``` or ``` ... ```).

    Returns:
        A Python dictionary parsed from the JSON content inside the response.

    Raises:
        ValueError: If the stripped text cannot be parsed as valid JSON.
    """
    text = raw.strip()
    # Remove ```json ... ``` or ``` ... ``` fences
    fence_pattern = re.compile(r"^```(?:json)?\s*([\s\S]*?)```$", re.MULTILINE)
    match = fence_pattern.search(text)
    if match:
        text = match.group(1).strip()

    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError(
            f"parse_json_response: could not parse as JSON. "
            f"Content preview: {text[:120]!r}"
        ) from exc


def build_system_instruction(fields: dict[str, str]) -> str:
    """Compose a flat key-value dictionary into a system-instruction string.

    Each non-empty field is rendered as "Key: Value" on its own line.
    Empty values are silently omitted so the model is not confused by blank
    fields.

    Args:
        fields: Ordered mapping of label → content. Insertion order is
            preserved (Python 3.7+).

    Returns:
        A multi-line string suitable for passing as the ``system_instruction``
        argument of ``types.GenerateContentConfig``.
    """
    lines: list[str] = []
    for key, value in fields.items():
        if value:
            lines.append(f"{key}: {value}")
    return "\n".join(lines)


def truncate_history(
    history: list[dict[str, str]],
    max_turns: int = 15,
) -> list[dict[str, str]]:
    """Return the most-recent ``max_turns`` entries from a conversation history.

    Stateless: does not modify the original list.

    Args:
        history: List of turn dicts, each with at minimum ``"speaker"`` and
            ``"text"`` keys.  Earlier entries are at lower indices.
        max_turns: Maximum number of turns to retain.  If 0, returns an empty
            list.  If the history is shorter than ``max_turns``, the full list
            is returned unchanged.

    Returns:
        A slice of ``history`` containing only the last ``max_turns`` entries.
    """
    if max_turns <= 0:
        return []
    return history[-max_turns:]


def format_cost_str(cost: float) -> str:
    """Format a floating-point API cost as a dollar string with six decimal places.

    Args:
        cost: The raw cost value in USD (e.g. ``0.000123456``).

    Returns:
        A human-readable string of the form ``"$0.000123"``.
    """
    return f"${cost:.6f}"
