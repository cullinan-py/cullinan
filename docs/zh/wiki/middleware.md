title: "Middleware"
slug: "middleware"
module: ["cullinan.web.middleware"]
tags: ["middleware"]
author: "plumeink"
reviewers: []
status: updated
locale: zh
translation_pair: "docs/wiki/middleware.md"
related_tests: ["tests/web/test_web_runtime.py"]
related_examples: []
estimate_pd: 1.0
last_updated: "2026-05-30T00:00:00Z"
pr_links: []

# Middleware

Cullinan 的 middleware 现在参与统一后的 Web Runtime pipeline。

## 主要导出

- `middleware`
- `Middleware`
- `MiddlewareChain`
- `BodyDecoderMiddleware`
- `get_middleware_registry()`
- `reset_middleware_registry()`

旧的手工注册辅助函数仍然存在，但新代码应优先使用装饰器式或启动阶段的运行时注册方式。

## 使用建议

- 保持 middleware 轻量，把业务逻辑委托给注入的服务
- 不要把 request scope 状态保存在长生命周期 middleware 实例上
- 让 gateway pipeline 统一处理组合与顺序

## 示例

```python
from cullinan.web.middleware import Middleware

class AuditMiddleware(Middleware):
    async def process_request(self, request):
        return None
```

对于旧式 middleware 集成，应用启动阶段可以把其桥接进 gateway pipeline。

## 另见

- [Web Runtime 指南](../web_runtime_guide.md)
- [应用生命周期](lifecycle.md)
