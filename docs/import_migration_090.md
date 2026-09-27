# Cullinan 0.90 Import Migration Guide

This guide helps you migrate your imports from the old structure to the new 0.90 structure.

> **Compatibility page:** use this when updating existing imports; for the current
> public surface, see [API Reference](reference/index.md).

## Overview

Cullinan 0.90 introduces a reorganized `core/` module with clear separation of concerns:

- **`container/`** - IoC/DI container (ApplicationContext, Definition, Scope)
- **`diagnostics/`** - Exceptions and error rendering
- **`lifecycle/`** - Lifecycle management
- **`request/`** - Request context
- **`legacy/`** - Deprecated components (will be removed in a future release)

---

## Quick Migration Table

### Core Container (0.93 API - Recommended)

| Old Import | New Import |
|------------|------------|
| `from cullinan.core.application_context import ApplicationContext` | `from cullinan.core.container import ApplicationContext` |
| `from cullinan.core.definitions import Definition, ScopeType` | `from cullinan.core.container import Definition, ScopeType` |
| `from cullinan.core.factory import Factory` | `from cullinan.core.container import Factory` |
| `from cullinan.core.scope_manager import ScopeManager` | `from cullinan.core.container import ScopeManager` |

### Exceptions

| Old Import | New Import |
|------------|------------|
| `from cullinan.core.exceptions import RegistryFrozenError` | `from cullinan.core.diagnostics import RegistryFrozenError` |
| `from cullinan.core.exceptions import DependencyNotFoundError` | `from cullinan.core.diagnostics import DependencyNotFoundError` |
| `from cullinan.core.exceptions import CircularDependencyError` | `from cullinan.core.diagnostics import CircularDependencyError` |
| `from cullinan.core.exceptions import ScopeNotActiveError` | `from cullinan.core.diagnostics import ScopeNotActiveError` |
| `from cullinan.core.exceptions import ConditionNotMetError` | `from cullinan.core.diagnostics import ConditionNotMetError` |
| `from cullinan.core.exceptions import CreationError` | `from cullinan.core.diagnostics import CreationError` |
| `from cullinan.core.exceptions import LifecycleError` | `from cullinan.core.diagnostics import LifecycleError` |

### Diagnostics

| Old Import | New Import |
|------------|------------|
| `from cullinan.core.diagnostics import render_resolution_path` | `from cullinan.core.diagnostics import render_resolution_path` |
| `from cullinan.core.diagnostics import format_circular_dependency_error` | `from cullinan.core.diagnostics import format_circular_dependency_error` |

### Lifecycle

| Old Import | New Import |
|------------|------------|
| `from cullinan.core.lifecycle import LifecycleManager` | `from cullinan.core.lifecycle import LifecycleManager` |
| `from cullinan.core.lifecycle_hooks import LifecycleEvent` | `from cullinan.core.lifecycle import LifecycleEvent` |
| `from cullinan.core.lifecycle_hooks import LifecycleEventManager` | `from cullinan.core.lifecycle import LifecycleEventManager` |

### Request Context

| Old Import | New Import |
|------------|------------|
| `from cullinan.core.context import RequestContext` | `from cullinan.core.request import RequestContext` |
| `from cullinan.core.context import get_current_context` | `from cullinan.core.request import get_current_context` |
| `from cullinan.core.context import create_context` | `from cullinan.core.request import create_context` |

### Types

| Old Import | New Import |
|------------|------------|
| `from cullinan.core.types import LifecycleState` | `from cullinan.core.diagnostics import LifecycleState` |
| `from cullinan.core.types import LifecycleAware` | `from cullinan.core.diagnostics import LifecycleAware` |

### Top-Level Files

| Old File | New File | Description |
|----------|----------|-------------|
| `cullinan/app.py` | `cullinan/bootstrap.py` | Application bootstrap |
| `cullinan/application.py` | `cullinan/scanner.py` | Module scanner |
| `cullinan/lifecycle_hooks.py` | `cullinan/core/lifecycle/events.py` | Lifecycle events |
| `cullinan/extensions.py` | `cullinan/core/extensions.py` | Extension registry |

---

## Legacy Imports (Deprecated)

The following imports are deprecated and will be removed in a future release:

```python
# Deprecated - will be removed in a future release
from cullinan.core.injection import Inject, InjectByName, injectable
from cullinan.core.provider import Provider, ProviderRegistry
from cullinan.core.facade import IoCFacade, get_ioc_facade
from cullinan.core.registry import Registry, SimpleRegistry
from cullinan.core.scope import SingletonScope, TransientScope, RequestScope
```

These have been moved to `cullinan.core.legacy/` and will emit `DeprecationWarning`.

---

## Code Examples

### Before (0.83)

```python
from cullinan.core.application_context import ApplicationContext
from cullinan.core.definitions import Definition, ScopeType
from cullinan.core.exceptions import (
    RegistryFrozenError,
    CircularDependencyError,
    ScopeNotActiveError,
)
from cullinan.core.context import RequestContext

ctx = ApplicationContext()
ctx.register(Definition(
    name='UserService',
    factory=lambda c: UserService(),
    scope=ScopeType.SINGLETON,
    source='service:UserService'
))
ctx.refresh()
```

### After (0.90)

```python
from cullinan.core.container import ApplicationContext, Definition, ScopeType
from cullinan.core.diagnostics import (
    RegistryFrozenError,
    CircularDependencyError,
    ScopeNotActiveError,
)
from cullinan.core.request import RequestContext

ctx = ApplicationContext()
ctx.register(Definition(
    name='UserService',
    factory=lambda c: UserService(),
    scope=ScopeType.SINGLETON,
    source='service:UserService'
))
ctx.refresh()
```

---

## Batch Migration Script

You can use the following regex patterns to batch-update your imports:

```bash
# Container imports
sed -i 's/from cullinan\.core\.application_context import/from cullinan.core.container import/g' *.py
sed -i 's/from cullinan\.core\.definitions import/from cullinan.core.container import/g' *.py
sed -i 's/from cullinan\.core\.factory import/from cullinan.core.container import/g' *.py
sed -i 's/from cullinan\.core\.scope_manager import/from cullinan.core.container import/g' *.py

# Exception imports
sed -i 's/from cullinan\.core\.exceptions import/from cullinan.core.diagnostics import/g' *.py

# Request context imports
sed -i 's/from cullinan\.core\.context import/from cullinan.core.request import/g' *.py
```

---

## Unchanged Imports

The following imports all work. Names that belong to the top-level entry
surface are still imported from `cullinan`; names that live in a dedicated
module are imported from that module:

```python
# These still work the same way
from cullinan import (
    # Configuration
    configure, get_config, CullinanConfig,

    # Service layer
    service,

    # Controller
    get_api, post_api, patch_api, delete_api, put_api,
    response,

    # Middleware
    Middleware, middleware,

    # WebSocket
    websocket_handler,
)

# Service layer classes and registries
from cullinan.core.services import Service, ServiceRegistry, get_service_registry

# Controller registry and request handler base
from cullinan.web.controller import ControllerRegistry, get_controller_registry, Handler

# Middleware chain
from cullinan.web.middleware import MiddlewareChain

# WebSocket registry
from cullinan.web.websocket_registry import WebSocketRegistry

# Test helpers
from cullinan.testing import ServiceTestCase, MockService, TestRegistry
```

---

## Questions?

- See [Dependency Injection Guide](dependency_injection_guide.md)
- See [Migration Guide](migration_guide.md)
