title: "组件"
slug: "components"
module: ["cullinan"]
tags: ["components", "architecture"]
author: "plumeink"
reviewers: []
status: updated
locale: zh
translation_pair: "docs/wiki/components.md"
related_tests: ["tests/core/test_application_model_refactor.py", "tests/web/test_web_runtime.py", "tests/integration/test_service_lifecycle_integration.py", "tests/core/test_strict_assembly.py"]
related_examples: []
estimate_pd: 1.5
last_updated: "2026-05-31T00:00:00Z"
pr_links: []

# 组件

本文给出 Cullinan 当前主要运行时组件的高层地图。

如果你想确认自动发现与注册到底保证什么，请先看[框架语义规则](../framework_semantics.md)。简而言之：Cullinan 只保证模块导入阶段执行到的模块顶层装饰器组件，不保证稍后才创建出来的局部类定义。

## 运行时概览

### 1. 应用编排层

- 职责：模块图发现、归属解析、运行时激活、draining 与活动应用查询
- 主包：`cullinan.application`
- 关键 API：`Application`、`module`、`Application.current()`、`Runtime`

### 2. 核心容器

- 职责：依赖注册、解析、作用域、生命周期、请求上下文
- 主包：`cullinan.core`
- 关键 API：`ApplicationContext`、`Definition`、`ScopeType`、`Inject`、`InjectByName`

### 3. 服务层

- 职责：业务逻辑与受框架管理的长生命周期服务
- 主包：`cullinan.core`（`@service`），高级 `Service`/registry helper 位于 `cullinan.core.services`
- 关键 API：`service`、`Service`

### 4. 控制器层

- 职责：路由声明与处理器方法
- 主包：`cullinan.web.controller`
- 关键 API：`controller`、`get_api`、`post_api`、`response_build`

### 5. Web Runtime

- 职责：标准化请求/响应模型、路由、分发、中间件、异常处理
- 主包：`cullinan.web.gateway`
- 关键 API：`WebRequest`、`WebResponse`、`Router`、`Dispatcher`、`MiddlewarePipeline`、`WebRuntime`

### 6. 适配器层

- 职责：把 Web Runtime 绑定到具体服务器环境
- 主包：`cullinan.transport.adapter`
- 关键 API：`WebAdapter`、`TornadoAdapter`、`ASGIAdapter`
- 定位：位于 Cullinan 语义化 Web 门面之后的后端集成层

### 7. 参数与模型绑定

- 职责：把 path/query/body/header/file 输入映射为处理器参数
- 主包：`cullinan.web.params`
- 关键 API：`Path`、`Query`、`Body`、`Header`、`File`

## 已声明但未装配

发现依赖导入执行，而装配只扫描 `user_packages` 中列出的包。若某组件的装饰器已经执行（**已声明**），而它所在的包**未**被列入，它就**从未被装配**。对这份差集，Cullinan 提供两档动作：

| 动作 | 何时 | 会发生什么 |
|------|------|-----------|
| **报告**（默认） | 始终 | `Application.get_declaration_diff()` 给出 `declared` / `assembled` / `dropped`，并发出 `component-declared-not-assembled` 诊断。启动继续。 |
| **失败**（可选开启） | `configure(strict_assembly=True)` | 先发出同一诊断，随后以 `ConfigurationError` 使启动失败。 |

若某组件是有意不装配的，可以在 `configure(strict_assembly_excludes=[...])` 中列出它（写法为 `package.module.Component`）。这表示承认该意图 —— 它仍会被报告，只是不再阻断启动。

`strict_assembly` 与 `startup_error_policy` 不是同一个配置：后者针对**服务初始化**失败，而不是未装配的声明。

完整契约见[框架语义规则](../framework_semantics.md) §11。

## 建议阅读顺序

1. [架构设计](../architecture.md)
2. [应用运行时模型](application_runtime.md)
3. [框架语义规则](../framework_semantics.md)
4. [依赖注入指南](../dependency_injection_guide.md)
5. [Web Runtime 指南](../web_runtime_guide.md)
6. [测试与验证](../testing.md)
