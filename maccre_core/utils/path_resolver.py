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
import os
from pathlib import Path


def get_maccre_root() -> Path:
    """
    Universally resolves the MACCREv2 root directory.

    Priority:
    1. MACCRE_ROOT environment variable (if explicitly injected for edge deployments)
    2. __file__ fallback (resolves three levels up from this file, capturing the true deployment root)
    """
    env_root = os.environ.get("MACCRE_ROOT")
    if env_root:
        return Path(env_root).resolve()

    # If this file is maccre_core/utils/path_resolver.py:
    # 1. parent = utils
    # 2. parent.parent = maccre_core
    # 3. parent.parent.parent = MACCREv2
    return Path(__file__).resolve().parent.parent.parent


def get_datacenter_path(*subpaths: str) -> Path:
    """
    Convenience method for fetching absolute paths inside __DATACENTER.
    Dynamically injects the active $projectName layer to isolate multi-tenant environments.
    """
    project_name = os.environ.get("MACCRE_ACTIVE_PROJECT", "GLOBAL") or "GLOBAL"
    p = get_maccre_root() / "__DATACENTER" / project_name
    if subpaths:
        p = p.joinpath(*subpaths)
    return p
