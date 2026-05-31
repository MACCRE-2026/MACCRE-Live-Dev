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
maccre_core/tools/storage_tools.py
=====================================
Strangler Fig StorageManager ABC for all file I/O in the MACCRE Tool Registry.

Architecture:
  StorageManager (ABC)
      └── LocalDiskAdapter     ← wraps pathlib.Path (current default)
      └── (future: GCSAdapter  ← swap to GCP Cloud Storage transparently)

Replaces raw ``open()`` / ``Path.write_text()`` calls as mandated by
.agrules rule 4 (Storage Inversion).

Gemini Function Calling schema contract:
  - Explicit Python type hints throughout.
  - Google-style docstrings (Args / Returns / Raises).
"""

import abc
import pathlib
from typing import Union


# ── Abstract Base Class ──────────────────────────────────────────────────────

class StorageManager(abc.ABC):
    """Abstract interface for reading and writing binary blobs.

    All MACCRE tools that need to persist data must accept a ``StorageManager``
    rather than hard-coding ``open()`` calls.  This guarantees zero-cost
    migration from local disk to GCP Cloud Storage (or any other backend)
    without rewriting tool logic.
    """

    @abc.abstractmethod
    def read(self, path: str) -> bytes:
        """Read the content of a file and return it as raw bytes.

        Args:
            path: Relative path within the backend's root namespace (e.g.
                ``"media/audio.wav"`` for local disk).

        Returns:
            The full file content as a ``bytes`` object.

        Raises:
            FileNotFoundError: If the object does not exist.
            OSError: On unexpected I/O errors.
        """

    @abc.abstractmethod
    def write(self, path: str, data: bytes, append: bool = False) -> None:
        """Write raw bytes to the given path, creating it if necessary.

        Args:
            path: Relative path within the backend's root namespace.
            data: Binary payload to write.

        Raises:
            OSError: If the file cannot be created or written.
        """

    @abc.abstractmethod
    def exists(self, path: str) -> bool:
        """Check whether an object exists in the backend.

        Args:
            path: Relative path within the backend's root namespace.

        Returns:
            ``True`` if the object exists, ``False`` otherwise.
        """


# ── Concrete Adapter ─────────────────────────────────────────────────────────

class LocalDiskAdapter(StorageManager):
    """Local-filesystem implementation of ``StorageManager``.

    All paths are resolved relative to ``base_dir``.  Parent directories are
    created automatically on :meth:`write`.

    Usage:
        adapter = LocalDiskAdapter(base_dir=pathlib.Path("/tmp/maccre"))
        adapter.write("media/clip.wav", pcm_bytes)
        data = adapter.read("media/clip.wav")
    """

    def __init__(self, base_dir: Union[str, pathlib.Path]) -> None:
        self._base = pathlib.Path(base_dir)

    def _resolve(self, path: str) -> pathlib.Path:
        return self._base / path

    def read(self, path: str) -> bytes:
        """Read a file from local disk relative to ``base_dir``.

        Args:
            path: Relative file path.

        Returns:
            File content as bytes.

        Raises:
            FileNotFoundError: If the file does not exist under ``base_dir``.
        """
        full = self._resolve(path)
        if not full.exists():
            raise FileNotFoundError(f"LocalDiskAdapter: '{full}' not found.")
        return full.read_bytes()

    def write(self, path: str, data: bytes, append: bool = False) -> None:
        """Write bytes to a file on local disk, creating parent dirs as needed.

        Args:
            path: Relative file path.
            data: Binary content to write.

        Raises:
            OSError: On I/O failures.
        """
        full = self._resolve(path)
        full.parent.mkdir(parents=True, exist_ok=True)
        mode = "ab" if append else "wb"
        with open(full, mode) as f:
            f.write(data)

    def exists(self, path: str) -> bool:
        """Check if a file exists on local disk.

        Args:
            path: Relative file path.

        Returns:
            ``True`` if the file exists, ``False`` otherwise.
        """
        return self._resolve(path).exists()


from maccre_core.utils.path_resolver import get_maccre_root, get_datacenter_path  # noqa: E402


# ── Project-Aware Storage Adapter ────────────────────────────────────────────
# Replaces the static LocalDiskAdapter(base_dir=__DATACENTER) so that
# write_file / read_file / file_exists route through the ACTIVE project jail
# just like admin_tools and rag_tools do via get_datacenter_path().

class ProjectAwareAdapter(StorageManager):
    """Strangler Fig adapter that routes all I/O through the currently-active
    project datacenter directory.  Calls ``get_datacenter_path()`` on every
    operation so that project switches are reflected immediately without
    recreating the manager instance.
    """

    @staticmethod
    def _resolve(path: str) -> pathlib.Path:
        parts = pathlib.PurePosixPath(path).parts
        return get_datacenter_path(*parts)

    def read(self, path: str) -> bytes:
        full = self._resolve(path)
        if not full.exists():
            raise FileNotFoundError(f"ProjectAwareAdapter: '{full}' not found.")
        return full.read_bytes()

    def write(self, path: str, data: bytes, append: bool = False) -> None:
        full = self._resolve(path)
        full.parent.mkdir(parents=True, exist_ok=True)
        mode = "ab" if append else "wb"
        with open(full, mode) as f:
            f.write(data)

    def exists(self, path: str) -> bool:
        return self._resolve(path).exists()


# Keep the old JAIL_ROOT for any legacy references; _DEFAULT_MANAGER is now project-aware.
MACCRE_JAIL_ROOT = get_maccre_root() / "__DATACENTER"
_DEFAULT_MANAGER = ProjectAwareAdapter()

def read_file(path: str) -> str:
    """Convenience wrapper: read a file via the default ``StorageManager``.

    Args:
        path: Relative path to the file.

    Returns:
        File content as a string.

    Raises:
        FileNotFoundError: If the file does not exist.
    """
    return _DEFAULT_MANAGER.read(path).decode('utf-8')


def write_file(path: str, data: str, append: bool = False) -> str:
    """Convenience wrapper: write text via the default ``StorageManager``.

    Args:
        path: Relative path for the destination file.
        data: Text content to write.

    Returns:
        A success confirmation string including the resolved path.

    Raises:
        OSError: On I/O failures.
    """
    _DEFAULT_MANAGER.write(path, data.encode('utf-8'), append)
    return f"Success: Payload written to {path}"


def write_dynamic_context(filename: str, data: str) -> str:
    """Safely write configuration files to the 02_Dynamic_Context tier.

    Unlike ``write_file``, which may be sandboxed to a session-specific
    artifacts folder by the ToolExecutor, this tool guarantees that the
    file is written strictly to the active project's 02_Dynamic_Context folder.
    Use this for persistent project configurations like voice_roster.json.

    Args:
        filename: Name of the file (e.g. ``"voice_roster.json"``). Path traversal
            is automatically stripped.
        data: Text or JSON content to write.

    Returns:
        A success confirmation string.
    """
    import pathlib
    # Strip any directory traversal or path components
    safe_name = pathlib.Path(filename).name
    path = f"02_Dynamic_Context/{safe_name}"
    _DEFAULT_MANAGER.write(path, data.encode('utf-8'), append=False)
    return f"Success: Wrote dynamic context file to {path}"



def file_exists(path: str) -> bool:
    """Convenience wrapper: check existence via the default ``StorageManager``.

    Args:
        path: Relative path to check (relative to the Jail Root).

    Returns:
        ``True`` if the object exists, ``False`` otherwise.
    """
    return _DEFAULT_MANAGER.exists(path)


def trash_file(path: str, reason: str = "", session_id: str = "", agent_id: str = "") -> str:
    """Safely delete a file by routing it through the canonical Trash Protocol.

    Delegates entirely to ``access_control.trash_file()`` which:
      - Moves the file to ``_archive/trash/`` (metadata-rich filename)
      - Logs a ``FILE_TRASHED`` event to the telemetry database
      - Preserves ``reason``, ``session_id``, and ``agent_id`` for the audit trail

    Resolves ``path`` relative to the active project (``MACCRE_ACTIVE_PROJECT``)
    if a relative path is given; an absolute path is passed through unchanged.

    Args:
        path: Relative path to the file to delete (e.g. ``"01_Raw_Source/payload.md"``),
              or an absolute path.
        reason: Optional reason for the deletion (logged to telemetry).
        session_id: Active session for audit trail.
        agent_id: Agent requesting the deletion.

    Returns:
        A confirmation message of the successful soft-delete, or a fault message.
    """
    from maccre_core.orchestration.access_control import trash_file as _ac_trash  # noqa: PLC0415

    # Resolve relative paths through the project-aware adapter so the caller
    # can use the same short form used by read_file / write_file.
    resolved = _DEFAULT_MANAGER._resolve(path) if not path.startswith(("\\", "/")) and ":" not in path else path

    return _ac_trash(resolved, reason=reason, session_id=session_id, agent_id=agent_id)

