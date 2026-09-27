title: "Middleware"
slug: "middleware"
module: ["cullinan.web.middleware"]
tags: ["middleware"]
author: "plumeink"
reviewers: []
status: updated
locale: zh
translation_pair: "docs/wiki/middleware.md"
related_tests: ["tests/web/test_web_runtime.py"]
related_examples: []
estimate_pd: 1.0
last_updated: "2026-05-30T00:00:00Z"
pr_links: []

# Middleware

Cullinan 的 middleware 现在参与统一后的 Web Runtime pipeline。

## 两种中间件协议

Cullinan 支持两种中间件协议。新代码应使用洋葱协议；基于钩子的协议为向后兼容而保留。

### 推荐：洋葱协议

继承 `cullinan.web.gateway.GatewayMiddleware` 并实现
`async def __call__(self, request, call_next)`。该中间件运行在 gateway pipeline 内部，因此既能检视、也能改写请求与响应：

```python
from cullinan.web.gateway import GatewayMiddleware


class AuditMiddleware(GatewayMiddleware):
    async def __call__(self, request, call_next):
        response = await call_next(request)
        response.set_header("X-Audited", "1")
        return response
```

通过顶层 `configure()` 入口在启动时声明中间件。管线在框架启动点统一装配，因此顺序由声明决定，而绝不由注册时机决定：

```python
from cullinan import application, configure


@configure(user_packages=["your_app"], middlewares=[AuditMiddleware()])
@application
def main(): ...
```

顺序由声明决定，而非时机。`before=` / `after=` 通过实例、类或类名把中间件锚定到另一个中间件上。`priority=` 是可选的全局键：**priority 越小越靠外层**，默认 `100` —— 与遗留的 `@middleware(priority=...)` 装饰器方向、默认值均一致。用它来声明「这一层位于最外层」：

```python
# priority 10 小于默认值 100，因此审计包装层落在最外层
configure(middlewares=[(AuditMiddleware(), {"priority": 10})])
```

完全不做声明时，最先声明的中间件保持最外层。

### 控制内置层

框架自己会装一层内置中间件 —— access log 中间件。它同样是声明式的：`configure(builtin_middleware=[...])` 可用你自己的实现替换它，`builtin_middleware=[]` 则把它整个关掉。

```python
from cullinan import application, configure
from cullinan.web.gateway import GatewayMiddleware


class MyAccessLog(GatewayMiddleware):
    async def __call__(self, request, call_next):
        response = await call_next(request)
        print(request.method, request.path, response.status_code)
        return response


# 用等效实现替换内置 access log。
@configure(user_packages=["your_app"], builtin_middleware=[MyAccessLog()])
@application
def main(): ...
```

传入空列表即可让内置层完全不进入管线：

```python
configure(user_packages=["your_app"], builtin_middleware=[])
```

省略该参数则保持框架默认，既有应用不受影响。无论内置层最终是什么，它都与 `middlewares` 参与同一套声明式排序。

### 遗留：`process_request` / `process_response`

`cullinan.web.middleware.Middleware` 上的钩子对仍然可用，并会被自动桥接进 gateway pipeline —— 每个遗留中间件各成一层。每个桥接层与内置层、声明层共用同一个声明式 `priority` 键排序，因此 `@middleware(priority=10)` 的遗留中间件会落在内置 access log（默认 `100`）更外层。仅用于既有集成：

```python
from cullinan.web.middleware import Middleware, middleware


@middleware(priority=100)
class LegacyAuditMiddleware(Middleware):
    def process_request(self, request):
        print(f"Request: {request.method} {request.path}")
```

请注意这一协议是能力受限的。只要任一遗留 `process_request` 钩子返回 `None`，该请求即被视为拒绝：遗留链在此中止，后续中间件不再执行，handler 也永远不会被触及。随后桥接层会以**固定**的错误响应替代 —— 状态码 `403`、响应体 `Request rejected by middleware`（`cullinan/web/gateway/pipeline.py:447`）。该短路响应无法通过钩子协议定制：没有任何钩子能改写状态码、响应体或响应头。遗留协议只能「放行」或「拒绝」请求，无法塑造拒绝响应本身。

如需自定义短路响应（不同状态码、JSON 响应体、额外响应头），请改用洋葱协议，在 `__call__` 中不调用 `call_next`、直接返回你自己构造的响应：

```python
from cullinan.web.gateway import GatewayMiddleware, WebResponse


class ApiKeyGate(GatewayMiddleware):
    async def __call__(self, request, call_next):
        if request.get_header("X-Api-Key") != "secret":
            # 原样返回；框架不会覆盖它
            return WebResponse.json({"error": "missing api key"}, status_code=401)
        return await call_next(request)
```

## 自省

`cullinan.web.gateway.get_pipeline().list_middleware()` 按执行顺序列出已安装的中间件，其中索引 `0` 为最外层。它是 `Router.get_all_routes()` 在管线侧的对应物。

## 使用建议

- 保持 middleware 轻量，把业务逻辑委托给注入的服务
- 不要把 request scope 状态保存在长生命周期 middleware 实例上
- 让 gateway pipeline 统一处理组合与顺序
- 新代码优先使用洋葱协议

## 另见

- [Web Runtime 指南](../web_runtime_guide.md)
- [应用生命周期](lifecycle.md)
