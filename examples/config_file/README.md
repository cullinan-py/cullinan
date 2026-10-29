# Configuration from a file

A project keeps its settings in `application.json` instead of a `.env` file. This
example shows the three things that file can do: base values, a profile overlay, and
a placeholder resolved from the environment.

## Run it

```bash
python -m examples.config_file
```

It prints what the loader produced, then starts the application.

## What to look at

| File | Role |
|---|---|
| `application.json` | the base document; `server_port` is 4085 |
| `application-prod.json` | merged **over** the base when a profile is named; `server_port` becomes 4086 and only `greeting.text` is overridden — `greeting.channel` survives, because nested tables merge rather than replace |
| `root.py` | `describe()` reads the file; `main()` is the application |

`application.json` contains `"channel": "${EXAMPLE_CHANNEL:general}"`. That is a
reference, not a value: it is resolved from the environment after the file is read,
and falls back to `general` when the variable is not set. A real deployment puts its
secret there and keeps the secret out of the repository.

```bash
EXAMPLE_CHANNEL=alerts python -m examples.config_file
```

## What this example deliberately does not do

It does not put the file inside a package, and it does not encrypt anything.

- Cullinan never searches the installed package for a configuration file, so a copy
  bundled into an artefact cannot shadow the one beside the binary. That is a
  positional defence, and it is the one that actually works.
- A key that travels beside the ciphertext is not encryption, so the framework does
  not ship a cipher. `load_project_config(decryptor=...)` accepts one from the
  deployment, which keeps the key outside the artefact.

See [Configuration](../../docs/configuration.md) for the full rules, including the
precedence order and where the file is searched for.
