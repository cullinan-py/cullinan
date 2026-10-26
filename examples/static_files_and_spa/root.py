"""Static files and SPA example for Cullinan.

Demonstrates:

* serving classic static assets under ``/static`` and ``/public`` with caching
  headers (the ``/static`` prefix used to be shadowed by Tornado's native
  static handler — Cullinan now serves it engine-neutrally through the router),
* serving a Single-Page Application bundle under ``/`` with client-side
  routing fallback to ``index.html`` while still returning 404 for missing
  ``*.js``/``*.css`` requests,
* coexistence with regular controllers — `GET /api/health` keeps working.

The same configuration runs under both Tornado and ASGI engines without
changes — Cullinan registers ``StaticFiles`` on its gateway router so
runtime selection stays a deployment decision, not an application concern.
"""

from pathlib import Path

from cullinan import application, configure
from cullinan import controller
from cullinan.web import StaticFiles, get_api


_HERE = Path(__file__).resolve().parent


@controller(url="/api/health")
class HealthController:
    @get_api(url="")
    def health(self):
        return {"status": "ok"}


@configure(
    user_packages=["examples.static_files_and_spa"],
    server_port=4082,
    static_files=[
        # Classic /static/* mount. The /static prefix is special: a Tornado
        # ``static_path`` setting would auto-register Tornado's native
        # StaticFileHandler here and shadow this mount. Cullinan keeps it
        # router-based so the prefix behaves identically on Tornado and ASGI.
        StaticFiles(
            url="/static",
            directory=str(_HERE / "static"),
            max_age=3600,
        ),
        # Classic /public/* mount with a 1-hour cache window.
        StaticFiles(
            url="/public",
            directory=str(_HERE / "public"),
            max_age=3600,
        ),
        # SPA bundle under / with client-side routing fallback.
        # Long-cache the immutable assets folder.
        StaticFiles(
            url="/assets",
            directory=str(_HERE / "spa" / "assets"),
            max_age=31536000,
            immutable=True,
        ),
        StaticFiles.spa_app(
            directory=str(_HERE / "spa"),
            index="index.html",
        ),
    ],
)
@application
def main(): ...


__all__ = ["main"]
