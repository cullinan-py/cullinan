# Cullinan 依赖注入指南

> **版本**：0.94a1
> **最后更新**：2026-06-01  
> **状态**：已更新

## 概述

Cullinan 当前的 DI 模型以 `ApplicationContext` 为中心，并通过 `cullinan` 作为公开入口。装饰器仍然是推荐的编写方式；旧式 registry API 仅保留兼容意义。

在选择注入原语之前，建议先阅读[框架语义规则](framework_semantics.md)。其中定义了 `Inject()`、`InjectByName()`、`refresh()` 以及兼容 API 的硬约束。

> **推荐默认方式：** 构造注入——在类级属性上声明裸类型注解，框架自动解析注入。零样板代码：无需 `Inject()`、无需 `__init__`、无需 `self.x = x`。  
> **如果你需要查符号而不是看指导：** 请转到 [API 参考](reference/index.md)。

## 推荐用法

### 1. 用装饰器注册服务

```python
from cullinan import service

@service
class DatabaseService:
    def query(self, sql: str):
        return {"sql": sql}

@service
class UserService:
    database: DatabaseService  # 构造注入 — 裸类型注解即可

    def get_user(self, user_id: int):
        return self.database.query(f"select * from users where id = {user_id}")
```

### 2. 在控制器中复用同一套注入模型

```python
from cullinan import controller, get_api, Path

@controller(url="/users")
class UserController:
    user_service: UserService  # 构造注入

    @get_api(url="/{user_id}")
    async def get_user(self, user_id: int = Path()):
        return self.user_service.get_user(user_id)
```

## 注入原语

### 构造注入 —— 首选（零样板、框架保证不可变）

最简洁的注入方式：一行类级类型注解即为 DI 声明。无需 `Inject()` 标记、无需 `__init__`、无需 `self.x = x`。

```python
from cullinan.core import service

@service
class UserService:
    database: DatabaseService       # 必需依赖，refresh() 时报错
    cache: CacheService             # 同上
    notifier: NotifierService = None  # Optional 依赖，没有则留 None
```

**规则**：

- 无默认值 `db: DatabaseService` → **必需** DI 依赖，缺失在 `refresh()` 抛出 `DependencyNotFoundError`
- `None` 默认值 `notifier: NotifierService = None` → **可选** DI，容器有则注入，无则静默跳过
- 有实际值 `timeout: int = 5` → 框架不碰，当作普通类属性
- 有 `Inject()`/`Lazy()` 标记 → 走字段注入路径，不受构造注入影响

**与字段注入的对比**：

| 对比 | 字段注入 (`Inject()`) | 构造注入（类型注解） |
|------|------------------------------|----------------------|
| 样板代码 | `x: T = Inject()` | `x: T` |
| 启动时校验 | `required=False` 运行时抛 | 必需依赖在 `refresh()` 即报 |
| 注入后不可变性 | 框架强制（全部注入路径统一） | 框架强制（全部注入路径统一） |
| 测试 mock | `Inject()` 妨碍直接 `cls()` 实例化 | `svc = cls(); svc.db = mock`（不走 DI，不冻结） |

**优势**：

- 零样板代码
- 启动早期即可发现缺失依赖
- 注入后属性由框架保证只读
- 测试时可直接实例化并手动注入 mock 对象

> **向后兼容**：现有 `Inject()` / `Lazy()` / `InjectByName()` 行为完全不变，构造注入与字段注入可在同一类上混用。

### `Inject()` —— 字段注入（类型驱动）

当运行时类型可用且希望获得更好的重构友好性时，使用 `Inject()` 进行显式字段注入。

```python
from cullinan.core import Inject

class AuditService:
    repo: Repository = Inject()
    cache: CacheService = Inject(required=False)
```

`Inject()` 采用严格的类型解析流水线：

- 直接可用的运行时类型仍按原方式工作
- `TYPE_CHECKING` + 前向引用在 **能唯一落到一个注册目标** 时可以正常工作
- `Optional[T]`、`Annotated[T, ...]`、`Final[T]`、`Provider[T]`、`list[T]`、`set[T]`、`tuple[T, ...]`、`Union[A, B]` 等常见包装类型已受控支持
- Cullinan 仍然禁止 `session_provider -> SessionProvider` 这类属性名猜测
- 如果注解无法安全归一化，或最终绑定不唯一，启动会直接抛出 `DependencyTypeResolutionError`

当你希望保留类型驱动注入，并且注解能够被稳定归一化时，优先使用它。

### `InjectByName()` —— 按名称解析

当依赖更适合按名称解析，或直接导入类型会引入不理想的依赖边时，使用 `InjectByName()`。

```python
from cullinan.core import InjectByName

class ReportController:
    report_service = InjectByName("ReportService")
```

Cullinan 现在把 `InjectByName("ExactComponentName")` 视为推荐写法。省略显式名称的 `InjectByName()` 仅作为兼容回退保留，并会触发 warning。

如果你**明确不想**在运行时导入目标类型，这就是正确选择。

### `Lazy()` —— 延迟解析

当依赖应该在第一次访问时再解析，而不是在实例装配时立即获取，可使用 `Lazy()`。

```python
from cullinan.core import Lazy

class AuditService:
    report_service = Lazy("ReportService")
```

`Lazy()` 与 `Inject()` / `InjectByName()` 遵循同一套命名规则：

- 如果希望延迟解析且不导入目标类型，优先显式传名称
- 如果希望按类型解析，类型同样必须能在运行时被解析

## 如何选择

| 需求 | 推荐注入原语 |
| --- | --- |
| **新项目首选：最简洁、框架保证不可变** | 构造注入 `db: DatabaseService` |
| 运行时类型可用，且希望获得更好的重构友好性 | `Inject()` |
| `TYPE_CHECKING` / 前向引用场景下仍希望按类型解析，且目标唯一 | `Inject()` |
| 运行时类型刻意不可用，或不适合直接导入 | `InjectByName("Name")` |
| 希望第一次使用时再查找依赖 | `Lazy("Name")` 或带运行时可解析类型的 `Lazy()` |
| 可选依赖 | `notifier: NotifierService = None` 或 `Inject(required=False)` |
| 希望注入延迟获取的提供者对象 | `Inject()` + `Provider[T]` |
| 希望注入某个契约下的全部实现 | `Inject()` + `list[T]` / `set[T]` / `tuple[T, ...]` |

## `TYPE_CHECKING` 与前向引用规则

`Inject()` 现在可以支持 `TYPE_CHECKING` 与前向引用，但前提是最终绑定结果仍然**唯一可判定**。

### 支持示例：单一目标前向引用

```python
from typing import TYPE_CHECKING

from cullinan.core import Inject, service

if TYPE_CHECKING:
    from .providers import DatabaseSessionProvider

@service
class ChannelBindingRepository:
    session_provider: "DatabaseSessionProvider" = Inject()
```

只要 `DatabaseSessionProvider` 最终能唯一匹配到一个已注册组件，启动就会成功。

### 支持的包装类型

```python
from typing import TYPE_CHECKING, Optional

from cullinan.core import Inject, Provider, service

if TYPE_CHECKING:
    from .contracts import Hook
    from .providers import DatabaseSessionProvider, PrimarySessionProvider, SecondarySessionProvider

@service
class ChannelBindingRepository:
    session_provider: Provider["DatabaseSessionProvider"] = Inject()
    hooks: list["Hook"] = Inject(required=False)
    fallback_cache: Optional["CacheService"] = Inject()
    preferred_provider: "PrimarySessionProvider | SecondarySessionProvider" = Inject()
```

规则如下：

- `Optional[T]` 在 `T` 缺失时允许得到 `None`
- `Provider[T]` 注入的是延迟获取 `T` 的 provider 对象
- 集合包装会注入所有匹配实现
- `Union[A, B]` 只有在恰好一个分支可绑定时才允许成功

### 仍然会被拒绝的情况

- `Union` 中多个分支同时可绑定
- `list[Union[A, B]]` 这类无法安全判定的嵌套组合
- 任何需要模糊猜测或属性名回退的情况

如果你本来就希望按名称显式控制，仍然应使用 `InjectByName("Name")` 或 `Lazy("Name")`。

## ApplicationContext 是唯一容器入口

装饰器注册已覆盖大多数业务代码。高级集成场景可直接使用 `ApplicationContext`。

```python
from cullinan.core import ApplicationContext, Definition, ScopeType

ctx = ApplicationContext()
ctx.register(Definition(
    name="CustomService",
    factory=lambda c: CustomService(),
    scope=ScopeType.SINGLETON,
    source="custom:CustomService",
))
ctx.refresh()
service = ctx.get("CustomService")
```

`cullinan.core.container.*` 路径现在只是同一公开容器 API 的兼容转发。

## 生命周期集成

DI 与生命周期属于同一运行时模型。受管组件可实现：

- `on_post_construct()`
- `on_startup()`
- `on_shutdown()`
- `on_pre_destroy()`

同样支持 `_async` 异步版本；如需控制顺序，可实现 `get_phase()`。

### 生命周期异常传播

关键生命周期阶段的异常会被传播，防止组件在不一致状态下运行：

- **`on_post_construct`** 和 **`on_pre_destroy`**：异常会重新抛出为 `LifecycleError`。`on_post_construct` 失败意味着组件未就绪，不应对外提供服务。
- **`on_startup`** 和 **`on_shutdown`**：异常会记录为错误但**不会**中断容器。这避免了单个组件的启动失败级联影响其他组件。

控制器路由注册失败同样会抛出 `LifecycleError`——路由无法注册的控制器属于硬启动错误。

## 作用域校验

### 传递作用域强制检查

Cullinan 会校验长生命周期组件是否间接依赖了短生命周期组件——即使是通过依赖链传递。这能防止运行时出现单例持有请求作用域对象过期引用的问题。

校验会递归遍历：
1. 通过 `@service(dependencies=[...])` 声明的**显式依赖**。
2. 类上的**字段注入标记**（`Inject()`、`InjectByName()`、`Lazy()`）。

违规示例：
```python
@service(scope="singleton")
class SingletonA:
    dep: "SingletonB" = Inject()        # → SingletonB（singleton）✓
                                         #   → RequestC（request）  ✗ 传递违规
```

错误信息会标明完整链路：`SingletonA → SingletonB → RequestC`。

### 注入标记过滤规则

仅 Python dunder 属性（`__init__`、`__repr__` 等）会被自动排除在注入扫描之外。单下划线前缀的属性（如 `_cache`、`_connection`）**现在**对注入系统可见——如果它们携带了 `Inject()` 标记。此变更（v0.93a10+）确保"约定私有"字段不再被静默忽略。

## 兼容性说明

Cullinan 仍导出部分旧名称，但不应再作为主要编程模型：

- `injectable` 当前是**空操作兼容装饰器**
- `inject_constructor` 当前是**空操作兼容装饰器**
- `get_injection_registry()` 当前返回 `None`
- `reset_injection_registry()` 是安全的兼容空操作

保留这些名称是为了降低旧代码的硬中断风险；新代码应依赖 `@service`、`@controller`、`Inject`、`InjectByName` 与 `ApplicationContext`。

## 故障排查

| 问题 | 检查点 |
| --- | --- |
| 依赖无法解析 | 确认类型或依赖名称与注册组件一致 |
| 启动时报 `DependencyTypeResolutionError` | 注解存在歧义、不受支持，或无法被安全归一化；缩小类型范围，或切换到 `InjectByName()` / `Lazy("Name")` |
| 可选依赖缺失 | 使用 `required=False` 并显式处理 `None` |
| 生命周期钩子未执行 | 确认组件受框架管理且已执行 `ApplicationContext.refresh()` |
| 高级注册行为不符合预期 | 检查 `Definition` 的 scope 与 factory/source 设置 |
| `_` 前缀注入字段未被解析 | 自 v0.93a10 起仅排除 `__dunder__` 属性。确认字段带有类型注解且依赖已注册 |

## 相关文档

- [架构设计](architecture.md)
- [运行时整合概览](runtime_updates_v093.md)
- [IoC 与 DI wiki](wiki/injection.md)
- [应用生命周期](wiki/lifecycle.md)
