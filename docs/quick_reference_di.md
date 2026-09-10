# Cullinan Dependency Injection Quick Reference

> **Version**: 0.95
> **Author**: Cullinan

> **Quick lookup page:** use this page as a compact DI recipe sheet; use
> [Dependency Injection Guide](dependency_injection_guide.md) for fuller guidance
> and [API Reference](reference/index.md) for symbol lookup.

## Basic Usage

### 1. Define a Service

```python
from cullinan import service

@service
class UserService:
    def __init__(self):
        self.name = "UserService"
    
    def get_user(self, user_id):
        return {"id": user_id, "name": "John"}
```

### 2. Inject Service into Controller

```python
from cullinan import Inject, InjectByName, Lazy, Provider
from cullinan import controller

@controller(url='/api')
class UserController:
    # Method 1: Constructor injection — bare type annotation, zero boilerplate (Recommended)
    user_service: UserService

    # Method 2: Explicit name
    auth_service = InjectByName('AuthService')
    
    # Method 3: Optional dependency — just set to None
    notifier: NotifierService = None

    # Method 4: Lazy lookup
    report_service = Lazy('ReportService')
```

### 3. Use Injected Service

```python
from cullinan import controller, get_api, Path

@controller(url='/api')
class UserController:
    user_service: UserService  # constructor injection

    @get_api(url='/users/{user_id}')
    async def get_user(self, user_id: int = Path()):
        user = self.user_service.get_user(user_id)
        return user
```

## Which injection primitive to use

| Case | Use |
| --- | --- |
| **Simplest, zero boilerplate (Recommended)** | `db: DatabaseService` — constructor injection |
| Type is importable at runtime | `Inject()` |
| `TYPE_CHECKING` / forward reference still maps to one unique target | `Inject()` |
| Type should not be imported at runtime | `InjectByName("Name")` |
| Lookup should happen on first access | `Lazy("Name")` |
| Optional dependency | `notifier: NotifierService = None` or `required=False` |
| Deferred provider object | `Provider[T] = Inject()` |
| Multiple implementations of one contract | `list[T] = Inject()` / `set[T] = Inject()` / `tuple[T, ...] = Inject()` |

## `TYPE_CHECKING` rule

`Inject()` now supports `TYPE_CHECKING` forward references when the binding result is unique:

```python
from typing import TYPE_CHECKING
from cullinan import Inject, Provider

if TYPE_CHECKING:
    from .contracts import Hook
    from .providers import DatabaseSessionProvider

class Repo:
    session_provider: Provider["DatabaseSessionProvider"] = Inject()
    hooks: list["Hook"] = Inject(required=False)
```

Startup still fails fast when:

- the annotation is ambiguous, such as `Union[A, B]` with multiple live candidates
- the combination is unsupported, such as `list[Union[A, B]]`
- the framework would need name guessing instead of exact resolution

## Packaging Configuration

### Using an Entry Method (Recommended)

```python
from cullinan import application, configure

# user_packages triggers automatic module discovery — no manual
# component imports needed. The framework scans and registers all
# @service / @controller / @component classes under my_app.
@configure(user_packages=["my_app"])
@application
def main(): ...

main()
```

Use `@module` only when the application needs an explicit advanced runtime boundary such as package ownership or hot-pluggable module structure.

### PyInstaller Configuration

```python
# your_app.spec
hiddenimports=[
    'my_app.service.user_service',
    'my_app.service.auth_service',
],
datas=[
    ('my_app', 'my_app'),
],
```

### Nuitka Configuration

```bash
nuitka --include-package=my_app \
       --include-module=my_app.service.user_service \
       your_app.py
```

## Troubleshooting

| Problem | Solution |
|---------|----------|
| Dependency is None | Ensure service uses `@service` decorator |
| Service not found | Check service name matches (case-sensitive) |
| Circular dependency or runtime-only import edge | Use `InjectByName()` or `Lazy("Name")` |
| `DependencyTypeResolutionError` | Annotation is ambiguous, unsupported, or cannot be normalized safely; narrow the type contract or use `InjectByName()` |
| Injection not working | Ensure the component is registered with `@service` / `@controller` and available to `ApplicationContext` |

## See Also

- [Dependency Injection Guide](dependency_injection_guide.md) - Complete DI documentation
- [Architecture](architecture.md) - System architecture overview
- [Migration Guide](migration_guide.md) - Migration from older versions
