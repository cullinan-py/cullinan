from cullinan import service


@service
class DroppedService:
    """Declared in a package that is **not** listed in ``user_packages``.

    This is the **negative** case: the decorator runs at import time, so the
    component is *declared*, but the assembly pass only scans ``user_packages``,
    so it is never *assembled*. Cullinan reports the difference with a
    ``component-declared-not-assembled`` warning instead of dropping it
    silently.
    """
