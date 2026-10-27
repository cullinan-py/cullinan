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
    assert "MIN_DOC_BANNERS" in body and "stale" in body, (
        "(e) must fail on a stale banner and on an empty scan"
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

