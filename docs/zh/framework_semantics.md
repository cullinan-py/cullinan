title: "框架语义规则"
slug: "framework-semantics"
tags: ["guide", "semantics", "diagnostics"]
author: "Cullinan"
reviewers: []
status: updated
locale: zh
translation_pair: "docs/framework_semantics.md"
related_tests: ["tests/regression/test_component_reliability.py", "tests/core/test_injection_annotation_parsing.py"]
related_examples: []
estimate_pd: 1.0
last_updated: "2026-06-01T00:00:00Z"
pr_links: []

# 框架语义规则

本文定义 Cullinan **保证什么**、哪些行为只是兼容保留，以及哪些场景现在会触发 warning 或启动期失败。目标是把 Cullinan 的运行时模型讲清楚：先写装饰器式业务代码，通过导入执行完成发现，在需要时再引入明确的运行时边界。

> **推荐下一步：** [架构设计](architecture.md)、[工程实践](how-to/index.md)  
> **如果你要查符号而不是读解释：** 请转到 [API 参考](reference/index.md)。

## 推荐的语义化包路径

Cullinan 当前推荐的主路径是：

- `cullinan` —— 应用启动入口（`@application`、`configure`）
- `cullinan.application` —— `Application`、`module` 等高级应用语义
- `cullinan.web` —— 控制器、路由装饰器、请求/响应、参数与中间件
- `cullinan.core` —— IoC/DI、生命周期与语义诊断

像 `cullinan.runtime`、`cullinan.transport`、`cullinan.support` 这样的更底层层级仍然可用，但不应成为普通业务应用的默认入门路径。

这也意味着默认学习路径**不是先学 Tornado 再学 Cullinan**。Tornado 与 ASGI 是框架边界之后的执行后端；对应用代码真正构成主契约的，是 Cullinan 自身的 Web 与 application 语义。

## 1. 组件发现依赖“导入执行”，不是静态 AST 扫描，也不是显式 app 注册

Cullinan 通过**导入 Python 模块**并执行装饰器来发现组件。

- 受保证：模块顶层定义、且在模块导入时就执行到的 `@service`、`@controller`、`@component`、`@provider`
- 不受保证：定义在函数、工厂、条件分支或其他局部作用域里的类；这些定义通常要等运行到对应代码块时装饰器才会执行

```python
from cullinan.core import component


@component
class TopLevelCache:
    pass


def build_repository():
    @component
    class LocalRepository:
        pass

    return LocalRepository
```

`TopLevelCache` 属于受支持的自动发现路径；`LocalRepository` 不属于自动顶层扫描契约。Cullinan 现在会对这类写法发 warning，如果它发生在 `refresh()` 之后，则会直接失败。如果某段能力需要更强的归属、reload 或热插拔运行时保证，应通过 `@module` 表达边界，而不是退回到手工 app 注册思路。

## 2. `Inject()` 是严格类型契约

只有当 Cullinan 能把注解归一化为**稳定且唯一**的依赖契约时，`Inject()` 才会成功。

当前支持的典型形式包括：

- `T`
- `"T"`
- `Optional[T]`
- `Annotated[T, ...]`
- `Final[T]`
- `Provider[T]`
- `list[T]`、`set[T]`、`tuple[T, ...]`
- `Union[A, B]` / `A | B`（前提是最终只命中一个候选）

Cullinan 已不再回退到属性名猜测。如果注解缺失、不受支持或存在歧义，启动会直接以类型化诊断失败。

## 3. `InjectByName()` 的语义是“显式名称绑定”

`InjectByName()` 按组件注册名解析，而不是按类型解析。

推荐写法：

```python
from cullinan.core import InjectByName


class ReportController:
    report_service: "ReportService" = InjectByName("ReportService")
```

兼容写法：

```python
class ReportController:
    report_service = InjectByName()
```

兼容写法目前仍会回退到属性名，但 Cullinan 现在会给出 warning，因为这种绑定在重构时更容易悄悄失效。即使使用按名注入，也建议保留真实类型注解，便于表达语义与静态检查。

## 4. `refresh()` 之后注册会被冻结

`ApplicationContext.refresh()` 是结构边界：

- 会消费并注册 pending 的装饰器组件
- 会完成定义校验与预热
- 会冻结相关注册表

从这一刻开始，再去新增装饰器组件就不再是受支持的运行时变更路径。Cullinan 现在会给出明确的语义错误，并附上修复建议。

**`PendingRegistry.clear()` 一致性**：自 v0.93a10 起，对已冻结的注册表调用 `clear()` 同样会抛出 `RuntimeError`——与 `add()` 行为保持一致。在测试清理中使用 `PendingRegistry.reset()` 可完整重置注册表（包括冻结状态）。

## 5. 作用域规则是强约束，不是"尽量工作"

Cullinan 把作用域兼容性视为硬规则。尤其是 `singleton` 组件不能直接依赖 `request` 作用域组件。现在这类情况会给出结构化生命周期诊断，而不是等到更晚阶段以不稳定方式出错。

**传递强制检查**：作用域检查现在会递归遍历完整依赖链——包括显式 `dependencies=[...]` 声明和字段注入标记（`Inject()`、`InjectByName()`）。如果单例依赖另一个单例，而后者又传递依赖了请求作用域对象，`refresh()` 时会检测并拒绝，错误信息中会标明完整链路。

**结构化作用域违规（v0.95）**：作用域违规现在抛出 `ScopeViolationError`（`LifecycleError` 的子类），携带三个诊断字段：

- `dependency_chain`：从起源单例到违规请求作用域组件的有序组件名列表（含两端）。
- `origin_name`：作用域被违规的根组件名。
- `violating_component`：被传递依赖到的请求作用域组件名。

`cullinan.core.diagnostics` 中的 `format_scope_violation_error()` 辅助函数可渲染人类可读的链路描述。由于 `ScopeViolationError` 继承 `LifecycleError`，既有 `except LifecycleError` 处理器继续有效。

**性能优化（v0.95）**：传递作用域校验器使用跨起源记忆化（`verified_safe` 集合），每个组件子图在所有起源中最多被完整遍历一次，将最坏情况复杂度从 O(N²×M) 降为 O(N+E)。`get_injection_markers()` 扫描器也通过 `WeakKeyDictionary` 按类缓存，避免重复 `dir()` 扫描。

## 6. 注入可见性与私有约定（v0.95）

注入标记扫描器（`get_injection_markers`）扫描类属性以查找 `Inject`、`InjectByName`、`Lazy` 标记。自 v0.93a11（commit c888738，构造器注入功能）起，单下划线前缀属性（`_xxx`）对注入系统**可见**--只有 dunder 属性（`__xxx__`）被跳过。这是有意的设计决策：构造器注入需要扫描类级裸类型标注，过滤所有 `_` 前缀属性会漏掉 `_internal_db: DatabaseService` 这类"私有但需要构造器注入"的属性。

这与 [[公共 API 暴露准则]] §3 的"下划线=私有"约定**不冲突**。规范 §3 约束的是**框架导出符号**的私有性（即用户不应 `from cullinan import _internal_helper`）。注入扫描器操作的是**用户自定义类属性**，属于不同层面。

对于需要严格私有语义（跳过单下划线属性）的项目，`ApplicationContext` 提供 `strict_private_injection` opt-out 开关：

```python
ctx = ApplicationContext(strict_private_injection=True)
```

`CULLINAN_STRICT_PRIVATE_INJECTION=1` 环境变量提供全局 opt-in（适用于 CI / 严格项目）。默认值 `False` 保留 v0.93a11+ 行为。

## 7. 生命周期异常传播（v0.95）

`ApplicationContext`（v0.94 主生命周期路径）区分关键和非关键生命周期钩子：

| 钩子 | 默认失败行为 | 理由 |
|------|------------|------|
| `on_post_construct` / `on_post_construct_async` | **抛出** `LifecycleError` | 组件状态不一致，无法继续初始化 |
| `on_pre_destroy` / `on_pre_destroy_async` | **抛出** `LifecycleError` | 资源清理失败可能导致泄漏 |
| `on_startup` / `on_startup_async` | **记录并吞掉** | 避免级联失败，允许部分启动 |
| `on_shutdown` / `on_shutdown_async` | **记录并吞掉** | 尽力关闭，避免中断其他组件清理 |

所有抛出的异常使用 `raise LifecycleError(...) from exc` 保留 `__cause__` 链，符合 [[错误码与异常分级规范]] §3。

对于需要所有生命周期失败都传播的项目（对齐 `LifecycleManager` 的 `force=False` 行为），`ApplicationContext` 提供 `strict_lifecycle` 开关：

```python
ctx = ApplicationContext(strict_lifecycle=True)
```

启用后，`on_startup` / `on_shutdown` 失败也会抛出 `LifecycleError`。默认值 `False` 保留 v0.94 行为。旧路径 `LifecycleManager` **不**做修改；其行为对现有直接使用者保持不变。

## 8. 兼容 API 已弃用（v0.95）

像 `@injectable`、`@inject_constructor`、`InjectionRegistry`、`get_injection_registry()`、`reset_injection_registry()` 这样的旧接口仍然保留，目的是让历史代码还能导入，但它们**自 v0.95 起弃用**，将在 **v0.97 移除**。

自 v0.95 起，这些符号携带：

- `@deprecated` 装饰器发出标准 `DeprecationWarning`（工具链可识别，如 `pytest -W error::DeprecationWarning`、linter、IDE）。
- `__deprecated__ = True` 和 `__deprecated_info__ = {version, alternative, removal_version}` 元数据，支持程序化检测。
- 既有 `CompatibilitySemanticWarning`（经 `warn_semantic_once`）继续作为去重语义提醒发出。

**迁移指引**：

| 弃用符号 | 替代方案 |
|---------|---------|
| `@injectable` | `@service` / `@component` / `@controller`（类自动可注入） |
| `@inject_constructor` | `ApplicationContext.refresh()`（统一处理构造器注入） |
| `InjectionRegistry` | `ApplicationContext` / `get_application_context()` |
| `get_injection_registry()` | `ApplicationContext` / `get_application_context()` |
| `reset_injection_registry()` | 显式创建新的 `ApplicationContext` |

## 9. 如何理解新的 warning 和报错

Cullinan 现在把关键诊断统一表达为：

- **语义规则**：框架当前强制执行的契约
- **当前问题**：运行时实际观察到的现象
- **建议**：最安全、最受支持的修复方式

当框架能够确定你违反了核心语义时，会直接失败；当代码虽然还能运行，但明显容易误导开发者时，则会发 warning。

## 10. 编译环境下的模块发现

当 Cullinan 运行在 Nuitka 或 PyInstaller 环境中时，标准的 `pkgutil.walk_packages` 可能无法发现全部用户模块——尤其是在 `--onefile` 模式下，文件系统布局与开发环境不同。

**`explicit_modules` 配置**：可通过 `configure()` 提供显式模块列表：

```python
from cullinan import configure

configure(explicit_modules=[
    "myapp",
    "myapp.services",
    "myapp.web",
])
```

该列表作为统一扫描管道中的最高优先级策略（S0），在回退到 `user_packages`（S1）等启发式方法之前使用。每个条目会被递归遍历以发现子包。

**深层子包发现**：`list_submodules()` 现在会在 `pkgutil.walk_packages` 基础上增加基于文件系统的递归扫描回退。如果深层嵌套包（如 `club.fnep.infrastructure.discord`）被 `walk_packages` 遗漏，文件系统回退会通过直接遍历 `__init__.py` 目录和 `.py` 文件来发现它们。
