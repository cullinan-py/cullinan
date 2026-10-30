# -*- coding: utf-8 -*-
"""Cullinan Tornado Adapter — Single-Handler Mode

Instead of creating one dynamic ``type('Servlet'+url, ...)`` per route,
this adapter registers **one** catch-all ``RequestHandler`` that delegates
every request to ``Dispatcher.dispatch()``.

Author: plumeink
"""

import logging
import os
import signal
from typing import Any, Dict, Optional

import tornado.httpserver
import tornado.ioloop
import tornado.web
import tornado.websocket

from cullinan._api_boundary import in_public_api_context
from cullinan.core.semantic_rules import PublicAPISemanticWarning, warn_semantic_once
from .driver import DriverCapabilities, DriverRequestAdapter, DriverResponseWriter
from cullinan.application.model import (
    bind_runtime_request_context,
    release_runtime_request_context,
)
from cullinan.web.gateway.dispatcher import Dispatcher
from cullinan.web.gateway.web_core import WebRequest, WebResponse
from .base import WebAdapter, resolve_max_request_body_bytes

logger = logging.getLogger(__name__)


class _CullinanTornadoHandler(tornado.web.RequestHandler):
    """The **single** Tornado ``RequestHandler`` that funnels all requests
    through the Cullinan ``Dispatcher``.

    This replaces the old per-URL dynamic Servlet classes.
    """

    # Class-level defaults — Tornado calls set_default_headers() inside
    # __init__() (via clear()), which runs *before* initialize().
    # Without these defaults the first access would raise AttributeError.
    _dispatcher: Dispatcher = None  # type: ignore[assignment]
    _adapter: "TornadoAdapter" = None  # type: ignore[assignment]
    _global_headers: list = []

    def initialize(self, dispatcher: Dispatcher, adapter: "TornadoAdapter", global_headers: list = None) -> None:  # type: ignore[override]
        self._dispatcher = dispatcher
        self._adapter = adapter
        self._global_headers = global_headers or []

    def set_etag_header(self) -> None:
        """Do not let Tornado invent an ETag for framework-produced responses.

        Tornado computes one from the response body on ``finish()`` and, when a
        client sends ``If-None-Match``, turns the response into a ``304``. The
        ASGI path does neither, so the *same* request returned ``200`` on one
        engine and ``304`` on the other -- a difference in status code, not in
        formatting, which a cross-engine framework cannot have.

        Responses that genuinely want an ETag set the header themselves (the
        static-file layer does, and implements its own conditional check), and
        this override does not touch a header it did not compute.
        """

    # Accept every HTTP method
    async def _handle(self) -> None:
        """Unified entry point for all HTTP methods.

        Catches any error during request conversion, dispatch, or response
        writing and falls back to a plain 500 so that Tornado's default
        error page is never triggered unexpectedly.
        """
        binding = None
        try:
            runtime = self._adapter.runtime
            if runtime is not None:
                runtime.begin_request()
            binding = bind_runtime_request_context(runtime)
            request = self._adapter.create_request_adapter().build_request(self)
            limit = resolve_max_request_body_bytes()
            if limit is not None and len(request.body or b'') > limit:
                # Answered before routing: the point of the ceiling is not to
                # hand a huge body to a handler that will reject it anyway.
                self.set_status(413)
                self.set_header('Connection', 'close')
                self.write(b'{"error":"Payload Too Large","reason":"request body exceeded max_request_body_bytes"}')
                self.finish()
                return
            if runtime is not None:
                request.attributes['runtime'] = runtime
            response = await self._dispatcher.dispatch(request)
            self._adapter.create_response_writer().write_response(response, self)
        except Exception as exc:
            # If the response has not been started yet, write an error. Which
            # error matters: a request that fails because the application is
            # draining is a timing problem, and answering 500 tells the caller
            # the code is broken. 503 says "try another instance".
            if not self._finished:
                try:
                    app = None
                    try:
                        from cullinan.application.model import Application

                        app = Application.current()
                    except Exception:  # noqa: BLE001
                        app = None
                    draining = app is not None and not getattr(app, 'accepts_requests', True)
                    from cullinan.core.exceptions import ContainerDrainingError

                    if isinstance(exc, ContainerDrainingError) or draining:
                        self.set_status(503)
                        self.set_header('Retry-After', '1')
                        self.write(b'{"error":"Service Unavailable","reason":"the application is draining"}')
                    else:
                        self.set_status(500)
                        self.write(b'{"error":"Internal Server Error","status":500}')
                    self.finish()
                except Exception:
                    pass
            logger.exception('Uncaught error in _CullinanTornadoHandler._handle')
        finally:
            runtime = self._adapter.runtime
            release_runtime_request_context(runtime, binding)
            if runtime is not None:
                runtime.end_request()

    # Map all standard methods to _handle
    async def get(self, *_args: Any, **_kwargs: Any) -> None:
        await self._handle()

    async def post(self, *_args: Any, **_kwargs: Any) -> None:
        await self._handle()

    async def put(self, *_args: Any, **_kwargs: Any) -> None:
        await self._handle()

    async def delete(self, *_args: Any, **_kwargs: Any) -> None:
        await self._handle()

    async def patch(self, *_args: Any, **_kwargs: Any) -> None:
        await self._handle()

    async def options(self, *_args: Any, **_kwargs: Any) -> None:
        await self._handle()

    async def head(self, *_args: Any, **_kwargs: Any) -> None:
        await self._handle()

    # ------------------------------------------------------------------
    # Request conversion
    # ------------------------------------------------------------------

    def write_error(self, status_code: int = 500, **kwargs: Any) -> None:
        """Override Tornado's default HTML error page.

        Produces a JSON error body consistent with
        ``WebResponse.error()``.
        """
        reason = self._reason if hasattr(self, '_reason') else 'Server Error'
        payload = {'error': reason, 'status': status_code}

        exc_info = kwargs.get('exc_info')
        if exc_info:
            logger.error(
                'Handler error %s: %s',
                status_code,
                exc_info[1],
                exc_info=exc_info,
            )

        self.set_header('Content-Type', 'application/json')
        import json as _json
        self.finish(_json.dumps(payload, ensure_ascii=False))

    def on_connection_close(self) -> None:
        """Cleanup hook when the client drops the connection mid-request."""
        logger.debug('Client disconnected during request: %s %s',
                      self.request.method, self.request.uri)

    def set_default_headers(self) -> None:
        """Apply global headers from the legacy HeaderRegistry."""
        for h in getattr(self, '_global_headers', []):
            if isinstance(h, (list, tuple)) and len(h) >= 2:
                self.set_header(str(h[0]), str(h[1]))


def server_options() -> dict:
    """Keyword arguments for ``HTTPServer``, given the configured ceiling.

    ``max_body_size`` is the only thing that makes Tornado stop reading; without
    it the handler-level check can only reject a body that has already been
    accepted in full. Exposed separately so the wiring is testable without
    starting a server.
    """
    limit = resolve_max_request_body_bytes()
    return {'max_body_size': limit} if limit is not None else {}


class TornadoAdapter(WebAdapter):
    """Tornado runtime adapter — single-handler mode.

    Creates a ``tornado.web.Application`` with one catch-all route that
    delegates to the ``Dispatcher``.  WebSocket routes are registered separately.

    Usage::

        adapter = TornadoAdapter(dispatcher)
        adapter.run(host='0.0.0.0', port=4080)
    """

    def __init__(
        self,
        dispatcher: Dispatcher,
        settings: Optional[Dict[str, Any]] = None,
        global_headers: Optional[list] = None,
        extra_handlers: Optional[list] = None,
        runtime: Any = None,
    ) -> None:
        super().__init__(dispatcher, runtime=runtime)
        self._settings: Dict[str, Any] = settings or {}
        self._global_headers: list = global_headers or []
        self._extra_handlers: list = extra_handlers or []
        self._http_server: Optional[tornado.httpserver.HTTPServer] = None
        self._app: Optional[tornado.web.Application] = None
        self._request_adapter = TornadoRequestAdapter()
        self._response_writer = TornadoResponseWriter(global_headers=self._global_headers)

    def capabilities(self) -> DriverCapabilities:
        return DriverCapabilities(
            supports_http=True,
            supports_websocket=True,
            supports_streaming_request=False,
            supports_streaming_response=False,
            supports_multipart=True,
        )

    def create_request_adapter(self) -> DriverRequestAdapter:
        return self._request_adapter

    def create_response_writer(self) -> DriverResponseWriter:
        return self._response_writer

    def create_app(self) -> tornado.web.Application:
        """Create a ``tornado.web.Application`` with a catch-all handler."""
        handlers = list(self._extra_handlers)

        # Register WebSocket handlers (if any)
        try:
            from cullinan.web.websocket_registry import get_websocket_registry
            ws_registry = get_websocket_registry()
            for url, name in ws_registry.list_urls().items():
                ws_cls = ws_registry.get(name)
                if ws_cls is not None:
                    handlers.append((url, ws_cls))
                    logger.info('WebSocket route: %s -> %s', url, name)
        except Exception as exc:
            logger.debug('WebSocket registry not available: %s', exc)

        # The catch-all handler — MUST be last
        handlers.append(
            (r'.*', _CullinanTornadoHandler, {
                'dispatcher': self.dispatcher,
                'adapter': self,
                'global_headers': self._global_headers,
            })
        )

        self._app = tornado.web.Application(handlers=handlers, **self._settings)
        return self._app

    def _create_http_server(self):
        """Build the ``HTTPServer``, passing the configured ceiling through.

        Kept as a method so a test can assert the wiring without starting a
        server: the ceiling is only real if ``max_body_size`` reaches this call,
        and a version that omits it stays green everywhere else while the
        protocol layer quietly goes back to buffering whole uploads.
        """
        return tornado.httpserver.HTTPServer(self._app, **server_options())

    def run(self, host: str = '0.0.0.0', port: int = 4080, **kwargs: Any) -> None:
        """Start the Tornado HTTP server (blocking)."""
        if self.runtime is not None and getattr(self.runtime, 'application', None) is not None and not in_public_api_context():
            warn_semantic_once(
                key="public-api:tornado-adapter-run",
                rule_key="public-api-boundary",
                problem="Calling TornadoAdapter.run() directly treats the runtime adapter layer as the default entry point.",
                guidance="For regular applications, prefer declaring an @application entry method with @configure(...), then call the entry method directly. If you are doing advanced server integration, explicitly import from cullinan.transport.adapter and use this path only in the integration layer.",
                category=PublicAPISemanticWarning,
                stacklevel=2,
            )
        if self._app is None:
            self.create_app()

        server_thread = kwargs.get('threads') or os.getenv('SERVER_THREAD')
        # Without this, Tornado buffers the whole body before the handler runs,
        # so the ceiling in the adapter could only ever reject an upload that
        # had already been accepted in full. The protocol layer has to know the
        # number, and it refuses at the point the limit is crossed.
        self._http_server = self._create_http_server()

        if server_thread is not None:
            self._http_server.bind(port)
            self._http_server.start(int(server_thread))
            logger.info('Tornado server starting (multi-process: %s)', server_thread)
        else:
            self._http_server.listen(port, address=host)

        logger.info('Tornado server listening on %s:%s', host, port)

        # Signal handling
        self._install_signal_handlers()

        loop = tornado.ioloop.IOLoop.current()

        def _request_shutdown() -> bool:
            """Hand the drain to the loop from whatever thread is asking.

            ``add_callback`` is the thread-safe entry point here: since Tornado 5
            it dispatches through ``call_soon_threadsafe`` when it is called from
            another thread, and directly when it is called on the loop. (The
            separate ``add_callback_threadsafe`` name was removed -- it is not
            present in 6.5.10, which is what this project runs against.) That is
            also why the drain itself is not called inline: it awaits, and a
            caller outside the loop cannot.
            """
            if not self._claim_shutdown_request():
                # Already scheduled: the answer is still True ("this server has
                # been asked to stop"), but there is nothing new to schedule.
                return True
            loop.add_callback(self._shutdown_gracefully)
            return True

        self._register_shutdown_requester(_request_shutdown)
        try:
            loop.start()
        except KeyboardInterrupt:
            logger.info('KeyboardInterrupt received, shutting down...')
        finally:
            self._register_shutdown_requester(None)
            self._cleanup()

    async def shutdown(self) -> None:
        """Gracefully stop the Tornado server."""
        if self._http_server:
            self._http_server.stop()
        try:
            loop = tornado.ioloop.IOLoop.current()
            loop.add_callback(loop.stop)
        except Exception:
            pass

    def _install_signal_handlers(self) -> None:
        try:
            # Resolve the loop now, while we know we are on it. Asking for
            # ``IOLoop.current()`` inside a signal handler can fail on platforms
            # where the handler runs outside the loop context, and the failure
            # used to be swallowed -- so the signal was received, logged and
            # then ignored, and the process kept serving until something else
            # killed it. That is what "Tornado ignores SIGTERM on Linux" looked
            # like from the outside.
            try:
                loop = tornado.ioloop.IOLoop.current()
            except Exception:  # noqa: BLE001 - fall back to per-signal resolution
                loop = None

            def _handle(signum: int, frame: Any) -> None:
                logger.info('Signal %s received, draining...', signum)
                try:
                    if loop is not None:
                        # The signal-safe way to hand work to the loop.
                        loop.add_callback_from_signal(self._shutdown_gracefully)
                    else:
                        tornado.ioloop.IOLoop.current().add_callback(self._shutdown_gracefully)
                except Exception:  # noqa: BLE001 - never raise inside a signal handler
                    logger.exception('signal %s could not schedule the drain', signum)

            for name in ('SIGINT', 'SIGTERM', 'SIGBREAK'):
                sig = getattr(signal, name, None)
                if sig is None:
                    continue
                try:
                    signal.signal(sig, _handle)
                except Exception:  # noqa: BLE001 - not every platform allows every signal
                    continue
        except Exception:  # noqa: BLE001 - signal setup must not stop the server
            pass

    def _drain_timeout(self) -> float:
        """The drain bound, from its single source (``WebRuntimeConfig``)."""
        try:
            from cullinan.web.gateway.runtime import WebRuntime

            runtime = WebRuntime.current()
            config = getattr(runtime, 'config', None) if runtime is not None else None
            value = getattr(config, 'drain_timeout', None)
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                return float(value)
        except Exception:  # noqa: BLE001 - the bound must never break shutdown
            pass
        return 30.0

    async def _shutdown_gracefully(self) -> None:
        """Stop accepting, finish what is in flight, then stop the loop.

        In that order. The previous handler did only the last step, which is
        why a stop signal behaved like a kill.
        """
        app = None
        try:
            from cullinan.application.model import Application

            app = Application.current()
        except Exception:  # noqa: BLE001 - shutdown must work without an application
            app = None

        if app is not None:
            try:
                app._begin_draining()  # noqa: SLF001 - same package, deliberate
                logger.info(
                    'Draining: waiting up to %ss for %s in-flight request(s); new work is refused',
                    self._drain_timeout(),
                    app.web_runtime.request_count,
                )
            except Exception as exc:  # noqa: BLE001
                logger.warning('Could not begin draining: %s', exc)

        # The listener stays open until the drain is over, on purpose. Closing
        # it first makes the process invisible to a probe -- the only signal it
        # can send is a refused connection -- while keeping it open lets new
        # requests be answered with 503, which says *why* they are not welcome.
        ctx = getattr(app, 'context', None) if app is not None else None
        if ctx is not None:
            try:
                await ctx.ashutdown(timeout=self._drain_timeout())
            except Exception as exc:  # noqa: BLE001
                logger.warning('Drain did not complete cleanly: %s', exc)
            try:
                # ``force``: the bound has expired and the loop is about to
                # stop, so a deferred finalisation would never be re-entered.
                app._finalize_drain(force=True)  # noqa: SLF001 - same package
            except Exception as exc:  # noqa: BLE001
                logger.warning('Could not finalise draining: %s', exc)

        # Only now close the listener: everything that arrived during the drain
        # has been answered, and the process is about to disappear.
        if self._http_server:
            try:
                self._http_server.stop()
            except Exception:  # noqa: BLE001
                pass

        try:
            tornado.ioloop.IOLoop.current().stop()
        except Exception:  # noqa: BLE001
            pass

    def _cleanup(self) -> None:
        if self._http_server:
            try:
                self._http_server.stop()
            except Exception:
                pass


class TornadoRequestAdapter(DriverRequestAdapter):
    def build_request(self, handler: _CullinanTornadoHandler) -> WebRequest:  # type: ignore[override]
        tr = handler.request
        headers = [(name, value) for name, value in tr.headers.get_all()]

        cookies: Dict[str, str] = {name: morsel.value for name, morsel in handler.cookies.items()}

        scheme = tr.protocol or 'http'
        host = tr.host or 'localhost'
        port = 80
        if ':' in host:
            host_part, port_str = host.rsplit(':', 1)
            try:
                port = int(port_str)
                host = host_part
            except ValueError:
                pass

        query_string = tr.uri.split('?', 1)[1] if '?' in tr.uri else ''

        return WebRequest(
            method=tr.method,
            path=tr.path,
            headers=headers,
            body=tr.body or b'',
            query_string=query_string,
            client_ip=tr.remote_ip or '127.0.0.1',
            scheme=scheme,
            server_host=host,
            server_port=port,
            full_url=tr.full_url(),
            cookies=cookies,
        )


class TornadoResponseWriter(DriverResponseWriter):
    def __init__(self, global_headers: Optional[list] = None) -> None:
        self._global_headers = global_headers or []

    def write_response(self, response: WebResponse, handler: _CullinanTornadoHandler) -> None:  # type: ignore[override]
        if handler._finished:
            return

        for h in self._global_headers:
            if isinstance(h, (list, tuple)) and len(h) >= 2:
                handler.set_header(str(h[0]), str(h[1]))

        seen_headers = set()
        for name, value in response.iter_headers(include_content_type=True):
            lower = name.lower()
            if lower == 'set-cookie' or lower in seen_headers:
                handler.add_header(name, value)
            else:
                handler.set_header(name, value)
                seen_headers.add(lower)

        handler.set_status(response.status_code)
        body_bytes = response.render_body()
        if body_bytes:
            handler.write(body_bytes)
        if not handler._finished:
            handler.finish()
