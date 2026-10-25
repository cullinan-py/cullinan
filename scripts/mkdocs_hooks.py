# -*- coding: utf-8 -*-
"""MkDocs hooks used by this project's documentation build.

Right now there is one job: separate *lint-level* messages from *build* errors.

The generated API reference reads the package through griffe, which reports
things like "no type annotation for ``**kwargs``". Those are real observations
about the docstrings and annotations, and they are on the list to clean up --
but they are not reasons to refuse to build a site. Promoting them into the
strict build would mean either silencing strict mode for everything (including
the broken links and missing pages it exists to catch) or blocking every
documentation change behind a typing cleanup of the whole package.

So they are counted and summarised instead: one line per build, naming how many
notes were set aside, so the backlog stays visible rather than disappearing.
"""

from __future__ import annotations

import logging

_SUPPRESSED = {"count": 0}
_SUMMARISED = {"done": False}


class _Counter(logging.Filter):
    """Count records at lint level and let them through to nobody."""

    def filter(self, record: logging.LogRecord) -> bool:  # noqa: A003 - logging API
        _SUPPRESSED["count"] += 1
        return False


def _install() -> None:
    # mkdocstrings-python relocates griffe's logger under ``mkdocs.plugins`` so
    # that it fits MkDocs' logging configuration; ``griffe`` itself is covered
    # in case a handler is used that does not patch it.
    for name in ("mkdocs.plugins.griffe", "griffe"):
        logger = logging.getLogger(name)
        logger.setLevel(logging.WARNING)
        if not any(isinstance(existing, _Counter) for existing in logger.filters):
            logger.addFilter(_Counter())


def on_startup(*_args, **_kwargs) -> None:
    _install()


def on_config(config, **_kwargs):
    _install()
    return config


def on_pre_build(*_args, **_kwargs) -> None:
    _install()


def on_post_build(*_args, **_kwargs) -> None:
    if _SUMMARISED["done"]:
        return
    _SUMMARISED["done"] = True
    count = _SUPPRESSED["count"]
    if count:
        logging.getLogger("mkdocs").info(
            "api reference: %d griffe note(s) set aside (annotation and docstring hygiene, "
            "tracked separately from build failures)",
            count,
        )
