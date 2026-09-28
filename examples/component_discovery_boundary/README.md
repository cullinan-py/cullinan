# Component Discovery Boundary Example

Teaches the **declared vs assembled** boundary: Cullinan discovers components by
importing modules, but it only *assembles* the components whose packages are
listed in `user_packages`. A component that is declared (its decorator ran) but
not assembled is no longer dropped silently — it is reported.

The demo contains two components:

- `examples/component_discovery_boundary/app/services.py` —
  `AssembledService`, declared **inside** `user_packages` → assembled.
- `examples/component_discovery_boundary/outside/services.py` —
  `DroppedService`, declared **outside** `user_packages` → dropped, with a
  `component-declared-not-assembled` warning.

The entry method in `app/root.py` imports the out-of-scope module so its
decorator runs, then restricts discovery to the `app` package:

```python
@configure(user_packages=["examples.component_discovery_boundary.app"])
@application
def main(): ...
```

Run:

```bash
python -m examples.component_discovery_boundary
```

It prints the `declared` / `assembled` / `dropped` sets, the warning, and the
fix. The same information is available programmatically from an application
instance:

```python
from cullinan.application import Application
from examples.component_discovery_boundary.app.root import main

app = Application(main)
app.build()
diff = app.get_declaration_diff()
print(diff.declared, diff.assembled, diff.dropped, diff.dropped_count)
app.uninstall()
```

## Fix the warning

Either add the owning package to `user_packages`:

```python
@configure(
    user_packages=[
        "examples.component_discovery_boundary.app",
        "examples.component_discovery_boundary.outside",
    ]
)
@application
def main(): ...
```

…or move the component into a package that is already listed (preferably to
module top level, so its decorator runs during import).

## Strict mode

The report above never stops startup; that is the default and it stays that way.
An application that would rather not start at all when a declaration never
reaches the container can ask for that:

```python
@configure(
    user_packages=["examples.component_discovery_boundary.app"],
    strict_assembly=True,
)
@application
def main(): ...
```

With `strict_assembly=True` in place, the run above ends with a
`ConfigurationError` instead of a warning. The switch is off by default
(`False`), so nothing changes for applications that do not set it.

The warning is still emitted *before* the failure. The two are not alternatives:
the warning leaves a trace that outlives an upper layer swallowing the
exception, while the exception is what actually stops the start.

`strict_assembly` is about **declarations that were never assembled**. It is a
different setting from `startup_error_policy`, which decides what happens when
a *service cannot be initialised* — the two "strict" names describe unrelated
situations.

### Acknowledging a component you do not want assembled

Some components are deliberately left out. Listing them acknowledges the intent,
so the requirement counts as met while the report stays honest:

```python
@configure(
    user_packages=["examples.component_discovery_boundary.app"],
    strict_assembly=True,
    strict_assembly_excludes=[
        "examples.component_discovery_boundary.outside.services.DroppedService",
    ],
)
@application
def main(): ...
```

Entries are written as `package.module.Component` — exactly the form the report
uses for `dropped`. With the entry above, startup completes again, and the
component is *still* listed in `get_declaration_diff().dropped`: an exclusion
changes the action, not the fact, and nothing is silently assembled behind your
back.

The demo prints all three outcomes — default, strict, and strict with the
acknowledgement — so `python -m examples.component_discovery_boundary` shows the
difference directly.

