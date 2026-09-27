# -*- coding: utf-8 -*-
"""Cullinan Adapter Module

Runtime adapter layer that bridges the transport-agnostic gateway
to concrete HTTP servers.

Supported adapters:
- ``TornadoAdapter`` — Tornado (single-handler mode)
- ``ASGIAdapter``    — ASGI 3.0 (uvicorn / hypercorn)

Author: plumeink
"""

from .base import WebAdapter
from .driver import DriverCapabilities, DriverRequestAdapter, DriverResponseWriter, WebDriver
from .runtime_selection import (
    get_available_runtime_engines,
    is_runtime_engine_available,
    resolve_runtime_engine,
)
__all__ = [
    'WebAdapter',
    'WebDriver',
    'DriverCapabilities',
    'DriverRequestAdapter',
    'DriverResponseWriter',
    'TornadoAdapter',
    'ASGIAdapter',
    'get_available_runtime_engines',
    'is_runtime_engine_available',
    'resolve_runtime_engine',
]


def __getattr__(name):
    if name == "ASGIAdapter":
        from .asgi_adapter import ASGIAdapter

        return ASGIAdapter
    if name == "TornadoAdapter":
        try:
            from .tornado_adapter import TornadoAdapter
        except ImportError:
            return None
        return TornadoAdapter
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
