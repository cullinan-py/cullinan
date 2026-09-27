title: "API Reference"
slug: "reference-index"
module: []
tags: ["docs", "reference", "knowledge-base"]
author: "plumeink"
reviewers: []
status: updated
locale: en
translation_pair: "docs/zh/reference/index.md"
related_tests: []
related_examples: []
estimate_pd: 1.0
last_updated: "2026-06-01T00:00:00Z"
pr_links: []

# API Reference

Use this section when you already know the symbol, surface, or module family you
want to inspect. The pages here stay stable and searchable.

## Main entrypoints

- [API Reference Overview](../api_reference.md) — recommended and advanced API layers
- Module references cover public lookup surfaces such as `cullinan.core`,
  `cullinan.web.controller`, and `cullinan.core.services`, plus advanced pages
  such as `cullinan.application`

## Reference rules

- Regular application code should start from the top-level `cullinan` API
- Advanced runtime APIs should be explicitly imported from their own modules
- Removed historical wrappers should be migrated rather than kept alive as a lookup path

## Related pages

- Need explanation instead of lookup? Go to [Framework Semantics](../concepts/index.md)
- Need step-by-step usage? Go to [Engineering Practices](../how-to/index.md)
- Need internals? Go to [Internals & Extensions](../internals/index.md)
