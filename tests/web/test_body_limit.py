# -*- coding: utf-8 -*-
"""A ceiling on the request body, enforced before anyone looks at the route.

The audit found the framework would read whatever a client sent: a 1 MiB body
posted to a path that does not exist was fully buffered and only then answered
404. That is an upload endpoint in everything but intent, and it needed no
credentials.

The ceiling is opt-in (``@configure(max_request_body_bytes=...)``), because
changing the default would break every existing upload; what is not optional is
that once you ask for a ceiling, both engines enforce it, and enforce it *while
the client is still sending*.
"""

from __future__ import annotations

import asyncio

import pytest

from cullinan.transport.adapter.asgi_adapter import ASGIAdapter, _read_body
from cullinan.web.gateway.dispatcher import Dispatcher


def _messages(*chunks: bytes):
    """A ``receive`` that yields ``chunks`` then an empty terminating message."""
    queue = [{'body': chunk, 'more_body': True} for chunk in chunks]
    queue.append({'body': b'', 'more_body': False})

    async def receive():
        return queue.pop(0) if queue else {'body': b'', 'more_body': False}

    return receive


def test_the_ceiling_stops_reading_while_the_client_is_still_sending():
    async def main():
        receive = _messages(b'x' * 6, b'y' * 6, b'z' * 6)
        body, too_large = await _read_body(receive, 10)
        return body, too_large

    body, too_large = asyncio.run(main())
    assert too_large is True
    assert len(body) == 12, "reading stopped at the first chunk that crossed the line"


def test_a_body_within_the_ceiling_is_read_whole():
    async def main():
        return await _read_body(_messages(b'abc', b'def'), 100)

    body, too_large = asyncio.run(main())
    assert body == b'abcdef'
    assert too_large is False


def test_no_ceiling_means_read_everything():
    async def main():
        return await _read_body(_messages(b'x' * 5000), None)

    body, too_large = asyncio.run(main())
    assert len(body) == 5000 and too_large is False


def _scope() -> dict:
    return {
        'type': 'http',
        'method': 'POST',
        'path': '/upload',
        'raw_path': b'/upload',
        'headers': [(b'content-type', b'application/octet-stream')],
        'query_string': b'',
        'client': ('127.0.0.1', 1234),
        'server': ('127.0.0.1', 4080),
        'scheme': 'http',
    }


def test_an_oversized_body_is_refused_with_413_before_dispatch(monkeypatch):
    from cullinan.support import config as config_module

    previous = config_module.get_config().max_request_body_bytes
    sent: list[dict] = []

    async def send(message):
        sent.append(message)

    try:
        config_module.configure(max_request_body_bytes=8)
        adapter = ASGIAdapter(Dispatcher())
        asyncio.run(_drive(adapter, _messages(b'x' * 50), send))
    finally:
        config_module.get_config().max_request_body_bytes = previous

    assert sent[0]['status'] == 413
    body = sent[1]['body']
    assert b'Payload Too Large' in body
    headers = {name.decode().lower(): value.decode() for name, value in sent[0]['headers']}
    assert headers['content-length'] == str(len(body)), "the 413 must be framed correctly too"


async def _drive(adapter, receive, send) -> None:
    from cullinan.transport.adapter.asgi_adapter import _handle_http

    await _handle_http(_scope(), receive, send, adapter)


def test_the_configured_ceiling_must_be_a_positive_number():
    from cullinan.support.config import configure

    with pytest.raises(ValueError):
        configure(max_request_body_bytes=0)
