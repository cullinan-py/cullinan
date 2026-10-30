# -*- coding: utf-8 -*-
"""The TLS fixtures are pinned by content, and the secret scanner watches that place.

Why two mechanisms instead of one
---------------------------------
The handshake suite needs a private key committed to the repository, because CI has
no `openssl` and a mocked handshake would prove nothing about the engine. "Committed
on purpose" is therefore a claim, and a claim with nothing checking it is how a real
key ends up where a test fixture belongs: the framework's own secret scan walks
configuration files **by name** (`application*.json|toml|yaml|yml`), and
`tests/fixtures/tls/server.key` is not one of those names. Measured, before this
file existed: replacing that key with an unrelated PEM left the scanner at
`scanned=3, verdict=CLEAN`.

So there are two checks, and they fail differently on purpose:

* this file pins the **sha256 of each fixture file**. Any byte changing -- a
  regenerated certificate, an appended newline, a swapped key -- is red, and the
  message names the file and both fingerprints;
* `scripts/check_config_secrets.py` gains a second surface: a PEM private-key block
  under `tests/fixtures/` is a **hit** unless its sha256 is in that script's
  `FIXTURE_KEY_FINGERPRINTS`. That one fires even when nobody runs this suite.

The pin is not a ban on regenerating: `tests/fixtures/tls/README.md` documents the
`openssl` commands, and regenerating means updating both tables in the same commit,
so the diff shows the change. What it forbids is the silent swap.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from scripts import check_config_secrets as ccs

REPO_ROOT = Path(__file__).resolve().parents[2]
TLS_DIR = REPO_ROOT / "tests" / "fixtures" / "tls"

#: sha256 of every certificate and key the TLS suite uses. Two independent tables
#: exist on purpose -- this one covers the public material as well (a certificate
#: nobody pins can be swapped for one signed by another CA), the scanner's covers
#: only what it can act on (private keys). A test below holds them consistent.
PINNED = {
    "ca.crt": "d9c8c64ff2bf2e3103a6bfecad0516d00191df257b51af15f7ced2a0d81ca7ec",
    "ca.key": "9f54852ad678c4c70416afe13310099370c57e82b80639c46f9f5aa423260b99",
    "server.crt": "c048fc2a05341d97628387fe248fb641475b22239b07c07c8d7dc97c840dc0e7",
    "server.key": "4088ffe8cd631fc0c873c8cedbb95b147f46cc99183aff6d8a0abe867c851a4c",
    "client.crt": "8b94e69c5b72ab02902932c6844d8c074a463ff9e31b6caafdb02ecc058c65ba",
    "client.key": "c8fd50ed2364ea3b0ce89cadbd5dc1e26398724a1cfc6f2341d73ca4d4d48c09",
}

A_PEM_THAT_IS_NOT_A_FIXTURE = (
    "-----BEGIN RSA PRIVATE KEY-----\n"
    "MIIBOgIBAAJBAKj34GkxFhD90vcNLYLInFEX6Ppy1tPf9Cnzj4p4WGeKLs1Pt8Qu\n"
    "-----END RSA PRIVATE KEY-----\n"
)


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


@pytest.mark.parametrize("name", sorted(PINNED))
def test_each_fixture_file_is_byte_identical_to_the_pinned_one(name):
    path = TLS_DIR / name
    assert path.is_file(), f"{path} is gone; the TLS suite cannot run without it"
    actual = _digest(path)
    assert actual == PINNED[name], (
        f"{name} changed.\n  pinned: {PINNED[name]}\n  found : {actual}\n"
        "If this is a deliberate regeneration, update PINNED in this file AND "
        "FIXTURE_KEY_FINGERPRINTS in scripts/check_config_secrets.py in the same "
        "commit, so the change is visible in the diff. If it is not deliberate, "
        "something was put where a test fixture belongs."
    )


def test_no_certificate_or_key_appears_that_is_not_pinned():
    """A new unpinned file in the fixtures directory is also a change worth seeing."""
    unexpected = sorted(
        path.name
        for path in TLS_DIR.iterdir()
        if path.is_file() and path.suffix.lower() in (".crt", ".key", ".pem")
        and path.name not in PINNED
    )
    assert not unexpected, (
        f"unpinned key material in {TLS_DIR.name}/: {unexpected}; add it to PINNED "
        "(and to the scanner's table if it carries a private key) or remove it"
    )


def test_the_scanner_knows_exactly_the_pinned_private_keys():
    """The two tables must not drift: the scanner's allowlist *is* these three files."""
    known = dict(ccs.FIXTURE_KEY_FINGERPRINTS)
    assert set(known.values()) == {
        f"tests/fixtures/tls/{name}" for name in PINNED if name.endswith(".key")
    }, (
        "scripts/check_config_secrets.py and this file disagree about which private "
        f"keys are pinned: scanner={sorted(known.values())}"
    )
    for digest, relative in known.items():
        assert _digest(REPO_ROOT / relative) == digest, (
            f"the scanner's fingerprint for {relative} is stale"
        )


def test_the_scanner_fires_on_a_private_key_it_does_not_know(tmp_path):
    """The rule, exercised on a tree shaped like this repository.

    Not a mock of the rule: a real directory layout, the real walker, the real
    classifier, and a PEM that is not one of the pinned ones.
    """
    planted = tmp_path / ccs.FIXTURE_ROOT / "tls"
    planted.mkdir(parents=True)
    (planted / "server.key").write_text(A_PEM_THAT_IS_NOT_A_FIXTURE, encoding="utf-8")

    targets = ccs.iter_fixture_pem_targets(tmp_path)
    assert [path.name for path in targets] == ["server.key"], (
        f"the fixture walker did not find the planted key: {targets}"
    )

    report = ccs.scan_fixture_pem(targets[0], tmp_path)
    hits = [finding for finding in report.findings if finding.verdict == "hit"]
    assert hits, "an unknown private key under the fixtures was not reported"
    assert "not one of the pinned ones" in hits[0].reason, (
        f"reported for the wrong reason: {hits[0].reason}"
    )


def test_a_public_certificate_with_no_private_key_is_not_reported(tmp_path):
    """The second surface must stay about private keys, not about the directory."""
    planted = tmp_path / ccs.FIXTURE_ROOT / "tls"
    planted.mkdir(parents=True)
    (planted / "other.crt").write_text(
        "-----BEGIN CERTIFICATE-----\nMIIB\n-----END CERTIFICATE-----\n", encoding="utf-8"
    )

    targets = ccs.iter_fixture_pem_targets(tmp_path)
    assert [path.name for path in targets] == ["other.crt"]
    assert ccs.scan_fixture_pem(targets[0], tmp_path).findings == [], (
        "a certificate carrying no private key was reported; the rule would then fire "
        "on every public fixture and get switched off"
    )


def test_the_repository_itself_scans_clean():
    """The two surfaces together, on this tree: nothing to report, and both seen."""
    reports = [
        ccs.scan_fixture_pem(path, REPO_ROOT) for path in ccs.iter_fixture_pem_targets(REPO_ROOT)
    ]
    findings = [finding for report in reports for finding in report.findings]
    assert findings == [], f"the committed fixtures did not scan clean: {findings}"
    assert reports, "the fixture surface found no files at all, so it would prove nothing"
