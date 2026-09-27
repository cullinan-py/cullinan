# -*- coding: utf-8 -*-
"""Cullinan Gateway Module

The gateway layer provides the transport-agnostic HTTP abstraction:
- WebRequest      – unified request object
- WebResponse     – unified response object
- Router           – prefix-tree route matching
- Dispatcher       – single entry-point request dispatcher
- MiddlewarePipeline – onion-model middleware chain
- ExceptionHandler – global exception → response conversion

Author: plumeink
"""

from .web_core import (
    HeaderPolicy,
    ResponseCookie,
    WebCookies,
    WebExchange,
    WebHeaders,
    WebRequest,
    WebResponse,
)
from .route_types import RouteEntry, RouteMatch, RouteGroup, HTTP_METHODS
from .router import Router
from .dispatcher import Dispatcher
from .invocation import HandlerMethod, ReturnValueHandler, ExceptionResolver
from .runtime import WebRuntime, WebRuntimeConfig, WebRuntimeState
from .pipeline import (
    MiddlewarePipeline,
    GatewayMiddleware,
    HandlerCallable,
    CORSMiddleware,
    RequestTimingMiddleware,
    AccessLogMiddleware,
    LegacyMiddlewareBridge,
)
from .exception_handler import ExceptionHandler
from .openapi import OpenAPIGenerator
from .globals import (
    get_router,
    get_dispatcher,
    get_pipeline,
    get_exception_handler,
    reset_gateway,
)

__all__ = [
    # Request / Response
    'WebRequest',
    'WebResponse',
    'WebHeaders',
    'WebCookies',
    'ResponseCookie',
    'WebExchange',
    'HeaderPolicy',
    # Routing
    'Router',
    'RouteEntry',
    'RouteMatch',
    'RouteGroup',
    'HTTP_METHODS',
    # Dispatch
    'Dispatcher',
    'HandlerMethod',
    'ReturnValueHandler',
    'ExceptionResolver',
    # Pipeline
    'MiddlewarePipeline',
    'GatewayMiddleware',
    'HandlerCallable',
    'CORSMiddleware',
    'RequestTimingMiddleware',
    'AccessLogMiddleware',
    'LegacyMiddlewareBridge',
    # Exception handling
    'ExceptionHandler',
    'WebRuntime',
    'WebRuntimeConfig',
    'WebRuntimeState',
    # OpenAPI
    'OpenAPIGenerator',
    # Global accessors
    'get_router',
    'get_dispatcher',
    'get_pipeline',
    'get_exception_handler',
    'reset_gateway',
]
