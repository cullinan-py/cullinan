title: "RESTful API"
slug: "wiki-restful-api"
module: ["controller"]
tags: ["wiki", "restful-api"]
author: "plumeink"
reviewers: []
status: updated
locale: zh
translation_pair: "docs/wiki/restful_api.md"
related_tests: ["tests/web/test_web_runtime.py"]
related_examples: []
estimate_pd: 1.5
last_updated: "2026-05-30T00:00:00Z"
pr_links: []

# RESTful API

Cullinan 当前的 REST 栈由控制器装饰器与统一后的 Web Runtime 共同组成。

## 推荐控制器写法

```python
from cullinan.web.controller import controller, get_api, post_api
from cullinan.web.params import Body, Path

@controller(url="/users")
class UserController:
    @get_api(url="/{user_id}")
    async def get_user(self, user_id: int = Path()):
        return {"id": user_id}

    @post_api(url="/")
    async def create_user(self, payload: dict = Body()):
        return {"created": True, "payload": payload}
```

普通字典、模型对象或显式 `WebResponse` 都可以作为处理器返回值。

## 当前运行时模型

- 进入框架的请求会被归一化为 `WebRequest`
- 路由匹配由 `Router` 负责
- 处理器调用由 `Dispatcher` 负责
- 输出响应统一归一化为 `WebResponse`
- 服务器集成由 `WebAdapter` 承担

## 响应控制

当需要显式控制 header、cookie 或状态码时，直接返回 `WebResponse`。

```python
from cullinan.web.gateway import WebResponse

return WebResponse.json({"ok": True}, status_code=201)
```

## 迁移说明

新代码与新文档应使用：

- `WebRequest`
- `WebResponse`
- `WebAdapter`

旧的 request / response / adapter 命名已不再是主要公开 API 面。

## 另见

- [Web Runtime 指南](../web_runtime_guide.md)
- [应用生命周期](lifecycle.md)
