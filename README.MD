![Python version](https://img.shields.io/badge/python-3.9%20|%203.10%20|%203.11%20|%203.12%20|%203.13-blue)
![PyPI version](https://img.shields.io/pypi/v/cullinan.svg?style=flat&logo=pypi&color=green)
![PyPI downloads](https://img.shields.io/pypi/dm/cullinan.svg?style=flat&logo=pypi&color=blue)
[![Ask DeepWiki](https://deepwiki.com/badge.svg)](https://deepwiki.com/cullinan-py/cullinan)
![GitHub stars](https://img.shields.io/github/stars/cullinan-py/cullinan.svg?style=flat&logo=github&color=white)
![License](https://img.shields.io/github/license/cullinan-py/cullinan.svg?style=flat&color=white)

```
   _____      _ _ _
  / ____|    | | (_)
 | |    _   _| | |_ _ __   __ _ _ __
 | |   | | | | | | | '_ \ / _` | '_ \
 | |___| |_| | | | | | | | (_| | | | |
  \_____\__,_|_|_|_|_| |_|\__,_|_| |_|
```

# Cullinan

**A business-first Python web framework for building applications through decorators, module boundaries, and built-in IoC/DI.**

Cullinan is a Python Web Framework for developers who want to organize applications around
business services, controllers, and methods instead of manually wiring an app object.
Its default path is decorator-first discovery plus `@application` + `@configure(...)`,
with `@module` used as the application boundary when ownership, runtime structure, and stability
matter. The framework-facing API stays engine-neutral:
Cullinan internally bridges your business application into Tornado or ASGI runtimes instead of
making a concrete server framework the primary developer mental model.

---

## What is Cullinan?

Cullinan is designed to make the framework work around your business architecture, not the
other way around.

- **Business-first application model** - write services, controllers, middleware, and methods first
- **Decorator-first discovery** - let Python imports and decorator metadata assemble the runtime
- **Structured module boundaries** - use `@module` to express ownership and runtime boundaries
- **Built-in IoC/DI and lifecycle** - keep application wiring inside the framework model
- **Engine-neutral Web facade** - build against Cullinan semantics while the framework adapts to Tornado or ASGI internally
- **Public semantic path** - build, run, test, and extend applications through stable public APIs

Cullinan is not centered on treating an app object as a manual registration hub. The
recommended development flow is to declare business components, define a root module when
structure matters, and let the framework assemble the application runtime.

---

## Why Cullinan?

### 1. Framework semantics before manual wiring

Cullinan gives you a clear application model: declare components with decorators, let the
framework discover them, and keep explicit runtime internals as an advanced path rather than
the default onboarding path.

### 2. Application boundaries that scale past toy examples

`@module` is more than a naming convention. It is the structured boundary for owned packages,
runtime composition, and higher-level lifecycle behavior when your application grows.

### 3. Web, DI, lifecycle, and testing in one model

Routing, parameter binding, dependency injection, lifecycle hooks, middleware, and test flow
all sit inside one framework vocabulary instead of forcing developers to stitch together
multiple unrelated patterns.

### 4. A Pythonic path for business applications

Cullinan is designed to keep developers focused on business architecture and business methods.
You can stay on the public path for most application work and only move into internals when
you intentionally need advanced extension behavior.

### 5. A clearer semantic package surface

Cullinan now exposes a clearer framework-shaped package surface:

- `cullinan` - recommended public startup and declaration API for application code
- `cullinan.web` - controllers, route decorators, request/response, parameters, middleware
- `cullinan.core` - IoC/DI, lifecycle, context, and semantic rules
- `cullinan.application` - advanced application semantics for maintainers and framework-aware integrations
- `cullinan.testing` - test-facing helpers
- `cullinan.runtime` / `cullinan.transport` - advanced discovery and adapter boundaries
- `cullinan.support` - constrained support utilities, not a second public app path

---

## Framework capabilities

| Capability layer | What Cullinan provides |
| --- | --- |
| **Application composition** | `@application` + `@configure(...)`, decorator-driven discovery, structured runtime assembly |
| **Web API model** | `cullinan.web` facade for `@controller`, RESTful decorators, `WebResponse`, parameters, middleware |
| **Parameter system** | Typed `Path`, `Query`, `Body`, validation, conversion, and controller-method binding |
| **IoC/DI and lifecycle** | `Inject()`, `InjectByName()`, request scope, startup/shutdown hooks, component lifecycle |
| **Runtime boundaries** | `@module` ownership, clearer package structure, better runtime organization |
| **Testing and delivery** | `get_asgi_app()`, resettable registries, packaging-friendly runtime, cross-platform support |

Cullinan's goal is not to expose every internal knob on the README homepage. The goal is to
provide a coherent framework model that remains readable from first contact through production use.

---

## Install

Cullinan is published on PyPI and currently supports **Python 3.9+**.

```bash
pip install -U pip
pip install cullinan
```

After installation, start from the minimal example in [`examples/minimal_app/`](examples/minimal_app)
or the repository guide in [`docs/examples.md`](docs/examples.md).

---

## Quick Start

The recommended starting point is: define business components, decorate them,
and declare the application entry with `@configure(...)` + `@application` + `main()`.

```python
from cullinan import application, configure
from cullinan.core import service
from cullinan.web import controller, get_api


@service
class GreetingService:
    def greet(self) -> str:
        return "Hello from Cullinan!"


@controller(url="/hello")
class HelloController:
    greeting_service: GreetingService  # constructor injection: one line is all you need

    @get_api(url="")
    def hello(self):
        return {"message": self.greeting_service.greet()}


@configure(user_packages=["minimal_app"], server_port=4080)
@application
def main(): ...
```

Run it:

```bash
python -m minimal_app
```

Then open:

```text
http://localhost:4080/hello
```

This example shows the default Cullinan path:

- business service first
- controller methods as the public web surface
- `@application` + `@configure(...)` + `main()` as the startup flow
- `@module` available when explicit runtime boundaries are needed
- runtime backend selection delegated to Cullinan instead of driving application structure

---

## Learning path

If you are new to Cullinan, use this order:

1. [`examples/minimal_app/`](examples/minimal_app) - shortest public entrypoint
2. [`examples/controller_service_inject/`](examples/controller_service_inject) - service/controller layering with `Inject()`
3. [`examples/middleware_and_module/`](examples/middleware_and_module) - `@module` boundaries and middleware semantics
4. [`examples/parameter_handling/`](examples/parameter_handling) - method-level `Path`, `Query`, and `Body`
5. [`examples/testing_flow/`](examples/testing_flow) - public-API testing with `get_asgi_app()`

Then move into the documentation knowledge base:

- [`docs/README.md`](docs/README.md) - English knowledge base home
- [`docs/zh/README.md`](docs/zh/README.md) - Chinese knowledge base home
- [`docs/getting_started.md`](docs/getting_started.md) - recommended application entry
- [`docs/framework_semantics.md`](docs/framework_semantics.md) - framework concepts and semantics
- [`docs/examples.md`](docs/examples.md) - example navigation page

---

## Documentation

### English

- [Documentation home](https://cullinan-py.github.io/cullinan/)
- [Getting Started](https://cullinan-py.github.io/cullinan/getting_started/)
- [Framework Semantics](https://cullinan-py.github.io/cullinan/framework_semantics/)
- [Examples](https://cullinan-py.github.io/cullinan/examples/)
- [Dependency Injection Guide](https://cullinan-py.github.io/cullinan/dependency_injection_guide/)
- [Web Runtime Guide](https://cullinan-py.github.io/cullinan/web_runtime_guide/)
- [Static Files and SPA Guide](https://cullinan-py.github.io/cullinan/static_files_guide/)
- [Parameter System Guide](https://cullinan-py.github.io/cullinan/parameter_system_guide/)
- [Testing & Verification](https://cullinan-py.github.io/cullinan/testing/)

### Chinese

- [Documentation home](https://cullinan-py.github.io/cullinan/zh/)
- [Getting Started](https://cullinan-py.github.io/cullinan/zh/getting_started/)
- [Framework Semantics](https://cullinan-py.github.io/cullinan/zh/framework_semantics/)
- [Examples](https://cullinan-py.github.io/cullinan/zh/examples/)
- [Dependency Injection Guide](https://cullinan-py.github.io/cullinan/zh/dependency_injection_guide/)
- [Web Runtime Guide](https://cullinan-py.github.io/cullinan/zh/web_runtime_guide/)
- [Static Files and SPA Guide](https://cullinan-py.github.io/cullinan/zh/static_files_guide/)
- [Parameter System Guide](https://cullinan-py.github.io/cullinan/zh/parameter_system_guide/)
- [Testing & Verification](https://cullinan-py.github.io/cullinan/zh/testing/)

---

## Current series

**v0.94a1** is the Phase A convergence cut for the 1.0 roadmap. This release line
locks down the public surface and packaging baseline around:

- `@application` + `@configure(...)` + `main()` as the startup flow
- decorator-first discovery through Python imports
- `@module` as the structured boundary for runtime ownership
- built-in IoC/DI, lifecycle, and semantic diagnostics
- a semantic package surface centered on the top-level `cullinan` API, with
  advanced semantic namespaces under `cullinan.application`, `cullinan.web`,
  and `cullinan.core`
- engine-neutral runtime selection over Tornado / ASGI backends
- `pyproject.toml` + `setuptools.build_meta` packaging with `setup.py` kept as a compatibility shim
- PEP 561 typed-package distribution via `cullinan/py.typed`

Version-specific details and migration notes live in the documentation knowledge base rather
than in the homepage narrative.

---

## Project links

- **GitHub**: https://github.com/cullinan-py/cullinan
- **PyPI**: https://pypi.org/project/cullinan/
- **Issues**: https://github.com/cullinan-py/cullinan/issues
- **Discussions**: https://github.com/cullinan-py/cullinan/discussions

---

## License

MIT License - see [LICENSE](LICENSE) for details.
