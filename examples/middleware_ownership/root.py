"""Two declarative middleware forms and their object ownership.

``configure(middlewares=[Class])`` is **container-managed**: a middleware class
declared with ``@component`` is created, injected and held by the framework
container, so the pipeline runs the same instance the container manages.

``configure(middlewares=[instance])`` is **externally-owned**: the middleware
instance is created by the application and installed as-is.

Both forms are declared here side by side, so the single pipeline that runs them
and the ownership difference between them are visible in one place.
"""
from cullinan import application, configure
from cullinan.core import component, get_application_context
from cullinan.web import controller, get_api
from cullinan.web.gateway import GatewayMiddleware, get_pipeline


@component
class AuditLog:
    """A dependency owned by the container; the middleware records into it."""

    def __init__(self):
        self.entries = []

    def record(self, path):
        self.entries.append(path)


@component
class AuditMiddleware(GatewayMiddleware):
    """Container-managed: declared as a class, so the container owns it.

    The declared ``log`` dependency is injected by the container, and the
    instance the container creates is the one installed on the pipeline.
    """

    log: AuditLog

    async def __call__(self, request, call_next):
        self.log.record(request.path)
        response = await call_next(request)
        response.set_header("X-Audit-Entries", str(len(self.log.entries)))
        return response


class MarkerMiddleware(GatewayMiddleware):
    """Externally-owned: the application creates the instance and passes it."""

    async def __call__(self, request, call_next):
        response = await call_next(request)
        response.set_header("X-Marker", "externally-owned")
        return response


@controller(url="/ownership")
class OwnershipController:
    @get_api(url="")
    def describe(self):
        """Report the installed order and the ownership of each form."""
        order = [entry["name"] for entry in get_pipeline().list_middleware()]
        container_instance = get_application_context().get("AuditMiddleware")
        print(f"middleware order (outermost first): {order}")
        print(f"audit entries recorded by the container instance: {container_instance.log.entries}")
        return {
            "order": order,
            "container_managed": "AuditMiddleware",
            "externally_owned": "MarkerMiddleware",
            "audit_log_entries": list(container_instance.log.entries),
        }


@configure(
    user_packages=["examples.middleware_ownership"],
    server_port=4087,
    # Class entry -> container-managed; instance entry -> externally-owned.
    middlewares=[AuditMiddleware, MarkerMiddleware()],
)
@application
def main(): ...


__all__ = [
    "AuditLog",
    "AuditMiddleware",
    "MarkerMiddleware",
    "OwnershipController",
    "main",
]
