title: "cullinan.core"
slug: "modules-core"
module: ["cullinan.core"]
tags: ["api", "module", "core"]
author: "plumeink"
reviewers: []
status: updated
locale: en
translation_pair: "docs/zh/modules/core.md"
related_tests: ["tests/di/test_core_constructor_injection.py", "tests/integration/test_service_lifecycle_integration.py"]
related_examples: []
estimate_pd: 1.5
last_updated: "2026-05-30T00:00:00Z"
pr_links: []

# cullinan.core

`cullinan.core` is the public facade for Cullinan's unified container, lifecycle, and request-context APIs.

## Recommended entrypoints

### Container and definitions

- `ApplicationContext`
- `Definition`
- `ScopeType`
- `get_application_context()`
- `set_application_context()`

### Decorator surface

- `service`
- `controller`
- `component`
- `Inject`
- `InjectByName`
- `Lazy`

### Lifecycle and request context

- `get_lifecycle_manager()`
- `reset_lifecycle_manager()`
- `create_context()`
- `destroy_context()`
- `get_current_context()`
- `set_current_context()`

## Example

```python
from cullinan.core import ApplicationContext, Definition, ScopeType

ctx = ApplicationContext()
ctx.register(Definition(
    name="Clock",
    factory=lambda c: object(),
    scope=ScopeType.SINGLETON,
    source="docs:Clock",
))
ctx.refresh()
clock = ctx.get("Clock")
ctx.shutdown()
```

## Compatibility exports

The following names still exist for backward compatibility, but they are not the primary programming model:

- `injectable`
- `inject_constructor`
- `InjectionRegistry`
- `get_injection_registry()`
- `reset_injection_registry()`

In the current runtime, new code should favor `ApplicationContext` plus decorator-based registration.

## Runtime Module Scanning

The `cullinan.runtime` module provides tools for module discovery and cache management:

### `invalidate_module_cache()`

Clears the cached module scan results. Call this after dynamically installing new packages or importing modules at runtime, so the next `file_list_func()` call re-scans:

```python
from cullinan.runtime import invalidate_module_cache

# After dynamically importing a new plugin package:
invalidate_module_cache()
```

### `get_caller_package(fallback_package=None)`

Determines the package name of the calling module. Uses `sys._getframe()` for performance (with `inspect.stack()` fallback for portability). The `fallback_package` parameter provides a default when caller detection fails — particularly useful in Nuitka/PyInstaller environments:

```python
from cullinan.runtime import get_caller_package

pkg = get_caller_package(fallback_package="myapp")
```

### `list_submodules(package_name)`

Recursively lists all submodules within a package. Uses both `pkgutil.walk_packages` (primary) and filesystem scanning (fallback) to ensure deep subpackages are discovered across different Python versions and packaging modes:

```python
from cullinan.runtime import list_submodules

# Discovers all submodules including deeply nested ones:
modules = list_submodules("myapp")
```

### Configuring Nuitka module lists

When deploying under Nuitka `--onefile` mode, provide an explicit module list via `configure()`:

```python
from cullinan import configure

configure(explicit_modules=["myapp", "myapp.services", "myapp.web"])
```

## See also

- [Dependency Injection Guide](../dependency_injection_guide.md)
- [Architecture](../architecture.md)
