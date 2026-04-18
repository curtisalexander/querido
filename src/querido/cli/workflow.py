"""``qdo workflow`` — declarative workflows (spec, run, lint, list, show).

Phase 4.1 shipped the spec + bundled examples.  Phase 4.2 adds the
runner, lint, list, and show commands (no CLI sugar / shim yet — that's
Phase 4.4).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import typer

from querido.cli._errors import friendly_errors

app = typer.Typer(help="Declarative workflows (spec, run, lint, list, show).")


@app.command()
@friendly_errors
def spec(
    examples: bool = typer.Option(
        False,
        "--examples",
        help="Emit bundled example workflow YAML files instead of the JSON Schema.",
    ),
) -> None:
    """Print the workflow JSON Schema (default) or bundled examples."""
    from querido.core.workflow import WORKFLOW_SCHEMA, load_examples

    if examples:
        docs = load_examples()
        parts: list[str] = []
        for filename, text in docs.items():
            parts.append(f"# file: {filename}\n{text.rstrip()}\n")
        sys.stdout.write("---\n".join(parts))
        return

    json.dump(WORKFLOW_SCHEMA, sys.stdout, indent=2, sort_keys=False)
    sys.stdout.write("\n")


@app.command("list")
@friendly_errors
def list_cmd() -> None:
    """List every discoverable workflow (project, user, bundled)."""
    from querido.cli._context import get_output_format
    from querido.core.workflow.loader import list_available_workflows

    entries = list_available_workflows()
    fmt = get_output_format()

    if fmt in ("json", "agent"):
        from querido.output.envelope import emit_envelope

        data = [
            {
                "name": e.name,
                "source": e.source,
                "path": str(e.path),
                "description": e.description,
            }
            for e in entries
        ]
        emit_envelope(command="workflow list", data=data)
        return

    if not entries:
        typer.echo("No workflows found.")
        return

    from rich.console import Console
    from rich.table import Table

    table = Table(title="Available workflows")
    table.add_column("name", style="bold")
    table.add_column("source")
    table.add_column("description")
    for e in entries:
        table.add_row(e.name, e.source, e.description)
    Console().print(table)


@app.command()
@friendly_errors
def show(name: str = typer.Argument(..., help="Workflow name or path to a .yaml file.")) -> None:
    """Print the resolved workflow's YAML source."""
    from querido.core.workflow.loader import resolve_workflow

    entry = resolve_workflow(name)
    sys.stdout.write(entry.path.read_text(encoding="utf-8"))


@app.command()
@friendly_errors
def lint(
    target: str = typer.Argument(..., help="Workflow name or path to a .yaml file."),
    connection: str | None = typer.Option(
        None,
        "--connection",
        "-c",
        help=("Optional target connection for schema-aware checks. Must be paired with --table."),
    ),
    table: str | None = typer.Option(
        None,
        "--table",
        "-t",
        help=(
            "Optional target table for schema-aware checks. When paired "
            "with --connection, every --columns/-C value in the workflow "
            "is checked against the table's actual columns."
        ),
    ),
    db_type: str | None = typer.Option(
        None,
        "--db-type",
        help="Database type for --connection (sqlite/duckdb). Inferred from path if omitted.",
    ),
) -> None:
    """Lint a workflow. Exits 1 if any issue is found.

    Pass ``--connection`` and ``--table`` together to enable schema-aware
    checks: every ``--columns`` / ``-C`` value referenced by a step is
    validated against the target table's real columns. Useful after
    ``qdo workflow from-session`` when the draft was captured against a
    different target than you're about to run it on.
    """
    from querido.cli._context import get_output_format
    from querido.core.workflow.lint import lint as run_lint
    from querido.core.workflow.loader import load_workflow_doc, resolve_workflow

    if (connection is None) != (table is None):
        raise typer.BadParameter(
            "--connection and --table must be used together (or neither) for schema-aware lint."
        )

    valid_columns: set[str] | None = None
    if connection is not None and table is not None:
        from querido.config import resolve_connection
        from querido.connectors.base import validate_table_name
        from querido.connectors.factory import create_connector

        validate_table_name(table)
        config = resolve_connection(connection, db_type)
        with create_connector(config) as connector:
            col_dicts = connector.get_columns(table)
            valid_columns = {c["name"] for c in col_dicts}

    entry = resolve_workflow(target)
    doc = load_workflow_doc(entry.path)
    result = run_lint(doc, valid_columns=valid_columns)

    fmt = get_output_format()
    if fmt in ("json", "agent"):
        from querido.output.envelope import emit_envelope

        payload = {
            "ok": result.ok,
            "path": str(entry.path),
            "issues": [i.to_dict() for i in result.issues],
        }
        emit_envelope(command="workflow lint", data=payload)
    else:
        if result.ok:
            typer.echo(f"OK {entry.path}")
        else:
            from rich.console import Console

            console = Console()
            console.print(f"[bold red]{len(result.issues)} issue(s) in {entry.path}:[/bold red]")
            for issue in result.issues:
                console.print(f"  [yellow]{issue.code}[/yellow] {issue.path or '/'}")
                console.print(f"    {issue.message}")
                if issue.fix:
                    console.print(f"    [dim]fix: {issue.fix}[/dim]")

    if not result.ok:
        raise typer.Exit(code=1)


@app.command()
@friendly_errors
def run(
    name: str = typer.Argument(..., help="Workflow name or path to a .yaml file."),
    inputs: list[str] = typer.Argument(  # noqa: B008
        None, help="Inputs as key=value pairs (repeatable, positional)."
    ),
    verbose: bool = typer.Option(
        False,
        "--verbose",
        "-v",
        help="Stream each step's stdout to stderr as it runs.",
    ),
    step_timeout: int | None = typer.Option(
        None,
        "--step-timeout",
        min=0,
        help=(
            "Per-step timeout in seconds. Overrides the workflow's "
            "step_timeout/timeout fields and the QDO_WORKFLOW_STEP_TIMEOUT "
            "env var. 0 = no limit."
        ),
    ),
) -> None:
    """Execute a workflow end-to-end."""
    from querido.cli._context import get_output_format
    from querido.core.workflow.lint import lint as run_lint
    from querido.core.workflow.loader import load_workflow_doc, resolve_workflow
    from querido.core.workflow.runner import StepFailed, WorkflowError, run_workflow

    entry = resolve_workflow(name)
    doc = load_workflow_doc(entry.path)

    lint_result = run_lint(doc)
    if not lint_result.ok:
        raise RuntimeError(
            f"workflow {entry.path} has {len(lint_result.issues)} lint issue(s); "
            "run 'qdo workflow lint' for details."
        )

    parsed_inputs = _parse_kv_inputs(inputs or [])

    try:
        result = run_workflow(
            doc,
            parsed_inputs,
            cwd=Path.cwd(),
            verbose=verbose,
            step_timeout=step_timeout,
        )
    except StepFailed as exc:
        fmt = get_output_format()
        if fmt in ("json", "agent"):
            _emit_step_failure_envelope(exc, workflow=entry.name, fmt=fmt)
            raise typer.Exit(code=1) from exc
        # Non-structured path: dump stderr verbatim and re-raise so
        # friendly_errors renders a human-readable message.
        if exc.stderr:
            sys.stderr.write(exc.stderr)
            if not exc.stderr.endswith("\n"):
                sys.stderr.write("\n")
        raise WorkflowError(str(exc)) from exc

    fmt = get_output_format()
    if fmt in ("json", "agent"):
        from querido.output.envelope import emit_envelope

        data = {
            "outputs": result.outputs,
            "session": result.session,
            "steps": [
                {
                    "id": s.id,
                    # ``run`` is the fully-interpolated, shell-quoted command
                    # that actually executed — agents can copy it verbatim to
                    # reproduce the step outside the workflow (R.17).
                    "run": s.run,
                    "skipped": s.skipped,
                    "exit_code": s.exit_code,
                    "duration": s.duration,
                    "capture": s.capture,
                }
                for s in result.steps
            ],
        }
        emit_envelope(command="workflow run", data=data, extra_meta={"workflow": entry.name})
        return

    if result.outputs:
        import yaml

        sys.stdout.write(yaml.safe_dump(result.outputs, sort_keys=False).rstrip() + "\n")
    else:
        typer.echo(f"Workflow {entry.name!r} completed ({len(result.steps)} step(s)).")


@app.command("from-session")
@friendly_errors
def from_session_cmd(
    session: str = typer.Argument(..., help="Session name recorded under .qdo/sessions/."),
    last: int = typer.Option(
        0,
        "--last",
        help="Only use the last N successful data-command steps (0 = all).",
    ),
    name: str = typer.Option(
        "", "--name", help="Workflow name (slug). Defaults to 'from-<session>'."
    ),
    description: str = typer.Option(
        "", "--description", help="Workflow description. Defaults to a generated note."
    ),
    output: str = typer.Option("", "--output", "-o", help="Write to a file. Defaults to stdout."),
) -> None:
    """Generate a draft workflow YAML from a session's recorded steps."""
    import yaml

    from querido.core.workflow.from_session import from_session

    doc = from_session(
        session,
        last=last if last > 0 else None,
        name=name or None,
        description=description or None,
    )
    text = yaml.safe_dump(doc, sort_keys=False, default_flow_style=False).rstrip() + "\n"

    if output:
        out_path = Path(output)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(text, encoding="utf-8")
        typer.echo(f"Wrote {out_path}")
        return
    sys.stdout.write(text)


def _parse_kv_inputs(items: list[str]) -> dict[str, str]:
    """Parse ``key=value`` positional arguments into a dict."""
    parsed: dict[str, str] = {}
    for item in items:
        if "=" not in item:
            raise ValueError(
                f"input {item!r} must be in 'key=value' form (use quotes if value has spaces)"
            )
        key, _, value = item.partition("=")
        key = key.strip()
        if not key:
            raise ValueError(f"input has empty key: {item!r}")
        parsed[key] = value
    return parsed


#: Cap the stderr tail copied into the step-failure envelope. Real driver
#: errors are a few hundred bytes; this is generous enough to preserve a
#: Python traceback without blowing an agent's context on a runaway log.
#: When the raw stderr exceeds this, the envelope includes
#: ``stderr_truncated: true`` and the stored ``stderr`` field is prefixed
#: with ``…(truncated)…\n`` (see ``_emit_step_failure_envelope``).
_STDERR_TAIL_BYTES = 4096


def _emit_step_failure_envelope(exc, *, workflow: str, fmt: str) -> None:
    """Print a structured step-failure error to stderr.

    Matches the shape of other error payloads (``{error, code, message,
    try_next}``) so agents parsing ``-f json`` / ``-f agent`` can act on
    the failure without scraping stderr. See R.7 in PLAN.md.
    """
    from querido.core.next_steps import for_workflow_step_failed
    from querido.output.envelope import render_agent

    stderr_raw = exc.stderr or ""
    stderr_truncated = len(stderr_raw) > _STDERR_TAIL_BYTES
    if stderr_truncated:
        stderr = "…(truncated)…\n" + stderr_raw[-_STDERR_TAIL_BYTES:]
    else:
        stderr = stderr_raw

    code = "WORKFLOW_STEP_TIMEOUT" if exc.timed_out else "WORKFLOW_STEP_FAILED"
    payload: dict = {
        "error": True,
        "code": code,
        "message": str(exc),
        "workflow": workflow,
        "step_id": exc.step_id,
        "step_cmd": exc.cmd,
        "exit_code": exc.exit_code,
        "stderr": stderr,
        # CC.10: surface truncation so agents don't misread a clipped 4096-byte
        # tail as a complete error.  Omitted (not set to False) when stderr
        # fit entirely; presence-as-signal keeps the payload slim.
    }
    if stderr_truncated:
        payload["stderr_truncated"] = True
    if exc.timed_out:
        payload["timed_out"] = True
        if exc.timeout is not None:
            payload["timeout"] = exc.timeout

    session = exc.session or ""
    if session:
        payload["session"] = session
    payload["try_next"] = for_workflow_step_failed(
        workflow=workflow,
        step_id=exc.step_id,
        step_cmd=exc.cmd,
        session=session,
        timed_out=bool(exc.timed_out),
    )

    if fmt == "agent":
        print(render_agent(payload), file=sys.stderr)
    else:
        print(json.dumps(payload, indent=2), file=sys.stderr)
