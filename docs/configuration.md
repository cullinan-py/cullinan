title: "Configuration"
slug: "configuration"
module: []
tags: ["docs", "guide", "configuration"]
author: "plumeink"
reviewers: []
status: new
locale: en
translation_pair: "docs/zh/configuration.md"
related_tests: ["tests/core/test_config_file.py", "tests/integration/test_feature_example_matrix.py"]
related_examples: ["examples/config_file"]
estimate_pd: null
last_updated: "2026-10-31"

# Configuration

Cullinan reads project settings from **one configuration file**, not from a `.env`
file and not from a dozen scattered environment variables.

```json
{
  "server_port": 8080,
  "server_host": "0.0.0.0",
  "server_engine": "asgi"
}
```

`application.run(main)` reads it. There is nothing to import and nothing to call.

## Why a file and not `.env`

`.env` is a flat `KEY=VALUE` list. It has no nesting, no types, and no way to say
"this value comes from somewhere else". It also cannot answer the question a
packaged build actually has: **where does this file live, and did it end up inside
the artefact that was shipped?**

A configuration file answers all four, which is why `python-dotenv` — previously the
framework's only runtime dependency — is no longer used. Cullinan now has **no runtime
dependencies**; JSON is read with the standard library.

## File names

| File | When it is read |
|---|---|
| `application.json` | always, when present |
| `application-<profile>.json` | merged **over** the base when `CULLINAN_PROFILE` is set |

`.toml`, `.yaml` and `.yml` are read too, but only when the interpreter or the
environment can parse them — TOML needs Python 3.11+ (or `tomli`), YAML needs
`pyyaml`. When the parser is missing, the error names the package to install instead
of silently loading nothing. JSON needs nothing, so it is the format that always works.

## Where the file is looked for

In order:

1. the path given by `CULLINAN_CONFIG`, or passed as `load_project_config(path=...)`
2. the working directory
3. the directory of the executable that was launched

!!! warning "The installed package is never searched"
    A configuration file inside the installed package would be a bug in two
    directions: it would ship your settings inside the artefact, and a stale copy
    inside the bundle would shadow the file you edited next to the binary. Only the
    two locations above are searched, and a test holds that.

An explicit path that does not exist is an error. Falling back to defaults after
someone named a file would hide a typo until production.

## Precedence

Highest first:

| # | Source | Example |
|---|---|---|
| 1 | argument to `run()` | `run(main, port=9090)` |
| 2 | environment variable | `SERVER_PORT=9090` |
| 3 | `configure(...)` | `@configure(server_port=9090)` |
| 4 | configuration file | `{"server_port": 9090}` |
| 5 | built-in default | `4080` |

A value written in code wins over the file because the file is applied first; an
environment variable wins over both because it is read when the value is used.

## Keep secrets out of the file

A file that is committed, or shipped beside a binary, is not a place for a secret.
**Do not write a value into the file.** What belongs there is safe to paste into an
issue tracker, because sooner or later it ends up in one.

**The file is ignored by default.** `application*.json`, `application*.toml`,
`application*.yaml` and `application*.yml` are in `.gitignore`, so a plain
`git add .` does not commit a file that carries a value. The template form —
`application*.example.json` and the `.toml` / `.yaml` / `.yml` equivalents — stays
trackable: that is the shape meant to be committed, and it holds references instead
of values. An ignore rule is a default rather than a wall (`git add -f` walks past
it), so a repository check reads every `application*` file **twice** — the copy on
disk and the copy in the index — and reports a plaintext value in either one. They
are not the same copy and either can carry a value: the index copy is what a push
would send, and an edit on disk that has not been staged is the next thing that
will be. It reports a value under a sensitive key, or a value whose shape is a
known credential form (a PEM private-key header, an AWS access-key id, a GitHub
token), whatever the key is called.

JSON and TOML are read as documents where the interpreter can parse them — TOML
needs Python 3.11+. Otherwise the file is read line by line and the fallback is
reported, never silent, which is also how a YAML file is always read: a value
written as a multi-line block is reported as undecided rather than quietly passed.

Two consequences worth knowing:

- Naming a file through `CULLINAN_CONFIG` puts it outside every rule here — the
  name can be anything. Keep that file out of version control yourself.
- A file that is already committed stays committed. The rule stops the next `git
  add .`; it does not rewrite history. Deleting the file is not the same as
  removing it: until the deletion is committed — and, for a value that was pushed,
  until history is rewritten — the copy is still there to be fetched. The check
  itself reads the **working tree and the index**; it does not read **`HEAD`**, so a
  value that was committed and later removed from the index is out of scope here.

**Do not `print` it either.** `get_config()` hands back resolved values, so a
`print` or a debug log of the whole document writes the secret into a terminal, a
log file or a CI transcript — a second copy, with none of the protections the first
one had. Print the setting you mean, not the document.

The alternative is to write a reference where a value would go, which two features
support:

```json
{
  "discord": {
    "token": "${DISCORD_TOKEN}",
    "fallback_channel": "${DEFAULT_CHANNEL:general}"
  }
}
```

- `${VAR}` is replaced by the environment variable, after the file is read.
- `${VAR:default}` falls back to `default` when the variable is not set.
- A placeholder with **neither** a value nor a default raises. Substituting an empty
  string would turn a missing setting into one that looks configured — the failure
  would surface later, somewhere less obvious.

### If the file must carry ciphertext

Pass a decryptor. Cullinan does not ship one:

```python
from cullinan.support.config_file import load_project_config

config = load_project_config(decryptor=my_decrypt)   # {"encrypted": "..."} → plain
```

A key that sits beside the ciphertext is not encryption, so the framework does not
pretend otherwise. The key belongs to the deployment — an environment variable, a
secret manager, an HSM — and stays outside the artefact.

## Packaging

Compiling the application raises the cost of reading your code; it does not make
shipped **data** secret. A configuration file placed inside a bundle can be extracted
from that bundle. So the guidance is positional, not cryptographic:

- **Do not bundle the configuration file.** Put it next to the executable, or point
  `CULLINAN_CONFIG` at it. Cullinan never looks inside the package, so a bundler
  configuration that copies it in gains nothing.
- **Let the file hold references, not values.** `${VAR}` keeps the secret in the
  environment where the secret manager put it.
- **Decide per setting whether it must be secret at all.** A port number is not a
  secret; a bot token is. Splitting the file along that line is more effective than
  encrypting all of it.

For how a packaged application resolves its own directories, see
[Packaging](packaging.md) — the same distinction between "where the code is" and
"where the user's data is" applies here.

## Complete example

```json
{
  "server_port": 8080,
  "server_host": "0.0.0.0",
  "server_engine": "tornado",
  "verbose": true,
  "discord": {
    "token": "${DISCORD_TOKEN}"
  }
}
```

```python
from cullinan import application, configure


@configure(user_packages=["myapp"])
@application
def main():
    ...


if __name__ == "__main__":
    main()
```

```bash
CULLINAN_PROFILE=prod DISCORD_TOKEN=... python -m myapp
```

`application-prod.json` in the same directory is merged over `application.json`
before the values are used.

A runnable version lives in [`examples/config_file`](https://github.com/cullinan-py/cullinan/tree/master/examples/config_file).

## Migrating from `.env`

Every key in `.env` has a home in the file, and nested keys are easier to read:

| `.env` | `application.json` |
|---|---|
| `SERVER_PORT=8080` | `{"server_port": 8080}` |
| `DISCORD_TOKEN=abc` | `{"discord": {"token": "${DISCORD_TOKEN}"}}` |
| — | profile switching via `CULLINAN_PROFILE` |

Reading `.env` is no longer supported, and the dependency that provided it has been
removed. If your deployment already exports those variables, nothing needs to change:
environment variables still take precedence over the file.

## Reading the configuration in code

```python
from cullinan.support import get_config

port = get_config().server_port
```

If you want the raw document rather than framework settings:

```python
from cullinan.support.config_file import load_project_config

settings = load_project_config()          # {} when there is no file
```

`load_project_config()` never raises for a missing file — an application without a
configuration file is a valid application. It does raise for a file it cannot parse,
a placeholder it cannot resolve, and an explicit path that does not exist.
