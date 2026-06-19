#!/usr/bin/env python3
"""
scripts/migrate_memory_pins.py
==============================
Migration utility: Moves existing 06_Memory_Pins/ data into
02_Dynamic_Context/memory_pins/ for all project directories.

Run once after upgrading to 5-tier-compliant datacenter layout.
"""
from __future__ import annotations

import shutil

from maccre_core.utils.path_resolver import get_maccre_root


def migrate() -> None:
    datacenter = get_maccre_root() / "__DATACENTER"
    if not datacenter.exists():
        print("[MIGRATE] No __DATACENTER found. Nothing to do.")
        return

    migrated = 0
    for project_dir in sorted(datacenter.iterdir()):
        if not project_dir.is_dir():
            continue

        old = project_dir / "06_Memory_Pins"
        new = project_dir / "02_Dynamic_Context" / "memory_pins"

        if not old.exists():
            continue

        print(f"[MIGRATE] {project_dir.name}: 06_Memory_Pins → 02_Dynamic_Context/memory_pins")
        new.mkdir(parents=True, exist_ok=True)

        # Move all files from old → new
        for item in old.iterdir():
            dest = new / item.name
            if dest.exists():
                print(f"  [SKIP] {item.name} already exists in destination")
                continue
            shutil.move(str(item), str(dest))
            print(f"  [MOVED] {item.name}")

        # Remove the now-empty 06_Memory_Pins directory
        try:
            old.rmdir()
            print("  [REMOVED] Empty 06_Memory_Pins/ directory")
        except OSError:
            print("  [WARN] 06_Memory_Pins/ not empty after migration — manual cleanup needed")

        migrated += 1

    print(f"\n[MIGRATE] Done. Migrated {migrated} project(s).")


if __name__ == "__main__":
    migrate()
