# ┌─────────────────────────────────────────────────────────────────────────────┐
# │  MACCREv2 Test Suite — Phase 6.12 Task A7: Remaining Shared-State Hazards    │
# └─────────────────────────────────────────────────────────────────────────────┘
"""
tests/test_shared_state_hazards.py
==================================
Phase 6.12 Task A7 — the process-global state that concurrent workers touch.

Three hazards, each with a failing-before / passing-after test:

1. ``CacheManager.get_or_create_cache`` — a read-modify-write over a shared JSON
   file with a **network upload in the middle**. Lost updates, duplicate uploads,
   and a load path that silently translated a torn read into "the registry is
   empty" and then persisted that.
2. ``setup_session_loggers`` — closes and re-adds every ``FileHandler`` on a
   *shared* logger, and ``execute_cycle`` calls it on every task claim.
3. ``MACCRE_ACTIVE_PROJECT`` — a process-global environment write performed once
   per task by every worker thread.
"""
from __future__ import annotations

import inspect
import json
import threading
from pathlib import Path
from typing import Any

import pytest

from maccre_core import logger as logger_module
from maccre_core.orchestration.cache_manager import CacheManager
from maccre_core.orchestration.concurrency import named_lock
from maccre_core.orchestration.swarm_worker import UniversalSwarmWorker


# ── named_lock, the primitive A7 depends on ───────────────────────────────────


class TestNamedLock:
    def test_same_key_serialises(self) -> None:
        inside = 0
        max_inside = 0
        counter = threading.Lock()
        start = threading.Barrier(6)

        def contend() -> None:
            nonlocal inside, max_inside
            start.wait(timeout=15)
            for _ in range(20):
                with named_lock("shared-resource"):
                    with counter:
                        inside += 1
                        max_inside = max(max_inside, inside)
                    with counter:
                        inside -= 1

        threads = [threading.Thread(target=contend, daemon=True) for _ in range(6)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=30)
            assert not t.is_alive()
        assert max_inside == 1

    def test_distinct_keys_do_not_contend(self) -> None:
        held = threading.Event()
        release = threading.Event()
        other_done = threading.Event()

        def holder() -> None:
            with named_lock("key-a"):
                held.set()
                release.wait(timeout=10)

        def other() -> None:
            held.wait(timeout=10)
            with named_lock("key-b"):
                other_done.set()

        t1 = threading.Thread(target=holder, daemon=True)
        t2 = threading.Thread(target=other, daemon=True)
        t1.start()
        t2.start()
        assert other_done.wait(timeout=10), "distinct keys must not block"
        release.set()
        t1.join(timeout=10)
        t2.join(timeout=10)


# ── CacheManager ──────────────────────────────────────────────────────────────


class FakeGeminiClient:
    """Counts uploads and simulates the latency that opens the race window."""

    def __init__(self, upload_delay: float = 0.05) -> None:
        self.upload_delay = upload_delay
        self.uploads: list[str] = []
        self._lock = threading.Lock()
        self._counter = 0

    def create_cached_content(
        self,
        model: str,
        contents: list[dict[str, Any]],
        system_instruction: Any = None,
        ttl_seconds: int = 3600,
    ) -> str:
        import time

        with self._lock:
            self._counter += 1
            uri = f"cachedContents/fake{self._counter:04d}"
            self.uploads.append(uri)
        time.sleep(self.upload_delay)  # the window a lost update needs
        return uri


def _contents(text: str) -> list[dict[str, Any]]:
    return [{"role": "user", "parts": [{"text": text}]}]


@pytest.fixture()
def manager() -> CacheManager:
    return CacheManager()


class TestCacheManagerRegistry:
    def test_creates_and_records_a_cache(self, manager: CacheManager) -> None:
        client = FakeGeminiClient(upload_delay=0.0)
        uri = manager.get_or_create_cache(client, "gemini-2.5-flash", _contents("hello"))
        assert uri == "cachedContents/fake0001"
        registry = json.loads(manager._registry_path.read_text(encoding="utf-8"))
        assert len(registry) == 1
        assert next(iter(registry.values()))["cache_uri"] == uri

    def test_second_identical_request_is_a_hit(self, manager: CacheManager) -> None:
        client = FakeGeminiClient(upload_delay=0.0)
        first = manager.get_or_create_cache(client, "gemini-2.5-flash", _contents("hello"))
        second = manager.get_or_create_cache(client, "gemini-2.5-flash", _contents("hello"))
        assert first == second
        assert len(client.uploads) == 1

    def test_registry_is_written_atomically(self, manager: CacheManager) -> None:
        source = inspect.getsource(CacheManager._save_registry)
        assert "atomic_write_text" in source
        assert "write_text(json.dumps" not in source

    def test_concurrent_identical_payloads_upload_once(
        self, manager: CacheManager
    ) -> None:
        """The 8-wide ``full_copy`` scatter case.

        Every lane gets the same payload, so all eight hash identically. Without
        per-payload serialisation each lane uploads the same >120 kB context.
        """
        client = FakeGeminiClient(upload_delay=0.05)
        results: list[str | None] = []
        results_lock = threading.Lock()
        start = threading.Barrier(8)

        def lane() -> None:
            start.wait(timeout=20)
            uri = manager.get_or_create_cache(
                client, "gemini-2.5-flash", _contents("shared scatter payload")
            )
            with results_lock:
                results.append(uri)

        threads = [threading.Thread(target=lane, daemon=True) for _ in range(8)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=60)
            assert not t.is_alive()

        assert len(client.uploads) == 1, (
            f"{len(client.uploads)} uploads for one payload — dedupe is not holding"
        )
        assert len(set(results)) == 1, "lanes disagreed on the cache URI"

    def test_concurrent_distinct_payloads_never_lose_a_registry_entry(
        self, manager: CacheManager
    ) -> None:
        """The lost-update hazard.

        Eight distinct payloads upload concurrently. Without re-reading the
        registry inside the lock before inserting, later saves overwrite earlier
        threads' entries and paid caches leak untracked.
        """
        client = FakeGeminiClient(upload_delay=0.05)
        start = threading.Barrier(8)

        def lane(idx: int) -> None:
            start.wait(timeout=20)
            manager.get_or_create_cache(
                client, "gemini-2.5-flash", _contents(f"distinct payload {idx}")
            )

        threads = [
            threading.Thread(target=lane, args=(i,), daemon=True) for i in range(8)
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=60)
            assert not t.is_alive()

        registry = json.loads(manager._registry_path.read_text(encoding="utf-8"))
        assert len(client.uploads) == 8, "distinct payloads must each upload"
        assert len(registry) == 8, (
            f"registry has {len(registry)} of 8 entries — updates were lost"
        )
        recorded = {entry["cache_uri"] for entry in registry.values()}
        assert recorded == set(client.uploads)

    def test_corrupt_registry_is_preserved_not_silently_discarded(
        self, manager: CacheManager
    ) -> None:
        """A parse failure used to return ``{}``, which the next save persisted.

        That turned one torn read into total loss of every live cache entry, with
        no error logged anywhere.
        """
        manager._registry_path.parent.mkdir(parents=True, exist_ok=True)
        manager._registry_path.write_text('{"truncated": ', encoding="utf-8")

        assert manager._load_registry() == {}
        corrupt = manager._registry_path.with_suffix(".corrupt.json")
        assert corrupt.exists(), "the unparseable registry must be kept for diagnosis"
        assert "truncated" in corrupt.read_text(encoding="utf-8")

    def test_empty_registry_file_is_not_treated_as_corrupt(
        self, manager: CacheManager
    ) -> None:
        manager._registry_path.parent.mkdir(parents=True, exist_ok=True)
        manager._registry_path.write_text("", encoding="utf-8")
        assert manager._load_registry() == {}
        assert not manager._registry_path.with_suffix(".corrupt.json").exists()

    def test_non_object_registry_is_rejected(self, manager: CacheManager) -> None:
        manager._registry_path.parent.mkdir(parents=True, exist_ok=True)
        manager._registry_path.write_text("[1, 2, 3]", encoding="utf-8")
        assert manager._load_registry() == {}

    def test_expired_entry_is_purged_and_re_uploaded(
        self, manager: CacheManager
    ) -> None:
        client = FakeGeminiClient(upload_delay=0.0)
        contents = _contents("expiring")
        manager.get_or_create_cache(client, "gemini-2.5-flash", contents, ttl_seconds=1)

        # Rewrite the entry as already past its safety buffer.
        registry = json.loads(manager._registry_path.read_text(encoding="utf-8"))
        key = next(iter(registry))
        registry[key]["expires_at"] = 0
        manager._registry_path.write_text(json.dumps(registry), encoding="utf-8")

        manager.get_or_create_cache(client, "gemini-2.5-flash", contents)
        assert len(client.uploads) == 2, "expired entry should force a re-upload"

    def test_upload_failure_returns_none_and_records_nothing(
        self, manager: CacheManager
    ) -> None:
        class Failing:
            def create_cached_content(self, **_kwargs: Any) -> str:
                raise RuntimeError("quota exceeded")

        assert manager.get_or_create_cache(Failing(), "m", _contents("x")) is None
        if manager._registry_path.exists():
            assert json.loads(manager._registry_path.read_text(encoding="utf-8")) == {}


# ── setup_session_loggers ─────────────────────────────────────────────────────


class TestSessionLoggerIdempotency:
    @pytest.fixture(autouse=True)
    def _reset(self) -> None:
        logger_module.reset_session_loggers()
        yield
        logger_module.reset_session_loggers()

    @staticmethod
    def _file_handlers() -> list[Any]:
        import logging

        from maccre_core.logger import ops_log

        return [h for h in ops_log._log.handlers if isinstance(h, logging.FileHandler)]

    def test_first_call_wires_handlers(self) -> None:
        logger_module.setup_session_loggers("TEST_PROJECT", "job_a7_one")
        assert self._file_handlers(), "expected at least the Op-logs handler"

    def test_repeat_call_for_same_session_does_not_churn_handlers(self) -> None:
        """The concurrency hazard.

        Re-running the body closes handlers another thread may be mid-write
        through, which raises ``ValueError: I/O operation on closed file`` and
        loses log lines.
        """
        logger_module.setup_session_loggers("TEST_PROJECT", "job_a7_two")
        before = [id(h) for h in self._file_handlers()]
        for _ in range(5):
            logger_module.setup_session_loggers("TEST_PROJECT", "job_a7_two")
        after = [id(h) for h in self._file_handlers()]
        assert before == after, "handlers were replaced on a repeat call"

    def test_repeat_calls_do_not_leak_handlers(self) -> None:
        logger_module.setup_session_loggers("TEST_PROJECT", "job_a7_three")
        count = len(self._file_handlers())
        for _ in range(5):
            logger_module.setup_session_loggers("TEST_PROJECT", "job_a7_three")
        assert len(self._file_handlers()) == count

    def test_a_different_session_does_re_wire(self) -> None:
        logger_module.setup_session_loggers("TEST_PROJECT", "job_a7_four")
        before = [id(h) for h in self._file_handlers()]
        logger_module.setup_session_loggers("TEST_PROJECT", "job_a7_five")
        after = [id(h) for h in self._file_handlers()]
        assert before != after, "a new session must get its own log files"

    def test_force_re_wires_the_same_session(self) -> None:
        logger_module.setup_session_loggers("TEST_PROJECT", "job_a7_six")
        before = [id(h) for h in self._file_handlers()]
        logger_module.setup_session_loggers("TEST_PROJECT", "job_a7_six", force=True)
        assert [id(h) for h in self._file_handlers()] != before

    def test_concurrent_setup_calls_do_not_corrupt_handler_state(self) -> None:
        """Eight workers claiming tasks for one job all call this."""
        errors: list[str] = []
        start = threading.Barrier(8)

        def worker() -> None:
            try:
                start.wait(timeout=20)
                for _ in range(5):
                    logger_module.setup_session_loggers("TEST_PROJECT", "job_a7_conc")
            except Exception as exc:  # noqa: BLE001
                errors.append(f"{type(exc).__name__}: {exc}")

        threads = [threading.Thread(target=worker, daemon=True) for _ in range(8)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=30)
            assert not t.is_alive()

        assert errors == [], f"concurrent setup raised: {errors[:3]}"
        assert len(self._file_handlers()) <= 2, (
            "handler count grew under concurrency — the idempotency guard leaked"
        )


# ── MACCRE_ACTIVE_PROJECT ─────────────────────────────────────────────────────


class TestActiveProjectEnvWrite:
    def test_task_queue_has_no_project_id_column(self, tmp_path: Path) -> None:
        """Establishes why the env write is safe today.

        ``task.get("project_id", self.project_name)`` can never hit, so every
        worker writes the value it already read at construction. If a
        ``project_id`` column is ever added, this fails and the env-driven path
        resolver must be replaced with explicit plumbing first.
        """
        from maccre_core.orchestration.local_broker import LocalMessageBroker

        broker = LocalMessageBroker(db_path=str(tmp_path / "q.db"))
        try:
            columns = {
                row[1]
                for row in broker._get_conn().execute("PRAGMA table_info(task_queue)")
            }
        finally:
            broker.close()
        assert "project_id" not in columns, (
            "task_queue gained a project_id column — cross-project concurrency is "
            "now reachable and MACCRE_ACTIVE_PROJECT can no longer be a global"
        )

    def test_env_write_is_guarded_by_a_conflict_check(self) -> None:
        """An unconditional write from N threads is what A7 removed."""
        source = inspect.getsource(UniversalSwarmWorker.execute_cycle)
        assert '_current_env_project' in source
        assert 'MACCRE_ACTIVE_PROJECT' in source
        # The write must be inside a conditional, not a bare statement.
        write_index = source.index('os.environ["MACCRE_ACTIVE_PROJECT"] = project_id')
        preceding = source[:write_index]
        assert "if _current_env_project != project_id:" in preceding

    def test_conflicting_project_is_logged_not_silent(self) -> None:
        source = inspect.getsource(UniversalSwarmWorker.execute_cycle)
        assert "logger.warning" in source
        assert "NOT supported" in source
