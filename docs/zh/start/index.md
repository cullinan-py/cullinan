title: "应用构建"
slug: "application-build"
module: []
tags: ["docs", "start", "knowledge-base"]
author: "plumeink"
reviewers: []
status: updated
locale: zh
translation_pair: "docs/start/index.md"
related_tests: ["tests/core/test_public_api_boundaries.py", "tests/integration/test_adapter_integration.py"]
related_examples: ["examples/minimal_app"]
estimate_pd: 1.0
last_updated: "2026-06-01T00:00:00Z"
pr_links: []

# 应用构建

从这里开始安装 Cullinan、运行最小应用，并确认推荐的公开入口。

Cullinan 应用代码应从业务装饰器、业务方法，以及顶层
`@application` + `@configure(...)` + `main()` 注解式入口开始。

## 从这里开始

1. [快速开始](../getting_started.md) —— 安装 Cullinan 并运行最小应用
2. [示例](../examples.md) —— 查看小型端到端示例
3. [构建与运行](../build_run.md) —— 本地构建与执行流程

## 这一部分回答什么

- 如何开始一个新的 Cullinan 应用？
- 推荐入口是什么？
- 最小应用应该长什么样？
- 第一次运行成功后接下来该看哪里？

## 推荐学习链路

完成最小启动路径后，继续阅读：

- [框架语义](../concepts/index.md) 了解 Cullinan 的规则
- [工程实践](../how-to/index.md) 了解常见开发任务
- [API 参考](../reference/index.md) 在需要查符号时使用

## 边界说明

这里刻意不展开高级运行时编排细节。如果你需要显式 runtime 切换、
底层 adapter 行为或扩展内部机制，请改走
[运行时与扩展](../internals/index.md)，不要把那些 API 当成默认启动路径。
