# -*- coding: utf-8 -*-
"""Import identity of the middleware facade after the switch.

``cullinan.web.middleware`` used to name the ``@middleware`` decorator, which
shadowed the same-named submodule: the package attribute disagreed with
``sys.modules`` and ``cullinan.web.middleware.Middleware`` raised
``AttributeError``. The name now resolves to the submodule, and the decorator
keeps its top-level promise at ``cullinan.middleware`` through an explicit
rebind in ``cullinan/__init__.py``.

Five properties are pinned here:

* the two names resolve to a module and a function respectively;
* both frozen ``__all__`` entries keep their names -- only the referent of the
  web entry changes;
* the top-level rebind is load-bearing, which is shown by a negative: the module
  is not callable, so losing the rebind would break ``@middleware(...)``;
* the four call sites migrated in the same change no longer take the decorator
  from ``cullinan.web`` and do take it from the top level;
* the migrated middleware still runs when driven through both engines.
"""
from __future__ import annotations

import asyncio
import importlib
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

import cullinan
import cullinan.web
from cullinan import get_config
from cullinan.application import Application
from cullinan.core import PendingRegistry, set_application_context
from cullinan.core.semantic_rules import reset_semantic_warnings
from cullinan.web.controller import reset_controller_registry
from cullinan.web.gateway import WebRuntime, reset_gateway
from cullinan.web.middleware import reset_middleware_registry

REPO_ROOT = Path(__file__).resolve().parents[2]

#: Example modules whose import line moved off ``cullinan.web`` in this change.
MIGRATED_EXAMPLE_MODULES = (
    "examples.extension_registration_demo",
    "examples.middleware_and_module.middleware",
    "examples.middleware_control.middleware",
)

#: Every call site migrated in this change, relative to the repository root.
MIGRATED_FILES = (
    "examples/extension_registration_demo.py",
    "examples/middleware_and_module/middleware.py",
    "examples/middleware_control/middleware.py",
    "tests/core/test_semantic_package_facades.py",
)


@pytest.fixture(autouse=True)
def _reset_runtime_state():
    """Isolate each case: registries, gateway globals and configuration."""
    cfg = get_config()
    original = cfg.to_dict()
    reset_semantic_warnings()
    PendingRegistry.reset()
    reset_controller_registry()
    reset_middleware_registry()
    WebRuntime.clear_active()
    reset_gateway()
    set_application_context(None)

    yield

    current = Application.current()
    if current is not None:
        current.uninstall()

    reset_semantic_warnings()
    PendingRegistry.reset()
    reset_controller_registry()
    reset_middleware_registry()
    WebRuntime.clear_active()
    reset_gateway()
    set_application_context(None)
    cfg.from_dict(original)


def _read_source(relative: str) -> str:
    return (REPO_ROOT / relative).read_text(encoding="utf-8")


def _clear_modules(prefix: str) -> None:
    """Drop cached modules so an import re-runs its module-level registration.

    The example middleware register themselves through ``@middleware`` at import
    time; once another test has imported them, the cache would make a fresh
    import a no-op and leave the (reset) registry empty.
    """
    for name in list(sys.modules):
        if name == prefix or name.startswith(f"{prefix}."):
            sys.modules.pop(name, None)


def _invoke_asgi(app, path: str):
    """Drive the ASGI app once and return ``(status, headers, body)``."""
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
    start = next(message for message in sent if message["type"] == "http.response.start")
    headers = {
        name.decode("latin-1").lower(): value.decode("latin-1")
        for name, value in start.get("headers", [])
    }
    body = b"".join(
        message.get("body", b"")
        for message in sent
        if message["type"] == "http.response.body"
    )
    return start["status"], headers, body


# ---------------------------------------------------------------------------
# The two names
# ---------------------------------------------------------------------------


def test_web_middleware_name_resolves_to_the_submodule():
    assert type(cullinan.web.middleware).__name__ == "module"
    assert cullinan.web.middleware is importlib.import_module("cullinan.web.middleware")
    assert sys.modules["cullinan.web.middleware"] is cullinan.web.middleware


def test_top_level_middleware_name_is_the_decorator():
    assert type(cullinan.middleware).__name__ == "function"
    assert callable(cullinan.middleware)
    assert cullinan.middleware is cullinan.web.middleware.middleware


def test_submodule_member_path_is_usable():
    # The attribute path that used to raise ``AttributeError`` now resolves.
    assert cullinan.web.middleware.Middleware is cullinan.Middleware
    assert "Middleware" in cullinan.web.middleware.__all__


def test_frozen_all_entries_keep_their_names():
    # The names stay in both frozen lists; only the web entry's referent changes
    # (decorator -> submodule). No symbol is renamed or dropped.
    assert "middleware" in cullinan.__all__
    assert "middleware" in cullinan.web.__all__


# ---------------------------------------------------------------------------
# Negative: the rebind is load-bearing, and the old web import is not callable
# ---------------------------------------------------------------------------


def test_top_level_rebind_is_load_bearing():
    """Removing the top-level rebind would break every ``@middleware`` call.

    ``cullinan.web.middleware`` is the submodule and a module is not callable.
    ``from cullinan import middleware`` must therefore hand back the decorator,
    which is exactly what the rebind supplies; without it the top-level name
    would be this module and the decorator form would raise at import time.
    """
    assert not callable(cullinan.web.middleware)
    assert callable(cullinan.middleware)
    assert cullinan.middleware is not cullinan.web.middleware


def test_the_web_import_no_longer_hands_back_the_decorator():
    """Negative: ``from cullinan.web import middleware`` now gives the module.

    Code that still uses that form and calls the name fails, which is why the
    four call sites migrated; the top-level form and the member path keep
    working.
    """
    from cullinan.web import middleware as web_middleware

    assert type(web_middleware).__name__ == "module"
    with pytest.raises(TypeError):
        web_middleware(priority=1)


# ---------------------------------------------------------------------------
# The four migrated call sites
# ---------------------------------------------------------------------------


def test_no_migrated_file_takes_middleware_from_cullinan_web():
    for relative in MIGRATED_FILES:
        offenders = [
            line
            for line in _read_source(relative).splitlines()
            if line.startswith("from cullinan.web import") and "middleware" in line
        ]
        assert offenders == [], f"{relative}: {offenders}"


def test_every_migrated_file_imports_the_decorator_from_the_top_level():
    for relative in MIGRATED_FILES:
        source = _read_source(relative)
        assert any(
            line.startswith("from cullinan import")
            and "middleware" in line.split("import", 1)[1]
            for line in source.splitlines()
        ), f"{relative} does not import `middleware` from the top level"


def test_migrated_example_modules_import_in_a_fresh_process():
    """The migrated example modules import and run in an isolated interpreter.

    They register middleware at module import, so a fresh process keeps that
    side effect out of the harness and still proves the new import path is
    usable at import time.
    """
    env = dict(os.environ)
    env["PYTHONPATH"] = os.pathsep.join(
        [str(REPO_ROOT), *filter(None, [env.get("PYTHONPATH")])]
    )
    probe = (
        "import importlib, json\n"
        "out = {}\n"
        f"for name in {list(MIGRATED_EXAMPLE_MODULES)!r}:\n"
        "    out[name] = importlib.import_module(name).__name__\n"
        "print(json.dumps(sorted(out)))\n"
    )
    completed = subprocess.run(
        [sys.executable, "-c", probe],
        capture_output=True,
        text=True,
        cwd=str(REPO_ROOT),
        env=env,
    )
    assert completed.returncode == 0, completed.stderr
    assert json.loads(completed.stdout.strip()) == sorted(MIGRATED_EXAMPLE_MODULES)


# ---------------------------------------------------------------------------
# Execution: the migrated middleware still runs on both engines
# ---------------------------------------------------------------------------


def test_migrated_example_middleware_runs_on_both_engines():
    """The migrated ``middleware_and_module`` example drives both engines.

    Its middleware comes from the module whose import moved, so a response
    carrying its headers on both engines shows the migration kept the example
    working end to end.
    """
    _clear_modules("examples.middleware_and_module")
    entry_method = importlib.import_module("examples.middleware_and_module.root").main

    asgi_app = entry_method.get_asgi_app()
    asgi_status, asgi_headers, _ = _invoke_asgi(asgi_app, "/inventory/summary")
    assert asgi_status == 200
    assert asgi_headers["x-cullinan-example"] == "middleware-and-module"
    assert asgi_headers["x-module-boundary"] == "examples.middleware_and_module"

    # The same assembled runtime drives the tornado adapter, so both engines run
    # the one shared dispatcher and pipeline.
    app = Application.current()
    tornado_testing = pytest.importorskip("tornado.testing")
    from cullinan.transport.adapter import TornadoAdapter

    tornado_app = TornadoAdapter(
        dispatcher=app.web_runtime.dispatcher,
        runtime=app.web_runtime,
    ).create_app()

    class _Case(tornado_testing.AsyncHTTPTestCase):
        def get_app(self):
            return tornado_app

    case = _Case()
    case.setUp()
    try:
        response = case.fetch("/inventory/summary")
        tornado_headers = {name.lower(): value for name, value in response.headers.items()}
    finally:
        case.tearDown()

    assert response.code == 200
    assert tornado_headers["x-cullinan-example"] == "middleware-and-module"
    assert tornado_headers["x-module-boundary"] == "examples.middleware_and_module"
