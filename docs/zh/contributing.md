title: "贡献指南"
slug: "contributing"
module: []
tags: ["contributing"]
author: "plumeink"
reviewers: []
status: updated
locale: zh
translation_pair: "docs/contributing.md"
related_tests: []
related_examples: []
estimate_pd: 1.0
last_updated: "2025-12-25T00:00:00Z"
pr_links: []

# 贡献指南

感谢你愿意改进 Cullinan。本页说明如何搭建开发环境、合并前会运行的检查，
以及一份完整贡献应包含什么。

## 搭建开发环境

需要 Python **3.9+**。

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate   |   Unix: source .venv/bin/activate
pip install -r requirements-dev.txt
pip install -e .
```

## 提交拉取请求之前

在本地运行与 CI 相同的检查，并确保全部通过：

```bash
ruff check .                 # 代码检查
python -m pytest tests -q    # 完整测试套件，必须保持绿色
python -m build && twine check dist/*   # 打包健康检查
```

## 一份完整贡献包含什么

任何特性、行为变更或重命名，都应在同一个拉取请求内同步更新以下各项：

- **代码** - 位于 `cullinan/` 下的实现，并通过相应的 `__init__` 公共 API 暴露。
- **测试** - 位于 `tests/` 下的 pytest 用例，覆盖**双引擎**（Tornado + ASGI）
  以及公共 API 路径，包含负例与边界情况。
- **示例** - 位于 `examples/<feature>/` 的可运行示例，并与 `docs/examples.md`
  保持一致。
- **文档** - 双语 `docs/<feature>_guide.md` + `docs/zh/...`；新增或重命名页面时
  同步更新 `mkdocs.yml` 导航。

## 运行示例

每个示例都可以独立运行：

```bash
python -m examples.minimal_app
python -m pytest examples/testing_flow/test_app.py -q
```

## 报告问题与提交变更

使用 issue 模板（bug report / feature request）提交问题，并向 `master` 发起
拉取请求。报告 bug 时请附上 Cullinan 版本、Python 版本、所用运行时
（Tornado 或 ASGI）以及最小复现。
