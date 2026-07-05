title: "静态文件与 SPA 指南"
slug: "static-files-guide"
module: ["cullinan.web.static"]
tags: ["web", "static", "spa", "caching"]
author: "Cullinan"
reviewers: []
status: updated
locale: zh
translation_pair: "docs/static_files_guide.md"
related_tests: ["tests/web/test_static_files.py"]
related_examples: ["examples/static_files_and_spa"]
estimate_pd: 1.0
last_updated: "2026-06-29T00:00:00Z"
pr_links: []

# 静态文件与 SPA 指南

Cullinan 提供声明式静态文件 API，在 Tornado 与 ASGI 两种运行时上行为完全一致。
挂载点以纯数据形式声明在 `@configure(...)` 上，框架会在启动阶段把它们注册到
gateway router，与普通 controller、middleware 共存，**无需任何引擎相关的胶水代码**。

> **适用场景：** 部署打包的 SPA 前端、品牌资源目录、需要确定性缓存头但开发期
> 不便引入独立 CDN 的服务。

## 为什么做成一等公民

大多数 Python Web 框架要么把静态资源做成临时的 `send_file` 调用，要么塞进
服务器适配层深处的 settings 字典。Cullinan 选择把它们提升为一级声明：
框架的对外路径本就是 decorator-first 的——路由、控制器、中间件、静态挂载点
都在应用边界上表达，由 runtime 完成装配。

由此带来的好处是：同一份配置可在 Tornado 与 ASGI 之间切换、可与 Nuitka /
PyInstaller 打包共存、可通过 `main.get_asgi_app()` 做集成测试，**无需重写处理器**。

## 公共 API

### `cullinan.web.StaticFiles`

描述一个挂载点的 frozen dataclass。把实例（或等价的 `dict` / `(url, directory)`
元组）传给 `@configure(...)` 的 `static_files` 参数即可：

```python
from cullinan import application, configure
from cullinan.web import StaticFiles

@configure(
    user_packages=["myapp"],
    static_files=[
        StaticFiles(url="/static", directory="static"),
        StaticFiles(url="/assets", directory="dist/assets",
                    max_age=31536000, immutable=True),
        StaticFiles.spa_app(directory="dist"),
    ],
)
@application
def main(): ...
```

字段：

| 字段 | 默认值 | 作用 |
| --- | --- | --- |
| `url` | 必填 | URL 前缀。`"/"` 代表根挂载（常见的 SPA 场景）。 |
| `directory` | 必填 | 磁盘路径；相对路径基于 project root，缺省时退回 `os.getcwd()`。 |
| `index` | `"index.html"` | 当请求映射到目录时、或 SPA 模式下文件不匹配时返回的文件名。 |
| `spa` | `False` | 启用下文描述的 SPA 回退策略。 |
| `max_age` | `None` | 添加 `Cache-Control: max-age=<秒数>, public`。 |
| `immutable` | `False` | 追加 `immutable` 指令（仅适用于带哈希指纹的资源）。 |
| `no_cache` | `False` | 强制 `no-cache, no-store, must-revalidate`，同时禁用 ETag。 |
| `etag` | `True` | 基于 `(mtime_ns, size)` 派生强 ETag，并实现 `If-None-Match`。 |
| `last_modified` | `True` | 输出 `Last-Modified` 并实现 `If-Modified-Since`。 |
| `methods` | `("GET", "HEAD")` | 允许的方法。**设计上**仅接受 `GET` 与 `HEAD`。 |
| `follow_symlinks` | `False` | 默认拒绝指向 `directory` 之外的符号链接。 |
| `extra_headers` | `()` | 应用到每个文件响应上的附加头。 |

### `StaticFiles.spa_app`

针对“根挂载 SPA”的快捷方式：

```python
StaticFiles.spa_app(directory="dist")  # url="/", spa=True, index="index.html"
```

## 行为说明

### 引擎中立

每个 `StaticFiles` 声明会转换为 gateway `Router` 上的若干 `RouteEntry`。
Tornado 与 ASGI 适配器都把请求送入 `Dispatcher.dispatch()`，因此两种后端
看到的文件、响应头、状态码完全一致。

> **`/static` 前缀没有特殊待遇。** Cullinan 不会向 Tornado 传入 `static_path`
> 设置，因此 Tornado 不会在 `/static/` 上自动注册其内置的 `StaticFileHandler`。
> `StaticFiles(url="/static", ...)` 挂载在两个引擎上都完全经由 router 提供服务，
> 与其它任意前缀行为一致。

### 路由优先级

Cullinan 的 router 偏好静态段与参数段，wildcard 优先级最低。这意味着
`@controller(url="/api/users")` 始终优先于宽泛的 `StaticFiles(url="/")`。
列表顺序只在两个挂载点共享前缀时才有意义。

### SPA 回退

`spa=True` 对应 Vue / React Router / Angular 等前端常见的 history 路由约定：

- 真实存在的文件按原样返回（`/assets/main.js` → 真实文件）。
- 看起来**不像**文件的路径（末段不含点，例如 `/settings/profile`）且找不到
  真实文件时，回退到 `index.html`，状态码 `200`。
- 看起来**像**文件的路径（例如 `/assets/missing.js`）当文件不存在时返回 `404`，
  避免把损坏的资源 URL 静默地藏在 index 页面后面。

### 缓存契约

- ETag 基于 `(mtime_ns, size)` 经 BLAKE2 哈希派生，跨进程一致。
- `If-None-Match` 与 `If-Modified-Since` 都会得到形态完整的 `304 Not Modified`
  响应，缓存头保留齐全。
- `no_cache=True` 会同时禁用 ETag 输出，杜绝中间层复用旧 body。

### 安全默认值

- 路径穿越在解析阶段就被拦截（`Path.resolve()` + `relative_to(...)`），
  `/static/../etc/passwd` 一律返回 `404`。
- 默认拒绝指向挂载目录外的符号链接，除非显式 `follow_symlinks=True`。
- 变更动作（`POST` / `PUT` / `DELETE` / `PATCH`）**永远不会**被注册。

### v1 限制

- 响应是全量缓冲读取的。流式与 HTTP `Range` 已列入路线图；超大资产请走 CDN。
- 暂未自动协商 `gzip` / `br` 压缩。预压缩资产可通过单独挂载 + `extra_headers`
  设置 `Content-Encoding` 实现。

## 配方

### 经典 `/static/*` 挂载

```python
StaticFiles(url="/static", directory="static", max_age=3600)
```

行为对标 Flask 的 `send_from_directory`、FastAPI 的 `StaticFiles` 挂载。

### 哈希指纹打包资产

```python
StaticFiles(
    url="/assets",
    directory="dist/assets",
    max_age=31536000,
    immutable=True,
)
```

配合 Vite / webpack 的哈希文件名，让已缓存的客户端永不回源。

### 同源 SPA + API

```python
@configure(
    user_packages=["myapp"],
    static_files=[
        StaticFiles(url="/assets", directory="dist/assets",
                    max_age=31536000, immutable=True),
        StaticFiles.spa_app(directory="dist"),
    ],
)
@application
def main(): ...
```

Cullinan 始终把 `/api/...` 控制器放在 SPA 回退之前——API 优先响应，
SPA 兜住其它请求。

## 验证

上述行为由 `tests/web/test_static_files.py` 覆盖：通过 dispatcher、
Tornado 适配器与 ASGI 适配器三条路径，对临时站点 fixture 跑通基础读取、
ETag/304、SPA 回退、目录穿越等用例。运行命令：

```bash
python -m pytest tests/web/test_static_files.py -v
```

## 延伸阅读

- `examples/static_files_and_spa/` — 可运行示例
- [Web Runtime 指南](web_runtime_guide.md)
- [框架语义](framework_semantics.md)
- [示例导航](examples.md)
