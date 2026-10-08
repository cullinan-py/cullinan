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
_REGISTERED = re.compile(r'check\(\s*"\s*\(([a-z])\)')
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
