"""Everything you can decide before the server starts, in one place.

Most examples change one thing and leave the rest at its default. This one is
the opposite: it sets the knobs a deployment usually needs -- where the project
root is, which packages to scan and which to skip, how loud the startup should
be, which engine and server to run under, and what address to bind -- so the
difference between "I read the option name" and "I saw it take effect" is a
single file.

Run it and the address it binds is the one written below; change one line and
the address moves.
"""

from __future__ import annotations

import logging
from pathlib import Path

from cullinan import application, configure
from cullinan import controller
from cullinan.web import get_api

# ``verbose=True`` below lowers the framework logger to DEBUG, but a logger with
# no handler prints nothing. This is the handler; uvicorn's own loggers are
# quietened so the scan lines are what you see.
logging.basicConfig(level=logging.DEBUG, format="%(levelname)-7s %(name)s: %(message)s")
for _noisy in ("uvicorn", "uvicorn.error", "uvicorn.access"):
    logging.getLogger(_noisy).setLevel(logging.WARNING)

# Pinning the root makes the example independent of the directory you launch it
# from: the framework would otherwise infer it from the working directory.
PROJECT_ROOT = Path(__file__).resolve().parents[2]


@controller(url="/runtime")
class RuntimeController:
    @get_api(url="/where")
    def where(self):
        # Read back what the framework was configured with, so changing
        # ``server_host`` / ``server_port`` below changes this answer too --
        # a hardcoded string would look like a demonstration and prove nothing.
        from cullinan.support.config import get_config

        config = get_config()
        return {
            "bound": "{}:{}".format(config.server_host, config.server_port),
            "scanned": "examples.runtime_controls only",
            "skipped": "examples.minimal_app",
        }


@configure(
    user_packages=["examples.runtime_controls"],
    # Where the project starts, instead of guessing from the cwd.
    project_root=str(PROJECT_ROOT),
    # Startup chatter: the scan summary is printed, so you can see what was found.
    verbose=True,
    # Packages the scanner must leave alone. Real projects have build output and
    # test fixtures that look importable but are not part of the application.
    exclude_packages=["examples.minimal_app"],
    # 'strict' refuses to start on a broken component; 'warn' starts anyway and
    # says so; 'ignore' is for debugging only.
    startup_error_policy="warn",
    # Pin the engine and the ASGI server so this example behaves the same on
    # every machine; leaving them unset lets the environment decide.
    server_engine="asgi",
    asgi_server="uvicorn",
    server_host="127.0.0.1",
    server_port=4085,
)
@application
def main(): ...


__all__ = ["RuntimeController", "main"]
