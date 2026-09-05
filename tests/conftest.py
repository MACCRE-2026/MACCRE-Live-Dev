# ┌─────────────────────────────────────────────────────────────────────────────┐
# │  MACCREv2 Test Infrastructure — Shared Fixtures                             │
# └─────────────────────────────────────────────────────────────────────────────┘
"""
tests/conftest.py
=================
Phase 2A — Pytest fixtures and shared test configuration.

Also holds the **temp-root redirect** (2026-09-05). See
:data:`PREFERRED_BASETEMP` and :func:`pytest_configure` for why the suite does not
write its scratch files to the system temp directory.
"""
from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from tests.mocks.mock_broker import MockMessageBroker
from tests.mocks.mock_inference import MockInferenceClient

# ── Temp-root redirect ────────────────────────────────────────────────────────
#
#: Where `tmp_path` and friends should live.
#:
#: **The incident.** On 2026-09-05 the suite produced 26 errors on one run and then
#: 49 errors plus 5 failures on the next, in *different* test sets each time, with the
#: same 1024 items collected. Nothing in the tree had changed between them. The cause
#: was `sqlite3.OperationalError: database or disk is full` — the system drive had
#: **7.1 MB** free while the workspace drive had 173 GB.
#:
#: `TEMP` lives on the system drive, so every test that builds a scratch SQLite
#: database was writing to the full disk. That is why the failures were transient,
#: escalated run over run, and moved around: each run consumed a little more of what
#: little was left, and targeted subsets passed because they created fewer temp dirs.
#:
#: Diagnosing this cost most of an afternoon and *looked* exactly like a defect in the
#: change under test. It was not. Recording it here because the next person to see a
#: shifting set of teardown errors should check free space before reading any code.
PREFERRED_BASETEMP = Path("B:/EXO_GANS_tests")


def pytest_configure(config: pytest.Config) -> None:
    """Point pytest's temp root at :data:`PREFERRED_BASETEMP` when it is available.

    .. danger::
       **pytest DELETES an explicitly-set basetemp directory at session start.**
       Verified empirically before this was wired up, not taken from documentation: a
       sentinel file placed in a candidate directory was gone after one run.

       So this location must be **dedicated to pytest scratch and hold nothing else**,
       ever. It is deliberately a sibling of the repository rather than a directory
       inside it, so nothing under version control can be within reach of that wipe.

    **Why a conftest hook rather than ``addopts`` in ``pyproject.toml``.** An absolute
    path in committed config would make the suite unrunnable on any machine without a
    ``B:`` drive — and this repository is public, with an explicit "MACCRE off the
    laptop" era planned. The hook is conditional: where the parent drive is absent, it
    changes nothing and pytest's own default applies. That keeps a machine-specific
    convenience out of the machine-independent file.

    Skipped entirely when ``--basetemp`` is already given on the command line, so an
    operator can always override without editing anything.
    """
    if config.option.basetemp:
        return
    # The *parent* must already exist. Creating a drive root's worth of directories on
    # a machine that simply lacks the drive would trade a clear failure for a strange
    # one, and "the drive is present" is the actual precondition being tested.
    if not PREFERRED_BASETEMP.parent.exists():
        return
    try:
        PREFERRED_BASETEMP.mkdir(parents=True, exist_ok=True)
    except OSError:
        # No basetemp is better than a broken one: pytest's default still works.
        return
    config.option.basetemp = PREFERRED_BASETEMP


def pytest_report_header() -> str:
    """State where scratch is going, in the header of every run.

    The disk-full incident was invisible for hours partly because nothing said where
    the suite was writing. One line makes the next occurrence a five-second diagnosis.
    """
    usage = shutil.disk_usage(
        PREFERRED_BASETEMP.parent
        if PREFERRED_BASETEMP.parent.exists()
        else Path.cwd().anchor
    )
    free_gb = usage.free / (1024**3)
    where = (
        str(PREFERRED_BASETEMP)
        if PREFERRED_BASETEMP.parent.exists()
        else "pytest default (system temp)"
    )
    return f"scratch: {where} — {free_gb:.1f} GB free on that volume"


@pytest.fixture()
def mock_broker() -> MockMessageBroker:
    """Fresh in-memory MockMessageBroker."""
    return MockMessageBroker()


@pytest.fixture()
def mock_client() -> MockInferenceClient:
    """Fresh MockInferenceClient with default responses."""
    return MockInferenceClient()


@pytest.fixture()
def mock_client_with_responses() -> type[MockInferenceClient]:
    """Factory fixture: create MockInferenceClient with custom responses.

    Usage::

        def test_something(mock_client_with_responses):
            client = mock_client_with_responses(["response_1", "response_2"])
    """
    return MockInferenceClient


@pytest.fixture()
def tmp_datacenter(tmp_path: Path) -> Path:
    """Create a temporary datacenter with 5-tier structure."""
    dc = tmp_path / "__DATACENTER" / "TEST_PROJECT"
    for tier in [
        "01_Raw_Source",
        "02_Dynamic_Context",
        "02_Dynamic_Context/memory_pins",
        "03_Agent_Ledgers",
        "04_Code_Artifacts",
        "05_Rendered_Media",
    ]:
        (dc / tier).mkdir(parents=True, exist_ok=True)
    return dc


@pytest.fixture()
def tmp_payload(tmp_path: Path) -> Path:
    """Create a temporary payload file for testing."""
    payload = tmp_path / "test_payload.txt"
    payload.write_text("This is a test payload for the MACCREv2 swarm.", encoding="utf-8")
    return payload


@pytest.fixture(autouse=True)
def _set_test_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Auto-applied fixture: sets env vars for test isolation."""
    monkeypatch.setenv("MACCRE_ROOT", str(tmp_path))
    monkeypatch.setenv("MACCRE_ACTIVE_PROJECT", "TEST_PROJECT")
