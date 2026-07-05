# -*- coding: utf-8 -*-
"""Compatibility shim for setuptools-based build entrypoints.

Project metadata now lives in ``pyproject.toml``. This file stays in place so
existing ``python setup.py ...`` workflows can continue to delegate to
setuptools while v0.94 is mid-migration.
"""

from setuptools import setup


if __name__ == "__main__":
    setup()
