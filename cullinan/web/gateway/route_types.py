# -*- coding: utf-8 -*-
"""Route data types for the Cullinan gateway layer.

Defines the data structures used by Router and Dispatcher for route
registration and matching.

Author: Cullinan
"""

from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Set, Type

from cullinan.support.deprecation import deprecated
from cullinan.support.deprecation import (
    resolve_removal_version as _resolve_removal_version,
)

# Removal version for the deprecated ``RouteGroup`` grouping type, derived from
# the framework version and the deprecation window rather than hard-coded, so
# this surface cannot introduce a second, hand-written removal version.
_REMOVAL_VERSION = _resolve_removal_version()


@dataclass(frozen=True)
class RouteEntry:
    """A registered route.

    Attributes:
        method: HTTP method (uppercase).  ``'*'`` means all methods.
        path: Original path pattern (e.g. ``/api/users/{id}``).
        path_regex: Compiled path regex (or ``None`` for static routes).
        handler: The callable that handles the request — typically a bound
                 controller method or a plain function.
        controller_cls: The controller class this handler belongs to (if any).
        controller_method_name: Name of the method on the controller class.
        param_names: Ordered list of path parameter names.
        metadata: Arbitrary metadata (e.g. ``tags``, ``summary`` for OpenAPI).
    """
    method: str
    path: str
    path_regex: Optional[Any] = None  # re.Pattern
    handler: Optional[Callable] = None
    controller_cls: Optional[Type] = None
    controller_method_name: str = ''
    param_names: tuple = ()
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class RouteMatch:
    """Result of a successful route match.

    Attributes:
        entry: The matched ``RouteEntry``.
        path_params: Dict of extracted path parameter values.
    """
    entry: RouteEntry
    path_params: Dict[str, str] = field(default_factory=dict)


@deprecated(
    version="0.95",
    alternative=(
        "configure(middlewares=[...]) or the @middleware decorator "
        "(per-group middleware tags are not supported)"
    ),
    removal_version=_REMOVAL_VERSION,
)
@dataclass
class RouteGroup:
    """A group of routes sharing a common prefix (used for controller registration).

    .. deprecated:: 0.95
        The group did not do anything beyond carrying its fields: nothing in the
        framework reads ``middleware_tags``, so a group could never apply
        middleware to its routes. Declare middleware through
        ``configure(middlewares=[...])`` or the ``@middleware`` decorator
        instead. The deprecation is carried by the class because the dataclass
        field itself cannot be decorated; ``RouteGroup`` stays importable and
        keeps ``middleware_tags`` readable for the length of the deprecation
        window.

    Attributes:
        prefix: URL prefix (e.g. ``/api/users``).
        routes: List of ``RouteEntry`` objects under this prefix.
        controller_cls: The controller class that owns the routes.
        middleware_tags: Deprecated. Middleware tags applied to all routes in
            this group. Retained during the deprecation window.
    """
    prefix: str
    routes: List[RouteEntry] = field(default_factory=list)
    controller_cls: Optional[Type] = None
    middleware_tags: Set[str] = field(default_factory=set)


# HTTP method constants
HTTP_METHODS: Set[str] = frozenset({
    'GET', 'POST', 'PUT', 'DELETE', 'PATCH', 'OPTIONS', 'HEAD',
})

