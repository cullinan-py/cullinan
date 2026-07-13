# -*- coding: utf-8 -*-
"""Runtime backend selection helpers for transport adapters."""

from __future__ import annotations

import importlib.util


def _is_module_available(module_name: str) -> bool:
    return importlib.util.find_spec(module_name) is not None


def is_runtime_engine_available(engine: str, *, asgi_server: str = "uvicorn") -> bool:
    normalized = (engine or "").strip().lower()
    if normalized == "asgi":
        return _is_module_available(asgi_server)
    if normalized == "tornado":
        return _is_module_available("tornado")
    return False


def get_available_runtime_engines(*, asgi_server: str = "uvicorn") -> list[str]:
    engines: list[str] = []
    if is_runtime_engine_available("asgi", asgi_server=asgi_server):
        engines.append("asgi")
    if is_runtime_engine_available("tornado", asgi_server=asgi_server):
        engines.append("tornado")
    return engines


def resolve_runtime_engine(engine: str | None, *, asgi_server: str = "uvicorn") -> str:
    normalized = (engine or "auto").strip().lower() or "auto"
    if normalized == "auto":
        available = get_available_runtime_engines(asgi_server=asgi_server)
        if available:
            return available[0]
        raise ImportError(
            "No available web backend found. Install cullinan[asgi] or cullinan[tornado], "
            "or explicitly configure an available server_engine."
        )

    if normalized == "asgi":
        if not is_runtime_engine_available("asgi", asgi_server=asgi_server):
            raise ImportError(
                f"ASGI backend unavailable: {asgi_server} not found. "
                "Install cullinan[asgi] or switch to server_engine='tornado'."
            )
        return "asgi"

    if normalized == "tornado":
        if not is_runtime_engine_available("tornado", asgi_server=asgi_server):
            raise ImportError(
                "Tornado backend unavailable. Install cullinan[tornado] or switch to server_engine='asgi'."
            )
        return "tornado"

    raise ValueError(f"Unsupported runtime engine: {engine!r}. Use 'auto', 'asgi', or 'tornado'.")
