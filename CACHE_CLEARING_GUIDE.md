# MACCRE Cache Clearing Guide

## When to Clear Caches

If you experience any of these symptoms:
- Changes to code don't seem to take effect
- Behavior is inconsistent between sessions
- Old bugs reappear after being fixed
- System seems to use "stale" versions of code

## What to Clear

### 1. Python Bytecode Cache (.pyc files)
```powershell
# From project root
Get-ChildItem -Path "." -Filter "__pycache__" -Recurse -Directory | Remove-Item -Recurse -Force
Get-ChildItem -Path "maccre_core","maccre_tui" -Filter "*.pyc" -Recurse | Remove-Item -Force
```

### 2. Topology Cache
The topology engine caches parsed CSV files. Force reload by:
- Restarting the TUI application
- Or calling `topology.flush_cache()` in code (already done in flow_engine.py)

### 3. MacroNode Registry Cache
SQLite-based, auto-updates on save, but if issues occur:
- Restart TUI to reload the registry

### 4. Python Import Cache
Python caches imported modules in memory. To clear:
- **Restart the TUI application**
- This is the most important cache clear!

### 5. Ruff Linter Cache
```powershell
Remove-Item -Recurse -Force .ruff_cache
```

## Recommended Workflow

**After making code changes:**
1. Stop the TUI (if running)
2. Clear bytecode caches (run the PowerShell commands above)
3. Restart the TUI
4. Test your changes

**Quick Clear Command:**
```powershell
# One-liner to clear all Python caches
Get-ChildItem -Path "." -Filter "__pycache__" -Recurse -Directory | Remove-Item -Recurse -Force; Get-ChildItem -Filter "*.pyc" -Recurse | Remove-Item -Force; Write-Output "✓ All caches cleared - restart TUI now"
```

## Why This Matters

Python's import system caches compiled bytecode (.pyc files) for performance. When you:
- Edit a .py file
- Python SHOULD detect the change and recompile
- But sometimes stale .pyc files persist
- This causes the old code to run instead of your new code

**The TUI restart is crucial** because:
- Python keeps imported modules in `sys.modules` 
- Even if you recompile .pyc files, the old module stays in memory
- Only a full process restart clears this

## Prevention

Consider adding to your development workflow:
- Always restart TUI after code changes
- Clear caches before major testing sessions
- Use a pre-launch script that clears caches automatically
