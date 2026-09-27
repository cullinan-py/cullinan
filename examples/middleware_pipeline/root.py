"""Middlewares declared through ``@configure(middlewares=[...])``.

Declaration order is meaningful only through the declarative order controls:

* ``priority=0`` (below the default ``100``) puts the security gate on the
  outermost layer, so it sees every request first.
* ``RequestMarkerMiddleware`` keeps the default priority and therefore ends up
  on the inner layer.

The ordered pipeline can be read back at runtime through the public reflection
API: ``cullinan.web.gateway.get_pipeline().list_middleware()``.
"""
from cullinan import application, configure
from cullinan.web import controller, get_api
from cullinan.web.gateway import get_pipeline

from .middleware import ApiKeyGateMiddleware, RequestMarkerMiddleware


@controller(url="/pipeline")
class PipelineController:
    @get_api(url="")
    def describe(self):
        """Report the middleware that is actually installed, in execution order."""
        order = [entry["name"] for entry in get_pipeline().list_middleware()]
        print(f"middleware order (outermost first): {order}")
        return {"order": order}

    @get_api(url="/echo")
    def echo(self):
        """Only reachable when the outermost gate lets the request through."""
        return {"message": "the gate let this request through"}


@configure(
    user_packages=["examples.middleware_pipeline"],
    server_port=4085,
    # Declarative entry: the pipeline is assembled at the framework startup point,
    # so this order does not depend on registration timing.
    middlewares=[
        (ApiKeyGateMiddleware(), {"priority": 0}),
        RequestMarkerMiddleware(),
    ],
)
@application
def main(): ...


__all__ = ["PipelineController", "main"]
