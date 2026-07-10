title: "Application Runtime Model"
slug: "wiki-application-runtime"
module: ["cullinan.application"]
tags: ["wiki", "application", "runtime", "module"]
author: "Cullinan"
reviewers: []
status: updated
locale: en
translation_pair: "docs/zh/wiki/application_runtime.md"
related_tests: ["tests/core/test_application_model_refactor.py", "tests/core/test_decorators.py", "tests/integration/test_adapter_integration.py"]
related_examples: []
estimate_pd: 1.0
last_updated: "2026-05-31T00:00:00Z"
pr_links: []

# Application Runtime Model

This page explains the advanced runtime model built around
`cullinan.application`.
Cullinan's intended experience is decorator-first business development: the
runtime assembles what your modules declare, instead of asking you to wire a
manual app object step by step.

> **Advanced topic:** regular applications should prefer `@application` + `@configure(...)` + `main()`.  
> **Reference companion:** see [API Reference](../api_reference.md) for the public / advanced / compatibility API split.

For regular applications, prefer `@application` + `@configure(...)` + `main()`.
Reach for `cullinan.application` only when you intentionally need explicit
runtime orchestration.

For the runtime contracts that now fail fast or warn, see [Framework Semantics](../framework_semantics.md). In particular, `Application.run()` assumes component decorators have already executed during module import, and `refresh()` marks the end of structural registration.

## Core concepts

- `Application` owns one root module graph, one `ApplicationContext`, and one `WebRuntime`
- `@module` declares a structured boundary for owned Python packages, reload, draining, and hot-pluggable runtime behavior
- `Runtime` is the mutable record for a validated / warmed application candidate
- `Application.current()` resolves the active application and prefers the request-bound snapshot during draining

## Typical runtime assembly

```python
from cullinan import controller, get_api, module, service
from cullinan.application import Application


@service
class GreetingService:
    def greet(self) -> str:
        return "hello"


@controller(url="/api")
class GreetingController:
    greeting_service: GreetingService  # constructor injection

    @get_api(url="/whoami")
    def whoami(self):
        return {"message": self.greeting_service.greet()}


@module
class RootModule:
    pass


app = Application.run(RootModule)
```

`RootModule` in the example is only a placeholder class name. `Application.run()`
accepts any class you declare with `@module` as the root module.

## Module graph and ownership

Each module contributes:

- `imports` — child or sibling modules included in the root graph
- `packages` — Python package prefixes owned by that module
- `ownership_overrides` — explicit ownership for intentionally shared packages
- `warmup` / `health_checks` — hooks that run during build and validation

Component ownership is resolved from decorator metadata captured on
`@service`, `@controller`, `@component`, and `@provider`. If the same component
matches multiple module package prefixes at the same depth, startup fails until
you provide `ownership_overrides`.

## Build and activation flow

`Application.run()` performs these stages:

1. Discover runtime boundaries and import owned Python modules.
2. Rebuild pending registrations from decorator metadata.
3. Assemble an `ApplicationContext` and `WebRuntime`.
4. Validate, refresh, and warm the runtime.
5. Atomically bind the new application as active.

## Reload and draining

`Application.reload()` creates a fresh application candidate from the same root
module. If activation succeeds:

1. the new runtime becomes active immediately
2. the previous runtime enters `DRAINING`
3. in-flight requests keep their request-bound app snapshot
4. the old runtime closes only after request counts drop to zero

This is why `Application.current()` may resolve an older application inside a draining
request even after a newer runtime is already active globally.

## Adapters and request binding

The transport adapters (`ASGIAdapter` / `TornadoAdapter`) bind the runtime into
the current request context before dispatch. That request binding enables:

- request-scoped dependency resolution against the correct application
- `Application.current()` inside runtime-aware controllers or middleware
- safe draining while older requests are still finishing

For normal business applications, this stays an internal transport concern; the
recommended entrypoint remains Cullinan's application and controller semantics.

## When to use ApplicationContext directly

Keep using `ApplicationContext` directly when you need low-level container
integration. For new application code, start from decorators and use
`Application` plus `@module` when you need explicit runtime boundaries.

## Related documents

- [cullinan.application module](../modules/application.md)
- [Application Lifecycle](lifecycle.md)
- [Components](components.md)
