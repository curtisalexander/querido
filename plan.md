# Query Interruption & Progress Feedback — Implementation Plan

## Overview

Add Ctrl-C query cancellation and elapsed-time progress feedback to both the CLI and web app. Produce a CLI tool-use reference document.

---

## 1. Query Execution Wrapper (`querido/core/runner.py` — new file)

Central module that runs any query in a background thread so the main thread stays responsive to signals.

```python
# Pseudocode
def run_query(connector, fn, *args, **kwargs):
    """Run fn(connector, ...) in a thread; raise QueryCancelled on Ctrl-C."""
```

- Wraps the call in `threading.Thread` with a result/exception container.
- Main thread joins with a short timeout loop so `KeyboardInterrupt` is catchable.
- On interrupt: calls connector-specific cancel (see §2), then raises `QueryCancelled`.
- Returns elapsed wall-clock time alongside the result.

Expose a `QueryCancelled(KeyboardInterrupt)` exception.

## 2. Connector-Level Cancel Support

Add an optional `cancel()` method to each connector. The `Connector` protocol gets a default no-op.

| Connector | Cancel mechanism |
|-----------|-----------------|
| **Snowflake** | `self.conn.cursor().cancel()` or `self.conn.close()` — Snowflake's connector supports cursor-level cancel which sends an abort to the server |
| **DuckDB** | `self.conn.interrupt()` — DuckDB's Python API supports this |
| **SQLite** | `self.conn.interrupt()` — stdlib sqlite3 supports this |

```python
# base.py — add to protocol with a default
def cancel(self) -> None: ...
```

Each concrete connector implements `cancel()` calling the appropriate driver method. This ensures the server-side query actually stops (no orphaned warehouse compute on Snowflake).

## 3. CLI Progress with Elapsed Time

Replace bare `console.status("Loading…")` with a custom status that shows elapsed seconds.

### Approach: Elapsed-Time Status Context Manager (`querido/cli/_progress.py` — new file)

```python
@contextmanager
def query_status(console, message, connector):
    """Show a spinner with elapsed time; cancel query on Ctrl-C."""
```

- Uses `rich.live.Live` or `console.status` with a thread that updates the status text every second: `"Profiling orders… (3s)"`.
- On `KeyboardInterrupt`: calls `connector.cancel()`, prints `"\nQuery cancelled after 3.2s"`, re-raises as `QueryCancelled`.
- On success: the caller can print `"Completed in 3.2s"` to stderr if elapsed > some threshold (e.g., 1s). Short queries stay silent.

### CLI Command Changes

Each command (preview, inspect, profile, dist, search, lineage, snowflake subcommands) replaces:

```python
with console.status(f"Loading…"):
    data = get_preview(connector, table)
```

with:

```python
with query_status(console, f"Loading preview of [bold]{table}[/bold]", connector) as qs:
    data = get_preview(connector, table)
# qs.elapsed is available; print if > 1s
```

### `friendly_errors` Enhancement

Add a `KeyboardInterrupt` / `QueryCancelled` catch to `friendly_errors` so it prints a clean message instead of a traceback, then exits with code 130 (standard for SIGINT).

## 4. Web App — Query Cancellation & Progress

### Server-Side

- Run queries in a background `asyncio` task (or thread via `run_in_executor`) keyed by a request ID.
- Store running query handles in `app.state.running_queries: dict[str, CancelHandle]`.
- Add endpoint: `POST /fragments/cancel/{request_id}` — calls `connector.cancel()` and removes the handle.
- On client disconnect (HTMX abort / `Request.is_disconnected()`), auto-cancel.

### Client-Side (HTMX)

- When a tab request starts, show an elapsed-time counter in the `#tab-content` area with a Cancel button.
- The Cancel button sends `hx-post="/fragments/cancel/{request_id}"`.
- Use a small JS snippet to increment a displayed timer every second.
- On completion, the HTMX swap replaces the timer with results.
- On cancel, swap in a "Query cancelled after Xs" message.

### Implementation Detail

Each fragment endpoint becomes:

```python
@router.get("/preview/{table}")
async def preview_fragment(request: Request, table: str):
    request_id = str(uuid4())
    # register cancel handle
    result = await run_in_executor(lambda: get_preview(connector, table))
    # deregister handle
    return template_response(...)
```

The existing HTMX indicator in `base.html` already shows a spinner. Enhance it to include elapsed time via JS and a cancel button.

## 5. CLI Tool-Use Reference Document (`docs/cli-reference.md` — new file)

A succinct markdown document designed to be fed into a coding agent's context so it knows how to use `qdo` as a tool. Contents:

- **Installation** — `pip install querido` / `uv pip install querido`
- **Connection setup** — `qdo config add` and `connections.toml` format
- **Command reference** — one-liner per subcommand with the most common flags
- **Output formats** — `--format json|csv|markdown` for machine-readable output
- **Piping** — stderr vs stdout separation (spinners on stderr, data on stdout)
- **Exit codes** — 0 success, 1 error, 130 cancelled
- **Examples** — 5-6 concrete command lines showing common workflows

Target: ~80 lines, enough for an agent to use `qdo` without reading source code.

## 6. Files Changed / Created

| File | Action |
|------|--------|
| `src/querido/core/runner.py` | **New** — threaded query runner with cancellation |
| `src/querido/cli/_progress.py` | **New** — elapsed-time status context manager |
| `src/querido/connectors/base.py` | **Edit** — add `cancel()` to protocol |
| `src/querido/connectors/sqlite.py` | **Edit** — implement `cancel()` |
| `src/querido/connectors/duckdb.py` | **Edit** — implement `cancel()` |
| `src/querido/connectors/snowflake.py` | **Edit** — implement `cancel()` |
| `src/querido/cli/_util.py` | **Edit** — handle `QueryCancelled` in `friendly_errors` |
| `src/querido/cli/preview.py` | **Edit** — use `query_status` |
| `src/querido/cli/inspect.py` | **Edit** — use `query_status` |
| `src/querido/cli/profile.py` | **Edit** — use `query_status` |
| `src/querido/cli/dist.py` | **Edit** — use `query_status` |
| `src/querido/cli/search.py` | **Edit** — use `query_status` |
| `src/querido/cli/lineage.py` | **Edit** — use `query_status` |
| `src/querido/web/routes/fragments.py` | **Edit** — async execution with cancel support |
| `src/querido/web/templates/base.html` | **Edit** — enhanced indicator with timer + cancel |
| `src/querido/web/static/app.js` | **Edit** — timer JS |
| `docs/cli-reference.md` | **New** — agent-friendly CLI reference |
| `tests/test_runner.py` | **New** — tests for cancellation logic |

## 7. Implementation Order

1. Connector `cancel()` methods (base + 3 connectors)
2. `core/runner.py` — threaded execution wrapper
3. `cli/_progress.py` — elapsed-time status
4. Update `friendly_errors` for `QueryCancelled`
5. Update all CLI commands to use new progress
6. Web app cancel infrastructure (endpoint, JS, templates)
7. `docs/cli-reference.md`
8. Tests
