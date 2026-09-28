# -*- coding: utf-8 -*-
"""Cullinan Gateway Globals

Provides module-level access to the shared Dispatcher, Router, and Pipeline
instances used by the framework.

Author: plumeink
"""

import logging
from typing import Optional

from .router import Router
from .dispatcher import Dispatcher
from .pipeline import MiddlewarePipeline
from .exception_handler import ExceptionHandler

logger = logging.getLogger(__name__)

# ============================================================================
# Module-level singletons
# ============================================================================

_global_router: Optional[Router] = None
_global_dispatcher: Optional[Dispatcher] = None
_global_pipeline: Optional[MiddlewarePipeline] = None
_global_exception_handler: Optional[ExceptionHandler] = None


def get_router() -> Router:
    """Get the global Router instance (created lazily)."""
    global _global_router
    if _global_router is None:
        _global_router = Router()
    return _global_router


def get_dispatcher() -> Dispatcher:
    """Get the global Dispatcher instance (created lazily)."""
    global _global_dispatcher
    if _global_dispatcher is None:
        _global_dispatcher = Dispatcher(
            router=get_router(),
            pipeline=get_pipeline(),
            exception_handler=get_exception_handler(),
        )
    return _global_dispatcher


def get_pipeline() -> MiddlewarePipeline:
    """Get the global MiddlewarePipeline instance (created lazily)."""
    global _global_pipeline
    if _global_pipeline is None:
        _global_pipeline = MiddlewarePipeline()
    return _global_pipeline


def _peek_pipeline() -> Optional[MiddlewarePipeline]:
    """Return the global pipeline as it currently stands, without creating it.

    ``get_pipeline()`` is lazy, so *calling* it is not a read: it materializes a
    pipeline as a side effect.  Observers that must not perturb what they look
    at -- diagnostics, and the boot boundary that is about to reset the gateway
    -- read the module-level global through here instead.
    """
    return _global_pipeline


def get_exception_handler() -> ExceptionHandler:
    """Get the global ExceptionHandler instance (created lazily)."""
    global _global_exception_handler
    if _global_exception_handler is None:
        _global_exception_handler = ExceptionHandler()
    return _global_exception_handler


def reset_gateway() -> None:
    """Reset all gateway globals (for testing)."""
    global _global_router, _global_dispatcher, _global_pipeline, _global_exception_handler
    _global_router = None
    _global_dispatcher = None
    _global_pipeline = None
    _global_exception_handler = None
    logger.debug('Gateway globals reset')

