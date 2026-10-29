# -*- coding: utf-8 -*-
"""Packaging detection: Nuitka does not always set ``sys.frozen``.

The failure these tests pin down is not "a path is wrong" but "the whole
packaging branch is unreachable, so every path silently falls back to the
development answer". A onefile build then reports the directory it unpacked
itself into -- a temp directory removed on exit -- as the place to write logs and
read configuration. Nothing raises; the logs simply are not there afterwards.

Each test builds the layout a onefile run actually sees: the launched executable
in one directory, the running copy unpacked in another.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from cullinan.support import path_utils


@pytest.fixture()
def onefile_layout(tmp_path, monkeypatch):
    """A launched binary and an unpacked copy of it, as onefile presents them."""
    launched = tmp_path / "app"
    unpacked = tmp_path / "unpacked"
    launched.mkdir()
    unpacked.mkdir()

    (launched / "main.bin").write_text("launcher", encoding="utf-8")
    (launched / ".env").write_text("SERVER_PORT=9999\n", encoding="utf-8")
    (unpacked / "main.bin").write_text("running copy", encoding="utf-8")

    monkeypatch.setattr(sys, "executable", str(unpacked / "main.bin"))
    monkeypatch.setattr(sys, "argv", [str(launched / "main.bin")])
    monkeypatch.delenv("APP_DATA_DIR", raising=False)
    monkeypatch.delenv("APP_EXE_DIR", raising=False)
    for name in path_utils._ONEFILE_ENV_MARKERS:
        monkeypatch.delenv(name, raising=False)
    # The packers are simulated through their markers; make sure neither leaks in.
    monkeypatch.delattr(sys, "frozen", raising=False)
    monkeypatch.delattr(sys, "_MEIPASS", raising=False)
    return launched, unpacked


def test_import_time_mode_is_development_in_a_plain_interpreter():
    """The suite itself runs unpackaged; packaging must not be inferred from nothing."""
    assert path_utils.get_packaging_mode() == "development"
    assert path_utils.is_frozen() is False
    assert path_utils.is_nuitka_compiled() is False


def test_nuitka_onefile_env_marker_is_enough(onefile_layout, monkeypatch):
    """``sys.frozen`` absent, an onefile marker present: still packaged."""
    launched, unpacked = onefile_layout
    monkeypatch.setenv("NUITKA_ONEFILE_PARENT", "14767")

    assert path_utils.is_frozen() is True
    assert path_utils.is_nuitka_compiled() is True
    assert path_utils.get_packaging_mode() == "nuitka_onefile"
    assert Path(path_utils.get_base_path()) == unpacked
    assert path_utils.get_original_executable_dir() == launched
    assert path_utils.get_executable_dir() == launched


def test_nuitka_module_marker_is_enough(onefile_layout, monkeypatch):
    """No env marker at all -- only the marker Nuitka injects into compiled modules."""
    launched, unpacked = onefile_layout
    monkeypatch.setitem(vars(path_utils), "__compiled__", object())

    assert path_utils.is_nuitka_compiled() is True
    assert path_utils.get_packaging_mode() == "nuitka_onefile"
    assert path_utils.get_executable_dir() == launched


def test_user_data_dir_is_never_the_unpacked_directory(onefile_layout, monkeypatch):
    """The regression that cost the reporter their logs: data dir inside the bundle."""
    launched, unpacked = onefile_layout
    monkeypatch.setenv("NUITKA_ONEFILE_PARENT", "14767")

    data_dir = path_utils.get_user_data_dir()

    assert data_dir == launched
    assert not path_utils._is_within(data_dir, unpacked), (
        "a frozen run must not be told to keep data inside the directory the packer "
        "deletes on exit"
    )


def test_app_data_dir_override_wins(onefile_layout, monkeypatch, tmp_path):
    """An explicit answer beats every guess, including the launched directory."""
    chosen = tmp_path / "chosen"
    monkeypatch.setenv("NUITKA_ONEFILE_PARENT", "14767")
    monkeypatch.setenv("APP_DATA_DIR", str(chosen))

    assert path_utils.get_user_data_dir() == chosen


def test_app_exe_dir_override_wins(onefile_layout, monkeypatch, tmp_path):
    chosen = tmp_path / "exe-dir"
    monkeypatch.setenv("NUITKA_ONEFILE_PARENT", "14767")
    monkeypatch.setenv("APP_EXE_DIR", str(chosen))

    assert path_utils.get_original_executable_dir() == chosen


def test_config_beside_the_binary_is_found_first(onefile_layout, monkeypatch):
    """A file next to the launched binary must not lose to a copy inside the bundle.

    This is the search-order half of the same incident: the unpacked directory
    used to lead, so a stale file shipped inside the bundle shadowed the one the
    operator edited.
    """
    launched, unpacked = onefile_layout
    monkeypatch.setenv("NUITKA_ONEFILE_PARENT", "14767")
    (unpacked / ".env").write_text("SERVER_PORT=4080\n", encoding="utf-8")

    found = path_utils.find_file_with_fallbacks(".env")

    assert found == launched / ".env"


def test_pyinstaller_is_not_mistaken_for_nuitka(tmp_path, monkeypatch):
    """The two packers must stay separable; they disagree about where the code is."""
    monkeypatch.setattr(sys, "executable", str(tmp_path / "app.exe"))
    monkeypatch.setattr(sys, "_MEIPASS", str(tmp_path / "meipass"), raising=False)
    monkeypatch.setattr(sys, "argv", [str(tmp_path / "app.exe")])
    monkeypatch.delenv("NUITKA_ONEFILE_PARENT", raising=False)

    assert path_utils.is_pyinstaller_frozen() is True
    assert path_utils.get_packaging_mode().startswith("pyinstaller_")


def test_diagnostics_report_the_evidence(onefile_layout, monkeypatch):
    """ "Why did it decide that?" must be answerable from the log alone."""
    monkeypatch.setenv("NUITKA_ONEFILE_PARENT", "14767")

    info = path_utils.get_path_info()

    assert info["packaging_mode"] == "nuitka_onefile"
    assert info["is_onefile"] is True
    assert "NUITKA_ONEFILE_PARENT" in info["detection_evidence"]
    assert info["original_executable_dir"]


def test_env_file_beside_the_binary_is_found(onefile_layout, monkeypatch, tmp_path):
    """The working directory holds no config in a service; the executable's does."""
    launched, _unpacked = onefile_layout
    monkeypatch.setenv("NUITKA_ONEFILE_PARENT", "14767")
    monkeypatch.delenv("APP_ENV_FILE", raising=False)
    elsewhere = tmp_path / "cwd"
    elsewhere.mkdir()
    monkeypatch.chdir(elsewhere)

    assert path_utils.find_env_file() == launched / ".env"


def test_env_file_prefers_the_working_directory(onefile_layout, monkeypatch):
    """An operator who starts the process from a configured directory meant it."""
    launched, _unpacked = onefile_layout
    monkeypatch.setenv("NUITKA_ONEFILE_PARENT", "14767")
    monkeypatch.delenv("APP_ENV_FILE", raising=False)
    monkeypatch.chdir(launched)

    assert path_utils.find_env_file() == launched / ".env"


def test_env_file_override_is_honoured(onefile_layout, monkeypatch, tmp_path):
    launched, _unpacked = onefile_layout
    chosen = tmp_path / "custom.env"
    chosen.write_text("SERVER_PORT=1\n", encoding="utf-8")
    monkeypatch.setenv("NUITKA_ONEFILE_PARENT", "14767")
    monkeypatch.setenv("APP_ENV_FILE", str(chosen))

    assert path_utils.find_env_file() == chosen


def test_missing_env_file_is_reported_as_none(onefile_layout, monkeypatch, tmp_path):
    """Absence must be answerable, not guessed at by the caller."""
    _launched, _unpacked = onefile_layout
    (onefile_layout[0] / ".env").unlink()
    monkeypatch.setenv("NUITKA_ONEFILE_PARENT", "14767")
    monkeypatch.delenv("APP_ENV_FILE", raising=False)
    elsewhere = tmp_path / "empty"
    elsewhere.mkdir()
    monkeypatch.chdir(elsewhere)

    assert path_utils.find_env_file() is None
