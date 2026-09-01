---
inclusion: always
---

# Omni Pipeline Mandate — The Sovereign Execution Boundary

**Always applied.** This governs every command run against this workspace, by any
engineer or agent, in any phase.

---

## Where Omni Lives

```
C:\OmniBuilder\omni.py      # implementation
C:\OmniBuilder\omni.bat     # launcher, on the system PATH
```

Omni is **system-pathed and lives outside the repository by design**. It is
deliberately decoupled from `requirements.txt` so that governance tooling never
depends on the environment it governs.

**Consequence for agents:** a recursive search inside `B:\EXO_GANS` for `omni*`
returns nothing. That is expected and is **not** evidence that omni is missing.
A previous session searched the workspace, found nothing, concluded "omni.py appears
to be missing", and silently substituted scoped `ruff`/`pyright` calls for the rest
of the session. Those scoped calls passed while three real defects sat in the tree.
Resolve omni with `Get-Command omni` or `where omni`, never with a workspace search.

Reference docs, in the same folder:
- `C:\OmniBuilder\omni_system_state_doctrine.md` — usage doctrine
- `C:\OmniBuilder\OMNI_DESIGN_SPEC.md` — design spec

---

## Invocation

Always from the project root, with no path argument:

```powershell
cd B:\EXO_GANS
omni qa       # quality gate: Ruff + Pyright in one pass
omni clean    # zombie hunt + cache/WAL purge
omni run      # canonical launcher (resolves entry point, hunts zombies first)
omni build    # zombie hunt -> QA -> purge -> PyInstaller
omni smoke    # E2E swarm validation via free Gemma API ($0)
```

`omni qa --smart` restricts Ruff to git-modified files. Pyright still runs globally.
Use it for tight inner loops only; the full `omni qa` is the gate.

---

## The Rules

### I. Sovereign Prefix Mandate
Never invoke bare Python to launch, test, or check this project.

```powershell
omni run                                    # correct
.\.venv\Scripts\python.exe run.py           # WRONG
```

Omni resolves the isolated engine (`.venv\Scripts\python.exe`) itself, and hunts
orphaned swarm workers before launching. Bypassing it means inheriting whatever
zombie SQLite connections the last crashed run left holding locks.

### II. `omni qa` Is The Only QA Gate
Run it after **every** change, before reporting any work complete.

Do **not** substitute scoped invocations:

```powershell
omni qa                                                  # correct
python -m ruff check maccre_core/orchestration           # WRONG — success-siloing
python -m pyright maccre_core/orchestration/flow_engine.py  # WRONG — worse
```

Scoped checks pass while the rest of the project is broken. `omni qa` lints the
**whole project** and type-checks per `pyrightconfig.json`, which is the only way
cross-module type breaks, broken return tuples and dangling imports in adjacent
scopes get caught.

Note the asymmetry that makes scoped runs actively misleading here:
- `ruff.toml` excludes `_archive`, `__Deprecated`, `user_scripts`, `.venv`
- `pyrightconfig.json` **excludes `maccre_tui` entirely** and includes only
  `maccre_core`, `maccre_mcp.py`, `maccre.py`

So a scoped `pyright some_tui_file.py` will happily type-check a file the real gate
never looks at, and a scoped `ruff check some_dir` will miss everything outside it.

### III. Omni Does Not Run Tests
`omni qa` is lint + types. It has **no pytest stage**. Static analysis passing is not
the same as the code working — this is the exact gap that let the previous Phase 6.12
attempt report "all checks pass" while the test suite could not even be collected
(an `ImportError` in one orphaned test module aborted collection repo-wide, so *zero*
tests ran).

The full gate for any orchestration change is therefore:

```powershell
omni qa                                          # lint + types, whole project
.\.venv\Scripts\python.exe -m pytest tests -q    # the suite must actually run
omni smoke                                       # E2E swarm, when touching execution paths
```

Running `pytest` directly is the one sanctioned exception to Rule I, because omni
exposes no test command. Always confirm the **collected count**, not just the pass
count — a collection error can silently reduce the suite to nothing.

### IV. `omni clean` Before Chasing Ghosts
"I fixed it but it's still broken, then it magically worked later" is a stale
`__pycache__` or a zombie process holding a SQLite lock. Run `omni clean` before
spending any time on a phantom bug.

`omni clean` protects `maccre_system.log`, `build_pipeline.log` and any `*telemetry*`
log. It does delete other root-level `*.log` files, `.ruff_cache`, `build`, `dist`,
`__pycache__`, and root `*.db-wal` / `*.db-shm` artifacts.

### V. Windows Is Still The Backstop
Omni is a JIT CI/CD gatekeeper in front of the interpreter, not a replacement for OS
controls. It does not circumvent UAC or PowerShell execution policy.

---

## Reporting Standard

Never claim work is complete on the strength of a scoped check. State which gate ran
and what it covered. If `omni qa` was not run, say so explicitly rather than implying
the project is clean.
