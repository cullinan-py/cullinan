title: "API 参考"
slug: "reference-index"
module: []
tags: ["docs", "reference", "knowledge-base"]
author: "plumeink"
reviewers: []
status: updated
locale: zh
translation_pair: "docs/reference/index.md"
related_tests: []
related_examples: []
estimate_pd: 1.0
last_updated: "2026-06-01T00:00:00Z"
pr_links: []

# API 参考

当你已经知道自己要找哪个符号、哪一类 API 或哪个模块族时，
请从这里进入。这里的页面保持稳定、可检索。

## 主要入口

- [API 参考总览](../api_reference.md) —— 推荐与高级 API 分层
- 模块参考覆盖 `cullinan.core`、`cullinan.web.controller`、`cullinan.core.services`
  等公开查阅面，也包含 `cullinan.application` 这类高级页面

## 查阅规则

- 常规业务应用应优先从顶层 `cullinan` API 开始
- 高级运行时 API 应显式从对应子模块导入
- 已移除的历史 wrapper 应直接迁移，不再作为查阅路径保留

## 相关页面

- 需要解释而不是查阅？去 [框架语义](../concepts/index.md)
- 需要步骤式指导？去 [工程实践](../how-to/index.md)
- 需要内部机制？去 [运行时与扩展](../internals/index.md)
