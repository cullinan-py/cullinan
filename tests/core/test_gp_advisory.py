"""Unit tests for ``scripts/verify_gp_advisory.py``.

The finder is advisory: it prints candidates and never decides PASS/FAIL, so
these tests check that it keeps producing the candidates it is meant to
produce rather than asserting a verdict. The end-to-end run is exercised by
``test_advisory_finder_returns_no_verdict``.
"""
import importlib.util
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = REPO_ROOT / "scripts" / "verify_gp_advisory.py"

assert SCRIPT_PATH.is_file(), f"advisory script missing: {SCRIPT_PATH}"
_spec = importlib.util.spec_from_file_location("verify_gp_advisory", SCRIPT_PATH)
assert _spec is not None and _spec.loader is not None
advisory = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(advisory)


def test_declared_replacement_sites_are_enumerated():
    """The finder lists every ``deprecated(..., alternative=...)`` declaration."""
    targets = advisory.iter_alternative_targets(REPO_ROOT)

    assert targets, "the advisory finder matched no declared replacement"
    assert all(alternative.strip() for _, _, alternative in targets)
    alternatives = {alternative for _, _, alternative in targets}
    # The compatibility helper announced ``MiddlewareRegistry.get_all()`` as its
    # replacement; a finder that stopped reading ``alternative=`` would lose it.
    assert "MiddlewareRegistry.get_all()" in alternatives


def test_silent_face_candidates_are_enumerated():
    """Silent-face candidates are reported with the phrase that matched."""
    candidates = advisory.iter_silent_face_candidates(REPO_ROOT)

    assert candidates, "the advisory finder matched no silent-face candidate"
    for relative, line, name, phrase in candidates:
        assert relative.endswith(".py")
        assert isinstance(line, int) and line > 0
        assert name
        assert phrase in advisory.SILENT_FACE_PHRASES


def test_advisory_finder_returns_no_verdict():
    """Running the finder always succeeds: it offers candidates, not a verdict."""
    assert advisory.main(["--repo", str(REPO_ROOT)]) == 0
