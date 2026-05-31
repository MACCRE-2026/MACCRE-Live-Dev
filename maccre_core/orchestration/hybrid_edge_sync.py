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
maccre_core/orchestration/hybrid_edge_sync.py
==============================================
Phase 12+ — Sovereign Edge State Synchroniser.

Formerly `datacenter_router.py`. The Drive-based hot-lock mechanism
(lock_task_for_agent / release_task_lock) has been permanently retired.
Race-condition prevention is now handled exclusively at the SQLite WAL
layer via the `BEGIN EXCLUSIVE` Gather Gate in local_broker.py.

HybridEdgeSync mandate (Git-like):
  1. Enforce the 5-Tier physical datacenter tree on every init.
  2. Expose a diff() hook for future sovereign Cloud ↔ Edge sync
     (Google Drive delta API, rsync-over-SSH, or Termux-local-only mode).
  3. Never own mutable agent state — it is a passive infrastructure tool.
"""

import os
from pathlib import Path
from typing import Any
from maccre_core.utils.path_resolver import get_datacenter_path


class HybridEdgeSync:
    """Sovereign Edge Infrastructure Sync.

    Enforces the 5-Tier Datacenter directory tree and provides the
    integration surface for future Cloud ↔ Edge state diffing.

    Hot-locking is NOT this class's responsibility. All concurrency
    control lives in LocalMessageBroker (SQLite WAL, BEGIN EXCLUSIVE).
    """

    # The 5-Tier Deterministic Tree — canonical, append-only
    TIERS: list[str] = [
        "01_Raw_Source",
        "02_Dynamic_Context",
        "03_Agent_Ledgers",
        "04_Code_Artifacts",
        "05_Rendered_Media",
    ]

    def __init__(self, root_path: str | None = None) -> None:
        self.root_path: str = root_path or str(get_datacenter_path())
        self._enforce_physical_tiers()

    # ── Infrastructure Enforcement ─────────────────────────────────────────────

    def _enforce_physical_tiers(self) -> None:
        """Ruthlessly enforces the local 5-Tier directory structure on init."""
        for tier in self.TIERS:
            tier_path = os.path.join(self.root_path, tier)
            os.makedirs(tier_path, exist_ok=True)

    def get_tier_path(self, tier_name: str) -> Path:
        """Return the absolute Path for a named tier.

        Args:
            tier_name: One of the TIERS strings (e.g. '01_Raw_Source').

        Returns:
            Absolute Path to the requested tier directory.

        Raises:
            ValueError: If tier_name is not in TIERS.
        """
        if tier_name not in self.TIERS:
            raise ValueError(
                f"Unknown tier '{tier_name}'. Valid tiers: {self.TIERS}"
            )
        return Path(self.root_path) / tier_name

    # ── Sync Surface (HITL — Human In The Loop required) ──────────────────────

    def diff(self, remote_service: Any | None = None) -> dict[str, list[str]]:
        """Git-like diff between local datacenter state and remote Cloud store.

        This is a HITL-gated operation. The diff() result is surfaced to the
        Architect for review before any sync is committed. No destructive
        operation is performed by this method.

        Args:
            remote_service: Optional Google Drive service object for cloud
                comparison. If None, returns a local-only inventory diff
                suitable for Termux/air-gap mode.

        Returns:
            A dict with keys 'local_only', 'remote_only', 'modified',
            each containing a list of relative file paths.

        Note:
            Full implementation wires to Google Drive Files.list() delta
            tokens or rsync --itemize-changes over SSH. Stub provided for
            CLI /sync command surface.
        """
        # Stub — returns local inventory for HITL review
        local_inventory: list[str] = []
        for tier in self.TIERS:
            tier_path = Path(self.root_path) / tier
            if tier_path.exists():
                for item in tier_path.rglob("*"):
                    if item.is_file():
                        local_inventory.append(str(item.relative_to(self.root_path)))

        return {
            "local_only": local_inventory,
            "remote_only": [],   # Populated when remote_service is wired
            "modified": [],
        }
