title: "Cullinan 是什么"
slug: "why-cullinan"
module: []
tags: ["docs", "positioning", "overview"]
author: "plumeink"
reviewers: []
status: updated
locale: zh
translation_pair: "docs/why-cullinan.md"
related_tests: ["tests/integration/test_positioning_claims.py"]
related_examples: ["examples/minimal_app", "examples/graceful_shutdown"]
estimate_pd: 1.0
last_updated: "2026-10-26"
pr_links: []

# Cullinan 是什么

Cullinan 是一个**声明式**的 Python Web 框架：你标记一个入口方法，把服务与控制器写成普通装饰类，
框架替你解析对象图、中间件顺序与请求路径 —— 跑在 Tornado 或 ASGI 任一后端之上，而你的代码不用改。

这就是全部主张。本页其余内容的存在目的，是让这句话**可被检验**，而不是一句愿景。

## 为什么这一页主要是一张表

框架的自我介绍是最容易注水、也最难审计的东西。"快"、"轻"、"可用于生产" 写起来零成本，而且**不可被否证** ——
这正是它们对一位正在决定"要不要依赖它"的读者毫无价值的原因。

所以这里的主张只保留**机器能查**的那些，并且每一条都点名证据。下面的清单由 `scripts/check_claims.py`
抽取并核验：**某条主张一旦失去证据，检查就失败** —— 一份会缩水的文档，比一份一直在声称的文档更诚实。

## 主张与证据

下面每个条目形如 ``{id, claim, evidence: [路径...], symbols: ["路径::Name"...]}``。
路径必须是存在的文件或目录；symbol 必须是该文件里真实声明的名字。

```json
{
  "claims": [
    {
      "id": "C1",
      "claim": "应用由一个装饰过的入口方法加配置来声明，而不是手工装配。",
      "evidence": ["examples/minimal_app/root.py", "docs/getting_started.md"],
      "symbols": ["examples/minimal_app/root.py::main"]
    },
    {
      "id": "C2",
      "claim": "服务与控制器以类声明，依赖通过构造注入获得。",
      "evidence": ["examples/controller_service_inject/services.py", "docs/dependency_injection_guide.md"],
      "symbols": ["examples/controller_service_inject/services.py::UserDirectoryService"]
    },
    {
      "id": "C3",
      "claim": "同一条请求路径可运行在 Tornado 后端与 ASGI 后端之上，按部署选择；正常流量在两个后端上得到相同的状态码与响应体。",
      "evidence": ["tests/integration/test_adapter_integration.py", "cullinan/transport/adapter"],
      "symbols": []
    },
    {
      "id": "C4",
      "claim": "公共 API 面是被计数并守住的：顶层 44 个符号，各命名空间的面由测试断言。",
      "evidence": ["tests/core/test_public_api_boundaries.py", "cullinan/_contracts.json"],
      "symbols": []
    },
    {
      "id": "C5",
      "claim": "以带类型的发行包（PEP 561）分发，下游类型检查器可直接读取。",
      "evidence": ["cullinan/py.typed"],
      "symbols": []
    },
    {
      "id": "C6",
      "claim": "关闭是有界且被执行的：上限交给真正等待的那一方，到期未完成即在飞请求被切断，排空结果以布尔值返回。",
      "evidence": ["tests/core/test_graceful_drain_async.py", "docs/deployment.md"],
      "symbols": [
        "cullinan/core/application_context.py::ashutdown",
        "cullinan/core/application_context.py::await_drained"
      ]
    },
    {
      "id": "C7",
      "claim": "就绪性在还有流量可摘时就改变：停止信号到达即宣告排空，已在跑的工作受一个可配置的上限约束。",
      "evidence": ["examples/graceful_shutdown/root.py", "examples/graceful_shutdown/README.md"],
      "symbols": ["cullinan/core/application_context.py::accepts_requests"]
    },
    {
      "id": "C8",
      "claim": "弃用的移除版本由「该弃用所落的版本」算出，从不是可能漂移的字面量。",
      "evidence": ["cullinan/support/deprecation.py", "tests/core/test_deprecated_api_warnings.py"],
      "symbols": ["cullinan/support/deprecation.py::resolve_removal_version"]
    },
    {
      "id": "C9",
      "claim": "运行时依赖刻意保持很小：一个包 python-dotenv，两个引擎作为可选 extra 提供。",
      "evidence": ["pyproject.toml"],
      "symbols": []
    },
    {
      "id": "C10",
      "claim": "每个被教学的特性都有可运行示例与对应页面，且双向受检。",
      "evidence": ["examples/features.json", "tests/integration/test_feature_example_matrix.py"],
      "symbols": []
    }
  ]
}
```

## 本页**不**主张什么

- **不主张"最快"。** 没有工作负载的数字只是装饰。仓库提供的是你可以在自己机器上跑的基准
  （`benchmarks/bench.py`），而不是一个无法迁移的头条数字。
- **不主张"零配置"。** 藏起配置的框架无法被运维；这个框架把开关摆出来，见 [生产部署](deployment.md)。
- **不主张"1.0"。** 当前是预发布线。公共面已冻结，因此依赖可以被放心锁定；
  但行为仍可能在发行说明明确写出的地方发生变化。
