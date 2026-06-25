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
maccre_core/orchestration/access_control.py
============================================
Phase 20 — Conditional Release Access Control Layer.

Implements a three-tier security model for Nexus file system operations:

Tier 1 — Read-Only Baseline (always active):
    Nexus can read any file under the MACCREv2 root.
    No restriction on introspection of system files.

Tier 2 — Conditional Release (write to system paths):
    Any write operation targeting paths OUTSIDE __DATACENTER requires:
      1. Agent submits a logged `request_elevation(justification)` tool call.
      2. User is prompted in the TUI for a numeric PIN.
      3. If PIN matches, operation proceeds and is logged to telemetry.
      4. Each elevation is single-use and session-scoped.

Tier 3 — MCP Bypass (Antigravity IDE connected):
    When the MCP server receives the MACCRE_ELEVATION_TOKEN from Antigravity,
    ConditionalRelease is suspended for the duration of that MCP session.
    All operations under bypass are still fully audited.

Trash Protocol:
    No MACCRE agent or tool may hard-delete a file. All deletion
    operations MUST route through `trash_file()` which physically
    moves the target to `B:\\MACCREv2\\_archive\\trash\\` with a UTC timestamp
    prefix, preserving the complete file history.
"""
from __future__ import annotations

import hashlib
import logging
import os
import shutil
from datetime import datetime, timezone
from pathlib import Path

from maccre_core.utils.path_resolver import get_maccre_root
from maccre_core.orchestration.telemetry_db import log_system_event

logger = logging.getLogger("maccre_core")

# ── Constants ──────────────────────────────────────────────────────────────────

_DATACENTER_ROOT: Path = get_maccre_root() / "__DATACENTER"
_ARCHIVE_ROOT: Path = get_maccre_root() / "_archive"
_TRASH_ROOT: Path = _ARCHIVE_ROOT / "trash"

# PIN is stored as a salted SHA-256 hash in the Windows Vault.
# For initial setup, the default PIN is "1234". Override via set_elevation_pin().
_DEFAULT_PIN_HASH: str = hashlib.sha256(b"maccre_salt_1234").hexdigest()

# Set by the MCP server when Antigravity connects with a valid token.
_mcp_bypass_active: bool = False
_MCP_ELEVATION_TOKEN: str | None = os.environ.get("MACCRE_ELEVATION_TOKEN")


# ── MCP Bypass Control ────────────────────────────────────────────────────────

def activate_mcp_bypass(token: str) -> bool:
    """Called by the MCP server when Antigravity sends a valid elevation token.

    Args:
        token: The elevation token passed from Antigravity via MCP.

    Returns:
        True if bypass was activated, False if token is invalid.
    """
    global _mcp_bypass_active
    expected = _MCP_ELEVATION_TOKEN
    if expected and token == expected:
        _mcp_bypass_active = True
        logger.info("[AccessControl] MCP Elevation Bypass ACTIVATED — Antigravity session established.")
        log_system_event(
            action_type="MCP_BYPASS_ACTIVATED",
            payload="Antigravity MCP session elevated.",
        )
        return True
    logger.warning("[AccessControl] MCP bypass attempt with INVALID token.")
    return False


def deactivate_mcp_bypass() -> None:
    """Revokes the MCP bypass. Called when the MCP server session ends."""
    global _mcp_bypass_active
    _mcp_bypass_active = False
    logger.info("[AccessControl] MCP Elevation Bypass DEACTIVATED.")


def is_mcp_bypass_active() -> bool:
    """Returns whether the MCP bypass is currently active."""
    return _mcp_bypass_active


# ── Path Classification ───────────────────────────────────────────────────────

def is_datacenter_path(path: str | Path) -> bool:
    """Returns True if the path resolves inside __DATACENTER (unrestricted zone)."""
    try:
        Path(path).resolve().relative_to(_DATACENTER_ROOT.resolve())
        return True
    except ValueError:
        return False


def requires_elevation(path: str | Path) -> bool:
    """Returns True if writing to this path requires a Conditional Release PIN.

    Args:
        path: The target file path for a write/modify operation.

    Returns:
        False if:
          - MCP bypass is active.
          - Path is inside __DATACENTER.
        True otherwise (system-level write detected).
    """
    if _mcp_bypass_active:
        return False
    return not is_datacenter_path(path)


# ── Elevation Request ─────────────────────────────────────────────────────────

def request_elevation(justification: str, session_id: str = "", agent_id: str = "") -> str:
    """Tool for Nexus to submit a logged request for elevated write access.

    This is the ONLY sanctioned way for an agent to request access to
    system-level files outside __DATACENTER. The request is logged to
    telemetry regardless of approval outcome.

    Args:
        justification: Agent's explanation of why system-level access is needed.
        session_id: Active session identifier for audit trail.
        agent_id: Agent name requesting elevation.

    Returns:
        '[ELEVATION_GRANTED]' if the user approves, '[ELEVATION_DENIED]' otherwise.
    """
    log_system_event(
        action_type="ELEVATION_REQUESTED",
        payload=justification,
        session_id=session_id,
        agent_id=agent_id,
    )
    logger.warning(
        f"[AccessControl] ⚠️ ELEVATION REQUEST from '{agent_id}': {justification}"
    )

    # NOTE: The TUI (maccre.py) intercepts this tool result and prompts the user.
    # The token '[ELEVATION_PIN_REQUIRED]' is the signal for the TUI to display
    # the PIN prompt and call verify_elevation_pin() with the user's input.
    return f"[ELEVATION_PIN_REQUIRED] Justification logged. Reason: {justification}"


def verify_elevation_pin(pin_attempt: str, session_id: str = "") -> bool:
    """Verifies the user-entered PIN against the stored hash.

    Args:
        pin_attempt: The raw PIN string entered by the user.
        session_id: Active session for audit logging.

    Returns:
        True if PIN matches, False otherwise.
    """
    from maccre_core.orchestration.universal_vault import get_provider_credential

    # Try to load a custom PIN hash from the vault; fall back to default.
    stored_hash = get_provider_credential("MACCRE_ELEVATION_PIN_HASH") or _DEFAULT_PIN_HASH
    attempt_hash = hashlib.sha256(f"maccre_salt_{pin_attempt}".encode()).hexdigest()

    approved = attempt_hash == str(stored_hash).strip()
    log_system_event(
        action_type="ELEVATION_RESULT",
        payload="GRANTED" if approved else "DENIED",
        session_id=session_id,
    )
    return approved


# ── Trash Protocol ────────────────────────────────────────────────────────────

def trash_file(path: str | Path, reason: str = "", session_id: str = "", agent_id: str = "") -> str:
    """Move a file to the _archive/trash/ silo instead of hard-deleting it.

    No MACCRE agent or tool may call `os.remove()` or `Path.unlink()` directly.
    All deletions must route through this function.

    Args:
        path: Absolute path of the file to trash.
        reason: Optional reason for the deletion (logged to telemetry).
        session_id: Active session for audit trail.
        agent_id: Agent requesting the deletion.

    Returns:
        A JSON-compatible string describing the outcome.
    """
    src = Path(path)
    if not src.exists():
        return f"[TRASH_FAULT] File not found: {path}"

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    dest_name = f"{timestamp}__{src.name}"
    _TRASH_ROOT.mkdir(parents=True, exist_ok=True)
    dest = _TRASH_ROOT / dest_name

    try:
        shutil.move(str(src), str(dest))
        log_system_event(
            action_type="FILE_TRASHED",
            payload=f"src={src} -> dest={dest} | reason={reason}",
            session_id=session_id,
            agent_id=agent_id,
        )
        logger.info(f"[AccessControl] Trashed: {src.name} -> {dest}")
        return f"[TRASH_SUCCESS] '{src.name}' archived to _archive/trash/ as '{dest_name}'."
    except Exception as e:
        return f"[TRASH_FAULT] Failed to trash '{path}': {e}"
