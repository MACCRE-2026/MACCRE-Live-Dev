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
maccre_core/drive_watcher.py
==============================
Google Drive Sovereign Inbox — File System Watcher Daemon.

Phase 17: Watches an inbox folder for new MACCRE_Swarm_Request.xlsx files
          and triggers full swarm materialisation + execution.

Phase 19: After each RUN_COMPLETE, automatically exports a database nugget
          to Google Drive so other devices can sync the project memory.

Phase 20: Primary trigger is now *_APPROVED.xlsx pattern anywhere inside
          __DATACENTER (recursive watch).  Inbox folder watch retained as
          fallback / legacy mode via --mode inbox flag.

Trigger decision:
  --mode approved (default):
      Watches __DATACENTER recursively for files whose stem ends with
      "_APPROVED" and whose suffix is ".xlsx".  On detection, the
      "_APPROVED" suffix is stripped from the stem to get the project name,
      and the file is moved to __DATACENTER/<PROJECT>/04_Code_Artifacts/
      with an _EXECUTED_<TIMESTAMP> suffix after completion.

  --mode inbox (legacy):
      Watches the configured inbox folder for any new .xlsx file.

Usage:
    python maccre.py watch
    python maccre.py watch --mode inbox --inbox "G:\\My Drive\\__MACCREv2_Inbox"

Omni-compliance:
    - All file handles closed in try/finally.
    - All telemetry written to GLOBAL/03_Agent_Ledgers/watcher_telemetry.json.
    - No print() — all output via logger.
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import shutil
import sys
import threading
import time
from pathlib import Path
from typing import Any

logger = logging.getLogger("maccre_core")

_DEFAULT_INBOX = os.environ.get(
    "MACCRE_DRIVE_INBOX",
    r"G:\My Drive\__MACCREv2_Inbox",
)
_SETTLE_SECS = 4          # wait after file event (Drive may still be writing)


# ── Telemetry ledger ───────────────────────────────────────────────────────────


def _write_ledger(entry: dict[str, Any]) -> None:
    """Append a JSON event record to the watcher telemetry ledger."""
    try:
        from maccre_core.utils.path_resolver import get_maccre_root  # noqa: PLC0415
        ledger_dir = get_maccre_root() / "__DATACENTER" / "GLOBAL" / "03_Agent_Ledgers"
        ledger_dir.mkdir(parents=True, exist_ok=True)
        ledger_path = ledger_dir / "watcher_telemetry.json"

        records: list[dict[str, Any]] = []
        if ledger_path.exists():
            try:
                records = json.loads(ledger_path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                records = []

        entry.setdefault("timestamp", time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))
        records.append(entry)
        ledger_path.write_text(json.dumps(records, indent=2), encoding="utf-8")
    except Exception as exc:  # noqa: BLE001
        logger.warning("[Watcher] Could not write telemetry ledger: %s", exc)


# ── Toast notification ─────────────────────────────────────────────────────────


def _notify(title: str, message: str) -> None:
    """Windows toast notification — silently skipped if unavailable."""
    try:
        from win10toast import ToastNotifier  # type: ignore[import-untyped]  # noqa: PLC0415
        notifier = ToastNotifier()
        notifier.show_toast(title, message, duration=8, threaded=True)
    except Exception:  # noqa: BLE001
        logger.debug("[Watcher] Toast notification skipped (win10toast unavailable).")


# ── Nugget auto-export (Phase 19) ─────────────────────────────────────────────


def _auto_export_nugget(project_name: str) -> None:
    """Export a database nugget to Drive after a completed run.

    Non-fatal — if Drive is not mounted or export fails, the run result
    is unaffected and only a warning is logged.
    """
    try:
        from maccre_core.tools.sync_tools import export_project_nugget  # noqa: PLC0415
        result = export_project_nugget(project_name)
        logger.info("[Watcher] %s", result)
        _write_ledger({"event": "NUGGET_EXPORTED", "project": project_name, "result": result[:200]})
    except Exception as exc:  # noqa: BLE001
        logger.warning("[Watcher] Nugget export failed (non-fatal): %s", exc)
        _write_ledger({"event": "NUGGET_EXPORT_SKIPPED", "project": project_name, "reason": str(exc)})


# ── Per-file processing ────────────────────────────────────────────────────────


def _process_sheet(xlsx_path: Path) -> None:
    """Parse, materialise, ignite, run, export nugget, and archive a workbook."""
    logger.info("[Watcher] Processing: %s", xlsx_path)
    _write_ledger({"event": "DETECTED", "file": str(xlsx_path)})

    # ── 1. Parse ─────────────────────────────────────────────────────────────
    try:
        from maccre_core.tools.sheet_parser import parse_workbook  # noqa: PLC0415
        parsed = parse_workbook(xlsx_path)
    except Exception as exc:  # noqa: BLE001
        logger.error("[Watcher] Parse failed for %s: %s", xlsx_path.name, exc)
        _write_ledger({"event": "PARSE_ERROR", "file": str(xlsx_path), "error": str(exc)})
        _notify("MACCRE -- Parse Error", f"{xlsx_path.name}: {exc}")
        return

    logger.info("[Watcher] Parsed: project=%s  agents=%d  nodes=%d",
                parsed.project_name, len(parsed.agents), len(parsed.topology))

    # ── 2. Materialise ───────────────────────────────────────────────────────
    try:
        from maccre_core.tools.sheet_parser import materialise_from_sheet  # noqa: PLC0415
        mat_result = materialise_from_sheet(xlsx_path)
    except Exception as exc:  # noqa: BLE001
        logger.error("[Watcher] Materialise failed: %s", exc)
        _write_ledger({"event": "MATERIALISE_ERROR", "project": parsed.project_name, "error": str(exc)})
        _notify("MACCRE -- Materialise Error", str(exc))
        return

    if "[SHEET_FAULT]" in mat_result or "[DESIGN_FAULT]" in mat_result:
        logger.error("[Watcher] Materialise fault: %s", mat_result)
        _write_ledger({"event": "MATERIALISE_FAULT", "project": parsed.project_name, "result": mat_result})
        _notify("MACCRE -- Materialise Fault", mat_result[:120])
        return

    logger.info("[Watcher] Materialised: %s", parsed.project_name)
    _write_ledger({"event": "MATERIALISED", "project": parsed.project_name})

    # Determine payload
    payload_file = "input.md"
    if parsed.payload_path:
        payload_file = Path(parsed.payload_path).name
    elif not parsed.payload_text.strip():
        logger.warning("[Watcher] No payload — skipping ignition.")
        _notify("MACCRE -- No Payload", f"Project {parsed.project_name} materialised without payload.")
        return

    # ── 3. Ignite ─────────────────────────────────────────────────────────────
    try:
        from maccre_core.tools.admin_tools import ignite_swarm  # noqa: PLC0415
        ignite_result = ignite_swarm(
            payload_path_relative=payload_file,
            starting_node=parsed.start_node,
        )
        logger.info("[Watcher] Ignition: %s", ignite_result)
        _write_ledger({"event": "IGNITED", "project": parsed.project_name, "result": ignite_result})
    except Exception as exc:  # noqa: BLE001
        logger.error("[Watcher] Ignition failed: %s", exc)
        _write_ledger({"event": "IGNITE_ERROR", "project": parsed.project_name, "error": str(exc)})
        _notify("MACCRE -- Ignition Error", str(exc))
        return

    if "[ADMIN_FAULT]" in ignite_result:
        _notify("MACCRE -- Ignition Fault", ignite_result[:120])
        return

    # ── 4. Run ────────────────────────────────────────────────────────────────
    logger.info("[Watcher] Starting swarm run: %s", parsed.project_name)
    _write_ledger({"event": "RUN_STARTED", "project": parsed.project_name})
    start_ts = time.time()

    try:
        from maccre_core.tools.admin_tools import run_swarm  # noqa: PLC0415
        run_result = run_swarm(project_name=parsed.project_name)
        elapsed = round(time.time() - start_ts, 1)
        logger.info("[Watcher] Swarm complete in %.1fs: %s", elapsed, run_result[:80])
        _write_ledger({
            "event": "RUN_COMPLETE",
            "project": parsed.project_name,
            "elapsed_s": elapsed,
            "result_prefix": run_result[:120],
        })
    except Exception as exc:  # noqa: BLE001
        elapsed = round(time.time() - start_ts, 1)
        logger.error("[Watcher] Swarm run failed after %.1fs: %s", elapsed, exc)
        _write_ledger({"event": "RUN_ERROR", "project": parsed.project_name, "error": str(exc)})
        _notify("MACCRE -- Run Error", f"{parsed.project_name}: {exc}")
        return

    # ── 5. Export nugget (Phase 19) ───────────────────────────────────────────
    _auto_export_nugget(parsed.project_name)

    # ── 6. Archive workbook (Phase 20) ────────────────────────────────────────
    _archive_workbook(xlsx_path, parsed.project_name)

    # ── 7. Notify ─────────────────────────────────────────────────────────────
    _notify(
        "MACCRE -- Swarm Complete",
        f"Project '{parsed.project_name}' finished in {elapsed}s.\n"
        f"Media: __DataCenter\\{parsed.project_name}\\05_Rendered_Media\\",
    )


def _archive_workbook(path: Path, project_name: str) -> None:
    """Move the executed workbook to the project's 04_Code_Artifacts folder.

    Phase 20: replaces the old .processed rename.  The original workbook
    lands permanently in the project silo for audit trail.
    """
    try:
        from maccre_core.utils.path_resolver import get_maccre_root  # noqa: PLC0415
        archive_dir = (
            get_maccre_root() / "__DATACENTER" / project_name / "04_Code_Artifacts"
        )
        archive_dir.mkdir(parents=True, exist_ok=True)
        ts = time.strftime("%Y%m%d_%H%M%S", time.gmtime())
        stem = path.stem.replace("_APPROVED", "")
        dest = archive_dir / f"{stem}_EXECUTED_{ts}.xlsx"
        shutil.move(str(path), str(dest))
        logger.info("[Watcher] Workbook archived to %s", dest.name)
    except OSError as exc:
        logger.warning("[Watcher] Could not archive workbook: %s", exc)


# ── APPROVED-pattern file filter (Phase 20) ────────────────────────────────────


def _is_approved_xlsx(path: Path) -> bool:
    """Return True if file matches the *_APPROVED.xlsx trigger pattern."""
    return (
        path.suffix.lower() == ".xlsx"
        and path.stem.upper().endswith("_APPROVED")
        and not path.stem.startswith(".")
    )


# ── Shared handler ─────────────────────────────────────────────────────────────


class _DispatchHandler:
    """File-system event dispatcher — mode-agnostic."""

    def __init__(self, mode: str) -> None:
        self.mode = mode   # "approved" | "inbox"
        self._seen: set[str] = set()

    def _should_dispatch(self, path: Path) -> bool:
        if path.suffix.lower() != ".xlsx":
            return False
        if self.mode == "approved":
            return _is_approved_xlsx(path)
        # inbox mode: any xlsx that isn't already archived
        return not (
            "_EXECUTED_" in path.stem
            or path.stem.endswith("_APPROVED")
        )

    def dispatch_if_new(self, path: Path) -> None:
        key = str(path)
        if key in self._seen:
            return
        if not self._should_dispatch(path):
            return
        self._seen.add(key)
        logger.info("[Watcher] Trigger detected: %s  (settling %ds...)", path.name, _SETTLE_SECS)
        time.sleep(_SETTLE_SECS)
        threading.Thread(target=_process_sheet, args=(path,), daemon=True).start()


# ── Watchdog watcher ───────────────────────────────────────────────────────────


def _watch_with_watchdog(watch_root: Path, recursive: bool) -> None:
    from watchdog.events import FileSystemEventHandler  # type: ignore[import-untyped]
    from watchdog.observers import Observer  # type: ignore[import-untyped]

    mode = "approved" if recursive else "inbox"
    handler_inst = _DispatchHandler(mode)

    class _Bridge(FileSystemEventHandler):  # type: ignore[misc]
        def on_created(self, event: Any) -> None:  # type: ignore[override]
            if not event.is_directory:
                handler_inst.dispatch_if_new(Path(event.src_path))

        def on_moved(self, event: Any) -> None:  # type: ignore[override]
            # Google Drive creates files via rename-from-temp
            if not event.is_directory:
                handler_inst.dispatch_if_new(Path(event.dest_path))

    observer = Observer()
    observer.schedule(_Bridge(), str(watch_root), recursive=recursive)
    observer.start()
    logger.info(
        "[Watcher] watchdog observer started | root=%s recursive=%s mode=%s",
        watch_root, recursive, mode,
    )
    try:
        while True:
            time.sleep(2)
    except KeyboardInterrupt:
        logger.info("[Watcher] Keyboard interrupt — stopping observer.")
    finally:
        observer.stop()
        observer.join()


def _watch_polling(watch_root: Path, recursive: bool, interval: float = 5.0) -> None:
    mode = "approved" if recursive else "inbox"
    logger.warning("[Watcher] watchdog unavailable — polling every %gs (mode=%s)", interval, mode)
    handler_inst = _DispatchHandler(mode)
    while True:
        try:
            pattern = "**/*.xlsx" if recursive else "*.xlsx"
            for entry in watch_root.glob(pattern):
                if entry.is_file():
                    handler_inst.dispatch_if_new(entry)
        except (OSError, PermissionError) as exc:
            logger.warning("[Watcher] Scan error: %s", exc)
        time.sleep(interval)


# ── Public entrypoint ──────────────────────────────────────────────────────────


def start_watcher(
    inbox_path: str | None = None,
    mode: str = "approved",
) -> None:
    """Start the Drive inbox watcher.  Blocks until KeyboardInterrupt.

    Args:
        inbox_path: Override the watch root path.
                    - approved mode: defaults to __DATACENTER root
                    - inbox mode: defaults to MACCRE_DRIVE_INBOX env / G:\\My Drive\\__MACCREv2_Inbox
        mode:       "approved" — watch __DATACENTER recursively for *_APPROVED.xlsx (default)
                    "inbox"    — watch a dedicated inbox folder for any .xlsx (legacy)
    """
    if mode == "approved":
        from maccre_core.utils.path_resolver import get_maccre_root  # noqa: PLC0415
        watch_root = Path(inbox_path) if inbox_path else get_maccre_root() / "__DATACENTER"
        recursive = True
    else:
        watch_root = Path(inbox_path or _DEFAULT_INBOX)
        recursive = False

    if not watch_root.exists():
        logger.info("[Watcher] Watch root not found — creating: %s", watch_root)
        try:
            watch_root.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            logger.error("[Watcher] Cannot create watch root: %s", exc)
            sys.exit(1)

    logger.info("[Watcher] ================================================================")
    logger.info("[Watcher] MACCRE Drive Watcher -- ACTIVE")
    logger.info("[Watcher] Mode:       %s", mode.upper())
    logger.info("[Watcher] Watch root: %s", watch_root)
    if mode == "approved":
        logger.info("[Watcher] Trigger:    Rename any workbook to *_APPROVED.xlsx to fire a swarm.")
    else:
        logger.info("[Watcher] Trigger:    Drop any .xlsx file here to fire a swarm.")
    logger.info("[Watcher] ================================================================")
    _write_ledger({"event": "WATCHER_STARTED", "mode": mode, "watch_root": str(watch_root)})

    try:
        _watch_with_watchdog(watch_root, recursive)
    except ImportError:
        _watch_polling(watch_root, recursive)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    ap = argparse.ArgumentParser(description="MACCRE Drive Watcher")
    ap.add_argument("--inbox", default=None, help="Override watch root path")
    ap.add_argument(
        "--mode",
        choices=["approved", "inbox"],
        default="approved",
        help="approved (default): watch __DATACENTER for *_APPROVED.xlsx; inbox: dedicated folder",
    )
    args = ap.parse_args()
    start_watcher(inbox_path=args.inbox, mode=args.mode)
