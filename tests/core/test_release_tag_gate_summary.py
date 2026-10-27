# -*- coding: utf-8 -*-
"""The pre-tag gate's summary must echo every check it enforces.

A check that is registered and enforced but absent from the printed summary is
indistinguishable, from the outside, from a check that does not exist at all --
which is exactly how an installed gate gets mistaken for a missing one. These
tests pin the correspondence so the two cannot drift apart again.
"""
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


def _run_gate(review: str, sync: str, sign_off: str = "P"):
    import subprocess
    import sys
    return subprocess.run(
        [sys.executable, str(GATE_PATH),
         "--sign-off-token", sign_off,
         "--review-token", review,
         "--sync-token", sync],
        cwd=str(REPO_ROOT), capture_output=True, text=True, encoding="utf-8",
    )


def test_the_tree_bound_credential_is_accepted():
    tree = _head_tree()
    result = _run_gate(f"ARCH#tree={tree}", f"KB#tree={tree}")
    assert "PASS (f)" in result.stdout, result.stdout[-400:]


def test_an_unbound_credential_is_refused_with_the_bound_form_suggested():
    result = _run_gate("review-0.96a7.post1-d69e66d", "sync-0.96a7.post1-d69e66d")
    assert "FAIL (f)" in result.stdout
    assert "reissue" in result.stdout, "the message must say how to fix the credential"
    assert _head_tree() in result.stdout, "and must print the tree to bind to"


def test_a_credential_bound_to_another_tree_fails_for_that_reason():
    """V4: a stale credential must fail as "wrong tree", not "unrecognised"."""
    zero = "0" * 40
    result = _run_gate(f"ARCH#tree={zero}", f"KB#tree={_head_tree()}")
    assert "FAIL (f)" in result.stdout
    assert "different tree" in result.stdout
    assert "reissue" not in result.stdout, (
        "the format was understood; sending the reader off to reissue would hide that "
        "the real problem is a credential for a different tree"
    )


def test_sign_off_is_exempt_from_the_tree_binding():
    """The sign-off credential binds to its evidence bundle, not to the tree."""
    tree = _head_tree()
    result = _run_gate(f"ARCH#tree={tree}", f"KB#tree={tree}", sign_off="<bundle>#sha256=deadbeef")
    assert "PASS (f)" in result.stdout


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
        expected_pages={"README.md", "zh/README.md", "architecture.md"},
    )
    assert not clean
    assert "architecture.md" in detail


def test_a_page_that_gains_a_banner_is_reported():
    """An unlisted page carrying a version is a claim nobody is reconciling."""
    clean, detail = gate.banner_findings(
        [("README.md", "1.0"), ("zh/README.md", "1.0"), ("new_page.md", "1.0")],
        "1.0",
        expected_pages={"README.md", "zh/README.md"},
    )
    assert not clean
    assert "new_page.md" in detail


def test_a_stale_version_is_reported_even_when_every_page_is_present():
    clean, detail = gate.banner_findings(
        [("README.md", "0.96a6"), ("zh/README.md", "1.0")],
        "1.0",
        expected_pages={"README.md", "zh/README.md"},
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

