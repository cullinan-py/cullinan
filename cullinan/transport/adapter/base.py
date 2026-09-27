# -*- coding: utf-8 -*-
"""Cullinan Web Adapter base class.

Defines the contract that all runtime adapters must implement.

Author: plumeink
"""

import logging
from abc import ABC, abstractmethod
from typing import Any, Optional

from .driver import DriverCapabilities, DriverRequestAdapter, DriverResponseWriter, WebDriver
from cullinan.web.gateway.dispatcher import Dispatcher

logger = logging.getLogger(__name__)


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
