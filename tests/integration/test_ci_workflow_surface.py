"""Keep the CI surface honest about two things it has already got wrong.

* the cross-platform matrix once lived only on a throwaway branch, so a clean
  clone could not reproduce the run that a release decision was based on;
* the docs deploy job installed mkdocs, its theme and two plugins, but not the
  docstring handler, so the published site silently stopped at the previous
  version while the package moved on.

Neither failure shows up as a failing test, because both are about the shape of
the workflows rather than the code. They are checked here as text, which is all
the shape is.
"""

from __future__ import annotations

import pathlib

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
WORKFLOWS = REPO_ROOT / ".github" / "workflows"


def _read(name: str) -> str:
    return (WORKFLOWS / name).read_text(encoding="utf-8")


def test_the_cross_platform_matrix_ships_with_the_repository():
    path = WORKFLOWS / "os-matrix.yml"
    assert path.is_file(), (
        "the multi-OS workflow is missing, so the matrix that a release relies on "
        "cannot be reproduced from a clean clone"
    )


def test_the_cross_platform_matrix_never_runs_on_a_shared_branch():
    text = _read("os-matrix.yml")
    assert '"dev/**"' in text or "'dev/**'" in text, (
        "the multi-OS workflow no longer names dev/** as its push trigger"
    )
    for branch in ("preview", "master", "release/"):
        assert f'- "{branch}' not in text and f"- '{branch}" not in text, (
            f"the multi-OS workflow has started running on {branch}, which costs four "
            "full suites per push on a branch that other work depends on"
        )


def test_the_docs_deploy_installs_what_the_api_reference_needs():
    text = _read("mkdocs-build.yml")
    assert "mkdocstrings" in text, (
        "the docs deploy job does not install the docstring handler, so the API "
        "reference aborts the build and the site keeps the previous version"
    )
    assert "pip install -e ." in text, (
        "the docs deploy job does not install the package, and the handler reads the "
        "API out of it"
    )


def test_the_docs_validation_installs_the_same_handler():
    text = _read("docs-validate.yml")
    assert "mkdocstrings" in text, (
        "the docs validation job does not install the docstring handler, so it "
        "validates a build that cannot be the one that ships"
    )
