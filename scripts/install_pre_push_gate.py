#!/usr/bin/env python3
"""Install (or remove) the M0..M9 pre-push hook.

Read this before running it, because the hook does not live where it looks like it
lives.

Where the hook goes
-------------------
This repository is used through several git worktrees. In a worktree, `.git` is a
file that points at the shared common directory, so `hooks/` is *shared by every
worktree*, not per checkout. The path is therefore resolved with

    git rev-parse --path-format=absolute --git-path hooks

and never assumed to be `<worktree>/.git/hooks`. Installing affects every worktree
of this repository at once. That is the point -- a guard that only arms one
checkout is a guard with a documented bypass -- but it must be a deliberate act.

What it does *not* do
--------------------
It never overwrites an existing `pre-push`. An existing hook is preserved verbatim
and the new hook chains to it, so a guard that was already there (a remote-write
guard, for instance) keeps running after the M0..M9 gate passes. The preserved copy
stays in the hooks directory, which git does not track: nothing about it enters the
repository.

Files written (all outside the repository, all reversible):

    <hooks>/pre-push                      the dispatcher (marker: M0-M9 GATE)
    <hooks>/pre-push.pre-m0m9.bak         the hook that was there before, if any
    <hooks>/gate_pre_push.py              a snapshot, used by worktrees whose tree
                                          does not yet carry scripts/gate_pre_push.py

Usage
-----
    python scripts/install_pre_push_gate.py              # install / refresh
    python scripts/install_pre_push_gate.py --dry-run    # show, change nothing
    python scripts/install_pre_push_gate.py --status     # what is installed
    python scripts/install_pre_push_gate.py --uninstall  # restore the old hook

Bypasses, stated plainly (a hook that pretends to be unbypassable is worse than one
that names its own holes): `git push --no-verify`, `CULLINAN_GATE_PRE_PUSH=off`,
`CULLINAN_GATE_PRE_PUSH_NO_SDIST=1`, and `git config core.hooksPath <elsewhere>`.
"""

from __future__ import annotations

import argparse
import hashlib
import os
import shutil
import stat
import subprocess
import sys

MARKER = "M0-M9 GATE"
BACKUP_NAME = "pre-push.pre-m0m9.bak"
SNAPSHOT_NAME = "gate_pre_push.py"

HOOK_TEMPLATE = """#!/bin/sh
# {marker} -- dispatcher installed by scripts/install_pre_push_gate.py.
# Not part of the repository: it lives in the shared git hooks directory.
#
# Order: this gate runs first and stops the push on failure; on success it hands
# the same stdin to the hook that was here before, preserved as {backup}.
#
# Bypass: `git push --no-verify`, or CULLINAN_GATE_PRE_PUSH=off,
#         or CULLINAN_GATE_PRE_PUSH_NO_SDIST=1 to skip only M9.

HOOKS_DIR=$(cd "$(dirname "$0")" && pwd)
ROOT=$(git rev-parse --show-toplevel 2>/dev/null)

REFBUF=$(mktemp 2>/dev/null || echo "${{TMPDIR:-/tmp}}/cullinan-prepush-$$.txt")
trap 'rm -f "$REFBUF"' EXIT INT TERM
cat > "$REFBUF"

if [ "${{CULLINAN_GATE_PRE_PUSH:-on}}" != "off" ]; then
  GATE=""
  if [ -n "$ROOT" ] && [ -f "$ROOT/scripts/gate_pre_push.py" ]; then
    GATE="$ROOT/scripts/gate_pre_push.py"
  elif [ -f "$HOOKS_DIR/{snapshot}" ]; then
    GATE="$HOOKS_DIR/{snapshot}"
  fi
  if [ -z "$GATE" ]; then
    echo "{marker}: gate script not found in this worktree or in the hooks directory." >&2
    echo "{marker}: NOT COVERED -- refusing to report a pass it did not earn." >&2
    exit 1
  fi
  PY="${{CULLINAN_GATE_PYTHON:-{interpreter}}}"
  if [ ! -x "$PY" ]; then
    for candidate in python3 python; do
      if command -v "$candidate" >/dev/null 2>&1; then PY="$candidate"; break; fi
    done
  fi
  EXTRA=""
  if [ "${{CULLINAN_GATE_PRE_PUSH_NO_SDIST:-0}}" = "1" ]; then EXTRA="--no-sdist"; fi
  # shellcheck disable=SC2086
  if ! "$PY" "$GATE" --refs-file "$REFBUF" $EXTRA; then
    echo "{marker}: push refused -- a mechanical gate failed above." >&2
    echo "{marker}: fix the finding, or bypass deliberately with --no-verify." >&2
    exit 1
  fi
fi

if [ -f "$HOOKS_DIR/{backup}" ]; then
  # Run the preserved hook with its own shebang; fall back to sh if the checkout
  # lost the executable bit (the platform reports core.filemode=false here).
  if [ -x "$HOOKS_DIR/{backup}" ]; then
    "$HOOKS_DIR/{backup}" "$@" < "$REFBUF"
  else
    sh "$HOOKS_DIR/{backup}" "$@" < "$REFBUF"
  fi
  exit $?
fi
exit 0
"""


class Installer:
    def __init__(self, repo=None):
        self.repo = repo
        self.repo = self.repo or self._git(["rev-parse", "--show-toplevel"]).strip()
        self.hooks = self._hooks_dir()

    def _git(self, args):
        proc = subprocess.run(["git", *args], cwd=self.repo, capture_output=True, text=True)
        if proc.returncode != 0:
            raise SystemExit("git {} failed: {}".format(" ".join(args), proc.stderr.strip()))
        return proc.stdout

    def _hooks_dir(self):
        """`--path-format=absolute` needs git >= 2.31; older git returns a relative path."""
        proc = subprocess.run(
            ["git", "rev-parse", "--path-format=absolute", "--git-path", "hooks"],
            cwd=self.repo, capture_output=True, text=True,
        )
        if proc.returncode == 0 and proc.stdout.strip():
            return proc.stdout.strip()
        raw = self._git(["rev-parse", "--git-path", "hooks"]).strip()
        return os.path.abspath(os.path.join(self.repo, raw))

    def source_script(self):
        return os.path.join(self.repo, "scripts", "gate_pre_push.py")

    def status(self):
        hook = os.path.join(self.hooks, "pre-push")
        backup = os.path.join(self.hooks, BACKUP_NAME)
        snapshot = os.path.join(self.hooks, SNAPSHOT_NAME)
        rows = []
        rows.append("repo      : {}".format(self.repo))
        rows.append("hooks dir : {} (shared by every worktree)".format(self.hooks))
        for label, path in (("pre-push", hook), ("backup", backup), ("snapshot", snapshot)):
            if os.path.isfile(path):
                rows.append("{:10s}: present, {} bytes, sha256 {}".format(
                    label, os.path.getsize(path), _sha256(path)[:16]))
            else:
                rows.append("{:10s}: absent".format(label))
        if os.path.isfile(hook):
            with open(hook, "r", encoding="utf-8", errors="replace") as handle:
                rows.append("ours      : {}".format(MARKER in handle.read()))
        source = self.source_script()
        if os.path.isfile(snapshot) and os.path.isfile(source):
            rows.append("snapshot matches scripts/gate_pre_push.py: {}".format(
                _sha256(snapshot) == _sha256(source)))
        return "\n".join(rows)

    def install(self, dry_run=False):
        os.makedirs(self.hooks, exist_ok=True)
        hook = os.path.join(self.hooks, "pre-push")
        backup = os.path.join(self.hooks, BACKUP_NAME)
        snapshot = os.path.join(self.hooks, SNAPSHOT_NAME)
        source = self.source_script()
        if not os.path.isfile(source):
            raise SystemExit("cannot install: {} is missing".format(source))

        actions = []
        if os.path.isfile(hook):
            with open(hook, "r", encoding="utf-8", errors="replace") as handle:
                is_ours = MARKER in handle.read()
            if not is_ours:
                if os.path.isfile(backup):
                    actions.append("WARNING: {} already exists and pre-push is foreign; "
                                   "refusing to choose between two backups".format(backup))
                    raise SystemExit("\n".join(actions))
                actions.append("preserve existing pre-push -> {}".format(BACKUP_NAME))
                if not dry_run:
                    shutil.copy2(hook, backup)
                    _make_executable(backup)
            else:
                actions.append("refresh existing gate hook (backup left untouched)")

        actions.append("write {}".format(hook))
        actions.append("write snapshot {}".format(snapshot))
        if not dry_run:
            shutil.copyfile(source, snapshot)
            _make_executable(snapshot)
            with open(hook, "w", encoding="utf-8", newline="\n") as handle:
                handle.write(HOOK_TEMPLATE.format(
                    marker=MARKER,
                    backup=BACKUP_NAME,
                    snapshot=SNAPSHOT_NAME,
                    interpreter=sys.executable.replace("\\", "/"),
                ))
            _make_executable(hook)
            subprocess.run(["git", "config", "--local", "m0m9Gate.hooksDir", self.hooks],
                           cwd=self.repo, capture_output=True)

        header = "DRY RUN -- nothing written" if dry_run else "installed"
        return "{}\n{}\n\n{}".format(header, "\n".join("  " + a for a in actions), self.status())

    def uninstall(self):
        hook = os.path.join(self.hooks, "pre-push")
        backup = os.path.join(self.hooks, BACKUP_NAME)
        snapshot = os.path.join(self.hooks, SNAPSHOT_NAME)
        notes = []
        if not os.path.isfile(hook):
            return "nothing to do: no pre-push hook at {}".format(hook)
        with open(hook, "r", encoding="utf-8", errors="replace") as handle:
            if MARKER not in handle.read():
                return ("refusing to remove {}: it is not the {} hook".format(hook, MARKER))
        os.remove(hook)
        notes.append("removed {}".format(hook))
        if os.path.isfile(backup):
            shutil.move(backup, hook)
            _make_executable(hook)
            notes.append("restored the previous hook from {}".format(BACKUP_NAME))
        if os.path.isfile(snapshot):
            os.remove(snapshot)
            notes.append("removed snapshot {}".format(snapshot))
        subprocess.run(["git", "config", "--local", "--unset", "m0m9Gate.hooksDir"],
                       cwd=self.repo, capture_output=True)
        notes.append("hook removed: pushes are now guarded by {} only".format(
            "the previous hook" if os.path.isfile(hook) else "nothing"))
        return "\n".join(notes)


def _sha256(path):
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _make_executable(path):
    mode = os.stat(path).st_mode
    os.chmod(path, mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


def main(argv=None):
    parser = argparse.ArgumentParser(description="Install the M0..M9 pre-push hook.")
    parser.add_argument("--repo", default=None)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--status", action="store_true")
    parser.add_argument("--uninstall", action="store_true")
    args = parser.parse_args(argv)

    installer = Installer(args.repo)
    if args.status:
        print(installer.status())
        return 0
    if args.uninstall:
        print(installer.uninstall())
        return 0
    print(installer.install(dry_run=args.dry_run))
    return 0


if __name__ == "__main__":
    sys.exit(main())
