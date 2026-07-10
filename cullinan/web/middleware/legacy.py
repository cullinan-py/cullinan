 # -*- coding: utf-8 -*-
"""Legacy middleware registration API (Backward Compatibility).

This module provides backward compatibility for the old middleware
registration API. It will be removed in v1.0.

DEPRECATED: Use @middleware decorator instead.

Author: Cullinan
"""

# ============================================================================
# BACKWARD_COMPAT: v0.8 - The following code is for backward compatibility, planned for removal in v1.0
# Alternative: Use the @middleware decorator instead of manual registration
# ============================================================================

import logging
from typing import Type, Optional
from cullinan.support.deprecation import deprecated

logger = logging.getLogger(__name__)


@deprecated(
    version="0.8",
    alternative="@middleware decorator",
    removal_version="1.0"
)
def register_middleware_manual(middleware_class: Type,
                              priority: int = 100,
                              name: Optional[str] = None):
    """Manually register middleware (deprecated).

    This function is deprecated. Use the @middleware decorator instead.

    Args:
        middleware_class: Middleware class
        priority: Priority
        name: Optional name

    Example (DEPRECATED):
        >>> register_middleware_manual(MyMiddleware, priority=50)

    Recommended:
        >>> @middleware(priority=50)
        >>> class MyMiddleware(Middleware):
        ...     pass
    """
    from cullinan.web.middleware.registry import get_middleware_registry

    registry = get_middleware_registry()
    # Note: name parameter is ignored in new API for backward compatibility
    registry.register(middleware_class, priority=priority)

    logger.warning(
        "register_middleware_manual() is deprecated. "
        "Use @middleware decorator instead."
    )


@deprecated(
    version="0.8",
    alternative="MiddlewareRegistry.get_all()",
    removal_version="1.0"
)
def get_registered_middlewares():
    """Get all registered middleware (deprecated).

    Returns:
        List of all registered middleware
    """
    from cullinan.web.middleware.registry import get_middleware_registry

    registry = get_middleware_registry()
    return registry.get_all()


# ============================================================================
# END BACKWARD_COMPAT
# ============================================================================

