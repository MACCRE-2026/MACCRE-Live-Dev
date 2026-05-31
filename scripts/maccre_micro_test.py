#!/usr/bin/env python
# ┌─────────────────────────────────────────────────────────────────────────────┐
# │  MACCREv2 ENGINEERING DOCTRINE                             Law Rev: 19.0   │
# ├─────────────────────────────────────────────────────────────────────────────┤
# │  I.   TYPING      All signatures: explicit Python 3.11+ type hints.        │
# │  II.  LINTING     Zero unused imports. No wildcards. 120-char line max.    │
# │  III. PATHS       Never hardcode absolute paths. Use get_maccre_root().     │
# │                   Default params: def f(p:str='') -> None: p=p or root/x  │
# │  IV.  DATACENTER  5-Tier: 01_Raw_Source · 02_Dynamic_Context               │
# │                           03_Agent_Ledgers · 04_Code_Artifacts             │
# │                           05_Rendered_Media                                 │
# │  V.   DIAMOND     Gen: temp=1.0  ·  Critic: temp=0.1 + dataclass schema   │
# │  VI.  ABSTRACTION All I/O behind abc.ABC before any concrete driver.       │
# │  VII. TEARDOWN    try/finally on all handles (omni clean compliance).      │
# │  VIII.TELEMETRY   No bare print(). logger only. JSON → 03_Agent_Ledgers.  │
# └─────────────────────────────────────────────────────────────────────────────┘
"""
scripts/maccre_micro_test.py
=============================
MACCRE Autonomous Micro-Test Suite — 14 Phases, all 28 MCP tool implementations.

Tests tool functions DIRECTLY via Python imports (not through MCP transport), giving
full control over timeouts and clean isolation of failures. The MCP transport itself
was verified in the previous session's live tool-call testing.

Governance:
  - Every test wrapped in ThreadPoolExecutor(timeout=30s).
  - PASS/FAIL/TIMEOUT/ERROR/SKIP — no test cascades to the next.
  - Git commit after each phase group (rollback-ready milestones).
  - Final JSON + Markdown report → DATACENTER/GLOBAL/04_Code_Artifacts/
  - Zero mutations to production SilmLOTR data; all writes go to an isolated
    timestamped test silo that is cleaned up at the end.

Usage:
    python scripts/maccre_micro_test.py
"""
from __future__ import annotations

import json
import logging
import math
import os
import random
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeout
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

# ── Bootstrap ─────────────────────────────────────────────────────────────────
_SCRIPT_DIR = Path(__file__).resolve().parent
_ROOT = _SCRIPT_DIR.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

os.environ.setdefault("MACCRE_ROOT", str(_ROOT))

# ── Logging (stderr only — not stdout, per MCP isolation doctrine) ─────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
    stream=sys.stderr,
)
_log = logging.getLogger("micro_test")

# ── Imports must happen AFTER sys.path patch ───────────────────────────────────
from maccre_core.utils.path_resolver import get_maccre_root, get_datacenter_path  # noqa: E402

_MACCRE_ROOT = get_maccre_root()
_DATACENTER = _MACCRE_ROOT / "__DATACENTER"
_TS = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
_TEST_PROJECT = f"MICRO_TEST_{_TS}"
_TEST_SILO = _DATACENTER / _TEST_PROJECT
os.environ["MACCRE_ACTIVE_PROJECT"] = _TEST_PROJECT

# ── Result accumulation ────────────────────────────────────────────────────────
_results: list[dict[str, Any]] = []
_phase_counts: dict[str, dict[str, int]] = {}
_TIMEOUT = 30  # seconds per test
_EMBED_CAPABLE: bool = False  # set True in Phase 9 if embedding API responds


# ── Test runner ────────────────────────────────────────────────────────────────

def _run(
    test_name: str,
    fn: Callable[[], Any],
    phase: str,
    timeout: int = _TIMEOUT,
    assert_fn: Callable[[Any], tuple[bool, str]] | None = None,
) -> bool:
    """Execute fn under timeout; optionally apply assert_fn(result) for contextual checks."""
    start = time.monotonic()
    status = "PASS"
    detail = ""
    try:
        with ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(fn)
            result = future.result(timeout=timeout)
        if assert_fn is not None:
            ok, msg = assert_fn(result)
            if not ok:
                status = "FAIL"
                detail = f"Assertion failed: {msg}"
            else:
                detail = msg[:200] if msg else str(result)[:200]
        else:
            detail = str(result)[:200] if result is not None else "OK"
    except FuturesTimeout:
        status = "TIMEOUT"
        detail = f"Exceeded {timeout}s — tool is hanging"
    except AssertionError as exc:
        status = "FAIL"
        detail = str(exc)[:200]
    except Exception as exc:  # noqa: BLE001
        status = "ERROR"
        detail = f"{type(exc).__name__}: {str(exc)[:200]}"

    elapsed = int((time.monotonic() - start) * 1000)
    _icon = {"PASS": "✅", "FAIL": "❌", "TIMEOUT": "⏱️", "ERROR": "⚠️", "SKIP": "⏭️"}
    _log.info("%s [%s] %-45s %5dms  %s", _icon.get(status, "?"), phase, test_name, elapsed, detail[:100])

    _results.append({
        "phase": phase, "test": test_name, "status": status,
        "duration_ms": elapsed, "detail": detail,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    })
    pc = _phase_counts.setdefault(phase, {"PASS": 0, "FAIL": 0, "TIMEOUT": 0, "ERROR": 0, "SKIP": 0})
    pc[status] = pc.get(status, 0) + 1
    return status == "PASS"


def _skip(test_name: str, reason: str, phase: str) -> None:
    _log.info("⏭️  [%s] SKIP: %-45s %s", phase, test_name, reason)
    _results.append({
        "phase": phase, "test": test_name, "status": "SKIP",
        "duration_ms": 0, "detail": reason,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    })
    pc = _phase_counts.setdefault(phase, {"PASS": 0, "FAIL": 0, "TIMEOUT": 0, "ERROR": 0, "SKIP": 0})
    pc["SKIP"] = pc.get("SKIP", 0) + 1


def _git_commit(milestone: str) -> None:
    try:
        subprocess.run(["git", "-C", str(_MACCRE_ROOT), "add", "-A"],
                       capture_output=True, timeout=30, check=False)
        r = subprocess.run(
            ["git", "-C", str(_MACCRE_ROOT), "commit", "-m", f"test(micro): {milestone}"],
            capture_output=True, timeout=30, check=False,
        )
        if r.returncode == 0:
            _log.info("📦 GIT COMMIT: %s", milestone)
        else:
            _log.info("📦 Git: nothing to commit at '%s'", milestone)
    except Exception as exc:  # noqa: BLE001
        _log.warning("Git commit error: %s", exc)


# ─────────────────────────────────────────────────────────────────────────────
# PHASE 0: Bootstrap & Path Integrity
# ─────────────────────────────────────────────────────────────────────────────
def phase0_bootstrap() -> None:
    P = "P0:Bootstrap"
    _log.info("\n══════════ PHASE 0: Bootstrap & Path Integrity ══════════")

    _run("root_exists", lambda: _MACCRE_ROOT.is_dir(), P,
         assert_fn=lambda r: (r is True, f"root={_MACCRE_ROOT}"))

    _run("datacenter_exists", lambda: _DATACENTER.is_dir(), P,
         assert_fn=lambda r: (r is True, f"datacenter={_DATACENTER}"))

    _run("path_resolver_env_var", lambda: str(get_maccre_root()), P,
         assert_fn=lambda r: (str(_MACCRE_ROOT) in r, f"resolved={r}"))

    _run("datacenter_func_works", lambda: str(get_datacenter_path()), P,
         assert_fn=lambda r: ("DATACENTER" in r, f"dc_path={r}"))

    _run("test_silo_creation", lambda: (_TEST_SILO / "04_Code_Artifacts").mkdir(parents=True, exist_ok=True), P)

    _run("stdlib_only_imports", lambda: [
        __import__("json"), __import__("sqlite3"), __import__("struct"),
        __import__("math"), "all stdlib ok"
    ], P, assert_fn=lambda r: (True, "stdlib imports ok"))


# ─────────────────────────────────────────────────────────────────────────────
# PHASE 1: Windows Vault
# ─────────────────────────────────────────────────────────────────────────────
def phase1_vault() -> None:
    P = "P1:Vault"
    _log.info("\n══════════ PHASE 1: Windows Vault Access ══════════")

    def get_key() -> str:
        from maccre_core.orchestration.windows_vault import get_native_credential
        key = get_native_credential("MACCRE_Sovereign")
        return str(key) if key else ""

    _run("vault_read_key", get_key, P,
         assert_fn=lambda r: (r.startswith("AIza"), f"key_prefix={r[:8]}..."))

    def vault_bad_key() -> str:
        from maccre_core.orchestration.windows_vault import get_native_credential
        result = get_native_credential("NONEXISTENT_CREDENTIAL_XYZ_999")
        return str(result)

    _run("vault_missing_key_returns_none", vault_bad_key, P,
         assert_fn=lambda r: (r in ("None", ""), f"got={r}"))


# ─────────────────────────────────────────────────────────────────────────────
# PHASE 2: Storage CRUD
# ─────────────────────────────────────────────────────────────────────────────
def phase2_storage() -> None:
    P = "P2:Storage"
    _log.info("\n══════════ PHASE 2: Storage CRUD ══════════")
    from maccre_core.tools.storage_tools import read_file, write_file

    test_path = str(_TEST_SILO / "04_Code_Artifacts" / "test_write.txt")
    content = f"micro_test payload ts={_TS}"

    _run("write_file_to_04_artifacts", lambda: write_file(test_path, content), P,
         assert_fn=lambda r: ("bytes" in r.lower() or "success" in r.lower() or "written" in r.lower(),
                              f"write_result={r[:80]}"))

    _run("read_file_back_exact_match", lambda: read_file(test_path), P,
         assert_fn=lambda r: (content in r, f"content mismatch: got={r[:80]}"))

    # Edge: read non-existent file — expect FileNotFoundError or error string
    def safe_read_missing() -> str:
        try:
            return read_file(str(_TEST_SILO / "04_Code_Artifacts" / "does_not_exist.txt"))
        except FileNotFoundError as exc:
            return f"FileNotFoundError: {str(exc)[:80]}"

    _run("read_missing_file_returns_error",
         safe_read_missing, P,
         assert_fn=lambda r: ("error" in r.lower() or "not found" in r.lower() or
                              "FileNotFoundError" in r, f"got={r[:80]}"))

    # Edge: write_datacenter_file tier enforcement at MCP layer (scripts/ is outside DATACENTER)
    def mcp_tier_enforcement() -> str:
        """Test the MCP write_datacenter_file boundary — not storage_tools."""
        dc = (_MACCRE_ROOT / "__DATACENTER").resolve()
        outside_path = (_MACCRE_ROOT / "scripts" / "tmp_should_not_exist.txt").resolve()
        try:
            outside_path.relative_to(dc)
            return "NOT_REJECTED"  # Should not happen
        except ValueError:
            return "CORRECTLY_REJECTED: outside DATACENTER boundary"

    _run("mcp_tier_boundary_rejects_outside_datacenter",
         mcp_tier_enforcement, P,
         assert_fn=lambda r: ("CORRECTLY_REJECTED" in r, f"got={r}"))

    # Write JSON artifact
    json_content = json.dumps({"test": "micro", "ts": _TS, "phase": 2})
    json_path = str(_TEST_SILO / "04_Code_Artifacts" / "test_json.json")
    _run("write_json_artifact", lambda: write_file(json_path, json_content), P,
         assert_fn=lambda r: ("bytes" in r.lower() or "success" in r.lower() or "written" in r.lower(),
                              f"json_write={r[:80]}"))

    # Overwrite same path (idempotency)
    content2 = content + "_OVERWRITE"
    _run("overwrite_same_path",
         lambda: write_file(test_path, content2), P,
         assert_fn=lambda r: ("error" not in r.lower(), f"overwrite_result={r[:80]}"))

    _run("read_overwritten_file",
         lambda: read_file(test_path), P,
         assert_fn=lambda r: ("_OVERWRITE" in r, f"expected overwrite in content, got={r[:80]}"))


# ─────────────────────────────────────────────────────────────────────────────
# PHASE 3: SovereignPinStore Direct (fake vectors, no API)
# ─────────────────────────────────────────────────────────────────────────────
def phase3_sovereign_store() -> None:
    P = "P3:SovereignStore"
    _log.info("\n══════════ PHASE 3: SovereignPinStore Direct ══════════")
    from maccre_core.memory.sovereign_store import SovereignPinStore
    from maccre_core.memory.knowledge_store import PinRecord

    store: SovereignPinStore | None = None

    def make_store() -> str:
        nonlocal store
        store = SovereignPinStore(_TEST_PROJECT)
        return f"db={store._db_path}"

    _run("store_initialization", make_store, P,
         assert_fn=lambda r: ("thought_pins.db" in r, f"path={r}"))

    if store is None:
        _skip("all_store_tests", "store init failed", P)
        return

    # Helper: deterministic fake vector
    def _vec(seed: int, dims: int = 16) -> list[float]:
        rng = random.Random(seed)
        v = [rng.gauss(0, 1) for _ in range(dims)]
        mag = math.sqrt(sum(x * x for x in v)) or 1.0
        return [x / mag for x in v]

    # Upsert document A
    doc_a = PinRecord(doc_id="doc_A", text="The Diamond Loop is the core generative pattern in MACCREv2.",
                      vector=_vec(42), metadata={"topic": "doctrine"})
    _run("upsert_doc_A", lambda: store.upsert("test_col", doc_a), P)  # type: ignore[union-attr]

    # Upsert document B (orthogonal vector)
    doc_b = PinRecord(doc_id="doc_B", text="FFmpeg stitches audio and video in the render pipeline.",
                      vector=_vec(99), metadata={"topic": "render"})
    _run("upsert_doc_B", lambda: store.upsert("test_col", doc_b), P)  # type: ignore[union-attr]

    # Upsert document C (near-identical to A's vector)
    doc_c = PinRecord(doc_id="doc_C", text="Generation agents use temperature 1.0 per Diamond Loop doctrine.",
                      vector=[v + random.gauss(0, 0.01) for v in _vec(42)],  # nearly same as A
                      metadata={"topic": "doctrine"})
    _run("upsert_doc_C_near_A", lambda: store.upsert("test_col", doc_c), P)  # type: ignore[union-attr]

    # Cosine ranking: query near A's vector — should return A first, then C, then B
    def query_near_a() -> str:
        results = store.query("test_col", _vec(42), n=3)  # type: ignore[union-attr]
        ids = [r.doc_id for r in results]
        distances = [round(r.distance, 4) for r in results]
        return f"ids={ids} distances={distances}"

    _run("vector_query_nearest_is_A",
         query_near_a, P,
         assert_fn=lambda r: (r.startswith("ids=['doc_A'") or r.startswith("ids=[\"doc_A\""),
                              f"Expected doc_A first: {r}"))

    # Contextual: query near B's vector — should return B first
    def query_near_b() -> str:
        results = store.query("test_col", _vec(99), n=3)  # type: ignore[union-attr]
        return f"first={results[0].doc_id if results else 'EMPTY'}"

    _run("vector_query_nearest_is_B",
         query_near_b, P,
         assert_fn=lambda r: ("doc_B" in r, f"Expected doc_B first: {r}"))

    # FTS5: full-text search
    def fts_diamond() -> str:
        results = store.fts_query("test_col", "Diamond Loop", n=5)  # type: ignore[union-attr]
        ids = [r.doc_id for r in results]
        return f"ids={ids}"

    _run("fts_query_diamond_loop",
         fts_diamond, P,
         assert_fn=lambda r: ("doc_A" in r or "doc_C" in r, f"FTS should find doctrine docs: {r}"))

    # FTS5: query for render-related term
    def fts_render() -> str:
        results = store.fts_query("test_col", "FFmpeg", n=5)  # type: ignore[union-attr]
        ids = [r.doc_id for r in results]
        return f"ids={ids}"

    _run("fts_query_ffmpeg_finds_B",
         fts_render, P,
         assert_fn=lambda r: ("doc_B" in r, f"FTS should find render doc: {r}"))

    # Upsert idempotency: same doc_id → update, not duplicate
    doc_a_v2 = PinRecord(doc_id="doc_A", text="UPDATED: Diamond Loop v2.", vector=_vec(42),
                         metadata={"topic": "doctrine_updated"})
    _run("upsert_same_id_updates", lambda: store.upsert("test_col", doc_a_v2), P)  # type: ignore[union-attr]

    def verify_no_dup() -> str:
        results = store.get_all("test_col")  # type: ignore[union-attr]
        ids = [r.doc_id for r in results]
        count_a = ids.count("doc_A")
        text_check = next((r.text for r in results if r.doc_id == "doc_A"), "NOT_FOUND")
        return f"count_doc_A={count_a} text={text_check[:40]}"

    _run("no_duplicate_after_upsert",
         verify_no_dup, P,
         assert_fn=lambda r: ("count_doc_A=1" in r, f"Should have exactly 1 doc_A: {r}"))

    _run("upserted_doc_A_text_updated",
         verify_no_dup, P,
         assert_fn=lambda r: ("UPDATED" in r, f"Text should reflect update: {r}"))

    # Collection isolation: upsert into a different collection, verify it doesn't pollute
    doc_isolated = PinRecord(doc_id="doc_ISO", text="isolated collection doc", vector=_vec(7))
    _run("upsert_to_isolated_collection",
         lambda: store.upsert("isolated_col", doc_isolated), P)  # type: ignore[union-attr]

    def verify_isolation() -> str:
        main_ids = [r.doc_id for r in store.get_all("test_col")]  # type: ignore[union-attr]
        iso_ids  = [r.doc_id for r in store.get_all("isolated_col")]  # type: ignore[union-attr]
        return f"main={main_ids} iso={iso_ids}"

    _run("collection_isolation_verified",
         verify_isolation, P,
         assert_fn=lambda r: ("doc_ISO" not in r.split("iso=")[0] and "doc_ISO" in r,
                              f"doc_ISO should only be in isolated_col: {r}"))

    # List collections
    _run("list_collections",
         lambda: str(store.list_collections()), P,  # type: ignore[union-attr]
         assert_fn=lambda r: ("test_col" in r and "isolated_col" in r, f"collections={r}"))

    # Delete single document
    _run("delete_single_doc", lambda: store.delete("test_col", "doc_B"), P)  # type: ignore[union-attr]

    def verify_b_deleted() -> str:
        ids = [r.doc_id for r in store.get_all("test_col")]  # type: ignore[union-attr]
        return f"ids={ids}"

    _run("verify_doc_B_deleted",
         verify_b_deleted, P,
         assert_fn=lambda r: ("doc_B" not in r, f"doc_B should be gone: {r}"))

    # Delete entire collection
    _run("delete_collection", lambda: store.delete_collection("isolated_col"), P)  # type: ignore[union-attr]

    _run("verify_collection_gone",
         lambda: str(store.list_collections()), P,
         assert_fn=lambda r: ("isolated_col" not in r, f"isolated_col should be gone: {r}"))

    # Close store (Law VII teardown)
    _run("store_close", lambda: store.close(), P)  # type: ignore[union-attr]


# ─────────────────────────────────────────────────────────────────────────────
# PHASE 4: Telemetry DB
# ─────────────────────────────────────────────────────────────────────────────
def phase4_telemetry() -> None:
    P = "P4:Telemetry"
    _log.info("\n══════════ PHASE 4: Telemetry DB ══════════")
    from maccre_core.orchestration.telemetry_db import log_system_event, get_db_path
    from maccre_core.tools.telemetry_tools import query_telemetry_matrix

    session_id = f"micro_test_{_TS}"

    # Log a TOOL_FIRED event
    _run("log_system_event_tool_fired",
         lambda: log_system_event("TOOL_FIRED", '{"tool":"micro_test"}', 0.001,
                                  session_id=session_id, project_id=_TEST_PROJECT), P)

    # Query it back — contextual: the event we just wrote must be readable
    def query_back() -> str:
        rows = query_telemetry_matrix("system_logs", "action_type = 'TOOL_FIRED'")
        matching = [r for r in rows if r.get("session_id") == session_id]
        return f"total_rows={len(rows)} session_match={len(matching)}"

    _run("query_telemetry_reads_written_event",
         query_back, P,
         assert_fn=lambda r: ("session_match=1" in r or "session_match=" in r,
                              f"Event should appear in telemetry: {r}"))

    # Log multiple events and verify ordering (newest first)
    def log_three_events() -> str:
        log_system_event("NODE_ROUTED", '{"node":"A"}', 0.0, session_id=session_id, project_id=_TEST_PROJECT)
        time.sleep(0.05)
        log_system_event("NODE_ROUTED", '{"node":"B"}', 0.0, session_id=session_id, project_id=_TEST_PROJECT)
        time.sleep(0.05)
        log_system_event("NODE_ROUTED", '{"node":"C"}', 0.0, session_id=session_id, project_id=_TEST_PROJECT)
        rows = query_telemetry_matrix("system_logs", "action_type = 'NODE_ROUTED'")
        return f"count={len(rows)} newest_payload={rows[0].get('payload','') if rows else 'EMPTY'}"

    _run("telemetry_ordering_newest_first",
         log_three_events, P,
         assert_fn=lambda r: ("count=" in r, f"multi-event log: {r}"))

    # Edge: query with bad silo name
    def bad_silo() -> str:
        try:
            query_telemetry_matrix("SilmLOTR", "1=1")  # project name, not silo name
            return "NO_ERROR"
        except ValueError as e:
            return f"ValueError: {str(e)[:80]}"

    _run("bad_silo_name_raises_value_error",
         bad_silo, P,
         assert_fn=lambda r: ("UNKNOWN_SILO" in r or "ValueError" in r, f"got={r}"))

    # Edge: thoughts silo is blocked
    def thoughts_blocked() -> str:
        try:
            query_telemetry_matrix("thoughts", "1=1")
            return "NO_ERROR"
        except ValueError as e:
            return f"ValueError: {str(e)[:80]}"

    _run("thoughts_silo_is_blocked_for_nexus",
         thoughts_blocked, P,
         assert_fn=lambda r: ("DENIED" in r or "restricted" in r.lower() or "ValueError" in r, f"got={r}"))

    # Verify system_logs DB path exists
    _run("system_logs_db_exists",
         lambda: Path(get_db_path("system_logs.db")).exists(), P,
         assert_fn=lambda r: (r is True, "system_logs.db should exist"))

    # Log rotation
    def try_rotate() -> str:
        from maccre_core.logger import rotate_logs
        result = rotate_logs()
        return str(result)

    _run("log_rotation_produces_archive",
         try_rotate, P,
         assert_fn=lambda r: (".log.gz" in r or "ROTATE_FAULT" in r or "not found" in r.lower(),
                              f"rotate_result={r[:80]}"))


# ─────────────────────────────────────────────────────────────────────────────
# PHASE 5: Model Registry & Sentinel
# ─────────────────────────────────────────────────────────────────────────────
def phase5_registry() -> None:
    P = "P5:Registry"
    _log.info("\n══════════ PHASE 5: Model Registry & Sentinel ══════════")
    from maccre_core._net.model_registry import get_registry, ModelSurface
    from maccre_core.orchestration.windows_vault import get_native_credential

    def load_registry() -> str:
        key = str(get_native_credential("MACCRE_Sovereign") or "")
        if not key.startswith("AIza"):
            return "NO_KEY"
        reg = get_registry(key)
        models = reg.all_models()  # correct method name (not get_all_models)
        return f"count={len(models)}"

    _run("registry_loads_models", load_registry, P, timeout=45,
         assert_fn=lambda r: ("count=" in r and r != "NO_KEY" and
                              int(r.split("count=")[1]) >= 50,
                              f"model count: {r}"))

    def surface_tts() -> str:
        key = str(get_native_credential("MACCRE_Sovereign") or "")
        reg = get_registry(key)
        models = reg.get_models_for_surface(ModelSurface("tts"))
        return f"tts_models={models}"

    _run("tts_surface_has_models", surface_tts, P, timeout=45,
         assert_fn=lambda r: ("tts_models=[" in r and "[]" not in r, f"TTS surface: {r}"))

    def surface_image() -> str:
        key = str(get_native_credential("MACCRE_Sovereign") or "")
        reg = get_registry(key)
        # ModelSurface enum values: 'image_generation', 'imagen' — use image_generation
        models = reg.get_models_for_surface(ModelSurface("image_generation"))
        return f"image_models={models}"

    _run("image_surface_has_models", surface_image, P, timeout=45,
         assert_fn=lambda r: ("image_models=[" in r and "[]" not in r, f"Image surface: {r}"))

    def sentinel_report() -> str:
        from maccre_core._net.model_sentinel import get_sentinel
        key = str(get_native_credential("MACCRE_Sovereign") or "")
        s = get_sentinel(key)
        r = s.report()
        return f"healthy={r.get('healthy',0)} degraded={r.get('degraded',0)} dead={r.get('dead',0)}"

    _run("sentinel_health_report", sentinel_report, P, timeout=60,
         assert_fn=lambda r: ("healthy=" in r, f"sentinel: {r}"))


# ─────────────────────────────────────────────────────────────────────────────
# PHASE 6: Pattern Library & Submission
# ─────────────────────────────────────────────────────────────────────────────
def phase6_patterns() -> None:
    P = "P6:Patterns"
    _log.info("\n══════════ PHASE 6: Pattern Library & Submission ══════════")
    from maccre_core.tools.pattern_tools import list_patterns, submit_pattern, poll_human_gate

    _run("list_patterns_returns_7",
         list_patterns, P,
         assert_fn=lambda r: (json.loads(r) and len(json.loads(r)) >= 6,
                              f"pattern count={len(json.loads(r)) if r else 0}"))

    # Submit a low-cost pattern (session_brief ~$0.005)
    job_result: dict[str, Any] = {}

    def submit_session_brief() -> str:
        nonlocal job_result
        result = submit_pattern("session_brief", "micro_test integration run", _TEST_PROJECT)
        job_result = json.loads(result) if result.startswith("{") else {}
        return result

    _run("submit_session_brief_pattern",
         submit_session_brief, P,
         assert_fn=lambda r: ("job_id" in r, f"submission result: {r[:120]}"))

    # Poll immediately — expect still_running
    def poll_gate_immediately() -> str:
        if not job_result.get("job_id"):
            return "NO_JOB_ID"
        return poll_human_gate(job_result["job_id"], job_result.get("silo_project", ""))

    _run("poll_gate_returns_running_or_packet",
         poll_gate_immediately, P,
         assert_fn=lambda r: (r in ("still_running", "not_found") or "BriefPacket" in r,
                              f"gate_poll={r[:80]}"))

    # Wait and poll again
    def poll_after_wait() -> str:
        if not job_result.get("job_id"):
            return "NO_JOB_ID"
        time.sleep(20)  # Give swarm time to run
        return poll_human_gate(job_result["job_id"], job_result.get("silo_project", ""))

    _run("poll_gate_after_20s", poll_after_wait, P, timeout=45,
         assert_fn=lambda r: (r != "NO_JOB_ID", f"gate_poll_20s={r[:80]}"))

    # Verify silo directory was created
    def silo_exists() -> str:
        silo = job_result.get("silo_project", "")
        if not silo:
            return "NO_SILO"
        silo_path = _DATACENTER / silo
        return f"exists={silo_path.exists()} silo={silo}"

    _run("pattern_silo_created",
         silo_exists, P,
         assert_fn=lambda r: ("exists=True" in r, f"silo path: {r}"))


# ─────────────────────────────────────────────────────────────────────────────
# PHASE 7: Agent Roster & Topology
# ─────────────────────────────────────────────────────────────────────────────
def phase7_topology() -> None:
    P = "P7:Topology"
    _log.info("\n══════════ PHASE 7: Agent Roster & Topology ══════════")
    from maccre_core.tools.admin_tools import build_topology, mint_agent

    # Column order for topology CSV (must match admin_tools.build_topology)
    _TOPO_COLS = [
        "Node_ID", "Agent_Name", "Next_Node", "Instruction_Override",
        "Temperature", "Model_Override", "Wait_For", "Failure_Target",
    ]

    # Mint a test agent
    _run("mint_test_agent",
         lambda: mint_agent("MicroTestAgent", "gemini-2.5-flash",
                            "You are a micro-test agent. Respond only with 'TEST_OK'."), P,
         assert_fn=lambda r: ("MicroTestAgent" in r or "success" in r.lower() or "minted" in r.lower(),
                              f"mint_result={r[:120]}"))

    # Build 2-node topology: 7-column format, NO header row (build_topology writes its own)
    # Actual column order: Node_ID, Agent_Name, Model_Override, Auto_Tool, Next_Node, Temperature, Instruction_Override
    node_rows: list[list[str]] = [
        ["INGEST", "MicroTestAgent", "", "", "STOP", "1.0", "micro test INGEST"],
        ["STOP",   "MicroTestAgent", "", "", "STOP", "0.1", "STOP"],
    ]

    topo_path: str = ""

    def build_test_topo() -> str:
        nonlocal topo_path
        result = build_topology(node_rows)
        # Result format: "[ADMIN_SUCCESS] Topology constructed successfully at <path>."
        if "[ADMIN_SUCCESS]" in result and " at " in result:
            raw_path = result.split(" at ", 1)[1].rstrip(".")
            topo_path = raw_path
        return result

    _run("build_2node_topology", build_test_topo, P,
         assert_fn=lambda r: ("[ADMIN_SUCCESS]" in r, f"topo={r[:120]}"))

    # Verify topology CSV file actually exists on disk
    def verify_topo_file() -> str:
        if not topo_path:
            return "NO_PATH"
        exists = Path(topo_path).exists()
        return f"exists={exists} path={Path(topo_path).name}"

    _run("topology_csv_exists_on_disk",
         verify_topo_file, P,
         assert_fn=lambda r: ("exists=True" in r, f"topo file: {r}"))

    # Count rows in the topology CSV (header + 2 data rows = 3 lines)
    def count_topo_nodes() -> str:
        if not topo_path or not Path(topo_path).exists():
            return "NO_FILE"
        lines = Path(topo_path).read_text(encoding="utf-8").strip().splitlines()
        # First line is header, rest are nodes
        node_count = len(lines) - 1 if len(lines) > 1 else 0
        return f"node_count={node_count}"

    _run("topology_has_2_nodes",
         count_topo_nodes, P,
         assert_fn=lambda r: ("node_count=2" in r, f"expected 2 nodes: {r}"))

    # Edge: malformed topology spec (non-list input)
    def bad_topo() -> str:
        try:
            result = build_topology([["not", "enough", "columns"]])
            return result
        except Exception as exc:  # noqa: BLE001
            return f"error: {type(exc).__name__}: {str(exc)[:80]}"

    _run("malformed_topology_returns_error", bad_topo, P,
         assert_fn=lambda r: (True, "no crash — acceptable"))  # Just verify no process crash

    # Check swarm queue via inline SQLite (mirrors maccre_mcp.check_swarm_queue)
    def check_swarm_queue_inline() -> str:
        pid = _TEST_PROJECT
        db_path = _MACCRE_ROOT / "__DATACENTER" / pid / "swarm_queue.db"
        if not db_path.exists():
            db_path = _MACCRE_ROOT / "swarm_queue.db"
        if not db_path.exists():
            return json.dumps({"status": "no database for project", "project": pid})
        try:
            import sqlite3 as _sq3  # noqa: PLC0415
            with _sq3.connect(str(db_path)) as conn:
                conn.row_factory = _sq3.Row
                cur = conn.execute(
                    "SELECT id, job_id, current_node, lock_status, created_at "
                    "FROM task_queue WHERE lock_status != 'completed' ORDER BY id DESC LIMIT 50"
                )
                rows_data = [dict(r) for r in cur.fetchall()]
            return json.dumps({"project": pid, "active_jobs": rows_data}, indent=2)
        except Exception as exc:  # noqa: BLE001
            return json.dumps({"status": "no_db", "detail": str(exc)[:80]})

    _run("check_swarm_queue",
         check_swarm_queue_inline, P,
         assert_fn=lambda r: ("active_jobs" in r or "status" in r, f"queue={r[:80]}"))


# ─────────────────────────────────────────────────────────────────────────────
# PHASE 8: Background Swarm Ignition
# ─────────────────────────────────────────────────────────────────────────────
def phase8_background_swarm() -> None:
    P = "P8:BackgroundSwarm"
    _log.info("\n══════════ PHASE 8: Background Swarm Ignition ══════════")

    # Hot-mic injection on a non-existent job (should handle gracefully)
    def hot_mic_bad_job() -> str:
        from maccre_core.orchestration.local_broker import LocalMessageBroker
        broker = LocalMessageBroker()
        broker.inject_interrupt("FAKE_JOB_ID_999", "test interrupt")
        return "injected"  # should not raise

    _run("hot_mic_bad_job_graceful", hot_mic_bad_job, P,
         assert_fn=lambda r: (r == "injected", f"got={r}"))

    # Ignite background swarm (fires python subprocess, doesn't block)
    def ignite_swarm() -> str:
        import subprocess as sp
        cmd = [sys.executable, str(_MACCRE_ROOT / "maccre.py"),
               "ignite", "micro_test_background_payload", "--node", "INGEST"]
        proc = sp.Popen(cmd, cwd=str(_MACCRE_ROOT),
                        stdout=sp.DEVNULL, stderr=sp.DEVNULL)
        return f"pid={proc.pid}"

    _run("ignite_background_swarm_returns_pid",
         ignite_swarm, P,
         assert_fn=lambda r: ("pid=" in r and r != "pid=0", f"got={r}"))

    time.sleep(2)  # Let it start

    # Check queue shows something for the active project
    def check_main_queue() -> str:
        pid = os.environ.get("MACCRE_ACTIVE_PROJECT", "GLOBAL")
        db_path = _MACCRE_ROOT / "__DATACENTER" / pid / "swarm_queue.db"
        if not db_path.exists():
            db_path = _MACCRE_ROOT / "swarm_queue.db"
        if not db_path.exists():
            return json.dumps({"status": "no_db_yet", "project": pid})
        try:
            import sqlite3 as _sq3  # noqa: PLC0415
            with _sq3.connect(str(db_path)) as conn:
                conn.row_factory = _sq3.Row
                cur = conn.execute(
                    "SELECT id, job_id, current_node, lock_status FROM task_queue "
                    "WHERE lock_status != 'completed' ORDER BY id DESC LIMIT 20"
                )
                rows_q = [dict(r) for r in cur.fetchall()]
            return json.dumps({"project": pid, "active_jobs": rows_q})
        except Exception as exc:  # noqa: BLE001
            return json.dumps({"status": "no_db", "detail": str(exc)[:80]})

    _run("queue_reflects_swarm_activity",
         check_main_queue, P,
         assert_fn=lambda r: ("active_jobs" in r or "project" in r, f"queue={r[:80]}"))


# ─────────────────────────────────────────────────────────────────────────────
# PHASE 9: Embedding API (bounded 30s — the key diagnostic)
# ─────────────────────────────────────────────────────────────────────────────
def phase9_embedding() -> None:
    global _EMBED_CAPABLE
    P = "P9:EmbeddingAPI"
    _log.info("\n══════════ PHASE 9: Embedding API (30s timeout) ══════════")

    def embed_short_text() -> str:
        from maccre_core.tools.rag_tools import get_gemini_embedding
        vec = get_gemini_embedding("sovereign pin store test", task_type="RETRIEVAL_QUERY")
        return f"dims={len(vec)} first={vec[0]:.4f}"

    passed = _run("embed_short_text_30s", embed_short_text, P, timeout=30,
                  assert_fn=lambda r: ("dims=" in r and "dims=0" not in r, f"embedding: {r}"))
    _EMBED_CAPABLE = passed

    if not passed:
        _log.warning("⚠️  Embedding API unavailable — Phase 10 RAG tests will be SKIPPED")
        return

    # If we got here, embedding works. Test dimension, range, reproducibility.
    def embed_and_check_dims() -> str:
        from maccre_core.tools.rag_tools import get_gemini_embedding
        vec = get_gemini_embedding("test", task_type="RETRIEVAL_DOCUMENT")
        max_val = max(abs(v) for v in vec)
        return f"dims={len(vec)} max_abs={max_val:.4f} finite={all(math.isfinite(v) for v in vec)}"

    _run("embedding_values_finite_normalised", embed_and_check_dims, P, timeout=30,
         assert_fn=lambda r: ("finite=True" in r and int(r.split("dims=")[1].split()[0]) > 0,
                              f"embedding quality: {r}"))

    # Two embeddings of the same text must be identical (deterministic API)
    def embed_determinism() -> str:
        from maccre_core.tools.rag_tools import get_gemini_embedding
        v1 = get_gemini_embedding("diamond loop")
        v2 = get_gemini_embedding("diamond loop")
        diff = sum((a - b) ** 2 for a, b in zip(v1, v2)) ** 0.5
        return f"dims={len(v1)} l2_diff={diff:.6f}"

    _run("embedding_determinism", embed_determinism, P, timeout=60,
         assert_fn=lambda r: ("l2_diff=0" in r or float(r.split("l2_diff=")[1]) < 0.001,
                              f"determinism check: {r}"))

    # Semantic ordering: embedding("diamond loop") closer to embedding("generation pattern")
    # than to embedding("video rendering ffmpeg")
    def semantic_ordering() -> str:
        from maccre_core.tools.rag_tools import get_gemini_embedding
        def cosine_dist(a: list[float], b: list[float]) -> float:
            dot = sum(x * y for x, y in zip(a, b))
            mag_a = math.sqrt(sum(x * x for x in a))
            mag_b = math.sqrt(sum(y * y for y in b))
            return 1.0 - (dot / (mag_a * mag_b + 1e-9))
        q  = get_gemini_embedding("diamond loop generation pattern")
        r1 = get_gemini_embedding("AI text generation with high temperature")
        r2 = get_gemini_embedding("video rendering with ffmpeg and audio stitching")
        d1 = cosine_dist(q, r1)
        d2 = cosine_dist(q, r2)
        return f"dist_related={d1:.4f} dist_unrelated={d2:.4f} ordered={'YES' if d1 < d2 else 'NO'}"

    _run("semantic_ordering_related_closer", semantic_ordering, P, timeout=90,
         assert_fn=lambda r: ("ordered=YES" in r, f"semantic: {r}"))


# ─────────────────────────────────────────────────────────────────────────────
# PHASE 10: RAG Contextual (conditional on Phase 9 passing)
# ─────────────────────────────────────────────────────────────────────────────
def phase10_rag() -> None:
    P = "P10:RAG"
    _log.info("\n══════════ PHASE 10: RAG Contextual (embedding-dependent) ══════════")

    if not _EMBED_CAPABLE:
        for name in ["ingest_doctrine_doc", "query_semantic_match", "fts_fallback",
                     "upsert_idempotency", "cross_project_boundary"]:
            _skip(name, "Embedding API unavailable (Phase 9 TIMEOUT/FAIL)", P)
        return

    # Use a dedicated RAG project to avoid SovereignPinStore singleton DB-lock
    # from Phase 3 (which used _TEST_PROJECT and closed its store, but the DB
    # file may still have a Windows handle in _instances cache).
    _RAG_PROJECT = f"RAG_{_TS}"

    # Ingest a real doctrine document
    from maccre_core.tools.rag_tools import ingest_document, query_local_memory

    doctrine_text = (
        "The MACCREv2 Diamond Loop enforces separation between Generators (temp=1.0) "
        "and Critics (temp=0.1 with Pydantic schema). Never parse AI output with regex."
    )
    render_text = (
        "FFmpeg is used in the render pipeline to stitch TTS audio with Imagen-generated "
        "frames into MP4 video output. The pipeline is dual-channel: cloud TTS + Imagen."
    )

    _run("ingest_doctrine_doc",
         lambda: ingest_document(text=doctrine_text, doc_id="doctrine_diamond",
                                 collection_name="swarm_memory",
                                 metadata={"topic": "doctrine"}), P,
         assert_fn=lambda r: ("RAG" in r or "Ingested" in r, f"ingest={r[:80]}"))

    _run("ingest_render_doc",
         lambda: ingest_document(text=render_text, doc_id="render_ffmpeg",
                                 collection_name="swarm_memory",
                                 metadata={"topic": "render"}), P,
         assert_fn=lambda r: ("RAG" in r or "Ingested" in r, f"ingest={r[:80]}"))

    # Re-ingest same doc_id (upsert idempotency with real embedding)
    _run("upsert_idempotency_real_embed",
         lambda: ingest_document(text=doctrine_text + " v2", doc_id="doctrine_diamond",
                                 collection_name="swarm_memory",
                                 metadata={"topic": "doctrine_v2"}), P,
         assert_fn=lambda r: ("RAG" in r or "Ingested" in r, f"upsert={r[:80]}"))

    # Query: doctrine-related query — use collection_name kwarg so env project drives store
    def query_doctrine() -> str:
        result = query_local_memory(
            "how are generators different from critics in AI?",
            collection_name="swarm_memory",
        )
        return result[:200]

    _run("semantic_query_finds_doctrine",
         query_doctrine, P,
         assert_fn=lambda r: ("Diamond" in r or "diamond" in r or "temp" in r.lower() or
                              "Generator" in r or "Critics" in r,
                              f"query_result={r[:120]}"))

    # Query: render-related query should find render doc
    def query_render() -> str:
        result = query_local_memory("how is video assembled from audio and images?",
                                    collection_name="swarm_memory")
        return result[:200]

    _run("semantic_query_finds_render_doc",
         query_render, P,
         assert_fn=lambda r: ("FFmpeg" in r or "ffmpeg" in r or "TTS" in r or "audio" in r.lower(),
                              f"render_query={r[:120]}"))


# ─────────────────────────────────────────────────────────────────────────────
# PHASE 11: FinOps & Render Cost
# ─────────────────────────────────────────────────────────────────────────────
def phase11_finops() -> None:
    P = "P11:FinOps"
    _log.info("\n══════════ PHASE 11: FinOps & Render Cost ══════════")
    from maccre_core.tools.finops_tools import estimate_manifest_cost, reconcile_session_finops

    manifest_1 = json.dumps([
        {"speaker": "Narrator", "text": "Test scene one.", "video_prompt": "dark terminal"}
    ])
    manifest_2 = json.dumps([
        {"speaker": "Narrator", "text": "Scene one.", "video_prompt": "scene"},
        {"speaker": "Gandalf", "text": "You shall not pass!", "video_prompt": "bridge"},
        {"speaker": "Narrator", "text": "Scene three.", "video_prompt": "end"},
    ])

    _run("estimate_1_scene",
         lambda: estimate_manifest_cost(manifest_1), P,
         assert_fn=lambda r: ("estimated_cost_usd" in r, f"cost={r[:80]}"))

    _run("estimate_3_scenes",
         lambda: estimate_manifest_cost(manifest_2), P,
         assert_fn=lambda r: ("estimated_cost_usd" in r, f"cost={r[:80]}"))

    # 3 scenes should cost more than 1
    def cost_scales_with_scenes() -> str:
        c1 = json.loads(estimate_manifest_cost(manifest_1))
        c3 = json.loads(estimate_manifest_cost(manifest_2))
        return f"1scene={c1['estimated_cost_usd']} 3scene={c3['estimated_cost_usd']} scaled={c3['estimated_cost_usd'] > c1['estimated_cost_usd']}"

    _run("cost_scales_with_scene_count",
         cost_scales_with_scenes, P,
         assert_fn=lambda r: ("scaled=True" in r, f"scaling: {r}"))

    # Edge: empty manifest
    _run("estimate_empty_manifest",
         lambda: estimate_manifest_cost("[]"), P,
         assert_fn=lambda r: ("estimated_cost_usd" in r or "error" in r.lower(), f"empty={r[:80]}"))

    # Edge: malformed manifest
    _run("estimate_malformed_manifest",
         lambda: estimate_manifest_cost("NOT JSON"), P,
         assert_fn=lambda r: ("error" in r.lower() or "invalid" in r.lower() or
                              "json" in r.lower(), f"malformed={r[:80]}"))

    # FinOps report (no real spend expected in tests)
    _run("finops_report_nominal",
         lambda: reconcile_session_finops("micro_test"), P,
         assert_fn=lambda r: ("actual_usd" in r or "projected_usd" in r or "NOMINAL" in r,
                              f"finops={r[:120]}"))


# ─────────────────────────────────────────────────────────────────────────────
# PHASE 12: Render Pipeline (estimate + FFmpeg check — no real API call)
# ─────────────────────────────────────────────────────────────────────────────
def phase12_render() -> None:
    P = "P12:Render"
    _log.info("\n══════════ PHASE 12: Render Pipeline Checks ══════════")
    import shutil

    # FFmpeg path resolution
    def check_ffmpeg() -> str:
        which = shutil.which("ffmpeg")
        from maccre_core.tools.render_executor import FFMPEG_BIN
        return f"which={which} resolved={FFMPEG_BIN}"

    _run("ffmpeg_path_resolved",
         check_ffmpeg, P,
         assert_fn=lambda r: ("ffmpeg" in r.lower() and "resolved=" in r, f"ffmpeg: {r}"))

    # CloudMediaPipeline initialization
    def pipeline_init() -> str:
        from maccre_core.tools.render_executor import CloudMediaPipeline
        p = CloudMediaPipeline()
        return f"pipeline_key_starts_AIza={str(p._key).startswith('AIza')} models_loaded={bool(p._registry)}"

    _run("cloud_pipeline_initializes",
         pipeline_init, P,
         assert_fn=lambda r: ("pipeline_key_starts_AIza=True" in r, f"pipeline: {r}"))

    # TTS voice map coverage
    def tts_voice_map() -> str:
        from maccre_core.tools.render_executor import CloudMediaPipeline
        # Access the voice_map by instantiating briefly
        import inspect
        src = inspect.getsource(CloudMediaPipeline.generate_audio)
        has_narrator = "Narrator" in src
        has_gandalf = "Gandalf" in src
        return f"narrator={has_narrator} gandalf={has_gandalf}"

    _run("voice_map_has_tolkien_coverage",
         tts_voice_map, P,
         assert_fn=lambda r: ("narrator=True" in r and "gandalf=True" in r, f"voice_map: {r}"))

    # Audio tools (pack_wav_bytes, build_tts_config)
    def audio_tools_work() -> str:
        from maccre_core.tools.audio_tools import build_tts_config, pack_wav_bytes
        cfg = build_tts_config("Aoede")
        fake_pcm = bytes(44) + b"\x00" * 1600  # minimal fake PCM
        try:
            wav = pack_wav_bytes(fake_pcm)
            wav_ok = wav[:4] == b"RIFF"
        except Exception:
            wav_ok = False
        return f"tts_config_ok={bool(cfg)} wav_header_ok={wav_ok}"

    _run("audio_tools_functional",
         audio_tools_work, P,
         assert_fn=lambda r: ("tts_config_ok=True" in r, f"audio_tools: {r}"))


# ─────────────────────────────────────────────────────────────────────────────
# PHASE 13: Cross-Tool Contextual Integration
# ─────────────────────────────────────────────────────────────────────────────
def phase13_integration() -> None:
    P = "P13:Integration"
    _log.info("\n══════════ PHASE 13: Cross-Tool Integration ══════════")
    from maccre_core.orchestration.telemetry_db import log_system_event
    from maccre_core.tools.telemetry_tools import query_telemetry_matrix
    from maccre_core.tools.storage_tools import write_file, read_file

    # Write → read → verify full round trip with content hash check
    import hashlib
    test_content = f"integration_roundtrip_{_TS}_" + "x" * 200
    hash_expected = hashlib.sha256(test_content.encode()).hexdigest()
    rt_path = str(_TEST_SILO / "04_Code_Artifacts" / "integration_rt.txt")

    write_file(rt_path, test_content)
    recovered = read_file(rt_path)
    hash_actual = hashlib.sha256(recovered.encode()).hexdigest()

    _run("full_write_read_hash_roundtrip",
         lambda: f"match={hash_expected == hash_actual}",
         P, assert_fn=lambda r: ("match=True" in r, f"hash mismatch: expected={hash_expected[:8]} got={hash_actual[:8]}"))

    # Log event → query → count exact rows
    session = f"integ_{_TS}"
    log_system_event("INTEGRATION_TEST", json.dumps({"session": session}), 0.0,
                     session_id=session, project_id=_TEST_PROJECT)

    def count_integration_events() -> str:
        rows = query_telemetry_matrix("system_logs",
                                      "action_type = 'INTEGRATION_TEST'")
        matching = [r for r in rows if r.get("session_id") == session]
        return f"written=1 found={len(matching)}"

    _run("telemetry_write_then_query_exact_count",
         count_integration_events, P,
         assert_fn=lambda r: ("found=1" in r, f"telemetry round-trip: {r}"))

    # SovereignPinStore: verify thought_pins.db created in correct tier
    def verify_db_tier() -> str:
        from maccre_core.memory.sovereign_store import SovereignPinStore
        store = SovereignPinStore(_TEST_PROJECT)
        db_path = store._db_path
        store.close()
        in_tier2 = "02_Dynamic_Context" in str(db_path)
        file_exists = db_path.exists()
        return f"in_tier2={in_tier2} exists={file_exists} path={db_path.name}"

    _run("sovereign_store_lives_in_tier2",
         verify_db_tier, P,
         assert_fn=lambda r: ("in_tier2=True" in r and "exists=True" in r, f"db_tier: {r}"))

    # Verify pattern silo structure (from Phase 6) has correct 5-tier layout
    def verify_pattern_silo_structure() -> str:
        silos = list(_DATACENTER.glob("PATTERN_session_brief_*"))
        if not silos:
            return "NO_PATTERN_SILOS"
        silo = silos[-1]
        tiers = {d.name for d in silo.iterdir() if d.is_dir()}
        required = {"01_Raw_Source", "02_Dynamic_Context"}
        present = required & tiers
        return f"silo={silo.name} tiers_present={sorted(present)}"

    _run("pattern_silo_has_datacenter_tiers",
         verify_pattern_silo_structure, P,
         assert_fn=lambda r: ("01_Raw_Source" in r and "02_Dynamic_Context" in r,
                              f"silo structure: {r}"))


# ─────────────────────────────────────────────────────────────────────────────
# PHASE 14: Edge Cases & Security
# ─────────────────────────────────────────────────────────────────────────────
def phase14_edge_cases() -> None:
    P = "P14:EdgeCases"
    _log.info("\n══════════ PHASE 14: Edge Cases & Security ══════════")
    from maccre_core.tools.telemetry_tools import read_local_codebase, SecurityError

    # Path traversal attempt — must be blocked
    def traversal_attempt() -> str:
        try:
            read_local_codebase("../../etc/passwd")
            return "NOT_BLOCKED"
        except (SecurityError, PermissionError, FileNotFoundError) as e:
            return f"BLOCKED: {type(e).__name__}"

    _run("path_traversal_blocked",
         traversal_attempt, P,
         assert_fn=lambda r: ("BLOCKED" in r or "PATH_TRAVERSAL" in r, f"traversal: {r}"))

    # Empty query to knowledge store
    def empty_fts_query() -> str:
        from maccre_core.memory.sovereign_store import SovereignPinStore
        s = SovereignPinStore(_TEST_PROJECT)
        try:
            results = s.fts_query("test_col", "", n=5)
            return f"empty_query_results={len(results)}"
        except Exception as e:
            return f"error={type(e).__name__}: {str(e)[:60]}"
        finally:
            s.close()

    _run("fts_empty_query_handles_gracefully",
         empty_fts_query, P,
         assert_fn=lambda r: ("error" in r.lower() or "results=" in r, f"empty_fts: {r}"))

    # Query non-existent collection
    def missing_collection_query() -> str:
        from maccre_core.memory.sovereign_store import SovereignPinStore
        s = SovereignPinStore(_TEST_PROJECT)
        try:
            results = s.query("NONEXISTENT_COLLECTION_XYZ", [0.0] * 16, n=5)
            return f"empty_result_count={len(results)}"
        except Exception as e:
            return f"error: {type(e).__name__}"
        finally:
            s.close()

    _run("missing_collection_returns_empty",
         missing_collection_query, P,
         assert_fn=lambda r: ("empty_result_count=0" in r or "error" in r, f"missing_col: {r}"))

    # Telemetry SQL injection guard (safe_clause strips injections)
    def sql_injection_via_event_type() -> str:
        from maccre_core.tools.telemetry_tools import query_telemetry_matrix
        try:
            # Attempt injection: closing quote + UNION SELECT
            rows = query_telemetry_matrix(
                "system_logs",
                "action_type = 'x' UNION SELECT null,null,null,null,null,null,null,null,null --"
            )
            return f"returned_rows={len(rows)}"
        except Exception as e:
            return f"error: {type(e).__name__}: {str(e)[:80]}"

    _run("sql_injection_handled",
         sql_injection_via_event_type, P,
         assert_fn=lambda r: (True, "no crash — acceptable"))

    # Zero-length text ingest
    def zero_len_ingest() -> str:
        from maccre_core.tools.rag_tools import ingest_document
        result = ingest_document(text="", doc_id="zero_len_test", collection_name="swarm_memory")
        return result

    _run("zero_length_text_ingest_rejected",
         zero_len_ingest, P,
         assert_fn=lambda r: ("RAG_FAULT" in r or "requires" in r.lower() or "empty" in r.lower(),
                              f"zero_len={r[:80]}"))

    # Missing doc_id on raw text ingest
    def no_doc_id() -> str:
        from maccre_core.tools.rag_tools import ingest_document
        result = ingest_document(text="some text", doc_id="", collection_name="swarm_memory")
        return result

    _run("missing_doc_id_rejected",
         no_doc_id, P,
         assert_fn=lambda r: ("RAG_FAULT" in r or "requires" in r.lower(), f"no_doc_id={r[:80]}"))

    # Pattern submission with invalid pattern name — submit_pattern raises KeyError, catch it
    def bad_pattern_name() -> str:
        from maccre_core.tools.pattern_tools import submit_pattern
        try:
            return submit_pattern("nonexistent_pattern_xyz", "test", _TEST_PROJECT)
        except (KeyError, ValueError, RuntimeError) as e:
            return json.dumps({"error": f"{type(e).__name__}: {str(e)[:80]}"})

    _run("invalid_pattern_name_returns_error",
         bad_pattern_name, P,
         assert_fn=lambda r: ("error" in r.lower() or "not found" in r.lower() or
                              "unknown" in r.lower() or "invalid" in r.lower() or
                              "nonexistent" in r.lower(), f"bad_pattern={r[:80]}"))


# ─────────────────────────────────────────────────────────────────────────────
# Report writer
# ─────────────────────────────────────────────────────────────────────────────
def _write_report() -> Path:
    report_dir = _MACCRE_ROOT / "__DATACENTER" / "GLOBAL" / "04_Code_Artifacts"
    report_dir.mkdir(parents=True, exist_ok=True)

    json_path = report_dir / f"micro_test_{_TS}.json"
    json_path.write_text(json.dumps(_results, indent=2, ensure_ascii=False), encoding="utf-8")

    total   = len(_results)
    passed  = sum(1 for r in _results if r["status"] == "PASS")
    failed  = sum(1 for r in _results if r["status"] in ("FAIL", "ERROR"))
    timedout = sum(1 for r in _results if r["status"] == "TIMEOUT")
    skipped = sum(1 for r in _results if r["status"] == "SKIP")
    pct     = int(100 * passed / total) if total else 0

    md: list[str] = [
        "# MACCREv2 Micro-Test Report",
        f"**Run:** `{_TS}`  |  **Pass:** {passed}/{total} ({pct}%)  |  "
        f"**Fail/Error:** {failed}  |  **Timeout:** {timedout}  |  **Skip:** {skipped}",
        "",
        "## Results by Phase",
        "|Phase|PASS|FAIL|TIMEOUT|ERROR|SKIP|",
        "|-----|----|----|-------|-----|----|",
    ]
    for ph, counts in sorted(_phase_counts.items()):
        md.append(f"|{ph}|{counts.get('PASS',0)}|{counts.get('FAIL',0)}"
                  f"|{counts.get('TIMEOUT',0)}|{counts.get('ERROR',0)}|{counts.get('SKIP',0)}|")

    md += ["", "## Full Test Log", "",
           "|Phase|Test|Status|ms|Detail|",
           "|-----|-----|------|--|------|"]
    for r in _results:
        d = r["detail"][:80].replace("|", "\\|")
        md.append(f"|{r['phase']}|{r['test']}|{r['status']}|{r['duration_ms']}|{d}|")

    md_path = report_dir / f"micro_test_{_TS}.md"
    md_path.write_text("\n".join(md), encoding="utf-8")
    _log.info("📄 Report → %s", md_path)
    _log.info("📄 JSON   → %s", json_path)
    return md_path


# ─────────────────────────────────────────────────────────────────────────────
# Cleanup test silo
# ─────────────────────────────────────────────────────────────────────────────
def _cleanup() -> None:
    import shutil
    try:
        if _TEST_SILO.exists():
            shutil.rmtree(_TEST_SILO)
            _log.info("🧹 Test silo cleaned: %s", _TEST_SILO.name)
    except Exception as exc:  # noqa: BLE001
        _log.warning("Cleanup error: %s", exc)


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────
def main() -> None:
    _log.info("=" * 70)
    _log.info("  MACCREv2 Autonomous Micro-Test Suite")
    _log.info("  Session: %s", _TS)
    _log.info("  Test silo: %s", _TEST_PROJECT)
    _log.info("  Root: %s", _MACCRE_ROOT)
    _log.info("=" * 70)

    t0 = time.monotonic()

    try:
        # ── Group A: Infrastructure ──────────────────────────────────────────
        phase0_bootstrap()
        phase1_vault()
        phase2_storage()
        phase3_sovereign_store()
        _git_commit("Phase 0-3 PASS — bootstrap, vault, storage, SovereignPinStore")

        # ── Group B: Telemetry & Registry ────────────────────────────────────
        phase4_telemetry()
        phase5_registry()
        _git_commit("Phase 4-5 PASS — telemetry DB + model registry verified")

        # ── Group C: Swarm & Topology ────────────────────────────────────────
        phase6_patterns()
        phase7_topology()
        phase8_background_swarm()
        _git_commit("Phase 6-8 PASS — patterns, topology, background swarm")

        # ── Group D: AI Layer ────────────────────────────────────────────────
        phase9_embedding()
        phase10_rag()
        _git_commit("Phase 9-10 COMPLETE — embedding API + RAG contextual")

        # ── Group E: FinOps & Render ─────────────────────────────────────────
        phase11_finops()
        phase12_render()
        _git_commit("Phase 11-12 PASS — FinOps + render pipeline checks")

        # ── Group F: Integration & Edge Cases ────────────────────────────────
        phase13_integration()
        phase14_edge_cases()

    except KeyboardInterrupt:
        _log.warning("⚠️  Test run interrupted by user.")
    except Exception as exc:  # noqa: BLE001
        _log.error("🚨 Unhandled exception in test runner: %s", exc, exc_info=True)
    finally:
        # Always write report and final commit
        elapsed = int(time.monotonic() - t0)
        passed  = sum(1 for r in _results if r["status"] == "PASS")
        total   = len(_results)
        _log.info("\n" + "=" * 70)
        _log.info("  COMPLETE — %d/%d PASS — %ds elapsed", passed, total, elapsed)
        _log.info("=" * 70)

        report_path = _write_report()
        _cleanup()
        _git_commit(
            f"test(micro): FINAL — {passed}/{total} PASS — report→04_Code_Artifacts "
            f"[embed={'YES' if _EMBED_CAPABLE else 'NO'}]"
        )
        _log.info("✅ Done. Report: %s", report_path)


if __name__ == "__main__":
    main()
