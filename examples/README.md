# Cullinan Examples

This directory is the single source of runnable examples for the current Cullinan public API.

## Recommended order

1. `examples/minimal_app/`
2. `examples/controller_service_inject/`
3. `examples/middleware_and_module/`
4. `examples/middleware_pipeline/`
5. `examples/middleware_control/`
6. `examples/middleware_ownership/`
7. `examples/parameter_handling/`
8. `examples/testing_flow/`
9. `examples/static_files_and_spa/`
10. `examples/component_discovery_boundary/` — advanced / boundary
11. `examples/assembly_snapshot/` — advanced / boundary

## Run examples

- `python -m examples.minimal_app`
- `python -m examples.controller_service_inject`
- `python -m examples.middleware_and_module`
- `python -m examples.middleware_pipeline`
- `python -m examples.middleware_control`
- `python -m examples.middleware_ownership`
- `python -m examples.parameter_handling`
- `python -m pytest examples/testing_flow/test_app.py -q`
- `python -m examples.static_files_and_spa`
- `python -m examples.component_discovery_boundary`
- `python -m examples.assembly_snapshot`

Each example keeps one teaching goal and follows the recommended Cullinan path:
entry-method startup with `@application`, optional `@configure(...)`,
decorator-first business code, and `Inject()` for type-led injection.

The examples are intentionally engine-neutral at the application layer: business
code targets Cullinan semantics first, while the framework decides whether to
bridge into ASGI or Tornado at runtime.

The maintained examples also stay inside the frozen public export boundary:
top-level `cullinan` for regular application code, and entry-method-bound helpers
such as `main.get_asgi_app()` when a test/demo needs runtime access without
teaching `cullinan.run` as a top-level import.

The **recommended entry form is a method**: `@application` + `@configure(...)` +
`main()` (run with `python -m examples.<name>`). Recommended examples never teach
`cullinan.application.Application` as the default entry. A few examples
(`component_discovery_boundary`, `assembly_snapshot`) do construct the advanced
entry class directly, because they need the application *object* without starting
a server; those are marked **advanced / boundary** here and in their own READMEs,
and their construction of the advanced entry class is explicitly labelled as
such.

Historical compatibility demos live under `examples/legacy/` and are not part of
the maintained default learning path. Only `decorator_demo_090.py` remains —
other legacy demos were cleaned up when their referenced APIs (`cullinan.run`,
`cullinan.core.provider`) were removed.

## Middleware examples

Four maintained examples cover middleware, with different teaching goals:

- `examples/middleware_pipeline/` — the **recommended** onion protocol
  (`async __call__(request, call_next)`), declared through
  `@configure(middlewares=[...])` with explicit order controls.
- `examples/middleware_control/` — replacing/switching off the **built-in**
  middleware layer through `@configure(builtin_middleware=[...])`, and letting a
  legacy `@middleware(priority=...)` class join the same declarative ordering.
- `examples/middleware_ownership/` — the two declaration forms side by side:
  a `@component` class entry (container-managed, dependencies injected) and an
  instance entry (externally-owned).
- `examples/middleware_and_module/` — the **compatibility** protocol
  (`process_request` / `process_response`), still auto-bridged into the same
  gateway pipeline.

## Advanced extension demos

- `examples/extension_registration_demo.py` — maintained advanced demo for extension discovery and middleware registration
