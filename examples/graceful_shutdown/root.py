"""Serve a readiness probe from the framework's own draining state.

A load balancer asks one question during a deploy: *should I still send traffic
here?* Answering it from a hard-coded `True` means traffic keeps arriving while
the process is trying to finish; answering it from the framework's state means
the answer changes the moment draining starts, without a second source of truth
that can disagree.

The framework supplies the state (`accepts_requests`) and a way to react to the
transition (`add_draining_handler`). It deliberately does not ship a route, a
port or an endpoint group: the probe is part of your operations story, and you
already have somewhere to put it.
"""

import asyncio

from cullinan import application, configure
from cullinan.application import Application
from cullinan.web import controller, get_api


@controller(url="/ops")
class OpsController:
    """Answers the readiness probe from the application's own state."""

    @get_api(url="/ready")
    def ready(self):
        app = Application.current()
        # Before an application exists there is nothing to drain, and the probe
        # is asked by an operator or a load balancer rather than by a request
        # that raced startup, so "no app" is reported as ready rather than as an
        # error the caller would read as "take this instance out".
        return {"ready": bool(app is None or app.accepts_requests)}

    @get_api(url="/slow")
    async def slow(self):
        # A request long enough to still be running when the signal arrives.
        # Without it the "watch the probe change" instruction in the README
        # produces nothing to watch: the drain finishes before you can type.
        await asyncio.sleep(5.0)
        return {"slept": 5.0}

    @get_api(url="/live")
    def live(self):
        # Liveness is a different question from readiness: it asks whether the
        # process is still working, not whether it wants traffic. Answering it
        # from draining state would make a graceful shutdown look like a crash.
        return {"alive": True}


@configure(
    user_packages=["examples.graceful_shutdown"],
    server_port=4082,
    # Deliberately shorter than /ops/slow (5s): the point of the example is to
    # watch the bound *do* something. With the 30s default the slow request
    # finishes inside the drain and the reader sees nothing but a 200.
    drain_timeout=2.0,
)
@application
def main(): ...


__all__ = ["OpsController", "main"]
