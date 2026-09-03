# `omni clean` Audit — Zombie Hunting and Cache Purging

**Date:** 2026-08-30
**Scope:** `C:\OmniBuilder\omni.py` — `hunt_zombies()` and `purge_cache()`
**Status:** audited and evidenced. **No changes made to `omni.py` yet** — it lives
outside the repository and governs every project it is run against, so the edits
below are proposed rather than applied.

---

## Headline

`omni clean` reports `Project directory sterilized.` while removing **nothing**.
Measured on `B:\EXO_GANS` immediately after a run:

```
=== AFTER omni clean ===
__pycache__ dirs remaining (excl .venv):  33
.pyc files remaining (excl .venv):       281
.pytest_cache present:                   True
.ruff_cache present:                     True
```

This matters more than a normal tidiness bug, because Rule IV of the pipeline
mandate points operators at `omni clean` as *the* answer to phantom behaviour:

> "I fixed it but it's still broken, then it magically worked later" is a stale
> `__pycache__` or a zombie process holding a SQLite lock. Run `omni clean` before
> spending any time on a phantom bug.

The tool that rule depends on does not currently clear stale bytecode at all.

---

## Verified defects — cache purging

### C1. The `__pycache__` purge is a no-op by construction

```python
for folder in [".ruff_cache", "build", "dist", "__pycache__"]:
    shutil.rmtree(folder, ignore_errors=True)
```

`shutil.rmtree` is not recursive across the tree — it removes *one named
directory*. Every `__pycache__` in a Python project is nested beside its package.
Confirmed directly:

```
cwd = B:\EXO_GANS
.ruff_cache exists = True
__pycache__ exists = False      <-- there is no root __pycache__ to remove
```

So the line targeting bytecode has never had anything to act on in this project.
All 33 directories and 281 `.pyc` files are nested.

**Fix:** walk the tree with `Path(".").rglob("__pycache__")`, and sweep stray
`*.pyc` / `*.pyo` separately for files whose parent directory was already removed.
**`.venv` must be excluded** — deleting site-packages bytecode is pointless and
makes the next run measurably slower.

### C2. `.ruff_cache` deletion fails silently on Windows

`ignore_errors=True` hid a real failure. With the error surfaced:

```
ERROR rmdir .ruff_cache\0.15.15 [WinError 5] Access is denied
ERROR rmdir .ruff_cache         [WinError 5] Access is denied
.ruff_cache exists after = True
```

The *files* are removed; the directory rmdir is refused. This is the ordinary
Windows behaviour of a directory with a lingering handle, and it resolves on
retry — a 5-attempt loop at 250 ms cleared it immediately.

The codebase already learned exactly this lesson. `concurrency.atomic_write_text`
carries `_REPLACE_ATTEMPTS = 40` with backoff because `os.replace` fails with
`PermissionError` on Windows where POSIX succeeds. `omni` needs the same
treatment.

**Fix:** replace `ignore_errors=True` with a bounded retry, and **report what
could not be removed**. A cache that survives a purge is exactly the condition the
operator needs to know about.

### C3. `.pytest_cache` is not purged at all

Not in the list. Present in this repo, dated 2026-06-19.

### C4. WAL/SHM cleanup looks in the wrong place

```python
for wal_artifact in Path(".").glob("*.db-wal"):
```

Root-level only. Every MACCRE database lives under
`__DATACENTER/<project>/`, so `swarm_queue.db-wal` — the one whose lock actually
strands a swarm — is never considered. Confirmed: the only WAL artifacts present
are under `__DATACENTER\499_TEST\`.

**Fix, with a caveat that matters:** switch to `rglob`, but **do not delete
unconditionally**. A `-wal` left by a *crashed* process can hold committed
transactions not yet checkpointed, and deleting it loses them. Safe order is:

1. hunt zombies first (already the order in `clean`)
2. attempt a proper checkpoint by opening the DB and running
   `PRAGMA wal_checkpoint(TRUNCATE)`, which is lossless
3. only remove a `-wal`/`-shm` that is still present *and* whose DB opened cleanly

Deleting the WAL is the one operation in `purge_cache` that can destroy user data,
so it should be the most conservative, not the least.

### C5. The summary line is unconditional

`logging.info("Project directory sterilized.")` runs regardless of outcome. Every
individual failure is swallowed by `ignore_errors=True` or a bare `except: pass`.
This is the same silent-success shape being removed from the orchestration engine
this phase — a green report over unperformed work.

**Fix:** count and log removals per category, list failures explicitly, and say
"sterilized" only when nothing failed.

---

## Verified defects — zombie hunting

### Z1. `wmic` is deprecated and absent on current Windows

```python
os.system('wmic process where "name=\'python.exe\' and commandline like \'%swarm_worker%\'" call terminate >nul 2>&1')
```

WMIC is deprecated and removed from recent Windows builds. When it is missing,
`os.system` returns non-zero and the return value is discarded, so the **one
command that targets swarm processes is the one most likely to be a silent
no-op**.

**Fix:** use `Get-CimInstance Win32_Process` via PowerShell, or `psutil` if a
dependency is acceptable — though Rule II (zero-dependency) argues for PowerShell.
Check return codes and log the result either way.

### Z2. It hunts the wrong shape of process

The pattern matches command lines containing `swarm_worker`. That was correct when
each worker was its own process. Since Phase 6.12, workers are **threads** inside a
single interpreter, managed by `DynamicSwarmPool` — see the pool's own docstring:
"Runs swarm workers as threads". An orphaned swarm is now a whole `run.py` / TUI
process holding SQLite locks, not a `swarm_worker.py` process.

So the hunter searches for a shape the current architecture rarely produces, and
misses the shape it does produce. `swarm_worker.py` retains a `__main__` block, so
the legacy pattern is still worth keeping — but it cannot be the only one.

**Fix:** match MACCRE processes by a broader signature — command line containing
`maccre`, `swarm_worker`, or the project's entry point — and **exclude the current
process and its ancestors**, or `omni clean` invoked from a MACCRE-adjacent shell
could terminate its own caller.

### Z3. `.session_pids.json` is ignored, and unbounded

The project maintains its own registry of processes holding database handles.
`hunt_zombies` never reads it. Its state on audit:

```
total entries: 48
dead pids:     45
live pids:      3
oldest entry:  06/20/2026 17:54:32
```

Two months of accumulation with no pruning.

### Z4. PID reuse makes that registry actively dangerous — read this before wiring it in

The obvious improvement is "read `.session_pids.json` and kill those PIDs". That
would have been destructive. The three PIDs still alive were **not** MACCRE
processes:

| Registered PID | Registered as | Actually running now |
|---|---|---|
| 14684 | `nexus_memory.db` (2026-06-21) | `pwsh.exe` — a Kiro terminal |
| 4192 | `nexus_memory.db` (2026-07-12) | `PresentationFontCache.exe` |
| 10048 | `nexus_memory.db` (2026-08-26) | `LogiPluginService.exe` |

Windows recycles PIDs. A stale registry entry is not evidence of a live process; it
is a number that may now belong to anything, including the operator's own terminal.

**Fix — mandatory rule:** never terminate on a registry PID alone. An entry is
actionable only when *all* hold:

1. the PID is alive, **and**
2. the process creation time is consistent with the recorded `started`, **and**
3. its command line matches a MACCRE signature

Anything else is a stale entry and should be **pruned, not killed**. Pruning dead
entries on every `omni clean` also keeps the file from reaching 48 stale rows again.

### Z5. Nothing is logged about what was killed

`hunt_zombies` logs `"Hunting zombies..."` and never says what it found or
terminated. An operator cannot tell a clean tree from a failed hunt — which is
precisely the ambiguity Rule IV asks them to resolve.

---

## Documentation defect

### D1. `omni qa --smart` is declared and ignored

`argparse` accepts `--smart`, and `OMNI_DESIGN_SPEC.md` lists it under **Current
Capabilities (Implemented)**. `enforce_quality_gates(py_engine, target)` takes no
`smart` parameter and `args.smart` is never read. `omni-proposed-improvements.txt`
contains the intended implementation, so the flag was added and the logic never
wired.

It fails safe — a full Ruff run rather than a partial one — so this is a docs and
expectations defect, not a correctness one. But the workspace steering also
describes the behaviour, and that description is currently false. Either implement
it or mark it unimplemented in both places.

---

## Proposed change set, in priority order

| # | Change | Risk |
|---|---|---|
| 1 | Recursive `__pycache__` / `*.pyc` purge, excluding `.venv` | low |
| 2 | Bounded retry on cache-dir removal; report failures | low |
| 3 | Add `.pytest_cache`, `.mypy_cache`, `.pyre` to the purge list | low |
| 4 | Per-category removal counts; conditional success line | low |
| 5 | Replace `wmic` with `Get-CimInstance`; check and log results | low |
| 6 | Broaden the process signature; exclude self and ancestors | **medium** |
| 7 | Prune dead `.session_pids.json` entries on every clean | low |
| 8 | Corroborate PID + start time + command line before any kill | **medium** |
| 9 | WAL: checkpoint first, delete only what remains and is safe | **medium** |
| 10 | Implement `--smart`, or correct both documents | low |

Items 6, 8 and 9 are the ones that can do harm if wrong — 6 and 8 terminate
processes, 9 touches data. They deserve a dry-run mode (`omni clean --dry-run`)
listing what *would* be killed and removed, which would also have made this entire
audit a single command.

### Recommended addition: `omni clean --dry-run` and `omni doctor`

`--dry-run` for the reasons above. An `omni doctor` that reports the state without
changing anything — cache counts, live MACCRE processes, stale registry entries,
orphaned WAL files — would turn Rule IV from "run clean and hope" into "look at
what is actually wrong". Every number in this audit came from ad-hoc PowerShell
that a `doctor` subcommand should be producing.

---

## Current state of `B:\EXO_GANS` after manual cleanup

Done by hand, since `omni clean` could not:

```
.ruff_cache:        absent
.pytest_cache:      absent
__pycache__ dirs:   0
.pyc files:         0
MACCRE processes:   0
.session_pids.json: pruned 48 -> 0 entries
```

`.session_pids.json` is untracked and listed in `.git/info/exclude`, so pruning it
has no repository effect.

**Not touched:** WAL/SHM artifacts under `__DATACENTER\499_TEST\`. They do not
affect code freshness, and deleting a WAL is the one action here that can lose
committed data. They are listed under C4 for proper handling.

The one live Python process on the machine is
`run-jedi-language-server.py` from the Kiro Python extension — an editor service,
not a MACCRE orphan.
