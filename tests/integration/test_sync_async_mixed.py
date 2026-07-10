# -*- coding: utf-8 -*-
"""Regression for public dispatch surface when sync and async controller methods are mixed."""

import asyncio
import importlib
import json
import sys
import textwrap
from pathlib import Path

import pytest

from cullinan import get_config
from cullinan.application import Application
from cullinan.core import PendingRegistry, set_application_context
from cullinan.core.semantic_rules import reset_semantic_warnings
from cullinan.web.controller import reset_controller_registry
from cullinan.web.gateway import WebRuntime, reset_gateway
from cullinan.web.middleware import reset_middleware_registry


def _write_package(tmp_path: Path, package_name: str, files: dict[str, str]) -> None:
    root = tmp_path / package_name
    for relative_path, content in files.items():
        target = root / relative_path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(textwrap.dedent(content).strip() + "\n", encoding="utf-8")


def _clear_modules(prefix: str) -> None:
    for module_name in list(sys.modules):
        if module_name == prefix or module_name.startswith(f"{prefix}."):
            sys.modules.pop(module_name, None)


async def _invoke_asgi_app(
    app,
    path: str,
    method: str = "GET",
    body: bytes = b"",
) -> tuple[int, dict]:
    messages = []
    delivered = False

    async def receive():
        nonlocal delivered
        if delivered:
            return {"type": "http.disconnect"}
        delivered = True
        return {"type": "http.request", "body": body, "more_body": False}

    async def send(message):
        messages.append(message)

    scope = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": method,
        "scheme": "http",
        "path": path,
        "raw_path": path.encode("utf-8"),
        "query_string": b"",
        "headers": [
            (b"host", b"example.test"),
            (b"content-type", b"application/json"),
        ],
        "client": ("127.0.0.1", 12345),
        "server": ("example.test", 80),
    }

    await app(scope, receive, send)

    start = next(message for message in messages if message["type"] == "http.response.start")
    body_message = next(message for message in messages if message["type"] == "http.response.body")
    return start["status"], json.loads(body_message["body"].decode("utf-8"))


@pytest.fixture(autouse=True)
def _reset_runtime_state():
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


def test_sync_and_async_controller_methods_share_same_public_dispatch_path(tmp_path, monkeypatch):
    package_name = "mixed_runtime_app"
    _write_package(
        tmp_path,
        package_name,
        {
            "__init__.py": "",
            "root.py": """
                import json

                from cullinan import application, configure, controller, get_api, post_api


                @controller(url="/api")
                class MixedController:
                    @post_api(url="/sync-method", get_request_body=True)
                    def sync_webhook(self, request_body):
                        payload = request_body
                        if isinstance(payload, (bytes, bytearray)):
                            payload = json.loads(payload.decode("utf-8"))
                        return {"sync": True, "executed": True, "payload": payload}

                    @post_api(url="/async-method", get_request_body=True)
                    async def async_webhook(self, request_body):
                        payload = request_body
                        if isinstance(payload, (bytes, bytearray)):
                            payload = json.loads(payload.decode("utf-8"))
                        return {"async": True, "executed": True, "payload": payload}

                    @get_api(url="/health")
                    def health_check(self):
                        return {"status": "ok"}


                @configure(user_packages=["mixed_runtime_app"])
                @application
                def main(): ...
            """,
        },
    )
    monkeypatch.syspath_prepend(str(tmp_path))
    _clear_modules(package_name)

    try:
        main = importlib.import_module(f"{package_name}.root").main
        app = main.get_asgi_app()

        sync_status, sync_payload = asyncio.run(
            _invoke_asgi_app(
                app,
                "/api/sync-method",
                method="POST",
                body=json.dumps({"test": "sync"}).encode("utf-8"),
            )
        )
        async_status, async_payload = asyncio.run(
            _invoke_asgi_app(
                app,
                "/api/async-method",
                method="POST",
                body=json.dumps({"test": "async"}).encode("utf-8"),
            )
        )
        health_status, health_payload = asyncio.run(_invoke_asgi_app(app, "/api/health"))

        assert sync_status == 200
        assert sync_payload == {"sync": True, "executed": True, "payload": {"test": "sync"}}

        assert async_status == 200
        assert async_payload == {"async": True, "executed": True, "payload": {"test": "async"}}

        assert health_status == 200
        assert health_payload == {"status": "ok"}
    finally:
        _clear_modules(package_name)
