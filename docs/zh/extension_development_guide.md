# Cullinan 扩展开发指南

> **版本**：0.94a1
> **作者**：Cullinan  
> **最后更新**：2026-02-19

> **高级主题：** 这页面向 framework extension 开发，不属于默认应用学习路径。

---

## 目录

1. [概述](#overview)
2. [扩展点分类](#extension-categories)
3. [中间件扩展](#middleware-extensions)
4. [依赖注入扩展](#di-extensions)
5. [生命周期扩展](#lifecycle-extensions)
6. [路由扩展](#routing-extensions)
7. [最佳实践](#best-practices)
8. [常见问题](#faq)

---

## 概述 {#overview}

Cullinan 框架提供了丰富的扩展点，允许开发者在不修改框架代码的前提下定制功能。本指南介绍如何开发各类扩展。

### 扩展理念

- **非侵入式**：通过装饰器、接口实现等方式扩展
- **统一模式**：所有扩展使用一致的注册方式
- **可发现性**：扩展点可通过 API 查询
- **向后兼容**：保持兼容性，不破坏现有功能

### 查询可用扩展点

```python
from cullinan.support.extensions import list_extension_points

# 查询所有扩展点
all_points = list_extension_points()
for point in all_points:
    print(f"{point['category']}: {point['name']}")
    print(f"  {point['description']}")

# 查询特定分类
middleware_points = list_extension_points(category='middleware')
```

---

## 扩展点分类 {#extension-categories}

Cullinan 提供 6 大类扩展点：

| 分类 | 说明 | 典型用例 |
|-----|------|---------|
| **Middleware** | 请求/响应拦截 | 认证、日志、CORS |
| **Lifecycle** | 生命周期钩子 | 初始化、启动、关闭 |
| **Injection** | 依赖注入 | 自定义 Scope、Provider |
| **Routing** | 路由处理 | 自定义 Handler |
| **Configuration** | 配置管理 | 配置源、环境适配 |
| **Handler** | 请求处理器 | 自定义请求处理逻辑 |

---

## 中间件扩展 {#middleware-extensions}

### 基础概念

中间件是请求处理管道中的拦截器，可以：
- 在请求到达 Handler 前进行预处理
- 在响应返回客户端前进行后处理
- 短路请求（如认证失败直接返回 401）

### 创建中间件

#### 方式一：装饰器注册（推荐）

```python
from cullinan.web.middleware import middleware, Middleware

@middleware(priority=100)
class LoggingMiddleware(Middleware):
    """日志中间件"""
    
    def process_request(self, handler):
        # 请求预处理
        print(f"Request: {handler.request.uri}")
        return handler  # 返回 handler 继续处理
    
    def process_response(self, handler, response):
        # 响应后处理
        print(f"Response: {response}")
        return response
```

#### 方式二：手动注册

```python
from cullinan.web.middleware import Middleware, get_middleware_registry

class MyMiddleware(Middleware):
    def process_request(self, handler):
        return handler

# 手动注册
registry = get_middleware_registry()
registry.register(MyMiddleware, priority=100)
```

### 优先级规则

- **数字越小，越先执行**
- 推荐范围：
  - `0-50`：关键中间件（CORS、安全）
  - `51-100`：标准中间件（日志、指标）
  - `101-200`：应用特定中间件

### 生命周期钩子

```python
@middleware(priority=100)
class DatabaseMiddleware(Middleware):
    def on_startup(self):
        """应用启动时执行"""
        self.pool = create_connection_pool()
    
    def on_shutdown(self):
        """应用关闭时执行"""
        self.pool.close()
    
    def process_request(self, handler):
        # 为每个请求获取连接
        handler.db = self.pool.get_connection()
        return handler
    
    def process_response(self, handler, response):
        # 归还连接
        if hasattr(handler, 'db'):
            self.pool.return_connection(handler.db)
        return response
```

### 短路请求

返回 `None` 表示短路，后续中间件和 Handler 不再执行：

```python
@middleware(priority=50)
class AuthMiddleware(Middleware):
    def process_request(self, handler):
        token = handler.request.headers.get('Authorization')
        if not token:
            # 认证失败，短路
            handler.set_status(401)
            handler.finish({'error': 'Unauthorized'})
            return None  # 停止处理
        
        # 认证成功，继续
        handler.current_user = validate_token(token)
        return handler
```

### 完整示例

参考：`examples/middleware_and_module/` — 查看使用现代 `@middleware` 装饰器 API 的中间件示例。

---

## 依赖注入扩展 {#di-extensions}

### 自定义 Scope

Scope 定义依赖的生命周期（单例、请求级、会话级等）。

```python
from cullinan.core.scope import Scope
from typing import Any, Optional

class SessionScope(Scope):
    """会话级作用域"""
    
    def __init__(self):
        super().__init__('session')
        self._instances = {}  # {session_id: {key: instance}}
    
    def get(self, key: str) -> Optional[Any]:
        """获取实例"""
        session_id = self._get_current_session_id()
        if session_id and session_id in self._instances:
            return self._instances[session_id].get(key)
        return None
    
    def set(self, key: str, value: Any) -> None:
        """设置实例"""
        session_id = self._get_current_session_id()
        if session_id:
            if session_id not in self._instances:
                self._instances[session_id] = {}
            self._instances[session_id][key] = value
    
    def clear(self) -> None:
        """清理当前会话"""
        session_id = self._get_current_session_id()
        if session_id and session_id in self._instances:
            del self._instances[session_id]
    
    def _get_current_session_id(self) -> Optional[str]:
        """从请求上下文获取会话 ID"""
        from cullinan.core.context import get_current_context
        try:
            context = get_current_context()
            return context.get('session_id')
        except:
            return None
```

### 自定义 Provider

Provider 负责创建和管理依赖实例。

#### 工厂模式 Provider

```python
from cullinan.core.provider import Provider

class FactoryProvider(Provider):
    """每次都创建新实例"""
    
    def __init__(self, factory: Callable[[], Any], name: str):
        self.factory = factory
        self.name = name
    
    def get(self, key: str) -> Optional[Any]:
        return self.factory()
    
    def set(self, key: str, value: Any) -> None:
        pass
```

#### 延迟初始化 Provider

```python
class LazyProvider(Provider):
    """首次访问时才初始化"""
    
    def __init__(self, factory: Callable[[], Any], name: str):
        self.factory = factory
        self.name = name
        self._instance = None
        self._initialized = False
    
    def get(self, key: str) -> Optional[Any]:
        if not self._initialized:
            self._instance = self.factory()
            self._initialized = True
        return self._instance
    
    def set(self, key: str, value: Any) -> None:
        self._instance = value
        self._initialized = True
```

### 注册自定义 Provider

```python
from cullinan.core import ApplicationContext, Definition, ScopeType

ctx = ApplicationContext()

ctx.register(Definition(
    name="MyClass",
    factory=lambda c: MyClass(),
    scope=ScopeType.SINGLETON,
    source="extension:MyClass",
))

ctx.register(Definition(
    name="HeavyClass",
    factory=lambda c: HeavyClass(),
    scope=ScopeType.SINGLETON,
    source="extension:HeavyClass",
))
```

对新扩展来说，优先通过 `ApplicationContext` 注册 `Definition` 或显式 factory，而不是直接修改旧注入 registry。

### 完整示例

参考：`examples/extension_registration_demo.py` — 演示使用当前公共 API 进行扩展发现与注册。

---

## 生命周期扩展 {#lifecycle-extensions}

### Service 生命周期钩子

```python
from cullinan.core.services import service, Service

@service
class DatabaseService(Service):
    def on_post_construct(self):
        """初始化资源（依赖注入完成后）"""
        self.connection = connect_to_database()
        print("Database connected")
    
    def on_startup(self):
        """应用启动时执行"""
        self.connection.execute("SELECT 1")  # 健康检查
        print("Database ready")
    
    def on_shutdown(self):
        """应用关闭时执行"""
        self.connection.close()
        print("Database disconnected")
    
    def on_pre_destroy(self):
        """销毁前执行"""
        pass
```

### 异步钩子

```python
@service
class AsyncService(Service):
    async def on_startup_async(self):
        """支持异步初始化"""
        self.client = await create_async_client()
    
    async def on_shutdown_async(self):
        """支持异步清理"""
        await self.client.close()
```

### 钩子执行顺序

1. **on_post_construct()**：依赖注入完成后执行
2. **on_startup()**：应用启动时执行
3. **on_shutdown()**：应用关闭时执行（逆序）
4. **on_pre_destroy()**：销毁前执行

---

## 路由扩展 {#routing-extensions}

### 自定义 Tornado Handler

```python
import tornado.web
from cullinan import application, configure


class CustomHandler(tornado.web.RequestHandler):
    """自定义请求处理器"""

    def get(self):
        self.write({"message": "Custom handler"})

    def post(self):
        data = self.get_json_argument()
        self.write({"received": data})


@configure(user_packages=["__main__"])
@application
def main(): ...

# 注册自定义 Handler
if __name__ == '__main__':
    application.run(main, handlers=[
        (r'/custom', CustomHandler),
        (r'/custom/(?P<id>[0-9]+)', CustomHandler),
    ])
```

### 与 Controller 混合使用

```python
from cullinan import application, configure
from cullinan.web.controller import controller, get_api


@controller(url='/api/users')
class UserController:
    @get_api(url='/')
    def list_users(self):
        return {"users": []}


@configure(user_packages=["__main__"])
@application
def main(): ...

# CustomHandler 和 UserController 可以共存
if __name__ == '__main__':
    application.run(
        main,
        handlers=[
            (r'/health', HealthCheckHandler),  # 自定义
        ]
    )  # UserController 会自动注册
```

---

## 最佳实践 {#best-practices}

### 1. 中间件设计原则

✅ **单一职责**：每个中间件只做一件事
```python
# 好的设计
@middleware(priority=50)
class AuthMiddleware(Middleware):  # 只负责认证
    pass

@middleware(priority=60)
class RoleMiddleware(Middleware):  # 只负责权限检查
    pass
```

❌ **避免职责混杂**
```python
# 不好的设计
@middleware(priority=50)
class AuthAndLoggingMiddleware(Middleware):  # 职责混杂
    pass
```

### 2. 优先级规划

- 按依赖关系排序（后续中间件依赖前面的结果）
- 安全相关的中间件优先级最高
- 日志和监控中间件优先级适中

```python
@middleware(priority=10)   # CORS（最先执行）
class CorsMiddleware(Middleware):
    pass

@middleware(priority=40)   # 速率限制（在认证前）
class RateLimitMiddleware(Middleware):
    pass

@middleware(priority=50)   # 认证
class AuthMiddleware(Middleware):
    pass

@middleware(priority=60)   # 权限（依赖认证结果）
class RoleMiddleware(Middleware):
    pass

@middleware(priority=100)  # 日志（最后执行）
class LoggingMiddleware(Middleware):
    pass
```

### 3. 依赖注入原则

✅ **优先使用构造器注入**（裸类型注解现在是主要风格）
```python
@service
class UserService(Service):
    email_service: EmailService  # 构造器注入（推荐）
```

✅ **特殊情况使用按名称注入**
```python
@service
class UserService(Service):
    email_service = InjectByName('EmailService')  # 避免循环导入
```

### 4. 生命周期管理

- **on_post_construct()**：依赖注入完成后初始化资源
- **on_startup()**：执行依赖其他服务的逻辑
- **on_shutdown()**：总是清理资源
- **on_pre_destroy()**：销毁前的最终清理

```python
@service
class ResourceService(Service):
    def on_post_construct(self):
        # 初始化独立资源
        self.connection = create_connection()
    
    def on_startup(self):
        # 依赖其他服务的初始化
        self.cache = get_cache_service()
    
    def on_shutdown(self):
        # 清理（必须实现）
        if self.connection:
            self.connection.close()
```

### 5. 错误处理

✅ **总是提供清晰的错误信息**
```python
@middleware(priority=50)
class AuthMiddleware(Middleware):
    def process_request(self, handler):
        try:
            token = self._extract_token(handler)
            user = self._validate_token(token)
            handler.current_user = user
            return handler
        except TokenExpiredError:
            handler.set_status(401)
            handler.finish({
                'error': 'TokenExpired',
                'message': 'Your token has expired. Please login again.'
            })
            return None
        except InvalidTokenError:
            handler.set_status(401)
            handler.finish({
                'error': 'InvalidToken',
                'message': 'Invalid authentication token.'
            })
            return None
```

### 6. 日志规范

- 使用结构化日志
- **严禁使用 emoji**
- 记录关键操作和错误

```python
import logging

logger = logging.getLogger(__name__)

@middleware(priority=100)
class LoggingMiddleware(Middleware):
    def process_request(self, handler):
        logger.info(
            "Request started",
            extra={
                'method': handler.request.method,
                'path': handler.request.path,
                'remote_ip': handler.request.remote_ip,
            }
        )
        return handler
```

---

## 常见问题 {#faq}

### Q1: 如何在中间件中访问依赖注入的服务？

A: 中间件本身不支持自动注入，但可以手动获取：

```python
@middleware(priority=100)
class ServiceAwareMiddleware(Middleware):
    def on_startup(self):
        # 从当前活动的 ApplicationContext 解析服务
        from cullinan.core import get_application_context
        self.user_service = get_application_context().get('UserService')
    
    def process_request(self, handler):
        # 使用服务
        user = self.user_service.get_user(123)
        return handler
```

### Q2: 中间件可以修改响应吗？

A: 可以，在 `process_response` 中修改：

```python
@middleware(priority=100)
class ResponseModifierMiddleware(Middleware):
    def process_response(self, handler, response):
        # 添加响应头
        handler.set_header('X-Custom-Header', 'value')
        
        # 修改响应体（如果是字典）
        if isinstance(response, dict):
            response['timestamp'] = time.time()
        
        return response
```

### Q3: 如何实现条件性中间件（仅应用于特定路径）？

A: 在中间件中判断路径：

```python
@middleware(priority=50)
class ConditionalMiddleware(Middleware):
    def process_request(self, handler):
        # 仅应用于 /api/ 路径
        if not handler.request.path.startswith('/api/'):
            return handler  # 跳过
        
        # 执行中间件逻辑
        # ...
        return handler
```

### Q4: 中间件的执行顺序是什么？

A: 请求和响应的顺序不同：

- **请求阶段**：按优先级从小到大（10 → 50 → 100）
- **响应阶段**：按优先级从大到小（100 → 50 → 10，逆序）

```
客户端请求
  ↓
Middleware A (priority=10)  →  process_request
  ↓
Middleware B (priority=50)  →  process_request
  ↓
Middleware C (priority=100) →  process_request
  ↓
Handler 处理
  ↓
Middleware C (priority=100) →  process_response
  ↓
Middleware B (priority=50)  →  process_response
  ↓
Middleware A (priority=10)  →  process_response
  ↓
客户端响应
```

### Q5: 如何测试自定义扩展？

A: 使用 Cullinan 的测试工具：

```python
from cullinan.testing import ServiceTestCase

class TestMyMiddleware(ServiceTestCase):
    def test_process_request(self):
        middleware = MyMiddleware()
        
        # 模拟 handler
        class MockHandler:
            request = MockRequest()
        
        handler = MockHandler()
        result = middleware.process_request(handler)
        
        self.assertIsNotNone(result)
```

---

## 进一步阅读

- [维基扩展](wiki/extensions.md) - 扩展模式与最佳实践
- [依赖注入指南](dependency_injection_guide.md) - DI 系统文档
- [扩展快速入门](quick_start_extensions.md) - 扩展快速入门指南

> **注意**：示例文件可以在仓库的 `examples/` 目录中找到：
> - `examples/extension_registration_demo.py` - 扩展注册演示
> - `examples/middleware_and_module/` - 中间件示例
> - `examples/controller_service_inject/` - DI 示例

---

## 获取帮助

- **GitHub Issues**：https://github.com/yourusername/cullinan/issues
- **示例代码**：`examples/` 目录
- **API 文档**：`docs/api_reference.md`

---

**版本**：0.94a1
**作者**：Cullinan  
**最后更新**：2026-06-01
