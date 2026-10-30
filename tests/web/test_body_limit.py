# -*- coding: utf-8 -*-
"""A ceiling on the request body, enforced before anyone looks at the route.

The framework used to read whatever a client sent: a 1 MiB body posted to a
path that does not exist was fully buffered and only then answered 404. That is
an upload endpoint in everything but intent, and it needed no credentials.

The ceiling is opt-in (``@configure(max_request_body_bytes=...)``), because
changing the default would break every existing upload; what is not optional is
that once you ask for a ceiling, both engines stop reading at the limit. What the
client sees differs: the ASGI adapter answers `413`, while Tornado refuses at its
own protocol layer with `400` before the framework is involved.

This file holds the unit-level wiring (the ceiling reaches the adapter, and it
reaches Tornado's `HTTPServer`). What a *client* observes on Tornado -- including
the cases where no status line arrives at all -- is measured against a live server
in ``tests/integration/test_tornado_client_view_of_an_oversized_body.py``. The
split is deliberate: "measured" belongs to the file that runs a socket, not to the
one that asserts a keyword argument.
"""

from __future__ import annotations

import asyncio

import pytest

from cullinan.transport.adapter.asgi_adapter import ASGIAdapter, _handle_http, _read_body
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
    # A dict would fold a duplicate Content-Length and hide exactly the defect
    # this asserts against, so count the pairs as they are.
    pairs = [(name.decode().lower(), value.decode()) for name, value in sent[0]['headers']]
    lengths = [value for name, value in pairs if name == 'content-length']
    assert lengths == [str(len(body))], f"the 413 must carry exactly one Content-Length, got {lengths}"


async def _drive(adapter, receive, send) -> None:
    from cullinan.transport.adapter.asgi_adapter import _handle_http

    await _handle_http(_scope(), receive, send, adapter)


def test_the_configured_ceiling_must_be_a_positive_number():
    from cullinan.support.config import configure

    with pytest.raises(ValueError):
        configure(max_request_body_bytes=0)


# ---------------------------------------------------------------------------
# A declared size is refused before the body is read.
#
# What a client observes used to depend on how fast it sent: reading until the
# limit was crossed answered a slow client only once it stopped writing, and a
# client that never stops writing was never answered at all. `Content-Length`
# arrives with the headers, so a body that declares itself too large can be
# refused at the first byte -- the proof below is a `receive` that never returns:
# if the implementation still reads, the case hangs instead of answering.
# ---------------------------------------------------------------------------


def _scope_with(*headers: tuple[bytes, bytes]) -> dict:
    scope = _scope()
    scope["headers"] = list(headers)
    return scope


async def _never_receives(counter: list) -> dict:
    """A ``receive`` that records the call and then never returns.

    Returning a body would let a reading implementation pass by accident; hanging
    is the state the ceiling exists to prevent, so that is what it is modelled as.
    """
    counter.append(1)
    await asyncio.Event().wait()
    return {"body": b"", "more_body": False}


def test_a_declared_oversize_body_is_refused_without_reading_it(monkeypatch):
    from cullinan.support import config as config_module

    previous = config_module.get_config().max_request_body_bytes
    sent: list[dict] = []
    receives: list[int] = []

    async def send(message):
        sent.append(message)

    async def drive():
        adapter = ASGIAdapter(Dispatcher())
        await asyncio.wait_for(
            _handle_http(
                _scope_with((b"content-length", b"4096")),
                lambda: _never_receives(receives),
                send,
                adapter,
            ),
            timeout=2.0,
        )

    try:
        config_module.configure(max_request_body_bytes=8)
        asyncio.run(drive())
    finally:
        config_module.get_config().max_request_body_bytes = previous

    assert not receives, (
        "the body was read even though Content-Length said it was over the ceiling; "
        "a client that sends slowly would still have been left waiting"
    )
    assert sent and sent[0]["status"] == 413, f"expected an immediate 413, got {sent[:1]}"
    pairs = [(name.decode().lower(), value.decode()) for name, value in sent[0]["headers"]]
    lengths = [value for name, value in pairs if name == "content-length"]
    assert lengths == [str(len(sent[1]["body"]))], (
        f"the early 413 must carry exactly one Content-Length, got {lengths}"
    )


def test_a_declared_size_within_the_ceiling_is_still_read(monkeypatch):
    from cullinan.support import config as config_module

    previous = config_module.get_config().max_request_body_bytes
    sent: list[dict] = []
    receives: list[int] = []

    async def send(message):
        sent.append(message)

    async def receive():
        receives.append(1)
        if len(receives) == 1:
            return {"body": b"hello", "more_body": False}
        return {"body": b"", "more_body": False}

    async def drive():
        adapter = ASGIAdapter(Dispatcher())
        await _handle_http(_scope_with((b"content-length", b"5")), receive, send, adapter)

    try:
        config_module.configure(max_request_body_bytes=8)
        asyncio.run(drive())
    finally:
        config_module.get_config().max_request_body_bytes = previous

    assert receives, "a body inside the ceiling must still be read"
    assert sent[0]["status"] != 413


def test_a_chunked_request_is_stopped_when_the_received_size_crosses_the_ceiling(monkeypatch):
    """No declaration, so the only evidence is the bytes themselves.

    The behaviour here must not change: read until the limit is crossed, then
    answer. A chunked body that declares nothing cannot be refused earlier without
    guessing.
    """
    from cullinan.support import config as config_module

    previous = config_module.get_config().max_request_body_bytes
    sent: list[dict] = []

    async def send(message):
        sent.append(message)

    async def drive():
        adapter = ASGIAdapter(Dispatcher())
        await _handle_http(
            _scope_with((b"transfer-encoding", b"chunked")),
            _messages(b"x" * 6, b"y" * 6),
            send,
            adapter,
        )

    try:
        config_module.configure(max_request_body_bytes=8)
        asyncio.run(drive())
    finally:
        config_module.get_config().max_request_body_bytes = previous

    assert sent[0]["status"] == 413


def test_a_content_length_that_is_not_a_number_is_not_evidence(monkeypatch):
    """An unreadable declaration must not be treated as "over the ceiling"."""
    from cullinan.transport.adapter.asgi_adapter import _declared_content_length

    assert _declared_content_length(_scope_with((b"content-length", b"not-a-number"))) is None
    assert _declared_content_length(_scope_with((b"content-length", b"12"))) == 12
    assert _declared_content_length(_scope_with((b"transfer-encoding", b"chunked"))) is None
    assert _declared_content_length(_scope()) is None


def test_tornado_is_told_the_ceiling_so_it_can_stop_reading(monkeypatch):
    """The handler-level check cannot stop a body Tornado has already buffered.

    Without ``max_body_size`` on its ``HTTPServer``, Tornado reads the whole body
    and only then hands it over, so the adapter's 413 would fire after the cost
    had already been paid — and a client that never finishes sending would never
    get an answer at all.
    """
    from cullinan.support import config as config_module
    from cullinan.transport.adapter.tornado_adapter import server_options

    previous = config_module.get_config().max_request_body_bytes
    try:
        config_module.get_config().max_request_body_bytes = None
        assert server_options() == {}, "no ceiling must not invent one"

        config_module.configure(max_request_body_bytes=256)
        assert server_options() == {"max_body_size": 256}
    finally:
        config_module.get_config().max_request_body_bytes = previous


def test_the_tornado_server_is_actually_told_the_ceiling(monkeypatch):
    """Assert the call site, not just the helper.

    An earlier version called ``server_options()`` in a test but passed nothing
    at the real call site; deleting the wiring left the whole suite green, and
    only a slow upload against a live server showed the regression. This asserts
    the keyword actually reaches ``HTTPServer``.
    """
    import tornado.httpserver as http_server_module

    from cullinan.support import config as config_module
    from cullinan.transport.adapter.tornado_adapter import TornadoAdapter

    captured: dict = {}

    class _FakeServer:
        def __init__(self, app, **kwargs):
            captured['app'] = app
            captured['kwargs'] = kwargs

    monkeypatch.setattr(http_server_module, 'HTTPServer', _FakeServer)

    previous = config_module.get_config().max_request_body_bytes
    try:
        config_module.configure(max_request_body_bytes=512)
        adapter = TornadoAdapter.__new__(TornadoAdapter)  # skip the constructor's dependencies
        adapter._app = object()
        adapter._create_http_server()
    finally:
        config_module.get_config().max_request_body_bytes = previous

    assert captured['kwargs'] == {'max_body_size': 512}, (
        "the ceiling never reached HTTPServer; Tornado would buffer the whole body "
        "before the adapter could reject it"
    )
