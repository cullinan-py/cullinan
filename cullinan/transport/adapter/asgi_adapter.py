# -*- coding: utf-8 -*-
"""Cullinan ASGI Adapter

Produces a standard ASGI 3.0 application callable that can be served by
uvicorn, hypercorn, daphne, or any other ASGI server.

Usage::

    from cullinan.transport.adapter import ASGIAdapter
    adapter = ASGIAdapter(dispatcher)
    app = adapter.create_app()
    # Then: uvicorn myapp:app

Author: Cullinan
"""

import asyncio
import logging
from typing import Any, Callable, Dict, List, Optional

from cullinan._api_boundary import in_public_api_context
from cullinan.core.semantic_rules import PublicAPISemanticWarning, warn_semantic_once
from .driver import DriverCapabilities, DriverRequestAdapter, DriverResponseWriter
from cullinan.application.model import (
    bind_runtime_request_context,
    release_runtime_request_context,
)
from cullinan.web.gateway.dispatcher import Dispatcher
from cullinan.web.gateway.web_core import WebRequest, WebResponse
from .base import WebAdapter

logger = logging.getLogger(__name__)

# ASGI type hints
Scope = Dict[str, Any]
Receive = Callable[..., Any]
Send = Callable[..., Any]


class ASGIAdapter(WebAdapter):
    """ASGI 3.0 adapter for the Cullinan Dispatcher.

    Creates an ASGI application callable (``async def app(scope, receive, send)``)
    that converts ASGI events into ``WebRequest`` / ``WebResponse``.

    Usage::

        dispatcher = Dispatcher(router=my_router)
        adapter = ASGIAdapter(dispatcher)
        asgi_app = adapter.create_app()

        # Serve with uvicorn
        import uvicorn
        uvicorn.run(asgi_app, host='0.0.0.0', port=4080)
    """

    def __init__(
        self,
        dispatcher: Dispatcher,
        global_headers: Optional[list] = None,
        runtime: Any = None,
    ) -> None:
        super().__init__(dispatcher, runtime=runtime)
        self._global_headers: list = global_headers or []
        self._asgi_app: Optional[Callable] = None
        self._request_adapter = ASGIRequestAdapter()
        self._response_writer = ASGIResponseWriter(global_headers=self._global_headers)

    def capabilities(self) -> DriverCapabilities:
        return DriverCapabilities(
            supports_http=True,
            supports_websocket=True,
            supports_lifespan=True,
            supports_streaming_request=True,
            supports_streaming_response=True,
            supports_multipart=True,
        )

    def create_request_adapter(self) -> DriverRequestAdapter:
        return self._request_adapter

    def create_response_writer(self) -> DriverResponseWriter:
        return self._response_writer

    def create_app(self) -> Callable:
        """Create and return the ASGI 3.0 application callable."""

        async def asgi_app(scope: Scope, receive: Receive, send: Send) -> None:
            if scope['type'] == 'http':
                await _handle_http(scope, receive, send, self)
            elif scope['type'] == 'websocket':
                await _handle_websocket(scope, receive, send)
            elif scope['type'] == 'lifespan':
                await _handle_lifespan(scope, receive, send)
            else:
                logger.warning('Unsupported ASGI scope type: %s', scope['type'])

        self._asgi_app = asgi_app
        return asgi_app

    def run(self, host: str = '0.0.0.0', port: int = 4080, **kwargs: Any) -> None:
        if self.runtime is not None and getattr(self.runtime, 'application', None) is not None and not in_public_api_context():
            warn_semantic_once(
                key="public-api:asgi-adapter-run",
                rule_key="public-api-boundary",
                problem="Calling ASGIAdapter.run() directly treats the runtime adapter layer as the default entry point.",
                guidance="For regular applications, prefer declaring an @application entry method with @configure(...), then call the entry method directly. If you are doing ASGI integration, explicitly import from cullinan.transport.adapter and use this path only in the integration layer.",
                category=PublicAPISemanticWarning,
                stacklevel=2,
            )
        """Start the ASGI server using uvicorn (or hypercorn).

        Requires ``uvicorn`` to be installed.
        """
        if self._asgi_app is None:
            self.create_app()

        server = kwargs.get('server', 'uvicorn')

        if server == 'uvicorn':
            try:
                import uvicorn
            except ImportError:
                raise ImportError(
                    "uvicorn is required for ASGI mode. Install it with: pip install uvicorn"
                )
            logger.info('Starting ASGI server (uvicorn) on %s:%s', host, port)
            uvicorn.run(
                self._asgi_app,
                host=host,
                port=port,
                log_level=kwargs.get('log_level', 'info'),
                **{k: v for k, v in kwargs.items() if k not in ('server', 'log_level')},
            )
        elif server == 'hypercorn':
            try:
                from hypercorn.config import Config
                from hypercorn.asyncio import serve
            except ImportError:
                raise ImportError(
                    "hypercorn is required. Install it with: pip install hypercorn"
                )
            config = Config()
            config.bind = [f'{host}:{port}']
            logger.info('Starting ASGI server (hypercorn) on %s:%s', host, port)
            asyncio.run(serve(self._asgi_app, config))
        else:
            raise ValueError(f"Unsupported ASGI server: {server}. Use 'uvicorn' or 'hypercorn'.")

    async def shutdown(self) -> None:
        """Graceful shutdown (ASGI servers handle this via lifespan events)."""
        logger.info('ASGI adapter shutdown requested')


# ======================================================================
# ASGI event handlers
# ======================================================================

async def _handle_http(
    scope: Scope,
    receive: Receive,
    send: Send,
    adapter: ASGIAdapter,
) -> None:
    """Handle an ASGI HTTP request.

    Wraps the entire dispatch in a try/except so that unhandled errors
    always produce a valid HTTP 500 response instead of crashing the
    ASGI server.
    """
    binding = None
    try:
        runtime = adapter.runtime
        if runtime is not None:
            runtime.begin_request()
        binding = bind_runtime_request_context(runtime)
        # 1. Read full body
        body = b''
        while True:
            message = await receive()
            body += message.get('body', b'')
            if not message.get('more_body', False):
                break

        # 2. Build WebRequest from ASGI scope
        request = await adapter.create_request_adapter().build_request(scope, body)
        if runtime is not None:
            request.attributes['runtime'] = runtime

        # 3. Dispatch
        response = await adapter.dispatcher.dispatch(request)

        # 4. Send response via ASGI
        await adapter.create_response_writer().write_response(response, send)

    except Exception:
        logger.exception('Uncaught error in ASGI HTTP handler')
        # Send a minimal 500 response so the connection is not left hanging
        try:
            error_body = b'{"error":"Internal Server Error","status":500}'
            await send({
                'type': 'http.response.start',
                'status': 500,
                'headers': [
                    [b'content-type', b'application/json'],
                    [b'content-length', str(len(error_body)).encode('latin-1')],
                ],
            })
            await send({
                'type': 'http.response.body',
                'body': error_body,
            })
        except Exception:
            pass
    finally:
        runtime = adapter.runtime
        release_runtime_request_context(runtime, binding)
        if runtime is not None:
            runtime.end_request()


async def _handle_lifespan(scope: Scope, receive: Receive, send: Send) -> None:
    """Handle ASGI lifespan events (startup / shutdown).

    Sends ``lifespan.startup.complete`` or ``lifespan.startup.failed``
    depending on whether the application context initialised cleanly.
    On shutdown, runs ``ApplicationContext.shutdown()`` if available.
    """
    while True:
        message = await receive()
        msg_type = message.get('type', '')

        if msg_type == 'lifespan.startup':
            try:
                # ApplicationContext is initialised by application.py before
                # the ASGI app is created; we simply confirm success here.
                await send({'type': 'lifespan.startup.complete'})
            except Exception as exc:
                logger.error('ASGI lifespan startup failed: %s', exc)
                await send({
                    'type': 'lifespan.startup.failed',
                    'message': str(exc),
                })
                return

        elif msg_type == 'lifespan.shutdown':
            try:
                from cullinan.core import get_application_context
                ctx = get_application_context()
                if ctx is not None and hasattr(ctx, 'shutdown'):
                    result = ctx.shutdown()
                    if asyncio.iscoroutine(result) or asyncio.isfuture(result):
                        await result
            except Exception as exc:
                logger.error('Error during ASGI lifespan shutdown: %s', exc)
            await send({'type': 'lifespan.shutdown.complete'})
            return

        else:
            return


def _build_request_from_scope(scope: Scope, body: bytes) -> WebRequest:
    """Convert an ASGI scope + body into a ``WebRequest``."""
    # Headers: list of [name_bytes, value_bytes]
    headers: List[tuple] = []
    for name_bytes, value_bytes in scope.get('headers', []):
        headers.append((name_bytes.decode('latin-1'), value_bytes.decode('latin-1')))

    # Query string
    query_string = scope.get('query_string', b'')
    if isinstance(query_string, bytes):
        query_string = query_string.decode('latin-1')

    # Path
    path = scope.get('path', '/')
    root_path = scope.get('root_path', '')
    if root_path and path.startswith(root_path):
        path = path[len(root_path):] or '/'

    # Client
    client = scope.get('client')
    client_ip = client[0] if client else '127.0.0.1'
    server = scope.get('server')
    server_host = server[0] if server else 'localhost'
    server_port = server[1] if server else 80
    scheme = scope.get('scheme', 'http')

    full_url = f'{scheme}://{server_host}:{server_port}{path}'
    if query_string:
        full_url += f'?{query_string}'

    # Cookies (parse from Cookie header)
    cookies: Dict[str, str] = {}
    cookie_header = ''
    for name, value in headers:
        if name.lower() == 'cookie':
            cookie_header = value
    if cookie_header:
        for part in cookie_header.split(';'):
            part = part.strip()
            if '=' in part:
                k, v = part.split('=', 1)
                cookies[k.strip()] = v.strip()

    return WebRequest(
        method=scope.get('method', 'GET'),
        path=path,
        headers=headers,
        body=body,
        query_string=query_string,
        client_ip=client_ip,
        scheme=scheme,
        server_host=server_host,
        server_port=server_port,
        full_url=full_url,
        cookies=cookies,
    )


class ASGIRequestAdapter(DriverRequestAdapter):
    async def build_request(self, scope: Scope, body: bytes) -> WebRequest:
        return _build_request_from_scope(scope, body)


class ASGIResponseWriter(DriverResponseWriter):
    def __init__(self, global_headers: Optional[list] = None) -> None:
        self._global_headers = global_headers or []

    async def write_response(self, response: WebResponse, send: Send) -> None:
        await _send_response(send, response, self._global_headers)


async def _send_response(
    send: Send,
    response: WebResponse,
    global_headers: list,
) -> None:
    """Send a ``WebResponse`` via ASGI ``send()``."""
    # Build header list
    raw_headers: List[List[bytes]] = []

    # Global headers (legacy)
    for h in global_headers:
        if isinstance(h, (list, tuple)) and len(h) >= 2:
            raw_headers.append([str(h[0]).encode('latin-1'), str(h[1]).encode('latin-1')])

    # Response headers
    for name, value in response.iter_headers(include_content_type=True):
        raw_headers.append([name.encode('latin-1'), value.encode('latin-1')])

    body = b''
    try:
        body = response.render_body()
    except Exception as exc:
        logger.error('Failed to render response body: %s', exc)
        body = b'{"error":"Response serialization error","status":500}'
        response = WebResponse.error(500, 'Response serialization error')
        raw_headers = [
            [str(h[0]).encode('latin-1'), str(h[1]).encode('latin-1')]
            for h in global_headers
            if isinstance(h, (list, tuple)) and len(h) >= 2
        ]
        for name, value in response.iter_headers(include_content_type=True):
            raw_headers.append([name.encode('latin-1'), value.encode('latin-1')])

    # Content-Length
    raw_headers.append([b'content-length', str(len(body)).encode('latin-1')])

    await send({
        'type': 'http.response.start',
        'status': response.status_code,
        'headers': raw_headers,
    })

    await send({
        'type': 'http.response.body',
        'body': body,
    })


# ======================================================================
# ASGI WebSocket handler
# ======================================================================

async def _handle_websocket(scope: Scope, receive: Receive, send: Send) -> None:
    """Handle an ASGI WebSocket connection.

    Protocol flow:
        1. Look up handler from ``WebSocketRegistry`` by URL.
        2. Accept the connection (``websocket.accept``).
        3. Call ``handler.on_open()``.
        4. Message loop: dispatch ``text``/``bytes`` to ``handler.on_message(data)``.
        5. On disconnect: call ``handler.on_close()``.

    If no handler is registered for the path, we close with code 4004.
    """
    path = scope.get('path', '/')

    # 1. Look up handler class
    try:
        from cullinan.web.websocket_registry import get_websocket_registry
        ws_registry = get_websocket_registry()
        handler_cls = ws_registry.get_by_url(path)
    except Exception as exc:
        logger.error('WebSocket registry lookup failed: %s', exc)
        handler_cls = None

    if handler_cls is None:
        logger.warning('No WebSocket handler registered for path: %s', path)
        # Accept then close immediately with 4004
        try:
            accept_msg = await receive()
            if accept_msg.get('type') == 'websocket.connect':
                await send({'type': 'websocket.close', 'code': 4004})
        except Exception:
            pass
        return

    # 2. Instantiate handler (prototype — one per connection, like Tornado)
    handler = _create_ws_handler_instance(handler_cls)

    # 3. Provide write_message helper bound to this connection's send()
    async def _write_message(message: Any, binary: bool = False) -> None:
        if binary:
            data = message if isinstance(message, bytes) else str(message).encode('utf-8')
            await send({'type': 'websocket.send', 'bytes': data})
        else:
            text = message if isinstance(message, str) else str(message)
            await send({'type': 'websocket.send', 'text': text})

    handler.write_message = _write_message

    # Attach connection metadata
    handler.scope = scope
    handler.path = path
    headers: Dict[str, str] = {}
    for name_bytes, value_bytes in scope.get('headers', []):
        headers[name_bytes.decode('latin-1')] = value_bytes.decode('latin-1')
    handler.headers = headers

    # 4. Wait for connect then accept
    try:
        connect_msg = await receive()
        if connect_msg.get('type') != 'websocket.connect':
            return
        await send({'type': 'websocket.accept'})
    except Exception as exc:
        logger.error('WebSocket accept failed: %s', exc)
        return

    # 5. Call on_open
    try:
        result = handler.on_open() if hasattr(handler, 'on_open') else None
        if asyncio.iscoroutine(result):
            await result
    except Exception as exc:
        logger.error('WebSocket on_open error: %s', exc, exc_info=True)
        await send({'type': 'websocket.close', 'code': 1011})
        return

    # 6. Message loop
    try:
        while True:
            message = await receive()
            msg_type = message.get('type', '')

            if msg_type == 'websocket.receive':
                data = message.get('text')
                if data is None:
                    data = message.get('bytes', b'')

                try:
                    result = handler.on_message(data) if hasattr(handler, 'on_message') else None
                    if asyncio.iscoroutine(result):
                        await result
                except Exception as exc:
                    logger.error('WebSocket on_message error: %s', exc, exc_info=True)
                    await send({'type': 'websocket.close', 'code': 1011})
                    break

            elif msg_type == 'websocket.disconnect':
                break
            else:
                # Unknown message type — break
                break
    except Exception as exc:
        logger.debug('WebSocket connection error: %s', exc)
    finally:
        # 7. Call on_close
        try:
            result = handler.on_close() if hasattr(handler, 'on_close') else None
            if asyncio.iscoroutine(result):
                await result
        except Exception as exc:
            logger.error('WebSocket on_close error: %s', exc, exc_info=True)


def _create_ws_handler_instance(handler_cls: type) -> Any:
    """Create a WebSocket handler instance with dependency injection."""
    try:
        from cullinan.core import get_application_context
        ctx = get_application_context()
        if ctx is not None and hasattr(ctx, '_create_class_instance'):
            return ctx._create_class_instance(handler_cls)
    except Exception:
        pass
    # Fallback: plain instantiation
    return handler_cls()
