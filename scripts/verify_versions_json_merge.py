"""
本地模拟验证 versions.json 合并式更新机制。

覆盖:
  1. stable 部署不覆盖 pre 字段
  2. pre 部署不覆盖 stable 字段
  3. stable 再次部署更新本通道、保留对方
  4. 同通道重发幂等性
退出码 0 = 全部通过
"""
import json, os, sys, tempfile, pathlib, shutil
from datetime import datetime, timezone

MERGE_SCRIPT = """
import json, os, pathlib
from datetime import datetime, timezone
versions_file = pathlib.Path(".gh-pages/versions.json")
existing = {}
if versions_file.exists():
    try:
        existing = json.loads(versions_file.read_text(encoding="utf-8"))
    except Exception:
        existing = {}
channel = os.environ.get("CHANNEL", "")
stable_version = os.environ.get("STABLE_VERSION", "")
pre_version = os.environ.get("PRE_VERSION", "")
stable_entry = existing.get("stable", {})
pre_entry = existing.get("pre", {})
if channel == "stable":
    stable_entry = {"version": stable_version, "path": "/"}
elif channel == "pre":
    pre_entry = {"version": pre_version, "path": "/pre/"}
payload = {"stable": stable_entry, "pre": pre_entry, "updated_at": datetime.now(timezone.utc).isoformat()}
versions_file.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\\n", encoding="utf-8")
pathlib.Path(".gh-pages/.nojekyll").write_text("", encoding="utf-8")
"""


def run_merge(gh_pages_dir, channel, stable_v="", pre_v=""):
    env = dict(os.environ)
    env["CHANNEL"] = channel
    env["STABLE_VERSION"] = stable_v
    env["PRE_VERSION"] = pre_v
    cwd = gh_pages_dir.parent
    script_path = cwd / "_merge.py"
    script_path.write_text(MERGE_SCRIPT, encoding="utf-8")
    import subprocess
    r = subprocess.run([sys.executable, str(script_path)], cwd=str(cwd), env=env,
                       capture_output=True, text=True)
    script_path.unlink(missing_ok=True)
    if r.returncode != 0:
        print("STDERR:", r.stderr)
    return r.returncode


def load_versions(gh_pages_dir):
    f = gh_pages_dir / "versions.json"
    return json.loads(f.read_text(encoding="utf-8")) if f.exists() else {}


def check(actual, expected, label, fails):
    if actual != expected:
        print(f"FAIL {label}: expected {expected!r}, got {actual!r}")
        fails.append(label)
        return
    print(f"PASS {label}")


def main():
    tmp = pathlib.Path(tempfile.mkdtemp(prefix="versions_json_"))
    gh = tmp / ".gh-pages"
    gh.mkdir()
    fails = []

    run_merge(gh, "stable", stable_v="0.94")
    v = load_versions(gh)
    check(v.get("stable", {}).get("version"), "0.94", "1. stable deploy sets stable field", fails)
    check(v.get("pre", {}).get("version"), None, "2. stable deploy leaves pre field empty", fails)

    run_merge(gh, "pre", pre_v="0.95a1")
    v = load_versions(gh)
    check(v.get("pre", {}).get("version"), "0.95a1", "3. pre deploy sets pre field", fails)
    check(v.get("stable", {}).get("version"), "0.94", "4. pre deploy preserves stable field", fails)

    run_merge(gh, "stable", stable_v="0.94.1")
    v = load_versions(gh)
    check(v.get("stable", {}).get("version"), "0.94.1", "5. stable redeploy updates stable field", fails)
    check(v.get("pre", {}).get("version"), "0.95a1", "6. stable redeploy preserves pre field", fails)

    run_merge(gh, "stable", stable_v="0.94.1")
    v = load_versions(gh)
    check(v.get("pre", {}).get("version"), "0.95a1", "7. stable idempotent redeploy preserves pre field", fails)

    shutil.rmtree(tmp, ignore_errors=True)
    print(f"\n{'ALL PASS' if not fails else f'{len(fails)} FAILURES: {fails}'}")
    return 0 if not fails else 1


if __name__ == "__main__":
    sys.exit(main())
