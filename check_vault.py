import os
from pathlib import Path
import ctypes
from ctypes import wintypes
import keyring

print("--- Old DPAPI Vault Check ---")
vault_dir = Path("__DATACENTER/.vault")
if vault_dir.exists():
    for f in vault_dir.glob("*.bin"):
        print(f"Found old DPAPI file: {f.name}")
else:
    print("No old DPAPI vault found.")

print("\n--- New Keyring Check ---")
try:
    gemini_key = keyring.get_password("MACCREv2_Sovereign_Vault", "MACCRE_Sovereign")
    brave_key = keyring.get_password("MACCREv2_Sovereign_Vault", "Brave_Search")
    print(f"Gemini Key (MACCREv2_Sovereign_Vault -> MACCRE_Sovereign): {'FOUND' if gemini_key else 'NOT FOUND'}")
    print(f"Brave Key (MACCREv2_Sovereign_Vault -> Brave_Search): {'FOUND' if brave_key else 'NOT FOUND'}")
except Exception as e:
    print(f"Keyring error: {e}")

print("\n--- Raw WinCred Check ---")
class _CREDENTIAL(ctypes.Structure):
    _fields_ = [
        ('Flags', wintypes.DWORD), 
        ('Type', wintypes.DWORD), 
        ('TargetName', wintypes.LPWSTR), 
        ('Comment', wintypes.LPWSTR), 
        ('LastWritten', wintypes.FILETIME), 
        ('CredentialBlobSize', wintypes.DWORD), 
        ('CredentialBlob', ctypes.POINTER(ctypes.c_byte)), 
        ('Persist', wintypes.DWORD), 
        ('AttributeCount', wintypes.DWORD), 
        ('Attributes', ctypes.c_void_p), 
        ('TargetAlias', wintypes.LPWSTR), 
        ('UserName', wintypes.LPWSTR)
    ]

advapi32 = ctypes.WinDLL("advapi32.dll")
def check_wincred(target: str):
    cred_ptr = ctypes.POINTER(_CREDENTIAL)()
    if advapi32.CredReadW(target, 1, 0, ctypes.byref(cred_ptr)):
        print(f"Found WinCred target: {target}")
        
        # Read the raw bytes out so we can migrate them!
        blob_bytes = ctypes.string_at(cred_ptr.contents.CredentialBlob, cred_ptr.contents.CredentialBlobSize)
        # Windows credentials are often utf-16-le
        try:
            secret_str = blob_bytes.decode('utf-16-le')
            print(f"  Successfully extracted secret length: {len(secret_str)}")
            
            # Auto-migrate to Universal Vault
            keyring.set_password("MACCREv2_Sovereign_Vault", target, secret_str)
            print(f"  Migrated {target} to MACCREv2_Sovereign_Vault!")
        except Exception as e:
            print(f"  Failed to decode or migrate blob: {e}")
            
        advapi32.CredFree(cred_ptr)
    else:
        print(f"WinCred target not found: {target}")

check_wincred("MACCRE_Sovereign")
check_wincred("Brave_Search")
check_wincred("GEMINI_API_KEY")
