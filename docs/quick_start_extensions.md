# Cullinan Extension Registration Quick Start

> **Feature**: Unified Extension Registration and Discovery Pattern  
> **Author**: plumeink

> **Advanced topic:** use this page when you are explicitly building extensions or
> middleware registration flows.

---

## Quick Start

### 1. Middleware Registration (Recommended)

Use the `@middleware` decorator to automatically register middleware:

```python
from cullinan.web.middleware import middleware, Middleware

@middleware(priority=100)
class LoggingMiddleware(Middleware):
    """Logging middleware - records all requests"""
    
    def process_request(self, handler):
        print(f"→ Request: {handler.request.uri}")
        return handler  # Return handler to continue processing
    
    def process_response(self, handler, response):
        print(f"← Response: {response}")
        return response
```

### 2. Priority Control

Lower priority numbers execute first:

```python
@middleware(priority=10)   # Executes first
class CorsMiddleware(Middleware):
    pass

@middleware(priority=50)   # Executes second
class AuthMiddleware(Middleware):
    pass

@middleware(priority=100)  # Executes third
class LoggingMiddleware(Middleware):
    pass
```

**Recommended Priority Ranges**:
- `0-50`: Critical middleware (CORS, security checks)
- `51-100`: Standard middleware (logging, metrics)
- `101-200`: Application-specific middleware

### 3. Extension Point Discovery

Query available extension points:

```python
from cullinan.support.extensions import list_extension_points

# Query all extension points
all_points = list_extension_points()

# Query extension points by category
middleware_points = list_extension_points(category='middleware')
lifecycle_points = list_extension_points(category='lifecycle')

# Display extension point info
for point in middleware_points:
    print(f"{point['name']}: {point['description']}")
```

Example output:
```
Middleware.process_request: Intercept and process requests before they reach handlers
Middleware.process_response: Intercept and process responses before they are sent
```

### 4. Query Registered Middleware

```python
from cullinan.web.middleware import get_middleware_registry

registry = get_middleware_registry()
registered = registry.get_registered_middleware()

for mw in registered:
    print(f"{mw['priority']:3d}: {mw['name']}")
```

Example output:
```
 10: CorsMiddleware
 50: AuthMiddleware
100: LoggingMiddleware
```

---

## Complete Example

### Scenario: Building an Authenticated API

```python
from cullinan import application, configure
from cullinan.web.middleware import middleware, Middleware
from cullinan.web.controller import controller, get_api
from cullinan.core.services import service, Service
from cullinan.web.params import Path

# 1. Define middleware (auto-sorted by priority)

@middleware(priority=10)
class CorsMiddleware(Middleware):
    """CORS middleware - executes first"""
    def process_response(self, handler, response):
        handler.set_header('Access-Control-Allow-Origin', '*')
        return response


@middleware(priority=50)
class AuthMiddleware(Middleware):
    """Auth middleware - executes after CORS"""
    def process_request(self, handler):
        token = handler.request.headers.get('Authorization')
        if not token and handler.request.path.startswith('/api/'):
            handler.set_status(401)
            handler.finish({"error": "Unauthorized"})
            return None  # Short-circuit, stop processing
        return handler


@middleware(priority=100)
class LoggingMiddleware(Middleware):
    """Logging middleware - executes last"""
    def process_request(self, handler):
        print(f"[{handler.request.method}] {handler.request.path}")
        return handler


# 2. Define services

@service
class UserService(Service):
    def get_user(self, user_id):
        return {"id": user_id, "name": "Alice"}


# 3. Define controllers

@controller(url='/api/users')
class UserController:
    user_service: UserService  # ← Construction injection

    @get_api(url='/{user_id}')
    async def get_user(self, user_id: int = Path()):
        return self.user_service.get_user(user_id)


# 4. Start application

@configure(user_packages=["__main__"], server_port=8080)
@application
def main(): ...
```

**Execution Flow**:
```
Request arrives
  ↓
CorsMiddleware (priority=10)
  ↓
AuthMiddleware (priority=50) 
  ↓
LoggingMiddleware (priority=100)
  ↓
UserController.get_user()
  ↓
LoggingMiddleware (response, reverse order)
  ↓
AuthMiddleware (response, reverse order)
  ↓
CorsMiddleware (response, reverse order)
  ↓
Response sent
```

---

## Backward Compatibility

Manual registration is still supported:

```python
from cullinan.web.middleware import Middleware, get_middleware_registry

class MyMiddleware(Middleware):
    def process_request(self, handler):
        return handler

# Manual registration
registry = get_middleware_registry()
registry.register(MyMiddleware, priority=100)
```

**Both methods can be used together**, and the framework will automatically sort by priority.

---

## Extension Point Categories

The framework provides 6 major extension point categories:

1. **Middleware**
   - `Middleware.process_request`
   - `Middleware.process_response`

2. **Lifecycle**
   - `on_post_construct`
   - `on_startup`
   - `on_shutdown`
   - `on_pre_destroy`

3. **Injection**
   - `custom_scope`
   - `custom_provider`

4. **Routing**
   - `custom_handler`

5. **Configuration**
   - `config_provider`

6. **Handler**
   - Custom Route Handler

---

## FAQ

### Q1: What happens when middleware returns None?

A: Returning `None` short-circuits the chain, skipping subsequent middleware and handlers:

```python
def process_request(self, handler):
    if not_authorized:
        handler.set_status(401)
        handler.finish({"error": "Unauthorized"})
        return None  # Short-circuit, stop processing
    return handler  # Continue to next middleware
```

### Q2: How to view middleware execution order?

A: Use the registry query:

```python
from cullinan.web.middleware import get_middleware_registry

registry = get_middleware_registry()
for mw in registry.get_registered_middleware():
    print(f"{mw['priority']}: {mw['name']}")
```

### Q3: Can middleware be registered dynamically?

A: Yes, but it's recommended to complete registration before application startup:

```python
# Register before startup
registry = get_middleware_registry()
registry.register(DynamicMiddleware, priority=150)

# Then start the application
run()
```

### Q4: Does middleware affect performance?

A: Decorator registration overhead is minimal (~1μs), with no runtime overhead. Middleware performance depends on your implementation logic.

---

## Further Reading

- **Example Code**: `examples/extension_registration_demo.py`
- **Extension Development Guide**: `docs/extension_development_guide.md`
- **Middleware Details**: `docs/wiki/middleware.md`

---

## Feedback & Support

For questions or suggestions:
1. Check example code: `examples/extension_registration_demo.py`
2. Submit an Issue or PR to the project repository
