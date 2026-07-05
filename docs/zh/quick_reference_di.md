# Cullinan 依赖注入快速参考

> **版本**: 0.94a1
> **作者**: Cullinan

> **速查页：** 这页用于快速查看 DI 写法；完整指导请看
> [依赖注入指南](dependency_injection_guide.md)，查符号请看 [API 参考](reference/index.md)。

## 基本用法

### 1. 定义服务

```python
from cullinan import service

@service
class UserService:
    def __init__(self):
        self.name = "UserService"
    
    def get_user(self, user_id):
        return {"id": user_id, "name": "John"}
```

### 2. 注入服务到 Controller

```python
from cullinan import Inject, InjectByName, Lazy, Provider
from cullinan import controller

@controller(url='/api')
class UserController:
    # 方式1: 构造注入 — 裸类型注解，零样板代码（推荐）
    user_service: UserService

    # 方式2: 显式指定名称
    auth_service = InjectByName('AuthService')
    
    # 方式3: 可选依赖 — 设为 None 即可
    notifier: NotifierService = None

    # 方式4: 延迟查找
    report_service = Lazy('ReportService')
```

### 3. 使用注入的服务

```python
from cullinan import controller, get_api, Path

@controller(url='/api')
class UserController:
    user_service: UserService  # 构造注入

    @get_api(url='/users/{user_id}')
    async def get_user(self, user_id: int = Path()):
        user = self.user_service.get_user(user_id)
        return user
```

## 注入原语如何选择

| 场景 | 用法 |
| --- | --- |
| **最简洁写法（推荐）** | `db: DatabaseService` 构造注入 |
| 类型可在运行时导入 | `Inject()` |
| `TYPE_CHECKING` / 前向引用最终仍能唯一命中一个目标 | `Inject()` |
| 类型不希望在运行时直接导入 | `InjectByName("Name")` |
| 希望第一次使用时再解析 | `Lazy("Name")` |
| 可选依赖 | `notifier: NotifierService = None` 或 `required=False` |
| 希望注入延迟 provider 对象 | `Provider[T] = Inject()` |
| 希望注入某个契约下的全部实现 | `list[T] = Inject()` / `set[T] = Inject()` / `tuple[T, ...] = Inject()` |

## `TYPE_CHECKING` 规则

`Inject()` 现在支持 `TYPE_CHECKING` 前向引用，但前提是最终绑定结果唯一：

```python
from typing import TYPE_CHECKING
from cullinan import Inject, Provider

if TYPE_CHECKING:
    from .contracts import Hook
    from .providers import DatabaseSessionProvider

class Repo:
    session_provider: Provider["DatabaseSessionProvider"] = Inject()
    hooks: list["Hook"] = Inject(required=False)
```

以下情况仍会在启动阶段快速失败：

- 注解有歧义，例如 `Union[A, B]` 同时存在多个可绑定候选
- 注解组合不受支持，例如 `list[Union[A, B]]`
- 框架需要靠名称猜测而不是精确解析才能继续

## 打包应用配置

### 使用入口方法（推荐）

```python
from cullinan import application, configure

# user_packages 触发自动模块发现——无需手动导入任何组件。
# 框架会自动扫描并注册 my_app 下所有 @service / @controller /
# @component 类。
@configure(user_packages=["my_app"])
@application
def main(): ...

main()
```

`@module` 只应在你需要显式高级运行时边界（例如包归属或热插拔模块结构）时再引入。

### PyInstaller 配置

```python
# your_app.spec
hiddenimports=[
    'my_app.service.user_service',
    'my_app.service.auth_service',
],
datas=[
    ('my_app', 'my_app'),
],
```

### Nuitka 配置

```bash
nuitka --include-package=my_app \
       --include-module=my_app.service.user_service \
       your_app.py
```

## 故障排查

| 问题 | 解决方案 |
|------|----------|
| 依赖为 None | 确保服务使用 `@service` 装饰器 |
| 找不到服务 | 检查服务名称是否匹配（区分大小写） |
| 循环依赖或运行时 import 边不合适 | 使用 `InjectByName()` 或 `Lazy("Name")` |
| 报 `DependencyTypeResolutionError` | 注解存在歧义、不受支持，或无法被安全归一化；缩小类型契约，或改用 `InjectByName()` |
| 注入不生效 | 确保组件已用 `@service` / `@controller` 注册，并可被 `ApplicationContext` 发现 |

## 另请参阅

- [依赖注入指南](dependency_injection_guide.md) - 完整 DI 文档
- [架构设计](architecture.md) - 系统架构概览
- [迁移指南](migration_guide.md) - 从旧版本迁移
