# ┌─────────────────────────────────────────────────────────────────────────────┐
# │  MACCREv2 Test Infrastructure — where the suite writes its scratch            │
# └─────────────────────────────────────────────────────────────────────────────┘
"""
tests/test_scratch_location_contract.py
=======================================
The suite must not write its scratch files to the system drive.

THE INCIDENT (2026-09-05)
-------------------------
Two consecutive full runs produced **26 errors**, then **49 errors and 5 failures**, in
*different* test sets each time, with the same 1024 items collected and no change to the
tree between them. The cause was ``sqlite3.OperationalError: database or disk is full``:
the system drive had **7.1 MB** free while the workspace drive had 173 GB.

``TEMP`` lives on the system drive, so every test building a scratch SQLite database was
writing to a full disk. That explains the whole signature — transient, escalating run over
run, moving around between runs, and targeted subsets passing because they create fewer
temp directories.

**It looked exactly like a defect in the change under test, and it was not.** These tests
exist so the next occurrence is a five-second diagnosis instead of an afternoon.

THE HAZARD THIS FILE ALSO GUARDS
--------------------------------
**pytest deletes an explicitly-set basetemp directory at session start.** That was verified
empirically before the redirect was wired — a sentinel file placed in a candidate directory
was gone after one run — not taken from documentation. So the scratch location must be
dedicated to pytest and hold nothing else, and it must sit **outside** the repository so
nothing under version control is ever within reach of that wipe.
"""
from __future__ import annotations

import shutil
from pathlib import Path

from tests.conftest import PREFERRED_BASETEMP, pytest_configure, pytest_report_header


class _FakeOption:
    def __init__(self, basetemp: object = None) -> None:
        self.basetemp = basetemp


class _FakeConfig:
    def __init__(self, basetemp: object = None) -> None:
        self.option = _FakeOption(basetemp)


class TestScratchIsNotOnTheSystemDrive:
    def test_the_preferred_location_is_on_the_workspace_drive(self) -> None:
        assert PREFERRED_BASETEMP.drive.upper() == "B:"

    def test_tmp_path_actually_lands_there(self, tmp_path: Path) -> None:
        """The one that matters: the *live* fixture, not the configured intention.

        Asserting the config value would pass while pytest still wrote elsewhere.
        """
        if not PREFERRED_BASETEMP.parent.exists():
            return  # Machine without the drive — the redirect is a no-op by design.
        assert str(tmp_path).upper().startswith(str(PREFERRED_BASETEMP).upper())

    def test_the_volume_has_room(self, tmp_path: Path) -> None:
        """A guard against the incident recurring silently on the new volume.

        1 GB is not a capacity plan; it is enough that a full-suite run will not die
        halfway through and be misread as a code defect.
        """
        free_gb = shutil.disk_usage(tmp_path).free / (1024**3)
        assert free_gb > 1.0, f"only {free_gb:.2f} GB free where the suite writes scratch"


class TestTheScratchLocationIsSafeToWipe:
    """pytest deletes this directory wholesale at session start."""

    def test_it_is_outside_the_repository(self) -> None:
        """So the wipe can never reach anything under version control."""
        repo = Path(__file__).resolve().parent.parent
        assert repo not in PREFERRED_BASETEMP.resolve().parents
        assert PREFERRED_BASETEMP.resolve() != repo

    def test_it_is_not_a_drive_root(self) -> None:
        """Pointing a wholesale delete at ``B:\\`` would erase the workspace itself."""
        resolved = PREFERRED_BASETEMP.resolve()
        assert resolved != Path(resolved.anchor)
        assert resolved.name != ""

    def test_it_is_dedicated_by_name(self) -> None:
        """The name has to say what it is, because its contents are disposable."""
        assert "test" in PREFERRED_BASETEMP.name.lower()


class TestTheRedirectIsConditional:
    """The repository is public and an off-laptop era is planned.

    An absolute path in committed ``addopts`` would make the suite unrunnable anywhere
    without a ``B:`` drive. The hook has to degrade to pytest's default instead.
    """

    def test_an_explicit_command_line_basetemp_wins(self) -> None:
        """An operator override must never be silently replaced."""
        config = _FakeConfig(basetemp="/somewhere/else")
        pytest_configure(config)  # type: ignore[arg-type]
        assert config.option.basetemp == "/somewhere/else"

    def test_a_missing_drive_leaves_pytest_alone(self, monkeypatch) -> None:
        """No drive, no redirect — not a crash, and not a fabricated directory."""
        import tests.conftest as ct

        monkeypatch.setattr(ct, "PREFERRED_BASETEMP", Path("Q:/nonexistent/scratch"))
        config = _FakeConfig()
        ct.pytest_configure(config)  # type: ignore[arg-type]
        assert config.option.basetemp is None

    def test_the_redirect_applies_when_the_drive_is_present(self) -> None:
        if not PREFERRED_BASETEMP.parent.exists():
            return
        config = _FakeConfig()
        pytest_configure(config)  # type: ignore[arg-type]
        assert config.option.basetemp == PREFERRED_BASETEMP


class TestTheRunSaysWhereItWrites:
    """The incident was invisible for hours partly because nothing reported this."""

    def test_the_header_names_the_location(self) -> None:
        header = pytest_report_header()
        assert str(PREFERRED_BASETEMP) in header or "pytest default" in header

    def test_the_header_reports_free_space(self) -> None:
        """Free space in the header is what turns this into a glance."""
        assert "GB free" in pytest_report_header()
