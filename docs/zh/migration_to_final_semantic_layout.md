title: "最终结构迁移说明"
slug: "final-structure-migration"
module: []
tags: ["migration", "final-structure", "semantics"]
author: "Cullinan"
reviewers: []
status: updated
locale: zh
translation_pair: "docs/migration_to_final_semantic_layout.md"
related_tests: ["tests/core/test_public_api_boundaries.py", "tests/core/test_semantic_package_facades.py"]
related_examples: ["examples/minimal_app", "examples/testing_flow"]
estimate_pd: 1.0
last_updated: "2026-06-02T00:00:00Z"
pr_links: []

# 最终结构迁移说明

本文说明如何把 `0.93a6` 及更早版本里基于混合布局的代码迁移到当前 pre 分支采用的最终语义结构。

## 发生了什么变化

Cullinan 不再保留以下历史根层 wrapper：

- `cullinan.app`
- `cullinan.application_model`
- `cullinan.public_api`
- `cullinan.module_scanner`
- `cullinan.scan_stats`
- `cullinan.scanner`
- `cullinan.compat`

当前维护中的正式结构收敛为：

- `cullinan.application`
- `cullinan.web`
- `cullinan.core`
- `cullinan.runtime`
- `cullinan.transport`
- `cullinan.testing`
- `cullinan.support`

## 为什么要移除

此前的新语义包与历史 wrapper 长期并存，导致：

- 包结构更难理解
- 旧导入持续被新代码沿用
- 仓库一直停留在“已经开始收敛、但还没真正收干净”的中间态

现在 Cullinan 直接把这些语义包视为真实结构，而不是覆盖在旧文件之上的 facade。

## 旧路径到新路径映射

| 旧路径 | 新路径 |
| --- | --- |
| `cullinan.app` | 顶层 `cullinan` 入口方法 API（`@application`、`configure`，然后调用 `main()`） |
| `cullinan.application_model` | `cullinan.application` |
| `cullinan.public_api` | `cullinan.application.public` |
| `cullinan.module_scanner` | `cullinan.runtime.module_scanner` |
| `cullinan.scan_stats` | `cullinan.runtime.scan_stats` |
| `cullinan.scanner` | `cullinan.runtime.scanner` |
| `cullinan.controller` | `cullinan.web.controller` |
| `cullinan.middleware` | `cullinan.web.middleware` |
| `cullinan.params` | `cullinan.web.params` |
| `cullinan.gateway` | `cullinan.web.gateway` |
| `cullinan.handler` | `cullinan.web.handler` |
| `cullinan.adapter` | `cullinan.transport.adapter` |
| `cullinan.service` | `cullinan.core`（`@service`）/ `cullinan.core.services`（`Service`、registry helper） |
| `cullinan.config` | `cullinan.support.config` |
| `cullinan.exceptions` | `cullinan.support.exceptions` |
| `cullinan.path_utils` | `cullinan.support.path_utils` |

## 常见迁移改写

### 应用启动

```python
# Before
from cullinan.public_api import run

# After
from cullinan import application, configure

@configure(user_packages=["myapp"])
@application
def main(): ...

main()
```

### 运行时模型 helper

```python
# Before
from cullinan.application_model import Application

# After
from cullinan.application import Application
```

### Web 公开 API

```python
# Before
from cullinan.controller import controller
from cullinan.params import Body

# After
from cullinan.web import controller, Body
```

### 高级传输集成

```python
# Before
from cullinan.adapter import ASGIAdapter

# After
from cullinan.transport.adapter import ASGIAdapter
```

## 心智切换

不要把这次迁移理解成“再找一个还能继续兼容的旧入口”。

新的规则是：

1. 业务应用启动放在顶层 `cullinan`
2. 业务 Web 开发放在 `cullinan.web`
3. IoC/DI 与生命周期放在 `cullinan.core`
4. 自动发现与扫描放在 `cullinan.runtime`
5. 服务端集成放在 `cullinan.transport`
6. 支撑工具放在 `cullinan.support`

如果已有代码依赖被移除的根层 wrapper，应直接迁移 import，而不是重新把 wrapper 加回来。
