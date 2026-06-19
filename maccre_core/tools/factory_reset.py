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
maccre_core/tools/factory_reset.py
===================================
MACCREv2 Day Zero Initialization Script.
Completely purges all databases, vector stores, ledgers, and logs.
Resets topology.csv to a blank state.

Pre-flight archive is ALWAYS executed before any deletion.
"""

import os
import shutil
from datetime import datetime, timezone
from maccre_core.logger import logger
from maccre_core.utils.path_resolver import get_maccre_root

_REPO_ROOT    = get_maccre_root()
_DC           = str(_REPO_ROOT / "__DATACENTER")
_ARCHIVE_ROOT = str(_REPO_ROOT / "_archive")

# 1. Directories to completely obliterate and recreate
_NUKE_DIRS = [
    os.path.join(_DC, "01_Raw_Source"),
    os.path.join(_DC, "02_Dynamic_Context"),
    os.path.join(_DC, "03_Agent_Ledgers"),
    os.path.join(_DC, "04_Code_Artifacts"),
    os.path.join(_DC, "05_Rendered_Media"),
    os.path.join(_DC, "02_Dynamic_Context", "memory_pins"),
    os.path.join(_DC, "IPC_Temp"),
    os.path.join(_DC, "telemetry"),
    os.path.join(_DC, "chroma_db"),
]

# 2. Specific files to delete
_NUKE_FILES = [
    os.path.join(_REPO_ROOT, "maccre_system.log"),
    os.path.join(_DC, "swarm_queue.db"),
    os.path.join(_DC, "swarm_queue.db-wal"),
    os.path.join(_DC, "swarm_queue.db-shm"),
    os.path.join(_DC, "chat_history.db"),
    os.path.join(_DC, "chat_history.db-wal"),
    os.path.join(_DC, "chat_history.db-shm"),
    os.path.join(_DC, "window_states.json"),
    os.path.join(_DC, "burn_in_autopsy.md"),
    os.path.join(_DC, "nexus_diagnostic_report.md"),
]

_TOPOLOGY_PATH = str(_REPO_ROOT / "topology.csv")
_TOPOLOGY_HEADERS = (
    "Node_ID,Prompt,Success_Target,Failure_Target,"
    "Wait_For,Temperature,Tools_Allowed,Model\n"
)


# ── Pre-flight archive ────────────────────────────────────────────────────────

def run_preflight_archive() -> str:
    """
    Snapshots everything that will be destroyed into a timestamped archive
    directory. Returns the archive path.
    """
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    dest = os.path.join(_ARCHIVE_ROOT, f"DayZero_PreReset_{stamp}")
    os.makedirs(dest, exist_ok=True)

    _archive_items = [
        (_TOPOLOGY_PATH,                             os.path.join(dest, "topology.csv")),
        (os.path.join(_DC, "01_Raw_Source"),         os.path.join(dest, "01_Raw_Source")),
        (os.path.join(_DC, "02_Dynamic_Context"),    os.path.join(dest, "02_Dynamic_Context")),
        (os.path.join(_DC, "03_Agent_Ledgers"),      os.path.join(dest, "03_Agent_Ledgers")),
        (os.path.join(_DC, "02_Dynamic_Context", "memory_pins"), os.path.join(dest, "memory_pins")),
        (os.path.join(_DC, "telemetry"),             os.path.join(dest, "telemetry")),
        (os.path.join(_DC, "swarm_queue.db"),        os.path.join(dest, "swarm_queue.db")),
    ]

    archived = 0
    for src, dst in _archive_items:
        if not os.path.exists(src):
            continue
        try:
            if os.path.isdir(src):
                shutil.copytree(src, dst, dirs_exist_ok=True)
            else:
                os.makedirs(os.path.dirname(dst), exist_ok=True)
                shutil.copy2(src, dst)
            archived += 1
        except Exception as exc:
            logger.info(f"  [ARCHIVE WARN] Could not archive {src}: {exc}")

    logger.info(f"[PREFLIGHT] Archive complete -> {dest} ({archived} items)")
    return dest


# ── Factory reset ─────────────────────────────────────────────────────────────

def execute_factory_reset() -> None:
    logger.info("=" * 60)
    logger.info("MACCREv2 FACTORY RESET — Day Zero Initialization")
    logger.info("=" * 60)

    # Mandatory pre-flight archive (always runs before any deletion)
    archive_path = run_preflight_archive()
    logger.info(f"[RESET]  Safe to proceed — state archived at:\n         {archive_path}\n")

    # Wipe and recreate directories
    for d in _NUKE_DIRS:
        if os.path.exists(d):
            try:
                shutil.rmtree(d)
                logger.info(f"[PURGED]  {d}")
            except Exception as exc:
                logger.error(f"[WARN]    Failed to purge {d}: {exc}")
        os.makedirs(d, exist_ok=True)
        logger.info(f"[CREATED] {d}")

    # Wipe loose files
    for f in _NUKE_FILES:
        if os.path.exists(f):
            try:
                os.remove(f)
                logger.info(f"[DELETED] {f}")
            except Exception as exc:
                logger.error(f"[WARN]    Failed to delete {f}: {exc}")

    # Blank the topology
    try:
        with open(_TOPOLOGY_PATH, "w", encoding="utf-8") as fh:
            fh.write(_TOPOLOGY_HEADERS)
        logger.info("[RESET]   topology.csv → blank headers only")
    except Exception as exc:
        logger.error(f"[WARN]    Failed to reset topology: {exc}")

    # Re-initialise schema so the system can boot immediately
    logger.info("\n[INIT]    Re-initialising telemetry matrix schemas...")
    from maccre_core.orchestration.telemetry_db import init_all_silos
    init_all_silos()

    logger.info("[INIT]    Re-initialising swarm queue schema...")
    from maccre_core.orchestration.local_broker import LocalMessageBroker
    LocalMessageBroker()

    logger.info("\n" + "=" * 60)
    logger.info("[SUCCESS] MACCREv2 restored to Day Zero state.")
    logger.info(f"          Archive snapshot: {archive_path}")
    logger.info("=" * 60)


if __name__ == "__main__":
    import sys
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]
    execute_factory_reset()
