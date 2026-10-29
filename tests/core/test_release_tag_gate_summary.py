# -*- coding: utf-8 -*-
"""The pre-tag gate's summary must echo every check it enforces.

A check that is registered and enforced but absent from the printed summary is
indistinguishable, from the outside, from a check that does not exist at all --
which is exactly how an installed gate gets mistaken for a missing one. These
tests pin the correspondence so the two cannot drift apart again.
"""
from __future__ import annotations

import importlib.util
import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
GATE_PATH = REPO_ROOT / "scripts" / "check_tag_gate.py"

assert GATE_PATH.is_file(), f"gate script missing: {GATE_PATH}"

_spec = importlib.util.spec_from_file_location("check_tag_gate", GATE_PATH)
assert _spec is not None and _spec.loader is not None
gate = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(gate)

SOURCE = GATE_PATH.read_text(encoding="utf-8")

# ``check("(x) ...")`` registrations, e.g. ``check("(d) declaration present ...")``
_REGISTERED = re.compile(r'check\(\s*f?"\s*\(([a-z])\)')
# ``print(f"  (x) ...")`` lines in the PASS summary
_SUMMARY = re.compile(r'print\(\s*f?"\s*\(([a-z])\)')


def _registered_labels() -> set:
    return set(_REGISTERED.findall(SOURCE))


def _summary_labels() -> set:
    return set(_SUMMARY.findall(SOURCE))


def test_the_script_still_has_labelled_checks():
    # Guards the guard: if the script is reshaped, fail loudly rather than
    # silently passing an empty comparison.
    assert _registered_labels(), "no labelled check(...) calls found"


def test_every_labelled_check_is_echoed_in_the_summary():
    missing = _registered_labels() - _summary_labels()
    assert not missing, (
        f"checks enforced but missing from the PASS summary: {sorted(missing)}"
    )


def test_declaration_backstop_is_visible_in_the_summary():
    assert "d" in _registered_labels(), "(d) declaration check is not registered"
    assert "d" in _summary_labels(), "(d) declaration check is not in the summary"


def test_declaration_check_actually_gates():
    """The (d) item must feed ``fails`` (i.e. really block a tag), not just print."""
    body = SOURCE.split("# (d) declaration backstop", 1)[1]
    assert "check(" in body and "if not reds" in body, (
        "(d) must be registered through check(...) so a RED blocks the tag"
    )

def test_docs_banner_check_is_registered_and_echoed():
    """(e) is the docs channel's only reconciliation -- it must be visible."""
    assert "e" in _registered_labels(), "(e) docs banner check is not registered"
    assert "e" in _summary_labels(), "(e) docs banner check is not in the summary"


def test_docs_banner_check_actually_gates():
    """The (e) item must feed ``fails``, not merely print a line."""
    body = SOURCE.split("# (e) docs version banners", 1)[1]
    assert "check(" in body, "(e) must be registered through check(...)"
    assert "banner_findings(" in body and "banners_clean" in body, (
        "(e) must feed the scan result into check(...), not merely print it"
    )


def test_banner_scan_finds_the_offending_page(tmp_path):
    """A page that advertises the wrong version must be named, not averaged away."""
    (tmp_path / "a.md").write_text("> **Version**: 0.96a7.post1\n", encoding="utf-8")
    (tmp_path / "b.md").write_text("> **当前版本：0.96a7.post1**\n", encoding="utf-8")
    (tmp_path / "c.md").write_text("> **Version**: 0.90a5\n", encoding="utf-8")
    found = dict(gate.find_doc_banners(tmp_path))
    assert found["a.md"] == "0.96a7.post1"
    assert found["b.md"] == "0.96a7.post1"
    assert found["c.md"] == "0.90a5", "the stale page must survive into the report"


def test_banner_scan_ignores_a_minimum_version_claim(tmp_path):
    """``0.90a5+`` states a floor, not the version being read."""
    (tmp_path / "p.md").write_text("> **Version**: 0.90a5+\n", encoding="utf-8")
    assert gate.find_doc_banners(tmp_path) == []


def test_banner_scan_does_not_backtrack_into_a_truncated_version(tmp_path):
    """The ``+`` filter must not leave ``0.90a`` behind as a captured version."""
    (tmp_path / "p.md").write_text("> **版本**: 0.90a5+\n", encoding="utf-8")
    assert gate.find_doc_banners(tmp_path) == []

# --- (f) credential -> tree binding ----------------------------------------

def _head_tree() -> str:
    import subprocess
    return subprocess.run(
        ["git", "-C", str(REPO_ROOT), "rev-parse", "HEAD^{tree}"],
        capture_output=True, text=True, check=True,
    ).stdout.strip()


def _tag_tree(version: str):
    """The tree of ``v<version>``, or ``None`` when that tag does not exist."""
    import subprocess
    result = subprocess.run(
        ["git", "-C", str(REPO_ROOT), "rev-parse", "--verify", "--quiet",
         f"refs/tags/v{version}^{{commit}}^{{tree}}"],
        capture_output=True, text=True,
    )
    return result.stdout.strip() if result.returncode == 0 else None


def _reference_tree() -> str:
    """The tree the gate must compare against: the tag once it exists, else HEAD.

    Written here independently of the script so the test says what the rule is,
    rather than asking the script what it thinks the rule is.
    """
    import importlib.util as _u
    spec = _u.spec_from_file_location("_ver", REPO_ROOT / "cullinan" / "_version.py")
    module = _u.module_from_spec(spec)
    spec.loader.exec_module(module)
    return _tag_tree(module.__version__) or _head_tree()


def _clean_junit(directory=None) -> str:
    """Write a minimal passing JUnit report and return its path."""
    import tempfile
    from pathlib import Path as _Path

    target = _Path(directory or tempfile.mkdtemp()) / "junit.xml"
    target.write_text(
        '<?xml version="1.0"?><testsuites><testsuite name="pytest" '
        'tests="1300" failures="0" errors="0" skipped="2"/></testsuites>',
        encoding="utf-8",
    )
    return str(target)


def _run_gate(review: str, sync: str, sign_off: str = "P", junit: str | None = None):
    import subprocess
    import sys
    return subprocess.run(
        [sys.executable, str(GATE_PATH),
         "--sign-off-token", sign_off,
         "--review-token", review,
         "--sync-token", sync,
         "--junit", junit if junit is not None else _clean_junit()],
        cwd=str(REPO_ROOT), capture_output=True, text=True, encoding="utf-8",
    )


def test_the_tree_bound_credential_is_accepted():
    tree = _reference_tree()
    result = _run_gate(f"review-a#tree={tree}", f"sync#tree={tree}")
    assert "PASS (f)" in result.stdout, result.stdout[-400:]


def test_an_unbound_credential_is_refused_with_the_bound_form_suggested():
    result = _run_gate("review-0.96a7.post1-d69e66d", "sync-0.96a7.post1-d69e66d")
    assert "FAIL (f)" in result.stdout
    assert "reissue" in result.stdout, "the message must say how to fix the credential"
    assert _reference_tree() in result.stdout, "and must print the tree to bind to"


def test_a_credential_bound_to_another_tree_fails_for_that_reason():
    """V4: a stale credential must fail as "wrong tree", not "unrecognised"."""
    zero = "0" * 40
    result = _run_gate(f"review-a#tree={zero}", f"sync#tree={_reference_tree()}")
    assert "FAIL (f)" in result.stdout
    assert "different tree" in result.stdout
    assert "reissue" not in result.stdout, (
        "the format was understood; sending the reader off to reissue would hide that "
        "the real problem is a credential for a different tree"
    )


def test_sign_off_is_exempt_from_the_tree_binding():
    """The sign-off credential binds to its evidence bundle, not to the tree."""
    tree = _reference_tree()
    result = _run_gate(f"review-a#tree={tree}", f"sync#tree={tree}", sign_off="<bundle>#sha256=deadbeef")
    assert "PASS (f)" in result.stdout


def test_the_tag_wins_over_head_once_it_exists():
    """After tagging, HEAD moves and the tag does not.

    Reading HEAD here made the check fail for every commit after the tag, against
    credentials that were correct -- a gate that fires on nobody's mistake. When a tag
    exists it is the fixed point, so a credential bound to the tag must pass and one
    bound to HEAD must fail, saying which tree it wanted.
    """
    import importlib.util as _u
    spec = _u.spec_from_file_location("_ver2", REPO_ROOT / "cullinan" / "_version.py")
    module = _u.module_from_spec(spec)
    spec.loader.exec_module(module)
    tag_tree = _tag_tree(module.__version__)
    if tag_tree is None or tag_tree == _head_tree():
        import pytest
        pytest.skip("this checkout has no tag whose tree differs from HEAD")

    passes = _run_gate(f"review-a#tree={tag_tree}", f"sync#tree={tag_tree}")
    assert "PASS (f)" in passes.stdout, passes.stdout[-400:]
    assert "tag v" in passes.stdout, "the detail must say which tree it compared against"

    fails = _run_gate(f"review-a#tree={_head_tree()}", f"sync#tree={tag_tree}")
    assert "FAIL (f)" in fails.stdout
    assert "different tree" in fails.stdout
    assert "tag v" in fails.stdout


def test_the_scope_limit_is_stated_where_a_reader_will_see_it():
    """The gate must not let its PASS be read as an authenticity check."""
    assert "(f) credential scope" in _summary_labels() or "f" in _summary_labels()
    assert "authenticity" in SOURCE, (
        "the docstring must say the check is format+scope, not authenticity"
    )

def test_a_page_that_loses_its_banner_is_reported():
    """The set is enumerated so a count cannot absorb a missing page."""
    clean, detail = gate.banner_findings(
        [("README.md", "1.0"), ("zh/README.md", "1.0")],
        "1.0",
        expected_pages={"README.md": 1, "zh/README.md": 1, "architecture.md": 1},
    )
    assert not clean
    assert "architecture.md" in detail


def test_a_page_that_gains_a_banner_is_reported():
    """An unlisted page carrying a version is a claim nobody is reconciling."""
    clean, detail = gate.banner_findings(
        [("README.md", "1.0"), ("zh/README.md", "1.0"), ("new_page.md", "1.0")],
        "1.0",
        expected_pages={"README.md": 1, "zh/README.md": 1},
    )
    assert not clean
    assert "new_page.md" in detail


def test_a_stale_version_is_reported_even_when_every_page_is_present():
    clean, detail = gate.banner_findings(
        [("README.md", "0.96a6"), ("zh/README.md", "1.0")],
        "1.0",
        expected_pages={"README.md": 1, "zh/README.md": 1},
    )
    assert not clean
    assert "README.md says 0.96a6" in detail


def test_both_colon_widths_are_recognised(tmp_path):
    """The Chinese pages use a full-width colon, and one uses the ASCII one."""
    (tmp_path / "full.md").write_text("> **版本**：0.96a8\n", encoding="utf-8")
    (tmp_path / "half.md").write_text("> **版本**: 0.96a8\n", encoding="utf-8")
    (tmp_path / "cur.md").write_text("> **当前版本：0.96a8**\n", encoding="utf-8")
    found = dict(gate.find_doc_banners(tmp_path))
    assert found == {"full.md": "0.96a8", "half.md": "0.96a8", "cur.md": "0.96a8"}, found

def test_losing_one_of_two_banners_on_the_same_page_is_reported():
    """A page count, not a page set: the extension guides carry two banners."""
    clean, detail = gate.banner_findings(
        [("guide.md", "1.0")],
        "1.0",
        expected_pages={"guide.md": 2},
    )
    assert not clean
    assert "guide.md" in detail


def test_a_tag_prefixed_banner_is_treated_as_an_applicability_claim(tmp_path):
    """``**版本**：v0.90`` says which release a page describes, not which is current.

    Two pages use that form to describe older behaviour; dragging them to the
    SSOT would be a false positive, and silently stripping the prefix would hide
    that the two forms mean different things.
    """
    (tmp_path / "p.md").write_text("> **版本**：v0.90\n", encoding="utf-8")
    assert gate.find_doc_banners(tmp_path) == []


def test_a_tag_prefixed_floor_is_still_skipped(tmp_path):
    """The ``+`` rule applies to the prefixed form too."""
    (tmp_path / "p.md").write_text("> **版本**: v0.90a5+\n", encoding="utf-8")
    assert gate.find_doc_banners(tmp_path) == []


def test_a_report_showing_a_failure_stops_the_tag(tmp_path):
    """Every other check reads tokens, banners and files. This one reads the tests.

    A tree with a failing test used to pass (a) through (f) without difficulty: none of
    them looked at test results at all.
    """
    report = tmp_path / "junit.xml"
    report.write_text(
        '<?xml version="1.0"?><testsuites><testsuite name="pytest" tests="1300" '
        'failures="2" errors="0" skipped="2"><testcase classname="t" name="x">'
        '<failure message="boom"/></testcase></testsuite></testsuites>',
        encoding="utf-8",
    )

    result = _run_gate("review-a", "sync-a", junit=str(report))

    assert "FAIL (g)" in result.stdout, result.stdout[-400:]
    assert "TAG GATE FAIL" in result.stdout, result.stdout[-400:]
    assert result.returncode != 0


def test_a_missing_report_is_not_a_passing_run(tmp_path):
    """No report is not the same as a clean one; the gate has to say so."""
    absent = tmp_path / "never-written.xml"

    result = _run_gate("review-a", "sync-a", junit=str(absent))

    assert "FAIL (g)" in result.stdout, result.stdout[-400:]
    assert "does not exist" in result.stdout, result.stdout[-400:]
    assert result.returncode != 0

