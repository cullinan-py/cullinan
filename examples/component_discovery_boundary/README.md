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
