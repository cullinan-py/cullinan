# -*- coding: utf-8 -*-
"""Declared-vs-assembled reconciliation of the component declaration boundary.

Covers the red-green pair:

* a component declared in a package that is **not** listed in ``user_packages``
  is *declared but not assembled* and must raise ``ComponentDiscoveryWarning``
  carrying ``component-declared-not-assembled``;
* moving the component into ``user_packages`` clears the difference and the
  warning disappears.

Also covers the query surface (``Application.get_declaration_diff()``), the
default-visibility requirement (WARNING level, no debug switch), the preserved
``component-top-level`` guard, and engine neutrality (Tornado + ASGI).
"""

import importlib
import logging
import sys
import textwrap
import warnings
from pathlib import Path

import pytest

from cullinan.application import Application
from cullinan.application import public as public_api
from cullinan.core import PendingRegistry, set_application_context
from cullinan.core.application_context import ApplicationContext
from cullinan.core.semantic_rules import (
    ComponentDiscoveryWarning,
    reset_semantic_warnings,
)
from cullinan.web.controller import reset_controller_registry
from cullinan.web.gateway import WebRuntime, reset_gateway

RULE_KEY = "component-declared-not-assembled"
TOP_LEVEL_RULE_PHRASE = "module top level"


@pytest.fixture(autouse=True)
def _reset_semantic_and_runtime_state():
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


def _write_tree(root: Path, files: dict) -> None:
    """Write ``{relative_path: source}`` under ``root`` (paths from ``root``)."""
    for relative_path, content in files.items():
        target = root / relative_path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(textwrap.dedent(content).strip() + "\n", encoding="utf-8")


def _clear_modules(*prefixes: str) -> None:
    for module_name in list(sys.modules):
        for prefix in prefixes:
            if module_name == prefix or module_name.startswith(f"{prefix}."):
                sys.modules.pop(module_name, None)
                break


def _build_app(root_module):
    app = Application(root_module)
    app.build()
    return app


def _rule_warnings(caught):
    return [
        item
        for item in caught
        if item.category is ComponentDiscoveryWarning and RULE_KEY in str(item.message)
    ]


# ---------------------------------------------------------------------------
# AC-1 / AC-4: out-of-scope component -> declared but not assembled
# ---------------------------------------------------------------------------
def test_out_of_scope_component_is_declared_but_not_assembled(tmp_path, monkeypatch):
    package_name = "decl_diff_out_of_scope"
    outside_name = "decl_diff_outside_a"
    _write_tree(
        tmp_path,
        {
            f"{package_name}/__init__.py": "",
            f"{package_name}/app/__init__.py": "",
            f"{package_name}/app/root.py": f"""
                from cullinan import application, configure

                import {outside_name}.svc  # deliberately outside user_packages

                @configure(user_packages=["{package_name}.app"])
                @application
                def main(): ...
            """,
            f"{outside_name}/__init__.py": "",
            f"{outside_name}/svc.py": """
                from cullinan import service

                @service
                class OutsideService:
                    pass
            """,
        },
    )
    monkeypatch.syspath_prepend(str(tmp_path))
    _clear_modules(package_name, outside_name)

    entry = importlib.import_module(f"{package_name}.app.root").main

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        app = _build_app(entry)

    try:
        diff = app.get_declaration_diff()

        assert diff.dropped_count == len(diff.dropped)
        assert diff.dropped_count >= 1
        assert f"{outside_name}.svc.OutsideService" in diff.dropped
        assert f"{outside_name}.svc.OutsideService" not in diff.assembled
        assert _rule_warnings(caught), [str(item.message) for item in caught]
    finally:
        app.uninstall()
        _clear_modules(package_name, outside_name)


# ---------------------------------------------------------------------------
# AC-2: moving the component into user_packages -> no warning, empty diff
# ---------------------------------------------------------------------------
def test_component_inside_user_packages_produces_no_warning(tmp_path, monkeypatch):
    package_name = "decl_diff_in_scope"
    inside_name = "decl_diff_inside_a"
    _write_tree(
        tmp_path,
        {
            f"{package_name}/__init__.py": "",
            f"{package_name}/app/__init__.py": "",
            f"{package_name}/app/root.py": f"""
                from cullinan import application, configure

                import {inside_name}.svc

                @configure(user_packages=["{package_name}.app", "{inside_name}"])
                @application
                def main(): ...
            """,
            f"{inside_name}/__init__.py": "",
            f"{inside_name}/svc.py": """
                from cullinan import service

                @service
                class InScopeService:
                    pass
            """,
        },
    )
    monkeypatch.syspath_prepend(str(tmp_path))
    _clear_modules(package_name, inside_name)

    entry = importlib.import_module(f"{package_name}.app.root").main

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        app = _build_app(entry)

    try:
        diff = app.get_declaration_diff()

        assert diff.dropped_count == 0
        assert diff.dropped == ()
        assert f"{inside_name}.svc.InScopeService" in diff.assembled
        assert not _rule_warnings(caught), [str(item.message) for item in caught]
    finally:
        app.uninstall()
        _clear_modules(package_name, inside_name)


# ---------------------------------------------------------------------------
# AC-5: default visibility -- WARNING level without any debug switch
# ---------------------------------------------------------------------------
def test_declaration_diff_warning_is_default_visible(tmp_path, monkeypatch, caplog):
    package_name = "decl_diff_visible"
    outside_name = "decl_diff_outside_b"
    _write_tree(
        tmp_path,
        {
            f"{package_name}/__init__.py": "",
            f"{package_name}/app/__init__.py": "",
            f"{package_name}/app/root.py": f"""
                from cullinan import application, configure

                import {outside_name}.svc

                @configure(user_packages=["{package_name}.app"])
                @application
                def main(): ...
            """,
            f"{outside_name}/__init__.py": "",
            f"{outside_name}/svc.py": """
                from cullinan import service

                @service
                class LooseService:
                    pass
            """,
        },
    )
    monkeypatch.syspath_prepend(str(tmp_path))
    _clear_modules(package_name, outside_name)

    entry = importlib.import_module(f"{package_name}.app.root").main

    with caplog.at_level(logging.WARNING):
        app = _build_app(entry)

    try:
        warning_records = [r for r in caplog.records if r.levelno >= logging.WARNING]
        assert warning_records, "expected at least one WARNING-level log record"
        assert any("not assembled" in r.getMessage() for r in warning_records)
    finally:
        app.uninstall()
        _clear_modules(package_name, outside_name)


# ---------------------------------------------------------------------------
# AC-3: the existing component-top-level guard stays reachable
# ---------------------------------------------------------------------------
def test_non_top_level_component_still_emits_top_level_warning():
    from cullinan import component

    PendingRegistry.reset()
    reset_semantic_warnings()

    def build_component():
        @component
        class LocalComponent:
            pass

        return LocalComponent

    build_component()

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        ctx = ApplicationContext()
        ctx.refresh()

    assert any(
        item.category is ComponentDiscoveryWarning
        and TOP_LEVEL_RULE_PHRASE in str(item.message)
        for item in caught
    ), [str(item.message) for item in caught]


# ---------------------------------------------------------------------------
# AC-6: no new top-level symbols; the diff type stays private
# ---------------------------------------------------------------------------
def test_declaration_diff_adds_no_public_symbols():
    import cullinan
    import cullinan.application as application_api
    import cullinan.core as core_api
    import cullinan.web as web_api

    assert len(cullinan.__all__) == 44
    assert len(application_api.__all__) == 26
    assert len(web_api.__all__) == 34
    assert len(core_api.__all__) == 72

    for module in (cullinan, application_api, web_api, core_api):
        assert "_DeclarationDiff" not in module.__all__
        assert "get_declaration_diff" not in module.__all__


def test_declaration_diff_is_a_frozen_private_view():
    from cullinan.application.model import _DeclarationDiff

    diff = _DeclarationDiff(declared=("a",), assembled=(), dropped=("a",))
    assert diff.dropped_count == len(diff.dropped) == 1
    with pytest.raises(Exception):
        diff.dropped = ()  # frozen dataclass


# ---------------------------------------------------------------------------
# AC-8 (partial): the reconciliation is engine neutral (Tornado + ASGI)
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("engine", ["tornado", "asgi"])
def test_declaration_diff_warning_is_engine_neutral(tmp_path, monkeypatch, engine):
    package_name = f"decl_diff_engine_{engine}"
    outside_name = f"decl_diff_engine_outside_{engine}"
    _write_tree(
        tmp_path,
        {
            f"{package_name}/__init__.py": "",
            f"{package_name}/app/__init__.py": "",
            f"{package_name}/app/root.py": f"""
                from cullinan import application, configure

                import {outside_name}.svc

                @configure(user_packages=["{package_name}.app"], server_engine="{engine}")
                @application
                def main(): ...
            """,
            f"{outside_name}/__init__.py": "",
            f"{outside_name}/svc.py": """
                from cullinan import service

                @service
                class EngineOutsideService:
                    pass
            """,
        },
    )
    monkeypatch.syspath_prepend(str(tmp_path))
    _clear_modules(package_name, outside_name)

    entry = importlib.import_module(f"{package_name}.app.root").main

    captured = {}

    class _DummyAdapter:
        def __init__(self, **kwargs):
            captured.update(kwargs)

        def run(self, host="0.0.0.0", port=4080, **kwargs):
            captured["host"] = host

    if engine == "asgi":
        monkeypatch.setattr(public_api, "ASGIAdapter", _DummyAdapter)
        monkeypatch.setattr(
            public_api, "resolve_runtime_engine", lambda value, asgi_server="uvicorn": "asgi"
        )
    else:
        monkeypatch.setattr(public_api, "_load_tornado_adapter", lambda: _DummyAdapter)
        monkeypatch.setattr(
            public_api, "resolve_runtime_engine", lambda value, asgi_server="uvicorn": "tornado"
        )

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        app = entry.run()

    try:
        assert app is not None
        assert _rule_warnings(caught), [str(item.message) for item in caught]
        diff = app.get_declaration_diff()
        assert f"{outside_name}.svc.EngineOutsideService" in diff.dropped
    finally:
        if app is not None:
            app.uninstall()
        _clear_modules(package_name, outside_name)
