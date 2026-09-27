title: "Extensions & Plugins"
slug: "extensions"
module: ["cullinan"]
tags: ["extensions", "plugins"]
author: "plumeink"
reviewers: []
status: updated
locale: en
translation_pair: "docs/zh/wiki/extensions.md"
related_tests: []
related_examples: []
estimate_pd: 1.0
last_updated: "2026-05-30T00:00:00Z"
pr_links: []

# Extensions & Plugins

Cullinan extensions should build on the unified container and Web Runtime rather than patching internal registries directly.

## Common extension points

### Container extensions

Register custom definitions or factories through `ApplicationContext`.

### Controller extensions

Expose routes with controller decorators or explicit startup registration.

### Middleware extensions

Add middleware to the gateway pipeline to influence request/response handling.

### Lifecycle extensions

Use component lifecycle hooks or application startup/shutdown orchestration.

## Recommended pattern

1. Create explicit registration code for your extension
2. Register definitions or middleware during application startup
3. Keep registration idempotent for tests and repeated bootstraps
4. Prefer public facades (`cullinan.core`, `cullinan.web.gateway`, `cullinan.transport.adapter`)

## See also

- [Extension Development Guide](../extension_development_guide.md)
- [Web Runtime Guide](../web_runtime_guide.md)
