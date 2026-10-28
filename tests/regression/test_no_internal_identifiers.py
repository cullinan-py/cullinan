# -*- coding: utf-8 -*-
"""No internal identifiers in anything this repository can publish.

Why this test exists
--------------------
Three times now, a commit whose stated purpose was *removing* an internal
reference introduced a new one. Twice on the code surface, and once -- the third
time -- inside this very file, on the commit that was supposed to close the
structural hole.

The third one is the instructive one. The first version of this file carried the
forbidden shapes literally: real ledger numbers in the docstring examples, real
numbers again in the fabricated test fixtures, and a whole-file allowlist so that
the scanner would skip itself. The result was a detector that was exempt from
itself, pinned that exemption as a requirement, and shipped real identifiers in
the process. A checker that cannot fail on its own file is not a checker; it is a
comment that runs.

So the exemptions here are as narrow as the job allows:

* the pattern table is bracketed by two sentinel lines and **only those lines are
  skipped** -- everything else in this file is scanned like any other;
* the fixtures are assembled at import time from fragments, so no forbidden
  shape is ever written down literally;
* the companion test asserts the exemption is exactly one bracketed region, so
  widening it means editing a boundary on purpose rather than adding a filename.

What it does not do
-------------------
It does not look for the *content* of internal documents -- only for the shapes
that give them away: their vocabulary, their staff-role prefixes, their entry
numbering. A leak written in fresh prose with none of those markers still needs a
human. Pretending otherwise would make this test an alibi rather than a check.

Scope
-----
`git ls-files` only -- the same surface the isolation rule defines. Untracked and
ignored paths cannot reach a reader, and scanning them would drown the signal in
editor caches and build output.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path
from typing import Dict, Iterable, List, Tuple

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]

#: 豁免的唯一形式：被这两行哨兵**恰好夹住**的区域，且仅限本文件。
#: 用哨兵而不是硬编码行号 —— 行号会随编辑漂移，漂移后的豁免会盖住别人。
EXEMPT_BEGIN = "# --- pattern table begin: exempt from this scan ---"
EXEMPT_END = "# --- pattern table end ---"

#: 允许出现哨兵的文件，只此一个。
EXEMPT_FILE = "tests/regression/test_no_internal_identifiers.py"

# --- pattern table begin: exempt from this scan ---
# 这一段必须写下禁用的形状本身，否则无从匹配；它是全仓库唯一允许写它们的地方。
PATTERNS: Dict[str, str] = {
    # 内部载体与流程名。中文词表比英文更可靠：这些词在本项目之外几乎不会自然出现。
    "internal-vocabulary": (
        r"知识库|Obsidian|OneDrive|cullinan-vault|五方面同步|每轮必过门"
        r"|隔离门|推后裁定|僵尸六形态|留痕式变更|收口单|知识库治理"
    ),
    # 岗位缩写 + 分隔符。单独一个岗位词是日常用语，加分隔符才是台账指纹。
    "role-prefix": r"\b(ORCH|INSPECTOR|STRAT|KNOWLEDGE|DESIGN)\s*[#:]|\b(ARCH|QA|PM|KB)\s*#",
    # 带强前缀的台账编号。只用两位以上字母的前缀，避免单字母加短数字的普通写法。
    "ledger-id": r"\b(KN|EV|ISO)-\d{1,4}\b",
    # 单字母编号。**必须含 1 位**：实测过的泄漏里有 1 位数的，而 `\d{2,4}` 会把它
    # 放过去 —— 门槛写成"看起来更严"的样子反而漏检。放宽到 1 位在 489 个已追踪
    # 文件上命中 0 行，故无假阳性代价。
    "single-letter-id": r"\b(K|R|D|S|G|Z|W|F)-\d{1,4}\b",
}
# --- pattern table end ---

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
    """→ [(path, lineno, pattern_name, line)]。

    跳过规则只有一条：当 `path` 是 `EXEMPT_FILE` 时，哨兵区间内的行不扫。
    其它文件**没有豁免**，包括本测试的兄弟文件。
    """
    hits: List[Tuple[str, int, str, str]] = []
    for path, text in texts.items():
        exempting = False
        for lineno, line in enumerate(text.splitlines(), 1):
            if path == EXEMPT_FILE:
                if line.strip() == EXEMPT_BEGIN:
                    exempting = True
                    continue
                if line.strip() == EXEMPT_END:
                    exempting = False
                    continue
                if exempting:
                    continue
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


#: 违例样本在导入时拼装。源码里不出现任何一条完整的禁用形状，
#: 否则本文件会成为它自己要抓的第一个对象（第一版就栽在这里）。
_A = "K"       # 单字母台账前缀
_B = "ARCH"    # 岗位词
_C = "ISO"     # 双字母以上前缀
_V = "知识" + "库" + "治理"   # 内部载体名，拆三段拼


def _fabricated_violations() -> Dict[str, str]:
    return {
        "fake/comment.py": f"# see {_A}-78 for the reason\n",
        "fake/role.py": f"# owner: {_B}#3\n",
        "fake/prose.md": f"详见{_V}下的那份件\n",
        "fake/ledger.py": f"# {_C}-104 is the precedent\n",
        "fake/clean.py": "# this line carries nothing internal\n",
    }


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
            f"Fix the line. Do not widen the exemption: the only bracketed region "
            f"in {EXEMPT_FILE} exists so that the pattern table can spell out what "
            f"it forbids."
        )


def test_the_scanner_can_actually_fail():
    """证明上一条不是永远绿。

    没有这一条，一个写错的正则会让主测试变成「永远通过」，而它的名字会让人
    以为已经查过了。样本来自 `_fabricated_violations()`，运行时拼接。
    """
    hits = scan_texts(_fabricated_violations())
    found = {p for p, _, _, _ in hits}
    expected = {"fake/comment.py", "fake/role.py", "fake/prose.md", "fake/ledger.py"}

    missing = expected - found
    assert not missing, f"scanner missed fabricated violations in: {sorted(missing)}"
    assert "fake/clean.py" not in found, (
        "scanner flagged a clean line; a false positive here will get the whole "
        "test disabled rather than fixed"
    )


def test_exemption_is_one_bracketed_region():
    """豁免必须**恰好**是一个哨兵区间，且在唯一允许的文件里。

    这条不是洁癖：豁免每扩大一次，就等于有人决定「这个公开文件可以点名内部件」。
    那种决定应当是一次显式的评审，而不是顺手加一个文件名 —— 第一版就是整文件
    自豁免，于是本文件里的真实编号永久免检。
    """
    text = (REPO_ROOT / EXEMPT_FILE).read_text(encoding="utf-8")
    begins = [ln for ln in text.splitlines() if ln.strip() == EXEMPT_BEGIN]
    ends = [ln for ln in text.splitlines() if ln.strip() == EXEMPT_END]

    assert len(begins) == 1 and len(ends) == 1, (
        f"expected exactly one bracketed region in {EXEMPT_FILE}, "
        f"found {len(begins)} begin / {len(ends)} end"
    )
    assert text.index(begins[0]) < text.index(ends[0]), "end sentinel precedes begin"

    # 区间之外，本文件也不得出现禁用形状 —— 这条正是第一版缺的。
    # 复用 `scan_texts` 而不是另写一遍字符串切分：第一版在这里手写了
    # `text.split(EXEMPT_BEGIN)`，结果被文件顶部那条**常量定义**（它本身就含
    # 哨兵字面量）抢先匹配，区间内的词表反而被算成"区间外"，测试自己红。
    # 同一逻辑写两遍，两份必然分叉 —— 所以这里只留一份。
    leaked = scan_texts({EXEMPT_FILE: text})
    assert not leaked, (
        "this file carries internal shapes outside the bracketed pattern table:\n"
        + "\n".join(f"  {p}:{n} [{k}] {ln}" for p, n, k, ln in leaked)
    )
