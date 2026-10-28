# -*- coding: utf-8 -*-
"""No internal identifiers in anything this repository can publish.

Why this test exists
--------------------
Twice now, a commit whose stated purpose was *removing* an internal reference
introduced a new one. The first time, a comment explained the word list by
pointing at the document that mandates it; the second time, a comment explained
a duplicated threshold by citing the ledger entry that names the defect. Both
sentences were written by someone who had just read the rule against doing
exactly that.

The lesson is not "be more careful". Care was not the missing ingredient -- the
detection was. Until now the only scanner for this lived outside the repository,
took its word list from a file outside the repository, and was invoked by a
pre-push hook that passes no `--strict` flag. In its default configuration a
missing word list yields `PARTIAL` and exit code 0. So a public file could name
an internal artifact freely and no exit code anywhere would turn red.

This test closes that: the patterns live in the repository, the scan runs on
every `pytest` invocation, and it needs nothing that is not already here.

What it does not do
-------------------
It does not look for the *content* of internal documents -- only for the shapes
that give them away: their vocabulary, their staff-role prefixes, their entry
numbering. A leak written in fresh prose with none of those markers still needs
a human. Pretending otherwise would make this test a alibi rather than a check.

The allowlist is one entry long and should stay that way. It exists because this
file has to spell out the patterns it forbids, so it matches itself. Widening it
means someone decided a published file may name internal artifacts.

Scope
-----
`git ls-files` only -- the same surface the isolation rule defines. Untracked and
ignored paths cannot reach a reader, and scanning them would drown the signal in
editor caches and build output.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]

#: 本文件是词表的唯一正本，必然命中自身 —— 这是唯一合法豁免。
ALLOWLIST = {"tests/regression/test_no_internal_identifiers.py"}

#: 四类「形状」——不涉密，只标识来源。
PATTERNS: Dict[str, str] = {
    # 内部载体与流程名。中文词表比英文更可靠：这些词在本项目之外几乎不会自然出现。
    "internal-vocabulary": (
        r"知识库|Obsidian|OneDrive|cullinan-vault|五方面同步|每轮必过门"
        r"|隔离门|推后裁定|僵尸六形态|留痕式变更|收口单|知识库治理"
    ),
    # 岗位缩写 + 分隔符。单独一个 ARCH 是建筑，`ARCH#` 才是台账。
    "role-prefix": r"\b(ORCH|INSPECTOR|STRAT|KNOWLEDGE|DESIGN)\s*[#:]|\b(ARCH|QA|PM|KB)\s*#",
    # 带强前缀的台账编号。只用两位以上字母的前缀，避免 `R-2` 这类数学写法。
    "ledger-id": r"\b(KN|EV|ISO)-\d{1,4}\b",
    # 单字母编号。**必须含 1 位**：实测过的两次泄漏里有一次正是 `D-2`（一位数），
    # 而 `\d{2,4}` 会把它放过去 —— 门槛写成"看起来更严"的样子反而漏检。
    # 放宽到 1 位在现有 489 个已追踪文件上命中 0 行，故无假阳性代价。
    "single-letter-id": r"\b(K|R|D|S|G|Z|W|F)-\d{1,4}\b",
}

_COMPILED = {name: re.compile(pat) for name, pat in PATTERNS.items()}

#: 二进制按扩展名跳过。用扩展名而非 try/decode：一个 latin-1 可解的文件会被
#: 误当文本，然后命中随机字节。
_BINARY_SUFFIXES = {
    ".png", ".jpg", ".jpeg", ".gif", ".ico", ".webp", ".pdf", ".zip", ".gz",
    ".whl", ".pyc", ".pyd", ".so", ".dll", ".exe", ".woff", ".woff2", ".ttf",
}


def tracked_files(root: Path) -> List[str]:
    """`git ls-files` 的相对路径。git 不可用时 skip，不静默返回空。"""
    proc = subprocess.run(
        ["git", "ls-files"], cwd=str(root), capture_output=True, text=True,
        encoding="utf-8", errors="replace",
    )
    if proc.returncode != 0:
        pytest.skip(f"git ls-files failed in {root}: {proc.stderr.strip()[:200]}")
    return [line for line in proc.stdout.splitlines() if line.strip()]


def scan_texts(texts: Dict[str, str]) -> List[Tuple[str, int, str, str]]:
    """→ [(path, lineno, pattern_name, line)]。抽出来是为了让自证测试能喂伪造输入。"""
    hits: List[Tuple[str, int, str, str]] = []
    for path, text in texts.items():
        if path in ALLOWLIST:
            continue
        for lineno, line in enumerate(text.splitlines(), 1):
            for name, rx in _COMPILED.items():
                if rx.search(line):
                    hits.append((path, lineno, name, line.strip()[:160]))
                    break  # 一行只报一次，避免同一行刷四条
    return hits


def read_surface(root: Path, files: Iterable[str]) -> Dict[str, str]:
    texts: Dict[str, str] = {}
    for rel in files:
        if Path(rel).suffix.lower() in _BINARY_SUFFIXES:
            continue
        path = root / rel
        try:
            texts[rel] = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue  # 读不了就不猜 —— 猜出来的命中比漏检更难查
    return texts


def test_tracked_files_carry_no_internal_identifiers():
    """已追踪面（= 可发布面）不得出现内部形状。"""
    root = REPO_ROOT
    files = tracked_files(root)
    assert files, "git ls-files returned nothing; the scan would be vacuously green"

    hits = scan_texts(read_surface(root, files))
    if hits:
        report = "\n".join(f"  {p}:{n}  [{k}]  {line}" for p, n, k, line in hits)
        pytest.fail(
            f"{len(hits)} internal identifier(s) on the published surface.\n"
            f"These are shapes that name internal artifacts; a reader outside the "
            f"project cannot resolve them.\n{report}\n"
            f"If a line is genuinely public vocabulary, widen ALLOWLIST in this "
            f"file *and say why* -- do not loosen a pattern."
        )


def test_the_scanner_can_actually_fail():
    """证明上一条不是永远绿。

    没有这一条，一个写错的正则会让 `test_..._carry_no_internal_identifiers`
    变成「永远通过」，而它的名字会让人以为已经查过了。
    """
    fake_texts = {
        "fake/comment.py": "# see K-78 for the reason\n",
        "fake/role.py": "# owner: ARCH#3\n",
        "fake/prose.md": "详见知识库治理下的那份件\n",
        "fake/ledger.py": "# ISO-104 is the precedent\n",
        "fake/clean.py": "# this line carries nothing internal\n",
    }
    hits = scan_texts(fake_texts)
    found_paths = {p for p, _, _, _ in hits}
    expected = {"fake/comment.py", "fake/role.py", "fake/prose.md", "fake/ledger.py"}

    missing = expected - found_paths
    assert not missing, f"scanner missed fabricated violations in: {sorted(missing)}"
    assert "fake/clean.py" not in found_paths, (
        "scanner flagged a clean line; a false positive here will get the whole "
        "test disabled rather than fixed"
    )


def test_allowlist_stays_minimal():
    """豁免必须一直是 1 条。

    这条不是洁癖：allowlist 每加一项，就等于有人决定「这个公开文件可以点名内部件」。
    那种决定应当是一次显式的评审，不是顺手改一行。
    """
    assert ALLOWLIST == {"tests/regression/test_no_internal_identifiers.py"}, (
        f"ALLOWLIST grew: {sorted(ALLOWLIST)}. "
        "Adding an entry means a published file may name internal artifacts; "
        "that needs a decision record, not a quiet edit."
    )
