import typer

from querido.cli.cache import app as cache_app
from querido.cli.config import app as config_app
from querido.cli.dist import app as dist_app
from querido.cli.explore import app as explore_app
from querido.cli.inspect import app as inspect_app
from querido.cli.lineage import app as lineage_app
from querido.cli.preview import app as preview_app
from querido.cli.profile import app as profile_app
from querido.cli.search import app as search_app
from querido.cli.serve import app as serve_app
from querido.cli.snowflake import app as snowflake_app
from querido.cli.sql import app as sql_app
from querido.cli.template import app as template_app

app = typer.Typer(
    name="qdo",
    help="CLI data analysis toolkit for SQLite, DuckDB, and Snowflake.",
    no_args_is_help=True,
)

app.add_typer(cache_app, name="cache")
app.add_typer(config_app, name="config")
app.add_typer(dist_app, name="dist")
app.add_typer(explore_app, name="explore")
app.add_typer(inspect_app, name="inspect")
app.add_typer(lineage_app, name="lineage")
app.add_typer(preview_app, name="preview")
app.add_typer(profile_app, name="profile")
app.add_typer(search_app, name="search")
app.add_typer(serve_app, name="serve")
app.add_typer(snowflake_app, name="snowflake")
app.add_typer(sql_app, name="sql")
app.add_typer(template_app, name="template")


def version_callback(value: bool) -> None:
    if value:
        from querido import __version__

        print(f"qdo {__version__}")
        raise typer.Exit()


@app.callback()
def main(
    ctx: typer.Context,
    version: bool = typer.Option(
        False,
        "--version",
        "-V",
        help="Show version and exit.",
        callback=version_callback,
        is_eager=True,
    ),
    show_sql: bool = typer.Option(
        False,
        "--show-sql",
        help="Print rendered SQL to stderr before executing.",
    ),
    output_format: str = typer.Option(
        "rich",
        "--format",
        "-f",
        help="Output format: rich, markdown, json, csv, html, yaml.",
    ),
) -> None:
    """qdo — query, do. Data analysis from your terminal."""
    valid = {"rich", "markdown", "json", "csv", "html", "yaml"}
    if output_format not in valid:
        raise typer.BadParameter(f"--format must be one of: {', '.join(sorted(valid))}")
    ctx.ensure_object(dict)
    ctx.obj["show_sql"] = show_sql
    ctx.obj["format"] = output_format
