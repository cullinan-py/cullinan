#!/usr/bin/env python3
"""Coverage gate: run the suite under `coverage` and fail below the floor.

What this is, and what it is not
--------------------------------
This is **not** a new gate. The gate has existed all along: `pyproject.toml`
carries `[tool.coverage.report] fail_under = 70`, and `ci.yml` has a
`coverage gate` job that runs `coverage run` then `coverage report` (which reads
that floor and exits non-zero when missed).

What was missing is the **local** half. The eight-gate checklist lists gate ① as
`pytest tests -q`, which produces no coverage figure at all, so the floor was
enforced on CI and measured nowhere else. For a while this was even read as
"`pytest-cov` is not installed, therefore the threshold has never been
measured" -- wrong on both counts: the tool is `coverage` (already pinned in
`requirements-dev.txt`), and it *was* being measured, just not on this machine.

So this file exists to make the CI door openable with one local command, and to
**read the floor from the same single source** (`pyproject.toml`) instead of
carrying a second copy of the number. A duplicated threshold is the exact defect
`S-18` describes: two master copies, and nobody can tell which one bound.

Usage
-----
    python scripts/check_coverage.py                 # run suite, gate at pyproject floor
    python scripts/check_coverage.py --min 72        # deliberate override (records both numbers)
    python scripts/check_coverage.py --report-only   # reuse existing .coverage
    python scripts/check_coverage.py --self-test     # prove the gate can fail

Exit codes
----------
0 = coverage measured and >= floor
1 = coverage measured and below floor
2 = could not measure (no `.coverage`, missing package, suite error) -- never
    reported as a pass; an unmeasurable gate is an absent gate.
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

DEFAULT_MIN = 70.0  #: 仅在 `pyproject.toml` 里读不到 `fail_under` 时使用的兜底
SOURCE = "cullinan"


def floor_from_pyproject(root: Path) -> tuple[float | None, str]:
    """读 `[tool.coverage.report] fail_under`。返回 `(值, 来源说明)`。

    优先 `tomllib`；解析不了（老 Python / 文件损坏）退回逐行正则，并在来源里
    标明用了哪种方式 —— 因为「读到了 70」和「读不到时默认 70」是两件事，
    后者必须能被看见，否则改了 pyproject 而门照旧跑 70 会被当成"门没生效"。
    """
    path = root / "pyproject.toml"
    if not path.is_file():
        return None, f"{path} 不存在"
    try:
        import tomllib  # type: ignore[import-not-found]
    except ModuleNotFoundError:
        tomllib = None  # type: ignore[assignment]

    if tomllib is not None:
        try:
            data = tomllib.loads(path.read_text(encoding="utf-8"))
            val = data.get("tool", {}).get("coverage", {}).get("report", {}).get("fail_under")
            if isinstance(val, (int, float)):
                return float(val), f"{path.name} [tool.coverage.report] fail_under（tomllib）"
        except (ValueError, OSError) as exc:
            return None, f"{path.name} 解析失败：{exc}"

    # 兜底：只在 `[tool.coverage.report]` 段内找 `fail_under`
    in_section = False
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if stripped.startswith("["):
            in_section = stripped == "[tool.coverage.report]"
            continue
        if in_section and stripped.startswith("fail_under"):
            _, _, raw = stripped.partition("=")
            try:
                return float(raw.strip()), f"{path.name} [tool.coverage.report] fail_under（regex fallback）"
            except ValueError:
                return None, f"{path.name} fail_under 值不可解析：{raw!r}"
    return None, f"{path.name} 里没有 [tool.coverage.report] fail_under"


def _run(cmd: list[str], cwd: Path, env: dict[str, str] | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(
        cmd, cwd=str(cwd), capture_output=True, text=True, encoding="utf-8", errors="replace", env=env
    )


def _total_pct(report_stdout: str) -> float | None:
    """Pull TOTAL percentage out of `coverage report`.

    Deliberately parses the TOTAL line rather than the fail-under exit code
    alone: the number has to be printed for the record, otherwise the gate
    answers "did it pass" but not "what was it", and the next round cannot tell
    a rise from a fall.
    """
    for line in report_stdout.splitlines():
        if line.strip().startswith("TOTAL"):
            parts = line.split()
            for tok in reversed(parts):
                if tok.endswith("%"):
                    try:
                        return float(tok.rstrip("%"))
                    except ValueError:
                        return None
    return None


def measure(cwd: Path, source: str) -> tuple[int, str]:
    """Run the suite under coverage in `cwd`. Returns (exit code, combined output)."""
    proc = _run([sys.executable, "-m", "coverage", "run", f"--source={source}", "-m", "pytest", "tests", "-q"], cwd)
    return proc.returncode, (proc.stdout or "") + (proc.stderr or "")


def report(cwd: Path) -> tuple[int, str]:
    proc = _run([sys.executable, "-m", "coverage", "report"], cwd)
    return proc.returncode, (proc.stdout or "") + (proc.stderr or "")


def self_test() -> int:
    """Build a tiny package whose coverage is known, then prove both directions.

    A gate that has never gone red is indistinguishable from a gate that cannot
    go red. This runs the same code path three ways: full coverage above a low
    threshold (green), full coverage below an impossible threshold (red), and
    partial coverage below a mid threshold (red for the right reason).
    """
    failures: list[str] = []
    tmp = Path(tempfile.mkdtemp(prefix="covgate-"))
    try:
        pkg = tmp / "demo"
        pkg.mkdir()
        (pkg / "__init__.py").write_text("", encoding="utf-8")
        (pkg / "m.py").write_text(
            "def covered(x):\n    return x + 1\n\n\ndef untouched(x):\n    return x - 1\n",
            encoding="utf-8",
        )
        (tmp / "tests").mkdir()
        (tmp / "tests" / "test_m.py").write_text(
            "from demo.m import covered\n\n\ndef test_covered():\n    assert covered(1) == 2\n",
            encoding="utf-8",
        )
        env = dict(os.environ)
        env["PYTHONPATH"] = str(tmp)

        # ① run the suite under coverage
        proc = _run(
            [sys.executable, "-m", "coverage", "run", "--source=demo", "-m", "pytest", "tests", "-q"],
            tmp,
            env=env,
        )
        if proc.returncode != 0:
            failures.append(f"① 自测用例本身没跑通：{(proc.stdout or '')[-200:]}")

        # ② report must yield a number
        rc, out = report(tmp)
        pct = _total_pct(out)
        if pct is None:
            failures.append(f"② 解析不出 TOTAL 百分比：{out[-200:]}")
        else:
            # 只调了 covered，untouched 未被执行 ⇒ 覆盖率必须 < 100
            if pct >= 100.0:
                failures.append(f"② 部分覆盖时算出 {pct}%（应 < 100%）⇒ 解析或采集有问题")

        # ③ 阈值 0 ⇒ 必须绿；阈值 100 ⇒ 必须红
        if pct is not None:
            low = _run([sys.executable, "-m", "coverage", "report", "--fail-under=0"], tmp)
            high = _run([sys.executable, "-m", "coverage", "report", "--fail-under=100"], tmp)
            if low.returncode != 0:
                failures.append("③ 阈值 0 仍失败 ⇒ 门会永远红")
            if high.returncode == 0:
                failures.append("③ 阈值 100 仍通过 ⇒ 门永远绿（fail-under 未生效）")

        # ④ floor 必须从 pyproject 读，且读不到时要**说出来**（不能静默用默认值）
        (tmp / "pyproject.toml").write_text(
            "[tool.coverage.report]\nfail_under = 42\n", encoding="utf-8"
        )
        val, src = floor_from_pyproject(tmp)
        if val != 42.0:
            failures.append(f"④ pyproject 里的 fail_under=42 未读到：{val}（{src}）")

        (tmp / "pyproject.toml").write_text("[tool.coverage.run]\nsource = ['x']\n", encoding="utf-8")
        val2, src2 = floor_from_pyproject(tmp)
        if val2 is not None:
            failures.append(f"④ 无 fail_under 时不该给出数值：{val2}（{src2}）")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    for f in failures:
        print(f"  ❌ {f}")
    print(
        "  == 自测：all ok（能取数 / 阈值 0 绿 / 阈值 100 红 / 部分覆盖被识别 / floor 从 pyproject 读）=="
        if not failures
        else "  == 自测：FAIL =="
    )
    return 1 if failures else 0


def main() -> int:
    ap = argparse.ArgumentParser(description="coverage gate for the cullinan package")
    ap.add_argument(
        "--min",
        type=float,
        default=None,
        help=f"覆盖 pyproject.toml 里的 floor（缺省读该处；读不到才用 {DEFAULT_MIN}）",
    )
    ap.add_argument("--source", default=SOURCE)
    ap.add_argument("--cwd", default=str(Path(__file__).resolve().parent.parent))
    ap.add_argument("--report-only", action="store_true", help="reuse the .coverage already on disk (no re-run)")
    ap.add_argument("--self-test", action="store_true")
    args = ap.parse_args()

    if args.self_test:
        return self_test()

    cwd = Path(args.cwd)

    # floor 的唯一真值在 pyproject.toml；`--min` 是显式覆盖，必须把两个数都打印出来
    pyproject_floor, source = floor_from_pyproject(cwd)
    if args.min is not None:
        threshold = args.min
        if pyproject_floor is None:
            source = f"显式 --min（{source}）"
            print(f"[warn] 未从 pyproject 读到 floor，使用 --min {args.min}", file=sys.stderr)
        else:
            source = f"显式 --min {args.min:g}（覆盖 pyproject 的 {pyproject_floor:g}）"
            if abs(pyproject_floor - args.min) > 1e-9:
                print(
                    f"[warn] --min {args.min:g} 覆盖了 pyproject floor {pyproject_floor:g}；本次判定以 {args.min:g} 为准",
                    file=sys.stderr,
                )
    elif pyproject_floor is not None:
        threshold = pyproject_floor
    else:
        threshold = DEFAULT_MIN
        print(f"[warn] {source} ⇒ 回退到内置默认 {DEFAULT_MIN}（这不是 pyproject 的值）", file=sys.stderr)

    if not args.report_only:
        rc, out = measure(cwd, args.source)
        tail = " / ".join(ln for ln in out.strip().splitlines()[-2:])
        if rc != 0:
            print(f"[RED] 测试未通过，覆盖率无意义：{tail}", file=sys.stderr)
            return 2
        print(f"[run] {tail}")

    rc, out = report(cwd)
    pct = _total_pct(out)
    if pct is None:
        print(f"[RED] 取不到覆盖率（.coverage 不存在或 coverage 未安装）：{out[-300:]}", file=sys.stderr)
        return 2

    total_line = next((ln for ln in out.splitlines() if ln.strip().startswith("TOTAL")), "")
    print(f"[report] {total_line.strip()}")
    print(f"[floor] {threshold:g}%（来源：{source}）")

    if pct >= threshold:
        print(f"[GREEN] 覆盖率 {pct:.2f}% >= {threshold:g}%（余量 {pct - threshold:.2f}pp）")
        return 0

    print(f"[RED] 覆盖率 {pct:.2f}% < {threshold:g}%（差 {threshold - pct:.2f}pp）", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
