# Application-level TLS

The same application, served over TLS, with no per-engine code: four options go to
whichever backend is running.

| Option | Meaning |
|---|---|
| `ssl_certfile` | the server certificate, PEM |
| `ssl_keyfile` | its private key — **both or neither** |
| `ssl_client_ca` | a CA bundle; giving it means client certificates are requested |
| `ssl_verify_client` | whether those certificates are checked (`True` by default) |

Two rules are worth stating because they are the ones that bite:

- **Half a key pair is a start-up error, not a fallback to HTTP.** A listener that was
  asked to be encrypted and quietly served plaintext is worse than one that refuses to
  start.
- **`ssl_verify_client=False` asks for a certificate and accepts any.** It exists for a
  migration where the client population cannot all be issued certificates at once. It
  is not a mode to stay in, and it is not a substitute for `ssl_client_ca`.

## Run it

```bash
TLS_CERTFILE=/path/server.crt \
TLS_KEYFILE=/path/server.key \
python -m examples.tls_termination

curl --cacert /path/ca.crt https://127.0.0.1:4443/api/hello
```

Add `TLS_CLIENT_CA=/path/ca.crt` and the server asks for a client certificate:

```bash
TLS_CERTFILE=/path/server.crt TLS_KEYFILE=/path/server.key TLS_CLIENT_CA=/path/ca.crt \
    python -m examples.tls_termination

curl --cacert /path/ca.crt --cert /path/client.crt --key /path/client.key \
     https://127.0.0.1:4443/api/hello      # 200
curl --cacert /path/ca.crt https://127.0.0.1:4443/api/hello   # handshake fails
```

With no variables set the example serves plain HTTP on port 4443 and answers
`{"tls": false}` — it still starts, which is the difference between an example people
run and one they read.

`TLS_PORT` moves the port. The test certificates in `tests/fixtures/tls/` are for the
test suite only and must never be trusted for anything.
