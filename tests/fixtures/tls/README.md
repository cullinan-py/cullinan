# Test-only TLS material

A CA, one server certificate and one client certificate, used by the handshake tests
for `ssl_certfile` / `ssl_keyfile` / `ssl_client_ca` / `ssl_verify_client`.

**These keys are committed on purpose and must never be trusted.** They exist so the
suite can perform a real TLS handshake on a machine with no `openssl` binary and no
`cryptography` package -- generating them at test time would make the tests depend on
a tool CI may not have, and a mocked handshake would prove nothing about the engine.

| File | What it is |
|---|---|
| `ca.crt` | the CA certificate; the server and the client certificate are signed by it |
| `ca.key` | the CA private key (kept only so the set can be regenerated) |
| `server.crt` / `server.key` | server certificate, `subjectAltName = IP:127.0.0.1, DNS:localhost` |
| `client.crt` / `client.key` | client certificate, `extendedKeyUsage = clientAuth` |

Valid for ten years from generation, so the tests do not acquire an expiry date.

## Regenerating

Run from this directory. `openssl` 3.x:

```bash
openssl req -x509 -newkey rsa:2048 -nodes -keyout ca.key -out ca.crt -days 3650 \
    -subj "/CN=cullinan-test-ca" \
    -addext "basicConstraints=critical,CA:TRUE" \
    -addext "keyUsage=critical,keyCertSign,cRLSign"

openssl req -newkey rsa:2048 -nodes -keyout server.key -out server.csr -subj "/CN=127.0.0.1"
printf "subjectAltName=IP:127.0.0.1,DNS:localhost\nbasicConstraints=CA:FALSE\nkeyUsage=digitalSignature,keyEncipherment\nextendedKeyUsage=serverAuth\n" > server.ext
openssl x509 -req -in server.csr -CA ca.crt -CAkey ca.key -CAcreateserial -out server.crt \
    -days 3650 -extfile server.ext

openssl req -newkey rsa:2048 -nodes -keyout client.key -out client.csr \
    -subj "/CN=cullinan-test-client"
printf "basicConstraints=CA:FALSE\nkeyUsage=digitalSignature\nextendedKeyUsage=clientAuth\n" > client.ext
openssl x509 -req -in client.csr -CA ca.crt -CAkey ca.key -CAcreateserial -out client.crt \
    -days 3650 -extfile client.ext

rm -f server.csr client.csr ca.srl server.ext client.ext
```

`subjectAltName` is what a modern client actually checks: without the `IP:127.0.0.1`
entry, a client that trusts the CA still refuses the certificate for the address the
tests connect to, and the failure looks like a TLS bug rather than a fixture bug.

The two `-addext` flags on the CA are equally load-bearing: a CA certificate without
`keyUsage = keyCertSign` is rejected by Python's verifier with "CA cert does not
include key usage extension", which reads like a server problem and is a fixture
problem.
