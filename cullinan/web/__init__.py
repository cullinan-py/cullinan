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
from cullinan.web import controller
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
# ``controller`` is switched on this release line, for the same reason and by the
# same rule as ``middleware`` above: the name now resolves to the
# ``cullinan.web.controller`` submodule, and the decorator stays available at the
# top level (``from cullinan import controller``) and inside the submodule
# (``from cullinan.web.controller import controller``).
#
# The reason it had been deferred is that a name cannot mean two things at once:
# while the decorator owned ``cullinan.web.controller``, the dotted form
# ``import cullinan.web.controller.<module> as x`` failed outright, because the
# attribute lookup found a function instead of a package. Deferring kept the
# examples working and left that import path broken; the switch trades a loud
# ``'module' object is not callable`` at the old call site for a working import
# path everywhere else.

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
