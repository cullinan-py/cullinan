# -*- coding: utf-8 -*-
"""The precedence order the configuration page states, measured rather than trusted.

`docs/configuration.md` publishes a five-layer table, and an earlier revision of it
described the opposite order: it put `configure(...)` above the project file, while
the file is applied *after* the values declared in code. A reader who planned a
rollback around the page ("change the code, not the file") would have found out in
production which one won.

So the table gets an executor. The assertions are on what `run()` actually does with
each source, not on the order in which the source reads the same variables: the
values below are all different, and the one that reaches the adapter is the one the
table says wins.

What is *not* changed here is behaviour. The order was already "the file wins", and
this file pins it so a future tidy-up cannot quietly restore the order the old page
described.
"""

from __future__ import annotations

import json

import pytest

from cullinan.application import public as public_api
from cullinan.support.config import get_config

CODE_PORT = 4100
FILE_PORT = 4200
ENV_PORT = 4300


@pytest.fixture()
def clean_environment(monkeypatch):
    """No ambient source can decide a case by accident, and the config is restored."""
    previous = get_config().server_port
    monkeypatch.delenv("SERVER_PORT", raising=False)
    monkeypatch.delenv("CULLINAN_CONFIG", raising=False)
    monkeypatch.delenv("CULLINAN_PROFILE", raising=False)
    try:
        yield
    finally:
        get_config().server_port = previous


def _entry(port: int):
    """An entry method that declares a bind port in code."""
    from cullinan import application, configure

    @configure(user_packages=["tests.helpers"], server_port=port)
    @application
    def entry():
        ...

    return entry


def _run_capturing(monkeypatch, entry) -> dict:
    """Call ``run()`` and return the arguments it handed to the adapter."""
    from cullinan.transport.adapter.tornado_adapter import TornadoAdapter

    served: list[dict] = []
    monkeypatch.setenv("CULLINAN_ENGINE", "tornado")
    monkeypatch.setattr(TornadoAdapter, "run", lambda self, **kwargs: served.append(kwargs))
    monkeypatch.setattr(public_api, "_finalize_public_runtime", lambda: ([], {}))

    application = None
    try:
        application = public_api.run(entry)
    finally:
        if application is not None:
            application.uninstall()

    assert served, "run() never asked an adapter to serve, so nothing was measured"
    return served[0]


def test_the_configuration_file_wins_over_the_value_written_in_code(
    monkeypatch, tmp_path, clean_environment
):
    """Row 3 beats row 4 -- the claim the earlier revision of the page got backwards."""
    config_file = tmp_path / "application.json"
    config_file.write_text(json.dumps({"server_port": FILE_PORT}), encoding="utf-8")
    monkeypatch.setenv("CULLINAN_CONFIG", str(config_file))

    served = _run_capturing(monkeypatch, _entry(CODE_PORT))

    assert served["port"] == FILE_PORT, (
        f"the file's {FILE_PORT} lost to the code's {CODE_PORT}; the configuration page "
        "lists the file above configure(...) and that order is what rollbacks rely on"
    )


def test_the_value_written_in_code_wins_when_there_is_no_file(
    monkeypatch, tmp_path, clean_environment
):
    """With no file, row 4 is the decider -- not the built-in default."""
    served = _run_capturing(monkeypatch, _entry(CODE_PORT))

    assert served["port"] == CODE_PORT, (
        f"without a configuration file the value in code must be used; got {served['port']}"
    )


def test_an_environment_variable_wins_over_both(monkeypatch, tmp_path, clean_environment):
    """Row 2 is read at use time, so it beats the file and the code alike."""
    config_file = tmp_path / "application.json"
    config_file.write_text(json.dumps({"server_port": FILE_PORT}), encoding="utf-8")
    monkeypatch.setenv("CULLINAN_CONFIG", str(config_file))

    served = _run_capturing(monkeypatch, _entry(CODE_PORT))
    assert served["port"] == FILE_PORT  # the baseline this case departs from

    monkeypatch.setenv("SERVER_PORT", str(ENV_PORT))
    served = _run_capturing(monkeypatch, _entry(CODE_PORT))

    assert served["port"] == ENV_PORT, (
        f"SERVER_PORT={ENV_PORT} did not win over the file and the code; got {served['port']}"
    )
