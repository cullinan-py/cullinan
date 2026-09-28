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

## 中间件桥接

应用启动阶段可把旧式 middleware 注册桥接进 gateway pipeline，使历史模块仍能参与请求处理，而新代码统一走 Web Runtime。

## 另见

- [IoC 与 DI](injection.md)
- [应用运行时模型](application_runtime.md)
- [Web Runtime 指南](../web_runtime_guide.md)
