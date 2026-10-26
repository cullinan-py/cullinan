title: "自动生成的 API 参考"
slug: "reference-api-index"
module: []
tags: ["docs", "reference", "api"]
author: "plumeink"
reviewers: []
status: updated
locale: zh
translation_pair: "docs/reference/api/index.md"
related_tests: []
related_examples: []
estimate_pd: 0.5
last_updated: "2026-10-27"
pr_links: []

# 自动生成的 API 参考

本节的页面在**构建时**从源码生成：你读到的签名、docstring 与成员列表都取自**已安装的包**，
而不是由人手写进某个文件。这正是它的意义 —— 手写页可能与代码脱节却仍显得权威，
而生成页不可能与它据以生成的代码不一致。

需要某个符号的**确切形状**（接受什么、返回什么、抛什么）时，看这里。
需要知道**该用哪个符号**时，看手写指南：

- [API 参考总览](../../api_reference.md) —— 推荐层与高级层之分，以及稳定性承诺覆盖什么
- [模块参考](../../modules/core.md) —— 手写的配套页，按你要完成的事情编排

## 页面

| 页面 | 覆盖 |
|---|---|
| [cullinan](cullinan.md) | 顶层公共面 —— 推荐入口 |
| [cullinan.application](application.md) | `Application` 运行时及其配置 |
| [cullinan.web](web.md) | 网关、路由、中间件与 Web 各命名空间 |
| [cullinan.core](core.md) | 容器、生命周期、请求上下文与对象模型 |

## 「自动生成」改变了什么

改变的是**失效方式**，不是内容。若 docstring 写错了，生成页会忠实地把错话发布出去。
所以 docstring 仍是要被审阅的东西，而本节只是它们被读出来的地方。
