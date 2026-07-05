# Cullinan 框架架构

> **版本**：0.94a1
> **最后更新**：2026-06-01  
> **状态**：已更新

> **这页用于解释框架结构，不是默认启动教程。**  
> 推荐启动路径请先看 [应用构建](start/index.md)；若你明确需要更深的运行时细节，再进入
> [运行时与扩展](internals/index.md)。

## 概览

Cullinan 是一个引擎中立的应用框架，当前运行时围绕三条已经整合完成的主线组织：

1. **统一容器门面** —— `cullinan.core` 是公开的 IoC/DI 入口。
2. **传输无关的 Web Runtime** —— `cullinan.web.gateway` 承载 `WebRequest`、`WebResponse`、路由、分发、中间件与异常处理。
3. **装饰器优先的运行时装配** —— 应用代码先从业务装饰器出发，运行时边界、热插拔与稳定性能力按需叠加。

## 架构分层

```text
应用代码
├── @service / @controller / @component
├── 使用 get_api/post_api/... 的控制器方法
└── 业务服务与中间件

框架门面
├── cullinan             -> @application、configure、业务向装饰器
├── cullinan.application -> Application、run/get_asgi_app、@module
├── cullinan.web         -> 控制器装饰器、WebRequest/WebResponse、参数系统、中间件
├── cullinan.core        -> ApplicationContext、作用域、生命周期、请求上下文
├── cullinan.testing     -> 测试辅助与验证入口
├── cullinan.runtime     -> 发现、扫描、运行时装配
└── cullinan.transport   -> WebAdapter、TornadoAdapter、ASGIAdapter

运行时执行
├── 装饰器声明 -> 导入执行发现 -> 运行时装配
├── ApplicationContext.refresh()
├── Gateway pipeline + dispatcher
├── 适配器层请求/响应转换
└── ApplicationContext.shutdown()
```

## 语义化包结构

Cullinan 现在按更像正式 Web Framework 的语义层公开主结构：

- `cullinan` —— 默认启动入口（`@application`、`configure`，然后直接调用入口方法）
- `cullinan.application` —— 应用定义、运行时边界与显式运行时 helper 等高级语义
- `cullinan.web` —— 面向业务开发者的 Web 公开层
- `cullinan.core` —— IoC/DI、生命周期、请求上下文、语义诊断
- `cullinan.testing` —— 测试辅助
- `cullinan.runtime` —— 自动发现、扫描、运行时装配内部机制
- `cullinan.transport` —— 服务端适配边界
- `cullinan.support` —— 受约束的支撑能力，不是默认第一入口

这种分层让默认路径保持业务优先，同时也让维护者与高级使用者在需要时有清晰下探层。像 `cullinan.app`、`cullinan.public_api` 这类历史根层 wrapper 已不再属于维护中的正式结构。

## 核心容器模型

`cullinan.core` 暴露公开容器 API。`ApplicationContext` 是注册、解析、refresh 与 shutdown 的唯一运行时入口。

### 主要职责

- 注册依赖定义
- 解析 singleton / prototype / request 作用域实例
- 在 `refresh()` 与 `shutdown()` 期间驱动生命周期钩子
- 保存框架集成使用的当前活动应用上下文

### 公开流程

```python
from cullinan.core import ApplicationContext, set_application_context

ctx = ApplicationContext()
set_application_context(ctx)

# 新应用代码先从装饰器声明和运行时装配出发；
# 显式 Definition 注册保留给底层集成场景
ctx.refresh()
...
ctx.shutdown()
```

旧的 `cullinan.core.container.*` 模块现在仅保留为薄转发层，不再维护独立状态。

## 依赖注入与生命周期

装饰器层（`@service`、`@controller`、`Inject`、`InjectByName`）最终都归并到统一容器模型。

### 推荐用法

- 普通业务代码优先使用 `@service` 和 `@controller`
- 字段注入优先使用 `Inject()` 以获得类型安全
- 需要按名称解析或规避循环导入时使用 `InjectByName()`
- 自定义工厂或第三方集成场景直接使用 `ApplicationContext`

### 生命周期钩子

所有受管组件共享同一套生命周期约定：

- `on_post_construct()`
- `on_startup()`
- `on_shutdown()`
- `on_pre_destroy()`

支持追加 `_async` 的异步版本；可通过 `get_phase()` 影响执行顺序。

## Web Runtime

当前 Web 栈以 `cullinan.web.gateway.web_core` 为核心，但推荐给业务开发者的公开入口现在收敛到 `cullinan.web`。

### 公开运行时对象

- `WebRequest` —— 标准化请求对象
- `WebResponse` —— 可在写回前冻结的响应构建器
- `Router` —— 路由注册与匹配
- `Dispatcher` —— 请求分发与返回值处理
- `MiddlewarePipeline` —— 洋葱模型中间件链
- `ExceptionHandler` —— 异常到响应的转换器
- `WebRuntime` —— 活动运行时状态与切换控制

### 适配器边界

服务器集成通过 `cullinan.transport` 暴露，并由底层 `cullinan.transport.adapter` 实现：

- `WebAdapter` —— 公共适配器协议
- `TornadoAdapter` —— Tornado 集成
- `ASGIAdapter` —— ASGI 集成

这种分层让请求处理逻辑不再绑定单一服务器实现。

## 请求流程

1. 业务代码用装饰器声明服务、控制器与处理方法。
2. 运行时装配阶段导入受管 Python 模块，并依据装饰器元数据重建注册项。
3. `ctx.refresh()` 解析 eager 组件并执行启动钩子。
4. Gateway pipeline 接收已归一化的 `WebRequest`。
5. `Dispatcher` 匹配路由、解析参数、调用处理器，并生成 `WebResponse`。
6. 具体适配器把响应写回 Tornado 或 ASGI。

现在默认应以“**先理解框架语义，再理解运行后端**”来阅读 Cullinan：应用代码对接的是 Cullinan 自身的请求/响应、控制器、参数、中间件与生命周期模型，而 Tornado 与 ASGI 则退到适配器边界之后，作为执行后端存在。
7. 关闭阶段调用 `ctx.shutdown()` 并完成所有受管生命周期清理。

## 测试策略

仓库当前以 pytest 作为唯一正式测试运行器。

- 仓库正式命令：`.venv\Scripts\python -m pytest`
- 共享测试引导位于 `tests/conftest.py`
- 测试目录按主题划分：`tests/core`、`tests/di`、`tests/web`、`tests/integration`、`tests/regression`、`tests/compat`

详见 [测试与验证](testing.md)。

## 相关文档

- [运行时整合概览](runtime_updates_v093.md)
- [依赖注入指南](dependency_injection_guide.md)
- [Web Runtime 指南](web_runtime_guide.md)
- [测试与验证](testing.md)
