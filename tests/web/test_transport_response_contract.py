# -*- coding: utf-8 -*-
"""The bytes on the wire, held to the protocol.

Each case here is a defect that reached a real client before it reached a test,
so the assertions are about what a client observes, not about which branch ran:

* a 204 that carried ``content-length: 0`` (not allowed, and some proxies say so);
* a response with two ``Content-Length`` headers (``15`` and ``0``), which made
  a HEAD request for a static file hang and then fail with
  ``ASGI callable returned without completing response``;
* a Tornado-only ``ETag``, which turned the same request into a ``304`` on one
  engine and left it ``200`` on the other.
"""

from __future__ import annotations

import asyncio

from cullinan.transport.adapter.asgi_adapter import _send_error_body, _send_response
from cullinan.transport.adapter.tornado_adapter import _CullinanTornadoHandler
from cullinan.web.gateway.web_core import WebResponse


def _headers_of(response: WebResponse) -> list[tuple[str, str]]:
    captured: list[dict] = []

    async def send(message: dict) -> None:
        captured.append(message)

    asyncio.run(_send_response(send, response, []))
    start = captured[0]
    return [(name.decode("latin-1").lower(), value.decode("latin-1")) for name, value in start["headers"]]


def test_no_content_does_not_advertise_a_content_length():
    headers = _headers_of(WebResponse(status_code=204))
    assert [name for name, _ in headers if name == "content-length"] == [], (
        "a 204 has no body, so Content-Length is not allowed (RFC 9110 8.6); "
        "sending 0 makes strict proxies reject the response"
    )


def test_not_modified_does_not_advertise_a_content_length():
    headers = _headers_of(WebResponse(status_code=304))
    assert [name for name, _ in headers if name == "content-length"] == []


def test_an_explicit_content_length_is_not_appended_again():
    response = WebResponse.json({"ok": True})
    response.set_header("Content-Length", "5")
    headers = _headers_of(response)
    values = [value for name, value in headers if name == "content-length"]
    assert values == ["5"], f"expected exactly one Content-Length, got {values}"


def test_head_of_a_larger_representation_keeps_its_declared_size():
    """A HEAD answer announces the size a GET would return, with no body."""
    response = WebResponse(body=b"", status_code=200)
    response.set_header("Content-Length", "15")
    headers = _headers_of(response)
    values = [value for name, value in headers if name == "content-length"]
    assert values == ["15"], (
        "the declared size of the representation must survive; appending the "
        f"actual body length produced a conflicting second header: {values}"
    )


def test_a_plain_response_still_gets_a_content_length():
    headers = _headers_of(WebResponse.json({"ok": True}))
    values = [value for name, value in headers if name == "content-length"]
    assert len(values) == 1 and int(values[0]) > 0


def test_tornado_does_not_invent_an_etag():
    """The ASGI path cannot produce one, so neither may this one."""
    assert "set_etag_header" in _CullinanTornadoHandler.__dict__, (
        "Tornado would otherwise compute an ETag on finish() and answer 304 to "
        "If-None-Match, while the same request on ASGI stays 200"
    )


def test_tornado_etag_override_does_not_touch_headers():
    """Calling it must leave the header map alone.

    Tornado's version computes a hash from the response body; if this override
    were ever dropped, that call would need a real handler. On a bare object it
    would raise -- so an empty mapping afterwards proves nothing was computed.
    """

    class _Bare:
        _headers: dict = {}

    instance = _Bare()
    _CullinanTornadoHandler.set_etag_header(instance)
    assert instance._headers == {}


def test_the_draining_error_body_is_a_complete_response():
    """503 must be sendable as-is: status, body and a length that matches it."""
    captured: list[dict] = []

    async def send(message: dict) -> None:
        captured.append(message)

    body = b'{"error":"Service Unavailable"}'
    asyncio.run(_send_error_body(send, 503, body, extra_headers=[[b'retry-after', b'1']]))
    start = captured[0]
    headers = {name.decode().lower(): value.decode() for name, value in start["headers"]}
    assert start["status"] == 503
    assert headers["content-length"] == str(len(body))
    assert headers["retry-after"] == "1"
    assert captured[1]["body"] == body


def test_a_draining_rejection_maps_to_503_not_500():
    from cullinan.core.exceptions import ContainerDrainingError
    from cullinan.web.gateway.exception_handler import ExceptionHandler
    from cullinan.web.gateway.web_core import WebRequest

    handler = ExceptionHandler()
    response = asyncio.run(handler.handle(WebRequest(method="GET", path="/ops/ready"), ContainerDrainingError("draining")))
    assert response.status_code == 503
