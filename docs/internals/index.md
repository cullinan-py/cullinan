title: "Internals & Extensions"
slug: "internals-and-extensions"
module: []
tags: ["docs", "internals", "knowledge-base"]
author: "plumeink"
reviewers: []
status: updated
locale: en
translation_pair: "docs/zh/internals/index.md"
related_tests: ["tests/core/test_application_model_refactor.py", "tests/integration/test_adapter_integration.py"]
related_examples: []
estimate_pd: 1.0
last_updated: "2026-10-27"
pr_links: []

# Internals & Extensions

This section is for **advanced runtime behavior, internal mechanisms, and extension work**.

It is intentionally outside the default onboarding path. Regular business
applications should not start here.

## Typical advanced topics

- [Application Runtime Model](../internals/application_runtime.md)
- [Components](../internals/components.md)
- [Decorators](../internals/decorators.md)
- [Injection](../internals/injection.md)
- [Lifecycle](../internals/lifecycle.md)
- [Middleware](../internals/middleware.md)
- [Extensions](../internals/extensions.md)
- [RESTful API](../internals/restful_api.md)
- [Extension Development Guide](../extension_development_guide.md)
- [Quick Start Extensions](../quick_start_extensions.md)

## Use this section when

- you are integrating Cullinan into a larger runtime environment
- you need explicit `Application` orchestration
- you are working on framework extensions or lower-level gateway/adapter behavior

If you are building a normal application, go back to [Application Build](../start/index.md).
