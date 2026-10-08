# -*- coding: utf-8 -*-
"""Read-only projections for the previously unreadable gateway surfaces.

Two gateway surfaces had no enumerable read-only face at all: the dispatcher
exposed only its public assembly-relation attributes, and the exception handler
kept its handler table private with no way to read it back. Both now have one,
so the registration-surface snapshot can enumerate them like the pipeline and the
router. The module-private ``_peek_*`` readers are covered here too: they are what
lets an observer read a surface without materializing it as a side effect.
"""

import pytest

from cullinan.web.gateway import (
    Dispatcher,
    ExceptionHandler,
    HeaderPolicy,
    MiddlewarePipeline,
    ReturnValueHandler,
    Router,
    WebRuntime,
    get_dispatcher,
    get_exception_handler,
    get_pipeline,
    get_router,
    reset_gateway,
)
from cullinan.web.gateway import globals as gateway_globals
from cullinan.web.gateway.invocation import ExceptionResolver


@pytest.fixture(autouse=True)
def _reset_gateway():
    reset_gateway()
    yield
    reset_gateway()


# ---------------------------------------------------------------------------
# Dispatcher projection
# ---------------------------------------------------------------------------
def test_dispatcher_lists_its_wiring():
    dispatcher = Dispatcher()

    wiring = dispatcher.list_wired_components()

    names = [descriptor["name"] for descriptor in wiring]
    assert names == [
        "router",
        "pipeline",
        "exception_handler",
        "header_policy",
        "return_value_handler",
        "exception_resolver",
    ]
    # Each descriptor names the class installed in that slot.
    by_name = {descriptor["name"]: descriptor["type"] for descriptor in wiring}
    assert by_name["router"] == Router.__name__
    assert by_name["pipeline"] == MiddlewarePipeline.__name__
    assert by_name["exception_handler"] == ExceptionHandler.__name__
    assert by_name["header_policy"] == HeaderPolicy.__name__
    assert by_name["return_value_handler"] == ReturnValueHandler.__name__
    assert by_name["exception_resolver"] == ExceptionResolver.__name__


def test_dispatcher_projection_reflects_the_installed_collaborators():
    router = Router()
    pipeline = MiddlewarePipeline()
    handler = ExceptionHandler()

    dispatcher = Dispatcher(
        router=router,
        pipeline=pipeline,
        exception_handler=handler,
    )

    wiring = {descriptor["name"]: descriptor["type"] for descriptor in dispatcher.list_wired_components()}
    assert wiring["router"] == Router.__name__
    assert wiring["pipeline"] == MiddlewarePipeline.__name__
    assert wiring["exception_handler"] == ExceptionHandler.__name__


# ---------------------------------------------------------------------------
# ExceptionHandler projection
# ---------------------------------------------------------------------------
def test_exception_handler_lists_registered_handlers_in_order():
    handler = ExceptionHandler()
    assert handler.list_registered_handlers() == []

    @handler.register(ValueError)
    def _handle_value_error(request, exc):
        return exc

    @handler.register(PermissionError)
    def _handle_permission_error(request, exc):
        return exc

    descriptors = handler.list_registered_handlers()
    assert [descriptor["name"] for descriptor in descriptors] == [
        "ValueError",
        "PermissionError",
    ]
    assert [descriptor["order"] for descriptor in descriptors] == [0, 1]


def test_exception_handler_projection_does_not_expose_the_callables():
    handler = ExceptionHandler()

    @handler.register(ValueError)
    def _handle(request, exc):
        return exc

    (descriptor,) = handler.list_registered_handlers()
    assert set(descriptor.keys()) == {"name", "order"}


# ---------------------------------------------------------------------------
# Non-materializing peek helpers
# ---------------------------------------------------------------------------
def test_peek_helpers_do_not_materialize_lazy_globals():
    assert gateway_globals._global_pipeline is None
    assert gateway_globals._global_router is None
    assert gateway_globals._global_dispatcher is None
    assert gateway_globals._global_exception_handler is None

    assert gateway_globals._peek_pipeline() is None
    assert gateway_globals._peek_router() is None
    assert gateway_globals._peek_dispatcher() is None
    assert gateway_globals._peek_exception_handler() is None

    assert gateway_globals._global_pipeline is None, "peeking created a pipeline"
    assert gateway_globals._global_router is None, "peeking created a router"
    assert gateway_globals._global_dispatcher is None, "peeking created a dispatcher"
    assert (
        gateway_globals._global_exception_handler is None
    ), "peeking created an exception handler"


def test_peek_helpers_return_the_materialized_instances():
    pipeline = get_pipeline()
    router = get_router()
    dispatcher = get_dispatcher()
    handler = get_exception_handler()

    assert gateway_globals._peek_pipeline() is pipeline
    assert gateway_globals._peek_router() is router
    assert gateway_globals._peek_dispatcher() is dispatcher
    assert gateway_globals._peek_exception_handler() is handler


# ---------------------------------------------------------------------------
# The gateway facade contract is untouched
# ---------------------------------------------------------------------------
def test_gateway_facade_export_count_is_unchanged():
    import cullinan.web.gateway as gateway_api

    assert len(gateway_api.__all__) == 33
    # The new projections are methods on existing classes, not new symbols.
    assert "list_wired_components" not in gateway_api.__all__
    assert "list_registered_handlers" not in gateway_api.__all__


def test_web_runtime_still_wires_the_same_dispatcher():
    """The dispatcher projection works on the runtime's own dispatcher too."""
    runtime = WebRuntime()

    wiring = runtime.dispatcher.list_wired_components()
    names = {descriptor["name"] for descriptor in wiring}
    assert "router" in names and "exception_handler" in names
