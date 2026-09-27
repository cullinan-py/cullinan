# -*- coding: utf-8 -*-
"""Ordering invariants for the unified middleware pipeline (both engines).

The unified bridge folds legacy ``@middleware`` classes into the same
declarative ``priority`` order as the declared and built-in layers. Four
invariants pin down that behaviour; each is exercised through *both* engines
(ASGI and Tornado) because they share a single ``Dispatcher`` — a test that
reaches only one adapter cannot catch a regression in the shared core.

1. **Registration order is not an input when the priorities differ.** The same
   declarations of legacy middleware whose priorities are pairwise distinct
   produce the same resolved order no matter in which order they were
   registered: swapping the two registrations leaves ``list_middleware()``
   byte-for-byte identical. This is what stops the order from depending on
   *when* a middleware happened to be registered. The scope is pairwise-distinct
   priorities: when two peers share a priority, the tie instead follows their
   declaration order — see invariant 4.

2. **A default-priority legacy layer stays inside the built-in layer.** A
   legacy middleware that declares no priority (so it keeps the default `100`)
   always resolves *inside* the built-in access-log layer — the same relative
   placement it had before the bridge was expanded.

3. **The default path keeps the pre-expansion layering.** With no explicit
   priority anywhere, the expanded order is exactly the long-standing
   declaration/assembly order; collapsing the expanded legacy layers back into
   a single bridge token reproduces the pre-expansion layering one-to-one.

4. **Same-priority peers keep their declaration order.** When two legacy
   middleware declare the *same* priority they are peers, and the tie between
   them is broken by their declaration (registration) order — a deterministic
   order, not a shuffle. This is the boundary of invariant 1: pairwise-distinct
   priorities never depend on registration order, but same-priority peers do.

Public paths covered: ``configure(middlewares=[...])``,
``MiddlewarePipeline.list_middleware()``, the legacy ``@middleware`` registry
and the ASGI / Tornado adapters.
"""
import asyncio
import json

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


# ---------------------------------------------------------------------------
# Test middleware
# ---------------------------------------------------------------------------


class _DeclaredTraceMiddleware(GatewayMiddleware):
    """Declared through ``configure(middlewares=...)``; unwinds with letter ``B``."""

    async def __call__(self, request, call_next):
        response = await call_next(request)
        response.set_header("X-Trace", "B" + (response.get_header("X-Trace") or ""))
        return response


class _LegacyMiddleware(Middleware):
    """Legacy hook protocol; stamps a letter so the resolved order is readable."""

    letter = "?"

    def process_request(self, request):
        return request

    def process_response(self, request, response):
        response.set_header(
            "X-Trace", self.letter + (response.get_header("X-Trace") or "")
        )
        return response


class _LegacyLowPriorityMiddleware(_LegacyMiddleware):
    """Declares ``priority=10`` — must land outside the built-in layer."""

    letter = "O"


class _LegacyHighPriorityMiddleware(_LegacyMiddleware):
    """Declares ``priority=150`` — must land inside the built-in layer."""

    letter = "I"


class _LegacyDefaultPriorityMiddleware(_LegacyMiddleware):
    """Declares no priority — keeps the default ``100``."""

    letter = "D"


class _LegacySecondDefaultMiddleware(_LegacyMiddleware):
    """A second default-priority legacy layer, registered after the first."""

    letter = "E"


class _LegacyTieFirstMiddleware(_LegacyMiddleware):
    """Default priority; declared before the other peer of the same priority."""

    letter = "1"


class _LegacyTieSecondMiddleware(_LegacyMiddleware):
    """Default priority; declared after the other peer of the same priority."""

    letter = "2"


# ---------------------------------------------------------------------------
# Isolation fixture + helpers
# ---------------------------------------------------------------------------


def _reset_state():
    """Drop every gateway / registry singleton and clear the declarative config."""
    reset_gateway()
    reset_middleware_registry()
    reset_extension_registry()
    cfg = get_config()
    cfg.middlewares = []
    cfg.builtin_middleware = None


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
    _reset_state()
    yield
    reset_gateway()
    reset_middleware_registry()
    reset_extension_registry()
    cfg.verbose = original[0]
    cfg.auto_scan = original[1]
    cfg.startup_error_policy = original[2]
    cfg.middlewares = original[3]
    cfg.builtin_middleware = original[4]


def _names(pipeline):
    return [entry["name"] for entry in pipeline.list_middleware()]


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


def _assemble_low_then_high():
    """Register the low-priority legacy first, then the high-priority one."""
    registry = get_middleware_registry()
    registry.register(_LegacyLowPriorityMiddleware, priority=10)
    registry.register(_LegacyHighPriorityMiddleware, priority=150)
    configure(middlewares=[_DeclaredTraceMiddleware()])
    _setup_middleware_pipeline()


def _assemble_high_then_low():
    """Register the high-priority legacy first, then the low-priority one."""
    registry = get_middleware_registry()
    registry.register(_LegacyHighPriorityMiddleware, priority=150)
    registry.register(_LegacyLowPriorityMiddleware, priority=10)
    configure(middlewares=[_DeclaredTraceMiddleware()])
    _setup_middleware_pipeline()


_EXPECTED_LOW_HIGH_ORDER = [
    "_LegacyLowPriorityMiddleware",
    "_DeclaredTraceMiddleware",
    "AccessLogMiddleware",
    "_LegacyHighPriorityMiddleware",
]


# ---------------------------------------------------------------------------
# Invariant 1 — the resolved order does not depend on legacy registration order
# ---------------------------------------------------------------------------


def test_swapping_legacy_registration_order_keeps_the_order_on_the_asgi_engine():
    _reset_state()
    _assemble_low_then_high()
    low_then_high = _names(get_pipeline())

    _reset_state()
    _assemble_high_then_low()
    high_then_low = _names(get_pipeline())

    # Byte-for-byte identical: registration order never leaks into the result.
    assert low_then_high == high_then_low == _EXPECTED_LOW_HIGH_ORDER

    status, headers, _ = _asgi_probe()
    assert status == 200
    # Outermost -> innermost is low(O) -> declared(B) -> built-in -> high(I).
    assert headers["x-trace"] == "OBI"


def test_swapping_legacy_registration_order_keeps_the_order_on_the_tornado_engine():
    _reset_state()
    _assemble_low_then_high()
    low_then_high = _names(get_pipeline())

    _reset_state()
    _assemble_high_then_low()
    high_then_low = _names(get_pipeline())

    assert low_then_high == high_then_low == _EXPECTED_LOW_HIGH_ORDER

    status, headers, _ = _tornado_probe()
    assert status == 200
    assert headers["x-trace"] == "OBI"


# ---------------------------------------------------------------------------
# Invariant 2 — a default-priority legacy layer stays inside the built-in layer
# ---------------------------------------------------------------------------


def test_default_priority_legacy_stays_inside_the_builtin_layer_on_the_asgi_engine():
    _reset_state()
    get_middleware_registry().register(_LegacyDefaultPriorityMiddleware)
    _setup_middleware_pipeline()

    names = _names(get_pipeline())
    assert names == ["AccessLogMiddleware", "_LegacyDefaultPriorityMiddleware"]
    assert names.index("AccessLogMiddleware") < names.index(
        "_LegacyDefaultPriorityMiddleware"
    )

    status, headers, _ = _asgi_probe()
    assert status == 200
    assert headers["x-trace"] == "D"


def test_default_priority_legacy_stays_inside_the_builtin_layer_on_the_tornado_engine():
    _reset_state()
    get_middleware_registry().register(_LegacyDefaultPriorityMiddleware)
    _setup_middleware_pipeline()

    names = _names(get_pipeline())
    assert names == ["AccessLogMiddleware", "_LegacyDefaultPriorityMiddleware"]
    assert names.index("AccessLogMiddleware") < names.index(
        "_LegacyDefaultPriorityMiddleware"
    )

    status, headers, _ = _tornado_probe()
    assert status == 200
    assert headers["x-trace"] == "D"


# ---------------------------------------------------------------------------
# Invariant 3 — the default path keeps the pre-expansion layering
# ---------------------------------------------------------------------------

_DEFAULT_LEGACY_LAYERS = [
    "_LegacyDefaultPriorityMiddleware",
    "_LegacySecondDefaultMiddleware",
]


def _assemble_default_path():
    registry = get_middleware_registry()
    registry.register(_LegacyDefaultPriorityMiddleware)
    registry.register(_LegacySecondDefaultMiddleware)
    configure(middlewares=[_DeclaredTraceMiddleware()])
    _setup_middleware_pipeline()


def test_default_path_keeps_the_pre_expansion_layering_on_the_asgi_engine():
    _reset_state()
    _assemble_default_path()

    names = _names(get_pipeline())
    # No priority declared anywhere: declared -> built-in -> legacy, in that order.
    assert names == [
        "_DeclaredTraceMiddleware",
        "AccessLogMiddleware",
        *_DEFAULT_LEGACY_LAYERS,
    ]

    # Collapsing the expanded legacy layers back into one bridge token reproduces
    # the pre-expansion layering exactly, so the data-plane change is the entry
    # count alone (1 -> N), not the relative placement of the other layers.
    legacy_count = len(_DEFAULT_LEGACY_LAYERS)
    assert names[-legacy_count:] == _DEFAULT_LEGACY_LAYERS
    collapsed = names[:-legacy_count] + ["<legacy bridge>"]
    assert collapsed == ["_DeclaredTraceMiddleware", "AccessLogMiddleware", "<legacy bridge>"]

    status, headers, _ = _asgi_probe()
    assert status == 200
    # Outermost -> innermost: declared(B) -> built-in -> default(D) -> second(E).
    assert headers["x-trace"] == "BDE"


def test_default_path_keeps_the_pre_expansion_layering_on_the_tornado_engine():
    _reset_state()
    _assemble_default_path()

    names = _names(get_pipeline())
    assert names == [
        "_DeclaredTraceMiddleware",
        "AccessLogMiddleware",
        *_DEFAULT_LEGACY_LAYERS,
    ]

    legacy_count = len(_DEFAULT_LEGACY_LAYERS)
    assert names[-legacy_count:] == _DEFAULT_LEGACY_LAYERS
    collapsed = names[:-legacy_count] + ["<legacy bridge>"]
    assert collapsed == ["_DeclaredTraceMiddleware", "AccessLogMiddleware", "<legacy bridge>"]

    status, headers, _ = _tornado_probe()
    assert status == 200
    assert headers["x-trace"] == "BDE"


# ---------------------------------------------------------------------------
# Invariant 4 — same-priority peers keep their declaration order
# ---------------------------------------------------------------------------

_TIE_FORWARD_ORDER = [
    "AccessLogMiddleware",
    "_LegacyTieFirstMiddleware",
    "_LegacyTieSecondMiddleware",
]

_TIE_REVERSED_ORDER = [
    "AccessLogMiddleware",
    "_LegacyTieSecondMiddleware",
    "_LegacyTieFirstMiddleware",
]


def _assemble_tie_forward():
    """Declare the two same-priority peers first, then second."""
    registry = get_middleware_registry()
    registry.register(_LegacyTieFirstMiddleware)
    registry.register(_LegacyTieSecondMiddleware)
    _setup_middleware_pipeline()


def _assemble_tie_reversed():
    """Declare the two same-priority peers second, then first."""
    registry = get_middleware_registry()
    registry.register(_LegacyTieSecondMiddleware)
    registry.register(_LegacyTieFirstMiddleware)
    _setup_middleware_pipeline()


def test_same_priority_peers_keep_their_declaration_order_on_the_asgi_engine():
    _reset_state()
    _assemble_tie_forward()
    forward = _names(get_pipeline())

    status, headers, _ = _asgi_probe()
    assert status == 200
    # Outermost -> innermost: built-in -> peer "1" -> peer "2".
    assert headers["x-trace"] == "12"

    # Deterministic: re-running the exact same declarations resolves to exactly
    # the same order, so the tie is an ordered result rather than a shuffle.
    _reset_state()
    _assemble_tie_forward()
    assert _names(get_pipeline()) == forward

    _reset_state()
    _assemble_tie_reversed()
    reversed_order = _names(get_pipeline())

    status, headers, _ = _asgi_probe()
    assert status == 200
    # Reversing the declaration reverses the peers; the built-in layer keeps its
    # fixed place, so the unwinding order flips to "21".
    assert headers["x-trace"] == "21"

    # Two peers of the same priority keep the order in which they were declared
    # (registered).
    assert forward == _TIE_FORWARD_ORDER
    assert reversed_order == _TIE_REVERSED_ORDER
    assert forward != reversed_order


def test_same_priority_peers_keep_their_declaration_order_on_the_tornado_engine():
    _reset_state()
    _assemble_tie_forward()
    forward = _names(get_pipeline())

    status, headers, _ = _tornado_probe()
    assert status == 200
    assert headers["x-trace"] == "12"

    _reset_state()
    _assemble_tie_forward()
    assert _names(get_pipeline()) == forward

    _reset_state()
    _assemble_tie_reversed()
    reversed_order = _names(get_pipeline())

    status, headers, _ = _tornado_probe()
    assert status == 200
    assert headers["x-trace"] == "21"

    assert forward == _TIE_FORWARD_ORDER
    assert reversed_order == _TIE_REVERSED_ORDER
    assert forward != reversed_order
