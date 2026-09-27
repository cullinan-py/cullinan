# -*- coding: utf-8 -*-
"""Extension point registry and discovery for Cullinan framework.

The live extension registry lives in :mod:`cullinan.support.extensions`. This
module re-exports it so that ``cullinan.core.extensions`` and
``cullinan.support.extensions`` resolve to the *same* objects - in particular
the same registry singleton - instead of each owning a private copy.

Author: plumeink
"""

# ``X as X`` marks these as deliberate re-exports, which satisfies ruff's F401
# without adding a module-level ``__all__``: an ``__all__`` here would change the
# framework's declared-surface counts, and a bare ``import X`` would be flagged
# as unused.
from cullinan.support.extensions import (
    ExtensionCategory as ExtensionCategory,
    ExtensionPoint as ExtensionPoint,
    ExtensionRegistry as ExtensionRegistry,
    get_extension_registry as get_extension_registry,
    list_extension_points as list_extension_points,
    reset_extension_registry as reset_extension_registry,
)
