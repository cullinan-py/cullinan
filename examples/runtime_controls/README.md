# Runtime controls

One file that sets every knob a deployment usually needs, so you can see each
one take effect instead of reading its name in a signature.

## Run it

```bash
python -m examples.runtime_controls
```

```bash
curl -s http://127.0.0.1:4085/runtime/where
# {"bound": "127.0.0.1:4085", "scanned": "examples.runtime_controls only", "skipped": "examples.minimal_app"}
```

The port in the response is the port the process bound, and it comes from the
`server_port` written in `root.py` — change that line and both move.

You will also see lines like `DEBUG cullinan.web.gateway.router: Route registered:
GET /runtime/where` — that is `verbose` doing its job.

## What it demonstrates

| Option | What it decides here |
|---|---|
| `project_root` | where the project starts, instead of inferring it from the working directory |
| `exclude_packages` | `examples.minimal_app` is importable but not part of this application, so the scanner is told to skip it; with `user_packages` pinned the scan is already narrow, so this option is about the case where it is not |
| `startup_error_policy` | `warn`: a broken component is reported and the server starts anyway. `strict` refuses to start; `ignore` is for debugging only |
| `server_engine` + `asgi_server` | pin the engine and the ASGI server so the example behaves the same on every machine |
| `server_host` + `server_port` | the address that is actually bound — deliberately `127.0.0.1`, never `0.0.0.0` in an example |
| `verbose` | lowers the framework logger to `DEBUG`, so you watch controllers and routes register as the process starts — that registration list is the fastest confirmation of what was picked up |

## One option that is deliberately not here

`root_module` is still in the signature so existing imports keep working, but the
startup path it used to select was removed: passing it raises `ValueError` with
the replacement spelled out. An example cannot demonstrate an option that
refuses to run, and showing it as if it worked would be worse than leaving it
out. The migration is `@application` on an entry function, which every other
example already uses.

## Where this is documented

- `docs/deployment.md` → *Configuration before start* and *What the two engines do not share*
- `tests/integration/test_config_option_coverage.py` → keeps every `configure` option visible in an example
