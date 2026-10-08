title: "应用生命周期"
slug: "wiki-lifecycle"
module: ["lifecycle"]
tags: ["wiki", "lifecycle"]
author: "plumeink"
reviewers: []
status: updated
locale: zh
translation_pair: "docs/wiki/lifecycle.md"
related_tests: ["tests/core/test_application_model_refactor.py", "tests/integration/test_service_lifecycle_integration.py"]
related_examples: []
estimate_pd: 1.0
last_updated: "2026-05-31T00:00:00Z"
pr_links: []

# 应用生命周期

Cullinan 的生命周期现在通常由当前活动的 `Application` 驱动；它会装配并持有
一个 `ApplicationContext` 和一个 `WebRuntime`。

## 主要阶段

1. **发现模块** —— `Application.run()` 收集根模块图及其声明的包归属
2. **装配运行时** —— 创建 `ApplicationContext` 与 `WebRuntime` 候选实例
3. **校验与预热** —— 执行健康检查、`refresh()`、router/dispatcher 绑定与 warmup hooks。开启 `configure(strict_assembly=True)` 时，「已声明但未装配」的差集会在 `refresh()` 内升级为失败；否则仅作报告
4. **激活** —— 原子切换活动运行时，并让旧运行时进入 draining
5. **处理请求** —— request scope 与中间件围绕请求绑定的应用快照运行
6. **Drain 与关闭** —— 待飞行中的请求完成后，旧上下文执行 shutdown，运行时关闭

## 生命周期钩子

受管组件可实现：

- `on_post_construct()`
- `on_startup()`
- `on_shutdown()`
- `on_pre_destroy()`

同样支持 `_async` 后缀的异步版本。

## 顺序控制

若组件必须先于其他组件启动或延后关闭，可实现 `get_phase()`。较低 phase 会更早启动、但在关闭时更晚执行。

## 请求作用域

request scope 依赖绑定到当前请求上下文。适配器会在分发前把活动 runtime
绑定到请求上下文，并在分发结束后释放。运行时切换期间，`Application.current()` 会在
该请求结束前持续返回请求绑定的应用快照。

## Reload 与 draining

`Application.reload()` 会先构建新的候选运行时，只有在校验与预热成功后才切换为
活动运行时。旧运行时会进入 `DRAINING`，继续服务已有请求，并在请求计数归零后
真正关闭。

在**正在运行的事件循环内**关闭是另一条路径。同步的
`ApplicationContext.shutdown()` 用阻塞式休眠等待在飞请求作用域，若在事件循环上
执行，就会**饿死**它正在等待的那些请求。因此它会检测到运行中的事件循环并**跳过**
阻塞等待，且以 `WARNING` 级别**如实报出**这次跳过，而不是静默处理。已经在事件循环
上的调用方应改用 `await ApplicationContext.ashutdown()`（或
`await ApplicationContext.await_drained(timeout)`），它会**让出控制权**，使在飞请求
得以真正完成。两条路径共用**同一个**超时来源 `WebRuntimeConfig.drain_timeout`。

`shutdown()` 与 `ashutdown()` 都会**返回**本次排空是否在时限内完成 —— 调用方无需翻日志
即可区分「干净排空」与「超时放弃」。

### 排空期间的 readiness

框架**刻意不内置**健康路由：路由属于应用自己，内置一条会与你的路由冲突。它提供的是
**机制**，且与其他生命周期钩子保持**同一种普通可调用对象**的写法：

- `ApplicationContext.accepts_requests` —— 一个开销极小的谓词，**进入排空那一刻起即为
  `False`**（`Application.accepts_requests` 是同一个读法）；
- `ApplicationContext.add_draining_handler(callback)` —— 普通回调（同步或异步均可），
  在**进入排空时触发一次**，与 `add_shutdown_handler` 同构。

于是探针就是你自己的几行代码，接进你现有的部署方式即可：

```python
from cullinan.application import Application

readiness = {"ready": True}
Application.current().add_draining_handler(lambda: readiness.update(ready=False))

# 若不想持有状态，直接用谓词也可以：
#     ready = Application.current().accepts_requests
```

在 Kubernetes 下，订阅一次并让 `readinessProbe` 失败，即可**在等待在飞请求之前**先摘掉
流量 —— 与 Spring Boot 在 `doClose()` 起始翻转 readiness 得到的**顺序相同**，但**不需要**
管理端口或端点分组。

## 中间件桥接

应用启动阶段可把旧式 middleware 注册桥接进 gateway pipeline，使历史模块仍能参与请求处理，而新代码统一走 Web Runtime。

## 装配持有清单与引导边界

应用预热会跨越一道引导边界：gateway globals —— pipeline、router、dispatcher 与
exception handler —— 在此处被重置并重建。因此，任何在边界**之前**注册到这些面上的条目，都不属于正在运行的应用。

`Application.get_assembly_snapshot()` 报告装配之后实际持有什么 —— 四个 gateway 面加上容器，
每个面都是一组 `declared` / `assembled` / `dropped` 三态 —— 于是被边界丢弃的预引导条目会与生效集
**并列**出现，而不是凭空消失。它是 `get_declaration_diff()` 的面级对应物，详见
[框架语义 §12](../framework_semantics.md)。pipeline 面的行为更严格：预引导注册会**拒绝启动**而非被丢弃，
详见[中间件](middleware.md)。

## 另见

- [IoC 与 DI](injection.md)
- [应用运行时模型](application_runtime.md)
- [Web Runtime 指南](../web_runtime_guide.md)
