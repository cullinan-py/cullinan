title: "测试与验证"
slug: "testing"
module: []
tags: ["testing"]
author: "plumeink"
reviewers: []
status: updated
locale: zh
translation_pair: "docs/testing.md"
related_tests: ["tests/core/test_application_model_refactor.py", "tests/core/test_public_api_boundaries.py", "tests/core/test_developer_experience.py", "tests/core/test_decorators.py", "tests/integration/test_adapter_integration.py", "tests/integration/test_gateway_integration.py", "tests/integration/test_examples_public_guides.py", "tests/web/test_openapi_generator.py", "tests/web/test_web_runtime.py", "tests/di/test_core_constructor_injection.py"]
related_examples: ["examples/testing_flow"]
estimate_pd: 1.5
last_updated: "2026-06-01T00:00:00Z"
pr_links: []

# 测试与验证

本文说明 application-model、公开 API 边界、adapter 与测试结构收尾后的当前仓库测试工作流。

> **仓库正式入口：** `.venv\Scripts\python -m pytest`  
> **相关语义：** 涉及运行时边界的测试，应与 [框架语义规则](framework_semantics.md)
> 和 [API 参考](api_reference.md) 保持一致。

## 仓库正式入口

请使用仓库虚拟环境执行：

```powershell
.venv\Scripts\python -m pytest
```

这就是当前仓库执行全量验证的正式命令。

## 测试发现配置

`pytest.ini` 定义了仓库默认规则：

```ini
[pytest]
testpaths = tests
python_files = test_*.py
addopts = -ra
```

`tests/conftest.py` 会把仓库根目录加入 `sys.path`，因此新测试不应再重复写本地 `sys.path.insert(...)` 引导代码。

## 测试目录结构

测试按主题组织：

- `tests/core`
- `tests/di`
- `tests/web`
- `tests/integration`
- `tests/regression`
- `tests/compat`
- `tests/helpers`

新增测试时，优先放入最接近的现有主题目录，而不是继续创建零散的顶层文件。

## 运行定向测试

示例：

```powershell
.venv\Scripts\python -m pytest tests\web\test_web_runtime.py -q
.venv\Scripts\python -m pytest tests\di\test_core_constructor_injection.py -q
```

通用的 `python -m pytest` 也可运行，但当前仓库文档标准统一使用 Windows 下的 `.venv\Scripts\python` 形式。

如果你想先看一个面向开发者的小型测试示例，而不是直接进入整个仓库测试集，
可以参考 `examples/testing_flow/test_app.py`。

## 当前约定

1. 使用标准 pytest 测试与普通 `assert` 断言。
2. pytest 现在是唯一正式测试入口；历史 `if __name__ == "__main__"`、`main()`、`run_all_tests()` 直跑尾巴不应再引入。
3. 需要共享初始化时，优先复用 `tests/conftest.py` 与 `tests/helpers/`。
4. 测试若修改全局 registry 或活动应用上下文，必须自行完成隔离与清理。

## 测试覆盖范围

当前测试集覆盖：

- application-first 启动、模块归属解析与运行时切换
- 顶层公开 API 边界、兼容 warning 与整理后的启动路径
- 容器与生命周期行为
- 兼容层语义
- gateway / Web Runtime 行为
- 控制器路由与参数处理
- 集成与回归场景

代表性文件：

- `tests/core/test_application_model_refactor.py`
- `tests/core/test_public_api_boundaries.py`
- `tests/core/test_developer_experience.py`
- `tests/core/test_decorators.py`
- `tests/integration/test_adapter_integration.py`
- `tests/integration/test_gateway_integration.py`
- `tests/web/test_openapi_generator.py`

## 相关文档

- [运行时整合概览](runtime_updates_v093.md)
- [应用运行时模型](wiki/application_runtime.md)
- [架构设计](architecture.md)
- [Web Runtime 指南](web_runtime_guide.md)
