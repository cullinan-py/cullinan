# -*- coding: utf-8 -*-
"""``drain_timeout`` is the single, real drain timeout source.

The runtime configuration field used to be declared and never read: the drain
path called ``ApplicationContext.shutdown`` with its own hard-coded default. The
finalise path now passes ``WebRuntimeConfig.drain_timeout`` straight through, so
the field actually drives the drain bound.

The default resolves to the very value the shutdown call used to hard-code, so
the default behaviour is unchanged. Both engines are exercised: the drain path
is shared, but the adapters own their own request plumbing.
"""
import asyncio
import importlib
import inspect
import sys

import pytest

from cullinan.application import Application
from cullinan.application.model import _clone_runtime_config
from cullinan.core import PendingRegistry, set_application_context
from cullinan.core.application_context import ApplicationContext
from cullinan.web.controller import reset_controller_registry
from cullinan.web.gateway import WebRuntime, WebRuntimeConfig, reset_gateway
from cullinan.web.middleware import reset_middleware_registry

# The value both the field and the shutdown call used to agree on.
EXPECTED_DEFAULT_DRAIN_TIMEOUT = 30.0


@pytest.fixture(autouse=True)
def _reset_application_state():
    set_application_context(None)
    PendingRegistry.reset()
    WebRuntime.clear_active()
    reset_gateway()
    reset_controller_registry()
    reset_middleware_registry()
    yield
    set_application_context(None)
    PendingRegistry.reset()
    WebRuntime.clear_active()
    reset_gateway()
    reset_controller_registry()
    reset_middleware_registry()


def _clear_modules(prefix):
    for module_name in list(sys.modules):
        if module_name == prefix or module_name.startswith(f"{prefix}."):
            sys.modules.pop(module_name, None)


def _write_app_package(tmp_path, package_name):
    package_root = tmp_path / package_name
    package_root.mkdir(parents=True, exist_ok=True)
    (package_root / "__init__.py").write_text("", encoding="utf-8")
    (package_root / "root.py").write_text(
        "from cullinan import controller, get_api, module\n"
        "\n"
        "@controller(url=\"/probe\")\n"
        "class ProbeController:\n"
        "    @get_api(url=\"\")\n"
        "    def probe(self):\n"
        "        return {\"ok\": True}\n"
        "\n"
        "@module\n"
        "class RootModule:\n"
        "    pass\n",
        encoding="utf-8",
    )


def _build_app(tmp_path, monkeypatch, package_name, *, runtime_config=None):
    _write_app_package(tmp_path, package_name)
    monkeypatch.syspath_prepend(str(tmp_path))
    _clear_modules(package_name)
    importlib.invalidate_caches()
    root_module = importlib.import_module(f"{package_name}.root").RootModule
    return Application.run(root_module, runtime_config=runtime_config)


def _spy_shutdown(monkeypatch):
    """Record every ``timeout`` the drain path hands to the context shutdown."""
    seen = []
    original = ApplicationContext.shutdown

    def spy(self, timeout=30.0):
        seen.append(timeout)
        return original(self, timeout)

    monkeypatch.setattr(ApplicationContext, "shutdown", spy)
    return seen


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


# ---------------------------------------------------------------------------
# The three values that must agree, so the default path stays neutral
# ---------------------------------------------------------------------------


def test_default_resolves_to_the_value_the_shutdown_call_used_to_hard_code():
    declared_default = WebRuntimeConfig().drain_timeout
    hardcoded_default = inspect.signature(ApplicationContext.shutdown).parameters["timeout"].default
    cloned_default = _clone_runtime_config(None).drain_timeout

    assert declared_default == hardcoded_default == cloned_default == EXPECTED_DEFAULT_DRAIN_TIMEOUT


def test_clone_keeps_an_explicit_drain_timeout():
    assert _clone_runtime_config(WebRuntimeConfig(drain_timeout=7.5)).drain_timeout == 7.5
    assert _clone_runtime_config(WebRuntimeConfig()).drain_timeout == EXPECTED_DEFAULT_DRAIN_TIMEOUT


# ---------------------------------------------------------------------------
# The value actually reaches the drain path
# ---------------------------------------------------------------------------


def test_default_app_drains_with_the_declared_default(tmp_path, monkeypatch):
    seen = _spy_shutdown(monkeypatch)
    app = _build_app(tmp_path, monkeypatch, "drain_default_app")
    try:
        assert app.web_runtime.config.drain_timeout == EXPECTED_DEFAULT_DRAIN_TIMEOUT
    finally:
        app.uninstall()

    assert seen, "the drain path must hand a timeout to the context shutdown"
    assert set(seen) == {EXPECTED_DEFAULT_DRAIN_TIMEOUT}


def test_a_configured_drain_timeout_drives_the_shutdown(tmp_path, monkeypatch):
    seen = _spy_shutdown(monkeypatch)
    app = _build_app(
        tmp_path,
        monkeypatch,
        "drain_custom_app",
        runtime_config=WebRuntimeConfig(drain_timeout=7.5),
    )
    try:
        assert app.web_runtime.config.drain_timeout == 7.5
    finally:
        app.uninstall()

    assert seen
    assert set(seen) == {7.5}, seen


# ---------------------------------------------------------------------------
# Both engines: the drain path still completes through each adapter
# ---------------------------------------------------------------------------


def _run_drain_through_engine(tmp_path, monkeypatch, package_name, engine):
    seen = _spy_shutdown(monkeypatch)
    app = _build_app(
        tmp_path,
        monkeypatch,
        package_name,
        runtime_config=WebRuntimeConfig(drain_timeout=5.0),
    )
    try:
        if engine == "asgi":
            from cullinan.transport.adapter import ASGIAdapter

            adapter = ASGIAdapter(dispatcher=app.web_runtime.dispatcher, runtime=app.web_runtime)
            events = _dispatch_asgi(adapter.create_app(), "/probe")
            status = next(event for event in events if event["type"] == "http.response.start")["status"]
        else:
            tornado_testing = pytest.importorskip("tornado.testing")
            from cullinan.transport.adapter import TornadoAdapter

            adapter = TornadoAdapter(dispatcher=app.web_runtime.dispatcher, runtime=app.web_runtime)
            http_app = adapter.create_app()

            class _Case(tornado_testing.AsyncHTTPTestCase):
                def get_app(self):
                    return http_app

            case = _Case()
            case.setUp()
            try:
                status = case.fetch("/probe").code
            finally:
                case.tearDown()

        assert status == 200
        # No request is in flight when the app is torn down, so the drain
        # completes immediately and hands the configured bound to the shutdown.
        app.uninstall()
        assert app.runtime.phase == "closed"
    finally:
        if Application.current() is app:
            app.uninstall()

    assert seen
    assert set(seen) == {5.0}, seen
    _clear_modules(package_name)


def test_drain_completes_through_the_asgi_engine(tmp_path, monkeypatch):
    _run_drain_through_engine(tmp_path, monkeypatch, "drain_asgi_app", "asgi")


def test_drain_completes_through_the_tornado_engine(tmp_path, monkeypatch):
    _run_drain_through_engine(tmp_path, monkeypatch, "drain_tornado_app", "tornado")
