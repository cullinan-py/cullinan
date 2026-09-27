from cullinan import service


@service
class AssembledService:
    """Declared inside ``user_packages`` -> discovered and assembled.

    This is the **positive** case: the declaring package is listed in
    ``@configure(user_packages=[...])``, so discovery imports it, the decorator
    runs, and the component is assembled.
    """
