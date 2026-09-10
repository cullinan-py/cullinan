# Cullinan 0.93 Migration Guide

> **Version**: v0.90  
> **Author**: Cullinan

> **Upgrade-only page:** use this when moving existing code, not when learning the
> recommended API path for a new project.

This guide helps you migrate from Cullinan 1.x to 0.93 (0.90).

## v0.95 migration notes (Track A internal refactor)

v0.95 is a non-breaking release that adds deprecation markers and optional
strict switches. Existing code continues to work without changes, but you are
encouraged to migrate now.

### Deprecated since v0.95 (removed in v0.97)

The five legacy compatibility symbols are now formally deprecated. Both a
standard `DeprecationWarning` (tool-chain visible) and the existing
`CompatibilitySemanticWarning` (deduplicated semantic reminder) fire on each
use.

| Deprecated symbol | Replacement |
|-------------------|-------------|
| `@injectable` | `@service` / `@component` / `@controller` (classes are auto-injectable) |
| `@inject_constructor` | `ApplicationContext.refresh()` |
| `InjectionRegistry` | `ApplicationContext` / `get_application_context()` |
| `get_injection_registry()` | `ApplicationContext` / `get_application_context()` |
| `reset_injection_registry()` | Create a new `ApplicationContext` explicitly |

To surface deprecation warnings as errors in CI:

```bash
python -m pytest -W error::DeprecationWarning
```

### Optional strict switches

- `strict_private_injection=True` (or `CULLINAN_STRICT_PRIVATE_INJECTION=1`):
  single-underscore (`_xxx`) class attributes are skipped by the injection
  marker scanner. Default `False` preserves v0.93a11+ behavior.
- `strict_lifecycle=True`: `on_startup`/`on_shutdown` failures propagate as
  `LifecycleError`. Default `False` preserves v0.94 behavior (log and swallow).

### Structured scope violations

Transitive scope violations now raise `ScopeViolationError` (a subclass of
`LifecycleError`). Existing `except LifecycleError` handlers continue to work.
The new exception carries `dependency_chain`, `origin_name`, and
`violating_component` fields for richer diagnostics; use
`format_scope_violation_error()` to render a human-readable chain.

## Breaking Changes

### 1. Single Entry Point

**Before (1.x):**
```python
from cullinan.core import get_injection_registry, get_service_registry

registry = get_injection_registry()
registry.add_provider_source(my_source)
```

**After (0.93):**
```python
from cullinan.core.container import ApplicationContext, Definition, ScopeType

ctx = ApplicationContext()
ctx.register(Definition(
    name='MyService',
    factory=lambda c: MyService(),
    scope=ScopeType.SINGLETON,
    source='service:MyService'
))
ctx.refresh()
```

### 2. Registry Freeze

In 0.93, the registry is frozen after `refresh()`. Any attempt to register new dependencies will raise `RegistryFrozenError`.

**Before (1.x):**
```python
# Could register at any time
registry.register('NewService', NewService)
```

**After (0.93):**
```python
ctx = ApplicationContext()
ctx.register(...)  # OK before refresh
ctx.refresh()
ctx.register(...)  # RegistryFrozenError!
```

### 3. Scope Enforcement

Request-scoped dependencies now strictly require a `RequestContext`.

**Before (1.x):**
```python
# Might silently fail or return wrong instance
instance = registry.get('RequestScoped')
```

**After (0.93):**
```python
ctx.enter_request_context()
try:
    instance = ctx.get('RequestScoped')  # OK
finally:
    ctx.exit_request_context()

# Without context:
ctx.get('RequestScoped')  # ScopeNotActiveError!
```

### 4. Structured Exceptions

All exceptions now carry structured diagnostic fields.

**Before (1.x):**
```python
try:
    registry.resolve('Missing')
except Exception as e:
    print(str(e))  # Generic message
```

**After (0.93):**
```python
from cullinan.core.diagnostics import DependencyNotFoundError

try:
    ctx.get('Missing')
except DependencyNotFoundError as e:
    print(e.dependency_name)      # 'Missing'
    print(e.resolution_path)      # ['ParentService', 'Missing']
    print(e.candidate_sources)    # [{'source': '...', 'reason': '...'}]
```

### 5. Circular Dependency Detection

Circular dependencies now produce stable, ordered chains.

**Before (1.x):**
```python
# Unordered, inconsistent output
CircularDependencyError: Circular dependency detected
```

**After (0.93):**
```python
# Stable, ordered chain
CircularDependencyError: Circular dependency detected: A -> B -> C -> A
```

## Migration Steps

### Step 1: Update Imports

```python
# Old imports (deprecated)
from cullinan.core import get_injection_registry, Inject, InjectByName

# New imports (0.93)
from cullinan.core.container import ApplicationContext, Definition, ScopeType
```

### Step 2: Convert Service Registration

```python
# Old style
@service
class UserService:
    user_repo = Inject()

# New style
ctx.register(Definition(
    name='UserService',
    factory=lambda c: UserService(user_repo=c.get('UserRepository')),
    scope=ScopeType.SINGLETON,
    source='service:UserService'
))
```

### Step 3: Update Application Startup

```python
# Old style (app.py)
from cullinan.app import run

# New style
from cullinan import application, configure

@configure(user_packages=["your_app"])
@application
def main(): ...

main()
```

The entry method is now the recommended default entrypoint. `configure(root_module=...)` is no longer part of the default public startup model.

### Step 4: Handle Request Scope

```python
# In request handler
class MyHandler(RequestHandler):
    def get(self):
        ctx.enter_request_context()
        try:
            service = ctx.get('RequestScopedService')
            # ... use service ...
        finally:
            ctx.exit_request_context()
```

## Deprecated APIs

The following APIs are deprecated in 0.93 and will be removed in 3.0:

| Deprecated API | Replacement |
|----------------|-------------|
| `get_injection_registry()` | `ApplicationContext` |
| `get_service_registry()` | `ApplicationContext.register()` |
| `@service` decorator with auto-inject | Explicit Definition registration |
| `Inject()` / `InjectByName()` | factory with `ctx.get()` |
| `DependencyInjector` | `ApplicationContext` |

## Compatibility Mode

During migration, you can enable compatibility mode (deprecated, will be removed):

```python
from cullinan.core.container import ApplicationContext

ctx = ApplicationContext()
ctx.set_strict_mode(False)  # Allow some legacy behaviors
```

**Warning:** Compatibility mode is for migration only. Always migrate to strict mode before production deployment.

## Testing Migration

Run all 0.93 tests to verify your migration:

```bash
python -m pytest tests/test_ioc_di_v2_*.py -v
```

## Getting Help

- [Dependency Injection Guide](dependency_injection_guide.md)
- [API Reference](api_reference.md)
- [GitHub Issues](https://github.com/your-repo/cullinan/issues)
