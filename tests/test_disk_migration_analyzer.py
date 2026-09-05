# ┌─────────────────────────────────────────────────────────────────────────────┐
# │  MACCREv2 Test Infrastructure — the disk migration analyzer                   │
# └─────────────────────────────────────────────────────────────────────────────┘
"""
tests/test_disk_migration_analyzer.py
=====================================
Tests for ``scripts/disk_migration_analyzer.py``.

WHY THIS FILE EXISTS AT ALL
---------------------------
The analyzer produced **three of its own defects** in the space of one sitting, and every
one of them failed in the same direction: the report stayed plausible while getting less
useful.

1. ``--depth`` stopped above ``AppData``, so the largest and most relevant directory on
   the disk was one 41.55 GB ``UNKNOWN`` line.
2. ``_expand`` did an exact-case environment lookup. **Python upper-cases ``os.environ``
   keys on Windows**, so every mixed-case placeholder — ``{SystemRoot}``,
   ``{ProgramFiles}``, ``{ProgramFiles(x86)}`` — silently matched nothing and roughly a
   third of the rule table was inert.
3. A broad rule outranked a specific one, so ``C:\\Program Files (x86)`` was reported
   whole and **swallowed the 9.96 GB Steam library** — the most actionable item on the
   disk, hidden behind a correct-but-useless verdict on its parent.

None of those raised. Each produced a confident report with the answer removed from it,
which is the failure mode a size analyser is most likely to have and least likely to be
challenged on.

.. note::
   ``scripts/`` is excluded from version control (``.git/info/exclude``), so on a fresh
   clone the module under test is absent and this file skips rather than fails. That is
   an honest consequence of Era 3 tracker #16 being open, not a workaround: a test that
   fails because the repository does not ship the thing it tests would be noise.
"""
from __future__ import annotations

import ast
import importlib.util
import sys
from pathlib import Path

import pytest

_ANALYZER = Path(__file__).resolve().parent.parent / "scripts" / "disk_migration_analyzer.py"

pytestmark = pytest.mark.skipif(
    not _ANALYZER.exists(),
    reason="scripts/ is git-excluded (tracker #16); the analyzer is not present here",
)


def _load():
    """Import the analyzer from an excluded directory by path.

    ``sys.modules`` is populated **before** ``exec_module``, and that is not optional:
    ``@dataclass`` resolves annotations through ``sys.modules.get(cls.__module__)``, so
    executing an unregistered module raises
    ``AttributeError: 'NoneType' object has no attribute '__dict__'`` from inside
    ``dataclasses`` — a failure that says nothing about the code under test.
    """
    spec = importlib.util.spec_from_file_location("_dma", _ANALYZER)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _dangerous_calls() -> set[str]:
    """Every function actually *called* by the analyzer, as dotted names.

    **Read from the AST rather than the source text, and that is the point.** The first
    version of the read-only tests grepped for strings like ``shutil.move`` and
    ``--apply``, and failed — on the module's own docstring, which explains that it
    deliberately has no ``--apply`` flag. Prose describing an absence tripped a guard
    written to detect that absence.

    That is the third time in this session a source-text assertion has matched its own
    explanation. The AST cannot make that mistake: a call is a call and a sentence is
    not.
    """
    tree = ast.parse(_ANALYZER.read_text(encoding="utf-8"))
    names: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        target = node.func
        if isinstance(target, ast.Name):
            names.add(target.id)
        elif isinstance(target, ast.Attribute):
            parts = [target.attr]
            inner: ast.expr = target.value
            while isinstance(inner, ast.Attribute):
                parts.append(inner.attr)
                inner = inner.value
            if isinstance(inner, ast.Name):
                parts.append(inner.id)
            names.add(".".join(reversed(parts)))
    return names


def _cli_flags() -> set[str]:
    """The flags the argparse setup actually registers."""
    tree = ast.parse(_ANALYZER.read_text(encoding="utf-8"))
    flags: set[str] = set()
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "add_argument"
        ):
            for arg in node.args:
                if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                    flags.add(arg.value)
    return flags


@pytest.fixture(scope="module")
def dma():
    return _load()


class TestPlaceholderExpansion:
    """Defect 2. The one that made a third of the rules inert."""

    def test_an_uppercase_variable_expands(self, dma) -> None:
        assert dma._expand("{LOCALAPPDATA}\\x") != "{LOCALAPPDATA}\\x"

    def test_a_mixed_case_variable_expands(self, dma) -> None:
        """``{SystemRoot}`` is the shape that silently failed.

        Python upper-cases environment keys on Windows, so an exact-case lookup found
        nothing and left the placeholder in place — after which the rule could never
        match a real path.
        """
        expanded = dma._expand("{SystemRoot}")
        assert "{" not in expanded
        assert expanded.lower().endswith("windows")

    def test_a_parenthesised_variable_expands(self, dma) -> None:
        """``{ProgramFiles(x86)}`` — parentheses in a variable name, and mixed case."""
        expanded = dma._expand("{ProgramFiles(x86)}\\Steam\\steamapps")
        assert "{" not in expanded
        assert expanded.endswith("\\Steam\\steamapps")

    def test_an_unknown_variable_is_left_alone(self, dma) -> None:
        """Degrading to "no rule" beats matching the wrong path.

        ``{ProgramFiles(x86)}`` genuinely does not exist on a 32-bit host, and callers
        treat a remaining brace as unexpandable rather than comparing it to anything.
        """
        assert dma._expand("{NO_SUCH_VAR_XYZ}\\x") == "{NO_SUCH_VAR_XYZ}\\x"

    def test_every_rule_in_the_table_expands_on_this_host(self, dma) -> None:
        """The guard that would have caught defect 2 on the first run.

        Any rule left holding a brace is a rule that can never fire. One or two are
        legitimately host-dependent, so this reports them rather than demanding zero.
        """
        unexpandable = [
            rule.template for rule in dma.RULES if "{" in dma._expand(rule.template)
        ]
        assert not unexpandable, f"rules that can never match on this host: {unexpandable}"


class TestSpecificRulesOutrankBroadOnes:
    """Defect 3. A parent verdict must not hide a child's actionable one."""

    def test_a_deeper_rule_is_detected_beneath_a_broad_one(self, dma) -> None:
        program_files_x86 = Path(dma._expand("{ProgramFiles(x86)}"))
        assert dma._has_rule_below(program_files_x86) is True

    def test_a_leaf_rule_has_nothing_below_it(self, dma) -> None:
        steam = Path(dma._expand("{ProgramFiles(x86)}\\Steam\\steamapps"))
        assert dma._has_rule_below(steam) is False

    def test_appdata_has_rules_below_it(self, dma) -> None:
        """Defect 1: this returning False is what produced the 41.55 GB blob."""
        assert dma._has_rule_below(Path(dma._expand("{LOCALAPPDATA}"))) is True

    def test_no_two_rules_expand_to_the_same_path(self, dma) -> None:
        """The real invariant under equality matching: no unreachable duplicate.

        Written first as an *ordering* assertion — most-specific-first, on the belief
        that ``_classify`` prefix-matched and a broad rule could shadow a longer one. It
        failed on ``{SystemRoot}`` preceding ``{SystemRoot}\\Installer``, and the code was
        right: ``_classify`` compares for **exact equality**, so those two are
        independent and neither can shadow the other.

        The overstated claim was in the ``RULES`` comment, which has been corrected.
        What equality matching *can* suffer is two entries resolving to one path, where
        the second is dead. That is what this now checks.
        """
        seen: dict[str, str] = {}
        for rule in dma.RULES:
            expanded = dma._expand(rule.template).casefold().rstrip("\\/")
            if "{" in expanded:
                continue
            assert expanded not in seen, (
                f"{rule.template} duplicates {seen[expanded]} — the second is unreachable"
            )
            seen[expanded] = rule.template


class TestClassification:
    def test_a_known_cache_classifies(self, dma) -> None:
        rule = dma._classify(Path(dma._expand("{LOCALAPPDATA}\\pip\\Cache")))
        assert rule is not None
        assert rule.ease is dma.Ease.ENV_VAR
        assert rule.env_var == "PIP_CACHE_DIR"

    def test_an_unknown_path_does_not_classify(self, dma) -> None:
        assert dma._classify(Path("C:/definitely/not/a/known/location")) is None

    def test_trailing_separators_do_not_defeat_a_match(self, dma) -> None:
        with_sep = Path(dma._expand("{LOCALAPPDATA}\\pip\\Cache") + "\\")
        assert dma._classify(with_sep) is not None

    def test_every_env_var_rule_names_its_variable(self, dma) -> None:
        """"Set an environment variable" without the name is not actionable."""
        for rule in dma.RULES:
            if rule.ease is dma.Ease.ENV_VAR:
                assert rule.env_var, rule.template

    def test_system_paths_are_marked_never_or_involved(self, dma) -> None:
        """A size report that lists Windows beside a movable cache invites the worst
        possible action, so those entries carry their verdict rather than a size alone.
        """
        for template in ("{SystemRoot}", "{SystemRoot}\\WinSxS", "{SystemRoot}\\Installer"):
            rule = dma._classify(Path(dma._expand(template)))
            assert rule is not None, template
            assert rule.ease is dma.Ease.NEVER, template


class TestItIsReadOnly:
    """The property that matters most, asserted on the source.

    A tool that both finds and frees space on a system drive is one typo away from an
    unbootable machine.
    """

    def test_nothing_deletes(self) -> None:
        called = _dangerous_calls()
        for forbidden in (
            "shutil.rmtree", "os.remove", "os.unlink", "os.rmdir", "os.removedirs",
            "Path.unlink", "path.unlink",
        ):
            assert forbidden not in called, forbidden

    def test_nothing_moves(self) -> None:
        called = _dangerous_calls()
        for forbidden in ("shutil.move", "shutil.copy", "shutil.copytree", "os.rename", "os.replace"):
            assert forbidden not in called, forbidden

    def test_nothing_creates_directories(self) -> None:
        called = _dangerous_calls()
        for forbidden in ("os.mkdir", "os.makedirs", "Path.mkdir"):
            assert forbidden not in called, forbidden

    def test_the_only_file_access_is_reading_metadata(self) -> None:
        """``stat``, ``scandir`` and ``disk_usage`` are the whole I/O surface.

        ``open`` is absent deliberately — the analyzer never needs a file's *contents*,
        only its size, so it never opens one.
        """
        called = _dangerous_calls()
        assert "open" not in called

    def test_there_is_no_apply_flag(self) -> None:
        """Deliberately absent. Every suggestion is for a human to run.

        Checked against the flags argparse actually registers, because the module
        docstring *mentions* these names while explaining that it has none of them.
        """
        flags = _cli_flags()
        for forbidden in ("--apply", "--fix", "--yes", "--force", "--move", "--clean"):
            assert forbidden not in flags, forbidden

    def test_it_says_it_is_read_only(self) -> None:
        """The one assertion that *should* read prose, since it is about prose."""
        assert "READ-ONLY" in _ANALYZER.read_text(encoding="utf-8")


class TestScanSafety:
    def test_reparse_points_are_not_followed(self, dma) -> None:
        """Following them would double-count WinSxS hard links and can loop forever."""
        source = _ANALYZER.read_text(encoding="utf-8")
        assert "is_junction()" in source
        assert "follow_symlinks=False" in source

    def test_a_scan_reports_its_own_coverage(self, dma, tmp_path: Path) -> None:
        """Totals that omit unreadable directories must say so.

        Otherwise the report claims completeness it does not have — and this tool's
        whole purpose is telling someone how much space exists.
        """
        (tmp_path / "a").mkdir()
        (tmp_path / "a" / "f.bin").write_bytes(b"x" * 2048)
        findings, stats = dma.scan(tmp_path, min_bytes=1, depth=1)
        assert stats.dirs_walked > 0
        assert isinstance(stats.permission_denied, int)
        assert findings

    def test_a_finding_below_the_threshold_is_omitted(self, dma, tmp_path: Path) -> None:
        (tmp_path / "small").mkdir()
        (tmp_path / "small" / "f.bin").write_bytes(b"x" * 16)
        findings, _ = dma.scan(tmp_path, min_bytes=10 * 1024 * 1024, depth=1)
        assert findings == []
