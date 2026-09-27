# -*- coding: utf-8 -*-
"""Built-in middleware control and the unified legacy bridge.

Two public behaviours are covered here:

* the built-in gateway middleware layer (the access-log middleware) can be
  switched off or replaced through the declarative ``configure(...)`` entry;
* every legacy ``@middleware`` middleware joins the pipeline as its own layer
  and is ordered by the same declarative ``priority`` key as the built-in and
  declared layers, instead of collapsing into one opaque wrapper.

Both engines (ASGI and Tornado) are driven through the single shared
``Dispatcher``, so a test that reaches both adapters proves engine parity rather
than two code paths.
"""
import asyncio
import json
import logging

import pytest

from cullinan import configure, get_config
from cullinan.application.legacy import _setup_middleware_pipeline
from cullinan.support.extensions import reset_extension_registry
from cullinan.web.gateway import (
    Dispatcher,
    GatewayMiddleware,
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


class _TraceGatewayMiddleware(GatewayMiddleware):
    """Stamps a letter so the outer-to-inner order is readable in the response."""

    letter = "?"

    async def __call__(self, request, call_next):
        response = await call_next(request)
        response.set_header("X-Trace", self.letter + (response.get_header("X-Trace") or ""))
        return response


class _DeclaredMiddleware(_TraceGatewayMiddleware):
    letter = "B"


class _ReplacementLogMiddleware(GatewayMiddleware):
    """A drop-in replacement for the built-in access-log layer."""

    def __init__(self):
        self.records = 0

    async def __call__(self, request, call_next):
        self.records += 1
        return await call_next(request)


class _LegacyMiddleware(Middleware):
    """Legacy hook protocol; the letter is a class attribute so it can be registered."""

    letter = "?"

    def process_request(self, request):
        return request

    def process_response(self, request, response):
        response.set_header("X-Trace", self.letter + (response.get_header("X-Trace") or ""))
        return response


class _LegacyOuterMiddleware(_LegacyMiddleware):
    letter = "A"


class _LegacyInnerMiddleware(_LegacyMiddleware):
    letter = "C"


@pytest.fixture(autouse=True)
def _isolate_middleware_state():
    cfg = get_config()
    original = (
        cfg.verbose,
        cfg.auto_scan,
        cfg.startup_error_policy,
        list(cfg.middlewares),
        cfg.builtin_middleware,
    )
    reset_gateway()
    reset_middleware_registry()
    reset_extension_registry()
    yield
    cfg.verbose = original[0]
    cfg.auto_scan = original[1]
    cfg.startup_error_policy = original[2]
    cfg.middlewares = original[3]
    cfg.builtin_middleware = original[4]
    reset_gateway()
    reset_middleware_registry()
    reset_extension_registry()


def _names(pipeline):
    return [entry["name"] for entry in pipeline.list_middleware()]


def _register_legacy():
    """Register two legacy middleware whose declaration contradicts registration order."""
    registry = get_middleware_registry()
    registry.register(_LegacyInnerMiddleware, priority=150)
    registry.register(_LegacyOuterMiddleware, priority=10)


def _build_dispatcher():
    router = Router()

    async def probe_handler(_request):
        return WebResponse.json({"ok": True})

    router.add_route("GET", "/probe", handler=probe_handler)
    return Dispatcher(router=router, pipeline=get_pipeline(), debug=True)


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


class _AccessLogCollector(logging.Handler):
    def __init__(self):
        super().__init__()
        self.records = 0

    def emit(self, record):
        self.records += 1


def _count_access_log_records():
    """Dispatch one real request and count entries on the built-in access logger."""
    access_logger = logging.getLogger("cullinan.access")
    previous_level = access_logger.level
    collector = _AccessLogCollector()
    access_logger.setLevel(logging.INFO)
    access_logger.addHandler(collector)
    try:
        _asgi_probe()
    finally:
        access_logger.removeHandler(collector)
        access_logger.setLevel(previous_level)
    return collector.records


# ---------------------------------------------------------------------------
# Built-in layer: on by default, switch-off-able, replaceable
# ---------------------------------------------------------------------------


def test_default_builtin_layer_is_the_access_log():
    _setup_middleware_pipeline()

    assert _names(get_pipeline()) == ["AccessLogMiddleware"]


def test_default_installs_exactly_one_access_log():
    _setup_middleware_pipeline()

    # One request -> one access-log entry: the default layer is installed once,
    # never doubled up with a declared copy.
    assert _count_access_log_records() == 1


def test_builtin_layer_can_be_switched_off():
    configure(builtin_middleware=[])
    _setup_middleware_pipeline()

    assert "AccessLogMiddleware" not in _names(get_pipeline())
    assert _count_access_log_records() == 0


def test_builtin_layer_can_be_replaced_by_an_equivalent():
    replacement = _ReplacementLogMiddleware()
    configure(builtin_middleware=[replacement])
    _setup_middleware_pipeline()

    names = _names(get_pipeline())
    assert "AccessLogMiddleware" not in names
    assert "_ReplacementLogMiddleware" in names


def test_undeclared_builtin_layer_keeps_the_baseline_behaviour():
    configure(middlewares=[_DeclaredMiddleware()])
    _setup_middleware_pipeline()

    names = _names(get_pipeline())
    # Declared middleware still sits outside the built-in layer by default.
    assert names.index("_DeclaredMiddleware") < names.index("AccessLogMiddleware")


# ---------------------------------------------------------------------------
# Legacy bridge: one entry per middleware, ordered by the declared priority
# ---------------------------------------------------------------------------


def test_each_legacy_middleware_becomes_its_own_entry():
    _register_legacy()
    _setup_middleware_pipeline()

    names = _names(get_pipeline())
    legacy_entries = [name for name in names if name in {"_LegacyOuterMiddleware", "_LegacyInnerMiddleware"}]
    assert len(legacy_entries) == 2, names
    # Not one opaque wrapper standing in for the whole legacy chain.
    assert "LegacyMiddlewareBridge" not in names


def test_declared_priority_orders_legacy_against_the_builtin_layer():
    _register_legacy()
    _setup_middleware_pipeline()

    names = _names(get_pipeline())
    # priority 10 < default 100 -> outer than the built-in layer.
    assert names.index("_LegacyOuterMiddleware") < names.index("AccessLogMiddleware")
    # priority 150 > default 100 -> inner than the built-in layer.
    assert names.index("AccessLogMiddleware") < names.index("_LegacyInnerMiddleware")


def test_legacy_order_follows_the_declaration_not_the_registration_order():
    _register_legacy()
    _setup_middleware_pipeline()

    names = _names(get_pipeline())
    # ``_LegacyOuterMiddleware`` was registered *after* ``_LegacyInnerMiddleware``
    # yet declares the lower priority, so it must still land outermost.
    assert names.index("_LegacyOuterMiddleware") < names.index("_LegacyInnerMiddleware")


def test_reflection_reports_the_real_legacy_layer_name():
    _register_legacy()
    _setup_middleware_pipeline()

    names = _names(get_pipeline())
    assert "_LegacyMiddlewareAdapter" not in names
    assert "_LegacyOuterMiddleware" in names
    assert "_LegacyInnerMiddleware" in names


# ---------------------------------------------------------------------------
# Both engines, one shared pipeline
# ---------------------------------------------------------------------------


def test_unified_order_reaches_both_engines_identically():
    _register_legacy()
    configure(middlewares=[_DeclaredMiddleware()])
    _setup_middleware_pipeline()

    names = _names(get_pipeline())
    assert names.index("_LegacyOuterMiddleware") < names.index("_DeclaredMiddleware")
    assert names.index("_DeclaredMiddleware") < names.index("AccessLogMiddleware")
    assert names.index("AccessLogMiddleware") < names.index("_LegacyInnerMiddleware")

    asgi_status, asgi_headers, asgi_body = _asgi_probe()
    tornado_status, tornado_headers, tornado_body = _tornado_probe()

    assert asgi_status == 200
    assert tornado_status == 200
    # Legacy outer (A) -> declared (B) -> built-in -> legacy inner (C):
    # the response unwinds innermost first, so the header reads "ABC".
    assert asgi_headers["x-trace"] == "ABC"
    assert tornado_headers["x-trace"] == "ABC"
    assert json.loads(asgi_body) == {"ok": True}
    assert json.loads(tornado_body) == {"ok": True}


def test_builtin_off_and_legacy_bridge_reach_both_engines():
    _register_legacy()
    configure(builtin_middleware=[])
    _setup_middleware_pipeline()

    assert "AccessLogMiddleware" not in _names(get_pipeline())

    asgi_status, asgi_headers, _ = _asgi_probe()
    tornado_status, tornado_headers, _ = _tornado_probe()

    assert asgi_status == 200
    assert tornado_status == 200
    assert asgi_headers["x-trace"] == "AC"
    assert tornado_headers["x-trace"] == "AC"
