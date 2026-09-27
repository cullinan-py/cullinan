# Cullinan 扩展注册快速指南

> **版本**：v0.90  
> **功能**：统一扩展注册与发现模式  
> **作者**：plumeink

> **高级主题：** 这页用于扩展或中间件注册场景，不是常规业务应用首读内容。

---

## 快速开始

### 1. 中间件注册（推荐方式）

使用 `@middleware` 装饰器自动注册中间件：

```python
from cullinan.web.middleware import middleware, Middleware

@middleware(priority=100)
class LoggingMiddleware(Middleware):
    """日志中间件 - 记录所有请求"""
    
    def process_request(self, handler):
        print(f"→ Request: {handler.request.uri}")
        return handler  # 返回 handler 继续处理
    
    def process_response(self, handler, response):
        print(f"← Response: {response}")
        return response
```

### 2. 优先级控制

优先级数字越小，越先执行：

```python
@middleware(priority=10)   # 第一个执行
class CorsMiddleware(Middleware):
    pass

@middleware(priority=50)   # 第二个执行
class AuthMiddleware(Middleware):
    pass

@middleware(priority=100)  # 第三个执行
class LoggingMiddleware(Middleware):
    pass
```

**推荐优先级范围**：
- `0-50`：关键中间件（CORS、安全检查）
- `51-100`：标准中间件（日志、指标收集）
- `101-200`：应用特定中间件

### 3. 扩展点发现

查询框架提供的扩展点：

```python
from cullinan.support.extensions import list_extension_points

# 查询所有扩展点
all_points = list_extension_points()

# 查询特定分类的扩展点
middleware_points = list_extension_points(category='middleware')
lifecycle_points = list_extension_points(category='lifecycle')

# 显示扩展点信息
for point in middleware_points:
    print(f"{point['name']}: {point['description']}")
```

输出示例：
```
Middleware.process_request: Intercept and process requests before they reach handlers
Middleware.process_response: Intercept and process responses before they are sent
```

### 4. 查询已注册中间件

```python
from cullinan.web.middleware import get_middleware_registry

registry = get_middleware_registry()
registered = registry.get_registered_middleware()

for mw in registered:
    print(f"{mw['priority']:3d}: {mw['name']}")
```

输出示例：
```
 10: CorsMiddleware
 50: AuthMiddleware
100: LoggingMiddleware
```

---

## 完整示例

### 场景：构建一个带认证的 API

```python
from cullinan import application, configure
from cullinan.web.middleware import middleware, Middleware
from cullinan.web.controller import controller, get_api
from cullinan.core.services import service, Service
from cullinan.web.params import Path

# 1. 定义中间件（按优先级自动排序）

@middleware(priority=10)
class CorsMiddleware(Middleware):
    """CORS 中间件 - 最先执行"""
    def process_response(self, handler, response):
        handler.set_header('Access-Control-Allow-Origin', '*')
        return response


@middleware(priority=50)
class AuthMiddleware(Middleware):
    """认证中间件 - CORS 之后执行"""
    def process_request(self, handler):
        token = handler.request.headers.get('Authorization')
        if not token and handler.request.path.startswith('/api/'):
            handler.set_status(401)
            handler.finish({"error": "Unauthorized"})
            return None  # 短路，不继续处理
        return handler


@middleware(priority=100)
class LoggingMiddleware(Middleware):
    """日志中间件 - 最后执行"""
    def process_request(self, handler):
        print(f"[{handler.request.method}] {handler.request.path}")
        return handler


# 2. 定义服务

@service
class UserService(Service):
    def get_user(self, user_id):
        return {"id": user_id, "name": "Alice"}


# 3. 定义控制器

@controller(url='/api/users')
class UserController:
    user_service: UserService  # ← 构造注入
    
    @get_api(url='/{user_id}')
    async def get_user(self, user_id: int = Path()):
        return self.user_service.get_user(user_id)


# 4. 启动应用

@configure(user_packages=["__main__"], server_port=8080)
@application
def main(): ...
```

**执行流程**：
```
请求到达
  ↓
CorsMiddleware (priority=10)
  ↓
AuthMiddleware (priority=50) 
  ↓
LoggingMiddleware (priority=100)
  ↓
UserController.get_user()
  ↓
LoggingMiddleware (响应，逆序)
  ↓
AuthMiddleware (响应，逆序)
  ↓
CorsMiddleware (响应，逆序)
  ↓
响应返回
```

---

## 向后兼容

手动注册方式仍然可用：

```python
from cullinan.web.middleware import Middleware, get_middleware_registry

class MyMiddleware(Middleware):
    def process_request(self, handler):
        return handler

# 手动注册
registry = get_middleware_registry()
registry.register(MyMiddleware, priority=100)
```

**新旧方式可以混用**，框架会自动按优先级排序。

---

## 扩展点分类

框架提供 6 大类扩展点：

1. **Middleware（中间件）**
   - `Middleware.process_request`
   - `Middleware.process_response`

2. **Lifecycle（生命周期）**
   - `on_post_construct`
   - `on_startup`
   - `on_shutdown`
   - `on_pre_destroy`

3. **Injection（依赖注入）**
   - `custom_scope`
   - `custom_provider`

4. **Routing（路由）**
   - `custom_handler`

5. **Configuration（配置）**
   - `config_provider`

6. **Handler（处理器）**
   - 自定义路由处理器

---

## 常见问题

### Q1: 中间件返回 None 会怎样？

A: 返回 `None` 表示短路，后续中间件和处理器不再执行：

```python
def process_request(self, handler):
    if not_authorized:
        handler.set_status(401)
        handler.finish({"error": "Unauthorized"})
        return None  # 短路，不继续
    return handler  # 继续到下一个中间件
```

### Q2: 如何查看中间件执行顺序？

A: 使用注册表查询：

```python
from cullinan.web.middleware import get_middleware_registry

registry = get_middleware_registry()
for mw in registry.get_registered_middleware():
    print(f"{mw['priority']}: {mw['name']}")
```

### Q3: 可以动态注册中间件吗？

A: 可以，但建议在应用启动前完成注册：

```python
# 启动前注册
registry = get_middleware_registry()
registry.register(DynamicMiddleware, priority=150)

# 然后启动应用
run()
```

### Q4: 中间件会影响性能吗？

A: 装饰器注册的开销极小（~1μs），运行时无额外开销。中间件的性能取决于你的实现逻辑。

---

## 进一步阅读

- **示例代码**：`examples/extension_registration_demo.py`
- **扩展开发指南**：`docs/extension_development_guide.md`
- **中间件详解**：`docs/wiki/middleware.md`

---

## 反馈与支持

如有问题或建议，请：
1. 查看示例代码：`examples/extension_registration_demo.py`
2. 提交 Issue 或 PR 到项目仓库
