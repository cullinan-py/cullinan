title: "Framework Semantics"
slug: "framework-semantics"
tags: ["guide", "semantics", "diagnostics"]
author: "Cullinan"
reviewers: []
status: updated
locale: en
translation_pair: "docs/zh/framework_semantics.md"
related_tests: ["tests/regression/test_component_reliability.py", "tests/core/test_injection_annotation_parsing.py"]
related_examples: []
estimate_pd: 1.0
last_updated: "2026-06-01T00:00:00Z"
pr_links: []

# Framework Semantics

This page defines the runtime semantics Cullinan **guarantees**, the behaviors it only keeps for compatibility, and the situations that now produce warnings or startup failures. The goal is to make Cullinan's runtime model legible: decorator-first business code, import-executed discovery, and explicit runtime boundaries when you need them.

> **Read next:** [Architecture](architecture.md), [Engineering Practices](how-to/index.md)  
> **Lookup instead of explanation?** Go to [API Reference](reference/index.md).

## Recommended semantic package path

Cullinan's default semantic path is now:

- `cullinan` for application startup (`@application`, `configure`)
- `cullinan.application` for advanced application semantics such as `Application` and `module`
- `cullinan.web` for controllers, route decorators, request/response, parameters, and middleware
- `cullinan.core` for IoC/DI, lifecycle, and semantic diagnostics

Lower-level layers such as `cullinan.runtime`, `cullinan.transport`, and `cullinan.support` remain available, but they are not the default onboarding path for normal business applications.

This also means the default semantic path is **not** "learn Tornado first, then learn Cullinan". Tornado and ASGI are execution backends behind the framework boundary; the primary contract for application code is Cullinan's own Web and application semantics.

## 1. Component discovery is import-executed, not static AST scanning or app-object registration

Cullinan discovers decorated components by **importing Python modules** and letting decorators execute.

- guaranteed: module-top-level `@service`, `@controller`, `@component`, and `@provider` definitions that execute during module import
- not guaranteed: classes defined inside functions, factories, branches, or other local scopes that only run later

```python
from cullinan.core import component


@component
class TopLevelCache:
    pass


def build_repository():
    @component
    class LocalRepository:
        pass

    return LocalRepository
```

`TopLevelCache` is in the supported discovery path. `LocalRepository` is not part of the automatic top-level discovery contract; Cullinan now emits a warning for this pattern, and if it happens after `refresh()` it fails fast. If a package needs stronger ownership, reload, or hot-pluggable runtime guarantees, express that boundary with `@module` rather than falling back to manual app registration.

## 2. `Inject()` is a strict type contract

`Inject()` only succeeds when Cullinan can normalize the annotation into a **stable and unique** dependency contract.

Supported examples include:

- `T`
- `"T"`
- `Optional[T]`
- `Annotated[T, ...]`
- `Final[T]`
- `Provider[T]`
- `list[T]`, `set[T]`, `tuple[T, ...]`
- `Union[A, B]` / `A | B` when only one candidate is bindable

Cullinan does **not** fall back to attribute-name guessing anymore. If the annotation is missing, unsupported, or ambiguous, startup fails with a typed diagnostic.

## 3. `InjectByName()` is explicit-name semantics

`InjectByName()` resolves by component name, not by type.

Recommended form:

```python
from cullinan.core import InjectByName


class ReportController:
    report_service: "ReportService" = InjectByName("ReportService")
```

Compatibility form:

```python
class ReportController:
    report_service = InjectByName()
```

The compatibility form still falls back to the attribute name, but Cullinan now warns because the binding becomes easier to break during refactors. Even with name-based injection, keeping a real type annotation is recommended for readability and static analysis.

## 4. Lifecycle registration freezes after `refresh()`

`ApplicationContext.refresh()` is the structural boundary:

- pending decorator registrations are drained and registered
- definitions are validated and warmed
- registries are frozen

After that point, adding new decorated classes is no longer a supported runtime mutation path. Cullinan now surfaces a semantic error that explains the rule and the fix.

**`PendingRegistry.clear()` consistency**: As of v0.93a10, `clear()` on a frozen registry also raises `RuntimeError` — matching the behavior of `add()`. Use `PendingRegistry.reset()` in test teardown to fully reset the registry including the frozen state.

## 5. Scope rules are enforced, not best-effort

Cullinan treats scope compatibility as a hard rule. In particular, a `singleton` component cannot directly depend on a `request` scoped component. This now produces structured lifecycle diagnostics instead of failing later in an unpredictable way.

**Transitive enforcement**: The scope check now recurses through the full dependency chain — both explicit `dependencies=[...]` declarations and field injection markers (`Inject()`, `InjectByName()`). A singleton depending on another singleton that transitively requires a request-scoped object is detected and rejected at `refresh()`, with the full chain reported in the error message.

**Structured scope violations (v0.95a1)**: Scope violations now raise `ScopeViolationError` (a subclass of `LifecycleError`) which carries three diagnostic fields:

- `dependency_chain`: the ordered list of component names from the origin singleton to the violating request-scoped component (inclusive).
- `origin_name`: the name of the root component whose scope was violated.
- `violating_component`: the name of the request-scoped component that was reached transitively.

The `format_scope_violation_error()` helper in `cullinan.core.diagnostics` renders a human-readable chain description. Because `ScopeViolationError` inherits from `LifecycleError`, existing `except LifecycleError` handlers continue to work.

**Performance (v0.95a1)**: The transitive scope validator uses cross-origin memoization (`verified_safe` set) so each component subgraph is fully traversed at most once across all origins, reducing worst-case complexity from O(N²×M) to O(N+E). The `get_injection_markers()` scanner is also cached per class via a `WeakKeyDictionary`, avoiding repeated `dir()` scans.

## 6. Injection visibility and private conventions (v0.95a1)

The injection marker scanner (`get_injection_markers`) scans class attributes for `Inject`, `InjectByName`, and `Lazy` markers. As of v0.93a11 (commit c888738, constructor injection feature), single-underscore-prefixed attributes (`_xxx`) are **visible** to the injection system - only dunder attributes (`__xxx__`) are skipped. This is an intentional design decision: constructor injection needs to scan class-level bare type annotations, and filtering all `_`-prefixed attributes would miss `_internal_db: DatabaseService`-style private injection points.

This does **not** conflict with the "underscore = private" convention in [[公共 API 暴露准则]] §3, which constrains the private-ness of **framework-exported symbols** (i.e. users should not `from cullinan import _internal_helper`). The injection scanner operates on **user-defined class attributes**, which is a different layer.

For projects that want strict private semantics (single-underscore attributes skipped), `ApplicationContext` accepts a `strict_private_injection` opt-out switch:

```python
ctx = ApplicationContext(strict_private_injection=True)
```

The `CULLINAN_STRICT_PRIVATE_INJECTION=1` environment variable provides a global opt-in (useful for CI / strict projects). The default (`False`) preserves the v0.93a11+ behavior.

## 7. Lifecycle exception propagation (v0.95a1)

`ApplicationContext` (the v0.94 main lifecycle path) distinguishes critical and non-critical lifecycle hooks:

| Hook | Default failure behavior | Rationale |
|------|-------------------------|-----------|
| `on_post_construct` / `on_post_construct_async` | **Raise** `LifecycleError` | Component state inconsistent, cannot continue initialization |
| `on_pre_destroy` / `on_pre_destroy_async` | **Raise** `LifecycleError` | Resource cleanup failure may cause leaks |
| `on_startup` / `on_startup_async` | **Log and swallow** | Avoid cascading failures, allow partial startup |
| `on_shutdown` / `on_shutdown_async` | **Log and swallow** | Best-effort shutdown, avoid disrupting other components' cleanup |

All raised exceptions use `raise LifecycleError(...) from exc` to preserve the `__cause__` chain per [[错误码与异常分级规范]] §3.

For projects that want all lifecycle failures to propagate (aligning with `LifecycleManager`'s `force=False` behavior), `ApplicationContext` accepts a `strict_lifecycle` switch:

```python
ctx = ApplicationContext(strict_lifecycle=True)
```

When enabled, `on_startup` / `on_shutdown` failures also raise `LifecycleError`. The default (`False`) preserves the v0.94 behavior. The legacy `LifecycleManager` path is intentionally **not** modified; its behavior remains unchanged for existing direct users.

## 8. Compatibility APIs are deprecated (v0.95a1)

Legacy surfaces such as `@injectable`, `@inject_constructor`, `InjectionRegistry`, `get_injection_registry()`, and `reset_injection_registry()` remain available so older code can still import them, but they are **deprecated since v0.95** and will be **removed in v0.97**.

As of v0.95a1, these symbols carry:

- `@deprecated` decorator emitting standard `DeprecationWarning` (tool-chain visible via `pytest -W error::DeprecationWarning`, linters, IDEs).
- `__deprecated__ = True` and `__deprecated_info__ = {version, alternative, removal_version}` metadata for programmatic detection.
- The existing `CompatibilitySemanticWarning` (via `warn_semantic_once`) continues to fire as a deduplicated semantic reminder.

**Migration**:

| Deprecated symbol | Replacement |
|-------------------|-------------|
| `@injectable` | `@service` / `@component` / `@controller` (classes are auto-injectable) |
| `@inject_constructor` | `ApplicationContext.refresh()` (handles constructor injection uniformly) |
| `InjectionRegistry` | `ApplicationContext` / `get_application_context()` |
| `get_injection_registry()` | `ApplicationContext` / `get_application_context()` |
| `reset_injection_registry()` | Create a new `ApplicationContext` explicitly |

## 9. How to read warnings and errors

Cullinan now formats key diagnostics as:

- **Semantic rule**: the contract the framework enforces
- **Current problem**: what the runtime observed
- **Suggestion**: the safest supported fix

When the framework can prove a core semantic violation, startup fails. When code is still technically runnable but likely misleading, Cullinan emits a warning instead.

## 10. Module discovery in compiled environments

When Cullinan runs under Nuitka or PyInstaller, standard `pkgutil.walk_packages` may not find all user modules — especially in `--onefile` mode where the filesystem layout differs from development.

**`explicit_modules` configuration**: You can provide an explicit module list to `configure()`:

```python
from cullinan import configure

configure(explicit_modules=[
    "myapp",
    "myapp.services",
    "myapp.web",
])
```

This list is used as the highest-priority strategy (S0) in the unified scan pipeline, before falling back to `user_packages` (S1) and other heuristics. Each entry is recursively walked for subpackages.

**Deep subpackage discovery**: `list_submodules()` now supplements `pkgutil.walk_packages` with filesystem-based recursive scanning. If a deeply nested package (e.g., `club.fnep.infrastructure.discord`) is missed by `walk_packages`, the filesystem fallback discovers it by walking `__init__.py` directories and `.py` files directly.
