# -*- coding: utf-8 -*-
"""What a client actually sees when Tornado refuses an oversized body.

``docs/deployment.md`` makes client-side claims about the Tornado ceiling, and the
server's own answer is unambiguous: `400`, empty body, raised by the protocol layer
before the framework sees the request. What the *client* can read back is a
different question, and it is decided below this project -- by the socket layer's
handling of a reset, and by when the client's ``recv`` lands relative to it.

**The invariant is not "no status line".** An earlier version of this file asserted
the absence of a status line in three of the shapes below. That passed on the
machine it was written on and failed on a Linux runner, where the same three shapes
delivered a complete ``400`` every time: the assertion had pinned one host's timing
as a product guarantee. What holds on both is narrower and worth stating plainly --
**the client never receives a successful answer**. Either the documented refusal
arrives (whole, or cut short by the close but then only as a prefix of it), or the
peer goes away and nothing is read at all. A different status line, a body, or a
hang is a different finding and still fails here.

This file is the executor for those claims: a live Tornado server, a raw socket, and
the send shapes the page describes. Nothing is mocked, so a change to the protocol
layer or to the ceiling's wiring shows up here.

**Timing decides, and there are two ways to lose the answer.** A 64x body sent in
one ``sendall`` is answered with a readable ``400`` because the client had finished
writing -- unless it reads 20 ms later, when the reset has already taken the answer
away. And a body far larger than the connection can buffer is lost even though
nothing about the client is slow. The shapes below cover both paths; the counts live
on the page, with their ``n``, and are labelled as one host's sample rather than a
rate. Renamed in 0.96a12 from ``..._is_left_without_a_status_line`` and friends,
because those names asserted the outcome that turned out to be host-dependent.
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


#: The refusal Tornado sends when it stops reading an oversized body: a status line,
#: an empty header block, no body.
COMPLETE_400 = b"HTTP/1.1 400 Bad Request\r\n\r\n"


def _complete_400(received: bytes) -> tuple[bool, str | None]:
    """Did a *complete* 400 arrive, and if not, which half is missing?

    The two failures are different findings and have to be reported apart. A header
    block that never finished means the response was cut -- the client read part of an
    answer. A header block that finished with another status line means the server
    answered something else entirely. A prefix test conflates them, and worse, passes
    on ``HTTP/1.1 400 Bad Re``, which is a truncated response rather than an answer.
    """
    if not received:
        return False, "no bytes arrived at all"
    header_block, separator, _body = received.partition(b"\r\n\r\n")
    if not separator:
        return False, f"the header block is incomplete ({received[:40]!r})"
    first_line = header_block.split(b"\r\n", 1)[0]
    if first_line != b"HTTP/1.1 400 Bad Request":
        return False, f"the status line is {first_line!r}, which is not a 400 Bad Request"
    return True, None


def _refusal_reason(received: bytes, error: BaseException | None) -> str | None:
    """Why this exchange is *not* a refusal of the oversized body, or ``None``.

    The status line is deliberately not part of the invariant. Whether it survives
    the close is decided below this project -- by the socket layer's handling of a
    reset, and by when the client's ``recv`` lands relative to it. Measured on
    Windows, three of the shapes below destroyed the answer; on a Linux runner the
    same three delivered a complete ``400`` every time. Asserting "no status line"
    therefore asserted one host's timing, not the product's behaviour.

    What holds on both, and is what these tests are actually for: **the client never
    receives a successful answer.** Either the documented refusal arrives -- whole,
    or cut short by the close but then only as a prefix of it -- or the peer goes
    away and nothing is read at all. A different status line, a body, a timeout
    (no answer *and* no close) is a different finding and still fails here.
    """
    if received:
        if not COMPLETE_400.startswith(received):
            return (
                f"the bytes read are neither the documented refusal nor a prefix of it "
                f"({received[:120]!r}); another status line or a body is a different "
                f"finding, not a variation on this one"
            )
        if error is not None and not _peer_went_away(error):
            return (
                f"part of the refusal was read, but the exchange ended with "
                f"{type(error).__name__}, which is neither a clean close nor the peer "
                f"going away"
            )
        return None
    if _peer_went_away(error):
        return None
    return (
        f"nothing was read and the connection neither reset nor aborted "
        f"(error={type(error).__name__ if error else None}); a timeout is a hang, "
        f"not a refusal"
    )


def test_the_400_verdict_rejects_a_truncated_or_absent_response():
    """The verdict, on its own: four shapes a substring test would accept.

    ``b"HTTP/1.1 400" in received`` is true for a 13-byte truncation and for a
    21-byte one, so the two cases that matter most -- a response cut mid-header, and a
    response that never came -- would have been measured as "a 400 arrived". Anyone who
    puts the substring test back finds out here.
    """
    cases = [
        (COMPLETE_400, True, None),
        (b"HTTP/1.1 400", False, "incomplete"),
        (b"HTTP/1.1 400 Bad Re", False, "incomplete"),
        (b"HTTP/1.1 413 Content Too Large\r\n\r\n", False, "not a 400"),
        (b"", False, "no bytes"),
    ]

    for payload, expected_complete, expected_fragment in cases:
        complete, missing = _complete_400(payload)
        assert complete is expected_complete, (payload, complete, missing)
        if expected_fragment is None:
            assert missing is None, (payload, missing)
        else:
            assert missing is not None and expected_fragment in missing, (payload, missing)


def test_the_refusal_verdict_rejects_a_wrong_answer():
    """The narrowed verdict, on its own: the shapes that must not pass as "refused".

    The three live tests below use this verdict, so it needs its own red side --
    otherwise widening it (to "any bytes at all", or to "any exception at all") would
    quietly turn them green against a server that answered ``200`` or hung.
    """
    cases = [
        # received, error, is-a-refusal
        (COMPLETE_400, None, True),
        (COMPLETE_400[:13], None, True),  # cut mid-header, but still only a prefix
        (COMPLETE_400, ConnectionResetError(), True),
        (b"", ConnectionResetError(), True),
        (b"", None, False),  # read nothing, nothing failed: the socket just closed
        (b"", TimeoutError(), False),  # no answer and no close: a hang
        (COMPLETE_400, TimeoutError(), False),  # an answer, then a hang
        (b"HTTP/1.1 200 OK\r\n\r\n", None, False),  # the one outcome that matters most
        (b"HTTP/1.1 413 Content Too Large\r\n\r\n", None, False),
        (COMPLETE_400 + b"body", None, False),  # the documented 400 carries no body
    ]

    for payload, error, expected in cases:
        reason = _refusal_reason(payload, error)
        assert (reason is None) is expected, (payload, error, reason)


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

    complete, missing = _complete_400(received)
    assert complete, (
        f"expected Tornado's 400 for a body twice the ceiling; {missing} (error={error!r})"
    )
    _, _, body = received.partition(b"\r\n\r\n")
    assert body == b"", f"the documented 400 carries an empty body, got {body!r}"


def test_a_client_still_writing_is_refused_mid_upload(oversized_tornado_server):
    """The same declared oversize, but refused while the client is still sending.

    This is the shape that makes "did you get a 400?" an unusable oversize signal --
    not because the status line is always absent, which is what this test used to
    assert and what a Linux runner disproved by delivering a complete ``400`` for
    exactly this shape, but because whether it survives the close is decided by the
    socket layer and by the client's read timing rather than by anything this
    framework controls. What is pinned here is the part that does not move: the
    upload is refused either way, and never answered successfully.
    """
    port = oversized_tornado_server
    pieces = [b"x" * CEILING for _ in range(64)]
    received, error = _exchange(port, _declared_headers(port, CEILING * 64), pieces, delay=0.01)

    reason = _refusal_reason(received, error)
    assert reason is None, (
        f"a refusal that landed mid-upload did not look like one: {reason} "
        f"(received={received[:120]!r}, error={error!r})"
    )


def test_a_client_that_reads_late_is_still_refused(oversized_tornado_server):
    """The refusal is written, and may be taken away by the reset before it is read.

    The least intuitive of the shapes, and the one whose name had to change: on the
    machine this was written on, a 20 ms pause between the last write and the first
    read lost the answer 13 times out of 13. On a Linux runner the same pause kept
    it. So "I finished sending, so I will see the status" is not a rule and "pause,
    so I will not" is not one either -- the pause is a lever on a race, not a switch.
    What is asserted is the invariant the race cannot move: the upload is refused.
    """
    port = oversized_tornado_server
    received, error = _exchange(
        port,
        _declared_headers(port, CEILING * 64),
        [b"x" * (CEILING * 64)],
        read_delay=0.02,
    )

    reason = _refusal_reason(received, error)
    assert reason is None, (
        f"a refusal read 20 ms late did not look like one: {reason} "
        f"(received={received[:120]!r}, error={error!r})"
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

    # The strict "a complete 400 arrives" claim is pinned by
    # ``test_a_client_that_finished_writing_can_read_the_400``, on the shape where it
    # holds on every host measured. Here the point is the *shape* of either outcome,
    # so a truncated read counts as the answer being cut rather than as a wrong answer.
    reason = _refusal_reason(received, error)
    assert reason is None, (
        f"a 4 MiB one-write upload did not look refused: {reason} "
        f"(received={received[:120]!r}, error={error!r})"
    )


def test_a_chunked_upload_is_refused_mid_stream(oversized_tornado_server):
    """No declaration to read, so the refusal lands mid-upload.

    The ceiling is crossed while the body is still streaming, which is why this one
    has no chance to be answered politely -- and on Windows it was not. On Linux the
    ``400`` still arrived, so the assertion is again the shape of the refusal rather
    than the presence or absence of a status line.
    """
    port = oversized_tornado_server
    half = CEILING // 2 + CEILING // 4  # 1.5x over the ceiling, in two chunks
    pieces = [f"{half:x}\r\n".encode("latin-1") + b"x" * half + b"\r\n" for _ in range(2)]
    pieces.append(b"0\r\n\r\n")
    received, error = _exchange(port, _chunked_headers(port), pieces, delay=0.01)

    reason = _refusal_reason(received, error)
    assert reason is None, (
        f"a chunked upload 1.5x over the ceiling did not look refused: {reason} "
        f"(received={received[:120]!r}, error={error!r})"
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
