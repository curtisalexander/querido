---
name: qdo-workflow-authoring
description: Write declarative qdo workflows — YAML files that compose qdo commands into parameterized, repeatable investigations. Load this when asked to author, edit, debug, or convert a qdo workflow, or when `qdo workflow` appears in the task.
compatibility: Requires qdo >= 0.1.0 (includes `qdo workflow run/lint/list/show/from-session`).
---

# Authoring qdo workflows

A qdo workflow is a **YAML file** that composes `qdo` subcommands into a parameterized, linearly-executed investigation. Workflows are files, not code — only `qdo` invocations, typed inputs, captured step outputs, and simple conditionals are permitted. No shell escape, no embedded Python.

Canonical invocation: **`qdo workflow run <name> [key=value...]`**. Do not expect top-level `qdo <workflow-name>` to work — it does not.

## When to write a workflow

- The same 3+ step investigation gets repeated against different tables or connections.
- A coworker needs to replay your investigation against their database.
- You want an agent-readable artifact of a recurring task.

**Do not** write a workflow for a one-off query. Use `qdo query` directly.

## Minimum viable workflow

```yaml
name: my-slug          # lowercase-hyphen; matches ^[a-z][a-z0-9-]*$
description: One line describing what this does.
version: 1             # positive integer; bump on breaking changes
steps:                 # ordered, must be non-empty
  - id: inspect        # ^[a-z][a-z0-9_]*$; unique across steps
    run: qdo inspect -c ${connection} -t ${table}
    capture: schema    # parses stdout as JSON into ${schema}
```

## File structure

```yaml
name: <slug>
description: <one-line>
version: 1
qdo_min_version: "0.1.0"    # optional; reject runs on older qdo

inputs:                      # caller-supplied values bound as ${name}
  connection:
    type: connection         # string|integer|number|boolean|table|connection
    required: true
    description: Target connection.
  table:
    type: table
    required: true
  top_n:
    type: integer
    default: 10

steps:
  - id: schema
    run: qdo inspect -c ${connection} -t ${table}
    capture: schema          # ${schema} now holds parsed JSON output

  - id: preview
    when: ${schema.data.row_count} > 0  # skipped when false
    run: qdo preview -c ${connection} -t ${table} -r ${top_n}
    capture: rows

outputs:                      # exposed to the caller; optional
  row_count: ${schema.data.row_count}
  sample: ${rows.data.rows}
```

## The `${...}` expression grammar

References: `${name}` or `${name.dotted.path}`. Walks nested dicts and lists (list indices are numeric: `${rows.data.rows.0.id}`).

**Available inside `run`, `when`, and `outputs`:**
- Any input name declared in `inputs:`.
- Any prior step's `id` or `capture` (captured JSON is the value).

**In `when:` only**, comparisons and boolean combinators work:
- `==  !=  <  <=  >  >=`
- `and  or  not`
- bare `${ref}` evaluates as truthy/falsy

**Not supported:** function calls (`len(x)`), attribute access (`obj.method()`), arithmetic (`a + b`), subscript syntax (`a[0]` — use `a.0`), string concatenation. This is deliberate — workflows are declarative.

## Captures and format flags

Captures require JSON output. The runner **auto-injects `-f json`** for any step with a `capture:` key if you don't specify one yourself. Writing `-f json` explicitly is also fine; the runner hoists it to the correct position (right after `qdo`).

```yaml
# Both of these work — runner injects -f json on the second.
- id: a
  run: qdo -f json inspect -c ${connection} -t ${table}
  capture: schema
- id: b
  run: qdo inspect -c ${connection} -t ${table}
  capture: schema
```

## Conditional steps with `when:`

```yaml
- id: join_search
  when: ${diff.data.changed} or ${diff.data.added}  # skip when schemas match
  run: qdo joins -c ${connection} -t ${left} --target ${right}
  capture: joins
```

When a step is skipped, its capture is never set. Any `outputs:` that reference it resolve to `null` rather than aborting the run.

## Destructive writes

Steps that run `qdo query` with a destructive SQL statement (`INSERT`, `UPDATE`, `DELETE`, `DROP`, `CREATE`, `ALTER`, `TRUNCATE`, `MERGE`) **must** set `allow_write: true`:

```yaml
- id: purge
  run: qdo query -c ${connection} --sql "delete from staging where run_id = ${run_id}"
  allow_write: true
```

Lint fails with `WRITE_WITHOUT_ALLOW` if you forget.

## Sessions, automatic

Every `qdo workflow run` executes under a session. If `QDO_SESSION` is already set, the runner inherits it; otherwise it creates `workflow-<name>-<unix_ts>` and each step is appended to `.qdo/sessions/<session>/steps.jsonl` — same shape as any other qdo invocation. No extra flags needed.

## How to author efficiently

1. **Investigate first, codify second.** Run the commands interactively under `QDO_SESSION=<name>` until you like the shape. Then:
   ```bash
   qdo workflow from-session <name> --name <workflow-name> -o .qdo/workflows/<workflow-name>.yaml
   ```
   You'll get a draft with `${connection}` and `${table}` parameterized and a `capture:` on every step. Edit as needed.

2. **Lint before running.** `qdo workflow lint <name>` returns structured issues. `qdo workflow run` auto-lints and refuses to execute dirty workflows.

3. **Dry-run captures mentally.** For each `${ref}` in `run`/`when`/`outputs`, ask: which prior step defined it? If it's from `capture:`, is the dotted path real?

## File locations

Workflows are discovered in this order (first match wins):

1. `./.qdo/workflows/<name>.yaml` — project-scoped, check into git.
2. `<user-config>/qdo/workflows/<name>.yaml` — user-scoped (`~/Library/Application Support/qdo/workflows/` on macOS, `~/.config/qdo/workflows/` on Linux).
3. Bundled with qdo — read `qdo workflow spec --examples`.

List everything available: `qdo workflow list`.

## Patterns

### Three-scan table summary

```yaml
steps:
  - id: schema
    run: qdo inspect -c ${connection} -t ${table}
    capture: schema
  - id: stats
    run: qdo profile -c ${connection} -t ${table} --quick
    capture: stats
  - id: quality
    run: qdo quality -c ${connection} -t ${table}
    capture: quality
```

### Guarded follow-up

```yaml
steps:
  - id: diff
    run: qdo diff -c ${connection} -t ${left} --target ${right}
    capture: diff
  - id: joins
    when: ${diff.data.changed} or ${diff.data.added} or ${diff.data.removed}
    run: qdo joins -c ${connection} -t ${left} --target ${right}
    capture: joins
```

### Fan-in output

```yaml
outputs:
  row_count: ${stats.data.row_count}
  columns: ${schema.data.columns}
  quality_columns: ${quality.data.columns}
```

## Anti-patterns

- **Shell pipelines or redirection.** `run: qdo ... | jq ...` fails lint (`INVALID_RUN`). Every step must start with `qdo <subcommand>`.
- **Arithmetic or function calls in `when`.** `when: len(${schema.data.columns}) > 0` fails. Use `when: ${schema.data.row_count} > 0` or similar on fields that exist.
- **Referencing a capture across a skipped step** without accepting nullability. The downstream step still runs if its own `when` is true; any `${skipped_step.*}` will be unresolved. Prefer aligning `when` conditions or treat outputs as optional.
- **Duplicate step ids.** Lint catches this (`DUPLICATE_STEP_ID`). Use `inspect`, `inspect_2`, `inspect_3` if you really need the same subcommand multiple times.
- **Inputs with no type.** `inputs:` entries require `type:`. Use `string` if you have no better choice.
- **Hardcoding connections.** Parameterize with `${connection}`. A workflow that only runs against `prod` is a query.

## Lint error catalog

| Code | Meaning | Fix |
|------|---------|-----|
| `MISSING_FIELD` | Top-level `name`/`description`/`version`/`steps` absent | Add the field. |
| `UNKNOWN_FIELD` | Stray top-level key | Remove it. Spec forbids extras. |
| `INVALID_NAME` | `name` isn't a lowercase-hyphen slug | Use `^[a-z][a-z0-9-]*$`. |
| `INVALID_DESCRIPTION` | Empty or non-string | Write a one-line description. |
| `INVALID_VERSION` | Not a positive integer | Set to `1` or higher. |
| `INVALID_QDO_MIN_VERSION` | Bad semver | Use e.g. `"0.1.0"`. |
| `INVALID_INPUTS` | `inputs:` not a mapping | Make it a YAML map. |
| `INVALID_INPUT_NAME` | Input name fails `^[a-z][a-z0-9_]*$` | Rename the input. |
| `INVALID_INPUT_TYPE` | Unknown type | Use `string`, `integer`, `number`, `boolean`, `table`, `connection`. |
| `UNKNOWN_INPUT_FIELD` | Extra key inside an input spec | Remove it. Allowed: `type`, `required`, `default`, `description`. |
| `EMPTY_STEPS` | No steps | Add at least one. |
| `INVALID_STEP` | Step isn't a mapping | Use `- id: ...` form. |
| `INVALID_STEP_ID` | Step id fails `^[a-z][a-z0-9_]*$` | Rename it. |
| `DUPLICATE_STEP_ID` | Two steps share an id | Rename one. |
| `UNKNOWN_STEP_FIELD` | Stray key on a step | Allowed: `id`, `run`, `capture`, `when`, `allow_write`. |
| `INVALID_RUN` | `run` doesn't start with `qdo ` | Rewrite as a `qdo <subcommand>` invocation. |
| `INVALID_CAPTURE` | Capture name fails `^[a-z][a-z0-9_]*$` | Rename. |
| `CAPTURE_SHADOWS` | Capture reuses an input or earlier capture name | Pick a unique name. |
| `UNRESOLVED_REFERENCE` | `${ref}` doesn't match any input/capture/id in scope | Declare it as an input or capture it earlier. |
| `WRITE_WITHOUT_ALLOW` | Destructive SQL without `allow_write: true` | Add `allow_write: true` after confirming intent. |
| `INVALID_OUTPUTS` | `outputs:` not a mapping | Make it a YAML map. |
| `INVALID_OUTPUT_NAME` / `INVALID_OUTPUT` | Malformed output | Non-empty string value; `^[a-z][a-z0-9_]*$` key. |

## Cheatsheet

```bash
# Discover
qdo workflow list
qdo workflow spec                    # JSON Schema for YAML authoring
qdo workflow spec --examples         # bundled example workflows
qdo workflow show <name>             # print a workflow's YAML

# Author from a recent investigation
QDO_SESSION=my-work qdo catalog -c mydb
QDO_SESSION=my-work qdo context -c mydb -t orders
qdo workflow from-session my-work --name orders-summary \
  -o .qdo/workflows/orders-summary.yaml

# Validate and run
qdo workflow lint .qdo/workflows/orders-summary.yaml
qdo workflow run orders-summary connection=mydb table=orders
qdo workflow run orders-summary connection=mydb table=orders --verbose
```
