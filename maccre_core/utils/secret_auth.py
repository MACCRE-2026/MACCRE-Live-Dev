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
maccre_core/utils/secret_auth.py
================================
**Paranoia Mode — hardware-token topology authentication. CURRENTLY DISABLED.**

Read the state before the description: :data:`PARANOIA_MODE_ENABLED` is ``False``,
so :func:`is_topology_approved` returns ``True`` for every topology and **no
authentication of any kind is performed.** Nothing in this module gates execution
today.

WHAT IT IS FOR
--------------
The intent is to abstract credential access away from the system behind a physical
key: a USB stick whose volume serial hashes to a known value must be inserted for
the duration of a session, and topologies are stamped as approved only while it is
present. The stamp is written to an NTFS Alternate Data Stream
(``topology.csv:maccre_auth``) rather than a visible file, so a scan of the
directory does not reveal which topologies are authorised.

The operator's own description: *a layer of paranoia.* It is deliberately kept
rather than deleted, and it is deliberately inert rather than half-enforcing.

WHY IT IS DISABLED RATHER THAN REMOVED
--------------------------------------
It was switched off to streamline agent execution — a headless swarm cannot insert
a USB stick. The mechanism is sound and wanted later, so the implementation stays.
See the register entry *Paranoia Mode — finish the hardware-token topology gate*
for the work required to turn it back on.

HISTORY, RECORDED BECAUSE IT WAS A DOCTRINE FAILURE
---------------------------------------------------
Until 2026-09-03 this module's docstring read *"Air-Gap Steganographic Hardware
Authentication. Approves topologies without exposing triggers to programmatic
scanners. Uses NTFS Alternate Data Streams and Hardware tokens"* — present tense,
while :func:`is_topology_approved` was already ``return True``. Three separate
places asserted a security control that did not exist: this docstring,
``pattern_executor``'s, and ``Analysis/Wave1/05_memory_schemas_utils_ledger.md``.

That is Doctrine 5, and the same shape as the doctrine's own ``--smart`` incident —
documented as implemented, never read — but worse in kind, because a reader
concludes topologies are hardware-gated when they are not. A disabled control must
announce that it is disabled.

Two further consequences were fixed at the same time:

* ``from ctypes import wintypes`` sat at **module scope**, which cannot import on a
  non-Windows host. ``topology_engine._pull_from_csv`` imported this module
  **unguarded**, so the topology loader — on every execution path in the system —
  was Windows-only, in service of a gate that always returned ``True``. The Windows
  imports are now **lazy**, inside the functions that need them, so this module
  imports cleanly on any platform.
* ``pattern_executor`` wrote the ADS stamp unconditionally and logged
  ``ADS auth stamp written``, implying an authentication step that was not
  happening.
"""

import hashlib
import logging
import os
import sys
from string import ascii_uppercase

_log = logging.getLogger(__name__)

#: The single seam controlling whether hardware authentication is enforced.
#:
#: ``False`` means :func:`is_topology_approved` short-circuits to ``True`` and no
#: check occurs. Flip this to ``True`` only alongside the work in the register
#: entry *Paranoia Mode — finish the hardware-token topology gate*: enabling it
#: without a token present would refuse every topology, and enabling it on a
#: non-Windows host would refuse every topology too, because the stamp it looks for
#: is an NTFS construct.
PARANOIA_MODE_ENABLED: bool = False

#: Marker written into the Alternate Data Stream when a topology is approved.
AUTH_STAMP_TOKEN = "O_AUTH_VALID"

#: Alternate Data Stream suffix appended to the topology path.
AUTH_STAMP_STREAM = "maccre_auth"

#: ``GetDriveTypeW`` return value for a removable volume.
_DRIVE_REMOVABLE = 2


def is_paranoia_mode_enabled() -> bool:
    """Report whether hardware-token authentication is actually being enforced.

    Exists so callers and tests can ask the question rather than infer it from
    behaviour. :func:`is_topology_approved` returning ``True`` is ambiguous on its
    own — it could mean *approved* or *not checked* — and Doctrine 3's rule against
    folding an ambiguous state into a success applies to authorisation answers as
    much as to task outcomes.
    """
    return PARANOIA_MODE_ENABLED


def is_windows() -> bool:
    """Whether the NTFS/Win32 facilities this module needs are available."""
    return sys.platform == "win32"


def _get_removable_drives() -> list[str]:
    """Scan for plugged-in removable USB drives. Windows only; ``[]`` elsewhere."""
    if not is_windows():
        return []
    import ctypes  # noqa: PLC0415 - lazy: keeps this module importable off Windows

    drives: list[str] = []
    bitmask = ctypes.windll.kernel32.GetLogicalDrives()  # type: ignore[attr-defined]
    for letter in ascii_uppercase:
        if bitmask & 1:
            drive_path = f"{letter}:\\"
            drive_type = ctypes.windll.kernel32.GetDriveTypeW(  # type: ignore[attr-defined]
                ctypes.c_wchar_p(drive_path)
            )
            if drive_type == _DRIVE_REMOVABLE:
                drives.append(letter)
        bitmask >>= 1
    return drives


def _get_volume_serial(drive_letter: str) -> str | None:
    """Return the hex volume serial for a drive, or ``None``. Windows only."""
    if not is_windows():
        return None
    import ctypes  # noqa: PLC0415 - lazy, see _get_removable_drives
    from ctypes import wintypes  # noqa: PLC0415 - ctypes.wintypes does not exist off Windows

    lp_root_path_name = f"{drive_letter}:\\"
    volume_serial_number = wintypes.DWORD()
    success = ctypes.windll.kernel32.GetVolumeInformationW(  # type: ignore[attr-defined]
        ctypes.c_wchar_p(lp_root_path_name),
        None, 0,
        ctypes.byref(volume_serial_number),
        None, None, None, 0,
    )
    if success:
        return hex(volume_serial_number.value)
    return None


def stamp_topology(csv_path: str, target_hash: str) -> str:
    """Validate the hardware key and, on a match, stamp the topology's ADS.

    Unchanged in behaviour from the pre-2026-09-03 implementation, other than being
    safe to call on a non-Windows host. Returns a human-readable result string
    rather than raising, because its callers log it.

    Note that this function performs a **real** check even while
    :data:`PARANOIA_MODE_ENABLED` is ``False`` — it is the enrolment half, and
    stamping is harmless when nothing reads the stamp. What it must not do is imply
    to a caller that execution was gated, which is why the result strings say what
    happened rather than that anything was authorised.
    """
    if not os.path.exists(csv_path):
        return "FAULT: Topology target does not exist."

    if not is_windows():
        return "SKIPPED: Alternate Data Streams require NTFS; no stamp written."

    removable_drives = _get_removable_drives()
    if not removable_drives:
        return "DENIED: Hardware token missing."

    authorized = False
    for drive in removable_drives:
        serial = _get_volume_serial(drive)
        if serial and hashlib.sha256(serial.encode("utf-8")).hexdigest() == target_hash:
            authorized = True
            break

    if not authorized:
        return "DENIED: Invalid hardware token connected."

    ads_path = f"{csv_path}:{AUTH_STAMP_STREAM}"
    try:
        with open(ads_path, "w", encoding="utf-8") as handle:
            handle.write(AUTH_STAMP_TOKEN)
        return "SUCCESS: Hardware token matched; topology stamped."
    except OSError as exc:
        return f"CRITICAL: Failed to write Alternate Data Stream: {exc}"


def has_auth_stamp(csv_path: str) -> bool:
    """Whether the topology carries a valid ADS approval stamp.

    Always ``False`` off Windows, because the stamp is an NTFS construct and cannot
    exist. That is the honest answer rather than a permissive one: a check that
    cannot be performed has not passed.
    """
    if not is_windows():
        return False
    ads_path = f"{csv_path}:{AUTH_STAMP_STREAM}"
    try:
        with open(ads_path, encoding="utf-8") as handle:
            return handle.read().strip() == AUTH_STAMP_TOKEN
    except OSError:
        return False


def is_topology_approved(csv_path: str) -> bool:
    """Whether a topology is cleared to run.

    **While Paranoia Mode is disabled this returns ``True`` unconditionally and
    performs no check.** Callers must not read a ``True`` here as evidence that
    anything was verified; ask :func:`is_paranoia_mode_enabled` for that.
    """
    if not PARANOIA_MODE_ENABLED:
        return True
    approved = has_auth_stamp(csv_path)
    if not approved:
        _log.warning(
            "[ParanoiaMode] Topology refused, no valid auth stamp: %s", csv_path
        )
    return approved
