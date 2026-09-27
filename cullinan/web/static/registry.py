# -*- coding: utf-8 -*-
"""Startup-time registration of :class:`StaticFiles` mounts on the router.

Static mounts are translated into wildcard routes (``/<prefix>/**`` or
``/**`` for SPA root mounts) so they integrate with the existing dispatcher,
middleware pipeline, and runtime adapters without any engine-specific code.

Author: plumeink
"""

from __future__ import annotations

import logging
from typing import Iterable, Optional

from cullinan.web.gateway.router import Router
from cullinan.web.static.handler import build_static_handler
from cullinan.web.static.spec import StaticFiles

logger = logging.getLogger(__name__)


# Routes registered for static mounts are tagged with this marker so other
# tooling (e.g. OpenAPI generation) can recognise and filter them.
STATIC_ROUTE_TAG = "cullinan.static"


def install_static_files(
    specs: Iterable[StaticFiles],
    *,
    router: Router,
    project_root: Optional[str] = None,
) -> int:
    """Register each :class:`StaticFiles` spec on the given ``router``.

    Args:
        specs: Iterable of static-files declarations.
        router: Target gateway router (typically the global one).
        project_root: Anchor used to resolve relative ``directory`` paths.

    Returns:
        Number of route entries registered (each spec registers a wildcard
        pattern plus a bare-prefix pattern for each accepted method).
    """
    count = 0
    for spec in specs:
        handler = build_static_handler(spec, project_root=project_root)
        # Wildcard sub-paths (e.g. /static/**, /assets/**, /**)
        wildcard_pattern = spec.route_pattern()
        # Bare prefix (e.g. /static, /assets, /) so directory-index and SPA
        # root requests reach the handler — Router's wildcard requires at
        # least one captured segment.
        bare_pattern = spec.url
        patterns = [wildcard_pattern]
        if bare_pattern != wildcard_pattern:
            patterns.append(bare_pattern)

        metadata = {
            "tags": (STATIC_ROUTE_TAG,),
            "hidden": True,  # exclude from OpenAPI by default
            "static_url": spec.url,
            "static_directory": str(spec.resolve_directory(project_root)),
            "static_spa": spec.spa,
        }

        for method in spec.methods:
            for pattern in patterns:
                router.add_route(
                    method=method,
                    path=pattern,
                    handler=handler,
                    metadata=metadata,
                )
                count += 1
        logger.info(
            "└---static mount: %s -> %s%s",
            spec.url,
            spec.resolve_directory(project_root),
            " (SPA)" if spec.spa else "",
        )
    return count
