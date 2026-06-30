import ctypes
import ctypes.wintypes
import keyring
from pathlib import Path

class DATA_BLOB(ctypes.Structure):
    _fields_ = [("cbData", ctypes.wintypes.DWORD),
                ("pbData", ctypes.POINTER(ctypes.c_char))]

crypt32 = ctypes.WinDLL("crypt32.dll")

def decrypt_blob(encrypted_bytes: bytes) -> bytes:
    if not encrypted_bytes:
        return b""
    data_in = DATA_BLOB(len(encrypted_bytes), ctypes.cast(ctypes.c_char_p(encrypted_bytes), ctypes.POINTER(ctypes.c_char)))
    data_out = DATA_BLOB()
    if crypt32.CryptUnprotectData(ctypes.byref(data_in), None, None, None, None, 0, ctypes.byref(data_out)):
        try:
            return ctypes.string_at(data_out.pbData, data_out.cbData)
        finally:
            ctypes.windll.kernel32.LocalFree(data_out.pbData)
    else:
        raise ValueError("Decryption failed")

try:
    brave_bytes = Path("__DATACENTER/.vault/BRAVE_SEARCH_API_KEY.bin").read_bytes()
    brave_str = decrypt_blob(brave_bytes).decode('utf-8')
    keyring.set_password("MACCREv2_Sovereign_Vault", "BRAVE_SEARCH_API_KEY", brave_str)
    print("Migrated Brave Search API Key!")
except Exception as e:
    print(f"Failed: {e}")
