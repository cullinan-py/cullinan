# -*- coding: utf-8 -*-
"""Cullinan Web Adapter base class.

Defines the contract that all runtime adapters must implement.

Author: plumeink
"""

import logging
import threading
from abc import ABC, abstractmethod
from typing import Any, Callable, Optional

from .driver import DriverCapabilities, DriverRequestAdapter, DriverResponseWriter, WebDriver
from cullinan.web.gateway.dispatcher import Dispatcher

logger = logging.getLogger(__name__)


def resolve_max_request_body_bytes() -> Optional[int]:
    """The configured request-body ceiling, or ``None`` for no ceiling.

    A ceiling nobody enforces is a comment: both adapters call this and both
    refuse the request themselves, because the body is read before routing (the
    framework cannot know whether the route wants it until it has it).
    """
    try:
        from cullinan.support.config import get_config

        value = getattr(get_config(), 'max_request_body_bytes', None)
    except Exception:  # noqa: BLE001 - a config lookup must never break a request
        return None
    if isinstance(value, int) and not isinstance(value, bool) and value > 0:
        return value
    return None


class WebAdapter(WebDriver, ABC):
    """Abstract base class for runtime-specific Web adapters.

    Adapters are responsible for:
    1. Creating a native server application that routes **all** requests
       through the shared ``Dispatcher``.
    2. Converting native request objects into ``WebRequest``.
    3. Converting ``WebResponse`` back into the native response format.
    4. Starting / stopping the server.

    Concrete implementations:
    - ``TornadoAdapter``  — uses a single ``tornado.web.RequestHandler``
    - ``ASGIAdapter``     — produces a standard ASGI 3.0 application callable
    """

    def __init__(self, dispatcher: Dispatcher, runtime: Optional[Any] = None) -> None:
        super().__init__(runtime=runtime)
        self._dispatcher = dispatcher
        self._shutdown_requester: Optional[Callable[[], bool]] = None
        self._shutdown_claim_lock = threading.Lock()
        self._shutdown_claimed = False

    def _claim_shutdown_request(self) -> bool:
        """Claim the right to schedule the drain; ``True`` only for the first caller.

        A second ``request_shutdown()`` has nothing new to ask for: the drain is
        already scheduled, or already running. Scheduling it twice would run
        ``_begin_draining()`` and the drain wait twice, which happens to be
        survivable today and is not a property anyone checked -- "it did not
        explode" is not the same answer as "it happened once".

        What the caller is told does **not** change: the second call still answers
        ``True``, because "this server has been asked to stop" remains true, and
        ``False`` is reserved for "there is nothing to ask" -- the answer a
        supervisor acts on after the process is gone.
        """
        with self._shutdown_claim_lock:
            if self._shutdown_claimed:
                return False
            self._shutdown_claimed = True
            return True

    def _register_shutdown_requester(self, requester: Optional[Callable[[], bool]]) -> None:
        """Publish (or withdraw) this engine's programmatic shutdown hook.

        Called from ``run()``: before the blocking call it publishes the hook,
        after it returns it withdraws it, so "is a server running?" has one
        answer that the adapter itself maintains. The hook is also registered on
        the runtime, which is what ``Application.request_shutdown()`` reaches --
        a caller asking an application to stop does not hold the adapter.

        Withdrawing also releases the drain claim, so a second ``run()`` on the
        same adapter can ask for a shutdown of its own.
        """
        self._shutdown_requester = requester
        if requester is None:
            with self._shutdown_claim_lock:
                self._shutdown_claimed = False
        runtime = self.runtime
        setter = getattr(runtime, "set_shutdown_requester", None)
        if setter is None:
            return
        try:
            setter(requester)
        except Exception:  # noqa: BLE001 - publishing must not stop a server
            logger.debug("Could not publish the shutdown hook on the runtime", exc_info=True)

    def request_shutdown(self) -> bool:
        """Ask this adapter's running server to stop gracefully.

        ``False`` when this adapter is not serving, so a supervisor can tell
        "already stopped" from "asked". Safe to call from any thread, and from
        inside the loop as well -- the concrete hook is what makes it so.
        """
        requester = self._shutdown_requester
        if requester is None:
            return False
        try:
            return bool(requester())
        except Exception:  # noqa: BLE001 - a shutdown request must not raise
            logger.exception("Could not ask the %s to shut down", self.get_engine_name())
            return False

    @property
    def dispatcher(self) -> Dispatcher:
        runtime = self.runtime
        if runtime is not None and hasattr(runtime, "router") and hasattr(runtime, "pipeline"):
            dispatcher = getattr(runtime, "dispatcher", None)
            if dispatcher is not None:
                return dispatcher
        return self._dispatcher

    def capabilities(self) -> DriverCapabilities:
        return DriverCapabilities()

    def create_request_adapter(self) -> DriverRequestAdapter:
        raise NotImplementedError(f"{self.__class__.__name__} must implement create_request_adapter()")

    def create_response_writer(self) -> DriverResponseWriter:
        raise NotImplementedError(f"{self.__class__.__name__} must implement create_response_writer()")

    def build_app(self) -> Any:
        return self.create_app()

    @abstractmethod
    def create_app(self) -> Any:
        """Create the native application object.

        Returns:
            The native application (e.g. ``tornado.web.Application`` or an ASGI callable).
        """
        ...

    @abstractmethod
    def run(self, host: str = '0.0.0.0', port: int = 4080, **kwargs: Any) -> None:
        """Start the server (blocking).

        Args:
            host: Bind address.
            port: Bind port.
            **kwargs: Engine-specific options.
        """
        ...

    @abstractmethod
    async def shutdown(self) -> None:
        """Gracefully shut down the server."""
        ...

    def get_engine_name(self) -> str:
        """Return a human-readable name for this adapter."""
        return self.__class__.__name__
