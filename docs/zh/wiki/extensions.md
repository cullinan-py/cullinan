title: "扩展与插件"
slug: "extensions"
module: ["cullinan"]
tags: ["extensions", "plugins"]
author: "plumeink"
reviewers: []
status: updated
locale: zh
translation_pair: "docs/wiki/extensions.md"
related_tests: []
related_examples: []
estimate_pd: 1.0
last_updated: "2026-05-30T00:00:00Z"
pr_links: []

# 扩展与插件

Cullinan 扩展应建立在统一容器与 Web Runtime 之上，而不是直接修改内部 registry。

## 常见扩展点

### 容器扩展

通过 `ApplicationContext` 注册自定义 Definition 或 factory。

### 控制器扩展

通过控制器装饰器或启动阶段显式注册暴露新路由。

### Middleware 扩展

把 middleware 加入 gateway pipeline，影响请求/响应处理流程。

### 生命周期扩展

通过组件生命周期钩子或应用启动/关闭编排接入扩展逻辑。

## 推荐模式

1. 为扩展编写显式注册代码
2. 在应用启动阶段注册 Definition 或 middleware
3. 让注册逻辑保持幂等，便于测试与重复启动
4. 优先依赖公开门面：`cullinan.core`、`cullinan.web.gateway`、`cullinan.transport.adapter`

## 另见

- [扩展开发指南](../extension_development_guide.md)
- [Web Runtime 指南](../web_runtime_guide.md)
