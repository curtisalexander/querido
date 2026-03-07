import typer

from querido.cli.inspect import app as inspect_app
from querido.cli.preview import app as preview_app
from querido.cli.profile import app as profile_app

app = typer.Typer(
    name="qdo",
    help="CLI data analysis toolkit for SQLite, DuckDB, and Snowflake.",
    no_args_is_help=True,
)

app.add_typer(inspect_app, name="inspect")
app.add_typer(preview_app, name="preview")
app.add_typer(profile_app, name="profile")


def version_callback(value: bool) -> None:
    if value:
        from querido import __version__

        print(f"qdo {__version__}")
        raise typer.Exit()


@app.callback()
def main(
    version: bool = typer.Option(
        False,
        "--version",
        "-V",
        help="Show version and exit.",
        callback=version_callback,
        is_eager=True,
    ),
) -> None:
    """qdo — query, do. Data analysis from your terminal."""
