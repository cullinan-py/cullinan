# -*- coding: utf-8 -*-
"""Compatibility shim for setuptools-based build entrypoints.

Project metadata now lives in ``pyproject.toml``. This file stays in place so
existing ``python setup.py ...`` workflows can continue to delegate to
setuptools while v0.94 is mid-migration.
"""

from setuptools import __version__ as setuptools_version
from setuptools import setup

_MINIMUM_SETUPTOOLS = (61, 0)


def _setuptools_major_minor(version: str) -> tuple[int, int]:
    parts = version.split(".")
    major = int(parts[0]) if parts and parts[0].isdigit() else 0
    minor = 0
    if len(parts) > 1:
        minor_digits = []
        for char in parts[1]:
            if char.isdigit():
                minor_digits.append(char)
            else:
                break
        if minor_digits:
            minor = int("".join(minor_digits))
    return major, minor


if _setuptools_major_minor(setuptools_version) < _MINIMUM_SETUPTOOLS:
    raise RuntimeError(
        "Cullinan's setup.py compatibility shim requires setuptools>=61. "
        f"Detected setuptools=={setuptools_version}. "
        "Please upgrade setuptools and retry."
    )

if __name__ == "__main__":
    setup()
