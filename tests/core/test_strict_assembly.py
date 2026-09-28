# -*- coding: utf-8 -*-
"""``strict_assembly``: the declared-vs-assembled report, optionally required.

The always-on behaviour is covered by ``test_declaration_diff.py`` and
``test_declared_not_assembled_visibility.py``: a component whose package is
missing from ``user_packages`` is *declared but not assembled*, and that
difference is reported without stopping startup.

``configure(strict_assembly=True)`` makes the very same difference fatal. These
tests pin the parts that make the switch safe to adopt:

* it is off by default, so the default path is today's behaviour;
* the failure carries the count, every dropped name, the existing rule
  identifier and an actionable fix;
* the report is still emitted *before* the failure -- the warning is what
  survives a deployment whose own ``try/except`` swallows the exception;
* the exclusion list changes the action only, never the reported facts;
* nothing is auto-assembled and no public symbol is added;
* the switch does not depend on one particular entry path;
* introspection stays available -- ``get_declaration_diff()`` must keep working
  even when ``refresh()`` would fail.

Every test builds its own throw-away package: the declaration snapshot is taken
from the import-time registry, so reusing a package inside one process would
reconcile against an empty declaration set and silently pass.
"""

import contextlib
import importlib
import inspect
import sys
import textwrap
import warnings

import pytest

from cullinan import configure
from cullinan.application import Application
from cullinan.application import public as public_api
from cullinan.core import PendingRegistry, set_application_context
from cullinan.core.semantic_rules import (
    ComponentDiscoveryWarning,
    reset_semantic_warnings,
)
from cullinan.support.config import get_config
from cullinan.support.exceptions import ConfigurationError, CullinanError
from cullinan.web.controller import reset_controller_registry
from cullinan.web.gateway import WebRuntime, reset_gateway

RULE_KEY = "component-declared-not-assembled"


@pytest.fixture(autouse=True)
def _reset_semantic_and_runtime_state():
    reset_semantic_warnings()
    set_application_context(None)
    PendingRegistry.reset()
    WebRuntime.clear_active()
    reset_gateway()
    reset_controller_registry()
    # The switch lives on the process-wide config object, and the entry-method
    # decorator writes to it at import time. Restore the pre-test snapshot so a
    # strict test cannot leak into the next one.
    config = get_config()
    snapshot = config.to_dict()
    yield
    config.from_dict(snapshot)
    reset_semantic_warnings()
    set_application_context(None)
    PendingRegistry.reset()
    WebRuntime.clear_active()
    reset_gateway()
    reset_controller_registry()


def _write_tree(root, files):
    """Write ``{relative_path: source}`` under ``root`` (paths from ``root``)."""
    for relative_path, content in files.items():
        target = root / relative_path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(textwrap.dedent(content).strip() + "\n", encoding="utf-8")


def _clear_modules(*prefixes):
    for module_name in list(sys.modules):
        for prefix in prefixes:
            if module_name == prefix or module_name.startswith(f"{prefix}."):
                sys.modules.pop(module_name, None)
                break


def _outside_package(slug):
    return f"sa_outside_{slug}"


def _identity(slug, class_name):
    """The component identity the declaration report itself produces."""
    return f"{_outside_package(slug)}.svc.{class_name}"


def _dropped_names(slug, class_names):
    return tuple(sorted(_identity(slug, name) for name in class_names))


def _make_tree(tmp_path, monkeypatch, slug, *, strict=False, excludes=None, outside_classes=("LooseService",)):
    """Materialise a fresh app whose declarer package is out of scope.

    ``strict=None`` leaves ``strict_assembly`` out of the entry's configuration
    entirely, which is the genuine "nothing was set" default path.

    Returns ``(entry, package, outside, outside_module, dropped_names)``. The
    identity form used for the expectations is the one the report produces
    (``package.module.Component``), so these tests double as a check on that
    shared identity.
    """
    package = f"sa_app_{slug}"
    outside = _outside_package(slug)

    decorator_kwargs = [f'user_packages=["{package}.app"]']
    if strict is not None:
        decorator_kwargs.append(f"strict_assembly={strict}")
    if excludes is not None:
        rendered = ", ".join(repr(item) for item in excludes)
        decorator_kwargs.append(f"strict_assembly_excludes=[{rendered}]")
    decorator = "@configure(\n" + "".join(f"    {item},\n" for item in decorator_kwargs) + ")"

    classes = "\n\n".join(
        f"@service\nclass {name}:\n    pass\n" for name in outside_classes
    )

    root_source = (
        "from cullinan import application, configure\n"
        "\n"
        f"import {outside}.svc  # deliberately outside user_packages\n"
        "\n"
        f"{decorator}\n"
        "@application\n"
        "def main(): ...\n"
    )
    service_source = f"from cullinan import service\n\n\n{classes}\n"

    _write_tree(
        tmp_path,
        {
            f"{package}/__init__.py": "",
            f"{package}/app/__init__.py": "",
            f"{package}/app/root.py": root_source,
            f"{outside}/__init__.py": "",
            f"{outside}/svc.py": service_source,
        },
    )
    monkeypatch.syspath_prepend(str(tmp_path))
    _clear_modules(package, outside)

    entry = importlib.import_module(f"{package}.app.root").main
    outside_module = importlib.import_module(f"{outside}.svc")
    return entry, package, outside, outside_module, _dropped_names(slug, outside_classes)


def _rule_warnings(caught):
    return [
        item
        for item in caught
        if item.category is ComponentDiscoveryWarning and RULE_KEY in str(item.message)
    ]


@contextlib.contextmanager
def _capture():
    """Record the semantic diagnostics instead of letting them print."""
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        yield caught


def _build(entry):
    app = Application(entry)
    app.build()
    return app


# ---------------------------------------------------------------------------
# Default is off -- the report stays non-blocking
# ---------------------------------------------------------------------------
def test_default_keeps_the_report_non_blocking(tmp_path, monkeypatch):
    # ``strict=None``: the entry does not mention the option at all, so this is
    # the unconfigured default rather than an explicit ``False``.
    entry, package, outside, _module, dropped = _make_tree(tmp_path, monkeypatch, "default", strict=None)

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        app = _build(entry)

    try:
        diff = app.get_declaration_diff()
        assert diff.dropped == dropped
        assert diff.dropped_count == len(diff.dropped) == 1
        assert _rule_warnings(caught), [str(item.message) for item in caught]
    finally:
        app.uninstall()
        _clear_modules(package, outside)


def test_default_value_is_off_in_config_and_in_the_signature():
    config = get_config()
    assert config.strict_assembly is False
    assert config.strict_assembly_excludes is None

    parameters = inspect.signature(configure).parameters
    strict = parameters["strict_assembly"]
    assert strict.kind is inspect.Parameter.KEYWORD_ONLY
    assert strict.default is False

    excludes = parameters["strict_assembly_excludes"]
    assert excludes.kind is inspect.Parameter.KEYWORD_ONLY
    assert excludes.default is None


def test_config_round_trips_through_to_dict_and_from_dict():
    config = get_config()
    exact = config.to_dict()
    assert exact["strict_assembly"] is False
    assert exact["strict_assembly_excludes"] is None

    exact["strict_assembly"] = True
    exact["strict_assembly_excludes"] = ["pkg.mod.Component"]
    config.from_dict(exact)
    exported = config.to_dict()
    assert exported["strict_assembly"] is True
    assert exported["strict_assembly_excludes"] == ["pkg.mod.Component"]

    # An empty list is preserved rather than normalised into ``None``.
    config.from_dict({**exported, "strict_assembly_excludes": []})
    assert config.to_dict()["strict_assembly_excludes"] == []


# ---------------------------------------------------------------------------
# Enabling it fails, and the failure says what and how to fix
# ---------------------------------------------------------------------------
def test_strict_failure_reports_count_names_and_fix(tmp_path, monkeypatch):
    entry, package, outside, _module, dropped = _make_tree(tmp_path, monkeypatch, "strictfail", strict=True)

    with _capture():
        with pytest.raises(ConfigurationError) as excinfo:
            _build(entry)

    try:
        message = str(excinfo.value)
        # (a) every dropped component, by its qualified name
        assert dropped[0] in message, message
        # (b) the count
        assert f"{len(dropped)} component(s)" in message, message
        # (c) the existing rule identifier -- reused, not reinvented
        assert RULE_KEY in message, message
        # (d) an actionable fix
        assert "user_packages" in message, message
        assert "module top level" in message, message

        # The failure uses the pre-existing exception, not a new one.
        assert type(excinfo.value) is ConfigurationError
        assert isinstance(excinfo.value, CullinanError)
        assert excinfo.value.error_code == "CONFIG_ERROR"
        assert excinfo.value.details["dropped_count"] == len(dropped)
        assert tuple(excinfo.value.details["dropped"]) == dropped
    finally:
        _clear_modules(package, outside)


def test_strict_failure_aborts_startup_without_activating_a_runtime(tmp_path, monkeypatch):
    """The failure stops startup; nothing is activated.

    The failure fires inside ``refresh()`` -- the report point -- so the
    candidate ``Runtime`` has been assembled by the time it raises. What must
    not happen is activation: no web runtime is published, and neither the
    application nor its runtime reaches the ``active`` phase.
    """
    entry, package, outside, _module, _dropped = _make_tree(tmp_path, monkeypatch, "noruntime", strict=True)

    app = Application(entry)
    with _capture():
        with pytest.raises(ConfigurationError):
            app.build()

    try:
        assert WebRuntime.current() is None
        assert app.phase != "active"
        assert app.runtime is None or app.runtime.phase != "active"
    finally:
        _clear_modules(package, outside)


# ---------------------------------------------------------------------------
# The warning is emitted first, then the failure -- both, not either
# ---------------------------------------------------------------------------
def test_strict_emits_the_warning_and_then_fails(tmp_path, monkeypatch):
    entry, package, outside, _module, dropped = _make_tree(tmp_path, monkeypatch, "warn", strict=True)

    with _capture() as caught:
        with pytest.raises(ConfigurationError) as excinfo:
            _build(entry)

    try:
        messages = [str(item.message) for item in _rule_warnings(caught)]
        assert messages, [str(item.message) for item in caught]
        assert any("not assembled" in message for message in messages)
        assert any(dropped[0] in message for message in messages)
        # The exception fired too, in the same run.
        assert RULE_KEY in str(excinfo.value)
    finally:
        _clear_modules(package, outside)


# ---------------------------------------------------------------------------
# Exclusions change the action, never the facts, and nothing is auto-assembled
# ---------------------------------------------------------------------------
def test_exclusion_clears_the_failure_but_not_the_reported_facts(tmp_path, monkeypatch):
    acknowledged = _identity("excl", "LooseService")
    entry, package, outside, module, dropped = _make_tree(
        tmp_path, monkeypatch, "excl", strict=True, excludes=[acknowledged],
    )
    assert dropped == (acknowledged,)

    try:
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            app = _build(entry)

        try:
            diff = app.get_declaration_diff()
            # The action changed: startup completed.
            assert diff.dropped == dropped, diff.dropped
            assert diff.dropped_count == 1
            # The facts did not: the component is still declared-but-not-assembled.
            assert acknowledged not in diff.assembled
            # And it was not silently assembled either.
            assert app.get_component_owner(module.LooseService) is None
            assert not [
                name for name in app.context.list_definitions() if "LooseService" in name
            ], app.context.list_definitions()
            # The report itself is unchanged as well.
            messages = [str(item.message) for item in _rule_warnings(caught)]
            assert any(acknowledged in message for message in messages), messages
        finally:
            app.uninstall()
    finally:
        _clear_modules(package, outside)


def test_partial_exclusion_still_fails_for_the_rest(tmp_path, monkeypatch):
    names = ("KeptService", "AcknowledgedService")
    acknowledged = _identity("partial", "AcknowledgedService")
    entry, package, outside, _module, dropped = _make_tree(
        tmp_path, monkeypatch, "partial", strict=True,
        excludes=[acknowledged], outside_classes=names,
    )

    try:
        with _capture():
            with pytest.raises(ConfigurationError) as excinfo:
                _build(entry)
        message = str(excinfo.value)
        # Every dropped name is still reported -- the acknowledged one included.
        for name in dropped:
            assert name in message, message
        assert f"{len(dropped)} component(s)" in message, message
    finally:
        _clear_modules(package, outside)


def test_exclusion_matching_uses_the_qualified_identity(tmp_path, monkeypatch):
    """A bare class name is not the identity the report uses, so it does not match."""
    entry, package, outside, _module, dropped = _make_tree(
        tmp_path, monkeypatch, "bare", strict=True, excludes=["LooseService"],
    )

    try:
        with _capture():
            with pytest.raises(ConfigurationError) as excinfo:
                _build(entry)
        assert dropped[0] in str(excinfo.value)
    finally:
        _clear_modules(package, outside)


def test_empty_exclusion_list_is_the_same_as_no_exclusions(tmp_path, monkeypatch):
    entry, package, outside, _module, _dropped = _make_tree(
        tmp_path, monkeypatch, "empty", strict=True, excludes=[],
    )

    try:
        with _capture():
            with pytest.raises(ConfigurationError):
                _build(entry)
    finally:
        _clear_modules(package, outside)


# ---------------------------------------------------------------------------
# Introspection must survive the switch
# ---------------------------------------------------------------------------
def test_declaration_diff_stays_queryable_under_strict(tmp_path, monkeypatch):
    """``get_declaration_diff()`` only discovers; it must not trip the check.

    Discovery and introspection never reach the report point, so an application
    that could not start can still be diagnosed before ``refresh()`` runs.
    """
    entry, package, outside, _module, dropped = _make_tree(tmp_path, monkeypatch, "introspect", strict=True)

    try:
        app = Application(entry)
        diff = app.get_declaration_diff()
        assert diff.dropped == dropped
    finally:
        _clear_modules(package, outside)


# ---------------------------------------------------------------------------
# The switch is not tied to a single entry path
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("path", ["entry_method", "adapter"])
def test_strict_applies_on_both_entry_paths(tmp_path, monkeypatch, path):
    entry, package, outside, _module, dropped = _make_tree(
        tmp_path, monkeypatch, f"path{path}", strict=True,
    )

    class _DummyAdapter:
        def __init__(self, **kwargs):
            pass

        def run(self, host="0.0.0.0", port=4080, **kwargs):
            raise AssertionError("no server may be started when startup fails")

    try:
        if path == "entry_method":
            # The recommended path: an @application entry method plus @configure.
            monkeypatch.setattr(public_api, "_load_tornado_adapter", lambda: _DummyAdapter)
            monkeypatch.setattr(
                public_api, "resolve_runtime_engine", lambda value, asgi_server="uvicorn": "tornado"
            )
            with _capture():
                with pytest.raises(ConfigurationError) as excinfo:
                    entry.run()
        else:
            # The adapter-facing path: the same build, entered through ASGI.
            with _capture():
                with pytest.raises(ConfigurationError) as excinfo:
                    entry.get_asgi_app()

        message = str(excinfo.value)
        assert RULE_KEY in message, message
        assert dropped[0] in message, message
        assert f"{len(dropped)} component(s)" in message, message
        assert type(excinfo.value) is ConfigurationError
    finally:
        _clear_modules(package, outside)


# ---------------------------------------------------------------------------
# The frozen public surface is untouched
# ---------------------------------------------------------------------------
def test_strict_assembly_adds_no_public_symbols():
    import cullinan
    import cullinan.application as application_api
    import cullinan.core as core_api
    import cullinan.web as web_api

    assert len(cullinan.__all__) == 44
    assert len(application_api.__all__) == 26
    assert len(web_api.__all__) == 34
    assert len(core_api.__all__) == 72

    for module in (cullinan, application_api, web_api, core_api):
        assert "strict_assembly" not in module.__all__
        assert "strict_assembly_excludes" not in module.__all__
        assert "ConfigurationError" not in module.__all__
