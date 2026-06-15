import ctypes
from ctypes import wintypes

class _FILETIME(ctypes.Structure):
    _fields_ = [("dwLow", wintypes.DWORD), ("dwHigh", wintypes.DWORD)]

class _CREDENTIAL(ctypes.Structure):
    _fields_ = [
        ("Flags", wintypes.DWORD),
        ("Type", wintypes.DWORD),
        ("TargetName", ctypes.c_wchar_p),
        ("Comment", ctypes.c_wchar_p),
        ("LastWritten", _FILETIME),
        ("CredentialBlobSize", wintypes.DWORD),
        ("CredentialBlob", ctypes.POINTER(ctypes.c_byte)),
        ("Persist", wintypes.DWORD),
        ("AttributeCount", wintypes.DWORD),
        ("Attributes", ctypes.c_void_p),
        ("TargetAlias", ctypes.c_wchar_p),
        ("UserName", ctypes.c_wchar_p),
    ]

def enum_creds():
    advapi32 = ctypes.WinDLL("advapi32.dll")
    advapi32.CredEnumerateW.restype = wintypes.BOOL
    advapi32.CredEnumerateW.argtypes = [
        ctypes.c_wchar_p, wintypes.DWORD, ctypes.POINTER(wintypes.DWORD),
        ctypes.POINTER(ctypes.POINTER(ctypes.POINTER(_CREDENTIAL)))
    ]
    
    count = wintypes.DWORD()
    creds_raw = ctypes.POINTER(ctypes.POINTER(_CREDENTIAL))()
    
    ok = advapi32.CredEnumerateW(None, 0, ctypes.byref(count), ctypes.byref(creds_raw))
    if ok:
        for i in range(count.value):
            cred = creds_raw[i].contents
            name = cred.TargetName
            if "BRAVE" in name.upper():
                print(f"Found: {name}, Type: {cred.Type}")
                blob = bytes(cred.CredentialBlob[:cred.CredentialBlobSize])
                print(f"Decoded: {blob.decode('utf-16-le', errors='replace')}")

enum_creds()
