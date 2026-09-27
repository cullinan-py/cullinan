title: "cullinan.web.controller"
slug: "modules-controller"
module: ["cullinan.web.controller"]
tags: ["api", "module", "controller"]
author: "plumeink"
reviewers: []
status: updated
locale: zh
translation_pair: "docs/modules/controller.md"
related_tests: ["tests/web/test_handler_module.py", "tests/web/test_web_runtime.py"]
related_examples: []
estimate_pd: 1.0
last_updated: "2026-05-30T00:00:00Z"
pr_links: []

# cullinan.web.controller

`cullinan.web.controller` 包含控制器装饰器、REST 风格路由装饰器以及兼容层 registry API。

## 主要导出

- `controller`
- `get_api`
- `post_api`
- `patch_api`
- `delete_api`
- `put_api`
- `response_build`

兼容与高级导出：

- `get_controller_registry()`
- `reset_controller_registry()`
- `get_header_registry()`
- `Handler`
- `HttpResponse`
- `StatusResponse`

## 示例

```python
from cullinan.web.controller import controller, get_api
from cullinan.web.params import Path

@controller(url="/users")
class UserController:
    service: UserService  # ← 构造注入

    @get_api(url="/{user_id}")
    async def get_user(self, user_id: int = Path()):
        return {"id": user_id}
```

新应用应把 Controller 视为统一 `ApplicationContext` 运行时的一部分，而不是独立 registry 系统。

## 另见

- [RESTful API wiki](../wiki/restful_api.md)
- [Web Runtime 指南](../web_runtime_guide.md)
