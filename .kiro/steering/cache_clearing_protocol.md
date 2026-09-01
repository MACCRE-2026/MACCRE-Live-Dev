---
inclusion: fileMatch
fileMatchPattern:
  - '**/flow_engine.py'
  - '**/swarm_*.py'
  - '**/nexus_plex.py'
  - '**/local_broker.py'
  - '**/swarm_worker.py'
---

# Python Cache Clearing Protocol

**Auto-Applied**: When editing core execution files (flow_engine, swarm_*, nexus_plex, broker, worker)

---

## The Memory Ghost Problem

**Symptom**: "I made a fix but it's still broken, then magically works later"

**Root Cause**:
1. Python compiles `.py` → `.pyc` bytecode for performance
2. When you edit code, Python SHOULD recompile
3. But stale `.pyc` files can persist
4. **Worse**: Even if recompiled, old modules stay in `sys.modules` until process restart

**Result**: You test against old code, not new code.

---

## Mandatory Protocol

**BEFORE** testing ANY changes to core execution files:

### Step 1: Clear Bytecode Caches

```powershell
# Clear all __pycache__ directories
Get-ChildItem -Path "." -Filter "__pycache__" -Recurse -Directory | Remove-Item -Recurse -Force

# Clear individual .pyc files
Get-ChildItem -Filter "*.pyc" -Recurse | Remove-Item -Force

# Confirmation
Write-Output "✓ All caches cleared - restart TUI now"
```

**One-Liner**:
```powershell
Get-ChildItem -Path "." -Filter "__pycache__" -Recurse -Directory | Remove-Item -Recurse -Force; Get-ChildItem -Filter "*.pyc" -Recurse | Remove-Item -Force; Write-Output "✓ Caches cleared"
```

### Step 2: Restart TUI Process

- **Stop** any running MACCRE TUI instances (Ctrl+C or close terminal)
- **Why**: Python's `sys.modules` caches imported modules in memory
- **Only** a full process restart clears this cache

### Step 3: Verify Changes Took Effect

After restart:
- ✅ Check logs for new debug statements
- ✅ Verify behavior matches new code logic
- ❌ If behavior seems "old", repeat steps 1-2

---

## When This Matters Most

### Critical Files (Always Clear)
- `flow_engine.py` - Multi-step flow execution loop
- `swarm_worker.py` - Task execution engine
- `swarm_pool.py` - Dynamic worker pool
- `local_broker.py` - Task queue management
- `nexus_plex.py` - TUI main application

### Why
These files control **runtime behavior**. Stale cache = testing old logic.

### Less Critical Files (Clear if Suspicious)
- `admin_tools.py` - Utility functions
- `agent_library.py` - Agent definitions
- Pure data files (JSON, CSV) - Not cached by Python

---

## Automated Cache Clearing

### Option 1: Pre-Launch Hook

Create `.kiro/hooks/clear-cache-on-launch.json`:

```json
{
  "version": "v1",
  "hooks": [{
    "name": "Clear Python Caches Before Launch",
    "trigger": "SessionStart",
    "action": {
      "type": "command",
      "command": "Get-ChildItem -Path '.' -Filter '__pycache__' -Recurse -Directory | Remove-Item -Recurse -Force; Get-ChildItem -Filter '*.pyc' -Recurse | Remove-Item -Force"
    }
  }]
}
```

### Option 2: Manual Script

Create `scripts/clear_cache.ps1`:

```powershell
#!/usr/bin/env pwsh
# Clear all Python bytecode caches

Write-Host "Clearing Python caches..." -ForegroundColor Cyan

$pycache = Get-ChildItem -Path "." -Filter "__pycache__" -Recurse -Directory
$pycFiles = Get-ChildItem -Filter "*.pyc" -Recurse

Write-Host "Found $($pycache.Count) __pycache__ directories"
Write-Host "Found $($pycFiles.Count) .pyc files"

$pycache | Remove-Item -Recurse -Force
$pycFiles | Remove-Item -Force

Write-Host "✓ All caches cleared" -ForegroundColor Green
Write-Host "⚠ Remember to restart TUI process!" -ForegroundColor Yellow
```

Run before testing:
```powershell
.\scripts\clear_cache.ps1
```

---

## Development Workflow

### Recommended Workflow

1. **Edit** code in VSCode/editor
2. **Save** changes
3. **Clear** caches (run one-liner)
4. **Restart** TUI process
5. **Test** changes
6. **Verify** behavior matches expectations

### Anti-Pattern (Don't Do This)

1. Edit code
2. Hot-reload / re-import modules
3. Test in same Python process
4. Get confused when old code runs

---

## How to Tell If You Have Stale Caches

### Symptoms
- Debug logs don't appear (you added `logger.info()` but nothing prints)
- Bugs persist after fix (you fixed the code but error still happens)
- Inconsistent behavior (sometimes works, sometimes doesn't)
- "Ghost" features (removed code still executes)

### Diagnostic
```powershell
# Check for .pyc files older than source files
$srcFile = Get-Item "maccre_core\orchestration\flow_engine.py"
$pycFile = Get-Item "maccre_core\orchestration\__pycache__\flow_engine*.pyc" -ErrorAction SilentlyContinue

if ($pycFile -and $pycFile.LastWriteTime -lt $srcFile.LastWriteTime) {
    Write-Host "⚠ Stale cache detected!" -ForegroundColor Red
    Write-Host "Source: $($srcFile.LastWriteTime)"
    Write-Host "Cache:  $($pycFile.LastWriteTime)"
}
```

---

## Special Cases

### Ruff Linter Cache
```powershell
# Ruff has its own cache (.ruff_cache/)
Remove-Item -Recurse -Force .ruff_cache
```

### SQLite WAL Files
```powershell
# Sometimes SQLite Write-Ahead Log files lock the DB
Remove-Item __DATACENTER\*\*.db-wal -Force
Remove-Item __DATACENTER\*\*.db-shm -Force
```

### Virtual Environment
```powershell
# Nuclear option: recreate venv (rarely needed)
Remove-Item -Recurse -Force .venv
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

---

## Why Kiro Needs This

Kiro operates in a **long-running session** where:
- You edit code during the session
- Kiro reads/tests code in the same session
- Python's import cache persists across edits
- **Without cache clearing, Kiro tests old code**

This is different from:
- Traditional development (restart IDE/terminal between tests)
- Compiled languages (explicit build step forces recompilation)

---

## Doctrine Alignment

This protocol addresses:
- **GEMINI.md Section I**: Omni clean command (cache purging)
- **User-reported "Memory Ghost" behavior** (Phase 6.12 post-mortem)
- **StateAndSovereignty_Oracle domain**: System state management

**Last Updated**: August 28, 2026
