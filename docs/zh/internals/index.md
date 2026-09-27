title: "运行时与扩展"
slug: "internals-and-extensions"
module: []
tags: ["docs", "internals", "knowledge-base"]
author: "plumeink"
reviewers: []
status: updated
locale: zh
translation_pair: "docs/internals/index.md"
related_tests: ["tests/core/test_application_model_refactor.py", "tests/integration/test_adapter_integration.py"]
related_examples: []
estimate_pd: 1.0
last_updated: "2026-06-01T00:00:00Z"
pr_links: []

# 运行时与扩展

这部分面向**高级运行时行为、内部机制与扩展开发**。

它刻意放在默认学习路径之外。普通业务应用不应从这里开始。

## 典型高级主题

- [应用运行时模型](../wiki/application_runtime.md)
- [组件](../wiki/components.md)
- [装饰器](../wiki/decorators.md)
- [注入](../wiki/injection.md)
- [生命周期](../wiki/lifecycle.md)
- [中间件](../wiki/middleware.md)
- [扩展](../wiki/extensions.md)
- [RESTful API](../wiki/restful_api.md)
- [扩展开发指南](../extension_development_guide.md)
- [扩展快速入门](../quick_start_extensions.md)

## 什么时候使用这里

- 需要把 Cullinan 集成到更大的运行时环境中
- 需要显式 `Application` 编排
- 正在处理 framework extension 或更底层的 gateway / adapter 行为

如果你是在构建普通业务应用，请回到 [应用构建](../start/index.md)。
