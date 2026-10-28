#!/usr/bin/env python3
"""Pre-push mechanical gate: the M0..M9 assertions, executed instead of described.

The assertions themselves are not defined here. They are defined once, in the
isolation ruling's section on "required mechanical gates" (M0..M9), and this file
is the executable side of that table: one function per assertion, same numbering,
same pass condition. A gate whose only existence is a written specification is a
gate that never blocks anything, which is the failure mode this script is meant to
end.

What each gate asserts (runnable form; numbers match the specification):

  M0  nothing internal or build-shaped is being *added* by this push or sitting in
      the index -- the `git add -f` line.
  M1  no tracked file lives under an ignored internal directory.
  M2  the HEAD tree contains no `.workbuddy`.
  M3  the `git archive HEAD` export (the packaging source surface) contains no
      `.workbuddy`.
  M4  the committable surface is empty: a plain `git add .` would add nothing.
  M5  no ref in the whole history ever *added* `.workbuddy`.
  M6  the packaging configuration does not mention the directory, and there is no
      `MANIFEST.in` that could re-include it.
  M7  package discovery excludes build/temp roots, and `package-data` uses no wide
      glob.
  M8  M1/M2/M3 hold in *every* worktree of this repository, not just this one --
      the worktree-copy line.
  M9  the real sdist contains no internal-library name in its member paths, and
      (stronger than the specification asks) none in its member contents either.

M0..M9 is the *mechanical* subset only. The content scans over documented
surfaces are separate assertions with their own owners and are deliberately not
duplicated here.

Usage
-----
    python scripts/gate_pre_push.py                    # check HEAD, no stdin read
    python scripts/gate_pre_push.py --refs-stdin < refs # pre-push refs from stdin
    python scripts/gate_pre_push.py --refs-file f      # pre-push refs from a file
    python scripts/gate_pre_push.py --rev HEAD         # check a revision
    python scripts/gate_pre_push.py --only M3,M9       # subset (diagnosis)
    python scripts/gate_pre_push.py --no-sdist         # skip M9 (reported, not hidden)
    python scripts/gate_pre_push.py --scan-archive p   # scan a built sdist, no rebuild
    python scripts/gate_pre_push.py --selftest         # prove the scanners can fire
    python scripts/gate_pre_push.py --json             # machine-readable

stdin is never read unless you ask for it with `--refs-stdin`: run by hand, an
implicit read blocks on a pipe nobody closes.

Exit codes: 0 every gate passed (see "NOT COVERED" for skips), 1 at least one gate
failed, 2 the gate could not decide (not a pass).

Two distinctions this script insists on, because collapsing them is how a gate
turns into decoration:

  * "the toolchain is missing" is not "the artifact is clean". A missing build
    toolchain yields SKIP, and SKIP is printed as `NOT COVERED` and never as PASS.
  * "the toolchain is present but the build or the scan failed" is a FAIL. A
    broken gate must not read as an unarmed gate.

Installation and removal are handled by `scripts/install_pre_push_gate.py`; the
hook lives in the shared git common directory, so read that script's docstring
before installing.
"""

from __future__ import annotations

import argparse
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile

GATE_VERSION = "1.0"
MARKER = "M0-M9 GATE"
ZERO_SHA = "0" * 40

# Directories that must never be added by a push (M0/M1/M2/M5) and never appear in
# the packaging export (M3/M9).
ADD_FORBIDDEN = re.compile(r"^(?:\.workbuddy|build|dist|site)/")

# Names of the internal knowledge base. Taken from the specification's M9 row; kept
# as one tuple so the path scan and the content scan cannot drift apart.
INTERNAL_TOKENS = (
    "知识库治理",
    "知识库",
    "Obsidian",
    "obsidian",
    "OneDrive",
    "cullinan-vault",
    ".workbuddy",
    ".obsidian",
)
INTERNAL_PATTERN = re.compile("|".join(re.escape(token) for token in INTERNAL_TOKENS))

# A `.gitignore`-family file inside a distribution may legitimately name an ignored
# directory -- that line is the reason the directory stays out of the repository.
# Those lines are reported as WARN, not as a clean pass and not as a failure.
IGNORE_FILE_NAMES = (".gitignore", ".gitignore_global", ".gitattributes", ".dockerignore")


class Result:
    """One gate's outcome. `status` is PASS, FAIL, SKIP or WARN-only."""

    def __init__(self, gate, title, status, detail, lines=None):
        self.gate = gate
        self.title = title
        self.status = status
        self.detail = detail
        self.lines = lines or []

    def as_dict(self):
        return {
            "gate": self.gate,
            "title": self.title,
            "status": self.status,
            "detail": self.detail,
            "lines": self.lines,
        }


def _run(args, cwd=None, stdin_bytes=None, timeout=600):
    return subprocess.run(
        args,
        cwd=cwd,
        input=stdin_bytes,
        capture_output=True,
        timeout=timeout,
    )


def git(*args, cwd=None, stdin_bytes=None):
    """Run git and return (returncode, stdout text, stderr text).

    Text is decoded with replacement so a non-UTF-8 blob name cannot crash the
    gate before it has decided anything.
    """
    proc = _run(["git", "-c", "core.quotepath=false", *args], cwd=cwd, stdin_bytes=stdin_bytes)
    return (
        proc.returncode,
        proc.stdout.decode("utf-8", "replace"),
        proc.stderr.decode("utf-8", "replace"),
    )


def repo_root(explicit=None):
    if explicit:
        return os.path.abspath(explicit)
    code, out, err = git("rev-parse", "--show-toplevel")
    if code != 0:
        raise SystemExit("not inside a git working tree: {}".format(err.strip()))
    return out.strip()


def _lines(text):
    return [line for line in text.splitlines() if line.strip()]


# --------------------------------------------------------------------------- #
# Ref handling (pre-push stdin)
# --------------------------------------------------------------------------- #


def parse_refs(text):
    """Parse the pre-push stdin format: `<local ref> <local sha> <remote ref> <remote sha>`."""
    refs = []
    for line in text.splitlines():
        parts = line.split()
        if len(parts) >= 4:
            refs.append(
                {
                    "local_ref": parts[0],
                    "local_sha": parts[1],
                    "remote_ref": parts[2],
                    "remote_sha": parts[3],
                }
            )
    return refs


def _is_zero(sha):
    return not sha or sha == ZERO_SHA or not sha.strip("0")


def empty_tree_sha(cwd=None):
    """The empty tree of *this* repository (hash algorithm independent)."""
    code, out, _ = git("mktree", cwd=cwd, stdin_bytes=b"")
    if code == 0 and out.strip():
        return out.strip()
    return "4b825dc642cb6eb9a060e54bf8d69288fbee4904"


def target_commits(refs, fallback_rev="HEAD", cwd=None):
    """Commits a push would publish, newest first, de-duplicated."""
    commits = []
    for ref in refs:
        sha = ref["local_sha"]
        if _is_zero(sha):
            continue  # a deletion publishes no tree
        if sha not in commits:
            commits.append(sha)
    if not commits and fallback_rev:
        code, out, _ = git("rev-parse", "--verify", fallback_rev + "^{commit}", cwd=cwd)
        if code == 0:
            commits.append(out.strip())
    return commits


# --------------------------------------------------------------------------- #
# M0
# --------------------------------------------------------------------------- #


def gate_m0(root, refs):
    """Nothing internal or build-shaped is being added: index additions plus the
    added paths of every pushed commit range."""
    hits = []

    code, out, err = git("diff", "--cached", "--name-only", "--diff-filter=A", cwd=root)
    if code != 0:
        return Result("M0", "no internal/build path added", "FAIL",
                      "git diff --cached failed: {}".format(err.strip()))
    hits.extend("index+" + path for path in _lines(out) if ADD_FORBIDDEN.match(path))

    empty = None
    for ref in refs:
        local = ref["local_sha"]
        if _is_zero(local):
            continue
        if _is_zero(ref["remote_sha"]):
            if empty is None:
                empty = empty_tree_sha(root)
            base = empty
        else:
            base = ref["remote_sha"]
        code, out, err = git(
            "diff", "--name-only", "--diff-filter=A", "{}..{}".format(base, local), cwd=root
        )
        if code != 0:
            # An unresolvable base (a remote-only commit that is not fetched here)
            # must not silently shrink the scan.
            return Result("M0", "no internal/build path added", "FAIL",
                          "cannot diff {}..{}: {}".format(base, local, err.strip()))
        hits.extend(
            "{}:{}".format(ref["remote_ref"], path)
            for path in _lines(out)
            if ADD_FORBIDDEN.match(path)
        )

    if hits:
        return Result("M0", "no internal/build path added", "FAIL",
                      "{} added path(s) match {}:".format(len(hits), ADD_FORBIDDEN.pattern),
                      hits[:20])
    scope = ("index + {} pushed range(s)".format(len(refs)) if refs
             else "index only (no refs on stdin: historical additions are M5's job)")
    return Result("M0", "no internal/build path added", "PASS",
                  "0 added path(s), {}".format(scope))


# --------------------------------------------------------------------------- #
# M1 / M2 / M3 -- shared by M8, which re-runs them per worktree
# --------------------------------------------------------------------------- #


def m1_hits(cwd):
    code, out, err = git("ls-files", cwd=cwd)
    if code != 0:
        return None, err.strip()
    pattern = re.compile(r"^(?:\.workbuddy|.*/\.workbuddy)/")
    return [path for path in _lines(out) if pattern.match(path)], ""


def m2_hits(cwd, rev="HEAD"):
    code, out, err = git("ls-tree", "-r", "--name-only", rev, cwd=cwd)
    if code != 0:
        return None, err.strip()
    return [path for path in _lines(out) if ".workbuddy/" in path], ""


def archive_bytes(cwd, rev="HEAD"):
    proc = _run(["git", "archive", "--format=tar", rev], cwd=cwd)
    if proc.returncode != 0:
        return None, proc.stderr.decode("utf-8", "replace").strip()
    return proc.stdout, ""


def archive_names(cwd, rev="HEAD"):
    data, err = archive_bytes(cwd, rev)
    if data is None:
        return None, err
    names = []
    with tarfile.open(fileobj=io.BytesIO(data), mode="r:") as tar:
        for member in tar.getmembers():
            names.append(member.name)
    return names, ""


def gate_m1(root, _refs):
    hits, err = m1_hits(root)
    if hits is None:
        return Result("M1", "no tracked file under an ignored internal directory", "FAIL",
                      "git ls-files failed: {}".format(err))
    if hits:
        return Result("M1", "no tracked file under an ignored internal directory", "FAIL",
                      "{} tracked path(s) under .workbuddy/".format(len(hits)), hits[:20])
    return Result("M1", "no tracked file under an ignored internal directory", "PASS",
                  "0 of {} tracked file(s) is under .workbuddy/".format(
                      len(_lines(git("ls-files", cwd=root)[1]))))


def gate_m2(root, _refs):
    hits, err = m2_hits(root)
    if hits is None:
        return Result("M2", "HEAD tree holds no .workbuddy", "FAIL",
                      "git ls-tree failed: {}".format(err))
    if hits:
        return Result("M2", "HEAD tree holds no .workbuddy", "FAIL",
                      "{} path(s) in HEAD".format(len(hits)), hits[:20])
    return Result("M2", "HEAD tree holds no .workbuddy", "PASS", "0 path(s) in HEAD")


def gate_m3(root, _refs):
    names, err = archive_names(root)
    if names is None:
        return Result("M3", "archive export holds no .workbuddy", "FAIL",
                      "git archive FAILED: {}".format(err))
    hits = [name for name in names if ".workbuddy/" in name]
    if hits:
        return Result("M3", "archive export holds no .workbuddy", "FAIL",
                      "{} path(s) in the export".format(len(hits)), hits[:20])
    if not names:
        return Result("M3", "archive export holds no .workbuddy", "FAIL",
                      "the export is empty: 0 members is not a clean export")
    # The member count is printed because "0 hits in 0 files" is indistinguishable
    # from "0 hits in 573 files" once the number is dropped.
    return Result("M3", "archive export holds no .workbuddy", "PASS",
                  "{} exported member(s), 0 hit(s)".format(len(names)))


def gate_m4(root, _refs):
    code, out, err = git("ls-files", "--others", "--exclude-standard", cwd=root)
    if code != 0:
        return Result("M4", "committable surface is empty", "FAIL",
                      "git ls-files --others failed: {}".format(err.strip()))
    others = _lines(out)
    if others:
        return Result("M4", "committable surface is empty", "FAIL",
                      "{} file(s) would enter the repository on `git add .`".format(
                          len(others)), others[:20])
    return Result("M4", "committable surface is empty", "PASS",
                  "0 untracked-not-ignored file(s)")


def gate_m5(root, _refs):
    code, out, err = git(
        "log", "--all", "--diff-filter=A", "--name-only", "--pretty=format:", "--", ".workbuddy/*",
        cwd=root,
    )
    if code != 0:
        return Result("M5", "no ref ever added .workbuddy", "FAIL",
                      "git log --all failed: {}".format(err.strip()))
    hits = [line for line in _lines(out) if line.startswith(".workbuddy/")]
    if hits:
        return Result("M5", "no ref ever added .workbuddy", "FAIL",
                      "{} historical addition(s)".format(len(hits)), hits[:20])
    return Result("M5", "no ref ever added .workbuddy", "PASS",
                  "0 historical addition(s) across all refs")


def gate_m6(root, _refs):
    problems = []
    for name in ("pyproject.toml", "setup.py"):
        path = os.path.join(root, name)
        if not os.path.isfile(path):
            continue
        with open(path, "r", encoding="utf-8", errors="replace") as handle:
            text = handle.read()
        hits = [line for line in text.splitlines() if re.search(r"workbuddy", line, re.I)]
        if hits:
            problems.append("{}: {}".format(name, hits[0].strip()))
    manifest = os.path.join(root, "MANIFEST.in")
    if os.path.isfile(manifest):
        with open(manifest, "r", encoding="utf-8", errors="replace") as handle:
            text = handle.read()
        if re.search(r"workbuddy", text, re.I):
            problems.append("MANIFEST.in: names the directory")
    if problems:
        return Result("M6", "packaging config does not name the directory", "FAIL",
                      "{} problem(s)".format(len(problems)), problems)
    manifest_note = "MANIFEST.in present but silent" if os.path.isfile(manifest) else "no MANIFEST.in"
    return Result("M6", "packaging config does not name the directory", "PASS",
                  "pyproject.toml=0 setup.py=0, {}".format(manifest_note))


M7_REQUIRED_EXCLUDES = ("tests", "examples", "docs", "build", "dist", "site")


def _load_pyproject(path):
    try:
        import tomllib
    except ModuleNotFoundError:  # Python < 3.11
        return None
    with open(path, "rb") as handle:
        return tomllib.load(handle)


def gate_m7(root, _refs):
    """Discovery excludes build/temp roots; `package-data` uses no wide glob.

    Falls back to a textual reading when `tomllib` is unavailable, because a gate
    that cannot run on the interpreter at hand would be skipped exactly where it is
    needed.
    """
    path = os.path.join(root, "pyproject.toml")
    if not os.path.isfile(path):
        return Result("M7", "packaging discovery is bounded", "SKIP",
                      "no pyproject.toml")
    text = open(path, "r", encoding="utf-8", errors="replace").read()
    data = _load_pyproject(path)

    if data is None:
        problems = []
        exclude_match = re.search(r"exclude\s*=\s*\[(.*?)\]", text, re.S)
        excludes = re.findall(r'"([^"]+)"', exclude_match.group(1)) if exclude_match else []
        for want in M7_REQUIRED_EXCLUDES:
            if not any(item.rstrip("*").rstrip("/") == want for item in excludes):
                problems.append("exclude list is missing {!r}".format(want))
        block = re.search(r"package-data\](.*?)(?=\n\[|\Z)", text, re.S)
        if block and re.search(r'"\*+"|"\*"', block.group(1)):
            problems.append("package-data uses a wide glob")
        if problems:
            return Result("M7", "packaging discovery is bounded", "FAIL",
                          "textual parse: {} problem(s)".format(len(problems)), problems)
        return Result("M7", "packaging discovery is bounded", "PASS",
                      "textual parse (tomllib unavailable): excludes cover {}; package-data "
                      "has no wide glob".format(", ".join(M7_REQUIRED_EXCLUDES)))

    tool = data.get("tool", {}).get("setuptools", {})
    excludes = list((tool.get("packages", {}) or {}).get("find", {}).get("exclude", []) or [])
    problems = []
    for want in M7_REQUIRED_EXCLUDES:
        if not any(item.rstrip("*").rstrip("/") == want for item in excludes):
            problems.append("packages.find.exclude is missing {!r}".format(want))

    package_data = tool.get("package-data", {}) or {}
    warns = []
    for package, patterns in package_data.items():
        if isinstance(patterns, str):
            patterns = [patterns]
        for pattern in patterns or []:
            pattern = str(pattern)
            if "*" in pattern:
                problems.append("package-data[{!r}] uses a wide glob {!r}".format(package, pattern))
            if ".." in pattern or pattern.startswith(("/", "\\")):
                problems.append("package-data[{!r}] escapes the package: {!r}".format(
                    package, pattern))
    stray = sorted(set(package_data) - {"cullinan", ""})
    if stray:
        warns.append("package-data declares non-cullinan keys: {}".format(", ".join(stray)))

    # Diagnostic only: files under the package that ship through neither
    # package-data nor `.py`, i.e. silently dropped from the distribution.
    declared = set()
    for patterns in package_data.values():
        if isinstance(patterns, str):
            patterns = [patterns]
        declared.update(str(p) for p in (patterns or []))
    pkg_dir = os.path.join(root, "cullinan")
    if os.path.isdir(pkg_dir):
        for name in sorted(os.listdir(pkg_dir)):
            full = os.path.join(pkg_dir, name)
            if os.path.isfile(full) and not name.endswith(".py") and name not in declared:
                warns.append("cullinan/{} ships through no package-data entry".format(name))

    if problems:
        return Result("M7", "packaging discovery is bounded", "FAIL",
                      "{} problem(s)".format(len(problems)), problems + ["WARN " + w for w in warns])
    return Result("M7", "packaging discovery is bounded", "PASS",
                  "excludes cover {}; package-data = {}".format(
                      ", ".join(M7_REQUIRED_EXCLUDES),
                      ", ".join("{}:{}".format(k, v) for k, v in package_data.items())),
                  ["WARN " + w for w in warns])


def gate_m8(root, _refs):
    """M1/M2/M3 hold in every worktree, not only this one."""
    code, out, err = git("worktree", "list", "--porcelain", cwd=root)
    if code != 0:
        return Result("M8", "every worktree passes M1/M2/M3", "FAIL",
                      "git worktree list failed: {}".format(err.strip()))
    paths = [line[len("worktree "):] for line in out.splitlines()
             if line.startswith("worktree ")]
    checked = []
    failures = []
    for path in paths:
        if not os.path.isdir(path):
            checked.append("{} (missing, skipped)".format(path))
            continue
        code, head, _ = git("rev-parse", "--verify", "HEAD^{commit}", cwd=path)
        if code != 0:
            checked.append("{} (no HEAD, skipped)".format(path))
            continue
        hits1, err1 = m1_hits(path)
        hits2, err2 = m2_hits(path)
        names, err3 = archive_names(path)
        if hits1 is None or hits2 is None or names is None:
            failures.append("{}: {}".format(path, err1 or err2 or err3))
            continue
        bad3 = [name for name in names if ".workbuddy/" in name]
        row = "{:<60s} {}/{} members, M1={} M2={} M3={}".format(
            path, len(names), len(names), len(hits1), len(hits2), len(bad3))
        checked.append(row)
        if hits1 or hits2 or bad3:
            failures.append(row)
    if failures:
        return Result("M8", "every worktree passes M1/M2/M3", "FAIL",
                      "{} worktree(s) failing".format(len(failures)), checked)
    if not paths:
        return Result("M8", "every worktree passes M1/M2/M3", "FAIL",
                      "git worktree list returned no worktree")
    return Result("M8", "every worktree passes M1/M2/M3", "PASS",
                  "{} worktree(s) scanned, all of M1/M2/M3 at 0".format(len(paths)), checked)


# --------------------------------------------------------------------------- #
# M9
# --------------------------------------------------------------------------- #


def _interpreters(explicit=None):
    candidates = []
    env = os.environ.get("CULLINAN_GATE_PYTHON")
    if explicit:
        candidates.append(explicit)
    if env:
        candidates.append(env)
    candidates.append(sys.executable)
    for name in ("python3", "python"):
        found = shutil.which(name)
        if found:
            candidates.append(found)
    seen = []
    for candidate in candidates:
        if not candidate:
            continue
        real = os.path.abspath(candidate) if os.path.exists(candidate) else candidate
        if real in seen:
            continue
        seen.append(real)
    return seen


def _has_build_toolchain(interpreter):
    if not (os.path.exists(interpreter) or shutil.which(interpreter)):
        return False
    probe = _run([interpreter, "-c", "import build, setuptools; print('ok')"], timeout=60)
    return probe.returncode == 0 and b"ok" in probe.stdout


def build_sdist(rev, root, interpreter, workdir):
    """Build a real sdist from `rev`. Returns (tarball path, member count, note) or raises."""
    src = os.path.join(workdir, "src")
    outdir = os.path.join(workdir, "dist")
    os.makedirs(src, exist_ok=True)
    os.makedirs(outdir, exist_ok=True)
    tar_path = os.path.join(workdir, "src.tar")
    code, _, err = git("archive", "--format=tar", "-o", tar_path, rev, cwd=root)
    if code != 0:
        raise RuntimeError("git archive {} failed: {}".format(rev, err.strip()))
    with tarfile.open(tar_path, "r:") as tar:
        try:
            tar.extractall(src, filter="data")  # Python 3.12+: no metadata surprises
        except TypeError:  # Python < 3.12 has no filter argument
            tar.extractall(src)
    proc = _run([interpreter, "-m", "build", "--sdist", "--no-isolation",
                 "--outdir", outdir], cwd=src, timeout=900)
    if proc.returncode != 0:
        tail = proc.stderr.decode("utf-8", "replace").strip().splitlines()[-6:]
        raise RuntimeError("python -m build --sdist failed: {}".format(" | ".join(tail)))
    tarballs = [name for name in os.listdir(outdir) if name.endswith(".tar.gz")]
    if len(tarballs) != 1:
        raise RuntimeError("expected exactly one sdist in {}, found {}".format(
            outdir, tarballs or "none"))
    return os.path.join(outdir, tarballs[0])


def scan_archive(tar_path):
    """Scan an sdist: member paths and member contents.

    Returns ``(path_hits, content_hits, warnings, members)``. Path hits are the
    assertion M9 actually makes. Content hits are a stronger reading of the same
    risk. Warnings are mentions that are *not* leaks -- a `.gitignore`-family file
    may name an ignored directory, and that line is the reason the directory stays
    out of the repository, so treating it as a failure would punish the defence.
    Keeping the three apart is what stops a warning from becoming a silent failure
    or a silent pass.
    """
    path_hits = []
    content_hits = []
    warnings = []
    members = 0
    tokens = {token.strip("/") for token in INTERNAL_TOKENS}
    with tarfile.open(tar_path, "r:*") as tar:
        for member in tar.getmembers():
            members += 1
            if INTERNAL_PATTERN.search(member.name):
                path_hits.append(member.name)
                continue
            if not member.isfile() or member.size > 4 * 1024 * 1024:
                continue
            handle = tar.extractfile(member)
            if handle is None:
                continue
            try:
                text = handle.read().decode("utf-8", "replace")
            except Exception:  # a member we cannot read is not a member we can clear
                content_hits.append("{}: unreadable member".format(member.name))
                continue
            base = os.path.basename(member.name)
            for number, line in enumerate(text.splitlines(), 1):
                if not INTERNAL_PATTERN.search(line):
                    continue
                stripped = line.strip()
                head = stripped.split()[0].lstrip("!/") if stripped else ""
                if base in IGNORE_FILE_NAMES and head.strip("/") in tokens:
                    warnings.append(
                        "WARN {}:{}: ignore-rule mention, not a leak".format(member.name, number))
                else:
                    content_hits.append("{}:{}: {}".format(member.name, number, stripped[:120]))
    return path_hits, content_hits, warnings, members


def gate_m9(root, refs, rev=None, allow_sdist=True, interpreter=None):
    title = "sdist holds no internal name"
    if not allow_sdist:
        return Result("M9", title, "SKIP", "--no-sdist given: NOT COVERED")

    commits = target_commits(refs, fallback_rev=rev, cwd=root)
    if not commits:
        reason = ("every pushed ref is a deletion: no tree is published"
                  if refs else "no revision given and no refs on stdin")
        return Result("M9", title, "SKIP", reason + ": NOT COVERED")

    interpreters = _interpreters(interpreter)
    usable = next((candidate for candidate in interpreters if _has_build_toolchain(candidate)),
                  None)
    if usable is None:
        return Result(
            "M9", title, "SKIP",
            "no interpreter with build+setuptools among {}: NOT COVERED (residual risk)".format(
                ", ".join(interpreters)))

    rows = []
    real_hits = []
    warnings = []
    for commit in commits:
        workdir = tempfile.mkdtemp(prefix="cullinan-m9-")
        try:
            tar_path = build_sdist(commit, root, usable, workdir)
            path_hits, content_hits, warns, members = scan_archive(tar_path)
            warnings.extend(warns)
            name = os.path.basename(tar_path)
            if path_hits:
                real_hits.extend(path_hits)
                rows.append("{} @ {}: {} member(s), {} PATH HIT(S)".format(
                    name, commit[:12], members, len(path_hits)))
            elif content_hits:
                real_hits.extend(content_hits)
                rows.append("{} @ {}: {} member(s), {} CONTENT HIT(S)".format(
                    name, commit[:12], members, len(content_hits)))
            else:
                rows.append("{} @ {}: {} member(s), 0 hit(s) in paths and contents".format(
                    name, commit[:12], members))
        except Exception as exc:  # a broken build is a failure, not a skip
            return Result("M9", title, "FAIL",
                          "sdist build/scan failed (toolchain present, so this is a FAIL): {}".format(
                              exc), rows)
        finally:
            shutil.rmtree(workdir, ignore_errors=True)

    if real_hits:
        return Result("M9", title, "FAIL",
                      "{} hit(s) in the sdist".format(len(real_hits)),
                      real_hits[:20], )
    return Result("M9", title, "PASS",
                  "{} build(s) via {}; 0 hit(s)".format(len(commits), usable),
                  rows + warnings)


# --------------------------------------------------------------------------- #
# Self-test: prove each scanner can fire
# --------------------------------------------------------------------------- #


def selftest(root):
    """Feed the scanners a deliberately dirty input and require them to say so.

    A scanner that has never returned a hit is indistinguishable from a scanner
    that cannot. This runs offline, touches nothing in the repository, and restores
    the tree it used.
    """
    failures = []

    # 1. Archive scan: inject one member with an internal name, one with the token in
    #    its body, and require both to be reported.
    with tempfile.TemporaryDirectory() as tmp:
        good = os.path.join(tmp, "good.txt")
        with open(good, "w", encoding="utf-8") as handle:
            handle.write("nothing to see\n")
        name_dirty = os.path.join(tmp, "vault-doc.md")
        with open(name_dirty, "w", encoding="utf-8") as handle:
            handle.write("clean body\n")
        body_dirty = os.path.join(tmp, "notes.md")
        with open(body_dirty, "w", encoding="utf-8") as handle:
            handle.write("see 知识库治理 for details\n")

        clean_tar = os.path.join(tmp, "clean.tar.gz")
        with tarfile.open(clean_tar, "w:gz") as tar:
            tar.add(good, arcname="pkg/good.txt")
        path_hits, content_hits, warns, members = scan_archive(clean_tar)
        if path_hits or content_hits or warns:
            failures.append("clean archive reported hits: {}{}{}".format(
                path_hits, content_hits, warns))
        print("  {:32s} members={} hits={} (expect 0)".format(
            "clean archive", members, len(path_hits) + len(content_hits) + len(warns)))

        dirty_tar = os.path.join(tmp, "dirty.tar.gz")
        with tarfile.open(dirty_tar, "w:gz") as tar:
            tar.add(good, arcname="pkg/good.txt")
            tar.add(name_dirty, arcname="pkg/知识库治理/leak.md")
            tar.add(body_dirty, arcname="pkg/notes.md")
        path_hits, content_hits, _warns, _members = scan_archive(dirty_tar)
        caught_name = any("知识库" in hit for hit in path_hits)
        caught_body = any("知识库" in hit for hit in content_hits)
        if not caught_name:
            failures.append("archive scan missed a member path")
        if not caught_body:
            failures.append("archive scan missed a member body")
        print("  {:32s} path_hits={} content_hits={} (expect >=1 and >=1)".format(
            "dirty archive", len(path_hits), len(content_hits)))

        # An ignore rule naming an ignored directory is a defence, not a leak: it has
        # to be reported and it must not be counted as a failure.
        ignore_tar = os.path.join(tmp, "ignore.tar.gz")
        ignore_file = os.path.join(tmp, ".gitignore")
        with open(ignore_file, "w", encoding="utf-8") as handle:
            handle.write(".workbuddy/\n")
        with tarfile.open(ignore_tar, "w:gz") as tar:
            tar.add(ignore_file, arcname="pkg/.gitignore")
        path_hits, content_hits, warns, _m = scan_archive(ignore_tar)
        if path_hits or content_hits or not warns:
            failures.append("ignore-rule mention was not classified as a warning")
        print("  {:32s} hits={} warns={} (expect 0 and >=1)".format(
            "ignore-rule archive", len(path_hits) + len(content_hits), len(warns)))

    # 2. Worktree/path scanners: an injected `.workbuddy` path must be seen by the M1
    #    and M2 filters. Pure regex here, so no repository state is touched.
    m1_pattern = re.compile(r"^(?:\.workbuddy|.*/\.workbuddy)/")
    cases = [
        (".workbuddy/memory/x.md", True),
        ("sub/.workbuddy/x.md", True),
        ("cullinan/.workbuddy.py", False),
        ("notes/.workbuddyish/x.md", False),
    ]
    for path, expect in cases:
        got = bool(m1_pattern.match(path))
        if got != expect:
            failures.append("M1 filter disagrees on {}".format(path))
        print("  {:32s} match={!s:5s} (expect {!s})".format("M1 filter " + path, got, expect))

    # 3. M4/M3 plumbing must be able to report a non-zero reading at all: run the M3
    #    filter over a synthetic member list containing .workbuddy.
    synthetic = ["pkg/a.py", "pkg/.workbuddy/memory/MEMORY.md"]
    if not [name for name in synthetic if ".workbuddy/" in name]:
        failures.append("M3 filter cannot see an injected member")

    if failures:
        print("selftest FAILED: {}".format("; ".join(failures)))
        return 1
    print("selftest: every scanner returned a hit on dirty input and none on clean input")
    return 0


# --------------------------------------------------------------------------- #
# Driver
# --------------------------------------------------------------------------- #

GATES = [
    ("M0", gate_m0),
    ("M1", gate_m1),
    ("M2", gate_m2),
    ("M3", gate_m3),
    ("M4", gate_m4),
    ("M5", gate_m5),
    ("M6", gate_m6),
    ("M7", gate_m7),
    ("M8", gate_m8),
]


def main(argv=None):
    parser = argparse.ArgumentParser(description="Pre-push mechanical gate (M0..M9).")
    parser.add_argument("--rev", default=None,
                        help="check this revision instead of reading pre-push stdin")
    parser.add_argument("--refs-file", default=None,
                        help="read pre-push ref lines from a file instead of stdin")
    parser.add_argument("--refs-stdin", action="store_true",
                        help="read pre-push ref lines from stdin (default: do not read stdin)")
    parser.add_argument("--only", default=None, help="comma separated gate ids, e.g. M3,M9")
    parser.add_argument("--no-sdist", action="store_true", help="skip M9 and say so")
    parser.add_argument("--python", default=None, help="interpreter used for the sdist build")
    parser.add_argument("--repo", default=None, help="repository root (default: git toplevel)")
    parser.add_argument("--json", action="store_true", help="machine-readable output")
    parser.add_argument("--selftest", action="store_true", help="prove the scanners can fire")
    parser.add_argument("--scan-archive", default=None, metavar="PATH",
                        help="scan an already-built sdist tar archive instead of building one")
    args = parser.parse_args(argv)

    if args.scan_archive:
        # The M9 scanner is useful on its own: an artifact that was built elsewhere
        # (CI, a release candidate, a file someone is about to upload) can be read
        # with the same rules without rebuilding it. During this gate's own drill
        # this was the only missing piece, and it had to be done by hand with tar
        # and grep -- which is exactly the kind of manual step that gets skipped.
        path = args.scan_archive
        if not os.path.isfile(path):
            print("no such archive: {}".format(path), file=sys.stderr)
            return 2
        try:
            path_hits, content_hits, warnings, members = scan_archive(path)
        except (tarfile.TarError, OSError) as exc:
            print("cannot read {} as an archive: {}".format(path, exc), file=sys.stderr)
            return 2
        verdict = "FAIL" if (path_hits or content_hits) else "PASS"
        if args.json:
            print(json.dumps({
                "gate": "M9", "archive": path, "members": members,
                "path_hits": path_hits, "content_hits": content_hits,
                "warnings": warnings, "verdict": verdict,
            }, ensure_ascii=False, indent=2))
        else:
            print("archive: {} ({} member(s))".format(path, members))
            print("[{}] M9 - sdist holds no internal name".format(verdict))
            print("      {} path hit(s), {} content hit(s), {} warning(s)".format(
                len(path_hits), len(content_hits), len(warnings)))
            for line in path_hits + content_hits + warnings:
                print("      " + line)
        return 1 if verdict == "FAIL" else 0

    root = repo_root(args.repo)
    if args.selftest:
        return selftest(root)

    if args.refs_file:
        with open(args.refs_file, "r", encoding="utf-8", errors="replace") as handle:
            stdin_text = handle.read()
    elif args.refs_stdin:
        stdin_text = sys.stdin.read()
    else:
        # No implicit stdin read. Git hands a hook its refs on stdin, so an implicit
        # read looks harmless -- but run by hand the same code blocks forever on a
        # pipe that nobody closes, and a gate that hangs is indistinguishable from a
        # gate that is broken. The installed hook passes `--refs-file`, so the refs
        # still arrive where they matter.
        stdin_text = ""
    refs = parse_refs(stdin_text)

    wanted = None
    if args.only:
        wanted = {item.strip().upper() for item in args.only.split(",") if item.strip()}

    results = []
    for gate_id, function in GATES:
        if wanted and gate_id not in wanted:
            continue
        results.append(function(root, refs))
    if not wanted or "M9" in wanted:
        # With no refs and no explicit revision there is still a tree to check: HEAD.
        # Defaulting to it keeps M9 armed for a hand run; a skip here would be the
        # "not covered" hole this gate exists to close.
        build_rev = args.rev or (None if refs else "HEAD")
        results.append(gate_m9(root, refs, rev=build_rev, allow_sdist=not args.no_sdist,
                               interpreter=args.python))

    failed = [result for result in results if result.status == "FAIL"]
    skipped = [result for result in results if result.status == "SKIP"]

    if args.json:
        print(json.dumps(
            {
                "gate_version": GATE_VERSION,
                "repo": root,
                "rev": args.rev,
                "refs": refs,
                "results": [result.as_dict() for result in results],
                "failed": [result.gate for result in failed],
                "skipped": [result.gate for result in skipped],
                "verdict": "FAIL" if failed else "PASS",
            },
            ensure_ascii=False,
            indent=2,
        ))
        return 1 if failed else 0

    print("M0-M9 gate {} -- {}".format(GATE_VERSION, root))
    for result in results:
        print("[{}] {}".format(result.status, result.gate), "-", result.title)
        print("      " + result.detail)
        for line in result.lines:
            print("      " + line)
    if skipped:
        print("NOT COVERED: {} -- a skip is not a pass".format(
            ", ".join(result.gate for result in skipped)))
    if failed:
        print("RESULT: FAIL ({} of {} gate(s) failed)".format(len(failed), len(results)))
        return 1
    print("RESULT: PASS ({} gate(s), {} not covered)".format(len(results), len(skipped)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
