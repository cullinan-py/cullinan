#!/usr/bin/env python3
"""Report plaintext values in the project configuration files this repository ships.

Why this exists
---------------
``.gitignore`` keeps value-carrying configuration files out of ``git add .``, but
an ignore rule is not a gate: ``git add -f`` walks straight past it, and a file
committed before the rule existed stays committed. This script is the check that
can say no. It reads the configuration files the loader would read and reports
any value that is written down instead of referenced.

What it decides
---------------
The unit of judgement is a **string leaf** -- one value in the document, with the
key path that reaches it. Each leaf is walked through the rules below and the
first match wins, so the order matters: value shapes are examined before key
names, because a credential's shape is evidence while its key name is only a
hint.

  R1  the value is a mapping whose only key is ``encrypted`` and whose value is
      a string -- the shape ``load_project_config(decryptor=...)`` consumes, so
      the file is expected to hold ciphertext there. CLEAN.
  R2  the value is not a string. A plaintext secret can only be text. CLEAN.
  R3  the value is the empty string. CLEAN.
  R4  the whole value is one ``${VAR}`` / ``${VAR:default}`` reference. CLEAN --
      this is the form the loader resolves from the environment, and it is the
      only form the documentation recommends.
  R5  the value matches a **deterministic value pattern** (a PEM private-key
      header, an AWS access-key id, a GitHub token) regardless of its key name.
      HIT.
  R6  the value contains ``${`` but is not a single reference (``prefix-${VAR}``,
      ``${A}${B}``). UNCERTAIN: the loader substitutes into such a string, so it
      may resolve to a value, but the environment is not visible from here. This
      is the only honest third answer, and it does not block.
  R7  the key name, lowercased with ``_`` and ``-`` removed, contains one of the
      sensitive stems. HIT.

What it deliberately does not decide
------------------------------------
* **No entropy scoring.** A threshold is a number, and a number tuned to this
  repository's fixtures would either miss the next leak or fire on a digest.
  ``VALUE_PATTERNS`` is the extension point if a shape is worth adding: a shape
  is checkable, a score is a guess.
* **No bypass switch.** There is no ``--skip``. A documented way past a gate is
  a gate that is already off. The escape hatch that exists is
  ``git push --no-verify``, which is visible in the reflog.
* **Nothing is rewritten, decrypted or moved into the environment.** This
  reports and exits non-zero. Editing a user's configuration file is not a
  read-only tool's job.

What it does not cover, stated so nobody assumes otherwise
---------------------------------------------------------
* B1 secrets in ``.py`` constants, ``.env`` files or CI definitions. That needs
  a whole-repository scanner with its own false-positive budget; use
  ``gitleaks`` or ``trufflehog``, which are built for it.
* B2 git history. Only the working tree and the index are read, so a value
  committed and later removed is not found here.
* B3 YAML is read line by line -- the standard library has no YAML parser. A
  single-line ``key: value`` is seen; multi-line block scalars are reported as
  uncertain rather than guessed at, and anchors, aliases and flow mappings are
  not seen at all. Every YAML run says so, per file.
* B4 TOML falls back to the same line scan below Python 3.11, which has no
  ``tomllib``. The fallback is announced, never silent.
* B5 only files named ``application*`` with a configuration suffix. A file
  named through ``CULLINAN_CONFIG`` can be called anything, and is not scanned.
* B6 template files are **not** given a pass. If ``application.example.json``
  held a value, it would be reported; a template that is allowed to hold values
  is an official channel for one.
* B7 a value's *validity* is not tested. ``"token": "abc"`` is reported, and so
  is a rotated-dead credential. Deciding that needs a live API call.
* B8 the report never repeats the value it found: only the path, the key path,
  the reason and the length. A checker that echoes its findings into a CI log
  has created a second place for the secret to be.

The scan surface
----------------
The set is every file in the working tree whose **name** matches
``CONFIG_NAME_GLOBS``, plus every matching path in the git index. It is
deliberately *not* derived from ``git ls-files --others --exclude-standard``:
the file most worth checking -- a local override that a ``.gitignore`` rule has
just started ignoring -- is invisible to that command, so a scan built on it
would report a clean repository while the value sat on disk. The directories in
``PRUNE_DIRS`` are skipped; every other directory is walked.

Exit codes
----------
``0`` clean (warnings and uncertain findings do not change this), ``1`` at least
one plaintext value was found, ``2`` the scan could not decide -- a file that
could enter the repository could not be read or parsed. ``2`` is not a pass;
the same three-way reading is used by ``scripts/gate_pre_push.py``.

Usage
-----
    python scripts/check_config_secrets.py                    # scan this repository
    python scripts/check_config_secrets.py --root <dir>       # scan another root
    python scripts/check_config_secrets.py --paths a.json b.yaml    # explicit files
    python scripts/check_config_secrets.py --json             # machine-readable
    python scripts/check_config_secrets.py --strict           # uncertain exits 2
    python scripts/check_config_secrets.py --selftest         # prove it can fire

Only ``--json`` output goes to stdout as data; in human mode the finding lines
go to stderr and the one-line summary goes to stdout, so a caller can read the
count without parsing prose.
"""

from __future__ import annotations

import argparse
import fnmatch
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import List, NamedTuple, Optional, Sequence, Tuple

EXIT_CLEAN, EXIT_HIT, EXIT_UNDECIDED = 0, 1, 2

#: Names the loader reads: CONFIG_BASENAME ('application') plus CONFIG_SUFFIXES.
#: Kept as a name pattern, not a path pattern, because the loader accepts the
#: base file, 'application-{profile}' and any nested combination of the two.
CONFIG_NAME_GLOBS = (
    "application*.json",
    "application*.toml",
    "application*.yaml",
    "application*.yml",
)

#: Directories that hold other people's files or build output. ``.venv*`` is
#: handled by prefix in ``iter_targets`` so a pinned interpreter path is skipped
#: too.
PRUNE_DIRS = {
    ".git",
    "build",
    "dist",
    "site",
    "node_modules",
    "__pycache__",
    ".pytest_cache",
    ".ruff_cache",
}

#: Key-name stems, matched as substrings of the normalised name. ``key`` is
#: deliberately absent: ``key_file``, ``sort_key`` and ``map_key`` are ordinary
#: names, and a gate that fires on ordinary names is a gate people switch off --
#: which costs more than the leaks it would have found.
SENSITIVE_KEYWORDS = (
    "token",
    "secret",
    "password",
    "passwd",
    "pwd",
    "credential",
    "apikey",
    "accesskey",
    "privatekey",
    "clientsecret",
)

#: The loader's own reference syntax, anchored at both ends: R4 asks whether the
#: *whole* value is a reference, so ``fullmatch`` is the honest anchor. The
#: pattern body is the same shape as ``config_file._PLACEHOLDER`` and a test
#: holds the two together.
PLACEHOLDER_FULL = re.compile(r"\$\{[A-Za-z_][A-Za-z0-9_]*(?::[^}]*)?\}$")

#: Shapes that are a credential by construction, so the key name is irrelevant.
#: The AWS expression is the one ``git-secrets --register-aws`` uses, kept
#: verbatim so the two tools agree; the GitHub prefixes are fixed by GitHub.
VALUE_PATTERNS = (
    ("pem-private-key", re.compile(r"-----BEGIN (?:[A-Z0-9 ]+ )?PRIVATE KEY-----")),
    (
        "aws-access-key-id",
        re.compile(r"(?:A3T[A-Z0-9]|AKIA|AGPA|AIDA|AROA|AIPA|ANPA|ANVA|ASIA)[A-Z0-9]{16}"),
    ),
    ("github-token", re.compile(r"gh[pousr]_[A-Za-z0-9]{36}|github_pat_[A-Za-z0-9_]{22,}")),
)

#: The single-key mapping ``load_project_config(decryptor=...)`` unwraps (R1).
ENCRYPTED_MARKER = "encrypted"

#: One ``key: value`` / ``key = value`` line. This is all the YAML and the
#: pre-3.11 TOML fallback can see, and it is why B3/B4 are written down above.
LINE_SCAN = re.compile(r"^\s*([A-Za-z0-9_][A-Za-z0-9_.\-]*)\s*[:=]\s*(.*)$")

#: YAML block-scalar indicators. ``token: |`` puts the value on the following
#: lines, which a line scan cannot judge: reporting its one-character indicator
#: as a hit would be a made-up finding, and calling it clean would be a silent
#: miss. It is reported as uncertain instead.
BLOCK_SCALAR_INDICATORS = frozenset(("|", ">", "|-", ">-", "|+", ">+"))

#: Suffix to reader kind. Anything else an explicit ``--paths`` names is read
#: line by line and the fallback is announced.
_JSON, _TOML, _LINES = "json", "toml", "lines"


class Finding(NamedTuple):
    """One reported leaf. ``value_len`` is the only thing kept about the value."""

    verdict: str  # 'hit' | 'uncertain'
    key_path: str
    reason: str
    value_len: int


class FileReport:
    """What one file produced. ``problem`` non-empty means it could not be read."""

    __slots__ = ("path", "findings", "problem", "warnings", "is_ignored")

    def __init__(self, path, findings, problem, warnings, is_ignored):
        self.path = path
        self.findings = findings or []
        self.problem = problem or ""
        self.warnings = warnings or []
        self.is_ignored = bool(is_ignored)


# --------------------------------------------------------------------------- #
# Target discovery
# --------------------------------------------------------------------------- #


def matches_config_name(name: str) -> bool:
    """True when ``name`` is a configuration file name the loader would read."""
    return any(fnmatch.fnmatchcase(name, pattern) for pattern in CONFIG_NAME_GLOBS)


def _pruned(name: str) -> bool:
    return name in PRUNE_DIRS or name.startswith(".venv")


def index_names(root: Path, notes: Optional[List[str]] = None) -> List[str]:
    """Matching paths from the git index, or [] when ``root`` is not a repository."""
    try:
        completed = subprocess.run(
            ["git", "-C", str(root), "ls-files", "-z"],
            capture_output=True,
            timeout=120,
        )
    except (OSError, subprocess.SubprocessError) as error:
        if notes is not None:
            notes.append("git index not scanned ({}): only the working tree was read".format(error))
        return []
    if completed.returncode != 0:
        if notes is not None:
            notes.append(
                "git index not scanned (not a git working tree): only the working tree was read"
            )
        return []
    text = completed.stdout.decode("utf-8", "replace")
    return [name for name in text.split("\0") if name and matches_config_name(name)]


def iter_targets(root, explicit=None, notes=None):
    """The files to scan. ``explicit`` wins when given (the testing surface).

    Recursing the whole working tree instead of asking git for the unignored set
    is the point, not an implementation detail: the file a ``.gitignore`` rule
    has just started ignoring is exactly the one worth reading, and
    ``git ls-files --others --exclude-standard`` cannot see it.
    """
    if explicit is not None:
        return [Path(item).resolve() for item in explicit]

    root = Path(root).resolve()
    seen = set()
    targets = []

    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(name for name in dirnames if not _pruned(name))
        for name in sorted(filenames):
            if not matches_config_name(name):
                continue
            path = (Path(dirpath) / name).resolve()
            if path in seen:
                continue
            seen.add(path)
            targets.append(path)

    for name in index_names(root, notes):
        path = (root / name).resolve()
        if path in seen or not path.is_file():
            continue
        seen.add(path)
        targets.append(path)

    return targets


# --------------------------------------------------------------------------- #
# Classification (the rules, in order)
# --------------------------------------------------------------------------- #


def normalize_key(name) -> str:
    """``'X-Api-Key'`` -> ``'xapikey'``; the form R7 matches as a substring."""
    return str(name).lower().replace("_", "").replace("-", "")


def format_key_path(parts: Sequence[str]) -> str:
    """``('a', 'b', '[0]')`` -> ``'a.b[0]'``."""
    text = ""
    for part in parts:
        if part.startswith("["):
            text += part
        elif text:
            text += "." + part
        else:
            text = part
    return text


def _named_segments(key_path: str) -> List[str]:
    return [part for part in key_path.split(".") if part and not part.startswith("[")]


def iter_string_leaves(node, key_path=()):
    """Depth-first ``(key_path_tuple, str)`` for every string leaf.

    R1 is applied here rather than in ``classify`` because it describes a
    *mapping*, not a leaf: a ``{"encrypted": "..."}`` value is the ciphertext
    form, so there is no plaintext leaf inside it to judge.
    """
    if isinstance(node, dict):
        if set(node) == {ENCRYPTED_MARKER} and isinstance(node[ENCRYPTED_MARKER], str):
            return
        for key, value in node.items():
            yield from iter_string_leaves(value, key_path + (str(key),))
        return
    if isinstance(node, list):
        for index, item in enumerate(node):
            yield from iter_string_leaves(item, key_path + ("[{}]".format(index),))
        return
    if isinstance(node, str):
        yield key_path, node


def classify(key_path, value):
    """Walk R2..R7 for one leaf. Returns a ``Finding`` or ``None`` (CLEAN)."""
    if not isinstance(value, str):
        return None  # R2
    if value == "":
        return None  # R3
    if PLACEHOLDER_FULL.fullmatch(value):
        return None  # R4

    for name, pattern in VALUE_PATTERNS:
        if pattern.search(value):
            return Finding("hit", key_path, "value-pattern:" + name, len(value))  # R5

    if "${" in value:
        return Finding("uncertain", key_path, "partial-placeholder", len(value))  # R6

    segments = _named_segments(key_path)
    key = normalize_key(segments[-1]) if segments else ""
    for keyword in SENSITIVE_KEYWORDS:
        if keyword in key:
            return Finding("hit", key_path, "plaintext-under-sensitive-key", len(value))  # R7
    return None


# --------------------------------------------------------------------------- #
# Readers
# --------------------------------------------------------------------------- #


def _read_text(path: Path) -> Tuple[str, str]:
    try:
        return path.read_text(encoding="utf-8"), ""
    except (OSError, UnicodeDecodeError) as error:
        return "", "unreadable: {}".format(error)


def _unquote(text: str) -> str:
    if len(text) >= 2 and text[0] == text[-1] and text[0] in ("'", '"'):
        return text[1:-1]
    return text


def classify_document(data) -> List[Finding]:
    """Run every string leaf of a parsed document through ``classify``."""
    findings = []
    for parts, value in iter_string_leaves(data):
        finding = classify(format_key_path(parts), value)
        if finding is not None:
            findings.append(finding)
    return findings


def scan_lines(text: str) -> List[Finding]:
    """The best a line scan can do: one ``key: value`` per line."""
    findings = []
    for raw in text.splitlines():
        stripped = raw.strip()
        if not stripped or stripped.startswith("#"):
            continue
        match = LINE_SCAN.match(raw)
        if not match:
            continue
        key, value = match.group(1), _unquote(match.group(2).strip())
        if value in BLOCK_SCALAR_INDICATORS:
            findings.append(Finding("uncertain", key, "block-scalar-not-inspected", len(value)))
            continue
        finding = classify(key, value)
        if finding is not None:
            findings.append(finding)
    return findings


def scan_json(path) -> Tuple[List[Finding], str, List[str]]:
    path = Path(path)
    text, problem = _read_text(path)
    if problem:
        return [], problem, []
    try:
        data = json.loads(text)
    except ValueError as error:
        return [], "json-parse-error: {}".format(error), []
    return classify_document(data), "", []


def scan_toml(path) -> Tuple[List[Finding], str, List[str]]:
    path = Path(path)
    text, problem = _read_text(path)
    if problem:
        return [], problem, []
    try:
        import tomllib  # Python 3.11+
    except ModuleNotFoundError:
        note = "{}: line-scan only (this interpreter has no TOML parser)".format(path.name)
        return scan_lines(text), "", [note]
    try:
        data = tomllib.loads(text)
    except ValueError as error:
        return [], "toml-parse-error: {}".format(error), []
    return classify_document(data), "", []


def scan_yaml_lines(path) -> Tuple[List[Finding], str, List[str]]:
    path = Path(path)
    note = "{}: line-scan only (no YAML parser in the standard library)".format(path.name)
    text, problem = _read_text(path)
    if problem:
        return [], problem, [note]
    return scan_lines(text), "", [note]


def scan_file(path, root=None, allow_git=True) -> FileReport:
    """Read one file and collect its findings, warnings and read failure.

    ``allow_git`` is off in ``--paths`` mode: a test corpus must behave the same
    way whether or not it happens to sit inside a repository, so a file that
    cannot be parsed there is treated as a file that could enter it.
    """
    path = Path(path)
    display = display_path(path, root)
    suffix = path.suffix.lower()

    if not path.is_file():
        return FileReport(display, [], "not a readable file", [], False)

    if suffix == ".json":
        findings, problem, warnings = scan_json(path)
    elif suffix == ".toml":
        findings, problem, warnings = scan_toml(path)
    elif suffix in (".yaml", ".yml"):
        findings, problem, warnings = scan_yaml_lines(path)
    else:
        text, problem = _read_text(path)
        findings = scan_lines(text) if not problem else []
        warnings = ["{}: line-scan only (unrecognised suffix)".format(path.name)]

    if problem and allow_git and root is not None and is_ignored(path, root):
        # An ignored file cannot reach the repository, and it may be mid-edit.
        warnings = warnings + ["{}: unreadable but ignored, so not counted as a finding: {}".format(
            display, problem)]
        problem = ""

    return FileReport(display, findings, problem, warnings, False)


def display_path(path, root) -> str:
    path = Path(path)
    if root is not None:
        try:
            return path.resolve().relative_to(Path(root).resolve()).as_posix()
        except (ValueError, OSError):
            pass
    return path.as_posix()


def is_ignored(path, root) -> bool:
    """Whether git ignores ``path``. A missing git reads as 'not ignored'."""
    try:
        completed = subprocess.run(
            ["git", "-C", str(root), "check-ignore", "-q", "--", str(path)],
            capture_output=True,
            timeout=60,
        )
    except (OSError, subprocess.SubprocessError):
        return False
    return completed.returncode == 0


# --------------------------------------------------------------------------- #
# Verdict
# --------------------------------------------------------------------------- #


def decide(reports, root=None, strict=False, extra_warnings=None):
    """Three-way verdict plus the JSON payload. ``2`` is never a pass."""
    hits = [f for report in reports for f in report.findings if f.verdict == "hit"]
    uncertain = [f for report in reports for f in report.findings if f.verdict == "uncertain"]
    undecided = [report for report in reports if report.problem]

    if hits:
        code = EXIT_HIT
    elif undecided:
        code = EXIT_UNDECIDED
    else:
        code = EXIT_CLEAN
    if code == EXIT_CLEAN and uncertain and strict:
        code = EXIT_UNDECIDED

    warnings = list(extra_warnings or [])
    for report in reports:
        warnings.extend(report.warnings)
    warnings = list(dict.fromkeys(warnings))

    payload = {
        "version": 1,
        "root": str(root) if root is not None else "",
        "scanned": len(reports),
        "hits": [
            {"path": report.path, "key_path": f.key_path, "reason": f.reason, "value_len": f.value_len}
            for report in reports
            for f in report.findings
            if f.verdict == "hit"
        ],
        "uncertain": [
            {"path": report.path, "key_path": f.key_path, "reason": f.reason}
            for report in reports
            for f in report.findings
            if f.verdict == "uncertain"
        ],
        "warnings": warnings,
        "undecided": [{"path": report.path, "reason": report.problem} for report in undecided],
        "strict": bool(strict),
        "verdict": {EXIT_CLEAN: "CLEAN", EXIT_HIT: "HIT", EXIT_UNDECIDED: "UNDECIDED"}[code],
    }
    return code, payload


def print_human(payload) -> None:
    """Finding lines to stderr, the one-line summary to stdout.

    The value itself is never printed -- only its length. A report that repeats
    what it found has moved the secret into the log.
    """
    for hit in payload["hits"]:
        print(
            "HIT {}:{}:{} ({} character(s) not shown)".format(
                hit["path"], hit["key_path"], hit["reason"], hit["value_len"]
            ),
            file=sys.stderr,
        )
    for item in payload["undecided"]:
        print("UNDECIDED {}:{}".format(item["path"], item["reason"]), file=sys.stderr)
    for item in payload["uncertain"]:
        print("UNCERTAIN {}:{}:{} (not blocking)".format(
            item["path"], item["key_path"], item["reason"]), file=sys.stderr)
    for warning in payload["warnings"]:
        print("WARN {}".format(warning), file=sys.stderr)
    print(
        "scanned={} hit={} uncertain={} undecided={} warning={} verdict={}".format(
            payload["scanned"],
            len(payload["hits"]),
            len(payload["uncertain"]),
            len(payload["undecided"]),
            len(payload["warnings"]),
            payload["verdict"],
        )
    )


# --------------------------------------------------------------------------- #
# Self-test: prove the rules can fire, and can stay quiet
# --------------------------------------------------------------------------- #


def _selftest_expect(failures, label, expected_verdict, reports, root, strict=False):
    code, payload = decide(reports, root=root, strict=strict)
    got = payload["verdict"]
    ok = got == expected_verdict
    print("  {:38s} verdict={:<9s} hit={} uncertain={} (expect {})".format(
        label, got, len(payload["hits"]), len(payload["uncertain"]), expected_verdict))
    if not ok:
        failures.append("{}: expected {} but the scan said {}".format(label, expected_verdict, got))
    return code, payload


def selftest() -> int:
    """Feed the rules files that are wrong on purpose and require it to be said.

    Nothing in the repository is read or touched: the samples are written to a
    temporary directory and scanned through the ``--paths`` code path. A check
    that has never returned a hit is indistinguishable from a check that cannot.
    """
    failures = []

    with tempfile.TemporaryDirectory(prefix="cullinan-config-secrets-") as tmp:
        base = Path(tmp)

        dirty = base / "application.local.json"
        dirty.write_text('{"token": "sk-live-DEADBEEF"}', encoding="utf-8")
        _code, payload = _selftest_expect(
            failures, "plaintext under a sensitive key", "HIT",
            [scan_file(dirty, root=base, allow_git=False)], base)
        if payload["hits"] and payload["hits"][0]["key_path"] != "token":
            failures.append("the hit did not carry the key path 'token'")
        if "sk-live-DEADBEEF" in json.dumps(payload):
            failures.append("the report repeated the value it found")

        clean = base / "application.json"
        clean.write_text('{"token": "${DISCORD_TOKEN}"}', encoding="utf-8")
        _selftest_expect(
            failures, "a single reference", "CLEAN",
            [scan_file(clean, root=base, allow_git=False)], base)

        shaped = base / "application-prod.json"
        shaped.write_text('{"x": "AKIAIOSFODNN7EXAMPLE"}', encoding="utf-8")
        _code, payload = _selftest_expect(
            failures, "a value pattern under an innocent key", "HIT",
            [scan_file(shaped, root=base, allow_git=False)], base)
        if not any(hit["reason"] == "value-pattern:aws-access-key-id" for hit in payload["hits"]):
            failures.append("the AWS access-key shape was not named as the reason")

        pem = base / "application.yaml"
        pem.write_text("cert: |\n  -----BEGIN RSA PRIVATE KEY-----\n", encoding="utf-8")
        _code, payload = _selftest_expect(
            failures, "a block scalar in a line scan", "CLEAN",
            [scan_file(pem, root=base, allow_git=False)], base)
        if not payload["uncertain"]:
            failures.append("a block scalar was neither inspected nor reported as uncertain")

        pem_json = base / "application-cert.json"
        pem_json.write_text(
            '{"cert": "-----BEGIN RSA PRIVATE KEY-----\\nMIIE..."}', encoding="utf-8")
        _code, payload = _selftest_expect(
            failures, "a PEM header in a parsed document", "HIT",
            [scan_file(pem_json, root=base, allow_git=False)], base)
        if not any(hit["reason"] == "value-pattern:pem-private-key" for hit in payload["hits"]):
            failures.append("the PEM header was not named as the reason")

        wrapped = base / "application.toml"
        wrapped.write_text('[token]\nencrypted = "AES256:abc"\n', encoding="utf-8")
        _selftest_expect(
            failures, "the encrypted mapping", "CLEAN",
            [scan_file(wrapped, root=base, allow_git=False)], base)

        typed = base / "application-typed.json"
        typed.write_text('{"token": 42, "password": null, "secret": ""}', encoding="utf-8")
        _selftest_expect(
            failures, "non-string and empty values", "CLEAN",
            [scan_file(typed, root=base, allow_git=False)], base)

        partial = base / "application-partial.json"
        partial.write_text('{"token": "prefix-${VAR}"}', encoding="utf-8")
        _selftest_expect(
            failures, "a partial reference", "CLEAN",
            [scan_file(partial, root=base, allow_git=False)], base)
        _code, payload = _selftest_expect(
            failures, "a partial reference under --strict", "UNDECIDED",
            [scan_file(partial, root=base, allow_git=False)], base, strict=True)
        if not payload["uncertain"]:
            failures.append("a partial reference went unreported")

        broken = base / "application-broken.json"
        broken.write_text('{"token": ', encoding="utf-8")
        _selftest_expect(
            failures, "a file that cannot be parsed", "UNDECIDED",
            [scan_file(broken, root=base, allow_git=False)], base)

        empty_dir = base / "empty"
        empty_dir.mkdir()
        _selftest_expect(
            failures, "no configuration file at all", "CLEAN",
            [scan_file(path, root=base, allow_git=False) for path in iter_targets(empty_dir)], base)

    if failures:
        print("selftest FAILED: {}".format("; ".join(failures)))
        return 1
    print("selftest: every rule returned a hit on a dirty sample and stayed quiet on a clean one")
    return 0


# --------------------------------------------------------------------------- #
# Driver
# --------------------------------------------------------------------------- #


def repo_root(explicit=None) -> Path:
    if explicit:
        return Path(explicit).resolve()
    try:
        completed = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"], capture_output=True, timeout=60
        )
    except (OSError, subprocess.SubprocessError):
        return Path.cwd().resolve()
    if completed.returncode != 0:
        return Path.cwd().resolve()
    text = completed.stdout.decode("utf-8", "replace").strip()
    return Path(text).resolve() if text else Path.cwd().resolve()


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Report plaintext values in application* configuration files."
    )
    parser.add_argument("--root", default=None, help="repository root (default: git toplevel)")
    parser.add_argument(
        "--paths", nargs="*", default=None, metavar="PATH",
        help="scan exactly these files and ignore git (the testing surface)")
    parser.add_argument("--json", action="store_true", help="machine-readable output on stdout")
    parser.add_argument(
        "--strict", action="store_true",
        help="a partial reference is treated as 'could not decide' (exit 2)")
    parser.add_argument("--selftest", action="store_true", help="prove the rules can fire")
    args = parser.parse_args(argv)

    if args.selftest:
        return selftest()

    notes: List[str] = []
    if args.paths is not None:
        base = Path.cwd().resolve()
        targets = iter_targets(base, explicit=args.paths)
        reports = [scan_file(path, root=base, allow_git=False) for path in targets]
        payload_root = base
    else:
        payload_root = repo_root(args.root)
        targets = iter_targets(payload_root, notes=notes)
        reports = [scan_file(path, root=payload_root) for path in targets]

    code, payload = decide(reports, root=payload_root, strict=args.strict,
                           extra_warnings=notes)

    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print_human(payload)
    return code


if __name__ == "__main__":
    sys.exit(main())
