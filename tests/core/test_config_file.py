# -*- coding: utf-8 -*-
"""Project configuration read from a file.

Two things are being pinned here beyond "it parses":

* **where the file is allowed to live** -- beside the launched executable and in
  the working directory, never inside the installed package. A packaged build
  that read its own bundled config would let a stale copy shadow the file the
  operator edited, and would ship the settings inside the artefact.
* **that secrets are referenced, not stored** -- ``${VAR}`` resolution and the
  decryptor hook exist so a committed file can hold a pointer instead of a value.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from cullinan.support import path_utils
from cullinan.support import config_file


@pytest.fixture()
def config_dir(tmp_path, monkeypatch):
    """An empty working directory, with the config environment cleared."""
    workdir = tmp_path / "work"
    workdir.mkdir()
    monkeypatch.chdir(workdir)
    monkeypatch.delenv(config_file.CONFIG_PATH_ENV, raising=False)
    monkeypatch.delenv(config_file.PROFILE_ENV, raising=False)
    for name in ("SERVER_PORT", "MY_SECRET"):
        monkeypatch.delenv(name, raising=False)
    return workdir


def write(path: Path, data: dict) -> Path:
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def test_no_file_is_not_an_error(config_dir):
    """An application without a config file must run; absence is a valid answer."""
    assert config_file.discover_config_file() is None
    assert config_file.load_project_config() == {}


def test_base_file_is_discovered_in_the_working_directory(config_dir):
    write(config_dir / "application.json", {"server_port": 8080})

    assert config_file.discover_config_file() == config_dir / "application.json"
    assert config_file.load_project_config()["server_port"] == 8080


def test_profile_overlay_merges_over_the_base(config_dir, monkeypatch):
    """A profile file overrides what it names and leaves the rest alone."""
    write(config_dir / "application.json", {"server_port": 8080, "verbose": True})
    write(config_dir / "application-prod.json", {"server_port": 9090})
    monkeypatch.setenv(config_file.PROFILE_ENV, "prod")

    loaded = config_file.load_project_config()

    assert loaded["server_port"] == 9090
    assert loaded["verbose"] is True, "the profile must not drop values it does not mention"


def test_nested_tables_merge_instead_of_replacing(config_dir, monkeypatch):
    write(config_dir / "application.json", {"tls": {"cert": "a.pem", "key": "a.key"}})
    write(config_dir / "application-prod.json", {"tls": {"cert": "b.pem"}})
    monkeypatch.setenv(config_file.PROFILE_ENV, "prod")

    assert config_file.load_project_config()["tls"] == {"cert": "b.pem", "key": "a.key"}


def test_the_package_directory_is_never_searched(config_dir, monkeypatch):
    """The regression that matters for packaging: a bundled file must not win."""
    package_dir = path_utils.get_cullinan_package_path()
    bundled = package_dir / "application.json"
    had_file = bundled.exists()
    try:
        write(bundled, {"server_port": 1111})
        assert config_file.discover_config_file() is None, (
            "a configuration file inside the installed package must not be discovered"
        )
    finally:
        if not had_file:
            bundled.unlink()


def test_file_beside_the_executable_is_found_when_the_cwd_has_none(config_dir, monkeypatch, tmp_path):
    launched = tmp_path / "app"
    launched.mkdir()
    write(launched / "application.json", {"server_port": 7070})
    monkeypatch.setattr(sys, "argv", [str(launched / "main.bin")])
    monkeypatch.setattr(sys, "executable", str(launched / "main.bin"))

    assert config_file.discover_config_file() == launched / "application.json"


def test_explicit_path_wins_and_must_exist(config_dir, tmp_path):
    chosen = write(tmp_path / "custom.json", {"server_port": 6060})

    assert config_file.load_project_config(path=chosen)["server_port"] == 6060
    with pytest.raises(FileNotFoundError):
        config_file.load_project_config(path=tmp_path / "absent.json")


def test_explicit_path_from_the_environment(config_dir, tmp_path, monkeypatch):
    chosen = write(tmp_path / "from-env.json", {"server_port": 5050})
    monkeypatch.setenv(config_file.CONFIG_PATH_ENV, str(chosen))

    assert config_file.load_project_config()["server_port"] == 5050


def test_placeholders_are_resolved_from_the_environment(config_dir, monkeypatch):
    write(config_dir / "application.json", {"token": "${MY_SECRET}", "host": "${MY_HOST:localhost}"})
    monkeypatch.setenv("MY_SECRET", "s3cret")

    loaded = config_file.load_project_config()

    assert loaded["token"] == "s3cret"
    assert loaded["host"] == "localhost"


def test_a_placeholder_without_value_or_default_is_an_error(config_dir):
    """Silently substituting '' would turn a missing setting into a configured one."""
    write(config_dir / "application.json", {"token": "${MY_SECRET}"})

    with pytest.raises(KeyError) as excinfo:
        config_file.load_project_config()

    assert "MY_SECRET" in str(excinfo.value)


def test_decryptor_hook_is_applied_to_wrapped_values(config_dir):
    write(config_dir / "application.json", {"token": {"encrypted": "YWJj"}})

    loaded = config_file.load_project_config(decryptor=lambda payload: f"plain:{payload}")

    assert loaded["token"] == "plain:YWJj"


def test_loading_folds_into_the_global_config(config_dir):
    from cullinan.support import get_config

    original = get_config().server_port
    try:
        write(config_dir / "application.json", {"server_port": 4545})
        config_file.apply_project_config()
        assert get_config().server_port == 4545
    finally:
        get_config().server_port = original


def test_toml_is_read_when_the_interpreter_can(config_dir):
    if sys.version_info < (3, 11):
        pytest.skip("tomllib arrived in 3.11 and tomli is not installed here")
    (config_dir / "application.toml").write_text('server_port = 3030\n', encoding="utf-8")

    assert config_file.load_project_config()["server_port"] == 3030


def test_yaml_without_pyyaml_names_the_missing_package(config_dir):
    try:
        import yaml  # noqa: F401
    except ModuleNotFoundError:
        pass
    else:
        pytest.skip("pyyaml is installed here, so the failure path cannot be exercised")

    (config_dir / "application.yaml").write_text("server_port: 1\n", encoding="utf-8")

    with pytest.raises(RuntimeError) as excinfo:
        config_file.load_project_config()

    assert "pyyaml" in str(excinfo.value)


def test_the_framework_has_no_runtime_dependencies():
    """``python-dotenv`` used to be the one dependency; the config file replaced it."""
    import tomllib

    root = path_utils.get_base_path()
    project = root / "pyproject.toml"
    if not project.is_file():
        pytest.skip("pyproject.toml is not next to the package in this layout")

    data = tomllib.loads(project.read_text(encoding="utf-8"))
    assert data["project"]["dependencies"] == [], (
        "a runtime dependency must be justified; an empty list is the current claim"
    )


_EXAMPLE = Path(__file__).resolve().parents[2] / "examples" / "config_file" / "application.json"


def test_the_shipped_example_falls_back_the_way_its_readme_says(monkeypatch):
    """The example's documented fallback must be the one the shipped file produces.

    Reading the real file is the point of this test. A hand-written sample can agree
    with the README while the example that ships disagrees with both, and that is what
    happened: the file said ``${EXAMPLE_CHANNEL:#general}`` and the README said the
    channel falls back to ``general``. Nothing failed -- the loader did exactly what
    ``${VAR:default}`` means, and ``#general`` is a legitimate default. The two
    statements only disagreed when the shipped file was actually resolved.

    So the anchor is the file, not a copy of it.
    """
    assert _EXAMPLE.is_file(), f"the example is what the page describes: {_EXAMPLE}"

    monkeypatch.delenv("EXAMPLE_CHANNEL", raising=False)

    resolved = config_file.load_project_config(path=_EXAMPLE)

    assert resolved["greeting"]["channel"] == "general"


def test_a_default_is_taken_literally_with_no_prefix_syntax(monkeypatch):
    """``${VAR:x}`` yields ``x``; there is no sigil that means "comment" or "required".

    Worth pinning because a ``#`` in a default reads like a comment marker to anyone
    coming from shell or YAML, and a loader that agreed with that reading would make
    the file mean something different from what it says.
    """
    monkeypatch.delenv("PLACEHOLDER_PROBE", raising=False)

    document = {"value": "${PLACEHOLDER_PROBE:#not-a-comment}"}
    path = Path(_EXAMPLE).with_name("placeholder-literal.json")
    path.write_text(json.dumps(document), encoding="utf-8")
    try:
        resolved = config_file.load_project_config(path=path)
    finally:
        path.unlink()

    assert resolved["value"] == "#not-a-comment"
