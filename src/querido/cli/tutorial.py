"""``qdo tutorial`` — interactive tutorial with National Parks data."""

from __future__ import annotations

import typer

app = typer.Typer(help="Interactive tutorial with a National Parks dataset.")


@app.callback(invoke_without_command=True)
def tutorial(
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
    """Walk through qdo's features with a National Parks dataset.

    Generates a DuckDB database with parks, trails, wildlife sightings,
    and visitor statistics, then guides you through 15 lessons covering
    the full qdo workflow.

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
