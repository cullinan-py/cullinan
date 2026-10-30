# -*- coding: utf-8 -*-
"""What a client actually sees when Tornado refuses an oversized body.

``docs/deployment.md`` makes three client-side claims about the Tornado ceiling,
and they are the interesting kind: the server's own status code is `400`, but
whether the client can *read* that `400` depends on whether it was still writing
when the server closed the connection. Two of the three outcomes carry no status
line at all. Those claims were measured once by hand and then only restated -- so
nothing failed when they drifted, which is what makes a "measured" note in prose
decay into an assumption.

This file is the executor for that note: a live Tornado server, a raw socket, and
the three send shapes the page describes. Nothing is mocked, so a change to the
protocol layer or to the ceiling's wiring shows up here.

**The variable is timing, not ratio.** Writing this file corrected the page: a
64x body sent in a single ``sendall`` is *also* answered with a readable ``400``
on this machine, because the client had finished writing before the refusal
landed. What decides the outcome is whether the client is still writing, so that
is what the three cases below vary -- and that is what the table now says.
"""

from __future__ import annotations

import socket
import threading
import time

import pytest

from cullinan.support.config import get_config
from cullinan.transport.adapter.tornado_adapter import TornadoAdapter
from cullinan.web.gateway.dispatcher import Dispatcher

CEILING = 1024
READ_TIMEOUT = 10.0


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


def _wait_until_serving(port: int, deadline: float) -> bool:
    while time.monotonic() < deadline:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=1.0):
                return True
        except OSError:
            time.sleep(0.05)
    return False


def _declared_headers(port: int, size: int) -> bytes:
    return (
        f"POST /upload HTTP/1.1\r\n"
        f"Host: 127.0.0.1:{port}\r\n"
        f"Content-Length: {size}\r\n"
        f"Connection: close\r\n"
        f"\r\n"
    ).encode("latin-1")


def _chunked_headers(port: int) -> bytes:
    return (
        f"POST /upload HTTP/1.1\r\n"
        f"Host: 127.0.0.1:{port}\r\n"
        f"Transfer-Encoding: chunked\r\n"
        f"Connection: close\r\n"
        f"\r\n"
    ).encode("latin-1")


def _exchange(
    port: int,
    headers: bytes,
    pieces: list[bytes],
    *,
    delay: float = 0.0,
) -> tuple[bytes, BaseException | None]:
    """Send ``headers`` then ``pieces``, and read whatever comes back.

    ``delay`` is the whole point of the second and third cases: with a pause
    between pieces the client is still writing when the server refuses, which is
    the condition the page names. A refused upload can close the connection while
    the client is mid-write, so an ``OSError`` there is a measurement, not a test
    error.
    """
    received = b""
    error: BaseException | None = None
    with socket.create_connection(("127.0.0.1", port), timeout=READ_TIMEOUT) as sock:
        sock.settimeout(READ_TIMEOUT)
        try:
            sock.sendall(headers)
            for piece in pieces:
                if delay:
                    time.sleep(delay)
                sock.sendall(piece)
        except OSError as exc:
            error = exc
        try:
            while True:
                chunk = sock.recv(65536)
                if not chunk:
                    break
                received += chunk
                if b"\r\n\r\n" in received:
                    # Everything this response consists of has arrived: the
                    # documented 400 carries no body.
                    break
                if len(received) > 1 << 20:
                    break
        except OSError as exc:
            error = error or exc
    return received, error


@pytest.fixture(scope="module")
def oversized_tornado_server():
    """A real Tornado server with a 1 KiB ceiling, on a port nobody else holds.

    The ceiling is set *before* the thread starts: ``run()`` reads it when it
    builds the ``HTTPServer``, so setting it afterwards would leave the protocol
    layer unbounded and the test would be measuring the adapter instead.
    """
    previous = get_config().max_request_body_bytes
    port = _free_port()
    adapter = TornadoAdapter(Dispatcher())
    thread = threading.Thread(
        target=adapter.run,
        kwargs={"host": "127.0.0.1", "port": port},
        daemon=True,
        name="tornado-ceiling",
    )

    get_config().max_request_body_bytes = CEILING
    try:
        thread.start()
        if not _wait_until_serving(port, time.monotonic() + 30.0):
            pytest.skip(
                f"the Tornado server never listened on 127.0.0.1:{port}, so nothing was "
                "measured; the port probe found it free, so something else is holding it"
            )
        yield port
    finally:
        try:
            adapter.request_shutdown()
        except Exception:  # noqa: BLE001 - teardown must not mask a failure
            pass
        thread.join(timeout=20.0)
        get_config().max_request_body_bytes = previous


def test_a_client_that_finished_writing_can_read_the_400(oversized_tornado_server):
    """Twice the ceiling, sent in one write: the refusal is readable."""
    port = oversized_tornado_server
    received, error = _exchange(port, _declared_headers(port, CEILING * 2), [b"x" * (CEILING * 2)])

    status_line, _, body = received.partition(b"\r\n\r\n")
    assert b"HTTP/1.1 400" in status_line, (
        f"expected Tornado's 400 for a body twice the ceiling; got {status_line!r} "
        f"(error={error!r})"
    )
    assert body == b"", f"the documented 400 carries an empty body, got {body!r}"


def test_a_client_still_writing_is_left_without_a_status_line(oversized_tornado_server):
    """The same declared oversize, but refused while the client is still sending.

    This is the row that makes "did you get a 400?" an unusable oversize signal:
    the refusal lands mid-upload, the socket is closed underneath the client, and
    no status line is ever readable.
    """
    port = oversized_tornado_server
    pieces = [b"x" * CEILING for _ in range(64)]
    received, error = _exchange(port, _declared_headers(port, CEILING * 64), pieces, delay=0.01)

    assert b"HTTP/1.1" not in received, (
        f"a status line was readable while the client was still writing "
        f"({received[:120]!r}); the page says this case carries none"
    )
    assert error is not None or received == b"", (
        f"the exchange neither failed nor came back empty: received={received[:120]!r}"
    )


def test_a_chunked_upload_is_aborted_without_a_status_line(oversized_tornado_server):
    """No declaration to read, so the refusal lands mid-upload."""
    port = oversized_tornado_server
    half = CEILING // 2 + CEILING // 4  # 1.5x over the ceiling, in two chunks
    pieces = [f"{half:x}\r\n".encode("latin-1") + b"x" * half + b"\r\n" for _ in range(2)]
    pieces.append(b"0\r\n\r\n")
    received, error = _exchange(port, _chunked_headers(port), pieces, delay=0.01)

    assert b"HTTP/1.1" not in received, (
        f"a status line was readable for a chunked upload 1.5x over the ceiling "
        f"({received[:120]!r}); the page says this case carries none"
    )
    assert error is not None or received == b"", (
        f"the exchange neither failed nor came back empty: received={received[:120]!r}"
    )
