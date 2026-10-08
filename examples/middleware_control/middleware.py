"""Middleware used by the pipeline-control example.

Two declaration styles cooperate in one pipeline:

* ``TraceHeaderMiddleware`` — the recommended onion protocol
  (``async def __call__(request, call_next)``), declared through
  ``@configure(middlewares=[...])``;
* ``LegacyAuditMiddleware`` — the compatibility hook protocol
  (``process_request`` / ``process_response``), registered through
  ``@middleware(priority=...)``.

The legacy hook declares ``priority=10``, below the default ``100``, so it ends
up on a *more outer* layer than the declared middleware — the two protocols
share one declarative ordering.

``QuietAccessLogMiddleware`` replaces the built-in access-log layer through
``@configure(builtin_middleware=[...])``.
"""
from cullinan import Middleware, middleware
from cullinan.web.gateway import GatewayMiddleware


def _prepend_trace(response, marker):
    """Prepend ``marker`` so the header reads outermost-first."""
    current = response.get_header("X-Control-Trace") or ""
    response.set_header("X-Control-Trace", f"{marker}>{current}" if current else marker)


class TraceHeaderMiddleware(GatewayMiddleware):
    """Declared onion middleware; keeps the default priority (100)."""

    async def __call__(self, request, call_next):
        response = await call_next(request)
        _prepend_trace(response, "declared")
        return response


@middleware(priority=10)
class LegacyAuditMiddleware(Middleware):
    """Compatibility hook middleware; priority 10 puts it outermost."""

    def process_request(self, request):
        return request

    def process_response(self, request, response):
        _prepend_trace(response, "legacy-outer")
        return response


class QuietAccessLogMiddleware(GatewayMiddleware):
    """Drop-in replacement for the built-in access-log layer.

    It keeps the per-request logging but tags each line with its own logger
    name, which makes it visible that the built-in layer was replaced rather
    than doubled up.
    """

    def __init__(self, log_name="cullinan.access.quiet"):
        import logging

        self._logger = logging.getLogger(log_name)

    async def __call__(self, request, call_next):
        response = await call_next(request)
        self._logger.info('%s %s -> %s', request.method, request.path, response.status_code)
        return response


__all__ = [
    "LegacyAuditMiddleware",
    "QuietAccessLogMiddleware",
    "TraceHeaderMiddleware",
]
