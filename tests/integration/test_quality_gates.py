# -*- coding: utf-8 -*-
"""Hold the quality gates themselves in place.

Each of these gates exists because a specific kind of rot is otherwise silent: a
coverage floor that is quietly deleted, a changelog that stops tracking
releases, a security policy that ages out of date, a publisher that would upload
a mislabelled artefact. The gates are configuration, and configuration is the
easiest thing in a repository to lose without noticing -- nothing fails when a
YAML block disappears.

So the gates are checked the same way the code is.
"""

from __future__ import annotations

import importlib.util
import re
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]


def _load(relative: str):
    path = REPO_ROOT / relative
    name = Path(relative).stem
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    # Registering the module is not optional: a module using ``dataclass`` with
    # postponed annotations resolves its own namespace through ``sys.modules``
    # while it executes, and fails with a bare AttributeError without this.
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _version() -> str:
    text = (REPO_ROOT / "cullinan" / "_version.py").read_text(encoding="utf-8")
    match = re.search(r'__version__\s*=\s*["\']([^"\']+)["\']', text)
    assert match, "cullinan/_version.py does not declare __version__"
    return match.group(1)


# ---------------------------------------------------------------- coverage gate


def test_coverage_floor_is_configured():
    pyproject = (REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    assert "[tool.coverage.run]" in pyproject, "coverage is not configured at all"
    match = re.search(r"^fail_under\s*=\s*(\d+)", pyproject, re.MULTILINE)
    assert match, "no fail_under, so coverage is measured but not enforced"
    floor = int(match.group(1))
    # A lower bound alone accepted 700, which would make CI permanently red --
    # a "gate" nobody can satisfy is deleted within a week.
    assert 0 < floor <= 100, f"fail_under={floor} is not a reachable percentage"
    assert floor >= 70, (
        "the coverage floor was lowered below the level the suite actually reaches; "
        "that needs an ADR, not a quiet edit"
    )


def test_ci_runs_the_coverage_gate():
    ci = (REPO_ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    assert "coverage run" in ci, "CI measures nothing"
    assert "coverage report" in ci, "CI measures coverage but never enforces the floor"


def test_coverage_is_a_development_dependency():
    requirements = (REPO_ROOT / "requirements-dev.txt").read_text(encoding="utf-8")
    assert "coverage" in requirements, "the gate depends on a package the toolchain does not install"


# --------------------------------------------------------------- changelog gate


def test_the_changelog_checker_self_tests():
    module = _load("scripts/check_changelog.py")
    assert module._self_test() == 0


def test_the_changelog_covers_the_released_versions():
    module = _load("scripts/check_changelog.py")
    text = (REPO_ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    problems = module.check(text, module.released_tags(REPO_ROOT), _version())
    assert not problems, "the changelog is not healthy: " + "; ".join(problems)


def test_the_changelog_gate_runs_in_ci_with_the_tags_it_needs():
    import yaml

    workflow = yaml.safe_load((REPO_ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8"))
    jobs = workflow.get("jobs", {})
    assert "changelog" in jobs, "the changelog check is not wired into CI at all"
    steps = jobs["changelog"].get("steps", [])
    checkouts = [step for step in steps if str(step.get("uses", "")).startswith("actions/checkout")]
    assert checkouts and checkouts[0].get("with", {}).get("fetch-depth") == 0, (
        "a shallow checkout sees no tags, so the continuity check would pass while checking nothing"
    )
    assert any("check_changelog.py" in str(step.get("run", "")) for step in steps)


def test_the_changelog_checker_refuses_to_pass_without_tags():
    module = _load("scripts/check_changelog.py")
    text = (REPO_ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    problems = module.check(text, [], _version())
    assert problems and "tags" in problems[0]


def test_the_changelog_checker_can_fail():
    module = _load("scripts/check_changelog.py")
    problems = module.check("## v0.1\n\n### Added\n\n- something\n", ["0.1", "0.2"], "0.2")
    assert problems, "the checker passed a changelog that is behind the release"


# ---------------------------------------------------------------- security policy


def test_security_policy_exists_and_names_a_private_channel():
    policy = REPO_ROOT / "SECURITY.md"
    assert policy.is_file(), "no SECURITY.md, so there is no stated way to report a vulnerability"
    text = policy.read_text(encoding="utf-8")
    assert "security/advisories/new" in text, "the policy does not name a private reporting channel"
    assert "TODO" not in text and "TBD" not in text, "the policy still contains placeholders"


def test_security_policy_supports_the_current_line():
    text = (REPO_ROOT / "SECURITY.md").read_text(encoding="utf-8")
    current = _version()
    match = re.match(r"(\d+)\.(\d+)", current)
    assert match, f"cannot read a version line out of {current!r}"
    minor = f"{match.group(1)}.{match.group(2)}"
    supported = re.findall(r"`(\d+\.\d+)\.x`", text)
    assert minor in supported, (
        f"SECURITY.md does not list the current line {minor}.x as supported; it claims {supported}"
    )


# ------------------------------------------------------------- publisher workflow


def test_publisher_refuses_a_mislabelled_tag():
    workflow = (REPO_ROOT / ".github" / "workflows" / "python-publish.yml").read_text(encoding="utf-8")
    assert "check_release_tag_matches_version.py" in workflow, (
        "the publisher would upload whatever tag it was handed without checking it against the code"
    )
    # The check has to run before the upload, or it is only a post-mortem.
    assert workflow.index("check_release_tag_matches_version.py") < workflow.index("twine upload")


def test_publisher_checks_the_artefact_it_builds():
    workflow = (REPO_ROOT / ".github" / "workflows" / "python-publish.yml").read_text(encoding="utf-8")
    assert "twine check" in workflow
    assert "import cullinan" in workflow, (
        "nothing proves the built wheel imports; a packaging fault would ship as a release"
    )


# ------------------------------------------------------------- documentation gate


def test_docs_build_installs_the_generator_and_the_package():
    workflow = (REPO_ROOT / ".github" / "workflows" / "docs-validate.yml").read_text(encoding="utf-8")
    assert "mkdocstrings" in workflow, (
        "the API reference pages are generated by mkdocstrings; without it the strict build fails"
    )
    assert "pip install -e ." in workflow, (
        "mkdocstrings reads the installed package; a docs build without it cannot generate the pages"
    )
