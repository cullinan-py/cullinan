"""A tiny upload endpoint with a body ceiling, so the limit is visible.

The framework reads the body before it knows which route will handle it, which
means a server that accepts uploads needs an edge limit rather than a check
inside the handler: by the time the handler runs, the bytes are already in
memory. This example sets one and nothing else, so the difference between "under
the ceiling" and "over it" is the only thing to look at.
"""

from cullinan import application, configure
from cullinan.web import controller, post_api

LIMIT = 1024


@controller(url="/upload")
class UploadController:
    @post_api(url="/size")
    def size(self, request):
        # Only reachable when the body fit under the ceiling: the refusal
        # happens before routing, so this line never sees an oversized body.
        return {"bytes": len(request.body or b"")}


@configure(
    user_packages=["examples.request_body_limit"],
    server_port=4084,
    # 1 KiB is small enough to cross with a single curl. Unset means "read
    # whatever arrives", which is the framework's default and would make this
    # example indistinguishable from one without a ceiling.
    max_request_body_bytes=LIMIT,
)
@application
def main(): ...


__all__ = ["UploadController", "main"]
