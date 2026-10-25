# Legacy Compatibility Demo (0.90 decorator system)

A runnable record of the decorator surface that 0.90-era applications were built
on: `@service`, `@controller`, `@component`, `Inject` / `InjectByName` / `Lazy`,
and conditional declarations. It exists so the compatibility promise stays
testable rather than remembered — if one of these stops working, this script
stops running.

It is **not** a template for new code. New applications declare one entry method
with `@application` and configure it with `@configure(...)`; see
[minimal_app](../minimal_app/README.md).

## Run it

```bash
python examples/legacy/decorator_demo_090.py
```

It prints the sections it demonstrates and exits. It runs on import by design —
it is a transcript of behaviour, not a server.

## What it demonstrates

| Section | Surface |
|---|---|
| services and controllers | `@service`, `@controller`, `@component` |
| injection forms | `Inject`, `InjectByName`, `Lazy` |
| conditionals | `ConditionalOnClass`, `Conditional` |
| assembly | `ApplicationContext`, `PendingRegistry` |

## When this script fails

That is a compatibility regression, not a broken example. The deprecation policy
puts an announced removal version on each of these surfaces; until that version
arrives, this script is expected to run clean.
