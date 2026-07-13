title: "cullinan.application 模块"
slug: "modules-application"
module: ["cullinan.application"]
tags: ["api", "module", "application"]
author: "Cullinan"
reviewers: []
status: updated
locale: zh
translation_pair: "docs/modules/application.md"
related_tests: ["tests/core/test_application_model_refactor.py", "tests/core/test_decorators.py", "tests/di/test_global_container_manager.py"]
related_examples: []
estimate_pd: 1.0
last_updated: "2026-05-31T00:00:00Z"
pr_links: []

# cullinan.application

`cullinan.application` 是应用定义与高级公开应用装配语义包。常规应用应优先使用更短的
顶层 `cullinan` 启动 API；但维护者和高级集成场景在需要更完整的应用模型时，仍然会落到这里：

> **高级但公开的语义层：** 这页记录的是真实语义层，不是默认首读路径。
> 新应用请优先阅读 [快速开始](../getting_started.md) 并使用顶层 `cullinan` API。

- `@application`：声明默认入口方法
- `@configure(...)`：把启动配置附着到这个方法上
- 直接调用入口方法：通过整理后的顶层 API 启动应用
- `@module`：当你需要模块归属、reload 与热插拔运行时能力时，用来声明高级结构边界
- 显式运行时 helper 位于 `cullinan.application` 与装饰后的入口方法上（如 `main.run()` / `main.get_asgi_app()`）

这里的启动契约同时依赖[框架语义规则](../framework_semantics.md)：组件发现基于导入执行、自动扫描只保证模块顶层装饰器组件、`refresh()` 之后结构性注册会被冻结。

在实际开发里，开发者主要写的是业务装饰器、业务方法和入口方法。`@module`
不是手工注册 app 的中心，而是把归属、reload、draining 与运行时切换明确化并稳定化的高级结构边界。

## 推荐启动方式

```python
from cullinan import application, configure, controller, get_api, service


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


@configure(user_packages=["myapp"])
@application
def main(): ...

if __name__ == "__main__":
    main()
```

## 什么时候使用 `@module`

普通单包应用不要一开始就写 `@module`。默认路径应先用入口方法。

当你需要以下能力时，再进入 `@module`：

- 显式包归属边界
- 多业务域之间更清晰的运行时分隔
- 可插拔模块 / 插件式装配
- 比默认启动路径更严格的 reload / draining / ownership 语义

## 模块归属与边界

`@module` 基于 Python 包归属发现组件。若某个组件同时匹配多个模块包，启动会立即失败；对有意共享的重叠区域，请用 `ownership_overrides` 显式指定归属。

```python
@module(
    imports=[SharedModule, OrdersModule],
    ownership_overrides={"myapp.shared": SharedModule},
)
class RootModule:
    pass
```

## Runtime 切换

`Application.reload()` 会先构建新的候选 runtime，完成校验与预热，再原子切换当前活动应用。旧 runtime 会进入 draining 状态，而 `Application.current()` 在请求结束前仍会解析到该请求绑定的旧应用快照。

## 维护者 / 高级说明

`ApplicationContext` 仍然是底层容器 / 运行时原语，而 `Application` 也仍可通过 `cullinan.application` 用于高级、运行时感知的应用装配。新的应用代码应先从业务装饰器与顶层入口方法路径出发。

## 相关文档

- [应用运行时模型](../wiki/application_runtime.md)
- [应用生命周期](../wiki/lifecycle.md)
