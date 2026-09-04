# ┌─────────────────────────────────────────────────────────────────────────────┐
# │  MACCREv2 Test Infrastructure — Quality Gate Scope Contract                 │
# └─────────────────────────────────────────────────────────────────────────────┘
"""
tests/test_lint_scope_contract.py
=================================
Asserts that the quality gate actually covers what it claims to cover.

WHY THIS FILE EXISTS
--------------------
On 2026-09-03 it was discovered that `omni qa` had been reporting "Quality gates
passed" over an unlinted subtree. Ruff honours `.gitignore` **and**
`.git/info/exclude` by default, and `.git/info/exclude` is where this project keeps
its private-internals list. So a control meaning *do not publish this* was silently
also enforcing *do not check this*.

`ruff.toml` asserted the opposite. Its `per-file-ignores` named `tests/*` and
`scripts/*` — naming a per-file-ignore for a path is a statement that the path is
linted, otherwise the entry is meaningless. The tool had visited neither. 17 errors
were hiding from a whole-project run, three of them `F821 undefined-name` in
`scripts/maccre_micro_test.py`, where a partial rename left three stale
`get_native_credential` call sites inside `_run()` probes. Three checks in the
system's own micro-test harness could never execute.

This is Doctrine 5: *specifications drift from implementations unless mechanically
checked.* A config file made a claim about behaviour and nothing verified it. It is
also the sibling of an incident already in the doctrine — a type-checker config
naming three targets while an explicit CLI path overrode them. Same failure, a
different override mechanism.

These tests use `ruff check --show-files`, which reports the files Ruff will
actually run against under the current settings. They therefore test the *effective*
scope rather than re-reading `ruff.toml` and trusting it, which would only re-assert
the config to itself and reproduce the original defect in test form.
"""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent

#: Directories that MUST be inside the lint gate. Each is load-bearing:
#: ``tests`` held 11,505 unlinted lines; ``scripts`` held the three F821 defects.
MUST_BE_LINTED = ("tests", "scripts", "maccre_core")

#: Directories that MUST NOT be linted, and the reason, so a future reader can
#: argue with the decision instead of guessing at it.
MUST_NOT_BE_LINTED = {
    "_archive": "retired code",
    "_legacy": "superseded generations",
    "scratch": "single-use throwaway probes",
    "__DATACENTER": "session artifacts, not source",
    "user_scripts": "third-party ingestion utilities",
    ".venv": "the interpreter environment",
}


def _ruff_effective_files() -> list[str]:
    """Ask Ruff which files it would actually check, using omni's exact flags.

    Mirrors ``enforce_quality_gates`` in ``C:\\OmniBuilder\\omni.py``. If omni's
    flags change and these diverge, that is itself the drift this module exists to
    catch, and :func:`test_omni_passes_no_respect_gitignore` covers it directly.
    """
    proc = subprocess.run(
        [
            sys.executable, "-m", "ruff", "check",
            ".", "--force-exclude", "--no-respect-gitignore", "--show-files",
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if proc.returncode != 0 and not proc.stdout.strip():
        pytest.fail(f"`ruff --show-files` produced nothing. stderr:\n{proc.stderr}")
    return [ln.strip() for ln in proc.stdout.splitlines() if ln.strip()]


@pytest.fixture(scope="module")
def effective_files() -> list[str]:
    return _ruff_effective_files()


def _top_level_dirs(paths: list[str]) -> set[str]:
    tops: set[str] = set()
    for raw in paths:
        try:
            rel = Path(raw).resolve().relative_to(REPO_ROOT)
        except ValueError:
            continue
        if rel.parts:
            tops.add(rel.parts[0])
    return tops


class TestLintScopeIsNotInheritedFromGit:
    """The gate's scope must be a stated decision, not a side effect."""

    def test_ruff_reports_a_non_trivial_file_set(self, effective_files: list[str]) -> None:
        """A near-empty file set is the failure mode that started all this.

        If `--show-files` returns almost nothing, the gate is passing over an empty
        set, which is Doctrine 3 — success reported over unperformed work.
        """
        assert len(effective_files) > 100, (
            f"Ruff would check only {len(effective_files)} files. The gate has "
            f"collapsed to near-nothing; a pass over this set means nothing."
        )

    @pytest.mark.parametrize("directory", MUST_BE_LINTED)
    def test_required_directory_is_inside_the_gate(
        self, directory: str, effective_files: list[str]
    ) -> None:
        """`tests/` and `scripts/` are named in per-file-ignores, so they are claimed."""
        if not (REPO_ROOT / directory).is_dir():
            pytest.skip(f"{directory}/ is not present in this checkout")
        tops = _top_level_dirs(effective_files)
        assert directory in tops, (
            f"'{directory}/' is NOT in Ruff's effective file set. ruff.toml's "
            f"per-file-ignores claims it is linted. This is the exact 2026-09-03 "
            f"defect: a config asserting coverage the tool does not provide."
        )

    @pytest.mark.parametrize("directory", sorted(MUST_NOT_BE_LINTED))
    def test_excluded_directory_stays_outside_the_gate(
        self, directory: str, effective_files: list[str]
    ) -> None:
        """Exclusions must come from ruff.toml, and must actually hold."""
        if not (REPO_ROOT / directory).is_dir():
            pytest.skip(f"{directory}/ is not present in this checkout")
        tops = _top_level_dirs(effective_files)
        assert directory not in tops, (
            f"'{directory}/' entered Ruff's scope ({MUST_NOT_BE_LINTED[directory]}). "
            f"If that is intended, remove it from MUST_NOT_BE_LINTED and say why. "
            f"If not, it needs an entry in ruff.toml's `exclude`."
        )

    def test_no_pycache_or_venv_leaks_into_the_gate(
        self, effective_files: list[str]
    ) -> None:
        leaks = [f for f in effective_files if "__pycache__" in f or ".venv" in f]
        assert not leaks, f"Generated or vendored files entered the gate: {leaks[:5]}"


class TestExclusionsAreDeclaredNotInherited:
    """`ruff.toml` must name every exclusion, rather than inheriting it from git."""

    def test_no_private_python_directory_is_in_an_undeclared_state(self) -> None:
        """Every private directory holding Python must be *accounted for*.

        The invariant is not "private implies excluded" — ``scripts/`` is private
        and deliberately linted, which is correct and is where the three F821
        defects lived. The invariant is that no directory is in an **undeclared**
        state, because an undeclared directory is one whose lint status is an
        accident of which file happened to mention it.

        Two legitimate declarations:
          * named in ``ruff.toml``'s ``exclude`` — a decision not to lint it;
          * named in :data:`MUST_BE_LINTED` — a decision to lint it despite privacy.

        Anything in neither list would silently leave the gate the moment
        ``--no-respect-gitignore`` were removed, which is the 2026-09-03 defect.
        """
        exclude_file = REPO_ROOT / ".git" / "info" / "exclude"
        if not exclude_file.is_file():
            pytest.skip("no .git/info/exclude in this checkout")

        ruff_toml = (REPO_ROOT / "ruff.toml").read_text(encoding="utf-8")
        privately_excluded = [
            ln.strip().rstrip("/")
            for ln in exclude_file.read_text(encoding="utf-8").splitlines()
            if ln.strip() and not ln.strip().startswith("#") and ln.strip().endswith("/")
        ]

        undeclared: list[str] = []
        for name in privately_excluded:
            d = REPO_ROOT / name
            if not d.is_dir():
                continue
            has_python = any(p for p in d.rglob("*.py") if "__pycache__" not in p.parts)
            if not has_python:
                continue
            declared_excluded = f'"{name}"' in ruff_toml
            declared_linted = name in MUST_BE_LINTED
            if not (declared_excluded or declared_linted):
                undeclared.append(name)

        assert not undeclared, (
            f"These directories hold Python, are private via .git/info/exclude, and "
            f"are declared NEITHER excluded in ruff.toml NOR linted in "
            f"MUST_BE_LINTED: {undeclared}. Pick one and record it. An undeclared "
            f"directory is how 17 errors stayed hidden behind a passing gate."
        )

    def test_omni_passes_no_respect_gitignore(self) -> None:
        """The gate's own invocation must keep privacy and lint scope decoupled.

        Skipped rather than failed when omni is absent: omni is system-pathed at
        C:\\OmniBuilder by design and a workspace search will never find it, so its
        absence here is an environment fact rather than a defect. Never assume it is
        missing — resolve it with `Get-Command omni`.
        """
        omni_py = Path("C:/OmniBuilder/omni.py")
        if not omni_py.is_file():
            pytest.skip("omni.py not present at its system path on this machine")
        source = omni_py.read_text(encoding="utf-8", errors="replace")

        # Parse the ACTUAL argument list, not the whole file.
        #
        # The first version of this assertion was `"--no-respect-gitignore" in
        # source`, and it passed after the flag had been deleted from the
        # subprocess call — because the flag's name also appears in the
        # explanatory comment above that call. The test matched the prose and
        # could not distinguish the flag from a mention of the flag.
        #
        # That is Doctrine 2 in test form: an approximately-correct check is worse
        # than none, because a green result was reported over a gate that had
        # already lost its scope. Caught by revert-to-red on 2026-09-03; it is the
        # reason this test parses rather than greps.
        call_lists = re.findall(r"ruff_cmd\s*\+\s*\[(.*?)\]", source, re.S)
        assert call_lists, (
            "Could not find a `ruff_cmd + [...]` invocation in omni.py. Either the "
            "gate was restructured or this test's parser is stale — both need eyes."
        )
        flattened = " ".join(call_lists)
        assert "--no-respect-gitignore" in flattened, (
            "omni's ruff invocation no longer passes --no-respect-gitignore.\n"
            f"Argument lists found: {call_lists}\n"
            "Removing it re-couples 'private' to 'unchecked' and silently shrinks "
            "the gate to whatever .git/info/exclude happens to hide. That is how 17 "
            "errors, three of them F821 in a credential path, sat behind a passing "
            "whole-project gate."
        )
