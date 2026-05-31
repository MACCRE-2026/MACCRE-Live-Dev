"""
setup_mcp.py
============
One-time setup script: generates the Antigravity mcp_config.json for this machine.

Run this after cloning MACCREv2 to a new machine or drive:

    python setup_mcp.py

It will auto-detect:
  - The project root (anchored to this file's location)
  - The correct venv Python path
  - The user's Antigravity config directory

Then it writes the correct mcp_config.json with no hardcoded drive letters.
"""
from __future__ import annotations

import json
import os
import platform
import sys
from pathlib import Path

# ── Project root is always this file's parent directory ───────────────────────
PROJECT_ROOT = Path(__file__).resolve().parent
VENV_PYTHON  = PROJECT_ROOT / ".venv" / "Scripts" / "python.exe"
MCP_SCRIPT   = PROJECT_ROOT / "maccre_mcp.py"

# ── Locate Antigravity config directory ───────────────────────────────────────
def find_antigravity_config_dir() -> Path:
    """Find the Antigravity app data directory on this machine."""
    # Standard Windows path
    if platform.system() == "Windows":
        candidates = [
            Path(os.environ.get("APPDATA", "")) / "antigravity",
            Path(os.environ.get("USERPROFILE", "")) / ".gemini" / "antigravity",
            Path.home() / ".gemini" / "antigravity",
        ]
    else:
        # Linux / macOS
        candidates = [
            Path.home() / ".gemini" / "antigravity",
            Path.home() / ".config" / "antigravity",
        ]

    for c in candidates:
        if c.exists():
            return c

    # Fallback: create in the most standard location
    fallback = Path.home() / ".gemini" / "antigravity"
    fallback.mkdir(parents=True, exist_ok=True)
    return fallback


def validate() -> list[str]:
    """Return list of validation errors (empty = OK to proceed)."""
    errors: list[str] = []
    if not VENV_PYTHON.exists():
        errors.append(
            f"  ❌  venv Python not found: {VENV_PYTHON}\n"
            f"      Run: python -m venv .venv && .venv\\Scripts\\pip install -r requirements.txt"
        )
    if not MCP_SCRIPT.exists():
        errors.append(f"  ❌  MCP server script not found: {MCP_SCRIPT}")
    return errors


def generate_config(active_project: str = "SilmLOTR") -> dict[str, object]:
    """Build the mcp_config dict using this machine's resolved paths."""
    return {
        "mcpServers": {
            "MACCREv2": {
                "command": str(VENV_PYTHON),
                "args": [str(MCP_SCRIPT)],
                "env": {
                    "PYTHONUTF8": "1",
                    "PYTHONIOENCODING": "utf-8",
                    "PYTHONUNBUFFERED": "1",
                    "PYTHONPATH": str(PROJECT_ROOT),
                    "MACCRE_ACTIVE_PROJECT": active_project,
                    # Explicit root anchor — picked up by path_resolver.py as highest priority
                    "MACCRE_ROOT": str(PROJECT_ROOT),
                },
            }
        }
    }


def main() -> None:
    print(f"\n{'='*60}")
    print("  MACCREv2 MCP Setup")
    print(f"  Project root: {PROJECT_ROOT}")
    print(f"{'='*60}\n")

    # Validate prerequisites
    errors = validate()
    if errors:
        print("Pre-flight checks FAILED:\n")
        for e in errors:
            print(e)
        sys.exit(1)

    # Detect Antigravity config dir
    config_dir = find_antigravity_config_dir()
    mcp_config_path = config_dir / "mcp_config.json"

    # Confirm with user
    print(f"  Venv Python : {VENV_PYTHON}")
    print(f"  MCP script  : {MCP_SCRIPT}")
    print(f"  Config dir  : {config_dir}")
    print(f"  Output file : {mcp_config_path}\n")

    # Allow active project override
    active_project = os.environ.get("MACCRE_ACTIVE_PROJECT", "SilmLOTR")
    if len(sys.argv) > 1:
        active_project = sys.argv[1]
    print(f"  Active project: {active_project}\n")

    config = generate_config(active_project)

    # Write
    mcp_config_path.write_text(json.dumps(config, indent=2), encoding="utf-8")

    print(f"✅  mcp_config.json written to: {mcp_config_path}")
    print("\nRestart Antigravity to activate the MCP server.\n")


if __name__ == "__main__":
    main()
