# 迁移指南: v0.9x → v0.93

> **Cullinan 框架** — 从 v0.9x 升级到 v0.93 的完整迁移指南。

> **仅用于升级：** 这页只服务于版本迁移工作，不属于首次 onboarding。

## 变更总览

Cullinan v0.93 是一次重大架构重写，引入了以下变化：

| 特性 | v0.9x | v0.93 |
|------|-------|------|
| **HTTP 引擎** | 仅 Tornado | Tornado 或 ASGI（可配置） |
| **请求处理** | 每个 URL 一个 Handler（Servlet-per-URL） | 单分发器（Spring 风格） |
| **请求对象** | `tornado.httputil.HTTPServerRequest` | `WebRequest`（传输无关） |
| **响应对象** | `HttpResponse` + `self.write()` | `WebResponse`（工厂方法） |
| **路由** | 动态 `type('Servlet'...)` 类 | 前缀树 Router |
| **中间件** | 仅初始化，不在请求管线中 | 洋葱模型管线，处理每个请求 |
| **Tornado 依赖** | 必需 | 可选（`pip install cullinan[tornado]`） |
| **ASGI 支持** | 无 | 完整 ASGI 3.0（uvicorn/hypercorn） |
| **WebSocket** | 仅 Tornado | Tornado + ASGI |
| **OpenAPI** | 无 | 自动从路由生成 |

## 安装

```bash
# Tornado 模式
pip install cullinan[tornado]

# ASGI 模式（uvicorn）
pip install cullinan[asgi]

# 完整安装
pip install cullinan[full]
```

## 逐步迁移

### 1. 导入路径变更

保留 controller/service 侧原有导入方式，但 Web 层统一使用新的入口命名：

```python
# v0.9x — 在 v0.93 中仍然有效
from cullinan.web.controller import controller, get_api, post_api
from cullinan.core.services import service, Service
from cullinan.core import Inject

# v0.93 — 新增语义导入
from cullinan import WebRequest, WebResponse   # 统一请求/响应

# 网关层：路由、分发、中间件管线与 OpenAPI 规范
from cullinan.web.gateway import (
    Router, Dispatcher,               # 网关层
    GatewayMiddleware, CORSMiddleware,# 中间件管线
    OpenAPIGenerator,                 # OpenAPI 规范
)

# 高级 transport 集成保持显式导入
from cullinan.transport.adapter import ASGIAdapter, TornadoAdapter, WebAdapter
```

### 2. Controller 变更

#### v0.9x：Controller 方法使用 Tornado 的 `self.write()`

```python
# v0.9x — handler 直接操作 tornado 内部 API
@controller(url='/api/users')
class UserController:
    @get_api(url='/{id}')
    async def get_user(self, url_params=None):
        user_id = url_params.get('id')
        # ... 业务逻辑 ...
        return HttpResponse(body=user_data, status=200)
```

#### v0.93：Controller 方法返回 `WebResponse`

```python
# v0.93 — 传输无关，返回 WebResponse
from cullinan import WebResponse

@controller(url='/api/users')
class UserController:
    user_service: UserService = Inject()

    @get_api(url='/{id}')
    async def get_user(self, id):
        user = self.user_service.get_by_id(id)
        if not user:
            return WebResponse.error(404, "User not found")
        return WebResponse.json(user)
```

**向后兼容**：旧的 `HttpResponse` 返回类型仍然有效 — `Dispatcher` 会自动转换。

### 3. 响应对象迁移

| v0.9x | v0.93 等价写法 |
|-------|-------------|
| `HttpResponse(body=data, status=200)` | `WebResponse.json(data)` |
| `HttpResponse(body="text", status=200)` | `WebResponse.text("text")` |
| `HttpResponse(body=data, status=404)` | `WebResponse.error(404, "msg")` |
| `return {"key": "value"}`（dict） | `return {"key": "value"}`（自动 JSON，仍有效） |
| `return None` | `return None`（自动 204 No Content） |

### 4. 运行应用

#### v0.9x：仅 Tornado

```python
from cullinan.public_api import run
run()  # 旧式直接启动入口
```

#### v0.94a1：优先使用入口方法；只有在需要时再显式调用运行时 helper

```python
from cullinan import application, configure

@configure(user_packages=["myapp"])
@application
def main(): ...

main()

# 若要交给外部 ASGI 服务器，优先使用入口方法上的 helper
app = main.get_asgi_app()
# 然后：uvicorn myapp:app
```

环境变量：`CULLINAN_ENGINE=asgi`，或配置：`server_engine='auto'` / `'asgi'` / `'tornado'`。

### 5. 配置变更

```python
from cullinan import configure

configure(
    user_packages=['myapp'],
    # v0.93 新增选项：
    # server_engine='auto',           # 'auto'、'tornado' 或 'asgi'
    # asgi_server='uvicorn',          # 'uvicorn' 或 'hypercorn'
    # route_trailing_slash=False,
    # route_case_sensitive=True,
    # debug=False,
)
```

### 6. 中间件迁移

#### v0.9x：中间件注册但未接入请求管线

```python
from cullinan.web.middleware import Middleware, middleware

@middleware(order=1)
class AuthMiddleware(Middleware):
    def process_request(self, request):
        # 启动时初始化，但不会在每个请求中调用
        pass
```

#### v0.93：中间件在洋葱管线中

```python
from cullinan.web.gateway import GatewayMiddleware, get_pipeline

class AuthMiddleware(GatewayMiddleware):
    async def __call__(self, request, call_next):
        token = request.get_header('Authorization')
        if not token:
            return WebResponse.error(401, "Unauthorized")
        response = await call_next(request)
        return response

# 注册
get_pipeline().add(AuthMiddleware())
```

**向后兼容**：旧的 `@middleware` 类仍会被自动桥接进 gateway pipeline —— 每个遗留中间件各成一层。

#### v0.96a1：遗留中间件纳入声明式排序

过去，旧的 `@middleware` 类会被折叠成**单个**桥接层，且始终位于内置 access log 层**内侧**，因此遗留 `priority` 无法移动它 —— 该优先级只在遗留链**内部**排序，从不跨越桥接边界。现在每个遗留中间件各自成为一个管线层，并与声明层、内置层共用同一个声明式 `priority` 键排序，因此一个较低的遗留 `priority` 现在可以把遗留中间件放到内置层**外侧**。

**受影响者界定。** 只有使用旧中间件协议（`@middleware(priority=...)` / `cullinan.web.middleware`）的应用才会受影响，且仅在以下情形可见变化：某个遗留中间件声明的优先级**不等于**默认值 `100`，或某个遗留层与声明了自身优先级的 `configure(middlewares=[...])` 条目发生交互。

| 场景 | 变更前（外 → 内） | 变更后（外 → 内） | 是否可见变化 |
|---|---|---|---|
| 未声明 priority（默认 `100`） | 内置 access log、遗留 | 内置 access log、遗留 | 否 |
| 遗留 `priority` 小于 `100`（如 `50`） | 内置 access log、遗留 | 遗留、内置 access log | **是** —— 遗留层现在包裹内置层 |
| 遗留 `priority` 大于 `100`（如 `150`） | 内置 access log、遗留 | 内置 access log、遗留（更靠内） | 否 |
| 两个同 `priority` 的遗留并列项（如都用默认 `100`） | 内置 access log、并列项按声明序 | 内置 access log、并列项按声明序 | 否 —— 并列序保持声明序 |

遗留中间件**彼此之间**的相对顺序不变，请求/响应的展开顺序也不变。唯一变化的是「声明了低于内置层 `100` 的 priority」的那一层的位置：它现在包裹内置层，而不是被内置层包裹。

**`priority` 在何处决定顺序。** 只有当两个遗留中间件的 `priority` **不同**时，`priority` 键才决定它们的相对顺序；此时顺序由声明的 priority 取值决定，与二者谁先注册无关。当两个遗留中间件声明**相同** `priority` 时，它们互为并列项，并列项之间的顺序由**声明序**破平 —— 即它们通过 `@middleware` 注册 / 被导入的先后顺序。在同一模块内这就是源码顺序，因此解析结果是确定性的：同一组声明总是得到同一顺序。若要摆脱对声明序的依赖，请给同 `priority` 的并列项显式声明不同的 `priority`。

**迁移动作。** 多数应用**无需改动** —— 使用默认优先级时解析顺序完全一致。仅当你**依赖**整条遗留链始终位于内置层内侧、并**曾以为**遗留 `priority` 无法跨越桥接边界时，才需要复核你声明的 `priority` 取值，确认新位置符合预期。

**自省面。** `cullinan.web.gateway.get_pipeline().list_middleware()` 现在按遗留中间件**逐个**列出条目 —— 条目数由**单个桥接条目变为每个已注册中间件各一条** —— 且每条以**真实中间件**命名（而非桥接名），因此解析后的顺序可直接读取。

内置层同样是声明式的：`configure(builtin_middleware=[...])` 可替换它，`configure(builtin_middleware=[])` 可关闭它。

### 7. OpenAPI 集成

```python
from cullinan.web.gateway import OpenAPIGenerator, get_router

# 从所有已注册路由自动生成规范
gen = OpenAPIGenerator(
    title='My API',
    version='1.0.0',
    description='我的 API',
)

# 注册 /openapi.json 和 /openapi.yaml 端点
gen.register_spec_routes()

# 或以编程方式获取规范
spec_dict = gen.to_dict()
json_str = gen.to_json()
```

### 8. WebSocket 变更

#### v0.9x：仅 Tornado WebSocket

```python
@websocket_handler(url='/ws/chat')
class ChatHandler:
    def on_open(self):
        pass
    def on_message(self, message):
        self.write_message(f"echo: {message}")
    def on_close(self):
        pass
```

#### v0.93：相同 API，同时支持 Tornado 和 ASGI

`@websocket_handler` API 不变。在 ASGI 模式下运行时，WebSocket 连接通过 ASGI WebSocket 协议原生处理。

### 9. 参数系统

`cullinan.web.params` 系统（`Path`、`Query`、`Body`、`Header`）不变，在 v0.93 中工作方式完全相同。参数现在由 `Dispatcher` 而非 Tornado handler 解析。

## 架构对比

### v0.9x 架构

```
请求 → Tornado → 动态 Handler(每个URL) → Controller 方法 → self.write()
```

### v0.93 架构

```
请求 → 适配器(Tornado/ASGI) → WebRequest → 中间件管线
  → Dispatcher → Router → Controller 方法 → WebResponse
  → 适配器 → 原生响应
```

## 破坏性变更

1. **`tornado` 不再是必需依赖** — 如果需要请使用 `pip install cullinan[tornado]` 安装。
2. **`Handler` 基类** 已弃用 — controller 不再继承 `tornado.web.RequestHandler`。
3. **直接使用 Tornado API**（controller 中的 `self.set_status()`、`self.write()`、`self.finish()`）已弃用 — 请使用 `WebResponse` 代替。

## 弃用时间表

| 项目 | v0.93 状态 | 计划移除 |
|------|----------|---------|
| `Handler` 类 | 弃用（警告） | 弃用窗口结束时 |
| `HttpResponse` | 弃用（自动桥接） | 弃用窗口结束时 |
| `EncapsulationHandler.add_url()` | 仅内部使用 | 弃用窗口结束时 |
| controller 中的 `self.write()` | 弃用 | 弃用窗口结束时 |
| 旧中间件（`Middleware` 基类） | 自动桥接 | 弃用窗口结束时 |

移除版本不手工书写，而是由框架版本与固定的弃用窗口（`当前 minor + N`）推导，因此本表不会与代码上报的版本发生漂移。
