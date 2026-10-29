# -*- coding: utf-8 -*-
"""Path utilities for different packaging environments.

Provides cross-platform path resolution for:
- Development environment (direct Python execution)
- Nuitka compiled applications (standalone/onefile)
- PyInstaller frozen applications (onefile/onedir)

This module ensures that file paths are correctly resolved regardless of
how the application is packaged and deployed.
"""

import os
import sys
import logging
from pathlib import Path
from typing import Optional, Union

logger = logging.getLogger(__name__)


# =============================================================================
# Packaging Environment Detection
# =============================================================================

_ONEFILE_ENV_MARKERS = (
    'NUITKA_ONEFILE_PARENT',
    'NUITKA_ONEFILE_BINARY',
    'NUITKA_ONEFILE_TEMP',
)


def _is_within(child: Path, parent: Path) -> bool:
    """Whether ``child`` sits inside ``parent``; false when either cannot be resolved."""
    try:
        child = Path(child).resolve()
        parent = Path(parent).resolve()
    except OSError:
        return False
    if child == parent:
        return True
    try:
        return child.is_relative_to(parent)
    except AttributeError:  # pragma: no cover - Python < 3.9
        return parent in child.parents


def _nuitka_evidence() -> tuple[bool, str]:
    """``(is_nuitka, evidence)`` -- and the evidence string is part of the contract.

    A single ``sys.frozen`` check cannot answer this. Nuitka does not set it in
    every mode, and when it is absent the whole packaging branch becomes
    unreachable rather than merely wrong. So several independent markers are
    tried, and whichever one fires is reported: "why do you think this is
    compiled?" is the first question anyone asks when the paths look wrong.

    The module-global marker only exists when *this* file was compiled, which is
    the normal case for ``--include-package=cullinan`` but not guaranteed; the
    environment markers cover the case where it was not.
    """
    if '__compiled__' in globals():
        return True, "module global '__compiled__'"
    if hasattr(sys, '__compiled__'):
        return True, "sys.__compiled__"
    for name in _ONEFILE_ENV_MARKERS:
        if os.environ.get(name):
            return True, f"env {name}={os.environ.get(name)!r}"
    if getattr(sys, 'frozen', False) and not hasattr(sys, '_MEIPASS'):
        return True, "sys.frozen without sys._MEIPASS"
    return False, ""


def _onefile_evidence() -> tuple[bool, str]:
    """``(is_onefile, evidence)`` for either packer, without reading path strings.

    ``'onefile' in path`` was the old test. It works only while the extraction
    directory happens to be named that way, which is an implementation detail of
    the packer rather than something the program controls. What actually
    distinguishes onefile is behavioural: the binary being executed is a copy
    unpacked next to the code, so the running executable is not the one the user
    launched.
    """
    for name in ('NUITKA_ONEFILE_PARENT', 'NUITKA_ONEFILE_TEMP'):
        if os.environ.get(name):
            return True, f"env {name}"
    if hasattr(sys, '_MEIPASS'):
        return True, "sys._MEIPASS"

    launched = sys.argv[0] if sys.argv else ''
    if launched:
        launched_dir = Path(launched).absolute().parent
        exe_dir = Path(sys.executable).absolute().parent
        if launched_dir != exe_dir and _is_within(exe_dir, get_base_path()):
            return True, f"running executable {exe_dir} is unpacked inside the code directory"
    return False, ""


def is_frozen() -> bool:
    """Check if running in any frozen/packaged environment.

    Returns:
        bool: True if frozen (Nuitka/PyInstaller), False in development
    """
    return (
        bool(getattr(sys, 'frozen', False))
        or hasattr(sys, '_MEIPASS')
        or _nuitka_evidence()[0]
    )


def is_pyinstaller_frozen() -> bool:
    """Check if running in PyInstaller frozen environment.

    Returns:
        bool: True if PyInstaller frozen, False otherwise
    """
    return hasattr(sys, '_MEIPASS')


def is_nuitka_compiled() -> bool:
    """Check if running in Nuitka compiled environment.

    Deliberately independent of :func:`is_frozen`. The previous version ended
    with ``is_frozen() and not hasattr(sys, '_MEIPASS')``, which made this
    function ask itself the question it was supposed to answer -- and, because
    ``get_packaging_mode`` returned early on ``not is_frozen()``, it was never
    even called in the case that mattered.

    Returns:
        bool: True if Nuitka compiled, False otherwise
    """
    return _nuitka_evidence()[0]


def get_packaging_mode() -> str:
    """Get current packaging mode.

    Order matters: the specific packers are asked first, and ``development`` is
    the answer only when nothing claims the process. The old version decided
    ``development`` from a single flag before any packer was consulted, so a
    packer that does not set that flag was indistinguishable from plain Python.

    Returns:
        str: 'development', 'nuitka_onefile', 'nuitka_standalone',
             'pyinstaller_onefile', 'pyinstaller_onedir'
    """
    if is_pyinstaller_frozen():
        return 'pyinstaller_onefile' if _onefile_evidence()[0] else 'pyinstaller_onedir'

    if is_nuitka_compiled():
        return 'nuitka_onefile' if _onefile_evidence()[0] else 'nuitka_standalone'

    if is_frozen():
        return 'unknown'

    return 'development'


# =============================================================================
# Base Path Resolution
# =============================================================================

def get_base_path() -> Path:
    """Get application base path, supporting all packaging modes.

    Returns the directory containing the application code:
    - Development: Project root directory
    - PyInstaller onefile: sys._MEIPASS (temporary extraction directory)
    - PyInstaller onedir: Directory containing the executable
    - Nuitka onefile: Temporary extraction directory
    - Nuitka standalone: Directory containing the executable

    Returns:
        Path: Absolute path to application base directory
    """
    if is_pyinstaller_frozen():
        # PyInstaller extracts to sys._MEIPASS
        base = Path(getattr(sys, '_MEIPASS', os.path.dirname(sys.executable)))
        logger.debug(f"Base path (PyInstaller): {base}")
        return base

    if is_nuitka_compiled():
        # Onefile and standalone answer the same way here, and the reason is the
        # point: this function reports where the *code* is. In onefile the packer
        # unpacked it next to the running executable (a temp directory, correctly);
        # in standalone it sits beside the executable too. The location that must
        # survive restarts is a different question -- see get_original_executable_dir.
        base = Path(sys.executable).resolve().parent
        logger.debug(f"Base path (Nuitka): {base}")
        return base

    # Development mode: path_utils now lives under cullinan/support/.
    # Go up two levels to reach the project root.
    base = Path(__file__).parent.parent.parent
    logger.debug(f"Base path (development): {base}")
    return base


def get_cullinan_package_path() -> Path:
    """Get the path to the cullinan package directory.

    Returns:
        Path: Absolute path to cullinan package
    """
    if is_frozen():
        # In frozen mode, cullinan is extracted to base_path/cullinan
        base = get_base_path()
        cullinan_path = base / 'cullinan'

        # Fallback: if not found in base_path/cullinan, try base_path directly
        # (some packaging configurations may flatten the structure)
        if not cullinan_path.exists():
            cullinan_path = base

        logger.debug(f"Cullinan package path (frozen): {cullinan_path}")
        return cullinan_path

    # Development mode: path_utils now lives under cullinan/support/.
    # Go up one level to reach the cullinan package root.
    cullinan_path = Path(__file__).parent.parent
    logger.debug(f"Cullinan package path (development): {cullinan_path}")
    return cullinan_path


def get_resource_path(relative_path: Union[str, Path]) -> Path:
    """Get absolute path to a resource file.

    Args:
        relative_path: Relative path from base directory

    Returns:
        Path: Absolute path to resource

    Example:
        >>> get_resource_path('config.yaml')
        Path('C:/app/config.yaml')
        >>> get_resource_path('templates/index.html')
        Path('C:/app/templates/index.html')
    """
    base = get_base_path()
    resource = base / relative_path
    logger.debug(f"Resource path for '{relative_path}': {resource}")
    return resource


def get_module_file_path(module_name: str, relative_to_cullinan: bool = True) -> Optional[Path]:
    """Get file path for a module within the cullinan package.

    Args:
        module_name: Module filename (e.g., 'controller.py', 'config.py')
        relative_to_cullinan: If True, resolve relative to cullinan package

    Returns:
        Path: Absolute path to module file, or None if not found

    Example:
        >>> get_module_file_path('controller.py')
        Path('C:/app/cullinan/controller.py')
    """
    if relative_to_cullinan:
        base = get_cullinan_package_path()
    else:
        base = get_base_path()

    module_path = base / module_name

    if module_path.exists():
        logger.debug(f"Found module file: {module_path}")
        return module_path

    logger.debug(f"Module file not found: {module_path}")
    return None


def get_original_executable_dir() -> Path:
    """Directory of the executable the user actually launched.

    In onefile the process runs an unpacked copy, so ``sys.executable`` points
    into a temp directory that is deleted on exit. Anything that has to survive a
    restart -- logs, a config file beside the binary, cached data -- cannot be
    derived from it, and a path derived that way looks plausible right up until
    the file is gone.

    ``sys.argv[0]`` is not automatically the answer either: a launcher may rewrite
    it to the unpacked path as well. So candidates are accepted only after
    checking that they are *not* inside the code directory, and the winner is
    logged -- a wrong guess should be visible in the startup log rather than
    discovered when the logs are missing.

    Order: ``APP_EXE_DIR`` (explicit override) -> ``NUITKA_ONEFILE_BINARY`` ->
    ``sys.argv[0]`` -> ``sys.executable`` -> working directory, with a warning.

    Returns:
        Path: Directory containing the launched executable
    """
    override = os.environ.get('APP_EXE_DIR')
    if override:
        logger.debug(f"Original executable directory (APP_EXE_DIR): {override}")
        return Path(override)

    unpacked = get_base_path()
    candidates: list[tuple[str, Path]] = []

    onefile_binary = os.environ.get('NUITKA_ONEFILE_BINARY')
    if onefile_binary:
        candidates.append(('NUITKA_ONEFILE_BINARY', Path(onefile_binary).absolute().parent))
    if sys.argv and sys.argv[0]:
        candidates.append(('sys.argv[0]', Path(sys.argv[0]).absolute().parent))
    if sys.executable:
        candidates.append(('sys.executable', Path(sys.executable).absolute().parent))

    for label, candidate in candidates:
        if _is_within(candidate, unpacked):
            logger.debug(f"Ignoring {label} ({candidate}): it is inside the code directory")
            continue
        logger.debug(f"Original executable directory ({label}): {candidate}")
        return candidate

    fallback = Path.cwd()
    logger.warning(
        "Could not locate the directory the executable was launched from "
        f"(packaging mode: {get_packaging_mode()}). Falling back to the working "
        f"directory {fallback}; set APP_EXE_DIR to make this explicit."
    )
    return fallback


def get_executable_dir() -> Path:
    """Get directory containing the executable or main script.

    Under a packer this is the directory of the executable the user launched, not
    the unpacked copy -- see :func:`get_original_executable_dir` for why that
    distinction matters.

    Returns:
        Path: Directory containing executable (frozen) or main script (development)
    """
    if is_frozen():
        return get_original_executable_dir()

    # Development: return directory of main script
    main_file = sys.argv[0] if sys.argv else __file__
    exe_dir = Path(main_file).parent.resolve()
    logger.debug(f"Executable directory (development): {exe_dir}")
    return exe_dir


def get_user_data_dir() -> Path:
    """Get directory for user data (logs, config, cache).

    This directory is outside the application bundle and persists across updates.

    Under a packer the answer is never the unpacked directory: it is deleted when
    the process exits, so anything written there disappears exactly when someone
    needs it. When no persistent location can be established the working directory
    is returned **with a warning** -- the silent temp path was the old failure.

    Returns:
        Path: User data directory
    """
    data_dir = os.environ.get('APP_DATA_DIR')
    if data_dir:
        return Path(data_dir)

    if is_frozen():
        resolved = get_original_executable_dir()
        unpacked = get_base_path()
        if not _is_within(resolved, unpacked):
            return resolved
        fallback = Path.cwd()
        logger.warning(
            "frozen application: no persistent data directory found, falling back to "
            f"{fallback}. Data written here may not survive a restart. Set APP_DATA_DIR "
            "to choose the location explicitly."
        )
        return fallback

    # Development: use current working directory
    return Path.cwd()


# =============================================================================
# Path Resolution with Fallbacks
# =============================================================================

def find_file_with_fallbacks(filename: str, search_paths: list[Path] = None) -> Optional[Path]:
    """Find a file by searching multiple paths with fallbacks.

    Args:
        filename: Name of file to find
        search_paths: List of paths to search (default: smart defaults)

    Returns:
        Path: First existing path, or None if not found
    """
    if search_paths is None:
        # Ordered by where a user would actually put a file. The two places a
        # person controls -- beside the executable they launched, and the
        # directory they started it from -- come first; the unpacked code
        # directory is where the packer put things, and the package directory is
        # the last resort. Leading with the unpacked directory (as this used to)
        # means a stale copy inside the bundle wins over the config next to the
        # binary.
        search_paths = [
            get_original_executable_dir(),
            Path.cwd(),
            get_base_path(),
            get_cullinan_package_path(),
        ]

    for search_path in search_paths:
        candidate = search_path / filename
        if candidate.exists():
            logger.debug(f"Found '{filename}' at: {candidate}")
            return candidate

    logger.warning(f"File '{filename}' not found in any search path")
    return None


# =============================================================================
# Module Import Utilities
# =============================================================================

def import_module_from_path(module_name: str, file_path: Path):
    """Import a module from a specific file path.

    Args:
        module_name: Name to register module as
        file_path: Absolute path to module file

    Returns:
        module: Imported module object

    Raises:
        ImportError: If module cannot be loaded
    """
    import importlib.util

    if not file_path.exists():
        raise ImportError(f"Module file not found: {file_path}")

    spec = importlib.util.spec_from_file_location(module_name, file_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot create spec for module: {module_name}")

    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module  # Register in sys.modules
    spec.loader.exec_module(module)

    logger.debug(f"Imported module '{module_name}' from {file_path}")
    return module


# =============================================================================
# Debug and Diagnostics
# =============================================================================

def get_path_info() -> dict:
    """Get diagnostic information about current path configuration.

    Returns:
        dict: Path configuration details
    """
    return {
        'packaging_mode': get_packaging_mode(),
        'is_frozen': is_frozen(),
        'is_pyinstaller': is_pyinstaller_frozen(),
        'is_nuitka': is_nuitka_compiled(),
        'detection_evidence': _nuitka_evidence()[1] or 'not compiled',
        'onefile_evidence': _onefile_evidence()[1] or 'not packed as onefile',
        'is_onefile': _onefile_evidence()[0],
        'base_path': str(get_base_path()),
        'cullinan_package_path': str(get_cullinan_package_path()),
        'executable_dir': str(get_executable_dir()),
        'original_executable_dir': str(get_original_executable_dir()),
        'user_data_dir': str(get_user_data_dir()),
        'cwd': str(Path.cwd()),
        'sys.executable': sys.executable,
        'sys.argv[0]': sys.argv[0] if sys.argv else 'N/A',
        'sys.frozen': getattr(sys, 'frozen', False),
        'sys._MEIPASS': getattr(sys, '_MEIPASS', 'N/A'),
        '__file__': __file__ if not is_frozen() else 'N/A',
    }


def log_path_info():
    """Log diagnostic information about current path configuration."""
    info = get_path_info()
    logger.info("=" * 70)
    logger.info("Path Configuration Diagnostics")
    logger.info("=" * 70)
    for key, value in info.items():
        logger.info(f"  {key:25s}: {value}")
    logger.info("=" * 70)


# =============================================================================
# Initialization
# =============================================================================

# One line at import, so the packaging decision reaches the startup log of a
# deployed build. Debug in development, where it is noise; INFO when packaged,
# because "which mode did it think it was in" is the first question anyone asks
# when a path looks wrong -- and previously that answer was invisible in
# production while the wrong path was not.
_packaging_mode = get_packaging_mode()
if _packaging_mode == 'development':
    logger.debug("Packaging mode: development")
else:
    logger.info(
        "Packaging mode: %s (%s); code=%s executable=%s data=%s",
        _packaging_mode,
        _nuitka_evidence()[1] or _onefile_evidence()[1] or 'unknown',
        get_base_path(),
        get_executable_dir(),
        get_user_data_dir(),
    )
