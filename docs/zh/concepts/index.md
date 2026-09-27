title: "框架语义"
slug: "framework-concepts"
module: []
tags: ["docs", "concepts", "knowledge-base"]
author: "plumeink"
reviewers: []
status: updated
locale: zh
translation_pair: "docs/concepts/index.md"
related_tests: ["tests/core/test_application_model_refactor.py", "tests/regression/test_component_reliability.py"]
related_examples: []
estimate_pd: 1.0
last_updated: "2026-06-01T00:00:00Z"
pr_links: []

# 框架语义

Cullinan 不是围绕手工注册 app 对象组织的框架，而是围绕装饰器优先的业务代码、
导入执行的自动发现、按需引入的模块边界，以及清晰的公开 API 分层展开。

## 建议阅读顺序

1. [框架语义规则](../framework_semantics.md) —— 了解 Cullinan 强化执行的规则
2. [架构设计](../architecture.md) —— 了解当前框架层次与执行流

## 这一部分回答什么

- 自动发现到底如何工作？
- `@module` 在 Cullinan 里意味着什么？
- 为什么 `Inject()` 是严格契约？
- 哪些能力是受保证的，哪些只是兼容保留或高级用法？

## 下一步

理解语义模型后，继续进入：

- [工程实践](../how-to/index.md) 查看具体开发任务
- [API 参考](../reference/index.md) 查找稳定符号入口

如果你明确需要显式 runtime 编排或更底层的运行时机制，再跳到
[运行时与扩展](../internals/index.md)。
