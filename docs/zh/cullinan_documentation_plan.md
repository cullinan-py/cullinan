title: "Cullinan 文档编写计划书"
slug: "documentation-plan"
module: ["docs"]
tags: ["plan", "documentation"]
author: "plumeink"
reviewers: []
status: draft
locale: zh
translation_pair: "docs/cullinan_documentation_plan.md"
related_tests: []
related_examples: []
estimate_pd: 0.0
last_updated: "2025-11-18T00:00:00Z"
pr_links: []

# Cullinan 文档编写计划书

> 说明：本计划基于 Cullinan 源码（仅以源码实现为准，忽略注释）进行设计，目标是为项目建立完整的中英双语文档体系（`docs/` 与 `docs/zh/` 1:1 对应）。

## 任务收敛与高层计划

本计划文档用于收纳多阶段任务规划，便于在仓库中保留规划内容，供团队审阅与分配。后续操作示例：

- 在 `docs/` 目录下维护本计划文件。
- 运行静态检查以确保文件没有语法/格式错误（文档文件通常不会产生代码编译错误，但仍建议进行基本检查）。

简要验收清单（在提交前）：
- [x] 文件以 UTF-8 编码、Markdown 格式保存。
- [x] 包含目标、范围、任务拆分、时间预估、质量门与示例命令说明。
- [x] 明确要求 `docs/` 与 `docs/zh/` 必须 1:1 对应。

---

TL;DR：为 Cullinan（基于 Tornado 的 IoC/DI 框架）编写中英双语文档（`docs/` 与 `docs/zh/` 1:1 对应），包括入门、示例、Wiki（架构/组件/生命周期/注入/中间件/扩展）、API 参考、迁移指南、贡献指南、测试与本地运行说明；采用源码驱动（忽略注释）研究策略，保持现有 IoC/DI 设计不变，提供分工、里程碑、质量门与 PowerShell 等环境下的运行/验证命令示例。

## 1. 目标与受众

- 目标：为 Cullinan 提供清晰、可执行、双语（英文/中文）文档套件，帮助新用户快速上手，帮助贡献者理解内部设计与注入机制，提供可运行的示例与测试验证步骤。
- 受众：库使用者（应用开发者）、框架贡献者/维护者、代码审查者、自动化测试工程师。

## 2. 范围与产物清单

必须产出（每项均需在 `docs/` 与 `docs/zh/` 下 1:1 对应）：

- `Getting Started`（快速入门） — `docs/getting_started.md` / `docs/zh/getting_started.md`
- `Examples`（示例） — `docs/examples.md` / `docs/zh/examples.md`（并在仓库保留 `examples/` 可运行代码）
- `Wiki`（架构/组件/生命周期/注入/中间件/扩展） — `docs/wiki/architecture.md`, `components.md`, `lifecycle.md`, `injection.md`, `middleware.md`, `extensions.md`（与 `docs/zh/wiki/*` 对应）
- `API Reference` — `docs/api_reference.md` / `docs/zh/api_reference.md`（可选择自动化生成）
- `Migration Guide` — `docs/migration_guide.md` / `docs/zh/migration_guide.md`
- `Contributing` — `docs/contributing.md` / `docs/zh/contributing.md`
- `Testing & Verification` — `docs/testing.md` / `docs/zh/testing.md`
- `Local Build & Run` — `docs/build_run.md` / `docs/zh/build_run.md`
- 文档模板和样例页面（front-matter、示例代码片段规范、翻译准则）

附加产物（建议）：

- `examples/` 可运行示例集合（轻量 demo）
- 简要 `README.md` 更新链接 `docs/` 页面
- 文档 CI 脚本（可选）

## 3. 研究方法与代码阅读策略（只读源码，忽略注释）

研究目标：从源码推断设计与行为（不依赖注释），定位关键模块与依赖关系，提取外部 API、生命周期和注入行为。

策略与步骤：

1. 高层目录扫描：先确认顶层模块与入口点。优先阅读 `cullinan/__init__.py`、`app.py`、`application.py`、`config.py`。
2. 核心子系统定位：定位 IoC/DI 实现位置（通常在 `cullinan/core`）。重点阅读 `core/__init__.py`、`core/provider.py`、`core/registry.py`、`core/scope.py` 等（实际文件名请根据 `cullinan/core` 目录文件列表调整）。
3. 控制器/路由/中间件：查看 `controller/`、`handler/`、`middleware/` 文件，找到路由注册、处理流程与生命周期钩子。
4. 模块扫描与自动注册：阅读 `module_scanner.py`、`websocket_registry.py` 等了解自动发现机制与注册时序。
5. 配置与启动流程：追踪 `application.py` 与 `app.py` 中的 `main`、`start`、`initialize`、`run` 风格函数，形成启动序列图（顺序、依赖）。
6. 注入点发现：在源码中搜索关键词（`inject`, `provide`, `provider`, `register`, `scope`, `singleton`, `transient`）以定位注入 API 与用法。
7. 以测试为反证：审阅 `tests/` 下关键测试（如 `test_core_injection.py`、`test_controller_injection_fix.py`、`test_registry.py` 等）来理解期望行为与边界条件（测试是行为规范的重要来源）。
8. 依赖图构建：使用静态读取（或简单脚本）列出模块之间 import 关系，绘制简易模块依赖图（帮助撰写架构/组件说明）。
9. 记录发现：以“事实陈述”记录每个模块的职责、输入输出、生命周期、错误模式。仅基于源码行为，不依赖注释解释。

工具与方法：

- 使用仓库搜索（通过 IDE 或 `rg`/`grep`）定位符号和字符串模式。
- 阅读关键测试用例以补全理解。
- 构建小的问答式笔记（模块 -> 责任 -> 与其他模块的交互）供文档写作使用。

注意：不要在文档中改变或鼓励改变现有 IoC/DI 设计；文档只描述/说明，可提出“改进建议”但须作为附录或 issues。

## 4. 任务拆分与里程碑（优先级 + 时间估算）

总体预计时长：6 周（可按资源并行压缩）。时间单位为人天（工作日）。

阶段 A — 发现与大纲（优先级：高，时长：4 人日）
- A1. 源码快速扫描并生成模块映射（2 人日）
- A2. 基于映射草拟文档总纲（1 人日）
- A3. 确认输出格式（Markdown 结构、目录、翻译流程、是否用 Sphinx/mkdocs 等）（1 人日）

里程碑 A：提交 `docs/outline.md` 与 `docs/zh/outline.md`，包含文件清单与负责人。

阶段 B — 入门与示例（优先级：高，时长：6 人日）
- B1. 编写 `Getting Started` 英中版本（2 人日）
- B2. 设计并实现 2–3 个最小可运行示例到 `examples/`（3 人日）
- B3. 将示例集成到文档并验证（1 人日）

里程碑 B：`docs/getting_started.md` 与 `examples/` 可被本地用户运行。

阶段 C — 核心 Wiki（架构/组件/生命周期/注入机制/中间件/扩展）（优先级：高，时长：10 人日）
- C1. `architecture.md`（2 人日）
- C2. `components.md`（2 人日）
- C3. `lifecycle.md`（2 人日）
- C4. `injection.md`（3 人日）
- C5. `middleware.md` / `extensions.md`（1 人日）

里程碑 C：完成核心设计的梳理与文档化，并通过同行评审。

阶段 D — API 参考与迁移指南（优先级：中，时长：8 人日）
- D1. 决定 API 参考方式（自动 vs 手工）（0.5 人日）
- D2. 生成或手写所有公共模块的 API 摘要（5 人日）
- D3. 编写迁移指南（兼容性/破坏性变化说明）（2.5 人日）

里程碑 D：API 参考完成并可索引；迁移指南覆盖主要变更点。

阶段 E — 贡献/测试/运行说明与本地构建（优先级：中，时长：4 人日）
- E1. `contributing.md`（1 人日）
- E2. `testing.md`（1 人日） — 包括如何运行现有测试、如何编写测试、CI 要求
- E3. `build_run.md`（2 人日） — 包含 Windows PowerShell 指令和虚拟环境步骤

里程碑 E：贡献流程与测试准则就绪。

阶段 F — 翻译、校验、质量门（优先级：高，时长：6 人日）
- F1. 翻译校对（英->中）并确保 1:1 文件结构（3 人日）
- F2. 文档内部审校（结构、事实、示例可运行）（2 人日）
- F3. 最终质量门（运行测试、示例验证、提交 PR）（1 人日）

里程碑 F：双语文档 1:1 对应通过质量评审。

总体里程碑时间表（可通过并行工作缩短）：
- 第 1 周：完成阶段 A
- 第 2 周：开始并完成阶段 B
- 第 3–4 周：完成阶段 C
- 第 5 周：完成阶段 D 和 E
- 第 6 周：完成阶段 F 的验收与发布

## 5. 人员分工建议（示例）

- 1 名技术作者（主文档撰写） — 负责入门、Wiki 主体、示例文本
- 1 名开发工程师（代码研究与示例实现） — 负责源码映射、可运行示例、验证测试
- 1 名翻译/本地化人员（中文校对） — 负责 `docs/zh/` 对应翻译与语境校验
- 1 名评审/维护者（架构 & CI 审核） — 负责审稿、CI 合并、质量门签收

## 6. 写作准则（必遵守）

- 文件编码：UTF-8。
- 目录结构：`docs/` 与 `docs/zh/` 必须 1:1 对应，文件名与相对路径一致。
- 语言与风格：简洁、以事实为基础（以源码行为为准），尽量提供示例和可复制步骤。
- 禁止在日志或示例输出中使用 emoji（项目规定）。
- Windows PowerShell 命令示例应符合 Windows PowerShell v5.1 语法；不要使用 `&&` 连接命令；若需要在一行执行多个命令，使用分号 `;`。
- 文档中引用文件或符号时使用反引号包裹（例如 `cullinan/core`、`application.py`）。
- 对于 API 参考，明确标注“公有 API”与“内部实现”，鼓励只在公有 API 上建立使用示例。
- 翻译策略：先完成英文原稿并评审通过，再做中文翻译；始终保持 1:1 内容一致性。

## 7. 校验 / 质量门（Quality Gates）

每个阶段必须通过相应的质量门才能进入下一阶段：

质量门示例：
- 代码研究完成：提交 `docs/outline.md`，包含模块映射与关键函数列表；至少两名工程师审核同意（签名或 PR 评论）。
- 示例可运行：`examples/` 中示例可在本地虚拟环境中成功运行（见验证命令）。
- 单元/集成测试：运行仓库现有测试并确保无回归（见下方命令）。必须至少实现“当前主分支相同或更好”的通过率。
- 文档审校：每篇文档至少进行 1 次技术审阅与 1 次语言校对。
- 发布前：CI 通过、文档链接完整性检查、示例在 Windows PowerShell 环境测试通过。

关键校验命令（以 PowerShell 表示，单行示例使用 `;` 分隔）：
- 创建虚拟环境并激活（可选）：确保存在可用的 Python 环境（virtualenv/conda/system Python 等均可），无需在文档中强制规定激活命令。
- 安装开发依赖并安装本包（可选 extras）：`pip install -U pip; pip install -e .[dev]` 或 `pip install -e .`
- 运行测试：`py -3 -m pytest -q`（或 `pytest -q`）
- 运行单个示例（在 `examples/` 目录）：`py example_script.py` 或 `python -m examples.demo`（视示例实现而定）
- 检查文档链接/拼写（若使用工具）：`pylint`/`flake8`（代码），`markdownlint`（文档）（按需安装）

## 8. 需要创建的文件结构与模板示例

建议在仓库中新增或补充以下文件（`docs/` 与 `docs/zh/` 必须镜像）：

- `docs/README.md`（文档主页/导航）
- `docs/getting_started.md`（快速开始：环境、安装、运行第一个应用）
- `docs/examples.md`（示例索引与说明） + `examples/` 目录放示例代码
- `docs/wiki/architecture.md`（架构总览）
- `docs/wiki/components.md`（组件责任与 API 摘要）
- `docs/wiki/lifecycle.md`（应用启动/关闭/生命周期钩子）
- `docs/wiki/injection.md`（IoC/DI 机制详解）
- `docs/wiki/middleware.md`（中间件链与扩展点）
- `docs/api_reference.md`（按模块列出的公有 API）
- `docs/migration_guide.md`（兼容性与迁移说明）
- `docs/contributing.md`（贡献者指南、代码风格、PR 流程）
- `docs/testing.md`（如何运行现有 tests、编写测试、CI 要求）
- `docs/build_run.md`（在 Windows/Unix 下的本地构建与运行说明）
- `docs/templates/`（页面模板：标题、概述、示例结构、API 条目格式、翻译对照表）

模板示例（描述而非代码块）：
- 文档顶部应包含简短的“目的/范围/前提”三段，随后“示例”部分按“示例说明 / 代码位置 / 运行步骤 / 期望结果”四段模板排列。
- API 条目模板：模块路径 -> 简短描述 -> 公开类/函数列表（每项：签名、参数说明、返回值、异常与使用示例行号引用）。
- 翻译模板：每个英文文件应带有一份对照清单列出“建议术语翻译”（例如 IoC -> 控制反转，DI -> 依赖注入）。

## 9. 验收标准（验收检查表）

每项文档在交付前必须满足以下条件：
- 英文与中文文件 1:1 对应（路径与文件名一致，内容等效）。
- Getting Started：新用户按步骤能在 30 分钟内运行示例并访问应用。
- Examples：至少包含 2 个可运行示例（最小：Hello World HTTP，进阶：Controller + DI + Middleware 示例）。
- Wiki：覆盖架构图、组件职责、注入生命周期与错误模型。
- API 参考：覆盖所有公共模块并提供至少一个使用示例。
- Migration Guide：列出所有破坏性变更与迁移步骤（若存在）。
- Contributing：包含代码风格、PR 流程、测试准入门槛。
- Testing：现有测试在干净环境下使用 `pytest` 运行通过（与主分支同等或更优）。
- 文档审阅：至少 2 名技术评审与 1 名文本校对人员通过审阅。
- CI/发布：文档构建或静态检查（若使用 mkdocs/sphinx）通过。

## 10. 风险与缓解措施

风险 1：源码理解偏差（只读源码、不看注释可能丢失设计背景）
- 缓解：以测试用例为行为规范，必要时在审阅阶段向原作者确认设计意图，并记录为“作者说明”附录（不修改源码）。

风险 2：IoC/DI 设计复杂，难以直观表达
- 缓解：使用流程图、顺序图和示例代码演示注入时序；在 `docs/wiki/injection.md` 中增加“常见模式/反模式”小节。

风险 3：中英文翻译不一致或术语不统一
- 缓解：维护“术语对照表”；先完成英文并审校，再由翻译人员对照逐条翻译并复核。

风险 4：示例在 Windows 环境下不可运行
- 缓解：在 Windows PowerShell v5.1 下测试所有示例，并在 `build_run.md` 中给出 PowerShell 专用命令（使用分号 `;`，避免 `&&`）。

风险 5：自动生成 API 工具配置复杂
- 缓解：如自动化成本过高，可采用半自动化方案（脚本提取公有符号并生成模板）或手工补全关键模块。

## 11. 必要的命令与工具（PowerShell v5.1 示例说明）

- 建议开发环境工具：Python 3.9+（项目当前要求请核对 `setup.py`），pytest，mkdocs/sphinx，markdownlint，Typora/VSCode（用于校对），可选：graphviz（绘制依赖图）。
- 虚拟环境（示例说明）：如需在本地创建虚拟环境，请参考使用的平台和偏好；文档示例统一使用 `pip` 命令，假定已有可用的 Python 环境。
- 安装开发依赖：`pip install -U pip; pip install -e .[dev]`（或 `pip install -e .`）
- 运行测试：`py -3 -m pytest -q`
- 运行单个示例（示例位于 `examples/hello.py`）：`py examples\hello.py`
- 若使用文档工具（mkdocs）构建本地预览：`pip install mkdocs mkdocs-material; mkdocs serve`（在项目根目录或包含 `mkdocs.yml` 的目录执行）

## 12. 交付物提交 / 合并流程建议

- 每个阶段完成后提交一个单独的 PR（例如 `docs/getting-started`、`docs/wiki-injection` 等），PR 必须包含：变更说明、测试/示例验证步骤、审阅检查清单。
- 合并前需通过至少一名代码/架构评审者与一名文档校对者的审阅。
- 发布文档版本（tag）后在 `README.MD` 中更新对应版本链接。

---

如需将本计划进一步拆分为具体的 `docs/` 文件模板，并为每个文件生成初始占位内容（英文 + 中文占位），可以基于本计划继续实施并创建这些文件。
