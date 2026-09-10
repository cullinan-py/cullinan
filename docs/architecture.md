# Cullinan Framework Architecture

> **Version**: 0.95
> **Last Updated**: 2026-06-01  
> **Status**: Updated

> **This page explains framework structure, not the default startup tutorial.**  
> Start from [Application Build](start/index.md) for the recommended bootstrap path,
> and use [Internals & Extensions](internals/index.md) when you intentionally need deeper runtime details.

## Overview

Cullinan is an engine-neutral application framework whose current runtime is organized around three consolidated pillars:

1. **Unified container facade** — `cullinan.core` is the public IoC/DI entrypoint.
2. **Transport-agnostic Web Runtime** — `cullinan.web.gateway` owns `WebRequest`, `WebResponse`, routing, dispatch, middleware, and exception handling.
3. **Decorator-first runtime assembly** — application code starts from business decorators, while runtime ownership and hot-pluggable stability are layered in when needed.

## Architecture layers

```text
Application code
├── @service / @controller / @component
├── Controller methods with get_api/post_api/...
└── Business services and middleware

Framework facade
├── cullinan             -> @application, configure, business-facing decorators
├── cullinan.application -> Application, run/get_asgi_app, @module
├── cullinan.web         -> controller decorators, WebRequest/WebResponse, params, middleware
├── cullinan.core        -> ApplicationContext, scopes, lifecycle, request context
├── cullinan.testing     -> testing helpers and verification entrypoints
├── cullinan.runtime     -> discovery, scanning, runtime assembly
└── cullinan.transport   -> WebAdapter, TornadoAdapter, ASGIAdapter

Runtime execution
├── Decorator declarations -> import-executed discovery -> runtime assembly
├── ApplicationContext.refresh()
├── Gateway pipeline + dispatcher
├── Adapter-specific request/response translation
└── ApplicationContext.shutdown()
```

## Semantic package surface

Cullinan's recommended package surface now follows a clearer framework-semantic split:

- `cullinan` — default startup surface (`@application`, `configure`, then call the entry method)
- `cullinan.application` — advanced application semantics such as application definition, runtime boundary, and explicit runtime helpers
- `cullinan.web` — business-facing Web development surface
- `cullinan.core` — IoC/DI, lifecycle, request context, semantic diagnostics
- `cullinan.testing` — test-facing support
- `cullinan.runtime` — discovery, scanning, and runtime assembly internals
- `cullinan.transport` — server adapter boundary
- `cullinan.support` — constrained support utilities, not a default first-read surface

This split keeps the default path business-first while still giving maintainers and advanced users explicit lower-level layers. Historical root-level wrappers such as `cullinan.app` or `cullinan.public_api` are no longer part of the maintained structure.

## Core container model

`cullinan.core` exposes the public container API. `ApplicationContext` is the single runtime entrypoint for registration, resolution, refresh, and shutdown.

### Main responsibilities

- Register dependency definitions
- Resolve singleton / prototype / request-scoped instances
- Drive lifecycle hooks during `refresh()` and `shutdown()`
- Hold the active application context used by framework integrations

### Public flow

```python
from cullinan.core import ApplicationContext, set_application_context

ctx = ApplicationContext()
set_application_context(ctx)

# new application code starts from decorators and runtime assembly;
# explicit Definition registration is reserved for low-level integration
ctx.refresh()
...
ctx.shutdown()
```

Legacy `cullinan.core.container.*` modules remain as thin forwards. They are no longer separate stateful entrypoints.

## Dependency injection and lifecycle

The decorator layer (`@service`, `@controller`, `Inject`, `InjectByName`) feeds the unified container model.

### Recommended usage

- Use `@service` and `@controller` for normal application code
- Use `Inject()` for type-safe field injection
- Use `InjectByName()` when name-based resolution is clearer or avoids circular imports
- Use `ApplicationContext` directly for custom factories or third-party integration

### Lifecycle hooks

All managed components participate in the same lifecycle contract:

- `on_post_construct()`
- `on_startup()`
- `on_shutdown()`
- `on_pre_destroy()`

Async hook variants with `_async` are supported. Ordering can be influenced with `get_phase()`.

## Web Runtime

The current web stack is centered on `cullinan.web.gateway.web_core`, but the recommended business-facing entry now goes through `cullinan.web`.

### Public runtime objects

- `WebRequest` — normalized request object
- `WebResponse` — mutable response builder that can be frozen before writing
- `Router` — route registration and matching
- `Dispatcher` — request dispatch and return-value handling
- `MiddlewarePipeline` — onion-style middleware composition
- `ExceptionHandler` — exception-to-response conversion
- `WebRuntime` — active runtime state and runtime switching

### Adapter boundary

Server integration lives behind `cullinan.transport` and its underlying `cullinan.transport.adapter` implementation:

- `WebAdapter` — common adapter contract
- `TornadoAdapter` — Tornado integration
- `ASGIAdapter` — ASGI integration

This split keeps request processing logic independent from any single server implementation.

## Request flow

1. Business code declares services, controllers, and handlers with decorators.
2. Runtime assembly imports owned Python modules and rebuilds registrations from decorator metadata.
3. `ApplicationContext.refresh()` resolves eager components and runs startup hooks.
4. The gateway pipeline receives a transport-normalized `WebRequest`.
5. `Dispatcher` matches a route, resolves parameters, invokes the handler, and produces a `WebResponse`.
6. A concrete adapter writes the response back to Tornado or ASGI.

Cullinan's default developer story is now **framework semantics first, runtime backend second**: application code targets Cullinan's request/response, controller, parameter, middleware, and lifecycle model, while Tornado and ASGI sit behind the adapter boundary as execution backends.
7. Shutdown calls `ctx.shutdown()` and drains managed lifecycle hooks.

## Testing strategy

The repository uses pytest as the single supported test runner.

- Formal repository command: `.venv\Scripts\python -m pytest`
- Shared test bootstrap lives in `tests/conftest.py`
- Test layout is topic-based: `tests/core`, `tests/di`, `tests/web`, `tests/integration`, `tests/regression`, `tests/compat`

See [Testing & Verification](testing.md) for the current workflow.

## Related documents

- [Runtime consolidation overview](runtime_updates_v093.md)
- [Dependency Injection Guide](dependency_injection_guide.md)
- [Web Runtime Guide](web_runtime_guide.md)
- [Testing & Verification](testing.md)
