title: "Application Lifecycle"
slug: "wiki-lifecycle"
module: ["lifecycle"]
tags: ["wiki", "lifecycle"]
author: "plumeink"
reviewers: []
status: updated
locale: en
translation_pair: "docs/zh/wiki/lifecycle.md"
related_tests: ["tests/core/test_application_model_refactor.py", "tests/integration/test_service_lifecycle_integration.py"]
related_examples: []
estimate_pd: 1.0
last_updated: "2026-05-31T00:00:00Z"
pr_links: []

# Application Lifecycle

Cullinan's lifecycle is now usually driven by the active `Application`, which
assembles and owns an `ApplicationContext` plus a `WebRuntime`.

## Main phases

1. **Discover modules** — `Application.run()` collects the root module graph and owned packages
2. **Assemble runtime** — create an `ApplicationContext` and `WebRuntime` candidate
3. **Validate and warm** — run health checks, `refresh()`, router/dispatcher wiring, and warmup hooks. When `configure(strict_assembly=True)` is set, the declared-but-not-assembled difference is raised as a failure inside `refresh()`; otherwise it is only reported
4. **Activate** — atomically switch the active runtime and begin draining the previous one
5. **Serve requests** — request scope and middleware operate against the request-bound application snapshot
6. **Drain and close** — once in-flight requests finish, the old context shuts down and the runtime closes

## Lifecycle hooks

Managed components may implement:

- `on_post_construct()`
- `on_startup()`
- `on_shutdown()`
- `on_pre_destroy()`

Async variants are supported through `_async` suffixes.

## Ordering

If a component must start or stop before others, implement `get_phase()`. Lower phases execute earlier on startup and later on shutdown.

## Request scope

Request-scoped dependencies are resolved against the current request context.
Adapters bind the active runtime into that request context before dispatch and
release it afterward. During runtime replacement, `Application.current()`
keeps resolving the request-bound snapshot until that request finishes.

## Reload and draining

`Application.reload()` builds a fresh candidate runtime and activates it only
after validation and warmup succeed. The previous runtime moves to
`DRAINING`, keeps serving in-flight requests, and closes only after request
counts reach zero.

## Middleware bridge

Application bootstrap can bridge older middleware registrations into the gateway pipeline so legacy modules continue to participate in request processing while new code uses the unified Web Runtime.

## See also

- [IoC & DI](injection.md)
- [Application Runtime Model](application_runtime.md)
- [Web Runtime Guide](../web_runtime_guide.md)
