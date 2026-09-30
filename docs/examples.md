title: "Examples and Guidance"
slug: "examples"
module: []
tags: ["examples"]
author: "plumeink"
reviewers: []
status: updated
locale: en
translation_pair: "docs/zh/examples.md"
related_tests: ["tests/integration/test_examples_public_guides.py"]
related_examples: ["examples/minimal_app", "examples/controller_service_inject", "examples/middleware_and_module", "examples/middleware_pipeline", "examples/middleware_control", "examples/parameter_handling", "examples/testing_flow"]
estimate_pd: 1.5
last_updated: "2026-06-01T00:00:00Z"
pr_links: []

# Examples and Guidance

This page is the canonical guide to the runnable examples maintained in the repository.
The source of truth is now the root `examples/` directory, not `docs/examples/` and not
legacy one-file demos.

> **Recommended mental model:** start from decorator-based business code, declare an entry method with `@application`,
> attach startup settings with `@configure(...)`, then call `main()` directly.<br>
> **See also:** [Getting Started](getting_started.md), [Build & Run](build_run.md),
> [Parameter System Guide](parameter_system_guide.md), [Testing & Verification](testing.md)

## Recommended reading order

1. `examples/minimal_app/` — the shortest public entrypoint
2. `examples/controller_service_inject/` — business layering with `@service`, `@controller`, and `Inject()`
3. `examples/middleware_and_module/` — when an explicit `@module` boundary is worth adding on top of the entry method
4. `examples/middleware_pipeline/` — declaring middleware order through `@configure(middlewares=[...])`
5. `examples/middleware_control/` — replacing/switching off the built-in middleware layer and unifying legacy middleware ordering
6. `examples/middleware_ownership/` — the two middleware declaration forms and who owns each instance
7. `examples/parameter_handling/` — controller-method parameter binding with `Path`, `Query`, and `Body`
8. `examples/testing_flow/` — testing through `main.get_asgi_app()` without a real server process

## Example map

| Example | Teaches | Run command | Source |
| --- | --- | --- | --- |
| `examples/minimal_app/` | Minimal app structure with `@application + @configure(...) + main()` | `python -m examples.minimal_app` | [View on GitHub](https://github.com/cullinan-py/cullinan/tree/main/examples/minimal_app) |
| `examples/controller_service_inject/` | Service/controller split and type-led `Inject()` wiring | `python -m examples.controller_service_inject` | [View on GitHub](https://github.com/cullinan-py/cullinan/tree/main/examples/controller_service_inject) |
| `examples/middleware_and_module/` | Module boundary ownership and the compatibility middleware protocol | `python -m examples.middleware_and_module` | [View on GitHub](https://github.com/cullinan-py/cullinan/tree/main/examples/middleware_and_module) |
| `examples/middleware_pipeline/` | Declarative middleware order via `@configure(middlewares=[...])` and public introspection | `python -m examples.middleware_pipeline` | [View on GitHub](https://github.com/cullinan-py/cullinan/tree/main/examples/middleware_pipeline) |
| `examples/middleware_control/` | Controlling the built-in middleware layer (`builtin_middleware=[...]`) and unifying legacy middleware ordering | `python -m examples.middleware_control` | [View on GitHub](https://github.com/cullinan-py/cullinan/tree/main/examples/middleware_control) |
| `examples/middleware_ownership/` | The two middleware declaration forms: a `@component` class entry (container-managed) and an instance entry (externally-owned) | `python -m examples.middleware_ownership` | [View on GitHub](https://github.com/cullinan-py/cullinan/tree/main/examples/middleware_ownership) |
| `examples/parameter_handling/` | `Path`, `Query`, and `Body` on controller methods | `python -m examples.parameter_handling` | [View on GitHub](https://github.com/cullinan-py/cullinan/tree/main/examples/parameter_handling) |
| `examples/testing_flow/` | Public-API test flow with ASGI dispatch | `python -m pytest examples/testing_flow/test_app.py -q` | [View on GitHub](https://github.com/cullinan-py/cullinan/tree/main/examples/testing_flow) |
| `examples/static_files_and_spa/` | Declarative `StaticFiles` mounts + SPA fallback (engine-neutral) | `python -m examples.static_files_and_spa` | [View on GitHub](https://github.com/cullinan-py/cullinan/tree/main/examples/static_files_and_spa) |

## Why the examples were restructured

Older examples could accidentally push developers toward a manual app-registration mindset.
The current example set intentionally keeps Cullinan's own concept front and center:

- business-first decorators instead of explicit app wiring
- an entry method as the default entrypoint
- `@module` only when structure needs an explicit runtime boundary
- `Inject()` as the default injection path when the type contract is clear
- parameter binding on controller methods instead of raw request plumbing
- testing via public APIs instead of internal bootstrap shortcuts

## Notes

- The root `examples/README.md` file mirrors this learning path for repository readers.
- You can browse the tracked source set directly from [`examples/`](https://github.com/cullinan-py/cullinan/tree/main/examples).
- `tests/integration/test_examples_public_guides.py` smoke-tests the maintained examples.
- Middleware has several maintained examples: `examples/middleware_pipeline/` uses the
  recommended onion protocol, `examples/middleware_ownership/` shows the two declaration
  forms and their object ownership, while `examples/middleware_and_module/` uses the
  compatibility protocol. See [Middleware](wiki/middleware.md).
- If you are learning Cullinan for the first time, start with `examples/minimal_app/` and then
  continue to `examples/controller_service_inject/`.
