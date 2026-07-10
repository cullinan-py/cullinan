title: "cullinan.core.services"
slug: "modules-service"
module: ["cullinan.core.services"]
tags: ["api", "module", "service"]
author: "Cullinan"
reviewers: []
status: updated
locale: en
translation_pair: "docs/zh/modules/service.md"
related_tests: ["tests/integration/test_service_lifecycle_integration.py"]
related_examples: []
estimate_pd: 1.0
last_updated: "2026-05-30T00:00:00Z"
pr_links: []

# cullinan.core.services

`cullinan.core.services` holds the advanced service base class and registry helpers. For most application code, import `@service` and dependency markers from `cullinan.core`.

## Main exports

- `service`
- `Service`
- `Inject`
- `InjectByName`
- `Lazy`

Compatibility registry exports:

- `ServiceRegistry`
- `get_service_registry()`
- `reset_service_registry()`

## Example

```python
from cullinan.core.services import Service, service

@service
class UserService(Service):
    repo: UserRepository  # constructor injection

    def get_user(self, user_id: int):
        return self.repo.find_by_id(user_id)
```

For most code, use `@service` plus dependency markers and let the active `ApplicationContext` manage creation and lifecycle.

## See also

- [Dependency Injection Guide](../dependency_injection_guide.md)
- [Application Lifecycle](../wiki/lifecycle.md)
