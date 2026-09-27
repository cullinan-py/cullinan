title: "Framework Semantics"
slug: "framework-concepts"
module: []
tags: ["docs", "concepts", "knowledge-base"]
author: "plumeink"
reviewers: []
status: updated
locale: en
translation_pair: "docs/zh/concepts/index.md"
related_tests: ["tests/core/test_application_model_refactor.py", "tests/regression/test_component_reliability.py"]
related_examples: []
estimate_pd: 1.0
last_updated: "2026-06-01T00:00:00Z"
pr_links: []

# Framework Semantics

Cullinan is not organized around a manually wired app object. It is organized
around decorator-first business code, import-executed discovery, explicit module
boundaries when needed, and a curated public API surface.

## Read in this order

1. [Framework Semantics](../framework_semantics.md) — the rules Cullinan enforces
2. [Architecture](../architecture.md) — the current framework layers and execution flow

## Core questions answered here

- How does automatic discovery really work?
- What does `@module` mean in Cullinan?
- Why is `Inject()` strict?
- What is guaranteed, what is compatibility-only, and what is advanced?

## Next step

Once the semantic model is clear, continue with:

- [Engineering Practices](../how-to/index.md) for applied development tasks
- [API Reference](../reference/index.md) for stable symbol lookup

## Advanced topics

If you intentionally need explicit runtime orchestration or lower-level runtime
behavior, jump to [Internals & Extensions](../internals/index.md).
