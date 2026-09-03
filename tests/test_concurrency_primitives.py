# ┌─────────────────────────────────────────────────────────────────────────────┐
# │  MACCREv2 Test Suite — Phase 6.12 Task A4: Concurrency Primitives            │
# └─────────────────────────────────────────────────────────────────────────────┘
"""
tests/test_concurrency_primitives.py
====================================
Phase 6.12 Task A4 — thread-routed stdout/stderr, per-path locks, atomic writes.

The behaviour under test replaces a process-wide ``sys.stdout`` swap. The two
properties that matter:

* Concurrent threads writing console output land in **their own** log files.
* ``sys.stdout`` is installed **once** and never reassigned afterwards, because
  ``maccre_core.logger.DynamicStreamHandler.emit()`` re-reads it on every record.
"""
from __future__ import annotations

import io
import sys
import threading
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

import pytest

from maccre_core.orchestration.concurrency import (
    MAX_SCATTER_AGENTS,
    SCATTER_HARD_CAP,
    active_tee_count,
    atomic_write_text,
    begin_thread_tee,
    end_thread_tee,
    file_lock,
    install_thread_routing,
    is_thread_routing_installed,
    resolve_scatter_cap,
    thread_tee,
    uninstall_thread_routing,
)


class _ThreadSafeSink(io.StringIO):
    """A ``StringIO`` whose writes are serialised.

    Stands in for the console. ``io.StringIO`` is not thread-safe, and several
    tests here write from up to eight threads at once.
    """

    def __init__(self) -> None:
        super().__init__()
        self._lock = threading.Lock()

    def write(self, s: str) -> int:  # type: ignore[override]
        with self._lock:
            return super().write(s)


@contextmanager
def isolated_streams() -> Iterator[_ThreadSafeSink]:
    """Install routing over a private, thread-safe stand-in for the console.

    **Must be used inside the test body, not a fixture.** pytest resumes its own
    global capture around each test phase, and ``SysCapture.start()`` reassigns
    ``sys.stdout``. Anything a fixture installs during setup is therefore
    clobbered before the test body runs.

    Routing must also never end up wrapping pytest's capture object: that object
    is a ``TextIOWrapper`` over a ``BytesIO`` and is not thread-safe, so the
    eight-thread tests below can wedge the whole session through it. Symptom
    observed while building this module — every test class passed in isolation
    while the full file hung with no failure reported.
    """
    sink = _ThreadSafeSink()
    stdout_before, stderr_before = sys.stdout, sys.stderr
    uninstall_thread_routing()
    install_thread_routing(base_stdout=sink, base_stderr=sink)
    try:
        yield sink
    finally:
        end_thread_tee()
        uninstall_thread_routing()
        sys.stdout, sys.stderr = stdout_before, stderr_before


@pytest.fixture(autouse=True)
def _guaranteed_cleanup() -> None:
    """Backstop: never leak a tee or a routing stream into the next test."""
    stdout_before, stderr_before = sys.stdout, sys.stderr
    try:
        yield
    finally:
        end_thread_tee()
        uninstall_thread_routing()
        sys.stdout, sys.stderr = stdout_before, stderr_before


# ── Scatter ceiling ───────────────────────────────────────────────────────────


class TestScatterCap:
    def test_default_is_eight(self) -> None:
        assert MAX_SCATTER_AGENTS == 8

    def test_hard_cap_matches_era2_roadmap(self) -> None:
        assert SCATTER_HARD_CAP == 12

    def test_none_and_nonpositive_fall_back_to_default(self) -> None:
        for value in (None, 0, -1, -99):
            assert resolve_scatter_cap(value) == MAX_SCATTER_AGENTS

    def test_in_range_requests_pass_through(self) -> None:
        for value in (1, 4, 8, 12):
            assert resolve_scatter_cap(value) == value

    def test_requests_above_the_hard_cap_are_clamped(self) -> None:
        assert resolve_scatter_cap(13) == SCATTER_HARD_CAP
        assert resolve_scatter_cap(9999) == SCATTER_HARD_CAP

    def test_result_is_always_at_least_one(self) -> None:
        """A pool sized zero would hang forever waiting on work nobody claims."""
        for value in (None, -5, 0, 1, 50):
            assert resolve_scatter_cap(value) >= 1

    def test_default_never_exceeds_the_hard_cap(self) -> None:
        assert MAX_SCATTER_AGENTS <= SCATTER_HARD_CAP


class TestScatterCapSingleSourceOfTruth:
    """Phase 6.12 Task A9.

    ``MAX_SCATTER: int = 8`` was a function-local redeclared in three separate
    methods of ``nexus_plex.py``, so the slot count the UI offered and the thread
    count the engine would run were free to drift apart.

    Asserted by reading the source rather than importing ``nexus_plex``, which
    would pull in the whole Textual app for a constant check.
    """

    @staticmethod
    def _nexus_source() -> str:
        from maccre_core.utils.path_resolver import get_maccre_root

        # MACCRE_ROOT is redirected to tmp_path by conftest, so locate the real
        # repository relative to this test file instead.
        repo_root = Path(__file__).resolve().parent.parent
        source_path = repo_root / "maccre_tui" / "nexus_plex.py"
        assert source_path.exists(), f"expected {source_path} to exist (root={get_maccre_root()})"
        return source_path.read_text(encoding="utf-8")

    def test_nexus_plex_imports_the_shared_constant(self) -> None:
        source = self._nexus_source()
        assert (
            "from maccre_core.orchestration.concurrency import MAX_SCATTER_AGENTS" in source
        )

    def test_no_hardcoded_scatter_cap_remains(self) -> None:
        source = self._nexus_source()
        offenders = [
            line.strip()
            for line in source.splitlines()
            if "MAX_SCATTER" in line
            and "= 8" in line
            and not line.lstrip().startswith("#")
        ]
        assert offenders == [], f"hardcoded scatter cap is back: {offenders}"

    def test_every_local_alias_derives_from_the_shared_constant(self) -> None:
        source = self._nexus_source()
        assignments = [
            line.strip()
            for line in source.splitlines()
            if "MAX_SCATTER: int =" in line and not line.lstrip().startswith("#")
        ]
        assert assignments, "expected the local MAX_SCATTER aliases to still exist"
        for line in assignments:
            assert line.endswith("MAX_SCATTER_AGENTS"), f"not derived from SSOT: {line}"


# ── Routing installation ──────────────────────────────────────────────────────


class TestRoutingInstallation:
    def test_install_is_idempotent(self) -> None:
        with isolated_streams():
            first = sys.stdout
            install_thread_routing()
            install_thread_routing()
            assert sys.stdout is first, "re-install must not replace the stream object"

    def test_install_replaces_both_streams(self) -> None:
        before_out, before_err = sys.stdout, sys.stderr
        with isolated_streams():
            assert sys.stdout is not before_out
            assert sys.stderr is not before_err
            assert is_thread_routing_installed()

    def test_uninstall_restores_the_originals(self) -> None:
        before_out, before_err = sys.stdout, sys.stderr
        with isolated_streams():
            pass
        assert sys.stdout is before_out
        assert sys.stderr is before_err
        assert not is_thread_routing_installed()

    def test_begin_tee_installs_routing_automatically(self, tmp_path: Path) -> None:
        uninstall_thread_routing()
        assert not is_thread_routing_installed()
        begin_thread_tee(str(tmp_path / "n.log"))
        assert is_thread_routing_installed()

    def test_stream_object_is_stable_across_tee_lifecycles(self, tmp_path: Path) -> None:
        """The property DynamicStreamHandler depends on.

        It does ``self.stream = sys.stdout`` on every emit, so the identity of
        ``sys.stdout`` must not change when nodes start and finish — only the
        routing table behind it may change.
        """
        with isolated_streams():
            begin_thread_tee(str(tmp_path / "a.log"))
            stream_during = sys.stdout
            end_thread_tee()
            assert sys.stdout is stream_during
            begin_thread_tee(str(tmp_path / "b.log"))
            assert sys.stdout is stream_during
            end_thread_tee()
            assert sys.stdout is stream_during


# ── Per-thread routing behaviour ──────────────────────────────────────────────


class TestThreadRouting:
    def test_output_reaches_the_registered_log(self, tmp_path: Path) -> None:
        log = tmp_path / "node.log"
        with isolated_streams(), thread_tee(str(log)):
            sys.stdout.write("hello from the node\n")
            sys.stdout.flush()
        assert "hello from the node" in log.read_text(encoding="utf-8")

    def test_output_also_reaches_the_console(self, tmp_path: Path) -> None:
        """Teeing means duplicating, not diverting — the TUI must still see it."""
        log = tmp_path / "node.log"
        with isolated_streams() as console:
            with thread_tee(str(log)):
                sys.stdout.write("visible\n")
                sys.stdout.flush()
            console_text = console.getvalue()
        assert "visible" in console_text
        assert "visible" in log.read_text(encoding="utf-8")

    def test_unregistered_threads_do_not_write_to_any_log(self, tmp_path: Path) -> None:
        log = tmp_path / "owner.log"
        with isolated_streams():
            begin_thread_tee(str(log))

            def other_thread() -> None:
                # No tee registered for this thread.
                sys.stdout.write("from an unregistered thread\n")
                sys.stdout.flush()

            t = threading.Thread(target=other_thread, daemon=True)
            t.start()
            t.join(timeout=10)
            end_thread_tee()

        content = log.read_text(encoding="utf-8")
        assert "from an unregistered thread" not in content

    def test_concurrent_threads_get_isolated_logs(self, tmp_path: Path) -> None:
        """The core A4 property, at full 8-wide scatter width."""
        slots = 8
        lines_each = 40
        start = threading.Barrier(slots)
        errors: list[str] = []

        def worker(slot: int) -> None:
            log = tmp_path / f"lane_{slot}.log"
            try:
                begin_thread_tee(str(log))
                start.wait(timeout=15)
                for i in range(lines_each):
                    sys.stdout.write(f"slot={slot} line={i}\n")
                sys.stdout.flush()
            except Exception as exc:  # noqa: BLE001
                errors.append(f"slot {slot}: {exc}")
            finally:
                end_thread_tee()

        with isolated_streams():
            threads = [
                threading.Thread(target=worker, args=(s,), daemon=True)
                for s in range(slots)
            ]
            for t in threads:
                t.start()
            for t in threads:
                t.join(timeout=30)
                assert not t.is_alive()
        assert not errors, errors

        for slot in range(slots):
            content = (tmp_path / f"lane_{slot}.log").read_text(encoding="utf-8")
            own = [ln for ln in content.splitlines() if ln.strip()]
            assert len(own) == lines_each, f"slot {slot} lost lines: {len(own)}"
            # No other slot's output may appear in this slot's log.
            for other in range(slots):
                if other != slot:
                    assert f"slot={other} " not in content, (
                        f"slot {other}'s output leaked into slot {slot}'s log"
                    )

    def test_end_tee_is_safe_without_a_begin(self) -> None:
        """It lives unconditionally in a finally block, so it must never raise."""
        end_thread_tee()
        end_thread_tee()

    def test_repeated_begin_closes_the_previous_sink(self, tmp_path: Path) -> None:
        first = tmp_path / "first.log"
        second = tmp_path / "second.log"
        with isolated_streams():
            begin_thread_tee(str(first))
            sys.stdout.write("to first\n")
            begin_thread_tee(str(second))
            sys.stdout.write("to second\n")
            end_thread_tee()

        assert "to first" in first.read_text(encoding="utf-8")
        assert "to second" in second.read_text(encoding="utf-8")
        assert "to second" not in first.read_text(encoding="utf-8")

    def test_tee_registry_is_emptied_on_teardown(self, tmp_path: Path) -> None:
        with isolated_streams():
            assert active_tee_count() == 0
            begin_thread_tee(str(tmp_path / "x.log"))
            assert active_tee_count() == 1
            end_thread_tee()
            assert active_tee_count() == 0

    def test_single_handle_per_thread_so_stderr_cannot_truncate_stdout(
        self, tmp_path: Path
    ) -> None:
        """Regression for the baseline's double-open.

        The old code built two ``_FileTee`` objects over the same path, each with
        mode ``"w"``. Constructing the second truncated the file the first had
        just opened. One sink serves both streams now.
        """
        log = tmp_path / "node.log"
        with isolated_streams(), thread_tee(str(log)):
            sys.stdout.write("line via stdout\n")
            sys.stderr.write("line via stderr\n")
            sys.stdout.flush()
            sys.stderr.flush()
        content = log.read_text(encoding="utf-8")
        assert "line via stdout" in content
        assert "line via stderr" in content

    def test_unopenable_log_path_does_not_raise(self, tmp_path: Path) -> None:
        """A bad log path must degrade to console-only, never abort the node."""
        blocker = tmp_path / "not_a_dir"
        blocker.write_text("i am a file", encoding="utf-8")
        with isolated_streams():
            begin_thread_tee(str(blocker / "nested" / "node.log"))
            sys.stdout.write("still running\n")
            end_thread_tee()

    def test_isatty_is_false_while_teeing(self, tmp_path: Path) -> None:
        with isolated_streams(), thread_tee(str(tmp_path / "n.log")):
            assert sys.stdout.isatty() is False


# ── Per-path locks ────────────────────────────────────────────────────────────


class TestFileLock:
    def test_serialises_threads_on_one_path(self, tmp_path: Path) -> None:
        target = tmp_path / "shared.txt"
        overlaps: list[int] = []
        inside = 0
        counter_lock = threading.Lock()
        start = threading.Barrier(6)

        def contend() -> None:
            nonlocal inside
            start.wait(timeout=15)
            for _ in range(20):
                with file_lock(target):
                    with counter_lock:
                        inside += 1
                        current = inside
                    if current > 1:
                        overlaps.append(current)
                    with counter_lock:
                        inside -= 1

        threads = [threading.Thread(target=contend, daemon=True) for _ in range(6)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=30)
            assert not t.is_alive()
        assert overlaps == [], f"lock allowed {len(overlaps)} concurrent entries"

    def test_different_paths_do_not_block_each_other(self, tmp_path: Path) -> None:
        released = threading.Event()
        finished = threading.Event()

        def holder() -> None:
            with file_lock(tmp_path / "a.txt"):
                released.wait(timeout=10)

        def other() -> None:
            with file_lock(tmp_path / "b.txt"):
                finished.set()

        t1 = threading.Thread(target=holder, daemon=True)
        t2 = threading.Thread(target=other, daemon=True)
        t1.start()
        t2.start()
        assert finished.wait(timeout=10), "distinct paths must not contend"
        released.set()
        t1.join(timeout=10)
        t2.join(timeout=10)

    def test_path_spellings_normalise_to_one_lock(self, tmp_path: Path) -> None:
        """Absolute vs relative vs differing case must contend, not diverge."""
        target = tmp_path / "Shared.txt"
        blocked = threading.Event()
        entered = threading.Event()

        def holder() -> None:
            with file_lock(str(target)):
                entered.set()
                blocked.wait(timeout=5)

        t = threading.Thread(target=holder, daemon=True)
        t.start()
        assert entered.wait(timeout=10)
        # Same file, different spelling — must be blocked while the holder waits.
        acquired = threading.Event()

        def contender() -> None:
            with file_lock(str(target).upper()):
                acquired.set()

        t2 = threading.Thread(target=contender, daemon=True)
        t2.start()
        assert not acquired.wait(timeout=0.5), "case-variant path took a second lock"
        blocked.set()
        t.join(timeout=10)
        t2.join(timeout=10)
        assert acquired.is_set()

    def test_lock_is_released_when_the_body_raises(self, tmp_path: Path) -> None:
        target = tmp_path / "x.txt"
        with pytest.raises(RuntimeError):
            with file_lock(target):
                raise RuntimeError("boom")
        # Must not deadlock.
        with file_lock(target):
            pass


# ── Atomic writes ─────────────────────────────────────────────────────────────


class TestAtomicWriteText:
    def test_writes_content(self, tmp_path: Path) -> None:
        target = tmp_path / "out.md"
        atomic_write_text(target, "hello")
        assert target.read_text(encoding="utf-8") == "hello"

    def test_overwrites_existing_content(self, tmp_path: Path) -> None:
        target = tmp_path / "out.md"
        target.write_text("old and much longer content", encoding="utf-8")
        atomic_write_text(target, "new")
        assert target.read_text(encoding="utf-8") == "new"

    def test_creates_missing_parent_directories(self, tmp_path: Path) -> None:
        target = tmp_path / "deep" / "nested" / "out.md"
        atomic_write_text(target, "x")
        assert target.read_text(encoding="utf-8") == "x"

    def test_leaves_no_temp_files_behind(self, tmp_path: Path) -> None:
        atomic_write_text(tmp_path / "out.md", "x")
        assert [p.name for p in tmp_path.iterdir()] == ["out.md"]

    def test_concurrent_writers_never_produce_a_torn_file(self, tmp_path: Path) -> None:
        """The property that protects the unified ledger.

        The ledger is both an output and the next node's input payload, so a
        reader catching a partial write silently feeds a truncated document into
        the next agent. Each write here is a distinct length; any read must match
        one of them exactly, never a splice.
        """
        target = tmp_path / "ledger.md"
        bodies = [f"body-{i}-" + ("x" * (500 * (i + 1))) for i in range(6)]
        atomic_write_text(target, bodies[0])
        start = threading.Barrier(7)
        bad_reads: list[int] = []
        write_errors: list[str] = []
        stop = threading.Event()

        def writer(idx: int) -> None:
            start.wait(timeout=15)
            for _ in range(25):
                try:
                    atomic_write_text(target, bodies[idx])
                except Exception as exc:  # noqa: BLE001
                    write_errors.append(f"{type(exc).__name__}: {exc}")
                    return

        def reader() -> None:
            start.wait(timeout=15)
            while not stop.is_set():
                try:
                    content = target.read_text(encoding="utf-8")
                except (FileNotFoundError, PermissionError):
                    continue
                if content not in bodies:
                    bad_reads.append(len(content))

        writers = [
            threading.Thread(target=writer, args=(i,), daemon=True)
            for i in range(len(bodies))
        ]
        r = threading.Thread(target=reader, daemon=True)
        r.start()
        for t in writers:
            t.start()
        for t in writers:
            t.join(timeout=60)
            assert not t.is_alive()
        stop.set()
        r.join(timeout=10)

        assert bad_reads == [], f"observed {len(bad_reads)} torn reads: {bad_reads[:5]}"
        # Writers must also survive. On Windows os.replace onto a path a reader
        # holds open raises WinError 5; without the retry loop this list fills up.
        assert write_errors == [], f"writers failed: {write_errors[:5]}"
        assert target.read_text(encoding="utf-8") in bodies

    def test_replace_retries_rather_than_failing_on_a_held_target(
        self, tmp_path: Path
    ) -> None:
        """Explicit coverage of the Windows ``os.replace`` contention path."""
        target = tmp_path / "held.md"
        atomic_write_text(target, "original")
        release = threading.Event()
        holder_ready = threading.Event()

        def holder() -> None:
            with open(target, encoding="utf-8") as fh:
                fh.read()
                holder_ready.set()
                release.wait(timeout=5)

        t = threading.Thread(target=holder, daemon=True)
        t.start()
        assert holder_ready.wait(timeout=10)

        result: list[str] = []

        def replacer() -> None:
            atomic_write_text(target, "replaced")
            result.append("ok")

        w = threading.Thread(target=replacer, daemon=True)
        w.start()
        release.set()
        w.join(timeout=30)
        t.join(timeout=10)

        assert result == ["ok"], "replace should have retried until the handle closed"
        assert target.read_text(encoding="utf-8") == "replaced"
