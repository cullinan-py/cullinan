# Cullinan 0.93 迁移指南

> **版本**：v0.90  
> **作者**：Cullinan

> **仅用于升级：** 这页用于迁移既有代码，不用于学习新项目的推荐 API 路径。

本指南帮助您从 Cullinan 1.x 迁移到 0.93（0.90）。

## v0.95a1 迁移说明（Track A 内部重构）

v0.95a1 是一个非破坏性版本，新增弃用标记和可选严格开关。既有代码无需修改即可继续运行，但建议尽早迁移。

### 自 v0.95 起弃用（v0.97 移除）

五个遗留兼容符号现已正式弃用。每次使用都会同时发出标准 `DeprecationWarning`（工具链可识别）和既有 `CompatibilitySemanticWarning`（去重语义提醒）。

| 弃用符号 | 替代方案 |
|---------|---------|
| `@injectable` | `@service` / `@component` / `@controller`（类自动可注入） |
| `@inject_constructor` | `ApplicationContext.refresh()` |
| `InjectionRegistry` | `ApplicationContext` / `get_application_context()` |
| `get_injection_registry()` | `ApplicationContext` / `get_application_context()` |
| `reset_injection_registry()` | 显式创建新的 `ApplicationContext` |

在 CI 中将弃用警告视为错误：

```bash
python -m pytest -W error::DeprecationWarning
```

### 可选严格开关

- `strict_private_injection=True`（或 `CULLINAN_STRICT_PRIVATE_INJECTION=1`）：
  注入标记扫描器跳过单下划线（`_xxx`）类属性。默认 `False` 保留 v0.93a11+ 行为。
- `strict_lifecycle=True`：`on_startup`/`on_shutdown` 失败以 `LifecycleError` 抛出。默认 `False` 保留 v0.94 行为（记录并吞掉）。

### 结构化作用域违规

传递作用域违规现在抛出 `ScopeViolationError`（`LifecycleError` 的子类）。既有 `except LifecycleError` 处理器继续有效。新异常携带 `dependency_chain`、`origin_name`、`violating_component` 字段，提供更丰富的诊断信息；使用 `format_scope_violation_error()` 渲染人类可读的链路描述。

## 破坏性变更

### 1. 单一入口

**之前（1.x）：**
```python
from cullinan.core import get_injection_registry, get_service_registry

registry = get_injection_registry()
registry.add_provider_source(my_source)
```

**之后（0.93）：**
```python
from cullinan.core.container import ApplicationContext, Definition, ScopeType

ctx = ApplicationContext()
ctx.register(Definition(
    name='MyService',
    factory=lambda c: MyService(),
    scope=ScopeType.SINGLETON,
    source='service:MyService'
))
ctx.refresh()
```

### 2. 注册表冻结

在 0.93 中，注册表在 `refresh()` 后被冻结。任何尝试注册新依赖的操作都会抛出 `RegistryFrozenError`。

**之前（1.x）：**
```python
# 可以随时注册
registry.register('NewService', NewService)
```

**之后（0.93）：**
```python
ctx = ApplicationContext()
ctx.register(...)  # refresh 前可以
ctx.refresh()
ctx.register(...)  # RegistryFrozenError!
```

### 3. 作用域强制

请求作用域依赖现在严格要求 `RequestContext`。

**之前（1.x）：**
```python
# 可能静默失败或返回错误实例
instance = registry.get('RequestScoped')
```

**之后（0.93）：**
```python
ctx.enter_request_context()
try:
    instance = ctx.get('RequestScoped')  # 正常
finally:
    ctx.exit_request_context()

# 没有上下文：
ctx.get('RequestScoped')  # ScopeNotActiveError!
```

### 4. 结构化异常

所有异常现在都携带结构化诊断字段。

**之前（1.x）：**
```python
try:
    registry.resolve('Missing')
except Exception as e:
    print(str(e))  # 通用消息
```

**之后（0.93）：**
```python
from cullinan.core.diagnostics import DependencyNotFoundError

try:
    ctx.get('Missing')
except DependencyNotFoundError as e:
    print(e.dependency_name)      # 'Missing'
    print(e.resolution_path)      # ['ParentService', 'Missing']
    print(e.candidate_sources)    # [{'source': '...', 'reason': '...'}]
```

### 5. 循环依赖检测

循环依赖现在产生稳定、有序的链路。

**之前（1.x）：**
```python
# 无序，不一致的输出
CircularDependencyError: Circular dependency detected
```

**之后（0.93）：**
```python
# 稳定、有序的链路
CircularDependencyError: 检测到循环依赖: A -> B -> C -> A
```

## 迁移步骤

### 第 1 步：更新导入

```python
# 旧导入（已弃用）
from cullinan.core import get_injection_registry, Inject, InjectByName

# 新导入（0.93）
from cullinan.core.container import ApplicationContext, Definition, ScopeType
```

### 第 2 步：转换服务注册

```python
# 旧风格
@service
class UserService:
    user_repo = Inject()

# 新风格
ctx.register(Definition(
    name='UserService',
    factory=lambda c: UserService(user_repo=c.get('UserRepository')),
    scope=ScopeType.SINGLETON,
    source='service:UserService'
))
```

### 第 3 步：更新应用启动

```python
# 旧风格（app.py）
from cullinan.app import run

# 新风格
from cullinan import application, configure

@configure(user_packages=["your_app"])
@application
def main(): ...

main()
```

入口方法现在是推荐的默认入口。`configure(root_module=...)` 已不再属于默认公开启动模型。

### 第 4 步：处理请求作用域

```python
# 在请求处理器中
class MyHandler(RequestHandler):
    def get(self):
        ctx.enter_request_context()
        try:
            service = ctx.get('RequestScopedService')
            # ... 使用服务 ...
        finally:
            ctx.exit_request_context()
```

## 已弃用的 API

以下 API 在 0.93 中已弃用，将在 3.0 中移除：

| 已弃用 API | 替代方案 |
|------------|----------|
| `get_injection_registry()` | `ApplicationContext` |
| `get_service_registry()` | `ApplicationContext.register()` |
| `@service` 装饰器（自动注入） | 显式 Definition 注册 |
| `Inject()` / `InjectByName()` | 使用 `ctx.get()` 的 factory |
| `DependencyInjector` | `ApplicationContext` |

## 兼容模式

迁移期间，您可以启用兼容模式（已弃用，将被移除）：

```python
from cullinan.core.container import ApplicationContext

ctx = ApplicationContext()
ctx.set_strict_mode(False)  # 允许一些旧行为
```

**警告：** 兼容模式仅用于迁移。生产部署前务必迁移到严格模式。

## 测试迁移

运行所有 0.93 测试以验证您的迁移：

```bash
python -m pytest tests/test_ioc_di_v2_*.py -v
```

## 获取帮助

- [依赖注入指南](dependency_injection_guide.md)
- [API 参考](api_reference.md)
- [GitHub Issues](https://github.com/your-repo/cullinan/issues)
