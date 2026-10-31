# -*- coding: utf-8 -*-
"""The README's quick-start block is executed, because nobody executes it.

`docs/` has a guide-example gate (`test_examples_public_guides.py`) and the
examples have runnable smoke tests. The repository root does not: `README.MD` is
the first thing a reader meets, its quick-start is the one block most likely to be
copied verbatim, and nothing ran it.

That is not hypothetical. The quick-start kept ``from cullinan.web import
controller`` after ``controller`` moved out of that module, so the import returned
a *module* instead of the decorator and the first decorated class raised
``TypeError: 'module' object is not callable``. It shipped that way from the
release that moved the symbol until someone tried the block by hand. A block that
is only read is a block that is only believed.

This file is the executor for that block. It extracts every ```` ```python ````
fence from `README.MD`, writes each into a throwaway package, and imports it in a
subprocess -- a subprocess because the block calls ``@configure(...)`` at module
level, which would otherwise reconfigure the test process.

**The self-test is the point.** A checker that has only ever seen passing input
cannot be distinguished from a checker that does nothing. ``test_a_broken_block_is_reported``
feeds a block with the old, broken import shape and asserts the checker reports it,
so a future edit that turns this file into a no-op fails here.
"""

from __future__ import annotations

import os
import subprocess
import sys
import textwrap
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
README = REPO_ROOT / "README.MD"

FENCE = "```"


def python_blocks(markdown: str) -> list[str]:
    """Every ```` ```python ```` fence in ``markdown``, without the fence lines."""
    blocks: list[str] = []
    current: list[str] | None = None
    for line in markdown.splitlines():
        stripped = line.strip()
        if current is None:
            if stripped in ("```python", "```py"):
                current = []
            continue
        if stripped == FENCE:
            blocks.append("\n".join(current))
            current = None
            continue
        current.append(line)
    if current is not None:
        raise AssertionError(
            "a ```python fence is never closed; the block cannot be run and a reader "
            "would copy the fence markers as code"
        )
    return blocks


def run_block(block: str, workdir: Path) -> subprocess.CompletedProcess:
    """Import ``block`` as a module inside ``workdir``, in a subprocess.

    The block is written as ``block_main.py`` inside a package directory so that
    ``user_packages`` resolves the way a reader's ``minimal_app/`` would.
    """
    package = workdir / "readme_block_app"
    package.mkdir(parents=True, exist_ok=True)
    (package / "__init__.py").write_text("", encoding="utf-8")
    (package / "main.py").write_text(textwrap.dedent(block) + "\n", encoding="utf-8")

    environment = dict(os.environ)
    environment["PYTHONPATH"] = os.pathsep.join(
        [str(workdir), str(REPO_ROOT), environment.get("PYTHONPATH", "")]
    ).rstrip(os.pathsep)
    return subprocess.run(
        [sys.executable, "-c", "import readme_block_app.main; print('README_BLOCK_OK')"],
        capture_output=True,
        text=True,
        cwd=str(workdir),
        env=environment,
        timeout=180,
    )


def test_the_readme_quick_start_block_runs(tmp_path):
    """The block a reader copies first must import without raising."""
    blocks = python_blocks(README.read_text(encoding="utf-8"))
    assert blocks, (
        "README.MD has no ```python block any more; this file is then guarding "
        "nothing and should be deleted rather than left green"
    )

    for index, block in enumerate(blocks):
        completed = run_block(block, tmp_path)
        assert completed.returncode == 0, (
            f"README python block #{index + 1} does not run: {completed.stderr[-1200:]}"
        )
        assert "README_BLOCK_OK" in completed.stdout


def test_a_broken_block_is_reported(tmp_path):
    """The checker's own red side: the shape that shipped broken must fail here.

    ``from cullinan.web import controller`` was the actual defect. It is kept as a
    fixture because a checker nobody has seen fail is indistinguishable from a
    checker that does nothing.
    """
    broken = (
        "from cullinan.web import controller\n"
        "from cullinan.web import get_api\n"
        "\n"
        "@controller(url='/x')\n"
        "class Broken:\n"
        "    @get_api(url='')\n"
        "    def handle(self):\n"
        "        return {}\n"
    )
    completed = run_block(broken, tmp_path)
    assert completed.returncode != 0, (
        "a block using the pre-move import shape imported cleanly, so this file no "
        "longer detects the defect it exists for"
    )
