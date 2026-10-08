# -*- coding: utf-8 -*-
"""Mocking a container-owned middleware's dependency through ``TestContext``.

A container-owned middleware is assembled with its declared dependencies already
injected, and those injected attributes are frozen afterwards. A test therefore
cannot swap a dependency by plain assignment: ``middleware.dep = fake`` is
refused by the framework's write guard. ``cullinan.testing.TestContext.mock()``
is the supported way in -- it bypasses the guard for the duration of a block and
restores the original dependency on exit.

These cases pin both halves of that contract for the middleware path:

* while the mock block is active, the instance the pipeline actually runs reads
  the replacement dependency, on both engines;
* outside the block the container's own dependency is back in place;
* a plain assignment of the injected attribute is refused, so a test cannot
  silently reach the middleware's dependency without the supported helper.

Both engines (ASGI and Tornado) drive the one shared ``Dispatcher``, so a case
that reaches both adapters proves engine parity rather than two code paths.
"""
import asyncio
import json

import pytest

from cullinan import configure, get_config
from cullinan.application.legacy import _setup_middleware_pipeline
from cullinan.core import ApplicationContext, set_application_context
from cullinan.core.application_context import _ImmutableAttributeError
from cullinan.core.decorators import component
from cullinan.core.pending import PendingRegistry
from cullinan.testing import TestContext
from cullinan.web.gateway import (
    Dispatcher,
    GatewayMiddleware,
    Router,
    WebResponse,
    get_pipeline,
    reset_gateway,
)
from cullinan.web.middleware import reset_middleware_registry


class _RecordSink:
    """A dependency the middleware declares; injected by the container."""

    def __init__(self):
        self.seen = []


class _RecordingMiddleware(GatewayMiddleware):
    """Reads its injected dependency while a request is in flight."""

    sink: _RecordSink

    async def __call__(self, request, call_next):
        self.sink.seen.append(request.path)
        return await call_next(request)


@pytest.fixture(autouse=True)
def _isolate_state():
    cfg = get_config()
    original = (
        list(cfg.middlewares),
        cfg.builtin_middleware,
        cfg.auto_scan,
        cfg.verbose,
        cfg.startup_error_policy,
    )
    PendingRegistry.reset()
    set_application_context(None)
    reset_gateway()
    reset_middleware_registry()
    yield
    cfg.middlewares = original[0]
    cfg.builtin_middleware = original[1]
    cfg.auto_scan = original[2]
    cfg.verbose = original[3]
    cfg.startup_error_policy = original[4]
    PendingRegistry.reset()
    set_application_context(None)
    reset_gateway()
    reset_middleware_registry()


def _assemble_container_owned_middleware():
    """Declare, refresh and assemble one container-owned middleware."""
    component(_RecordSink)
    component(_RecordingMiddleware)
    ctx = ApplicationContext()
    set_application_context(ctx)
    ctx.refresh()
    configure(middlewares=[_RecordingMiddleware], builtin_middleware=[])
    _setup_middleware_pipeline()

    installed = [entry.middleware for entry in get_pipeline()._entries]
    assert len(installed) == 1
    return ctx, installed[0]


def _dispatch_asgi(app, path):
    sent = []
    messages = [{"type": "http.request", "body": b"", "more_body": False}]

    async def receive():
        if messages:
            return messages.pop(0)
        return {"type": "http.disconnect"}

    async def send(message):
        sent.append(message)

    asyncio.run(
        app(
            {
                "type": "http",
                "asgi": {"version": "3.0"},
                "http_version": "1.1",
                "method": "GET",
                "scheme": "http",
                "path": path,
                "raw_path": path.encode("utf-8"),
                "query_string": b"",
                "headers": [(b"host", b"example.test")],
                "client": ("127.0.0.1", 12345),
                "server": ("example.test", 80),
            },
            receive,
            send,
        )
    )
    return sent


def _asgi_probe():
    from cullinan.transport.adapter import ASGIAdapter

    app = ASGIAdapter(dispatcher=_build_dispatcher()).create_app()
    events = _dispatch_asgi(app, "/probe")
    start = next(event for event in events if event["type"] == "http.response.start")
    body = b"".join(
        event.get("body", b"")
        for event in events
        if event["type"] == "http.response.body"
    )
    return start["status"], body


def _tornado_probe():
    tornado_testing = pytest.importorskip("tornado.testing")
    from cullinan.transport.adapter import TornadoAdapter

    app = TornadoAdapter(dispatcher=_build_dispatcher()).create_app()

    class _Case(tornado_testing.AsyncHTTPTestCase):
        def get_app(self):
            return app

    case = _Case()
    case.setUp()
    try:
        response = case.fetch("/probe")
        return response.code, response.body
    finally:
        case.tearDown()


def _build_dispatcher():
    router = Router()

    async def probe(_request):
        return WebResponse.json({"ok": True})

    router.add_route("GET", "/probe", handler=probe)
    return Dispatcher(router=router, pipeline=get_pipeline(), debug=True)


def _assert_both_engines_ok():
    asgi_status, asgi_body = _asgi_probe()
    tornado_status, tornado_body = _tornado_probe()
    assert asgi_status == 200
    assert tornado_status == 200
    assert json.loads(asgi_body) == {"ok": True}
    assert json.loads(tornado_body) == {"ok": True}


# ---------------------------------------------------------------------------
# Positive: the mock is what the running middleware reads, on both engines
# ---------------------------------------------------------------------------


def test_mock_replaces_the_middleware_dependency_on_both_engines():
    ctx, middleware = _assemble_container_owned_middleware()

    # The assembled middleware carries the container's own dependency.
    container_sink = ctx.get("_RecordSink")
    assert middleware.sink is container_sink

    replacement = _RecordSink()
    with TestContext.mock(middleware, "sink", replacement) as entered:
        assert entered is middleware
        assert middleware.sink is replacement

        _assert_both_engines_ok()

        # The instance the pipeline ran read the replacement, not the container's.
        assert replacement.seen == ["/probe", "/probe"]
        assert container_sink.seen == []


def test_mock_is_scoped_to_the_block_and_restored_on_exit():
    ctx, middleware = _assemble_container_owned_middleware()
    container_sink = ctx.get("_RecordSink")

    replacement = _RecordSink()
    with TestContext.mock(middleware, "sink", replacement):
        _assert_both_engines_ok()
        assert replacement.seen == ["/probe", "/probe"]

    # Outside the block the container's dependency is back in place: the next
    # request is recorded against the original sink, not the replacement.
    assert middleware.sink is container_sink

    _assert_both_engines_ok()

    assert container_sink.seen == ["/probe", "/probe"]
    assert replacement.seen == ["/probe", "/probe"]


# ---------------------------------------------------------------------------
# Negative: a plain assignment of the injected dependency is refused
# ---------------------------------------------------------------------------


def test_direct_assignment_of_the_injected_dependency_is_refused():
    ctx, middleware = _assemble_container_owned_middleware()
    container_sink = ctx.get("_RecordSink")

    # Reaching the dependency by plain assignment is refused by the framework's
    # write guard, so the supported helper is the only way to swap it.
    with pytest.raises(_ImmutableAttributeError):
        middleware.sink = _RecordSink()

    assert middleware.sink is container_sink
