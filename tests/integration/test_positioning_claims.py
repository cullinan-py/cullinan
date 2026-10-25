# -*- coding: utf-8 -*-
"""Check the positioning page's claims, and that both languages claim the same.

`scripts/check_claims.py` does the work; this file makes it part of the ordinary
test run, because a check nobody runs is a comment. It also holds the two
language versions to the same claim set: a translated page may phrase a claim
differently, but it may not quietly drop one.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "check_claims.py"
ENGLISH = REPO_ROOT / "docs" / "why-cullinan.md"
CHINESE = REPO_ROOT / "docs" / "zh" / "why-cullinan.md"


def _module():
    spec = importlib.util.spec_from_file_location("check_claims", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_the_script_exists_and_self_tests():
    assert SCRIPT.is_file(), "the claim checker is missing"
    assert _module()._self_test() == 0


def test_every_claim_still_has_its_evidence():
    module = _module()
    payload = module.extract_claims(ENGLISH.read_text(encoding="utf-8"))
    problems = module.check(REPO_ROOT, payload)
    assert not problems, "positioning claims lost their evidence: " + "; ".join(problems)


def test_no_claim_is_unsupported():
    module = _module()
    payload = module.extract_claims(ENGLISH.read_text(encoding="utf-8"))
    unsupported = [claim["id"] for claim in payload["claims"] if not claim.get("evidence")]
    assert unsupported == [], f"these claims are asserted without evidence: {unsupported}"


def test_both_languages_declare_the_same_claims():
    module = _module()
    english = module.extract_claims(ENGLISH.read_text(encoding="utf-8"))
    chinese = module.extract_claims(CHINESE.read_text(encoding="utf-8"))

    english_ids = [claim["id"] for claim in english["claims"]]
    chinese_ids = [claim["id"] for claim in chinese["claims"]]
    assert english_ids == chinese_ids, (
        "the two language versions disagree about which claims exist: "
        f"en={english_ids} zh={chinese_ids}"
    )


def test_the_chinese_page_points_at_evidence_that_exists_too():
    module = _module()
    chinese = module.extract_claims(CHINESE.read_text(encoding="utf-8"))
    problems = module.check(REPO_ROOT, chinese)
    assert not problems, "the Chinese page cites evidence that does not hold: " + "; ".join(problems)


def test_a_claim_without_evidence_is_rejected():
    """The gate must be able to fail, or it is decoration."""
    module = _module()
    payload = {"claims": [{"id": "X", "claim": "something impressive", "evidence": [], "symbols": []}]}
    assert module.check(REPO_ROOT, payload)
