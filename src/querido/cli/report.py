"""``qdo report`` — generate polished, single-file HTML reports."""

from __future__ import annotations

import typer

from querido.cli._errors import friendly_errors

app = typer.Typer(help="Generate single-file HTML reports.")


@app.command("table")
@friendly_errors
def report_table(
    table: str = typer.Option(..., "--table", "-t", help="Table name."),
    connection: str = typer.Option(
        ..., "--connection", "-c", help="Named connection or file path."
    ),
    db_type: str | None = typer.Option(
        None,
        "--db-type",
        help="Database type (sqlite/duckdb). Inferred from path if omitted.",
    ),
    output: str | None = typer.Option(
        None,
        "--output",
        "-o",
        help="Write the HTML to this file. Without -o, a temp file is opened in your browser.",
    ),
) -> None:
    """Build a hand-off HTML report for a single table.

    Aggregates context, metadata, quality, and join candidates into a
    single self-contained HTML file — no CDN, no JavaScript, print-friendly.
    Suitable for sharing with people who don't have qdo installed.
    """
    from pathlib import Path

    from querido.cli._pipeline import table_command
    from querido.core.report import build_table_report
    from querido.output.report_html import render_table_report

    command = _reconstruct_command(table=table, connection=connection, output=output)

    with table_command(table=table, connection=connection, db_type=db_type) as ctx:
        with ctx.spin(f"Building report for [bold]{ctx.table}[/bold]"):
            report = build_table_report(
                ctx.connector,
                connection,
                ctx.table,
                command=command,
            )

        html_text = render_table_report(report)

    if output:
        out_path = Path(output).expanduser().resolve()
        out_path.write_text(html_text, encoding="utf-8")
        import sys

        print(f"Wrote {out_path}", file=sys.stderr)
        return

    from querido.output.html import open_html

    path = open_html(html_text, prefix=f"qdo-report-{table}-")
    import sys

    print(f"Opened {path}", file=sys.stderr)


def _reconstruct_command(*, table: str, connection: str, output: str | None) -> str:
    """Rebuild the ``qdo report table ...`` invocation for the footer.

    Uses Click's captured argv when available so the footer matches what
    the user actually ran; falls back to a canonical reconstruction when
    called outside the CLI (e.g. from tests).
    """
    import click

    try:
        ctx = click.get_current_context(silent=True)
        while ctx is not None and ctx.parent is not None:
            ctx = ctx.parent
        if ctx is not None and ctx.obj:
            raw = ctx.obj.get("_raw_argv")
            if raw:
                from querido.output.envelope import cmd

                return cmd(["qdo", *raw])
    except (AttributeError, LookupError):
        pass

    parts = ["qdo", "report", "table", "-c", connection, "-t", table]
    if output:
        parts += ["-o", output]
    from querido.output.envelope import cmd

    return cmd(parts)
