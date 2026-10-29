# -*- coding: utf-8 -*-
"""Recommended high-level API for regular Cullinan applications."""

from __future__ import annotations

import os
import inspect
from typing import Any, Callable, Optional

from cullinan._api_boundary import public_api_context
from cullinan.application.legacy import _build_transport_settings, _collect_global_headers, _finalize_runtime_setup
from cullinan.application.model import Application, has_application_metadata, has_module_metadata
from cullinan.support.config import get_class_config, get_config, push_config_overrides
from cullinan.support.diagnostics import (
    invalid_application_entry,
    legacy_public_entry_removed,
    legacy_root_module_entry_removed,
    require_application_entry,
)
from cullinan.support.config_file import apply_project_config
from cullinan.transport.adapter.asgi_adapter import ASGIAdapter
from cullinan.transport.adapter.runtime_selection import resolve_runtime_engine


def _resolve_entry_method(
    api_name: str,
    entry_method: Optional[Callable[..., Any]],
    root_module: Optional[type[Any]],
) -> Callable[..., Any]:
    if root_module is not None:
        raise RuntimeError(legacy_root_module_entry_removed())

    if entry_method is None:
        raise RuntimeError(require_application_entry(api_name))
    if inspect.isclass(entry_method):
        raise RuntimeError(legacy_public_entry_removed(api_name, entry_method))
    if has_module_metadata(entry_method) and not has_application_metadata(entry_method):
        raise RuntimeError(legacy_public_entry_removed(api_name, entry_method))
    if callable(entry_method) and has_application_metadata(entry_method):
        return entry_method
    raise RuntimeError(invalid_application_entry(api_name, entry_method))


def _resolve_engine_setting(engine: Optional[str]) -> str:
    if engine:
        return engine.strip().lower()
    env_engine = os.getenv("CULLINAN_ENGINE", "").strip().lower()
    if env_engine:
        return env_engine
    return getattr(get_config(), "server_engine", "auto")


def _resolve_engine(engine: Optional[str]) -> str:
    asgi_server = getattr(get_config(), "asgi_server", "uvicorn")
    return resolve_runtime_engine(_resolve_engine_setting(engine), asgi_server=asgi_server)


def _resolve_host_port(host: Optional[str], port: Optional[int]) -> tuple[str, int]:
    cfg = get_config()
    resolved_host = host or os.getenv("SERVER_HOST") or getattr(cfg, "server_host", "0.0.0.0")
    resolved_port = int(port or os.getenv("SERVER_PORT") or getattr(cfg, "server_port", 4080))
    return resolved_host, resolved_port


def _finalize_public_runtime() -> tuple[list, dict[str, Any]]:
    _finalize_runtime_setup()
    return _collect_global_headers(), _build_transport_settings()


def _load_tornado_adapter():
    from cullinan.transport.adapter.tornado_adapter import TornadoAdapter

    return TornadoAdapter


def run(
    entry_method: Optional[Callable[..., Any]] = None,
    *,
    root_module: Optional[type[Any]] = None,
    engine: Optional[str] = None,
    host: Optional[str] = None,
    port: Optional[int] = None,
    runtime_config: Optional[Any] = None,
    **adapter_kwargs: Any,
) -> Optional[Application]:
    """Run a regular Cullinan application through the recommended top-level API."""

    resolved_entry_method = _resolve_entry_method("cullinan.run", entry_method, root_module)

    with public_api_context():
        with push_config_overrides(get_class_config(resolved_entry_method)):
            # Configuration file first: the engine and the bind address may be
            # named there, and a value the caller passes explicitly still wins
            # because it is resolved after this.
            apply_project_config()
            actual_engine = _resolve_engine(engine)
            resolved_host, resolved_port = _resolve_host_port(host, port)
            app = Application.run(resolved_entry_method, runtime_config=runtime_config)
            global_headers, transport_settings = _finalize_public_runtime()
            if actual_engine == "asgi":
                adapter = ASGIAdapter(
                    dispatcher=app.web_runtime.dispatcher,
                    global_headers=global_headers,
                    runtime=app.web_runtime,
                )
                adapter_kwargs.setdefault("server", getattr(get_config(), "asgi_server", "uvicorn"))
            else:
                adapter = _load_tornado_adapter()(
                    dispatcher=app.web_runtime.dispatcher,
                    settings=transport_settings,
                    global_headers=global_headers,
                    runtime=app.web_runtime,
                )

            adapter.run(host=resolved_host, port=resolved_port, **adapter_kwargs)
            return app


def get_asgi_app(
    entry_method: Optional[Callable[..., Any]] = None,
    *,
    root_module: Optional[type[Any]] = None,
    runtime_config: Optional[Any] = None,
):
    """Create an ASGI app through the recommended top-level API."""

    resolved_entry_method = _resolve_entry_method("cullinan.get_asgi_app", entry_method, root_module)

    with public_api_context():
        with push_config_overrides(get_class_config(resolved_entry_method)):
            apply_project_config()
            app = Application.run(resolved_entry_method, runtime_config=runtime_config)
            global_headers, _ = _finalize_public_runtime()
            adapter = ASGIAdapter(
                dispatcher=app.web_runtime.dispatcher,
                global_headers=global_headers,
                runtime=app.web_runtime,
            )
            return adapter.create_app()
