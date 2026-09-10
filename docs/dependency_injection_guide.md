# Cullinan Dependency Injection Guide

> **Version**: 0.95
> **Last Updated**: 2026-06-01  
> **Status**: Updated

## Overview

Cullinan's current DI model is centered on `ApplicationContext` and exposed publicly through `cullinan`. Decorators remain the recommended authoring surface, while legacy registry-style APIs are kept only for compatibility.

Before choosing an injection primitive, read [Framework Semantics](framework_semantics.md). That page defines the hard rules behind `Inject()`, `InjectByName()`, `refresh()`, and compatibility APIs.

> **Recommended default:** constructor injection — declare a bare type annotation on a class-level attribute and the framework resolves it automatically. Zero boilerplate: no `Inject()`, no `__init__`, no `self.x = x`.  
> **Need symbol lookup instead of guidance?** See [API Reference](reference/index.md).

## Recommended usage

### 1. Register services with decorators

```python
from cullinan import service

@service
class DatabaseService:
    def query(self, sql: str):
        return {"sql": sql}

@service
class UserService:
    database: DatabaseService  # constructor injection — bare annotation

    def get_user(self, user_id: int):
        return self.database.query(f"select * from users where id = {user_id}")
```

### 2. Use the same injection model in controllers

```python
from cullinan import controller, get_api, Path

@controller(url="/users")
class UserController:
    user_service: UserService  # constructor injection

    @get_api(url="/{user_id}")
    async def get_user(self, user_id: int = Path()):
        return self.user_service.get_user(user_id)
```

## Injection primitives

### Constructor injection — preferred (zero boilerplate, framework-enforced immutability)

The cleanest injection style: a bare class-level type annotation is a DI declaration.
No `Inject()` marker, no `__init__`, no `self.x = x` assignment.

```python
from cullinan.core import service

@service
class UserService:
    database: DatabaseService       # required — error at refresh() if missing
    cache: CacheService             # same
    notifier: NotifierService = None  # optional — stays None if not registered
```

**Rules**:

- No default `db: DatabaseService` → **required** DI, `DependencyNotFoundError` at `refresh()`
- `None` default `notifier: NotifierService = None` → **optional** DI, injected if available
- Actual value `timeout: int = 5` → ignored by the framework
- `Inject()` / `Lazy()` marker → field injection path, unaffected by constructor injection

**Contrast with field injection**:

| Contrast | field injection (`Inject()`) | constructor injection |
|----------|------------------------------|-----------------------|
| Boilerplate | `x: T = Inject()` | `x: T` |
| Startup check | `required=False` defers to runtime | required deps fail at `refresh()` |
| Immutability after injection | enforced (all injection paths) | enforced (all injection paths) |
| Test mock | `Inject()` blocks direct `cls()` | `svc = cls(); svc.db = mock` (no freeze) |

**Advantages**:

- Zero boilerplate
- Missing required dependencies caught early at startup
- Injected attributes are enforced as read-only after injection
- Test-friendly: instantiate directly and inject mocks manually

> **Backward-compatible**: existing `Inject()` / `Lazy()` / `InjectByName()` work unchanged.
> Constructor and field injection can coexist on the same class.

### `Inject()` — field injection (type-driven)

Use `Inject()` for explicit field injection when the runtime type is available and you want
refactoring-friendly, type-driven wiring.

```python
from cullinan.core import Inject

class AuditService:
    repo: Repository = Inject()
    cache: CacheService = Inject(required=False)
```

`Inject()` uses a strict, typed resolution pipeline:

- direct runtime types still work as before
- `TYPE_CHECKING` + forward references are supported when Cullinan can map the annotation to a **single** registered target
- common wrappers such as `Optional[T]`, `Annotated[T, ...]`, `Final[T]`, `Provider[T]`, `list[T]`, `set[T]`, `tuple[T, ...]`, and `Union[A, B]` are supported
- Cullinan still refuses attribute-name guesses such as `session_provider -> SessionProvider`
- if the annotation is ambiguous or cannot be normalized safely, startup fails with `DependencyTypeResolutionError`

Use it when you want typed wiring and the annotation can be normalized into a unique dependency contract.

### `InjectByName()` — name-based fallback

Use `InjectByName()` when the dependency is more naturally resolved by name or when importing the type would create an undesirable dependency edge.

```python
from cullinan.core import InjectByName

class ReportController:
    report_service = InjectByName("ReportService")
```

Cullinan now treats `InjectByName("ExactComponentName")` as the recommended form. `InjectByName()` without an explicit name is kept only as a compatibility fallback and now emits a warning.

This is the correct choice when you intentionally do **not** want to import the target type at runtime.

### `Lazy()` — deferred lookup

Use `Lazy()` when the dependency should be resolved on first access rather than during eager instance wiring.

```python
from cullinan.core import Lazy

class AuditService:
    report_service = Lazy("ReportService")
```

`Lazy()` follows the same naming rules as `Inject()` / `InjectByName()`:

- prefer an explicit name when you want late lookup without importing the target type
- if you rely on type-driven resolution, the type still needs to be resolvable at runtime

## How to choose

| Need | Recommended primitive |
| --- | --- |
| **New projects: cleanest, framework-enforced immutability** | constructor injection `db: DatabaseService` |
| Runtime type is available and you want refactor-friendly injection | `Inject()` |
| `TYPE_CHECKING` / forward-reference type is unique and still should be type-driven | `Inject()` |
| Runtime type is intentionally unavailable or awkward to import | `InjectByName("Name")` |
| Lookup should be deferred until first use | `Lazy("Name")` or `Lazy()` with a runtime-resolvable type |
| Optional dependency | `notifier: NotifierService = None` or `Inject(required=False)` |
| Deferred provider object | `Inject()` with `Provider[T]` |
| Multiple implementations of one contract | `Inject()` with `list[T]`, `set[T]`, or `tuple[T, ...]` |

## `TYPE_CHECKING` and forward-reference rules

`Inject()` can now work with `TYPE_CHECKING` and forward references, but only when the final binding is still uniquely decidable.

### Supported: single target forward reference

```python
from typing import TYPE_CHECKING

from cullinan.core import Inject, service

if TYPE_CHECKING:
    from .providers import DatabaseSessionProvider

@service
class ChannelBindingRepository:
    session_provider: "DatabaseSessionProvider" = Inject()
```

As long as `DatabaseSessionProvider` is the only matching registered component, startup succeeds.

### Supported wrappers

```python
from typing import TYPE_CHECKING, Optional

from cullinan.core import Inject, Provider, service

if TYPE_CHECKING:
    from .contracts import Hook
    from .providers import DatabaseSessionProvider, PrimarySessionProvider, SecondarySessionProvider

@service
class ChannelBindingRepository:
    session_provider: Provider["DatabaseSessionProvider"] = Inject()
    hooks: list["Hook"] = Inject(required=False)
    fallback_cache: Optional["CacheService"] = Inject()
    preferred_provider: "PrimarySessionProvider | SecondarySessionProvider" = Inject()
```

Rules:

- `Optional[T]` allows `None` when `T` is missing
- `Provider[T]` injects a deferred provider object instead of `T` directly
- collection wrappers inject all matching implementations
- `Union[A, B]` works only when exactly one branch is bindable

### Still rejected: ambiguous or unsupported combinations

- multiple `Union` branches are available at the same time
- nested combinations such as `list[Union[A, B]]`
- anything that would require fuzzy guessing or attribute-name fallback

Use `InjectByName("Name")` or `Lazy("Name")` when you intentionally want explicit, name-based control.

## ApplicationContext as the single container entrypoint

Decorator-based registration covers most application code. For advanced integration, use `ApplicationContext` directly.

```python
from cullinan.core import ApplicationContext, Definition, ScopeType

ctx = ApplicationContext()
ctx.register(Definition(
    name="CustomService",
    factory=lambda c: CustomService(),
    scope=ScopeType.SINGLETON,
    source="custom:CustomService",
))
ctx.refresh()
service = ctx.get("CustomService")
```

`cullinan.core.container.*` paths are compatibility forwards to the same public container API.

## Lifecycle integration

DI and lifecycle are part of the same runtime model. Managed components can implement:

- `on_post_construct()`
- `on_startup()`
- `on_shutdown()`
- `on_pre_destroy()`

Async variants with `_async` are also supported. Use `get_phase()` if startup/shutdown ordering matters.

### Lifecycle error propagation

Critical lifecycle phases propagate failures to prevent components from running in an inconsistent state:

- **`on_post_construct`** and **`on_pre_destroy`**: exceptions are re-raised as `LifecycleError`. A failed `on_post_construct` means the component is not ready and should not be served.
- **`on_startup`** and **`on_shutdown`**: exceptions are logged as errors but do **not** halt the container. This avoids a single component's startup failure from cascading to unrelated components.

Controller route registration failures are also re-raised as `LifecycleError` — a controller whose routes cannot be registered is a hard startup error.

## Scope validation

### Transitive scope enforcement

Cullinan validates that a longer-lived component never depends on a shorter-lived component — even transitively through a chain of dependencies. This prevents runtime bugs where a singleton holds a stale reference to a request-scoped object.

The validation recurses through:
1. **Explicit dependencies** declared via `@service(dependencies=[...])`.
2. **Field injection markers** (`Inject()`, `InjectByName()`, `Lazy()`) on the class.

Example of a violation:
```python
@service(scope="singleton")
class SingletonA:
    dep: "SingletonB" = Inject()        # → SingletonB (singleton) ✓
                                         #   → RequestC (request)   ✗ transitive violation
```

The error message identifies the full chain: `SingletonA → SingletonB → RequestC`.

### Injection marker filtering

Only Python dunder attributes (`__init__`, `__repr__`, etc.) are automatically excluded from injection scanning. Single-underscore-prefixed attributes like `_cache` or `_connection` are **now** visible to the injection system if they carry an `Inject()` marker. This change (v0.93a10+) ensures that "private by convention" fields are not silently ignored.

## Compatibility notes

Cullinan still exports some legacy names, but they should not be used as the primary programming model:

- `injectable` is currently a **no-op compatibility decorator**
- `inject_constructor` is currently a **no-op compatibility decorator**
- `get_injection_registry()` currently returns `None`
- `reset_injection_registry()` is a safe compatibility no-op

Those names are kept so older code paths fail less abruptly, but new code should rely on `@service`, `@controller`, `Inject`, `InjectByName`, and `ApplicationContext`.

## Troubleshooting

| Problem | What to check |
| --- | --- |
| Dependency cannot be resolved | Confirm the type or dependency name matches the registered component |
| `DependencyTypeResolutionError` on startup | The annotation is ambiguous, unsupported, or cannot be normalized safely; narrow the type contract or switch to `InjectByName()` / `Lazy("Name")` |
| Optional dependency is missing | Use `required=False` and handle `None` explicitly |
| Lifecycle hooks do not run | Ensure the component is managed and `ApplicationContext.refresh()` has executed |
| Advanced registration behaves differently than expected | Verify the `Definition` scope and factory source |
| `_` prefixed injection fields are not resolved | As of v0.93a10, only `__dunder__` attributes are excluded. Ensure the field has a type annotation and the dependency is registered |

## Related documents

- [Architecture](architecture.md)
- [Runtime consolidation overview](runtime_updates_v093.md)
- [IoC & DI wiki](wiki/injection.md)
- [Application Lifecycle](wiki/lifecycle.md)
