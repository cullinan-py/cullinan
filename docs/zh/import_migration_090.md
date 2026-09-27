# Cullinan 0.90 导入迁移手册

本手册帮助您将导入语句从旧结构迁移到新的 0.90 结构。

> **兼容页：** 这页用于更新既有导入；当前公开 API 表面请结合 [API 参考](reference/index.md) 阅读。

## 概述

Cullinan 0.90 重新组织了 `core/` 模块，实现了清晰的职责分离：

- **`container/`** - IoC/DI 容器（ApplicationContext、Definition、Scope）
- **`diagnostics/`** - 异常与错误渲染
- **`lifecycle/`** - 生命周期管理
- **`request/`** - 请求上下文
- **`legacy/`** - 已弃用组件（将在 1.0 中移除）

---

## 快速迁移对照表

### 核心容器（0.93 API - 推荐）

| 旧导入 | 新导入 |
|--------|--------|
| `from cullinan.core.application_context import ApplicationContext` | `from cullinan.core.container import ApplicationContext` |
| `from cullinan.core.definitions import Definition, ScopeType` | `from cullinan.core.container import Definition, ScopeType` |
| `from cullinan.core.factory import Factory` | `from cullinan.core.container import Factory` |
| `from cullinan.core.scope_manager import ScopeManager` | `from cullinan.core.container import ScopeManager` |

### 异常

| 旧导入 | 新导入 |
|--------|--------|
| `from cullinan.core.exceptions import RegistryFrozenError` | `from cullinan.core.diagnostics import RegistryFrozenError` |
| `from cullinan.core.exceptions import DependencyNotFoundError` | `from cullinan.core.diagnostics import DependencyNotFoundError` |
| `from cullinan.core.exceptions import CircularDependencyError` | `from cullinan.core.diagnostics import CircularDependencyError` |
| `from cullinan.core.exceptions import ScopeNotActiveError` | `from cullinan.core.diagnostics import ScopeNotActiveError` |
| `from cullinan.core.exceptions import ConditionNotMetError` | `from cullinan.core.diagnostics import ConditionNotMetError` |
| `from cullinan.core.exceptions import CreationError` | `from cullinan.core.diagnostics import CreationError` |
| `from cullinan.core.exceptions import LifecycleError` | `from cullinan.core.diagnostics import LifecycleError` |

### 诊断

| 旧导入 | 新导入 |
|--------|--------|
| `from cullinan.core.diagnostics import render_resolution_path` | `from cullinan.core.diagnostics import render_resolution_path` |
| `from cullinan.core.diagnostics import format_circular_dependency_error` | `from cullinan.core.diagnostics import format_circular_dependency_error` |

### 生命周期

| 旧导入 | 新导入 |
|--------|--------|
| `from cullinan.core.lifecycle import LifecycleManager` | `from cullinan.core.lifecycle import LifecycleManager` |
| `from cullinan.core.lifecycle_hooks import LifecycleEvent` | `from cullinan.core.lifecycle import LifecycleEvent` |
| `from cullinan.core.lifecycle_hooks import LifecycleEventManager` | `from cullinan.core.lifecycle import LifecycleEventManager` |

### 请求上下文

| 旧导入 | 新导入 |
|--------|--------|
| `from cullinan.core.context import RequestContext` | `from cullinan.core.request import RequestContext` |
| `from cullinan.core.context import get_current_context` | `from cullinan.core.request import get_current_context` |
| `from cullinan.core.context import create_context` | `from cullinan.core.request import create_context` |

### 类型

| 旧导入 | 新导入 |
|--------|--------|
| `from cullinan.core.types import LifecycleState` | `from cullinan.core.diagnostics import LifecycleState` |
| `from cullinan.core.types import LifecycleAware` | `from cullinan.core.diagnostics import LifecycleAware` |

### 顶层文件

| 旧文件 | 新文件 | 说明 |
|--------|--------|------|
| `cullinan/app.py` | `cullinan/bootstrap.py` | 应用启动引导 |
| `cullinan/application.py` | `cullinan/scanner.py` | 模块扫描器 |
| `cullinan/lifecycle_hooks.py` | `cullinan/core/lifecycle/events.py` | 生命周期事件 |
| `cullinan/extensions.py` | `cullinan/core/extensions.py` | 扩展注册表 |

---

## 遗留导入（已弃用）

以下导入已弃用，将在 1.0 中移除：

```python
# 已弃用 - 将在 1.0 中移除
from cullinan.core.injection import Inject, InjectByName, injectable
from cullinan.core.provider import Provider, ProviderRegistry
from cullinan.core.facade import IoCFacade, get_ioc_facade
from cullinan.core.registry import Registry, SimpleRegistry
from cullinan.core.scope import SingletonScope, TransientScope, RequestScope
```

这些已被移动到 `cullinan.core.legacy/`，使用时会发出 `DeprecationWarning`。

---

## 代码示例

### 迁移前（0.83）

```python
from cullinan.core.application_context import ApplicationContext
from cullinan.core.definitions import Definition, ScopeType
from cullinan.core.exceptions import (
    RegistryFrozenError,
    CircularDependencyError,
    ScopeNotActiveError,
)
from cullinan.core.context import RequestContext

ctx = ApplicationContext()
ctx.register(Definition(
    name='UserService',
    factory=lambda c: UserService(),
    scope=ScopeType.SINGLETON,
    source='service:UserService'
))
ctx.refresh()
```

### 迁移后（0.90）

```python
from cullinan.core.container import ApplicationContext, Definition, ScopeType
from cullinan.core.diagnostics import (
    RegistryFrozenError,
    CircularDependencyError,
    ScopeNotActiveError,
)
from cullinan.core.request import RequestContext

ctx = ApplicationContext()
ctx.register(Definition(
    name='UserService',
    factory=lambda c: UserService(),
    scope=ScopeType.SINGLETON,
    source='service:UserService'
))
ctx.refresh()
```

---

## 批量迁移脚本

可以使用以下正则表达式批量更新导入：

### Linux/Mac (sed)

```bash
# 容器导入
sed -i 's/from cullinan\.core\.application_context import/from cullinan.core.container import/g' *.py
sed -i 's/from cullinan\.core\.definitions import/from cullinan.core.container import/g' *.py
sed -i 's/from cullinan\.core\.factory import/from cullinan.core.container import/g' *.py
sed -i 's/from cullinan\.core\.scope_manager import/from cullinan.core.container import/g' *.py

# 异常导入
sed -i 's/from cullinan\.core\.exceptions import/from cullinan.core.diagnostics import/g' *.py

# 请求上下文导入
sed -i 's/from cullinan\.core\.context import/from cullinan.core.request import/g' *.py
```

### Windows (PowerShell)

```powershell
# 容器导入
Get-ChildItem -Filter *.py -Recurse | ForEach-Object {
    (Get-Content $_.FullName) -replace 'from cullinan\.core\.application_context import', 'from cullinan.core.container import' | Set-Content $_.FullName
}

# 异常导入
Get-ChildItem -Filter *.py -Recurse | ForEach-Object {
    (Get-Content $_.FullName) -replace 'from cullinan\.core\.exceptions import', 'from cullinan.core.diagnostics import' | Set-Content $_.FullName
}

# 请求上下文导入
Get-ChildItem -Filter *.py -Recurse | ForEach-Object {
    (Get-Content $_.FullName) -replace 'from cullinan\.core\.context import', 'from cullinan.core.request import' | Set-Content $_.FullName
}
```

---

## 无需更改的导入

以下导入均可正常使用。属于顶层入口面的名字仍从 `cullinan` 导入；位于独立模块中的名字从对应模块导入：

```python
# 这些导入方式保持不变
from cullinan import (
    # 配置
    configure, get_config, CullinanConfig,

    # 服务层
    service,

    # 控制器
    get_api, post_api, patch_api, delete_api, put_api,
    response,

    # 中间件
    Middleware, middleware,

    # WebSocket
    websocket_handler,
)

# 服务层类与注册表
from cullinan.core.services import Service, ServiceRegistry, get_service_registry

# 控制器注册表与请求处理器基类
from cullinan.web.controller import ControllerRegistry, get_controller_registry, Handler

# 中间件链
from cullinan.web.middleware import MiddlewareChain

# WebSocket 注册表
from cullinan.web.websocket_registry import WebSocketRegistry

# 测试辅助
from cullinan.testing import ServiceTestCase, MockService, TestRegistry
```

---

## 常见问题

### Q: 旧的导入还能用吗？

A: 旧的顶层文件（如 `cullinan.core.exceptions`）暂时仍可用，但会发出弃用警告。建议尽快迁移到新路径。

### Q: 遗留模块什么时候移除？

A: `cullinan.core.legacy/` 中的组件将在 1.0 版本中完全移除。

### Q: 如何验证迁移是否成功？

A: 运行测试并确保没有 `ImportError` 或 `DeprecationWarning`：

```bash
python -m pytest tests/ -v --tb=short
```

---

## 相关文档

- [依赖注入指南](dependency_injection_guide.md)
- [完整迁移指南](migration_guide.md)
