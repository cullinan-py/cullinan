# -*- coding: utf-8 -*-
"""Which engine is running, and which layer chose it -- printed at start-up.

Four layers can name the engine: the ``run()`` argument, ``CULLINAN_ENGINE``, the
configuration file's ``server_engine`` and ``configure(server_engine=...)``. When
two of them disagree, the honest question ("why is this process on uvicorn?") has
no answer that does not involve reading the source -- and the wrong answer is
expensive, because two runs meant to compare engines can both be the same engine
and the difference observed between them is then imagined.

One of the four is a naming trap rather than a setting: ``SERVER_ENGINE`` is not
read by anything, while ``SERVER_HOST`` and ``SERVER_PORT`` are. Setting the wrong
one is silent, so the start-up path says so out loud.
"""

from __future__ import annotations

import logging

import pytest

from cullinan.application import public as public_api
from cullinan.application.public import _announce_engine
from cullinan.support.config import get_config

LOGGER = "cullinan.application.public"


@pytest.fixture(autouse=True)
def _clean_engine_environment(monkeypatch):
    """No ambient engine setting can decide a case by accident."""
    monkeypatch.delenv("CULLINAN_ENGINE", raising=False)
    monkeypatch.delenv("SERVER_ENGINE", raising=False)
    previous = get_config().server_engine
    get_config().server_engine = "auto"
    try:
        yield
    finally:
        get_config().server_engine = previous


def _line(caplog) -> str:
    lines = [record.getMessage() for record in caplog.records if record.name == LOGGER]
    assert lines, f"nothing was logged by {LOGGER}: {[r.name for r in caplog.records]}"
    return "\n".join(lines)


def test_the_run_argument_is_named_as_the_source(caplog):
    with caplog.at_level(logging.INFO, logger=LOGGER):
        engine = _announce_engine("tornado", {})

    assert engine == "tornado"
    assert "Web engine: tornado (decided by: run(engine='tornado'))" in _line(caplog)


def test_the_environment_variable_is_named_as_the_source(monkeypatch, caplog):
    monkeypatch.setenv("CULLINAN_ENGINE", "tornado")

    with caplog.at_level(logging.INFO, logger=LOGGER):
        engine = _announce_engine(None, {})

    assert engine == "tornado"
    assert "decided by: environment (CULLINAN_ENGINE)" in _line(caplog)


def test_the_configuration_file_is_named_as_the_source(caplog):
    # ``apply_project_config()`` has already folded the file into the config when
    # this is asked, so the file's value is what ``get_config()`` holds.
    get_config().server_engine = "tornado"

    with caplog.at_level(logging.INFO, logger=LOGGER):
        engine = _announce_engine(None, {"server_engine": "tornado", "server_port": 8080})

    assert engine == "tornado"
    assert "decided by: configuration file (server_engine)" in _line(caplog)


def test_the_default_is_named_as_the_source(caplog):
    with caplog.at_level(logging.INFO, logger=LOGGER):
        engine = _announce_engine(None, {})

    assert engine in {"asgi", "tornado"}, "auto resolves to an installed engine"
    assert "decided by: built-in default (auto)" in _line(caplog)


def test_a_value_written_in_code_is_named_as_its_own_source(caplog):
    """``configure(server_engine=...)`` is a fourth layer, not "the default".

    Reporting it as the default would be the same class of mistake as the page
    that described the wrong precedence: the value is right and the attribution is
    wrong, which is worse than not printing anything.
    """
    get_config().server_engine = "tornado"

    with caplog.at_level(logging.INFO, logger=LOGGER):
        _announce_engine(None, {})

    assert "decided by: configure(server_engine=...)" in _line(caplog)


def test_a_variable_that_is_not_read_is_reported(monkeypatch, caplog):
    monkeypatch.setenv("SERVER_ENGINE", "tornado")

    with caplog.at_level(logging.WARNING, logger=LOGGER):
        _announce_engine(None, {})

    messages = [record.getMessage() for record in caplog.records if record.levelno >= logging.WARNING]
    assert any("SERVER_ENGINE" in message and "CULLINAN_ENGINE" in message for message in messages), (
        "a deployment that sets SERVER_ENGINE must be told it is not the variable this "
        f"framework reads: {messages}"
    )


def test_nothing_is_reported_when_the_right_variable_is_used(monkeypatch, caplog):
    monkeypatch.setenv("CULLINAN_ENGINE", "tornado")
    monkeypatch.setenv("SERVER_ENGINE", "asgi")

    with caplog.at_level(logging.WARNING, logger=LOGGER):
        _announce_engine(None, {})

    assert not [r for r in caplog.records if r.levelno >= logging.WARNING]


def _entry():
    from cullinan import application, configure

    @configure(user_packages=["tests.helpers"])
    @application
    def entry():
        ...

    return entry


def test_run_prints_the_line_without_starting_a_server(monkeypatch, caplog):
    """The wiring, not just the helper: ``run()`` is what a deployment calls."""
    from cullinan.transport.adapter.tornado_adapter import TornadoAdapter

    served: list = []
    monkeypatch.setenv("CULLINAN_ENGINE", "tornado")
    monkeypatch.setattr(TornadoAdapter, "run", lambda self, **kwargs: served.append(kwargs))
    monkeypatch.setattr(public_api, "_finalize_public_runtime", lambda: ([], {}))

    application = None
    try:
        with caplog.at_level(logging.INFO, logger=LOGGER):
            application = public_api.run(_entry())
    finally:
        if application is not None:
            application.uninstall()

    assert served, "the adapter was never asked to serve"
    assert "decided by: environment (CULLINAN_ENGINE)" in _line(caplog)
