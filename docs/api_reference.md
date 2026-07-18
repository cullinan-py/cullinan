title: "API Reference"
slug: "api-reference"
module: []
tags: ["api", "reference"]
author: "Cullinan"
reviewers: []
status: updated
locale: en
translation_pair: "docs/zh/api_reference.md"
related_tests: []
related_examples: []
estimate_pd: 1.5
last_updated: "2026-06-01T00:00:00Z"
pr_links: []

# API Reference

> **Note (v0.90)**: The core module has been reorganized. For the new API structure, see [Dependency Injection Guide](dependency_injection_guide.md) and [Import Migration Guide](import_migration_090.md).

This page provides an overview of the public API surface of Cullinan and clarifies which APIs are recommended and which stay in advanced runtime-facing layers.

> **Need the recommended learning path first?** Start from [Application Build](start/index.md)
> and [Framework Semantics](concepts/index.md).  
> **Need advanced runtime internals?** Continue in [Internals & Extensions](internals/index.md).

## API layering

### Recommended default API

- `cullinan` — top-level application API for regular business projects:
  - startup: `@application`, `configure(...)`, then call the entry method directly (for example `main()`)
  - declaration: `@service`, `@controller`, `@module` (advanced boundary), route decorators
  - injection / params: `Inject`, `InjectByName`, `Path`, `Query`, `Body`, ...
  - framework mental model: decorator-first business code, component discovery,
    IoC/DI wiring, and module boundaries with hot-pluggable runtime semantics

### Advanced integration API

- `cullinan.application` — advanced public application semantics for maintainers
  and framework-aware integrations (`Application`, `Runtime`, `module`, `run`, `get_asgi_app`)
- `cullinan.transport.adapter` — server integration (`WebAdapter`, `TornadoAdapter`, `ASGIAdapter`)
- `cullinan.web.gateway` — request / response / dispatcher contracts
- `cullinan.core` — low-level container and lifecycle primitives

These advanced modules are not the default application-facing mental model.
Regular business code should stay on the top-level `cullinan` API and the
framework's own decorator / DI / module semantics rather than dropping into
low-level runtime orchestration or a concrete server adapter.

For regular applications, prefer the top-level `cullinan` API. Advanced modules
should be imported explicitly so the boundary stays visible in code review, IDE
completion, and onboarding docs.

The v0.94 Phase A freeze uses package `__all__` lists as the reviewable export contract:

- `cullinan.__all__` — regular application-facing startup, declaration, and request APIs
- `cullinan.application.__all__` — advanced application/runtime helpers, including `run()` and `get_asgi_app()`
- `cullinan.web.__all__` / `cullinan.core.__all__` — explicit business-web and container/lifecycle surfaces

Symbols that are not present in the corresponding `__all__` list should be
treated as private implementation details. Underscore-prefixed compatibility
exports may still exist, but they are not part of the default business-facing
stability promise.

## New in v0.90+: Parameter System

The parameter system provides type-safe request parameter handling. See [Parameter System Guide](parameter_system_guide.md) for details.

### cullinan.web.params (v0.90a4+)

| Symbol | Type | Description |
|--------|------|-------------|
| `Param` | class | Base parameter class |
| `Path` | class | URL path parameter marker |
| `Query` | class | Query string parameter marker |
| `Body` | class | Request body parameter marker |
| `Header` | class | HTTP header parameter marker |
| `File` | class | File upload parameter marker |
| `RawBody` | class | Raw unparsed request body, use `bytes = RawBody()` (v0.90a5+) |
| `UNSET` | sentinel | Sentinel value for unset parameters |
| `TypeConverter` | class | Type conversion utility |
| `Auto` | class | Auto type inference utility |
| `AutoType` | class | Auto type marker for signatures |
| `DynamicBody` | class | Dynamic request body container |
| `SafeAccessor` | class | Chain-safe property accessor |
| `EMPTY` | sentinel | Empty value sentinel |
| `ParamValidator` | class | Parameter validation utility |
| `ValidationError` | exception | Validation error |
| `ModelResolver` | class | dataclass model resolution |
| `ModelError` | exception | Model resolution error |
| `ParamResolver` | class | Parameter resolution orchestrator |
| `ResolveError` | exception | Parameter resolution error |

### cullinan.web.params (v0.90a5+)

| Symbol | Type | Description |
|--------|------|-------------|
| `FileInfo` | class | File metadata container |
| `FileList` | class | Multiple files container |
| `field_validator` | decorator | Dataclass field validator |
| `validated_dataclass` | decorator | Auto-validating dataclass |
| `FieldValidationError` | exception | Field validation error |
| `Response` | decorator | Response model decorator |
| `ResponseModel` | class | Response model definition |
| `ResponseSerializer` | class | Response serialization utility |
| `serialize_response` | function | Convenience serialization function |
| `get_response_models` | function | Get response models from function |

### cullinan.web.params.model_handlers (v0.90a5+)

Pluggable model handler architecture for third-party library integration.

| Symbol | Type | Description |
|--------|------|-------------|
| `ModelHandler` | class | Abstract base class for model handlers |
| `ModelHandlerError` | exception | Model handler error |
| `ModelHandlerRegistry` | class | Registry for model handlers |
| `DataclassHandler` | class | Built-in dataclass handler |
| `PydanticHandler` | class | Optional Pydantic handler (if installed) |
| `get_model_handler_registry()` | function | Get global handler registry |
| `reset_model_handler_registry()` | function | Reset registry (testing) |

### cullinan.codec

| Symbol | Type | Description |
|--------|------|-------------|
| `BodyCodec` | class | Abstract request body codec |
| `ResponseCodec` | class | Abstract response codec |
| `JsonBodyCodec` | class | JSON body decoder |
| `JsonResponseCodec` | class | JSON response encoder |
| `FormBodyCodec` | class | Form body decoder |
| `CodecRegistry` | class | Codec registry |
| `get_codec_registry()` | function | Get global codec registry |
| `reset_codec_registry()` | function | Reset codec registry (testing) |
| `DecodeError` | exception | Decoding error |
| `EncodeError` | exception | Encoding error |
| `CodecError` | exception | Base codec error |

### cullinan.web.middleware (new additions)

| Symbol | Type | Description |
|--------|------|-------------|
| `BodyDecoderMiddleware` | class | Auto body decoding middleware |
| `get_decoded_body()` | function | Get decoded request body |
| `set_decoded_body()` | function | Set decoded body (testing) |

## Public symbols and signatures (recommended structure)

For each module, the API reference is recommended to follow this structure:

- Module path, for example: `cullinan.web.controller`
- Short description: primary responsibility and typical usage scenarios
- List of public classes and functions (example):
  - `@controller(...)` — Controller decorator, responsible for auto-registering controllers and their routes
  - `@get_api(url=..., query_params=..., body_params=..., headers=...)` — GET endpoint decorator
  - `@post_api(url=..., body_params=..., headers=...)` — POST endpoint decorator
  - `Inject`, `InjectByName` — Property/constructor injection markers

A complete API reference can be populated using this structure, either via automated generation or by manual curation.

## v0.95a1 additions (Track A internal refactor)

### New public API symbols

| Symbol | Location | Type | Description |
|--------|----------|------|-------------|
| `ScopeViolationError` | `cullinan.core.exceptions` | exception (subclass of `LifecycleError`) | Raised when a singleton/prototype component transitively depends on a request-scoped component. Carries `dependency_chain`, `origin_name`, `violating_component`. |
| `format_scope_violation_error` | `cullinan.core.diagnostics` | function | Renders a human-readable description of a scope violation from the dependency chain, origin, and violating component. |
| `strict_private_injection` | `ApplicationContext.__init__` | kwarg | When `True`, single-underscore (`_xxx`) attributes are skipped by the injection marker scanner. Default `False`. |
| `strict_lifecycle` | `ApplicationContext.__init__` | kwarg | When `True`, non-critical lifecycle hook failures (`on_startup`/`on_shutdown`) propagate as `LifecycleError`. Default `False`. |
| `skip_private` | `get_injection_markers` | kwarg | When `True`, skips single-underscore-prefixed attributes during marker scanning. Default `False`. |
| `CULLINAN_STRICT_PRIVATE_INJECTION` | environment variable | config | Set to `1`/`true`/`yes` to globally enable `strict_private_injection` for all `ApplicationContext` instances. |

### Deprecated symbols (removed in v0.97)

| Symbol | Replacement |
|--------|-------------|
| `injectable` | `@service` / `@component` / `@controller` |
| `inject_constructor` | `ApplicationContext.refresh()` |
| `InjectionRegistry` | `ApplicationContext` / `get_application_context()` |
| `get_injection_registry()` | `ApplicationContext` / `get_application_context()` |
| `reset_injection_registry()` | Create a new `ApplicationContext` explicitly |

See [Framework Semantics](concepts/framework_semantics.md) §5-§8 for full details.

## Regenerating API documentation (example workflow)

When adding automation later, a static analysis script can be used to generate the API index and keep this page in sync with the source. A typical workflow might be:

1. Maintain a script under `docs/work/` (for example `generate_api_reference.py`) that scans modules and emits Markdown fragments.
2. Have the script produce a per-module API list (classes, functions, signatures, short descriptions) into `docs/work/api_modules.md` or update this page directly.
3. Run the script periodically in CI or as part of local documentation build steps to ensure the API reference reflects the current codebase.

The exact tooling and script implementation can be refined based on project conventions and the chosen documentation toolchain.
