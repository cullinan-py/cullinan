# -*- coding: utf-8 -*-
"""TLS is a handshake, so the test performs one -- on both engines.

A configuration option that is stored, exported and passed along proves nothing about
whether the listener encrypted anything. These cases open a TLS connection to a live
server and check the three things an operator actually cares about:

* a client that trusts the CA gets an answer;
* a client that does **not** trust it fails the handshake -- and fails it *as a
  handshake*, not by finding nothing listening, which is what "TLS was never enabled"
  would look like;
* with a client CA configured, a client certificate is mandatory, and the right one is
  accepted.

The certificates are committed under ``tests/fixtures/tls/`` so the suite does not
depend on an ``openssl`` binary being present, and a handshake is never simulated.
"""

from __future__ import annotations

import http.client
import socket
import ssl
import threading
import time
from pathlib import Path

import pytest

from cullinan.support.config import configure, get_config
from cullinan.transport.adapter.asgi_adapter import ASGIAdapter
from cullinan.transport.adapter.tls import resolve_tls_settings
from cullinan.transport.adapter.tornado_adapter import TornadoAdapter
from cullinan.web.gateway.dispatcher import Dispatcher
from cullinan.web.gateway.router import Router

TLS_DIR = Path(__file__).resolve().parents[1] / "fixtures" / "tls"
CA_CERT = str(TLS_DIR / "ca.crt")
SERVER_CERT = str(TLS_DIR / "server.crt")
SERVER_KEY = str(TLS_DIR / "server.key")
CLIENT_CERT = str(TLS_DIR / "client.crt")
CLIENT_KEY = str(TLS_DIR / "client.key")

TLS_FIELDS = ("ssl_certfile", "ssl_keyfile", "ssl_client_ca", "ssl_verify_client")


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


def _dispatcher() -> Dispatcher:
    router = Router()

    def hello(request):
        return {"hello": "tls"}

    router.add_route("GET", "/hello", handler=hello)
    return Dispatcher(router=router)


def _trusting_context() -> ssl.SSLContext:
    context = ssl.create_default_context(cafile=CA_CERT)
    context.check_hostname = True
    context.verify_mode = ssl.CERT_REQUIRED
    return context


def _untrusting_context() -> ssl.SSLContext:
    """The system trust store: our self-signed CA is not in it."""
    context = ssl.create_default_context()
    context.check_hostname = True
    context.verify_mode = ssl.CERT_REQUIRED
    return context


def _context_with_client_certificate() -> ssl.SSLContext:
    context = _trusting_context()
    context.load_cert_chain(certfile=CLIENT_CERT, keyfile=CLIENT_KEY)
    return context


def _https_get(port: int, context: ssl.SSLContext, path: str = "/hello", timeout: float = 15.0):
    """Return ``(status, body)``; TLS problems propagate as ``ssl.SSLError``."""
    connection = http.client.HTTPSConnection("127.0.0.1", port, context=context, timeout=timeout)
    try:
        connection.request("GET", path)
        response = connection.getresponse()
        return response.status, response.read()
    finally:
        connection.close()


def _set_tls(**values) -> None:
    for name in TLS_FIELDS:
        setattr(get_config(), name, values.get(name))


def _wait_until_ready(port: int, context: ssl.SSLContext, deadline: float) -> bool:
    while time.monotonic() < deadline:
        try:
            status, _ = _https_get(port, context, timeout=3.0)
            if status:
                return True
        except (OSError, ssl.SSLError):
            time.sleep(0.1)
    return False


class _RunningServer:
    """A live server on a free port, with TLS settings applied before it starts.

    The settings go in before the thread starts because both engines read them while
    building their listener: setting them afterwards would leave the listener exactly
    as it was and the test would measure a plain-HTTP server.

    ``readiness`` is the client identity used to decide the server is up. A server that
    demands a client certificate cannot be probed without one -- the probe would fail
    forever and the fixture would report "never started" while the server was fine.
    """

    def __init__(self, engine: str, readiness: ssl.SSLContext, **tls):
        self.engine = engine
        self.readiness = readiness
        self.previous = {name: getattr(get_config(), name) for name in TLS_FIELDS}
        self.port = _free_port()
        _set_tls(**tls)
        adapter_class = TornadoAdapter if engine == "tornado" else ASGIAdapter
        self.adapter = adapter_class(_dispatcher())
        self.thread = threading.Thread(
            target=self.adapter.run,
            kwargs={"host": "127.0.0.1", "port": self.port},
            daemon=True,
            name=f"{engine}-tls",
        )

    def __enter__(self) -> "_RunningServer":
        self.thread.start()
        if not _wait_until_ready(self.port, self.readiness, time.monotonic() + 30.0):
            self.thread.join(timeout=5.0)
            pytest.fail(
                f"the {self.engine} server never completed a TLS handshake on "
                f"127.0.0.1:{self.port}, so nothing was measured"
            )
        return self

    def __exit__(self, *exc_info) -> None:
        try:
            self.adapter.request_shutdown()
        except Exception:  # noqa: BLE001 - teardown must not mask a failure
            pass
        self.thread.join(timeout=20.0)
        for name, value in self.previous.items():
            setattr(get_config(), name, value)


@pytest.fixture(params=["tornado", "asgi"])
def server_with_tls(request):
    with _RunningServer(
        request.param,
        readiness=_trusting_context(),
        ssl_certfile=SERVER_CERT,
        ssl_keyfile=SERVER_KEY,
    ) as server:
        yield server


@pytest.fixture(params=["tornado", "asgi"])
def server_with_client_certificates(request):
    with _RunningServer(
        request.param,
        readiness=_context_with_client_certificate(),
        ssl_certfile=SERVER_CERT,
        ssl_keyfile=SERVER_KEY,
        ssl_client_ca=CA_CERT,
        ssl_verify_client=True,
    ) as server:
        yield server


def test_a_client_that_trusts_the_ca_gets_an_answer(server_with_tls):
    status, body = _https_get(server_with_tls.port, _trusting_context())

    assert status == 200, f"HTTPS GET returned {status}"
    assert b"tls" in body, f"unexpected body from the TLS listener: {body[:200]!r}"


def test_a_client_that_does_not_trust_the_ca_fails_the_handshake(server_with_tls):
    """The failure has to be a certificate failure, not a refused connection.

    "Nothing is listening" and "the certificate is not trusted" are both failures and
    they mean opposite things, so the port is probed with a plain TCP connect first:
    it has to accept, which is what makes the TLS error the actual finding.
    """
    with socket.create_connection(("127.0.0.1", server_with_tls.port), timeout=10.0):
        pass  # the listener is up; whatever fails next is the handshake

    with pytest.raises(ssl.SSLCertVerificationError) as caught:
        _https_get(server_with_tls.port, _untrusting_context())

    assert "CERTIFICATE_VERIFY_FAILED" in str(caught.value).upper() or isinstance(
        caught.value, ssl.SSLCertVerificationError
    )


def test_a_client_without_a_certificate_is_refused(server_with_client_certificates):
    """With a client CA configured, the certificate is not optional.

    The requirement is "no answer", not "a particular exception": TLS 1.3 reports the
    missing certificate after the handshake from the client's point of view, so Tornado
    surfaces it as an ``ssl.SSLError`` and uvicorn as an aborted connection while
    reading. Both are the server refusing; a status is the thing that must not happen.
    The fixture has already proved the listener works with a certificate, so this is
    not measuring a server that failed to start.
    """
    outcome = None
    try:
        status, _ = _https_get(server_with_client_certificates.port, _trusting_context())
        outcome = status
    except (ssl.SSLError, ConnectionAbortedError, ConnectionResetError) as exc:
        outcome = exc

    assert not isinstance(outcome, int), (
        f"a client that presented no certificate was answered {outcome}, so the client "
        "certificate is not being enforced"
    )


def test_a_client_with_the_client_certificate_gets_an_answer(server_with_client_certificates):
    status, body = _https_get(
        server_with_client_certificates.port, _context_with_client_certificate()
    )

    assert status == 200, f"mTLS GET returned {status}"
    assert b"tls" in body


def test_half_a_key_pair_is_refused_instead_of_serving_plain_http():
    """The one configuration that must not degrade quietly."""
    previous = {name: getattr(get_config(), name) for name in TLS_FIELDS}
    try:
        with pytest.raises(ValueError) as caught:
            configure(ssl_certfile=SERVER_CERT)
        assert "ssl_keyfile" in str(caught.value)

        with pytest.raises(ValueError) as caught:
            configure(ssl_keyfile=SERVER_KEY)
        assert "ssl_certfile" in str(caught.value)

        # The same rule on the start-up path, which is what a configuration file
        # goes through -- ``configure()`` is not the only way in.
        _set_tls(ssl_certfile=SERVER_CERT)
        with pytest.raises(ValueError):
            resolve_tls_settings()
    finally:
        for name, value in previous.items():
            setattr(get_config(), name, value)
