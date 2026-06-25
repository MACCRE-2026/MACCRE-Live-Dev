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
maccre_core/orchestration/universal_vault.py
=============================================
The Federated Auth Vault.
A provider-agnostic, cross-platform credential manager.

Strategy:
1. Attempt OS Vault integration via the `keyring` library (Windows/macOS/Linux native).
2. Fallback to `FernetVault` (fully vendored, AES-128 encrypted .bin file) if
   the OS Vault is unavailable or locked (e.g. headless containers, Android Termux).
"""

import abc
import json
import logging
from typing import Optional

from cryptography.fernet import Fernet
import keyring
from keyring.errors import KeyringError

from maccre_core.utils.path_resolver import get_datacenter_path

_log = logging.getLogger(__name__)
_SERVICE_NAME = "MACCREv2_Sovereign_Vault"


class AuthVault(abc.ABC):
    """Abstract interface for the secure credential vault."""
    
    @abc.abstractmethod
    def set_credential(self, provider_id: str, secret: str) -> bool:
        """Store a secret securely."""
        
    @abc.abstractmethod
    def get_credential(self, provider_id: str) -> Optional[str]:
        """Retrieve a secret."""


class OSVaultAdapter(AuthVault):
    """Uses Python `keyring` to interface with the native OS secure enclave."""
    
    def set_credential(self, provider_id: str, secret: str) -> bool:
        try:
            keyring.set_password(_SERVICE_NAME, provider_id, secret)
            return True
        except KeyringError as e:
            _log.warning("OSVaultAdapter: Failed to set credential for %s: %s", provider_id, e)
            return False
            
    def get_credential(self, provider_id: str) -> Optional[str]:
        try:
            return keyring.get_password(_SERVICE_NAME, provider_id)
        except KeyringError as e:
            _log.warning("OSVaultAdapter: Failed to get credential for %s: %s", provider_id, e)
            return None


class FernetVaultAdapter(AuthVault):
    """Fallback vendored vault using symmetric AES-128 encryption."""
    
    def __init__(self, master_key: bytes) -> None:
        self._fernet = Fernet(master_key)
        self._vault_path = get_datacenter_path("02_Dynamic_Context", "auth_vault.bin", project_id="GLOBAL")
        self._vault_path.parent.mkdir(parents=True, exist_ok=True)
        
    def _load(self) -> dict[str, str]:
        if not self._vault_path.exists():
            return {}
        try:
            encrypted_data = self._vault_path.read_bytes()
            if not encrypted_data:
                return {}
            decrypted_data = self._fernet.decrypt(encrypted_data)
            return json.loads(decrypted_data.decode("utf-8"))
        except Exception as e:
            _log.error("FernetVaultAdapter: Failed to load vault: %s", e)
            return {}
            
    def _save(self, data: dict[str, str]) -> None:
        raw_data = json.dumps(data).encode("utf-8")
        encrypted_data = self._fernet.encrypt(raw_data)
        self._vault_path.write_bytes(encrypted_data)

    def set_credential(self, provider_id: str, secret: str) -> bool:
        try:
            data = self._load()
            data[provider_id] = secret
            self._save(data)
            return True
        except Exception as e:
            _log.error("FernetVaultAdapter: Failed to set credential: %s", e)
            return False
            
    def get_credential(self, provider_id: str) -> Optional[str]:
        data = self._load()
        return data.get(provider_id)


class FederatedVault(AuthVault):
    """
    Main orchestration router for credentials.
    Tries the OSVaultAdapter first. If `keyring` raises errors or fails,
    it falls back to FernetVaultAdapter (if a master key has been provided).
    """
    
    def __init__(self) -> None:
        self.os_vault = OSVaultAdapter()
        self.fallback_vault: Optional[FernetVaultAdapter] = None
        
    def configure_fallback(self, master_key: bytes) -> None:
        """Initialize the fallback vault with a Fernet key derived from a user password."""
        self.fallback_vault = FernetVaultAdapter(master_key)

    def set_credential(self, provider_id: str, secret: str) -> bool:
        if self.os_vault.set_credential(provider_id, secret):
            return True
        if self.fallback_vault:
            _log.warning("FederatedVault: OS vault failed. Falling back to Fernet vault.")
            return self.fallback_vault.set_credential(provider_id, secret)
        _log.error("FederatedVault: No usable vault available to store credential.")
        return False
        
    def get_credential(self, provider_id: str) -> Optional[str]:
        # Try OS vault first
        secret = self.os_vault.get_credential(provider_id)
        if secret is not None:
            return secret
            
        # Try fallback vault
        if self.fallback_vault:
            return self.fallback_vault.get_credential(provider_id)
            
        return None

# Singleton instance
_vault_instance = FederatedVault()

def get_vault() -> FederatedVault:
    return _vault_instance

def get_provider_credential(provider_id: str) -> Optional[str]:
    """Convenience wrapper for the federated vault."""
    return _vault_instance.get_credential(provider_id)

def wipe_string(target: str) -> None:
    if not isinstance(target, str):
        return
    import sys
    import ctypes
    buffer_size = sys.getsizeof(target)
    address = id(target)
    try:
        ctypes.memset(address, 0, buffer_size)
    except Exception:
        pass

def clear_windows_clipboard() -> None:
    try:
        import ctypes
        user32 = ctypes.windll.user32
        if user32.OpenClipboard(None):
            user32.EmptyClipboard()
            user32.CloseClipboard()
    except Exception:
        pass

def protect_string(target_name: str, secret: str) -> None:
    pass # Deprecated in favor of universal_vault
