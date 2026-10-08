# -*- coding: utf-8 -*-
"""Cullinan Global Exception Handler

Catches exceptions during request dispatching and converts them
into structured ``WebResponse`` objects.

Author: plumeink
"""

import logging
import traceback
from typing import Any, Callable, Dict, List, Type

from .web_core import WebRequest, WebResponse

logger = logging.getLogger(__name__)


class ExceptionHandler:
    """Converts exceptions into HTTP responses.

    Supports:
    - Per-exception-type handlers via ``@register`` decorator.
    - Default catch-all for unhandled exceptions.
    - Debug mode with stack traces.

    Usage::

        handler = ExceptionHandler(debug=True)

        @handler.register(ValueError)
        def handle_value_error(request, exc):
            return WebResponse.error(400, str(exc))

        response = await handler.handle(request, some_exception)
    """

    def __init__(self, debug: bool = False) -> None:
        """
        Args:
            debug: If True, include stack trace in error responses.
        """
        self._handlers: Dict[Type[Exception], Callable] = {}
        self._debug: bool = debug

    def register(self, exc_type: Type[Exception]) -> Callable:
        """Decorator to register a handler for a specific exception type.

        Args:
            exc_type: The exception class to handle.

        Returns:
            Decorator function.

        Example::

            @exc_handler.register(PermissionError)
            def handle_permission(request, exc):
                return WebResponse.error(403, 'Forbidden')
        """
        def decorator(fn: Callable) -> Callable:
            self._handlers[exc_type] = fn
            return fn
        return decorator

    def register_handler(
        self,
        exc_type: Type[Exception],
        handler_fn: Callable,
    ) -> None:
        """Programmatic handler registration (non-decorator)."""
        self._handlers[exc_type] = handler_fn

    def list_registered_handlers(self) -> List[Dict[str, Any]]:
        """Return the exception handlers registered so far, in registration order.

        The handler table is private, and until now there was no way to read it
        back.  This is the read-only counterpart of
        ``Router.get_all_routes()`` / ``MiddlewarePipeline.list_middleware()``
        for the exception handler: it reports what the handler *holds* without
        exposing the callables themselves, and never mutates the table.

        Returns:
            A list of descriptors, each with a ``name`` (the registered exception
            type's name) and its ``order`` (registration order).
        """
        descriptors: List[Dict[str, Any]] = []
        for order, exc_type in enumerate(self._handlers):
            descriptors.append({
                'name': getattr(exc_type, '__name__', str(exc_type)),
                'order': order,
            })
        return descriptors

    async def handle(
        self,
        request: WebRequest,
        exc: Exception,
    ) -> WebResponse:
        """Convert an exception to a response.

        Resolution order:
        1. Exact type match in registered handlers.
        2. Walk MRO for the closest registered base class.
        3. Fall back to default handler.

        Args:
            request: The request that caused the exception.
            exc: The exception instance.

        Returns:
            A ``WebResponse``.
        """
        # 1. Exact match
        handler = self._handlers.get(type(exc))
        if handler is not None:
            return await self._invoke(handler, request, exc)

        # 2. MRO walk
        for cls in type(exc).__mro__:
            handler = self._handlers.get(cls)
            if handler is not None:
                return await self._invoke(handler, request, exc)

        # 3. Default
        return self._default_handler(request, exc)

    async def _invoke(
        self,
        handler: Callable,
        request: WebRequest,
        exc: Exception,
    ) -> WebResponse:
        """Invoke a registered handler (sync or async)."""
        import inspect
        try:
            result = handler(request, exc)
            if inspect.isawaitable(result):
                result = await result
            if isinstance(result, WebResponse):
                return result
            # If handler returned something else, wrap it
            return WebResponse.json(result)
        except Exception as inner:
            logger.error(
                'Exception handler itself raised: %s',
                inner,
                exc_info=True,
            )
            return self._default_handler(request, exc)

    def _default_handler(
        self,
        request: WebRequest,
        exc: Exception,
    ) -> WebResponse:
        """Built-in fallback: returns 500 with optional debug info."""
        from cullinan.support.exceptions import CullinanError

        # Map known framework exceptions to appropriate status codes
        status = 500
        message = 'Internal Server Error'

        if isinstance(exc, CullinanError):
            # Try to infer status from error_code
            code = getattr(exc, 'error_code', '')
            if 'PARAMETER' in code or 'MISSING_HEADER' in code:
                status = 400
            elif 'NOT_FOUND' in code:
                status = 404
            elif 'FORBIDDEN' in code or 'AUTH' in code:
                status = 403
            message = exc.message
        elif isinstance(exc, ValueError):
            status = 400
            message = str(exc)
        elif isinstance(exc, PermissionError):
            status = 403
            message = str(exc) or 'Forbidden'
        elif isinstance(exc, FileNotFoundError):
            status = 404
            message = str(exc) or 'Not Found'
        else:
            message = str(exc) if self._debug else 'Internal Server Error'

        logger.error(
            'Unhandled exception during %s %s: %s',
            request.method,
            request.path,
            exc,
            exc_info=True,
        )

        payload: Dict[str, Any] = {
            'error': message,
            'status': status,
        }
        if self._debug:
            payload['traceback'] = traceback.format_exception(
                type(exc), exc, exc.__traceback__,
            )

        return WebResponse(
            body=payload,
            status_code=status,
            content_type='application/json',
        )
