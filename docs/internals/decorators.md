# Decorators

> **Author**: plumeink

This document describes the decorator-based component registration system in Cullinan 0.90.

## Overview

Cullinan 0.90 introduces a powerful decorator system that provides a clean, declarative way to register components. This approach is consistent with Cullinan's original design philosophy while integrating with the new IoC/DI 2.0 architecture.

### Key Features

- **Simple Syntax**: Use `@service`, `@controller`, `@component` without parentheses
- **Two-Phase Registration**: Decorators collect metadata → `refresh()` registers all
- **Dependency Injection**: Constructor injection (bare annotation, recommended), `Inject`, `InjectByName`, `Lazy` markers
- **Conditional Registration**: Register components based on conditions

## Component Decorators

### @service

Marks a class as a service component. Services are singleton by default.

```python
from cullinan.core import service
from cullinan.core.decorators import Inject

# Simple usage (no parentheses needed)
@service
class UserService:
    def get_user(self, id: int):
        return {"id": id}

# With parameters
@service(name="customUserService", scope="prototype")
class UserService:
    pass

# With dependencies
@service(dependencies=["EmailService"])
class NotificationService:
    email: EmailService = Inject()
```

**Parameters:**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `name` | `str` | Class name | Custom component name |
| `scope` | `str` | `"singleton"` | Scope: `"singleton"`, `"prototype"`, `"request"` |
| `dependencies` | `list[str]` | `None` | Explicit dependencies for ordering |

### @controller

Marks a class as a controller component. Controllers handle HTTP requests.

```python
from cullinan.web.controller import controller, get_api
from cullinan.core import Inject
from cullinan.web.params import Path

# Simple usage
@controller
class RootController:
    pass

# With URL prefix
@controller(url="/api/users")
class UserController:
    user_service: UserService = Inject()
    
    @get_api(url="")
    def list_users(self):
        return {"users": []}
    
    @get_api(url="/{id}")
    async def get_user(self, id: int = Path()):
        return self.user_service.get_user(id)
```

**Parameters:**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `url` | `str` | `""` | URL prefix for all routes |

### @component

Generic component decorator for classes that are neither services nor controllers.

```python
from cullinan.core import component

# Simple usage
@component
class CacheManager:
    pass

# With scope
@component(scope="prototype")
class RequestHandler:
    pass

# With custom name
@component(name="myHelper")
class Helper:
    pass
```

**Parameters:**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `name` | `str` | Class name | Custom component name |
| `scope` | `str` | `"singleton"` | Scope: `"singleton"`, `"prototype"`, `"request"` |

### @provider

Marks a class as a dependency provider (factory).

```python
from cullinan.core.decorators import provider

@provider
class DatabaseConnectionProvider:
    def get(self):
        return create_connection()

@provider(name="customProvider")
class CustomProvider:
    pass
```

## Injection Markers

### Constructor Injection (recommended)

The preferred and simplest way to inject dependencies — just annotate the type. No imports needed beyond the type itself.

```python
@service
class UserService:
    # Constructor injection (recommended):
    # Bare annotation — no Inject() needed
    email_service: EmailService
    cache: CacheService

    # Optional dependencies can use default=None
    logger: LoggerService = None
```

**Benefits:**
- No import from `cullinan.core.decorators` needed
- Cleaner, more Pythonic code
- Works by default for all `@service`, `@controller`, and `@component` classes

> **Note:** Constructor injection resolves dependencies by type annotation. If you need name‑based or lazy injection, use the markers below.

### Inject

Inject a dependency by type annotation (explicit marker).

```python
from cullinan.core.decorators import Inject

@service
class UserService:
    # Required injection (default)
    email_service: EmailService = Inject()
    
    # Optional injection
    cache: CacheService = Inject(required=False)
```

**Parameters:**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `required` | `bool` | `True` | Raise error if dependency not found |

### InjectByName

Inject a dependency by explicit name.

```python
from cullinan.core.decorators import InjectByName

@service
class UserService:
    # Explicit name
    email = InjectByName("EmailService")
    
    # Auto-infer from attribute name (user_repo -> UserRepo)
    user_repo = InjectByName()
```

**Parameters:**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `name` | `str` | `None` | Dependency name (auto-infer if None) |
| `required` | `bool` | `True` | Raise error if dependency not found |

### Lazy

Lazy injection - resolve dependency on first access. Useful for breaking circular dependencies.

```python
from cullinan.core.decorators import Lazy

@service
class ServiceA:
    # Break circular dependency
    service_b: 'ServiceB' = Lazy()

@service
class ServiceB:
    service_a: 'ServiceA' = Lazy()
```

**Parameters:**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `name` | `str` | `None` | Optional explicit dependency name |

## Conditional Decorators

### @ConditionalOnProperty

Register component based on configuration property.

```python
from cullinan.core.decorators import service
from cullinan.core.conditions import ConditionalOnProperty

@service
@ConditionalOnProperty("feature.email", having_value="true")
class EmailService:
    pass

@service
@ConditionalOnProperty("cache.enabled", match_if_missing=True)
class CacheService:
    pass
```

### @ConditionalOnClass

Register component only if a class/module is available.

```python
from cullinan.core.conditions import ConditionalOnClass

@service
@ConditionalOnClass("redis.Redis")
class RedisCacheService:
    pass
```

### @ConditionalOnMissingBean

Register component only if specified bean is not already registered.

```python
from cullinan.core.conditions import ConditionalOnMissingBean

@service
@ConditionalOnMissingBean("CustomEmailService")
class DefaultEmailService:
    pass
```

### @ConditionalOnBean

Register component only if specified bean exists.

```python
from cullinan.core.conditions import ConditionalOnBean

@service
@ConditionalOnBean("DatabaseConnection")
class DatabaseService:
    pass
```

### @Conditional

Generic conditional with custom function.

```python
from cullinan.core.conditions import Conditional

def is_production(ctx):
    return ctx.get_property("env") == "production"

@service
@Conditional(is_production)
class ProductionOnlyService:
    pass
```

## Complete Example

```python
from cullinan.web.controller import controller, get_api
from cullinan.core import service, ApplicationContext, PendingRegistry
from cullinan.core.decorators import Inject, InjectByName
from cullinan.core.conditions import ConditionalOnClass
from cullinan.web.params import Path

# Reset for clean state
PendingRegistry.reset()

# Define services
@service
class EmailService:
    def send(self, to: str, content: str):
        return f"Email sent to {to}"

@service
class UserService:
    email_service: EmailService = Inject()
    
    def get_user(self, id: int):
        return {"id": id, "name": f"User{id}"}
    
    def notify_user(self, id: int):
        user = self.get_user(id)
        return self.email_service.send(user["name"], "Hello!")

# Define controller
@controller(url="/api/users")
class UserController:
    user_service: UserService = Inject()
    
    @get_api(url="/{id}")
    async def get_user(self, id: int = Path()):
        return self.user_service.get_user(id)

# Optional JSON processor (only if json module available)
@service
@ConditionalOnClass("json")
class JsonProcessor:
    def process(self, data):
        import json
        return json.dumps(data)

# Create and start application
ctx = ApplicationContext()
ctx.refresh()

# Use services
user_svc = ctx.get("UserService")
print(user_svc.get_user(1))
# Output: {'id': 1, 'name': 'User1'}

# Cleanup
ctx.shutdown()
```

## Two-Phase Registration

Decorators use a two-phase registration mechanism:

```
┌─────────────────────┐     ┌─────────────────────┐     ┌─────────────────────┐
│   Module Loading    │     │  ApplicationContext │     │    Runtime Use      │
│                     │     │      refresh()      │     │                     │
│  @service collects  │────▶│  Process pending    │────▶│  ctx.get("Name")    │
│  metadata to        │     │  registrations      │     │  returns instance   │
│  PendingRegistry    │     │  Freeze registry    │     │                     │
└─────────────────────┘     └─────────────────────┘     └─────────────────────┘
```

### PendingRegistry

All decorator metadata is collected in `PendingRegistry`:

```python
from cullinan.core import PendingRegistry

# Check registered components before refresh
pending = PendingRegistry.get_instance()
print(f"Pending registrations: {pending.count}")

# After refresh, registry is frozen
ctx.refresh()
assert pending.is_frozen  # True
```

## Best Practices

1. **Use decorators without parentheses when possible**: `@service` is cleaner than `@service()`

2. **Prefer bare annotations (constructor injection)**: Cleaner than `Inject()`, no import needed. Use `Inject()` only when you need `required=False` or explicit markers

3. **Use `Lazy` for circular dependencies**: Breaks the cycle explicitly

4. **Put conditions after component decorator**: Order matters!
   ```python
   @service  # First
   @ConditionalOnClass("redis")  # Second
   class RedisService:
       pass
   ```

5. **Reset PendingRegistry in tests**:
   ```python
   def setup_method(self):
       PendingRegistry.reset()
   ```

## Migration from v0.83

| v0.83 | v0.90 |
|-------|-------|
| `@service` (from `cullinan.core.service`) | `@service` (from `cullinan.core`) |
| `@controller(url=...)` (from `cullinan.web.controller`) | `@controller(url=...)` (from `cullinan.core`) |
| Manual service registry | `ApplicationContext.refresh()` |

```python
# Before (v0.83)
from cullinan.core.services import service
from cullinan.web.controller import controller

# After (v0.90)
from cullinan.core import service, controller
```

## Related Documentation

- [Dependency Injection Guide](../dependency_injection_guide.md)
- [Import Migration Guide](../import_migration_090.md)
- [Components](components.md)
