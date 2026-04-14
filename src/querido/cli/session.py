"""qdo session — manage agent-workflow sessions.

Sessions are append-only JSONL logs of ``qdo`` invocations stored under
``.qdo/sessions/<name>/``. Set ``QDO_SESSION=<name>`` in your shell to have
every subsequent ``qdo`` call recorded into that session.
"""

from __future__ import annotations

import typer

app = typer.Typer(help="Manage agent-workflow sessions.")


@app.command()
def start(
    name: str = typer.Argument(..., help="Session name (used as directory under .qdo/sessions/)."),
) -> None:
    """Create a new session directory and print the ``export QDO_SESSION`` hint.

    Sessions are nothing more than directories — ``start`` just creates one
    and reminds you to set the environment variable so subsequent ``qdo``
    calls get recorded. No daemon is started.

    \b
    Example:
        qdo session start my-investigation
        export QDO_SESSION=my-investigation
        qdo profile -c mydb -t orders
    """
    from querido.core.session import session_dir

    try:
        dir_ = session_dir(name)
    except ValueError as exc:
        raise typer.BadParameter(str(exc)) from None

    dir_.mkdir(parents=True, exist_ok=True)
    typer.echo(f"Created session directory: {dir_}")
    typer.echo("")
    typer.echo("Activate it with one of:")
    typer.echo(f"  export QDO_SESSION={name}           # bash/zsh")
    typer.echo(f"  set -x QDO_SESSION {name}           # fish")


@app.command(name="list")
def list_cmd() -> None:
    """List session names under ``.qdo/sessions/`` with step counts."""
    from querido.core.session import iter_steps, list_sessions

    names = list_sessions()
    if not names:
        typer.echo("No sessions found under .qdo/sessions/")
        return

    rows: list[tuple[str, int, str]] = []
    for n in names:
        steps = list(iter_steps(n))
        count = len(steps)
        last = steps[-1].get("timestamp", "") if steps else ""
        rows.append((n, count, last))

    width = max(len(n) for n, _, _ in rows)
    for name, count, last in rows:
        suffix = f"  last: {last}" if last else ""
        typer.echo(f"{name.ljust(width)}  {count} step{'s' if count != 1 else ''}{suffix}")


@app.command()
def show(
    name: str = typer.Argument(..., help="Session name to show."),
    limit: int = typer.Option(0, "--limit", "-n", help="Show only the last N steps (0 = all)."),
) -> None:
    """Print a readable summary of the steps in a session."""
    from querido.core.session import iter_steps, session_dir

    dir_ = session_dir(name)
    if not dir_.is_dir():
        raise typer.BadParameter(f"Session not found: {name}")

    steps = list(iter_steps(name))
    if not steps:
        typer.echo(f"Session {name!r} has no steps yet.")
        return

    if limit > 0:
        steps = steps[-limit:]

    typer.echo(f"Session: {name}   ({len(steps)} step{'s' if len(steps) != 1 else ''})")
    typer.echo("")

    for step in steps:
        idx = step.get("index", "?")
        ts = step.get("timestamp", "")
        cmd = step.get("cmd", "")
        args = step.get("args") or []
        duration = step.get("duration", 0.0)
        exit_code = step.get("exit_code", 0)
        rows = step.get("row_count")
        status = "ok" if exit_code == 0 else f"exit={exit_code}"

        rows_part = f"  rows={rows}" if rows is not None else ""
        typer.echo(f"[{idx:>3}] {ts}  qdo {' '.join(args)}")
        typer.echo(f"      {status}  {duration:.2f}s{rows_part}   cmd={cmd}")
