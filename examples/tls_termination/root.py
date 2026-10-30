"""Serve the same application over TLS, configured from the environment.

The framework takes four options and passes them to whichever engine is running, so
the TLS surface does not change when the backend does:

    ssl_certfile      the server certificate (PEM)
    ssl_keyfile       its private key; the two must be given together
    ssl_client_ca     a CA bundle; giving it means client certificates are requested
    ssl_verify_client whether those certificates are checked (default ``True``)

Run it:

    TLS_CERTFILE=server.crt TLS_KEYFILE=server.key \\
    TLS_CLIENT_CA=ca.crt python -m examples.tls_termination

With none of them set the example serves plain HTTP, so it still starts on a machine
that has no certificates -- the point of the demo is what changes when they are set,
and an example that cannot start is an example nobody runs.

The route answers with the scheme it was reached on, which is the cheapest way to see
that TLS really happened rather than being configured and quietly skipped.
"""

import os

from cullinan import application, configure, controller
from cullinan.web import get_api

#: ``None`` when unset: the framework treats "no certificate" as plain HTTP, and
#: treats "a certificate without its key" as a start-up error.
CERTFILE = os.environ.get("TLS_CERTFILE") or None
KEYFILE = os.environ.get("TLS_KEYFILE") or None
CLIENT_CA = os.environ.get("TLS_CLIENT_CA") or None


@controller(url="/api")
class TlsController:
    @get_api(url="/hello")
    def hello(self):
        return {"tls": CERTFILE is not None, "client_ca": CLIENT_CA is not None}


@configure(
    user_packages=["examples.tls_termination"],
    server_port=int(os.environ.get("TLS_PORT", "4443")),
    ssl_certfile=CERTFILE,
    ssl_keyfile=KEYFILE,
    ssl_client_ca=CLIENT_CA,
    # Left at the default: a CA was given, so the certificate is checked. Set this to
    # ``False`` only while migrating -- it asks for a client certificate and accepts
    # an unknown one, which is not a mode to stay in.
    ssl_verify_client=True,
)
@application
def main(): ...


__all__ = ["TlsController", "main"]
