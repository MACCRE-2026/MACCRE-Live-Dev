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
maccre_core/orchestration/windows_vault.py
============================================
Dual-mode credential store.

Primary:  DPAPI .bin files in __DATACENTER/.vault/  (written by `config set-key`)
Fallback: Windows Credential Manager via CredReadW  (written by `cmdkey`)

Both stores are read transparently by get_provider_credential().
"""
import ctypes
import os
import sys
from ctypes import wintypes
from pathlib import Path

from maccre_core.utils.path_resolver import get_maccre_root


class DATA_BLOB(ctypes.Structure):
    _fields_ = [
        ("cbData", wintypes.DWORD),
        ("pbData", ctypes.POINTER(ctypes.c_char)),
    ]


def wipe_string(target: str) -> None:
    """Overwrites the CPython string buffer in RAM with null bytes."""
    if not isinstance(target, str):
        return
    # Direct memory mutation via ctypes
    buffer_size = sys.getsizeof(target)
    address = id(target)
    ctypes.memset(address, 0, buffer_size)


def clear_windows_clipboard() -> None:
    """Empties the Windows clipboard via Win32 API."""
    user32 = ctypes.windll.user32
    if user32.OpenClipboard(None):
        try:
            user32.EmptyClipboard()
        finally:
            user32.CloseClipboard()




def _get_vault_dir() -> Path:
    p = get_maccre_root() / "__DATACENTER" / ".vault"
    os.makedirs(p, exist_ok=True)
    return p


def protect_string(target_name: str, secret: str) -> None:
    """Encrypt a string using Windows DPAPI and save it as an opaque .bin file."""
    crypt32 = ctypes.WinDLL("crypt32.dll")
    secret_bytes = secret.encode("utf-8")
    data_in = DATA_BLOB()
    data_in.cbData = len(secret_bytes)
    data_in.pbData = ctypes.cast(ctypes.c_char_p(secret_bytes), ctypes.POINTER(ctypes.c_char))

    data_out = DATA_BLOB()
    if crypt32.CryptProtectData(ctypes.byref(data_in), None, None, None, None, 0, ctypes.byref(data_out)):
        try:
            blob = ctypes.string_at(data_out.pbData, data_out.cbData)
            target_path = _get_vault_dir() / f"{target_name}.bin"
            with open(target_path, "wb") as f:
                f.write(blob)
        finally:
            ctypes.windll.kernel32.LocalFree(data_out.pbData)
    else:
        raise RuntimeError("CryptProtectData failed.")


# ── Windows Credential Manager reader (CredReadW) ────────────────────────────

class _FILETIME(ctypes.Structure):
    _fields_ = [("dwLow", wintypes.DWORD), ("dwHigh", wintypes.DWORD)]


class _CREDENTIAL(ctypes.Structure):
    """Win32 CREDENTIAL structure (wincred.h)."""
    _fields_ = [
        ("Flags",              wintypes.DWORD),
        ("Type",               wintypes.DWORD),
        ("TargetName",         ctypes.c_wchar_p),
        ("Comment",            ctypes.c_wchar_p),
        ("LastWritten",        _FILETIME),
        ("CredentialBlobSize", wintypes.DWORD),
        ("CredentialBlob",     ctypes.POINTER(ctypes.c_byte)),
        ("Persist",            wintypes.DWORD),
        ("AttributeCount",     wintypes.DWORD),
        ("Attributes",         ctypes.c_void_p),
        ("TargetAlias",        ctypes.c_wchar_p),
        ("UserName",           ctypes.c_wchar_p),
    ]


def _try_wincred(target_name: str) -> str | None:
    """Read a credential from Windows Credential Manager (cmdkey / CredReadW).

    cmdkey stores credentials as CRED_TYPE_DOMAIN_PASSWORD (type 2) and encodes
    the password blob as UTF-16-LE.  argtypes/restype are set explicitly to
    prevent ctypes from mismarshaling the pointer on 64-bit Windows.
    """
    try:
        advapi32 = ctypes.WinDLL("advapi32.dll")
        advapi32.CredReadW.restype = wintypes.BOOL
        advapi32.CredReadW.argtypes = [
            ctypes.c_wchar_p,
            wintypes.DWORD,
            wintypes.DWORD,
            ctypes.POINTER(ctypes.c_void_p),
        ]
        advapi32.CredFree.restype = None
        advapi32.CredFree.argtypes = [ctypes.c_void_p]

        CRED_TYPE_DOMAIN_PASSWORD: int = 2

        cred_raw = ctypes.c_void_p()
        ok = advapi32.CredReadW(target_name, CRED_TYPE_DOMAIN_PASSWORD, 0, ctypes.byref(cred_raw))
        if ok and cred_raw.value:
            try:
                cred = ctypes.cast(cred_raw, ctypes.POINTER(_CREDENTIAL)).contents
                size = cred.CredentialBlobSize
                blob = bytes(cred.CredentialBlob[:size])
                for enc in ("utf-16-le", "utf-8"):
                    try:
                        return blob.decode(enc).strip("\x00").strip()
                    except UnicodeDecodeError:
                        continue
            finally:
                advapi32.CredFree(cred_raw)
        return None
    except Exception:  # noqa: BLE001
        return None


# ── Public API ───────────────────────────────────────────────────────────────

def get_provider_credential(target_name: str) -> str | None:
    """Read a secret from the MACCRE vault or Windows Credential Manager.

    Resolution order:
      1. DPAPI ``.bin`` file in ``__DATACENTER/.vault/``  (``config set-key`` path)
      2. Windows Credential Manager via ``CredReadW``     (``cmdkey`` path)

    Both ingestion methods are supported transparently.
    """
    # ── 1. DPAPI .bin vault ───────────────────────────────────────────────────
    target_path = _get_vault_dir() / f"{target_name}.bin"
    if os.path.exists(target_path):
        with open(target_path, "rb") as f:
            encrypted_blob = f.read()

        crypt32 = ctypes.WinDLL("crypt32.dll")
        data_in = DATA_BLOB()
        data_in.cbData = len(encrypted_blob)
        data_in.pbData = ctypes.cast(ctypes.c_char_p(encrypted_blob), ctypes.POINTER(ctypes.c_char))

        data_out = DATA_BLOB()
        if crypt32.CryptUnprotectData(
            ctypes.byref(data_in), None, None, None, None, 0, ctypes.byref(data_out)
        ):
            try:
                return ctypes.string_at(data_out.pbData, data_out.cbData).decode("utf-8")
            finally:
                ctypes.windll.kernel32.LocalFree(data_out.pbData)

    # ── 2. Windows Credential Manager fallback (cmdkey store) ─────────────────
    return _try_wincred(target_name)
