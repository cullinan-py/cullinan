# -*- coding: utf-8 -*-
"""Middleware components obey the existing component scope contract.

A container-owned middleware class is a component like any other: the scope it
declares is honoured by the same scope machinery every component goes through.
This module pins that equivalence -- there is no middleware-specific scope, and
no scope rule is relaxed for the middleware path:

* ``singleton`` (the default) -- the container builds the middleware once, and
  the pipeline runs that single instance on every request, on both engines.
* ``prototype`` -- every lookup produces a fresh instance. Assembly keeps the
  one instance it resolved, and no further lookup happens per request.
* ``request`` -- a request-scoped instance exists only while a request context
  is active, so resolving one during assembly is refused exactly as it is for
  any other component. A singleton may not depend on a request-scoped
  component: the container refuses the graph during ``refresh()`` -- at
  startup, before the application can serve a request.

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
from cullinan.core.diagnostics import ScopeNotActiveError
from cullinan.core.exceptions import LifecycleError, ScopeViolationError
from cullinan.core.pending import PendingRegistry
from cullinan.web.gateway import (
    Dispatcher,
    GatewayMiddleware,
    Router,
    WebResponse,
    get_pipeline,
    reset_gateway,
)
from cullinan.web.middleware import reset_middleware_registry


class _ScopeSink:
    """A dependency the middleware declares; injected by the container."""

    def __init__(self):
        self.seen = []


class _SingletonMiddleware(GatewayMiddleware):
    """Default scope: one container instance serves every request."""

    sink: _ScopeSink
    constructions = 0

    def __init__(self):
        type(self).constructions += 1

    async def __call__(self, request, call_next):
        self.sink.seen.append(request.path)
        return await call_next(request)


class _PrototypeMiddleware(GatewayMiddleware):
    """Prototype scope: each lookup hands back a fresh instance."""

    sink: _ScopeSink
    constructions = 0

    def __init__(self):
        type(self).constructions += 1

    async def __call__(self, request, call_next):
        self.sink.seen.append(request.path)
        return await call_next(request)


class _RequestScopedMiddleware(GatewayMiddleware):
    """Request scope: the instance only exists inside a request context."""

    async def __call__(self, request, call_next):
        return await call_next(request)


class _RequestScopedLeaf:
    """A request-scoped component a singleton is not allowed to depend on."""


class _SingletonDependingOnRequest(GatewayMiddleware):
    """A singleton middleware whose dependency is request-scoped."""

    leaf: _RequestScopedLeaf

    async def __call__(self, request, call_next):
        return await call_next(request)


class _SingletonRelay:
    """A singleton component that reaches a request-scoped leaf transitively."""

    leaf: _RequestScopedLeaf


class _SingletonRelayingMiddleware(GatewayMiddleware):
    """A singleton middleware that reaches the leaf through ``_SingletonRelay``."""

    relay: _SingletonRelay

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
    _SingletonMiddleware.constructions = 0
    _PrototypeMiddleware.constructions = 0
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


def _assert_both_engines_ok():
    asgi_status, _asgi_headers, asgi_body = _asgi_probe()
    tornado_status, _tornado_headers, tornado_body = _tornado_probe()
    assert asgi_status == 200
    assert tornado_status == 200
    assert json.loads(asgi_body) == {"ok": True}
    assert json.loads(tornado_body) == {"ok": True}


# ---------------------------------------------------------------------------
# singleton: one instance, shared by every request on every engine
# ---------------------------------------------------------------------------


def test_singleton_middleware_is_built_once_and_shared_across_engines():
    component(_ScopeSink)
    component(_SingletonMiddleware)
    ctx = _refresh_context()

    configure(middlewares=[_SingletonMiddleware], builtin_middleware=[])
    _setup_middleware_pipeline()

    installed = _installed_middleware()
    assert len(installed) == 1
    assert _SingletonMiddleware.constructions == 1

    # The pipeline runs the container's own instance, and a later lookup is
    # still that same instance -- the singleton scope is not narrowed by the
    # middleware path.
    assert installed[0] is ctx.get("_SingletonMiddleware")

    _assert_both_engines_ok()

    # One instance served both engines (rather than a per-request copy), and its
    # declared dependency is the container's singleton sink.
    assert installed[0].sink is ctx.get("_ScopeSink")
    assert installed[0].sink.seen == ["/probe", "/probe"]
    assert _SingletonMiddleware.constructions == 1


# ---------------------------------------------------------------------------
# prototype: a fresh instance per lookup, no per-request construction
# ---------------------------------------------------------------------------


def test_prototype_middleware_resolves_a_fresh_instance_per_lookup():
    component(_ScopeSink)
    component(_PrototypeMiddleware, scope="prototype")
    ctx = _refresh_context()

    configure(middlewares=[_PrototypeMiddleware], builtin_middleware=[])
    _setup_middleware_pipeline()

    installed = _installed_middleware()
    assert len(installed) == 1
    assembled = installed[0]
    assert _PrototypeMiddleware.constructions == 1

    # A prototype lookup is a new instance -- the container keeps no shared one.
    assert ctx.get("_PrototypeMiddleware") is not assembled
    assert _PrototypeMiddleware.constructions == 2

    _assert_both_engines_ok()

    # Assembly resolved the instance exactly once; the pipeline is the snapshot
    # of that lookup, so serving requests adds no further constructions.
    assert assembled.sink.seen == ["/probe", "/probe"]
    assert _PrototypeMiddleware.constructions == 2


# ---------------------------------------------------------------------------
# request: only resolvable inside a request context
# ---------------------------------------------------------------------------


def test_request_scoped_middleware_cannot_be_assembled_outside_a_request():
    component(_RequestScopedMiddleware, scope="request")
    ctx = _refresh_context()

    # A request-scoped component is unresolved outside an active request context.
    with pytest.raises(ScopeNotActiveError) as excinfo:
        ctx.get("_RequestScopedMiddleware")
    assert excinfo.value.scope_type == "REQUEST"
    assert excinfo.value.dependency_name == "_RequestScopedMiddleware"

    configure(middlewares=[_RequestScopedMiddleware], builtin_middleware=[])

    # Assembly resolves the class during startup, so the same rule applies: the
    # middleware path neither invents nor relaxes scope semantics.
    with pytest.raises(ScopeNotActiveError):
        _setup_middleware_pipeline()

    assert _installed_middleware() == []


# ---------------------------------------------------------------------------
# singleton must not depend on request scope (startup-time refusal)
# ---------------------------------------------------------------------------


def test_singleton_middleware_may_not_depend_on_request_scoped_component():
    component(_RequestScopedLeaf, scope="request")
    component(_SingletonDependingOnRequest)

    ctx = ApplicationContext()
    set_application_context(ctx)

    # The refusal happens during refresh() -- at startup, before any request.
    with pytest.raises(ScopeViolationError) as excinfo:
        ctx.refresh()

    error = excinfo.value
    assert isinstance(error, LifecycleError)
    assert error.dependency_chain == ["_SingletonDependingOnRequest", "_RequestScopedLeaf"]
    assert error.origin_name == "_SingletonDependingOnRequest"
    assert error.violating_component == "_RequestScopedLeaf"


def test_transitively_reached_request_scope_is_also_refused():
    component(_RequestScopedLeaf, scope="request")
    component(_SingletonRelay)
    component(_SingletonRelayingMiddleware)

    ctx = ApplicationContext()
    set_application_context(ctx)

    with pytest.raises(ScopeViolationError) as excinfo:
        ctx.refresh()

    error = excinfo.value
    # The chain spans the offending singleton and the request-scoped leaf.
    assert error.dependency_chain[0] == "_SingletonRelay"
    assert error.dependency_chain[-1] == "_RequestScopedLeaf"
    assert error.origin_name == "_SingletonRelay"
    assert error.violating_component == "_RequestScopedLeaf"
