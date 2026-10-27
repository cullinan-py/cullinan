"""Hygiene of the published surface: links, metadata form, and package discovery.

Three properties, each of which failed silently before it was pinned:

1. **Relative links resolve.** The published docs are built from the repository,
   so a link to a page that was moved or removed does not break the build -- it
   produces a 404 for the reader. That is what happened when the wiki section was
   replaced: five example READMEs kept pointing at the old paths.
2. **Frontmatter is bare key/value, not a YAML fence.** The documentation toolchain
   strips bare key/value lines from the rendered page; a fenced block renders as
   body text, so the reader sees `title:` and `slug:` at the top of the page.
3. **The packaging finder does not adopt the theme directory.** ``overrides/`` is
   the MkDocs theme override directory and also a name on PyPI; declaring it as a
   package produced a ``top_level.txt`` entry with no files behind it.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
LINK = re.compile(r"\]\(([^)#\s]+\.md)(?:#[^)]*)?\)")
SKIP_SCHEMES = ("http://", "https://", "mailto:")


def _markdown_files():
    for base in ("docs", "examples"):
        yield from sorted((REPO_ROOT / base).rglob("*.md"))


def _resolve(page: Path, target: str) -> bool:
    if (page.parent / target).exists():
        return True
    return (REPO_ROOT / target).exists()


def test_relative_links_resolve():
    """Every relative markdown link points at a file that exists."""
    broken = []
    for page in _markdown_files():
        text = page.read_text(encoding="utf-8", errors="replace")
        for match in LINK.finditer(text):
            target = match.group(1)
            if target.startswith(SKIP_SCHEMES):
                continue
            if not _resolve(page, target):
                broken.append(f"{page.relative_to(REPO_ROOT).as_posix()} -> {target}")
    assert not broken, "relative links that resolve to nothing: " + "; ".join(broken)


def test_relative_link_check_is_falsifiable(tmp_path):
    """The check must report a link to a page that is not there."""
    page = tmp_path / "page.md"
    page.write_text("[gone](./not-there.md)\n", encoding="utf-8")
    text = page.read_text(encoding="utf-8")
    assert [m.group(1) for m in LINK.finditer(text)] == ["./not-there.md"]
    assert not _resolve(page, "./not-there.md")


def test_docs_frontmatter_is_bare_key_value():
    """A fenced metadata block renders as body text; bare keys are stripped."""
    fenced = [
        page.relative_to(REPO_ROOT).as_posix()
        for page in sorted((REPO_ROOT / "docs").rglob("*.md"))
        if page.read_text(encoding="utf-8", errors="replace").startswith("---\n")
    ]
    assert not fenced, (
        "these pages open with a YAML fence, which the build renders as body text "
        "instead of consuming it: " + ", ".join(fenced)
    )


def _packaging_excludes() -> set[str]:
    text = (REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    block = text.split("[tool.setuptools.packages.find]", 1)[1]
    exclude_open = block.index("exclude = [")
    body = block[exclude_open:block.index("]", exclude_open)]
    return set(re.findall(r'"([^"]+)"', body))


def test_the_theme_override_directory_is_not_a_package():
    """`overrides/` is theme HTML; declaring it ships a module that is not there."""
    assert (REPO_ROOT / "overrides" / "main.html").is_file(), (
        "the theme override directory moved; update this guard and the packaging "
        "exclusion together, or the wheel starts declaring a module again"
    )
    excludes = _packaging_excludes()
    assert "overrides*" in excludes, (
        "`overrides` is back in the package finder: top_level.txt will list a "
        f"top-level module the wheel does not contain (excludes: {sorted(excludes)})"
    )


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__]))
