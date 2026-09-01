# ┌─────────────────────────────────────────────────────────────────────────────┐
# │  MACCREv2 ENGINEERING DOCTRINE                             Law Rev: 19.0   │
# ├─────────────────────────────────────────────────────────────────────────────┤
# │  I.   TYPING      All signatures: explicit Python 3.11+ type hints.        │
# │  II.  LINTING     Zero unused imports. No wildcards. 120-char line max.    │
# │  III. PATHS       Never hardcode absolute paths. Use get_maccre_root().     │
# │  VII. TEARDOWN    try/finally on all handles (omni clean compliance).      │
# │  VIII.TELEMETRY   No bare print(). logger only. JSON → 03_Agent_Ledgers.  │
# └─────────────────────────────────────────────────────────────────────────────┘
"""
maccre_core/orchestration/concurrency.py
========================================
Phase 6.12 — concurrency primitives shared by the swarm worker and the pool.

These unrelated-looking pieces live together because each is something that was
perfectly safe with one worker per process and stops being safe the moment
several run side by side:

1. **The scatter ceiling** (:data:`MAX_SCATTER_AGENTS`, :func:`resolve_scatter_cap`)
   — one authoritative number for "how wide can a scatter go", instead of a
   magic ``8`` duplicated across the UI and the engine.

2. **Thread-routed stdout/stderr** (:func:`install_thread_routing`,
   :func:`begin_thread_tee`, :func:`end_thread_tee`) — so per-node agent logs stay
   separate when several nodes execute at once.

3. **Per-path file locks** (:func:`file_lock`) and
   :func:`atomic_write_text` — so two threads writing the same artifact cannot
   interleave or leave a half-written file behind.

4. **A shared provider rate limiter** (:func:`get_provider_rate_limiter`) — one
   worker could never out-pace the inference provider on its own; eight can, and
   each worker builds its own router, so the budget has to live above them.

5. **The task lock heartbeat** (:func:`task_heartbeat`) — so lock age can tell a
   slow node apart from a dead one. Sequentially nothing needed to ask; a lock
   was held by the only worker there was.

Why stdout routing has to exist
-------------------------------
The baseline captured a node's console output by *globally reassigning*
``sys.stdout`` and ``sys.stderr`` for the duration of a task, then restoring them::

    orig_stdout = sys.stdout
    sys.stdout = _FileTee(agent_log_path, orig_stdout)   # process-wide!
    ...
    sys.stdout = orig_stdout

That works with exactly one worker per process and breaks in three ways with more:

- ``sys.stdout`` is process-wide. Two concurrent nodes each install their own tee,
  the second overwrites the first, and both nodes' output lands in whichever log
  file won the race — while the loser's log stays empty.
- The restore is "assign back the value I saw when I started". With interleaved
  workers that value is already stale, so a restore can install *another* node's
  tee as the process default, or resurrect a closed file handle.
- ``maccre_core.logger.DynamicStreamHandler.emit()`` re-reads ``sys.stdout`` on
  every single record. ``swarm_worker`` contains no bare ``print()`` calls at all,
  so **every** line in a ``*_agent.log`` arrives through that handler. The global
  swap is therefore not an edge case in the logging path — it *is* the logging
  path, and it is the whole interleaving vector.

The fix inverts the ownership. A routing stream is installed **once** and left in
place for the life of the process. Threads register and deregister their own sink;
the router dispatches each write by thread identity, and falls through to the real
console for any thread that has not registered one. ``DynamicStreamHandler`` then
keeps working unmodified, because the object it re-reads never changes — only the
routing table behind it does.

State contract
--------------
============================  ========================  ==========================
Object                        Owner                     Mutation rights
============================  ========================  ==========================
``_SINKS`` routing table      this module               ``begin/end_thread_tee``,
                                                        each thread touching only
                                                        its own entry
``sys.stdout`` / ``sys.stderr``  this module (after     ``install_thread_routing``
                              install)                  / ``uninstall`` only
``_PATH_LOCKS``               this module               ``file_lock`` only
============================  ========================  ==========================

No function here accepts a :class:`threading.Event`, so the observer rule in
``orchestration_oracle_principles.md`` cannot be violated from this module.
"""
from __future__ import annotations

import logging
import os
import sys
import threading
import time
from contextlib import contextmanager
from pathlib import Path
from typing import IO, Any, Iterator, Protocol

logger = logging.getLogger("maccre_core.concurrency")

__all__ = [
    "DEFAULT_HEARTBEAT_SECONDS",
    "DEFAULT_PROVIDER_RPM",
    "MAX_SCATTER_AGENTS",
    "SCATTER_HARD_CAP",
    "HeartbeatMonitor",
    "RateLimiter",
    "atomic_write_text",
    "begin_thread_tee",
    "end_thread_tee",
    "file_lock",
    "get_provider_rate_limiter",
    "install_thread_routing",
    "named_lock",
    "reset_provider_rate_limiters",
    "resolve_scatter_cap",
    "task_heartbeat",
    "thread_tee",
    "uninstall_thread_routing",
]

# ── 1. The scatter ceiling ────────────────────────────────────────────────────

#: Default maximum number of agents executing concurrently in one scatter.
#:
#: Single source of truth. Previously ``MAX_SCATTER: int = 8`` was redeclared as a
#: function-local in three separate places in ``nexus_plex.py``, so the slot count
#: the UI offered and the thread count the engine would run were free to drift.
MAX_SCATTER_AGENTS: int = 8

#: Absolute ceiling, per Era 2 roadmap §6.12. ``resolve_scatter_cap`` will not
#: exceed this even if a topology or config asks for more. Guards against a
#: malformed topology trying to open hundreds of threads and API connections.
SCATTER_HARD_CAP: int = 12


def resolve_scatter_cap(requested: int | None = None) -> int:
    """Clamp a requested concurrency level into the sanctioned range.

    Args:
        requested: Desired number of concurrent agents. ``None``, zero or
            negative means "use the default".

    Returns:
        A value in ``1 .. SCATTER_HARD_CAP``.
    """
    if requested is None or requested <= 0:
        requested = MAX_SCATTER_AGENTS
    return max(1, min(int(requested), SCATTER_HARD_CAP))


# ── 2. Thread-routed stdout / stderr ──────────────────────────────────────────


class _ThreadSink:
    """One open log file, shared by a thread's stdout **and** stderr routing.

    Deliberately one handle for both streams. The baseline built two ``_FileTee``
    objects over the *same* path, each opening it with mode ``"w"`` — so
    constructing the stderr tee truncated the file the stdout tee had just opened,
    and the two handles then wrote to one file through independent buffers with
    independent file positions.
    """

    def __init__(self, path: str) -> None:
        self.path = path
        self._lock = threading.Lock()
        self._closed = False
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        # buffering=1 (line buffered) so a crashed node still leaves readable logs.
        self._fh: IO[str] = open(path, "w", buffering=1, encoding="utf-8")  # noqa: SIM115

    def write(self, msg: str) -> None:
        with self._lock:
            if self._closed:
                return
            try:
                self._fh.write(msg)
            except (ValueError, OSError):
                # Never let a logging write take down a node.
                self._closed = True

    def flush(self) -> None:
        with self._lock:
            if self._closed:
                return
            try:
                self._fh.flush()
            except (ValueError, OSError):
                self._closed = True

    def close(self) -> None:
        with self._lock:
            if self._closed:
                return
            self._closed = True
            try:
                self._fh.close()
            except (ValueError, OSError):
                pass


#: thread ident -> sink. Guarded by _SINKS_LOCK.
_SINKS: dict[int, _ThreadSink] = {}
_SINKS_LOCK = threading.Lock()


def _sink_for_current_thread() -> _ThreadSink | None:
    with _SINKS_LOCK:
        return _SINKS.get(threading.get_ident())


class _RoutingStream:
    """A stdout/stderr stand-in that dispatches writes by thread identity.

    Installed once and never swapped out, which is what makes it safe:
    ``DynamicStreamHandler`` re-reads ``sys.stdout`` on every log record, so the
    object it finds must be stable even while the routing behind it changes.

    A thread with a registered sink gets its output written to **both** the real
    console and its own log file. A thread without one — the TUI main thread, the
    orchestrating thread, anything else in the process — passes straight through
    to the console and is unaffected.
    """

    def __init__(self, base: IO[str] | None) -> None:
        #: The real stream. May legitimately be ``None``: PyInstaller
        #: ``--noconsole`` builds (which ``omni build`` produces) have no stdout.
        self._base = base

    # ── stream protocol ───────────────────────────────────────────────────────

    def write(self, msg: str) -> int:
        if self._base is not None:
            try:
                self._base.write(msg)
            except (ValueError, OSError):
                pass
        sink = _sink_for_current_thread()
        if sink is not None:
            sink.write(msg)
        return len(msg)

    def writelines(self, lines: Any) -> None:
        for line in lines:
            self.write(line)

    def flush(self) -> None:
        if self._base is not None:
            try:
                self._base.flush()
            except (ValueError, OSError):
                pass
        sink = _sink_for_current_thread()
        if sink is not None:
            sink.flush()

    def fileno(self) -> int:
        """Delegate to the real stream.

        Windows console APIs and any ``subprocess`` call that inherits stdio will
        probe this. Raising ``OSError`` when there is no real stream is the same
        contract as a detached stream, which callers already handle.
        """
        if self._base is None:
            raise OSError("no underlying stream")
        return self._base.fileno()

    def isatty(self) -> bool:
        # False even when the console is a TTY: output is being duplicated into a
        # log file, so callers must not emit ANSI cursor control.
        return False

    def writable(self) -> bool:
        return True

    def readable(self) -> bool:
        return False

    def seekable(self) -> bool:
        return False

    @property
    def encoding(self) -> str:
        return getattr(self._base, "encoding", "utf-8") or "utf-8"

    @property
    def errors(self) -> str:
        return getattr(self._base, "errors", "replace") or "replace"

    @property
    def base_stream(self) -> IO[str] | None:
        """The real stream underneath. Exposed for tests and diagnostics."""
        return self._base


_INSTALL_LOCK = threading.Lock()
_original_stdout: IO[str] | None = None
_original_stderr: IO[str] | None = None
_installed = False


def install_thread_routing(
    base_stdout: IO[str] | None = None,
    base_stderr: IO[str] | None = None,
) -> None:
    """Install the routing streams over ``sys.stdout``/``sys.stderr``.

    Idempotent and safe to call from any thread. Called automatically by
    :func:`begin_thread_tee`, so production code rarely needs it directly.

    Args:
        base_stdout: Stream that non-teed writes pass through to. Defaults to the
            current ``sys.stdout``, which is what production wants — it preserves
            any redirection Textual has already installed for the TUI.
        base_stderr: Same, for stderr.

    The explicit arguments exist for tests. Wrapping whatever happens to be in
    ``sys.stdout`` is right in production but wrong under pytest, whose capture
    object is swapped per test and is not written to safely from worker threads —
    wrapping it wedges the test session. Tests pass a stable stream instead.
    """
    global _installed, _original_stdout, _original_stderr
    with _INSTALL_LOCK:
        if _installed:
            return
        _original_stdout = base_stdout if base_stdout is not None else sys.stdout
        _original_stderr = base_stderr if base_stderr is not None else sys.stderr
        sys.stdout = _RoutingStream(_original_stdout)  # type: ignore[assignment]
        sys.stderr = _RoutingStream(_original_stderr)  # type: ignore[assignment]
        _installed = True


def uninstall_thread_routing() -> None:
    """Restore the original streams. Primarily for tests.

    Production code should leave routing installed for the process lifetime —
    tearing it down is the mutable-global behaviour this module exists to remove.
    """
    global _installed, _original_stdout, _original_stderr
    with _INSTALL_LOCK:
        if not _installed:
            return
        # Only restore if nobody else has swapped the streams since; clobbering a
        # third party's redirection would be exactly the bug we are fixing.
        if isinstance(sys.stdout, _RoutingStream):
            sys.stdout = _original_stdout  # type: ignore[assignment]
        if isinstance(sys.stderr, _RoutingStream):
            sys.stderr = _original_stderr  # type: ignore[assignment]
        _original_stdout = None
        _original_stderr = None
        _installed = False


def is_thread_routing_installed() -> bool:
    """True when the routing streams are in place."""
    return _installed


def begin_thread_tee(path: str) -> None:
    """Start duplicating this thread's console output into *path*.

    Replaces the baseline's ``sys.stdout = _FileTee(...)``. Ensures routing is
    installed, then registers a sink for the calling thread only. Other threads
    are unaffected.

    Calling twice on one thread closes the previous sink first, so a leaked
    ``begin`` cannot strand a file handle.

    Args:
        path: Log file to write. Parent directories are created. Opened with
            mode ``"w"``, matching baseline behaviour — each task's log path
            already includes its node id and queue row id, so it is unique.
    """
    install_thread_routing()
    ident = threading.get_ident()
    try:
        sink = _ThreadSink(path)
    except OSError as exc:
        # A missing drive or a permission problem must not abort the node — the
        # console still gets the output, only the sidecar log is lost.
        logger.warning("[CONCURRENCY] Could not open thread log %s: %s", path, exc)
        return
    with _SINKS_LOCK:
        previous = _SINKS.get(ident)
        _SINKS[ident] = sink
    if previous is not None:
        previous.close()


def end_thread_tee() -> None:
    """Stop duplicating this thread's output and close its sink.

    Safe to call when no sink is registered, so it can live unconditionally in a
    ``finally`` block.
    """
    ident = threading.get_ident()
    with _SINKS_LOCK:
        sink = _SINKS.pop(ident, None)
    if sink is not None:
        sink.close()


@contextmanager
def thread_tee(path: str) -> Iterator[None]:
    """Context-manager form of :func:`begin_thread_tee`."""
    begin_thread_tee(path)
    try:
        yield
    finally:
        end_thread_tee()


def active_tee_count() -> int:
    """Number of threads currently teeing output. For tests and diagnostics."""
    with _SINKS_LOCK:
        return len(_SINKS)


# ── 3. Per-path file locks and atomic writes ──────────────────────────────────

#: lock key -> lock. Grows with the number of distinct keys used, which is
#: bounded by a job's artifact and payload set, so it is not a leak worth reaping.
_NAMED_LOCKS: dict[str, threading.Lock] = {}
_NAMED_LOCKS_META = threading.Lock()


def _normalise(path: str | os.PathLike[str]) -> str:
    return os.path.normcase(os.path.abspath(os.fspath(path)))


@contextmanager
def named_lock(key: str) -> Iterator[None]:
    """Serialise this process's threads on an arbitrary *key*.

    In-process only — it coordinates threads, not separate processes. That is the
    right scope for Phase 6.12, where concurrency comes from threads inside one
    interpreter. Cross-process coordination stays with SQLite, which has its own
    locking.

    Use a key that names the *resource* being protected, not the operation. Two
    different resources must never share a key, or unrelated work serialises for
    no reason; two names for one resource must never differ, or the lock protects
    nothing.
    """
    with _NAMED_LOCKS_META:
        lock = _NAMED_LOCKS.get(key)
        if lock is None:
            lock = threading.Lock()
            _NAMED_LOCKS[key] = lock
    with lock:
        yield


@contextmanager
def file_lock(path: str | os.PathLike[str]) -> Iterator[None]:
    """Serialise this process's access to *path*.

    Two callers using different spellings of the same file (relative vs absolute,
    differing case on Windows) still contend correctly, because the key is
    normalised through :func:`os.path.abspath` and :func:`os.path.normcase`.
    """
    with named_lock(f"file:{_normalise(path)}"):
        yield


#: Attempts and backoff for the ``os.replace`` swap. See :func:`atomic_write_text`.
_REPLACE_ATTEMPTS: int = 40
_REPLACE_BACKOFF_SECONDS: float = 0.025


def atomic_write_text(
    path: str | os.PathLike[str],
    text: str,
    encoding: str = "utf-8",
) -> None:
    """Write *text* to *path* so readers never observe a partial file.

    Writes a sibling temp file, flushes and fsyncs it, then swaps it into place
    with :func:`os.replace`, which is atomic on both POSIX and Windows.

    This matters because several MACCRE artifacts are *both* an output and the
    next node's input payload — the unified session ledger most of all
    (``swarm_worker`` feeds the regenerated ledger straight into the next node).
    A reader that catches a plain ``open(path, "w")`` mid-write sees a truncated
    document and silently hands a half-empty payload to the next agent, with no
    error raised anywhere.

    Combine with :func:`file_lock` on the same path when several threads may write
    it, so writes are serialised as well as non-torn.

    **Windows retry.** ``os.replace`` onto a path another handle has open fails
    with ``PermissionError`` (``WinError 5``) on Windows, where POSIX would simply
    succeed. Concurrent readers are exactly the situation this function exists to
    serve, so a bare ``os.replace`` would trade torn reads for intermittent write
    failures. Measured during Phase 6.12 A4: a 6-writer / 1-reader test produced
    no torn reads but several dead writer threads. The swap is therefore retried
    with a short backoff (~1 s total) before giving up.
    """
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    # Temp file must be a sibling: os.replace is only atomic within a filesystem.
    tmp = target.with_name(f".{target.name}.{os.getpid()}.{threading.get_ident()}.tmp")
    try:
        with open(tmp, "w", encoding=encoding, newline="") as fh:
            fh.write(text)
            fh.flush()
            os.fsync(fh.fileno())

        last_error: OSError | None = None
        for attempt in range(_REPLACE_ATTEMPTS):
            try:
                os.replace(tmp, target)
                return
            except PermissionError as exc:
                # Windows: a reader holds the target open. Back off and retry.
                last_error = exc
                time.sleep(_REPLACE_BACKOFF_SECONDS * (1 + attempt // 8))
        raise last_error if last_error is not None else OSError("replace failed")
    except BaseException:
        try:
            if tmp.exists():
                tmp.unlink()
        except OSError:
            pass
        raise


# ── 4. Provider rate limiting ─────────────────────────────────────────────────

#: Requests per minute assumed for the inference provider when nothing else is
#: configured. Era 2 roadmap §6.12 requires a guard that "respects Gemini 3.x
#: paid-tier RPM limits (~1000-2000 RPM) across all concurrent threads". The
#: conservative end of that range is used as the default, because the cost of
#: guessing low is a small amount of added latency while the cost of guessing
#: high is provider-side 429s in the middle of a paid scatter.
#:
#: Override with the ``MACCRE_PROVIDER_RPM`` environment variable.
DEFAULT_PROVIDER_RPM: int = 1000


class RateLimiter:
    """Sliding-window request limiter, shared across threads.

    Sequential execution never needed this: one worker could not out-pace a
    provider on its own. Eight concurrent workers can, and a 429 mid-scatter is
    expensive — the lanes that already completed have been paid for.

    A sliding window rather than a token bucket, because provider limits are
    expressed as "N requests per minute" and a bucket would permit a burst of N
    followed by a stall. The window matches the published semantics.

    Thread-safe. All state is guarded by an internal :class:`threading.Condition`,
    and waiters are woken as capacity frees up rather than polling.
    """

    def __init__(self, max_per_minute: int, window_seconds: float = 60.0) -> None:
        """
        Args:
            max_per_minute: Requests permitted per window. Values below 1 are
                clamped to 1 — a limiter that permits nothing would deadlock the
                swarm rather than protect it.
            window_seconds: Window length. Configurable so tests need not take a
                minute to observe the behaviour.
        """
        self.max_per_minute = max(1, int(max_per_minute))
        self.window_seconds = float(window_seconds)
        self._condition = threading.Condition()
        self._timestamps: list[float] = []
        self._granted = 0
        self._waits = 0
        self._total_wait_seconds = 0.0

    def _prune(self, now: float) -> None:
        """Drop timestamps that have fallen out of the window. Caller holds the lock."""
        cutoff = now - self.window_seconds
        if self._timestamps and self._timestamps[0] < cutoff:
            self._timestamps = [t for t in self._timestamps if t >= cutoff]

    def acquire(self, timeout: float | None = None) -> bool:
        """Reserve one request slot, blocking until one is free.

        Args:
            timeout: Maximum seconds to wait. ``None`` waits indefinitely.

        Returns:
            True when a slot was reserved. False only on timeout — in which case
            **nothing was reserved** and the caller must not proceed with the
            request.
        """
        deadline = None if timeout is None else time.monotonic() + timeout
        waited_from: float | None = None
        with self._condition:
            while True:
                now = time.monotonic()
                self._prune(now)
                if len(self._timestamps) < self.max_per_minute:
                    self._timestamps.append(now)
                    self._granted += 1
                    if waited_from is not None:
                        self._waits += 1
                        self._total_wait_seconds += now - waited_from
                    return True

                # At capacity. The earliest timestamp determines when a slot frees.
                if waited_from is None:
                    waited_from = now
                wait_for = (self._timestamps[0] + self.window_seconds) - now
                if deadline is not None:
                    remaining = deadline - now
                    if remaining <= 0:
                        return False
                    wait_for = min(wait_for, remaining)
                # Positive floor so a clock quirk cannot spin.
                self._condition.wait(timeout=max(0.001, wait_for))

    def try_acquire(self) -> bool:
        """Reserve a slot only if one is free right now."""
        return self.acquire(timeout=0.0)

    def release_unused(self) -> None:
        """Return the most recently reserved slot.

        For a request that was reserved but never actually sent (an early
        validation failure, say), so a rejected call does not consume quota.
        """
        with self._condition:
            if self._timestamps:
                self._timestamps.pop()
                self._granted = max(0, self._granted - 1)
                self._condition.notify()

    @property
    def in_window(self) -> int:
        """Requests currently counted inside the window."""
        with self._condition:
            self._prune(time.monotonic())
            return len(self._timestamps)

    @property
    def stats(self) -> dict[str, float]:
        """Counters for telemetry and tests."""
        with self._condition:
            return {
                "max_per_minute": float(self.max_per_minute),
                "granted": float(self._granted),
                "waits": float(self._waits),
                "total_wait_seconds": self._total_wait_seconds,
            }


#: provider name -> limiter. Process-wide on purpose: every worker thread builds
#: its own router, so a per-router limiter would enforce nothing.
_RATE_LIMITERS: dict[str, RateLimiter] = {}
_RATE_LIMITERS_LOCK = threading.Lock()


def _configured_rpm() -> int:
    raw = os.environ.get("MACCRE_PROVIDER_RPM", "").strip()
    if not raw:
        return DEFAULT_PROVIDER_RPM
    try:
        return max(1, int(raw))
    except ValueError:
        logger.warning(
            "[CONCURRENCY] MACCRE_PROVIDER_RPM=%r is not an integer; using %d.",
            raw, DEFAULT_PROVIDER_RPM,
        )
        return DEFAULT_PROVIDER_RPM


def get_provider_rate_limiter(
    provider: str = "gemini",
    max_per_minute: int | None = None,
) -> RateLimiter:
    """Return the process-wide limiter for *provider*, creating it on first use.

    Shared deliberately. Each :class:`UniversalSwarmWorker` constructs its own
    ``UniversalRouter``, so a limiter owned by a router would count one thread's
    requests and miss the other seven.

    Args:
        provider: Limiter key. Separate providers have separate budgets.
        max_per_minute: Override for the first call that creates the limiter.
            Later calls return the existing limiter unchanged, so the rate cannot
            be silently redefined mid-flight.
    """
    key = provider.strip().lower() or "gemini"
    with _RATE_LIMITERS_LOCK:
        limiter = _RATE_LIMITERS.get(key)
        if limiter is None:
            rpm = max_per_minute if max_per_minute is not None else _configured_rpm()
            limiter = RateLimiter(rpm)
            _RATE_LIMITERS[key] = limiter
            logger.info(
                "[CONCURRENCY] Provider rate limiter for %r: %d req/min.", key, limiter.max_per_minute
            )
        return limiter


def reset_provider_rate_limiters() -> None:
    """Drop every provider limiter. For tests only."""
    with _RATE_LIMITERS_LOCK:
        _RATE_LIMITERS.clear()

# ── 5. Task lock heartbeat ────────────────────────────────────────────────────

#: Seconds between lock refreshes. Chosen against the reclaim timeout, not in
#: isolation: it must be comfortably shorter, so a healthy worker misses several
#: beats' worth of margin before anything considers it dead. At the sanctioned
#: eight-wide scatter this is ~1.6 extra write transactions per second across the
#: whole pool, which is negligible next to the 2-3 writes each node already makes.
DEFAULT_HEARTBEAT_SECONDS: float = 5.0


class _HeartbeatBroker(Protocol):
    """The single method :class:`HeartbeatMonitor` needs from a broker.

    A structural type rather than an import of ``MessageBroker``, so this module
    keeps its zero-dependency position at the bottom of the orchestration stack.
    """

    def heartbeat_task(self, row_id: int) -> bool: ...


class HeartbeatMonitor:
    """Refreshes one task's lock on a background daemon thread.

    Why a separate thread is mandatory rather than convenient
    --------------------------------------------------------
    The obvious cheaper design is to refresh the lock from inside the node's own
    execution path, at whatever checkpoints already exist. That cannot work here.
    A node's wall-clock time is dominated by a single blocking call into the
    inference provider, which can occupy tens of seconds and offers no callback
    to hook. A stack sitting inside ``recv()`` cannot heartbeat on its own
    behalf, and those are exactly the seconds during which the lock must not look
    abandoned.

    Connection ownership
    --------------------
    ``LocalMessageBroker`` keeps one SQLite connection per thread, so this thread
    transparently gets its own. That is required, not incidental: sharing the
    node thread's connection would let a heartbeat's ``UPDATE`` join whatever
    transaction the node had open, and ``fetch_and_lock_task``'s
    ``BEGIN EXCLUSIVE`` would stop being exclusive.

    Failure policy
    --------------
    A heartbeat failure never propagates. Losing a lock refresh is a recoverable
    degradation — worst case the lock eventually looks stale — whereas letting
    the exception escape would kill a node that is running perfectly well. A
    transient error is retried on the next tick; a definitive "this row is no
    longer locked" stops the thread, because there is nothing left to refresh.
    """

    def __init__(
        self,
        broker: _HeartbeatBroker,
        row_id: int,
        interval: float = DEFAULT_HEARTBEAT_SECONDS,
    ) -> None:
        self._broker = broker
        self._row_id = int(row_id)
        #: Positive floor: a zero interval would spin the CPU and flood SQLite.
        self._interval = max(0.01, float(interval))
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        #: Successful refreshes. Read by tests and diagnostics.
        self.beats = 0
        #: Set when the broker reported the row was no longer locked.
        self.lock_lost = False
        #: Count of refreshes that raised. Non-zero is a contention signal worth
        #: recording in UT-0, not necessarily a defect.
        self.errors = 0

    def _run(self) -> None:
        # wait() returns True only when stop is set, so this both paces the loop
        # and provides immediate, non-polling shutdown.
        while not self._stop.wait(self._interval):
            try:
                still_locked = self._broker.heartbeat_task(self._row_id)
            except Exception as exc:  # noqa: BLE001 - see "Failure policy" above
                self.errors += 1
                logger.warning(
                    "[HEARTBEAT] Refresh failed for task %d (%s: %s); will retry.",
                    self._row_id, type(exc).__name__, exc,
                )
                continue
            if not still_locked:
                # Completed, released or reclaimed. Nothing to vouch for.
                self.lock_lost = True
                logger.debug(
                    "[HEARTBEAT] Task %d is no longer locked; stopping.", self._row_id
                )
                return
            self.beats += 1

    def start(self) -> None:
        """Begin heartbeating. Idempotent."""
        if self._thread is not None:
            return
        self._thread = threading.Thread(
            target=self._run,
            name=f"heartbeat-{self._row_id}",
            daemon=True,
        )
        self._thread.start()

    def stop(self, join_timeout: float = 2.0) -> None:
        """Stop heartbeating and join the thread. Safe to call more than once.

        The join is bounded and the thread is a daemon, so a heartbeat wedged in
        a slow SQLite write can delay teardown briefly but can never prevent the
        process from exiting.
        """
        self._stop.set()
        thread, self._thread = self._thread, None
        if thread is not None and thread.is_alive():
            thread.join(timeout=join_timeout)

    @property
    def is_running(self) -> bool:
        thread = self._thread
        return thread is not None and thread.is_alive()


@contextmanager
def task_heartbeat(
    broker: _HeartbeatBroker,
    row_id: int,
    interval: float = DEFAULT_HEARTBEAT_SECONDS,
) -> Iterator[HeartbeatMonitor]:
    """Keep *row_id*'s lock fresh for the duration of the block.

    Wrap node execution with this. On exit — normal, exceptional or cancelled —
    the heartbeat stops, so a dead worker stops vouching for itself and its lock
    is allowed to age out.

    Yields:
        The :class:`HeartbeatMonitor`, whose ``beats``, ``errors`` and
        ``lock_lost`` counters are readable after the block for telemetry.
    """
    monitor = HeartbeatMonitor(broker, row_id, interval)
    monitor.start()
    try:
        yield monitor
    finally:
        monitor.stop()
