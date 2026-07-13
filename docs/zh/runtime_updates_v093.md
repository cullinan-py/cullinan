title: "运行时整合概览"
slug: "runtime-updates-v093"
module: []
tags: ["release", "architecture", "testing"]
author: "Cullinan"
reviewers: []
status: updated
locale: zh
translation_pair: "docs/runtime_updates_v093.md"
related_tests: ["tests/core/test_application_model_refactor.py", "tests/integration/test_adapter_integration.py", "tests/web/test_web_runtime.py", "tests/di/test_core_constructor_injection.py"]
related_examples: []
estimate_pd: 1.0
last_updated: "2026-06-01T00:00:00Z"
pr_links: []

# 运行时整合概览

本文汇总当前代码库与文档已落地的四次主要更新。

> **历史总结页：** 这页用于解释发生了哪些变化，不属于新应用的默认入门路径。

## 1. IoC/DI 整合

当前容器模型以 `ApplicationContext` 为中心，并通过 `cullinan.core` 作为公开入口。

### 变更内容

- `cullinan.core` 成为容器、生命周期与上下文 API 的公开门面
- `ApplicationContext.refresh()` / `shutdown()` 成为主要生命周期转换点
- `cullinan.core.container.*` 下的兼容模块现在转发到同一套核心实现
- 旧构造器注入辅助 API 仅保留兼容意义，不再是推荐模型

### 当前应使用

- `@service`、`@controller`
- `Inject()` 与 `InjectByName()`
- 需要显式注册或做集成时直接使用 `ApplicationContext`

## 2. Application-first 运行时

Cullinan 现在把显式运行时编排放在 `cullinan.application` 中，
并把最短公开启动路径通过顶层 `cullinan` 重新导出。

### 变更内容

- `Application.run(...)` 会构建、校验、预热并激活声明的根模块
- `@module` 用于声明模块导入、包归属、warmup hooks 与 health checks
- 组件发现会从装饰器元数据重建待注册项，而不再依赖一次性的导入时机
- 当旧 runtime 进入 draining 时，`Application.current()` 会优先返回请求绑定的应用快照

### 迁移含义

新的启动代码应优先使用 `from cullinan import application, configure`，然后直接调用装饰后的入口方法。
底层容器编排仍可直接使用 `ApplicationContext`；当你明确需要显式运行时编排时，
再进入 `cullinan.application`，而不是把它当成默认开发者路径。

## 3. Web Runtime 整合

Web 栈已围绕 `cullinan.web.gateway` 中的传输无关运行时完成重组。

### 变更内容

- `WebRequest`、`WebResponse`、`WebAdapter` 定义了当前公开 HTTP 抽象
- `Router`、`Dispatcher`、`MiddlewarePipeline`、`ExceptionHandler` 统一经由 gateway 门面暴露
- `cullinan.web.gateway.web_core` 承载共享请求/响应模型
- 适配器独立在 `cullinan.transport.adapter` 中（`TornadoAdapter`、`ASGIAdapter`）
- 运行后端选择现在采用引擎中立的 `auto` / `asgi` / `tornado`，而不再把 Tornado 作为默认的应用叙事

### 迁移含义

新代码应直接使用统一后的 Web Runtime 名称；旧的 request / response / adapter 名称不再是主要公开接口。

## 4. 测试体系对齐

仓库测试工作流仍在向 pytest 收敛，而新的 application-model 与 adapter 覆盖
已经进入常规可收集测试。

### 变更内容

- 唯一正式入口：`.venv\Scripts\python -m pytest`
- 测试发现规则由 `pytest.ini` 统一定义
- `tests/` 下按主题组织测试
- 新增和刷新后的覆盖统一使用 `tests/core`、`tests/integration` 下的 pytest 测试
- 示例回归与公开边界覆盖现在也都进入常规 pytest 套件

### 当前目录

- `tests/core`
- `tests/di`
- `tests/web`
- `tests/integration`
- `tests/regression`
- `tests/compat`

## 后续阅读

- [架构设计](architecture.md)
- [应用运行时模型](wiki/application_runtime.md)
- [依赖注入指南](dependency_injection_guide.md)
- [Web Runtime 指南](web_runtime_guide.md)
- [测试与验证](testing.md)
