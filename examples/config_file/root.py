"""Where the settings come from, and what they resolve to.

The file is read explicitly here so the example behaves the same wherever it is
started from. An application normally lets ``application.run()`` do it, which
searches the working directory and the directory of the launched executable --
and never the installed package, so a bundled copy cannot shadow the operator's.
"""

from __future__ import annotations

from pathlib import Path

from cullinan import application, configure
from cullinan.support.config_file import load_project_config

#: The base document. `application-<profile>.json` beside it is merged over this
#: one when the CULLINAN_PROFILE environment variable names a profile.
CONFIG_FILE = Path(__file__).with_name("application.json")


@configure(user_packages=["examples.config_file"], server_port=4085)
@application
def main():
    """The application itself; the settings were resolved before it starts."""
    ...


def describe(profile: str | None = None) -> dict:
    """Return what the loader produces, for printing or for an assertion.

    ``${EXAMPLE_CHANNEL:#general}`` in the file is resolved from the environment
    after reading, so the document on disk holds a reference rather than a value.
    """
    return load_project_config(path=CONFIG_FILE, profile=profile)


__all__ = ["main", "describe", "CONFIG_FILE"]
