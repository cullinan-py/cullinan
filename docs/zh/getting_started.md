title: "Cullinan 快速开始"
slug: "getting-started"
module: ["cullinan"]
tags: ["getting-started", "tutorial"]
author: "plumeink"
reviewers: []
status: updated
locale: zh
translation_pair: "docs/getting_started.md"
related_tests: ["tests/core/test_application_model_refactor.py", "tests/integration/test_adapter_integration.py"]
related_examples: ["examples/minimal_app"]
estimate_pd: 2.0
last_updated: "2026-06-01T00:00:00Z"
pr_links: []

# Cullinan 快速开始

本页提供最小化的快速入门，说明如何安装并运行 Cullinan 示例应用。
核心心智是：先用装饰器声明业务方法与组件，再由运行时完成装配；
Cullinan 不是围绕手工组装 app 对象展开的框架。

> **推荐下一步：** [框架语义](framework_semantics.md)、[工程实践](how-to/index.md)  
> **仓库可运行指引：** `examples/minimal_app/` 是当前维护中的最小示例。<br>
> **高级边界：** 如果你明确需要显式 `Application` 编排，请进入
> [运行时与扩展](internals/index.md)，不要把那条路径当成默认启动方式。

## 前置条件
- Python 3.9+
- Git

## 安装

在继续之前，请确保已经安装 Python 3.9+ 并可以在命令行中使用 `python` 和 `pip`。

在大多数环境中，可以使用以下命令升级 pip 并安装 Cullinan（适用于 Windows、Linux、macOS）：

```bash
python -m pip install -U pip
python -m pip install cullinan
```

## 快速开始
1. 在你希望放置项目的目录创建一个新项目目录并进入：

在所有平台上：

```bash
mkdir my_cullinan_project
cd my_cullinan_project
```

2. 确保你已有一个 Python 环境（virtualenv、conda、系统 Python 等均可）。然后安装发布版本的包：

```bash
python -m pip install -U pip
python -m pip install cullinan
```

3. 在项目根目录创建一个最小应用文件 `minimal_app.py`，内容如下：

```python
# minimal_app.py
from cullinan import application, configure
from cullinan.core import service
from cullinan.web import controller, get_api


@service
class GreetingService:
    def greet(self) -> str:
        return "Hello from Cullinan!"


@controller(url="/hello")
class HelloController:
    """简单的 HTTP 控制器。"""

    greeting_service: GreetingService  # ← 构造注入 (constructor injection)

    @get_api(url="")
    def hello(self):
        return {"message": self.greeting_service.greet()}


@configure(user_packages=["my_cullinan_project"])
@application
def main(): ...

if __name__ == '__main__':
    main()
```

4. 运行你的应用：

在 Windows（PowerShell）中：

```powershell
python minimal_app.py
```

在 Linux / macOS 中：

```bash
python minimal_app.py
```

在浏览器中打开 `http://localhost:4080/hello` 验证服务器是否启动。

## 这个示例展示了什么

- 你主要写的是 `@service`、`@controller` 和处理方法等业务声明
- `@application` 用来声明默认入口方法
- `@configure(...)` 用来把启动配置附着到这个方法上
- `@module` 不是默认必需项，只在你需要显式高级运行时边界时使用
- 纯类型注解启用构造注入，会从活动应用上下文中解析控制器依赖
- 直接调用入口方法会通过框架默认启动路径完成装配并启动服务

## 最小应用示例

这是一个演示 Cullinan 核心功能的最小应用：

```python
# minimal_app.py
from cullinan import application, configure
from cullinan.core import service
from cullinan.web import controller, get_api


@service
class GreetingService:
    def greet(self) -> str:
        return "Hello from Cullinan!"


@controller(url="/hello")
class HelloController:
    greeting_service: GreetingService  # ← 构造注入 (constructor injection)

    @get_api(url="")
    def hello(self):
        return {"message": self.greeting_service.greet()}


@configure(user_packages=["my_cullinan_project"])
@application
def main(): ...

if __name__ == "__main__":
    main()
```

运行此示例：

```powershell
# 将上述代码保存为 minimal_app.py
python minimal_app.py
```

然后在浏览器中访问 `http://localhost:4080/hello`。

## 理解基础知识

### 应用生命周期
1. **声明入口**：`@application` 标记入口方法，`@configure(...)` 把启动配置附着到这个方法上
2. **发现与装配**：调用 `main()` 会导入所属包、完成待注册装饰器项收口，并在框架管理的运行时边界下装配业务组件
3. **激活**：通过校验的 runtime 成为活动 runtime，并通过框架选择的后端路径对外提供服务
4. **Reload / 关闭**：旧 runtime 会先 drain 飞行中请求，然后再关闭

### 依赖注入
Cullinan 通过装饰器驱动的组件发现与运行时管理的装配流程提供内置 IoC/DI 支持。

#### 推荐运行时模型

- 业务服务使用 `@service`
- HTTP 控制器使用 `@controller`
- 使用纯类型注解进行构造注入（推荐）
- 需要显式注入时使用 `Inject()`
- 按名称解析更方便时使用 `InjectByName()`
- 先从业务装饰器和入口方法开始
- 只有在需要包归属、热插拔模块或更严格的 reload / draining 边界时再引入 `@module`
- 如果你明确需要底层容器或运行时内部机制，请转到 [运行时与扩展](internals/index.md)，不要把那条路径当成快速开始模型

```python
from cullinan.web import controller, get_api, Path
from cullinan.core import service

@service
class UserService:
    def get_user(self, user_id):
        return {'id': user_id, 'name': 'John'}

@controller(url='/api/users')
class UserController:
    user_service: UserService  # ← 构造注入 (constructor injection)

    @get_api(url='/{user_id}')
    async def get_user(self, user_id: int = Path()):
        return self.user_service.get_user(user_id)
```

**兼容性说明：** `injectable` 和 `inject_constructor` 仍然存在，但只是兼容 shim；新代码不应再把它们作为主要模式。

---

#### RESTful API 装饰器（快速说明）

Cullinan 提供一组 REST 风格的装饰器，用于将 Controller 方法绑定到 HTTP 路由：

- `get_api`
- `post_api`
- `patch_api`
- `delete_api`
- `put_api`

关键点：

- 这些装饰器在源码中定义为 `def get_api(**kwargs)` 等，**只接受关键字参数**。
  - 写法 `@get_api('/user')` 是**不合法**的，会在导入模块时抛出 `TypeError`。
  - 正确写法应为：`@get_api(url='/user')`。
- `url` 参数使用轻量级模板语法，支持 `{param}` 占位符。

**v0.90+ 推荐：类型安全参数系统**

```python
from cullinan.web.params import Path, Query, Body, DynamicBody

@controller(url='/api/users')
class UserController:
    # 类型安全的路径和查询参数（新的统一语法）
    @get_api(url='/{id}')
    async def get_user(self, id: int = Path(), include_posts: bool = Query(default=False)):
        return {"id": id, "include_posts": include_posts}
    
    # 纯类型注解作为 Query（v0.90a5+）
    @get_api(url='/')
    async def list_users(
        self,
        page: int = 1,      # 等同于 Query(default=1)
        size: int = 10,     # 等同于 Query(default=10)
    ):
        return {"page": page, "size": size}
    
    # 带校验的类型安全请求体参数
    @post_api(url='/')
    async def create_user(
        self,
        name: str = Body(required=True),
        age: int = Body(default=0, ge=0, le=150),
    ):
        return {"name": name, "age": age}
    
    # DynamicBody 提供灵活的属性访问
    @post_api(url='/dynamic')
    async def create_dynamic(self, body: DynamicBody):
        return {"name": body.name, "age": body.get('age', 0)}
```

详见 [参数系统指南](parameter_system_guide.md)，包括：
- 使用 `FileInfo`/`FileList` 的文件上传
- 使用 `@field_validator` 的 Dataclass 校验
- Pydantic 集成（可选，使用 `pip install pydantic` 安装）
- 自定义模型处理器

<details>
<summary><strong>传统方式（仍然支持）</strong></summary>

传统参数风格仍然支持，用于向后兼容：

常用参数：
- `url`：路由路径（字符串），支持 `{param}` 占位符，例如 `'/users/{user_id}'`。
- `query_params`：查询参数名称列表/元组，例如 `('page', 'size')`。
- `body_params`（仅 POST/PATCH）：需要从 JSON/form body 中解析的字段名称集合。
- `file_params`：上传文件字段名称列表。
- `headers`：必须存在的 HTTP 请求头名称列表。
- `get_request_body`（仅 POST/PATCH）：为 `True` 时，会将原始请求体作为参数传入方法。

```python
@controller(url='/api/users')
class UserController:
    @get_api(url='/{user_id}')
    def get_user(self, url_params):
        user_id = url_params.get('user_id') if url_params else None
        return {"id": user_id}

    @get_api(url='/', query_params=('page', 'size'))
    def list_users(self, query_params):
        page = query_params.get('page') if query_params else None
        size = query_params.get('size') if query_params else None
        return {"page": page, "size": size}

    @post_api(url='/', body_params=('name', 'email'))
    def create_user(self, body_params):
        name = body_params.get('name') if body_params else None
        email = body_params.get('email') if body_params else None
        return {"name": name, "email": email}
```

</details>

如需了解 URL 模板与各装饰器参数的完整说明，请参考 `wiki/restful_api.md`。

---

#### 推荐的依赖注入方式

**方式一：构造注入（推荐）**

优先使用纯类型注解进行构造注入——最简洁、最符合惯用法：

```python
from cullinan.core import service

@service
class DatabaseService:
    def query(self, sql):
        return f"Results for: {sql}"

@service
class UserRepository:
    db: DatabaseService  # ← 构造注入 (constructor injection)

    def get_users(self):
        return self.db.query("SELECT * FROM users")
```

**方式二：Inject**

当需要显式注入语义或维护旧代码时，使用带类型的 `Inject()`：

```python
from cullinan.core import Inject, service

@service
class DatabaseService:
    def query(self, sql):
        return f"Results for: {sql}"

@service
class UserRepository:
    db: DatabaseService = Inject()

    def get_users(self):
        return self.db.query("SELECT * FROM users")
```

**方式三：InjectByName**

按名称注入，无需导入依赖类，避免循环导入问题：

```python
from cullinan.core import InjectByName, service

@service
class DatabaseService:
    def query(self, sql):
        return f"Results for: {sql}"

@service
class UserRepository:
    db = InjectByName('DatabaseService')
    
    def get_users(self):
        return self.db.query("SELECT * FROM users")
```

**方式四：Inject + TYPE_CHECKING（支持 IDE 联想）**

如果需要 IDE 自动补全和类型检查，可以使用 `Inject` 配合 TYPE_CHECKING：

```python
from typing import TYPE_CHECKING
from cullinan.core import Inject, service

# TYPE_CHECKING 块中的导入不会在运行时执行，避免循环导入
if TYPE_CHECKING:
    from my_project.services import DatabaseService

@service
class DatabaseService:
    def query(self, sql):
        return f"Results for: {sql}"

@service
class UserRepository:
    db: 'DatabaseService' = Inject()
    
    def get_users(self):
        return self.db.query("SELECT * FROM users")
```

**总结：**
- **构造注入（纯类型注解）**：推荐默认方式——最简洁、最符合惯用法
- **Inject**：兼容旧代码的显式注入语法，或需要显式注入语义时使用
- **InjectByName**：适合解耦或规避循环导入
- **Inject + TYPE_CHECKING**：兼顾运行时解耦与编辑器类型支持

有关注入模式的详细信息，请参阅 `wiki/injection.md`。

## 常见模式

### 添加中间件
```python
from cullinan.web.middleware import MiddlewareBase

class LoggingMiddleware(MiddlewareBase):
    def process_request(self, request):
        print(f"Request: {request.method} {request.path}")

# 在应用初始化期间注册
app.add_middleware(LoggingMiddleware())
```

### 配置
```python
from cullinan.support.config import Config

config = Config()
config.set('database.url', 'postgresql://localhost/mydb')
config.set('server.port', 8080)
```

## 故障排查
- 如果安装包时出现错误，请确保 Python 和 pip 已更新，并且能访问 PyPI（网络或代理设置）。
- 如果在运行 PowerShell 命令时遇到权限问题，请检查 PowerShell 的执行策略或以管理员权限运行命令。

## 下一步
- 阅读 `wiki/injection.md` 了解 IoC/DI 细节。
- 浏览 `examples/` 目录查看可运行示例。

## 其他资源

- **架构**：参阅 `architecture.md` 了解系统设计概览
- **应用运行时**：阅读 `wiki/application_runtime.md` 了解模块图、归属与 draining
- **组件**：阅读 `wiki/components.md` 了解组件职责
- **生命周期**：在 `wiki/lifecycle.md` 中学习应用生命周期
- **中间件**：在 `wiki/middleware.md` 中理解中间件
- **API 参考**：浏览 `api_reference.md` 查看完整 API 文档
- **示例**：探索 `examples/` 目录获取更多示例

## 社区与支持

- **问题反馈**：在 [GitHub Issues](https://github.com/your-org/cullinan/issues) 报告 bug
- **贡献**：参阅 `contributing.md` 了解贡献指南
- **测试**：阅读 `testing.md` 了解测试最佳实践
