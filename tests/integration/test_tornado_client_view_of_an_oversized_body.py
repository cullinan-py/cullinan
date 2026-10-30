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

**Timing decides, and there are two ways to lose the answer.** Writing this file
corrected the page twice. A 64x body sent in one ``sendall`` is answered with a
readable ``400`` because the client had finished writing -- unless it reads 20 ms
later, when the reset has already taken the answer away. And a body far larger than
the connection can buffer is lost even though nothing about the client is slow. The
shapes below cover both paths; the counts live on the page, with their ``n``.
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
    read_delay: float = 0.0,
) -> tuple[bytes, BaseException | None]:
    """Send ``headers`` then ``pieces``, and read whatever comes back.

    ``delay`` is the point of the "still writing" cases: with a pause between pieces
    the client is still sending when the server refuses. ``read_delay`` is the point
    of the "read late" case: the refusal was written, and whether the client ever
    sees it depends on getting to the socket before the reset does.

    A refused upload can close the connection while the client is mid-write, so an
    ``OSError`` there is a measurement, not a test error.
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
        if read_delay:
            time.sleep(read_delay)
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


#: The exceptions that mean "the peer went away while we were using the socket".
#:
#: ``ConnectionResetError`` is the peer's RST, ``ConnectionAbortedError`` is the local
#: abort Windows reports for the same event, and ``BrokenPipeError`` is what POSIX
#: raises when the write is the operation that notices. All three are the refusal
#: arriving; ``TimeoutError`` is not -- it means neither an answer nor a close, which
#: is a *hang*, and accepting it would let a server that never reacts pass as a server
#: that refused.
#:
#: ⚠️ The boundary is guarded by exactly one test, ``test_the_verdict_rejects_a_timeout``
#: below. **Deleting that test removes this gate**: the tuple would then be free to
#: drift back to "any exception counts", which is the weaker assertion this file was
#: corrected from, and nothing else in the suite would notice.
PEER_WENT_AWAY = (ConnectionResetError, ConnectionAbortedError, BrokenPipeError)


def _peer_went_away(error: BaseException | None) -> bool:
    return isinstance(error, PEER_WENT_AWAY)


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
    assert _peer_went_away(error), (
        f"expected the connection to be reset or aborted, got "
        f"{type(error).__name__ if error else None} (received={received[:120]!r}); a "
        "socket timeout is a hang, not this outcome"
    )


def test_a_client_that_reads_late_loses_the_status_line(oversized_tornado_server):
    """The refusal is written, and then taken away by the reset before it is read.

    This is the least intuitive of the shapes: the client has finished writing, the
    server answered, and the answer is still gone. Measured 13 times out of 13 with a
    20 ms pause between the last write and the first read, so "I finished sending, so
    I will see the status" is not a rule -- it is a race the client usually wins by
    reading immediately.
    """
    port = oversized_tornado_server
    received, error = _exchange(
        port,
        _declared_headers(port, CEILING * 64),
        [b"x" * (CEILING * 64)],
        read_delay=0.02,
    )

    assert b"HTTP/1.1" not in received, (
        f"a status line survived a 20 ms delay before reading ({received[:120]!r}); the "
        "page says this case carries none"
    )
    assert _peer_went_away(error), (
        f"expected the connection to be reset or aborted, got "
        f"{type(error).__name__ if error else None} (received={received[:120]!r}); a "
        "socket timeout is a hang, not this outcome"
    )


def test_a_very_large_single_write_is_a_race(oversized_tornado_server):
    """4 MiB in one write: the client is not slow, and the answer may still be lost.

    This is the case that killed the tidy rule "a large body is fine, writing slowly
    is what costs you the status line". Two independent samples disagree only in the
    ratio: 9 of 13 here, 12 of 13 in the audit, both with the `400` readable the rest
    of the time. A probability is not an assertion, so what is pinned here is the
    *shape* of every outcome: either a `400` and nothing else, or a reset with no
    status line at all -- never another status, never a body, never a hang.
    """
    port = oversized_tornado_server
    received, error = _exchange(port, _declared_headers(port, CEILING * 4096), [b"x" * (CEILING * 4096)])

    if received:
        header_block, separator, body = received.partition(b"\r\n\r\n")
        assert separator, (
            f"only a partial response was read ({received[:120]!r}); a status line counts "
            "as read only when its header block is complete -- a prefix match would pass "
            "on a truncated 'HTTP/1.1 400 Bad Re'"
        )
        first_line = header_block.split(b"\r\n", 1)[0]
        assert first_line == b"HTTP/1.1 400 Bad Request", (
            f"a 4 MiB one-write upload produced {first_line!r}; Tornado refuses with a "
            "400 and nothing else, so either the page or the engine changed"
        )
        assert body == b"", f"the 400 carries an empty body, got {body!r}"
    else:
        assert _peer_went_away(error), (
            f"nothing was read and the connection did not reset or abort (error={error!r}); "
            "the page describes this outcome as a reset"
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
    assert _peer_went_away(error), (
        f"expected the connection to be reset or aborted, got "
        f"{type(error).__name__ if error else None} (received={received[:120]!r}); a "
        "socket timeout is a hang, not this outcome"
    )

def test_the_verdict_rejects_a_timeout():
    """The narrowed verdict, on its own: a timeout is not "the peer went away".

    The previous assertion accepted anything that was not an empty read --
    ``error is not None`` -- and a socket timeout satisfies that. A timeout is the
    shape of a *hang*: no answer and no close. A refused upload never looks like that,
    so letting it pass would have made this file green against a server that had
    stopped reacting altogether.
    """
    for error in (ConnectionResetError(), ConnectionAbortedError(), BrokenPipeError()):
        assert _peer_went_away(error), f"{type(error).__name__} is the peer going away"

    assert not _peer_went_away(TimeoutError()), (
        "a timeout means neither an answer nor a close, which is a hang rather than a "
        "refusal"
    )
    assert not _peer_went_away(None)
