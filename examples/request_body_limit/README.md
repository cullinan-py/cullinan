# Request body limit

An upload endpoint with a 1 KiB ceiling, so the refusal is something you can
watch rather than something you have to trust.

## Run it

```bash
python -m examples.request_body_limit
```

```bash
curl -i -X POST --data-binary @<(head -c 512 /dev/zero) http://127.0.0.1:4084/upload/size
# 200 {"bytes": 512}

curl -i -X POST --data-binary @<(head -c 4096 /dev/zero) http://127.0.0.1:4084/upload/size
# ASGI:      413 Content Too Large
# Tornado:   400 Bad Request
```

## What it demonstrates

- `configure(max_request_body_bytes=N)` refuses a body that crosses the ceiling
  **without reading the rest of it**, before any handler runs. Unset (the
  default) means "read whatever arrives".
- The status is **not** the same on both engines, and the difference is real:

  | Engine | Oversized body | Why |
  |---|---|---|
  | ASGI | `413` with a JSON body | the adapter reads in chunks and stops at the limit |
  | Tornado | `400` with an empty body | Tornado's protocol layer (`max_body_size`) refuses before the framework sees the request |

  Both stop early — that is the property that matters — but a client that needs
  to distinguish "too large" from "malformed" has to handle both codes.

## What it does not cover

A request to a path that does not exist still has its body read before the
`404` if no ceiling is configured; with a ceiling, it is refused at the ceiling.
Rejecting before reading would require routing before the body, which the
framework does not do — see `docs/deployment.md` and the ADR behind it.

## Where this is documented

- `docs/deployment.md` → *Request body size* and *What the two engines do not share*
- `tests/web/test_body_limit.py` → the behavioural assertions
