# Security Policy

## Reporting a vulnerability

Please report security issues **privately**, through GitHub's private advisory
channel:

<https://github.com/cullinan-py/cullinan/security/advisories/new>

That channel is visible only to the maintainers, and it lets us discuss,
prepare and publish a fix together with you. Please do not open a public issue
for a suspected vulnerability, and please do not include exploit details in a
public discussion thread.

A useful report tells us:

- the Cullinan version (`python -c "import cullinan; print(cullinan.__version__)"`)
  and the Python version;
- which engine you run (`tornado` or `asgi`), if the behaviour is engine-specific;
- the smallest reproduction you can manage, and what you expected instead;
- the impact as you see it — what an attacker gains, and what they need first.

We will acknowledge a report as soon as we are able, keep you informed of the
assessment, and credit you in the release notes unless you ask us not to. This
is a volunteer-maintained project, so we do not promise a fixed response or fix
deadline; we do promise that a report will be read, assessed and answered.

## Supported versions

| Version line | Supported |
|---|---|
| `0.96.x` (current alpha line) | ✅ security fixes |
| `0.95.x` (stable line) | ✅ security fixes |
| `0.94.x` and earlier | ❌ |

The `0.96` line is an alpha series: the public API surface is frozen for
stability purposes (see the API reference), but a pre-release may still change
behaviour where a release note says so. Security fixes are applied to the
current alpha line and, where the defect exists there, to the stable line.

## Scope

In scope — defects in this repository's own code:

- request handling: routing, middleware pipeline, parameter binding, response
  serialisation;
- the framework's security-relevant surfaces: header policy, static-file
  serving and path handling, template rendering entry points;
- dependency injection and lifecycle handling, where a defect lets one
  component reach something it should not;
- packaging and release artefacts: a published wheel or sdist that does not
  match its source.

Out of scope:

- vulnerabilities in third-party dependencies — report those upstream (we will
  still act on the version pin);
- misconfiguration of a deployment, reverse proxy or web server;
- issues that require an already-compromised host or an attacker with
  filesystem access to the process;
- denial of service by request volume, absent a specific algorithmic defect.

## Disclosure

We follow coordinated disclosure: we publish an advisory and a fixed release
together, and we ask that you give us that window before writing publicly. Once
a fix is released, we are happy for you to publish your analysis.
