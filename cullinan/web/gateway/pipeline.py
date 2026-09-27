# -*- coding: utf-8 -*-
"""Cullinan Middleware Pipeline

Implements the onion-model middleware pipeline that wraps the core
dispatch logic.  Every request flows through all middleware in order;
responses flow back in reverse order.

Author: Cullinan
"""

import heapq
import logging
import time
from dataclasses import dataclass
from typing import Any, Callable, Awaitable, Dict, List, Optional, Type, Union

from .web_core import WebRequest, WebResponse

logger = logging.getLogger(__name__)

# Type alias for the "next" callable in the pipeline
HandlerCallable = Callable[[WebRequest], Awaitable[WebResponse]]

# A middleware ordering anchor: an instance, a class, or a class name.
OrderingAnchor = Union["GatewayMiddleware", Type["GatewayMiddleware"], str]


def _anchor_label(anchor: OrderingAnchor) -> str:
    """Return a readable label for an ordering anchor."""
    if isinstance(anchor, str):
        return anchor
    if isinstance(anchor, type):
        return anchor.__name__
    return anchor.__class__.__name__


def _anchor_matches(anchor: OrderingAnchor, middleware: "GatewayMiddleware") -> bool:
    """Return whether ``anchor`` refers to ``middleware``."""
    if isinstance(anchor, str):
        return middleware.__class__.__name__ == anchor
    if isinstance(anchor, type):
        return isinstance(middleware, anchor)
    return middleware is anchor


# Default priority for pipeline middleware, matching the legacy
# ``@middleware(priority=...)`` decorator. A lower priority runs on a more outer
# layer, so "the security gate must be outermost" is declared with a low value.
_DEFAULT_MIDDLEWARE_PRIORITY = 100


def _entry_sort_key(entry: "_MiddlewareEntry"):
    """Sort key used to break ties in the topological sort: (priority, sequence)."""
    priority = (
        entry.priority if entry.priority is not None else _DEFAULT_MIDDLEWARE_PRIORITY
    )
    return priority, entry.sequence


@dataclass
class _MiddlewareEntry:
    """One registered middleware plus its optional declarative ordering hints."""

    middleware: "GatewayMiddleware"
    sequence: int
    before: Optional[OrderingAnchor] = None
    after: Optional[OrderingAnchor] = None
    priority: Optional[int] = None


class GatewayMiddleware:
    """Base class for gateway-level middleware (onion model).

    Subclasses override :meth:`__call__` and invoke ``await call_next(request)``
    to continue the chain.

    Example::

        class TimingMiddleware(GatewayMiddleware):
            async def __call__(self, request, call_next):
                start = time.time()
                response = await call_next(request)
                elapsed = time.time() - start
                response.set_header('X-Response-Time', f'{elapsed:.4f}s')
                return response
    """

    async def __call__(
        self,
        request: WebRequest,
        call_next: HandlerCallable,
    ) -> WebResponse:
        """Process the request.

        Default implementation simply forwards to the next handler.

        Args:
            request: The incoming request.
            call_next: Awaitable that invokes the next middleware or the final handler.

        Returns:
            The response from downstream.
        """
        return await call_next(request)


class MiddlewarePipeline:
    """Ordered middleware chain using the onion (wrap) model.

    Middleware are executed in registration order for the *request* phase
    and in reverse order for the *response* phase, unless a declarative
    ordering hint (``before`` / ``after`` / ``priority``) says otherwise.
    The resolved order is introspectable through :meth:`list_middleware`.

    Usage::

        pipeline = MiddlewarePipeline()
        pipeline.add(LoggingMiddleware())
        pipeline.add(AuthMiddleware())

        response = await pipeline.execute(request, final_handler)
    """

    def __init__(self) -> None:
        self._entries: List[_MiddlewareEntry] = []
        self._resolved_cache: Optional[List[_MiddlewareEntry]] = None

    def add(
        self,
        mw: GatewayMiddleware,
        *,
        before: Optional[OrderingAnchor] = None,
        after: Optional[OrderingAnchor] = None,
        priority: Optional[int] = None,
    ) -> None:
        """Append a middleware to the pipeline.

        Ordering is declarative and entirely optional:

        * with no hints the registration order is preserved, so the first
          middleware added stays the outermost layer (unchanged behaviour);
        * ``before`` / ``after`` anchor this middleware relative to another
          middleware (matched by instance, class, or class name);
        * ``priority`` is an optional global key: a lower value runs on a more
          outer layer, defaulting to 100 — the same direction and default as the
          legacy ``@middleware(priority=...)`` decorator.  It is therefore how a
          middleware declares "I am the outermost layer";
        * ``priority`` and ``before`` / ``after`` are mutually exclusive.

        Hints may reference middleware that is added later, because the order
        is resolved lazily when the pipeline runs or is introspected.  The
        resolved order depends only on the declarations, never on when the
        middleware was registered.
        """
        if priority is not None and (before is not None or after is not None):
            raise ValueError(
                "Middleware ordering declarations are mutually exclusive: pass either "
                "'priority' or 'before'/'after', not both."
            )
        self._entries.append(
            _MiddlewareEntry(
                middleware=mw,
                sequence=len(self._entries),
                before=before,
                after=after,
                priority=priority,
            )
        )
        self._invalidate()
        logger.debug('Middleware added: %s', mw.__class__.__name__)

    def add_class(self, mw_cls: Type[GatewayMiddleware], **kwargs: Any) -> GatewayMiddleware:
        """Instantiate and add a middleware class.  Returns the instance."""
        inst = mw_cls(**kwargs)
        self.add(inst)
        return inst

    async def execute(
        self,
        request: WebRequest,
        final_handler: HandlerCallable,
    ) -> WebResponse:
        """Run the full pipeline and return the final response.

        Args:
            request: The incoming request.
            final_handler: The core dispatch callable that produces the response
                           after all middleware have processed the request.

        Returns:
            The response (potentially modified by middleware).
        """
        # Build the chain from inside-out (last middleware wraps final_handler first)
        handler = final_handler
        for entry in reversed(self._resolved()):
            handler = _wrap(entry.middleware, handler)
        return await handler(request)

    def list_middleware(self) -> List[Dict[str, Any]]:
        """Return the middleware currently installed, in execution order.

        Index 0 is the outermost middleware — the one that sees the request
        first and the response last.  This is the read-only counterpart of
        ``Router.get_all_routes()`` for the pipeline.

        Returns:
            A list of descriptors, each with a ``name`` (the middleware class
            name) and its ``order``; declared ordering hints are included when
            present.
        """
        descriptors: List[Dict[str, Any]] = []
        for order, entry in enumerate(self._resolved()):
            descriptor: Dict[str, Any] = {
                'name': getattr(entry.middleware, 'display_name', None) or entry.middleware.__class__.__name__,
                'order': order,
            }
            if entry.priority is not None:
                descriptor['priority'] = entry.priority
            if entry.before is not None:
                descriptor['before'] = _anchor_label(entry.before)
            if entry.after is not None:
                descriptor['after'] = _anchor_label(entry.after)
            descriptors.append(descriptor)
        return descriptors

    @property
    def count(self) -> int:
        return len(self._entries)

    def clear(self) -> None:
        self._entries.clear()
        self._invalidate()

    # ------------------------------------------------------------------
    # Ordering resolution
    # ------------------------------------------------------------------

    @property
    def _middleware(self) -> List[GatewayMiddleware]:
        """Resolved middleware in outer-to-inner order (internal view)."""
        return [entry.middleware for entry in self._resolved()]

    def _invalidate(self) -> None:
        self._resolved_cache = None

    def _resolved(self) -> List[_MiddlewareEntry]:
        if self._resolved_cache is None:
            self._resolved_cache = self._compute_order()
        return self._resolved_cache

    def _compute_order(self) -> List[_MiddlewareEntry]:
        """Resolve declarative ordering into a deterministic outer-to-inner list."""
        entries = list(self._entries)
        count = len(entries)

        # edges[i] holds the entries that must run *inside* entry i.
        edges: Dict[int, set] = {index: set() for index in range(count)}

        for index, entry in enumerate(entries):
            if entry.before is not None:
                anchor = self._resolve_anchor(entries, entry.before, 'before')
                if anchor == index:
                    raise ValueError(
                        "Middleware cannot be declared 'before' itself: "
                        f"{entries[index].middleware.__class__.__name__}."
                    )
                edges[index].add(anchor)
            if entry.after is not None:
                anchor = self._resolve_anchor(entries, entry.after, 'after')
                if anchor == index:
                    raise ValueError(
                        "Middleware cannot be declared 'after' itself: "
                        f"{entries[index].middleware.__class__.__name__}."
                    )
                edges[anchor].add(index)

        return self._stable_topological_sort(entries, edges)

    @staticmethod
    def _resolve_anchor(entries, anchor: OrderingAnchor, relation: str) -> int:
        matches = [index for index, entry in enumerate(entries) if _anchor_matches(anchor, entry.middleware)]
        if not matches:
            raise ValueError(
                f"Middleware ordering '{relation}' anchor {_anchor_label(anchor)!r} does not "
                "match any registered middleware."
            )
        if len(matches) > 1:
            raise ValueError(
                f"Middleware ordering '{relation}' anchor {_anchor_label(anchor)!r} is ambiguous: "
                f"it matches {len(matches)} registered middleware."
            )
        return matches[0]

    @staticmethod
    def _stable_topological_sort(entries, edges) -> List[_MiddlewareEntry]:
        """Kahn's algorithm, always taking the lowest ``(priority, index)`` next.

        ``priority`` is an optional global key (lower = more outer, default 100),
        so a middleware can declare itself outermost without depending on the
        registration order.  ``before`` / ``after`` are hard constraints.  With no
        declarations at all every key is ``(100, registration index)``, so the
        result is exactly the registration order — preserving the long-standing
        "first added is outermost" semantics.
        """
        indegree = {index: 0 for index in range(len(entries))}
        for targets in edges.values():
            for target in targets:
                indegree[target] += 1

        ready = [
            (_entry_sort_key(entries[index]), index)
            for index in range(len(entries))
            if indegree[index] == 0
        ]
        heapq.heapify(ready)

        ordered: List[_MiddlewareEntry] = []
        while ready:
            _, index = heapq.heappop(ready)
            ordered.append(entries[index])
            for target in sorted(edges[index]):
                indegree[target] -= 1
                if indegree[target] == 0:
                    heapq.heappush(ready, (_entry_sort_key(entries[target]), target))

        if len(ordered) != len(entries):
            raise ValueError(
                "Middleware ordering declarations form a cycle and cannot be satisfied."
            )
        return ordered


def _wrap(mw: GatewayMiddleware, next_handler: HandlerCallable) -> HandlerCallable:
    """Create a closure that calls ``mw(request, next_handler)``."""
    async def _inner(request: WebRequest) -> WebResponse:
        return await mw(request, next_handler)
    return _inner


# ======================================================================
# Built-in middleware implementations
# ======================================================================

class CORSMiddleware(GatewayMiddleware):
    """Cross-Origin Resource Sharing middleware.

    Handles preflight ``OPTIONS`` requests and injects CORS headers.

    Args:
        allow_origins: Allowed origins (``'*'`` for all).
        allow_methods: Allowed HTTP methods.
        allow_headers: Allowed request headers.
        allow_credentials: Whether to allow credentials.
        max_age: Preflight cache duration in seconds.
    """

    def __init__(
        self,
        allow_origins: str = '*',
        allow_methods: str = 'GET,POST,PUT,DELETE,PATCH,OPTIONS',
        allow_headers: str = '*',
        allow_credentials: bool = False,
        max_age: int = 86400,
    ) -> None:
        self._origins = allow_origins
        self._methods = allow_methods
        self._headers = allow_headers
        self._credentials = allow_credentials
        self._max_age = str(max_age)

    async def __call__(self, request: WebRequest, call_next: HandlerCallable) -> WebResponse:
        # Preflight
        if request.method == 'OPTIONS':
            resp = WebResponse(status_code=204)
            self._set_cors_headers(resp)
            return resp

        resp = await call_next(request)
        self._set_cors_headers(resp)
        return resp

    def _set_cors_headers(self, resp: WebResponse) -> None:
        resp.set_header('Access-Control-Allow-Origin', self._origins)
        resp.set_header('Access-Control-Allow-Methods', self._methods)
        resp.set_header('Access-Control-Allow-Headers', self._headers)
        resp.set_header('Access-Control-Max-Age', self._max_age)
        if self._credentials:
            resp.set_header('Access-Control-Allow-Credentials', 'true')


class RequestTimingMiddleware(GatewayMiddleware):
    """Adds an ``X-Response-Time`` header with the request duration."""

    async def __call__(self, request: WebRequest, call_next: HandlerCallable) -> WebResponse:
        start = time.perf_counter()
        resp = await call_next(request)
        elapsed = time.perf_counter() - start
        resp.set_header('X-Response-Time', f'{elapsed:.6f}s')
        return resp


class AccessLogMiddleware(GatewayMiddleware):
    """Emits an access-log entry for each request."""

    def __init__(self, log_name: str = 'cullinan.access') -> None:
        self._logger = logging.getLogger(log_name)

    async def __call__(self, request: WebRequest, call_next: HandlerCallable) -> WebResponse:
        start = time.perf_counter()
        resp: Optional[WebResponse] = None
        try:
            resp = await call_next(request)
            return resp
        finally:
            elapsed = time.perf_counter() - start
            status = resp.status_code if resp else 500
            self._logger.info(
                '%s - "%s %s" %s %.3fs',
                request.client_ip,
                request.method,
                request.path,
                status,
                elapsed,
            )


class LegacyMiddlewareBridge(GatewayMiddleware):
    """Bridge that adapts legacy ``cullinan.web.middleware.Middleware`` instances
    into the new gateway pipeline.

    This allows existing ``@middleware`` decorated classes to participate
    in the new pipeline without modification.
    """

    def __init__(self, legacy_chain: Any) -> None:
        """
        Args:
            legacy_chain: A ``MiddlewareChain`` instance from ``cullinan.web.middleware``.
        """
        self._chain = legacy_chain

    async def __call__(self, request: WebRequest, call_next: HandlerCallable) -> WebResponse:
        # Process request through legacy chain
        processed = self._chain.process_request(request)
        if processed is None:
            # Short-circuited by legacy middleware
            return WebResponse.error(403, 'Request rejected by middleware')

        resp = await call_next(request)

        # Process response through legacy chain (reverse)
        self._chain.process_response(request, resp)
        return resp


class _LegacyMiddlewareAdapter(GatewayMiddleware):
    """Internal adapter exposing **one** legacy middleware as a pipeline layer.

    The legacy ``process_request`` / ``process_response`` hook pair is
    synchronous and chain-oriented. Adapting a single instance at a time lets
    every legacy middleware become its own pipeline entry, so the declarative
    ``priority`` ordering — and the public reflection via ``list_middleware()`` —
    apply uniformly across built-in, declared and legacy middleware, instead of
    the whole legacy chain collapsing into one opaque wrapper.

    ``display_name`` carries the wrapped middleware's class name so the
    reflection API reports the real layer, not this adapter.
    """

    def __init__(self, legacy_middleware: Any) -> None:
        self._middleware = legacy_middleware
        self.display_name = legacy_middleware.__class__.__name__

    async def __call__(self, request: WebRequest, call_next: HandlerCallable) -> WebResponse:
        processed = self._middleware.process_request(request)
        if processed is None:
            # Same fixed rejection contract as LegacyMiddlewareBridge: the
            # legacy hook protocol can only accept or reject.
            return WebResponse.error(403, 'Request rejected by middleware')

        resp = await call_next(request)

        self._middleware.process_response(request, resp)
        return resp
