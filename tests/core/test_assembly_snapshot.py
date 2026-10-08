# -*- coding: utf-8 -*-
"""Observability of the registration surfaces at the boot boundary.

An application can now answer one question in one call:
``Application.get_assembly_snapshot()`` reports what this assembly actually
holds, surface by surface. It covers every surface the boot boundary rebuilds --
the four gateway globals ``pipeline`` / ``router`` / ``dispatcher`` /
``exception_handler`` -- plus the ``container``, and it reports a pre-boot
registration the boundary discarded side by side with the assembled set.

Pinned here:

* the snapshot covers all four gateway surfaces and the container in a single
  call, each as a ``declared`` / ``assembled`` / ``dropped`` triple;
* a pre-boot registration on a surface the boundary resets (``router`` /
  ``exception_handler``) is *dropped* and *queryable* -- not merely logged;
* the pipeline sub-surface always carries a ``dropped`` field, empty on a
  successful start: a "missing field" is a failure, not a silent omission;
* the query never materializes a lazy gateway global (an observer must not
  perturb the observed);
* the snapshot adds no public symbol -- the top-level ``__all__`` stays 44 and
  the four frozen contracts are unchanged -- and stays a module-private frozen
  view;
* the reconciliation is engine neutral (Tornado + ASGI).
"""

import importlib
import sys
import textwrap
from pathlib import Path
from types import MappingProxyType

import pytest

from cullinan.application import Application
from cullinan.application import public as public_api
from cullinan.application.model import _AssemblySnapshot, _SurfaceHoldings
from cullinan.core import PendingRegistry, set_application_context
from cullinan.core.semantic_rules import reset_semantic_warnings
from cullinan.web.controller import reset_controller_registry
from cullinan.web.gateway import (
    WebRuntime,
    get_exception_handler,
    get_router,
    reset_gateway,
)

GATEWAY_SURFACES = ("pipeline", "router", "dispatcher", "exception_handler")


@pytest.fixture(autouse=True)
def _reset_framework_globals():
    reset_semantic_warnings()
    set_application_context(None)
    PendingRegistry.reset()
    WebRuntime.clear_active()
    reset_gateway()
    reset_controller_registry()
    yield
    reset_semantic_warnings()
    set_application_context(None)
    PendingRegistry.reset()
    WebRuntime.clear_active()
    reset_gateway()
    reset_controller_registry()


def _clear_modules(*prefixes: str) -> None:
    for module_name in list(sys.modules):
        for prefix in prefixes:
            if module_name == prefix or module_name.startswith(f"{prefix}."):
                sys.modules.pop(module_name, None)
                break


def _write_app_package(tmp_path: Path, package_name: str) -> None:
    root = tmp_path / package_name
    root.mkdir(parents=True, exist_ok=True)
    (root / "__init__.py").write_text("", encoding="utf-8")
    (root / "root.py").write_text(
        textwrap.dedent(
            f"""
            from cullinan import application, configure

            @configure(user_packages=["{package_name}"])
            @application
            def main(): ...
            """
        ).strip()
        + "\n",
        encoding="utf-8",
    )


def _boot(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, package_name: str):
    """Assemble a real application from a throwaway package (no port binding)."""
    _write_app_package(tmp_path, package_name)
    monkeypatch.syspath_prepend(str(tmp_path))
    _clear_modules(package_name)
    return importlib.import_module(f"{package_name}.root").main


def _uninstall():
    current = Application.current()
    if current is not None:
        current.uninstall()


# ---------------------------------------------------------------------------
# One call covers every surface (4 gateway globals + container)
# ---------------------------------------------------------------------------
def test_snapshot_covers_all_four_gateway_surfaces_and_the_container(
    tmp_path, monkeypatch
):
    entry = _boot(tmp_path, monkeypatch, "snap_covers")

    app = Application(entry)
    app.build()
    try:
        snapshot = app.get_assembly_snapshot()

        # One call, every surface -- not one call per surface.
        assert set(snapshot.gateway.keys()) == set(GATEWAY_SURFACES)
        for surface in GATEWAY_SURFACES:
            holdings = snapshot.gateway[surface]
            assert isinstance(holdings, _SurfaceHoldings)
            assert isinstance(holdings.declared, tuple)
            assert isinstance(holdings.assembled, tuple)
            assert isinstance(holdings.dropped, tuple)

        # ... plus the container surface.
        assert isinstance(snapshot.container, _SurfaceHoldings)
        assert snapshot.container is not None
    finally:
        app.uninstall()


def test_container_surface_mirrors_the_declaration_diff(tmp_path, monkeypatch):
    entry = _boot(tmp_path, monkeypatch, "snap_container")

    app = Application(entry)
    app.build()
    try:
        snapshot = app.get_assembly_snapshot()
        diff = app.get_declaration_diff()

        assert snapshot.container.declared == diff.declared
        assert snapshot.container.assembled == diff.assembled
        assert snapshot.container.dropped == diff.dropped
    finally:
        app.uninstall()


# ---------------------------------------------------------------------------
# The pipeline sub-surface must always carry a (possibly empty) dropped field
# ---------------------------------------------------------------------------
def _pipeline_dropped_is_present(snapshot) -> bool:
    """The pipeline sub-surface exists and carries a ``dropped`` sequence.

    This is the check ORCH's per-surface verdict asks for: on a successful start
    the pipeline's dropped set is empty, so it must be *present and empty*, never
    *absent*. The predicate has teeth (see the red/green pair below).
    """
    try:
        surface = snapshot.gateway["pipeline"]
        return isinstance(surface.dropped, tuple)
    except (KeyError, AttributeError, TypeError):
        return False


def test_successful_start_reports_an_empty_pipeline_dropped_field(
    tmp_path, monkeypatch
):
    entry = _boot(tmp_path, monkeypatch, "snap_pipeline_empty")

    app = Application(entry)
    app.build()
    try:
        snapshot = app.get_assembly_snapshot()

        # Green: field present, and empty because the boundary refuses any
        # pre-boot pipeline registration rather than dropping it.
        assert _pipeline_dropped_is_present(snapshot) is True
        assert snapshot.gateway["pipeline"].dropped == ()
        assert snapshot.gateway["pipeline"].declared == ()
    finally:
        app.uninstall()


def test_a_missing_pipeline_dropped_field_would_fail_the_same_check():
    """Red side of the pair: the check rejects a snapshot that omits the field.

    ``test_successful_start_reports_an_empty_pipeline_dropped_field`` only means
    something if the same predicate can fail. These counterfactual snapshots
    model the two ways the field can go missing -- the surface key itself absent,
    and the surface present but without a ``dropped`` sequence -- and the
    predicate rejects both.
    """
    container = _SurfaceHoldings()
    missing_surface = _AssemblySnapshot(
        gateway=MappingProxyType({}),
        container=container,
    )
    assert _pipeline_dropped_is_present(missing_surface) is False

    surface_without_dropped = _AssemblySnapshot(
        gateway=MappingProxyType({"pipeline": object()}),
        container=container,
    )
    assert _pipeline_dropped_is_present(surface_without_dropped) is False


# ---------------------------------------------------------------------------
# A pre-boot registration the boundary discards is reported and queryable
# ---------------------------------------------------------------------------
def test_pre_boot_exception_handler_registration_is_dropped_and_queryable(
    tmp_path, monkeypatch
):
    entry = _boot(tmp_path, monkeypatch, "snap_eh_dropped")

    # Registered *before* startup, on the handler the boot boundary rebuilds.
    @get_exception_handler().register(ValueError)
    def _handle_value_error(request, exc):  # pragma: no cover - never invoked here
        raise exc

    entry.get_asgi_app()
    try:
        app = Application.current()
        assert app is not None
        snapshot = app.get_assembly_snapshot()

        holdings = snapshot.gateway["exception_handler"]
        assert "ValueError" in holdings.dropped
        assert "ValueError" not in holdings.assembled
        # Reconcile in one place: dropped is declared minus assembled.
        assert set(holdings.dropped) <= set(holdings.declared)
        assert set(holdings.assembled).isdisjoint(holdings.dropped)
    finally:
        _uninstall()


def test_pre_boot_router_registration_is_dropped_and_queryable(tmp_path, monkeypatch):
    entry = _boot(tmp_path, monkeypatch, "snap_router_dropped")

    # A route registered *before* startup, on the router the boundary rebuilds.
    get_router().add_route("GET", "/pre-boot-check", handler=lambda request: None)

    entry.get_asgi_app()
    try:
        app = Application.current()
        assert app is not None
        snapshot = app.get_assembly_snapshot()

        holdings = snapshot.gateway["router"]
        assert "GET /pre-boot-check" in holdings.dropped
        assert "GET /pre-boot-check" not in holdings.assembled
    finally:
        _uninstall()


# ---------------------------------------------------------------------------
# The query must not perturb what it observes
# ---------------------------------------------------------------------------
def test_query_does_not_materialize_lazy_gateway_globals():
    from cullinan.web.gateway import globals as gateway_globals

    assert gateway_globals._global_pipeline is None
    assert gateway_globals._global_router is None
    assert gateway_globals._global_dispatcher is None
    assert gateway_globals._global_exception_handler is None

    # An application that has not started yet: reading its snapshot must not
    # bring any lazy global into being.
    app = Application(_standalone_entry())
    snapshot = app.get_assembly_snapshot()

    assert gateway_globals._global_pipeline is None, "the query created a pipeline"
    assert gateway_globals._global_router is None, "the query created a router"
    assert gateway_globals._global_dispatcher is None, "the query created a dispatcher"
    assert (
        gateway_globals._global_exception_handler is None
    ), "the query created an exception handler"

    # A not-yet-started application still answers, with an empty reconciliation.
    assert set(snapshot.gateway.keys()) == set(GATEWAY_SURFACES)
    assert snapshot.gateway["dispatcher"].dropped == ()


def _standalone_entry():
    """A minimal ``@application`` entry, used only to construct an Application."""
    from cullinan import application

    @application
    def standalone():  # pragma: no cover - the body never runs in this test
        ...

    return standalone


# ---------------------------------------------------------------------------
# No new public symbols; private + frozen
# ---------------------------------------------------------------------------
def test_assembly_snapshot_adds_no_public_symbols():
    import cullinan
    import cullinan.application as application_api
    import cullinan.core as core_api
    import cullinan.web as web_api

    assert len(cullinan.__all__) == 44
    assert len(application_api.__all__) == 26
    assert len(web_api.__all__) == 34
    assert len(core_api.__all__) == 72

    for module in (cullinan, application_api, web_api, core_api):
        assert "_AssemblySnapshot" not in module.__all__
        assert "_SurfaceHoldings" not in module.__all__
        assert "get_assembly_snapshot" not in module.__all__


def test_assembly_snapshot_is_a_frozen_private_view():
    holdings = _SurfaceHoldings(declared=("a",), assembled=(), dropped=("a",))
    with pytest.raises(Exception):
        holdings.dropped = ()  # frozen dataclass

    snapshot = _AssemblySnapshot(
        gateway=MappingProxyType({"pipeline": holdings}),
        container=holdings,
    )
    with pytest.raises(Exception):
        snapshot.container = holdings  # frozen dataclass


# ---------------------------------------------------------------------------
# Engine neutrality (Tornado + ASGI)
# ---------------------------------------------------------------------------
class _CapturingAdapter:
    def __init__(self, **kwargs):
        self.init_kwargs = kwargs

    def run(self, **kwargs):
        self.run_kwargs = kwargs


@pytest.mark.parametrize("engine", ["tornado", "asgi"])
def test_assembly_snapshot_is_engine_neutral(tmp_path, monkeypatch, engine):
    package_name = f"snap_engine_{engine}"
    entry = _boot(tmp_path, monkeypatch, package_name)

    if engine == "asgi":
        app = entry.get_asgi_app()
        assert app is not None
    else:
        built: list = []

        class _Adapter(_CapturingAdapter):
            def __init__(self, **kwargs):
                super().__init__(**kwargs)
                built.append(self)

        monkeypatch.setattr(public_api, "_load_tornado_adapter", lambda: _Adapter)
        public_api.run(entry, engine="tornado")
        assert built, "the tornado adapter was never built"

    try:
        current = Application.current()
        assert current is not None
        snapshot = current.get_assembly_snapshot()
        assert set(snapshot.gateway.keys()) == set(GATEWAY_SURFACES)
        assert snapshot.container is not None
    finally:
        _uninstall()
