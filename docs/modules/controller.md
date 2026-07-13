title: "cullinan.web.controller"
slug: "modules-controller"
module: ["cullinan.web.controller"]
tags: ["api", "module", "controller"]
author: "Cullinan"
reviewers: []
status: updated
locale: en
translation_pair: "docs/zh/modules/controller.md"
related_tests: ["tests/web/test_handler_module.py", "tests/web/test_web_runtime.py"]
related_examples: []
estimate_pd: 1.0
last_updated: "2026-05-30T00:00:00Z"
pr_links: []

# cullinan.web.controller

`cullinan.web.controller` contains the controller decorator plus REST-style route decorators and compatibility registries.

## Main exports

- `controller`
- `get_api`
- `post_api`
- `patch_api`
- `delete_api`
- `put_api`
- `response_build`

Compatibility and advanced exports:

- `get_controller_registry()`
- `reset_controller_registry()`
- `get_header_registry()`
- `Handler`
- `HttpResponse`
- `StatusResponse`

## Example

```python
from cullinan.web.controller import controller, get_api
from cullinan.web.params import Path

@controller(url="/users")
class UserController:
    service: UserService  # constructor injection

    @get_api(url="/{user_id}")
    async def get_user(self, user_id: int = Path()):
        return {"id": user_id}
```

New applications should treat controllers as part of the unified `ApplicationContext`-driven runtime, not as a standalone registry system.

## See also

- [RESTful API wiki](../wiki/restful_api.md)
- [Web Runtime Guide](../web_runtime_guide.md)
