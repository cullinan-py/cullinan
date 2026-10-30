# -*- coding: utf-8 -*-
"""TLS settings, resolved once and translated per engine.

The configuration surface is one set of options (``ssl_certfile``, ``ssl_keyfile``,
``ssl_client_ca``, ``ssl_verify_client``); the two engines want them in different
shapes -- Tornado takes ``ssl_options`` for its ``HTTPServer``, uvicorn takes keyword
arguments on ``Config``. Resolving them here means the pairing rule is stated once, so
Tornado cannot accept a configuration that ASGI refuses.

Three decisions worth knowing:

**Half a key pair is an error, not a downgrade.** A certificate without its key cannot
serve TLS, and carrying on in plain HTTP would leave the operator believing the
connection was encrypted -- the failure would show up as "it works" until someone
looked at the scheme.

**A client CA implies asking for client certificates**, and ``ssl_verify_client``
defaults to ``True``: giving a CA and then not checking the certificate is a
configuration almost nobody wants. The option exists because "request a certificate
and record it without rejecting an unknown one" is a real migration step, and it is
documented as not recommended.

**Nothing here reads files.** The paths are passed through as given; whether they exist
is the server's business, and it reports that far more precisely than this module
could.
"""

from __future__ import annotations

import ssl
from typing import Any, Dict, Optional


def resolve_tls_settings(config: Optional[Any] = None) -> Optional[Dict[str, Any]]:
    """Return the TLS settings, or ``None`` when the application serves plain HTTP.

    Args:
        config: The configuration object to read. Defaults to the global one.

    Raises:
        ValueError: When only one half of the key pair was given, or a client CA was
            given without a server certificate. Both are start-up errors: the process
            must not come up serving something other than what was asked for.
    """
    if config is None:
        from cullinan.support.config import get_config

        config = get_config()

    certfile = getattr(config, 'ssl_certfile', None)
    keyfile = getattr(config, 'ssl_keyfile', None)
    client_ca = getattr(config, 'ssl_client_ca', None)
    verify_client = bool(getattr(config, 'ssl_verify_client', True))

    if not certfile and not keyfile and not client_ca:
        return None

    if bool(certfile) != bool(keyfile):
        given, missing = ('ssl_certfile', 'ssl_keyfile') if certfile else ('ssl_keyfile', 'ssl_certfile')
        raise ValueError(
            f"{given} was given without {missing}: a TLS listener needs both halves of the key "
            "pair. Serving plain HTTP instead would silently downgrade a connection that was "
            "asked to be encrypted."
        )

    if client_ca and not certfile:
        raise ValueError(
            "ssl_client_ca was given without ssl_certfile/ssl_keyfile: client certificates are "
            "part of a TLS listener, not a replacement for one."
        )

    return {
        'certfile': certfile,
        'keyfile': keyfile,
        'client_ca': client_ca,
        'verify_client': verify_client,
    }


def tornado_ssl_options(settings: Dict[str, Any]) -> Dict[str, Any]:
    """Translate resolved settings into Tornado's ``ssl_options`` mapping."""
    options: Dict[str, Any] = {
        'certfile': settings['certfile'],
        'keyfile': settings['keyfile'],
    }
    client_ca = settings.get('client_ca')
    if client_ca:
        options['ca_certs'] = client_ca
        # CERT_REQUIRED is what makes the client certificate mandatory; with
        # ``ssl_verify_client=False`` the certificate is requested and accepted
        # without being checked, which is the documented mirror-image case.
        options['cert_reqs'] = ssl.CERT_REQUIRED if settings['verify_client'] else ssl.CERT_NONE
    return options


def uvicorn_ssl_options(settings: Dict[str, Any]) -> Dict[str, Any]:
    """Translate resolved settings into ``uvicorn.Config`` keyword arguments."""
    options: Dict[str, Any] = {
        'ssl_certfile': settings['certfile'],
        'ssl_keyfile': settings['keyfile'],
    }
    client_ca = settings.get('client_ca')
    if client_ca:
        options['ssl_ca_certs'] = client_ca
        # uvicorn passes this straight to ``SSLContext.verify_mode``, which takes an
        # int: CERT_REQUIRED is 2, CERT_NONE is 0.
        options['ssl_cert_reqs'] = int(ssl.CERT_REQUIRED if settings['verify_client'] else ssl.CERT_NONE)
    return options
