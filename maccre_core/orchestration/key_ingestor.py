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
maccre_core/orchestration/key_ingestor.py
============================================
Autonomous Key Fingerprinting Layer.
Regex-matches incoming raw API keys to determine the vendor SDK,
and natively routes them into the local DPAPI vault without
human configuration.

Supports an explicit ``vault_name`` override so operators can store
any arbitrary secret without waiting for a fingerprint pattern.
"""
import re

from maccre_core.orchestration.universal_vault import protect_string, clear_windows_clipboard

# Fingerprint Map: Regex -> Target Vault Name
_FINGERPRINTS: dict[str, str] = {
    # Google Gemini: AIzaSy + 33 chars
    r"^AIzaSy[a-zA-Z0-9\-_]{33}$": "MACCRE_Sovereign",

    # Anthropic: sk-ant-api03- + long string
    r"^sk-ant-api[a-zA-Z0-9\-_]{20,}$": "MACCRE_Sovereign_Anthropic",

    # OpenAI: sk-proj- or sk- + 40+ chars
    r"^sk-(proj-)?[a-zA-Z0-9\-_]{32,}$": "MACCRE_Sovereign_OpenAI",

    # Groq: gsk_ + alphanumeric
    r"^gsk_[a-zA-Z0-9]{25,}$": "MACCRE_Sovereign_Groq",

    # xAI: xai-...
    r"^xai-[a-zA-Z0-9\-_]{30,}$": "MACCRE_Sovereign_xAI",

    # Brave Search API: BSA + alphanumeric (32+ chars)
    r"^BSA[a-zA-Z0-9\-_]{29,}$": "BRAVE_SEARCH_API_KEY",
}


def ingest_key(raw_key: str, vault_name: str = "") -> str:
    """Fingerprint an API key and encrypt it into the local DPAPI vault.

    If ``vault_name`` is provided, skips fingerprinting and stores the key
    directly under that name — useful for keys with non-standard formats.

    Args:
        raw_key:    The raw API key string to store.
        vault_name: Optional explicit vault target name (bypasses fingerprinting).

    Returns:
        A SUCCESS or FAULT string describing the result.
    """
    raw_key = raw_key.strip()

    # ── Explicit override — skip fingerprinting ───────────────────────────────
    if vault_name:
        try:
            protect_string(vault_name, raw_key)
            clear_windows_clipboard()
            return (
                f"SUCCESS: Key stored in DPAPI Vault as '{vault_name}.bin' "
                "(explicit name — fingerprinting bypassed)."
            )
        except Exception as exc:  # noqa: BLE001
            return f"CRITICAL: Windows DPAPI protection failed for '{vault_name}': {exc}"

    # ── Auto-fingerprint ──────────────────────────────────────────────────────
    for pattern, target_name in _FINGERPRINTS.items():
        if re.match(pattern, raw_key):
            vendor = target_name.replace("MACCRE_Sovereign_", "").replace("MACCRE_Sovereign", "Google Gemini")
            if target_name == "BRAVE_SEARCH_API_KEY":
                vendor = "Brave Search"
            try:
                protect_string(target_name, raw_key)
                clear_windows_clipboard()
                return (
                    f"SUCCESS: Fingerprint matched '{vendor}'. "
                    f"Key securely locked in DPAPI Vault under '{target_name}.bin'."
                )
            except Exception as exc:  # noqa: BLE001
                return f"CRITICAL: Matched '{vendor}', but Windows DPAPI protection failed: {exc}"

    return (
        "FAULT: Key signature unrecognized. "
        "It does not match standard Gemini, Anthropic, OpenAI, Groq, xAI, or Brave entropy masks.\n"
        "Use --vault-name to store it explicitly:  "
        "python maccre.py config set-key <KEY> --vault-name BRAVE_SEARCH_API_KEY"
    )
