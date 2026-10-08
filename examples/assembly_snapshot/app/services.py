from cullinan import service


@service
class ReportService:
    """A container-managed component.

    It exists so the assembly snapshot's ``container`` surface has something to
    report: the component is declared inside ``user_packages`` and assembled.
    """


__all__ = ["ReportService"]
