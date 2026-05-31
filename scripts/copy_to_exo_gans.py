import os
import shutil
from pathlib import Path
import sys

DRY_RUN = os.environ.get("DRY_RUN", "TRUE").upper() == "TRUE"

SRC_DIR = Path(r"B:\MACCREv2")
DST_DIR = Path(r"B:\EXO_GANS")

# Strict allowlist of root-level items to copy
ROOT_ALLOWLIST = {
    # Core directories
    "maccre_core",
    "scripts",
    "maccre_dashboard",
    "maccre_tui",
    "templates",
    ".agent",
    
    # Entry points and setup
    "maccre.py",
    "maccre_mcp.py",
    "setup.ps1",
    "setup_mcp.py",
    
    # Configuration
    "pyproject.toml",
    "pyrightconfig.json",
    "ruff.toml",
    ".gitignore",
    ".pyre_configuration",
    
    # Dependencies
    "requirements.txt",
    "requirements-global.txt",
    "requirements-optional.txt",
    "requirements-sovereign.txt",
    
    # Documentation
    "README.md",
    "MACCRE_Operator_Manual.md"
}

# Directories to exclude even if they are inside an allowed root directory
EXCLUDE_SUBDIRS = {
    "__pycache__",
    "node_modules",
    ".next",
    ".ruff_cache",
    "maccre_core.egg-info",
    ".pytest_cache"
}

# Extensions to exclude globally
EXCLUDE_EXTS = {
    ".pyc",
    ".log",
    ".sqlite3",
    ".db",
    ".db-shm",
    ".db-wal"
}

def should_copy(path: Path) -> bool:
    # Check if the file's root ancestor is in the allowlist
    rel_path = path.relative_to(SRC_DIR)
    root_part = rel_path.parts[0] if rel_path.parts else ""
    
    if root_part not in ROOT_ALLOWLIST:
        return False
        
    # Check for excluded subdirectories
    if path.name in EXCLUDE_SUBDIRS:
        return False
    if any(parent.name in EXCLUDE_SUBDIRS for parent in path.parents):
        return False
        
    # Check for excluded extensions
    if path.is_file() and any(path.name.endswith(ext) for ext in EXCLUDE_EXTS):
        return False
        
    return True

def copy_clean_system():
    print(f"[{'DRY RUN' if DRY_RUN else 'EXECUTE'}] Copying MACCREv2 -> {DST_DIR}")
    
    if not DRY_RUN and not DST_DIR.exists():
        DST_DIR.mkdir(parents=True)
        
    copied_files = 0
    copied_dirs = 0
    bytes_copied = 0

    for root, dirs, files in os.walk(SRC_DIR):
        current_dir = Path(root)
        
        # Filter directories in-place for os.walk
        dirs[:] = [d for d in dirs if should_copy(current_dir / d)]
        
        rel_path = current_dir.relative_to(SRC_DIR)
        
        # If the root part itself is excluded, skip walking
        root_part = rel_path.parts[0] if rel_path.parts else ""
        if root_part and root_part not in ROOT_ALLOWLIST:
            continue
            
        target_dir = DST_DIR / rel_path
        
        if not DRY_RUN and not target_dir.exists():
            target_dir.mkdir(parents=True)
            copied_dirs += 1
            
        for file in files:
            src_file = current_dir / file
            if should_copy(src_file):
                target_file = target_dir / file
                bytes_copied += src_file.stat().st_size
                copied_files += 1
                
                if not DRY_RUN:
                    shutil.copy2(src_file, target_file)
                else:
                    print(f"  -> {target_file}")

    print("\n" + "="*40)
    print(f"[{'DRY RUN' if DRY_RUN else 'EXECUTE'}] COMPLETE")
    print(f"Files to copy: {copied_files}")
    print(f"Data volume:   {bytes_copied / (1024*1024):.2f} MB")
    print("="*40)

if __name__ == "__main__":
    copy_clean_system()
