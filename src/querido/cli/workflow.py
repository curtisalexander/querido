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
) -> None:
    """Lint a workflow. Exits 1 if any issue is found."""
    from querido.cli._context import get_output_format
    from querido.core.workflow.lint import lint as run_lint
    from querido.core.workflow.loader import load_workflow_doc, resolve_workflow

    entry = resolve_workflow(target)
    doc = load_workflow_doc(entry.path)
    result = run_lint(doc)

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
        result = run_workflow(doc, parsed_inputs, cwd=Path.cwd(), verbose=verbose)
    except StepFailed as exc:
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
