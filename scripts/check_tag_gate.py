"""
打 tag 前的手动门禁校验脚本（版本规范 S6，v0.95a1 修进降级项，v0.95 兑现）。

git 原生无 pre-tag hook，本脚本将「命令骨架第 5 步 (a)(b)(c) 确认」机械化：
  (a) QA 签收消息 ID 已提供且非空（thread 证据）
  (b) review 门禁消息 ID 已提供且非空（thread 证据）
  (c) 五方面同步达标（本地可验证部分）：
      - 版本号 SSOT 对齐（cullinan.__version__ 与 cullinan.core.__version__ 一致）
      - Release Notes 就位（根目录 RELEASE-v{version}.md）
      - README "Current series" 指向当前版本
      - 工作树 clean（tag 须指向已提交状态）

用法：
  python scripts/check_tag_gate.py --qa-msg <MSG_ID> --review-msg <MSG_ID> [--version 0.95]

退出码：0 = PASS（方可执行 git tag），1 = FAIL（阻断）。
"""
import argparse
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def read_ssot_version():
    text = (ROOT / "cullinan" / "_version.py").read_text(encoding="utf-8")
    match = re.search(r'__version__\s*=\s*"([^"]+)"', text)
    if not match:
        return None
    return match.group(1)


def main():
    parser = argparse.ArgumentParser(description="Pre-tag gate verification (spec S6)")
    parser.add_argument("--qa-msg", required=True,
                        help="(a) QA sign-off message ID in the release thread")
    parser.add_argument("--review-msg", required=True,
                        help="(b) Review gate completion message ID in the release thread")
    parser.add_argument("--version", default=None,
                        help="Expected version (default: read from cullinan/_version.py)")
    args = parser.parse_args()

    fails = []

    def check(label, ok, detail=""):
        status = "PASS" if ok else "FAIL"
        suffix = f" -- {detail}" if detail else ""
        print(f"{status} {label}{suffix}")
        if not ok:
            fails.append(label)

    # (a) QA 签收证据
    check("(a) QA sign-off message ID provided", bool(args.qa_msg.strip()),
          args.qa_msg.strip() or "empty")

    # (b) review 门禁证据
    check("(b) Review gate message ID provided", bool(args.review_msg.strip()),
          args.review_msg.strip() or "empty")

    # (c) 五方面同步（本地可验证部分）
    ssot = read_ssot_version()
    expected = args.version or ssot
    check("Version SSOT readable (cullinan/_version.py)", ssot is not None)
    check("Expected version matches SSOT", expected == ssot,
          f"expected={expected} ssot={ssot}")

    if expected:
        notes = ROOT / f"RELEASE-v{expected}.md"
        check(f"Release notes present ({notes.name})", notes.exists())

        readme = (ROOT / "README.MD").read_text(encoding="utf-8")
        check("README Current series aligned", f"**v{expected}**" in readme)

    try:
        sys.path.insert(0, str(ROOT))
        import cullinan
        from cullinan import core
        check("Import smoke + runtime version aligned",
              cullinan.__version__ == expected == core.__version__,
              f"cullinan={cullinan.__version__} core={core.__version__}")
    except Exception as exc:  # noqa: BLE001 - gate must fail, not crash
        check("Import smoke + runtime version aligned", False, repr(exc))

    status = subprocess.run(
        ["git", "-C", str(ROOT), "status", "--porcelain"],
        capture_output=True, text=True, check=True,
    ).stdout.strip()
    check("Working tree clean", status == "", status or "clean")

    print()
    if fails:
        print(f"TAG GATE FAIL ({len(fails)} check(s) failed) -- do NOT run git tag")
        return 1
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    print(f"TAG GATE PASS -- version {expected} @ {stamp}")
    print(f"  (a) QA sign-off message : {args.qa_msg.strip()}")
    print(f"  (b) Review gate message : {args.review_msg.strip()}")
    print("  (c) Five-aspect sync    : SSOT aligned / release notes / README / clean tree")
    return 0


if __name__ == "__main__":
    sys.exit(main())
