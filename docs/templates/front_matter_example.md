title: "Front-matter Example"
slug: "front-matter-example"
module: []
tags: ["template"]
author: "TBD"
reviewers: []
status: draft
locale: en
translation_pair: "docs/zh/templates/front_matter_example.md"
related_tests: []
related_examples: ["examples/minimal_app"]
estimate_pd: 0.1
last_updated: "2025-11-18"
pr_links: []

# Front-matter example (template)

Place this block at the top of each public doc (replace values):

```
title: "<Short title>"
slug: "<path-friendly-slug>"
module: ["cullinan.core"]
tags: ["getting-started", "ioc"]
author: "Name <github>"
reviewers: ["Name <github>"]
status: draft
locale: en
translation_pair: "docs/zh/<file>.md"
related_tests: ["tests/test_real_app_startup.py"]
related_examples: ["examples/minimal_app"]
estimate_pd: 2.0
last_updated: "2025-11-18"
pr_links: []
```

Notes: Keep this block short and machine-parseable.
