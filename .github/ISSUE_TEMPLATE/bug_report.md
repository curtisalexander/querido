---
name: Bug report
about: Something in qdo is broken or behaving unexpectedly
labels: bug
---

## What happened

<!-- A short description of the wrong behavior. One or two sentences. -->

## What you expected

<!-- What the correct behavior would have looked like. -->

## How to reproduce

<!--
Minimum commands that reproduce. Prefer a self-contained example so we can run it.
If the bug needs a specific schema, paste `qdo catalog -c <db> -f json` output or a small CREATE/INSERT.
-->

```bash
qdo ...
```

## Environment

- qdo version: <!-- `qdo --version` -->
- OS: <!-- macOS 14.5 / Ubuntu 24.04 / Windows 11 / etc. -->
- Python version: <!-- `python --version` -->
- Install path: <!-- `uv tool install` / `uv pip install` / from source -->
- Optional extras installed: <!-- `duckdb` / `snowflake` / `tui` / none -->
- Backend involved: <!-- sqlite / duckdb / snowflake / parquet -->

## Structured error (if applicable)

<!--
If qdo printed an error, rerun with `-f json` and paste the envelope here.
This gives us the `code`, `try_next`, and context in one block.
-->

```json
```

## Anything else

<!-- Logs, screenshots, or context that might help. -->
