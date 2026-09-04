# 2026-09-03: Paranoia Mode — Honest Disable, and Removing a Hard Portability Blocker

## Summary

The hardware-token topology gate is now **honestly disabled** rather than silently inert,
and the topology loader is no longer Windows-only.

`maccre_core/utils/secret_auth.py` advertised *"Air-Gap Steganographic Hardware
Authentication… Uses NTFS Alternate Data Streams and Hardware tokens"* in the present tense
while `is_topology_approved()` was already `return True`. Three separate places asserted a
security control that did not exist: that module docstring, `pattern_executor`'s, and
`Analysis/Wave1/05_memory_schemas_utils_ledger.md`.

The larger cost was structural. `secret_auth` imported `ctypes.wintypes` at **module scope**,
which cannot import on a non-Windows host, and `topology_engine._pull_from_csv` imported it
**unguarded**. So the topology loader — on every execution path in the system — was
Windows-only, in service of a gate that always returned `True`. That is a hard Android blocker
of the same class as the DPAPI credential vault, and unlike the vault it cost nothing to
remove, because nothing depended on the value.

Found while assessing an unrelated question about using Google Drive file headers as a
laptop↔phone transport, which led into Alternate Data Streams and from there into this module.

## Files Modified

- `maccre_core/utils/secret_auth.py` — rewritten. Named the capability **Paranoia Mode**,
  introduced `PARANOIA_MODE_ENABLED` as the single seam, made all Win32 imports lazy, added
  `is_paranoia_mode_enabled()` and `has_auth_stamp()`, and rewrote the docstring to lead with
  the disabled state. `stamp_topology` keeps its real hardware check and now reports
  `SKIPPED:` rather than a success off Windows.
- `maccre_core/orchestration/topology_engine.py` — removed the `secret_auth` import and the
  unreachable `PermissionError`. Recorded why in the docstring, including where the
  enforcement point returns if the gate is revived.
- `maccre_core/patterns/pattern_executor.py` — `_sign_topology` → `_record_topology_hash`;
  dropped the unread ADS write and the `ADS auth stamp written` log line; kept the SHA-256
  content hash, which is a genuine audit record.
- `tests/test_paranoia_mode.py` — new, 17 tests.

## Function Signatures Added/Changed

```python
# secret_auth.py
PARANOIA_MODE_ENABLED: bool = False    # the single seam
AUTH_STAMP_TOKEN = "O_AUTH_VALID"
AUTH_STAMP_STREAM = "maccre_auth"

def is_paranoia_mode_enabled() -> bool: ...   # NEW — resolves the True/unchecked ambiguity
def is_windows() -> bool: ...                 # NEW — platform predicate
def has_auth_stamp(csv_path: str) -> bool: ...# NEW — reads the ADS; False off Windows
def stamp_topology(csv_path: str, target_hash: str) -> str: ...   # unchanged contract
def is_topology_approved(csv_path: str) -> bool: ...              # unchanged contract

# pattern_executor.py
def _record_topology_hash(self, topology_path: Path) -> None: ... # was _sign_topology
```

## State Contracts

| Object | Owner | Observers | Mutation Rights |
|---|---|---|---|
| `PARANOIA_MODE_ENABLED` | `secret_auth` module | `topology_engine` (indirect, now none), tests | Module only. Tests monkeypatch it; production code must never write it |
| `topology.csv:maccre_auth` (ADS) | `stamp_topology` | `has_auth_stamp` | Writer only. No longer written by `pattern_executor` |
| `topology.csv.stamp` (SHA-256) | `pattern_executor._record_topology_hash` | nothing reads it — audit record only | Owner only |

No `threading.Event`, `queue.Queue` or shared mutable runtime state is touched by this change.
`topology_engine._pull_from_csv` lost a dependency and gained none.

## Architecture Decisions

**Disabled honestly rather than deleted.** The operator's intent is real and wanted later:
abstract credential access behind a physical key the user keeps inserted for the session. So
the mechanism stays, the flag says it is off, and the docstring leads with that. A deleted
capability takes its reasoning with it; a silently inert one is worse than either.

**`is_paranoia_mode_enabled()` exists because `True` is ambiguous.** A caller receiving `True`
from `is_topology_approved` cannot tell *approved* from *not checked*. Doctrine 3's rule
against folding an ambiguous state into a success applies to authorisation answers as much as
to task statuses, so the two questions are now separately askable.

**`has_auth_stamp` returns `False` off Windows, not `True`.** A check that cannot be performed
has not passed. The permissive alternative is exactly the approximately-correct value
Principle 2 exists for — downstream logic would act on it.

**The enforcement point was removed from `topology_engine` rather than guarded.** With the gate
returning `True` unconditionally the call could only ever succeed, so a platform guard would
have preserved a Windows coupling for a no-op. The docstring records where the check returns if
Paranoia Mode is revived. *Alternative rejected:* keeping the import behind
`if sys.platform == "win32"` — that retains the coupling in spirit and leaves a reader thinking
a gate exists.

**The ADS write was deleted rather than corrected.** It had no reader. *Alternative rejected:*
keeping the write and fixing only the log line — that preserves dead work whose only effect is
to make a future reader believe authentication happens.

**The content hash was kept.** It is platform-neutral, it is a real audit record, and it is
what a future Paranoia Mode would stamp over.

**Pre-work protocol finding worth recording:** none of the four mandatory domain artifacts
documents the auth gate as load-bearing. `Wave2`'s pre-flight flowchart enumerates seven
validation points and `MASTER_FLOWCHART`'s `FE_CHECKS` six; the auth stamp is in neither. So
removing it contradicts nothing in the documented architecture.

**Also noticed, not fixed, recorded for the register:** `Wave2`'s broker section documents a
`tasks` table with `task_id`, `node_id`, `status`, `wait_for` plus a `task_deps` table. The
real table is `task_queue` with `id`, `job_id`, `current_node`, `lock_status`. That is a
seventh representation of the queue schema, this one in documentation, alongside the six found
on disk earlier today.

## Testing

`tests/test_paranoia_mode.py`, 17 tests in four classes.

**The load-bearing one is `test_docstring_cannot_drift_from_the_flag`.** It asserts that the
docstring says "CURRENTLY DISABLED" if and only if `PARANOIA_MODE_ENABLED` is `False`, so
flipping the flag without rewriting the prose fails, and rewriting the prose while the flag is
off fails too. **This is the test whose absence caused the original defect** — Doctrine 5's
applied rule, that every claim a document makes about behaviour needs a test that fails when
the claim goes false.

Two assertions read the AST rather than executing anything, and the trade is stated in the
module docstring: the failure mode is an *import-time platform* break that cannot be reproduced
on this host, because the suite runs on Windows where the bad import succeeds. An AST assertion
is weaker than an execution assertion; it is stronger than the no check that existed before.

**Revert-to-red, both performed and restored:**

| Injected fault | Test that went red |
|---|---|
| `PARANOIA_MODE_ENABLED = True` | `test_docstring_cannot_drift_from_the_flag`, plus `test_callers_can_distinguish_approved_from_unchecked` |
| `from ctypes import wintypes` restored at module scope | `test_secret_auth_has_no_windows_only_module_scope_imports` |

**Gate, all observed 2026-09-03:**

```
omni clean   purged 283 bytecode files, 4 WAL/SHM artifacts  (22:12)
omni qa      PASS, whole project                             (22:15)
pytest       784 collected / 784 passed, 189.34s             (22:19)
omni smoke   ALL CHECKS PASSED, inference 1.7s               (22:19)
```

`omni smoke` was run because `topology_engine` is on an execution path.

**Not verified.** The portability fix has **not been executed on a non-Windows host**, because
none is available — that is the entire point of the defect and also the limit of this evidence.
The claim "the topology loader now imports off Windows" rests on removing the only Windows-only
module-scope import from the chain, verified by AST, not on an Android or Linux run. It should
be treated as *the blocker was removed* rather than *portability is proven*, and the proof is
the first time the loader runs on the target platform.

The linear-flow slot flake did not reproduce in this run — five clean full-suite runs now
against one failure. Still unexplained, still blocks UT-0.
