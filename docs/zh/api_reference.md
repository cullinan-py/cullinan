title: "API 参考"
slug: "api-reference"
module: []
tags: ["api", "reference"]
author: "plumeink"
reviewers: []
status: updated
locale: zh
translation_pair: "docs/api_reference.md"
related_tests: []
related_examples: []
estimate_pd: 1.5
last_updated: "2026-06-01T00:00:00Z"
pr_links: []

# API 参考

> **说明（v0.90）**：核心模块已重新组织。新的 API 结构请参阅 [依赖注入指南](dependency_injection_guide.md) 和 [导入迁移指南](import_migration_090.md)。

本页概览 Cullinan 的公开 API，并明确哪些 API 属于推荐路径、哪些属于高级集成能力。

> **如果你还没建立推荐学习路径：** 请先看 [应用构建](start/index.md)
> 和 [框架语义](concepts/index.md)。  
> **如果你要进入高级运行时内部机制：** 请转到 [运行时与扩展](internals/index.md)。

## API 分层

### 推荐默认 API

- `cullinan` —— 常规业务项目应优先使用的顶层应用 API：
  - 启动入口：`@application`、`configure(...)`，然后直接调用入口方法（例如 `main()`）
  - 声明入口：`@service`、`@controller`、`@module`（高级边界）、路由装饰器
  - 注入 / 参数：`Inject`、`InjectByName`、`Path`、`Query`、`Body` 等
  - 框架心智：装饰器优先的业务代码、组件发现、IoC/DI 装配，以及带有热插拔语义的模块边界

### 高级集成 API

- `cullinan.application` —— 面向维护者与框架感知型集成的高级公开应用语义（`Application`、`Runtime`、`module`、`run`、`get_asgi_app`）
- `cullinan.transport.adapter` —— 服务器集成（`WebAdapter`、`TornadoAdapter`、`ASGIAdapter`）
- `cullinan.web.gateway` —— 请求 / 响应 / dispatcher 契约
- `cullinan.core` —— 低层容器与生命周期原语

这些高级模块都不是默认的应用开发心智模型。常规业务代码应停留在顶层 `cullinan` API，以及框架自身的装饰器 / DI / 模块边界语义上，而不是转向低层运行时编排或具体服务器适配器。

对于常规应用，请优先使用顶层 `cullinan` API。高级模块应显式从对应子模块导入，这样在代码评审、IDE 补全和 onboarding 文档中都能更清楚地看到边界。

## 公开 API 稳定冻结（1.0）

**1.0 公开 API 冻结**把此前较窄的导出冻结升级为 1.0 线的稳定契约。它包含三部分：

- **生效时点** —— 宣告于 **2026-09-27**。**`1.0` 线尚未发布。** 本节宣告的是 1.0 线自此刻起将承载的稳定契约，并非「`1.0` 已发布」的声明。自此之后，对冻结集合内符号的任何改动均属冻结后变更。
- **范围** —— 恰为四个包的 `__all__` 列表，冻结粒度为**符号名**（签名、字段类型与默认值不在此契约内）：

  | 契约 | 符号数 |
  |---|---|
  | `cullinan.__all__` —— 常规应用应使用的启动、声明与请求处理 API | 44 |
  | `cullinan.application.__all__` —— 高级 application/runtime 辅助入口，包括 `run()` 与 `get_asgi_app()` | 26 |
  | `cullinan.web.__all__` —— 显式业务 Web 面 | 34 |
  | `cullinan.core.__all__` —— 容器与生命周期面 | 72 |

  `cullinan.web.gateway.__all__` 门面**不在此契约内**：它是分层、需显式导入的集成面，而非冻结的稳定性承诺。

  四条冻结列表合起来即**稳定性承诺面**（stability commitment surface；机器可读产物中的字段名为 `stability_commitment`）。它比泛指的**公共面**（public API surface）更窄：`cullinan.web.gateway` 等需显式导入的门面属于公共面，但不在承诺面之内。
- **只增不改** —— 冻结后，冻结集合内符号可以**新增**，但不得改名、不得改变语义、不得改变行为、不得删除。新增并非零成本：新符号属公共面扩张，落地前须在所有受支持面（子包 `__all__`、双语文档、双引擎）同步。

未出现在对应 `__all__` 列表中的符号应视为私有实现细节。带 `_` 前缀的兼容性导出可以继续存在，但不属于默认业务公开稳定承诺。

### 机器可读的契约产物

稳定性承诺面还会以**机器可读产物**随包发布，因此可以**离线**核对——既不需要导入框架，也不需要阅读本页：

- 文件：`cullinan/_contracts.json`（随 wheel 一起发布）
- `stability_commitment` —— 四个契约模块（`cullinan`、`cullinan.application`、`cullinan.web`、`cullinan.core`）各自的符号名清单
- `not_in_commitment` —— 明确排除在承诺面之外的门面，例如 `cullinan.web.gateway`
- `schema_version` 与 `generated_from` —— schema 版本与生成溯源信息

离线读取：

```python
import json
from pathlib import Path

payload = json.loads(Path("cullinan/_contracts.json").read_text(encoding="utf-8"))
print("Param" in payload["stability_commitment"]["cullinan.web"])
```

或者在已安装包的情况下：

```python
import json
from importlib import resources

payload = json.loads(
    resources.files("cullinan").joinpath("_contracts.json").read_text(encoding="utf-8")
)
print("Param" in payload["stability_commitment"]["cullinan.web"])
```

该产物是实测 `__all__` 的**派生副本**。用 `python scripts/generate_contracts.py` 重新生成；有一项漂移校验会逐名断言产物与实测列表一致。

## v0.90+ 新增：参数系统

参数系统提供类型安全的请求参数处理。详见 [参数系统指南](parameter_system_guide.md)。

### cullinan.web.params (v0.90a4+)

| 符号 | 类型 | 说明 |
|------|------|------|
| `Param` | 类 | 参数基类 |
| `Path` | 类 | URL 路径参数标记 |
| `Query` | 类 | 查询字符串参数标记 |
| `Body` | 类 | 请求体参数标记 |
| `Header` | 类 | HTTP 请求头参数标记 |
| `File` | 类 | 文件上传参数标记 |
| `RawBody` | 类 | 原始请求体，使用 `bytes = RawBody()` (v0.90a5+) |
| `UNSET` | 哨兵 | 表示未设置的哨兵值 |
| `TypeConverter` | 类 | 类型转换工具 |
| `Auto` | 类 | 自动类型推断工具 |
| `AutoType` | 类 | 用于签名的自动类型标记 |
| `DynamicBody` | 类 | 动态请求体容器 |
| `SafeAccessor` | 类 | 链式安全访问器 |
| `EMPTY` | 哨兵 | 空值哨兵 |
| `ParamValidator` | 类 | 参数校验工具 |
| `ValidationError` | 异常 | 校验错误 |
| `ModelResolver` | 类 | dataclass 模型解析器 |
| `ModelError` | 异常 | 模型解析错误 |
| `ParamResolver` | 类 | 参数解析编排器 |
| `ResolveError` | 异常 | 参数解析错误 |

### cullinan.web.params (v0.90a5+)

| 符号 | 类型 | 说明 |
|------|------|------|
| `FileInfo` | 类 | 文件元数据容器 |
| `FileList` | 类 | 多文件容器 |
| `field_validator` | 装饰器 | Dataclass 字段校验器 |
| `validated_dataclass` | 装饰器 | 自动校验的 dataclass |
| `FieldValidationError` | 异常 | 字段校验错误 |
| `Response` | 装饰器 | 响应模型装饰器 |
| `ResponseModel` | 类 | 响应模型定义 |
| `ResponseSerializer` | 类 | 响应序列化工具 |
| `serialize_response` | 函数 | 便捷序列化函数 |
| `get_response_models` | 函数 | 获取函数的响应模型 |

### cullinan.web.params.model_handlers (v0.90a5+)

可插拔模型处理器架构，用于第三方库集成。

| 符号 | 类型 | 说明 |
|------|------|------|
| `ModelHandler` | 类 | 模型处理器抽象基类 |
| `ModelHandlerError` | 异常 | 模型处理器错误 |
| `ModelHandlerRegistry` | 类 | 模型处理器注册表 |
| `DataclassHandler` | 类 | 内置 dataclass 处理器 |
| `PydanticHandler` | 类 | 可选 Pydantic 处理器（安装后可用）|
| `get_model_handler_registry()` | 函数 | 获取全局处理器注册表 |
| `reset_model_handler_registry()` | 函数 | 重置注册表（测试用）|

### cullinan.codec

| 符号 | 类型 | 说明 |
|------|------|------|
| `BodyCodec` | 类 | 请求体编解码器抽象类 |
| `ResponseCodec` | 类 | 响应编码器抽象类 |
| `JsonBodyCodec` | 类 | JSON 请求体解码器 |
| `JsonResponseCodec` | 类 | JSON 响应编码器 |
| `FormBodyCodec` | 类 | Form 请求体解码器 |
| `CodecRegistry` | 类 | Codec 注册表 |
| `get_codec_registry()` | 函数 | 获取全局 Codec 注册表 |
| `reset_codec_registry()` | 函数 | 重置 Codec 注册表（测试用）|
| `DecodeError` | 异常 | 解码错误 |
| `EncodeError` | 异常 | 编码错误 |
| `CodecError` | 异常 | 编解码错误基类 |

### cullinan.web.middleware（新增）

| 符号 | 类型 | 说明 |
|------|------|------|
| `BodyDecoderMiddleware` | 类 | 自动请求体解码中间件 |
| `get_decoded_body()` | 函数 | 获取已解码的请求体 |
| `set_decoded_body()` | 函数 | 设置已解码的请求体（测试用）|

## 公共符号与签名（建议结构）

每个模块建议按以下结构列出公共符号：

- 模块路径，例如：`cullinan.web.controller`
- 简要说明：模块的主要职责与使用场景
- 公有类与函数列表（示例）：
  - `@controller(...)` — 控制器装饰器，负责自动注册控制器与路由
  - `@get_api(url=..., query_params=..., body_params=..., headers=...)` — GET 接口装饰器
  - `@post_api(url=..., body_params=..., headers=...)` — POST 接口装饰器
  - `Inject`, `InjectByName` — 属性/构造器注入标记

完整 API 参考可以通过自动生成脚本或手工整理的方式填充上述结构。

## v0.95 新增（Track A 内部重构）

### 新增公共 API 符号

| 符号 | 位置 | 类型 | 说明 |
|------|------|------|------|
| `ScopeViolationError` | `cullinan.core.exceptions` | 异常（`LifecycleError` 子类） | 当单例/原型组件传递依赖请求作用域组件时抛出。携带 `dependency_chain`、`origin_name`、`violating_component`。 |
| `format_scope_violation_error` | `cullinan.core.diagnostics` | 函数 | 根据依赖链、起源、违规组件渲染人类可读的作用域违规描述。 |
| `strict_private_injection` | `ApplicationContext.__init__` | 关键字参数 | 为 `True` 时，注入标记扫描器跳过单下划线（`_xxx`）属性。默认 `False`。 |
| `strict_lifecycle` | `ApplicationContext.__init__` | 关键字参数 | 为 `True` 时，非关键生命周期钩子失败（`on_startup`/`on_shutdown`）以 `LifecycleError` 抛出。默认 `False`。 |
| `skip_private` | `get_injection_markers` | 关键字参数 | 为 `True` 时，扫描标记时跳过单下划线前缀属性。默认 `False`。 |
| `CULLINAN_STRICT_PRIVATE_INJECTION` | 环境变量 | 配置 | 设为 `1`/`true`/`yes` 可对所有 `ApplicationContext` 实例全局启用 `strict_private_injection`。 |
| `builtin_middleware` | `configure` | 关键字参数 | 控制内置 gateway 中间件层（access log 中间件）。`None`（默认）安装框架默认，`[]` 关闭内置层，列表则替换它。 |

### 弃用符号（将在未来版本中移除）

| 符号 | 替代方案 |
|------|---------|
| `injectable` | `@service` / `@component` / `@controller` |
| `inject_constructor` | `ApplicationContext.refresh()` |
| `InjectionRegistry` | `ApplicationContext` / `get_application_context()` |
| `get_injection_registry()` | `ApplicationContext` / `get_application_context()` |
| `reset_injection_registry()` | 显式创建新的 `ApplicationContext` |
| `RouteGroup` | `configure(middlewares=[...])` / `@middleware`（不支持按组匹配的中间件标签） |

详见 [框架语义](framework_semantics.md) §5-§8。

## 新增

以下均为**新增**、**向后兼容**、且**默认关闭**。

| 符号 | 位置 | 类型 | 说明 |
|------|------|------|------|
| `strict_assembly` | `configure` | 关键字参数 | `False`（默认）：导入期已声明但从未装配的组件会被报告，启动继续。`True`：要求该差集为空 —— 先发出报告，随后以 `ConfigurationError`（`CONFIG_ERROR`）使启动失败。仅关键字参数。 |
| `strict_assembly_excludes` | `configure` | 关键字参数 | 「有意不装配」的组件清单，写法为 `package.module.Component` —— 即声明对账报告使用的同一标识。列入的组件仍会被报告为「已声明未装配」，只是不再导致启动失败。`None`（默认）表示没有有意排除项；空列表含义相同。仅关键字参数。 |

两个配置项同时是 `CullinanConfig` 的字段，并可通过 `to_dict()` / `from_dict()`
往返，因此与其它配置项一样可以用 `@configure(...)` 声明。

失败时复用既有语义规则（`component-declared-not-assembled`）与既有
`ConfigurationError`：不新增异常类型、不新增规则标识、不新增公共符号。

> `strict_assembly` 与 `startup_error_policy` 无关：前者针对**从未被装配的声明**，
> 后者针对**服务初始化**失败。

完整契约见 [框架语义](framework_semantics.md) §11。

## 重新生成 API 文档（步骤示例）

在后续实现自动化时，可以选择使用静态分析脚本生成 API 索引并更新本页面。典型流程示例：

1. 在 `docs/work/` 目录下维护一个用于扫描模块并生成 Markdown 片段的脚本（例如 `generate_api_reference.py`）。
2. 脚本输出按模块划分的 API 列表（类、函数、签名、简要说明），写入 `docs/work/api_modules.md` 或直接更新本页面。
3. 在 CI 或本地构建流程中定期运行该脚本，保证 API 参考与源码保持同步。

具体实现细节可根据项目约定和工具链选择进行补充。
