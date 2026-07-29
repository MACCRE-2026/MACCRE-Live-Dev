# MACCREv2 Auth Layer & Security Analysis

**Classification:** Sovereign Edge Internal Audit
**Target Systems:** `windows_vault.py`, `key_ingestor.py`, `maccre_router.py`, `gemini_client.py`
**Objective:** Zero-cleartext exposure in memory/clipboards.

## 1. Executive Summary
A comprehensive audit of the MACCREv2 credential pipeline reveals that while the storage mechanism at rest (DPAPI `.bin` Vault & Windows Credential Manager) is highly secure, the **in-memory lifecycle of credentials violates zero-cleartext constraints**. API keys are currently loaded as immutable Python strings, bound to long-lived router objects, interpolated into URLs, and left susceptible to memory scraping or crash-dump extraction. Additionally, clipboard hygiene during ingestion is absent.

## 2. Current Architecture Audit

### 2.1 Storage at Rest (Secure)
*   `windows_vault.py` leverages `CryptProtectData` (DPAPI) and `CredReadW` to store credentials natively. This is highly Sovereign-compliant, utilizing the OS's protected enclave.

### 2.2 Lifecycle & Transport (Vulnerable)
*   **Long-Lived State:** `UniversalRouter` (in `maccre_router.py`) calls `get_native_credential()` upon initialization and stores the cleartext API key in memory as `self.gemini_key`.
*   **Immutable Leakage:** `GeminiClient` binds the key to `self._key`. In Python, strings are immutable. This means the cleartext key sits in the heap indefinitely, immune to standard garbage collection until the object dies, and even then, memory isn't zeroed out.
*   **Traceback Risk:** `gemini_client.py` builds HTTP request URLs using `f"{_BASE_URL}/{clean}:{action}?key={self._key}"`. If `urllib.error.HTTPError` is raised, the `exc.url` contains the cleartext API key, risking exposure in standard telemetry or console logs.

### 2.3 Key Ingestion (Vulnerable)
*   **Clipboard Contamination:** Users ingest keys via `nexus_plex.py` (which has multiple clipboard paste routines) or standard CLI. The sensitive string remains in the system clipboard until overwritten by the user, risking accidental pasting into untrusted applications (e.g., chat clients, browsers).

---

## 3. Sovereign Edge Security Enhancements

To enforce absolute hardware-level sovereignty, we must implement a **Just-In-Time (JIT) Credential Pipeline** with destructive memory teardown.

### Recommendation 1: Shift to Header-Based Authentication
**Action:** Modify `gemini_client.py`.
**Rationale:** Passing API keys in URL query parameters (`?key=...`) is an anti-pattern that exposes credentials to proxy logs and exception tracebacks.
**Implementation:**
Remove `?key=` from the URL and inject the key into the HTTP headers instead:
```python
# In maccre_core/_net/gemini_client.py -> _make_req
extra_headers = {"x-goog-api-key": self._key_provider()}
```

### Recommendation 2: Destructive `SecureString` and JIT Resolution
**Action:** Introduce a `SecureString` abstraction that uses `ctypes.memset` to aggressively overwrite the string's memory blocks.
**Rationale:** Python's garbage collector only frees memory references; it does not zero out the physical RAM. We must bypass the Python VM and interact directly with the C-struct underlying the string.
**Implementation:**
Instead of `self.gemini_key = "AIza..."`, objects will receive a JIT lambda:
```python
# Fetch key right before HTTP dispatch, and immediately wipe it
raw_key = get_native_credential("MACCRE_Sovereign")
try:
    # Build request headers and dispatch
finally:
    wipe_string(raw_key)
```

**C-Level Wipe Utility (Proposed for `windows_vault.py` or new `crypto_utils.py`):**
```python
import ctypes
import sys

def wipe_string(target: str) -> None:
    """Overwrites the CPython string buffer in RAM with null bytes."""
    if not isinstance(target, str):
        return
    # CPython string internal structure offset (approx 48-56 bytes depending on architecture/encoding)
    # A safer approach using ctypes to target the memory block:
    buffer_size = sys.getsizeof(target)
    address = id(target)
    
    # Cast the address to a writable c_char pointer and overwrite
    # WARNING: This mutates an immutable type. Ensure the string is NOT interned.
    # (Strings from ctypes.string_at.decode() are usually safely un-interned).
    ctypes.memset(address, 0, buffer_size)
```

### Recommendation 3: Autonomous Clipboard Hygiene
**Action:** Implement `ctypes`-driven clipboard clearing in `key_ingestor.py`.
**Rationale:** Prevent remnant credential leakage after a successful `ingest_key` operation.
**Implementation:**
```python
import ctypes

def clear_windows_clipboard():
    user32 = ctypes.windll.user32
    if user32.OpenClipboard(None):
        try:
            user32.EmptyClipboard()
        finally:
            user32.CloseClipboard()
```
*Inject this into `key_ingestor.py` right after `protect_string(target_name, raw_key)` returns success.*

### Recommendation 4: Discard Router-Level Credentials
**Action:** Refactor `UniversalRouter` (`maccre_router.py`).
**Rationale:** The router should not cache keys.
**Implementation:**
Instead of assigning `self.gemini_key = get_native_credential(...)`, modify `GeminiClient` to accept a `Callable[[], str]` or call `get_native_credential()` internally *only* at the exact moment `urllib.request.urlopen` is invoked.

---

## 4. Execution Plan (OmniBuilder Compliant)
1. **Create `maccre_core/orchestration/crypto_utils.py`**: House `wipe_string` and `clear_windows_clipboard`.
2. **Patch `windows_vault.py`**: Ensure all decoded strings bypass Python's string interning so they can be safely wiped.
3. **Patch `key_ingestor.py`**: Call `clear_windows_clipboard()` upon successful fingerprint match.
4. **Patch `gemini_client.py`**: Migrate `?key=` to `x-goog-api-key` header.
5. **Patch `maccre_router.py`**: Remove all `self.gemini_key`, `self.anthropic_key` state vars. Pass resolver functions down instead.
