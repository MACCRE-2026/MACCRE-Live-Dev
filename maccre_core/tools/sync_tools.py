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
maccre_core/tools/sync_tools.py
================================
Database Nugget Protocol -- Cross-Device Project Memory Sync.

After any swarm run completes on Device A, this module exports a compressed
snapshot of the project's cognitive state (ChromaDB vectors + SQLite ledgers)
to Google Drive. Any other device running MACCREv2 can pull these "nuggets"
and immediately work with the full project memory -- without any custom sync
server.

Architecture:
    Device A (post-swarm) --> export_project_nugget() --+
                                                         |  G: My Drive __DataCenter
    Device B (on demand)  <-- import_project_nuggets() <-+  <PROJECT> _nuggets

Nugget file naming:
    <DEVICE_ID>_vectors_<YYYYMMDD_HHmmss>.json      -- ChromaDB collections
    <DEVICE_ID>_thoughts_<YYYYMMDD_HHmmss>.db.gz    -- thoughts.db WAL snapshot
    <DEVICE_ID>_queue_<YYYYMMDD_HHmmss>.json        -- completed swarm jobs

Device ID: socket.gethostname() -- simple, no registration required.

Omni-compliance:
    - All file handles closed in try/finally.
    - All telemetry via logger (no print).
    - All telemetry appended to 03_Agent_Ledgers/watcher_telemetry.json.
"""
from __future__ import annotations

import gzip
import json
import logging
import socket
import sqlite3
import time
from pathlib import Path
from typing import Any

logger = logging.getLogger("maccre_core")

_NUGGETS_DIRNAME = "_nuggets"
_MAX_QUEUE_ROWS = 100   # only export the last N completed/failed jobs


# ── Helpers ────────────────────────────────────────────────────────────────────


def _device_id() -> str:
    """Stable, human-readable device identifier — hostname normalised to FS-safe."""
    return socket.gethostname().replace(" ", "_").replace(".", "-")


def _ts() -> str:
    return time.strftime("%Y%m%d_%H%M%S", time.gmtime())


def _nuggets_dir(project_name: str) -> Path:
    """Resolve the Drive-synced nuggets folder for a project."""
    from maccre_core.utils.path_resolver import get_maccre_root  # noqa: PLC0415

    # Prefer the Google Drive junction path so nuggets land on Drive directly.
    # Falls back to the local __DATACENTER path if Drive is not mounted.
    drive_base = Path(r"G:\My Drive\__DataCenter")
    local_base = get_maccre_root() / "__DATACENTER"

    base = drive_base if drive_base.exists() else local_base
    nuggets = base / project_name / _NUGGETS_DIRNAME
    nuggets.mkdir(parents=True, exist_ok=True)
    return nuggets


def _local_chroma_path(project_name: str) -> Path:
    from maccre_core.utils.path_resolver import get_maccre_root  # noqa: PLC0415
    return get_maccre_root() / "__DATACENTER" / project_name / "chroma_db"


def _local_thoughts_path(project_name: str) -> Path:
    from maccre_core.utils.path_resolver import get_maccre_root  # noqa: PLC0415
    return get_maccre_root() / "__DATACENTER" / project_name / "thoughts.db"


def _local_queue_path(project_name: str) -> Path:
    from maccre_core.utils.path_resolver import get_maccre_root  # noqa: PLC0415
    return get_maccre_root() / "__DATACENTER" / project_name / "swarm_queue.db"


def _write_telemetry(entry: dict[str, Any]) -> None:
    """Append a JSON event to the global watcher telemetry ledger."""
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
        logger.warning("[SyncTools] Telemetry write failed: %s", exc)


# ── ChromaDB export ────────────────────────────────────────────────────────────


def _export_chroma(project_name: str, nuggets_dir: Path, device_id: str, ts: str) -> dict[str, Any]:
    """Serialize all collections for a project to a JSON nugget file via KnowledgeStore."""
    try:
        from maccre_core.memory import get_knowledge_store  # noqa: PLC0415

        store = get_knowledge_store(project_name)
        collections = store.list_collections()
        if not collections:
            return {"status": "skipped", "reason": "no collections found"}

        payload: dict[str, Any] = {
            "device_id": device_id,
            "project": project_name,
            "exported_at": ts,
            "collections": {},
        }

        doc_count = 0
        for col_name in collections:
            pins = store.get_all(col_name)
            payload["collections"][col_name] = {
                "ids":        [p.doc_id for p in pins],
                "documents":  [p.text for p in pins],
                "metadatas":  [p.metadata for p in pins],
                "embeddings": [p.vector for p in pins if p.vector is not None],
            }
            doc_count += len(pins)

        out_path = nuggets_dir / f"{device_id}_vectors_{ts}.json"
        out_path.write_text(json.dumps(payload), encoding="utf-8")
        logger.info(
            "[SyncTools] Store export: %d collections, %d docs -> %s",
            len(collections), doc_count, out_path.name,
        )
        return {"status": "ok", "collections": len(collections), "docs": doc_count, "file": out_path.name}
    except Exception as exc:  # noqa: BLE001
        logger.error("[SyncTools] Store export failed: %s", exc)
        return {"status": "error", "error": str(exc)}


# ── thoughts.db export ─────────────────────────────────────────────────────────


def _export_thoughts(project_name: str, nuggets_dir: Path, device_id: str, ts: str) -> dict[str, Any]:
    """WAL checkpoint + gzip compress thoughts.db into a nugget."""
    thoughts_path = _local_thoughts_path(project_name)
    if not thoughts_path.exists():
        return {"status": "skipped", "reason": "thoughts.db not found"}

    try:
        # Force WAL checkpoint so all in-memory pages are flushed to the main DB file
        con = sqlite3.connect(str(thoughts_path), check_same_thread=False)
        try:
            con.execute("PRAGMA wal_checkpoint(FULL)")
        finally:
            con.close()

        out_path = nuggets_dir / f"{device_id}_thoughts_{ts}.db.gz"
        raw = thoughts_path.read_bytes()
        with gzip.open(str(out_path), "wb") as gz:
            gz.write(raw)

        size_kb = round(out_path.stat().st_size / 1024, 1)
        logger.info("[SyncTools] thoughts.db exported: %skB gzip -> %s", size_kb, out_path.name)
        return {"status": "ok", "size_kb": size_kb, "file": out_path.name}
    except Exception as exc:  # noqa: BLE001
        logger.error("[SyncTools] thoughts.db export failed: %s", exc)
        return {"status": "error", "error": str(exc)}


# ── swarm_queue.db export ──────────────────────────────────────────────────────


def _export_queue(project_name: str, nuggets_dir: Path, device_id: str, ts: str) -> dict[str, Any]:
    """Export completed / failed job records from swarm_queue.db as JSON."""
    queue_path = _local_queue_path(project_name)
    if not queue_path.exists():
        return {"status": "skipped", "reason": "swarm_queue.db not found"}

    try:
        con = sqlite3.connect(str(queue_path), check_same_thread=False, timeout=5)
        con.row_factory = sqlite3.Row
        try:
            rows = con.execute(
                "SELECT * FROM swarm_queue WHERE status IN ('COMPLETE','FAILED') "
                "ORDER BY rowid DESC LIMIT ?",
                (_MAX_QUEUE_ROWS,),
            ).fetchall()
        finally:
            con.close()

        records = [dict(r) for r in rows]
        payload = {"device_id": device_id, "project": project_name, "exported_at": ts, "jobs": records}
        out_path = nuggets_dir / f"{device_id}_queue_{ts}.json"
        out_path.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
        logger.info("[SyncTools] Queue export: %d jobs -> %s", len(records), out_path.name)
        return {"status": "ok", "jobs": len(records), "file": out_path.name}
    except Exception as exc:  # noqa: BLE001
        logger.error("[SyncTools] Queue export failed: %s", exc)
        return {"status": "error", "error": str(exc)}


# ── Public: export ─────────────────────────────────────────────────────────────


def export_project_nugget(project_name: str) -> str:
    """Export a compressed cognitive snapshot of a project to Google Drive.

    Exports three artifacts to G:\\My Drive\\__DataCenter\\<PROJECT>\\_nuggets\\:
      - <DEVICE_ID>_vectors_<TS>.json        ChromaDB collections (docs + embeddings)
      - <DEVICE_ID>_thoughts_<TS>.db.gz      thoughts.db WAL snapshot (gzip)
      - <DEVICE_ID>_queue_<TS>.json          Completed swarm job history

    Any other device can import these nuggets to immediately access the full
    project memory without any manual transfer or custom sync server.

    Args:
        project_name: The project silo name (must exist in __DATACENTER).

    Returns:
        [NUGGET_EXPORTED] summary string on success.
        [NUGGET_FAULT] description on failure.
    """
    logger.info("[SyncTools] Exporting nugget: project=%s device=%s", project_name, _device_id())
    _write_telemetry({"event": "NUGGET_EXPORT_STARTED", "project": project_name, "device": _device_id()})

    try:
        nuggets_dir = _nuggets_dir(project_name)
        device_id = _device_id()
        ts = _ts()

        chroma_result = _export_chroma(project_name, nuggets_dir, device_id, ts)
        thoughts_result = _export_thoughts(project_name, nuggets_dir, device_id, ts)
        queue_result = _export_queue(project_name, nuggets_dir, device_id, ts)

        exported = sum(1 for r in [chroma_result, thoughts_result, queue_result] if r["status"] == "ok")
        skipped  = sum(1 for r in [chroma_result, thoughts_result, queue_result] if r["status"] == "skipped")
        errors   = sum(1 for r in [chroma_result, thoughts_result, queue_result] if r["status"] == "error")

        summary = (
            f"[NUGGET_EXPORTED] Project '{project_name}' | Device: {device_id}\n"
            f"  Artifacts: {exported} exported, {skipped} skipped, {errors} errors\n"
            f"  Destination: {nuggets_dir}"
        )
        _write_telemetry({
            "event": "NUGGET_EXPORTED",
            "project": project_name,
            "device": device_id,
            "exported": exported,
            "skipped": skipped,
            "errors": errors,
            "destination": str(nuggets_dir),
        })
        logger.info("[SyncTools] %s", summary)
        return summary

    except Exception as exc:  # noqa: BLE001
        logger.error("[SyncTools] Nugget export failed: %s", exc)
        return f"[NUGGET_FAULT] Export failed for '{project_name}': {exc}"


# ── Public: import ─────────────────────────────────────────────────────────────


def _import_chroma_nugget(json_path: Path, project_name: str) -> dict[str, Any]:
    """Merge a foreign device's vector dump into the local knowledge store."""
    try:
        from maccre_core.memory import PinRecord, get_knowledge_store  # noqa: PLC0415

        payload = json.loads(json_path.read_text(encoding="utf-8"))
        store = get_knowledge_store(project_name)
        total_imported = 0

        for col_name, col_data in payload.get("collections", {}).items():
            ids        = col_data.get("ids", [])
            documents  = col_data.get("documents", [])
            metadatas  = col_data.get("metadatas", [])
            embeddings = col_data.get("embeddings", [])

            for i, doc_id in enumerate(ids):
                text = documents[i] if i < len(documents) else ""
                meta: dict[str, Any] = dict(metadatas[i]) if i < len(metadatas) else {}
                vec: list[float] | None = embeddings[i] if i < len(embeddings) else None
                store.upsert(col_name, PinRecord(
                    doc_id=doc_id, text=text, vector=vec, metadata=meta,
                ))
                total_imported += 1

        logger.info("[SyncTools] Store import: %d docs from %s", total_imported, json_path.name)
        return {"status": "ok", "docs": total_imported, "file": json_path.name}
    except Exception as exc:  # noqa: BLE001
        logger.error("[SyncTools] Store import failed for %s: %s", json_path.name, exc)
        return {"status": "error", "error": str(exc), "file": json_path.name}


def _import_thoughts_nugget(gz_path: Path, project_name: str) -> dict[str, Any]:
    """Replay a foreign thoughts.db gzip into the local thoughts.db."""
    try:
        thoughts_path = _local_thoughts_path(project_name)

        # Decompress to a temp file
        tmp_path = gz_path.with_suffix(".tmp_import.db")
        try:
            with gzip.open(str(gz_path), "rb") as gz:
                data = gz.read()
            tmp_path.write_bytes(data)

            # Read all rows from the foreign DB
            foreign_con = sqlite3.connect(str(tmp_path), check_same_thread=False)
            foreign_con.row_factory = sqlite3.Row
            try:
                tables = [r[0] for r in foreign_con.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
            finally:
                foreign_con.close()

            # Connect to local thoughts.db (create if missing)
            local_con = sqlite3.connect(str(thoughts_path), check_same_thread=False)
            try:
                # Attach foreign, copy rows with INSERT OR IGNORE
                local_con.execute(f"ATTACH DATABASE '{tmp_path}' AS foreign_db")
                replayed = 0
                for tbl in tables:
                    try:
                        n = local_con.execute(
                            f"INSERT OR IGNORE INTO {tbl} SELECT * FROM foreign_db.{tbl}"  # noqa: S608
                        ).rowcount
                        replayed += n
                    except sqlite3.OperationalError:
                        # Table may not exist in local DB — create it then retry
                        ddl_row = foreign_con.execute(
                            f"SELECT sql FROM sqlite_master WHERE type='table' AND name='{tbl}'"  # noqa: S608
                        ).fetchone()
                        if ddl_row and ddl_row[0]:
                            local_con.execute(ddl_row[0])
                            n = local_con.execute(
                                f"INSERT OR IGNORE INTO {tbl} SELECT * FROM foreign_db.{tbl}"  # noqa: S608
                            ).rowcount
                            replayed += n
                local_con.commit()
            finally:
                local_con.close()
        finally:
            tmp_path.unlink(missing_ok=True)

        logger.info("[SyncTools] thoughts.db import: %d rows replayed from %s", replayed, gz_path.name)
        return {"status": "ok", "rows": replayed, "file": gz_path.name}
    except Exception as exc:  # noqa: BLE001
        logger.error("[SyncTools] thoughts.db import failed for %s: %s", gz_path.name, exc)
        return {"status": "error", "error": str(exc), "file": gz_path.name}


def import_project_nuggets(project_name: str) -> str:
    """Import cognitive snapshots from other devices to the local project memory.

    Scans G:\\My Drive\\__DataCenter\\<PROJECT>\\_nuggets\\ for nugget files
    from foreign devices (all devices except this one), then:
      - Merges foreign ChromaDB vector snapshots into local chroma_db
      - Replays foreign thoughts.db entries into local thoughts.db

    Safe to run repeatedly — ChromaDB upserts are idempotent (same ID = overwrite),
    thoughts.db replay uses INSERT OR IGNORE (no duplicates).

    Args:
        project_name: The project silo name to sync.

    Returns:
        [NUGGETS_IMPORTED] summary string.
        [NUGGET_FAULT] on hard failure.
    """
    logger.info("[SyncTools] Importing nuggets: project=%s", project_name)
    _write_telemetry({"event": "NUGGET_IMPORT_STARTED", "project": project_name, "device": _device_id()})

    try:
        nuggets_dir = _nuggets_dir(project_name)
        my_device = _device_id()

        # Find all foreign nugget files (exclude own device)
        vector_files = [
            f for f in nuggets_dir.glob("*_vectors_*.json")
            if not f.name.startswith(my_device)
        ]
        thoughts_files = [
            f for f in nuggets_dir.glob("*_thoughts_*.db.gz")
            if not f.name.startswith(my_device)
        ]

        if not vector_files and not thoughts_files:
            return (
                f"[NUGGETS_IMPORTED] No foreign nuggets found for '{project_name}'.\n"
                f"  Searched: {nuggets_dir}"
            )

        # Import vectors — group by device, take only the latest per device
        devices_seen: set[str] = set()
        latest_vectors: list[Path] = []
        for f in sorted(vector_files, reverse=True):
            dev = f.name.split("_vectors_")[0]
            if dev not in devices_seen:
                devices_seen.add(dev)
                latest_vectors.append(f)

        devices_seen.clear()
        latest_thoughts: list[Path] = []
        for f in sorted(thoughts_files, reverse=True):
            dev = f.name.split("_thoughts_")[0]
            if dev not in devices_seen:
                devices_seen.add(dev)
                latest_thoughts.append(f)

        vector_results = [_import_chroma_nugget(f, project_name) for f in latest_vectors]
        thoughts_results = [_import_thoughts_nugget(f, project_name) for f in latest_thoughts]

        total_docs = sum(r.get("docs", 0) for r in vector_results if r["status"] == "ok")
        total_rows = sum(r.get("rows", 0) for r in thoughts_results if r["status"] == "ok")
        foreign_devices = len({f.name.split("_")[0] for f in (latest_vectors + latest_thoughts)})
        errors = sum(1 for r in (vector_results + thoughts_results) if r["status"] == "error")

        summary = (
            f"[NUGGETS_IMPORTED] Project '{project_name}'\n"
            f"  Vectors merged:   {total_docs} docs from {len(latest_vectors)} device snapshot(s)\n"
            f"  Thoughts replayed:{total_rows} rows from {len(latest_thoughts)} device snapshot(s)\n"
            f"  Foreign devices:  {foreign_devices} | Errors: {errors}"
        )
        _write_telemetry({
            "event": "NUGGETS_IMPORTED",
            "project": project_name,
            "total_docs": total_docs,
            "total_rows": total_rows,
            "foreign_devices": foreign_devices,
            "errors": errors,
        })
        logger.info("[SyncTools] Import complete: %s", summary)
        return summary

    except Exception as exc:  # noqa: BLE001
        logger.error("[SyncTools] Nugget import failed: %s", exc)
        return f"[NUGGET_FAULT] Import failed for '{project_name}': {exc}"


# ── Public: list ───────────────────────────────────────────────────────────────


def list_project_nuggets(project_name: str) -> str:
    """List all nugget snapshots available for a project in the Drive folder.

    Shows each nugget file with device ID, type, timestamp, and size — so Nexus
    can describe what cognitive state is available for import.

    Args:
        project_name: The project silo to inspect.

    Returns:
        Formatted table string, or a [NUGGET_FAULT] message.
    """
    try:
        nuggets_dir = _nuggets_dir(project_name)
        files = sorted(nuggets_dir.iterdir(), reverse=True)

        if not files:
            return f"[NUGGETS_EMPTY] No nuggets found for '{project_name}'.\n  Folder: {nuggets_dir}"

        my_device = _device_id()
        lines = [f"Nuggets for project '{project_name}' ({nuggets_dir})", ""]
        lines.append(f"{'FILE':<55}  {'SIZE':>8}  {'DEVICE'}")
        lines.append("-" * 80)

        for f in files:
            if f.suffix not in {".json", ".gz"}:
                continue
            size_kb = round(f.stat().st_size / 1024, 1)
            device = f.name.split("_")[0]
            marker = " (this device)" if device == my_device else ""
            lines.append(f"{f.name:<55}  {size_kb:>6.1f}kB  {device}{marker}")

        return "\n".join(lines)

    except Exception as exc:  # noqa: BLE001
        return f"[NUGGET_FAULT] Could not list nuggets for '{project_name}': {exc}"
