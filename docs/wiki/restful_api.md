title: "RESTful API"
slug: "wiki-restful-api"
module: ["controller"]
tags: ["wiki", "restful-api"]
author: "plumeink"
reviewers: []
status: updated
locale: en
translation_pair: "docs/zh/wiki/restful_api.md"
related_tests: ["tests/web/test_web_runtime.py"]
related_examples: []
estimate_pd: 1.5
last_updated: "2026-05-30T00:00:00Z"
pr_links: []

# RESTful API

Cullinan's current REST stack combines controller decorators with the unified Web Runtime.

## Recommended controller style

```python
from cullinan.web.controller import controller, get_api, post_api
from cullinan.web.params import Body, Path

@controller(url="/users")
class UserController:
    @get_api(url="/{user_id}")
    async def get_user(self, user_id: int = Path()):
        return {"id": user_id}

    @post_api(url="/")
    async def create_user(self, payload: dict = Body()):
        return {"created": True, "payload": payload}
```

Plain dictionaries, models, or explicit `WebResponse` objects are all valid handler results.

## Current runtime model

- incoming requests are normalized to `WebRequest`
- route matching is handled by `Router`
- handler invocation is handled by `Dispatcher`
- outgoing responses are normalized to `WebResponse`
- server integration is delegated to a `WebAdapter`

## Response control

Return `WebResponse` directly when you need explicit headers, cookies, or status handling.

```python
from cullinan.web.gateway import WebResponse

return WebResponse.json({"ok": True}, status_code=201)
```

## Migration note

New code and documentation should use:

- `WebRequest`
- `WebResponse`
- `WebAdapter`

The old request / response / adapter naming is no longer the main public API surface.

## See also

- [Web Runtime Guide](../web_runtime_guide.md)
- [Application Lifecycle](lifecycle.md)
