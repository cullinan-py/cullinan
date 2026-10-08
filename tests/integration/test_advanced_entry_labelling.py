# -*- coding: utf-8 -*-
"""The advanced entry class must never appear unlabelled in public docs.

``Application(...)`` is the advanced entry class. A page or example may use it,
but only when the same material says so -- an unlabelled mention is how a reader
gets taught to reach for the class form without knowing it is the advanced face.

The older guard only watched a hand-picked list of recommended files, so a
mention added to (say) ``docs/wiki/middleware.md`` would have gone unnoticed.
These tests cover the whole public documentation and example surface instead,
and prove the check itself can go red.
"""

from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]

# Phrases that explicitly mark the advanced face, in both site languages.
ADVANCED_MARKERS = (
    "advanced entry class",
    "advanced / boundary",
    "高级入口类",
    "高级 / 边界",
)

# The strict tier: these must not mention the class form at all.
RECOMMENDED_FILES = (
    "README.MD",
    "docs/examples.md",
    "docs/zh/examples.md",
    "docs/api_reference.md",
    "docs/zh/api_reference.md",
    "docs/architecture.md",
    "docs/zh/architecture.md",
    "docs/getting_started.md",
    "docs/zh/getting_started.md",
    "examples/README.md",
)


def find_unlabelled_mentions(entries):
    """Return the labels of entries that mention ``Application(`` unlabelled.

    ``entries`` is an iterable of ``(label, text)`` pairs, so the rule can be
    exercised directly on synthetic input -- including input that must be
    rejected -- without touching the real tree.
    """
    offenders = []
    for label, text in entries:
        if "Application(" not in text:
            continue
        lowered = text.lower()
        if any(marker.lower() in lowered for marker in ADVANCED_MARKERS):
            continue
        offenders.append(label)
    return offenders


def _labelling_text(rel_path: str, text: str) -> str:
    """Text used to look for the label, allowing a sibling example README.

    An example's ``.py`` carries the code while its ``README.md`` carries the
    explanation, so the label legitimately lives next door.
    """
    path = REPO_ROOT / rel_path
    if path.suffix != ".py" or not rel_path.startswith("examples/"):
        return text
    sibling = path.parent / "README.md"
    if sibling.is_file():
        return text + "\n" + sibling.read_text(encoding="utf-8")
    return text


def _collect_public_surface():
    entries = []
    readme = REPO_ROOT / "README.MD"
    if readme.is_file():
        entries.append(("README.MD", readme.read_text(encoding="utf-8")))
    for base in ("docs", "examples"):
        root = REPO_ROOT / base
        if not root.is_dir():
            continue
        for path in sorted(root.rglob("*")):
            if not path.is_file() or path.suffix not in (".md", ".py"):
                continue
            rel = path.relative_to(REPO_ROOT).as_posix()
            raw = path.read_text(encoding="utf-8")
            entries.append((rel, _labelling_text(rel, raw)))
    return entries


def test_no_unlabelled_advanced_entry_mentions_in_public_surface():
    offenders = find_unlabelled_mentions(_collect_public_surface())
    assert not offenders, (
        "these public files mention Application(...) without marking it as the "
        "advanced face: " + ", ".join(offenders)
    )


@pytest.mark.parametrize("rel_path", RECOMMENDED_FILES)
def test_recommended_files_never_mention_the_class_form(rel_path):
    path = REPO_ROOT / rel_path
    assert path.is_file(), f"recommended file missing: {rel_path}"
    assert "Application(" not in path.read_text(encoding="utf-8"), (
        f"{rel_path} must not teach Application(...)"
    )


def test_the_guard_flags_an_unlabelled_wiki_page():
    """Red side: this is the hole the file-list guard used to leave open."""
    offenders = find_unlabelled_mentions([
        ("docs/wiki/middleware.md", "app = Application(main)\napp.run()\n"),
    ])
    assert offenders == ["docs/wiki/middleware.md"]


def test_the_guard_flags_an_unlabelled_example():
    offenders = find_unlabelled_mentions([
        ("examples/new_demo/demo.py", "app = Application(entry)\n"),
    ])
    assert offenders == ["examples/new_demo/demo.py"]


@pytest.mark.parametrize("marker", ADVANCED_MARKERS)
def test_the_guard_accepts_a_labelled_mention(marker):
    """Green side: a labelled mention must pass, in either language."""
    offenders = find_unlabelled_mentions([
        ("docs/wiki/whatever.md", f"Application(...) is the {marker}.\n"),
    ])
    assert offenders == []


def test_the_guard_ignores_files_without_the_class_form():
    offenders = find_unlabelled_mentions([
        ("docs/wiki/plain.md", "@configure(middlewares=[AuditMiddleware])\n"),
    ])
    assert offenders == []
