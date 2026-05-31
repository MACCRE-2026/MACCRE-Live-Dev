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
maccre_core/_net/environment_probe.py
======================================
Probes local hardware to populate the environment matrix for routing.
"""
import urllib.request
import urllib.error
import os

def get_environment_matrix() -> dict[str, bool]:
    """Actively probes the environment to determine local routing capabilities."""
    
    matrix = {
        "ollama_active": False,
        "high_compute": False
    }
    
    # 1. Probe Ollama
    try:
        req = urllib.request.Request("http://localhost:11434/api/tags", method="GET")
        with urllib.request.urlopen(req, timeout=1.0) as r:
            if r.status == 200:
                matrix["ollama_active"] = True
    except (urllib.error.URLError, ConnectionError):
        matrix["ollama_active"] = False
        
    # 2. Hardware heuristic (rough gauge of logical processors)
    try:
        logical_cores = os.cpu_count() or 0
        if logical_cores >= 8:
            matrix["high_compute"] = True
    except Exception:
        pass
        
    return matrix
