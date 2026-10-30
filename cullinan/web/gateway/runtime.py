# -*- coding: utf-8 -*-
"""High-availability Web runtime primitives."""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass, field
from typing import Any, Callable, Iterable, List, Optional

from .dispatcher import Dispatcher
from .exception_handler import ExceptionHandler
from .invocation import ExceptionResolver, ReturnValueHandler
from .pipeline import MiddlewarePipeline
from .router import Router
from .web_core import HeaderPolicy

logger = logging.getLogger(__name__)


class WebRuntimeState:
    CREATED = "CREATED"
    BUILDING = "BUILDING"
    VALIDATING = "VALIDATING"
    WARMING = "WARMING"
    ACTIVE = "ACTIVE"
    DRAINING = "DRAINING"
    CLOSED = "CLOSED"


@dataclass
class WebRuntimeConfig:
    warmup_checks: Iterable[Callable[["WebRuntime"], None]] = field(default_factory=tuple)
    health_checks: Iterable[Callable[["WebRuntime"], None]] = field(default_factory=tuple)
    drain_timeout: float = 30.0
    trust_forwarded_headers: bool = False


class WebRuntime:
    """Carries the active Web stack and supports atomic runtime switching."""

    _active_runtime: Optional["WebRuntime"] = None
    _active_lock = threading.RLock()

    def __init__(
        self,
        *,
        router: Optional[Router] = None,
        pipeline: Optional[MiddlewarePipeline] = None,
        exception_handler: Optional[ExceptionHandler] = None,
        header_policy: Optional[HeaderPolicy] = None,
        return_value_handler: Optional[ReturnValueHandler] = None,
        exception_resolver: Optional[ExceptionResolver] = None,
        config: Optional[WebRuntimeConfig] = None,
    ) -> None:
        self.router = router or Router()
        self.pipeline = pipeline or MiddlewarePipeline()
        self.exception_handler = exception_handler or ExceptionHandler()
        self.header_policy = header_policy or HeaderPolicy()
        self.return_value_handler = return_value_handler or ReturnValueHandler()
        self.exception_resolver = exception_resolver or ExceptionResolver(self.exception_handler)
        self.config = config or WebRuntimeConfig()
        self.dispatcher = Dispatcher(
            router=self.router,
            pipeline=self.pipeline,
            exception_handler=self.exception_handler,
            header_policy=self.header_policy,
            return_value_handler=self.return_value_handler,
            exception_resolver=self.exception_resolver,
        )
        self.state = WebRuntimeState.CREATED
        self._request_count = 0
        self._request_lock = threading.RLock()
        self._close_callbacks: List[Callable[["WebRuntime"], None]] = []
        self.application: Optional[Any] = None
        #: The transport's "stop this server" hook, published by an adapter while
        #: it is serving and withdrawn when it stops. ``None`` means no server is
        #: running under this runtime, which is why a request to shut down can be
        #: answered with ``False`` instead of raising.
        self._shutdown_requester: Optional[Callable[[], bool]] = None

    def set_shutdown_requester(self, requester: Optional[Callable[[], bool]]) -> None:
        """Publish (or withdraw) the engine's programmatic shutdown hook.

        The adapter owns the engine-specific part -- a Tornado ``IOLoop``, a
        uvicorn ``Server`` -- and registers it here when the server starts, so
        the application can be asked to stop without the caller holding the
        adapter. ``None`` withdraws it: after ``run()`` returns there is nothing
        left to stop, and reporting otherwise would be a lie a supervisor acts
        on.
        """
        with self._request_lock:
            self._shutdown_requester = requester

    def request_shutdown(self) -> bool:
        """Ask the running server to stop gracefully.

        Returns ``True`` when a running server was actually asked, ``False`` when
        there is nothing to ask. The call is safe from any thread: the hook it
        delegates to is the engine's threaded entry point, not the loop itself.
        """
        with self._request_lock:
            requester = self._shutdown_requester
        if requester is None:
            return False
        try:
            return bool(requester())
        except Exception:  # noqa: BLE001 - a shutdown request must not raise
            logger.exception("Could not ask the running server to shut down")
            return False

    def validate(self) -> None:
        self.state = WebRuntimeState.VALIDATING
        for check in self.config.health_checks:
            check(self)

    def warmup(self) -> None:
        self.state = WebRuntimeState.WARMING
        for check in self.config.warmup_checks:
            check(self)

    def prepare(self) -> None:
        self.state = WebRuntimeState.BUILDING
        self.validate()
        self.warmup()

    def add_close_callback(self, callback: Callable[["WebRuntime"], None]) -> None:
        self._close_callbacks.append(callback)

    def activate(self, *, prepare: bool = True) -> Optional["WebRuntime"]:
        if prepare and self.state not in {WebRuntimeState.WARMING, WebRuntimeState.ACTIVE}:
            self.prepare()
        with self._active_lock:
            previous = self.__class__._active_runtime
            if previous is not None and previous is not self and previous.state != WebRuntimeState.CLOSED:
                previous.begin_draining()
            self.__class__._active_runtime = self
            self.state = WebRuntimeState.ACTIVE
        return previous

    def begin_draining(self) -> None:
        with self._request_lock:
            if self.state == WebRuntimeState.CLOSED:
                return
            self.state = WebRuntimeState.DRAINING
            should_close = self._request_count == 0
        if should_close:
            self.close()

    def close(self) -> None:
        callbacks: List[Callable[["WebRuntime"], None]] = []
        with self._request_lock:
            if self.state == WebRuntimeState.CLOSED:
                return
            self.state = WebRuntimeState.CLOSED
            callbacks = list(self._close_callbacks)
        for callback in callbacks:
            callback(self)

    def begin_request(self) -> None:
        with self._request_lock:
            self._request_count += 1

    def end_request(self) -> None:
        with self._request_lock:
            self._request_count = max(0, self._request_count - 1)
            should_close = self.state == WebRuntimeState.DRAINING and self._request_count == 0
        if should_close:
            self.close()

    @property
    def request_count(self) -> int:
        with self._request_lock:
            return self._request_count

    @classmethod
    def current(cls) -> Optional["WebRuntime"]:
        with cls._active_lock:
            return cls._active_runtime

    @classmethod
    def activate_runtime(cls, runtime: "WebRuntime", *, prepare: bool = True) -> Optional["WebRuntime"]:
        return runtime.activate(prepare=prepare)

    @classmethod
    def bind_runtime(cls, runtime: Optional["WebRuntime"]) -> None:
        with cls._active_lock:
            cls._active_runtime = runtime

    @classmethod
    def clear_active(cls) -> None:
        with cls._active_lock:
            cls._active_runtime = None
