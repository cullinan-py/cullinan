---
title: "参数系统指南"
slug: "parameter-system-guide"
module: ["cullinan.web.params", "cullinan.codec"]
tags: ["params", "api", "guide"]
author: "plumeink"
reviewers: []
status: new
locale: zh
translation_pair: "docs/parameter_system_guide.md"
related_tests: ["tests/test_params.py", "tests/test_codec.py", "tests/test_resolver.py"]
related_examples: ["examples/parameter_handling"]
estimate_pd: 2
last_updated: "2026-01-08T00:00:00Z"
pr_links: []
---

# 参数系统指南

> **版本**: 0.90a5+
> 
> 本指南介绍 Cullinan 0.90 版本引入的参数系统，提供类型安全的参数处理，支持自动转换、校验和模型映射。

## 概述

参数系统提供了现代化的 HTTP 请求参数处理方式：

- **类型安全参数**：在函数签名中声明参数类型
- **自动类型转换**：字符串值自动转换为目标类型
- **参数校验**：内置校验器 (ge, le, regex 等)
- **多数据源**：Path, Query, Body, Header, File
- **模型支持**：dataclass 和 DynamicBody
- **自动类型推断**：自动检测值类型
- **文件处理**：FileInfo/FileList 及校验 (v0.90a5+)
- **Dataclass 校验**：@field_validator 装饰器 (v0.90a5+)
- **响应序列化**：ResponseSerializer (v0.90a5+)

## 模块结构

```
cullinan/
├── codec/                    # 编解码层
│   ├── base.py              # BodyCodec / ResponseCodec 抽象
│   ├── errors.py            # DecodeError / EncodeError
│   ├── json_codec.py
│   ├── form_codec.py
│   └── registry.py          # CodecRegistry
├── params/                   # 参数处理层
│   ├── base.py              # Param 基类 + UNSET
│   ├── types.py             # Path/Query/Body/Header/File
│   ├── converter.py         # TypeConverter
│   ├── auto.py              # Auto 类型推断
│   ├── dynamic.py           # DynamicBody + SafeAccessor
│   ├── validator.py         # ParamValidator
│   ├── model.py             # ModelResolver (dataclass)
│   ├── resolver.py          # ParamResolver
│   ├── file_info.py         # FileInfo / FileList (v0.90a5+)
│   ├── dataclass_validators.py  # @field_validator (v0.90a5+)
│   └── response.py          # @Response / ResponseSerializer (v0.90a5+)
└── middleware/
    └── body_decoder.py      # BodyDecoderMiddleware
```

## 快速开始

### 基础用法（推荐语法）

```python
from cullinan import get_api, post_api
from cullinan.web.params import Path, Query, Body

@controller
class UserController:
    
    @get_api(url="/users/{id}")
    async def get_user(self, id: int = Path()):
        # id 已经转换为 int 类型
        return {"id": id}
    
    @get_api(url="/users")
    async def list_users(
        self,
        page: int = Query(default=1, ge=1),
        size: int = Query(default=10, ge=1, le=100),
    ):
        return {"page": page, "size": size}
    
    @post_api(url="/users")
    async def create_user(
        self,
        name: str = Body(required=True),
        age: int = Body(default=0, ge=0),
    ):
        return {"name": name, "age": age}
```

### 纯类型注解作为 Query (v0.90a5+)

纯类型注解会自动作为 Query 参数处理：

```python
@get_api(url="/users")
async def list_users(
    self,
    page: int,          # 等同于 page: int = Query()
    size: int = 10,     # 等同于 size: int = Query(default=10)
    name: str = "",     # 等同于 name: str = Query(default="")
):
    pass
```

### as_required() 快捷方法 (v0.90a5+)

使用 `.as_required()` 声明必填参数：

```python
from cullinan.web.params import Body, File

@post_api(url="/users")
async def create_user(
    self,
    name: str = Body.as_required(min_length=1),
    avatar: File = File.as_required(max_size=5*1024*1024),
):
    pass
```

### 简化语法 (v0.90a5+)

对于带别名的参数（如包含 `-` 的 HTTP 头），直接在类型注解中指定：

```python
from cullinan.web.params import Header, Query, Body, DynamicBody

@post_api(url="/webhook")
async def handle_webhook(
    self,
    # 标准语法：Header(类型, alias="...")
    sign: Header(str, alias="X-Hub-Signature-256"),
    event: Header(str, alias="X-GitHub-Event"),
    request_body: DynamicBody,
):
    pass

@get_api(url="/items")
async def list_items(
    self,
    page: Query(int, default=1, ge=1),
    size: Query(int, default=10, le=100),
):
    pass
```

**要点：**
- 类型作为第一个参数传入 `Header(str, ...)`
- 使用 `alias` 指定实际的 HTTP 头名称
- HTTP 头匹配是**大小写不敏感**的（符合 RFC 7230）
- 支持 `X-Hub-Signature-256`、`X-GitHub-Event` 等带 `-` 的头名称

### 使用 RawBody (v0.90a5+)

获取未解析的原始请求体 (bytes)，用于签名验证或自定义解析：

```python
from cullinan.web.params import Header, RawBody
import hmac
import hashlib

@post_api(url="/webhook")
async def handle_webhook(
    self,
    sign: str = Header(alias="X-Hub-Signature-256"),
    event: str = Header(alias="X-GitHub-Event"),
    raw_body: bytes = RawBody(),  # 推荐语法
):
    # raw_body 是 bytes 类型
    secret = b'your_secret'
    expected = 'sha256=' + hmac.new(secret, raw_body, hashlib.sha256).hexdigest()
    
    if not hmac.compare_digest(sign, expected):
        raise ValueError('签名无效')
    
    # 手动解析请求体
    import json
    data = json.loads(raw_body)
```

**对比：**

| 类型 | 写法 | 返回类型 | 说明 |
|------|------|----------|------|
| `DynamicBody` | `body: DynamicBody = DynamicBody()` | DynamicBody 对象 | 已解析的请求体 |
| `RawBody` | `body: bytes = RawBody()` | bytes | 未解析的原始请求体 |

> **注意**: 使用 `= RawBody()` 或 `= DynamicBody()` 语法可以避免 Python 的 "non-default parameter follows default parameter" 错误。

### 使用 DynamicBody

```python
from cullinan.web.params import DynamicBody

@post_api(url="/users")
async def create_user(self, body: DynamicBody):
    # 属性访问
    print(body.name)
    print(body.age)
    
    # 字典式访问
    email = body.get('email', 'default@example.com')
    
    return body.to_dict()
```

#### DynamicBody 增强方法

**判空方法:**

```python
# 检查字段是否存在
if body.has('email'):
    send_email(body.email)

# 检查字段存在且有值（不是 None、''、[] 等）
if body.has_value('name'):
    process(body.name)

# 检查是否为空
if body.is_empty():
    return {'error': 'No data'}

# 检查字段是否为 None
if body.is_not_null('callback_url'):
    notify(body.callback_url)
```

**嵌套安全访问:**

```python
# 路径式嵌套访问（不抛异常）
city = body.get_nested('user.address.city', 'Unknown')
```

**类型化获取器:**

```python
name = body.get_str('name')        # 缺失返回 ''
age = body.get_int('age')          # 缺失返回 0
price = body.get_float('price')    # 缺失返回 0.0
active = body.get_bool('active')   # 缺失返回 False
tags = body.get_list('tags')       # 缺失返回 []
```

**链式安全访问器:**

```python
# 传统方式可能抛 AttributeError
# city = body.user.address.city

# 链式安全访问器（不抛异常）
city = body.safe.user.address.city.value_or('Unknown')

# 检查存在性
if body.safe.user.email.exists:
    send_email(body.safe.user.email.value)
```

### 使用 dataclass 模型

```python
from dataclasses import dataclass
from typing import Optional

@dataclass
class CreateUserRequest:
    name: str
    age: int = 0
    email: Optional[str] = None

@post_api(url="/users")
async def create_user(self, user: CreateUserRequest):
    # user 是类型化的 dataclass 实例
    return {
        "name": user.name,
        "age": user.age,
        "email": user.email
    }
```

### Dataclass 字段校验 (v0.90a5+)

使用 `@field_validator` 进行自定义字段校验：

```python
from cullinan.web.params import validated_dataclass, field_validator, FieldValidationError

@validated_dataclass
class CreateUserRequest:
    name: str
    email: str
    age: int = 0
    
    @field_validator('email')
    @classmethod
    def validate_email(cls, v):
        if '@' not in str(v):
            raise ValueError('无效的邮箱格式')
        return v
    
    @field_validator('age')
    @classmethod
    def validate_age(cls, v):
        if v < 0 or v > 150:
            raise ValueError('年龄必须在 0 到 150 之间')
        return v

# 实例化时自动校验
try:
    user = CreateUserRequest(name='John', email='invalid', age=25)
except FieldValidationError as e:
    print(f"校验错误: {e.field} - {e.message}")
```

## 参数类型

### Path

URL 路径参数，始终必填。

```python
@get_api(url="/users/{user_id}/posts/{post_id}")
async def get_post(
    self,
    user_id: int = Path(),
    post_id: int = Path(ge=1),
):
    pass
```

### Query

查询字符串参数。

```python
@get_api(url="/search")
async def search(
    self,
    q: str = Query(required=True),
    page: int = Query(default=1),
    limit: int = Query(default=10, ge=1, le=100),
):
    pass
```

### Body

请求体参数。

```python
@post_api(url="/articles")
async def create_article(
    self,
    title: Body(str, required=True, min_length=1, max_length=200),
    content: Body(str, required=True),
    published: Body(bool, default=False),
):
    pass
```

### Header

HTTP 请求头参数。

```python
@get_api(url="/protected")
async def protected_resource(
    self,
    auth: Header(str, alias='Authorization', required=True),
    request_id: Header(str, alias='X-Request-ID', required=False),
):
    pass
```

### File

文件上传参数。在 v0.90a5+ 中返回 `FileInfo`（单文件）或 `FileList`（多文件）。

```python
from cullinan.web.params import File, FileInfo, FileList

@post_api(url="/upload")
async def upload_file(
    self,
    # 新的统一语法: Type = Type(...)
    avatar: File = File(max_size=5*1024*1024),  # 5MB 限制
    document: File = File(allowed_types=['application/pdf']),
):
    # avatar 是 FileInfo 实例 (v0.90a5+)
    print(avatar.filename)      # 原始文件名
    print(avatar.size)          # 文件大小（字节）
    print(avatar.content_type)  # MIME 类型
    avatar.save('/uploads/')    # 保存到磁盘
    pass

# 使用 as_required() 声明必填文件
@post_api(url="/upload-required")
async def upload_required(
    self,
    avatar: File = File.as_required(max_size=5*1024*1024),
):
    pass
```

#### File 参数选项 (v0.90a5+)

| 选项 | 类型 | 说明 |
|------|------|------|
| `max_size` | int | 最大文件大小（字节）|
| `min_size` | int | 最小文件大小（字节）|
| `allowed_types` | list | 允许的 MIME 类型（支持通配符如 `image/*`）|
| `multiple` | bool | 启用多文件上传 |
| `max_count` | int | 最大文件数量（multiple=True 时）|

#### 多文件上传 (v0.90a5+)

```python
@post_api(url="/upload-multiple")
async def upload_multiple(
    self,
    files: File(multiple=True, max_count=10),
):
    # files 是 FileList 实例
    for f in files:
        print(f.filename)
        f.save('/uploads/')
    return {"count": len(files), "total_size": files.total_size}
```

#### FileInfo 方法 (v0.90a5+)

| 方法 | 说明 |
|------|------|
| `filename` | 原始文件名 |
| `size` | 文件大小（字节）|
| `content_type` | MIME 类型 |
| `body` | 原始文件内容（bytes）|
| `extension` | 文件扩展名（不含点）|
| `read()` | 读取文件内容 |
| `read_text(encoding)` | 以文本读取 |
| `save(path)` | 保存到磁盘 |
| `is_image()` | 检查是否是图片 |
| `is_pdf()` | 检查是否是 PDF |
| `match_type(pattern)` | 匹配 MIME 模式 |

## 校验器

内置校验约束：

| 校验器 | 类型 | 说明 |
|--------|------|------|
| `required` | 所有 | 字段必填 |
| `ge` | 数值 | 大于等于 |
| `le` | 数值 | 小于等于 |
| `gt` | 数值 | 大于 |
| `lt` | 数值 | 小于 |
| `min_length` | 字符串/列表 | 最小长度 |
| `max_length` | 字符串/列表 | 最大长度 |
| `regex` | 字符串 | 正则表达式匹配 |

示例：

```python
@post_api(url="/register")
async def register(
    self,
    email: Body(str, regex=r'^[\w.-]+@[\w.-]+\.\w+$'),
    password: Body(str, min_length=8, max_length=128),
    age: Body(int, ge=18, le=120),
):
    pass
```

## 自动类型推断

使用 `AutoType` 进行自动类型检测：

```python
from cullinan.web.params import AutoType

@get_api(url="/search")
async def search(self, value: Query(AutoType)):
    # value 会自动推断类型:
    # "123" -> 123 (int)
    # "12.5" -> 12.5 (float)
    # "true" -> True (bool)
    # '{"a":1}' -> {"a": 1} (dict)
    pass
```

## Codec 系统

### 注册自定义 Codec

```python
from cullinan.codec import BodyCodec, get_codec_registry

class XmlBodyCodec(BodyCodec):
    content_types = ['application/xml', 'text/xml']
    priority = 30
    
    def decode(self, body: bytes, charset: str = 'utf-8'):
        import xml.etree.ElementTree as ET
        root = ET.fromstring(body.decode(charset))
        return {child.tag: child.text for child in root}

# 注册 codec
registry = get_codec_registry()
registry.register_body_codec(XmlBodyCodec)
```

### 请求体解码中间件

`BodyDecoderMiddleware` 自动解码请求体：

```python
from cullinan.web.middleware import BodyDecoderMiddleware, get_decoded_body

# 在处理器中获取已解码的请求体
class MyController:
    @post_api(url="/data")
    async def handle_data(self):
        body = get_decoded_body(self.request)
        return body
```

## 响应序列化 (v0.90a5+)

### ResponseSerializer

自动将 dataclass 和其他对象序列化为 JSON 兼容的字典：

```python
from dataclasses import dataclass
from cullinan.web.params import ResponseSerializer

@dataclass
class UserResponse:
    id: int
    name: str
    email: str

user = UserResponse(id=1, name='John', email='john@example.com')

# 序列化为字典
result = ResponseSerializer.serialize(user)
# {'id': 1, 'name': 'John', 'email': 'john@example.com'}

# 序列化为 JSON 字符串
json_str = ResponseSerializer.to_json(user)
# '{"id": 1, "name": "John", "email": "john@example.com"}'
```

### @Response 装饰器

为 API 文档定义响应模型：

```python
from cullinan.web.params import Response, get_response_models

@dataclass
class SuccessResponse:
    data: dict

@dataclass
class ErrorResponse:
    message: str
    code: int = 0

@Response(model=SuccessResponse, status_code=200, description="成功")
@Response(model=ErrorResponse, status_code=404, description="未找到")
async def get_user(user_id):
    pass

# 获取响应模型用于文档生成
models = get_response_models(get_user)
```

## 向后兼容

传统参数风格完全支持：

```python
# 传统方式（仍然有效）
@post_api(url="/users", body_params=['name', 'age'])
async def create_user(self, body_params):
    name = body_params.get('name')
    age = body_params.get('age')
```

## 错误处理

参数错误返回结构化响应：

```python
from cullinan.web.params import ValidationError, ResolveError

# ValidationError 用于单个参数校验失败
# ResolveError 用于多个参数解析失败

# 错误响应格式：
{
    "error": "参数校验失败",
    "details": [
        {"param": "age", "error": "必须 >= 0", "constraint": "ge:0"}
    ]
}
```

## 最佳实践

1. **使用类型提示**：始终指定参数类型以提高代码清晰度
2. **设置合理的默认值**：为可选参数提供默认值
3. **尽早校验**：使用内置校验器而非手动检查
4. **复杂请求体使用模型**：结构化请求体使用 dataclass
5. **灵活场景使用 DynamicBody**：请求体结构变化时使用

## 可插拔模型处理器 (v0.90a5+)

框架使用可插拔架构进行模型解析，允许 Pydantic 等第三方库在不修改核心代码的情况下集成。

### 内置处理器

| 处理器 | 优先级 | 说明 |
|--------|--------|------|
| `DataclassHandler` | 10 | Python dataclass 支持 |
| `PydanticHandler` | 50 | Pydantic BaseModel（如果已安装）|

### 注册自定义处理器

```python
from cullinan.web.params import ModelHandler, get_model_handler_registry

class MyModelHandler(ModelHandler):
    priority = 100  # 数值越大优先级越高
    name = "my_handler"
    
    def can_handle(self, type_):
        # 如果能处理该类型返回 True
        return hasattr(type_, '__my_model__')
    
    def resolve(self, model_class, data):
        # 将数据解析为模型实例
        return model_class.from_dict(data)
    
    def to_dict(self, instance):
        # 将实例转换为字典
        return instance.to_dict()

# 注册处理器
registry = get_model_handler_registry()
registry.register(MyModelHandler())
```

### Pydantic 集成（可选）

当 Pydantic 已安装时，`PydanticHandler` 会自动注册：

```python
from pydantic import BaseModel, Field, EmailStr

class CreateUserRequest(BaseModel):
    name: str = Field(..., min_length=2, max_length=50)
    email: EmailStr
    age: int = Field(default=0, ge=0, le=150)

@post_api(url="/users")
async def create_user(self, user: CreateUserRequest):
    # Pydantic 校验自动执行
    return {"name": user.name, "email": user.email}
```

安装 Pydantic: `pip install pydantic`

## API 参考

### cullinan.web.params

| 类 | 说明 |
|---|------|
| `Param` | 参数基类 |
| `Path` | URL 路径参数 |
| `Query` | 查询字符串参数 |
| `Body` | 请求体参数 |
| `Header` | HTTP 请求头参数 |
| `File` | 文件上传参数 |
| `RawBody` | 原始请求体，使用 `bytes = RawBody()` (v0.90a5+) |
| `TypeConverter` | 类型转换工具 |
| `Auto` | 自动类型推断 |
| `AutoType` | 自动类型标记 |
| `DynamicBody` | 动态请求体容器 |
| `SafeAccessor` | 链式安全访问器 (v0.90a4+) |
| `ParamValidator` | 参数校验器 |
| `ModelResolver` | dataclass 模型解析器 |
| `ParamResolver` | 参数解析编排器 |
| `FileInfo` | 文件元数据容器 (v0.90a5+) |
| `FileList` | 多文件容器 (v0.90a5+) |
| `field_validator` | Dataclass 字段校验装饰器 (v0.90a5+) |
| `validated_dataclass` | 自动校验的 dataclass 装饰器 (v0.90a5+) |
| `FieldValidationError` | 字段校验错误 (v0.90a5+) |
| `Response` | 响应模型装饰器 (v0.90a5+) |
| `ResponseSerializer` | 响应序列化工具 (v0.90a5+) |
| `ModelHandler` | 模型处理器基类 (v0.90a5+) |
| `ModelHandlerRegistry` | 模型处理器注册表 (v0.90a5+) |
| `DataclassHandler` | 内置 dataclass 处理器 (v0.90a5+) |
| `get_model_handler_registry` | 获取全局处理器注册表 (v0.90a5+) |

### cullinan.codec

| 类 | 说明 |
|---|------|
| `BodyCodec` | 请求体编解码器抽象类 |
| `ResponseCodec` | 响应编码器抽象类 |
| `JsonBodyCodec` | JSON 请求体解码器 |
| `JsonResponseCodec` | JSON 响应编码器 |
| `FormBodyCodec` | Form 请求体解码器 |
| `CodecRegistry` | Codec 注册表 |
| `DecodeError` | 解码错误 |
| `EncodeError` | 编码错误 |

### cullinan.web.middleware

| 类 | 说明 |
|---|------|
| `BodyDecoderMiddleware` | 自动请求体解码中间件 |
| `get_decoded_body()` | 获取已解码的请求体 |
