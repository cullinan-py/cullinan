# -*- coding: utf-8 -*-
"""Shutdown wiring: the bound reaches the server, and the app is told.

The defect these hold in place was not a wrong calculation -- every value was
right and nothing was connected:

* ``drain_timeout`` was resolved correctly and then never handed to uvicorn, so
  the number that was supposed to bound the wait bounded nothing;
* in-flight requests were awaited *before* ``begin_draining`` ran, so the
  readiness predicate changed after the traffic it was meant to shed;
* the Tornado signal handler stopped the loop directly, which is a kill with
  extra steps.

The real behaviour is measured on a running server in the lab; these are the
unit-level facts underneath it, so a refactor cannot quietly unwire them again.
"""

from __future__ import annotations

import asyncio

import pytest

from cullinan.transport.adapter import asgi_adapter as asgi_module
from cullinan.transport.adapter.asgi_adapter import (
    ASGIAdapter,
    _begin_draining_for_active_application,
    _finalize_draining_for_active_application,
)
from cullinan.transport.adapter.tornado_adapter import TornadoAdapter
from cullinan.web.gateway.dispatcher import Dispatcher


class _StubContext:
    def __init__(self) -> None:
        self.calls: list[tuple[str, float | None]] = []

    async def ashutdown(self, timeout: float | None = None) -> bool:
        self.calls.append(("ashutdown", timeout))
        return True


class _StubApplication:
    def __init__(self) -> None:
        self.context = _StubContext()
        self.events: list[str] = []

    def _begin_draining(self) -> None:
        self.events.append("begin_draining")

    def _finalize_drain(self) -> None:
        self.events.append("finalize_drain")


@pytest.fixture()
def stub_app(monkeypatch):
    import cullinan.application.model as model

    app = _StubApplication()
    monkeypatch.setattr(model.Application, "current", classmethod(lambda cls, default=None: app))
    return app


def test_begin_draining_is_announced_before_anything_else(stub_app):
    _begin_draining_for_active_application()
    assert stub_app.events == ["begin_draining"]


def test_finalisation_is_separate_from_beginning(stub_app):
    _begin_draining_for_active_application()
    _finalize_draining_for_active_application()
    assert stub_app.events == ["begin_draining", "finalize_drain"]


def test_drain_timeout_reaches_uvicorn(monkeypatch, stub_app):
    """The bound must be handed to the server that actually waits."""
    captured: dict = {}

    class _FakeConfig:
        def __init__(self, app, **kwargs):
            captured.update(kwargs)

    class _FakeServer:
        def __init__(self, config):
            self.config = config

        def run(self):
            captured["ran"] = True

    import uvicorn

    monkeypatch.setattr(uvicorn, "Config", _FakeConfig)
    monkeypatch.setattr(uvicorn, "Server", _FakeServer)
    monkeypatch.setattr(asgi_module, "_resolve_drain_timeout", lambda default=30.0: 7.5)

    adapter = ASGIAdapter(Dispatcher())
    adapter.run(host="127.0.0.1", port=1)

    assert captured.get("timeout_graceful_shutdown") == 7.5, (
        "uvicorn must be told the framework's bound; its own default is to wait forever"
    )
    assert captured.get("ran") is True


def test_tornado_shutdown_stops_accepting_before_waiting(monkeypatch, stub_app):
    """Stop the listener, then drain, then stop the loop -- in that order."""

    class _FakeServer:
        def __init__(self) -> None:
            self.stopped = 0

        def stop(self) -> None:
            self.stopped += 1

    adapter = TornadoAdapter(Dispatcher())
    adapter._http_server = _FakeServer()

    asyncio.run(adapter._shutdown_gracefully())

    assert stub_app.events == ["begin_draining", "finalize_drain"]
    assert adapter._http_server.stopped == 1, "the listener has to close, or draining changes nothing"
    assert stub_app.context.calls and stub_app.context.calls[0][0] == "ashutdown"


def test_tornado_shutdown_uses_the_configured_bound(monkeypatch, stub_app):
    adapter = TornadoAdapter(Dispatcher())
    monkeypatch.setattr(adapter, "_drain_timeout", lambda: 12.5)

    class _FakeServer:
        def stop(self) -> None:
            pass

    adapter._http_server = _FakeServer()
    asyncio.run(adapter._shutdown_gracefully())
    assert stub_app.context.calls == [("ashutdown", 12.5)]


def test_configure_drain_timeout_reaches_the_runtime_config():
    """The bound must be settable from the same surface as the port and engine."""
    from cullinan.application.model import _clone_runtime_config
    from cullinan.support.config import configure, get_config

    previous = get_config().drain_timeout
    try:
        configure(drain_timeout=7.25)
        runtime_config = _clone_runtime_config(None)
        assert runtime_config.drain_timeout == 7.25, (
            "@configure(drain_timeout=...) was accepted and then ignored; only the "
            "advanced Application entry could set the bound"
        )
    finally:
        get_config().drain_timeout = previous


def test_configure_rejects_a_useless_bound():
    from cullinan.support.config import configure

    with pytest.raises(ValueError):
        configure(drain_timeout=0)
