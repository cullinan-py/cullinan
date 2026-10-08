# -*- coding: utf-8 -*-
"""Container ownership for the two declarative middleware forms.

A middleware **instance** passed to ``configure(middlewares=[...])`` stays owned
by the caller. A middleware **class** is container-owned: it must be declared
with ``@component``, and the instance the container creates -- with its declared
dependencies injected -- is the one installed on the pipeline. The pipeline and
the container therefore share a single instance, and an unresolvable dependency
fails at startup rather than on the first request.

Both engines (ASGI and Tornado) drive the one shared ``Dispatcher``, so a case
that reaches both adapters proves engine parity rather than two code paths.
"""
import asyncio
import json

import pytest

from cullinan import configure, get_config
from cullinan.application.legacy import _setup_middleware_pipeline
from cullinan.core import ApplicationContext, set_application_context
from cullinan.core.decorators import component
from cullinan.core.exceptions import DependencyResolutionError
from cullinan.core.pending import PendingRegistry
from cullinan.support.exceptions import ConfigurationError
from cullinan.web.gateway import (
    Dispatcher,
    GatewayMiddleware,
    Router,
    WebResponse,
    get_pipeline,
    reset_gateway,
)
from cullinan.web.middleware import reset_middleware_registry


class _AuditSink:
    """A dependency the middleware declares; injected by the container."""

    def __init__(self):
        self.seen = []


class _ContainerOwnedMiddleware(GatewayMiddleware):
    """Class form: the container creates and injects this instance."""

    sink: _AuditSink

    async def __call__(self, request, call_next):
        self.sink.seen.append(request.path)
        response = await call_next(request)
        response.set_header("X-Owned", "1")
        return response


class _AbsentDependency:
    """Never registered -- used to prove the startup-time failure."""


class _NeedsAbsentDependency(GatewayMiddleware):
    missing: _AbsentDependency

    async def __call__(self, request, call_next):
        return await call_next(request)


class _PlainMiddleware(GatewayMiddleware):
    """A gateway middleware without a container declaration."""

    async def __call__(self, request, call_next):
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


def _register_component(cls):
    """Declare a plain test class with ``@component`` inside a fresh registry.

    The classes are defined at module level so their identities (and the type
    hint cache keyed on them) stay stable; registration is done per test, after
    the registry has been reset.
    """
    return component(cls)


def _refresh_context() -> ApplicationContext:
    ctx = ApplicationContext()
    set_application_context(ctx)
    ctx.refresh()
    return ctx


def _installed_middleware():
    return [entry.middleware for entry in get_pipeline()._entries]


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
    headers = {
        name.decode("latin-1").lower(): value.decode("latin-1")
        for name, value in start.get("headers", [])
    }
    body = b"".join(
        event.get("body", b"")
        for event in events
        if event["type"] == "http.response.body"
    )
    return start["status"], headers, body


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
        return response.code, headers, response.body
    finally:
        case.tearDown()


def _build_dispatcher():
    router = Router()

    async def probe(_request):
        return WebResponse.json({"ok": True})

    router.add_route("GET", "/probe", handler=probe)
    return Dispatcher(router=router, pipeline=get_pipeline(), debug=True)


# ---------------------------------------------------------------------------
# Registration: a @component class is created by the container
# ---------------------------------------------------------------------------


def test_component_middleware_class_is_installed_by_the_container():
    _register_component(_AuditSink)
    _register_component(_ContainerOwnedMiddleware)
    ctx = _refresh_context()

    configure(middlewares=[_ContainerOwnedMiddleware])
    _setup_middleware_pipeline()

    names = [entry["name"] for entry in get_pipeline().list_middleware()]
    assert "_ContainerOwnedMiddleware" in names
    assert ctx.has("_ContainerOwnedMiddleware")


def test_instance_middleware_stays_caller_owned():
    owned = _ContainerOwnedMiddleware.__new__(_ContainerOwnedMiddleware)
    owned.sink = _AuditSink()

    configure(middlewares=[owned], builtin_middleware=[])
    _setup_middleware_pipeline()

    assert _installed_middleware() == [owned]


# ---------------------------------------------------------------------------
# Dependency injection: declared dependencies are resolved by the container
# ---------------------------------------------------------------------------


def test_declared_dependency_is_injected_by_the_container():
    _register_component(_AuditSink)
    _register_component(_ContainerOwnedMiddleware)
    ctx = _refresh_context()

    configure(middlewares=[_ContainerOwnedMiddleware], builtin_middleware=[])
    _setup_middleware_pipeline()

    # The instance actually installed on the pipeline has its declared
    # dependency injected -- and it is the container's own sink.
    installed = _installed_middleware()
    assert len(installed) == 1
    assert isinstance(installed[0].sink, _AuditSink)
    assert installed[0].sink is ctx.get("_AuditSink")


# ---------------------------------------------------------------------------
# Identity: the pipeline runs the container instance, never a second one
# ---------------------------------------------------------------------------


def test_pipeline_uses_the_container_instance():
    _register_component(_AuditSink)
    _register_component(_ContainerOwnedMiddleware)
    ctx = _refresh_context()

    configure(middlewares=[_ContainerOwnedMiddleware], builtin_middleware=[])
    _setup_middleware_pipeline()

    installed = _installed_middleware()
    assert len(installed) == 1
    assert installed[0] is ctx.get("_ContainerOwnedMiddleware")


def test_builtin_class_entry_is_also_container_owned():
    _register_component(_AuditSink)
    _register_component(_ContainerOwnedMiddleware)
    ctx = _refresh_context()

    configure(builtin_middleware=[_ContainerOwnedMiddleware])
    _setup_middleware_pipeline()

    installed = _installed_middleware()
    assert len(installed) == 1
    assert installed[0] is ctx.get("_ContainerOwnedMiddleware")


# ---------------------------------------------------------------------------
# Execution: the container instance runs, on both engines
# ---------------------------------------------------------------------------


def test_container_owned_middleware_runs_on_both_engines():
    _register_component(_AuditSink)
    _register_component(_ContainerOwnedMiddleware)
    ctx = _refresh_context()

    configure(middlewares=[_ContainerOwnedMiddleware], builtin_middleware=[])
    _setup_middleware_pipeline()

    asgi_status, asgi_headers, asgi_body = _asgi_probe()
    tornado_status, tornado_headers, tornado_body = _tornado_probe()

    assert asgi_status == 200
    assert tornado_status == 200
    assert asgi_headers["x-owned"] == "1"
    assert tornado_headers["x-owned"] == "1"
    assert json.loads(asgi_body) == {"ok": True}
    assert json.loads(tornado_body) == {"ok": True}

    # The middleware that ran is the container instance, and it observed both.
    assert ctx.get("_ContainerOwnedMiddleware").sink.seen == ["/probe", "/probe"]


# ---------------------------------------------------------------------------
# Negative: a class without a container declaration is refused
# ---------------------------------------------------------------------------


def test_class_without_component_declaration_is_refused():
    configure(middlewares=[_PlainMiddleware])

    with pytest.raises(ConfigurationError) as excinfo:
        _setup_middleware_pipeline()

    assert excinfo.value.error_code == "MIDDLEWARE_DECLARATION_ERROR"
    assert "@component" in str(excinfo.value)


def test_builtin_class_without_component_declaration_is_refused():
    configure(builtin_middleware=[_PlainMiddleware])

    with pytest.raises(ConfigurationError) as excinfo:
        _setup_middleware_pipeline()

    assert excinfo.value.error_code == "MIDDLEWARE_DECLARATION_ERROR"


# ---------------------------------------------------------------------------
# Startup failure: an unresolvable dependency surfaces at assembly, not later
# ---------------------------------------------------------------------------


def test_unresolvable_dependency_fails_at_startup_not_on_first_request():
    """A class-owned middleware cannot defer its dependency failure.

    The dependency of a container-owned middleware is resolved during startup
    assembly; an unresolvable one fails there, before the application can serve
    a request -- never lazily on the first request.
    """
    _register_component(_NeedsAbsentDependency)
    ctx = ApplicationContext()
    set_application_context(ctx)

    with pytest.raises(DependencyResolutionError):
        ctx.refresh()
