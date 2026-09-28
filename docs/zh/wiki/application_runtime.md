title: "应用运行时模型"
slug: "wiki-application-runtime"
module: ["cullinan.application"]
tags: ["wiki", "application", "runtime", "module"]
author: "plumeink"
reviewers: []
status: updated
locale: zh
translation_pair: "docs/wiki/application_runtime.md"
related_tests: ["tests/core/test_application_model_refactor.py", "tests/core/test_decorators.py", "tests/integration/test_adapter_integration.py", "tests/core/test_strict_assembly.py"]
related_examples: []
estimate_pd: 1.0
last_updated: "2026-05-31T00:00:00Z"
pr_links: []

# 应用运行时模型

本文解释围绕 `cullinan.application` 构建的高级应用运行时模型。Cullinan 的目标体验是让开发者先围绕业务装饰器与业务方法开发，再由运行时去装配模块声明的能力，而不是手工围绕一个 app 对象逐步注册。

> **高级主题：** 常规应用应优先使用 `@application` + `@configure(...)` + `main()` 注解式入口。  
> **参考配套：** 公开 / 高级 / 兼容 API 的分层，请同时查看 [API 参考](../api_reference.md)。

对于常规应用，请优先使用 `@application` + `@configure(...)` + `main()` 注解式入口。只有在你明确需要显式运行时编排时，才应进入 `cullinan.application`。

如果你想了解哪些运行时契约现在会 warning 或直接失败，请同时阅读[框架语义规则](../framework_semantics.md)。尤其要注意：`Application.run()` 假定组件装饰器已在模块导入阶段执行，且 `refresh()` 是结构性注册的结束边界。

## 核心概念

- `Application` 持有一个根模块图、一个 `ApplicationContext` 和一个 `WebRuntime`
- `@module` 用于声明拥有的 Python 包及其结构边界，并承载 reload、draining 与热插拔运行时语义
- `Runtime` 是一个应用候选实例在校验 / 预热过程中的可变记录
- `Application.current()` 用于解析当前活动应用，并会在 draining 期间优先返回请求绑定的快照

## 典型运行时装配

```python
from cullinan import controller, get_api, module, service
from cullinan.application import Application


@service
class GreetingService:
    def greet(self) -> str:
        return "hello"


@controller(url="/api")
class GreetingController:
    greeting_service: GreetingService  # ← 构造注入

    @get_api(url="/whoami")
    def whoami(self):
        return {"message": self.greeting_service.greet()}


@module
class RootModule:
    pass


app = Application.run(RootModule)
```

这里的 `RootModule` 只是占位示例名。`Application.run()` 接受任何使用 `@module`
声明的模块类作为根模块。

## 模块图与归属解析

每个模块都可提供：

- `imports` —— 纳入根图的子模块或兄弟模块
- `packages` —— 归属于该模块的 Python 包前缀
- `ownership_overrides` —— 用于显式处理有意共享包的归属
- `warmup` / `health_checks` —— 在构建与校验阶段执行的钩子

组件归属会基于 `@service`、`@controller`、`@component`、`@provider` 捕获的装饰器元数据解析。
如果同一组件以相同深度匹配多个模块包前缀，启动会失败，直到你通过
`ownership_overrides` 显式指定归属。

## 构建与激活流程

`Application.run()` 会依次执行：

1. 发现运行时边界并导入各模块声明拥有的 Python 模块
2. 基于装饰器元数据重建待注册项
3. 装配 `ApplicationContext` 与 `WebRuntime`。导入期已声明的组件与本轮实际取到的组件之间的差集在此处对账；未开启 `configure(strict_assembly=True)` 时仅作报告。
4. 校验、`refresh()` 并完成运行时预热。开启 `configure(strict_assembly=True)` 时，上一步对账出的差集会在**这一阶段**（诊断已发出之后）升级为启动失败。
5. 原子地把新应用绑定为当前活动应用

## Reload 与 draining

`Application.reload()` 会基于同一个根模块创建新的应用候选实例。若激活成功：

1. 新运行时立即成为活动运行时
2. 旧运行时进入 `DRAINING`
3. 飞行中的请求继续持有自己的请求绑定应用快照
4. 旧运行时只有在请求计数归零后才会真正关闭

这也是为什么全局已经切换到新运行时后，某个 draining 中的旧请求里
`Application.current()` 仍可能解析到旧应用。

## 适配器与请求绑定

传输适配器（`ASGIAdapter` / `TornadoAdapter`）会在分发前把运行时绑定到当前请求上下文。
这个绑定提供了：

- 针对正确应用的 request-scoped 依赖解析
- 运行时感知控制器或中间件中的 `Application.current()`
- 旧请求尚未结束时的安全 draining

对于常规业务应用，这仍应被视为内部 transport 细节；推荐入口依然是 Cullinan 自身的 application / controller 语义。

## 何时直接使用 ApplicationContext

当你需要底层容器集成时，仍应直接使用 `ApplicationContext`。对于新的应用代码，应先从装饰器声明出发，并在需要明确运行时边界时使用 `Application` + `@module`。

## 相关文档

- [cullinan.application 模块](../modules/application.md)
- [应用生命周期](lifecycle.md)
- [组件](components.md)
