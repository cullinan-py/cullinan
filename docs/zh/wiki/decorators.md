# 装饰器

> **版本**: v0.90  
> **作者**: plumeink

本文档描述 Cullinan 0.90 中基于装饰器的组件注册系统。

## 概述

Cullinan 0.90 引入了强大的装饰器系统，提供了一种简洁、声明式的组件注册方式。这种方式与 Cullinan 的原始设计理念保持一致，同时与新的 IoC/DI 2.0 架构集成。

### 核心特性

- **简洁语法**：使用 `@service`、`@controller`、`@component`，无需括号
- **两阶段注册**：装饰器收集元数据 → `refresh()` 统一注册
- **依赖注入**：构造函数注入（裸注解，推荐）、`Inject`、`InjectByName`、`Lazy` 标记
- **条件注册**：根据条件注册组件

## 组件装饰器

### @service

将类标记为服务组件。服务默认为单例模式。

```python
from cullinan.core import service
from cullinan.core.decorators import Inject

# 简单用法（无需括号）
@service
class UserService:
    def get_user(self, id: int):
        return {"id": id}

# 带参数
@service(name="customUserService", scope="prototype")
class UserService:
    pass

# 带依赖
@service(dependencies=["EmailService"])
class NotificationService:
    email: EmailService = Inject()
```

**参数：**

| 参数 | 类型 | 默认值 | 描述 |
|------|------|--------|------|
| `name` | `str` | 类名 | 自定义组件名称 |
| `scope` | `str` | `"singleton"` | 作用域：`"singleton"`、`"prototype"`、`"request"` |
| `dependencies` | `list[str]` | `None` | 显式依赖列表（用于排序） |

### @controller

将类标记为控制器组件。控制器处理 HTTP 请求。

```python
from cullinan.web.controller import controller, get_api
from cullinan.core import Inject
from cullinan.web.params import Path

# 简单用法
@controller
class RootController:
    pass

# 带 URL 前缀
@controller(url="/api/users")
class UserController:
    user_service: UserService = Inject()
    
    @get_api(url="")
    def list_users(self):
        return {"users": []}
    
    @get_api(url="/{id}")
    async def get_user(self, id: int = Path()):
        return self.user_service.get_user(id)
```

**参数：**

| 参数 | 类型 | 默认值 | 描述 |
|------|------|--------|------|
| `url` | `str` | `""` | 所有路由的 URL 前缀 |

### @component

通用组件装饰器，用于既不是服务也不是控制器的类。

```python
from cullinan.core import component

# 简单用法
@component
class CacheManager:
    pass

# 带作用域
@component(scope="prototype")
class RequestHandler:
    pass

# 带自定义名称
@component(name="myHelper")
class Helper:
    pass
```

**参数：**

| 参数 | 类型 | 默认值 | 描述 |
|------|------|--------|------|
| `name` | `str` | 类名 | 自定义组件名称 |
| `scope` | `str` | `"singleton"` | 作用域：`"singleton"`、`"prototype"`、`"request"` |

### @provider

将类标记为依赖提供者（工厂）。

```python
from cullinan.core.decorators import provider

@provider
class DatabaseConnectionProvider:
    def get(self):
        return create_connection()

@provider(name="customProvider")
class CustomProvider:
    pass
```

## 注入标记

### 构造函数注入（推荐）

首选且最简单的依赖注入方式 — 只需类型注解即可，无需额外导入。

```python
@service
class UserService:
    # 构造函数注入（推荐）：
    # 裸注解 — 无需 Inject()
    email_service: EmailService
    cache: CacheService

    # 可选依赖可使用 default=None
    logger: LoggerService = None
```

**优势：**
- 无需从 `cullinan.core.decorators` 导入任何标记
- 更简洁、更符合 Python 风格的代码
- 所有 `@service`、`@controller`、`@component` 类均默认支持

> **注意：** 构造函数注入按类型注解解析依赖。如需基于名称注入或延迟注入，请使用下方标记。

### Inject

按类型注解注入依赖（显式标记）。

```python
from cullinan.core.decorators import Inject

@service
class UserService:
    # 必须注入（默认）
    email_service: EmailService = Inject()
    
    # 可选注入
    cache: CacheService = Inject(required=False)
```

**参数：**

| 参数 | 类型 | 默认值 | 描述 |
|------|------|--------|------|
| `required` | `bool` | `True` | 找不到依赖时是否抛出错误 |

### InjectByName

按显式名称注入依赖。

```python
from cullinan.core.decorators import InjectByName

@service
class UserService:
    # 显式名称
    email = InjectByName("EmailService")
    
    # 从属性名自动推断（user_repo -> UserRepo）
    user_repo = InjectByName()
```

**参数：**

| 参数 | 类型 | 默认值 | 描述 |
|------|------|--------|------|
| `name` | `str` | `None` | 依赖名称（None 时自动推断） |
| `required` | `bool` | `True` | 找不到依赖时是否抛出错误 |

### Lazy

延迟注入 - 首次访问时解析依赖。用于打断循环依赖。

```python
from cullinan.core.decorators import Lazy

@service
class ServiceA:
    # 打断循环依赖
    service_b: 'ServiceB' = Lazy()

@service
class ServiceB:
    service_a: 'ServiceA' = Lazy()
```

**参数：**

| 参数 | 类型 | 默认值 | 描述 |
|------|------|--------|------|
| `name` | `str` | `None` | 可选的显式依赖名称 |

## 条件装饰器

### @ConditionalOnProperty

根据配置属性注册组件。

```python
from cullinan.core.decorators import service
from cullinan.core.conditions import ConditionalOnProperty

@service
@ConditionalOnProperty("feature.email", having_value="true")
class EmailService:
    pass

@service
@ConditionalOnProperty("cache.enabled", match_if_missing=True)
class CacheService:
    pass
```

### @ConditionalOnClass

仅当类/模块可用时注册组件。

```python
from cullinan.core.conditions import ConditionalOnClass

@service
@ConditionalOnClass("redis.Redis")
class RedisCacheService:
    pass
```

### @ConditionalOnMissingBean

仅当指定 bean 未注册时注册组件。

```python
from cullinan.core.conditions import ConditionalOnMissingBean

@service
@ConditionalOnMissingBean("CustomEmailService")
class DefaultEmailService:
    pass
```

### @ConditionalOnBean

仅当指定 bean 存在时注册组件。

```python
from cullinan.core.conditions import ConditionalOnBean

@service
@ConditionalOnBean("DatabaseConnection")
class DatabaseService:
    pass
```

### @Conditional

使用自定义函数的通用条件装饰器。

```python
from cullinan.core.conditions import Conditional

def is_production(ctx):
    return ctx.get_property("env") == "production"

@service
@Conditional(is_production)
class ProductionOnlyService:
    pass
```

## 完整示例

```python
from cullinan.web.controller import controller, get_api
from cullinan.core import service, ApplicationContext, PendingRegistry
from cullinan.core.decorators import Inject, InjectByName
from cullinan.core.conditions import ConditionalOnClass
from cullinan.web.params import Path

# 重置以获得干净状态
PendingRegistry.reset()

# 定义服务
@service
class EmailService:
    def send(self, to: str, content: str):
        return f"邮件已发送至 {to}"

@service
class UserService:
    email_service: EmailService = Inject()
    
    def get_user(self, id: int):
        return {"id": id, "name": f"用户{id}"}
    
    def notify_user(self, id: int):
        user = self.get_user(id)
        return self.email_service.send(user["name"], "你好！")

# 定义控制器
@controller(url="/api/users")
class UserController:
    user_service: UserService = Inject()
    
    @get_api(url="/{id}")
    async def get_user(self, id: Path(int)):
        return self.user_service.get_user(id)

# 可选的 JSON 处理器（仅当 json 模块可用时）
@service
@ConditionalOnClass("json")
class JsonProcessor:
    def process(self, data):
        import json
        return json.dumps(data)

# 创建并启动应用
ctx = ApplicationContext()
ctx.refresh()

# 使用服务
user_svc = ctx.get("UserService")
print(user_svc.get_user(1))
# 输出: {'id': 1, 'name': '用户1'}

# 清理
ctx.shutdown()
```

## 两阶段注册

装饰器使用两阶段注册机制：

```
┌─────────────────────┐     ┌─────────────────────┐     ┌─────────────────────┐
│     模块加载        │     │  ApplicationContext │     │      运行时使用     │
│                     │     │      refresh()      │     │                     │
│  @service 收集      │────▶│  处理待注册组件     │────▶│  ctx.get("Name")    │
│  元数据到           │     │  冻结注册表         │     │  返回实例           │
│  PendingRegistry    │     │                     │     │                     │
└─────────────────────┘     └─────────────────────┘     └─────────────────────┘
```

### PendingRegistry

所有装饰器元数据都收集在 `PendingRegistry` 中：

```python
from cullinan.core import PendingRegistry

# 在 refresh 前检查已注册的组件
pending = PendingRegistry.get_instance()
print(f"待注册数量: {pending.count}")

# refresh 后，注册表被冻结
ctx.refresh()
assert pending.is_frozen  # True
```

## 最佳实践

1. **尽可能不使用括号**：`@service` 比 `@service()` 更简洁

2. **优先使用裸注解（构造函数注入）**：比 `Inject()` 更简洁，无需额外导入。仅在需要 `required=False` 或显式标记时使用 `Inject()`

3. **使用 `Lazy` 处理循环依赖**：显式打断循环

4. **条件装饰器放在组件装饰器之后**：顺序很重要！
   ```python
   @service  # 首先
   @ConditionalOnClass("redis")  # 其次
   class RedisService:
       pass
   ```

5. **在测试中重置 PendingRegistry**：
   ```python
   def setup_method(self):
       PendingRegistry.reset()
   ```

## 从 v0.83 迁移

| v0.83 | v0.90 |
|-------|-------|
| `@service`（来自 `cullinan.core.service`） | `@service`（来自 `cullinan.core`） |
| `@controller(url=...)`（来自 `cullinan.web.controller`） | `@controller(url=...)`（来自 `cullinan.core`） |
| 手动服务注册 | `ApplicationContext.refresh()` |

```python
# 之前 (v0.83)
from cullinan.core.services import service
from cullinan.web.controller import controller

# 之后 (v0.90)
from cullinan.core import service, controller
```

## 相关文档

- [依赖注入指南](../dependency_injection_guide.md)
- [导入迁移指南](../import_migration_090.md)
- [组件](components.md)

