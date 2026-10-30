# -*- coding: utf-8 -*-
"""The configuration-value guard: the ignore rules, the checker, and the gate.

Three separate promises are held here, and each can fail on its own:

1. **The default is safe.** A file the loader would read is ignored by git, and the
   template form is not -- so the committable shape holds references instead of
   values. Both directions are checked, because a rule that ignores too much hides
   the template a reader needs.
2. **The checker can tell the two apart.** A plaintext value under a sensitive key
   is reported; a `${VAR}` reference, an encrypted mapping, a non-string value and
   an empty string are not. Without the second half, the first half is a rule that
   fires on the documented correct answer -- the worst kind of check, because it
   teaches the wrong lesson.
3. **The gate reads the checker's answer, and 2 is not a pass.** A checker that is
   absent reports NOT COVERED rather than PASS, and a value planted on disk turns
   the gate red. A gate that is installed but never consulted is the failure mode
   all of this exists to prevent.

Every assertion runs in a subprocess or in a temporary directory. None of them
reads or writes the repository's own configuration, so a developer with a local
`application.local.json` gets the same result as CI.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from scripts import check_config_secrets as ccs
from scripts import gate_pre_push as gate
from scripts import install_pre_push_gate as installer

REPO_ROOT = Path(__file__).resolve().parents[2]
CHECKER = REPO_ROOT / "scripts" / "check_config_secrets.py"
GATE = REPO_ROOT / "scripts" / "gate_pre_push.py"
EXAMPLES = REPO_ROOT / "examples" / "config_file"

#: The value the positive cases plant. It is a placeholder credential -- the
#: repository's checker must find it through the key name, not through a shape
#: added to the pattern table to make this test pass.
PLANTED = "sk-live-DEADBEEF"


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #


def run_checker(*args, cwd=None):
    return subprocess.run(
        [sys.executable, str(CHECKER), *args],
        cwd=str(cwd or REPO_ROOT),
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=180,
    )


def run_gate(*args, cwd=None):
    return subprocess.run(
        [sys.executable, str(GATE), *args],
        cwd=str(cwd or REPO_ROOT),
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=300,
    )


def run_git(cwd, *args):
    try:
        return subprocess.run(
            ["git", *args], cwd=str(cwd), capture_output=True, text=True, timeout=120
        )
    except (OSError, subprocess.SubprocessError) as error:  # pragma: no cover - no git
        pytest.skip("git is required by this guard: {}".format(error))


def write(tmp_path, name, body):
    path = tmp_path / name
    path.write_text(body, encoding="utf-8")
    return path


def is_ignored(relative):
    """Whether the repository's own ``.gitignore`` covers ``relative``."""
    result = run_git(REPO_ROOT, "check-ignore", "-q", "--", relative)
    return result.returncode == 0


def payload_of(result):
    assert result.stdout.strip(), "the checker printed nothing on stdout: {}".format(result.stderr)
    return json.loads(result.stdout)


# --------------------------------------------------------------------------- #
# 1. The default: value-carrying files are ignored, the template is not
# --------------------------------------------------------------------------- #

#: Paths the rules must cover. Every one of them is a name the loader reads:
#: the base file, a profile overlay, a local override, and the other suffixes.
IGNORED_SHAPES = (
    "application.json",
    "application.local.json",
    "application-prod.json",
    "application.toml",
    "application.yaml",
    "application.yml",
    "sub/application.json",
)

#: Paths the rules must leave alone -- otherwise the documented template has
#: nowhere to live and the shipped example disappears from the tree.
TRACKABLE_SHAPES = (
    "application.example.json",
    "application.example.toml",
    "application.example.yaml",
    "application.example.yml",
    "sub/application.example.json",
    "examples/config_file/application.json",
    "examples/config_file/application-prod.json",
    "examples/config_file/application.example.json",
    "README.md",
)


@pytest.mark.parametrize("relative", IGNORED_SHAPES)
def test_a_file_the_loader_reads_is_ignored(relative):
    assert is_ignored(relative), (
        "{} would enter the repository on `git add .`; a file the loader reads is a "
        "file that can carry a value".format(relative)
    )


@pytest.mark.parametrize("relative", TRACKABLE_SHAPES)
def test_the_template_form_and_the_shipped_example_stay_trackable(relative):
    assert not is_ignored(relative), (
        "{} is ignored, so the documented template has nowhere to live".format(relative)
    )


def test_the_rules_name_the_loader_the_repository_ships():
    """The ignore set is checked against the loader's own constants.

    Written this way so the rule text and the loader cannot drift apart: a
    fourth suffix added to ``CONFIG_SUFFIXES`` makes the corresponding ignore
    rule mandatory here rather than a thing someone has to remember.
    """
    from cullinan.support import config_file

    text = (REPO_ROOT / ".gitignore").read_text(encoding="utf-8")
    base = config_file.CONFIG_BASENAME
    missing = [
        "{}{}".format(base, suffix)
        for suffix in config_file.CONFIG_SUFFIXES
        if "{}*{}".format(base, suffix) not in text
    ]
    assert not missing, (
        "the loader reads these suffixes but no ignore rule covers them, so the "
        "ignore surface is narrower than the read surface: {}".format(missing)
    )
    assert text.count("application") >= 1, "the ignore rules no longer mention the base name"


def test_the_ignore_rules_are_not_vacuous(tmp_path):
    """A rule that names a file is not a rule that matches it.

    ``application*.{json,yaml}`` is a plausible-looking line that matches nothing:
    gitignore has no brace expansion. This test builds a scratch repository from
    the repository's own rules and requires each probe to be classified, so a line
    that has silently stopped matching is reported instead of assumed.
    """
    run_git(tmp_path, "init", "-q")
    (tmp_path / ".gitignore").write_text(
        (REPO_ROOT / ".gitignore").read_text(encoding="utf-8"), encoding="utf-8"
    )
    for name in ("application.json", "application.local.json"):
        write(tmp_path, name, '{"server_port": 1}')

    ignored = run_git(tmp_path, "check-ignore", "application.json").returncode == 0
    assert ignored, (
        "the repository's own .gitignore, replayed in a scratch repository, does not "
        "cover application.json -- the rule text is there but matches nothing"
    )


# --------------------------------------------------------------------------- #
# 2. The scan surface: ignored files are read anyway
# --------------------------------------------------------------------------- #


def test_the_scan_surface_includes_a_file_git_ignores(tmp_path):
    """The file most worth reading is the one the ignore rule just started hiding.

    ``git ls-files --others --exclude-standard`` cannot see it, so a scan built on
    that command reports a clean repository while the value sits on disk. This is
    the guard against that implementation, and it fails if the surface is ever
    narrowed to the unignored set.
    """
    run_git(tmp_path, "init", "-q")
    (tmp_path / ".gitignore").write_text("application*.json\n", encoding="utf-8")
    write(tmp_path, "application.local.json", '{"token": "planted"}')

    ignored = run_git(tmp_path, "check-ignore", "-q", "--", "application.local.json")
    assert ignored.returncode == 0, "the probe file must be ignored for this test to mean anything"

    names = [path.name for path in ccs.iter_targets(tmp_path)]
    assert "application.local.json" in names, (
        "an ignored configuration file is not in the scan set, so a planted value "
        "would be reported as a clean repository"
    )
    others = run_git(tmp_path, "ls-files", "--others", "--exclude-standard")
    assert "application.local.json" not in others.stdout, (
        "this test is only meaningful while the candidate implementation cannot see "
        "the file: git now reports it as committable"
    )


# --------------------------------------------------------------------------- #
# 3. The checker fires where it must
# --------------------------------------------------------------------------- #


def test_a_plaintext_value_is_reported_and_never_echoed(tmp_path):
    """The headline case: a value written down is a finding, and it is not printed."""
    target = write(tmp_path, "application.local.json", '{"token": "' + PLANTED + '"}')
    result = run_checker("--paths", str(target))

    assert result.returncode == 1, "a plaintext value did not make the checker exit 1"
    combined = result.stdout + result.stderr
    assert "application.local.json" in combined, "the report does not name the file"
    assert "token" in combined, "the report does not name the key"
    assert PLANTED not in combined, (
        "the report repeated the value it found; a checker that echoes its findings "
        "into a CI log has created a second place for the secret to be"
    )


def test_the_key_path_reaches_a_nested_value(tmp_path):
    target = write(tmp_path, "application.json", '{"discord": {"token": "abc123"}}')
    result = run_checker("--paths", str(target), "--json")

    assert result.returncode == 1
    assert [hit["key_path"] for hit in payload_of(result)["hits"]] == ["discord.token"]


#: The three ways a plaintext configuration value shows up, and why each has to be
#: caught by a *different* rule. A checker that only passes the first one is a
#: checker that recognises a value by what it is called, which is the assumption
#: behind most leaked credentials.
PLAINTEXT_SHAPES = (
    # A sensitive key and a value that looks like a token: the ordinary case.
    ('{"token": "sk-live-DEADBEEF"}', "token", "plaintext-under-sensitive-key"),
    # An innocent key and a value that is a credential by its shape. Nothing about
    # the name gives it away, so this one rests entirely on the value patterns.
    ('{"note": "AKIAIOSFODNN7EXAMPLE"}', "note", "value-pattern:aws-access-key-id"),
    # A sensitive key and a value that looks like nothing in particular. This is
    # the case an entropy score would miss and a value pattern would miss, and it
    # is why the key-name rule exists at all.
    ('{"password": "hunter2"}', "password", "plaintext-under-sensitive-key"),
)


@pytest.mark.parametrize("body,key_path,reason", PLAINTEXT_SHAPES)
def test_each_plaintext_shape_is_caught_by_the_rule_that_can_see_it(tmp_path, body, key_path, reason):
    target = write(tmp_path, "application.json", body)
    result = run_checker("--paths", str(target), "--json")

    assert result.returncode == 1, "{} was not reported".format(body)
    hits = payload_of(result)["hits"]
    assert [(hit["key_path"], hit["reason"]) for hit in hits] == [(key_path, reason)], (
        "{} was reported, but not by the rule that can see it".format(body)
    )


def test_a_credential_shape_is_caught_whatever_the_key_is_called(tmp_path):
    """A value pattern is evidence on its own; the key name is only a hint."""
    target = write(tmp_path, "application.json", '{"x": "AKIAIOSFODNN7EXAMPLE"}')
    result = run_checker("--paths", str(target), "--json")

    assert result.returncode == 1
    reasons = [hit["reason"] for hit in payload_of(result)["hits"]]
    assert reasons == ["value-pattern:aws-access-key-id"], reasons


def test_a_private_key_header_is_caught(tmp_path):
    body = '{"cert": "-----BEGIN RSA PRIVATE KEY-----\\nMIIEowIBAAKCAQEA"}'
    target = write(tmp_path, "application.json", body)
    result = run_checker("--paths", str(target), "--json")

    assert result.returncode == 1
    assert [hit["reason"] for hit in payload_of(result)["hits"]] == ["value-pattern:pem-private-key"]


def test_the_checker_can_prove_it_fires():
    """The synthetic dirty samples are the proof, and they need no repository state."""
    result = run_checker("--selftest")

    assert result.returncode == 0, result.stdout + result.stderr
    assert "selftest:" in result.stdout
    assert "FAILED" not in result.stdout


# --------------------------------------------------------------------------- #
# 3b. Which segment of the key path decides whether a value is a secret
# --------------------------------------------------------------------------- #
#
# A key path can carry the meaning anywhere along it, and the first version of this
# check read only the last segment. That missed an entire shape -- a sensitive
# container holding the value under a name that says nothing -- because the leaf
# name alone cannot clear it: `credentials.value` is a credential and
# `greeting.text` is a greeting, and the difference is one segment up.
#
# The obvious repair, matching the whole path, was rejected: it fires on
# `credentials.endpoint`, `credentials.base_url`, `credentials.username`,
# `credentials.ttl` -- every ordinary setting anyone adds under a container that
# happens to be called `credentials`. That set cannot be listed in advance, and a
# hit blocks a push, so the expensive mistake is the false positive.
#
# What is implemented instead reads the container only when the leaf name is one of
# a short allow-list of names that genuinely carry no meaning. That list can be
# complete, which is why it is the one used. The two tests below exist as a pair on
# purpose: one fails if the miss comes back, the other fails if closing the miss
# starts firing on ordinary settings.


def test_a_neutral_leaf_under_a_sensitive_container_is_caught(tmp_path):
    """Closing the miss. Red if the rule goes back to reading only the last segment."""
    target = write(tmp_path, "application.json", '{"credentials": {"value": "sk-live-DEADBEEF"}}')
    result = run_checker("--paths", str(target), "--json")

    assert result.returncode == 1, "a value under a neutral leaf was not reported"
    hits = payload_of(result)["hits"]
    assert [(hit["key_path"], hit["reason"]) for hit in hits] == [
        ("credentials.value", "plaintext-under-neutral-leaf-of-sensitive-container")
    ]


def test_a_benign_leaf_under_a_sensitive_container_stays_clean(tmp_path):
    """Not over-firing. Red if the rule is widened to match the whole key path."""
    target = write(
        tmp_path, "application.json", '{"credentials": {"endpoint": "https://api.example.com"}}'
    )
    result = run_checker("--paths", str(target), "--json")

    assert result.returncode == 0, (
        "an address under a container called `credentials` was reported, which makes "
        "every ordinary setting under such a container block a push"
    )
    assert payload_of(result)["hits"] == []


#: Ordinary settings that live under a container with a sensitive name, carrying a
#: value that is *not* a URL. The URL case above is cleared by the plain-URL rule
#: whether or not the neutral-leaf gate exists, so it cannot tell the two designs
#: apart; these two can. That distinction is the whole reason the gate exists.
BENIGN_NON_URL_LEAVES = (
    '{"credentials": {"username": "svc-account"}}',
    '{"credentials": {"region": "eu-west-1"}}',
)


@pytest.mark.parametrize("body", BENIGN_NON_URL_LEAVES)
def test_a_benign_leaf_with_a_non_url_value_stays_clean(tmp_path, body):
    """The case that actually separates the two designs.

    Widening the rule to the whole key path fires on these, because the container is
    called `credentials` and nothing else is consulted. That is the false positive
    the neutral-leaf gate exists to prevent -- and unlike a URL, there is no
    plain-URL exemption in the way to mask it.
    """
    target = write(tmp_path, "application.json", body)
    result = run_checker("--paths", str(target), "--json")

    assert result.returncode == 0, (
        "{} was reported; every ordinary setting under a container named "
        "`credentials` would then block a push".format(body)
    )
    assert payload_of(result)["hits"] == []


def test_a_plain_url_is_an_address_not_a_credential(tmp_path):
    """The same neutral leaf, so the container is sensitive; the value decides."""
    target = write(
        tmp_path, "application.json", '{"credentials": {"value": "https://api.example.com"}}'
    )
    result = run_checker("--paths", str(target), "--json")

    assert result.returncode == 0
    assert payload_of(result)["hits"] == []


def test_a_url_carrying_userinfo_is_reported(tmp_path):
    """The credential is in the string itself, so the key name is irrelevant."""
    target = write(tmp_path, "application.json", '{"proxy": "https://user:pass@host:8080/x"}')
    result = run_checker("--paths", str(target), "--json")

    assert result.returncode == 1
    assert [hit["reason"] for hit in payload_of(result)["hits"]] == ["url-carries-userinfo"]


def test_a_plain_url_under_an_innocent_key_is_not_reported(tmp_path):
    """Without this, the userinfo rule could be 'pass' by firing on every URL."""
    target = write(tmp_path, "application.json", '{"homepage": "https://example.com/a@b"}')
    result = run_checker("--paths", str(target), "--json")

    assert result.returncode == 0, "an @ in the path is not userinfo"
    assert payload_of(result)["hits"] == []


#: The documented shapes that must not change when the key-path rule changes, one
#: per rule that is supposed to answer before it does.
UNCHANGED_SHAPES = (
    ('{"token": "sk-live-DEADBEEF"}', 1, "plaintext-under-sensitive-key"),
    ('{"token": "${DISCORD_TOKEN}"}', 0, None),
    ('{"token": {"encrypted": "AES256:x"}}', 0, None),
    ('{"db_password": "abc"}', 1, "plaintext-under-sensitive-key"),
    ('{"X-Api-Key": "abc"}', 1, "plaintext-under-sensitive-key"),
)


@pytest.mark.parametrize("body,expected,reason", UNCHANGED_SHAPES)
def test_the_rules_that_answer_before_the_key_path_still_answer(tmp_path, body, expected, reason):
    """Changing one rule must not quietly change the ones in front of it."""
    target = write(tmp_path, "application.json", body)
    result = run_checker("--paths", str(target), "--json")

    assert result.returncode == expected, "{} changed its verdict".format(body)
    hits = payload_of(result)["hits"]
    assert [hit["reason"] for hit in hits] == ([reason] if reason else []), body


def test_the_neutral_leaf_list_stays_short():
    """A tripwire, not a style rule.

    The allow-list is the only part of this design that can be complete, and it
    stays complete only while it holds names that genuinely say nothing. One that
    keeps growing means it is chasing the false positives the other approach would
    have produced -- at which point the approach has stopped working and the
    decision belongs somewhere else, not in a longer tuple.
    """
    assert len(ccs.NEUTRAL_LEAVES) <= 12, (
        "the neutral-leaf list has grown to {} entries; it is chasing false positives "
        "rather than describing leaf names that carry no meaning".format(
            len(ccs.NEUTRAL_LEAVES))
    )


# --------------------------------------------------------------------------- #
# 4. The checker stays quiet where it must
# --------------------------------------------------------------------------- #


def test_a_single_reference_is_clean(tmp_path):
    """The documented correct answer must not be the thing the gate blocks."""
    target = write(tmp_path, "application.json", '{"token": "${DISCORD_TOKEN}"}')
    result = run_checker("--paths", str(target), "--json")

    assert result.returncode == 0
    payload = payload_of(result)
    assert payload["hits"] == []
    assert payload["verdict"] == "CLEAN"


def test_the_shipped_example_configuration_is_clean():
    result = run_checker(
        "--paths",
        "examples/config_file/application.json",
        "examples/config_file/application-prod.json",
        "examples/config_file/application.example.json",
        "--json",
    )

    assert result.returncode == 0, result.stderr
    payload = payload_of(result)
    assert payload["scanned"] == 3, "the example's own files were not all read"
    assert payload["hits"] == [], payload["hits"]


def test_the_encrypted_mapping_is_clean(tmp_path):
    """``{"encrypted": ...}`` is the ciphertext form the decryptor consumes."""
    target = write(tmp_path, "application.json", '{"token": {"encrypted": "AES256:abc"}}')
    result = run_checker("--paths", str(target), "--json")

    assert result.returncode == 0
    assert payload_of(result)["hits"] == []


def test_non_string_and_empty_values_are_clean(tmp_path):
    target = write(
        tmp_path, "application.json", '{"token": 42, "password": null, "secret": ""}'
    )
    result = run_checker("--paths", str(target), "--json")

    assert result.returncode == 0
    assert payload_of(result)["hits"] == []


def test_a_partial_reference_is_reported_without_blocking(tmp_path):
    """The third answer: a concatenated reference may resolve to a value.

    It cannot be decided statically -- the environment is not visible from here --
    and blocking the legal embedded form would block correct usage. So it is
    reported, it does not change the exit code, and ``--strict`` exists for a
    caller that would rather stop.
    """
    target = write(tmp_path, "application.json", '{"token": "prefix-${VAR}"}')
    result = run_checker("--paths", str(target), "--json")

    assert result.returncode == 0
    payload = payload_of(result)
    assert payload["hits"] == []
    assert [item["reason"] for item in payload["uncertain"]] == ["partial-placeholder"], (
        "a partial reference went unreported, so the run would be green and silent"
    )

    strict = run_checker("--paths", str(target), "--strict")
    assert strict.returncode == 2, "under --strict an undecided value must not exit 0"


def test_a_file_that_cannot_be_parsed_is_undecided_not_clean(tmp_path):
    """``2`` is not a pass: a file nobody could read has not been cleared."""
    target = write(tmp_path, "application.json", '{"token": ')
    result = run_checker("--paths", str(target), "--json")

    assert result.returncode == 2
    payload = payload_of(result)
    assert payload["verdict"] == "UNDECIDED"
    assert payload["undecided"]


# --------------------------------------------------------------------------- #
# 5. The rules agree with the loader
# --------------------------------------------------------------------------- #


def test_the_reference_rule_matches_the_loader():
    """The checker's idea of a reference must be the loader's idea of one.

    The pattern is copied rather than imported -- the checker has to run where the
    framework is not installed -- so the copy can drift. Comparing the two by
    behaviour over a generated corpus turns that drift into a red test; comparing
    the pattern text would not, because the two differ in capturing groups while
    accepting exactly the same strings.
    """
    from cullinan.support import config_file

    names = ("VAR", "_x", "A1", "1A", "", " ", "a b", "with-hyphen")
    forms = (
        "${{{0}}}",
        "${{{0}:}}",
        "${{{0}:default}}",
        "${{{0}:-x}}",
        "${{{0}:a:b}}",
        "prefix-${{{0}}}",
        "${{{0}}}-suffix",
        "${{{0}}}{{{0}}}}}",
        "${{{0}",
        "{{{0}}}",
    )
    corpus = ["plain", "", "${}", "${ }", "${A}", "${A}${B}"]
    for name in names:
        for form in forms:
            corpus.append(form.format(name))

    disagreements = [
        sample
        for sample in corpus
        if bool(ccs.PLACEHOLDER_FULL.fullmatch(sample))
        != bool(config_file._PLACEHOLDER.fullmatch(sample))
    ]
    assert not disagreements, (
        "the checker and the loader disagree about whether these are references: "
        "{}".format(disagreements)
    )


def test_the_reference_comparison_can_fail():
    """A narrower rule disagrees on the corpus, so the comparison has teeth."""
    from cullinan.support import config_file

    dropped_default = re.compile(r"\$\{[A-Za-z_][A-Za-z0-9_]*\}$")
    assert bool(config_file._PLACEHOLDER.fullmatch("${A:default}"))
    assert not dropped_default.fullmatch("${A:default}")
    assert dropped_default.fullmatch("${A}")


# --------------------------------------------------------------------------- #
# 6. The gate: M10 is wired, ordered, and can turn red
# --------------------------------------------------------------------------- #


def test_m10_is_appended_after_m9_rather_than_listed_with_the_rest():
    """``GATES`` is invoked before M9's special branch, so M10 must not live there.

    Listing it would print M8, M10, M9 -- an output order that contradicts the
    numbers a reader is following, in the one place a reader is counting.
    """
    assert "M10" not in [gate_id for gate_id, _ in gate.GATES]
    assert gate.MARKER == "CULLINAN PRE-PUSH GATE"
    assert gate.GATE_VERSION == "1.1"


def test_the_gate_runs_m10_and_reports_how_many_files_it_read():
    result = run_gate("--only", "M0,M10", "--json")

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert [item["gate"] for item in payload["results"]] == ["M0", "M10"], (
        "M10 did not run last, or did not run at all"
    )
    detail = payload["results"][1]["detail"]
    assert payload["results"][1]["status"] == "PASS"
    assert "scanned=" in detail, (
        "'0 hits' without a file count cannot be told apart from '0 files read': "
        + detail
    )


def test_a_planted_value_turns_the_gate_red(tmp_path):
    """The end-to-end assertion: the gate reads the checker, and the checker fires."""
    (tmp_path / "scripts").mkdir()
    shutil.copyfile(CHECKER, tmp_path / "scripts" / "check_config_secrets.py")
    write(tmp_path, "application.local.json", '{"token": "' + PLANTED + '"}')

    result = run_gate("--repo", str(tmp_path), "--only", "M10")

    assert result.returncode == 1, "a planted value did not stop the gate"
    assert "FAIL" in result.stdout
    assert "application.local.json" in result.stdout
    assert PLANTED not in result.stdout, "the gate echoed the value it found"


def test_a_missing_checker_is_not_covered_rather_than_a_pass(tmp_path):
    """An absent component is a gap in the machine's configuration, not a finding.

    It is still never reported as PASS: the summary reads PARTIAL, and ``--strict``
    -- what CI uses -- turns it into a failing exit.
    """
    write(tmp_path, "application.json", '{"token": "${TOKEN}"}')

    relaxed = run_gate("--repo", str(tmp_path), "--only", "M10")
    assert relaxed.returncode == 0
    assert "NOT COVERED" in relaxed.stdout
    assert "RESULT: PARTIAL" in relaxed.stdout
    assert "RESULT: PASS" not in relaxed.stdout

    strict = run_gate("--repo", str(tmp_path), "--only", "M10", "--strict")
    assert strict.returncode == 1


def test_the_gate_self_test_reaches_m10():
    """A gate that is wired but whose checker cannot fire is wired to nothing."""
    result = run_gate("--selftest")

    assert result.returncode == 0, result.stdout[-1500:] + result.stderr[-500:]
    assert "M10 checker selftest" in result.stdout


# --------------------------------------------------------------------------- #
# 7. The hook recognises the marker it wrote before
# --------------------------------------------------------------------------- #


LEGACY_MARKER = installer.LEGACY_MARKERS[0]


def test_the_installer_still_recognises_the_previous_marker():
    assert installer.hook_identity("# CULLINAN PRE-PUSH GATE\n") == "ours"
    assert installer.hook_identity("#!/bin/sh\n# {} -- dispatcher\n".format(LEGACY_MARKER)) == (
        "ours-legacy"
    )
    assert installer.hook_identity("#!/bin/sh\n# somebody else\nexit 0\n") == "foreign"


def test_a_hook_written_under_the_previous_marker_can_still_be_removed(tmp_path):
    """The migration's whole point: an installed hook is not orphaned by a rename.

    Before the marker stopped carrying the gate count, an added gate made the
    installed hook look foreign, and ``--uninstall`` refused to touch it.
    """
    run_git(tmp_path, "init", "-q")
    hooks = tmp_path / ".git" / "hooks"
    hooks.mkdir(parents=True, exist_ok=True)
    legacy = hooks / "pre-push"
    legacy.write_text(
        "#!/bin/sh\n# {} -- dispatcher installed by an older version\nexit 0\n".format(
            LEGACY_MARKER
        ),
        encoding="utf-8",
    )

    message = installer.Installer(repo=str(tmp_path)).uninstall()

    assert "refusing" not in message, message
    assert not legacy.exists(), "the legacy hook survived an uninstall"


def test_installing_over_a_legacy_hook_upgrades_it_without_a_second_backup(tmp_path):
    run_git(tmp_path, "init", "-q")
    (tmp_path / "scripts").mkdir()
    shutil.copyfile(GATE, tmp_path / "scripts" / "gate_pre_push.py")
    hooks = tmp_path / ".git" / "hooks"
    hooks.mkdir(parents=True, exist_ok=True)
    (hooks / "pre-push").write_text(
        "#!/bin/sh\n# {} -- dispatcher installed by an older version\nexit 0\n".format(
            LEGACY_MARKER
        ),
        encoding="utf-8",
    )

    message = installer.Installer(repo=str(tmp_path)).install()

    assert "upgrade" in message, message
    assert not (hooks / installer.BACKUP_NAME).exists(), (
        "a hook this installer wrote was preserved as somebody else's, so the backup "
        "slot is now occupied by our own file"
    )
    assert installer.MARKER in (hooks / "pre-push").read_text(encoding="utf-8")
    assert (hooks / installer.SNAPSHOT_NAME).is_file(), "the snapshot was not refreshed"


# --------------------------------------------------------------------------- #
# 8. The two guides say it, in both languages
# --------------------------------------------------------------------------- #

ANCHORS_EN = (
    "**Do not write a value into the file.**",
    "**The file is ignored by default.**",
    "**Do not `print` it either.**",
)
ANCHORS_ZH = (
    "**不要把一个值写进文件。**",
    "**该文件默认被忽略。**",
    "**也不要 `print` 它。**",
)


def missing_anchors(text, anchors):
    return [anchor for anchor in anchors if anchor not in text]


def test_both_guides_carry_the_three_warnings():
    english = (REPO_ROOT / "docs" / "configuration.md").read_text(encoding="utf-8")
    chinese = (REPO_ROOT / "docs" / "zh" / "configuration.md").read_text(encoding="utf-8")

    assert not missing_anchors(english, ANCHORS_EN), (
        "docs/configuration.md no longer says what the ignore rules and the print rule "
        "are: {}".format(missing_anchors(english, ANCHORS_EN))
    )
    assert not missing_anchors(chinese, ANCHORS_ZH), (
        "docs/zh/configuration.md no longer says what the ignore rules and the print "
        "rule are: {}".format(missing_anchors(chinese, ANCHORS_ZH))
    )


def test_the_anchor_check_is_not_vacuous():
    assert missing_anchors("", ANCHORS_EN) == list(ANCHORS_EN)
    assert missing_anchors(ANCHORS_EN[0], ANCHORS_EN) == list(ANCHORS_EN[1:])
