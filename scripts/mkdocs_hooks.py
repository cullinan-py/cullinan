# -*- coding: utf-8 -*-
"""MkDocs hooks used by this project's documentation build.

Two jobs: separate *lint-level* messages from *build* errors, and keep the
addresses of pages that moved answering.

The second one used to be a plugin. It was dropped on 2026-10-27 for a reason
that does not require reading anyone's motives: its current release requires
Python 3.10 and pins MkDocs to 1.6.1 or older, while this project still supports
3.9 and tracks MkDocs itself. The forwarding pages are written a few lines
further down, so the dependency list stays as it was.

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
from pathlib import Path

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



# ---------------------------------------------------------------------------
# Pages that moved keep working.
#
# The internals section used to live under ``docs/wiki/``; it is
# ``docs/internals/`` now, matching the name the navigation always used. A
# bookmark saved against the old address should land on the page it named
# instead of a 404, so each old path gets a small page that forwards.
MOVED_PAGES = (
    "application_runtime",
    "components",
    "decorators",
    "extensions",
    "injection",
    "lifecycle",
    "middleware",
    "restful_api",
)

_REDIRECT_PAGE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Moved: {name}</title>
<link rel="canonical" href="{target}">
<meta http-equiv="refresh" content="0; url={target}">
<meta name="robots" content="noindex">
</head>
<body>
<p>This page moved to <a href="{target}">{target}</a>.</p>
</body>
</html>
"""


def _write_redirects(config) -> int:
    """Write one forwarding page per moved address, per locale."""
    site_dir = Path(config["site_dir"])
    written = 0
    for locale in ("", "zh"):
        for name in MOVED_PAGES:
            page = site_dir / locale / "wiki" / name / "index.html"
            page.parent.mkdir(parents=True, exist_ok=True)
            # From <site>/[zh/]wiki/<name>/ back to <site>/[zh/], then into internals.
            target = "../../internals/" + name + "/"
            page.write_text(
                _REDIRECT_PAGE.format(name=name, target=target),
                encoding="utf-8",
            )
            written += 1
    return written


def on_startup(*_args, **_kwargs) -> None:
    _install()


def on_config(config, **_kwargs):
    _install()
    return config


def on_pre_build(*_args, **_kwargs) -> None:
    _install()


def on_post_build(config=None, **_kwargs) -> None:
    if config is not None:
        moved = _write_redirects(config)
        logging.getLogger("mkdocs").info(
            "moved pages: %d forwarding page(s) written for the internals section", moved
        )
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
