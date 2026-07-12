# ┌─────────────────────────────────────────────────────────────────────────────┐
# │  MACCREv2 ENGINEERING DOCTRINE                             Law Rev: 19.0   │
# ├─────────────────────────────────────────────────────────────────────────────┤
# │  DB Migration: DET_ → CTRL_ prefix rename in saved templates               │
# └─────────────────────────────────────────────────────────────────────────────┘
"""
scripts/migrate_det_to_ctrl.py
==============================
One-shot migration script: renames DET_ prefixes to CTRL_ in all saved
macronode templates stored in macronode_registry.db.

Scans:
  - macronode_registry.macronodes → topology_json column
  - Any JSON fields containing "DET_" strings

Safe to run multiple times (idempotent).

Usage:
    omni run scripts/migrate_det_to_ctrl.py
"""
from __future__ import annotations

import json
import logging
import sqlite3
from pathlib import Path

from maccre_core.utils.path_resolver import get_datacenter_path

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(message)s")

DET_PREFIXES = [
    "DET_REVIEW", "DET_ANCHOR", "DET_RECURSION", "DET_PAUSE",
    "DET_GATE", "DET_CHECKPOINT", "DET_DELAY", "DET_TRANSFORM",
    "DET_PAUSE_MANUAL",
]


def _replace_det_in_string(s: str) -> str:
    """Replace all DET_ node references with CTRL_ equivalents."""
    result = s
    for det in DET_PREFIXES:
        ctrl = det.replace("DET_", "CTRL_")
        result = result.replace(det, ctrl)
    return result


def _replace_det_in_json(json_str: str) -> str:
    """Parse JSON, walk structure, replace DET_ references, re-serialize."""
    try:
        data = json.loads(json_str)
    except (json.JSONDecodeError, TypeError):
        return _replace_det_in_string(json_str)

    serialized = json.dumps(data, indent=2)
    return _replace_det_in_string(serialized)


def migrate_macronode_registry() -> int:
    """Migrate macronode_registry.db topology_json fields."""
    db_path = get_datacenter_path("macronode_registry.db")
    if not Path(db_path).exists():
        logger.info("  ⚠ macronode_registry.db not found — skipping.")
        return 0

    updated = 0
    with sqlite3.connect(str(db_path)) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute("SELECT name, topology_json FROM macronode_registry").fetchall()
        for row in rows:
            original = row["topology_json"] or ""
            if "DET_" not in original:
                continue
            migrated = _replace_det_in_json(original)
            if migrated != original:
                conn.execute(
                    "UPDATE macronode_registry SET topology_json = ? WHERE name = ?",
                    (migrated, row["name"]),
                )
                logger.info(f"  ✓ Migrated template: {row['name']}")
                updated += 1
        conn.commit()
    return updated


def migrate_autosave_flows() -> int:
    """Migrate autosave_flow.json files in all project DATACENTER folders."""
    datacenter_root = get_datacenter_path("")
    if not Path(datacenter_root).exists():
        return 0

    updated = 0
    for autosave in Path(datacenter_root).rglob("autosave_flow.json"):
        try:
            content = autosave.read_text(encoding="utf-8")
            if "DET_" not in content:
                continue
            migrated = _replace_det_in_string(content)
            if migrated != content:
                autosave.write_text(migrated, encoding="utf-8")
                logger.info(f"  ✓ Migrated autosave: {autosave}")
                updated += 1
        except Exception as e:  # noqa: BLE001
            logger.warning(f"  ⚠ Failed to migrate {autosave}: {e}")
    return updated


def migrate_topology_snapshots() -> int:
    """Migrate topology_snapshot.csv and as_wrapped_topology.json in 02_Dynamic_Context."""
    datacenter_root = get_datacenter_path("")
    if not Path(datacenter_root).exists():
        return 0

    updated = 0
    for pattern in ["as_wrapped_topology.json", "topology_snapshot.csv"]:
        for filepath in Path(datacenter_root).rglob(pattern):
            try:
                content = filepath.read_text(encoding="utf-8")
                if "DET_" not in content:
                    continue
                migrated = _replace_det_in_string(content)
                if migrated != content:
                    filepath.write_text(migrated, encoding="utf-8")
                    logger.info(f"  ✓ Migrated snapshot: {filepath}")
                    updated += 1
            except Exception as e:  # noqa: BLE001
                logger.warning(f"  ⚠ Failed to migrate {filepath}: {e}")
    return updated


def main() -> None:
    """Run all migrations."""
    logger.info("=" * 60)
    logger.info("DET_ → CTRL_ Database Migration")
    logger.info("=" * 60)

    logger.info("\n[1/3] Migrating macronode_registry.db...")
    n1 = migrate_macronode_registry()
    logger.info(f"  → {n1} template(s) updated.\n")

    logger.info("[2/3] Migrating autosave_flow.json files...")
    n2 = migrate_autosave_flows()
    logger.info(f"  → {n2} autosave(s) updated.\n")

    logger.info("[3/3] Migrating topology snapshots...")
    n3 = migrate_topology_snapshots()
    logger.info(f"  → {n3} snapshot(s) updated.\n")

    total = n1 + n2 + n3
    logger.info("=" * 60)
    if total > 0:
        logger.info(f"✅ Migration complete: {total} file(s) updated.")
    else:
        logger.info("✅ No DET_ references found — nothing to migrate.")
    logger.info("=" * 60)


if __name__ == "__main__":
    main()
