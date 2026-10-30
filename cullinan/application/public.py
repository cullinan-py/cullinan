# -*- coding: utf-8 -*-
"""Recommended high-level API for regular Cullinan applications."""

from __future__ import annotations

import inspect
import logging
import os
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

logger = logging.getLogger(__name__)


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


def _resolve_engine_setting_and_source(
    engine: Optional[str],
    file_config: Optional[dict],
) -> tuple[str, str]:
    """The engine setting, and the layer that decided it.

    Four layers can name the engine -- the ``run()`` argument, the environment, the
    configuration file and ``configure(...)`` -- and when two of them disagree the
    operator needs to know which one won without reading the source. Returning the
    source alongside the value is what makes that printable, and printing it is
    what turns "which engine am I running?" into a question the log answers.
    """
    if engine:
        return engine.strip().lower(), f"run(engine={engine!r})"
    env_engine = os.getenv("CULLINAN_ENGINE", "").strip().lower()
    if env_engine:
        return env_engine, "environment (CULLINAN_ENGINE)"
    if isinstance(file_config, dict) and "server_engine" in file_config:
        return (
            str(getattr(get_config(), "server_engine", "auto")),
            "configuration file (server_engine)",
        )
    configured = str(getattr(get_config(), "server_engine", "auto") or "auto")
    if configured.strip().lower() != "auto":
        return configured, "configure(server_engine=...)"
    return "auto", "built-in default (auto)"


def _warn_if_engine_variable_is_not_one_we_read() -> None:
    """Report ``SERVER_ENGINE`` when it is set, because it is not a setting.

    ``SERVER_HOST`` and ``SERVER_PORT`` are read, so ``SERVER_ENGINE`` reads like
    the third member of the same family. It is not: the engine comes from
    ``CULLINAN_ENGINE``. A deployment that sets the wrong one gets the default
    engine and no error, so two runs that were meant to compare engines can both
    be the same engine -- which is how a measured difference becomes a phantom.
    """
    if not os.environ.get("SERVER_ENGINE", "").strip():
        return
    if os.getenv("CULLINAN_ENGINE", "").strip():
        return
    logger.warning(
        "SERVER_ENGINE=%r is set but is not a variable this framework reads; the engine is "
        "chosen by CULLINAN_ENGINE (or run(engine=...), or server_engine in the configuration "
        "file). Ignoring it.",
        os.environ.get("SERVER_ENGINE", ""),
    )


def _announce_engine(engine: Optional[str], file_config: Optional[dict]) -> str:
    """Resolve the engine, print the layer that decided it, and return it.

    The line is printed at start-up rather than on demand: the question "which
    engine is this process actually running?" is asked when something behaves
    differently than expected, and by then nobody wants to add logging and
    redeploy.
    """
    _warn_if_engine_variable_is_not_one_we_read()
    setting, source = _resolve_engine_setting_and_source(engine, file_config)
    asgi_server = getattr(get_config(), "asgi_server", "uvicorn")
    actual_engine = resolve_runtime_engine(setting, asgi_server=asgi_server)
    logger.info("└---Web engine: %s (decided by: %s)", actual_engine, source)
    return actual_engine


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
            # because it is resolved after this. The returned mapping is also how
            # the start-up line can say *which* layer chose the engine.
            file_config = apply_project_config()
            actual_engine = _announce_engine(engine, file_config)
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
