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

### 命令式注册（`get_pipeline().add`）

`cullinan.web.gateway.get_pipeline().add(AuditMiddleware())` 是**启动前**的命令式入口，供手工构建管线的集成使用。它写入的是应用装配**之前**就已存在的那份管线实例，而 gateway globals 会在启动边界被整体重建（`Runtime.warmup()` 会重建 pipeline、router、dispatcher、exception handler）：因此经该入口加入的条目会在**引导边界被拒绝** —— 应用不会启动。框架会**先**报告它丢弃的条目（一条诊断，给出名称与数量），**再**抛出，因此在调用方捕获异常之后，报告仍已被看到。

**支持级别。** 该命令式注册在**引导边界不受支持**：启动前的 `get_pipeline().add(...)` 会在装配期（而非首个请求）拒绝启动。`get_pipeline()` 本身保留其**运行时自省 / 高级用途 / 测试**级别的作用 —— 应用启动**之后**，`get_pipeline().list_middleware()` 会报告已安装的中间件，且不受影响。要让中间件真正参与请求处理，请使用声明式入口：`configure(middlewares=[...])` 或 `@middleware` 装饰器。

**不止是 pipeline 一道边界。** 引导边界重建的是全部四个 gateway globals，而不只是 pipeline —— 且对它们区别对待：pipeline 上的预引导注册会拒绝启动（见上文），而 router、dispatcher、exception handler 上的预引导注册会被**丢弃并留痕**，应用仍能启动。`Application.get_assembly_snapshot()` 报告每个面实际持有什么 —— 四个 gateway 面加容器，各一组 `declared` / `assembled` / `dropped` —— 于是预引导条目可在一处完成对账，而无需从日志文本里读。详见[框架语义 §12](../framework_semantics.md)与[应用生命周期](lifecycle.md)。

### 遗留：`process_request` / `process_response`

`Middleware`（从 `cullinan.web.middleware` 导入）上的钩子对仍然可用，并会被自动桥接进 gateway pipeline —— 每个遗留中间件各成一层。每个桥接层与内置层、声明层共用同一个声明式 `priority` 键排序，因此 `@middleware(priority=10)` 的遗留中间件会落在内置 access log（默认 `100`）更外层。仅用于既有集成：

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

**所有权。** 通过 `@middleware` 声明的中间件由框架容器创建，与通过 `configure(middlewares=[...])` 声明的类写法一致。你写的声明不变：`@middleware(priority=...)` 保持其语法与默认值 `100`。

## 两种声明写法与对象所有权

`configure(middlewares=[...])` 接受两种写法，二者的区别在于**实例归谁所有**：

- **实例** —— `configure(middlewares=[AuditMiddleware()])`。由应用创建对象并保留其所有权，框架原样装入该实例。这是**外部持有**（externally-owned）的中间件。
- **用 `@component` 声明的类** —— `configure(middlewares=[AuditMiddleware])`。由框架容器创建对象、注入其声明的依赖并持有它，管线运行的正是这一个实例。这是**容器托管**（container-managed）的中间件。

类写法让中间件成为一等容器参与者：像其他组件一样声明依赖，交给容器完成装配。

```python
from cullinan import component
from cullinan.web.gateway import GatewayMiddleware


@component
class AuditLog:
    def record(self, path): ...


@component
class AuditMiddleware(GatewayMiddleware):
    log: AuditLog  # 由容器注入

    async def __call__(self, request, call_next):
        self.log.record(request.path)
        return await call_next(request)
```

```python
configure(middlewares=[AuditMiddleware])    # 容器托管
configure(middlewares=[AuditMiddleware()])  # 外部持有
```

以类形式传入时，该类**必须**用 `@component` 声明。未加该声明的
`GatewayMiddleware` 类会在启动期被拒绝，抛出 `ConfigurationError`
（`error_code = "MIDDLEWARE_DECLARATION_ERROR"`）——框架从不猜测容器所有权：要么补上
`@component`，要么传入你自己持有的实例。容器托管的中间件在启动期解析依赖，因此依赖不可解析会在启动期失败，而不会推迟到首个请求。`builtin_middleware=[...]` 遵循同一规则。

## 自省

`cullinan.web.gateway.get_pipeline().list_middleware()` 按执行顺序列出已安装的中间件，其中索引 `0` 为最外层。它是 `Router.get_all_routes()` 在管线侧的对应物。

`list_middleware()` 只报告**一个**面。若要一次调用取得整个装配 —— 四个 gateway 面（`pipeline` / `router` / `dispatcher` / `exception_handler`）加容器，每个面一组 `declared` / `assembled` / `dropped` 三态 —— 请使用 `Application.get_assembly_snapshot()`，详见[框架语义 §12](../framework_semantics.md)。

## 使用建议

- 保持 middleware 轻量，把业务逻辑委托给注入的服务
- 不要把 request scope 状态保存在长生命周期 middleware 实例上
- 让 gateway pipeline 统一处理组合与顺序
- 新代码优先使用洋葱协议

## 另见

- [Web Runtime 指南](../web_runtime_guide.md)
- [应用生命周期](lifecycle.md)
