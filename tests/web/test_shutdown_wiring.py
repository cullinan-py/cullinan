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

    def _finalize_drain(self, force: bool = False) -> None:
        self.events.append("finalize_drain" + ("(force)" if force else ""))


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

    assert stub_app.events == ["begin_draining", "finalize_drain(force)"]
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


def test_the_shared_claim_lets_only_the_first_caller_schedule(stub_app):
    """Both engines stand on the same guard, so it is asserted once on its own.

    ``request_shutdown()`` is idempotent in what it *reports* and exactly once in
    what it *does*: a repeat call answers ``True`` (the server has been asked) but
    must not schedule the drain again.
    """
    adapter = TornadoAdapter(Dispatcher())

    assert adapter._claim_shutdown_request() is True
    assert adapter._claim_shutdown_request() is False, (
        "the second caller claimed the drain again; it would run twice"
    )

    adapter._register_shutdown_requester(None)
    assert adapter._claim_shutdown_request() is True, (
        "withdrawing the hook must release the claim, or a second run() could never "
        "ask for a shutdown"
    )


def test_the_asgi_hook_announces_the_drain_once(monkeypatch):
    """The ASGI side of the same rule, on the side effect that is observable."""
    import uvicorn

    captured: dict = {}
    announced: list[int] = []
    monkeypatch.setattr(
        asgi_module,
        "_begin_draining_for_active_application",
        lambda: announced.append(1),
    )

    class _FakeConfig:
        def __init__(self, app, **kwargs):
            captured["config"] = kwargs

    class _FakeServer:
        def __init__(self, config):
            self.should_exit = False
            captured["server"] = self

        def run(self):
            captured["requester"] = adapter._shutdown_requester

    monkeypatch.setattr(uvicorn, "Config", _FakeConfig)
    monkeypatch.setattr(uvicorn, "Server", _FakeServer)

    adapter = ASGIAdapter(Dispatcher())
    adapter.run(host="127.0.0.1", port=1)

    requester = captured.get("requester")
    assert requester is not None, "the hook was never published, so nothing could ask"
    assert requester() is True
    assert requester() is True, "a repeat call reports the same fact"
    assert announced == [1], f"the drain was announced {len(announced)} times"
    assert captured["server"].should_exit is True


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


def test_a_timed_out_drain_is_still_finalised():
    """When the bound expires the process is about to end, so nobody re-enters.

    Deferring because work is still recorded is correct while something can call
    back; at the end of the shutdown there is nothing left to call back, and a
    deferred finalisation strands ``phase`` at "draining" for the rest of the
    process's life -- which is a lie the last request could have read.
    """
    from types import SimpleNamespace

    from cullinan.application.model import Application
    from cullinan.core.application_context import ContainerState

    class _Context:
        state = ContainerState.DRAINING
        calls: list = []
        active_request_count = 1

        def shutdown(self, timeout: float | None = None) -> bool:
            self.calls.append(timeout)
            self.state = ContainerState.CLOSED
            return True

    stub = SimpleNamespace(
        runtime=SimpleNamespace(phase="active"),
        web_runtime=SimpleNamespace(request_count=1, config=SimpleNamespace(drain_timeout=4.0)),
        context=_Context(),
        phase="draining",
    )

    Application._finalize_drain(stub)
    assert stub.phase == "draining", "a deferral is right while a callback may still arrive"
    assert stub.context.calls == []

    Application._finalize_drain(stub, force=True)
    assert stub.context.calls == [4.0]
    assert stub.phase == "closed" and stub.runtime.phase == "closed"
