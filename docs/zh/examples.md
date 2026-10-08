title: "示例与指引"
slug: "examples"
module: []
tags: ["examples"]
author: "plumeink"
reviewers: []
status: updated
locale: zh
translation_pair: "docs/examples.md"
related_tests: ["tests/integration/test_examples_public_guides.py"]
related_examples: ["examples/minimal_app", "examples/controller_service_inject", "examples/middleware_and_module", "examples/middleware_pipeline", "examples/middleware_control", "examples/parameter_handling", "examples/testing_flow"]
estimate_pd: 1.5
last_updated: "2026-06-01T00:00:00Z"
pr_links: []

# 示例与指引

本页是仓库内可运行示例的正式导航入口。现在唯一的示例代码主入口是项目根目录
`examples/`，而不是 `docs/examples/`，也不再是早期的单文件 demo。

> **推荐心智：** 先写装饰器式业务代码，用 `@application` 声明入口方法，再用 `@configure(...)` 附着启动配置，
> 然后直接调用 `main()` 完成运行时装配。<br>
> **延伸阅读：** [快速开始](getting_started.md)、[构建与运行](build_run.md)、
> [参数系统指南](parameter_system_guide.md)、[测试与验证](testing.md)

## 推荐阅读顺序

1. `examples/minimal_app/` —— 最短公开入口
2. `examples/controller_service_inject/` —— `@service`、`@controller` 与 `Inject()` 的业务分层
3. `examples/middleware_and_module/` —— 什么时候值得在入口方法之上再显式引入 `@module`
4. `examples/middleware_pipeline/` —— 通过 `@configure(middlewares=[...])` 声明中间件顺序
5. `examples/middleware_control/` —— 替换/关闭内置中间件层，并统一旧式中间件的排序
6. `examples/middleware_ownership/` —— 中间件的两种声明写法，以及各自实例的归属
7. `examples/parameter_handling/` —— `Path`、`Query`、`Body` 的控制器方法参数绑定
8. `examples/testing_flow/` —— 不启动真实服务进程时通过 `main.get_asgi_app()` 做测试
9. `examples/assembly_snapshot/` —— 逐面读回本次装配实际持有什么（高级 / 边界）

## 示例地图

| 示例 | 主要讲什么 | 运行命令 | 源码 |
| --- | --- | --- | --- |
| `examples/minimal_app/` | 使用 `@application + @configure(...) + main()` 组织最小应用 | `python -m examples.minimal_app` | [在 GitHub 查看](https://github.com/cullinan-py/cullinan/tree/main/examples/minimal_app) |
| `examples/controller_service_inject/` | `service/controller` 分层与类型驱动的 `Inject()` 注入 | `python -m examples.controller_service_inject` | [在 GitHub 查看](https://github.com/cullinan-py/cullinan/tree/main/examples/controller_service_inject) |
| `examples/middleware_and_module/` | 模块边界归属与兼容版中间件协议 | `python -m examples.middleware_and_module` | [在 GitHub 查看](https://github.com/cullinan-py/cullinan/tree/main/examples/middleware_and_module) |
| `examples/middleware_pipeline/` | 通过 `@configure(middlewares=[...])` 声明中间件顺序 + 公开反射 API | `python -m examples.middleware_pipeline` | [在 GitHub 查看](https://github.com/cullinan-py/cullinan/tree/main/examples/middleware_pipeline) |
| `examples/middleware_control/` | 通过 `builtin_middleware=[...]` 控制内置中间件层，并统一旧式中间件的排序 | `python -m examples.middleware_control` | [在 GitHub 查看](https://github.com/cullinan-py/cullinan/tree/main/examples/middleware_control) |
| `examples/middleware_ownership/` | 中间件的两种声明写法：`@component` 类条目（容器托管）与实例条目（外部持有） | `python -m examples.middleware_ownership` | [在 GitHub 查看](https://github.com/cullinan-py/cullinan/tree/main/examples/middleware_ownership) |
| `examples/parameter_handling/` | 控制器方法上的 `Path`、`Query`、`Body` | `python -m examples.parameter_handling` | [在 GitHub 查看](https://github.com/cullinan-py/cullinan/tree/main/examples/parameter_handling) |
| `examples/testing_flow/` | 基于公开 API 的 ASGI 测试流 | `python -m pytest examples/testing_flow/test_app.py -q` | [在 GitHub 查看](https://github.com/cullinan-py/cullinan/tree/main/examples/testing_flow) |
| `examples/static_files_and_spa/` | 声明式 `StaticFiles` 挂载 + SPA 回退（引擎中立） | `python -m examples.static_files_and_spa` | [在 GitHub 查看](https://github.com/cullinan-py/cullinan/tree/main/examples/static_files_and_spa) |
| `examples/assembly_snapshot/` | 装配快照：一次调用取得四个 gateway 子面 + 容器面的 `declared` / `assembled` / `dropped`（高级 / 边界） | `python -m examples.assembly_snapshot` | [在 GitHub 查看](https://github.com/cullinan-py/cullinan/tree/main/examples/assembly_snapshot) |

## 为什么要重构示例

旧示例容易把开发者带回“手工注册 app”的思路。新的示例集刻意把
Cullinan 当前想表达的概念放在最前面：

- 业务装饰器优先，而不是显式 app 装配优先
- 先用入口方法表达默认入口
- 当结构和归属重要时，再显式引入 `@module` 表达运行时边界
- 类型契约清晰时，默认优先使用 `Inject()`
- 把参数绑定写在控制器方法上，而不是先教底层 request plumbing
- 通过公开 API 做测试，而不是依赖内部启动捷径

## 补充说明

- 根目录 `examples/README.md` 会同步这条学习链路，方便直接看仓库的开发者。
- 推荐入口形态是**方法**：`@application` + `@configure(...)` + `main()`。少数示例
  （`examples/component_discovery_boundary/`、`examples/assembly_snapshot/`）会直接构造
  高级入口类 `cullinan.application.Application` —— 它们需要在不启动服务器的前提下拿到
  应用**对象** —— 这些示例在 `examples/README.md` 及其自身 README 中均标注为
  **高级 / 边界**。推荐示例不会把 `Application` 当作默认入口来教。
- 也可以直接从 [`examples/`](https://github.com/cullinan-py/cullinan/tree/main/examples) 浏览已入库的示例源码。
- `tests/integration/test_examples_public_guides.py` 会对当前维护的示例做 smoke test。
- 中间件有多个维护中的示例：`examples/middleware_pipeline/` 使用推荐的洋葱协议，
  `examples/middleware_ownership/` 展示两种声明写法及其对象归属，
  而 `examples/middleware_and_module/` 使用兼容协议。详见[中间件](wiki/middleware.md)。
- 如果你第一次接触 Cullinan，建议先完成 `examples/minimal_app/`，再进入
  `examples/controller_service_inject/`。
