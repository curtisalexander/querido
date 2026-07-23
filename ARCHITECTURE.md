# qdo architecture

This document describes the current implementation and its boundaries.
[DIFFERENTIATION.md](./DIFFERENTIATION.md) owns product intent;
[AGENTS.md](./AGENTS.md) owns contributor rules; [PLAN.md](./PLAN.md) owns
current commitments.

qdo is a deterministic persistent-memory layer for data exploration. The CLI
is the public interface, plain files are the durable state, and database engines
own query execution.

## Boundary map

```diagram
┌──────────────────────────────────────────────────────────────┐
│ Public interface                                             │
│ qdo CLI · JSON envelope · metadata/session/bundle file specs │
└──────────────────────────────┬───────────────────────────────┘
                               │
┌──────────────────────────────▼───────────────────────────────┐
│ cli/                                                         │
│ Parse options · resolve user input · connector scope         │
│ progress/errors · call core · select output                  │
└──────────────┬───────────────────────────────┬───────────────┘
               │                               │
┌──────────────▼───────────────┐  ┌────────────▼──────────────┐
│ core/                        │  │ output/                    │
│ Deterministic domain logic  │  │ Rich/JSON/CSV/YAML/HTML   │
│ metadata · safety · policy  │  │ serialization only         │
└──────────────┬───────────────┘  └───────────────────────────┘
               │
┌──────────────▼───────────────┐  ┌───────────────────────────┐
│ connectors/                  │  │ sql/                      │
│ Backend protocol + adapters │◀─│ renderer + templates      │
└──────────────────────────────┘  └───────────────────────────┘
               ▲
┌──────────────┴───────────────┐
│ persistence infrastructure  │
│ config.py · cache.py         │
└──────────────────────────────┘
```

The intended dependency direction is downward:

- `core/` does not import `cli/` or `output/`.
- `connectors/` does not import `cli/`, `core/`, or `output/`.
- `output/` may use small canonical core read models, but must not execute
  queries or make product decisions.
- `cli/` is the composition boundary and may import every lower layer.
- `config.py` and `cache.py` own durable application persistence. They may
  depend on the connector protocol, but never on `cli/`, `core/`, or `output/`.
- `tui/` is a secondary front end over core/connectors; `tutorial/` drives the
  public CLI learning path.

## Repository map

```text
src/querido/
├── cli/          Typer commands and application orchestration
├── core/         backend-neutral deterministic operations and policies
│   ├── next_steps/  deterministic agent suggestion graph
│   └── workflow/    experimental workflow spec, lint, loader, and runner
├── connectors/   Connector protocol and SQLite/DuckDB/Snowflake adapters
├── sql/          Jinja renderer and dialect-specific .sql templates
├── output/       human and machine renderers
├── tui/          optional Textual interface
├── tutorial/     built-in guided datasets and lessons
├── agent_docs/   package location populated from integrations/ at build time
├── config.py     versioned connection and column-set persistence infrastructure
└── cache.py      versioned local SQLite cache infrastructure

integrations/     canonical agent instructions packaged into the wheel
docs/
├── cli-reference.md  complete end-user lookup surface
├── examples/          curated output artifacts
├── research/          dated, uncommitted research with status banners
└── archive/           historical plans and completed reviews
tests/            behavior tests and extensible contract matrices
```

This map stays at directory and responsibility level deliberately. The
filesystem is the source of truth for individual modules; duplicating every
filename here made the old architecture document long and stale.

## Public and internal APIs

### Supported external API

qdo is **CLI-first**. Compatibility treatment applies to:

1. The stable core command names and documented options.
2. JSON envelopes: `{command, data, next_steps, meta}` for scanning commands.
3. Structured error codes and `try_next` records where documented or covered by
   contract tests.
4. Versioned metadata, bundle, config, and session-record formats. Sessions
   remain append-only JSONL rather than requiring a database or service.
5. `querido.__version__`.

The package includes `py.typed` so internal annotations remain useful to
contributors, but importable `querido.core`, `querido.connectors`, and
`querido.output` modules are **not a supported embedding API**. Their names and
signatures may change between minor releases. If real embedding demand appears,
add a small explicit `querido.api` façade rather than treating all internals as
public by accident.

### CLI/application boundary

Command modules should:

1. Parse Typer options and resolve SQL/file/session input.
2. Enter `table_command()` or `database_command()` so connectors always close.
3. Call one or more core operations.
4. Attach a named deterministic next-step rule.
5. Emit through `cli/_pipeline.py`.

They should not implement SQL classification, metadata merge rules, quality
semantics, or backend behavior. For example, `core.query.prepare_query()` is
the single source for destructive classification and effective SQL shared by
query plan, estimate, and execution paths.

### Core boundary

Core operations accept connectors and plain typed values, return dict-like
results, and do not know about Typer, Rich, process exit, connector factories,
or named-connection resolution. Core may read domain files and cache snapshots
through persistence infrastructure, but the CLI owns connector lifecycles and
configuration writes. Safety checks are defense-in-depth: the CLI validates for
good errors, while any core operation that interpolates identifiers or executes
arbitrary SQL validates again so it is safe when called internally.

`core/next_steps/` owns deterministic exploration suggestions. CLI modules may
supply runtime values such as connection and table names; product policy about
what should follow belongs in the next-step package.

### Connector boundary

`connectors/base.py` defines the `Connector` protocol, identifier validation,
quoting helpers, and typed connector errors. Every connector:

- supports context-manager use;
- exposes the full protocol even when a feature is unsupported;
- documents case normalization and deterministic cache keys;
- translates driver exceptions at its boundary;
- imports optional drivers lazily.

SQLite is always available. DuckDB/Parquet and Snowflake are optional extras.
DuckDB and Snowflake can use the Arrow fast path; SQLite returns dictionaries.
Snowflake supports concurrent profile queries, while SQLite and DuckDB remain
serial.

### SQL boundary

Database queries live under `sql/templates/`. The renderer selects a dialect
template and falls back to `common.sql`. Identifiers are validated and quoted
before interpolation; data values use driver parameters. Backend catalog calls
such as SQLite `pragma table_info` and Snowflake `information_schema` queries
remain inside connectors because their mechanisms are backend-specific.

### Output boundary

Core results contain data, not presentation. `cli/_pipeline.py:emit()` is the
single output fork:

- `json` → `output/envelope.py`, with core-owned `next_steps`;
- `rich` → `output/console.py`;
- `html` → `output/html.py`;
- `markdown`, `csv`, and `yaml` → `output/formats.py`.

Progress and diagnostics go to stderr. Results go to stdout. Reports are
single-file artifacts rendered by `output/report_html.py`.

## Primary flows

### Scan and emit

```text
argv
  → cli option/input validation
  → resolve named connection or direct file path
  → create connector in a context manager
  → core operation
  → optional metadata merge/write
  → emit
      → JSON envelope + next_steps
      → or human/text renderer
```

### Persistent-memory loop

```text
context/profile/values/quality
  → derive deterministic facts
  → metadata_write applies provenance and confidence rules
  → .qdo/metadata/<connection>/<table>.yaml
  → later context/quality/catalog reads and merges those facts
  → report or bundle carries the accumulated understanding forward
```

Human-authored fields have `confidence: 1.0` and are never automatically
overwritten. Managed writes create snapshots so `metadata undo` can recover.

### Sessions and workflows

With `QDO_SESSION=<name>`, the root CLI callback records each invocation to
`.qdo/sessions/<name>/steps.jsonl` and stores stdout beside it. There is no
daemon. Session SQL can be reused by `query --from` and `export --from` when the
source step was recorded as structured JSON.

Workflows are YAML files executed as qdo subprocesses. Their boundary is
intentionally separate from core operations: they orchestrate the public CLI,
which keeps workflows honest about what users and agents can invoke. The schema
and recovery behavior remain experimental.

## Pay for what you use

Packaging and imports enforce the same segmentation:

| Capability | Extra | Imported when |
|---|---|---|
| SQLite and core CLI | base install | command requires it |
| DuckDB and Parquet | `duckdb` | connector is created |
| Snowflake and Arrow | `snowflake` | connector is created |
| Textual TUI | `tui` | `qdo explore` runs |

Heavy imports belong inside functions. Root help must render without optional
extras installed. `TYPE_CHECKING` imports are allowed at module scope.

## Contracts and verification

- `_ENVELOPE_CASES` in `tests/test_next_steps.py` covers scanning-command JSON
  envelopes.
- `_READBACK_CASES` in `tests/test_readback_loop.py` covers metadata write/read
  compounding.
- `tests/test_errors.py` covers stable structured error codes.
- Connector tests cover shared protocol behavior; dialect-specific tests stay
  separate where SQL or types differ.
- `tests/test_cli.py` protects qdo-owned root-help grouping and first routes,
  not Typer's generic rendering behavior.

The standard gate is:

```bash
uv run ruff format src/ tests/
uv run ruff check src/ tests/
uv run ty check
uv run pytest
```
