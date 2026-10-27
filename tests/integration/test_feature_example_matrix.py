# -*- coding: utf-8 -*-
"""Hold the examples to the claim that every public feature is demonstrated.

Two failures are easy to make and hard to notice:

* a feature is taught in the guides, but no example runs it -- so the guide is
  the only thing anyone can check it against;
* an example directory exists, nobody wired it into the docs, and it quietly
  rots until the day someone runs it.

``examples/features.json`` is the claim, and this module checks it both ways.
The evidence strings are what keep an entry honest: a directory with a nice
README and no code cannot satisfy them.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
EXAMPLES = REPO_ROOT / "examples"
MATRIX_PATH = EXAMPLES / "features.json"


def _matrix() -> dict:
    return json.loads(MATRIX_PATH.read_text(encoding="utf-8"))


def _python_sources(example_dir: Path) -> str:
    """Python sources with comments removed.

    A substring check over raw text can be satisfied by a comment -- replacing
    an example's whole body with ``# def main()`` kept the gate green. Strip the
    comments and the evidence has to appear in something that executes.
    """
    import io
    import tokenize

    chunks: list[str] = []
    for path in sorted(example_dir.rglob("*.py")):
        source = path.read_text(encoding="utf-8", errors="replace")
        lines = source.splitlines(True)
        try:
            for token in tokenize.generate_tokens(io.StringIO(source).readline):
                # Comments and string literals are both removed: a docstring
                # describing the feature is prose about the code, not the code.
                if token.type not in (tokenize.COMMENT, tokenize.STRING):
                    continue
                row, start = token.start
                _end_row, end = token.end
                if row == _end_row and row - 1 < len(lines):
                    lines[row - 1] = lines[row - 1][:start] + lines[row - 1][end:]
        except (tokenize.TokenError, IndentationError):
            pass
        chunks.append("".join(lines))
    return "\n".join(chunks)


def _example_dirs() -> list[str]:
    # ``__pycache__`` shows up the moment anything imports an example, which CI
    # does by running the examples; a runtime artifact is not an undeclared
    # example, and treating it as one turns a green build red on a fresh clone.
    return sorted(
        path.name
        for path in EXAMPLES.iterdir()
        if path.is_dir() and not path.name.startswith("__")
    )


def test_the_matrix_is_present_and_well_formed():
    assert MATRIX_PATH.is_file(), "examples/features.json is the claim this gate checks"

    matrix = _matrix()
    features = matrix.get("features", [])
    assert features, "the matrix declares no features at all"

    for entry in features:
        for key in ("feature", "example", "evidence", "docs"):
            assert entry.get(key), f"entry {entry!r} is missing {key}"
        assert isinstance(entry["evidence"], list) and entry["evidence"], (
            f"{entry['example']} has no evidence strings, so the entry could survive an empty directory"
        )


def test_declared_examples_exist_and_actually_demonstrate_the_feature():
    for entry in _matrix()["features"]:
        example_dir = EXAMPLES / entry["example"]
        assert example_dir.is_dir(), f"{entry['example']} is declared as an example but does not exist"
        assert (example_dir / "README.md").is_file(), f"{entry['example']} has no README.md"

        sources = _python_sources(example_dir)
        assert sources.strip(), f"{entry['example']} contains no Python at all"

        missing = [needle for needle in entry["evidence"] if needle not in sources]
        assert not missing, (
            f"{entry['example']} does not demonstrate {entry['feature']!r}: "
            f"the sources never mention {missing}"
        )


def test_every_example_is_declared():
    declared = {entry["example"] for entry in _matrix()["features"]}
    present = set(_example_dirs())
    undeclared = sorted(present - declared)
    assert not undeclared, (
        "these example directories are not declared in examples/features.json, so nothing "
        f"holds them to a feature or a docs page: {undeclared}"
    )


def test_each_example_is_claimed_once():
    names = [entry["example"] for entry in _matrix()["features"]]
    duplicates = sorted({name for name in names if names.count(name) > 1})
    assert not duplicates, f"these examples are claimed by more than one feature: {duplicates}"


def test_each_feature_links_to_a_page_that_exists_in_both_languages():
    # Pages that legitimately exist in one language only. Each entry is a known
    # gap recorded on purpose: the list has to stay explicit, because a silent
    # gap is how a bilingual project quietly becomes a monolingual one.
    known_monolingual = {
        "packaging.md": "Chinese packaging guide not written yet",
    }

    for entry in _matrix()["features"]:
        english = REPO_ROOT / "docs" / entry["docs"]
        chinese = REPO_ROOT / "docs" / "zh" / entry["docs"]
        assert english.is_file(), f"{entry['feature']!r} points at docs/{entry['docs']}, which does not exist"
        if entry["docs"] in known_monolingual:
            continue
        assert chinese.is_file(), (
            f"{entry['feature']!r} points at docs/{entry['docs']}, but the Chinese counterpart "
            f"docs/zh/{entry['docs']} does not exist -- the two channels are supposed to stay in step"
        )


def test_the_monolingual_exception_list_does_not_grow_silently():
    """Only pages that were already monolingual may stay that way."""
    allowed = {"packaging.md", "templates/release-note-template.md"}
    docs_root = REPO_ROOT / "docs"
    missing = []
    for english in docs_root.rglob("*.md"):
        relative = english.relative_to(docs_root)
        if relative.parts[0] == "zh":
            continue
        if not (docs_root / "zh" / relative).is_file():
            missing.append(relative.as_posix())
    unexpected = sorted(set(missing) - allowed)
    assert not unexpected, (
        "these pages have no Chinese counterpart and are not on the recorded exception list: "
        f"{unexpected}"
    )


def test_the_gate_can_actually_fail():
    """Guard against the gate being vacuously true.

    If a future refactor made the evidence check compare against the wrong
    thing -- an empty string, a normalised form, a cached file -- every test
    above would still pass. This one feeds the same comparison a value that
    cannot be present and requires it to be reported.
    """
    entry = _matrix()["features"][0]
    sources = _python_sources(EXAMPLES / entry["example"])
    absent = "definitely-not-in-this-example-8f3c1a"
    missing = [needle for needle in entry["evidence"] + [absent] if needle not in sources]
    assert missing == [absent]


# What each kind of example promises about its own shape. Without this, a
# directory can satisfy the matrix with a README and a stray function while
# claiming to be something a reader can run.
KNOWN_KINDS = {"runnable", "test-driven", "historical"}


def test_every_example_names_a_kind_it_belongs_to():
    unknown = [
        f"{entry['example']}: {entry.get('kind')!r}"
        for entry in _matrix()["features"]
        if entry.get("kind") not in KNOWN_KINDS
    ]
    assert not unknown, (
        "these examples do not say what kind of example they are, so nothing can "
        f"decide what shape they should have: {unknown}"
    )


def test_each_kind_has_the_shape_it_promises():
    problems = []
    for entry in _matrix()["features"]:
        directory = EXAMPLES / entry["example"]
        kind = entry["kind"]

        if kind == "runnable":
            if not (directory / "__main__.py").is_file():
                problems.append(
                    f"{entry['example']} is declared runnable but has no __main__.py, "
                    "so `python -m examples.<name>` cannot start it"
                )
        elif kind == "test-driven":
            if not list(directory.glob("test_*.py")):
                problems.append(
                    f"{entry['example']} is declared test-driven but holds no test_*.py, "
                    "so pytest collects nothing from it"
                )
        elif kind == "historical":
            readme = (directory / "README.md").read_text(encoding="utf-8").lower()
            if not any(marker in readme for marker in ("legacy", "historical", "历史", "0.90", "0.9x")):
                problems.append(
                    f"{entry['example']} is declared historical but its README never says so, "
                    "so a reader will try to run it as current guidance"
                )

    assert not problems, "examples do not match the shape their kind promises:/n" + "\n".join(problems)
