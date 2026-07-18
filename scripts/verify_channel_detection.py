"""
模拟 mkdocs-build.yml 的通道判定逻辑，验证 force_channel 与 feat 分支场景。
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
    if is_default and not is_pre:
        channel = "stable"
    elif (not is_default) and is_pre:
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
    check(detect_channel("master", "0.94"), ("stable", True),
          "1. master + non-alpha -> stable", fails)
    check(detect_channel("release/v0.93-pre", "0.93a13"), ("pre", True),
          "2. release branch + alpha -> pre", fails)
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
          ("pre", False), "9. tag ref does not deploy", fails)
    print(f"\n{9 - len(fails)}/9 PASS")
    return 0 if not fails else 1


if __name__ == "__main__":
    sys.exit(main())
