title: "Getting Started with Cullinan"
slug: "getting-started"
module: ["cullinan"]
tags: ["getting-started", "tutorial"]
author: "Cullinan"
reviewers: []
status: updated
locale: en
translation_pair: "docs/zh/getting_started.md"
related_tests: ["tests/core/test_application_model_refactor.py", "tests/integration/test_adapter_integration.py"]
related_examples: ["examples/minimal_app"]
estimate_pd: 2.0
last_updated: "2026-06-01T00:00:00Z"
pr_links: []

# Getting Started with Cullinan

This page provides a minimal quick-start to install and run a small Cullinan application.
The key mental model is: write business methods and components with decorators first,
then let the runtime assemble them. Cullinan is not centered on a manually wired app object.

> **Read next:** [Framework Semantics](framework_semantics.md), [Engineering Practices](how-to/index.md)  
> **Runnable repository guide:** `examples/minimal_app/` is the maintained minimal example.<br>
> **Advanced boundary:** if you intentionally need explicit `Application` orchestration,
> continue in [Internals & Extensions](internals/index.md) instead of treating that path
> as the default bootstrap.

## Prerequisites
- Python 3.9+
- Git

## Install

Before you start, make sure Python 3.9+ is installed and that `python` and `pip` are available on your PATH.

On most systems, you can upgrade pip and install Cullinan with the following commands (valid on Windows, Linux, and macOS):

```bash
python -m pip install -U pip
python -m pip install cullinan
```

## Quick start
1. Create a new project directory and change into it:

On all platforms:

```bash
mkdir my_cullinan_project
cd my_cullinan_project
```

2. Ensure you have a Python environment (virtualenv, conda, system Python, etc.). Install the published package:

```bash
python -m pip install -U pip
python -m pip install cullinan
```

3. Create a minimal application file `minimal_app.py` in your project with the following content:

```python
# minimal_app.py
from cullinan import application, configure
from cullinan.core import service
from cullinan.web import controller, get_api


@service
class GreetingService:
    def greet(self) -> str:
        return "Hello from Cullinan!"


@controller(url="/hello")
class HelloController:
    """Simple HTTP controller."""

    greeting_service: GreetingService  # constructor injection

    @get_api(url="")
    def hello(self):
        return {"message": self.greeting_service.greet()}


@configure(user_packages=["my_cullinan_project"])
@application
def main(): ...

if __name__ == '__main__':
    main()
```

4. Run your app:

On Windows (PowerShell):

```powershell
python minimal_app.py
```

On Linux / macOS:

```bash
python minimal_app.py
```

Then open `http://localhost:4080/hello` in your browser to verify the server is running.

## What this example demonstrates

- You mainly write business components with `@service`, `@controller`, and handler decorators
- `@application` marks the default entry method
- `@configure(...)` attaches startup settings to that method
- `@module` is optional and only needed when you want an explicit advanced runtime boundary
- Bare type annotations enable constructor injection, resolving controller dependency from the active application context
- calling the entry method assembles and serves the application through the framework's default startup API

## Minimal application example

Here's a minimal Cullinan application that demonstrates the core framework features:

```python
# minimal_app.py
from cullinan import application, configure
from cullinan.core import service
from cullinan.web import controller, get_api


@service
class GreetingService:
    def greet(self) -> str:
        return "Hello from Cullinan!"


@controller(url="/hello")
class HelloController:
    greeting_service: GreetingService  # constructor injection

```powershell
# Save the above code as minimal_app.py
python minimal_app.py
```

Then visit `http://localhost:4080/hello` in your browser.

## Understanding the basics

### Application lifecycle
1. **Entry declaration**: `@application` marks the entry method, and `@configure(...)` attaches startup settings to it
2. **Discovery and assembly**: calling `main()` imports owned packages, finalizes pending decorator registrations, and assembles business components under the framework-managed runtime boundary
3. **Activation**: the validated runtime becomes active and is served through the framework-selected backend path
4. **Reload / shutdown**: old runtimes drain in-flight requests before closing

### Dependency Injection
Cullinan provides built-in IoC/DI support through decorator-driven component discovery and runtime-managed wiring.

#### Recommended runtime model

- Use `@service` for business services
- Use `@controller` for HTTP controllers
- Use bare type annotations for constructor injection (recommended)
- Use `Inject()` for explicit type-based injection when needed
- Use `InjectByName()` when name-based lookup is more convenient
- Start from business decorators and an entry method first
- Add `@module` only when you need explicit runtime boundaries such as package ownership, hot-pluggable modules, or stricter reload/draining control
- If you intentionally need low-level container or runtime internals, continue in [Internals & Extensions](internals/index.md) instead of treating that path as the quick-start model

```python
from cullinan.web import controller, get_api, Path
from cullinan.core import service

@service
class UserService:
    def get_user(self, user_id):
        return {'id': user_id, 'name': 'John'}

@controller(url='/api/users')
class UserController:
    user_service: UserService  # constructor injection

    @get_api(url='/{user_id}')
    async def get_user(self, user_id: int = Path()):
        return self.user_service.get_user(user_id)
```

**Compatibility note:** `injectable` and `inject_constructor` still exist as compatibility shims, but new code should not use them as the primary pattern.

---

#### RESTful API decorators (quick overview)

Cullinan provides a set of REST-style decorators that bind controller methods to HTTP routes:

- `get_api`
- `post_api`
- `patch_api`
- `delete_api`
- `put_api`

Key points:

- These decorators **only accept keyword arguments** (they are defined as `def get_api(**kwargs)` etc.).
  - `@get_api('/user')` is **invalid** and will raise a `TypeError` at import time.
  - Always use the keyword form: `@get_api(url='/user')`.
- The `url` argument uses a lightweight template syntax with `{param}` placeholders.

**v0.90+ Recommended: Type-Safe Parameter System**

```python
from cullinan.web.params import Path, Query, Body, DynamicBody

@controller(url='/api/users')
class UserController:
    # Type-safe path and query parameters (new unified syntax)
    @get_api(url='/{id}')
    async def get_user(self, id: int = Path(), include_posts: bool = Query(default=False)):
        return {"id": id, "include_posts": include_posts}
    
    # Pure type annotation as Query (v0.90a5+)
    @get_api(url='/')
    async def list_users(
        self,
        page: int = 1,      # Same as Query(default=1)
        size: int = 10,     # Same as Query(default=10)
    ):
        return {"page": page, "size": size}
    
    # Type-safe body parameters with validation
    @post_api(url='/')
    async def create_user(
        self,
        name: str = Body(required=True),
        age: int = Body(default=0, ge=0, le=150),
    ):
        return {"name": name, "age": age}
    
    # DynamicBody for flexible access
    @post_api(url='/dynamic')
    async def create_dynamic(self, body: DynamicBody):
        return {"name": body.name, "age": body.get('age', 0)}
```

See [Parameter System Guide](parameter_system_guide.md) for full details, including:
- File uploads with `FileInfo`/`FileList`
- Dataclass validation with `@field_validator`
- Pydantic integration (optional, install with `pip install pydantic`)
- Custom model handlers

<details>
<summary><strong>Legacy Style (still supported)</strong></summary>

The traditional parameter style is still supported for backward compatibility:

Common options:
- `url`: Route pattern (string). Supports `{param}` placeholders, e.g. `'/users/{user_id}'`.
- `query_params`: Iterable of query parameter names, e.g. `('page', 'size')`.
- `body_params` (POST/PATCH only): Iterable of body field names for JSON/form parsing.
- `file_params`: Iterable of file field names for file uploads.
- `headers`: Iterable of required HTTP header names.
- `get_request_body` (POST/PATCH only): If `True`, passes the raw request body to your method.

```python
@controller(url='/api/users')
class UserController:
    @get_api(url='/{user_id}')
    def get_user(self, url_params):
        user_id = url_params.get('user_id') if url_params else None
        return {"id": user_id}

    @get_api(url='/', query_params=('page', 'size'))
    def list_users(self, query_params):
        page = query_params.get('page') if query_params else None
        size = query_params.get('size') if query_params else None
        return {"page": page, "size": size}

    @post_api(url='/', body_params=('name', 'email'))
    def create_user(self, body_params):
        name = body_params.get('name') if body_params else None
        email = body_params.get('email') if body_params else None
        return {"name": name, "email": email}
```

</details>

For a deeper dive into URL patterns and all decorator options, see `wiki/restful_api.md`.

---

#### Recommended Dependency Injection Approaches

**Approach 1: Constructor Injection (Recommended)**

Prefer bare type annotations for constructor injection — the simplest and most idiomatic pattern:

```python
from cullinan.core import service

@service
class DatabaseService:
    def query(self, sql):
        return f"Results for: {sql}"

@service
class UserRepository:
    db: DatabaseService  # constructor injection

    def get_users(self):
        return self.db.query("SELECT * FROM users")
```

**Approach 2: Inject**

Use typed `Inject()` when you need explicit injection semantics or are working with legacy code:

```python
from cullinan.core import Inject, service

@service
class DatabaseService:
    def query(self, sql):
        return f"Results for: {sql}"

@service
class UserRepository:
    db: DatabaseService = Inject()

    def get_users(self):
        return self.db.query("SELECT * FROM users")
```

**Approach 3: InjectByName**

Inject by name without importing dependencies, avoiding circular import issues:

```python
from cullinan.core import InjectByName, service

@service
class DatabaseService:
    def query(self, sql):
        return f"Results for: {sql}"

@service
class UserRepository:
    db = InjectByName('DatabaseService')
    
    def get_users(self):
        return self.db.query("SELECT * FROM users")
```

**Approach 4: Inject + TYPE_CHECKING (IDE autocomplete support)**

If you need IDE autocomplete and type checking, use `Inject` with TYPE_CHECKING:

```python
from typing import TYPE_CHECKING
from cullinan.core import Inject, service

# TYPE_CHECKING imports are not executed at runtime, avoiding circular imports
if TYPE_CHECKING:
    from my_project.services import DatabaseService

@service
class DatabaseService:
    def query(self, sql):
        return f"Results for: {sql}"

@service
class UserRepository:
    db: 'DatabaseService' = Inject()
    
    def get_users(self):
        return self.db.query("SELECT * FROM users")
```

**Summary:**
- **Constructor Injection (bare type annotation)**: Recommended default — simplest, cleanest, idiomatic
- **Inject**: Explicit syntax for legacy compatibility or when explicit injection semantics are preferred
- **InjectByName**: Useful for decoupling or avoiding circular imports
- **Inject + TYPE_CHECKING**: Best for strong editor support without runtime import coupling

For detailed information on injection patterns, see `wiki/injection.md`.

## Common patterns

### Adding middleware
```python
from cullinan.web.middleware import MiddlewareBase

class LoggingMiddleware(MiddlewareBase):
    def process_request(self, request):
        print(f"Request: {request.method} {request.path}")

# Register during app initialization
app.add_middleware(LoggingMiddleware())
```

### Configuration
```python
from cullinan.support.config import Config

config = Config()
config.set('database.url', 'postgresql://localhost/mydb')
config.set('server.port', 8080)
```

## Troubleshooting
- If you encounter errors installing packages, ensure your Python and pip are up to date and that you have network access to PyPI.

## Next steps
- Read `wiki/injection.md` for IoC/DI details.
- Explore `examples/` for runnable samples.

## Additional resources

- **Architecture**: See `architecture.md` for system design overview
- **Application runtime**: Read `wiki/application_runtime.md` for module graph, ownership, and draining
- **Components**: Read `wiki/components.md` for component responsibilities
- **Lifecycle**: Learn about application lifecycle in `wiki/lifecycle.md`
- **Middleware**: Understand middleware in `wiki/middleware.md`
- **API Reference**: Browse `api_reference.md` for complete API documentation
- **Examples**: Explore `examples/` directory for more samples

## Community and support

- **Issues**: Report bugs at [GitHub Issues](https://github.com/your-org/cullinan/issues)
- **Contributing**: See `contributing.md` for contribution guidelines
- **Testing**: Read `testing.md` for testing best practices
