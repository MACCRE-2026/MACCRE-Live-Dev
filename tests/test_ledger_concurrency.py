# ┌─────────────────────────────────────────────────────────────────────────────┐
# │  MACCREv2 Test Suite — Phase 6.12 Task A6: Ledger Generation Concurrency     │
# └─────────────────────────────────────────────────────────────────────────────┘
"""
tests/test_ledger_concurrency.py
================================
Phase 6.12 Task A6 — the unified session ledger is the highest-severity
concurrency hazard in the system.

``swarm_worker.execute_cycle`` regenerates it on every node completion and then
hands the returned path straight to ``broker.route_task`` as the **next** node's
input payload. So a torn read is not a cosmetic logging problem: it silently feeds
a truncated document to the next agent, and nothing raises.

Two properties are asserted:

* **Serialised per job** — concurrent regenerations do not interleave their
  read-collect-write.
* **Atomic swap** — a reader concurrent with a write always sees a complete
  document, never a partial one.

The tests drive the real ``flow_engine`` functions against a temporary datacenter
(``conftest`` points ``MACCRE_ROOT`` at ``tmp_path``), with no LLM and no live
queue.
"""
from __future__ import annotations

import inspect
import threading
from pathlib import Path

import pytest

from maccre_core.orchestration import flow_engine
from maccre_core.orchestration.flow_engine import (
    generate_unified_ledger,
    generate_unified_thoughts_ledger,
    thoughts_ledger_path,
    unified_ledger_path,
)
from maccre_core.utils.path_resolver import get_datacenter_path

JOB = "job_20260829-999999-a6ts"

#: Marker every complete ledger must carry. Used to detect truncation.
HEADER = "# Unified Session Ledger"


@pytest.fixture()
def seeded_job() -> str:
    """A job directory with several agent turns, as a real flow would leave it."""
    ledger_dir = get_datacenter_path("03_Agent_Ledgers", JOB)
    ledger_dir.mkdir(parents=True, exist_ok=True)
    for idx in range(6):
        # Bodies are long and distinct so a spliced read is detectable.
        body = f"LANE{idx} " + ("payload " * 400)
        (ledger_dir / f"AGENT_Lane{idx}_S0_{10 + idx}.md").write_text(
            f"# Lane {idx}\n\n{body}\n", encoding="utf-8"
        )
        (ledger_dir / f"AGENT_Lane{idx}_S0_{10 + idx}_agent.log").write_text(
            f"<thought>\nthinking about lane {idx}\n</thought>\n", encoding="utf-8"
        )
    return JOB


# ── Path resolution ───────────────────────────────────────────────────────────


class TestLedgerPaths:
    """The lock key is derived from these, so they must match what gets written."""

    def test_unified_path_is_under_code_artifacts(self) -> None:
        path = unified_ledger_path(JOB)
        assert path.name == "unified_session_ledger.md"
        assert path.parent.name == JOB
        assert path.parent.parent.name == "04_Code_Artifacts"

    def test_studio_sessions_get_their_own_name_and_directory(self) -> None:
        path = unified_ledger_path("studio_session_abc123")
        assert path.name == "unified_chat_ledger.md"
        assert path.parent.name == "abc123-Chat"

    def test_thoughts_path_is_a_sibling(self) -> None:
        assert thoughts_ledger_path(JOB).parent == unified_ledger_path(JOB).parent
        assert thoughts_ledger_path(JOB).name == "unified_thoughts_ledger.md"

    def test_unified_and_thoughts_use_distinct_lock_keys(self) -> None:
        """Non-reentrant locks: same key would self-deadlock.

        ``generate_unified_ledger`` calls ``generate_unified_thoughts_ledger``
        while holding its own lock.
        """
        assert unified_ledger_path(JOB) != thoughts_ledger_path(JOB)

    def test_path_helper_agrees_with_what_generation_writes(
        self, seeded_job: str
    ) -> None:
        """If these diverged, the lock would guard the wrong file."""
        written = Path(generate_unified_ledger(seeded_job))
        assert written == unified_ledger_path(seeded_job)


# ── Serialisation and atomicity ───────────────────────────────────────────────


class TestConcurrentGeneration:
    def test_single_generation_produces_a_complete_ledger(
        self, seeded_job: str
    ) -> None:
        path = Path(generate_unified_ledger(seeded_job))
        content = path.read_text(encoding="utf-8")
        assert content.startswith(HEADER)
        for idx in range(6):
            assert f"LANE{idx}" in content, f"lane {idx} missing from the ledger"

    def test_concurrent_generation_never_yields_a_torn_read(
        self, seeded_job: str
    ) -> None:
        """The core A6 property, at 8-wide scatter width.

        Eight nodes finishing at once each regenerate the ledger while a reader
        polls it. Every observed read must be a complete document.
        """
        target = unified_ledger_path(seeded_job)
        generate_unified_ledger(seeded_job)  # ensure it exists before reading

        errors: list[str] = []
        torn: list[str] = []
        stop = threading.Event()
        start = threading.Barrier(8)

        def regenerate() -> None:
            try:
                start.wait(timeout=30)
                for _ in range(4):
                    generate_unified_ledger(seeded_job)
            except Exception as exc:  # noqa: BLE001
                errors.append(f"{type(exc).__name__}: {exc}")

        def reader() -> None:
            while not stop.is_set():
                try:
                    content = target.read_text(encoding="utf-8")
                except (FileNotFoundError, PermissionError):
                    continue
                if not content:
                    continue
                # A complete ledger starts with the header and ends with the
                # canonization footer. Anything else is a partial document.
                if not content.startswith(HEADER):
                    torn.append(f"missing header, len={len(content)}")
                elif "Canonization Status" not in content:
                    torn.append(f"truncated body, len={len(content)}")

        r = threading.Thread(target=reader, daemon=True)
        r.start()
        threads = [threading.Thread(target=regenerate, daemon=True) for _ in range(8)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=120)
            assert not t.is_alive(), "ledger generation deadlocked"
        stop.set()
        r.join(timeout=15)

        assert errors == [], f"generation raised: {errors[:3]}"
        assert torn == [], f"observed {len(torn)} torn reads: {torn[:3]}"

    def test_concurrent_generation_is_serialised(self, seeded_job: str) -> None:
        """Assembly bodies must not overlap.

        Wraps the unlocked body to detect re-entry. Without the per-job lock,
        eight threads would be inside it simultaneously.
        """
        original = flow_engine._generate_unified_ledger_unlocked
        inside = 0
        max_inside = 0
        counter_lock = threading.Lock()

        def instrumented(job_id: str, steps: object = None) -> str:
            nonlocal inside, max_inside
            with counter_lock:
                inside += 1
                max_inside = max(max_inside, inside)
            try:
                return original(job_id, steps)  # type: ignore[arg-type]
            finally:
                with counter_lock:
                    inside -= 1

        flow_engine._generate_unified_ledger_unlocked = instrumented  # type: ignore[assignment]
        try:
            start = threading.Barrier(8)

            def worker() -> None:
                start.wait(timeout=30)
                generate_unified_ledger(seeded_job)

            threads = [threading.Thread(target=worker, daemon=True) for _ in range(8)]
            for t in threads:
                t.start()
            for t in threads:
                t.join(timeout=120)
                assert not t.is_alive()
        finally:
            flow_engine._generate_unified_ledger_unlocked = original  # type: ignore[assignment]

        assert max_inside == 1, (
            f"{max_inside} threads were inside the assembly body at once — "
            "the per-job lock is not holding"
        )

    def test_different_jobs_are_not_serialised_against_each_other(
        self, seeded_job: str
    ) -> None:
        """The lock is per job, not global — unrelated flows must not block."""
        other = "job_20260829-999998-a6tb"
        other_dir = get_datacenter_path("03_Agent_Ledgers", other)
        other_dir.mkdir(parents=True, exist_ok=True)
        (other_dir / "AGENT_Other_S0_1.md").write_text("# Other\n\nbody\n", encoding="utf-8")

        assert unified_ledger_path(seeded_job) != unified_ledger_path(other)
        # Both complete without contending on one key.
        generate_unified_ledger(seeded_job)
        generate_unified_ledger(other)
        assert unified_ledger_path(other).exists()

    def test_nested_thoughts_generation_does_not_self_deadlock(
        self, seeded_job: str
    ) -> None:
        """``generate_unified_ledger`` calls the thoughts generator inside its lock."""
        done = threading.Event()

        def run() -> None:
            generate_unified_ledger(seeded_job)
            done.set()

        t = threading.Thread(target=run, daemon=True)
        t.start()
        assert done.wait(timeout=60), "self-deadlock between the two ledger locks"
        t.join(timeout=10)
        assert thoughts_ledger_path(seeded_job).exists()

    def test_thoughts_ledger_can_be_generated_directly(self, seeded_job: str) -> None:
        path = Path(generate_unified_thoughts_ledger(seeded_job))
        assert path == thoughts_ledger_path(seeded_job)
        assert path.exists()

    def test_repeated_generation_is_stable(self, seeded_job: str) -> None:
        """Same inputs, same output — no accumulation or duplication."""
        first = Path(generate_unified_ledger(seeded_job)).read_text(encoding="utf-8")
        second = Path(generate_unified_ledger(seeded_job)).read_text(encoding="utf-8")
        # Timestamps differ, so compare the turn count rather than the bytes.
        assert first.count("LANE0") == second.count("LANE0")
        assert second.count("LANE0") >= 1


# ── No plain truncating writes may return ─────────────────────────────────────


class TestNoTruncatingWrites:
    """Source guard: a reintroduced ``write_text`` on a ledger reopens the hazard."""

    @pytest.mark.parametrize(
        "func",
        [
            flow_engine._generate_unified_ledger_unlocked,
            flow_engine._generate_unified_thoughts_ledger_unlocked,
            flow_engine.generate_targeted_ledger,
        ],
    )
    def test_ledger_writers_use_atomic_write_text(self, func: object) -> None:
        source = inspect.getsource(func)  # type: ignore[arg-type]
        assert "atomic_write_text(output_path" in source, (
            f"{getattr(func, '__name__', func)} must write atomically"
        )
        assert "output_path.write_text" not in source, (
            f"{getattr(func, '__name__', func)} still truncates in place"
        )

    def test_public_generators_take_a_lock(self) -> None:
        for func in (generate_unified_ledger, generate_unified_thoughts_ledger):
            source = inspect.getsource(func)
            assert "file_lock(" in source, f"{func.__name__} is not serialised"

    def test_debounce_was_deliberately_not_added(self) -> None:
        """Records a design decision so it is not "fixed" later.

        A debounce would skip regeneration while still returning the path, so the
        caller would route the *previous* snapshot — missing the output of the
        node that just finished. Serialisation costs CPU; debouncing would cost
        correctness on the one artifact that feeds the next agent.
        """
        source = inspect.getsource(generate_unified_ledger)
        assert "debounc" in source.lower(), (
            "the no-debounce rationale must stay documented at the call site"
        )
