# -*- coding: utf-8 -*-
"""Container ownership for the legacy ``@middleware`` path.

A class registered through ``@middleware(priority=...)`` used to be constructed
with a bare ``middleware_class()`` call owned by no one, so a middleware that
declared dependencies received none. The application container now creates the
instance, the same way it creates a class passed to
``configure(middlewares=[...])``: declared dependencies are injected, the
instance installed on the pipeline is the container's own, and an unresolvable
dependency fails while the application is assembled rather than on the first
request.

The declaration does not change -- ``@middleware(priority=...)`` keeps its
syntax and its default -- and the registry still works stand-alone, where there
is no refreshed container to create the instance.

Four properties are pinned here:

* the container creates and injects the legacy instance, without any extra
  declaration on the middleware class;
* an unresolvable declared dependency fails at assembly, never lazily;
* with no refreshed container the registry keeps constructing plainly;
* the container-created instance is the one that runs, on both engines.
"""
import asyncio

import pytest

from cullinan import configure, get_config
from cullinan.application.legacy import _setup_middleware_pipeline
from cullinan.core import ApplicationContext, set_application_context
from cullinan.core.decorators import component
from cullinan.core.exceptions import DependencyResolutionError
from cullinan.core.pending import PendingRegistry
from cullinan.web.gateway import (
    Dispatcher,
    Router,
    WebResponse,
    get_pipeline,
    reset_gateway,
)
from cullinan.web.middleware import (
    Middleware,
    get_middleware_registry,
    reset_middleware_registry,
)


class _LegacySink:
    """A dependency the middleware declares; injected by the container."""

    def __init__(self):
        self.seen = []


class _TagMiddleware(Middleware):
    """Legacy hook middleware with a declared dependency and no ``@component``.

    The point of the legacy path is that the declaration does not change, so
    this class is *not* declared with ``@component``: the container still creates
    it and injects the dependency it declares.
    """

    sink: _LegacySink

    def process_request(self, request):
        self.sink.seen.append(request.path)
        request.attributes["owned"] = True
        return request

    def process_response(self, request, response):
        response.set_header("X-Legacy-Owned", "1")
        return response


class _AbsentDependency:
    """Never registered -- used to prove the assembly-time failure."""


class _NeedsAbsentDependency(Middleware):
    missing: _AbsentDependency

    def process_request(self, request):
        return request


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


def _register_component(cls):
    """Declare a plain test class with ``@component`` in the fresh registry."""
    return component(cls)


def _refresh_context() -> ApplicationContext:
    ctx = ApplicationContext()
    set_application_context(ctx)
    ctx.refresh()
    return ctx


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


def _build_dispatcher():
    router = Router()

    async def probe(_request):
        return WebResponse.json({"ok": True})

    router.add_route("GET", "/probe", handler=probe)
    return Dispatcher(router=router, pipeline=get_pipeline(), debug=True)


def _asgi_probe():
    from cullinan.transport.adapter import ASGIAdapter

    app = ASGIAdapter(dispatcher=_build_dispatcher()).create_app()
    events = _dispatch_asgi(app, "/probe")
    start = next(event for event in events if event["type"] == "http.response.start")
    headers = {
        name.decode("latin-1").lower(): value.decode("latin-1")
        for name, value in start.get("headers", [])
    }
    return start["status"], headers


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
        headers = {name.lower(): value for name, value in response.headers.items()}
        return response.code, headers
    finally:
        case.tearDown()


# ---------------------------------------------------------------------------
# The container creates and injects the legacy instance
# ---------------------------------------------------------------------------


def test_legacy_middleware_is_created_by_the_container_with_injection():
    _register_component(_LegacySink)
    ctx = _refresh_context()

    get_middleware_registry().register(_TagMiddleware, priority=50)
    ordered = get_middleware_registry().iter_ordered_middleware()

    assert len(ordered) == 1
    priority, instance = ordered[0]
    assert priority == 50
    # The declared dependency was injected -- without the middleware declaring
    # ``@component`` itself.
    assert isinstance(instance.sink, _LegacySink)
    assert instance.sink is ctx.get("_LegacySink")


# ---------------------------------------------------------------------------
# Negative: an unresolvable dependency fails at assembly, not on a request
# ---------------------------------------------------------------------------


def test_unresolvable_dependency_fails_at_assembly_not_on_first_request():
    _refresh_context()
    get_middleware_registry().register(_NeedsAbsentDependency, priority=50)

    with pytest.raises(DependencyResolutionError):
        get_middleware_registry().iter_ordered_middleware()


# ---------------------------------------------------------------------------
# Negative: with no refreshed container the registry still works stand-alone
# ---------------------------------------------------------------------------


def test_registry_still_constructs_without_a_refreshed_container():
    set_application_context(None)
    get_middleware_registry().register(_NeedsAbsentDependency, priority=50)

    ordered = get_middleware_registry().iter_ordered_middleware()

    assert len(ordered) == 1
    assert isinstance(ordered[0][1], _NeedsAbsentDependency)


# ---------------------------------------------------------------------------
# Execution: the container instance runs, on both engines
# ---------------------------------------------------------------------------


def test_container_owned_legacy_middleware_runs_on_both_engines():
    _register_component(_LegacySink)
    ctx = _refresh_context()

    configure(middlewares=[], builtin_middleware=[])
    get_middleware_registry().register(_TagMiddleware, priority=50)
    _setup_middleware_pipeline()

    asgi_status, asgi_headers = _asgi_probe()
    tornado_status, tornado_headers = _tornado_probe()

    assert asgi_status == 200
    assert tornado_status == 200
    assert asgi_headers["x-legacy-owned"] == "1"
    assert tornado_headers["x-legacy-owned"] == "1"

    # The middleware that ran is the container instance, and it observed both
    # engines: the same assembled pipeline drives the one shared dispatcher.
    assert ctx.get("_LegacySink").seen == ["/probe", "/probe"]
