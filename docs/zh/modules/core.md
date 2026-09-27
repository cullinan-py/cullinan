title: "cullinan.core"
slug: "modules-core"
module: ["cullinan.core"]
tags: ["api", "module", "core"]
author: "plumeink"
reviewers: []
status: updated
locale: zh
translation_pair: "docs/modules/core.md"
related_tests: ["tests/di/test_core_constructor_injection.py", "tests/integration/test_service_lifecycle_integration.py"]
related_examples: []
estimate_pd: 1.5
last_updated: "2026-05-30T00:00:00Z"
pr_links: []

# cullinan.core

`cullinan.core` 是 Cullinan 统一容器、生命周期与请求上下文 API 的公开门面。

## 推荐入口

### 容器与定义

- `ApplicationContext`
- `Definition`
- `ScopeType`
- `get_application_context()`
- `set_application_context()`

### 装饰器层

- `service`
- `controller`
- `component`
- `Inject`
- `InjectByName`
- `Lazy`

### 生命周期与请求上下文

- `get_lifecycle_manager()`
- `reset_lifecycle_manager()`
- `create_context()`
- `destroy_context()`
- `get_current_context()`
- `set_current_context()`

## 示例

```python
from cullinan.core import ApplicationContext, Definition, ScopeType

ctx = ApplicationContext()
ctx.register(Definition(
    name="Clock",
    factory=lambda c: object(),
    scope=ScopeType.SINGLETON,
    source="docs:Clock",
))
ctx.refresh()
clock = ctx.get("Clock")
ctx.shutdown()
```

## 兼容导出

以下名称仍然存在，但只保留向后兼容意义，不再是主要编程模型：

- `injectable`
- `inject_constructor`
- `InjectionRegistry`
- `get_injection_registry()`
- `reset_injection_registry()`

在当前运行时中，新代码应优先使用 `ApplicationContext` 与基于装饰器的注册方式。

## 运行时模块扫描

`cullinan.runtime` 模块提供模块发现与缓存管理工具：

### `invalidate_module_cache()`

清除缓存的模块扫描结果。在动态安装新包或运行时导入模块后调用，使下一次 `file_list_func()` 调用重新扫描：

```python
from cullinan.runtime import invalidate_module_cache

# 动态导入新插件包后：
invalidate_module_cache()
```

### `get_caller_package(fallback_package=None)`

确定调用模块的包名。优先使用 `sys._getframe()` 以提升性能（保留 `inspect.stack()` 回退以保证跨解释器兼容）。`fallback_package` 参数在调用方检测失败时提供默认值——在 Nuitka/PyInstaller 环境中尤为有用：

```python
from cullinan.runtime import get_caller_package

pkg = get_caller_package(fallback_package="myapp")
```

### `list_submodules(package_name)`

递归列出包内所有子模块。同时使用 `pkgutil.walk_packages`（主策略）和文件系统扫描（回退策略），确保深层子包在不同 Python 版本与打包模式下均能被发现：

```python
from cullinan.runtime import list_submodules

# 发现所有子模块，包括深层嵌套的：
modules = list_submodules("myapp")
```

### 配置 Nuitka 模块列表

在 Nuitka `--onefile` 模式下部署时，可通过 `configure()` 提供显式模块列表：

```python
from cullinan import configure

configure(explicit_modules=["myapp", "myapp.services", "myapp.web"])
```

## 另见

- [依赖注入指南](../dependency_injection_guide.md)
- [架构设计](../architecture.md)
