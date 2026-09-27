"""Onion-model middleware used by this example.

Both classes implement the recommended protocol — ``async def __call__(self,
request, call_next)`` — so they run *inside* the gateway pipeline and can read
the request as well as rewrite the response.
"""
from cullinan.web.gateway import GatewayMiddleware, WebResponse

GATE_HEADER = "X-Demo-Key"
GATE_VALUE = "let-me-in"


class ApiKeyGateMiddleware(GatewayMiddleware):
    """The "security gate": rejects a request unless it carries the demo key.

    It is declared with ``priority=0``, which is below the default (``100``), so
    it lands on the outermost layer and sees every request first. The order comes
    from the declaration, never from when the class happened to be registered.
    """

    async def __call__(self, request, call_next):
        if request.get_header(GATE_HEADER) != GATE_VALUE:
            return WebResponse.json({"error": "missing demo key"}, status_code=403)

        response = await call_next(request)
        response.set_header("X-Demo-Gate", "passed")
        return response


class RequestMarkerMiddleware(GatewayMiddleware):
    """Inner layer: stamp every accepted response with a visible marker."""

    async def __call__(self, request, call_next):
        response = await call_next(request)
        response.set_header("X-Demo-Marker", "middleware-pipeline")
        return response


__all__ = ["ApiKeyGateMiddleware", "GATE_HEADER", "GATE_VALUE", "RequestMarkerMiddleware"]
