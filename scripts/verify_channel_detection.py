"""
模拟 mkdocs-build.yml 的通道判定逻辑，验证 force_channel 与 feat 分支场景。

S4 (v0.95a1): origin/preview 为 pre 通道唯一权威来源。release/v0.93-pre
转为只读归档，不再触发 pre 通道部署。preview 分支名优先于版本号 'a' 判定。
"""
import sys
from packaging.version import Version


def detect_channel(branch, version, default_branch="master", event_name="push",
                   is_tag_ref=False, force_channel="skip"):
    if force_channel in ("stable", "pre"):
        channel = force_channel
        should_deploy = event_name in {"push", "workflow_dispatch"} and not is_tag_ref
        return channel, should_deploy
    is_pre = "a" in version
    is_default = branch == default_branch
    # S4 (v0.95a1): preview 分支 -> pre 通道（分支名优先，不依赖版本号 'a'）
    is_preview_branch = branch == "preview"
    if is_default and not is_pre:
        channel = "stable"
    elif is_preview_branch:
        channel = "pre"
    elif (not is_default) and is_pre and not branch.startswith("release/"):
        channel = "pre"
    else:
        channel = "skip"
    should_deploy = (event_name in {"push", "workflow_dispatch"}
                     and channel in {"stable", "pre"} and not is_tag_ref)
    return channel, should_deploy


def check(actual, expected, label, fails):
    if actual != expected:
        print(f"FAIL {label}: expected {expected!r}, got {actual!r}")
        fails.append(label)
        return
    print(f"PASS {label}")


def main():
    fails = []
    # --- 原有用例（保留，确保不回归） ---
    check(detect_channel("master", "0.94"), ("stable", True),
          "1. master + non-alpha -> stable", fails)
    # 2. release/v0.93-pre 现在不再触发 pre（S4: 只读归档）
    check(detect_channel("release/v0.93-pre", "0.93a13"), ("skip", False),
          "2. release branch + alpha -> skip (S4 archive)", fails)
    check(detect_channel("feat/v0.94", "0.94a3"), ("pre", True),
          "3. feat branch + alpha -> pre", fails)
    check(detect_channel("master", "0.94a3"), ("skip", False),
          "4. master + alpha -> skip", fails)
    check(detect_channel("feat/v0.94", "0.94"), ("skip", False),
          "5. feat branch + non-alpha -> skip", fails)
    check(detect_channel("release/v0.93-pre", "0.93a13", force_channel="pre"),
          ("pre", True), "6. force_channel=pre overrides", fails)
    check(detect_channel("master", "0.94", force_channel="stable"),
          ("stable", True), "7. force_channel=stable overrides", fails)
    check(detect_channel("master", "0.94", event_name="pull_request"),
          ("stable", False), "8. PR does not deploy", fails)
    check(detect_channel("release/v0.93-pre", "0.93a13", is_tag_ref=True),
          ("skip", False), "9. tag ref does not deploy (S4 archive)", fails)

    # --- S4 (v0.95a1) 新增用例 ---
    # 10. preview 分支 + alpha 版本 -> pre（基本场景）
    check(detect_channel("preview", "0.95a1"), ("pre", True),
          "10. preview branch + alpha -> pre", fails)
    # 11. preview 分支 + 正式版本 -> pre（分支名优先，不依赖 'a'）
    check(detect_channel("preview", "0.95"), ("pre", True),
          "11. preview branch + non-alpha -> pre (branch-name priority)", fails)
    # 12. preview 分支 + tag -> pre 通道但不部署
    check(detect_channel("preview", "0.95a1", is_tag_ref=True),
          ("pre", False), "12. preview branch + tag ref -> pre, no deploy", fails)
    # 13. preview 分支 + PR -> pre 通道但不部署
    check(detect_channel("preview", "0.95a1", event_name="pull_request"),
          ("pre", False), "13. preview branch + PR -> pre, no deploy", fails)
    # 14. release/v0.93-pre + 正式版本 -> skip（release/** 全部不触发）
    check(detect_channel("release/v0.93-pre", "0.93"), ("skip", False),
          "14. release branch + non-alpha -> skip (S4 archive)", fails)
    # 15. feat 分支 + alpha -> pre（feat 通道保持不变）
    check(detect_channel("feat/v0.94", "0.95a1"), ("pre", True),
          "15. feat branch + alpha -> pre (unchanged)", fails)

    total = 15
    print(f"\n{total - len(fails)}/{total} PASS")
    return 0 if not fails else 1


if __name__ == "__main__":
    sys.exit(main())
