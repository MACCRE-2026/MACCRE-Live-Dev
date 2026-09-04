# ┌─────────────────────────────────────────────────────────────────────────────┐
# │  MACCREv2 Test Infrastructure — Paranoia Mode contract                      │
# └─────────────────────────────────────────────────────────────────────────────┘
"""
tests/test_paranoia_mode.py
===========================
Locks down the hardware-token topology gate: that it is *honestly* disabled, that
its documentation cannot drift from its state, and that it no longer makes the
topology loader Windows-only.

WHY THIS FILE EXISTS
--------------------
Until 2026-09-03, ``maccre_core/utils/secret_auth.py`` carried a module docstring
reading *"Air-Gap Steganographic Hardware Authentication … Uses NTFS Alternate Data
Streams and Hardware tokens"* — present tense — while ``is_topology_approved()`` was
already ``return True``. Three places asserted a security control that did not
exist. A reader concluded topologies were hardware-gated. They were not.

That is Doctrine 5, and the same shape as the doctrine's own ``--smart`` incident,
but worse in kind because it is an authorization control rather than a CLI flag.

It carried a second cost. ``secret_auth`` imported ``ctypes.wintypes`` at **module
scope**, which cannot import on a non-Windows host, and
``topology_engine._pull_from_csv`` imported it **unguarded** — so the topology
loader, on every execution path in the system, was Windows-only in service of a gate
that always returned ``True``. That is a hard Android blocker of the same class as
the DPAPI credential vault, and it had no register entry at all.

TESTING APPROACH, AND WHY SOME ASSERTIONS READ SOURCE
-----------------------------------------------------
Two of the invariants here are *import-time platform* properties that cannot be
reproduced on this host, because the suite runs on Windows where the bad import
succeeds. Those are asserted against the module's AST instead. That is a deliberate
trade: an AST assertion is weaker evidence than an execution assertion, but it is
mechanical, it fails when the claim goes false, and the alternative is no check at
all on a defect that only manifests on the platform the project is aiming for.
"""
from __future__ import annotations

import ast
import sys
from pathlib import Path

import pytest

from maccre_core.utils import secret_auth

REPO_ROOT = Path(__file__).resolve().parent.parent
SECRET_AUTH_SRC = Path(secret_auth.__file__)
TOPOLOGY_ENGINE_SRC = REPO_ROOT / "maccre_core" / "orchestration" / "topology_engine.py"
PATTERN_EXECUTOR_SRC = REPO_ROOT / "maccre_core" / "patterns" / "pattern_executor.py"

#: Modules that exist only on Windows. A top-level import of any of these makes the
#: importing module unusable on the platform the Android goal targets.
WINDOWS_ONLY_MODULES = {"ctypes.wintypes", "winreg", "msvcrt", "_winapi"}


def _module_level_imports(path: Path) -> set[str]:
    """Every module imported at *module scope*, ignoring function-local imports.

    Function-local imports are the fix pattern here, so the distinction is the whole
    point: ``from ctypes import wintypes`` inside a function is fine, at module scope
    it is a portability break.
    """
    tree = ast.parse(path.read_text(encoding="utf-8"))
    found: set[str] = set()
    for node in tree.body:  # module scope only — no ast.walk
        if isinstance(node, ast.Import):
            found.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            found.add(node.module)
            found.update(f"{node.module}.{alias.name}" for alias in node.names)
    return found


class TestParanoiaModeIsHonestlyDisabled:
    """A disabled control must announce that it is disabled."""

    def test_the_flag_is_the_single_seam(self) -> None:
        assert isinstance(secret_auth.PARANOIA_MODE_ENABLED, bool)
        assert secret_auth.is_paranoia_mode_enabled() is secret_auth.PARANOIA_MODE_ENABLED

    def test_approval_is_unconditional_while_disabled(self) -> None:
        """Records the current reality rather than an aspiration."""
        if secret_auth.PARANOIA_MODE_ENABLED:
            pytest.skip("Paranoia Mode is enabled; this asserts the disabled behaviour")
        assert secret_auth.is_topology_approved("does/not/exist.csv") is True
        assert secret_auth.is_topology_approved("") is True

    def test_callers_can_distinguish_approved_from_unchecked(self) -> None:
        """``True`` from the gate is ambiguous on its own; the seam resolves it.

        Doctrine 3's rule against folding an ambiguous state into a success applies
        to authorisation answers as much as to task outcomes. A caller must be able
        to ask "was anything actually verified?" and get a straight answer.
        """
        approved = secret_auth.is_topology_approved("anything")
        enforced = secret_auth.is_paranoia_mode_enabled()
        assert approved is True
        assert enforced is False, (
            "If enforcement is on, this test's premise changed and the docstring "
            "contract test below should have caught it first."
        )

    def test_docstring_cannot_drift_from_the_flag(self) -> None:
        """Doctrine 5: the claim and the code must fail together.

        This is the test whose absence caused the original defect. If someone flips
        ``PARANOIA_MODE_ENABLED`` to ``True`` without rewriting the docstring, or
        rewrites the docstring while the flag is ``False``, this fails.
        """
        doc = (secret_auth.__doc__ or "").upper()
        if secret_auth.PARANOIA_MODE_ENABLED:
            assert "CURRENTLY DISABLED" not in doc, (
                "Paranoia Mode is ENABLED but the module docstring still says it is "
                "disabled. The docstring is now a lie in the opposite direction."
            )
        else:
            assert "CURRENTLY DISABLED" in doc, (
                "Paranoia Mode is disabled and the module docstring does not say so. "
                "This is exactly the 2026-09-03 defect: a security control "
                "documented in the present tense that does not run."
            )

    def test_no_authorisation_is_claimed_in_the_present_tense(self) -> None:
        """The old docstring's phrasing must not come back while the gate is off."""
        if secret_auth.PARANOIA_MODE_ENABLED:
            pytest.skip("only meaningful while disabled")
        doc = secret_auth.__doc__ or ""
        first_paragraph = doc.strip().split("\n\n")[0].upper()
        assert "DISABLED" in first_paragraph, (
            "The disabled state must appear in the opening paragraph, not buried "
            "below a description of what the control would do. A reader who stops "
            "after one paragraph must not come away believing it is active."
        )


class TestParanoiaModeStillWorksWhenEnabled:
    """Kept, not deleted — so it has to actually function when switched on."""

    def test_enabling_it_refuses_an_unstamped_topology(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        topo = tmp_path / "topology.csv"
        topo.write_text("NODE_ID,ACTION\n", encoding="utf-8")
        monkeypatch.setattr(secret_auth, "PARANOIA_MODE_ENABLED", True)
        assert secret_auth.is_topology_approved(str(topo)) is False, (
            "With Paranoia Mode on and no auth stamp present, the topology must be "
            "refused. If this passes something is short-circuiting the gate."
        )

    def test_a_check_that_cannot_run_has_not_passed(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """Off Windows the ADS cannot exist, and the honest answer is False.

        Principle 2's territory: a permissive answer to an unanswerable question is
        an approximately-correct result, and downstream logic would act on it.
        """
        topo = tmp_path / "topology.csv"
        topo.write_text("NODE_ID,ACTION\n", encoding="utf-8")
        monkeypatch.setattr(secret_auth, "is_windows", lambda: False)
        assert secret_auth.has_auth_stamp(str(topo)) is False

    def test_stamping_off_windows_reports_skipped_rather_than_success(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        topo = tmp_path / "topology.csv"
        topo.write_text("NODE_ID,ACTION\n", encoding="utf-8")
        monkeypatch.setattr(secret_auth, "is_windows", lambda: False)
        result = secret_auth.stamp_topology(str(topo), "deadbeef")
        assert result.startswith("SKIPPED:"), result
        assert "SUCCESS" not in result, (
            "Doctrine 3: a no-op must not report success."
        )

    def test_missing_topology_is_a_fault_not_a_denial(self, tmp_path: Path) -> None:
        result = secret_auth.stamp_topology(str(tmp_path / "absent.csv"), "x")
        assert result.startswith("FAULT:"), result

    @pytest.mark.skipif(sys.platform != "win32", reason="ADS is an NTFS construct")
    def test_a_valid_stamp_is_recognised_on_windows(self, tmp_path: Path) -> None:
        """Round-trip the real mechanism where the platform supports it."""
        topo = tmp_path / "topology.csv"
        topo.write_text("NODE_ID,ACTION\n", encoding="utf-8")
        ads = f"{topo}:{secret_auth.AUTH_STAMP_STREAM}"
        with open(ads, "w", encoding="utf-8") as handle:
            handle.write(secret_auth.AUTH_STAMP_TOKEN)
        assert secret_auth.has_auth_stamp(str(topo)) is True

    @pytest.mark.skipif(sys.platform != "win32", reason="ADS is an NTFS construct")
    def test_a_wrong_stamp_value_is_rejected(self, tmp_path: Path) -> None:
        topo = tmp_path / "topology.csv"
        topo.write_text("NODE_ID,ACTION\n", encoding="utf-8")
        with open(f"{topo}:{secret_auth.AUTH_STAMP_STREAM}", "w", encoding="utf-8") as h:
            h.write("NOT_THE_TOKEN")
        assert secret_auth.has_auth_stamp(str(topo)) is False


class TestPortability:
    """The gate must not cost the project its target platform."""

    def test_secret_auth_has_no_windows_only_module_scope_imports(self) -> None:
        offenders = _module_level_imports(SECRET_AUTH_SRC) & WINDOWS_ONLY_MODULES
        assert not offenders, (
            f"{SECRET_AUTH_SRC.name} imports {offenders} at module scope, so it "
            f"cannot import on a non-Windows host. Move them inside the functions "
            f"that need them. This is the defect that made the topology loader "
            f"Windows-only for the sake of a gate returning True."
        )

    def test_topology_engine_no_longer_depends_on_secret_auth(self) -> None:
        """The loader is on every execution path; it must stay platform-neutral."""
        source = TOPOLOGY_ENGINE_SRC.read_text(encoding="utf-8")
        tree = ast.parse(source)
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                assert "secret_auth" not in node.module, (
                    "topology_engine imports secret_auth again. That import was "
                    "unguarded and made the topology loader Windows-only. If a gate "
                    "is genuinely wanted here, it needs a platform guard and its own "
                    "test — not a bare import."
                )

    def test_the_unreachable_permission_error_is_gone(self) -> None:
        source = TOPOLOGY_ENGINE_SRC.read_text(encoding="utf-8")
        assert "lacks Hardware Auth Stamp" not in source, (
            "The PermissionError referencing a Hardware Auth Stamp is back. While "
            "Paranoia Mode returns True unconditionally that branch is unreachable, "
            "and unreachable error handling reads as a control that exists."
        )


class TestPatternExecutorClaimsNothingItDoesNotDo:
    """It writes an audit record. It must not imply it authenticated anything."""

    def test_it_no_longer_writes_an_unread_ads_stamp(self) -> None:
        source = PATTERN_EXECUTOR_SRC.read_text(encoding="utf-8")
        code_lines = [
            ln for ln in source.splitlines()
            if not ln.lstrip().startswith("#") and "``" not in ln
        ]
        code = "\n".join(code_lines)
        assert f":{secret_auth.AUTH_STAMP_STREAM}" not in code, (
            "pattern_executor is writing the ADS auth stream again. Nothing reads "
            "it while Paranoia Mode is disabled, so the write is dead work and the "
            "accompanying log line implies an authorisation step that is not "
            "happening."
        )

    def test_the_method_name_matches_what_it_does(self) -> None:
        source = PATTERN_EXECUTOR_SRC.read_text(encoding="utf-8")
        assert "_record_topology_hash" in source
        assert "_sign_topology" not in source, (
            "A method named _sign_topology that signs nothing is the same class of "
            "claim as the docstring that started this."
        )

    def test_it_still_writes_the_content_hash_audit_record(self, tmp_path: Path) -> None:
        """The genuine artifact must survive the cleanup."""
        from maccre_core.patterns.pattern_executor import PatternExecutor

        topo = tmp_path / "topology.csv"
        topo.write_text("NODE_ID,ACTION\nA,B\n", encoding="utf-8")
        executor = PatternExecutor.__new__(PatternExecutor)
        executor._record_topology_hash(topo)  # type: ignore[attr-defined]

        stamp = topo.with_suffix(".stamp")
        assert stamp.is_file(), "the SHA-256 audit record is a real artifact and was dropped"
        assert len(stamp.read_text(encoding="utf-8").strip()) == 64
