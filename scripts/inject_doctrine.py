"""
scripts/inject_doctrine.py
============================
One-shot doctrinal header injector for MACCREv2.

Prepends the Engineering Doctrine comment block to every eligible Python
source file in the codebase.  Safe to re-run — idempotent via the
MACCRE_DOCTRINE sentinel tag.

Usage:
    python scripts/inject_doctrine.py [--dry-run] [--target path]

Options:
    --dry-run   Print what would be changed; write nothing.
    --target    Override the scan root (default: project root).
"""
from __future__ import annotations

import argparse
from pathlib import Path

# ── Doctrine block ─────────────────────────────────────────────────────────────
# Pinned to Law Rev 19.0.  To update the doctrine:
#   1. Edit DOCTRINE_LINES below.
#   2. Bump LAW_REV.
#   3. Re-run this script (old headers are auto-replaced).

LAW_REV = "19.0"

DOCTRINE_LINES: list[str] = [
    "# ┌─────────────────────────────────────────────────────────────────────────────┐",
    f"# │  MACCREv2 ENGINEERING DOCTRINE                             Law Rev: {LAW_REV}   │",
    "# ├─────────────────────────────────────────────────────────────────────────────┤",
    "# │  I.   TYPING      All signatures: explicit Python 3.11+ type hints.        │",
    "# │  II.  LINTING     Zero unused imports. No wildcards. 120-char line max.    │",
    "# │  III. PATHS       Never hardcode absolute paths. Use get_maccre_root().     │",
    "# │                   Default params: def f(p:str='') -> None: p=p or root/x   │",
    "# │  IV.  DATACENTER  5-Tier: 01_Raw_Source · 02_Dynamic_Context               │",
    "# │                           03_Agent_Ledgers · 04_Code_Artifacts             │",
    "# │                           05_Rendered_Media                                 │",
    "# │  V.   DIAMOND     Gen: temp=1.0  ·  Critic: temp=0.1 + dataclass schema   │",
    "# │  VI.  ABSTRACTION All I/O behind abc.ABC before any concrete driver.       │",
    "# │  VII. TEARDOWN    try/finally on all handles (omni clean compliance).      │",
    "# │  VIII.TELEMETRY   No bare print(). logger only. JSON → 03_Agent_Ledgers.  │",
    "# └─────────────────────────────────────────────────────────────────────────────┘",
]

# Sentinel: first token we search for to detect an existing header.
# Changing LAW_REV above makes old headers detectable as stale.
_SENTINEL_TAG   = "# │  MACCREv2 ENGINEERING DOCTRINE"
_SENTINEL_START = "# ┌──"
_SENTINEL_END   = "# └──"

DOCTRINE_BLOCK = "\n".join(DOCTRINE_LINES) + "\n"

# ── Skip lists ─────────────────────────────────────────────────────────────────
SKIP_DIR_FRAGMENTS = {
    "_vendor", "_archive", "__pycache__", ".egg-info",
    "_historical_documentation", ".venv", ".git", "legacy",
}
SKIP_FILES = {"setup_mcp.py"}   # meta/tool scripts that describe themselves

# ── Core logic ─────────────────────────────────────────────────────────────────

def _should_skip(path: Path) -> bool:
    parts = set(path.parts)
    if any(frag in part for frag in SKIP_DIR_FRAGMENTS for part in parts):
        return True
    if path.name in SKIP_FILES:
        return True
    return False


def _strip_existing_doctrine(text: str) -> str:
    """Remove any previously-injected doctrine block from the file text."""
    if _SENTINEL_START not in text:
        return text

    lines = text.splitlines(keepends=True)
    out: list[str] = []
    inside = False
    for line in lines:
        if not inside and line.startswith(_SENTINEL_START):
            inside = True
            continue
        if inside:
            if line.startswith(_SENTINEL_END):
                inside = False
            continue
        out.append(line)
    return "".join(out)


def inject(path: Path, dry_run: bool = False) -> str:
    """
    Inject (or replace) the Engineering Doctrine comment block at the top of
    *path*.  Returns a human-readable status string.
    """
    text = path.read_text(encoding="utf-8")

    # Strip stale header first (idempotent for re-runs and law-rev upgrades)
    stripped = _strip_existing_doctrine(text)

    # Check if stale header was present
    had_doctrine = stripped != text

    # Compose new file: doctrine block + blank separator + rest of file
    # Preserve any leading shebang (#!/usr/bin/env python) or encoding cookie
    new_lines: list[str] = []
    rest_lines = stripped.splitlines(keepends=True)

    # Drain any leading shebang / encoding / blank lines BEFORE the doctrine
    cursor = 0
    for i, ln in enumerate(rest_lines):
        stripped_ln = ln.strip()
        if stripped_ln.startswith("#!") or stripped_ln.startswith("# -*-") or stripped_ln == "":
            new_lines.append(ln)
            cursor = i + 1
        else:
            break

    # Insert doctrine
    new_lines.append(DOCTRINE_BLOCK)

    # Append the remainder of the file
    new_lines.extend(rest_lines[cursor:])
    new_text = "".join(new_lines)

    if new_text == text:
        return "  UNCHANGED  (already current)"

    action = "REPLACED" if had_doctrine else "INJECTED"
    if not dry_run:
        path.write_text(new_text, encoding="utf-8")
    return f"  {action}   {'(dry-run) ' if dry_run else ''}{path}"


# ── Entry point ────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="Inject MACCREv2 doctrine headers")
    parser.add_argument("--dry-run", action="store_true", help="Preview only, no writes")
    parser.add_argument("--target", type=Path, default=None, help="Override scan root")
    args = parser.parse_args()

    script_dir = Path(__file__).resolve().parent
    project_root = script_dir.parent
    scan_root = args.target or project_root

    # Collect targets: maccre_core/ + root-level entry points
    targets: list[Path] = []

    # Root-level Python files
    for p in scan_root.glob("*.py"):
        if not _should_skip(p):
            targets.append(p)

    # maccre_core subtree
    for p in (scan_root / "maccre_core").rglob("*.py"):
        if not _should_skip(p):
            targets.append(p)

    targets.sort()

    print(f"\nMACCREv2 Doctrine Injector — Law Rev {LAW_REV}")
    print(f"Scan root : {scan_root}")
    print(f"Targets   : {len(targets)} files")
    print(f"Mode      : {'DRY RUN (no writes)' if args.dry_run else 'LIVE'}\n")

    injected = replaced = unchanged = 0
    for p in targets:
        result = inject(p, dry_run=args.dry_run)
        print(result)
        if "INJECTED" in result:
            injected += 1
        elif "REPLACED" in result:
            replaced += 1
        else:
            unchanged += 1

    print(f"\n{'-'*60}")
    print(f"  Injected : {injected}")
    print(f"  Replaced : {replaced}  (stale law-rev updated)")
    print(f"  Unchanged: {unchanged}")
    print(f"  Total    : {len(targets)}\n")

    if not args.dry_run and (injected + replaced) > 0:
        print("Run `omni qa` to verify all files pass Ruff + Pyright.\n")


if __name__ == "__main__":
    main()
