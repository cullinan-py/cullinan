# Example: Cullinan application packaged with Nuitka or PyInstaller
#
# This example demonstrates the recommended configuration for frozen
# environments.  The unified pipeline (scan_strategies + scan_pipelines)
# handles all packaging modes automatically.
#
# Build commands:
#   Nuitka standalone:  nuitka --standalone --include-package=myapp main.py
#   Nuitka onefile:     nuitka --onefile --include-package=myapp main.py
#   PyInstaller onedir: pyinstaller --onedir main.py
#   PyInstaller onefile: pyinstaller --onefile main.py
#
# Usage:
#   cd examples/packaging_demo
#   python main.py

from cullinan import application, configure

# ---------------------------------------------------------------------------
# Packaging Configuration
# ---------------------------------------------------------------------------
# explicit_modules: hard-coded list for --onefile modes where filesystem
#   scanning is unavailable.  Also works in --standalone/--onedir modes.
# user_packages: pkgutil-based discovery for --standalone/--onedir modes.
#   Works alongside explicit_modules — the pipeline runs S0 then S1.
# ---------------------------------------------------------------------------

@configure(
    # Primary: explicit module list (works for ALL packaging modes)
    explicit_modules=["myapp"],

    # Secondary: package-based discovery (works when filesystem is available)
    user_packages=["myapp"],

    # Auto-scan sys.modules as additional fallback
    auto_scan=True,
)
@application
def main():
    """Recommended entry method: call it directly (or via ``python -m``).

    This is the standard Cullinan entry form — ``@configure(...)`` attaches the
    startup settings and ``@application`` marks the function as the entry
    method. ``python main.py`` / ``python -m`` reaches it; a frozen build
    (Nuitka / PyInstaller) starts the same way.
    """


if __name__ == "__main__":
    main()
