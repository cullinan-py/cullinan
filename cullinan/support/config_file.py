# -*- coding: utf-8 -*-
"""Project configuration read from a file, not from ``.env``.

``.env`` was a compromise: a flat ``KEY=VALUE`` list that has no nesting, no
types, and no way to say "this value comes from somewhere else". It also could
not answer the question a packaged build actually has -- *where does the file
live, and did it end up inside the artefact*.

This module replaces it with one configuration file per application:

    application.json      base values
    application-prod.json the same file for one profile, merged over the base

``.toml``/``.yaml``/``.yml`` are read too when the interpreter or the environment
can parse them; JSON is always available because it is in the standard library,
so no new runtime dependency is introduced.

Three decisions worth stating, because each is a place a config layer usually
gets wrong:

**The file is never looked for inside the installed package.** A packaged build
that shipped its own config would put the operator's settings in the same
artefact as the code -- shadowed by a stale copy, and extractable from the
bundle. Only the working directory and the directory of the launched executable
are searched.

**Secrets are referenced, not stored.** ``${VAR}`` and ``${VAR:default}`` are
resolved from the environment after the file is read, so a file that is committed
or shipped holds a pointer rather than a value.

**A cipher is not provided, and the absence is deliberate.** Real encryption
needs a key, and a key shipped beside the ciphertext is not encryption. If a
deployment must carry encrypted values, it supplies the decryptor -- see
``load_project_config(decryptor=...)`` -- and keeps the key outside the artefact.
"""

from __future__ import annotations

import json
import logging
import os
import re
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, Optional

from cullinan.support.path_utils import get_original_executable_dir

logger = logging.getLogger(__name__)

#: Base name of the configuration file, without extension.
CONFIG_BASENAME = 'application'

#: Environment variable naming an explicit configuration file.
CONFIG_PATH_ENV = 'CULLINAN_CONFIG'

#: Environment variable selecting the profile.
PROFILE_ENV = 'CULLINAN_PROFILE'

#: Extensions tried in order. JSON first: it needs nothing installed.
CONFIG_SUFFIXES = ('.json', '.toml', '.yaml', '.yml')

_PLACEHOLDER = re.compile(r'\$\{([A-Za-z_][A-Za-z0-9_]*)(?::([^}]*))?\}')


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding='utf-8'))


def _read_toml(path: Path) -> Any:
    try:
        import tomllib  # Python 3.11+
    except ModuleNotFoundError:  # pragma: no cover - depends on interpreter
        try:
            import tomli as tomllib  # type: ignore[no-redef]
        except ModuleNotFoundError as exc:
            raise RuntimeError(
                f"{path.name} is TOML, which this interpreter ({os.sys.version_info.major}."
                f"{os.sys.version_info.minor}) cannot parse without 'tomli'. "
                f"Install it, or use a .json file."
            ) from exc
    with path.open('rb') as handle:
        return tomllib.load(handle)


def _read_yaml(path: Path) -> Any:
    try:
        import yaml
    except ModuleNotFoundError as exc:
        raise RuntimeError(
            f"{path.name} is YAML, which needs 'pyyaml'. Install it, or use a .json file."
        ) from exc
    with path.open('r', encoding='utf-8') as handle:
        return yaml.safe_load(handle)


_READERS: Dict[str, Callable[[Path], Any]] = {
    '.json': _read_json,
    '.toml': _read_toml,
    '.yaml': _read_yaml,
    '.yml': _read_yaml,
}


def _merge(base: Dict[str, Any], overlay: Dict[str, Any]) -> Dict[str, Any]:
    """Recursive merge; ``overlay`` wins, and returning a new dict keeps inputs intact."""
    merged = dict(base)
    for key, value in overlay.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def _search_dirs() -> Iterable[Path]:
    """Where the file may be, most specific first.

    The package directory is deliberately absent. Searching it would let a file
    that shipped inside the artefact win over the one the operator placed beside
    the binary -- the same shadowing mistake that made ``find_file_with_fallbacks``
    look in the wrong order.
    """
    seen = set()
    for directory in (Path.cwd(), get_original_executable_dir()):
        try:
            key = directory.resolve()
        except OSError:
            key = directory
        if key in seen:
            continue
        seen.add(key)
        yield directory


def discover_config_file(
    path: Optional[os.PathLike | str] = None,
    profile: Optional[str] = None,
) -> Optional[Path]:
    """Find the configuration file, or return None when the application has none.

    An explicit ``path`` -- argument or ``CULLINAN_CONFIG`` -- is taken as the
    answer. If it does not exist that is an error, not a silent fallback: a
    deployment that named a file and got defaults instead would be harder to
    diagnose than one that stopped.
    """
    explicit = path or os.environ.get(CONFIG_PATH_ENV)
    if explicit:
        candidate = Path(explicit)
        if not candidate.is_file():
            raise FileNotFoundError(
                f"configuration file not found: {candidate} "
                f"(from {'argument' if path else CONFIG_PATH_ENV})"
            )
        return candidate

    active = profile or os.environ.get(PROFILE_ENV) or ''

    # The base file is what discovery returns; the profile is an overlay applied
    # afterwards by load_project_config. Preferring the profile file here looked
    # natural and was wrong: it made the profile the base, so everything the
    # profile did not mention disappeared.
    for directory in _search_dirs():
        for suffix in CONFIG_SUFFIXES:
            candidate = directory / f'{CONFIG_BASENAME}{suffix}'
            if candidate.is_file():
                return candidate

    # A deployment may ship only the profile file. That is a base of its own.
    if active:
        for directory in _search_dirs():
            for suffix in CONFIG_SUFFIXES:
                candidate = directory / f'{CONFIG_BASENAME}-{active}{suffix}'
                if candidate.is_file():
                    logger.debug(f"Only a profiled configuration exists: {candidate}")
                    return candidate

    return None


def _profile_file_for(base: Path, profile: str) -> Optional[Path]:
    """The profile overlay beside ``base``, in the same directory and extension."""
    candidate = base.with_name(f'{CONFIG_BASENAME}-{profile}{base.suffix}')
    return candidate if candidate.is_file() else None


def _resolve_placeholders(value: Any, source: str) -> Any:
    """Expand ``${VAR}`` / ``${VAR:default}`` in strings, recursively.

    A placeholder with no value and no default is an error rather than an empty
    string: silently substituting "" turns a missing setting into a value that
    looks configured.
    """
    if isinstance(value, dict):
        return {k: _resolve_placeholders(v, source) for k, v in value.items()}
    if isinstance(value, list):
        return [_resolve_placeholders(item, source) for item in value]
    if not isinstance(value, str):
        return value

    def replace(match: 're.Match[str]') -> str:
        name, default = match.group(1), match.group(2)
        if name in os.environ:
            return os.environ[name]
        if default is not None:
            return default
        raise KeyError(
            f"{source}: ${{{name}}} has no value in the environment and no default"
        )

    return _PLACEHOLDER.sub(replace, value)


def load_project_config(
    path: Optional[os.PathLike | str] = None,
    profile: Optional[str] = None,
    decryptor: Optional[Callable[[str], Any]] = None,
) -> Dict[str, Any]:
    """Read the project configuration file and return it as a dict.

    Args:
        path: Explicit file. Falls back to ``CULLINAN_CONFIG``, then discovery.
        profile: Profile name. Falls back to ``CULLINAN_PROFILE``.
            ``application-<profile>.*`` is merged over ``application.*``.
        decryptor: Optional callable applied to string values wrapped as
            ``{"encrypted": "<payload>"}``. The key is the deployer's problem, on
            purpose -- see the module docstring.

    Returns:
        dict: Merged configuration; empty when no file exists.
    """
    base = discover_config_file(path, profile)
    if base is None:
        return {}

    reader = _READERS.get(base.suffix.lower())
    if reader is None:
        raise RuntimeError(
            f"unsupported configuration file {base.name}; use one of "
            f"{', '.join(CONFIG_SUFFIXES)}"
        )

    data = reader(base) or {}
    if not isinstance(data, dict):
        raise RuntimeError(f"{base.name}: the top level must be an object, got {type(data).__name__}")

    documents = [(base, data)]
    active = profile or os.environ.get(PROFILE_ENV) or ''
    if active:
        overlay_path = _profile_file_for(base, active)
        if overlay_path is not None:
            overlay = _READERS[overlay_path.suffix.lower()](overlay_path) or {}
            documents.append((overlay_path, overlay))
            logger.debug(f"Configuration profile '{active}' applied from {overlay_path}")

    merged: Dict[str, Any] = {}
    for document_path, document in documents:
        merged = _merge(merged, _resolve_placeholders(document, document_path.name))

    if decryptor is not None:
        merged = _apply_decryptor(merged, decryptor)

    logger.info("Configuration loaded from %s", base)
    return merged


def _apply_decryptor(value: Any, decryptor: Callable[[str], Any]) -> Any:
    if isinstance(value, dict):
        if set(value) == {'encrypted'}:
            return decryptor(str(value['encrypted']))
        return {k: _apply_decryptor(v, decryptor) for k, v in value.items()}
    if isinstance(value, list):
        return [_apply_decryptor(item, decryptor) for item in value]
    return value


def apply_project_config(
    path: Optional[os.PathLike | str] = None,
    profile: Optional[str] = None,
    decryptor: Optional[Callable[[str], Any]] = None,
) -> Dict[str, Any]:
    """Load the file and fold it into the global configuration.

    Values written in code -- ``configure(...)`` -- still win, because this runs
    before them and they overwrite what they name. Environment variables win over
    both, because they are read at use time.

    Returns:
        dict: What was loaded, so a caller can log or assert on it.
    """
    from cullinan.support.config import get_config

    data = load_project_config(path=path, profile=profile, decryptor=decryptor)
    if data:
        get_config().from_dict(data)
    return data
