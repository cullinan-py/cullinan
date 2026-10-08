# -*- coding: utf-8 -*-
import importlib
import inspect
import os
import importlib.util
import logging
import sys
import threading

from dotenv import load_dotenv
from pathlib import Path

# Import module scanning utilities (refactored for better maintainability)
from cullinan.runtime.module_scanner import (
    is_pyinstaller_frozen,
    is_nuitka_compiled,
    file_list_func
)

# Module-level logger
logger = logging.getLogger(__name__)


def reflect_module(module_name: str, func: str) -> None:
    """Import a module by dotted name and optionally call a function on it.

    - If `func` is 'nobody' or 'controller' we only import the module (decorators will run at import).
    - Otherwise, if the attribute named `func` exists and is callable, call it.

    Errors during import or call are logged but swallowed to keep scanning robust.
    
    Args:
        module_name: Dotted module name to import (e.g., 'myapp.controllers.user')
        func: Function name to call after import, or 'nobody'/'controller' to skip calling
    """
    if not module_name:
        return

    # sanitize package-style paths that may come from file-system discovery
    if module_name.endswith('.py'):
        module_name = module_name[:-3]
    module_name = module_name.strip('.')

    if not module_name:
        return

    logger.debug("Reflecting module: %s (func: %s)", module_name, func)

    mod = None

    # Strategy 0: Check sys.modules first (Nuitka environments typically have modules pre-loaded)
    if module_name in sys.modules:
        mod = sys.modules[module_name]
        logger.info("[OK] Found in sys.modules: %s", module_name)

        # For controller and service, module already loaded means decorators have executed
        if func in ('nobody', 'controller'):
            logger.debug("[OK] Module already loaded (decorators executed): %s", module_name)
            return

        # Continue to call the function (if needed)
        if func not in ('nobody', 'controller'):
            try:
                fn = getattr(mod, func, None)
                if callable(fn):
                    fn()
                    logger.debug("[OK] Called function: %s.%s", module_name, func)
            except Exception as e:
                logger.debug("[FAIL] Error calling %s.%s: %s", module_name, func, str(e))
        return

    # Strategy 1: Standard import (works in all environments)
    try:
        mod = importlib.import_module(module_name)
        logger.info("[OK] Successfully imported: %s", module_name)

        # For controller and service, importing is enough (decorators will execute)
        if func in ('nobody', 'controller'):
            logger.debug("[OK] Module imported (decorators executed): %s", module_name)
            return

    except ImportError as e:
        error_msg = str(e)
        logger.warning("[FAIL] Import failed for %s: %s", module_name, error_msg)

        # Strategy 2: Try relative import (may be needed after Nuitka compilation)
        if is_nuitka_compiled() and '.' in module_name:
            # Try importing from parent package
            parts = module_name.rsplit('.', 1)
            if len(parts) == 2:
                parent_pkg, mod_part = parts
                try:
                    parent = importlib.import_module(parent_pkg)
                    if hasattr(parent, mod_part):
                        mod = getattr(parent, mod_part)
                        logger.info("[OK] Imported as attribute: %s from %s", mod_part, parent_pkg)

                        if func in ('nobody', 'controller'):
                            return
                    else:
                        # Try using __import__ with the fromlist parameter
                        try:
                            mod = __import__(module_name, fromlist=[mod_part])
                            logger.info("[OK] Imported using __import__: %s", module_name)

                            if func in ('nobody', 'controller'):
                                return
                        except Exception as e2:
                            logger.debug("[FAIL] __import__ also failed: %s", str(e2))
                except Exception as e3:
                    logger.debug("[FAIL] Relative import failed: %s", str(e3))

        # Strategy 3: Fetch from sys.modules (may have been pre-loaded by packaging tool)
        if module_name in sys.modules:
            mod = sys.modules[module_name]
            logger.info("[OK] Found in sys.modules: %s", module_name)

            if func in ('nobody', 'controller'):
                return

        # Strategy 4: Try importing via file path (last resort)
        elif is_pyinstaller_frozen() or is_nuitka_compiled():
            # Try constructing possible file paths
            base_dirs = []

            if is_pyinstaller_frozen():
                meipass = getattr(sys, '_MEIPASS', None)
                if meipass:
                    base_dirs.append(meipass)

            if is_nuitka_compiled():
                exe_dir = os.path.dirname(sys.executable)
                base_dirs.append(exe_dir)

            for base in base_dirs:
                module_path = os.path.join(base, module_name.replace('.', os.sep) + '.py')
                if os.path.exists(module_path):
                    try:
                        spec = importlib.util.spec_from_file_location(module_name, module_path)
                        if spec and spec.loader:
                            mod = importlib.util.module_from_spec(spec)
                            sys.modules[module_name] = mod  # Register with sys.modules
                            spec.loader.exec_module(mod)
                            logger.info("[OK] Imported from file: %s", module_path)
                            break
                    except Exception as import_ex:
                        logger.warning("[FAIL] Failed to import from file %s: %s", module_path, str(import_ex))
    except Exception as e:
        logger.warning("[FAIL] Unexpected error importing %s: %s", module_name, str(e))
        return

    if mod is None:
        logger.warning("[FAIL] Could not import module: %s", module_name)
        return

    # For controller and service, importing is enough (decorators execute at import time)
    if func in ('nobody', 'controller'):
        logger.debug("[OK] Module imported (decorators executed): %s", module_name)
        return

    # Call the specified function (if it exists)
    try:
        fn = getattr(mod, func, None)
        if callable(fn):
            fn()
            logger.debug("[OK] Called function: %s.%s", module_name, func)
    except Exception as e:
        logger.debug("[FAIL] Error calling %s.%s: %s", module_name, func, str(e))
        return



def scan_controller(modules: list) -> None:
    """Scan and import controller modules to register their handlers.
    
    Args:
        modules: List of dotted module names to scan
    """
    for mod in modules:
        reflect_module(mod, 'controller')



def scan_service(modules: list) -> None:
    """Scan and import service modules to register their services.
    
    Args:
        modules: List of dotted module names to scan
    """
    for mod in modules:
        reflect_module(mod, 'nobody')




def is_started_directly() -> bool:
    """Return True if the process was started directly (a __main__ frame exists).

    Uses sys._getframe() for efficiency in compiled environments (Nuitka/PyInstaller).
    Falls back to inspect.stack() if _getframe is unavailable.
    """
    try:
        frame = sys._getframe()
        while frame is not None:
            module = inspect.getmodule(frame)
            if module is not None:
                if getattr(module, '__name__', '') == '__main__':
                    return True
            frame = frame.f_back
        return False
    except Exception:
        pass

    # Fallback for environments without sys._getframe()
    try:
        for frame_info in inspect.stack():
            module = inspect.getmodule(frame_info[0])
            if module is None:
                continue
            if getattr(module, '__name__', '') == '__main__':
                return True
    except Exception:
        pass
    return False


# Thread-safety guard for _ensure_console_logging
_logging_initialized = False
_logging_lock = threading.Lock()


def _ensure_console_logging():
    """Ensure framework logs appear on console when the application hasn't configured logging.

    Behavior:
    - If the root logger already has handlers, assume application configured logging and do nothing.
    - If the 'cullinan' package logger already has handlers, do nothing.
    - Otherwise add a StreamHandler to stdout on the 'cullinan' logger at INFO level.
    - Honor env var CULLINAN_DISABLE_AUTO_CONSOLE=1 to disable this behavior.

    Thread-safe: uses a module-level lock and flag to prevent duplicate handlers.
    """
    global _logging_initialized
    if _logging_initialized:
        return None
    with _logging_lock:
        if _logging_initialized:
            return None
        try:
            if os.getenv('CULLINAN_DISABLE_AUTO_CONSOLE', '0') == '1':
                _logging_initialized = True
                return None
            # Allow forcing console handler via env var (useful in tests/IDE runs)
            force = os.getenv('CULLINAN_FORCE_CONSOLE', '0').lower() in ('1', 'true', 'yes')
            # only auto-enable console logging when the process was started directly
            # unless forced via CULLINAN_FORCE_CONSOLE
            if not force and not is_started_directly():
                _logging_initialized = True
                return None
            root = logging.getLogger()
            # consider only "real" handlers (not NullHandler)
            root_has_real = any(not isinstance(h, logging.NullHandler) for h in getattr(root, 'handlers', []) if h is not None)
            if root_has_real:
                _logging_initialized = True
                return None
            pkg_logger = logging.getLogger('cullinan')
            pkg_has_real = any(not isinstance(h, logging.NullHandler) for h in getattr(pkg_logger, 'handlers', []) if h is not None)
            if pkg_has_real:
                _logging_initialized = True
                return None
            # add a console handler to the package logger
            console_handler = logging.StreamHandler(sys.stdout)
            fmt = logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
            console_handler.setFormatter(fmt)
            # allow customizing console level via env var (e.g. DEBUG/INFO)
            lvl_name = os.getenv('CULLINAN_AUTO_CONSOLE_LEVEL', '').strip()
            if lvl_name:
                try:
                    level = int(lvl_name)
                except Exception:
                    level = getattr(logging, lvl_name.upper(), None)
                if isinstance(level, int):
                    console_handler.setLevel(level)
                else:
                    console_handler.setLevel(logging.INFO)
            else:
                console_handler.setLevel(logging.INFO)
            pkg_logger.addHandler(console_handler)
            pkg_logger.setLevel(logging.INFO)
            pkg_logger.propagate = False
            _logging_initialized = True
            return console_handler
        except Exception:
            # never raise from logging setup
            _logging_initialized = True
            return None


# ASCII banner used when the framework starts; backslashes are escaped so this
# compiles cleanly and prints exactly as intended.
BANNER = (
    "|||||||||||||||||||||||||||||||||||||||||||||||||\n"
    "|||                                           |||\n"
    "|||    _____      _ _ _                       |||\n"
    "|||   / ____|    | | (_)                      |||\n"
    "|||  | |    _   _| | |_ _ __   __ _ _ __      |||\n"
    "|||  | |   | | | | | | | '_ \\ / _` | '_ \\     |||\n"
    "|||  | |___| |_| | | | | | | | (_| | | | |    |||\n"
    "|||   \\_____\\__,_|_|_|_|_| |_|\\__,_|_| |_|    |||\n"
    "|||                                           |||\n"
    "|||||||||||||||||||||||||||||||||||||||||||||||||\n"
    "\t|||\n"
)


def _register_explicit_classes():
    """Legacy explicit registration mode has been removed."""


def run(handlers=None):
    """Legacy entry point — delegates to top-level ``cullinan.run()``.

    This function performs the module scanning (services + controllers)
    and then hands off to the gateway-based startup in ``application.py``.
    """
    if handlers is None:
        handlers = []
    # ensure console logging is available by default
    installed_handler = _ensure_console_logging()
    if installed_handler is not None:
        old_fmt = None
        try:
            old_fmt = getattr(installed_handler, 'formatter', None)
            installed_handler.setFormatter(logging.Formatter('%(message)s'))
            logger.info(BANNER)
        finally:
            try:
                installed_handler.setFormatter(old_fmt)
            except Exception:
                pass
    else:
        logger.info(BANNER)
    logger.info("loading env...")
    load_dotenv()
    load_dotenv(verbose=True)
    env_path = Path(os.getcwd()) / '.env'
    load_dotenv(dotenv_path=env_path)

    # Initialize IoC/DI 2.0
    logger.info("└---initializing IoC/DI 2.0...")
    from cullinan.core import ApplicationContext, set_application_context

    ctx = ApplicationContext()
    set_application_context(ctx)
    logger.info("└---IoC/DI 2.0 initialized (ApplicationContext created)")

    # Register explicit services and controllers (if configured)
    _register_explicit_classes()

    # Scan services
    logger.info("└---scanning services...")
    service_modules = file_list_func()
    if not service_modules:
        logger.warning("[WARN] No modules found for service scanning!")
    else:
        logger.info("└---found %d modules to scan", len(service_modules))
        scan_service(service_modules)

    # Scan controllers
    logger.info("└---scanning controllers...")
    controller_modules = file_list_func()
    if not controller_modules:
        logger.warning("[WARN] No modules found for controller scanning!")
    else:
        logger.info("└---found %d modules to scan", len(controller_modules))
        scan_controller(controller_modules)

    # Service lifecycle
    logger.info("└---services initialized via ApplicationContext lifecycle...")
    from cullinan.core.services import get_service_registry as get_svc_reg
    from cullinan.core import get_application_context

    service_registry = get_svc_reg()
    service_count = service_registry.count()
    if service_count > 0:
        logger.info(f"└---found {service_count} registered services")
        app_ctx = get_application_context()
        if app_ctx and app_ctx.is_refreshed:
            logger.info(f"[OK] All {service_count} services managed by unified lifecycle")
    else:
        logger.info("└---no services registered")

    # Delegate to gateway-based startup
    from cullinan import run as app_run
    app_run(extra_handlers=handlers)

