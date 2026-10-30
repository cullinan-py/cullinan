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
| `application.example.json` | a template: the committable form, holding references instead of values |
| `root.py` | `describe()` reads the file; `main()` is the application |

`application.json` contains `"channel": "${EXAMPLE_CHANNEL:general}"`. That is a
reference, not a value: it is resolved from the environment after the file is read,
and falls back to `general` when the variable is not set. A real deployment puts its
secret there and keeps the secret out of the repository.

```bash
EXAMPLE_CHANNEL=alerts python -m examples.config_file
```

## Which of these files git will take

The repository ignores the files the loader would read, because those are the files
that can hold a value. Two shapes are worth telling apart, and the command that
decides it is `git check-ignore`:

```bash
# A local file with your own values: ignored, so `git add .` will not take it.
cp application.example.json application.local.json
git check-ignore -q application.local.json && echo "ignored, as intended"

# The template: trackable, because it holds references and not values.
git check-ignore -q application.example.json || echo "trackable, as intended"
```

- `application*.json` (and the `.toml` / `.yaml` / `.yml` forms) is ignored. A file
  named `application.local.json` next to the executable is the normal place for your
  own values, and it never enters the repository by accident.
- `application*.example.json` is the template: **that** is the shape to commit. Put
  `${VAR}` where a value would go, so the file says where the value comes from
  without containing it.
- The two files this example ships are named by the documentation and are read by an
  explicit path, so they stay tracked — the exemption is per file, not per directory.
  A new `application*.json` dropped into this directory is ignored like anywhere
  else.
- `git add -f` still walks past an ignore rule. Ignoring a file lowers the chance of
  committing a value; it does not make the file uncommittable, which is why the
  repository also reads every `application*` file it can see and reports a plaintext
  value under a sensitive key.

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
