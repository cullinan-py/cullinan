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

Organize your application around business services, controllers, and methods — declare them
with decorators and let Cullinan assemble the runtime, instead of wiring an app object by hand.

---

## Quick start

Declare business components with decorators — there is no app object to wire by hand:

```python
from cullinan import application, configure
from cullinan.core import service
from cullinan.web import controller, get_api

@service
class GreetingService:
    def greet(self):
        return "Hello from Cullinan!"

@controller(url="/hello")
class HelloController:
    greeting: GreetingService          # injected: no constructor wiring to write

    @get_api(url="")
    def hello(self):
        return {"message": self.greeting.greet()}

@configure(user_packages=["minimal_app"], server_port=4080)
@application
def main(): ...
```

Save it in a `minimal_app/` package, run `python -m minimal_app`, and open <http://localhost:4080/hello>.

---

## Install

Cullinan is published on PyPI and currently supports **Python 3.9+**.

```bash
pip install -U pip
pip install cullinan
```

After installation, start from the minimal example in [`examples/minimal_app/`](examples/minimal_app)
or the repository guide in [`docs/examples.md`](docs/examples.md).

A one-line smoke check confirms which version you are running:

```bash
python -c "from cullinan import application, configure; import cullinan; print(cullinan.__version__)"
```

---

## What is Cullinan?

Cullinan makes the framework work around your business architecture, not the other way around:
you declare services, controllers, and methods, and the framework assembles the runtime.

- **Business-first application model** - write services, controllers, middleware, and methods first
- **Decorator-first discovery** - Python imports and decorator metadata assemble the runtime
- **Structured module boundaries** - `@module` expresses ownership and runtime boundaries
- **Built-in IoC/DI and lifecycle** - keep application wiring inside the framework model
- **Engine-neutral Web facade** - build against Cullinan semantics while the framework adapts to Tornado or ASGI internally
- **Public semantic path** - build, run, test, and extend applications through stable public APIs

The quick-start example shows the default path: a business service first, controller methods as
the public web surface, and `@application` + `@configure(...)` + `main()` as the startup flow.
`@module` is available when explicit runtime boundaries are needed, and runtime backend selection
is delegated to Cullinan instead of driving application structure.

---

## Why Cullinan?

- **Semantics before manual wiring** - declare components with decorators and let the framework discover them; explicit runtime internals stay an advanced path rather than the default onboarding path.
- **Application boundaries that scale past toy examples** - `@module` is a structured boundary for owned packages, runtime composition, and higher-level lifecycle behavior, not just a naming convention.
- **Web, DI, lifecycle, and testing in one model** - routing, parameter binding, dependency injection, lifecycle hooks, middleware, and test flow share one framework vocabulary instead of several unrelated patterns.
- **A Pythonic path for business applications** - stay on the public path for most application work and move into internals only when you intentionally need advanced extension behavior.
- **A clearer semantic package surface** - `cullinan` for recommended public startup and declaration, `cullinan.web` for controllers, route decorators, request/response, parameters, and middleware, `cullinan.core` for IoC/DI, lifecycle, context, and semantic rules, `cullinan.testing` for test-facing helpers.
- **Advanced surfaces stay explicit** - `cullinan.application` for maintainers and framework-aware integrations, `cullinan.runtime` / `cullinan.transport` for discovery and adapter boundaries, and `cullinan.support` for constrained support utilities that are not a second public app path.

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

## Learning path

If you are new to Cullinan, use this order:

1. [`examples/minimal_app/`](examples/minimal_app) - shortest public entrypoint
2. [`examples/controller_service_inject/`](examples/controller_service_inject) - service/controller layering with `Inject()`
3. [`examples/middleware_and_module/`](examples/middleware_and_module) - `@module` boundaries and middleware semantics
4. [`examples/middleware_control/`](examples/middleware_control) - turn the built-in middleware layer off or replace it, and unify legacy `@middleware` ordering with `@configure(...)`
5. [`examples/parameter_handling/`](examples/parameter_handling) - method-level `Path`, `Query`, and `Body`
6. [`examples/testing_flow/`](examples/testing_flow) - public-API testing with `get_asgi_app()`

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

**v0.96a4** is the current release of the 0.96 line; **v0.95** remains the current stable line, centered on the top-level `cullinan` API.
The release history for earlier versions is recorded in [CHANGELOG.md](CHANGELOG.md).

---

## Project status

Cullinan — the project carries the name `Cullinan`, the package on PyPI is
`cullinan` — is under active development, working through the `0.96` alpha
line towards `1.0`. Alphas are published to PyPI as they land, so
`pip install cullinan` follows the alpha line, while `v0.95` stays the stable
one.

Development is driven by `plumeink`, who reads and answers issues and pull
requests as time allows — usually within a week, though real life occasionally
stretches that.

---

## Project links

- **GitHub**: https://github.com/cullinan-py/cullinan
- **PyPI**: https://pypi.org/project/cullinan/
- **Issues**: https://github.com/cullinan-py/cullinan/issues
- **Discussions**: https://github.com/cullinan-py/cullinan/discussions

---

## License

MIT License - see [LICENSE](LICENSE) for details.
