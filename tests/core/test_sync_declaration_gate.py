"""Unit tests for ``scripts/check_sync_declaration.py``.

These exercise the pure decision functions only: the governed-surface matcher,
the trailer parser / validity rules, and the ``pyproject.toml`` per-key trigger
predicate. The gate's own ``--self-test`` provides the end-to-end red/green
contrast, and the CI job / release tag gate wire it into the pipeline.
"""
import importlib.util
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
GATE_PATH = REPO_ROOT / "scripts" / "check_sync_declaration.py"

assert GATE_PATH.is_file(), f"gate script missing: {GATE_PATH}"
_spec = importlib.util.spec_from_file_location("check_sync_declaration", GATE_PATH)
assert _spec is not None and _spec.loader is not None
gate = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(gate)


# ---------------------------------------------------------------------------
# Governed surface (file level)
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("path", [
    ".github/workflows/ci.yml",
    ".github/workflows/release.yaml",
    "scripts/check_tag_gate.py",
    "scripts/verify_versions_json_merge.py",
    "CONTRIBUTING.md",
    "SECURITY.md",
    "LICENSE",
    "mkdocs.yml",
    "cullinan/_version.py",
])
def test_governed_paths_are_detected(path):
    assert gate.governed_reason(path) is not None


@pytest.mark.parametrize("path", [
    "cullinan/core/model.py",
    "docs/guide.md",
    "README.MD",
    "scripts/check_sync_declaration.py",
])
def test_unrelated_paths_are_ignored(path):
    assert gate.governed_reason(path) is None


def test_pyproject_is_handled_by_the_key_predicate_not_the_file_table():
    assert gate.governed_reason("pyproject.toml") is None
    hits = gate.governed_hits(["pyproject.toml"])
    assert hits == []


def test_leading_dot_slash_is_normalized():
    assert gate.governed_reason("./.github/workflows/ci.yml") is not None


def test_governed_hits_reports_each_matched_path():
    hits = gate.governed_hits([".github/workflows/ci.yml", "cullinan/core/model.py"])
    assert [path for path, _ in hits] == [".github/workflows/ci.yml"]


# ---------------------------------------------------------------------------
# Trailer parsing
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("message,state", [
    ("feat: x\n\nMeta-Sync: required id=abc1234\n", "required"),
    ("feat: x\n\nMeta-Sync: n-a reason=cosmetic rename only\n", "n-a"),
    ("feat: x\n", "absent"),
    ("feat: x\n\nMeta-Sync: n-a reason=\n", "malformed"),
    ("feat: x\n\nMeta-Sync: n-a reason=short\n", "malformed"),
    ("feat: x\n\nMeta-Sync: required\n", "malformed"),
    ("feat: x\n\nMeta-Sync: required id=ab\n", "malformed"),
    ("feat: x\n\nMeta-Sync: maybe\n", "malformed"),
])
def test_parse_declaration_states(message, state):
    assert gate.parse_declaration(message)[0] == state


def test_parse_declaration_returns_the_token():
    assert gate.parse_declaration("x\n\nMeta-Sync: required id=abc1234\n")[1] == "abc1234"


def test_parse_declaration_accepts_reason_of_exactly_eight_chars():
    state, _ = gate.parse_declaration("x\n\nMeta-Sync: n-a reason=12345678\n")
    assert state == "n-a"


def test_parse_declaration_last_occurrence_wins():
    message = "x\n\nMeta-Sync: required id=first01\n\nMeta-Sync: n-a reason=later value here\n"
    state, detail = gate.parse_declaration(message)
    assert state == "n-a"
    assert detail == "later value here"


def test_parse_declaration_found_outside_the_final_line():
    message = "x\n\nMeta-Sync: required id=abc0004\n\nmore body\n"
    assert gate.parse_declaration(message)[0] == "required"


# ---------------------------------------------------------------------------
# Verdict
# ---------------------------------------------------------------------------
def test_governed_change_without_declaration_is_red():
    hits = gate.governed_hits([".github/workflows/ci.yml"])
    verdict, detail = gate.judge(hits, "ci: x\n")
    assert verdict == "RED"
    assert "missing" in detail
    assert ".github/workflows/ci.yml" in detail


def test_governed_change_with_valid_declaration_is_green():
    hits = gate.governed_hits(["SECURITY.md"])
    verdict, _ = gate.judge(hits, "docs: x\n\nMeta-Sync: required id=abc0001\n")
    assert verdict == "GREEN"


def test_governed_change_with_malformed_declaration_is_red():
    hits = gate.governed_hits(["LICENSE"])
    verdict, detail = gate.judge(hits, "chore: x\n\nMeta-Sync: required\n")
    assert verdict == "RED"
    assert "malformed" in detail


def test_unrelated_change_is_green_regardless_of_declaration():
    assert gate.judge([], "chore: x\n")[0] == "GREEN"
    assert gate.judge([], "chore: x\n\nMeta-Sync: required id=abc0001\n")[0] == "GREEN"


def test_legacy_unsupported_key_is_not_honoured():
    # NEGATIVE CASE -- the previous trailer key is no longer recognised, so a
    # message that only carries it counts as an undeclared change (RED).
    hits = gate.governed_hits([".github/workflows/ci.yml"])
    verdict, detail = gate.judge(hits, "ci: x\n\nKB-Sync: required id=abc0001\n")
    assert verdict == "RED"
    assert "missing" in detail


# ---------------------------------------------------------------------------
# pyproject.toml per-key trigger (four key classes + fail-safe + non-triggers)
# ---------------------------------------------------------------------------
_PKG_DATA_BEFORE = ("[project]", 'name = "demo"', "", "[tool.setuptools.package-data]",
                    'demo = ["py.typed"]')
_PKG_DATA_AFTER = ("[project]", 'name = "demo"', "", "[tool.setuptools.package-data]",
                   'demo = ["py.typed", "extra.json"]')


def test_package_data_only_change_does_not_trigger():
    assert gate.pyproject_trigger(_PKG_DATA_BEFORE, _PKG_DATA_AFTER)[0] is False


def test_project_key_change_triggers():
    before = ("[project]", 'name = "demo"', 'dynamic = ["version"]')
    after = ("[project]", 'name = "demo"', "dynamic = []")
    triggered, why = gate.pyproject_trigger(before, after)
    assert triggered is True
    assert "T2" in why


def test_build_system_change_triggers():
    before = ("[build-system]", 'requires = ["setuptools>=61"]')
    after = ("[build-system]", 'requires = ["setuptools>=61", "wheel"]')
    triggered, why = gate.pyproject_trigger(before, after)
    assert triggered is True
    assert "T1" in why


def test_dynamic_version_section_change_triggers():
    before = ("[tool.setuptools.dynamic]", 'version = { attr = "demo._version.__version__" }')
    after = ("[tool.setuptools.dynamic]", 'version = { attr = "demo.other.__version__" }')
    triggered, why = gate.pyproject_trigger(before, after)
    assert triggered is True
    assert "T3" in why


def test_unknown_non_tool_section_triggers_fail_safe():
    before = ("[project]", 'name = "demo"')
    after = ("[project]", 'name = "demo"', "", "[dependency-groups]", 'dev = ["ruff"]')
    triggered, why = gate.pyproject_trigger(before, after)
    assert triggered is True
    assert "fail-safe" in why


def test_tool_section_change_does_not_trigger():
    before = ("[tool.ruff]", "line-length = 100")
    after = ("[tool.ruff]", "line-length = 110")
    assert gate.pyproject_trigger(before, after)[0] is False


def test_packages_find_change_does_not_trigger():
    before = ("[tool.setuptools.packages.find]", 'include = ["demo*"]')
    after = ("[tool.setuptools.packages.find]", 'include = ["demo*", "extra*"]')
    assert gate.pyproject_trigger(before, after)[0] is False


def test_comment_only_change_does_not_trigger():
    before = ("# comment a", "[project]", 'name = "demo"')
    after = ("# comment b", "[project]", 'name = "demo"')
    assert gate.pyproject_trigger(before, after)[0] is False


def test_no_change_does_not_trigger():
    lines = ("[project]", 'name = "demo"')
    assert gate.pyproject_trigger(lines, lines)[0] is False


# ---------------------------------------------------------------------------
# Built-in self-test contract
# ---------------------------------------------------------------------------
def test_builtin_self_test_is_green():
    assert gate.self_test() == 0
