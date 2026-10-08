# -*- coding: utf-8 -*-
"""Middleware pipeline entry, reflection and ordering.

Public paths covered:

* ``configure(middlewares=[...])`` — the declarative entry (keyword-only)
* ``MiddlewarePipeline.list_middleware()`` — public reflection
* ``before`` / ``after`` / ``priority`` — order control that never depends on the
  moment a middleware was registered
* ``list_extension_points()`` — the onion protocol as a framework extension point

Both engines (ASGI and Tornado) are driven through the single shared
``Dispatcher``; the order under test is declared on the pipeline that dispatcher
owns, so the assertion proves engine parity rather than two code paths.
"""
import asyncio
import inspect
import json

import pytest

from cullinan import configure, get_config
from cullinan.application.legacy import (
    _register_declared_middleware,
    _setup_middleware_pipeline,
)
from cullinan.support.extensions import list_extension_points, reset_extension_registry
from cullinan.web.gateway import (
    Dispatcher,
    GatewayMiddleware,
    MiddlewarePipeline,
    Router,
    WebResponse,
    get_pipeline,
    reset_gateway,
)


class _AlphaMiddleware(GatewayMiddleware):
    """Outermost in the "no hints" and "priority" scenarios."""

    async def __call__(self, request, call_next):
        response = await call_next(request)
        response.set_header("X-Trace", "A" + (response.get_header("X-Trace") or ""))
        return response


class _BetaMiddleware(GatewayMiddleware):
    async def __call__(self, request, call_next):
        response = await call_next(request)
        response.set_header("X-Trace", "B" + (response.get_header("X-Trace") or ""))
        return response


class _GammaMiddleware(GatewayMiddleware):
    async def __call__(self, request, call_next):
        response = await call_next(request)
        response.set_header("X-Trace", "C" + (response.get_header("X-Trace") or ""))
        return response


class _FakeConfig:
    """Minimal stand-in exposing only what the declarative reader needs."""

    def __init__(self, middlewares):
        self.middlewares = middlewares


def _names(pipeline: MiddlewarePipeline):
    return [entry["name"] for entry in pipeline.list_middleware()]


@pytest.fixture(autouse=True)
def _restore_middleware_state():
    cfg = get_config()
    original = (cfg.verbose, cfg.auto_scan, cfg.startup_error_policy, list(cfg.middlewares))
    reset_extension_registry()
    reset_gateway()
    yield
    cfg.verbose = original[0]
    cfg.auto_scan = original[1]
    cfg.startup_error_policy = original[2]
    cfg.middlewares = original[3]
    reset_extension_registry()
    reset_gateway()


# ---------------------------------------------------------------------------
# Order control (order must not depend on registration timing)
# ---------------------------------------------------------------------------


def test_no_hints_preserves_registration_order_first_added_is_outermost():
    pipeline = MiddlewarePipeline()
    pipeline.add(_AlphaMiddleware())
    pipeline.add(_BetaMiddleware())
    pipeline.add(_GammaMiddleware())

    assert _names(pipeline) == [
        "_AlphaMiddleware",
        "_BetaMiddleware",
        "_GammaMiddleware",
    ]


def test_priority_is_a_global_key_and_lower_runs_outermost():
    pipeline = MiddlewarePipeline()
    pipeline.add(_AlphaMiddleware())                 # default priority (100)
    pipeline.add(_BetaMiddleware(), priority=10)
    pipeline.add(_GammaMiddleware(), priority=1)

    assert _names(pipeline) == [
        "_GammaMiddleware",
        "_BetaMiddleware",
        "_AlphaMiddleware",
    ]


def test_priority_places_a_lone_middleware_outermost_despite_registration_order():
    pipeline = MiddlewarePipeline()
    pipeline.add(_AlphaMiddleware())
    pipeline.add(_BetaMiddleware())
    pipeline.add(_GammaMiddleware(), priority=0)

    assert _names(pipeline)[0] == "_GammaMiddleware"


def test_before_and_after_anchors_by_instance_class_and_name():
    pipeline = MiddlewarePipeline()
    alpha = _AlphaMiddleware()
    pipeline.add(alpha)
    pipeline.add(_BetaMiddleware(), before=alpha)          # instance anchor
    pipeline.add(_GammaMiddleware(), after=_AlphaMiddleware)  # class anchor

    assert _names(pipeline) == [
        "_BetaMiddleware",
        "_AlphaMiddleware",
        "_GammaMiddleware",
    ]

    by_name = MiddlewarePipeline()
    by_name.add(_AlphaMiddleware())
    by_name.add(_BetaMiddleware(), before="_AlphaMiddleware")  # by class name
    assert _names(by_name) == ["_BetaMiddleware", "_AlphaMiddleware"]


def test_order_does_not_depend_on_registration_timing():
    """A fully anchored declaration resolves identically in any registration order.

    ``Gamma`` must sit outside ``Alpha``, and ``Alpha`` outside ``Beta`` — the
    anchors may be written before the middleware they point at exists.
    """
    first = MiddlewarePipeline()
    first.add(_AlphaMiddleware(), before="_BetaMiddleware")
    first.add(_BetaMiddleware())
    first.add(_GammaMiddleware(), before="_AlphaMiddleware")

    second = MiddlewarePipeline()
    second.add(_GammaMiddleware(), before="_AlphaMiddleware")
    second.add(_BetaMiddleware())
    second.add(_AlphaMiddleware(), before="_BetaMiddleware")

    expected = ["_GammaMiddleware", "_AlphaMiddleware", "_BetaMiddleware"]
    assert _names(first) == expected
    assert _names(second) == expected

    # Inverting only the registration order must not change the resolved order.
    inverted = MiddlewarePipeline()
    inverted.add(_GammaMiddleware())
    inverted.add(_BetaMiddleware())
    inverted.add(_AlphaMiddleware(), before="_BetaMiddleware")

    assert _names(inverted)[0] == "_GammaMiddleware"


def test_declared_security_gate_can_be_the_outermost_layer():
    pipeline = MiddlewarePipeline()
    pipeline.add(_AlphaMiddleware())
    pipeline.add(_BetaMiddleware(), before="_AlphaMiddleware")

    assert _names(pipeline)[0] == "_BetaMiddleware"


# ---------------------------------------------------------------------------
# Reflection + boundary
# ---------------------------------------------------------------------------


def test_list_middleware_is_empty_for_an_empty_pipeline():
    pipeline = MiddlewarePipeline()

    assert pipeline.list_middleware() == []
    assert pipeline.count == 0


def test_list_middleware_reports_order_and_declared_hints():
    pipeline = MiddlewarePipeline()
    pipeline.add(_AlphaMiddleware(), priority=4)
    pipeline.add(_BetaMiddleware(), after="_AlphaMiddleware")

    descriptors = pipeline.list_middleware()

    assert descriptors[0] == {"name": "_AlphaMiddleware", "order": 0, "priority": 4}
    assert descriptors[1]["name"] == "_BetaMiddleware"
    assert descriptors[1]["order"] == 1
    assert descriptors[1]["after"] == "_AlphaMiddleware"


def test_count_and_clear_track_registered_middleware():
    pipeline = MiddlewarePipeline()
    pipeline.add(_AlphaMiddleware())
    pipeline.add(_BetaMiddleware())
    assert pipeline.count == 2

    pipeline.clear()

    assert pipeline.count == 0
    assert pipeline.list_middleware() == []


# ---------------------------------------------------------------------------
# Declarative entry: configure(middlewares=...)
# ---------------------------------------------------------------------------


def test_middlewares_parameter_is_keyword_only():
    parameter = inspect.signature(configure).parameters["middlewares"]

    assert parameter.kind is inspect.Parameter.KEYWORD_ONLY


def test_configure_middlewares_is_stored_on_the_config_and_serialized():
    configure(middlewares=[_AlphaMiddleware()])

    assert [type(m).__name__ for m in get_config().middlewares] == ["_AlphaMiddleware"]

    # The value also travels through from_dict/to_dict.
    assert get_config().to_dict()["middlewares"] == get_config().middlewares


def test_declarative_middleware_is_assembled_before_the_builtin_layer():
    configure(middlewares=[_AlphaMiddleware(), (_BetaMiddleware(), {"priority": 5})])

    _setup_middleware_pipeline()

    names = _names(get_pipeline())
    assert names[0] == "_BetaMiddleware"  # priority 5 -> outermost
    assert names.index("_AlphaMiddleware") < names.index("AccessLogMiddleware")
    assert "AccessLogMiddleware" in names
    assert get_pipeline().count == 3


def test_assembly_point_surfaces_declaration_errors_instead_of_swallowing_them():
    configure(middlewares=[(_AlphaMiddleware(), {"before": "_MissingMiddleware"})])

    with pytest.raises(ValueError):
        _setup_middleware_pipeline()


# ---------------------------------------------------------------------------
# Declarative reader: negative and boundary inputs
# ---------------------------------------------------------------------------


def test_reader_accepts_instances():
    pipeline = MiddlewarePipeline()
    _register_declared_middleware(
        pipeline,
        _FakeConfig([_AlphaMiddleware(), _BetaMiddleware()]),
    )

    assert _names(pipeline) == ["_AlphaMiddleware", "_BetaMiddleware"]


def test_reader_rejects_a_non_gateway_middleware():
    with pytest.raises(TypeError):
        _register_declared_middleware(MiddlewarePipeline(), _FakeConfig([object()]))


def test_reader_rejects_a_non_gateway_middleware_class_without_constructing_it():
    """A rejected class must never run its constructor.

    Validation happens before the class is instantiated, so a class that is not a
    ``GatewayMiddleware`` fails as a type error with no construction side effect
    and nothing added to the pipeline.
    """
    constructed = []

    class _PlainNotMiddleware:
        def __init__(self):
            constructed.append(self)

    pipeline = MiddlewarePipeline()
    with pytest.raises(TypeError) as excinfo:
        _register_declared_middleware(pipeline, _FakeConfig([_PlainNotMiddleware]))

    assert constructed == []
    assert pipeline.count == 0
    # The message still names the offending type.
    assert "_PlainNotMiddleware" in str(excinfo.value)


def test_reader_rejects_a_malformed_options_tuple():
    with pytest.raises(ValueError):
        _register_declared_middleware(
            MiddlewarePipeline(),
            _FakeConfig([(_AlphaMiddleware(), "not-a-mapping")]),
        )


def test_reader_rejects_priority_combined_with_an_anchor():
    with pytest.raises(ValueError):
        _register_declared_middleware(
            MiddlewarePipeline(),
            _FakeConfig([(_AlphaMiddleware(), {"priority": 1, "before": "_BetaMiddleware"})]),
        )


def test_unknown_anchor_is_rejected():
    pipeline = MiddlewarePipeline()
    pipeline.add(_AlphaMiddleware(), before="_MissingMiddleware")

    with pytest.raises(ValueError):
        pipeline.list_middleware()


def test_self_anchor_is_rejected():
    pipeline = MiddlewarePipeline()
    pipeline.add(_AlphaMiddleware(), before="_AlphaMiddleware")

    with pytest.raises(ValueError):
        pipeline.list_middleware()


def test_ambiguous_anchor_is_rejected():
    pipeline = MiddlewarePipeline()
    pipeline.add(_AlphaMiddleware())
    pipeline.add(_AlphaMiddleware())
    pipeline.add(_BetaMiddleware(), before="_AlphaMiddleware")

    with pytest.raises(ValueError):
        pipeline.list_middleware()


def test_cyclic_ordering_is_rejected():
    pipeline = MiddlewarePipeline()
    pipeline.add(_AlphaMiddleware(), before="_BetaMiddleware")
    pipeline.add(_BetaMiddleware(), before="_AlphaMiddleware")

    with pytest.raises(ValueError):
        pipeline.list_middleware()


# ---------------------------------------------------------------------------
# Both engines, one dispatcher
# ---------------------------------------------------------------------------


async def _dispatch_asgi(app, path: str):
    sent = []
    messages = [{"type": "http.request", "body": b"", "more_body": False}]

    async def receive():
        if messages:
            return messages.pop(0)
        return {"type": "http.disconnect"}

    async def send(message):
        sent.append(message)

    await app(
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
    return sent


def _build_ordered_dispatcher() -> Dispatcher:
    router = Router()

    async def order_handler(_request):
        return WebResponse.json({"ok": True})

    router.add_route("GET", "/order", handler=order_handler)

    pipeline = MiddlewarePipeline()
    # Registration order deliberately contradicts the declared priority.
    pipeline.add(_AlphaMiddleware())
    pipeline.add(_BetaMiddleware(), priority=10)
    pipeline.add(_GammaMiddleware(), priority=0)

    return Dispatcher(router=router, pipeline=pipeline, debug=True)


def test_ordering_reaches_the_asgi_engine():
    from cullinan.transport.adapter import ASGIAdapter

    app = ASGIAdapter(dispatcher=_build_ordered_dispatcher()).create_app()
    events = asyncio.run(_dispatch_asgi(app, "/order"))

    start = next(event for event in events if event["type"] == "http.response.start")
    headers = {
        name.decode("latin-1").lower(): value.decode("latin-1")
        for name, value in start.get("headers", [])
    }
    assert start["status"] == 200
    # Gamma (priority 0) outermost, then Beta (10), then Alpha (default 100).
    assert headers["x-trace"] == "CBA"

    body = b"".join(
        event.get("body", b"")
        for event in events
        if event["type"] == "http.response.body"
    )
    assert json.loads(body) == {"ok": True}


def test_ordering_reaches_the_tornado_engine():
    tornado_testing = pytest.importorskip("tornado.testing")
    from cullinan.transport.adapter import TornadoAdapter

    app = TornadoAdapter(dispatcher=_build_ordered_dispatcher()).create_app()

    class _Case(tornado_testing.AsyncHTTPTestCase):
        def get_app(self):
            return app

    case = _Case()
    case.setUp()
    try:
        response = case.fetch("/order")
        assert response.code == 200
        assert response.headers["X-Trace"] == "CBA"
        assert json.loads(response.body) == {"ok": True}
    finally:
        case.tearDown()


# ---------------------------------------------------------------------------
# The onion protocol is a registered extension point
# ---------------------------------------------------------------------------


def test_onion_protocol_is_registered_as_a_middleware_extension_point():
    middleware_points = [
        point for point in list_extension_points("middleware")
    ]
    names = [point["name"] for point in middleware_points]

    assert "GatewayMiddleware.__call__" in names
    assert "Middleware.process_request" in names

    onion = next(
        point for point in middleware_points
        if point["name"] == "GatewayMiddleware.__call__"
    )
    assert onion["interface"] == "GatewayMiddleware"
    assert "recommended" in onion["description"].lower()


def test_middleware_wiki_documents_both_protocols_and_recommends_the_onion_one():
    en = _read("docs/wiki/middleware.md")
    zh = _read("docs/zh/wiki/middleware.md")

    for content in (en, zh):
        assert "GatewayMiddleware" in content
        assert "process_request" in content

    assert "Recommended: onion protocol" in en
    assert "推荐：洋葱协议" in zh
    # Both pages link to each other as a translation pair.
    assert "translation_pair" in en and "translation_pair" in zh


def _read(path: str) -> str:
    from pathlib import Path

    return Path(path).read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# C-4 guardrail: `MiddlewarePipeline.add_class` is a registered legacy path
# ---------------------------------------------------------------------------


def test_add_class_is_a_registered_legacy_bare_construction_path():
    """``MiddlewarePipeline.add_class`` stays, and stays a bare-construction path.

    ``add_class`` is the pre-R17 legacy convenience method: it constructs the
    middleware itself, so the instance is **not** container-managed and its
    declared dependencies are **not** injected. The container-managed path is the
    declarative ``configure(middlewares=[Class])`` with ``@component``. The method
    is kept because removing it changes public behaviour and must go through a
    deprecation window; a pre-boot ``get_pipeline().add_class(...)`` is refused at
    the boot boundary (``PREBOOT_REGISTRATION_ERROR``), so it cannot silently lose
    a middleware.

    This test pins that the method still exists and still returns the bare
    instance it constructed, so removing it or changing its semantics must be a
    deliberate, reviewed change rather than an accidental one.
    """
    pipeline = MiddlewarePipeline()
    instance = pipeline.add_class(_AlphaMiddleware)

    assert isinstance(instance, _AlphaMiddleware)
    assert pipeline.count == 1
    assert pipeline.list_middleware()[0]["name"] == "_AlphaMiddleware"
