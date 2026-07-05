# Contributing to Cullinan / 贡献指南

Thanks for your interest in improving Cullinan! 感谢你为 Cullinan 做贡献！

This project iterates through pull requests against `master` (stable) and the
active `release/**` pre-release branch. 本项目通过向 `master`（稳定）与活跃的
`release/**` 预发布分支提交 PR 来迭代。

## Development setup / 开发环境

Requires Python **3.9+**. 需要 Python **3.9 及以上**。

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate   |   Unix: source .venv/bin/activate
pip install -r requirements-dev.txt
pip install -e .
```

## Before you open a PR / 提交 PR 前

Run the same gates CI runs. 请在本地跑通与 CI 一致的门禁：

```bash
ruff check .                 # lint (E9 + F)
python -m pytest tests -q    # full test suite — must stay green
python -m build && twine check dist/*   # packaging health
```

## Four-aspect sync / 四方面同步（硬性要求）

Any feature, behavior change, or rename MUST advance four aspects **together**
in the same PR. 任何特性、行为变更或重命名，必须在同一个 PR 内**同时**推进四方面：

1. **Code / 代码** — implementation under `cullinan/`, exposed through the
   relevant `__init__` public API. 实现 + 公共 API 暴露。
2. **Tests / 测试** — pytest cases under `tests/` covering **both engines**
   (Tornado + ASGI) plus the public-API path, including negative & edge cases.
   覆盖**双引擎** + 公共 API 路径，含负例与边界。
3. **Examples / 示例** — a runnable demo under `examples/<feature>/` with
   `__main__.py` + `README.md`. 可运行的最小 demo。
4. **Docs / 文档** — bilingual `docs/<feature>_guide.md` + `docs/zh/...`, and
   update `mkdocs.yml` nav + `README.MD`. 双语文档 + 导航 + README。

A change is not "done" until all four align. 四者对齐，特性才算完成。

## Engine neutrality / 引擎中立

Cullinan runs on both Tornado and ASGI. Features route through the gateway
`Router` / `Dispatcher`, **not** engine-native handlers. Do not add
backend-specific behavior that diverges between engines. 特性统一经 `Router` /
`Dispatcher`，**不要**引入在两引擎间行为不一致的基座原生实现。

## Code style / 代码风格

- Lint with `ruff check .` (config in `ruff.toml`). 用 ruff 校验。
- Match surrounding code; comment only where clarification is needed. 与周边
  代码一致，仅在需要解释处加注释。

## Commits / 提交规范

- Use a clear type prefix: `feat:`, `fix:`, `docs:`, `ci:`, `build:`,
  `refactor:`, `test:`. 使用清晰的类型前缀。
- Describe the root cause and which of the four aspects you touched. 说明根因
  与四方面落点。
- Keep the trailer when applicable:
  `Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>`。

## Versioning / 版本号

Follows PEP 440. `0.93aN` for feature iterations, `0.93aN.postM` for
patch/defect fixes (no new public API). The canonical package version now lives
in `cullinan/_version.py`; `pyproject.toml`, `cullinan/__init__.py`, and
`cullinan/core/__init__.py` must stay aligned to that single source.
遵循 PEP 440；补丁用 `.postM`；版本事实源在 `cullinan/_version.py`，其余位置必须与之对齐。

## Reporting issues / 反馈问题

Use the issue templates (bug report / feature request). Include Cullinan
version, Python version, engine (Tornado/ASGI), and a minimal repro. 使用 issue
模板，附版本、Python 版本、引擎与最小复现。
