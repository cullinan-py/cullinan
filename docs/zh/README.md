title: "Cullinan 文档"
slug: "docs-home"
module: []
tags: ["docs", "home", "knowledge-base"]
author: "Cullinan"
reviewers: []
status: updated
locale: zh
translation_pair: "docs/README.md"
related_tests: []
related_examples: []
estimate_pd: 0.5
last_updated: "2026-06-01T00:00:00Z"
pr_links: []

# Cullinan 文档

> **当前版本：0.95**。最短公开启动路径是
> `@application` + `@configure(...)` + `main()` 注解式入口；语义学习路径先从顶层 `cullinan`
> 以及业务向的 `cullinan.web` / `cullinan.core` 语汇开始：先理解业务装饰器与业务方法，
> 只有在应用确实需要时，再进入高级 application/runtime 细节。

## 默认学习路径

1. [应用构建](start/index.md)
2. [框架语义](concepts/index.md)
3. [工程实践](how-to/index.md)
4. [API 参考](reference/index.md)

这条路径适用于大多数使用 Cullinan 构建业务应用的开发者。它刻意把高级运行时内部机制
与版本迁移说明放在首读路径之外。

## 文档导航

### 1. [应用构建](start/index.md)

用于通过推荐公开 API 启动新应用。

- [快速开始](getting_started.md)
- [示例](examples.md)
- [构建与运行](build_run.md)

### 2. [框架语义](concepts/index.md)

用于理解 Cullinan 的工作方式，以及它为什么不鼓励显式 app 风格的手工注册。

- [框架语义规则](framework_semantics.md)
- [架构设计](architecture.md)

### 3. [工程实践](how-to/index.md)

用于回答具体开发任务怎么做。

- [依赖注入指南](dependency_injection_guide.md)
- [Web Runtime 指南](web_runtime_guide.md)
- [参数系统指南](parameter_system_guide.md)
- [测试与验证](testing.md)

### 4. [API 参考](reference/index.md)

用于查符号与查看稳定 API 表面。

- [API 参考总览](api_reference.md)
- 具体模块参考留在这一部分，按查阅需要进入即可。
- 默认先看总览，再按需查看 `controller`、`service`、`core` 等参考页。
- 高级 application/runtime 表面不再放进默认首读路径。

### 5. [运行时与扩展](internals/index.md)

只有在你明确需要高级运行时或扩展知识时才进入这里。

- [应用运行时模型](wiki/application_runtime.md)
- [扩展开发指南](extension_development_guide.md)
- [扩展快速入门](quick_start_extensions.md)

### 6. [版本迁移](migration/index.md)

用于升级版本或把旧代码对齐到新语义。

- [运行时整合](runtime_updates_v093.md)
- [迁移指南](migration_guide.md)
- [迁移指南 v2](migration_guide_v2.md)
- [0.90 导入迁移](import_migration_090.md)

源码与发布历史请访问 [GitHub 仓库](https://github.com/cullinan-py/cullinan)。
