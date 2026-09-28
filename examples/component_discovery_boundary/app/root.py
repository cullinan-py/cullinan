from cullinan import application, configure

# Imported so its ``@service`` decorator runs at import time -- this is what
# makes the component *declared*. It is deliberately NOT listed in
# ``user_packages`` below, so the assembly pass never picks it up.
import examples.component_discovery_boundary.outside.services  # noqa: F401

from examples.component_discovery_boundary.app import services  # noqa: F401


@configure(user_packages=["examples.component_discovery_boundary.app"])
@application
def main(): ...


__all__ = ["main"]
