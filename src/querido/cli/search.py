"""``qdo search`` — discover commands from a natural-language intent."""

from __future__ import annotations

import typer

from querido.cli._errors import friendly_errors

app = typer.Typer(help="Find the right qdo command from a natural-language intent.")


@app.callback(invoke_without_command=True)
@friendly_errors
def search(
    intent: str = typer.Argument(..., help="What you want to do, in plain language."),
    limit: int = typer.Option(5, "--limit", min=1, max=20, help="Maximum results to return."),
) -> None:
    """Rank qdo commands against a natural-language intent."""
    from querido.cli._pipeline import dispatch_output
    from querido.cli.overview import _build_payload
    from querido.core.search import search_commands, search_next_steps
    from querido.output.envelope import emit_envelope, is_structured_format

    commands = _build_payload()["commands"]
    result = search_commands(intent, commands, limit=limit)
    steps = search_next_steps(result)

    if is_structured_format():
        emit_envelope(command="search", data=result, next_steps=steps)
        return

    dispatch_output("search", result)
