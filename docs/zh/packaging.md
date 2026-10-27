pr_links: []
last_updated: "2026-10-28"
title: "打包指南"
slug: "packaging"
module: []
tags: ["docs", "guide", "packaging"]
author: "plumeink"
reviewers: []
status: updated
locale: zh
translation_pair: "docs/packaging.md"
related_tests: ["tests/integration/test_docs_i18n_parity.py"]
related_examples: []
estimate_pd: 0.5

# 打包指南 —— 冻结环境下的模块发现

Cullinan 自 v0.93a11.post2+ 起，把跨打包工具（Nuitka、PyInstaller）与开发环境的模块发现
统一成一条**策略流水线**。

## 快速开始

### 显式模块清单（单文件模式下推荐）

`--onefile` 构建里最可靠的做法：

```python
from cullinan import configure

configure(
    explicit_modules=["myapp.services", "myapp.controllers"],
    user_packages=["myapp"],
)
```

**`explicit_modules`** 取代了已废弃的 `nuitka_modules`（v0.93a11.post2 移除）。它对**所有**
打包工具都有效 —— Nuitka、PyInstaller，以及将来任何一种打包器。

### 用户包（目录模式下推荐）

适用于 `--standalone` / `--onedir` 这类**文件系统可达**的构建：

```python
from cullinan import configure

configure(
    user_packages=["myapp"],
    auto_scan=True,  # 默认值
)
```

## 策略流水线

Cullinan 现在由**六个相互独立的策略**组成一条可组合的流水线，具体走哪条由
`get_packaging_mode()` 自动决定：

### Nuitka

| 模式 | 流水线 | 说明 |
|------|--------|------|
| `--standalone` | S0 → S1 → S2 → S3 → S4 | 完整文件系统扫描 |
| `--onefile` | S0 → S1 → S2 → S3 → S5 | 跳过 S4（没有源文件），改用递归 `dir(pkg)` + `sys.modules` 兜底 |

### PyInstaller

| 模式 | 流水线 | 说明 |
|------|--------|------|
| `--onedir` | S0 → S1 → S4 | `_MEIPASS` + 可执行文件所在目录扫描 |
| `--onefile` | S0 → S1 → S4 | `_MEIPASS` 解压临时目录 |

### 开发环境

| 模式 | 流水线 | 说明 |
|------|--------|------|
| `development` | S0 → S1 → S2 → S3 | `get_caller_package()` + 兜底 |

### 策略说明

| 策略 | 作用 | 触发条件 |
|------|------|----------|
| **S0: explicit_modules** | 用户显式给出的模块清单 | 设置了 `explicit_modules` |
| **S1: user_packages** | 通过 `pkgutil.walk_packages` 遍历配置的包 | 设置了 `user_packages` |
| **S2: sys_modules_scan** | 按路径启发式自动扫描 `sys.modules` | `auto_scan=True` |
| **S3: main_module_inference** | 由 `__main__.__file__` 反推包 | 总是执行 |
| **S4: directory_scanning** | 遍历文件系统找 `.py`/`.pyc`/`.pyd`/`.so` | standalone/onedir 模式 |
| **S5: onefile_dir_fallback** | 递归 `dir(pkg)` + `sys.modules` 前缀扫描 | 单文件模式（最后手段） |

## 性能改进（v0.93a11.post2+）

1. **类型提示全局缓存** —— `typing.get_type_hints()` 的结果在模块级缓存，**跨
   `ApplicationContext` 实例共享**。此前每个上下文实例各有一份缓存，导致重复解析。

2. **源码行号延迟获取** —— 注册装饰器时不再调用 `inspect.getsourcelines()`。源文件路径
   仍然会记录，行号推迟到真正需要诊断时才取。

## 从 v0.93a11 迁移

| 旧 API | 新 API |
|--------|--------|
| `nuitka_modules=["myapp"]` | `explicit_modules=["myapp"]` |
| `scan_modules_nuitka()` | 流水线自动选择 |
| `scan_modules_pyinstaller()` | 流水线自动选择 |

旧函数**已移除**，不提供向后兼容别名 —— 升级框架的同时请一并改配置。

## 故障排查

### 单文件模式下发现不到任何模块

```python
configure(explicit_modules=["your_top_level_package"])
```

### 类重载后类型提示解析报错（测试中）

`PendingRegistry.reset()` 现在会同时让类型提示的全局缓存失效：

```python
from cullinan.core.pending import PendingRegistry

PendingRegistry.reset()  # 同时清掉类型提示缓存
```

### 覆盖策略（进阶）

```python
from cullinan.runtime.scan_pipelines import execute_pipeline
from cullinan.support.config import get_config

modules = execute_pipeline(
    get_config(),
    packaging_mode="nuitka-onefile",
    base_dirs=["/custom/path"],
    early_termination=False,  # 跑完全部策略
)
```
