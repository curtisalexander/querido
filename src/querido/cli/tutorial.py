"""``qdo tutorial`` — interactive tutorials with National Parks data."""

from __future__ import annotations

import typer

from querido.cli._errors import friendly_errors

app = typer.Typer(help="Interactive tutorials with a National Parks dataset.")


@app.callback(invoke_without_command=True)
@friendly_errors
def tutorial(ctx: typer.Context) -> None:
    """Walk through qdo's features with a National Parks dataset.

    Run ``qdo tutorial explore`` for the core exploration workflow,
    or ``qdo tutorial agent`` for the metadata + AI-assisted SQL workflow.

    Requires DuckDB: install with  uv pip install 'querido[duckdb]'
    """
    if ctx.invoked_subcommand is None:
        print(ctx.get_help())
        raise typer.Exit()


@app.command()
@friendly_errors
def explore(
    lesson: int | None = typer.Option(
        None,
        "--lesson",
        "-l",
        min=1,
        max=15,
        help="Start from a specific lesson number (1-15).",
    ),
    list_lessons: bool = typer.Option(
        False,
        "--list",
        help="List all lessons and exit.",
    ),
    db_path: str | None = typer.Option(
        None,
        "--db",
        help="Path to an existing tutorial database (skip generation).",
    ),
) -> None:
    """Core exploration workflow: catalog, inspect, profile, query.

    Generates a DuckDB database with parks, trails, wildlife sightings,
    and visitor statistics, then guides you through 15 lessons covering
    the full qdo exploration and query workflow.

    Requires DuckDB: install with  uv pip install 'querido[duckdb]'
    """
    if not list_lessons:
        try:
            import duckdb as _duckdb  # noqa: F401
        except ImportError:
            import sys

            print(
                "Error: duckdb is required for the tutorial.\n"
                "Install it with: uv pip install 'querido[duckdb]'",
                file=sys.stderr,
            )
            raise typer.Exit(1) from None

    from querido.tutorial.runner import run_tutorial

    run_tutorial(
        start_lesson=lesson or 1,
        list_only=list_lessons,
        db_path=db_path,
    )


@app.command()
@friendly_errors
def agent(
    lesson: int | None = typer.Option(
        None,
        "--lesson",
        "-l",
        min=1,
        max=13,
        help="Start from a specific lesson number (1-13).",
    ),
    list_lessons: bool = typer.Option(
        False,
        "--list",
        help="List all lessons and exit.",
    ),
    db_path: str | None = typer.Option(
        None,
        "--db",
        help="Path to an existing tutorial database (skip generation).",
    ),
) -> None:
    """Metadata enrichment and AI-assisted SQL workflow.

    Walks through creating metadata templates, enriching them with
    business context, and using that metadata as context for a coding
    agent to generate accurate, schema-aware SQL.

    Requires DuckDB: install with  uv pip install 'querido[duckdb]'
    """
    from querido.tutorial.runner_agent import run_agent_tutorial

    run_agent_tutorial(
        start_lesson=lesson or 1,
        list_only=list_lessons,
        db_path=db_path,
    )
