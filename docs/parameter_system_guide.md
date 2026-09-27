---
title: "Parameter System Guide"
slug: "parameter-system-guide"
module: ["cullinan.web.params", "cullinan.codec"]
tags: ["params", "api", "guide"]
author: "plumeink"
reviewers: []
status: new
locale: en
translation_pair: "docs/zh/parameter_system_guide.md"
related_tests: ["tests/test_params.py", "tests/test_codec.py", "tests/test_resolver.py"]
related_examples: ["examples/parameter_handling"]
estimate_pd: 2
last_updated: "2026-01-08T00:00:00Z"
pr_links: []
---

# Parameter System Guide

> **Version**: 0.90a5+
> 
> This guide covers the parameter system introduced in Cullinan 0.90, providing type-safe parameter handling with automatic conversion, validation, and model support.

## Overview

The parameter system provides a modern approach to handling HTTP request parameters:

- **Type-safe parameters**: Declare parameter types in function signatures
- **Automatic conversion**: String values converted to target types
- **Validation**: Built-in validators (ge, le, regex, etc.)
- **Multiple sources**: Path, Query, Body, Header, File
- **Model support**: dataclass and DynamicBody
- **Auto type inference**: Automatic type detection
- **File handling**: FileInfo/FileList with validation (v0.90a5+)
- **Dataclass validation**: @field_validator decorator (v0.90a5+)
- **Response serialization**: ResponseSerializer (v0.90a5+)

## Module Structure

```
cullinan/
├── codec/                    # Encoding/Decoding layer
│   ├── base.py              # BodyCodec / ResponseCodec abstractions
│   ├── errors.py            # DecodeError / EncodeError
│   ├── json_codec.py
│   ├── form_codec.py
│   └── registry.py          # CodecRegistry
├── params/                   # Parameter handling layer
│   ├── base.py              # Param base class + UNSET
│   ├── types.py             # Path/Query/Body/Header/File
│   ├── converter.py         # TypeConverter
│   ├── auto.py              # Auto type inference
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

## Quick Start

### Basic Usage (Recommended Syntax)

```python
from cullinan import get_api, post_api
from cullinan.web.params import Path, Query, Body

@controller
class UserController:
    
    @get_api(url="/users/{id}")
    async def get_user(self, id: int = Path()):
        # id is already converted to int
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

### Pure Type Annotation as Query (v0.90a5+)

Pure type annotations are automatically treated as Query parameters:

```python
@get_api(url="/users")
async def list_users(
    self,
    page: int,          # Same as page: int = Query()
    size: int = 10,     # Same as size: int = Query(default=10)
    name: str = "",     # Same as name: str = Query(default="")
):
    pass
```

### as_required() Shortcut (v0.90a5+)

Use `.as_required()` for required parameters:

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

### Simplified Syntax (v0.90a5+)

For parameters with alias (like HTTP headers with `-`), specify directly in type annotation:

```python
from cullinan.web.params import Header, Query, Body, DynamicBody

@post_api(url="/webhook")
async def handle_webhook(
    self,
    # Standard syntax: Header(type, alias="...")
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

**Key Points:**
- Type is passed as the first argument `Header(str, ...)`
- Use `alias` to specify the actual HTTP header name
- HTTP header matching is **case-insensitive** (per RFC 7230)
- Supports headers with `-` like `X-Hub-Signature-256`, `X-GitHub-Event`

### Using RawBody (v0.90a5+)

Get the raw unparsed request body (bytes) for signature verification or custom parsing:

```python
from cullinan.web.params import Header, RawBody
import hmac
import hashlib

@post_api(url="/webhook")
async def handle_webhook(
    self,
    sign: str = Header(alias="X-Hub-Signature-256"),
    event: str = Header(alias="X-GitHub-Event"),
    raw_body: bytes = RawBody(),  # Recommended syntax
):
    # raw_body is bytes
    secret = b'your_secret'
    expected = 'sha256=' + hmac.new(secret, raw_body, hashlib.sha256).hexdigest()
    
    if not hmac.compare_digest(sign, expected):
        raise ValueError('Invalid signature')
    
    # Manually parse the body
    import json
    data = json.loads(raw_body)
```

**Comparison:**

| Type | Syntax | Return Type | Description |
|------|--------|-------------|-------------|
| `DynamicBody` | `body: DynamicBody = DynamicBody()` | DynamicBody object | Parsed request body |
| `RawBody` | `body: bytes = RawBody()` | bytes | Unparsed raw request body |

> **Note**: Use `= RawBody()` or `= DynamicBody()` syntax to avoid Python's "non-default parameter follows default parameter" error.

### Using DynamicBody

```python
from cullinan.web.params import DynamicBody

@post_api(url="/users")
async def create_user(self, body: DynamicBody):
    # Access fields as attributes
    print(body.name)
    print(body.age)
    
    # Or use dict-like access
    email = body.get('email', 'default@example.com')
    
    return body.to_dict()
```

#### DynamicBody Enhanced Methods

**Null Checking:**

```python
# Check if field exists
if body.has('email'):
    send_email(body.email)

# Check if field exists and has value (not None, '', [], etc.)
if body.has_value('name'):
    process(body.name)

# Check if body is empty
if body.is_empty():
    return {'error': 'No data'}

# Check if field is null/not null
if body.is_not_null('callback_url'):
    notify(body.callback_url)
```

**Nested Safe Access:**

```python
# Path-based nested access (no exceptions)
city = body.get_nested('user.address.city', 'Unknown')
```

**Typed Getters:**

```python
name = body.get_str('name')        # '' if missing
age = body.get_int('age')          # 0 if missing
price = body.get_float('price')    # 0.0 if missing
active = body.get_bool('active')   # False if missing
tags = body.get_list('tags')       # [] if missing
```

**Chain-Safe Accessor:**

```python
# Traditional way may throw AttributeError
# city = body.user.address.city

# Chain-safe accessor (no exceptions)
city = body.safe.user.address.city.value_or('Unknown')

# Check existence
if body.safe.user.email.exists:
    send_email(body.safe.user.email.value)
```

### Using dataclass Models

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
    # user is a typed dataclass instance
    return {
        "name": user.name,
        "age": user.age,
        "email": user.email
    }
```

### Dataclass Field Validation (v0.90a5+)

Use `@field_validator` for custom field validation:

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
            raise ValueError('Invalid email format')
        return v
    
    @field_validator('age')
    @classmethod
    def validate_age(cls, v):
        if v < 0 or v > 150:
            raise ValueError('Age must be between 0 and 150')
        return v

# Validation is automatic on instantiation
try:
    user = CreateUserRequest(name='John', email='invalid', age=25)
except FieldValidationError as e:
    print(f"Validation error: {e.field} - {e.message}")
```

## Parameter Types

### Path

URL path parameters, always required.

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

Query string parameters.

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

Request body parameters.

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

HTTP header parameters.

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

File upload parameters. Returns `FileInfo` (single) or `FileList` (multiple) in v0.90a5+.

```python
from cullinan.web.params import File, FileInfo, FileList

@post_api(url="/upload")
async def upload_file(
    self,
    # New unified syntax: Type = Type(...)
    avatar: File = File(max_size=5*1024*1024),  # 5MB limit
    document: File = File(allowed_types=['application/pdf']),
):
    # avatar is a FileInfo instance (v0.90a5+)
    print(avatar.filename)      # Original filename
    print(avatar.size)          # File size in bytes
    print(avatar.content_type)  # MIME type
    avatar.save('/uploads/')    # Save to disk
    pass

# Required file using as_required()
@post_api(url="/upload-required")
async def upload_required(
    self,
    avatar: File = File.as_required(max_size=5*1024*1024),
):
    pass
```

#### File Parameter Options (v0.90a5+)

| Option | Type | Description |
|--------|------|-------------|
| `max_size` | int | Maximum file size in bytes |
| `min_size` | int | Minimum file size in bytes |
| `allowed_types` | list | Allowed MIME types (supports wildcards like `image/*`) |
| `multiple` | bool | Enable multiple file upload |
| `max_count` | int | Maximum number of files (when multiple=True) |

#### Multiple File Upload (v0.90a5+)

```python
@post_api(url="/upload-multiple")
async def upload_multiple(
    self,
    files: File(multiple=True, max_count=10),
):
    # files is a FileList instance
    for f in files:
        print(f.filename)
        f.save('/uploads/')
    return {"count": len(files), "total_size": files.total_size}
```

#### FileInfo Methods (v0.90a5+)

| Method | Description |
|--------|-------------|
| `filename` | Original filename |
| `size` | File size in bytes |
| `content_type` | MIME type |
| `body` | Raw file content (bytes) |
| `extension` | File extension (without dot) |
| `read()` | Read file content |
| `read_text(encoding)` | Read as text |
| `save(path)` | Save to disk |
| `is_image()` | Check if image |
| `is_pdf()` | Check if PDF |
| `match_type(pattern)` | Match MIME pattern |

## Validators

Built-in validation constraints:

| Validator | Types | Description |
|-----------|-------|-------------|
| `required` | All | Field is required |
| `ge` | Numeric | Greater than or equal |
| `le` | Numeric | Less than or equal |
| `gt` | Numeric | Greater than |
| `lt` | Numeric | Less than |
| `min_length` | String/List | Minimum length |
| `max_length` | String/List | Maximum length |
| `regex` | String | Regular expression match |

Example:

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

## Auto Type Inference

Use `AutoType` for automatic type detection:

```python
from cullinan.web.params import AutoType

@get_api(url="/search")
async def search(self, value: Query(AutoType)):
    # value will be auto-inferred:
    # "123" -> 123 (int)
    # "12.5" -> 12.5 (float)
    # "true" -> True (bool)
    # '{"a":1}' -> {"a": 1} (dict)
    pass
```

## Codec System

### Registering Custom Codecs

```python
from cullinan.codec import BodyCodec, get_codec_registry

class XmlBodyCodec(BodyCodec):
    content_types = ['application/xml', 'text/xml']
    priority = 30
    
    def decode(self, body: bytes, charset: str = 'utf-8'):
        import xml.etree.ElementTree as ET
        root = ET.fromstring(body.decode(charset))
        return {child.tag: child.text for child in root}

# Register the codec
registry = get_codec_registry()
registry.register_body_codec(XmlBodyCodec)
```

### Body Decoder Middleware

The `BodyDecoderMiddleware` automatically decodes request bodies:

```python
from cullinan.web.middleware import BodyDecoderMiddleware, get_decoded_body

# Access decoded body in handlers
class MyController:
    @post_api(url="/data")
    async def handle_data(self):
        body = get_decoded_body(self.request)
        return body
```

## Response Serialization (v0.90a5+)

### ResponseSerializer

Automatically serialize dataclass and other objects to JSON-compatible dicts:

```python
from dataclasses import dataclass
from cullinan.web.params import ResponseSerializer

@dataclass
class UserResponse:
    id: int
    name: str
    email: str

user = UserResponse(id=1, name='John', email='john@example.com')

# Serialize to dict
result = ResponseSerializer.serialize(user)
# {'id': 1, 'name': 'John', 'email': 'john@example.com'}

# Serialize to JSON string
json_str = ResponseSerializer.to_json(user)
# '{"id": 1, "name": "John", "email": "john@example.com"}'
```

### @Response Decorator

Define response models for API documentation:

```python
from cullinan.web.params import Response, get_response_models

@dataclass
class SuccessResponse:
    data: dict

@dataclass
class ErrorResponse:
    message: str
    code: int = 0

@Response(model=SuccessResponse, status_code=200, description="Success")
@Response(model=ErrorResponse, status_code=404, description="Not found")
async def get_user(user_id):
    pass

# Get response models for documentation
models = get_response_models(get_user)
```

## Backward Compatibility

The traditional parameter style is fully supported:

```python
# Traditional style (still works)
@post_api(url="/users", body_params=['name', 'age'])
async def create_user(self, body_params):
    name = body_params.get('name')
    age = body_params.get('age')
```

## Error Handling

Parameter errors return structured responses:

```python
from cullinan.web.params import ValidationError, ResolveError

# ValidationError for single parameter failures
# ResolveError for multiple parameter failures

# Error response format:
{
    "error": "Parameter validation failed",
    "details": [
        {"param": "age", "error": "must be >= 0", "constraint": "ge:0"}
    ]
}
```

## Best Practices

1. **Use type hints**: Always specify parameter types for clarity
2. **Set sensible defaults**: Provide defaults for optional parameters
3. **Validate early**: Use built-in validators instead of manual checks
4. **Use models for complex bodies**: dataclass for structured request bodies
5. **Use DynamicBody for flexibility**: When body structure varies

## Pluggable Model Handlers (v0.90a5+)

The framework uses a pluggable architecture for model parsing, allowing third-party libraries like Pydantic to be integrated without modifying core code.

### Built-in Handlers

| Handler | Priority | Description |
|---------|----------|-------------|
| `DataclassHandler` | 10 | Python dataclass support |
| `PydanticHandler` | 50 | Pydantic BaseModel (if installed) |

### Registering Custom Handlers

```python
from cullinan.web.params import ModelHandler, get_model_handler_registry

class MyModelHandler(ModelHandler):
    priority = 100  # Higher = matched first
    name = "my_handler"
    
    def can_handle(self, type_):
        # Return True if this handler can process the type
        return hasattr(type_, '__my_model__')
    
    def resolve(self, model_class, data):
        # Parse data into model instance
        return model_class.from_dict(data)
    
    def to_dict(self, instance):
        # Convert instance to dict
        return instance.to_dict()

# Register the handler
registry = get_model_handler_registry()
registry.register(MyModelHandler())
```

### Pydantic Integration (Optional)

When Pydantic is installed, `PydanticHandler` is automatically registered:

```python
from pydantic import BaseModel, Field, EmailStr

class CreateUserRequest(BaseModel):
    name: str = Field(..., min_length=2, max_length=50)
    email: EmailStr
    age: int = Field(default=0, ge=0, le=150)

@post_api(url="/users")
async def create_user(self, user: CreateUserRequest):
    # Pydantic validation is automatic
    return {"name": user.name, "email": user.email}
```

Install Pydantic: `pip install pydantic`

## API Reference

### cullinan.web.params

| Class | Description |
|-------|-------------|
| `Param` | Base parameter class |
| `Path` | URL path parameter |
| `Query` | Query string parameter |
| `Body` | Request body parameter |
| `Header` | HTTP header parameter |
| `File` | File upload parameter |
| `RawBody` | Raw unparsed request body, use `bytes = RawBody()` (v0.90a5+) |
| `TypeConverter` | Type conversion utility |
| `Auto` | Auto type inference |
| `AutoType` | Auto type marker |
| `DynamicBody` | Dynamic request body container |
| `SafeAccessor` | Chain-safe property accessor (v0.90a4+) |
| `ParamValidator` | Parameter validation |
| `ModelResolver` | dataclass model resolution |
| `ParamResolver` | Parameter resolution orchestrator |
| `FileInfo` | File metadata container (v0.90a5+) |
| `FileList` | Multiple files container (v0.90a5+) |
| `field_validator` | Dataclass field validator decorator (v0.90a5+) |
| `validated_dataclass` | Auto-validating dataclass decorator (v0.90a5+) |
| `FieldValidationError` | Field validation error (v0.90a5+) |
| `Response` | Response model decorator (v0.90a5+) |
| `ResponseSerializer` | Response serialization utility (v0.90a5+) |
| `ModelHandler` | Base class for model handlers (v0.90a5+) |
| `ModelHandlerRegistry` | Model handler registry (v0.90a5+) |
| `DataclassHandler` | Built-in dataclass handler (v0.90a5+) |
| `get_model_handler_registry` | Get global handler registry (v0.90a5+) |

### cullinan.codec

| Class | Description |
|-------|-------------|
| `BodyCodec` | Request body codec abstract class |
| `ResponseCodec` | Response codec abstract class |
| `JsonBodyCodec` | JSON body decoder |
| `JsonResponseCodec` | JSON response encoder |
| `FormBodyCodec` | Form body decoder |
| `CodecRegistry` | Codec registry |
| `DecodeError` | Decoding error |
| `EncodeError` | Encoding error |

### cullinan.web.middleware

| Class | Description |
|-------|-------------|
| `BodyDecoderMiddleware` | Auto body decoding middleware |
| `get_decoded_body()` | Get decoded request body |
