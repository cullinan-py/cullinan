title: "Generated API Reference"
slug: "reference-api-index"
module: []
tags: ["docs", "reference", "api"]
author: "plumeink"
reviewers: []
status: updated
locale: en
translation_pair: "docs/zh/reference/api/index.md"
related_tests: []
related_examples: []
estimate_pd: 0.5
last_updated: "2026-10-25"
pr_links: []

# Generated API Reference

These pages are generated from the source at build time: the signatures, the
docstrings and the member lists you read here are read out of the installed
package, not typed into a file by hand. That is the point — a handwritten page
can drift from the code and still look authoritative, while a generated one
cannot disagree with the code it was built from.

Use them when you want the exact shape of a symbol: what it accepts, what it
returns, what it raises. Use the hand-written guides when you want to know which
symbol to reach for in the first place:

- [API Reference Overview](../../api_reference.md) — recommended versus advanced
  layers, and what the stability commitment covers
- [Module references](../../modules/core.md) — the hand-written companions,
  grouped by the job you are trying to do

## Pages

| Page | Covers |
|---|---|
| [cullinan](cullinan.md) | the top-level public surface — the recommended entry points |
| [cullinan.application](application.md) | the `Application` runtime and its configuration |
| [cullinan.web](web.md) | gateway, routing, middleware, and the web namespaces |
| [cullinan.core](core.md) | container, lifecycle, request context, and the object model |

## A note on what "generated" changes

It changes the failure mode, not the content. If a docstring is wrong, the
generated page will faithfully publish the wrong sentence. So the docstrings
remain the thing to review, and this section is the place they are read from.
