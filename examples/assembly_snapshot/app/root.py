from cullinan import application, configure

# Imported so its ``@service`` decorator runs at import time.
from examples.assembly_snapshot.app import services  # noqa: F401


@configure(user_packages=["examples.assembly_snapshot.app"])
@application
def main(): ...


__all__ = ["main"]
