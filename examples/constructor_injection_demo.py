# -*- coding: utf-8 -*-
"""Constructor injection demo (Issue 6).

Usage::

    cd <repo-root> && python examples/constructor_injection_demo.py

Core demo: bare type annotations = constructor injection, zero boilerplate.
"""

from cullinan.core.application_context import ApplicationContext
from cullinan.core.definitions import Definition, ScopeType


# ── Service definitions ─────────────────────────────────────────────────────

class DatabaseService:
    def query(self, sql: str) -> str:
        return f"result: [{sql}]"


class CacheService:
    def get(self, key: str) -> str:
        return f"cached({key})"


# ═══════════════════════════════════════════════════════════════════════
# Constructor injection — no Inject() needed
# ═══════════════════════════════════════════════════════════════════════

class ReportService:
    database: DatabaseService   # ← One-line declaration, framework auto-injects
    cache: CacheService         # ← No __init__, no self.x = x required


class OptionalService:
    database: DatabaseService          # Required
    notifier: "SomeNotifier" = None    # Optional — works even when not registered (= None)


# ═══════════════════════════════════════════════════════════════════════
# Mixed: constructor injection + field injection
# ═══════════════════════════════════════════════════════════════════════

from cullinan.core.decorators import Inject

class MixedService:
    database: DatabaseService          # ← Constructor injection
    cache: CacheService = Inject()     # ← Traditional field injection (coexists)


# ── Main program ────────────────────────────────────────────────────────────

def _reg(ctx, cls, name):
    """Helper: register a service in context."""
    ctx.register(Definition(
        name=name, factory=lambda c: c._create_class_instance(cls),
        scope=ScopeType.SINGLETON, source="demo", type_=cls,
    ))


def main():
    ctx = ApplicationContext()

    # Register dependencies (in production, @service + scanning does this automatically)
    _reg(ctx, DatabaseService, "db")
    _reg(ctx, CacheService, "cache")
    _reg(ctx, ReportService, "report")
    _reg(ctx, OptionalService, "optsvc")
    _reg(ctx, MixedService, "mixed")
    ctx.refresh()

    # ── Constructor injection ──
    report = ctx.get("report")
    print(f"[constructor injection] ReportService.database = {report.database}")
    print(f"[constructor injection] query → {report.database.query('SELECT 2')}")
    print(f"[constructor injection] ReportService.cache   = {report.cache}")

    # ── Optional DI ──
    opt = ctx.get("optsvc")
    print(f"[Optional]  database = {opt.database}")
    print(f"[Optional]  notifier = {opt.notifier}")  # None

    # ── Mixed mode ──
    mixed = ctx.get("mixed")
    print(f"[hybrid] database ({type(mixed.database).__name__}) from constructor injection")
    print(f"[hybrid] cache   ({type(mixed.cache).__name__}) from field injection")

    ctx.shutdown()
    print("\n[OK] Constructor injection demo completed.")


if __name__ == "__main__":
    main()
