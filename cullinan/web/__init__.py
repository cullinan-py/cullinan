# -*- coding: utf-8 -*-
"""Business-facing Web facade for Cullinan."""

from cullinan.web.controller import (
    Handler,
    get_api,
    get_missing_header_handler,
    patch_api,
    post_api,
    put_api,
    delete_api,
    response,
    set_missing_header_handler,
)
from cullinan.core import controller
from cullinan.web.gateway import WebRequest, WebResponse
from cullinan.web.middleware import BodyDecoderMiddleware, Middleware, get_decoded_body, set_decoded_body
from cullinan.web.params import (
    Auto,
    AutoType,
    Body,
    DynamicBody,
    File,
    Header,
    Param,
    ParamResolver,
    ParamValidator,
    Path,
    Query,
    ResolveError,
    TypeConverter,
    UNSET,
    ValidationError,
)
from cullinan.web.static import StaticFiles
from cullinan.web.websocket_registry import websocket_handler

# The ``middleware`` entry of this package changes referent on this release
# line: the name now resolves to the ``cullinan.web.middleware`` submodule
# instead of the decorator, which stays available at the top level
# (``from cullinan import middleware``). A caller still reaching for the old
# decorator binding fails immediately (``'module' object is not callable``)
# rather than silently, so this transition carries no runtime warning of its own.
#
# ``controller`` is NOT switched in this release line: unlike ``middleware``,
# ``from cullinan.web import controller`` is used by the maintained examples, so
# the referent change is a breaking change that has to go through the
# deprecation process (ADR + migration note + window) rather than ride along.

__all__ = [
    "Auto",
    "AutoType",
    "Body",
    "BodyDecoderMiddleware",
    "DynamicBody",
    "File",
    "Handler",
    "Header",
    "Middleware",
    "Param",
    "ParamResolver",
    "ParamValidator",
    "Path",
    "Query",
    "ResolveError",
    "StaticFiles",
    "TypeConverter",
    "UNSET",
    "ValidationError",
    "WebRequest",
    "WebResponse",
    "controller",
    "delete_api",
    "get_api",
    "get_decoded_body",
    "get_missing_header_handler",
    "middleware",
    "patch_api",
    "post_api",
    "put_api",
    "response",
    "set_decoded_body",
    "set_missing_header_handler",
    "websocket_handler",
]
