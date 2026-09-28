title: "Components"
slug: "components"
module: ["cullinan"]
tags: ["components", "architecture"]
author: "plumeink"
reviewers: []
status: updated
locale: en
translation_pair: "docs/zh/wiki/components.md"
related_tests: ["tests/core/test_application_model_refactor.py", "tests/web/test_web_runtime.py", "tests/integration/test_service_lifecycle_integration.py", "tests/core/test_strict_assembly.py"]
related_examples: []
estimate_pd: 1.5
last_updated: "2026-05-31T00:00:00Z"
pr_links: []

# Components

This page gives a current high-level map of Cullinan's main runtime components.

For the contract behind automatic discovery and registration, read [Framework Semantics](../framework_semantics.md). The short version is: Cullinan guarantees module-top-level decorated components whose decorators run during import, not arbitrary local class definitions created later.

## Runtime overview

### 1. Application orchestration

- Responsibility: module graph discovery, ownership resolution, runtime activation, draining, and active-app lookup
- Main package: `cullinan.application`
- Key APIs: `Application`, `module`, `Application.current()`, `Runtime`

### 2. Core container

- Responsibility: dependency registration, resolution, scopes, lifecycle, request context
- Main package: `cullinan.core`
- Key APIs: `ApplicationContext`, `Definition`, `ScopeType`, `Inject`, `InjectByName`

### 3. Service layer

- Responsibility: business logic and long-lived framework-managed services
- Main package: `cullinan.core` (`@service`) with advanced `Service`/registry helpers under `cullinan.core.services`
- Key APIs: `service`, `Service`

### 4. Controller layer

- Responsibility: route declaration and handler methods
- Main package: `cullinan.web.controller`
- Key APIs: `controller`, `get_api`, `post_api`, `response_build`

### 5. Web Runtime

- Responsibility: normalized request/response model, routing, dispatch, middleware, exceptions
- Main package: `cullinan.web.gateway`
- Key APIs: `WebRequest`, `WebResponse`, `Router`, `Dispatcher`, `MiddlewarePipeline`, `WebRuntime`

### 6. Adapters

- Responsibility: bind the Web Runtime to a specific server environment
- Main package: `cullinan.transport.adapter`
- Key APIs: `WebAdapter`, `TornadoAdapter`, `ASGIAdapter`
- Positioning: backend integration layer behind Cullinan's semantic Web facade

### 7. Parameters and model binding

- Responsibility: map path/query/body/header/file inputs into handler arguments
- Main package: `cullinan.web.params`
- Key APIs: `Path`, `Query`, `Body`, `Header`, `File`

## Declared but not assembled

Discovery is import-executed, assembly scans the packages listed in
`user_packages`. A component whose decorator ran while its package was **not**
listed is therefore *declared* but never *assembled*, and Cullinan acts on that
difference in one of two strengths:

| Action | When | What happens |
|--------|------|--------------|
| **Report** (default) | always | `Application.get_declaration_diff()` exposes `declared` / `assembled` / `dropped`, and a `component-declared-not-assembled` diagnostic is emitted. Startup continues. |
| **Fail** (opt-in) | `configure(strict_assembly=True)` | The same diagnostic is emitted, and startup then fails with a `ConfigurationError`. |

Components that are intentionally left unassembled can be named in
`configure(strict_assembly_excludes=[...])`, written as
`package.module.Component`. That acknowledges the intent — the component is
still reported, but it no longer stops startup.

`strict_assembly` is a different setting from `startup_error_policy`, which
governs service *initialisation* failures rather than unassembled declarations.

See [Framework Semantics](../framework_semantics.md) §11 for the full contract.

## Suggested reading order

1. [Architecture](../architecture.md)
2. [Application Runtime Model](application_runtime.md)
3. [Framework Semantics](../framework_semantics.md)
4. [Dependency Injection Guide](../dependency_injection_guide.md)
5. [Web Runtime Guide](../web_runtime_guide.md)
6. [Testing & Verification](../testing.md)
