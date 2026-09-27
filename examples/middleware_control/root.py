"""Control the built-in middleware layer and unify legacy middleware ordering.

A single ``@configure(...)`` call shows both controls:

* ``middlewares=[TraceHeaderMiddleware()]`` — declare pipeline middleware;
* ``builtin_middleware=[QuietAccessLogMiddleware()]`` — replace the built-in
  access-log layer instead of accepting the framework default.

The legacy ``@middleware(priority=10)`` class declared in ``middleware.py``
joins the same pipeline as its own layer, so the introspection order reflects
one declarative ordering across declared, built-in and legacy middleware.
"""
from cullinan import application, configure
from cullinan.web import controller, get_api
from cullinan.web.gateway import get_pipeline

from .middleware import QuietAccessLogMiddleware, TraceHeaderMiddleware


@controller(url="/control")
class ControlController:
    @get_api(url="")
    def describe(self):
        """Report the installed middleware, outermost first."""
        order = [entry["name"] for entry in get_pipeline().list_middleware()]
        print(f"middleware order (outermost first): {order}")
        return {"order": order}


@configure(
    user_packages=["examples.middleware_control"],
    server_port=4086,
    # Declared layers for this application.
    middlewares=[TraceHeaderMiddleware()],
    # Replace the built-in access-log layer with an equivalent one.
    builtin_middleware=[QuietAccessLogMiddleware()],
)
@application
def main(): ...


__all__ = ["ControlController", "main"]
